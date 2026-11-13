"""Release gate checks; no downloads or device access."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location('release_gate_test_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_only_changes_prepared_copy(tmp_path):
    release = load(ROOT / 'tools/release.py')
    original = (ROOT / 'discprobe/version.py').read_bytes()
    (tmp_path / 'discprobe').mkdir()
    target = tmp_path / 'discprobe/version.py'
    target.write_bytes(original)
    release.set_version(tmp_path, '1.0.0-alpha')
    assert '"1.0.0-alpha"' in target.read_text()
    assert (ROOT / 'discprobe/version.py').read_bytes() == original


def test_alpha_metadata_normalization(tmp_path, monkeypatch):
    backend = load(ROOT / '_build_backend.py')
    monkeypatch.setattr(backend, 'ROOT', tmp_path)
    (tmp_path / 'pyproject.toml').write_bytes((ROOT / 'pyproject.toml').read_bytes())
    (tmp_path / 'discprobe').mkdir()
    for public, canonical in [('1.0.0-alpha', '1.0.0a0'), ('1.0.0-alpha.1', '1.0.0a1'), ('1.0.0', '1.0.0')]:
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
