"""Reproduce the PR #29 geometry checks and offline replay using this worktree."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "evidence" / "pr29-eval"
TEMP = Path("D:/dp-dev/tmp/pr29merge")
VARIANTS = ("interp", "median")


def setup():
    for disk in ("D:/", "F:/"):
        if shutil.disk_usage(disk).free < 5 * 1024**3:
            raise SystemExit(f"STOP: {disk} has less than 5 GiB free")
    TEMP.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP),
                      OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    sys.path[:0] = [str(ROOT), str(EVALUATION)]


class RecordChecks:
    def __init__(self):
        self.checks = []

    def check(self, condition, description):
        self.checks.append((bool(condition), description))


def check_seed(seed):
    from discprobe.cd_selftest import _ladder as cd_ladder
    from discprobe.selftest import _ladder_geometry

    checks = RecordChecks()
    try:
        _ladder_geometry(checks, seed)
        cd_ladder(checks, seed=seed)
    except RuntimeError as exc:
        checks.check(False, f"ladder stopped: {exc}")
    return dict(seed=seed, checks=checks.checks)


def sweep(out):
    with ProcessPoolExecutor(max_workers=2, initializer=setup) as pool:
        rows = list(pool.map(check_seed, range(200)))
    failures = [row["seed"] for row in rows if not all(ok for ok, _ in row["checks"])]
    prefixes = (" rungs, angle error", "same geometry:", "angle error over the measured span", "0-98% error",
                "plain rung phase bias", "whole ECC rung phase bias", "texture rings rung phase bias")
    extrema = {}
    for prefix in prefixes:
        values = [abs(float(re.search(r"([+-]?\d+\.\d+) deg", line.split(prefix, 1)[1])[1]))
                  for row in rows for _, line in row["checks"] if prefix in line]
        extrema[prefix.strip()] = max(values) if values else None
    data = dict(passed=200 - len(failures), total=200, failed_seeds=failures,
                max_abs_reported_deg=extrema, rows=rows)
    (out / "seeds.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "rows"}, indent=2))
    if len(failures) > 2:
        raise SystemExit("Fewer than 99% of seeds passed the ladder geometry checks")


def trace_seed4(out):
    import numpy as np
    from discprobe import analysis, varpitch
    from discprobe.calib import SECTOR_BITS, theta
    from discprobe.geo import Ladder, TURN_ABORT_DEG
    from discprobe.sim import SimDrive

    def degrees_delta(a, b):
        return (a - b + 180) % 360 - 180

    class Trace(Ladder):
        def __init__(self, drive, sectors, auto_correct):
            super().__init__(drive, reps=16, max_targets=14, sectors=sectors,
                             speed_kbs=None, state_check=False, log=lambda *_: None)
            self.drive = drive
            self.auto_correct = auto_correct
            self.trigger = self.dense_span_mm = self.stop_probe = None
            bit_mm = drive.spiral.sector_mm / SECTOR_BITS
            self.truth = drive.spiral.r0_mm / bit_mm, drive.spiral.pitch_mm / bit_mm

        def fit(self, *args, **kwargs):
            super().fit(*args, **kwargs)
            if self.bend is not None and self.trigger is None:
                rms = math.sqrt(np.mean([t["residual_deg"] ** 2 for t in self.targets]))
                noise = math.sqrt(np.mean([t["sigma_deg"] ** 2 for t in self.targets]))
                self.trigger = dict(rungs=len(self.targets), chi2=self.chi2_dof, rms_deg=rms,
                                    threshold_deg=max(varpitch.TRIGGER_RMS_DEG, 2 * noise))

        def dense_correction(self):
            self.dense_span_mm = [float(self.bend.x[0]), float(self.bend.x[-1])]
            return super().dense_correction()

        def measure(self, lba, reps=None):
            result = super().measure(lba, reps)
            if result and self.progress_stage == "measuring angle correction":
                prediction = math.degrees(self._predict(result["n"]))
                innovation = degrees_delta(result["phase_deg"], prediction)
                if abs(innovation) > TURN_ABORT_DEG:
                    truth = self.drive.true_phase_deg(self.ref, lba)
                    self.stop_probe = dict(lba=lba, radius_mm=float(self._fit_radius(result["n"])),
                                           innovation_deg=innovation,
                                           phase_error_deg=degrees_delta(result["phase_deg"], truth))
            return result

    rows = []
    for label, estimator, sectors, jitter, outliers, auto_correct in (
        ("interp", analysis.robust_circular_mean, 1, 60, 0.01, True),
        ("median", analysis.robust_median_mean, 1, 60, 0.01, True),
        ("median, whole ECC", analysis.robust_median_mean, 16, 60, 0.01, True),
        ("median, no automatic correction", analysis.robust_median_mean, 1, 60, 0.01, False),
        ("median, no outliers", analysis.robust_median_mean, 1, 60, 0.0, True),
        ("median, low noise", analysis.robust_median_mean, 1, 8, 0.0, True),
    ):
        sim = SimDrive(mode="cav", seed=4, reread_delay_ms=35, jitter_us=jitter, outlier_rate=outliers)
        ladder = Trace(sim, sectors, auto_correct)
        with patch.object(analysis, "robust_median_mean", estimator):
            try:
                status = ladder.run()["completion_status"]
            except RuntimeError as exc:
                status = str(exc)
        ref = theta(ladder.n_ref, *ladder.truth)
        errors = [t["unwrapped_deg"] - math.degrees(theta(t["n"], *ladder.truth) - ref)
                  for t in ladder.targets]
        n = np.linspace(0, .98 * sim.capacity * SECTOR_BITS, 400)
        span = np.ptp(np.degrees(theta(n, ladder.u, ladder.v) - theta(n, *ladder.truth)))
        rows.append(dict(case=label, status=status, rungs=len(errors), first_bend=ladder.trigger,
                         dense_span_mm=ladder.dense_span_mm, stop_probe=ladder.stop_probe,
                         rung_errors_deg=[min(errors), max(errors)], span_deg=float(span)))
    rendered = json.dumps(rows, indent=2) + "\n"
    (out / "seed4.json").write_text(rendered, encoding="utf-8")
    print(rendered)


def load_replay(folder):
    with (folder / "replay.csv").open(encoding="utf-8", newline="") as source:
        rows = {row["run_id"]: row for row in csv.DictReader(source)}
    manifest = json.loads((folder / "replay_manifest.json").read_text(encoding="utf-8"))
    return {run["path"]: (rows[run["run_id"]], run["sha256"]) for run in manifest["runs"]}


def compare_replay(out):
    from evaluate import replay

    replay(out)
    previous, current = load_replay(EVALUATION), load_replay(out)
    fields = ("status", "classification", "eligible", "rebuild_estimator", "rebuild_deg", "delta_ri_nm", "delta_ro_nm")
    numeric = ("chi2_dof", "rms_deg", "ri_mm", "ro_mm_or_pitch_um", "derived_ro_mm")
    fields += tuple(f"{variant}_{key}" for variant in VARIANTS for key in numeric)
    matched_paths = {p for p in previous.keys() & current.keys() if previous[p][1] == current[p][1]}
    changes = [(current[p][0]["run_id"], key, previous[p][0].get(key), current[p][0].get(key))
               for p in sorted(matched_paths) for key in fields
               if previous[p][0].get(key) != current[p][0].get(key)]
    rows = [
        "| ID | Drive | Class | Rebuild ° | χ²/dof interp → median | RMS ° interp → median | Δri nm | Δro nm |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    hashes = {}
    rms_results = {"lower": 0, "higher": 0, "equal": 0}
    for p, (row, sha) in current.items():
        ident = row["run_id"]
        originals = previous.get(p)
        if originals and originals[0]["run_id"] != ident:
            ident += f" (eval {originals[0]['run_id']})"
        key = tuple(sorted(sha.items()))
        duplicate = key in hashes
        if duplicate:
            ident += f" = {hashes[key]}"
        else:
            hashes[key] = row["run_id"]

        def pair(key, decimals):
            if not row.get(f"interp_{key}"):
                return "—"
            return " → ".join(f"{float(row[f'{v}_{key}']):.{decimals}f}" for v in VARIANTS)

        def delta(key):
            return f"{float(row[key]):+.3f}" if row.get(key) else "—"

        rebuild = f"{float(row['rebuild_deg']):.3f}" if row.get("rebuild_deg") else row["status"]
        rows.append(f"| {ident} | {row['drive']} | {row['classification']} | {rebuild} | "
                    f"{pair('chi2_dof', 2)} | {pair('rms_deg', 3)} | {delta('delta_ri_nm')} | {delta('delta_ro_nm')} |")
        if row["classification"] == "real" and row["eligible"] == "True" and not duplicate:
            a, b = (float(row[f"{variant}_rms_deg"]) for variant in VARIANTS)
            rms_results["lower" if b < a else "higher" if b > a else "equal"] += 1
    counts = dict(eval_candidates=len(previous), candidates=len(current), same_inputs=len(matched_paths),
                  checked_fields=len(fields), differences=changes, duplicates=len(current) - len(hashes),
                  rms_results=rms_results)
    (out / "replay-comparison.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    (out / "replay-table.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps(counts, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seeds", "seed4", "replay"))
    args = parser.parse_args()
    setup()
    out = TEMP / args.mode
    out.mkdir(exist_ok=True)
    {"seeds": sweep, "seed4": trace_seed4, "replay": compare_replay}[args.mode](out)


if __name__ == "__main__":
    main()
