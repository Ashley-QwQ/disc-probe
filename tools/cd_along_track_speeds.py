#!/usr/bin/env python3
"""Read CD ladders taken at different spindle speeds and fit the time-like part of `C`.

Why this exists
---------------
`docs/research/CD_GEOMETRY_INVESTIGATION.md` shows that a ladder measures `r0 + C`, never `C`
alone: shifting every read end by `d` frames is exactly a change of the fitted inner radius,
`dr0/dC = 1.663 nm/frame` at 25 mm. That identity does not care how fast the disc is read, so a
constant frame count stays degenerate with `r0`.

A frame count that comes from *time* does care. If the reader's completion path has a fixed
latency `tau`, reading a sector at linear speed `v` finishes `tau*v` millimetres early, which is
`tau*v/b` frames (`b` = channel bit length). Then

    r0_eff(v)^2 = r0^2 + k*(W + R0) + k*tau*v/b,          k = p*588*b/pi   [mm^2/frame]

which is a straight line in `v`. Its *slope* is the only piece of `C` a single disc and a single
drive can isolate; the intercept still mixes `r0` with the fixed part of `C`. Two speeds give the
slope, three give it an error bar, one gives nothing.

What it prints
--------------
Per run: what the drive actually did (`period_ms` at `reference_lba`, so `rpm` and the linear speed
there), and the fitted `r0`, pitch, residual and chi2. Then the straight-line fit above, the
implied `tau`, and a plain statement of whether the slope is distinguishable from zero. A slope
consistent with zero is a result: it says `C` is a track-length offset only, so no read command on
this drive will ever see it.

Quality
-------
A ladder's own chi2/dof says whether its r0 error is believable. Runs with chi2/dof above
`--max-chi2-nu` (default 3) are excluded before the fit, with the excluded run and the reason
printed; the rest enter the line with their r0 sigma inflated by `sqrt(max(1, chi2/dof))`. The
table still shows the raw sigma. With only two speeds the slope has no residual degrees of
freedom, so its error is formal and the output says so.

Usage
-----
    python tools/cd_along_track_speeds.py results/geo-G-2026*/summary.json
    python tools/cd_along_track_speeds.py --json out.json results/geo-G-2026*/summary.json
    python tools/cd_along_track_speeds.py --max-chi2-nu 0 results/geo-G-2026*/summary.json
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe import cd                                        # noqa: E402

SECTOR_BITS = cd.SECTOR_BITS          # 57624 channel bits per CD sector


def n_end(lba: int) -> float:
    """Where the nominal read of one mode 1 sector ends, in channel bits (geo.py:_n_end)."""
    return ((lba // 16 + 1) * 16) * SECTOR_BITS


def radius_mm(b_mm: float, u: float, v: float, n: float) -> float:
    return b_mm * math.sqrt(u * u + v * n / math.pi)


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    fit = summary.get("fit") or {}
    if "u" not in fit or "v" not in fit:
        raise SystemExit(f"{path}: no fit in this summary")
    if fit.get("media") not in (None, "cd"):
        raise SystemExit(f"{path}: fit media is {fit.get('media')!r}, not cd")
    b_nm = float(fit.get("bit_nm_assumed", 277.66208524226016))
    if not 200.0 < b_nm < 400.0:                      # DVDs and BDs fit a different bit length
        raise SystemExit(f"{path}: bit length {b_nm:.1f} nm is not a CD (277.66 nm)")
    b_mm = b_nm * 1e-6
    u, v = float(fit["u"]), float(fit["v"])
    r0 = u * b_mm
    pitch = v * b_mm
    sigma_r0 = (abs(float(fit["u_sigma"])) * b_mm) if fit.get("u_sigma") else None   # u_sigma is on u
    ref = fit.get("reference_lba")
    period_ms = fit.get("period_ms")
    if period_ms and ref is not None:
        r_ref = radius_mm(b_mm, u, v, n_end(int(ref)))
        rpm = 60_000.0 / float(period_ms)
        v_ref = 2 * math.pi * r_ref / (float(period_ms) / 1000.0)      # mm/s
    else:
        r_ref = rpm = v_ref = None
    chi2 = fit.get("chi2_per_dof")
    scale = math.sqrt(max(1.0, chi2)) if (chi2 is not None and sigma_r0) else 1.0
    return {
        "path": path,
        "u": u, "v": v, "bit_nm": b_mm * 1e6,
        "r0_mm": r0, "pitch_um": pitch * 1e3, "r0_sigma_mm": sigma_r0,
        "sigma_fit_mm": sigma_r0 * scale if sigma_r0 else None, "sigma_scale": scale,
        "chi2": chi2, "rms_deg": fit.get("residual_rms_deg"),
        "reference_lba": ref, "period_ms": period_ms,
        "r_ref_mm": r_ref, "rpm": rpm, "v_ref_mm_s": v_ref,
        "stopped": summary.get("stopped"),
        "rungs": _rungs(path),
    }


def _rungs(path: str) -> int | None:
    csv = os.path.join(os.path.dirname(path), "targets.csv")
    try:
        with open(csv, encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)
    except OSError:
        return None


def fit_line(rows: list[dict]) -> dict | None:
    """Weighted least squares of r0_eff^2 against v, with formal errors from the per-run sigma.

    Each run's sigma is its own r0 error inflated by sqrt(max(1, chi2/dof)): a ladder that does not
    fit its own model reports an r0 error that is too small, and scaling it is the cheap way to keep
    that run from dominating the slope. Formal, not residual-based: two speeds have no residual
    degrees of freedom, and what limits the slope there is how well each run knows its own r0.
    """
    use = [r for r in rows if r["v_ref_mm_s"] and r["sigma_fit_mm"]]
    if len(use) < 2:
        return None
    x = [r["v_ref_mm_s"] for r in use]
    y = [r["r0_mm"] ** 2 for r in use]
    sig = [2 * r["r0_mm"] * r["sigma_fit_mm"] for r in use]
    w = [1.0 / (s * s) for s in sig]
    sw = sum(w); sx = sum(wi * xi for wi, xi in zip(w, x)); sy = sum(wi * yi for wi, yi in zip(w, y))
    sxx = sum(wi * xi * xi for wi, xi in zip(w, x)); sxy = sum(wi * xi * yi for wi, xi, yi in zip(w, x, y))
    det = sw * sxx - sx * sx
    if abs(det) < 1e-30:
        return None
    slope = (sw * sxy - sx * sy) / det
    intercept = (sxx * sy - sx * sxy) / det
    var_slope = sw / det
    var_intercept = sxx / det
    chi2 = sum(wi * (yi - intercept - slope * xi) ** 2 for wi, xi, yi in zip(w, x, y))
    dof = len(use) - 2
    scale = max(1.0, chi2 / dof) if dof > 0 else 1.0
    slope_sigma = math.sqrt(var_slope * scale)
    worst = max(use, key=lambda r: r["r0_sigma_mm"])
    b_mm = worst["bit_nm"] * 1e-6
    p_mm = worst["pitch_um"] * 1e-3
    k = p_mm * 588 * b_mm / math.pi                 # mm^2 per frame
    tau = slope * b_mm / k
    tau_sigma = slope_sigma * b_mm / k
    spread_frames = (max(y) - min(y)) / k if k else None
    dr0_per_frame = k / (2 * worst["r0_mm"]) * 1e6   # nm per frame at r0
    return {"slope": slope, "slope_sigma": slope_sigma, "intercept": intercept,
            "intercept_sigma": math.sqrt(var_intercept * scale),
            "k_mm2_per_frame": k, "tau_s": tau, "tau_sigma": tau_sigma,
            "spread_frames": spread_frames, "dr0_nm_per_frame": dr0_per_frame,
            "chi2": chi2, "dof": dof, "n": len(use)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("summaries", nargs="+", help="geo summary.json files (globs are fine)")
    ap.add_argument("--json", help="also write the table and the fit here")
    ap.add_argument("--max-chi2-nu", type=float, default=3.0,
                    help="exclude runs whose ladder chi2/dof is above this before fitting "
                         "(0 disables; default 3)")
    args = ap.parse_args(argv)

    def bad(r):
        return (args.max_chi2_nu > 0 and r["chi2"] is not None
                and r["chi2"] > args.max_chi2_nu)

    paths = []
    for pattern in args.summaries:
        paths.extend(sorted(glob.glob(pattern)) or [pattern])
    rows = [load(p) for p in paths]
    rows.sort(key=lambda r: (r["v_ref_mm_s"] or 0.0, r["path"]))

    print(f"{'run':<40} {'rpm':>7} {'v mm/s':>8} {'r0 mm':>10} {'+- nm':>7} {'pitch um':>9} "
          f"{'rms deg':>8} {'chi2':>7} {'rungs':>5}")
    for r in rows:
        name = os.path.basename(os.path.dirname(r["path"]))
        rpm = f"{r['rpm']:.1f}" if r["rpm"] else "-"
        v = f"{r['v_ref_mm_s']:.1f}" if r["v_ref_mm_s"] else "-"
        rung = "-" if r["rungs"] is None else str(r["rungs"])
        sig_nm = f"{r['r0_sigma_mm'] * 1e6:.1f}" if r["r0_sigma_mm"] else "-"
        print(f"{name:<40} {rpm:>7} {v:>8} {r['r0_mm']:>10.6f} {sig_nm:>7} {r['pitch_um']:>9.4f} "
              f"{(r['rms_deg'] or 0):>8.3f} {(r['chi2'] or 0):>7.2f} {rung:>5}"
              + ("  (stopped)" if r["stopped"] else "")
              + (f"  (excluded: chi2/dof > {args.max_chi2_nu:g})" if bad(r) else ""))

    kept = [r for r in rows if not bad(r)]
    dropped = [r for r in rows if bad(r)]
    if dropped:
        print()
        print(f"Excluded {len(dropped)} run(s) with chi2/dof above {args.max_chi2_nu:g}:")
        for r in dropped:
            name = os.path.basename(os.path.dirname(r["path"]))
            print(f"  {name}: chi2/dof {r['chi2']:.2f} -- its ladder does not fit its own model, "
                  "so its r0 error is too small to weight a slope with.")
        print("  (--max-chi2-nu N changes the cut; 0 keeps every run.)")

    inflated = [r for r in kept if r["sigma_scale"] > 1.0]
    if inflated:
        print()
        print("The fit inflates each r0 error by sqrt(chi2/dof); the table shows the raw sigma:")
        for r in inflated:
            name = os.path.basename(os.path.dirname(r["path"]))
            print(f"  {name}: {r['r0_sigma_mm'] * 1e6:.1f} -> {r['sigma_fit_mm'] * 1e6:.1f} nm "
                  f"(chi2/dof {r['chi2']:.2f})")

    print()
    speeds = sorted({round(r["v_ref_mm_s"], 3) for r in kept if r["v_ref_mm_s"]})
    span_pct = ((speeds[-1] - speeds[0]) / (sum(speeds) / len(speeds)) * 100.0) if len(speeds) > 1 else 0.0
    result = {"speeds": speeds, "rows": [_public(r) for r in kept],
              "excluded": [_public(r) for r in dropped], "max_chi2_nu": args.max_chi2_nu,
              "fit": None}
    if not kept:
        print("All runs were excluded by the quality cut; nothing to fit.")
    elif not speeds:
        print("No run carries a usable period_ms/reference_lba, so there is no read speed to fit against.")
    elif len(speeds) < 2:
        lead = "After the quality cut one speed remains" if dropped else "One read speed here"
        print(f"{lead} ({', '.join(f'{s:.1f}' for s in speeds) or 'unknown'} mm/s). "
              "A single speed cannot separate the time-like part of C from r0: the answer is r0 + C, "
              "as CD_GEOMETRY_INVESTIGATION.md section 3 derives.")
    elif span_pct < 5.0:
        print(f"The read speeds span only {span_pct:.1f}% ({speeds[0]:.1f} to {speeds[-1]:.1f} mm/s). "
              "Those are the same speed for this purpose: the drive did not honour a change, or these are "
              "runs of one geometry. A slope fitted across a span that small is an extrapolation, not a "
              "measurement, so it is not fitted here.")
        result["span_pct"] = span_pct
    else:
        fit = fit_line(kept)
        if not fit:
            print("Two or more speeds remain, but the summaries do not carry period_ms and u_sigma, "
                  "so the straight-line fit cannot be weighted. Rerun with a current geo.")
        else:
            print(f"r0_eff^2 against v at the reference radius, {fit['n']} runs:")
            print(f"  slope      {fit['slope']:.6e} mm^2/(mm/s)  +- {fit['slope_sigma']:.2e}")
            print(f"  intercept  {fit['intercept']:.6f} mm^2")
            print(f"  k          {fit['k_mm2_per_frame']:.4e} mm^2/frame "
                  f"({fit['dr0_nm_per_frame']:.3f} nm/frame at this r0)")
            print(f"  spread     {fit['spread_frames']:+.2f} frames between the two extreme speeds "
                  f"({span_pct:.0f}% apart): the frame shift the time-like part alone accounts for")
            print(f"  tau        {fit['tau_s'] * 1e3:+.4f} ms  +- {fit['tau_sigma'] * 1e3:.4f} ms "
                  "(the time-like part of C)")
            print(f"  meaning    doubling the read speed moves the time-like part of C by "
                  f"{fit['slope'] * speeds[0] / fit['k_mm2_per_frame']:+.2f} frames")
            if fit["slope_sigma"] > 0:
                sigma = abs(fit["slope"] / fit["slope_sigma"])
            else:                                   # exact synthetic data: no scatter to weigh
                sigma = float("inf") if fit["slope"] else 0.0
            print()
            shown = ("exact" if sigma == float("inf")
                     else "more than 1000" if sigma > 1000 else f"{sigma:.1f}")
            if sigma < 3:
                print(f"The slope is {shown} sigma from zero. C has no measurable time-like part "
                      "here: it is a track-length offset, which no read command can separate from r0. "
                      "That is a result, not a failure: the constant has to come from optics or from "
                      "DIS calibration.")
            else:
                print(f"The slope is {shown} sigma from zero. C changes with read speed: "
                      f"tau = {fit['tau_s'] * 1e3:+.3f} ms, so C(v) = W + R0 + tau*v/b, and r0_eff at "
                      "one speed predicts the constant at another. The absolute value is still open.")
            if fit["n"] == 2:
                print()
                print("Only two speeds contribute: they define a slope, but with no residual degrees of "
                      "freedom its sigma is formal and cannot test whether the two runs agree. A third "
                      "speed is what would turn this into an error bar.")
            result["fit"] = fit

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nwrote {args.json}")
    return 0


def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "path"} | {"run": os.path.basename(os.path.dirname(r["path"]))}


if __name__ == "__main__":
    raise SystemExit(main())
