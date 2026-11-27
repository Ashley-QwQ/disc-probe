"""Bounded filesystem and content probes for checkburn's read-only sector reader."""
from pathlib import PurePosixPath

import numpy as np

from . import bd, cd, content, dvd

SECTOR = 2048
MAX_ROOT = 128 * SECTOR
FILE_SUFFIXES = {'.iso', '.img', '.bin', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff'}


def _record(data):
    if len(data) < 34 or data[0] != len(data) or not 0 < data[32] <= len(data) - 33:
        raise ValueError('invalid ISO directory record')
    lba, size = int.from_bytes(data[2:6], 'little'), int.from_bytes(data[10:14], 'little')
    if lba != int.from_bytes(data[6:10], 'big') or size != int.from_bytes(data[14:18], 'big'):
        raise ValueError('ISO endian copies disagree')
    return lba + data[1], size, bool(data[25] & 2), data[33:33 + data[32]]


def filesystem(read, end, start=0):
    """Latest data session's ISO 9660 / Joliet root. LBA extents are disc absolute."""
    primary, joliet, udf = None, None, False
    try:
        for lba in range(start + 16, min(start + 48, end)):
            data = read(lba, 1)
            if data[1:6] in (b'NSR02', b'NSR03', b'BEA01'):
                udf = True
            if data[1:7] != b'CD001\x01':
                if lba == start + 16 or primary is not None:
                    break
                continue
            if data[0] == 1:
                primary = data
            if data[0] == 2 and data[88:91] in (b'%/@', b'%/C', b'%/E'):
                joliet = data
            if data[0] == 255:
                break
        descriptor = joliet or primary
        if descriptor is None:
            return dict(status='unsupported' if udf else 'absent', format='UDF' if udf else None, entries=[])
        root, size, directory, _ = _record(descriptor[156:190])
        count = (size + SECTOR - 1) // SECTOR
        if not directory or not 0 < size <= MAX_ROOT or root < 16 or root + count > end:
            raise ValueError('invalid or oversized ISO root')
        entries = []
        # Read in small blocks so the same route works with transports that limit transfers.
        for first in range(0, count, 16):
            raw = read(root + first, min(16, count - first))
            for position in range(0, len(raw), SECTOR):
                sector = raw[position:min(position + SECTOR, size - first * SECTOR)]
                offset = 0
                while offset < len(sector) and sector[offset]:
                    stop = offset + sector[offset]
                    lba, length, is_dir, name = _record(sector[offset:stop])
                    offset = stop
                    if name in (b'\x00', b'\x01'):
                        continue
                    decoded = name.decode('utf-16-be' if joliet else 'ascii')
                    name, separator, version = decoded.rpartition(';')
                    if not separator or not version.isdigit():
                        name = decoded
                    last = lba + (length + SECTOR - 1) // SECTOR
                    if (not name or '/' in name or '\\' in name or name in ('.', '..')
                            or length and (lba < 16 or last > end)):
                        raise ValueError('invalid ISO name or extent')
                    entries.append(dict(name=name, directory=is_dir, lba=lba, sectors=last - lba))
                    if len(entries) > 128:
                        return dict(status='large_root', format='Joliet' if joliet else 'ISO 9660', entries=[])
        layout = 'Joliet' if joliet else 'ISO 9660'
        return dict(status='read', format=layout, entries=entries, root_end=root + count)
    except (OSError, ValueError) as exc:
        return dict(status='unavailable', format=None, entries=[], error=str(exc))


def _views(media, lba, raw):
    if media == 'dvd':
        return [raw ^ dvd.MASKS[dvd.preset_index(lba)]]
    if media == 'cd':
        return [raw ^ cd.SCRAMBLE[offset:offset + SECTOR] for offset in cd.SECTOR_LAYOUTS.values()]
    if media == 'bd':
        return [raw ^ bd.masks(np.array([lba]))[0]]
    return []


def _repeats(raw):
    if not np.any(raw):
        return False
    counts = np.bincount(raw, minlength=256)
    if counts.max() >= .90 * len(raw):
        return True
    if np.count_nonzero(counts) > 64:
        return False
    return any(np.mean(raw[period:] == raw[:-period]) >= .95 for period in range(1, 33))


def probe(read, end, media, *, start=0, audio=False):
    root = (dict(status='audio', format=None, entries=[]) if audio else filesystem(read, end, start))
    entries = root['entries']
    files = [e for e in entries if e['name'].casefold() != 'discprobe.id']
    first = max(start + (0 if audio else 32), root.get('root_end', 0))
    ranges = [(first, end)] if first < end else []
    # Files can look random or can themselves contain a whole picture ISO. Draw
    # samples from the recorded area outside file extents before classifying it.
    for entry in entries:
        left, right = entry['lba'], entry['lba'] + entry['sectors']
        remaining = []
        for a, b in ranges:
            if b <= left or a >= right:
                remaining.append((a, b))
            else:
                if a < left:
                    remaining.append((a, left))
                if b > right:
                    remaining.append((right, b))
        ranges = remaining
    # Allocate probes across the remaining lengths, including the last sector.
    size = sum(b - a for a, b in ranges)
    indexes = np.linspace(0, size - 1, min(24, size), dtype=int).tolist()
    random = patterned = read_errors = 0
    for a, b in ranges:
        for index in (i for i in indexes if i < b - a):
            lba = a + index
            try:
                data = read(lba, 1)
            except OSError:
                read_errors += 1
                continue
            raw = np.frombuffer(data, dtype=np.uint8)
            recorded = [raw] if audio else _views(media, lba, raw)
            if (audio or np.any(raw) and not _repeats(raw)) and any(_repeats(view) for view in recorded):
                patterned += 1
            elif not audio and (content.is_random(lba, data) if media == 'dvd' else
                                content._spread(raw) and all(content._spread(view) for view in recorded)):
                random += 1
        indexes = [i - (b - a) for i in indexes if i >= b - a]

    if patterned >= 2:
        kind = 'pattern'
    elif files or root['status'] == 'large_root':
        kind = 'files'
    elif root['status'] in ('read', 'absent') and random >= 2 and random >= .9 * (min(24, size) - read_errors):
        kind = 'random'
    else:
        kind = 'unknown'
    file_copy = None
    if kind in ('random', 'pattern') or root['status'] == 'read' and not audio:
        file_copy = (kind == 'files' and 1 <= len(files) <= 8 and not read_errors and not patterned
                     and all(not e['directory'] and PurePosixPath(e['name']).suffix.casefold() in FILE_SUFFIXES
                             for e in files))
        if kind == 'files' and (read_errors or patterned):
            file_copy = None
    return dict(kind=kind, filesystem=root, files=[e['name'] for e in files], image_as_file=file_copy,
                samples=dict(total=min(24, size), random=random, pattern=patterned, unreadable=read_errors))
