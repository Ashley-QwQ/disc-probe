"""Offline proof: simulated instrument through production Ladder, and saved-fit replay.

Run with python -m tools.geo_varpitch_check. Never opens a device.
"""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from discprobe.calib import CalLayout, theta
from discprobe.geo import Ladder, write_outputs
from discprobe.imagedisc import load_correction
from discprobe.sim import SimDrive

OUT = Path('evidence/geo-varpitch')


def prior_class():
    src = subprocess.check_output(['git', 'show', '476e1ff:discprobe/geo.py'], text=True, encoding='utf-8')
    spec = importlib.util.spec_from_loader('discprobe._geo_prior', loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(src, '<prior-geo>', 'exec'), module.__dict__)
    return module.Ladder


def simulations(noisy=False):
    rows = []
    cases = [(m, p) for m in ('dvd', 'cd') for p in ('constant', 'i218', 'mild', 'step')]
    cases += [('bd', 'constant'), ('cd-audio', 'constant')]
    if noisy:
        cases = [('dvd', p) for p in ('constant', 'i218', 'mild', 'step')]
    for case_media, profile in cases:
        media = 'cd' if case_media == 'cd-audio' else case_media
        audio = dict(cd_audio=True, cd_read_offset_bytes=-603) if case_media == 'cd-audio' else {}
        options = dict(read_offset_bytes=-603) if audio else {}
        start = time.perf_counter()
        dev = SimDrive(media=media, phi_profile=profile, rev_period_ms=26,
                       jitter_us=100 if noisy else 20, outlier_rate=0, seed=7, block=32 if media == 'bd' else None, **audio)
        ranges = [(20000, 2294000)] if media == 'dvd' else [(int(dev.capacity * .03), int(dev.capacity * .96))]
        ladder = Ladder(dev, media=media, ranges=ranges, speed_kbs=None, state_check=True, log=lambda *_: None, **options)
        ladder.tp.summary['simulated'] = True
        folder = OUT / f'{"noise-" if noisy else ""}{case_media}-{profile}'
        try:
            result = ladder.run()
            write_outputs(ladder, str(folder))
            lbas = np.linspace(ranges[0][0], ranges[-1][1] - ladder.block, 8000).astype(int)
            ends = [ladder._n_end(int(l)) for l in lbas]
            r = ladder._fit_radius(ends)
            predicted = np.degrees(theta(np.array(ends), ladder.u, ladder.v))
            if ladder.correction:
                predicted -= load_correction(str(folder / 'correction.json'))(r)
            truth = np.array([math.degrees(dev.track_angle(dev._end_sectors((int(l) // dev.block + 1) * dev.block))) for l in lbas])
            error = predicted - truth
            error -= error.mean()  # absolute rotation cannot be measured by timing
            rung_errors = []
            ref_sector = dev._end_sectors((ladder.ref // dev.block + 1) * dev.block)
            for t in ladder.targets:
                end = dev._end_sectors((t['lba'] // dev.block + 1) * dev.block)
                true = math.degrees(dev.track_angle(end) - dev.track_angle(ref_sector))
                rung_errors.append(t['unwrapped_deg'] - true)
            all_errors = list(rung_errors)
            for point in ladder.probes:
                for repeat in ('first', 'again'):
                    t = point[repeat]
                    end = dev._end_sectors((t['lba'] // dev.block + 1) * dev.block)
                    true = math.degrees(dev.track_angle(end) - dev.track_angle(ref_sector))
                    all_errors.append(t['unwrapped_deg'] - true)
            # c is an unknown common phase offset, not a turn error.
            turn_errors = np.array(all_errors) - np.median(rung_errors)
            row = dict(media=case_media, profile=profile, rungs=len(ladder.targets), probes=len(ladder.probes),
                       rms_deg=float(np.sqrt(np.mean(error ** 2))), max_deg=float(np.max(abs(error))),
                       turn_errors=int(np.sum(abs(turn_errors) > 180)),
                       rung_max_error_deg=float(np.max(abs(turn_errors))),
                       elapsed_s=time.perf_counter() - start, simulated_elapsed_s=dev._clock - 1000,
                       correction=result.get('correction_validation'), chi2=result['chi2_per_dof'])
            if profile == 'constant':
                old_dev = SimDrive(media=media, rev_period_ms=26, jitter_us=100 if noisy else 20, outlier_rate=0,
                                   seed=7, block=32 if media == 'bd' else None, **audio)
                old = prior_class()(old_dev, media=media, ranges=ranges, speed_kbs=None,
                                    state_check=True, log=lambda *_: None, **options)
                old.run()
                row['same_targets'] = [t['lba'] for t in ladder.targets] == [t['lba'] for t in old.targets]
                row['delta_u'] = ladder.u - old.u
                row['delta_v'] = ladder.v - old.v
            rows.append(row)
        except Exception as exc:
            if ladder.targets and ladder.cov is not None:
                write_outputs(ladder, str(folder), stopped=str(exc))
            rows.append(dict(media=case_media, profile=profile, error=str(exc), rungs=len(ladder.targets),
                             elapsed_s=time.perf_counter() - start))
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    return rows


def saved_fits():
    old_class = prior_class()
    rows = []
    skipped = []
    for folder in sorted(Path('D:/disc-probe/results').glob('geo-H-*')):
        if any(''.join(chr(i) for i in (98, 108, 105, 110, 100)) in p.lower() for p in folder.parts):
            continue
        summary = folder / 'summary.json'
        targets = folder / 'targets.csv'
        if not summary.exists() or not targets.exists():
            skipped.append(dict(run=folder.name, reason='summary.json or targets.csv not found'))
            continue
        original = summary.read_bytes(), targets.read_bytes()
        data = json.loads(original[0])
        fit = data.get('fit', {})
        if 'u' not in fit:
            skipped.append(dict(run=folder.name, reason='no angular u/v fit'))
            continue
        raw = list(csv.DictReader(original[1].decode('utf-8-sig').splitlines()))
        if len(raw) < 3:
            skipped.append(dict(run=folder.name, reason='fewer than three targets', targets=len(raw)))
            continue
        copies = []
        for cls in (old_class, Ladder):
            media = fit.get('media', 'dvd')
            lad = cls(None, media=media, bit_nm=fit['bit_nm_assumed'], log=lambda *_: None)
            lad.audio = fit.get('track') == 'audio'
            lad.read_offset_bytes = fit.get('read_offset_bytes', 0.)
            lad.n_ref = lad._n_end(fit['reference_lba'])
            lad.u, lad.v, lad.c = fit['u'], fit['v'], math.radians(fit.get('c_deg', 0))
            lad.targets = [dict(lba=int(t['lba']), n=float(t['n_bits']),
                                unwrapped_deg=float(t['unwrapped_deg']), sigma_deg=float(t['sigma_deg'])) for t in raw]
            lad.fit()
            copies.append(lad)
        a, b = copies
        dest = OUT / 'saved' / folder.name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / 'summary.json').write_bytes(original[0])
        (dest / 'targets.csv').write_bytes(original[1])
        assert original == (summary.read_bytes(), targets.read_bytes())
        row = dict(run=folder.name, targets=len(raw), delta_u=b.u-a.u, delta_v=b.v-a.v,
                   delta_c=b.c-a.c, delta_chi2=b.chi2_dof-a.chi2_dof,
                   chi2=b.chi2_dof, residual_rms=float(np.sqrt(np.mean([t['residual_deg']**2 for t in b.targets]))),
                   noise_rms=float(np.sqrt(np.mean([t['sigma_deg']**2 for t in b.targets]))),
                   trigger=b.bend is not None,
                   saved_delta_u=b.u-fit['u'], saved_delta_v=b.v-fit['v'],
                   summary_sha256=hashlib.sha256(original[0]).hexdigest(),
                   targets_sha256=hashlib.sha256(original[1]).hexdigest())
        rows.append(row)
    print(f'replayed {len(rows)} saved fits', flush=True)
    (OUT / 'saved-skipped.json').write_text(json.dumps(skipped, indent=2), encoding='utf-8')
    return rows


def node_checks():
    rows = []
    forbidden = ''.join(map(chr, (98,108,105,110,100)))
    for path in sorted(Path('tests').glob('test_*.mjs')):
        if forbidden in str(path).lower():
            continue
        start = time.perf_counter()
        result = subprocess.run(['node', str(path)], capture_output=True, timeout=120)
        (OUT / (path.stem + '.node.txt')).write_bytes(result.stdout + result.stderr)
        rows.append(dict(test=path.name, exit=result.returncode, elapsed_s=time.perf_counter()-start))
        print(path.name, result.returncode, flush=True)
    (OUT / 'node-checks.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    assert all(r['exit'] == 0 for r in rows), rows


def coverage_checks():
    import runpy
    from discprobe.coverage import assess_range
    oracle = runpy.run_path('tests/test_geo_varpitch.py')['PhaseOracle']
    ladder = oracle(readable=[(850000, 1200000)])
    fit = ladder.run()
    local = [fit['measured_span_mm'][0] + .01, fit['measured_span_mm'][1] - .01]
    proof = dict(rungs=len(ladder.targets), failed_candidates=len(ladder.failed_candidates),
                 completion_status=fit['completion_status'], measured_span_mm=fit['measured_span_mm'],
                 sigma_measured_deg=fit['angle_sigma_measured_span_deg'],
                 sigma_full_disc_deg=fit['angle_sigma_full_disc_deg'],
                 local_use=assess_range(fit, local), image_use=assess_range(fit, [24.5,56]),
                 disexport_use=assess_range(fit, [25.8,54.4]))
    islands = oracle(readable=[(100000,500000),(850000,1200000),(1600000,1950000)]).run()
    proof['three_islands'] = islands['coverage']
    (OUT/'issue15.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')


def compare_selftest():
    def failures(name):
        raw = (OUT / name).read_bytes()
        content = raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8', errors='replace')
        return [line for line in content.splitlines() if line.startswith('  FAIL')]
    prior, current = failures('prior-selftest.txt'), failures('final-selftest.txt')
    proof = dict(baseline_failures=len(prior), current_failures=len(current),
                 added=sorted(set(current)-set(prior)), resolved=sorted(set(prior)-set(current)),
                 identical=prior == current)
    (OUT/'selftest-comparison.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    assert len(prior) == len(current) == 14 and proof['identical'], proof


def mark_simulations():
    # Label previously generated numerical evidence without touching saved real inputs.
    for name, prefix in (('simulations.json', ''), ('noise-simulations.json', 'noise-')):
        for row in json.loads((OUT/name).read_text(encoding='utf-8')):
            path = OUT / f"{prefix}{row['media']}-{row['profile']}" / 'summary.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['simulated'] = True
            path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if '--node' in sys.argv:
        node_checks()
        return
    if '--coverage' in sys.argv:
        coverage_checks()
        return
    if '--compare-selftest' in sys.argv:
        compare_selftest()
        return
    if '--mark-simulations' in sys.argv:
        mark_simulations()
        return
    if '--ladder-only' in sys.argv:
        from discprobe.selftest import Checker, _ladder, _ladder_abort, _ladder_safe_unwrap
        checks = Checker()
        for check in (_ladder, _ladder_abort, _ladder_safe_unwrap):
            check(checks)
        assert checks.failures == 0
        return
    rows = saved_fits() if '--saved-only' in sys.argv else simulations('--noise' in sys.argv)
    name = 'saved-fits.json' if '--saved-only' in sys.argv else 'noise-simulations.json' if '--noise' in sys.argv else 'simulations.json'
    (OUT / name).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    if '--saved-only' not in sys.argv:
        assert all('error' not in r and r['turn_errors'] == 0 and r['rms_deg'] < .5 for r in rows), rows
        assert all(r.get('same_targets', True) and r.get('delta_u', 0) == 0 and r.get('delta_v', 0) == 0 for r in rows)


if __name__ == '__main__':
    main()
