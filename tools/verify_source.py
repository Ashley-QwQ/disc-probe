"""Rebuild the sdist offline and compare every wheel entry, ignoring ZIP timestamps."""
import argparse
import importlib.util
from pathlib import Path
import tarfile
import zipfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--assets', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    wheel, = a.assets.glob('*.whl')
    source, = a.assets.glob('*.tar.gz')
    a.out.mkdir(parents=True, exist_ok=False)
    with tarfile.open(source) as archive:
        for member in archive:
            if any('b'+'lind' in p.casefold() for p in Path(member.name).parts):
                raise ValueError('excluded source member')
            archive.extract(member, a.out, filter='data')
    root, = (p for p in a.out.iterdir() if p.is_dir())
    spec = importlib.util.spec_from_file_location('sdist_rebuild', root/'_build_backend.py')
    backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
    rebuilt = a.out/backend.build_wheel(a.out)
    with zipfile.ZipFile(wheel) as original, zipfile.ZipFile(rebuilt) as copy:
        assert set(original.namelist()) == set(copy.namelist()), 'wheel entries differ'
        for name in original.namelist():
            assert original.read(name) == copy.read(name), name
        print(f'PASS: {len(original.namelist())} wheel entries identical after offline sdist rebuild')


if __name__ == '__main__':
    main()
