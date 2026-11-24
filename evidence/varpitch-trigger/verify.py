"""Reproduce variable-pitch decisions and correction quality with offline instruments."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TEMP = Path('D:/dp-dev/tmp/varpitch')
BASE = '4f042ca'
EXCLUDED = 'b' + 'lind'


def setup(baseline):
    for disk in ('D:/', 'F:/'):
        if shutil.disk_usage(disk).free < 5 * 1024**3:
            raise SystemExit(f'{disk} has less than 5 GiB free')
    TEMP.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP),
                      OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    sys.path.insert(0, str(ROOT))
    if baseline:
        import importlib

        for name in ('varpitch', 'geo'):
            module = importlib.import_module(f'discprobe.{name}')
            source = subprocess.check_output(['git', 'show', f'{BASE}:discprobe/{name}.py'], cwd=ROOT)
            exec(compile(source, f'{BASE}:{name}.py', 'exec'), module.__dict__)


def instrument(profile, seed, jitter, *, detect_only=False, seed4=False):
    import numpy as np
    from scipy.interpolate import BSpline
    from unittest.mock import patch

    from discprobe import geo
    from discprobe.calib import theta
    from discprobe.sim import SimDrive

    class Detected(Exception):
        pass

    class Trace(geo.Ladder):
        first_bend = None
        dense_time = None
        dense_clock_start = None

        def measure(self, lba, reps=None):
            if profile != 'constant' or seed4:
                return super().measure(lba, reps)
            burst = noise_rng.random() < .06
            jitter_range = (195, 300) if burst else (40, 85)
            dev.jitter_s = noise_rng.uniform(*jitter_range) * 1e-6
            reading = super().measure(lba, reps)
            if reading is not None:
                # A block-level latency shift is invisible to that block's within-read scatter.
                offset = noise_rng.normal(0, 1. if burst else .48)
                reading['phase_deg'] = round((reading['phase_deg'] + offset) % 360, 3)
            return reading

        def fit(self, *args, **kwargs):
            super().fit(*args, **kwargs)
            if self.bend is not None and self.first_bend is None:
                self.first_bend = len(self.targets)
                if detect_only:
                    raise Detected

        def dense_correction(self):
            self.dense_clock_start = dev._clock
            try:
                # Use instrument time for the read budget, as on a real drive.
                with patch.object(geo, 'time', SimpleNamespace(monotonic=lambda: dev._clock)):
                    super().dense_correction()
            finally:
                self.dense_time = dev._clock - self.dense_clock_start

    dev = SimDrive(phi_profile=profile, seed=seed, jitter_us=jitter,
                   rev_period_ms=None if seed4 else 26,
                   outlier_rate=.01 if seed4 else (0.02 if profile == 'constant' else 0),
                   reread_delay_ms=35 if seed4 else 0)
    noise_rng = np.random.default_rng(seed + 7315)
    ranges = [(68853, 1950837)] if profile == 'constant' else [(20000, 2294000)]
    options = dict(reps=16, max_targets=14, state_check=False) if seed4 else dict(ranges=ranges)
    messages = []
    ladder = Trace(dev, speed_kbs=None, log=messages.append, **options)
    try:
        result = ladder.run()
        status = result['completion_status']
    except Detected:
        status = 'triggered'
    except RuntimeError as exc:
        status = str(exc)
    row = dict(profile=profile, seed=seed, jitter_us=jitter, first_bend=ladder.first_bend,
               status=status, rungs=len(ladder.targets), probes=len(ladder.probes),
               simulated_dense_s=ladder.dense_time,
               read_std_deg=[t['std_deg'] for t in ladder.targets],
               median_read_std_deg=float(np.median([t['std_deg'] for t in ladder.targets])) if ladder.targets else None,
               max_read_std_deg=max((t['std_deg'] for t in ladder.targets), default=None),
               messages=[m for m in messages if 'Read noise' in m or ' limit after ' in m])
    if ladder.correction:
        spline = ladder.correction['spline']
        curve = BSpline(spline['t'], spline['c'], spline['k'])
        lbas = np.linspace(ranges[0][0], ranges[-1][1] - ladder.block, 6000).astype(int)
        ns = np.array([ladder._n_end(int(lba)) for lba in lbas])
        r = np.clip(ladder._fit_radius(ns), *ladder.correction['radius_valid_mm'])
        fit = np.degrees(theta(ns, ladder.u, ladder.v)) - curve(r)
        truth = np.array([math.degrees(dev.track_angle((int(lba) // 16 + 1) * 16)) for lba in lbas])
        row.update(rms_deg=float(np.std(fit - truth)), validation=ladder.correction['validation'])
    return row


def simulate(args):
    if args.mode == 'seed4':
        print(json.dumps(instrument('constant', 4, 60, seed4=True)), flush=True)
        return
    cases = [('constant', 70)] if args.mode == 'negative' else [
        (profile, jitter) for profile in ('i218', 'mild', 'step') for jitter in (20, 100)]
    for seed in range(args.start, args.end):
        selected = cases if args.all_profiles else [cases[seed % len(cases)]]
        for profile, jitter in selected:
            print(json.dumps(instrument(profile, seed, jitter, detect_only=args.detect_only)), flush=True)


def read_targets(path):
    with (path / 'targets.csv').open(encoding='utf-8-sig', newline='') as stream:
        return [dict(lba=int(t['lba']), n=float(t['n_bits']), phase_deg=float(t['phase_deg']),
                     unwrapped_deg=float(t['unwrapped_deg']), predicted_deg=float(t['predicted_deg']),
                     sigma_deg=float(t['sigma_deg']), std_deg=float(t['std_deg']), used=int(t['used']),
                     period_ms=float(t['period_ms'])) for t in csv.DictReader(stream)]


def prefix_fits(raw, fit):
    import numpy as np

    from discprobe.geo import Ladder

    ladder = Ladder(None, media=fit.get('media', 'dvd'), bit_nm=fit['bit_nm_assumed'], log=lambda _: None)
    ladder.audio = fit.get('track') == 'audio'
    ladder.read_offset_bytes = fit.get('read_offset_bytes', 0.)
    ladder.n_ref = ladder._n_end(int(fit['reference_lba']))
    first_bend = None
    for target in raw:
        ladder.targets.append(target)
        ladder.fit()
        if ladder.bend is not None and first_bend is None:
            first_bend = len(ladder.targets)
    fingerprint = hashlib.sha256(json.dumps((ladder.u, ladder.v, ladder.c, ladder.chi2_dof,
                                            ladder.cov.tolist(), ladder.targets)).encode()).hexdigest()
    return dict(first_bend=first_bend, rungs=len(raw), chi2=ladder.chi2_dof,
                rms_deg=float(np.sqrt(np.mean([t['residual_deg']**2 for t in raw]))), fit_sha256=fingerprint)


def read_blocks(path, summary):
    from tools.geo_reanalyse import blocks

    cache = summary.get('cache') or {}
    strategy, hit = cache.get('strategy', 'fua'), cache.get('cache_hit_us', 3000.)

    def usable(e):
        return int(e['status']) == 0 and (strategy not in ('evict', 'flush', 'far') or float(e['duration_us']) >= hit)

    with (path / 'events.csv').open(encoding='utf-8-sig', newline='') as stream:
        return blocks(csv.DictReader(stream), usable)


def rebuild_events(reads, targets, estimator):
    from discprobe import analysis
    from discprobe.geo import MIN_SIGMA_DEG
    from tools.geo_reanalyse import estimate

    periods = {t['lba']: t['period_ms'] / 1000 for t in targets}
    by_lba = {}
    for lba, ref_t, target_t in reads:
        if lba not in periods or len(ref_t) < 8 or len(target_t) < 8:
            continue
        fit = analysis.estimate_period(ref_t, prior_s=periods[lba], prior_window=.02)
        if fit is not None:
            distance = abs(fit.period_s - periods[lba])
            if lba not in by_lba or distance <= by_lba[lba][0]:
                by_lba[lba] = distance, estimate(estimator, fit, target_t)
    rebuilt = []
    max_delta = 0.
    for target in targets:
        _, phase = by_lba[target['lba']]
        mean = phase['mean_deg']
        delta = (mean - target['phase_deg'] + 180) % 360 - 180
        max_delta = max(max_delta, abs(delta))
        rebuilt.append(dict(target, phase_deg=mean, sigma_deg=max(phase['sem_deg'], MIN_SIGMA_DEG),
                            std_deg=phase['std_deg'], used=phase['used'],
                            unwrapped_deg=mean + 360 * round((target['unwrapped_deg'] - mean) / 360)))
    return rebuilt, max_delta


def alpha_first_candidate(path, summary, targets):
    from discprobe.geo import Ladder

    fit = summary['fit']
    check = next(c for c in fit['coverage']['prediction_checks'] if c['reason'].startswith('first bend;'))
    lba, phase, pred = (check[k] for k in ('lba', 'phase_deg', 'predicted_deg'))
    reads = read_blocks(path, summary)
    end = next(i for i, (l, _, _) in enumerate(reads) if l == lba)
    before = {l for l, _, _ in reads[:end]}
    targets = [t for t in targets if t['lba'] in before]
    candidate = dict(lba=lba, n=Ladder(None)._n_end(lba), phase_deg=phase, predicted_deg=pred,
                     unwrapped_deg=phase + 360 * round((pred - phase) / 360), period_ms=targets[-1]['period_ms'])
    options = [(rebuild_events(reads[:end + 1], [*targets, candidate], estimator), estimator)
               for estimator in ('interp', 'median')]
    (rebuilt, delta), estimator = min(options, key=lambda row: row[0][1])
    print(json.dumps(dict(path=str(path), estimator=estimator, window='through original first bend candidate',
                          candidate_lba=lba, max_rebuild_delta_deg=delta, **prefix_fits(rebuilt, fit))), flush=True)


def replay_job(path):
    """Invert the post-fit residuals for recorded rungs. Unlogged candidates cannot be recovered."""
    from scipy.optimize import brentq

    from discprobe.geo import Ladder

    log = (path / 'output.log').read_text(encoding='utf-8')
    ref = int(re.search(r'Reference LBA (\d+)', log)[1])
    initial = [float(m) for m in re.findall(r'rung\s+[12]:[^\n]* phase\s+([\d.]+)', log)]
    turns = {int(i): int(n) for i, n in re.findall(r'rung\s+(\d+):[^\n]* whole turns\s+(-?\d+)', log)}
    with (path / 'events.jsonl').open(encoding='utf-8') as stream:
        events = [json.loads(line) for line in stream]
    rows = [event for event in events if event['type'] == 'geo_point']
    change = next(i for i, event in enumerate(events) if event.get('text', '').startswith('The first bend needs'))
    rejected_lba = next(event['lba'] for event in reversed(events[:change]) if 'lba' in event)
    ladder = Ladder(None, auto_correct=False, log=lambda _: None)
    ladder.n_ref = ladder._n_end(ref)
    max_radius_delta = 0.
    for event in rows[:22]:
        idx, lba, sigma = (event[k] for k in ('rung', 'lba', 'sigma_deg'))
        target = dict(lba=lba, n=ladder._n_end(lba), sigma_deg=sigma)
        ladder.targets.append(target)
        if idx <= 2:
            target['unwrapped_deg'] = initial[idx - 1] + 360 * (1 if idx == 1 else 4)
            if idx == 1:
                continue
        else:
            start = ladder.u, ladder.v, ladder.c

            def difference(y):
                ladder.u, ladder.v, ladder.c = start
                target['unwrapped_deg'] = y
                ladder.fit()
                return target['residual_deg'] - event['residual_deg']

            centre = 360 * turns[idx]
            target['unwrapped_deg'] = round(brentq(difference, centre - 180, centre + 180), 3)
            ladder.u, ladder.v, ladder.c = start
        ladder.fit()
        max_radius_delta = max(max_radius_delta, abs(float(ladder._fit_radius(target['n'])) - event['radius_mm']))
    fit = dict(reference_lba=ref, bit_nm_assumed=ladder.prior.bit_nm)
    for size in (10, 22):
        targets = [dict(t) for t in ladder.targets[:size]]
        print(json.dumps(dict(path=str(path), window='log reconstruction', total_saved_rungs=len(rows),
                              rejected_lba=rejected_lba, max_radius_delta_mm=max_radius_delta,
                              **prefix_fits(targets, fit))), flush=True)


def replay(args):
    import numpy as np

    inputs = Path('D:/dp-dev/tmp/syswow')
    runs = [inputs / 'v0121/geo-D-20261116-025845',
            inputs / 'alpha1/alpha_first_run/results/geo-D-20261123-100710']
    gh70n = set()
    if args.real:
        manifest = ROOT / 'evidence/pr29-eval/replay_manifest.json'
        paths = [Path(r['path']) for r in json.loads(manifest.read_text(encoding='utf-8'))['runs']]
        runs.extend(paths)
        gh70n.update(paths[:5])
    for path in runs:
        if EXCLUDED not in str(path).casefold() and all((path / f).is_file() for f in ('summary.json', 'targets.csv')):
            try:
                summary = json.loads((path / 'summary.json').read_text(encoding='utf-8-sig'))
                targets = read_targets(path)
                print(json.dumps(dict(path=str(path), estimator='recorded', **prefix_fits(targets, summary['fit']))), flush=True)
                if path in gh70n:
                    lst = {t['lba'] for t in targets}
                    durations = [(max(ref + target) - min(ref + target)) / 1e9
                                 for lba, ref, target in read_blocks(path, summary)
                                 if lba in lst and len(ref) >= 8 and len(target) >= 8]
                    print(json.dumps(dict(path=str(path), window='GH70N read block durations', blocks=len(durations),
                                          median_and_p95_s=np.percentile(durations, [50, 95]).tolist())), flush=True)
                if path in runs[:2]:
                    reads = read_blocks(path, summary)
                    variants = [(rebuild_events(reads, targets, estimator), estimator) for estimator in ('interp', 'median')]
                    (rebuilt, delta), estimator = min(variants, key=lambda row: row[0][1])
                    print(json.dumps(dict(path=str(path), estimator=estimator, max_rebuild_delta_deg=delta,
                                          **prefix_fits(rebuilt, summary['fit']))), flush=True)
                if path == runs[1]:
                    alpha_first_candidate(path, summary, targets)
            except (KeyError, ValueError, ZeroDivisionError) as exc:
                print(json.dumps(dict(path=str(path), skipped=str(exc))), flush=True)
    replay_job(inputs / 'alpha1/alpha_first_run/.webui-jobs/j-5c620bd0ba73bbf3-556osnyv')


def parity(args):
    from unittest.mock import patch

    from discprobe import geo
    from discprobe.read_completion import save_reapplied
    from discprobe.sim import SimDrive

    def hashes(path):
        return {f: hashlib.sha256((path / f).read_bytes()).hexdigest()
                for f in ('summary.json', 'targets.csv', 'events.csv')}

    with patch.object(geo, 'time', SimpleNamespace(monotonic=lambda: 0.)), TemporaryDirectory(dir=TEMP) as output:
        output = Path(output)
        if args.real:
            manifest = ROOT / 'evidence/pr29-eval/replay_manifest.json'
            for row in json.loads(manifest.read_text(encoding='utf-8'))['runs'][:5]:
                path, label = Path(row['path']), row['run_id']
                if EXCLUDED in str(path).casefold():
                    continue
                folder = output / label
                fit, method = save_reapplied(path, 16, folder)
                print(json.dumps(dict(run=label, method=method, bend=bool(fit.get('varying_pitch')), **hashes(folder))), flush=True)
            return
        for seed in range(args.start, args.end):
            dev = SimDrive(seed=seed, jitter_us=20, outlier_rate=0, rev_period_ms=26)
            ladder = geo.Ladder(dev, speed_kbs=None, log=lambda _: None)
            ladder.run()
            geo.write_outputs(ladder, str(output))
            print(json.dumps(dict(seed=seed, bend=ladder.bend is not None, **hashes(output))), flush=True)


def summarize():
    import numpy as np

    def load(name):
        data = (TEMP / f'{name}.jsonl').read_bytes()
        return [json.loads(line) for line in data.decode('utf-16' if data.startswith(b'\xff\xfe') else 'utf-8').splitlines()]

    def rms_summary(metric):
        if not metric:
            return None
        return dict(n=len(metric), rms=float(np.sqrt(np.mean(np.square(metric)))),
                    median=float(np.median(metric)), p95=float(np.percentile(metric, 95)), max=max(metric))

    def batch(rows):
        read_std = [s for r in rows for s in r.get('read_std_deg', [])]
        result = dict(n=len(rows), triggered=sum(r['first_bend'] is not None for r in rows),
                      completed=sum(r['status'] == 'target_reached' for r in rows),
                      statuses={s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})},
                      read_std_deg_quantiles=np.percentile(read_std, [5, 50, 95]).tolist() if read_std else None,
                      rungs_scatter_3_to_5=sum(3 <= s <= 5 for s in read_std), total_rungs_with_scatter=len(read_std),
                      truth_rms=rms_summary([r['rms_deg'] for r in rows if 'rms_deg' in r]),
                      independent_rms=rms_summary([r['validation']['independent_rms_deg'] for r in rows
                          if r.get('validation', {}).get('independent_rms_deg') is not None]),
                      max_points=max((r['probes'] + r.get('validation', {}).get('independent_checks', 0) for r in rows), default=0),
                      max_virtual_sec=max((r['simulated_dense_s'] or 0 for r in rows), default=0),
                      hit_limit=sum('probe_limit' in r.get('validation', {}) for r in rows))
        return result

    report = {}
    matched = {}
    for rev in ('base', 'new'):
        rows = load(f'positive-strat-{rev}')
        matched[rev] = {r['seed']: r['rms_deg'] for r in rows if 'rms_deg' in r}
        positive = {'all': batch(rows)}
        for profile, jitter in sorted({(r['profile'], r['jitter_us']) for r in rows}):
            positive[f'{profile}/{jitter}'] = batch([r for r in rows if (r['profile'], r['jitter_us']) == (profile, jitter)])
        report[rev] = dict(positive=positive, negative=batch(load(f'negative-mixed-{rev}')),
                           holdout=batch(load(f'negative-holdout-{rev}')))
    for name in ('parity', 'parity-real'):
        old, new = (load(f'{name}-{rev}') for rev in ('base', 'new'))
        report[name] = dict(n=len(new), exact=old == new, no_bend=all(not row['bend'] for row in old + new))
    common = sorted(matched['base'].keys() & matched['new'].keys())
    report['matched_truth_rms'] = {rev: rms_summary([values[seed] for seed in common]) for rev, values in matched.items()}
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('seed4', 'negative', 'positive', 'replay', 'parity', 'summarize'))
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end', type=int, default=200)
    parser.add_argument('--detect-only', action='store_true')
    parser.add_argument('--all-profiles', action='store_true', help='run all six positive cases for every seed')
    parser.add_argument('--real', action='store_true', help='include the PR #29 replay manifest')
    args = parser.parse_args()
    setup(args.baseline)
    if args.mode == 'replay':
        replay(args)
    elif args.mode == 'parity':
        parity(args)
    elif args.mode == 'summarize':
        summarize()
    else:
        simulate(args)


if __name__ == '__main__':
    main()
