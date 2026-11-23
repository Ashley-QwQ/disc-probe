"""Paired, offline PR29 evaluation; never opens a hardware transport.

python evidence/pr29-eval/evaluate.py --seeds 200 --end-seeds 30
Use --mode phase/end-to-end/replay to rerun one part. All outputs are CSV/JSON.
Only two worker processes are allowed; BLAS threads are capped before importing numpy.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor

for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from discprobe import analysis
from discprobe.calib import SECTOR_BITS, theta
from discprobe.geo import Ladder, MEASURE_COHERENCE, PERIOD_TOL
from discprobe.rings import RingLayout
from discprobe.sim import SimDrive
from discprobe.timing import TimingProbe
from tools import geo_reanalyse

OUT = Path(__file__).resolve().parent
TEMP = Path("F:/dp-dev-tmp/pr29eval")
OLD = analysis.robust_circular_mean
NEW = analysis.robust_median_mean
RATES = (0.0, 0.03, 0.10, 0.20)
BLOCKED = "".join(("b", "l", "i", "n", "d"))


def allowed(path):
    return BLOCKED not in str(path).lower()


def safe_children(path):
    """Filter names before stat, opening, recursion, or recording a path."""
    if not allowed(path) or not path.is_dir():
        return []
    with os.scandir(path) as entries:
        return sorted((Path(e.path) for e in entries if allowed(e.path)), key=str)


def safe_walk(path):
    if not allowed(path) or not path.is_dir():
        return
    yield path
    for child in safe_children(path):
        if child.is_dir() and not child.is_symlink():
            yield from safe_walk(child)


def dump_csv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


class LateDrive(SimDrive):
    """Add late completion to media reads only, including references and targets.

    Independent RNG preserves SimDrive's original RNG sequence. Conditional tail:
    80% U(10,20) degrees, 20% U(4,60), a declared model rather than BU20N data.
    Added time propagates through SimDrive.execute's clock to the following read.
    """
    def __init__(self, *, tail_rate=0.0, **kwargs):
        super().__init__(**kwargs)
        self.tail_rate = tail_rate
        self.tail_rng = random.Random(kwargs.get("seed", 1) + 1_000_003)
        self.tail_count = 0
        self.tail_eligible = 0

    def _read(self, t, lba, count, fua):
        before = self.media_reads
        done = super()._read(t, lba, count, fua)
        if self.tail_rate and self.media_reads > before:
            self.tail_eligible += 1
            hit, component, draw = (self.tail_rng.random() for _ in range(3))
            if hit < self.tail_rate:
                deg = 10 + 10 * draw if component < 0.8 else 4 + 56 * draw
                done += math.radians(deg) / self._omega(done)
                self.tail_count += 1
        return done


def phase_job(job):
    seed, rate, media, period_window = job
    period_ms, reps = (6.6, 16) if media == "dvd" else (48.35, 32)
    sim = LateDrive(mode="cav", seed=seed, tail_rate=rate, media=media,
                    cd_audio=media == "cd", rev_period_ms=period_ms, reread_delay_ms=35)
    tp = TimingProbe(sim, speed_kbs=None, media=media, reps=reps, cd_audio=media == "cd")
    # Fixed protocol, no setup, search, state check, retry, or adaptive LBA selection.
    tp.method = "read12" if media == "dvd" else "readcd"
    tp.strategy = "fua" if media == "dvd" else "far"
    tp.last_lba = sim.capacity - 1
    ref = int(sim.capacity * 0.05) // sim.block * sim.block
    lbas = [int(sim.capacity * f) // sim.block * sim.block for f in np.linspace(.08, .85, 14)]
    b = sim.spiral.sector_mm / SECTOR_BITS if media == "dvd" else None
    truth_u = sim.spiral.r0_mm / b if b else None
    truth_v = sim.spiral.pitch_mm / b if b else None
    out = []
    for rung, lba in enumerate(lbas):
        refs, targets = [], []
        for _ in range(reps):
            refs.append(tp._measure(ref, "ref").t_end_ns)
            targets.append(tp._measure(lba, "target").t_end_ns)
        # Use local true period as a narrow prior, then apply geo's common period
        # acceptance gate: estimate_period also searches submultiples of any prior.
        # --period-window .02 reproduces the original wide search
        # with its nominal initial prior, retained as a separate diagnostic dataset.
        midpoint = (refs[0] + refs[-1]) * .5e-9
        prior = (2 * math.pi / sim._omega(midpoint) if period_window < .001 else period_ms / 1000)
        fit = analysis.estimate_period(refs, prior_s=prior, prior_window=period_window)
        # DVD truth agrees with _ladder's theta(truth_u, truth_v); CD uses simulator read ends.
        truth = sim.true_phase_deg(ref, lba)
        if b:
            nr = ((ref // 16 + 1) * 16) * SECTOR_BITS
            nt = ((lba // 16 + 1) * 16) * SECTOR_BITS
            geom_truth = float(np.degrees(theta(nt, truth_u, truth_v) - theta(nr, truth_u, truth_v))) % 360
            assert abs(math.degrees(analysis.wrap_pi(math.radians(geom_truth - truth)))) < 1e-6
        row = dict(seed=seed, tail_rate=rate, media=media, period_ms=period_ms, reps=reps,
                   rung=rung, ref_lba=ref, target_lba=lba, truth_deg=truth,
                   truth_u=truth_u, truth_v=truth_v, period_window=period_window,
                   period_prior_s=prior, status="ok" if fit else "period_failed")
        if fit:
            offsets = analysis.phase_offsets(fit, targets)
            # Exactly the same offsets, including period fit and reference interpolation.
            row.update(coherence=fit.coherence, ref_used=fit.used, fitted_period_s=fit.period_s)
            for name, estimator in (("interp", OLD), ("median", NEW)):
                result = estimator(offsets)
                row[name + "_error_deg"] = math.degrees(analysis.wrap_pi(math.radians(result["mean_deg"] - truth)))
                row[name + "_used"] = result["used"]
            if fit.coherence < MEASURE_COHERENCE or abs(fit.period_s / prior - 1) > PERIOD_TOL:
                row["status"] = "period_rejected"
        out.append(row)
    return out


def span(n, a, b):
    error = np.degrees(theta(n, a[0], a[1]) - theta(n, b[0], b[1]))
    return float(np.ptp(error))


def end_job(job):
    seed, rate, variant = job
    analysis.robust_median_mean = OLD if variant == "interp" else NEW
    rows = []
    plain_uv = None
    for scenario in ("plain", "whole", "rings"):
        start = time.monotonic()
        sim = None
        row = dict(seed=seed, tail_rate=rate, estimator=variant, scenario=scenario)
        try:
            patterns = []
            if scenario == "rings":
                layout = RingLayout(textures=("A5", "RND", "B9", "RND", "66", "RND", "64", "RND", "E4", "RND", "92", "RND"),
                                    groups=2, ring_width_mm=1.04, start_mm=25, filler="RND").build()
                patterns = [(r["lba_start"], r["lba_end"], int(r["texture"], 16))
                            for r in layout.rings if r["texture"] != "RND"]
                patterns.append((layout.total_sectors, 2295104, 0xB9))
            sim = LateDrive(mode="cav", seed=seed, reread_delay_ms=35, tail_rate=rate, patterns=patterns)
            lad = Ladder(sim, speed_kbs=None, reps=16, max_targets=14, log=lambda *_: None,
                         sectors=16 if scenario == "whole" else 1, state_check=scenario == "rings")
            result = lad.run()
            b = sim.spiral.sector_mm / SECTOR_BITS
            truth_uv = (sim.spiral.r0_mm / b, sim.spiral.pitch_mm / b)
            n = (np.linspace(min(t["n"] for t in lad.targets), max(t["n"] for t in lad.targets), 300)
                 if scenario == "rings" else np.linspace(0, .98 * sim.capacity * SECTOR_BITS, 400))
            uv = (lad.u, lad.v)
            truth_span = span(n, uv, truth_uv)
            if scenario == "plain":
                plain_uv = uv
            check_span = span(n, uv, plain_uv) if scenario == "whole" and plain_uv else truth_span
            row.update(status="ok" if scenario != "whole" or plain_uv else "plain_missing",
                       span_deg=check_span, truth_span_deg=truth_span, rungs=len(lad.targets),
                       chi2_dof=result["chi2_per_dof"], u=lad.u, v=lad.v,
                       n_min=float(n.min()), n_max=float(n.max()),
                       ranges=len(lad.auto_ranges or []), completion_status=result.get("completion_status"))
        except Exception as e:
            row.update(status="error", error=f"{type(e).__name__}: {e}")
        row.update(seconds=time.monotonic() - start,
                   injected_late_reads=sim.tail_count if sim else 0,
                   eligible_reads=sim.tail_eligible if sim else 0)
        rows.append(row)
    return rows


def simulate(mode, seeds, end_seeds, workers, out, period_window):
    jobs = ([(s, r, media, period_window) for media in ("dvd", "cd") for r in RATES for s in range(1, seeds + 1)]
            if mode == "phase" else [(s, r, e) for r in (0.0, .10)
                                     for s in range(1, end_seeds + 1) for e in ("interp", "median")])
    rows = []
    file = out / ("phase.csv" if mode == "phase" else "end_to_end.csv")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, batch in enumerate(pool.map(phase_job if mode == "phase" else end_job, jobs), 1):
            rows.extend(batch)
            if i % 10 == 0 or i == len(jobs):
                dump_csv(file, rows)
                print(f"{mode}: {i}/{len(jobs)} jobs, {len(rows)} rows", flush=True)
    dump_csv(file, rows)
    return rows


def candidates():
    roots = [Path("D:/disc-probe/results"), Path("D:/disc-probe/evidence/geo"),
             Path("F:/dp-archive/worktree-leftovers-20261116"), Path("D:/dp-dev/integ/evidence")]
    runs, inventory = set(), []
    for index, root in enumerate(roots):
        inventory.append(dict(root=str(root), exists=root.is_dir()))
        if not root.is_dir():
            continue
        if index == 0:
            bases = [p for p in safe_children(root) if p.name.startswith("geo-") and p.is_dir()]
        elif index == 2:
            bases = []
            for child in safe_children(root):
                untracked = child / "untracked"
                for folder in safe_walk(untracked):
                    if folder.name.startswith("results"):
                        bases.extend(p for p in safe_children(folder) if p.name.startswith("geo-") and p.is_dir())
        else:
            bases = [root]
        for base in bases:
            for folder in safe_walk(base):
                if all((folder / name).is_file() for name in ("events.csv", "summary.json")):
                    runs.add(folder)
    return sorted(runs, key=str), inventory


def replay(out):
    runs, inventory = candidates()
    rows, manifest = [], []
    logdir = out / "replay_logs"
    logdir.mkdir(exist_ok=True)
    for index, folder in enumerate(runs, 1):
        row = dict(run_id=f"R{index:03d}", path=str(folder))
        files = {n: digest(folder / n) for n in ("summary.json", "events.csv", "targets.csv") if (folder / n).is_file()}
        try:
            summary = json.loads((folder / "summary.json").read_text(encoding="utf-8-sig"))
            row["drive"] = (summary.get("identity") or {}).get("drive", "UNKNOWN")
            row["media"] = summary.get("fit", {}).get("media", "dvd")
            row["track"] = summary.get("fit", {}).get("track", "data")
            row["classification"] = "sim" if ("-Z-" in str(folder) or "sim" in str(folder).lower()
                                                       or summary.get("simulated") or "simulat" in row["drive"].lower()) else "real"
            if "fit" not in summary:
                row.update(status="not_geo", eligible=False, error="summary has no fit; timing result")
                rows.append(row)
                manifest.append(dict(run_id=row["run_id"], path=str(folder), sha256=files))
                continue
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                geo_reanalyse.main([str(folder)])
            log = buffer.getvalue()
            (logdir / (row["run_id"] + ".txt")).write_text(log, encoding="utf-8")
            match = re.search(r"rebuild check: the (\w+) phases differ .* at most ([\d.]+) deg", log)
            row.update(status="ok", rebuild_estimator=match[1], rebuild_deg=float(match[2]))
            row["eligible"] = row["rebuild_deg"] == 0.0
            for line in log.splitlines():
                fields = line.split()
                if fields and fields[0] in ("interp", "median"):
                    name = fields[0]
                    for key, value in zip(("rungs", "median_sem", "chi2_dof", "rms_deg", "ri_mm", "ro_mm_or_pitch_um"), fields[1:]):
                        row[name + "_" + key] = float(value)
            row["delta_ri_nm"] = (row["median_ri_mm"] - row["interp_ri_mm"]) * 1e6
            if row["track"] == "audio":
                row["delta_ro_nm"] = (row["median_ro_mm_or_pitch_um"] - row["interp_ro_mm_or_pitch_um"]) * 1e6
            else:
                # geo_reanalyse prints pitch for data tracks: compute actual outer radius if capacity exists.
                f = summary["fit"]
                sectors = f.get("sectors") or f.get("dis_equivalent", {}).get("sectors")
                if not sectors and summary.get("setup", {}).get("last_lba") is not None:
                    sectors = int(summary["setup"]["last_lba"]) + 1
                row["data_sectors"] = sectors
                if sectors:
                    if row["media"] == "dvd":
                        bits = SECTOR_BITS
                    elif row["media"] == "bd":
                        from discprobe.geo import BD_SECTOR_BITS
                        bits = BD_SECTOR_BITS
                    else:
                        from discprobe.cd import SECTOR_BITS as bits
                    for name in ("interp", "median"):
                        ri = row[name + "_ri_mm"]
                        pitch_mm = row[name + "_ro_mm_or_pitch_um"] / 1000
                        row[name + "_derived_ro_mm"] = math.sqrt(ri * ri + pitch_mm * sectors * bits * f["bit_nm_assumed"] * 1e-6 / math.pi)
                    row["delta_ro_nm"] = (row["median_derived_ro_mm"] - row["interp_derived_ro_mm"]) * 1e6
        except Exception as e:
            row.update(status="error", eligible=False, error=f"{type(e).__name__}: {e}")
        after = {n: digest(folder / n) for n in files}
        assert files == after, f"source changed while reading {folder}"
        manifest.append(dict(run_id=row["run_id"], path=str(folder), sha256=files))
        rows.append(row)
        print(f"replay {index}/{len(runs)}: {row['status']}", flush=True)
    dump_csv(out / "replay.csv", rows)
    (out / "replay_manifest.json").write_text(json.dumps(dict(roots=inventory, runs=manifest), indent=2, ensure_ascii=False), encoding="utf-8")
    return rows


def summarize(out):
    phase = list(csv.DictReader((out / "phase.csv").open(encoding="utf-8"))) if (out / "phase.csv").exists() else []
    ends = list(csv.DictReader((out / "end_to_end.csv").open(encoding="utf-8"))) if (out / "end_to_end.csv").exists() else []
    # Allows reclassification of the initial narrow-prior run without drawing any
    # new samples; retain all estimates, and expose common period rejections.
    for row in phase:
        if row.get("fitted_period_s"):
            row["status"] = ("period_rejected" if float(row["coherence"]) < MEASURE_COHERENCE
                             or abs(float(row["fitted_period_s"]) / float(row["period_prior_s"]) - 1) > PERIOD_TOL else "ok")
    if phase:
        dump_csv(out / "phase.csv", phase)
    agg, seed_rows = [], []
    for media in ("dvd", "cd"):
        for rate in RATES:
            subset = [r for r in phase if r["media"] == media and float(r["tail_rate"]) == rate]
            if not subset:
                continue
            valid = [r for r in subset if r["status"] == "ok"]
            wins = ties = 0
            for seed in sorted({int(r["seed"]) for r in valid}):
                rs = [r for r in valid if int(r["seed"]) == seed]
                rms = {e: float(np.sqrt(np.mean([float(r[e + "_error_deg"]) ** 2 for r in rs]))) for e in ("interp", "median")}
                wins += rms["median"] < rms["interp"] - 1e-12
                ties += abs(rms["median"] - rms["interp"]) <= 1e-12
                seed_rows.append(dict(media=media, tail_rate=rate, seed=seed, blocks=len(rs), interp_rms=rms["interp"], median_rms=rms["median"]))
            for e in ("interp", "median"):
                values = np.array([float(r[e + "_error_deg"]) for r in valid])
                agg.append(dict(media=media, tail_rate=rate, estimator=e, seeds=len({r["seed"] for r in valid}), blocks=len(valid),
                                failed_blocks=len(subset) - len(valid), bias_deg=float(values.mean()), rms_deg=float(np.sqrt(np.mean(values ** 2))),
                                p95_abs_deg=float(np.quantile(abs(values), .95)), median_better_seeds=wins, tied_seeds=ties))
    dump_csv(out / "phase_summary.csv", agg)
    dump_csv(out / "phase_seeds.csv", seed_rows)
    agg = []
    for rate in (0.0, .10):
        for scene in ("plain", "whole", "rings"):
            for e in ("interp", "median"):
                rs = [r for r in ends if float(r["tail_rate"]) == rate and r["scenario"] == scene and r["estimator"] == e]
                if not rs:
                    continue
                valid = [r for r in rs if r["status"] == "ok"]
                values = np.array([float(r["span_deg"]) for r in valid])
                agg.append(dict(tail_rate=rate, scenario=scene, estimator=e, seeds=len(rs), completed=len(valid), errors=len(rs) - len(valid),
                                median_span_deg=float(np.median(values)) if len(values) else None,
                                p90_span_deg=float(np.quantile(values, .90)) if len(values) else None,
                                over_1_5=int(sum(values > 1.5)), rate_over_1_5=float(np.mean(values > 1.5)) if len(values) else None))
    dump_csv(out / "end_summary.csv", agg)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--end-seeds", type=int, default=30)
    ap.add_argument("--workers", type=int, choices=(1, 2), default=2)
    ap.add_argument("--period-window", type=float, default=.0001,
                    help="phase-only period prior window; .0001 isolates clipping, .02 keeps wide-search aliases")
    ap.add_argument("--mode", choices=("all", "phase", "end-to-end", "replay", "summarize"), default="all")
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args()
    if min(args.seeds, args.end_seeds) < 1:
        ap.error("seed counts must be positive")
    for drive in ("D:/", "F:/"):
        free = shutil.disk_usage(drive).free
        if free < 5 * 1024 ** 3:
            raise SystemExit(f"STOP: {drive} free {free} bytes below 5 GiB")
    TEMP.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP))
    for mode in ("phase", "end-to-end", "replay"):
        if args.mode in ("all", mode):
            if mode == "replay":
                replay(args.output)
            else:
                simulate(mode, args.seeds, args.end_seeds, args.workers, args.output, args.period_window)
    summarize(args.output)
    sources = ("discprobe/analysis.py", "discprobe/sim.py", "discprobe/geo.py", "discprobe/selftest.py", "tools/geo_reanalyse.py")
    metadata = dict(command=sys.argv, python=sys.version, numpy=np.__version__, seed_range=[1, args.seeds],
                    end_seed_range=[1, args.end_seeds], workers=args.workers,
                    phase_period_window=args.period_window,
                    tail_model="all media reads: 80% U(10,20) + 20% U(4,60) degrees; independent RNG seed+1000003",
                    quantiles="numpy.quantile linear; phase p95 absolute signed circular error; win per-seed RMS over 14 fixed targets",
                    source_sha256={p: digest(ROOT / p) for p in sources}, script_sha256=digest(Path(__file__)))
    (args.output / ("metadata_" + args.mode + ".json")).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
