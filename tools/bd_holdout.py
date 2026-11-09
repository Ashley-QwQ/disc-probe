"""Measure places the fit never saw, and score the geometry there.

`geo --media bd` fits a line through the zones it happened to visit. A good R^2 says the line
describes *those* zones; it does not say the line predicts a sector nobody measured. This tool
does that second thing on a constant-linear-speed disc:

    python tools/bd_holdout.py --collect holdout.csv --drive G: --fractions 0.07,0.13,0.31,0.44,0.58,0.72,0.86,0.94
    python tools/bd_holdout.py --check results/geo-G-20261108-052047 holdout.csv --pitch 0.32

`--collect` only reads: it measures one period per fraction, writes lba/period/coherence/jitter,
and never writes the disc. `--check` is offline: it predicts the period at those same sectors from
the run's summary.json and reports the leftover in milliseconds and in millimetres of radius.

Residuals are reported two ways because the two answer different questions:

    T residual      the model's own units; what the fit's slope and intercept actually describe
    radius residual v*dT/(2*pi); what a preset would move if it trusted the geometry

For a disc read at a constant angular velocity there is no period to predict (the period is flat
by definition), so `--check` refuses with that reason instead of printing a meaningless zero.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _fractions(text: str) -> list[float]:
    out = []
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        value = float(piece)
        if not 0.0 < value < 1.0:
            raise ValueError(f"{value} is not a fraction between 0 and 1")
        out.append(value)
    if len(out) < 3:
        raise ValueError("give at least three fractions, or the check has nothing to say")
    return out


def collect(args) -> int:
    from discprobe import mmc
    from discprobe.spti import SptiDevice, raise_priority
    from discprobe.timing import TimingProbe

    fractions = _fractions(args.fractions)
    raise_priority()
    dev = SptiDevice(args.drive)
    try:
        probe = TimingProbe(dev, media=args.media, reps=args.reps,
                            speed_kbs=int(args.speed) if args.speed else None,
                            log=lambda s: print(s, flush=True))
        probe.setup()
        probe.cache_test()
        probe.settle_spindle()
        zones = probe.period_test(zones=tuple(fractions), announce_rotation=False)
    finally:
        dev.close()

    with open(args.collect, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["fraction", "lba", "period_ms", "coherence", "jitter_us"])
        for zone in zones:
            if not zone.get("period_ms"):
                continue
            writer.writerow([zone.get("fraction", ""), zone["lba"], f"{zone['period_ms']:.6f}",
                             f"{zone.get('coherence', 0.0):.4f}", f"{zone.get('jitter_us', 0.0):.1f}"])
    kept = [z for z in zones if z.get("period_ms")]
    print(f"{len(kept)} of {len(fractions)} zones measured; wrote {args.collect}")
    print("Now: python tools/bd_holdout.py --check <run dir> " + args.collect)
    return 0


def _model(run_dir: str) -> tuple[dict, dict]:
    path = os.path.join(run_dir, "summary.json")
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    fit = summary.get("fit") or {}
    if "slope_ms2_per_lba" not in fit:
        raise SystemExit(f"{path} has no constant-linear-speed fit; this check needs one")
    zones = fit.get("zones_used")
    if zones and int(zones) < 3:
        raise SystemExit(f"{path} kept only {zones} zones; a line through fewer than three "
                         "cannot be checked against held-out points")
    return summary, fit


def check(args) -> int:
    summary, fit = _model(args.check)
    setup = summary.get("setup") or {}
    last_lba = setup.get("last_lba")
    if last_lba is None:
        last_lba = (fit.get("per_lba") or {})
    slope = float(fit["slope_ms2_per_lba"])
    intercept = float(fit["intercept_ms2"])
    offset = float(fit.get("offset_ms") or 0.0)
    v_mm_ms = float(fit["v_m_s"])  # mm/ms and m/s are the same number
    r0_mm = float(fit["r0_mm"])
    pitch_um = float(fit.get("pitch_um") or 0.0)

    rows = []
    with open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lba = int(row["lba"])
            measured = float(row["period_ms"])
            predicted = math.sqrt(slope * lba + intercept) + offset
            residual_ms = measured - predicted
            radius_mm = v_mm_ms * residual_ms / (2 * math.pi)
            rows.append((lba, measured, predicted, residual_ms, radius_mm))
    if not rows:
        raise SystemExit(f"{args.csv} has no rows")
    if last_lba is not None and any(lba > int(last_lba) for lba, *_ in rows):
        print(f"note: some held-out sectors lie past the last one the run's drive reported ({last_lba})")

    n = len(rows)
    mean = sum(r[3] for r in rows) / n
    rms = math.sqrt(sum(r[3] ** 2 for r in rows) / n)
    centred = math.sqrt(sum((r[3] - mean) ** 2 for r in rows) / n)
    worst = max(rows, key=lambda r: abs(r[3]))
    print(f"{n} sectors the fit did not see, {os.path.basename(args.check.rstrip('/\\\\'))}")
    print(f"  model: pitch {pitch_um:.4f} um (anchor), r0 {r0_mm:.4f} mm, "
          f"v {v_mm_ms:.4f} m/s, R^2 {fit.get('r2')}")
    print(f"  period residual: rms {rms * 1e3:.1f} us, centred {centred * 1e3:.1f} us, "
          f"worst {worst[3] * 1e3:+.1f} us at sector {worst[0]}")
    print(f"  radius equivalent: rms {rms * v_mm_ms * 1e3 / (2 * math.pi) * 1e3:.2f} um, "
          f"worst {worst[4] * 1e3:+.2f} um")
    if centred * 1e3 < rms * 1e3 * 0.9:
        print("  (most of it is one offset, not shape: the line is parallel but displaced, "
              "which is what a wrong anchor of r0 or v looks like)")
    if args.json_out:
        payload = dict(run=args.check, held_out=n, slope_ms2_per_lba=slope, intercept_ms2=intercept,
                       offset_ms=offset, v_m_s=v_mm_ms, r0_mm=r0_mm, pitch_um=pitch_um,
                       rms_ms=rms, mean_ms=mean, centred_ms=centred,
                       worst=dict(lba=worst[0], residual_ms=worst[3], radius_um=worst[4] * 1e3),
                       points=[dict(lba=lba, measured_ms=m, predicted_ms=p, residual_ms=d,
                                    radius_um=rad * 1e3)
                               for lba, m, p, d, rad in rows])
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"  wrote {args.json_out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--collect", metavar="CSV", help="measure fresh sectors on the drive into this file")
    parser.add_argument("--drive", default="G:", help="drive letter or device node (default: G:)")
    parser.add_argument("--media", default="bd", choices=("bd", "dvd", "cd"), help="media family (default: bd)")
    parser.add_argument("--speed", type=float, default=None, help="requested read speed in kB/s")
    parser.add_argument("--reps", type=int, default=40, help="pairs per zone (default: 40)")
    parser.add_argument("--fractions", default="0.07,0.13,0.31,0.44,0.58,0.72,0.86,0.94",
                        help="where to measure, as fractions of the disc (default avoids the ends)")
    parser.add_argument("--check", metavar="RUN_DIR", help="score a finished run against a held-out CSV")
    parser.add_argument("csv", nargs="?", metavar="CSV", help="held-out measurements written by --collect")
    parser.add_argument("--pitch", type=float, default=None, help="unused when the run already fixed it")
    parser.add_argument("--fit-offset", action="store_true", help="keep a fitted period offset when predicting")
    parser.add_argument("--json", dest="json_out", metavar="PATH", help="write the numbers to this file")
    args = parser.parse_args(argv)

    if args.collect:
        return collect(args)
    if args.check:
        if not args.csv:
            parser.error("--check also needs the held-out CSV as its first argument")
        return check(args)
    parser.error("choose --collect or --check")


if __name__ == "__main__":
    raise SystemExit(main())
