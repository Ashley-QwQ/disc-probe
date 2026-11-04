"""Colour lookup table from flash photos of a tile palette target (tiles / LUT v2 disc).

Each photo is fitted with discprobe.tilephoto (tiles whose ID decodes are the only ones
used, so a wrong fit cannot leak in). With the flash next to the lens, the along-track
diffraction condition depends only on the camera position C (from the homography and the
EXIF focal length): delta = 2 c.t, with c the unit vector from the tile to the camera and t
the track tangent. Output: one row per (photo, tile) with delta and every swatch colour,
and a chart with one colour strip per texture against delta.

Usage: python tools/flash_lut_tiles.py LAYOUT.json IMG_a.jpeg IMG_b.jpeg ...
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe import tilephoto  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from flash_lut import chart, focal_px, pose  # noqa: E402


def main(layout_path, photos, out_dir=os.path.join("results", "flash_lut_tiles")):
    with open(layout_path, encoding="utf-8") as f:
        palette = json.load(f)["palette"]
    rows = []
    for p in photos:
        name = os.path.splitext(os.path.basename(p))[0]
        s = tilephoto.analyse(p, layout_path, os.path.join(out_dir, name), mirrors=(False,))
        H = np.array(s["homography_disc_mm_to_px"])
        rgb = tilephoto.load_photo(p)
        C = pose(H, focal_px(p, rgb.shape[1], rgb.shape[0]), rgb.shape[1] / 2, rgb.shape[0] / 2)
        print(f"  camera at ({C[0]:.0f}, {C[1]:.0f}, {C[2]:.0f}) mm", flush=True)
        with open(os.path.join(out_dir, name, "tiles.csv"), encoding="utf-8") as f:
            for t in csv.DictReader(f):
                if t["id_ok"] != "1":
                    continue
                a, r = math.radians(float(t["design_angle_deg"])), float(t["radius_mm"])
                pt = np.array([r * math.cos(a), r * math.sin(a), 0.0])
                c = (C - pt) / np.linalg.norm(C - pt)
                row = {"photo": name, "ring": t["ring"], "sector": t["sector"],
                       "delta": round(float(2 * c @ np.array([-math.sin(a), math.cos(a), 0.0])), 4),
                       "view_tilt_deg": round(math.degrees(math.acos(c[2])), 1)}
                row.update({n: t[f"{n}_rgb"] for n in palette})
                rows.append(row)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "swatch_colours_vs_delta.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    import flash_lut
    flash_lut.NAMES = palette
    chart(rows, os.path.join(out_dir, "lut_chart.png"))
    d = [r["delta"] for r in rows]
    print(f"{len(rows)} verified tile observations, delta {min(d):.2f} .. {max(d):.2f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
