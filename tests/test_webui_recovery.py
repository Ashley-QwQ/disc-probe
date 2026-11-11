"""Command construction only; never starts a child or touches a drive."""
import sys
import pytest
from discprobe import webui


def test_recovery_arguments(tmp_path):
    drives = [{"id": "TEST"}]
    prefix = [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "discprobe"]
    for action, args in [("timing", {}), ("geo", {"speed": "keep"})]:
        argv, drive = webui.command(dict(action=action, drive="TEST", media="cd", args=args), tmp_path, drives)
        assert argv == prefix + [action, "--drive", "TEST", "--media", "cd"] + (["--speed", "keep"] if args else [])
        assert drive == "TEST"
    args = dict(geo="results/test", sectors=300000, output="presets/usable.json", r_min=28, r_max=48)
    argv, _ = webui.command(dict(action="disexport", media="cd", args=args), tmp_path, [])
    assert argv == prefix + ["disexport", "--media", "cd", "--geo", str(tmp_path / "results/test"), "--sectors", "300000", "--output", str(tmp_path / "presets/usable.json"), "--r-min", "28", "--r-max", "48"]
    for action in ("timing", "calibrate", "burn"):
        with pytest.raises(webui.APIError):
            webui.command(dict(action=action, drive="TEST", args={"speed":"keep"}), tmp_path, drives)
    for radius in (0, 59, float("nan"), "28", True):
        with pytest.raises(webui.APIError):
            webui.command(dict(action="disexport", args={**args, "r_min":radius}), tmp_path, [])
    for speed in ("KEEP", "keep --force", True, 0):
        with pytest.raises(webui.APIError):
            webui.command(dict(action="geo", drive="TEST", args={"speed":speed}), tmp_path, drives)


def test_export_radius_order(tmp_path):
    for lo, hi in [(48, 28), (28, 28)]:
        with pytest.raises(webui.APIError, match="r_min must be less"):
            webui.command(dict(action="disexport", args=dict(geo="results/test", sectors=300000,
                           r_min=lo, r_max=hi)), tmp_path, [])
