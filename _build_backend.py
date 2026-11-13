"""Small PEP 517 backend: offline builds use only Python's standard library.

Both wheels and source archives include runtime assets. No git or build-time
dependency is needed. Keep package metadata in pyproject.toml and version.py.
"""
from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import re
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent


def allowed(path):
    return not any('b' + 'lind' in p.casefold() or p in ('.git', '__pycache__') for p in Path(path).parts)


def files(folder):
    for base, dirs, names in os.walk(ROOT / folder):
        dirs[:] = sorted(n for n in dirs if allowed(Path(base) / n))
        for name in sorted(names):
            path = Path(base) / name
            if allowed(path) and path.suffix not in ('.pyc', '.pyo') and path.is_file():
                yield path, path.relative_to(ROOT).as_posix()


def project():
    data = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    tree = ast.parse((ROOT / 'discprobe/version.py').read_text(encoding='utf-8'))
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    # The public spelling 1.0.0-alpha.1 has canonical PEP 440 spelling 1.0.0a1.
    data['version'] = re.sub(r'-alpha(?:\.(\d+))?$', lambda m: 'a' + (m[1] or '0'), version)
    return data


def identity():
    data = project()
    return data['name'].replace('-', '_') + '-' + data['version']


def metadata_files():
    data = project()
    metadata = '\n'.join([
        'Metadata-Version: 2.4', f"Name: {data['name']}", f"Version: {data['version']}",
        f"Summary: {data['description']}", f"Requires-Python: {data['requires-python']}",
        f"License-Expression: {data['license']}", 'License-File: LICENSE',
        *[f'Requires-Dist: {dep}' for dep in data['dependencies']],
        'Description-Content-Type: text/markdown', '',
        (ROOT / data['readme']).read_text(encoding='utf-8'),
    ])
    scripts = '\n'.join(f'{k} = {v}' for k, v in data['scripts'].items())
    return {
        'METADATA': metadata.encode('utf-8'),
        'WHEEL': b'Wheel-Version: 1.0\nGenerator: disc-probe stdlib backend\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        'entry_points.txt': ('[console_scripts]\n' + scripts + '\n').encode('utf-8'),
        'licenses/LICENSE': (ROOT / 'LICENSE').read_bytes(),
    }


def get_requires_for_build_wheel(config_settings=None):
    return []


get_requires_for_build_sdist = get_requires_for_build_wheel


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    name = identity() + '.dist-info'
    for relative, data in metadata_files().items():
        target = Path(metadata_directory) / name / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = identity()
    filename = name + '-py3-none-any.whl'
    Path(wheel_directory).mkdir(parents=True, exist_ok=True)
    records = []
    with zipfile.ZipFile(Path(wheel_directory) / filename, 'w', compression=zipfile.ZIP_DEFLATED) as wheel:
        def write(relative, data):
            wheel.writestr(relative, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')
            records.append((relative, 'sha256=' + digest, len(data)))
        for source, relative in files('discprobe'):
            write(relative, source.read_bytes())
        for folder in ('presets', 'tools', 'data'):
            for source, relative in files(folder):
                write('discprobe/_' + relative, source.read_bytes())
        # The installed selftest resolves this recorded fixture beside discprobe.
        fixture = 'tests/data/bd_discussion_samples/local_uj272_bd_zones.csv'
        write(fixture, (ROOT / fixture).read_bytes())
        # WindowsDVD still resolves this helper beside the installed package.
        # Preserve that runtime path without changing the product adapter.
        write('tools/burn_imapi.ps1', (ROOT / 'tools/burn_imapi.ps1').read_bytes())
        if (ROOT / 'release-build.json').is_file():
            write('discprobe/_release.json', (ROOT / 'release-build.json').read_bytes())
        for relative, data in metadata_files().items():
            write(name + '.dist-info/' + relative, data)
        record = name + '.dist-info/RECORD'
        records.append((record, '', ''))
        stream = io.StringIO(newline='')
        csv.writer(stream, lineterminator='\n').writerows(records)
        wheel.writestr(record, stream.getvalue())
    return filename


def build_sdist(sdist_directory, config_settings=None):
    name = identity()
    filename = name + '.tar.gz'
    Path(sdist_directory).mkdir(parents=True, exist_ok=True)
    with tarfile.open(Path(sdist_directory) / filename, 'w:gz') as archive:
        for folder in ('discprobe', 'presets', 'tools', 'data'):
            for source, relative in files(folder):
                archive.add(source, arcname=f'{name}/{relative}', recursive=False)
        for relative in ('pyproject.toml', '_build_backend.py', 'README.md', 'README.en.md', 'LICENSE', 'docs/API_VERSIONING.md',
                         'INSTALL-linux.md', 'tests/data/bd_discussion_samples/local_uj272_bd_zones.csv'):
            archive.add(ROOT / relative, arcname=f'{name}/{relative}', recursive=False)
        if (ROOT / 'release-build.json').is_file():
            archive.add(ROOT / 'release-build.json', arcname=f'{name}/release-build.json', recursive=False)
        data = metadata_files()['METADATA']
        entry = tarfile.TarInfo(f'{name}/PKG-INFO'); entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
    return filename
