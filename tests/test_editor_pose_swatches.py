"""The design page's per-pose palettes (design/pose-swatches*.json): where they come from, that they are what the
generator makes from today's inputs, and that the lamp view can be asked for the same pose and scale."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from discprobe import editor_preview, simulate_a3, focal
from discprobe.hashing import file_sha256

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "discprobe/web/home/design"
spec = importlib.util.spec_from_file_location("editor_pose_swatches", ROOT / "tools/editor_pose_swatches.py")
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


def load(name):
    return json.loads((DESIGN / name).read_text(encoding="utf8"))


@pytest.mark.parametrize("name", ["pose-swatches.json", "pose-swatches-custom.json"])
def test_sources_and_hashes_are_recorded_and_current(name):
    d = load(name)
    assert d["source"]["palette_sha256"] == file_sha256(DESIGN / "swatches.json")
    assert d["source"]["generator_sha256"] == file_sha256(ROOT / "tools/editor_pose_swatches.py")
    assert d["model"]["table_sha256"] == file_sha256(simulate_a3.TABLE)
    assert d["model"]["table_signature"] == simulate_a3.tables()["signature"]
    assert d["model"]["module"] == "discprobe.simulate_a3" and d["model"]["entry"] == "swatches"
    assert d["model"]["delta_scale"] == 1. and d["model"]["focal_px"] == focal.VIDEO_FOCAL_PX
    assert d["source"]["pose"].endswith("pose_1x.json") and d["source"]["pose_sha256"]
    assert d["source"]["pose_sha256"] == file_sha256(ROOT / "data/focal/pose_1x.json")
    assert d["source"]["geometry_sha256"] == file_sha256(ROOT / "discprobe/focal.py")
    assert d["sets_sha256"] == G.sets_sha(d["sets"])
    assert d["order"] == [m["id"] for m in load("swatches.json")["swatches"].values()]


def test_every_phone_and_height_has_a_palette():
    d, c = load("pose-swatches.json"), load("pose-swatches-custom.json")
    assert [h["ruler_cm"] for h in d["heights"]] == [focal.DESIGN_RULER_CM, 30, 40, 50, 70]
    assert d["heights"][0]["camera_z_mm"] == focal.DESIGN_Z_MM and d["rig"]["lens_offset_mm"] == 28.45
    assert set(d["sets"]) == {f"{p['id']}@{h['id']}" for p in d["phones"] for h in d["heights"]}
    assert set(c["sets"]) == {f"{mm}@{h['id']}" for mm in d["custom"]["flash_mm"] for h in d["heights"]}
    assert d["sets"]["iphone17pro@21"]["camera"] == list(focal.CAMERA)
    assert d["sets"]["iphone17pro@21"]["flash"] == list(focal.FLASH)


@pytest.mark.parametrize("key", ["iphone17pro@21", "iphone17pro@70", "custom:32@30", "custom:10@70"])
def test_sets_are_what_the_generator_makes_today(key):
    materials = list(load("swatches.json")["swatches"].values())
    if key.startswith("custom:"):
        mm, h = key[7:].split("@")
        stored, flash = load("pose-swatches-custom.json")["sets"][key[7:]], float(mm)
    else:
        h = key.split("@")[1]
        stored, flash = load("pose-swatches.json")["sets"][key], focal.FLASH_Y_MM-focal.LENS_Y_MM
    z = next(x["camera_z_mm"] for x in G.HEIGHTS if x["id"] == h)
    assert G.one_set(materials, flash, z) == stored


def test_delta_scale_is_the_texture_lookup_only():
    mats = list(load("swatches.json")["swatches"].values())[:20]
    cam, fl = (0., 28.45, 206.5), (0., 76.35, 206.5)
    assert simulate_a3.swatches(mats, cam, fl) == simulate_a3.swatches(mats, cam, fl, delta_scale=1.)
    assert simulate_a3.swatches(mats, cam, fl, delta_scale=.93) != simulate_a3.swatches(mats, cam, fl)
    sig = simulate_a3.swatch_signal(mats, cam, fl, delta_scale=.93)
    assert set(sig) == {m["id"] for m in mats} and all(v >= 0 for v in sig.values())


def test_lamp_view_pose_takes_the_scale():
    assert editor_preview.pose_options({})["delta_scale"] == 1.
    assert editor_preview.pose_options({"camera": [0, 28.45, 206.5], "flash": [0, 76.35, 206.5], "delta_scale": .93})["delta_scale"] == .93
    for bad in (0, 2, "0.93", float("nan"), True):
        with pytest.raises(ValueError):
            editor_preview.pose_options({"delta_scale": bad})


def test_web_rig_panel_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    out = subprocess.run([node, str(ROOT / "tests/test_editor_rig.mjs")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
