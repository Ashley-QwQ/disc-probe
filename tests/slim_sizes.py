"""Measure actual zip payloads, overhead and uncompressed bytes per part."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slim_support import ARTIFACTS, allowed, low_priority
low_priority()


def part(name):
    name = name.replace('\\', '/').lower()
    if '/site-packages/scipy' in name:
        return 'scipy + scipy.libs + metadata'
    if '/site-packages/numpy.libs/' in name:
        return 'numpy OpenBLAS'
    if '/site-packages/numpy' in name:
        return 'numpy + metadata'
    if '/site-packages/pil/' in name or '/site-packages/pillow-' in name:
        return 'Pillow + metadata'
    if '/python/' in name:
        return 'embedded Python'
    return 'disc-probe + source + manifest'


def sizes(path):
    counts = defaultdict(lambda: dict(unpacked=0, zipped_payload=0, files=0))
    with zipfile.ZipFile(path) as z:
        for entry in z.infolist():
            if not allowed(entry.filename):
                raise ValueError('excluded archive path')
            if entry.is_dir():
                continue
            row = counts[part(entry.filename)]
            row['unpacked'] += entry.file_size
            row['zipped_payload'] += entry.compress_size
            row['files'] += 1
    payload = sum(c['zipped_payload'] for c in counts.values())
    raw = sum(c['unpacked'] for c in counts.values())
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), parts=dict(counts), zipped=path.stat().st_size,
                unpacked=raw, zip_headers=path.stat().st_size - payload)


if __name__ == '__main__':
    paths = [Path('D:/disc-probe-dist/disc-probe-0.1.2.1-full-win64.zip'),
             Path('D:/disc-probe-dist/slim-20261111/disc-probe-slim-20261111-full-win64.zip'),
             Path('D:/disc-probe-dist/slim-20261111/disc-probe-slim-20261111-core.zip')]
    report = [sizes(p) for p in paths if p.is_file()]
    (ARTIFACTS / 'sizes.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps([{k: r[k] for k in ('path', 'zipped', 'unpacked')} for r in report]))
