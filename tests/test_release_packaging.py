"""Release gate checks; no downloads or device access."""
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = [
    ('1.0.0-alpha', '1.0.0a0'), ('1.0.0-alpha.1', '1.0.0a1'), ('1.0.0', '1.0.0'),
    ('0.1.2.1', '0.1.2.1'), ('1.0.0.0-alpha', '1.0.0.0a0'),
    ('1.0.0.0-alpha.2', '1.0.0.0a2'), ('1.0.0.0', '1.0.0.0'),
]


def load(path):
    spec = importlib.util.spec_from_file_location('release_gate_test_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('public,canonical', VERSIONS)
def test_version_only_changes_prepared_copy(tmp_path, public, canonical):
    release = load(ROOT / 'tools/release.py')
    original = (ROOT / 'discprobe/version.py').read_bytes()
    (tmp_path / 'discprobe').mkdir()
    target = tmp_path / 'discprobe/version.py'
    target.write_bytes(original)
    release.set_version(tmp_path, public)
    assert f'"{public}"' in target.read_text()
    assert (ROOT / 'discprobe/version.py').read_bytes() == original


def test_alpha_metadata_normalization(tmp_path, monkeypatch):
    backend = load(ROOT / '_build_backend.py')
    monkeypatch.setattr(backend, 'ROOT', tmp_path)
    (tmp_path / 'pyproject.toml').write_bytes((ROOT / 'pyproject.toml').read_bytes())
    (tmp_path / 'discprobe').mkdir()
    for public, canonical in VERSIONS:
        (tmp_path / 'discprobe/version.py').write_text(f'__version__ = "{public}"\n')
        assert backend.project()['version'] == canonical


def test_dirty_tree_is_refused(tmp_path, monkeypatch):
    release = load(ROOT / 'tools/release.py')
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    subprocess.run(['git', 'init', '--quiet', str(tmp_path)], check=True)
    (tmp_path / 'untracked.txt').write_text('pending change')
    with pytest.raises(RuntimeError, match='dirty tree'):
        release.clean_commit()


def test_failed_check_stops_and_preserves_log(tmp_path):
    release = load(ROOT / 'tools/release.py')
    log = tmp_path / 'failure.log'
    checks = []
    with pytest.raises(RuntimeError, match='check failed'):
        release.run_check([sys.executable, '-c', 'print("sentinel"); raise SystemExit(9)'],
                          tmp_path, log, None, checks, 30)
    assert checks[0]['exit_code'] == 9
    assert 'sentinel' in log.read_text()
    assert checks[0]['sha256'] == release.sha256(log)


@pytest.mark.parametrize('public,canonical', VERSIONS)
def test_version_arguments(tmp_path, monkeypatch, public, canonical):
    release = load(ROOT / 'tools/release.py')
    monkeypatch.delenv('DISC_NEO_DIR', raising=False)
    _, args = release.parse_args(['--version', public, '--out', str(tmp_path)])
    assert args.version == public
    assert args.neo is None


@pytest.mark.parametrize('version', ['1.0', '1.0.0.0.0', '1.0.0-beta', '1.0.0.0-alpha.x', '../1.0.0', '1.0.0\n'])
def test_bad_version_arguments(tmp_path, version):
    release = load(ROOT / 'tools/release.py')
    with pytest.raises(SystemExit) as exc:
        release.parse_args(['--version', version, '--out', str(tmp_path)])
    assert exc.value.code == 2


@pytest.mark.parametrize('public,canonical', VERSIONS)
def test_built_metadata_and_public_payload(tmp_path, monkeypatch, public, canonical):
    """Build small real archives, then import the exported API in isolation."""
    backend = load(ROOT / '_build_backend.py')
    monkeypatch.setattr(backend, 'ROOT', tmp_path)
    troubleshoot = 'discprobe/data/troubleshoot.json'
    for name in ('pyproject.toml', 'LICENSE', 'STYLE.md', 'DESIGN.md', 'docs/API_VERSIONING.md', 'INSTALL-linux.md',
                 '_build_backend.py', 'discprobe/api.py', troubleshoot):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    for name in ('README.md', 'README.en.md', 'discprobe/__init__.py',
                 'tests/data/bd_discussion_samples/local_uj272_bd_zones.csv'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('', encoding='utf-8')
    (tmp_path / 'discprobe/version.py').write_text('__version__ = "old"\n', encoding='utf-8')
    load(ROOT / 'tools/release.py').set_version(tmp_path, public)
    assets = tmp_path / 'candidates'
    wheel = assets / backend.build_wheel(assets)
    sdist = assets / backend.build_sdist(assets)
    assert wheel.name == f'disc_probe-{canonical}-py3-none-any.whl'
    assert sdist.name == f'disc_probe-{canonical}.tar.gz'
    installed = tmp_path / 'installed'
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(installed)
        assert archive.read(troubleshoot) == (ROOT / troubleshoot).read_bytes()
        metadata = archive.read(f'disc_probe-{canonical}.dist-info/METADATA').decode()
        assert f'\nVersion: {canonical}\n' in metadata
    with tarfile.open(sdist) as archive:
        metadata = archive.extractfile(f'disc_probe-{canonical}/PKG-INFO').read().decode()
        assert f'\nVersion: {canonical}\n' in metadata
    code = ('import sys,json; sys.path.insert(0,sys.argv[1]); from discprobe import api; '
            'p=api.version_payload(); '
            'assert api.api_matches(p["api_version"],">=1.0 <2"); '
            'print(json.dumps(p))')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(installed)],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['core_version'] == public
    # API versions retain their separate major.minor grammar.
    from discprobe import api
    assert api._VERSION.fullmatch('1.0')
    assert not api.api_matches(public, '>=1.0 <2')


def make_neo(root, release):
    root.mkdir()
    for name in (*release.NEO_REQUIRED, 'atlas/dvd/sample.bin', 'texture-cards/card.txt'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((name + '\n').encode())
    return root


def test_neo_environment_and_explicit_override(tmp_path, monkeypatch):
    release = load(ROOT / 'tools/release.py')
    monkeypatch.setenv('DISC_NEO_DIR', str(tmp_path / 'from-env'))
    argv = ['--version', '1.0.0.0-alpha', '--out', str(tmp_path / 'out')]
    assert release.parse_args(argv)[1].neo == tmp_path / 'from-env'
    assert release.parse_args([*argv, '--neo', str(tmp_path / 'explicit')])[1].neo == tmp_path / 'explicit'


def test_neo_skip(tmp_path, capsys):
    release = load(ROOT / 'tools/release.py')
    result = release.build_disc_neo(None, tmp_path, '1.0.0.0-alpha')
    assert result['status'] == 'skipped' and result['files'] == []
    assert 'Disc Neo skipped' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('missing', ['README.md', 'README.zh.md', 'SCHEMA.md', 'PROVENANCE.json', 'LICENSE'])
def test_neo_required_file_refusal(tmp_path, missing):
    release = load(ROOT / 'tools/release.py')
    neo = make_neo(tmp_path / 'disc-neo', release)
    (neo / missing).unlink()
    candidates = tmp_path / 'candidates'
    candidates.mkdir()
    with pytest.raises(ValueError, match=missing.replace('.', r'\.')):
        release.build_disc_neo(neo, candidates, '1.0.0.0-alpha')
    assert not list(candidates.iterdir())


def test_neo_missing_directory_refusal(tmp_path):
    release = load(ROOT / 'tools/release.py')
    with pytest.raises(ValueError, match='directory'):
        release.build_disc_neo(tmp_path / 'absent', tmp_path, '1.0.0.0-alpha')


def test_neo_exact_inventory_and_read_only(tmp_path):
    release = load(ROOT / 'tools/release.py')
    neo = make_neo(tmp_path / 'Disc Neo 空间', release)
    before = {p.relative_to(neo).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in neo.rglob('*') if p.is_file()}
    candidates = tmp_path / 'candidates'
    candidates.mkdir()
    result = release.build_disc_neo(neo, candidates, '1.0.0.0-alpha')
    assert result['status'] == 'PASS'
    assert result['asset'] == 'disc-neo-1.0.0.0-alpha-preview.zip'
    with zipfile.ZipFile(candidates / result['asset']) as archive:
        assert set(archive.namelist()) == {'disc-neo/' + p for p in before}
        assert {entry['file'] for entry in result['files']} == set(archive.namelist())
        for entry in result['files']:
            data = archive.read(entry['file'])
            assert data == before[entry['file'].removeprefix('disc-neo/')][0]
            assert entry['size'] == len(data)
            assert entry['sha256'] == hashlib.sha256(data).hexdigest()
    after = {p.relative_to(neo).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
             for p in neo.rglob('*') if p.is_file()}
    assert after == before


def test_disc_lab_skip(tmp_path, capsys):
    release = load(ROOT / 'tools/release.py')
    checks = []
    result = release.build_disc_lab(tmp_path, tmp_path, '1.0.0.0-alpha', [], tmp_path, {}, checks)
    assert result['status'] == 'skipped'
    assert checks == [] and not list(tmp_path.iterdir())
    assert 'disclab/ absent from the frozen commit' in capsys.readouterr().out


@pytest.mark.parametrize('passes', [True, False])
def test_disc_lab_export_gate(tmp_path, passes):
    release = load(ROOT / 'tools/release.py')
    snapshot = tmp_path / 'snapshot'
    core = snapshot / 'discprobe'
    core.mkdir(parents=True)
    (core / '__init__.py').write_text('MARKER = "frozen-core"\n', encoding='utf-8')
    lab = snapshot / 'disclab'
    (lab / 'tests').mkdir(parents=True)
    (lab / '__init__.py').write_text('', encoding='utf-8')
    test = ('from pathlib import Path\nimport discprobe\nimport disclab\n'
            'def test_exported_lab():\n'
            '    assert discprobe.MARKER == "frozen-core"\n'
            f'    assert Path(discprobe.__file__).parent == Path({str(core)!r})\n'
            f'    assert Path(disclab.__file__).parent == Path({str(tmp_path / "disc-lab-check/disclab")!r})\n'
            f'    assert {passes!r}\n')
    (lab / 'tests/test_sample.py').write_text(test, encoding='utf-8')
    (lab / 'README.md').write_text('Small laboratory fixture.\n', encoding='utf-8')
    candidates = tmp_path / 'candidates'
    candidates.mkdir()
    logs = tmp_path / 'logs'
    logs.mkdir()
    checks = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    args = (snapshot, candidates, '1.0.0.0-alpha', [sys.executable, '-B'], logs, env, checks)
    if passes:
        result = release.build_disc_lab(*args)
        assert result['asset'] == 'disc-lab-1.0.0.0-alpha.zip'
        assert checks[-1]['exit_code'] == 0
    else:
        with pytest.raises(RuntimeError, match='disc-lab-pytest.log'):
            release.build_disc_lab(*args)
        assert checks[-1]['exit_code'] == 1
    assert not (tmp_path / 'assets').exists()
    with zipfile.ZipFile(candidates / 'disc-lab-1.0.0.0-alpha.zip') as archive:
        assert archive.read('disclab/tests/test_sample.py') == (lab / 'tests/test_sample.py').read_bytes()
        assert all(name.startswith('disclab/') for name in archive.namelist())
        assert not any(name.startswith('discprobe/') for name in archive.namelist())


def test_shared_manifest_and_sums(tmp_path):
    release = load(ROOT / 'tools/release.py')
    candidates = tmp_path / 'candidates'
    candidates.mkdir()
    sources = []
    for name, package in [('disc_probe-1.0.0.0a0.whl', 'disc-probe'),
                          ('disc-lab-1.0.0.0-alpha.zip', 'disc-lab'),
                          ('disc-neo-1.0.0.0-alpha-preview.zip', 'disc-neo')]:
        path = candidates / name
        path.write_bytes(name.encode())
        sources.append((path, package))
    assets = release.finalize_assets(tmp_path, sources, dict(status='PASS', disc_neo={'status': 'PASS'}))
    manifest = json.loads((assets / 'manifest.json').read_text())
    assert {p['package'] for p in manifest['assets']} == {'disc-probe', 'disc-lab', 'disc-neo'}
    assert {p['file'] for p in manifest['assets']} == {p.name for p, _ in sources}
    checksum_file = assets / 'SHA256SUMS.txt'
    assert b'\r' not in checksum_file.read_bytes()
    sums = dict(line.split('  ', 1)[::-1] for line in checksum_file.read_text().splitlines())
    assert set(sums) == {p.name for p in assets.iterdir()} - {'SHA256SUMS.txt'}
    for path in assets.iterdir():
        if path.name != 'SHA256SUMS.txt':
            assert sums[path.name] == release.sha256(path)
    for entry in manifest['assets']:
        assert entry['sha256'] == sums[entry['file']]
        assert entry['size'] == (assets / entry['file']).stat().st_size
    assert not (tmp_path / 'verified-assets').exists()


def test_failed_finalization_exposes_no_assets(tmp_path):
    release = load(ROOT / 'tools/release.py')
    with pytest.raises(FileNotFoundError):
        release.finalize_assets(tmp_path, [(tmp_path / 'missing.zip', 'disc-neo')], {})
    assert not (tmp_path / 'assets').exists()


def make_portable(tmp_path, output, inputs):
    builder = load(ROOT / 'tools/build_winpack.py')
    root = tmp_path / 'portable-stage'
    files = {
        'discprobe/data/troubleshoot.json': b'{"shared": true}',
        'discprobe/__main__.py': b'print("same application")\n',
        'python/python.exe': b'Windows runtime', builder.START_NAME: b'Windows launcher',
        'linux/python/bin/python3': b'Linux runtime', builder.LINUX_START: b'Linux launcher',
        'winpack-keep-list.json': b'{}', 'linuxpack-keep-list.json': b'{}',
        builder.READ_FIRST: 'Windows 和 Linux'.encode(),
    }
    files.update({name: (ROOT / name).read_bytes() for name in builder.DOWNLOAD_DOCS})
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    runtime = dict(python='3.13.14', dependencies={'opencv-python-headless': '5.0.0.93'})
    info = dict(windows=runtime, linux=runtime, pack_inputs=inputs)
    return tuple(builder.pack_portable(root, output, '1.0.0.0-alpha', info, {'trimmed': True}))


def test_portable_archives_sizes_and_launchers(tmp_path):
    full, windows, linux = make_portable(tmp_path, tmp_path, {'lock_sha256': '0' * 64})
    builder = load(ROOT / 'tools/build_winpack.py')
    for artifact, platform in ((full, 'full'), (windows, 'win64'), (linux, 'linux-x86_64')):
        with zipfile.ZipFile(artifact) as archive:
            prefix = artifact.stem + '/'
            info = json.loads(archive.read(prefix + 'release-build.json'))
            note = archive.read(prefix + builder.READ_FIRST).decode()
            for name in builder.DOWNLOAD_DOCS:
                doc = archive.read(prefix + name).decode()
                for entry in info['portable_packages'].values():
                    assert entry['file'] in doc
                    assert f"{entry['size'] / 1e6:.3f} MB" in doc
            names = {name.removeprefix(prefix) for name in archive.namelist()}
            assert (builder.START_NAME in names) == (platform != 'linux-x86_64')
            assert ('python/python.exe' in names) == (platform != 'linux-x86_64')
            assert ('linux/python/bin/python3' in names) == (platform != 'win64')
            assert (builder.LINUX_START in names) == (platform != 'win64')
            assert archive.read(prefix + 'discprobe/data/troubleshoot.json') == b'{"shared": true}'
            assert info['variant'] == platform
            assert info['portable_packages'][platform]['size'] == artifact.stat().st_size
            if platform == 'win64':
                assert builder.START_NAME in note and builder.LINUX_START not in note and 'linux-x86_64' in note
            if platform == 'linux-x86_64':
                assert builder.LINUX_START in note and builder.START_NAME not in note and 'win64' in note
                assert archive.getinfo(prefix + builder.LINUX_START).external_attr >> 16 & 0o777 == 0o755


@pytest.fixture
def rehearsal(tmp_path, monkeypatch):
    """Exercise orchestration with tiny local inputs and stub expensive gates."""
    release = load(ROOT / 'tools/release.py')
    checkout = tmp_path / 'checkout'
    (checkout / 'discprobe').mkdir(parents=True)
    (checkout / 'discprobe/version.py').write_text('__version__ = "old"\n', encoding='utf-8')
    cache = tmp_path / 'cache'
    cache.mkdir()
    out = tmp_path / 'out'
    state = dict(lab=False, failure=None, gates=[], commits=0)
    inputs = dict(lock_sha256='a'*64, windows=[dict(verified=True)], linux=[dict(verified=True)])
    monkeypatch.setattr(release, 'ROOT', checkout)
    monkeypatch.setattr(release, 'os', SimpleNamespace(name='nt', environ=dict(os.environ), walk=os.walk))
    monkeypatch.setattr(release, 'sys', SimpleNamespace(version_info=(3, 13), executable=sys.executable, version=sys.version))
    monkeypatch.setattr(release.shutil, 'which', lambda name: 'node')
    monkeypatch.setenv('DISC_NEO_DIR', '')
    # Use an isolated environment mapping rather than inheriting a staged folder.
    release.os.environ.pop('DISC_NEO_DIR', None)

    def clean():
        state['commits'] += 1
        if state['failure'] == 'final-clean' and state['commits'] == 2:
            raise RuntimeError('dirty tree after gates')
        return 'a' * 40

    def git(*args):
        if args[0] == 'archive':
            stream = io.BytesIO()
            files = {'discprobe/version.py': b'__version__ = "old"\n',
                     'discprobe/web/gui.json': b'{"gui_version":"test"}',
                     'INSTALL-linux.md': b'fake install guide', 'tests/test_smoke.mjs': b'// fake Node input'}
            if state['lab']:
                files['disclab/tests/test_lab.py'] = b'def test_lab(): assert True\n'
            with tarfile.open(fileobj=stream, mode='w') as archive:
                for name, data in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            return stream.getvalue()
        if args[0] == 'rev-parse':
            return str(checkout / '.git').encode()
        assert args[0] == 'cat-file'
        return b''

    def check(command, cwd, log, env, checks, timeout=3600):
        state['gates'].append(log.name)
        log.write_text('fake gate log\n', encoding='utf-8')
        code = 1 if state['failure'] == log.name else 0
        checks.append(dict(log=log.name, exit_code=code, sha256=release.sha256(log)))
        if code:
            raise RuntimeError(f'check failed: {log.name}')
        if log.name == 'pack-inputs.log':
            (out / 'pack-inputs.json').write_text(json.dumps(inputs), encoding='utf-8')
        if log.name == 'source-build.log':
            candidates = out / 'candidate-assets'
            candidates.mkdir()
            (candidates / 'disc_probe-1.0.0.0a0-py3-none-any.whl').write_bytes(b'fake wheel')
            (candidates / 'disc_probe-1.0.0.0a0.tar.gz').write_bytes(b'fake sdist')
        if log.name == 'winpack-build.log':
            winpack = out / 'winpack'
            winpack.mkdir()
            (winpack / 'disc-probe-1.0.0.0-alpha-core.zip').write_bytes(b'fake core package')
            make_portable(tmp_path, winpack, inputs)

    monkeypatch.setattr(release, 'clean_commit', clean)
    monkeypatch.setattr(release, 'git', git)
    monkeypatch.setattr(release, 'run_check', check)
    monkeypatch.setattr(release, 'subprocess', SimpleNamespace(
        check_output=lambda command, **kwargs: 'test-node\n' if command[0] == 'node' else '1.0.0.0a0\n'))
    argv = ['--version', '1.0.0.0-alpha', '--out', str(out), '--cache', str(cache)]
    return release, out, argv, state


@pytest.mark.parametrize('with_packages', [False, True])
def test_orchestration_packages_and_gates(rehearsal, tmp_path, with_packages):
    release, out, argv, state = rehearsal
    state['lab'] = with_packages
    if with_packages:
        neo = make_neo(tmp_path / 'disc-neo', release)
        argv += ['--neo', str(neo)]
    release.main(argv)
    expected = ['pack-inputs.log', 'source-build.log', 'sdist-equivalence.log', 'wheel-venv.log', 'wheel-dependencies.log',
                'wheel-install.log', 'wheel-pip-check.log', 'wheel-verify.log', 'pytest.log',
                'test_smoke.mjs.log', 'selftest.log', 'winpack-build.log']
    if with_packages:
        expected += ['disc-lab-pytest.log']
    assert state['gates'] == expected
    assert state['commits'] == 2
    manifest = json.loads((out / 'assets/manifest.json').read_text())
    assert manifest['public_version'] == '1.0.0.0-alpha'
    assert manifest['pep440_version'] == '1.0.0.0a0'
    assert manifest['pack_inputs'] == json.loads((out / 'pack-inputs.json').read_text())
    for platform in ('windows', 'linux'):
        assert manifest[platform]['dependencies'] == {'opencv-python-headless': '5.0.0.93'}
        assert f'# {platform}: Python 3.13.14 opencv-python-headless==5.0.0.93' in (
            out / 'assets/SHA256SUMS.txt').read_text(encoding='ascii')
    assert {p['package'] for p in manifest['assets']} == (
        {'disc-probe', 'disc-lab', 'disc-neo'} if with_packages else {'disc-probe'})
    assert manifest['disc_lab']['status'] == ('PASS' if with_packages else 'skipped')
    assert manifest['disc_neo']['status'] == ('PASS' if with_packages else 'skipped')
    assert len(manifest['assets']) == (9 if with_packages else 7)
    assets = out / 'assets'
    selected = manifest['portable_packages']
    assert set(selected) == {'full', 'win64', 'linux-x86_64'}
    assert all((assets / item['file']).stat().st_size == item['size'] for item in selected.values())
    sums = (assets / 'SHA256SUMS.txt').read_text(encoding='ascii')
    assert all(f"# {item['file']}: {item['size']} bytes" in sums for item in selected.values())
    assert (release.ROOT / 'discprobe/version.py').read_text() == '__version__ = "old"\n'


@pytest.mark.parametrize('failure', ['pack-inputs.log', 'source-build.log', 'sdist-equivalence.log', 'wheel-venv.log',
    'wheel-dependencies.log', 'wheel-install.log', 'wheel-pip-check.log', 'wheel-verify.log',
    'pytest.log', 'test_smoke.mjs.log', 'selftest.log', 'winpack-build.log', 'disc-lab-pytest.log', 'final-clean'])
def test_failed_gate_never_promotes_assets(rehearsal, failure):
    release, out, argv, state = rehearsal
    state.update(lab=True, failure=failure)
    with pytest.raises(RuntimeError):
        release.main(argv)
    assert not (out / 'assets').exists()
    if failure == 'pack-inputs.log':
        assert not list(out.rglob('*.zip'))
    assert json.loads((out / 'status.json').read_text())['status'] == 'FAIL'
    if failure != 'final-clean':
        assert state['gates'][-1] == failure


def test_missing_single_platform_prevents_release_promotion(rehearsal, monkeypatch):
    release, out, argv, _ = rehearsal
    run_check = release.run_check

    def remove_single(command, cwd, log, env, checks, timeout=3600):
        run_check(command, cwd, log, env, checks, timeout)
        if log.name == 'winpack-build.log':
            (out / 'winpack/disc-probe-1.0.0.0-alpha-win64.zip').unlink()

    monkeypatch.setattr(release, 'run_check', remove_single)
    with pytest.raises(FileNotFoundError, match='win64'):
        release.main(argv)
    assert not (out / 'assets').exists()
    assert json.loads((out / 'status.json').read_text())['status'] == 'FAIL'


def test_neo_output_overlap_refused(rehearsal, tmp_path, capsys):
    release, out, argv, state = rehearsal
    neo = make_neo(tmp_path / 'disc-neo', release)
    argv[argv.index('--out') + 1] = str(neo / 'output')
    with pytest.raises(SystemExit):
        release.main([*argv, '--neo', str(neo)])
    assert 'must not overlap' in capsys.readouterr().err
    assert state['gates'] == []
    assert not (neo / 'output').exists()


def test_set_version_aligns_disc_lab_requirement(tmp_path):
    import importlib.util, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('release_tool_align', root / 'tools/release.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    (tmp_path / 'discprobe').mkdir()
    (tmp_path / 'discprobe/version.py').write_text('"""v"""\n\n__version__ = "0.1.2.1"\n', encoding='utf-8')
    (tmp_path / 'disclab').mkdir()
    (tmp_path / 'disclab/compat.py').write_text('X = 1\nREQUIRED_DISCPROBE_VERSION = "0.1.2.1"\n', encoding='utf-8')
    release.set_version(tmp_path, '1.0.0.0-alpha')
    assert '__version__ = "1.0.0.0-alpha"' in (tmp_path / 'discprobe/version.py').read_text(encoding='utf-8')
    assert 'REQUIRED_DISCPROBE_VERSION = "1.0.0.0-alpha"' in (tmp_path / 'disclab/compat.py').read_text(encoding='utf-8')
