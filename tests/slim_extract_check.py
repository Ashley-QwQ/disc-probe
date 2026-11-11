"""Verify real zip extraction in a Chinese path containing spaces, then selftest."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slim_support import ROOT, ARTIFACTS, allowed, low_priority
low_priority()


def main():
    scratch = Path('D:/disc-probe-dist/slim-20261111')
    destination = scratch / ('解压 验证 ' + str(time.time_ns()))
    destination.mkdir()
    result = {}
    for kind in ('core', 'full-win64'):
        path = scratch / f'disc-probe-slim-20261111-{kind}.zip'
        with zipfile.ZipFile(path) as z:
            for entry in z.infolist():
                if not allowed(entry.filename) or not (destination / entry.filename).resolve().is_relative_to(destination.resolve()):
                    raise ValueError('unsafe or excluded extraction entry')
            z.extractall(destination)
            for entry in z.infolist():
                if not entry.is_dir():
                    disk = destination / entry.filename
                    if hashlib.sha256(disk.read_bytes()).digest() != hashlib.sha256(z.read(entry)).digest():
                        raise AssertionError('extraction changed bytes')
            if kind == 'core':
                assert not any('/python/' in e.filename or '/site-packages/' in e.filename for e in z.infolist())
        result[kind] = dict(zip=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), extracted_identical=True)
    full = destination / 'disc-probe-slim-20261111-full-win64'
    log = scratch / ('extracted-selftest-' + str(time.time_ns()) + '.log')
    command = [str(full / 'python/python.exe'), '-I', '-X', 'utf8', '-B', str(ROOT / 'tests/slim_trace.py'),
               '--root', str(full), '--output', str(scratch / 'audit-extracted'), '--mode', 'selftest']
    with log.open('w', encoding='utf-8') as stream:
        done = subprocess.run(command, cwd=full, stdout=stream, stderr=subprocess.STDOUT)
    result['selftest'] = dict(returncode=done.returncode, log=str(log), command=command)
    result['destination'] = str(destination)
    (ARTIFACTS / 'extracted.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(selftest_returncode=done.returncode, extraction_identical=True)))
    raise SystemExit(done.returncode)


if __name__ == '__main__':
    main()
