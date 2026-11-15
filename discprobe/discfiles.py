"""DVD single-layer ISO 9660 + Joliet, with one shared sector layout.

All intervals are [start, end), in 2048-byte logical sectors. Files are never
split. The optional legacy identity copies reserve whole DVD ECC units.
No DIS source is used in this implementation.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
from dataclasses import dataclass, field

from . import iso9660 as iso
from .geometry import NOMINAL

BLOCK = 2048
MAX_FILE = 2**32 - 1
MAX_SECTORS = 2295104
# A conservative, optional 5% of sector capacity avoids the least reliable rim.
# This is a policy, not a measured property of any blank. Set 0 to use all of it.
OUTER_MARGIN = .05


def blocks(size):
    return (size + BLOCK - 1) // BLOCK


def radius(lba, geometry=None):
    if geometry is None:
        return NOMINAL['dvd'].radius(lba)
    u, v, bit = (float(geometry[k]) for k in ('u', 'v', 'bit_nm_assumed'))
    if not all(math.isfinite(x) and x > 0 for x in (u, v, bit)):
        raise ValueError('Invalid DVD geometry')
    return bit * 1e-6 * math.sqrt(u*u + v*lba*38688/math.pi)


@dataclass
class Entry:
    relative: str
    source: Path | None
    size: int
    mtime_ns: int
    directory: bool
    parent: str
    primary: bytes = b''
    joliet: bytes = b''
    lba: int = 0
    directory_lba: dict = field(default_factory=dict)
    directory_size: dict = field(default_factory=dict)

    @property
    def when(self):
        when = dt.datetime.fromtimestamp(self.mtime_ns / 1e9, dt.timezone.utc)
        if not 1900 <= when.year <= 2155:
            raise ValueError(f'Timestamp outside ISO 9660 range: {self.relative}')
        return when.replace(tzinfo=None)


def _pack_records(records):
    out = bytearray()
    for record in records:
        left = BLOCK - len(out) % BLOCK
        if len(record) > left:
            out.extend(bytes(left))
        out.extend(record)
    out.extend(bytes((-len(out)) % BLOCK))
    return bytes(out)


@dataclass
class Layout:
    folder: Path
    files_at: str
    writable_sectors: int
    total_sectors: int
    margin: float
    entries: list
    metadata_end: int
    path_tables: dict
    identity_spans: list
    geometry: dict | None
    picture_lba: list

    def is_picture(self, start, end=None):
        end = start + 1 if end is None else end
        return any(a <= start and end <= b for a, b in self.picture_lba)

    def fingerprint(self):
        # Bind export to the guide the user saw. A changed tree, timestamp,
        # geometry or capacity must be checked again before writing an image.
        state = dict(folder=str(self.folder), placement=self.files_at, writable=self.writable_sectors,
                     total=self.total_sectors, margin=self.margin, metadata_end=self.metadata_end,
                     picture=self.picture_lba, identity=self.identity_spans,
                     geometry=([self.geometry[k] for k in ('u','v','bit_nm_assumed')] if self.geometry else None),
                     entries=[[e.relative,e.size,e.mtime_ns,e.directory,e.lba,e.directory_lba,e.directory_size]
                              for e in self.entries])
        return hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()

    def as_dict(self):
        files = [dict(path=e.relative, bytes=e.size, start_lba=e.lba,
                      end_lba_exclusive=e.lba + blocks(e.size), mtime_ns=e.mtime_ns)
                 for e in self.entries if not e.directory]
        occupied = [[0, self.metadata_end]] + [[f['start_lba'], f['end_lba_exclusive']]
                     for f in files if f['bytes']] + self.identity_spans
        merged = []
        for start,end in sorted(occupied):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1],end)
            else:
                merged.append([start,end])
        occupied = merged
        return dict(version=1, layout_sha256=self.fingerprint(), media='dvd', filesystem='ISO 9660 + Joliet', files_at=self.files_at,
                    writable_sectors=self.writable_sectors, total_sectors=self.total_sectors,
                    files_margin=self.margin, margin_sectors=self.writable_sectors-self.total_sectors,
                    metadata_lba=[16, self.metadata_end], metadata_sectors=self.metadata_end-16,
                    system_sectors=16, file_count=len(files), file_bytes=sum(f['bytes'] for f in files),
                    file_sectors=sum(blocks(f['bytes']) for f in files), files=files,
                    occupied_lba=occupied, identity_lba=self.identity_spans,
                    occupied_radius_mm=[[radius(a, self.geometry), radius(b, self.geometry)] for a,b in occupied],
                    margin_radius_mm=([radius(self.total_sectors, self.geometry), radius(self.writable_sectors, self.geometry)]
                                      if self.margin else None),
                    picture_lba=self.picture_lba,
                    picture_radius_mm=[[radius(a, self.geometry), radius(b, self.geometry)] for a,b in self.picture_lba],
                    picture_sectors=sum(b-a for a,b in self.picture_lba))


def plan(folder, files_at, writable_sectors, *, margin=None, geometry=None, identity=False, media='dvd'):
    if media != 'dvd':
        raise ValueError('随盘文件目前只支持 DVD±R 单层 / DVD single-layer only')
    if files_at not in ('inner', 'outer'):
        raise ValueError('files_at must be inner or outer')
    if isinstance(writable_sectors, bool) or not isinstance(writable_sectors, int) or not 32 <= writable_sectors <= MAX_SECTORS:
        raise ValueError(f'DVD writable sectors must be 32..{MAX_SECTORS}')
    margin = (OUTER_MARGIN if files_at == 'outer' else 0.) if margin is None else float(margin)
    if not math.isfinite(margin) or not 0 <= margin < 1 or (files_at == 'inner' and margin != 0):
        raise ValueError('files margin must be 0 <= X < 1 (inner placement requires 0)')
    total = int(writable_sectors * (1-margin)) // 16 * 16 if margin else writable_sectors
    radius(total, geometry)  # validate before scanning
    folder = Path(os.path.abspath(folder))
    if str(folder).startswith(('\\\\', '//')) or folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
        raise ValueError('Use a local folder, without links or junctions')
    if not folder.is_dir():
        raise ValueError(f'文件夹不存在 / folder not found: {folder}')
    entries = [Entry('', folder, 0, folder.stat().st_mtime_ns, True, '')]
    # Breadth-first order makes ISO path-table parents precede children.
    directories = [entries[0]]
    for directory in directories:
        used = set()
        for child in sorted(directory.source.iterdir(), key=lambda p: p.name):
            # Do not follow links/reparse points into another tree.
            if child.is_symlink() or getattr(child, 'is_junction', lambda: False)():
                raise ValueError(f'Links/junctions are unsupported: {child.name}')
            stat = child.stat()
            is_dir = child.is_dir()
            if not is_dir and not child.is_file():
                raise ValueError(f'Not a regular file: {child.name}')
            if not is_dir and stat.st_size > MAX_FILE:
                raise ValueError(f'单个文件超过 4 GiB−1 / file exceeds 4 GiB-1: {child.name}')
            name = child.name
            if name.upper() == 'DISCPROBE.ID' and directory.relative == '':
                raise ValueError('DISCPROBE.ID is reserved for disc identity')
            try:
                encoded = name.encode('utf-16-be')
            except UnicodeError as exc:
                raise ValueError(f'Invalid Joliet filename: {name}') from exc
            if len(encoded) > 128 or any(ord(c) > 0xffff for c in name):
                raise ValueError(f'Joliet names require at most 64 UCS-2 characters: {name}')
            stem = re.sub('[^A-Z0-9_]', '_', name.upper())[:24] or '_'
            alias, index = stem, 0
            while alias in used:
                index += 1
                alias = stem[:24] + '_' + str(index)
            used.add(alias)
            rel = (Path(directory.relative) / name).as_posix()
            entry = Entry(rel, child, 0 if is_dir else stat.st_size, stat.st_mtime_ns, is_dir,
                          directory.relative, alias.encode() + (b'' if is_dir else b';1'),
                          encoded + (b'' if is_dir else ';1'.encode('utf-16-be')))
            entry.when  # refuse unsupported dates early
            entries.append(entry)
            if is_dir:
                directories.append(entry)
    if len(directories) > 65535:
        raise ValueError('ISO path tables support at most 65535 directories')
    slots = []
    if identity:
        from . import discid
        slots = [[x//16*16, (x//16+1)*16] for x in discid.positions(total)]
        entries.append(Entry('DISCPROBE.ID', None, discid.SIZE, entries[0].mtime_ns, False, '',
                             b'DISCPROBE.ID;1', 'DISCPROBE.ID;1'.encode('utf-16-be'), discid.LBA))
    cursor = 32 if identity else 19
    tables = {}
    for tree in ('primary', 'joliet'):
        length = sum(8 + (1 if not d.relative else len(getattr(d, tree))) +
                     ((1 if not d.relative else len(getattr(d, tree))) % 2) for d in directories)
        tables[tree] = (cursor, cursor+blocks(length), length)
        cursor += 2*blocks(length)
        for d in directories:
            children = [e for e in entries[1:] if e.parent == d.relative]
            records = [iso._dir_record(b'\0', d.when), iso._dir_record(b'\1', d.when)]
            records += [iso._dir_record(getattr(e, tree), e.when, size=e.size, directory=e.directory) for e in children]
            size = len(_pack_records(records))
            d.directory_lba[tree], d.directory_size[tree] = cursor, size
            cursor += blocks(size)
    metadata_end = cursor
    if any(a < metadata_end and b > 32 for a,b in slots):
        raise ValueError('Filesystem metadata overlaps fixed disc identity slots; disable disc identity')
    files = [e for e in entries if not e.directory and e.source is not None]
    cursor = metadata_end if files_at == 'inner' else total
    for e in (files if files_at == 'inner' else reversed(files)):
        n = blocks(e.size)
        if files_at == 'inner':
            while any(cursor < b and cursor+n > a for a,b in slots):
                cursor = max(b for a,b in slots if cursor < b and cursor+n > a)
            e.lba, cursor = cursor, cursor+n
        else:
            while any(cursor-n < b and cursor > a for a,b in slots):
                cursor = min(a for a,b in slots if cursor-n < b and cursor > a)
            e.lba, cursor = cursor-n, cursor-n
        if e.lba < metadata_end or e.lba+n > total:
            raise ValueError(f'文件装不下 / files do not fit: {e.relative}; need {sum(blocks(x.size) for x in files)} file sectors + {metadata_end} system/metadata sectors, have {total}')
    # One main annulus; the identity's scattered copies carve small protected gaps.
    low = cursor if files_at == 'inner' else metadata_end
    high = total if files_at == 'inner' else cursor
    picture = []
    for a,b in sorted(slots):
        if b <= low or a >= high:
            continue
        if low < a:
            picture.append([low, a])
        low = max(low, b)
    if low < high:
        picture.append([low, high])
    if metadata_end > total:
        raise ValueError(f'Filesystem metadata does not fit: {metadata_end} > {total} sectors')
    return Layout(folder, files_at, writable_sectors, total, margin, entries, metadata_end, tables, slots, geometry, picture)


def metadata(layout, volume_id='DISCPROBE_FILES'):
    entries = layout.entries
    dirs = [e for e in entries if e.directory]
    by_path = {e.relative: e for e in dirs}
    result = {}
    now = entries[0].when
    for tree, kind in (('primary', 1), ('joliet', 2)):
        little, big, length = layout.path_tables[tree]
        pvd = bytearray(iso.sectors(layout.total_sectors, volume_id)[16])
        pvd[0] = kind
        if kind == 2:
            pvd[8:40] = 'DISC-PROBE'.ljust(16).encode('utf-16-be')
            pvd[40:72] = volume_id[:16].ljust(16).encode('utf-16-be')
            pvd[88:120] = b'%/E' + bytes(29)
        pvd[132:140] = iso._both32(length)
        pvd[140:144], pvd[148:152] = struct.pack('<I', little), struct.pack('>I', big)
        pvd[156:190] = iso._dir_record(b'\0', now, dirs[0].directory_lba[tree], dirs[0].directory_size[tree])
        result[16 if kind == 1 else 17] = bytes(pvd)
        for endian, lba in (('<', little), ('>', big)):
            data = bytearray()
            for d in dirs:
                name = getattr(d, tree) if d.relative else b'\0'
                parent = dirs.index(by_path[d.parent])+1 if d.relative else 1
                data += bytes([len(name), 0]) + struct.pack(endian+'IH', d.directory_lba[tree], parent) + name
                if len(name) % 2:
                    data += b'\0'
            data += bytes((-len(data)) % BLOCK)
            result.update({lba+i: bytes(data[i*BLOCK:(i+1)*BLOCK]) for i in range(blocks(len(data)))})
        for d in dirs:
            parent = by_path[d.parent]
            records = [iso._dir_record(name, node.when, node.directory_lba[tree], node.directory_size[tree])
                       for name,node in ((b'\0', d), (b'\1', parent))]
            children = [e for e in entries[1:] if e.parent == d.relative]
            for e in sorted(children, key=lambda e: getattr(e, tree)):
                records.append(iso._dir_record(getattr(e, tree), e.when,
                               e.directory_lba[tree] if e.directory else e.lba,
                               e.directory_size[tree] if e.directory else e.size, e.directory))
            data = _pack_records(records)
            result.update({d.directory_lba[tree]+i: data[i*BLOCK:(i+1)*BLOCK] for i in range(blocks(len(data)))})
    result[18] = bytes([255])+b'CD001'+bytes([1])+bytes(BLOCK-7)
    return result


def write_files(path, layout, identity=None):
    """Overlay the planned metadata and files; never write a pattern sector."""
    hashes = {}
    with open(path, 'r+b') as target:
        for lba,data in metadata(layout).items():
            target.seek(lba*BLOCK)
            target.write(data)
        # ISO system area is reserved too.
        target.seek(0)
        target.write(bytes(16*BLOCK))
        for e in layout.entries:
            if e.directory or e.source is None:
                continue
            before = e.source.stat()
            if (before.st_size, before.st_mtime_ns) != (e.size, e.mtime_ns):
                raise ValueError(f'Source changed since layout: {e.relative}')
            h = hashlib.sha256()
            target.seek(e.lba*BLOCK)
            with e.source.open('rb') as source:
                left = e.size
                while left:
                    data = source.read(min(left, 1024*1024))
                    if not data:
                        raise ValueError(f'Source shortened: {e.relative}')
                    target.write(data)
                    h.update(data)
                    left -= len(data)
                if source.read(1):
                    raise ValueError(f'Source grew: {e.relative}')
            after = e.source.stat()
            if (after.st_size, after.st_mtime_ns) != (e.size, e.mtime_ns):
                raise ValueError(f'Source changed during copy: {e.relative}')
            target.write(bytes((-e.size) % BLOCK))
            hashes[e.relative] = h.hexdigest()
        if identity is not None:
            from . import discid
            for index,lba in enumerate(discid.positions(layout.total_sectors)):
                target.seek(lba*BLOCK)
                target.write(discid.encode_copy(identity, index))
    return hashes


def add_arguments(parser, *, layout_only=False):
    import argparse
    parser.add_argument('--files', required=layout_only, help='local folder to include (DVD single-layer)')
    parser.add_argument('--files-at', choices=('inner', 'outer'), default='inner')
    parser.add_argument('--files-margin', type=float, help='outer safety fraction; default 0.05 outer, 0 inner')
    parser.add_argument('--writable-sectors', type=int, help='blank writable capacity; otherwise measured geometry capacity')
    parser.add_argument('--files-plan-sha256', help=argparse.SUPPRESS)


def command(args):
    geometry = None
    if args.geo:
        # Resolve the same fit as image, without touching a drive.
        from .__main__ import _geo_fit
        import contextlib
        import sys
        with contextlib.redirect_stdout(sys.stderr):
            geometry = _geo_fit(args, 'dvd')
    total = args.writable_sectors or (geometry or {}).get('capacity_sectors') or (geometry or {}).get('total_sectors')
    if not total:
        import sys
        sys.exit('Give --writable-sectors from blank info or a geometry with capacity_sectors')
    try:
        result = plan(args.files, args.files_at, int(total), margin=args.files_margin, geometry=geometry,
                      identity=getattr(args, 'disc_id', False) or bool(getattr(args, 'disc_id_code', None)))
    except ValueError as exc:
        import sys
        sys.exit(str(exc))
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))


def clip_design(design, layout):
    """The preview and coverage check show the same annuli used by the writer."""
    import numpy as np
    out = design.copy()
    coords = (np.arange(len(design)) + .5) * (120 / len(design)) - 60
    ranges = layout.as_dict()['picture_radius_mm']
    for start in range(0, len(design), 128):
        r = np.hypot(coords[None, :], coords[start:start+128, None])
        keep = np.zeros(r.shape, bool)
        for a,b in ranges:
            keep |= (r >= a) & (r < b)
        out[start:start+128][~keep] = 0
    return out
