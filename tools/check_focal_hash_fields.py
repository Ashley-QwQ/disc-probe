"""Prove focal regeneration only changes permitted provenance hash fields.

Example: python -B -X utf8 tools/check_focal_hash_fields.py --baseline ffd369d
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SWATCH_HASHES = {('source', key) for key in (
    'palette_sha256', 'generator_sha256', 'pose_sha256', 'geometry_sha256',
)}
ARTIFACTS = {
    'data/focal/pose_1x.json': {
        ('source', 'calibration_sha256'), ('source', 'legacy_sha256'),
    },
    'discprobe/web/home/design/pose-swatches.json': SWATCH_HASHES,
    'discprobe/web/home/design/pose-swatches-custom.json': SWATCH_HASHES,
    'tools/focal_data/regression.json': {('fixture_sha256',), ('geometry_sha256',)},
}


def compare(before, after, allowed, path=()):
    assert type(before) is type(after), f'type changed: {path}'
    changes = []
    if isinstance(before, dict):
        assert before.keys() == after.keys(), f'keys changed: {path}'
        for key in before:
            changes.extend(compare(before[key], after[key], allowed, (*path, key)))
    elif isinstance(before, list):
        assert len(before) == len(after), f'length changed: {path}'
        for i, (old, new) in enumerate(zip(before, after)):
            changes.extend(compare(old, new, allowed, (*path, str(i))))
    elif before != after:
        assert path in allowed, f'non-provenance value changed: {path}'
        assert all(isinstance(v, str) and len(v) == 64 and
                   all(c in '0123456789abcdef' for c in v) for v in (before, after))
        changes.append(dict(field='.'.join(path), before=before, after=after))
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, help='Git revision before regeneration')
    parser.add_argument('--out', type=Path, help='Optional JSON evidence path')
    args = parser.parse_args()
    files = []
    for name, allowed in ARTIFACTS.items():
        original = subprocess.run(['git', 'show', f'{args.baseline}:{name}'],
                                  cwd=ROOT, check=True, capture_output=True).stdout
        changes = compare(json.loads(original), json.loads((ROOT / name).read_bytes()), allowed)
        files.append(dict(file=name, changes=changes))
    result = dict(baseline=args.baseline, files=files,
                  changed_hash_fields=sum(len(f['changes']) for f in files),
                  non_hash_changes=0)
    text = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()
