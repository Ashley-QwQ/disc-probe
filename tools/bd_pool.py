"""Pool several Blu-ray runs of one disc into a single geometry.

Every run of `geo --media bd` gives one straight line, T^2 = A + B*lba, and the two numbers it
returns (r0 and v) need the pitch as an anchor. Run the same disc at two speeds and the runs
describe the same spiral with different slopes, which is a constraint the separate fits never use:
with L the sector length and p the pitch,

    A = (2*pi*r0/v)^2,  B = 4*pi*p*L/v^2   =>   B = (p*L/(pi*r0^2)) * A

so every run shares the same ratio k = p*L/(pi*r0^2). Fitting all the runs together for (A_i, k) is one
Gauss-Newton problem in a handful of parameters, and it turns "the two runs agree to 20 um" into a
pooled radius with an honest tolerance, from the same data.

Usage:

    python tools/bd_pool.py results/geo-G-20261108-054613 results/geo-G-20261108-052047 --pitch 0.32
    python tools/bd_pool.py --glob "results/geo-G-20261108-05*" --pitch 0.32

The pitch is an anchor, exactly as in `geo`: pass `--pitch` (um) to get r0, or `--linear-mm-s`
(a linear speed measured some other way) to get the pitch with r0.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe import clv                                   # noqa: E402
from discprobe.geometry import NOMINAL                      # noqa: E402

COHERENCE_FLOOR = 0.90


def load_run(path: str, media: str = "bd") -> dict:
    """Read one run: its sectors, its periods, and the fit that already dropped bad zones."""
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    with open(os.path.join(folder, "summary.json"), encoding="utf-8") as handle:
        summary = json.load(handle)
    zones = (summary.get("period") or {}).get("zones") or []
    samples = [clv.Sample(lba=int(z["lba"]), period_ms=float(z["period_ms"]),
                          coherence=float(z.get("coherence", 1.0)), fraction=z.get("fraction"))
               for z in zones if z.get("period_ms")]
    if len(samples) < 3:
        raise SystemExit(f"{folder}: fewer than three zones with a period; nothing to pool")
    usable = [s for s in samples if s.coherence >= COHERENCE_FLOOR]
    one = clv.fit_t2(usable, sector_mm=NOMINAL[media].sector_mm)
    # The per-run fit is only used for what it threw away; the pooled fit below re-derives the rest.
    drop = set(one.dropped)
    kept = [s for index, s in enumerate(usable) if index not in drop]
    if len(kept) < 3:
        raise SystemExit(f"{folder}: fewer than three zones survive; nothing to pool")
    return {"folder": os.path.basename(folder), "samples": kept}


def pool(runs: list[dict], *, sector_mm: float, pitch_um: float) -> dict:
    """Solve T^2 = A_i * (1 + k * lba) with one k shared by every run."""
    x = [np.array([s.lba for s in r["samples"]], dtype=float) for r in runs]
    t = [np.array([s.period_ms for s in r["samples"]], dtype=float) for r in runs]
    # Start each A from that run's own intercept, and k from the middle run's slope ratio.
    a = []
    for i in range(len(runs)):
        y = t[i] ** 2
        slope, intercept = np.polyfit(x[i], y, 1)
        a.append(float(intercept))
    k = float(np.median([np.polyfit(x[i], t[i] ** 2, 1)[0] / a[i] for i in range(len(runs))]))

    def residuals(a: list[float], k: float) -> np.ndarray:
        return np.concatenate([(t[i] ** 2) - a[i] * (1.0 + k * x[i]) for i in range(len(runs))])

    free = len(runs) + 1
    for _ in range(60):
        r = residuals(a, k)
        blocks = []
        for i in range(len(runs)):
            jac = np.zeros((len(x[i]), free))
            jac[:, i] = -(1.0 + k * x[i])
            jac[:, -1] = -a[i] * x[i]
            blocks.append(jac)
        jac = np.vstack(blocks)
        try:
            step = np.linalg.lstsq(jac, -r, rcond=None)[0]
        except np.linalg.LinAlgError:
            break
        scale = 1.0
        # A is an intercept in ms^2 and k is per sector: a shared damping keeps both positive.
        while scale > 1e-6:
            trial_a = [a[i] + scale * step[i] for i in range(len(runs))]
            trial_k = k + scale * step[-1]
            if all(v > 0 for v in trial_a) and trial_k > 0:
                break
            scale *= 0.5
        a = [a[i] + scale * step[i] for i in range(len(runs))]
        k = k + scale * step[-1]
        if np.abs(step).max() * scale < 1e-12:
            break

    r = residuals(a, k)
    dof = max(1, len(r) - free)
    s2 = float((r ** 2).sum()) / dof
    blocks = []
    for i in range(len(runs)):
        jac = np.zeros((len(x[i]), free))
        jac[:, i] = -(1.0 + k * x[i])
        jac[:, -1] = -a[i] * x[i]
        blocks.append(jac)
    jac = np.vstack(blocks)
    cov = s2 * np.linalg.pinv(jac.T @ jac)

    p_mm = pitch_um * 1e-3
    r0_mm = math.sqrt(p_mm * sector_mm / (math.pi * k))
    sigma_r0 = r0_mm * 0.5 * math.sqrt(abs(cov[-1, -1])) / k
    speeds = [2 * math.pi * r0_mm / math.sqrt(a[i]) for i in range(len(runs))]   # mm/ms = m/s
    rows = []
    start = 0
    for i, run in enumerate(runs):
        piece = r[start:start + len(x[i])]
        start += len(x[i])
        rows.append({"run": run["folder"], "zones": len(x[i]), "a_ms2": a[i], "v_m_s": speeds[i],
                     "rms_ms2": float(np.sqrt((piece ** 2).mean()))})
    # What each run alone would have said, for the check the covariance cannot make: the pooled
    # tolerance assumes the zones are independent, but each run also carries its own offset.
    alone = []
    for i in range(len(runs)):
        slope, intercept = np.polyfit(x[i], t[i] ** 2, 1)
        alone.append(math.sqrt(p_mm * sector_mm / (math.pi * slope / intercept)))
    return {"k": k, "r0_mm": r0_mm, "sigma_r0_mm": sigma_r0, "pitch_um": pitch_um,
            "sector_mm": sector_mm, "dof": dof, "rms_ms2": math.sqrt(s2), "runs": rows,
            "alone_mm": alone, "cov": cov}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pool Blu-ray runs of one disc into one geometry.")
    parser.add_argument("runs", nargs="*", help="result directories (or their summary.json)")
    parser.add_argument("--glob", default=None, help="shell-style pattern of result directories")
    parser.add_argument("--pitch", type=float, default=0.32, help="track pitch in um to anchor on")
    parser.add_argument("--media", default="bd")
    args = parser.parse_args(argv)

    paths = list(args.runs)
    if args.glob:
        paths.extend(sorted(p for p in glob.glob(args.glob) if os.path.isdir(p)))
    if len(paths) < 2:
        parser.error("give at least two runs (a shared ratio needs two different lines)")

    runs = [load_run(path, media=args.media) for path in paths]
    result = pool(runs, sector_mm=NOMINAL[args.media].sector_mm, pitch_um=args.pitch)

    print(f"{len(runs)} runs, {sum(r['zones'] for r in result['runs'])} zones, "
          f"{result['dof']} degrees of freedom")
    for row in result["runs"]:
        print(f"  {row['run']:<28} {row['zones']:>3} zones  A = {row['a_ms2']:10.4f} ms^2  "
              f"v = {row['v_m_s']:7.4f} m/s  rms = {row['rms_ms2']:.4f} ms^2")
    print(f"shared ratio k = pL/(pi r0^2) = {result['k']:.6e} 1/sector")
    print(f"r0 = {result['r0_mm']:.4f} +- {result['sigma_r0_mm']:.4f} mm  (pitch anchored at "
          f"{result['pitch_um']:g} um, rms {result['rms_ms2']:.4f} ms^2)")
    spread = max(r["v_m_s"] for r in result["runs"]) - min(r["v_m_s"] for r in result["runs"])
    print(f"the runs span {spread:.4f} m/s, and one k describes all of them")
    alone = result["alone_mm"]
    print(f"one at a time they would say r0 = {min(alone):.4f} .. {max(alone):.4f} mm "
          f"(spread {(max(alone) - min(alone)) * 1000:.1f} um)")
    if (max(alone) - min(alone)) > 3 * result["sigma_r0_mm"]:
        print("the runs disagree by more than the pooled tolerance, so that tolerance is the fit's and "
              "not the model's: each run carries its own offset, and the covariance does not know it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
