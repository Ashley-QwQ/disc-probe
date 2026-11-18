"""Test the package launchers locally, without installing a runtime or touching a drive."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools import build_winpack


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def package(tmp_path):
    if os.name == "nt":
        git = shutil.which("git")
        candidates = (parent / "bin" / "bash.exe" for parent in Path(git).resolve().parents[1:3]) if git else ()
        bash = next((candidate for candidate in candidates if candidate.is_file()), None)
    else:
        bash = shutil.which("bash")
    if not bash or not Path(bash).is_file():
        pytest.skip("local Bash is required")
    root = tmp_path / "验收 Linux 包"
    root.mkdir()
    launcher = root / "start-linux.sh"
    shutil.copyfile(ROOT / launcher.name, launcher)
    stubs = tmp_path / "commands"
    stubs.mkdir()
    uname = stubs / "uname"
    uname.write_text('#!/bin/sh\nprintf "%s\\n" "$DP_TEST_UNAME"\n', encoding="ascii", newline="\n")
    uname.chmod(0o755)

    def run(script, *args, platform="Linux", shell="bash"):
        env = dict(os.environ, DP_TEST_UNAME=platform, DP_TEST_PYTHON=Path(sys.executable).as_posix(),
                   PYTHONIOENCODING="utf-8", BASH_ENV="", ENV="")
        return subprocess.run([str(bash), "--noprofile", "--norc", "-c",
                               'export PATH="$(cd "$1" && pwd):$PATH"; shift; exec "$@"',
                               "_", stubs.as_posix(), shell, script.as_posix(), *args], cwd=tmp_path,
                              env=env, capture_output=True, encoding="utf-8", timeout=20)
    return root, launcher, run


def test_linux_launcher_reports_wrong_package(package):
    _, launcher, run = package
    missing = run(launcher)
    assert missing.returncode == 1
    assert "解压不完整" in missing.stderr and "Bundled Python is missing" in missing.stderr


@pytest.mark.parametrize("platform", ["MINGW64_NT-10.0", "MSYS_NT-10.0", "CYGWIN_NT-10.0"])
def test_linux_launcher_points_windows_shells_to_bat(package, platform):
    _, launcher, run = package
    wrong_os = run(launcher, platform=platform)
    assert wrong_os.returncode == 1 and build_winpack.START_NAME in wrong_os.stderr


def test_linux_launcher_execs_bundled_python_from_package_root(package):
    root, launcher, run = package
    python = root / "linux/python/bin/python3"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nexec "$DP_TEST_PYTHON" -B report.py "$@"\n', encoding="ascii", newline="\n")
    python.chmod(0o755)
    (root / "report.py").write_text(
        'import json, sys\nfrom pathlib import Path\nprint(json.dumps([str(Path.cwd()), sys.argv[1:]]))\n',
        encoding="ascii")
    result = run(launcher, "--local-only", "--out", "my results")
    assert result.returncode == 0, result.stderr
    cwd, argv = json.loads(result.stdout)
    assert Path(cwd) == root
    assert argv == ["-X", "utf8", "-B", "-m", "discprobe", "webui", "--open",
                    "--local-only", "--out", "my results"]
    assert not (root / ".venv").exists()


def test_windows_batch_is_safe_in_sh_and_start_note_is_packaged(package):
    root, launcher, run = package
    build_winpack.write_start(root)
    batch = root / build_winpack.START_NAME
    assert batch.read_bytes().count(b"\r\n") == 2
    result = run(batch, shell="sh")
    assert result.returncode == 1 and "bash start-linux.sh" in result.stdout and not result.stderr
    note = "先看我 Read me first.txt"
    assert {launcher.name, note} <= set(build_winpack.SOURCE)
    windows, linux = (ROOT / note).read_text(encoding="utf-8").splitlines()
    assert batch.name in windows and "bash start-linux.sh" in linux
