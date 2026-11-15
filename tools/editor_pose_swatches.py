"""Build the design page's colour palettes, one per phone and viewing height (pose first, colour second).

    python tools/editor_pose_swatches.py            # writes discprobe/web/home/design/pose-swatches*.json
    python tools/editor_pose_swatches.py --check    # recomputes and compares, writes nothing

Same model and same entry as the bundled swatches.json (tools/editor_assets.py): discprobe.simulate_a3.swatches,
the A3 v3 texture table (LED), one patch of each material at r = 40 mm, 3 o'clock. Only the pose changes:

* the placement sheet fixes the 1x lens 28.45 mm toward 12 o'clock from the disc centre and the phone turned so
  the flash sits further toward 12 o'clock (docs/goals/showcase/pose/pose_1x.json, make_rulers.py);
* the flash is D mm from the lens along that line: 47.9 mm on iPhone 17 Pro (Apple's drawing, (-43.66, 19.79)),
  any whole mm from 10 to 60 for a phone the person measures themself (unverified);
* the height is the lens above the disc's top face: 206.5 mm at the design height (pose_1x, the printed 21 cm
  ruler), and for the other heights the ruler mark above the table less disc and sheet (1.3 mm);
* the along-track factor is scaled by 0.93 as the release's labels are (pose numbers of the 3126 px focal length,
  --delta-scale 0.93), so a swatch is what the practice discs showed. The 3355 px refocus is not done here.

The first file holds the measured phone; the second (fetched only when someone types their own distance) the grid.
Each file records its inputs' hashes and the sha256 of its own `sets`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from discprobe import simulate_a3  # noqa: E402

DESIGN = ROOT / "discprobe/web/home/design"
PALETTE = DESIGN / "swatches.json"
OUT = DESIGN / "pose-swatches.json"
OUT_CUSTOM = DESIGN / "pose-swatches-custom.json"
POSE_1X = Path("D:/disc-probe/docs/goals/showcase/pose/pose_1x.json")   # not in the repo; hash recorded when present

LENS_OFFSET_MM = 28.45          # pose_1x chosen.camera[1]
DESIGN_Z_MM = 206.5             # pose_1x chosen.camera[2]
DISC_AND_SHEET_MM = 1.3         # make_rulers.py: 1.2 mm disc + 0.1 mm sheet under it
DELTA_SCALE = .93
DELTA_OFFSET = 0.
FOCAL_PX = 3126
SAMPLE_MM = (40., 0.)
PHONES = [dict(id="iphone17pro", name="iPhone 17 Pro", flash_mm=47.9, verified=True,
               source="Apple dimensional drawing: flash (-43.66, 19.79) mm from the 1x lens")]
HEIGHTS = [
    dict(id="21", ruler_cm=21, camera_z_mm=DESIGN_Z_MM, status="photo-checked",
         evidence="design height of the placement sheet; SHOW-D and SHOW-E photographed and compared"),
    *[dict(id=str(h), ruler_cm=h, camera_z_mm=round(h * 10 - DISC_AND_SHEET_MM, 1), status="photographed-model",
           evidence="photographed; the palette is the model's prediction, not yet compared swatch by swatch")
      for h in (30, 40, 50, 70)],
]
CUSTOM_FLASH_MM = list(range(10, 61))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sets_sha(sets: dict) -> str:
    return hashlib.sha256(json.dumps(sets, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def pose(flash_mm: float, z: float):
    return [0., LENS_OFFSET_MM, z], [0., round(LENS_OFFSET_MM + flash_mm, 3), z]


def one_set(materials, flash_mm, z):
    camera, flash = pose(flash_mm, z)
    lights = simulate_a3.swatches(materials, camera, flash, at=SAMPLE_MM, delta_scale=DELTA_SCALE)
    signal = simulate_a3.swatch_signal(materials, camera, flash, at=SAMPLE_MM, delta_scale=DELTA_SCALE)
    rgb = "".join("%02x%02x%02x" % tuple(lights[m["id"]]["rgb"]) for m in materials)
    # swatches()' own rule judges colour after the palette is brought to a common brightness; when hardly anything
    # diffracts (70 cm) that lifts the mirror's purple into "colour". So also: the texture's own light must be at
    # least the room seen in the mirror (simulate_a3.VEIL).
    bits = [bool(lights[m["id"]]["dark"]) or signal[m["id"]] < simulate_a3.VEIL for m in materials]
    dark = "".join("%x" % sum(b << (3 - j) for j, b in enumerate(bits[i:i + 4] + [False] * (4 - len(bits[i:i + 4]))))
                   for i in range(0, len(bits), 4))
    return dict(camera=camera, flash=flash, rgb=rgb, dark=dark)


def header(materials, palette_raw):
    head = dict(
        schema_version=1,
        model=dict(module="discprobe.simulate_a3", entry="swatches", table="discprobe/simulate_a3v3.npz",
                   table_sha256=sha(simulate_a3.TABLE), table_signature=simulate_a3.tables()["signature"],
                   delta_scale=DELTA_SCALE, dark_rule="swatches() dark, or own light < simulate_a3.VEIL (swatch_signal)", delta_offset=DELTA_OFFSET, focal_px=FOCAL_PX, sample_mm=list(SAMPLE_MM),
                   note="A3 v3 wave model (docs/goals/night/palette/a3card); same entry as swatches.json display_colours"),
        source=dict(palette="discprobe/web/home/design/swatches.json", palette_sha256=hashlib.sha256(palette_raw).hexdigest(),
                    generator="tools/editor_pose_swatches.py", generator_sha256=sha(Path(__file__)),
                    pose="docs/goals/showcase/pose/pose_1x.json",
                    pose_sha256=sha(POSE_1X) if POSE_1X.exists() else None,
                    rulers="docs/goals/showcase/template/make_rulers.py"),
        rig=dict(lens_offset_mm=LENS_OFFSET_MM, disc_and_sheet_mm=DISC_AND_SHEET_MM,
                 axes="mm; x right, y toward 12 o'clock, z up from the disc's top face; flash on the lens's 12 o'clock side"),
        encoding=dict(order="materials in swatches.json order", rgb="6 hex digits per material (sRGB)",
                      dark="1 bit per material, 4 per hex digit, first material = high bit; 1 = shows no colour here"),
        order=[m["id"] for m in materials],
    )
    return head


def build():
    raw = PALETTE.read_bytes()
    materials = list(json.loads(raw)["swatches"].values())
    main = header(materials, raw)
    main.update(phones=PHONES, heights=HEIGHTS,
                custom=dict(file="pose-swatches-custom.json", flash_mm=CUSTOM_FLASH_MM, verified=False))
    main["sets"] = {f"{p['id']}@{h['id']}": one_set(materials, p["flash_mm"], h["camera_z_mm"]) for p in PHONES for h in HEIGHTS}
    main["sets_sha256"] = sets_sha(main["sets"])
    custom = header(materials, raw)
    custom.update(heights=HEIGHTS, flash_mm=CUSTOM_FLASH_MM, verified=False)
    custom["sets"] = {f"{d}@{h['id']}": one_set(materials, d, h["camera_z_mm"]) for d in CUSTOM_FLASH_MM for h in HEIGHTS}
    custom["sets_sha256"] = sets_sha(custom["sets"])
    return main, custom


def dump(data) -> str:
    # one set per line keeps diffs readable; the rest indented
    sets = data.pop("sets")
    text = json.dumps(data, ensure_ascii=False, indent=1)
    data["sets"] = sets
    body = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, separators=(',', ':'))}" for k, v in sets.items())
    return text[:-2] + ',\n "sets": {\n' + body + "\n }\n}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    main_data, custom = build()
    out = [(OUT, main_data), (OUT_CUSTOM, custom)]
    bad = 0
    for path, data in out:
        text = dump(data)
        if a.check:
            same = path.exists() and json.loads(path.read_text(encoding="utf8"))["sets"] == data["sets"]
            print(path.name, "matches" if same else "DIFFERS")
            bad += not same
        else:
            path.write_text(text, encoding="utf8")
            print(f"{len(data['sets'])} sets -> {path.relative_to(ROOT)} ({len(text) // 1024} KB)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
