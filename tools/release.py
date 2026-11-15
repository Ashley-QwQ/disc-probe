"""Offline release rehearsal. Never edits the checkout, downloads, tags or publishes.

python tools/release.py --version 1.0.0.0-alpha --out DIR --cache WINPACK_CACHE [--neo DIR]
The output directory must be new or empty. All checks and build logs are retained.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDES = [':(exclude,icase,glob)**/*b[l]ind*', ':(exclude,icase,glob)**/*b[l]ind*/**']
PACKAGES = ('numpy', 'Pillow', 'scipy', 'opencv-python')
NEO_REQUIRED = ('README.md', 'README.zh.md', 'SCHEMA.md', 'PROVENANCE.json', 'LICENSE')


def public_version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?(?:-alpha(?:\.\d+)?)?', value):
        raise argparse.ArgumentTypeError('version must be X.Y.Z or X.Y.Z.W, optionally with -alpha or -alpha.N')
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', required=True, type=public_version)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=os.environ.get('DISC_PROBE_WINPACK_CACHE'),
                        help='offline Python embed ZIP and site-packages; or DISC_PROBE_WINPACK_CACHE')
    parser.add_argument('--neo', type=Path, default=os.environ.get('DISC_NEO_DIR'),
                        help='read-only staged Disc Neo folder; or DISC_NEO_DIR; omitted means skipped')
    return parser, parser.parse_args(argv)


def allowed(path):
    return all('b' + 'lind' not in p.casefold() for p in Path(path).parts)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def clean_commit():
    if git('status', '--porcelain=v1', '-z', '--untracked-files=all'):
        raise RuntimeError('dirty tree: commit or remove all tracked/untracked changes before release')
    return git('rev-parse', 'HEAD').decode().strip()


def set_version(snapshot, version):
    path = snapshot / 'discprobe/version.py'
    content = path.read_text(encoding='utf-8')
    tree = ast.parse(content)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets)]
    if len(assignments) != 1:
        raise RuntimeError('expected exactly one version assignment')
    lines = content.splitlines(keepends=True)
    node = assignments[0]
    lines[node.lineno - 1:node.end_lineno] = [f'__version__ = {json.dumps(version)}\n']
    path.write_text(''.join(lines), encoding='utf-8')
    # Disc Lab requires exactly the core it ships with (disclab/compat.py): the same public version.
    compat = snapshot / 'disclab/compat.py'
    if compat.is_file():
        content = compat.read_text(encoding='utf-8')
        tree = ast.parse(content)
        found = [n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'REQUIRED_DISCPROBE_VERSION' for t in n.targets)]
        if len(found) != 1:
            raise RuntimeError('expected exactly one REQUIRED_DISCPROBE_VERSION in disclab/compat.py')
        lines = content.splitlines(keepends=True)
        node = found[0]
        lines[node.lineno - 1:node.end_lineno] = [f'REQUIRED_DISCPROBE_VERSION = {json.dumps(version)}' + chr(10)]
        compat.write_text(''.join(lines), encoding='utf-8')


def run_check(command, cwd, log, env, checks, timeout=3600):
    print(f'Running {log.name}', flush=True)
    started = time.monotonic()
    with log.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(command, ensure_ascii=False) + '\n'); stream.flush()
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    checks.append(dict(log=log.name, command=command, exit_code=result.returncode,
                       seconds=round(time.monotonic() - started, 3), sha256=sha256(log)))
    if result.returncode:
        raise RuntimeError(f'check failed ({result.returncode}): {log}')


def package_files(root):
    """Inventory regular files without following links or silently dropping data."""
    if not allowed(root) or root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ValueError(f'package source must be an allowed regular directory: {root}')
    def walk_error(exc):
        raise exc
    files = []
    for base, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        for name in sorted(dirs + names):
            path = Path(base) / name
            if not allowed(path) or path.is_symlink() or path.is_junction():
                raise ValueError(f'excluded or linked package path: {path}')
            if name in names:
                if not path.is_file():
                    raise ValueError(f'package entry is not a regular file: {path}')
                files.append(path)
    return sorted(files)


def validate_neo(root):
    files = package_files(root)
    missing = [name for name in NEO_REQUIRED if not (root / name).is_file()]
    if missing:
        raise ValueError('Disc Neo missing required files: ' + ', '.join(missing))
    return files


def zip_package(root, files, target, prefix):
    """Record hashes of the exact bytes written to the ZIP; never write to root."""
    inventory = []
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            name = f'{prefix}/{relative}'
            digest = hashlib.sha256()
            size = 0
            with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as destination:
                for data in iter(lambda: source.read(1 << 20), b''):
                    destination.write(data)
                    digest.update(data)
                    size += len(data)
            inventory.append(dict(file=name, size=size, sha256=digest.hexdigest()))
    return inventory


def build_disc_neo(root, candidates, version):
    if root is None:
        reason = 'neither --neo nor DISC_NEO_DIR supplied'
        print(f'Disc Neo skipped: {reason}', flush=True)
        return dict(status='skipped', reason=reason, files=[])
    files = validate_neo(root)
    target = candidates / f'disc-neo-{version}-preview.zip'
    inventory = zip_package(root, files, target, 'disc-neo')
    return dict(status='PASS', asset=target.name, files=inventory)


def build_disc_lab(snapshot, candidates, version, python, logs, env, checks):
    root = snapshot / 'disclab'
    if not root.exists():
        reason = 'disclab/ absent from the frozen commit'
        print(f'Disc Lab skipped: {reason}', flush=True)
        return dict(status='skipped', reason=reason)
    files = package_files(root)
    target = candidates / f'disc-lab-{version}.zip'
    zip_package(root, files, target, 'disclab')
    # Test the exported bytes outside the source directory, importing the core
    # from the same frozen snapshot. The checkout is never an import fallback.
    extracted = candidates.parent / 'disc-lab-check'
    extracted.mkdir()
    with zipfile.ZipFile(target) as archive:
        archive.extractall(extracted)
    lab_env = dict(env, PYTHONPATH=str(snapshot))
    # test_package.py checks the repository layout itself (it clears PYTHONPATH and expects discprobe/ beside
    # disclab/); it runs in the full suite on the frozen commit, so the unpacked copy skips it.
    run_check([*python, '-m', 'pytest', 'disclab/tests', '-q', '-p', 'no:cacheprovider',
               '--ignore=disclab/tests/test_package.py'],
              extracted, logs / 'disc-lab-pytest.log', lab_env, checks)
    return dict(status='PASS', asset=target.name, core_source='frozen snapshot')


def finalize_assets(out, sources, manifest):
    """Expose assets only as one completed directory, after the caller's gates."""
    ready = out / 'verified-assets'
    ready.mkdir()
    inventory = []
    for source, package in sources:
        target = ready / source.name
        if target.exists():
            raise RuntimeError(f'duplicate release asset: {target.name}')
        shutil.copy2(source, target)
        inventory.append(dict(file=target.name, package=package, size=target.stat().st_size,
                              sha256=sha256(target)))
    inventory.sort(key=lambda entry: entry['file'])
    write_json(ready / 'manifest.json', dict(manifest, assets=inventory))
    sums = inventory + [dict(file='manifest.json', sha256=sha256(ready / 'manifest.json'))]
    (ready / 'SHA256SUMS.txt').write_text(''.join(f'{p["sha256"]}  {p["file"]}\n' for p in sums), encoding='ascii')
    assets = out / 'assets'
    ready.rename(assets)
    return assets


def main(argv=None):
    parser, args = parse_args(argv)
    if os.name != 'nt' or sys.version_info[:2] != (3, 13):
        parser.error('all-platform assembly requires Windows Python 3.13 (embedded runtime is 3.13.14)')
    commit = clean_commit()  # Even an untracked file is a refusal, before output mutation.
    out = args.out.resolve()
    if not allowed(out) or out == ROOT or ROOT in out.parents:
        parser.error('output must be an allowed path outside the checkout')
    if out.exists() and any(out.iterdir()):
        parser.error('output must be new or empty; old results are never reused')
    neo = args.neo
    if neo is not None:
        try:
            validate_neo(neo)
        except ValueError as exc:
            parser.error(str(exc))
        neo = neo.resolve()
        if out == neo or out in neo.parents or neo in out.parents:
            parser.error('output and the read-only Disc Neo staging folder must not overlap')
    if not args.cache:
        parser.error('set --cache or DISC_PROBE_WINPACK_CACHE to an existing offline cache')
    cache = args.cache.resolve()
    if not allowed(cache):
        parser.error('excluded cache path')
    embed = cache / 'python-3.13.14-embed-amd64.zip'
    deps = cache / 'site-packages'
    if not embed.is_file() or not deps.is_dir():
        parser.error('cache needs python-3.13.14-embed-amd64.zip and site-packages/')
    node = shutil.which('node')
    if not node:
        parser.error('Node is required, never downloaded')
    # The render regression deliberately compares against the previous release.
    git('cat-file', '-e', 'v0.1.2.1:discprobe/simulate.py')
    out.mkdir(parents=True, exist_ok=True)
    logs = out / 'logs'; logs.mkdir()
    snapshot = out / 'build-copy'; snapshot.mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PIP_NO_INDEX='1',
               PIP_DISABLE_PIP_VERSION_CHECK='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1',
               DISCPROBE_WORKERS='1')  # Parent + one image worker: at most two heavy processes.
    checks = []
    original_version = (ROOT / 'discprobe/version.py').read_bytes()
    try:
        archive = git('archive', '--format=tar', commit, '--', '.', *EXCLUDES)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source:
                if not allowed(member.name):
                    raise RuntimeError('excluded source path')
                source.extract(member, snapshot, filter='data')
        # A historical-render regression needs local Git objects. A gitfile in
        # this copy supplies read-only history without exporting GIT_DIR into
        # subprocesses that initialize their own temporary test repositories.
        (snapshot / '.git').write_text('gitdir: ' + git('rev-parse', '--absolute-git-dir').decode().strip() + '\n', encoding='utf-8')
        set_version(snapshot, args.version)
        info = dict(commit=commit, public_version=args.version, source_archive_sha256=hashlib.sha256(archive).hexdigest())
        write_json(snapshot / 'release-build.json', info)
        python = [sys.executable, '-X', 'utf8', '-B']
        # Test installable candidates before the expensive source suite. They
        # become public assets only after every gate passes; copy their exact
        # bytes so the recorded wheel verification hash remains authoritative.
        candidates = out / 'candidate-assets'
        run_check([*python, '-c', 'import _build_backend as b; print(b.build_wheel("../candidate-assets")); print(b.build_sdist("../candidate-assets"))'],
                  snapshot, logs / 'source-build.log', env, checks)
        run_check([*python, str(snapshot/'tools/verify_source.py'), '--assets', str(candidates),
                   '--out', str(out/'from-sdist')], snapshot, logs/'sdist-equivalence.log', env, checks)
        venv = out / 'wheel-venv'
        run_check([*python, '-m', 'venv', str(venv)], out, logs/'wheel-venv.log', env, checks)
        copy_code = ("import importlib.util,shutil; "
                     f"s=importlib.util.spec_from_file_location('winpack_deps',{str(snapshot/'tools/build_winpack.py')!r}); "
                     "b=importlib.util.module_from_spec(s); s.loader.exec_module(b); "
                     f"b.copy_packages({str(deps)!r},{str(out/'wheel-dependencies')!r}); "
                     f"shutil.copytree({str(out/'wheel-dependencies')!r},{str(venv/'Lib/site-packages')!r},dirs_exist_ok=True)")
        run_check([*python, '-c', copy_code], out, logs/'wheel-dependencies.log', env, checks)
        wheel_python = str(venv/'Scripts/python.exe')
        wheel, = candidates.glob('*.whl')
        run_check([wheel_python, '-B', '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel)],
                  out, logs/'wheel-install.log', env, checks)
        run_check([wheel_python, '-B', '-m', 'pip', 'check'], out, logs/'wheel-pip-check.log', env, checks)
        run_check([wheel_python, '-X', 'utf8', '-B', str(snapshot/'tools/verify_package.py'),
                   '--artifact', str(wheel), '--expected-root', str(venv), '--version', args.version,
                   '--out', str(out/'wheel-proof')], out, logs/'wheel-verify.log', env, checks)
        run_check([*python, '-m', 'pytest', '-q', 'tests', 'tests/scipy_oracle_checks.py',
                   '-p', 'no:cacheprovider', '--ignore-glob=*b[l]ind*'], snapshot, logs / 'pytest.log', env, checks)
        scripts = sorted(p for p in (snapshot / 'tests').iterdir() if allowed(p.name)
                         and p.name.startswith('test_') and p.suffix in ('.js', '.mjs', '.cjs'))
        if not scripts:
            raise RuntimeError('no Node tests found')
        for script in scripts:
            run_check([node, str(script)], snapshot, logs / (script.name + '.log'), env, checks, 180)
        run_check([*python, '-m', 'discprobe', 'selftest'], snapshot, logs / 'selftest.log', env, checks)
        run_check([*python, str(snapshot / 'tools/build_winpack.py'), '--source-root', str(snapshot),
                   '--commit', commit, '--ref', commit, '--label', args.version, '--cache', str(cache), '--out', str(out / 'winpack')],
                  snapshot, logs / 'winpack-build.log', env, checks)
        disc_lab = build_disc_lab(snapshot, candidates, args.version, python, logs, env, checks)
        disc_neo = build_disc_neo(neo, candidates, args.version)
        sources = [(p, 'disc-probe') for p in sorted(candidates.iterdir())
                   if p.suffix == '.whl' or p.name.endswith('.tar.gz')]
        sources.extend((p, 'disc-probe') for p in sorted((out / 'winpack').glob('*.zip')))
        sources.append((snapshot / 'INSTALL-linux.md', 'disc-probe'))
        for package, result in (('disc-lab', disc_lab), ('disc-neo', disc_neo)):
            if result['status'] == 'PASS':
                sources.append((candidates / result['asset'], package))
        # Read canonical identity from the backend in the prepared build copy.
        canonical = subprocess.check_output([*python, '-c', 'import _build_backend as b; print(b.project()["version"])'],
                                            cwd=snapshot, env=env, text=True).strip()
        gui = json.loads((snapshot / 'discprobe/web/gui.json').read_text(encoding='utf-8'))
        dependencies = {d.metadata['Name']: d.version for d in importlib.metadata.distributions(path=[str(deps)])
                        if d.metadata['Name'].lower() in {p.lower() for p in PACKAGES}}
        manifest = dict(schema=2, status='PASS', **info, pep440_version=canonical, gui_version=gui['gui_version'],
                        resource_limits=dict(image_workers=1, math_threads=1),
                        python=sys.version, node=subprocess.check_output([node, '--version'], text=True).strip(),
                        check_dependencies={n: importlib.metadata.version(n) for n in (*PACKAGES, 'pytest')},
                        windows=dict(python='3.13.14', dependencies=dependencies, embed_sha256=sha256(embed)),
                        checks=checks, disc_lab=disc_lab, disc_neo=disc_neo)
        if (ROOT / 'discprobe/version.py').read_bytes() != original_version or clean_commit() != commit:
            raise RuntimeError('checkout changed during release')
        assets = finalize_assets(out, sources, manifest)
        write_json(out / 'status.json', dict(status='PASS', commit=commit, checks=checks))
        print(f'Release assets ready: {assets}', flush=True)
    except BaseException as exc:
        # Partial build directories are diagnostic evidence, never a completed release.
        write_json(out / 'status.json', dict(status='FAIL', commit=commit, error=str(exc), checks=checks))
        raise


if __name__ == '__main__':
    main()
