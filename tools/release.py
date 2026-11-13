"""Offline release rehearsal. Never edits the checkout, downloads, tags or publishes.

python tools/release.py --version 1.0.0-alpha --out DIR --cache WINPACK_CACHE
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

ROOT = Path(__file__).resolve().parents[1]
EXCLUDES = [':(exclude,icase,glob)**/*b[l]ind*', ':(exclude,icase,glob)**/*b[l]ind*/**']
PACKAGES = ('numpy', 'Pillow', 'scipy', 'opencv-python')


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=os.environ.get('DISC_PROBE_WINPACK_CACHE'),
                        help='offline Python embed ZIP and site-packages; or DISC_PROBE_WINPACK_CACHE')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-alpha(?:\.\d+)?)?', args.version):
        parser.error('version must be X.Y.Z, X.Y.Z-alpha or X.Y.Z-alpha.N')
    if os.name != 'nt' or sys.version_info[:2] != (3, 13):
        parser.error('all-platform assembly requires Windows Python 3.13 (embedded runtime is 3.13.14)')
    commit = clean_commit()  # Even an untracked file is a refusal, before output mutation.
    out = args.out.resolve()
    if not allowed(out) or out == ROOT or ROOT in out.parents:
        parser.error('output must be an allowed path outside the checkout')
    if out.exists() and any(out.iterdir()):
        parser.error('output must be new or empty; old results are never reused')
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
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
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
        run_check([*python, '-m', 'pytest', '-q', 'tests', 'tests/scipy_oracle_checks.py',
                   '-p', 'no:cacheprovider', '--ignore-glob=*b[l]ind*'], snapshot, logs / 'pytest.log', env, checks)
        scripts = sorted(p for p in (snapshot / 'tests').iterdir() if allowed(p.name)
                         and p.name.startswith('test_') and p.suffix in ('.js', '.mjs', '.cjs'))
        if not scripts:
            raise RuntimeError('no Node tests found')
        for script in scripts:
            run_check([node, str(script)], snapshot, logs / (script.name + '.log'), env, checks, 180)
        run_check([*python, '-m', 'discprobe', 'selftest'], snapshot, logs / 'selftest.log', env, checks)
        run_check([*python, '-c', 'import _build_backend as b; print(b.build_wheel("../assets")); print(b.build_sdist("../assets"))'],
                  snapshot, logs / 'source-build.log', env, checks)
        run_check([*python, str(snapshot/'tools/verify_source.py'), '--assets', str(out/'assets'),
                   '--out', str(out/'from-sdist')], snapshot, logs/'sdist-equivalence.log', env, checks)
        run_check([*python, str(snapshot / 'tools/build_winpack.py'), '--source-root', str(snapshot),
                   '--commit', commit, '--ref', commit, '--label', args.version, '--cache', str(cache), '--out', str(out / 'winpack')],
                  snapshot, logs / 'winpack-build.log', env, checks)
        assets = out / 'assets'
        for path in (out / 'winpack').glob('*.zip'):
            shutil.copy2(path, assets / path.name)
        shutil.copy2(snapshot / 'INSTALL-linux.md', assets / 'INSTALL-linux.md')
        # Read canonical identity from the backend in the prepared build copy.
        canonical = subprocess.check_output([*python, '-c', 'import _build_backend as b; print(b.project()["version"])'],
                                            cwd=snapshot, env=env, text=True).strip()
        gui = json.loads((snapshot / 'discprobe/web/gui.json').read_text(encoding='utf-8'))
        dependencies = {d.metadata['Name']: d.version for d in importlib.metadata.distributions(path=[str(deps)])
                        if d.metadata['Name'].lower() in {p.lower() for p in PACKAGES}}
        inventory = [dict(file=p.name, size=p.stat().st_size, sha256=sha256(p)) for p in sorted(assets.iterdir())]
        manifest = dict(schema=1, status='PASS', **info, pep440_version=canonical, gui_version=gui['gui_version'],
                        python=sys.version, node=subprocess.check_output([node, '--version'], text=True).strip(),
                        check_dependencies={n: importlib.metadata.version(n) for n in (*PACKAGES, 'pytest')},
                        windows=dict(python='3.13.14', dependencies=dependencies, embed_sha256=sha256(embed)),
                        checks=checks, assets=inventory)
        if (ROOT / 'discprobe/version.py').read_bytes() != original_version or clean_commit() != commit:
            raise RuntimeError('checkout changed during release')
        write_json(assets / 'manifest.json', manifest)
        sums = inventory + [dict(file='manifest.json', sha256=sha256(assets / 'manifest.json'))]
        (assets / 'SHA256SUMS.txt').write_text(''.join(f'{p["sha256"]}  {p["file"]}\n' for p in sums), encoding='ascii')
        write_json(out / 'status.json', dict(status='PASS', commit=commit, checks=checks))
        print(f'Release assets ready: {assets}', flush=True)
    except BaseException as exc:
        # Partial build directories are diagnostic evidence, never a completed release.
        write_json(out / 'status.json', dict(status='FAIL', commit=commit, error=str(exc), checks=checks))
        raise


if __name__ == '__main__':
    main()
