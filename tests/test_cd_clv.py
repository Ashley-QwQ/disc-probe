"""CLV retry history and experimental CD geometry, entirely on simulated drives."""
import json
import math
from argparse import Namespace
from pathlib import Path
from functools import wraps
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import sys

import pytest

from discprobe import clv, guide, i18n, timing, webui_catalog
from discprobe.sim import SimDrive


def workspace_test(fn):
    """The package's small selftest runner calls these without pytest fixtures."""
    @wraps(fn)
    def run(tmp_path=None, *args, **kwargs):
        if tmp_path is not None:
            return fn(tmp_path, *args, **kwargs)
        with TemporaryDirectory() as folder:
            return fn(Path(folder), *args, **kwargs)
    return run


def args_for(root, media="cd", speed=1411, **extra):
    return Namespace(**dict(out=str(root), media=media, speed=speed, drive="E:",
                            sim="clv", sectors=1, transport="auto", **extra))


def save(root, args, summary, index=0):
    path = root / f"timing-SIM-{index:02d}-20261112-1200{index:02d}"
    path.mkdir()
    payload = {**summary, "args": vars(args), "simulated": True}
    (path / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload, path


def measure(media="cd", speed=1411, threshold=None):
    dev = SimDrive(mode="clv", media=media, jitter_us=2, outlier_rate=0,
                   cav_above_kbs=threshold)
    probe = timing.TimingProbe(dev, media=media, speed_kbs=speed, reps=8,
                               period_reads=40, stop_if_not_cav=True, log=lambda *a: None)
    return probe.run()


@workspace_test
def test_clv_at_every_speed_stops_suggesting(tmp_path):
    for media in ("cd", "dvd", "bd"):
        root = tmp_path / media
        root.mkdir()
        _clv_at_every_speed(root, media)


def _clv_at_every_speed(tmp_path, media):
    seen = []
    speed = guide.ALTERNATIVE_SPEEDS[media][0]
    for index in range(len(guide.ALTERNATIVE_SPEEDS[media])):
        args = args_for(tmp_path, media, int(speed))
        summary, path = save(tmp_path, args, measure(media, int(speed)), index)
        assert summary["period"]["rotation"]["mode"] == "CLV"
        seen.append(speed)
        advice = guide.speed_advice(args, media, summary)
        text = "\n".join(guide.after_timing(args, summary))
        assert "--speed None" not in text
        speed = advice["next_speed"]
        assert speed not in seen
        if speed is not None:
            assert f"--speed {speed}" in text
    assert set(seen) == set(guide.ALTERNATIVE_SPEEDS[media])
    assert advice["all_clv"] and advice["exhausted"]
    assert "constant linear speed" in text and "every speed tried" in text
    assert "--force" in text and "does not force CAV" in text
    assert not any(" timing " in line and "--speed" in line for line in text.splitlines())
    if media == "bd":
        assert "--media bd" in text and "--bd-zones 25" in text
        assert guide.scan(str(tmp_path))[0].media == "bd"
    if media == "cd":
        assert "--cd-clv" in text and "along-track" in text
    saved = guide.Result(str(path), "timing", "SIM", "20261112-120000")
    assert webui_catalog.measurement(saved)["speed_advice"]["exhausted"]


@workspace_test
def test_cd_changes_to_cav_at_high_speed(tmp_path):
    for index, speed in enumerate((1411, 2822, 4234, 5645)):
        args = args_for(tmp_path, speed=speed)
        summary, _ = save(tmp_path, args, measure(speed=speed, threshold=5645), index)
        mode = summary["period"]["rotation"]["mode"]
        text = "\n".join(guide.after_timing(args, summary))
        if speed < 5645:
            assert mode == "CLV"
            assert guide.speed_advice(args, summary=summary)["next_speed"] == str((2822, 4234, 5645)[index])
        else:
            assert mode == "CAV" and "Next, measure the geometry" in text


@workspace_test
def test_history_is_scoped_and_higher_speeds_come_first(tmp_path):
    summary = {"setup": {"family": "cd"}, "period": {"rotation": {"mode": "CLV"}}}
    for index, speed in enumerate((1411, 2822, 4234)):
        save(tmp_path, args_for(tmp_path, speed=speed), summary, index)
    args = args_for(tmp_path)
    assert guide.speed_advice(args, summary=summary)["next_speed"] == "5645"
    args.speed = 7056
    assert guide.speed_advice(args, summary=summary)["next_speed"] == "8467"
    args.sim = "cav"
    assert guide.speed_advice(args, summary=summary)["tried"] == ["7056"]
    args.sim = None
    assert guide.speed_advice(args, summary=summary)["tried"] == ["7056"]
    args.media = "dvd"
    assert guide.speed_advice(args, summary=summary)["next_speed"] == "3324"


@workspace_test
def test_geo_attempts_are_remembered_even_when_clv_stops_the_ladder(tmp_path):
    args = args_for(tmp_path, speed=2822)
    path = tmp_path / "geo-SIM-clv-20261112-120000"
    path.mkdir()
    summary = {"args": vars(args), "setup": {"family": "cd"}, "fit": None,
               "rotation_check": {"mode": "CLV"}, "simulated": True, "stopped": "CLV"}
    (path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert guide._other_speed(args) == "4234"
    assert guide.scan(str(tmp_path))[0].media == "cd"


@workspace_test
def test_real_history_identity_and_incomplete_runs(tmp_path):
    args = args_for(tmp_path)
    args.sim = None
    base = {"setup": {"family": "cd"}, "identity": {"drive": "HP SH-216DB", "firmware": "1"},
            "period": {"rotation": {"mode": "CLV"}}}
    for index, changes in enumerate(({}, {"drive": "F:"}, {"speed": 2822}, {"speed": 4234}, {"speed": 5645})):
        old = {**vars(args), **changes}
        summary = {**base, "args": old}
        if index == 2:
            summary["stopped"] = "interrupted"
        if index == 3:
            summary["identity"] = {"drive": "Other drive"}
        if index == 4:
            summary["setup"] = {"family": "dvd"}
        path = tmp_path / f"timing-E-20261112-1200{index:02d}"
        path.mkdir()
        (path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert guide.speed_advice(args, summary=base)["tried"] == ["1411"]
    assert guide.speed_advice(args, summary=base)["next_speed"] == "2822"
    args.drive = "e:"
    assert guide.speed_advice(args, summary=base)["tried"] == ["1411"]


@workspace_test
def test_plain_guide_does_not_restart_the_speed_list(tmp_path):
    args = args_for(tmp_path)
    args.sim = None
    for index, speed in enumerate(guide.ALTERNATIVE_SPEEDS["cd"]):
        args.speed = int(speed)
        path = tmp_path / f"timing-E-20261112-1200{index:02d}"
        path.mkdir()
        summary = {"args": vars(args), "period": {"rotation": {"mode": "CLV"}}}
        (path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with patch.object(guide, "optical_drives", return_value=["E:"]), patch.object(guide, "missing_packages", return_value=[]):
        text = "\n".join(guide.guide_lines("cd", str(tmp_path)))
    assert "every speed tried" in text
    assert not any(" timing " in line and "--speed" in line for line in text.splitlines())


@workspace_test
def test_cd_clv_solver_on_simulated_drive(tmp_path):
    for anchor in ("pitch", "speed"):
        _cd_clv_solver(tmp_path / anchor, anchor)


def _cd_clv_solver(tmp_path, anchor):
    dev = SimDrive(mode="clv", media="cd", jitter_us=2, outlier_rate=0)
    run = clv.ClvLadder(dev, media="cd", period_reads=60, log=lambda *a: None,
                        pitch_um=dev.spiral.pitch_mm * 1000 if anchor == "pitch" else None,
                        v_m_s=dev.clv_speed_mm_s / 1000 if anchor == "speed" else None)
    fit = run.run()
    assert fit["model"] == "clv" and fit["media"] == "cd"
    assert abs(fit["r0_mm"] - dev.spiral.r0_mm) < 0.005
    assert abs(fit["pitch_um"] - dev.spiral.pitch_mm * 1000) < 0.0001
    assert fit["r2"] > 0.99999
    assert fit["calibrated_angles"] is False and fit["along_track_frames"] is None
    run.summary["simulated"] = True
    path = tmp_path / "geo-SIM-20261112-120000"
    clv.write_outputs(run, str(path))
    result = guide.scan(str(tmp_path))[0]
    assert result.quality() == "experimental" and not result.geo_complete()
    assert guide.latest_geo("cd", str(tmp_path)) is None
    assert "not a calibrated" in guide.install_blocker(str(path / "summary.json"), allow_simulated=True)


def test_cd_clv_refuses_cav():
    run = clv.ClvLadder(SimDrive(mode="cav", media="cd"), media="cd", pitch_um=1.6, log=lambda *a: None)
    with pytest.raises(clv.ConstantAngularVelocity, match="without --cd-clv"):
        run.run()


@workspace_test
def test_cd_clv_cli_validates_anchor_before_opening(tmp_path):
    for options, message in (([], "needs an independently"),
        (["--linear-mm-s", "-1"], "finite and positive"), (["--pitch-um", "nan"], "finite and positive"),
        (["--linear-mm-s", "0"], "finite and positive"),
        (["--linear-mm-s", "19200", "--pitch-um", "1.6"], "Choose one"),
        (["--pitch-um", "1.6", "--clv-zones", "3"], "at least five")):
        result = subprocess.run([sys.executable, "-m", "discprobe", "geo", "--media", "cd", "--cd-clv",
                                 "--out", str(tmp_path), *options], capture_output=True, text=True)
        assert result.returncode != 0 and message in result.stderr
        assert not list(tmp_path.iterdir())


@workspace_test
def test_cd_clv_cli_and_export_boundary(tmp_path):
    result = subprocess.run([sys.executable, "-m", "discprobe", "geo", "--sim", "clv", "--media", "cd",
                             "--cd-clv", "--linear-mm-s", "19200", "--clv-zones", "9", "--out", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = next(tmp_path.glob("geo-*/summary.json"))
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["simulated"] is True and data["fit"]["media"] == "cd"
    assert data["args"]["cd_clv"] is True
    assert "not a calibrated" in result.stdout and "--install" not in result.stdout
    exported = tmp_path / "preset.json"
    result = subprocess.run([sys.executable, "-m", "discprobe", "disexport", "--geo", str(summary),
                             "--sectors", "359849", "--force", "--output", str(exported)],
                            capture_output=True, text=True)
    assert result.returncode != 0 and "Experimental CD CLV" in result.stderr
    assert not exported.exists()


@workspace_test
def test_new_advice_is_translated(tmp_path):
    args = args_for(tmp_path)
    summary = {"period": {"rotation": {"mode": "CLV"}}}
    i18n.use("zh")
    try:
        for line in guide.after_timing(args, summary):
            if line and not line.lstrip().startswith("python "):
                assert i18n.tr(line) != line, line
    finally:
        i18n.use("en")
