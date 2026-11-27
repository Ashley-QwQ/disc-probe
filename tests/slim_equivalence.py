"""Reproducible offline equivalence audit; writes evidence, never edits recordings.

Run: python -I -B tests/slim_equivalence.py [--section all|recorded|filters|iso|photo|special]
An audit with failed or unavailable certificates returns a failing equivalence
status in JSON. It is intentionally separate from ordinary regression tests.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, redirect_stdout
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import importlib.util
import io
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile
import warnings

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from slim_support import ROOT, ARTIFACTS, allowed, low_priority, walk
low_priority()
import numpy as np
from discprobe import numerics as new
import equivalence_scipy as old


def serial(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(type(obj).__name__)


def write(name, data):
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / name).write_text(json.dumps(data, default=serial, ensure_ascii=False, indent=2), encoding='utf-8')


def snapshot():
    destination = ARTIFACTS / 'baseline'
    if (destination / 'discprobe/__main__.py').is_file():
        return destination
    destination.mkdir(exist_ok=True)
    exclusions = [':(exclude,icase,glob)**/*b[l]ind*', ':(exclude,icase,glob)**/*b[l]ind*/**']
    archive = subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', 'HEAD', 'discprobe', 'tools', *exclusions], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source:
            if not allowed(member.name):
                raise ValueError('excluded path reached archive')
            source.extract(member, destination, filter='data')
    return destination


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def flat(value, prefix=''):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(flat(child, f'{prefix}.{key}' if prefix else key))
    elif isinstance(value, (list, tuple, np.ndarray)):
        for i, child in enumerate(value):
            result.update(flat(child, f'{prefix}[{i}]'))
    elif isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)):
        result[prefix] = float(value)
    return result


def differences(a, b):
    aa, bb = flat(a), flat(b)
    return {key: abs(value - bb[key]) for key, value in aa.items() if key in bb and math.isfinite(value) and math.isfinite(bb[key])}


def run_pair(module, call):
    """Capture both returned points, and recompute diagnostics independently."""
    results, captures = {}, {}
    for name, solver in [('old', old.least_squares), ('new', new.least_squares)]:
        records = []
        def solve(fun, x0, **kwargs):
            sol = solver(fun, x0, **kwargs)
            records.append((fun, kwargs.get('jac'), np.array(sol.x), new.solution_certificate(fun, sol.x, kwargs.get('jac'))))
            return sol
        before = module.least_squares
        module.least_squares = solve
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            try:
                results[name] = dict(value=call(), warnings=[str(w.message) for w in ws])
            except (ValueError, ArithmeticError, np.linalg.LinAlgError) as e:
                results[name] = dict(error=f'{type(e).__name__}: {e}', warnings=[str(w.message) for w in ws])
            finally:
                module.least_squares = before
        captures[name] = records
    comparisons = []
    for a, b in zip(captures['old'], captures['new']):
        fun, jac, x, cert = a
        y, other = b[2], b[3]
        J = np.asarray(jac(x) if callable(jac) else new._jacobian(fun, x))
        # Delta expressed in the measurement's weighted observation metric.
        noise_scale = max(1., math.sqrt(2 * cert['cost'] / max(1, len(fun(x)) - len(x))))
        scaled_delta = float(np.linalg.norm(J @ (y - x)) / noise_scale)
        coordinate_sigma = np.sqrt(np.maximum(0, np.diag(cert['covariance'])))
        comparisons.append(dict(old=cert, new=other, cost_delta=abs(cert['cost'] - other['cost']),
                                delta_observation_sigma=scaled_delta,
                                delta_parameter_sigma=float(np.max(np.abs(y - x) / np.maximum(coordinate_sigma, np.finfo(float).tiny))),
                                x_old=x, x_new=y))
    results['solutions'] = comparisons
    if 'value' in results['old'] and 'value' in results['new']:
        results['delta'] = differences(results['old']['value'], results['new']['value'])
    return results


def replay_geo(path, run):
    """Re-fit recorded rungs with the unchanged geo algorithm, no drive object."""
    import csv
    from types import SimpleNamespace
    geo = load_module(path, 'discprobe._audit_geo_' + str(abs(hash(str(path)))))
    report = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
    f = report['fit']
    rows = list(csv.DictReader((run / 'targets.csv').open()))
    ladder = object.__new__(geo.Ladder)
    from discprobe import cd
    from discprobe.calib import CalLayout
    from discprobe.geometry import NOMINAL
    ladder.media = f.get('media', 'dvd')
    ladder.audio = f.get('track') == 'audio'
    ladder.read_offset_bytes = f.get('read_offset_bytes', 0.)
    ladder.prior = CalLayout(r0_mm=cd.R0_MM if ladder.media == 'cd' else NOMINAL['dvd'].r0_mm,
                             pitch_um=cd.PITCH_UM if ladder.media == 'cd' else .74, bit_nm=f['bit_nm_assumed'])
    ladder.u0, ladder.v0 = ladder.prior.u0, ladder.prior.v0
    ladder.u, ladder.v = f['u'], f['v']
    ladder.c = math.radians(f.get('c_deg', 0))
    ladder.targets = [dict(n=float(r['n_bits']), unwrapped_deg=float(r['unwrapped_deg']), sigma_deg=float(r['sigma_deg'])) for r in rows]
    # Identical reconstruction on both paths. Prior settings that were not
    # recorded are explicitly reconstruction assumptions, not recovered data.
    ladder.sig_u = (.08 if ladder.media == 'cd' else .01) * ladder.u0
    ladder.sig_v = (.15 if ladder.media == 'cd' else .03) * ladder.v0
    ref = f.get('reference_lba', int(rows[0]['lba']))
    ladder.ref = ref
    ladder.n_ref = ladder._n_end(ref)
    ladder.tp = SimpleNamespace(last_lba=report.get('setup', {}).get('last_lba', 2295103))
    ladder.T = f.get('period_ms', 0.) / 1000 if f.get('period_ms') is not None else None
    ladder.state = f.get('state_check')
    for key in ('completion_status', 'failed_candidates'):
        if key in f:
            setattr(ladder, key, f[key])
    ladder.fit()
    return dict(summary=ladder.result(), cov=ladder.cov, residual_deg=[t['residual_deg'] for t in ladder.targets])


def recorded():
    if not old.AVAILABLE:
        return dict(status='SKIPPED', reason='SciPy oracle absent')
    inventory = json.loads((ARTIFACTS / 'inventory.json').read_text(encoding='utf-8'))
    baseline = snapshot()
    gp = load_module(ROOT / 'tools/geo_polyfit.py', '_audit_polyfit')
    from discprobe import disexport, cd
    runs = []
    for dataset in inventory['datasets']:
        run = Path(dataset['path'])
        record = dict(path=str(run), targets_sha256=dataset['targets_sha256'])
        try:
            n, y, s, f = gp.load(run)
            if 'u' not in f:
                raise ValueError('not an angular fit')
            rc, rs = gp.RC_MM / (f['bit_nm_assumed'] * 1e-6), gp.RS_MM / (f['bit_nm_assumed'] * 1e-6)
            fits = {}
            for order in (0, 2, 3):
                if len(n) <= 3 + order:
                    fits[str(order)] = dict(status='INSUFFICIENT_POINTS')
                    continue
                fits[str(order)] = run_pair(gp, lambda order=order: gp.fit(n, y, s, f['u'], f['v'], order, rc, rs))
            record['polyfit'] = fits
            a = replay_geo(baseline / 'discprobe/geo.py', run)
            b = replay_geo(ROOT / 'discprobe/geo.py', run)
            record['geo'] = dict(delta=differences(a, b), reconstruction='recorded rounded rungs, documented default priors; unrecorded custom priors cannot be recovered; not acquisition replay')
            media = f.get('media', 'dvd')
            sectors = f.get('sectors', cd.CAPACITY if media == 'cd' else 2295104)
            lo = max(25 if media == 'cd' else 24, float(np.min(f['bit_nm_assumed'] * 1e-6 * np.sqrt(f['u'] ** 2 + f['v'] * n / np.pi))))
            hi = min(58., float(np.max(f['bit_nm_assumed'] * 1e-6 * np.sqrt(f['u'] ** 2 + f['v'] * n / np.pi))))
            record['disexport'] = run_pair(disexport, lambda: disexport.fit_preset(f['u'], f['v'], f['bit_nm_assumed'], sectors, lo, hi,
                                                                                 sector_bits=57624 if media == 'cd' else 38688))
            if 'delta' in record['disexport']:
                old_value = record['disexport']['old']['value']
                new_value = record['disexport']['new']['value']
                formats = {'innerRadiusMm': '.9f', 'outerRadiusMm': '.9f', 'pitchLinear': '.3e',
                           'pitchQuadratic': '.3e', 'pitchCubic': '.3e', 'max_angle_diff_deg': '.4f', 'rms_angle_diff_deg': '.4f'}
                record['disexport']['printed_changed'] = {k: [format(old_value[k], fmt), format(new_value[k], fmt)]
                                                          for k, fmt in formats.items() if format(old_value[k], fmt) != format(new_value[k], fmt)}
                record['disexport']['json_value_changed'] = [k for k in old_value if old_value[k] != new_value[k]]
                record['disexport']['source_uncertainty'] = {k: f[k] for k in ('u_sigma', 'v_sigma', 'angle_sigma_deg') if k in f}
                record['disexport']['inner_radius_sigma_mm'] = f.get('u_sigma', 0) * f['bit_nm_assumed'] * 1e-6
        except (ValueError, KeyError, ArithmeticError, np.linalg.LinAlgError) as e:
            record['error'] = str(e)
        runs.append(record)
        write('recorded_partial.json', runs)
    # These five archived runs are explicitly documented as one GH70N disc.
    group = [Path(d['path']) for d in inventory['datasets'] if '/geo/gh70n-20261107/' in d['path'].replace('\\', '/')]
    joints = []
    if group:
        data = [gp.load(path) for path in group]
        bit = data[0][3]['bit_nm_assumed'] * 1e-6
        for order in (0, 2, 3):
            result = run_pair(gp, lambda order=order: gp.joint_fit(data, order, gp.RC_MM / bit, gp.RS_MM / bit))
            joints.append(dict(runs=list(map(str, group)), order=order, **result))
    summaries_without_rungs = []
    for filename in inventory['json_files']:
        path = Path(filename)
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get('fit'), dict) and 'u' in obj['fit'] and not (path.parent / 'targets.csv').is_file():
            summaries_without_rungs.append(dict(path=str(path), status='INPUT_MISSING', reason='no matching targets.csv; summary is not raw evidence'))
    return dict(runs=runs, joint=joints, summaries_without_rungs=summaries_without_rungs,
                archived_presets=replay_archived_presets(inventory))


def replay_archived_presets(inventory):
    from discprobe import disexport
    presets = []
    from discprobe.imagedisc import load_correction
    for filename in inventory['json_files']:
        path = Path(filename)
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get('preset'), dict):
            continue
        source = obj.get('source', {})
        geo_candidates = [Path(p) for p in inventory['json_files'] if Path(p).name == source.get('geo')]
        correction_candidates = [Path(p) for p in inventory['json_files'] if Path(p).name == source.get('correction')]
        # Prefer a same-directory source. Copies with identical content do not
        # introduce a different numerical input; distinct contents do.
        def select(candidates, source_name):
            local = path.parent / (source_name or '')
            if local in candidates:
                return [local]
            by_digest = {}
            for candidate in candidates:
                by_digest.setdefault(hashlib.sha256(candidate.read_bytes()).hexdigest(), candidate)
            return list(by_digest.values())
        geo_candidates = select(geo_candidates, source.get('geo'))
        correction_candidates = select(correction_candidates, source.get('correction'))
        record = dict(path=str(path))
        if len(geo_candidates) != 1 or (source.get('correction') and len(correction_candidates) != 1):
            presets.append(dict(**record, status='INPUT_MISSING_OR_AMBIGUOUS'))
            continue
        f = json.loads(geo_candidates[0].read_text(encoding='utf-8'))['fit']
        preset = obj['preset']
        lo, hi = obj['fit']['fit_range_mm']
        correction = load_correction(str(correction_candidates[0])) if correction_candidates else None
        sectors = preset.get('totalSectors', preset.get('sectors'))
        result = run_pair(disexport, lambda: disexport.fit_preset(f['u'], f['v'], f['bit_nm_assumed'], sectors, lo, hi,
                                                                 correction, 57624 if f.get('media') == 'cd' else 38688))
        record.update(result)
        record['source'] = dict(geo=str(geo_candidates[0]), correction=str(correction_candidates[0]) if correction_candidates else None)
        if 'value' in result['old']:
            record['historical_archive_delta'] = differences(obj['fit'], result['old']['value'])
        if 'value' in result['old'] and 'value' in result['new']:
            formats = {'innerRadiusMm': '.9f', 'outerRadiusMm': '.9f', 'pitchLinear': '.3e', 'pitchQuadratic': '.3e',
                       'pitchCubic': '.3e', 'max_angle_diff_deg': '.4f', 'rms_angle_diff_deg': '.4f'}
            record['printed_changed'] = {k: [format(result['old']['value'][k], fmt), format(result['new']['value'][k], fmt)]
                                         for k, fmt in formats.items() if format(result['old']['value'][k], fmt) != format(result['new']['value'][k], fmt)}
        presets.append(record)
    return presets


def filters():
    from scipy_oracle_checks import gaussian_bound, fft_bound
    from PIL import Image
    inventory = json.loads((ARTIFACTS / 'inventory.json').read_text(encoding='utf-8'))
    rng = np.random.default_rng(20261111)
    arrays = [('random64', rng.normal(size=(81, 93))), ('random32', rng.normal(size=(81, 93)).astype('float32'))]
    # Real files are full images, not resized test substitutes.
    for rec in inventory['photos']:
        if 'photo-check-fanjzss' in rec['path'] and rec['path'].lower().endswith('.jpg'):
            with Image.open(rec['path']) as im:
                arrays.append((rec['path'], np.asarray(im.convert('L'), dtype=np.float32) / 255))
    rows = []
    for name, a in arrays:
        for sigma in (1, 1.5, 5, 6, 12, 15):
            delta = float(np.max(np.abs(new.gaussian_filter(a, sigma) - old.gaussian_filter(a, sigma))))
            bound = gaussian_bound(a, sigma)
            rows.append(dict(input=name, function='gaussian_filter', sigma=sigma, delta=delta, bound=bound, passed=delta <= bound))
        from discprobe.beaconread import _ring_kernel
        b = _ring_kernel([3., 6., 9.])
        delta = float(np.max(np.abs(new.fftconvolve(a, b) - old.fftconvolve(a, b, 'same'))))
        bound = fft_bound(a, b)
        rows.append(dict(input=name, function='fftconvolve', delta=delta, bound=bound, passed=delta <= bound))
        for width in (3, 11, 31):
            aa, bb = new.maximum_filter(a, width), old.maximum_filter(a, width)
            rows.append(dict(input=name, function='maximum_filter', size=width, passed=aa.tobytes() == bb.tobytes()))
        # The only production uniform_filter call explicitly produces float64.
        a64 = a.astype(np.float64)
        aa, bb = new.uniform_filter(a64, (41, 1)), old.uniform_filter(a64, (41, 1), mode='nearest')
        bound = 500 * np.finfo(float).eps * max(1, a.shape[0]) * float(np.max(np.abs(a)))
        rows.append(dict(input=name, function='uniform_filter', delta=float(np.max(np.abs(aa - bb))), bound=bound,
                         passed=float(np.max(np.abs(aa - bb))) <= bound))
    return rows


def beta_independent(value, dfn, dfd):
    """Independent binomial integral series, 180+ digit Decimal arithmetic.

    This expands (1-t)^(b-1), unlike the positive Euler-transformed production
    series. Beta normalization uses the half-integer gamma identity.
    """
    with localcontext() as ctx:
        ctx.prec = max(180, 2 * (dfn + dfd))
        D = Decimal
        a, b = D(dfd) / 2, D(dfn) / 2
        x = D(dfd) / (D(dfd) + D(dfn) * D.from_float(float(value)))
        complement = x > D('.5')
        if complement:
            a, b, x = b, a, 1 - x
        term = total = 1 / a
        absolute_sum = abs(term)
        for k in range(100000):
            term *= (D(k + 1) - b) / D(k + 1) * x * (a + k) / (a + k + 1)
            total += term
            absolute_sum += abs(term)
            # After b, the remaining magnitude ratio is strictly below x.
            if k > b and abs(term) * x / (1 - x) < D('1e-100'):
                break
        else:
            raise ArithmeticError('independent integral series exhausted')
        # Compute pi independently by Machin's arctangent identity.
        def atan(z):
            power, s, k = z, z, 1
            while True:
                power *= -z * z
                t = power / (2 * k + 1)
                s += t
                if abs(t) < D(10) ** (-ctx.prec + 10):
                    return s
                k += 1
        pi = 16 * atan(D(1) / 5) - 4 * atan(D(1) / 239)
        def gamma(z):
            value = D(1) if z == z.to_integral_value() else pi.sqrt()
            t = D(1) if z == z.to_integral_value() else D('.5')
            while t < z:
                value *= t
                t += 1
            return value
        normalizer = gamma(a) * gamma(b) / gamma(a + b)
        xa = x ** int(a) * (x.sqrt() if a != a.to_integral_value() else 1)
        v = total * xa / normalizer
        tail = abs(term) * x / (1 - x) * abs(xa / normalizer)
        rounding = D(10) ** (-ctx.prec + 17) * max(D(1), absolute_sum) * max(D(1), abs(xa / normalizer))
        return (1 - v if complement else v), tail + rounding


def special():
    rows = []
    for dfn, dfd in itertools.product((1, 2, 3, 5, 12, 30), (1, 2, 5, 28, 100, 500)):
        for value in (1e-8, .01, .1, 1., 10., 100., 1e8):
            ref, reference_error = beta_independent(value, dfn, dfd)
            actual = new.f_sf(value, dfn, dfd)
            delta = abs(Decimal.from_float(actual) - ref)
            bound = Decimal(2) ** -53 + Decimal('1e-50')
            rows.append(dict(F=value, dfn=dfn, dfd=dfd, new=actual, reference=str(ref), reference_error_bound=str(reference_error),
                             delta=str(delta), bound=str(bound), passed=delta + reference_error <= bound))
    return rows


def iso():
    baseline = snapshot()
    commands = [['random', '--sectors', '256', '--seed', '317'],
                ['random', '--sectors', '256', '--seed', '318', '--media', 'bd'],
                ['calibdisc', '--sectors', '512']]
    results = []
    for i, command in enumerate(commands):
        paths, modules = {}, {}
        for backend, root in [('old', baseline), ('new', ROOT)]:
            output = ARTIFACTS / f'iso-{i}-{backend}.iso'
            module_file = ARTIFACTS / f'iso-{i}-{backend}-modules.json'
            code = "import sys,runpy,json,atexit,datetime; sys.path.insert(0,sys.argv.pop(1)); dest=sys.argv.pop(1); original=datetime.datetime; Frozen=type('Frozen',(original,),{'now':classmethod(lambda cls,tz=None: cls(2026,11,11,12,0,0,tzinfo=tz))}); datetime.datetime=Frozen; atexit.register(lambda: open(dest,'w').write(json.dumps(sorted(sys.modules)))); runpy.run_module('discprobe',run_name='__main__')"
            done = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(root), str(module_file), *command, '--output', str(output)],
                                  cwd=ARTIFACTS, capture_output=True, text=True)
            if done.returncode:
                results.append(dict(command=command, backend=backend, error=done.stderr[-2000:]))
                break
            paths[backend] = hashlib.sha256(output.read_bytes()).hexdigest()
            modules[backend] = json.loads(module_file.read_text())
        else:
            results.append(dict(command=command, sha256=paths, bytes=output.stat().st_size,
                                identical=paths['old'] == paths['new'],
                                scipy_modules={k: [m for m in v if m == 'scipy' or m.startswith('scipy.')] for k, v in modules.items()}))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--section', choices=('all', 'recorded', 'presets', 'filters', 'iso', 'special'), default='all')
    a = ap.parse_args()
    if not old.AVAILABLE:
        print('SKIPPED: optional SciPy oracle absent')
        return
    if a.section == 'presets':
        inventory = json.loads((ARTIFACTS / 'inventory.json').read_text(encoding='utf-8'))
        result = replay_archived_presets(inventory)
        recorded_data = json.loads((ARTIFACTS / 'recorded.json').read_text(encoding='utf-8'))
        recorded_data['archived_presets'] = result
        write('recorded.json', recorded_data)
        print('archived presets: evidence written', flush=True)
        return
    for name, function in [('recorded', recorded), ('filters', filters), ('iso', iso), ('special', special)]:
        if a.section in ('all', name):
            result = function()
            write(name + '.json', result)
            print(name + ': evidence written', flush=True)


if __name__ == '__main__':
    main()
