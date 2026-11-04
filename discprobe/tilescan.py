"""Read a flatbed scan of the tile palette target (see tiledisc.py).

1. Locate the disc and find its rotation and mirroring by correlating thin rings of the
   scan with the design (A5 cells as -1, 92 cells as +1, band-passed as in gridscan).
2. For every tile, sample the interior of each cell, decide the A5/92 polarity from the
   two finder slots, read the ten ID bits by comparing the cells of each pair, and check
   them against the tile that should sit there.
3. For every tile with a correct ID, express each palette swatch as a level on the tile's
   own A5 = 0 / 92 = 1 scale, in grey and per colour channel. Comparing swatches inside one
   tile cancels lamp shading and stray rainbow.

Writes tiles.csv (one row per tile) and summary.json (median level per swatch).
"""

from __future__ import annotations

import csv
import json
import math
import os

import numpy as np

from . import scan, tiledisc as T
from .imagedisc import CELL_MM, HALF_MM, SIZE

N_THETA = 8192
BAND = (20, 2500)
MIN_CONTRAST = 0.02        # |grey(92) - grey(A5)| a tile needs before its swatches count


def _label_rings(labels, textures, radii, mirrored):
    th = np.arange(N_THETA) * (2 * np.pi / N_THETA)
    if mirrored:
        th = -th
    ix = np.clip(np.floor((radii[:, None] * np.cos(th)[None, :] + HALF_MM) / CELL_MM).astype(int), 0, SIZE - 1)
    iy = np.clip(np.floor((HALF_MM - radii[:, None] * np.sin(th)[None, :]) / CELL_MM).astype(int), 0, SIZE - 1)
    value = np.zeros(len(textures))
    value[textures.index("A5")], value[textures.index("92")] = -1.0, 1.0
    return value[labels[iy, ix]]


def _band(f):
    F = np.fft.rfft(np.nan_to_num(f - np.nanmean(f, axis=1, keepdims=True)), axis=1)
    F[:, :BAND[0]] = 0
    F[:, BAND[1]:] = 0
    return F


def _rgb(path):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


def destripe(rgb, cy, r_px):
    """Divide out per-column sensor gain, measured on the blank paper below (or above) the disc."""
    lo, hi = int(cy + r_px * 1.08), rgb.shape[0]
    if hi - lo < 200:
        lo, hi = 0, int(cy - r_px * 1.08)
    if hi - lo < 200:
        return rgb, False
    col = np.median(rgb[lo:hi], axis=0)                  # columns x channels
    gain = col / np.median(col, axis=0, keepdims=True)
    return rgb / np.clip(gain, 0.5, 2.0)[None], True


def _plane(values, rows, cols):
    """Least-squares a + b*row + c*col per channel; returns a function of (row, col)."""
    A = np.column_stack([np.ones(len(rows)), rows, cols])
    coef, *_ = np.linalg.lstsq(A, values, rcond=None)
    return lambda r, c: np.array([1.0, r, c]) @ coef


def analyse(path: str, layout_path: str, out_dir: str, dpi: float = 600.0, log=print) -> dict:
    if "blind" in os.path.basename(path).lower():
        raise ValueError("refusing to read a file whose name contains 'blind'")
    with open(layout_path, encoding="utf-8") as f:
        lay = json.load(f)
    palette = lay["palette"]
    labels, textures, _ = T.design(palette)
    img, meta = scan.load_gray(path)
    px = (dpi or (meta[0] if meta else 600.0)) / 25.4
    outer, _ = scan.locate_disc(img, px)
    cx, cy, sx, sy = outer["cx"], outer["cy"], px, px * outer["ry"] / outer["rx"]
    rgb, destriped = destripe(_rgb(path), cy, outer["ry"])
    img = rgb.mean(-1)

    radii = np.arange(T.RING_EDGES_MM[0] + 0.6, T.RING_EDGES_MM[-1] - 0.6, 0.1)
    f, _ = scan.polar_rings(img, cx, cy, sx, sy, radii, n_theta=N_THETA, sub=1)
    S = _band(f)
    best = None
    for mirrored in (False, True):
        total = np.fft.irfft((S * np.conj(_band(_label_rings(labels, textures, radii, mirrored)))).sum(0), n=N_THETA)
        j = int(np.argmax(np.abs(total)))
        score = abs(total[j]) / np.std(total)
        if best is None or score > best[0]:
            best = (score, mirrored, j)
    score, mirrored, j0 = best
    rot = j0 * 2 * math.pi / N_THETA

    def to_px(r, th_design):
        th = (rot - th_design) if mirrored else (th_design + rot)
        return cx + r * sx * np.cos(th), cy - r * sy * np.sin(th), th

    def cell_mean(r_lo, r_hi, a_lo, a_hi):
        rr = r_lo + (r_hi - r_lo) * np.linspace(0.15, 0.85, 7)
        aa = a_lo + (a_hi - a_lo) * np.linspace(0.15, 0.85, 7)
        R, A = np.meshgrid(rr, aa)
        x, y, _ = to_px(R.ravel(), A.ravel())
        vals = np.stack([scan._sample(rgb[..., k], x, y) for k in range(3)], -1)
        return np.nanmean(vals, axis=0)

    rows, n_ok = [], 0
    for k, nsec in enumerate(lay["sectors_per_ring"]):
        r_in, r_out = T.RING_EDGES_MM[k] + T.GAP_MM / 2, T.RING_EDGES_MM[k + 1] - T.GAP_MM / 2
        dr = (r_out - r_in) / T.ROWS
        r_mid = (r_in + r_out) / 2
        for j in range(nsec):
            span = 2 * math.pi / nsec - T.GAP_MM / r_mid
            a0 = j * 2 * math.pi / nsec + T.GAP_MM / 2 / r_mid
            da = span / T.COLS
            cells = np.array([[cell_mean(r_in + row * dr, r_in + (row + 1) * dr, a0 + col * da, a0 + (col + 1) * da)
                               for col in range(T.COLS)] for row in range(T.ROWS)])        # rows x cols x rgb
            grey = cells.mean(-1)
            want = T.tile_cells(k, j, len(palette))
            a5, n92 = cells[want == -1].mean(0), cells[want == -2].mean(0)
            contrast = float(n92.mean() - a5.mean())
            ra, ca = np.nonzero(want == -1)
            rb, cb = np.nonzero(want == -2)
            ref_a5 = _plane(cells[want == -1], ra, ca)      # lamp shading across the tile
            ref_92 = _plane(cells[want == -2], rb, cb)
            a5_dark = grey[0, 0] + grey[1, 0] < grey[4, 3] + grey[5, 3]     # finder slot 0 (A5/A5) vs slot 11 (92/92)
            bits = []
            for s in range(1, 11):
                col, pair = divmod(s, 3)
                bits.append(int((grey[2 * pair, col] < grey[2 * pair + 1, col]) == a5_dark))
            ok = T.decode_slots(bits) == (k, j)
            n_ok += ok
            _, _, th_scan = to_px(r_mid, a0 + span / 2)
            row = {"ring": k, "sector": j, "radius_mm": round(r_mid, 2),
                   "design_angle_deg": round(math.degrees(a0 + span / 2), 2),
                   "scan_angle_deg": round(math.degrees(th_scan) % 360, 2),
                   "id_ok": int(ok), "a5_darker": int(a5_dark), "contrast": round(contrast, 4)}
            for i, name in enumerate(palette):
                col, pair = divmod(i, 3)
                sw = cells[2 * pair:2 * pair + 2, T.ID_COLS + col].mean(0)
                at = (2 * pair + 0.5, T.ID_COLS + col)
                lo_ref, hi_ref = ref_a5(*at), ref_92(*at)
                den = hi_ref - lo_ref
                lev = (sw - lo_ref) / np.where(np.abs(den) > 1e-6, den, np.nan)
                gden = float(hi_ref.mean() - lo_ref.mean())
                row[f"{name}_level"] = round(float((sw.mean() - lo_ref.mean()) / gden), 3) if abs(gden) > 1e-6 else ""
                row[f"{name}_rgb"] = " ".join(f"{v:.3f}" for v in sw)
                row[f"{name}_level_rgb"] = " ".join(f"{v:.2f}" for v in lev)
            rows.append(row)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "tiles.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    use = [r for r in rows if r["id_ok"] and abs(r["contrast"]) >= MIN_CONTRAST]
    levels = {}
    for name in palette:
        v = np.array([r[f"{name}_level"] for r in use], float)
        levels[name] = {"median": round(float(np.median(v)), 3), "q25": round(float(np.percentile(v, 25)), 3),
                        "q75": round(float(np.percentile(v, 75)), 3)} if len(v) else None
    summary = {"scan": os.path.abspath(path), "destriped": destriped, "mirrored": bool(mirrored),
               "rotation_deg": round(math.degrees(rot), 3),
               "rotation_score": round(float(score), 1), "tiles": len(rows), "ids_ok": int(n_ok),
               "tiles_used": len(use), "levels_a5_0_92_1": levels}
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    log(f"{os.path.basename(path)}: mirrored {mirrored}, rotation {summary['rotation_deg']} deg "
        f"(score {summary['rotation_score']}), IDs read {n_ok}/{len(rows)}, tiles used {len(use)}")
    return summary
