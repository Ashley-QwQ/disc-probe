"""Portable package checks; subprocesses only use virtual lab devices."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from disclab.__main__ import ROOT
from disclab.compat import REQUIRED_DISCPROBE_VERSION


def clean_env():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    for key in ("PYTHONPATH", "DISCPROBE_DISCLAB", "DISCLAB_ROOT"):
        env.pop(key, None)
    return env


def test_five_minute_example_tiny_box(tmp_path):
    config = json.loads((ROOT / "disclab/examples/dvd-r-12.json").read_text(encoding="utf-8"))
    config.update(count=2, iso_sectors=65536, reps=8, max_targets=6)
    config_path = tmp_path / "tiny.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    lab = tmp_path / "lab with spaces \u6d4b\u8bd5"
    command = [sys.executable, "-B", "-m", "disclab.examples", "--lab", str(lab),
               "--config", str(config_path)]
    result = subprocess.run(command, cwd=ROOT, env=clean_env(), capture_output=True,
                            text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads((lab / "scores/geo-wide.json").read_text(encoding="utf-8"))
    assert len(rows) == 2
    for row in rows:
        assert row["exit"] == 0
        assert Path(row["geo"], "summary.json").is_file()
        assert math.isfinite(row["du_bits"]) and math.isfinite(row["dv_rel"])
        for key in ("vs_timing_measured_span", "vs_timing_full", "placement_on_target"):
            for metric, value in row[key].items():
                assert math.isfinite(value), (key, metric, value)
                if "rms" in metric or "pp_deg" in metric:
                    assert value >= 0
        assert row["vs_timing_measured_span"]["rms_deg"] < 1
        assert abs(row["path_L_mm"] - 0.19) < 1e-12
    assert not list((lab / "iso").glob("*.iso"))
    assert "Wall time:" in result.stdout and "LAB-A 1-02 |" in result.stdout
    # A second invocation must refuse the existing folder without overwriting its box.
    before = (lab / "box.json").read_bytes()
    again = subprocess.run(command, cwd=ROOT, env=clean_env(), capture_output=True, timeout=15)
    assert again.returncode != 0 and (lab / "box.json").read_bytes() == before


def test_no_absolute_machine_paths():
    package = ROOT / "disclab"
    patterns = [r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]", r"\\\\[A-Za-z0-9_-]+\\",
                r"(?<![:/\w])/(?:home|Users|mnt|Volumes|tmp)/[^\s\"']+"]
    for path in package.rglob("*"):
        if any(part in {"__pycache__", "_package_checks", "dist", ".pytest_cache"}
               for part in path.relative_to(package).parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".ps1", ".sh", ".txt"}:
            continue
        content = path.read_text(encoding="utf-8")
        assert not any(re.search(pattern, content) for pattern in patterns), path.relative_to(package)


@pytest.mark.parametrize("layout", ["sibling", "installed"])
def test_unpacked_package_boot(tmp_path, layout):
    unpacked = tmp_path / "unpacked package \u6d4b\u8bd5"
    unpacked.mkdir()
    shutil.copytree(ROOT / "disclab", unpacked / "disclab",
                    ignore=shutil.ignore_patterns("__pycache__", "_package_checks", "dist"))
    env = clean_env()
    if layout == "sibling":
        shutil.copytree(ROOT / "discprobe", unpacked / "discprobe",
                        ignore=shutil.ignore_patterns("__pycache__"))
    else:
        # Model site-packages discovery independently of an adjacent source tree.
        site = tmp_path / "site-packages"
        shutil.copytree(ROOT / "discprobe", site / "discprobe",
                        ignore=shutil.ignore_patterns("__pycache__"))
        env["PYTHONPATH"] = str(site)
    lab = unpacked / "lab"
    box = subprocess.run([sys.executable, "-B", "-m", "disclab", "box", "--lab", str(lab), "--count", "2"],
                         cwd=unpacked, env=env, capture_output=True, text=True, timeout=20)
    assert box.returncode == 0, box.stdout + box.stderr
    # web also runs from LAB rather than from the unpacked package root.
    env["PYTHONPATH"] = os.pathsep.join([str(unpacked / "disclab/boot"), str(unpacked),
                                         env.get("PYTHONPATH", "")])
    env["DISCPROBE_DISCLAB"] = str(lab)
    code = "from discprobe.device import list_optical_drives; assert list_optical_drives() == ['X:']"
    child = subprocess.run([sys.executable, "-B", "-c", code], cwd=lab, env=env,
                           capture_output=True, text=True, timeout=20)
    assert child.returncode == 0, child.stdout + child.stderr


@pytest.mark.parametrize("version", [None, REQUIRED_DISCPROBE_VERSION + "-alpha"])
def test_missing_or_mismatched_discprobe_refused(tmp_path, version):
    unpacked = tmp_path / "package"
    shutil.copytree(ROOT / "disclab", unpacked / "disclab",
                    ignore=shutil.ignore_patterns("__pycache__", "_package_checks", "dist"))
    if version:
        dp = unpacked / "discprobe"
        dp.mkdir()
        (dp / "__init__.py").write_text("", encoding="utf-8")
        (dp / "version.py").write_text(f"__version__ = {version!r}\n", encoding="utf-8")
    # -S excludes installed packages so the missing case is independent of this host.
    result = subprocess.run([sys.executable, "-S", "-B", "-m", "disclab", "box", "--lab", "lab"],
                            cwd=unpacked, env=clean_env(), capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "Disc Lab requires disc-probe" in result.stderr
    assert "Traceback" not in result.stderr and not (unpacked / "lab").exists()
    env = clean_env()
    env["DISCPROBE_DISCLAB"] = str(unpacked / "lab")
    env["PYTHONPATH"] = str(unpacked / "disclab/boot")
    # Import sitecustomize explicitly under -S to exercise the same fail-closed boot.
    child = subprocess.run([sys.executable, "-S", "-B", "-c", "import sitecustomize"],
                           cwd=unpacked, env=env, capture_output=True, text=True, timeout=15)
    assert child.returncode != 0 and "Disc Lab requires disc-probe" in child.stderr
    assert "Traceback" not in child.stderr


@pytest.mark.parametrize("stage", ["random", "geo"])
def test_failed_loop_removes_iso(tmp_path, monkeypatch, stage):
    from disclab import loop
    from disclab.lab import Lab

    lab = Lab(tmp_path)
    image = lab.root / "iso/random.iso"

    def fake_dp(lab, args, **kwargs):
        image.parent.mkdir()
        image.write_bytes(b"partial image")
        if stage == "random":
            raise RuntimeError("random stopped")

    monkeypatch.setattr(loop, "dp", fake_dp)
    monkeypatch.setattr(loop, "burn", lambda *args: None)

    def fail_geo(*args, **kwargs):
        raise RuntimeError("geo stopped")

    monkeypatch.setattr(loop, "geo", fail_geo)
    with pytest.raises(RuntimeError, match="stopped"):
        loop.loop_geo(lab, discs=["test disc"], iso_sectors=1)
    assert not image.exists()
