"""Re-estimate a `geo` run's rung phases from its events.csv and refit, with each phase estimator.

    python tools/geo_reanalyse.py results/geo-E-...  [--compare RI RO]

No new measurement: every rung's reference and target reads are rebuilt from events.csv (the same
usable-read filter as the run), the block's period is fitted as `geo` fits it (the prior is the
rung's own recorded period, since a run's period can change partway), and the phase of the targets
is estimated three ways:

  interp  robust_circular_mean of phase_offsets, what `geo` used before: each target is corrected by
          its two neighbouring reference reads, then the targets are clipped at 5 x MAD about
          their circular mean
  median  what `geo` does now: the same corrections, clipped at 4 x MAD (at least 1.5 deg) about
          their median (robust_median_mean)
  line    not in `geo`, here for comparison: the reference drift from a straight line through the
          block's reference reads instead of the neighbours, the same median clip, and a sem that
          adds the line's own uncertainty

Each set is unwrapped with the run's own predictions and fitted with geo's fit. The "recorded"
row is the run as written. The rebuild check compares the rebuilt phases with the recorded ones
for the estimator the run used; 0.000 deg says the blocks are the run's own.
--compare RI RO prints the inner and outer radius differences against values from elsewhere
(a CD audio run's dis_equivalent, in mm).
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe import analysis, cd  # noqa: E402
from discprobe.geo import MIN_SIGMA_DEG, Ladder  # noqa: E402

VARIANTS = ("interp", "median", "line")


def blocks(events, usable):
    """(target lba, usable reference times, usable target times) per measurement block, in order.
    A block is a run of (reference, target) pairs for one target; a settle read starts a new one."""
    out, ref, cur = [], None, None
    for e in events:
        if e["label"] == "settle":
            cur = None
        elif e["label"] == "ref":
            ref = e
        elif e["label"] == "target":
            lba = int(e["lba"])
            if cur is None or cur[0] != lba:
                cur = (lba, [], [])
                out.append(cur)
            if ref is not None and usable(ref):
                cur[1].append(int(ref["t_end_ns"]))
            if usable(e):
                cur[2].append(int(e["t_end_ns"]))
            ref = None
    return out


def phase_line(fit, x_t):
    """Phase of the targets with the reference drift from a straight line through the block's kept
    reference residuals. sem_deg adds the line's own uncertainty, from the reference scatter."""
    ref = [(fit.times_s[i], r) for i, r in enumerate(fit.residuals_s) if r is not None]
    if len(ref) < 3:
        return {"mean_deg": None}
    tm = statistics.fmean(t for t, _ in ref)
    rm = statistics.fmean(r for _, r in ref)
    sxx = sum((t - tm) ** 2 for t, _ in ref)
    slope = sum((t - tm) * (r - rm) for t, r in ref) / sxx if sxx > 0 else 0.0
    ref_sd = math.sqrt(sum((r - rm - slope * (t - tm)) ** 2 for t, r in ref) / max(1, len(ref) - 2))
    angles = []
    for tn in x_t:
        t = (tn - fit.base_ns) * 1e-9
        frac = ((t - fit.t0_s) / fit.period_s) % 1.0
        angles.append((analysis.TWO_PI * (frac - (rm + slope * (t - tm)) / fit.period_s)) % analysis.TWO_PI)
    ph = analysis.robust_median_mean(angles)
    ref_deg = 360.0 * ref_sd / fit.period_s
    ph["sem_deg"] = round(math.sqrt(ph["std_deg"] ** 2 / ph["used"] + ref_deg ** 2 / len(ref)), 3)
    return ph


def estimate(variant, fit, x_t):
    if variant == "interp":
        return analysis.robust_circular_mean(analysis.phase_offsets(fit, x_t))
    if variant == "median":
        return analysis.robust_median_mean(analysis.phase_offsets(fit, x_t))
    return phase_line(fit, x_t)


def refit(summary_fit, media, rows, n_ref):
    lad = Ladder(None, media=media, log=lambda *_: None)
    lad.u, lad.v, lad.c = summary_fit["u"], summary_fit["v"], math.radians(summary_fit.get("c_deg", 0.0))
    lad.n_ref = n_ref
    lad.targets = rows
    lad.fit()
    res = [t["residual_deg"] for t in rows]
    return lad, math.sqrt(statistics.fmean(r * r for r in res))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", help="a geo result folder (summary.json, targets.csv, events.csv)")
    ap.add_argument("--compare", nargs=2, type=float, metavar=("RI", "RO"),
                    help="inner and outer radius in mm to compare a CD audio fit with")
    a = ap.parse_args(argv)
    summary = json.load(open(os.path.join(a.run, "summary.json"), encoding="utf-8"))
    fit0 = summary["fit"]
    media = fit0.get("media", "dvd")
    cache = summary.get("cache") or {}
    strategy, hit_us = cache.get("strategy", "fua"), cache.get("cache_hit_us", 3000.0)
    targets = list(csv.DictReader(open(os.path.join(a.run, "targets.csv"), encoding="utf-8")))
    events = list(csv.DictReader(open(os.path.join(a.run, "events.csv"), encoding="utf-8")))

    def usable(e):
        return int(e["status"]) == 0 and (strategy not in ("evict", "flush", "far") or float(e["duration_us"]) >= hit_us)

    # geo fits each block with the period it has followed so far as the prior. The rung's recorded
    # period stands in for that; the summary only has the run's last one.
    period_of = {int(t["lba"]): float(t["period_ms"]) / 1e3 for t in targets}
    by_lba = {}
    for lba, ref_t, x_t in blocks(events, usable):
        if lba not in period_of or len(ref_t) < 8 or len(x_t) < 8:
            continue
        fit = analysis.estimate_period(ref_t, prior_s=period_of[lba], prior_window=0.02)
        if fit is None:
            continue
        # A sector read in more than one block (a retry, or a check point that is also a rung):
        # the rung's block is the one whose period is the recorded one; the later one on a tie.
        had = by_lba.get(lba)
        if had is None or abs(fit.period_s - period_of[lba]) <= abs(had[0].period_s - period_of[lba]):
            by_lba[lba] = (fit, x_t)

    sectors = fit0.get("sectors") or fit0.get("dis_equivalent", {}).get("sectors")
    b = fit0["bit_nm_assumed"] * 1e-6
    lad0 = Ladder(None, media=media, log=lambda *_: None)
    lad0.audio = fit0.get("track") == "audio"
    lad0.read_offset_bytes = fit0.get("read_offset_bytes", 0.0)
    n_ref = lad0._n_end(int(fit0["reference_lba"]))

    def geometry(u, v):
        if lad0.audio and sectors:
            return u * b, b * math.sqrt(u * u + v * sectors * cd.SECTOR_BITS / math.pi)
        return u * b, v * b * 1e3          # r0 (mm), pitch (um)

    names = ("ri (mm)", "ro (mm)") if lad0.audio and sectors else ("r0 (mm)", "pitch (um)")
    print(f"{a.run}: {len(targets)} rungs, cache strategy {strategy}, media {media}"
          f"{', audio track' if lad0.audio else ''}")
    head = f"{'':10s} {'rungs':>5s} {'median sem':>10s} {'chi2/dof':>8s} {'rms deg':>8s} {names[0]:>14s} {names[1]:>14s}"
    if a.compare:
        head += f" {'d ri nm':>8s} {'d ro nm':>8s}"
    print(head)

    def line(name, n, sem, chi, rms, g):
        s = f"{name:10s} {n:5d} {sem:10.3f} {chi:8.2f} {rms:8.3f} {g[0]:14.9f} {g[1]:14.9f}"
        if a.compare:
            s += f" {(g[0] - a.compare[0]) * 1e6:+8.1f} {(g[1] - a.compare[1]) * 1e6:+8.1f}"
        print(s)

    rec_res = [float(t["residual_deg"]) for t in targets]
    line("recorded", len(targets), statistics.median(float(t["sigma_deg"]) for t in targets), fit0["chi2_per_dof"],
         math.sqrt(statistics.fmean(r * r for r in rec_res)), geometry(fit0["u"], fit0["v"]))
    worst = {}
    for variant in VARIANTS:
        rows = []
        for t in targets:
            lba = int(t["lba"])
            if lba not in by_lba:
                continue
            fit, x_t = by_lba[lba]
            ph = estimate(variant, fit, x_t)
            if ph["mean_deg"] is None:
                continue
            worst[variant] = max(worst.get(variant, 0.0),
                                 abs(analysis.wrap_pi(math.radians(ph["mean_deg"] - float(t["phase_deg"])))))
            pred = float(t["predicted_deg"])
            rows.append({"lba": lba, "n": float(t["n_bits"]), "phase_deg": ph["mean_deg"],
                         "sigma_deg": max(ph["sem_deg"], MIN_SIGMA_DEG), "predicted_deg": pred,
                         "unwrapped_deg": ph["mean_deg"] + 360.0 * round((pred - ph["mean_deg"]) / 360.0)})
        lad, rms = refit(fit0, media, rows, n_ref)
        line(variant, len(rows), statistics.median(r["sigma_deg"] for r in rows), lad.chi2_dof, rms,
             geometry(lad.u, lad.v))
    # A run made before the median clip reproduces under "interp", one made since under "median".
    used = min(("interp", "median"), key=lambda v: worst.get(v, math.inf))
    print(f"rebuild check: the {used} phases differ from the recorded ones by at most "
          f"{math.degrees(worst.get(used, math.nan)):.3f} deg")
    print(f"(sem is floored at {MIN_SIGMA_DEG} deg, as in geo)")


if __name__ == "__main__":
    main()
