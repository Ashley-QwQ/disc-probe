"""The pack CLI must reject modified original inputs before creating any ZIP."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.version_info[:2] != (3, 13), reason="pack CLI requires Python 3.13")


def receipt(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel(path, entry, *, version=None, platform=None):
    package = entry["name"].replace("-", "_")
    version = version or entry["version"]
    platform = platform or entry["platform"]
    info = f"{package}-{entry['version']}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{info}/METADATA", f"Name: {entry['name']}\nVersion: {version}\n")
        archive.writestr(f"{info}/WHEEL", f"Tag: {entry['python_tag']}-{entry['abi']}-{platform}\n")


@pytest.fixture
def inputs(tmp_path):
    script = tmp_path / "build_winpack.py"
    shutil.copyfile(ROOT / "tools/build_winpack.py", script)
    lock_file = tmp_path / "pack_inputs.lock.json"
    lock = json.loads((ROOT / "tools/pack_inputs.lock.json").read_bytes())
    cache = tmp_path / "cache"
    cache.mkdir()
    for target in ("windows", "linux"):
        for entry in lock[target]:
            path = cache / entry["file"]
            if entry["kind"] == "wheel":
                wheel(path, entry)
            else:
                path.write_bytes(b"runtime stub: invalid inputs are rejected before extraction")
            entry["sha256"] = receipt(path)
    return script, lock_file, lock, cache


@pytest.mark.parametrize(("platform", "name", "damage", "message"), [
    ("windows", "numpy", "byte", "SHA-256 mismatch"),
    ("windows", "cpython", "byte", "SHA-256 mismatch"),
    ("linux", "cpython", "byte", "SHA-256 mismatch"),
    ("linux", "cpython", "unstripped", "asset name does not match linux lock"),
    ("linux", "cpython", "missing", "missing locked linux input cpython"),
    ("windows", "pillow", "version", "METADATA name or version"),
    ("linux", "numpy", "platform", "WHEEL tag"),
    ("linux", "scipy", "missing", "missing locked linux input scipy"),
])
def test_invalid_input_refuses_to_create_archives(tmp_path, inputs, platform, name, damage, message):
    tool, lock_file, lock, cache = inputs
    entry = next(entry for entry in lock[platform] if entry["name"] == name)
    path = cache / entry["file"]
    if (platform, name) == ("linux", "cpython"):
        assert path.name.endswith("-install_only_stripped.tar.gz")
    if damage == "byte":
        data = path.read_bytes()
        path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    elif damage == "version":
        wheel(path, entry, version="0.0.1")
        entry["sha256"] = receipt(path)
    elif damage == "platform":
        wheel(path, entry, platform="win_amd64")
        entry["sha256"] = receipt(path)
    elif damage == "unstripped":
        entry["file"] = path.name.replace("-install_only_stripped", "-install_only")
        entry["url"] = entry["url"].replace("-install_only_stripped", "-install_only")
        path.rename(cache / entry["file"])
    else:
        path.unlink()
    lock_file.write_text(json.dumps(lock), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    for variant in ("core", "full", "win64", "linux-x86_64"):
        (out / f"disc-probe-main-{variant}.zip").write_bytes(b"stale package")
        (out / f"disc-probe-main-{variant}.zip.sha256").write_bytes(b"stale checksum")
    command = [sys.executable, "-X", "utf8", "-B", str(tool), "--cache", str(cache), "--out", str(out)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, encoding="utf-8", timeout=25)
    assert result.returncode != 0
    assert message in result.stderr and entry["file"] in result.stderr
    assert list(out.iterdir()) == []
