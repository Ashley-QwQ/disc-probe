"""Re-fit a finished geo ladder under a different completion model, and watch r0 move.

A ladder records, for every target, the measured phase (mod one turn) and the channel bit n at
which the model says the read completed.  The along-track constant is exactly a constant shift
of n, so the whole question "how well does timing pin the constant down" can be asked offline:

  * shift every recorded n by d frames,
  * run the same fit the ladder would have run,
  * compare r0 and the residual rms with the original fit.

The identity behind it (docs/research/CD_GEOMETRY_INVESTIGATION.md) says the answer is a pure
translation of r0 -- down by 1.663 nm per frame on a CD when every n is shifted forward -- with
the residuals unchanged, whatever the data.

    python tools/cd_refit_along_offset.py results/geo-G-.../summary.json
    python tools/cd_refit_along_offset.py results/geo-G-.../summary.json --frames -300 300 61
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe import cd
from discprobe.calib import theta

FRAME_BITS = cd.FRAME_BITS


def load(path: str):
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    d = os.path.dirname(os.path.abspath(path))
    with open(os.path.join(d, "targets.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fit = summary.get("fit") or summary
    track = fit.get("track", "data")
    ref_lba = int(fit["reference_lba"])
    offset_bytes = float(fit.get("read_offset_bytes") or 0.0)
    if track == "audio":
        n_ref = (ref_lba + 1) * cd.SECTOR_BITS - offset_bytes * cd.SECTOR_BITS / cd.RAW_BYTES
    else:
        n_ref = float((ref_lba + 1) * cd.FRAMES_PER_SECTOR + cd.READ_TAIL_FRAMES) * FRAME_BITS
    n = np.array([float(r["n_bits"]) for r in rows])
    y = np.radians([float(r["unwrapped_deg"]) for r in rows])
    w = 1.0 / np.radians([max(float(r["sigma_deg"]), 1e-3) for r in rows])
    b = float(fit.get("bit_nm_assumed") or cd.BIT_NM) * 1e-6
    return dict(summary=summary, fit=fit, n=n, y=y, w=w, n_ref=n_ref, b=b, track=track)


def refit(d, delta_bits: float, u0: float, v0: float, sig_u: float, sig_v: float, iters: int = 20):
    """geo.Ladder.fit, with every n shifted by delta_bits."""
    n = d["n"] + delta_bits
    n_ref = d["n_ref"] + delta_bits
    y, w = d["y"], d["w"]
    u, v, c = u0, v0, 0.0
    for _ in range(iters):
        model = theta(n, u, v) - theta(n_ref, u, v) + c
        du, dv = _dtheta(n, u, v)
        du0, dv0 = _dtheta(n_ref, u, v)
        J = np.column_stack([du - du0, dv - dv0, np.ones_like(n)]) * w[:, None]
        r = (y - model) * w
        J = np.vstack([J, [1 / sig_u, 0, 0], [0, 1 / sig_v, 0]])
        r = np.concatenate([r, [(u0 - u) / sig_u, (v0 - v) / sig_v]])
        sc = np.sqrt((J ** 2).sum(axis=0))
        step, *_ = np.linalg.lstsq(J / sc, r, rcond=None)
        step /= sc
        u, v, c = u + step[0], v + step[1], c + step[2]
        if np.all(np.abs(step * sc) < 1e-9):
            break
    model = theta(n, u, v) - theta(n_ref, u, v) + c
    plain = y - model
    res = plain * w
    return (float(u), float(v), float(np.degrees(np.sqrt(np.mean(plain ** 2)))),
            float(res @ res / max(1, len(n) - 3)))


def _dtheta(n, u, v):
    s = np.sqrt(u * u + v * np.asarray(n, dtype=float) / math.pi)
    ds_du, ds_dv = u / s, np.asarray(n, dtype=float) / (2.0 * math.pi * s)
    den = (s + u) ** 2
    return -2.0 * n * (ds_du + 1.0) / den, -2.0 * n * ds_dv / den


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("summary", help="summary.json of a finished geo run")
    ap.add_argument("--frames", type=float, nargs=3, default=[-200.0, 200.0, 21],
                    metavar=("LO", "HI", "N"), help="along-track shifts to re-fit, in EFM frames")
    a = ap.parse_args()
    d = load(a.summary)
    fit = d["fit"]
    b = d["b"]
    u0, v0 = float(fit["u"]), float(fit["v"])
    sig_u, sig_v = 0.08 * u0, 0.15 * v0
    ref_r0 = float(fit["r0_mm_at_bit"])
    print(f"track {d['track']}, {len(d['n'])} targets, bit {b * 1e6:.3f} nm, "
          f"original fit r0 {ref_r0:.6f} mm pitch {float(fit['pitch_um_at_bit']):.6f} um")
    print(f"original residual rms {float(fit['residual_rms_deg']):.3f} deg")

    frames = np.linspace(a.frames[0], a.frames[1], int(a.frames[2]))
    rows = []
    for fr in frames:
        u, v, rms, chi2 = refit(d, fr * FRAME_BITS, u0, v0, sig_u, sig_v)
        rows.append((fr, u * b, v * b * 1e3, rms, chi2))
    hdr = "shift frames   r0 mm      delta r0 um   pitch um   rms deg   chi2/dof   nm per frame"
    print(hdr)
    print("-" * len(hdr))
    for (fr, r0, p, rms, chi2), prev in zip(rows, [None] + rows[:-1]):
        slope = "" if prev is None else f"{(r0 - prev[1]) * 1e6 / (fr - prev[0]):+8.3f}"
        print(f"{fr:12.1f}   {r0:9.6f}  {(r0 - ref_r0) * 1e3:+11.3f}   {p:8.6f}  {rms:7.3f}  {chi2:8.3f}   {slope}")

    moved = [r[1] - ref_r0 for r in rows]
    print(f"\nr0 moved by {(min(moved) * 1e3):+.3f} .. {(max(moved) * 1e3):+.3f} um over "
          f"{frames[0]:+.0f}..{frames[-1]:+.0f} frames; residual rms stayed "
          f"{min(r[3] for r in rows):.3f}..{max(r[3] for r in rows):.3f} deg")
    print("The data cannot choose between these fits: the along-track constant is not observable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
