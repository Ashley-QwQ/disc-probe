"""Two runs of one disc at two linear speeds: does the period carry a constant offset?

Under a constant linear speed the time to turn once is T = 2*pi*r/v, with
r^2 = r0^2 + p*l*LBA/pi, so T^2 = a*LBA + b with

    a = 4*pi^2*p*l / v^2          b = (2*pi*r0 / v)^2

Two runs at different speeds share r0 and p but not v. If T is exactly the turn time, the two
runs are consistent only through one scale: a1/a2 must equal b1/b2, and that ratio is the speed
ratio squared. Any overall scale (p, r0, v all multiplied by k, k^2, k) fits just as well, which
is why a single anchor -- the standard pitch -- is still needed for absolute numbers.

What the two runs do buy is the *other* unknown. If the measured period is the turn time plus a
constant epsilon (a fixed cost per period estimate), then a1/a2 still says (v2/v1)^2, but
b1/b2 no longer does: the intercept picks up epsilon. With the pitch anchored, epsilon and r0
are then solvable together, and the answer to "is r0 24.68 mm or 24.0 mm?" becomes a measurement
rather than a choice of anchor.

    python tools/bd_two_speeds.py <run 1 folder> <run 2 folder> [--pitch-um 0.32]

Both folders are the ones `geo --media bd` writes; they hold zones.csv.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import numpy as np

BD_SECTOR_MM = 2.23945          # 30066.75 channel bits of 74.50 nm


def zones(folder: str, min_coherence: float = 0.90):
    path = os.path.join(folder, "zones.csv")
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    keep = [r for r in rows if float(r.get("coherence") or 0) >= min_coherence
            and float(r.get("period_ms") or 0) > 0]
    if len(keep) < 3:
        raise SystemExit(f"{path}: only {len(keep)} zone(s) with coherence >= {min_coherence}; "
                         f"a T^2 fit needs three")
    lba = np.array([float(r["lba"]) for r in keep])
    period = np.array([float(r["period_ms"]) for r in keep])
    return lba, period


def line(lba, period, offset_ms: float):
    """Least squares for T - offset = sqrt(a*LBA + b), which is linear in (a, b)."""
    y = (period - offset_ms) ** 2
    A = np.vstack([lba, np.ones_like(lba)]).T
    a, b = np.linalg.lstsq(A, y, rcond=None)[0]
    pred = np.sqrt(np.maximum(a * lba + b, 0.0)) + offset_ms
    return float(a), float(b), period - pred


def numbers(a: float, b: float, pitch_um: float):
    """pitch anchored: v from the slope, r0 from the intercept."""
    p_mm = pitch_um * 1e-3
    v = math.sqrt(4 * math.pi * p_mm * BD_SECTOR_MM / a)        # mm/ms == m/s
    r0 = math.sqrt(max(b, 0.0)) * v / (2 * math.pi)             # mm
    return r0, v


def scan(first, second, pitch_um: float, lo: float, hi: float, steps: int):
    best = None
    for eps in np.linspace(lo, hi, steps):
        rows, total = [], 0.0
        for lba, period in (first, second):
            a, b, resid = line(lba, period, eps)
            if a <= 0 or b <= 0:
                total = float("inf")
                break
            rows.append((a, b, resid, numbers(a, b, pitch_um)))
            total += float((resid ** 2).sum())
        if best is None or total < best[0]:
            best = (total, eps, rows)
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs=2, metavar="FOLDER", help="two geo --media bd run folders")
    ap.add_argument("--pitch-um", type=float, default=0.32)
    ap.add_argument("--min-coherence", type=float, default=0.90)
    ap.add_argument("--offset-range", type=float, nargs=2, default=(-3.0, 3.0), metavar=("LO", "HI"))
    ap.add_argument("--steps", type=int, default=1201)
    args = ap.parse_args(argv)

    data = [zones(f, args.min_coherence) for f in args.runs]
    for folder, (lba, period) in zip(args.runs, data):
        a, b, resid = line(lba, period, 0.0)
        r0, v = numbers(a, b, args.pitch_um)
        rms = math.sqrt(float((resid ** 2).mean()))
        print(f"{os.path.basename(folder.rstrip(os.sep))}: {len(lba)} zones, LBA {lba.min():.0f}-{lba.max():.0f}, "
              f"period {period.min():.2f}-{period.max():.2f} ms")
        print(f"    no offset: a={a:.6e} b={b:.3e} -> v {v:.4f} m/s, r0 {r0:.4f} mm, rms {rms:.4f} ms")

    total, eps, rows = scan(data[0], data[1], args.pitch_um, args.offset_range[0],
                            args.offset_range[1], args.steps)
    r0s = [r[3][0] for r in rows]
    vs = [r[3][1] for r in rows]
    print(f"\nwith one offset shared by both runs: eps = {eps:+.3f} ms, total sum of squares {total:.6e}")
    for (lba, period), (a, b, resid, (r0, v)) in zip(data, rows):
        print(f"    v {v:.4f} m/s, r0 {r0:.4f} mm")
    print(f"    the two runs' r0 agree to {abs(r0s[0] - r0s[1]) * 1000:.1f} um; "
          f"their speeds differ by {abs(vs[0] - vs[1]) / max(vs):.1%}")

    # How much does the answer move over the whole offset range? That is the honest error bar.
    lo, hi = args.offset_range
    edge = []
    for e in (lo, hi):
        rs, ok = [], True
        for lba, period in data:
            a, b, _ = line(lba, period, e)
            if a <= 0 or b <= 0:
                ok = False
                break
            rs.append(numbers(a, b, args.pitch_um)[0])
        if ok:
            edge.append((e, rs))
    if edge:
        spread0 = abs(edge[0][1][0] - edge[-1][1][0]) * 1000
        print(f"    r0's first run moves {spread0:.0f} um across offsets {edge[0][0]:+.1f}..{edge[-1][0]:+.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
