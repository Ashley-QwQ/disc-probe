"""Run-bound photo L export; synthetic geometry, no drives or product servers."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pytest

from discprobe import cd, disexport, photo, webui, webui_catalog

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="along-track-", dir=ROOT) as folder:
        yield Path(folder)


def run_files(root, name="geo-H-20261111-010101", **fit_changes):
    folder = root / "results" / name
    folder.mkdir(parents=True)
    bit = cd.BIT_NM * 1e-6
    geo = dict(fit=dict(media="cd", u=25 / bit, v=.0016 / bit,
                        bit_nm_assumed=cd.BIT_NM, measured_span_mm=[26, 52],
                        chi2_per_dof=1, angle_sigma_measured_span_deg=.1,
                        **fit_changes),
               identity=dict(drive="Test drive model", firmware="1", disc="MID"),
               setup=dict(last_lba=299999, first_track_audio=False, read_method="read12"))
    summary = folder / "summary.json"
    summary.write_text(json.dumps(geo), encoding="utf-8")
    (folder / "targets.csv").write_text("header\n" + "point\n" * 10)
    record = dict(path=str(folder), media="cd", verdict="ok", L_frames=-105.25,
                  per_photo=[dict(id="photo-one"), dict(id="photo-two")],
                  burn_path=dict(burner="specific burner H:", path="DIS", mode="audio; delayed interleave on"),
                  source_geo=dict(run_id=folder.name,
                                  sha256=hashlib.sha256(summary.read_bytes()).hexdigest(),
                                  identity=geo["identity"], setup=geo["setup"],
                                  drive_identity=photo.drive_identity(geo, folder)))
    target = folder / "photo.json"
    target.write_text(json.dumps(record), encoding="utf-8")
    return summary, target, record


def write_record(path, record):
    path.write_text(json.dumps(record), encoding="utf-8")


def export(summary, target=None, output=None, **kwargs):
    return disexport.export(str(summary), 300000, None, str(output) if output else None,
                            26, 52, "test-photo", "Photo preset", photo_path=target, **kwargs)


def test_same_run_provenance_and_disc_batch_not_a_drive_identity(tmp_path):
    summary, target, record = run_files(tmp_path)
    record["source_geo"]["identity"]["disc"] = "a different batch label"
    write_record(target, record)
    decision = photo.photo_shift(summary, target, device_id="H:")
    assert decision["written"] and decision["frames"] == -105.25
    provenance = decision["provenance"]
    assert provenance["geo_run_id"] == summary.parent.name
    assert provenance["photo_json"] == str(target.resolve())
    assert provenance["drive_identity"]["model"] == "Test drive model"
    assert provenance["drive_identity"]["device_id"] == "H:"
    assert provenance["drive_identity"]["machine"]
    assert provenance["burn_path"] == record["burn_path"]
    assert provenance["verdict"] == "ok"
    assert provenance["photo_ids"] == ["photo-one", "photo-two"]


@pytest.mark.parametrize("change,reason", [
    ("run", "different_run"), ("drive", "different_drive"), ("device", "different_drive"),
    ("machine", "different_drive"), ("hash", "different_run"),
    ("unsure", "verdict_not_ok"), ("rejected", "verdict_not_ok"),
    ("missing", "missing_L"), ("null", "missing_L"), ("bool", "missing_L"),
    ("nan", "missing_L"), ("model_only", "unknown_drive"), ("legacy", "unknown_drive"),
])
def test_refusal_saves_geometry_without_L(tmp_path, change, reason):
    summary, target, record = run_files(tmp_path)
    device = "H:"
    if change == "run":
        record["path"] = str(summary.parent.with_name("other-geo"))
    elif change == "drive":
        record["source_geo"]["drive_identity"]["model"] = "Another drive"
    elif change == "device":
        device = "I:"  # same model still is not the same device
    elif change == "machine":
        record["source_geo"]["drive_identity"]["machine"] = "Another PC"
    elif change == "hash":
        record["source_geo"]["sha256"] = "0" * 64
    elif change in ("unsure", "rejected"):
        record["verdict"] = change
    elif change == "missing":
        record.pop("L_frames")
    elif change in ("null", "bool", "nan"):
        record["L_frames"] = {"null": None, "bool": True, "nan": float("nan")}[change]
    elif change == "model_only":
        record["source_geo"]["drive_identity"]["device_id"] = None
    elif change == "legacy":
        record["source_geo"].pop("drive_identity")
    write_record(target, record)
    output = tmp_path / "refused.json"
    result = export(summary, target, output, device_id=device)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == result
    assert saved["source"]["photo_shift"] == dict(written=False, reason=reason)
    assert "along_track_frames" not in saved["source"]
    assert "photo_provenance" not in saved["source"]
    assert "constant unknown" in saved["preset"]["description"]
    assert "constant 0" not in saved["preset"]["description"]


def test_different_directory_with_identical_summary_is_not_same_run(tmp_path):
    summary, target, record = run_files(tmp_path)
    other, _, _ = run_files(tmp_path, "geo-H-20261111-020202")
    assert summary.read_bytes() == other.read_bytes()
    assert photo.photo_shift(other, target)["reason"] == "different_run"


def test_missing_photo_never_becomes_zero_and_measured_zero_is_valid(tmp_path):
    summary, target, record = run_files(tmp_path)
    target.unlink()
    saved = export(summary)
    assert "along_track_frames" not in saved["source"]
    assert saved["source"]["photo_shift"]["reason"] == "no_photo"
    record["L_frames"] = 0
    write_record(target, record)
    assert export(summary)["source"]["along_track_frames"] == 0


def test_preset_roundtrip_carries_shift_in_DIS_geometry_and_description(tmp_path):
    summary, target, record = run_files(tmp_path, track="audio")
    output = tmp_path / "preset.json"
    export(summary, target, output)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["source"]["along_track_frames"] == record["L_frames"]
    assert json.loads(saved["preset"]["description"].split("; photo provenance: ")[1]) == saved["source"]["photo_provenance"]
    # Reconstruct DIS's map from the serialized preset, then compare it against
    # theta(n - L*588), allowing the free overall rotation used by the exporter.
    p = saved["preset"]
    n, angle, _ = disexport.dis_angle_map(p["innerRadiusMm"], p["outerRadiusMm"],
        p["pitchLinear"], p["pitchQuadratic"], p["pitchCubic"], p["sectors"], cd.BIT_NM, cd.SECTOR_BITS)
    geo = json.loads(summary.read_text())["fit"]
    shift = record["L_frames"] * cd.FRAME_BITS
    shifted_u = math.sqrt(geo["u"] ** 2 - geo["v"] * shift / math.pi)
    error = np.degrees(angle - disexport.target_angle(n, shifted_u, geo["v"], cd.BIT_NM))
    assert np.max(np.abs(error - error.mean())) < .01
    # The original explicit --along-track-frames mechanism produces the same map.
    target.unlink()
    manual = export(summary, along_track_frames=record["L_frames"])
    for key in ("innerRadiusMm", "outerRadiusMm", "pitchLinear", "pitchQuadratic", "pitchCubic"):
        assert p[key] == manual["preset"][key]


@pytest.mark.parametrize("selected_drive,expected", [("H:", True), ("I:", False)])
def test_explicit_cli_photo_path(tmp_path, selected_drive, expected):
    summary, target, _ = run_files(tmp_path)
    output = tmp_path / "path with spaces 照片.json"
    proc = subprocess.run([sys.executable, "-m", "discprobe", "calibrate", "--geo", str(summary.parent),
                           "--media", "cd", "--photo", str(target), "--drive", selected_drive,
                           "--sectors", "300000", "--preset", str(output)],
                          cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["source"]["photo_shift"]["written"] is expected
    assert ("along_track_frames" in saved["source"]) is expected
    assert ("written: -105.25 frames" if expected else "not written: different_drive") in proc.stdout


def test_legacy_disexport_cli_discovers_same_run_photo(tmp_path):
    summary, _, _ = run_files(tmp_path)
    output = tmp_path / "dis.json"
    proc = subprocess.run([sys.executable, "-m", "discprobe", "disexport", "--geo", str(summary),
                           "--sectors", "300000", "--output", str(output)], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(output.read_text())["source"]["along_track_frames"] == -105.25


def test_web_save_uses_same_drive_free_CLI_and_returns_saved_decision(tmp_path):
    summary, target, _ = run_files(tmp_path)
    payload = dict(action="disexport", media="cd", args=dict(geo=str(summary), photo=str(target),
                   reading_drive="I:", sectors=300000, output="presets/web.json"))
    argv, drive = webui.command(payload, tmp_path, [])
    assert drive is None
    assert argv[argv.index("discprobe") + 1] == "calibrate"
    assert "--preset" in argv and "--photo" in argv
    assert argv[argv.index("--drive") + 1] == "I:"
    proc = subprocess.run(argv, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    entry = webui_catalog.catalogue(tmp_path, tmp_path / "results")["cd"][0]
    saved = webui_catalog.save_entry(tmp_path, tmp_path / "results", dict(id=entry["id"], preset="presets/web.json"))
    assert saved["photo_shift"] == dict(written=False, reason="different_drive")


def test_parser_help_documents_explicit_path_and_refusal():
    from discprobe.__main__ import _build_parser
    _, sub, _ = _build_parser()
    help_text = sub.choices["calibrate"].format_help()
    for word in ("--geo", "--photo", "specific drive", "refusals", "never assumed zero"):
        assert word in help_text
