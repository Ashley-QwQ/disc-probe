"""Export a measured angle map as a DiscImageStudio DVD preset (cubic track pitch).

DiscImageStudio models a DVD by its inner and outer radius, the sector count, a fixed
channel bit length, and a pitch p(x) = p0 (1 + c1 x + c2 x^2 + c3 x^3), x = (r - ri) /
(ro - ri), with p0 set by the total track length. That is a different family from our
constant-pitch u, v model plus an angle correction phi(r), so the conversion is a fit:
ri, ro, c1, c2, c3 are chosen to reproduce our angle as a function of track position
over the measured radius range (an overall rotation is free), and the remaining angle
difference is reported so the export can be judged before use.

Thin-track approximation for arc length (ds = 2 pi r / p dr); against the exact arc
length this changes angles by well under 0.001 degree over a whole DVD.
"""

from __future__ import annotations

import json
import math

import numpy as np
from scipy.optimize import least_squares

from .calib import SECTOR_BITS, theta

GRID = 40001


def dis_angle_map(ri, ro, c1, c2, c3, total_sectors, bit_nm):
    """Track position n (channel bits) and accumulated angle (rad) on a radius grid."""
    b = bit_nm * 1e-6
    r = np.linspace(ri, ro, GRID)
    x = (r - ri) / (ro - ri)
    shape = 1 + c1 * x + c2 * x * x + c3 * x ** 3
    if np.any(shape <= 0):
        return None
    cum = lambda y: np.concatenate([[0.0], np.cumsum((y[1:] + y[:-1]) * 0.5 * np.diff(r))])
    length = total_sectors * SECTOR_BITS * b
    s_unit = cum(2 * np.pi * r / shape)          # arc length times p0
    p0 = s_unit[-1] / length
    n = s_unit / p0 / b
    th = cum(2 * np.pi / shape) / p0
    return n, th, p0


def target_angle(n, u, v, bit_nm, correction=None):
    """Our angle along the track: constant-pitch model, minus phi(r) when a correction is given
    (phi is counter-clockwise in data-side view, while the track angle runs clockwise)."""
    th = theta(n, u, v)
    if correction is not None:
        r = bit_nm * 1e-6 * np.sqrt(u * u + v * n / math.pi)
        th = th - np.radians(correction(r))
    return th


def fit_preset(u, v, bit_nm, total_sectors, r_lo, r_hi, correction=None):
    b = bit_nm * 1e-6
    n_lo = math.pi * ((r_lo / b) ** 2 - u * u) / v
    n_hi = math.pi * ((r_hi / b) ** 2 - u * u) / v
    n_eval = np.linspace(n_lo, n_hi, 600)
    want = target_angle(n_eval, u, v, bit_nm, correction)
    ri0 = u * b
    ro0 = b * math.sqrt(u * u + v * total_sectors * SECTOR_BITS / math.pi)
    scale = np.array([1e-3, 1e-3, 1e-4, 1e-4, 1e-4])   # mm, mm, relative

    def resid(z):
        ri, ro, c1, c2, c3 = np.array([ri0, ro0, 0, 0, 0]) + z * scale
        m = dis_angle_map(ri, ro, c1, c2, c3, total_sectors, bit_nm)
        if m is None:
            return np.full(len(n_eval), 1e3)
        n, th, _ = m
        d = np.interp(n_eval, n, th) - want
        return np.degrees(d - d.mean())

    sol = least_squares(resid, np.zeros(5), x_scale=1.0, xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=400)
    ri, ro, c1, c2, c3 = np.array([ri0, ro0, 0, 0, 0]) + sol.x * scale
    d = resid(sol.x)
    _, _, p0 = dis_angle_map(ri, ro, c1, c2, c3, total_sectors, bit_nm)
    return {"innerRadiusMm": float(ri), "outerRadiusMm": float(ro), "pitchLinear": float(c1),
            "pitchQuadratic": float(c2), "pitchCubic": float(c3), "p0_um": float(p0 * 1e3),
            "fit_range_mm": [r_lo, r_hi], "max_angle_diff_deg": float(np.max(np.abs(d))),
            "rms_angle_diff_deg": float(np.sqrt(np.mean(d * d))),
            "peak_to_peak_angle_diff_deg": float(d.max() - d.min())}


def preset_json(fit, total_sectors, bit_nm, preset_id, name, description):
    return {"id": preset_id, "displayName": name, "description": description,
            "totalSectors": total_sectors, "innerRadiusMm": fit["innerRadiusMm"],
            "outerRadiusMm": fit["outerRadiusMm"], "channelBitLengthNm": bit_nm,
            "pitchLinear": fit["pitchLinear"], "pitchQuadratic": fit["pitchQuadratic"],
            "pitchCubic": fit["pitchCubic"]}


def export(geo_summary: str, total_sectors: int, correction_path: str | None, out_path: str,
           r_lo: float, r_hi: float, preset_id: str, name: str) -> dict:
    with open(geo_summary, encoding="utf-8") as f:
        geo = json.load(f)["fit"]
    corr = None
    if correction_path:
        from .imagedisc import load_correction
        corr = load_correction(correction_path)
    fit = fit_preset(geo["u"], geo["v"], geo["bit_nm_assumed"], total_sectors, r_lo, r_hi, corr)
    desc = (f"Drive-timing calibration (discprobe){' + grid-scan angle correction' if corr else ''}; "
            f"fitted over {r_lo}-{r_hi} mm, max angle difference to the measured map "
            f"{fit['max_angle_diff_deg']:.3f} deg")
    out = {"preset": preset_json(fit, total_sectors, geo["bit_nm_assumed"], preset_id, name, desc), "fit": fit,
           "source": {"geo": geo_summary.replace("\\", "/").split("/")[-1],
                      "correction": correction_path.replace("\\", "/").split("/")[-1] if correction_path else None}}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out
