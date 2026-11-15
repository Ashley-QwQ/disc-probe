"""Test focal inputs as CRLF in this worktree, then restore their exact bytes.

Backups, logs, pytest temporary files and the generated map stay under --out.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    'tools/editor_pose_swatches.py', 'tools/make_rulers.py',
    'tools/focal_geometry.py', 'tools/focal_regression.py',
    'tools/focal_capture.py', 'tools/focal_verify_rulers.py',
    'discprobe/focal.py', 'discprobe/hashing.py',
    'data/focal/legacy.json', 'data/focal/pose_1x.json',
    'discprobe/web/home/design/swatches.json',
    'discprobe/web/home/design/pose-swatches.json',
    'discprobe/web/home/design/pose-swatches-custom.json',
    'discprobe/web/home/design/focal-geometry.mjs',
    'tools/focal_data/regression.json',
)
TESTS = ('tests/test_hashing.py', 'tests/test_editor_pose_swatches.py',
         'tests/test_focal_geometry.py', 'tests/test_editor_preview.py',
         'tests/test_focal_packaging.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('D:/dp-dev/tmp/hash-eol/crlf'))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    originals = {name: (ROOT / name).read_bytes() for name in INPUTS}
    for name, data in originals.items():
        backup = out / 'originals' / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(data)
    env = dict(os.environ, TEMP=str(out), TMP=str(out), PYTHONDONTWRITEBYTECODE='1',
               DISC_PROBE_FOCAL_CACHE_DIR=str(out / 'cache'))
    commands = (
        ['-m', 'pytest', '-n', '2', '-q', '--basetemp', str(out / 'pytest'), *TESTS],
        ['tools/focal_geometry.py', '--check'],
        ['tools/editor_pose_swatches.py', '--check'],
    )
    results = []
    try:
        for name, data in originals.items():
            crlf = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            (ROOT / name).write_bytes(crlf)
            assert b'\r\n' in crlf and b'\n' not in crlf.replace(b'\r\n', b'')
        print(f'CRLF inputs verified: {len(originals)}', flush=True)
        for i, command in enumerate(commands):
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', *command],
                                 cwd=ROOT, env=env, capture_output=True, text=True,
                                 encoding='utf-8', timeout=600)
            (out / f'command-{i}.log').write_text(run.stdout + run.stderr, encoding='utf-8')
            results.append(dict(args=command, returncode=run.returncode))
            print(run.stdout, end='', flush=True)
            assert run.returncode == 0, run.stderr
    finally:
        for name, data in originals.items():
            (ROOT / name).write_bytes(data)
        restored = all((ROOT / name).read_bytes() == data for name, data in originals.items())
        evidence = dict(converted_files=list(originals), commands=results, restored_exactly=restored,
                        original_byte_sha256={name: hashlib.sha256(data).hexdigest()
                                              for name, data in originals.items()})
        (out / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        assert restored
        print(f'Exact byte restoration verified: {len(originals)}', flush=True)


if __name__ == '__main__':
    main()
