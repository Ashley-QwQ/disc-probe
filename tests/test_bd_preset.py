"""The Blu-ray preset: three numbers that DiscImageStudio turns back into a spiral.

DiscImageStudio keeps Blu-ray presets in their own file (`blu-ray-presets.json`), one record per
preset: an id, a display name, `parameters` (totalSectors, layerCount, innerRadiusMm, outerRadiusMm,
startAngleDegrees) and `invertMapping`. The pitch is not in the file on purpose -- with no pitch
coefficients the engine solves one constant pitch from the radii and the track length -- so what a
`geo --media bd` run has to supply is the radius of sector 0, the sector count, and a pitch good
enough to place the last sector.

Runs with pytest, or on its own: `python tests/test_bd_preset.py`.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from discprobe import bdexport                                  # noqa: E402

FIT = {"model": "clv", "media": "bd", "r0_mm": 24.6427, "pitch_um": 0.32, "v_m_s": 7.9054,
       "r2": 0.999994, "zones_used": 7, "anchor": "pitch 0.32 um", "pitch_um_anchor": 0.32}
SECTORS = 12_088_320        # what this BD-RE actually holds, 131 072 short of a full layer


def test_the_nominal_three_numbers_close_their_own_identity():
    """24.0 mm to 58.0 mm over a full layer is the standard 0.320 um pitch, to its rounding."""
    length = bdexport.track_length_mm(bdexport.BD_SECTORS_PER_LAYER)
    pitch_um = (58.0 ** 2 - 24.0 ** 2) * math.pi / length * 1e3
    assert abs(pitch_um - bdexport.BD_NOMINAL_PITCH_UM) < 2e-4, pitch_um


def test_the_outer_radius_follows_the_pitch_and_the_sector_count():
    outer = bdexport.outer_radius_mm(24.6427, 0.32, SECTORS)
    assert abs(outer - 58.0117) < 1e-3, outer


def test_a_pitch_follows_from_the_slope_when_the_run_measured_speed_instead():
    """The T^2 slope and the linear speed fix p on their own: p = a v^2 / (4 pi S)."""
    slope = 4 * math.pi * bdexport.sector_mm() * 0.32e-3 / (10.342 ** 2)
    assert abs(bdexport.pitch_um_from_slope(slope, 10.342) - 0.32) < 1e-4


def test_check_refuses_what_disc_image_studio_refuses():
    """Each of these is a condition in `BluRayDiscParameters.Validate`."""
    cases = [
        (dict(total_sectors=SECTORS + 1, inner_mm=24.6, outer_mm=58.0), "multiple of"),
        (dict(total_sectors=0, inner_mm=24.6, outer_mm=58.0), "multiple of"),
        (dict(total_sectors=bdexport.BD_SECTORS_PER_LAYER + 32, inner_mm=24.6, outer_mm=58.0), "no more than"),
        (dict(total_sectors=SECTORS, inner_mm=58.0, outer_mm=24.6), "0 < inner < outer"),
        (dict(total_sectors=SECTORS, inner_mm=24.6, outer_mm=61.0), "0 < inner < outer"),
        (dict(total_sectors=SECTORS, inner_mm=24.6, outer_mm=58.0, layer_count=2), "single-layer"),
    ]
    for kwargs, fragment in cases:
        try:
            bdexport.check(**kwargs)
        except bdexport.BdPresetError as e:
            assert fragment in str(e), (kwargs, str(e))
        else:
            raise AssertionError(f"accepted what DiscImageStudio would refuse: {kwargs}")


def test_the_parameters_come_from_the_fit_and_nothing_is_fitted_again():
    params = bdexport.parameters(FIT, SECTORS)
    assert params["totalSectors"] == SECTORS
    assert params["layerCount"] == 1
    assert params["innerRadiusMm"] == FIT["r0_mm"]
    assert abs(params["outerRadiusMm"] - 58.0117) < 1e-3
    assert params["startAngleDegrees"] == 0.0
    assert "pitchLinear" not in params and "channelBitLengthNm" not in params


def test_an_angular_fit_is_refused_rather_than_converted():
    try:
        bdexport.parameters({"model": None, "u": 1.0, "v": 1.0}, SECTORS)
    except bdexport.BdPresetError as e:
        assert "constant-linear-speed" in str(e)
    else:
        raise AssertionError("converted a u/v fit as if it were a linear-speed run")


def test_the_document_is_what_the_import_reader_reads():
    document = bdexport.document(bdexport.preset(FIT, SECTORS, "discprobe-bd-re", "BD-RE", "test"))
    assert set(document["parameters"]) == {"totalSectors", "layerCount", "innerRadiusMm",
                                          "outerRadiusMm", "startAngleDegrees"}
    assert document["luminanceMapping"] == {"invert": False}


def test_the_catalog_entry_has_no_field_the_catalog_does_not_store():
    """`BluRayPresetStore.Entry` is (id, displayName, parameters, invertMapping); a description there
    would be dropped on the next save and read as noise."""
    entry = bdexport.catalog_entry(bdexport.preset(FIT, SECTORS, "discprobe-bd-re", "BD-RE", "test"))
    assert set(entry) == {"id", "displayName", "parameters", "invertMapping"}


def _preset(**overrides):
    fit = dict(FIT, **overrides.pop("fit", {}))
    return bdexport.preset(fit, overrides.pop("sectors", SECTORS), overrides.pop("id", "discprobe-bd-re"),
                           "BD-RE (drive-timing calibration)", "test")


def test_install_is_idempotent_and_keeps_the_file_it_replaced():
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, bdexport.FILE_NAME)
        first = bdexport.install(_preset(), path)
        assert first["action"] == "added" and first["created"] and first["backup"] is None
        before = open(path, "rb").read()

        again = bdexport.install(_preset(), path)
        assert again["action"] == "unchanged" and not again["created"]
        assert open(path, "rb").read() == before, "an unchanged install rewrote the file"

        changed = bdexport.install(_preset(fit={"r0_mm": 24.65}), path, replace=True)
        assert changed["action"] == "replaced" and changed["backup"]
        assert open(changed["backup"], "rb").read() == before, "the backup is not the file it replaced"
        assert json.load(open(path, encoding="utf-8"))["presets"][0]["parameters"]["innerRadiusMm"] == 24.65


def test_install_refuses_to_overwrite_a_different_preset_of_the_same_id():
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, bdexport.FILE_NAME)
        bdexport.install(_preset(), path)
        try:
            bdexport.install(_preset(fit={"r0_mm": 24.65}), path)
        except bdexport.BdPresetError as e:
            assert "--replace" in str(e)
        else:
            raise AssertionError("overwrote a different preset without being asked")


def test_a_catalog_of_another_schema_is_left_alone():
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, bdexport.FILE_NAME)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"schemaVersion": 2, "presets": []}')
        try:
            bdexport.install(_preset(), path)
        except bdexport.BdPresetError as e:
            assert "schemaVersion 2" in str(e)
        else:
            raise AssertionError("wrote into a catalog whose layout it does not know")
        assert open(path, encoding="utf-8").read() == '{"schemaVersion": 2, "presets": []}'


def _run(*argv, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "discprobe", *argv], cwd=cwd,
                          capture_output=True, text=True, timeout=180)


def _summary(folder, **fit):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"fit": dict(FIT, **fit)}, f)


def test_the_command_writes_an_importable_document():
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        _summary(folder)
        out = os.path.join(work, "dis_preset_bd.json")
        proc = _run("disexport", "--geo", folder, "--sectors", str(SECTORS), "--output", out)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        document = json.load(open(out, encoding="utf-8"))
        assert document["parameters"]["totalSectors"] == SECTORS
        assert "Traceback" not in proc.stdout + proc.stderr


def test_the_command_installs_into_the_blu_ray_catalog_not_the_cd_one():
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        _summary(folder)
        catalog = os.path.join(work, "catalog", bdexport.FILE_NAME)
        proc = _run("disexport", "--geo", folder, "--sectors", str(SECTORS),
                    "--install", "--dis-presets", catalog)
        text = proc.stdout + proc.stderr
        assert proc.returncode == 0, text
        assert os.path.exists(catalog), text
        assert not os.path.exists(os.path.join(work, "catalog", "disc-presets.json")), text
        entry = json.load(open(catalog, encoding="utf-8"))["presets"][0]
        assert set(entry) == {"id", "displayName", "parameters", "invertMapping"}
        assert "Restart DiscImageStudio" in text


def test_the_command_says_why_the_angle_map_options_do_not_apply():
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        _summary(folder)
        for option in (("--correction", "0.1,0.2"), ("--along-track-frames", "206"),
                       ("--r-min", "25.0")):
            proc = _run("disexport", "--geo", folder, "--sectors", str(SECTORS), *option)
            text = proc.stdout + proc.stderr
            assert proc.returncode == 1, text
            assert "Blu-ray preset" in text, text
            assert "Traceback" not in text, text


def test_a_run_with_a_fitted_offset_says_the_radius_depends_on_it():
    """r0 and a free period offset are nearly one parameter, so a reader has to know it was fitted."""
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        _summary(folder, offset_ms=-0.246, sigma_offset_ms=0.104, r0_mm=25.0148)
        proc = _run("disexport", "--geo", folder, "--sectors", str(SECTORS),
                    "--output", os.path.join(work, "p.json"))
        text = proc.stdout + proc.stderr
        assert proc.returncode == 0, text
        assert "offset" in text.lower(), "it wrote a radius without saying the offset moved it"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as e:                                   # noqa: BLE001 - a test runner
                failures += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
            else:
                print(f"ok   {name}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
