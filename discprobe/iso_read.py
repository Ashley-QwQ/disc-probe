"""Independent read-only ISO 9660/Joliet directory walker (no writer imports)."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct


def read_tree(path, *, joliet=True, hashes=False, directories=False):
    size = Path(path).stat().st_size
    result, seen = {}, set()
    with open(path, 'rb') as stream:
        def read(lba, length):
            if lba < 0 or length < 0 or lba*2048+length > size:
                raise ValueError('ISO extent exceeds image')
            stream.seek(lba*2048)
            data = stream.read(length)
            if len(data) != length:
                raise ValueError('Truncated ISO')
            return data
        descriptor = None
        for sector in range(16, min(size//2048, 256)):
            data = read(sector, 2048)
            if data[1:7] != b'CD001\x01':
                raise ValueError('Invalid ISO volume descriptor')
            if data[0] == (2 if joliet else 1) and (not joliet or data[88:91] in (b'%/@', b'%/C', b'%/E')):
                descriptor = data
            if data[0] == 255:
                break
        if descriptor is None:
            raise ValueError('Requested ISO directory tree is absent')
        def record(data):
            if len(data) < 34 or data[0] != len(data):
                raise ValueError('Invalid directory record')
            lba, length = struct.unpack_from('<I', data, 2)[0], struct.unpack_from('<I', data, 10)[0]
            if lba != struct.unpack_from('>I', data, 6)[0] or length != struct.unpack_from('>I', data, 14)[0]:
                raise ValueError('ISO endian copies disagree')
            name = data[33:33+data[32]]
            return lba, length, bool(data[25] & 2), name, list(data[18:25])
        def walk(raw, parent):
            lba, length, is_dir, name, timestamp = record(raw)
            if not is_dir or (lba, length) in seen:
                raise ValueError('Invalid/cyclic ISO directory')
            seen.add((lba, length))
            data, offset = read(lba, length), 0
            while offset < len(data):
                n = data[offset]
                if not n:
                    offset = (offset//2048+1)*2048
                    continue
                if offset % 2048+n > 2048:
                    raise ValueError('Directory record crosses a sector')
                child = data[offset:offset+n]
                start, count, directory, name, timestamp = record(child)
                offset += n
                if name in (b'\0', b'\1'):
                    continue
                name = name.decode('utf-16-be' if joliet else 'ascii').removesuffix(';1')
                if '/' in name or '\\' in name or name in ('.', '..'):
                    raise ValueError('Invalid ISO name')
                relative = f'{parent}/{name}' if parent else name
                if relative in result:
                    raise ValueError('Duplicate ISO name')
                if directory:
                    if directories:
                        result[relative] = dict(directory=True, timestamp=timestamp, lba=start, bytes=count)
                    walk(child, relative)
                else:
                    item = dict(lba=start, bytes=count, timestamp=timestamp)
                    if hashes:
                        digest, left = hashlib.sha256(), count
                        stream.seek(start*2048)
                        if start*2048+count > size:
                            raise ValueError('File extent exceeds image')
                        while left:
                            chunk = stream.read(min(left, 1024*1024))
                            if not chunk:
                                raise ValueError('Truncated file extent')
                            digest.update(chunk)
                            left -= len(chunk)
                        item['sha256'] = digest.hexdigest()
                    result[relative] = item
        walk(descriptor[156:190], '')
    return result
