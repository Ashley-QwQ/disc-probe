"""Verify final archives against the already selftested extracted runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slim_support import ARTIFACTS, allowed, low_priority
low_priority()


def main():
    scratch = Path('D:/disc-probe-dist/slim-20261111')
    gate = json.loads((ARTIFACTS / 'extracted.json').read_text(encoding='utf-8'))
    assert gate['selftest']['returncode'] == 0
    previous = Path(gate['destination']) / 'disc-probe-slim-20261111-full-win64'
    destination = scratch / ('最终 核验 ' + str(time.time_ns()))
    destination.mkdir()
    result = {}
    for kind in ('core', 'full-win64'):
        path = scratch / f'disc-probe-slim-20261111-{kind}.zip'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert path.with_name(path.name + '.sha256').read_text(encoding='ascii').split()[0] == digest
        with zipfile.ZipFile(path) as z:
            for entry in z.infolist():
                assert allowed(entry.filename)
                assert (destination / entry.filename).resolve().is_relative_to(destination.resolve())
            z.extractall(destination)
        root = destination / f'disc-probe-slim-20261111-{kind}'
        manifest = json.loads((root / 'source-sha256.json').read_text(encoding='utf-8'))
        assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == value for name, value in manifest.items())
        result[kind] = dict(path=str(path), sha256=digest, source_manifest_verified=True)
        if kind == 'full-win64':
            compared = 0
            for entry in zipfile.ZipFile(path).infolist():
                if entry.is_dir():
                    continue
                name = entry.filename.split('/', 1)[1]
                if name in ('tools/build_winpack.py', 'source-sha256.json'):
                    continue
                assert (root / name).read_bytes() == (previous / name).read_bytes(), name
                compared += 1
            result[kind]['identical_to_selftested_files'] = compared
            command = [str(root / 'python/python.exe'), '-I', '-X', 'utf8', '-B', '-c',
                       "import importlib.util,json; from discprobe.numerics import f_sf; import numpy,PIL; assert importlib.util.find_spec('scipy') is None; print(json.dumps({'scipy_absent':True,'F_sf':f_sf(1.,3,28),'numpy':numpy.__version__,'pillow':PIL.__version__}))"]
            done = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8', check=True)
            result[kind]['final_extracted_import_probe'] = json.loads(done.stdout)
    result['destination'] = str(destination)
    (ARTIFACTS / 'final-artifacts.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('final zip hashes, manifests and extracted runtime verified')


if __name__ == '__main__':
    main()
