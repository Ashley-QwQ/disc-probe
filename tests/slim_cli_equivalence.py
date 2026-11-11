"""Replay complete geo_polyfit CLI output, including joint F-test verdicts."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import warnings

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from slim_support import ROOT, ARTIFACTS, low_priority
low_priority()
from slim_equivalence import snapshot, load_module, differences, write
import equivalence_scipy as oracle


def run(module, arguments):
    out, err = io.StringIO(), io.StringIO()
    previous = sys.argv
    sys.argv = ['geo_polyfit.py', *map(str, arguments)]
    error = None
    f_tests = []
    original_f = module.nested_f
    def nested(small, big):
        result = original_f(small, big)
        f_tests.append(dict(small=list(small), big=list(big), F=float(result[0]), p=float(result[1]),
                            dfn=int(result[2]), dfd=int(big[1])))
        return result
    module.nested_f = nested
    with redirect_stdout(out), redirect_stderr(err), warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter('always')
        try:
            module.main()
        except (SystemExit, ValueError, ArithmeticError, KeyError) as e:
            error = f'{type(e).__name__}: {e}'
        finally:
            sys.argv = previous
            module.nested_f = original_f
    return dict(stdout=out.getvalue(), stderr=err.getvalue(), error=error, warnings=[str(w.message) for w in ws], f_tests=f_tests)


def main():
    if not oracle.AVAILABLE:
        print('SKIPPED: optional SciPy oracle absent')
        return
    old = load_module(snapshot() / 'tools/geo_polyfit.py', '_cli_old_polyfit')
    new = load_module(ROOT / 'tools/geo_polyfit.py', '_cli_new_polyfit')
    inventory = json.loads((ARTIFACTS / 'inventory.json').read_text(encoding='utf-8'))
    rows = []
    for record in inventory['datasets']:
        path = record['path']
        a, b = run(old, [path]), run(new, [path])
        rows.append(dict(path=path, old=a, new=b, stdout_identical=a['stdout'] == b['stdout'], same_error=a['error'] == b['error']))
    group = [d['path'] for d in inventory['datasets'] if '/geo/gh70n-20261107/' in d['path'].replace('\\', '/')]
    joint = []
    for label, options in [('quadratic', []), ('cubic', ['--order', 'cubic']), ('phi5', ['--phi-degree', '5'])]:
        result = {}
        for name, module in [('old', old), ('new', new)]:
            folder = ARTIFACTS / ('joint-cli-' + label) / name
            folder.mkdir(parents=True, exist_ok=True)
            result[name] = run(module, [*group, *options, '--write-summary', folder / 'summary.json', '--write-correction', folder / 'correction.json'])
            result[name]['stdout_normalized_destination'] = result[name]['stdout'].replace(str(folder), '<OUTPUT>')
        result['mode'] = label
        result['stdout_identical_except_destination'] = result['old']['stdout_normalized_destination'] == result['new']['stdout_normalized_destination']
        for file in ('summary.json', 'correction.json'):
            a, b = [ARTIFACTS / ('joint-cli-' + label) / name / file for name in ('old', 'new')]
            if a.exists() and b.exists():
                result[file + '_delta'] = differences(json.loads(a.read_text()), json.loads(b.read_text()))
        joint.append(result)
    write('cli.json', dict(runs=rows, joint=joint))
    from slim_equivalence import beta_independent
    from discprobe.numerics import f_sf
    from decimal import Decimal
    import math
    actual = []
    for record in joint:
        for backend in ('old', 'new'):
            for test in record[backend]['f_tests']:
                if test['dfn'] <= 0 or test['dfd'] <= 0 or not math.isfinite(test['F']):
                    continue
                ref, ref_error = beta_independent(test['F'], test['dfn'], test['dfd'])
                value = f_sf(test['F'], test['dfn'], test['dfd'])
                delta = abs(Decimal.from_float(value) - ref)
                bound = Decimal(2) ** -53 + Decimal('1e-50')
                actual.append(dict(mode=record['mode'], backend=backend, **test, value=value, reference=str(ref),
                                   reference_error_bound=str(ref_error), delta=str(delta), bound=str(bound), passed=delta + ref_error <= bound))
    write('special_actual.json', actual)
    print(json.dumps(dict(single_runs=len(rows), identical_stdout=sum(r['stdout_identical'] for r in rows),
                          same_error=sum(r['same_error'] for r in rows),
                          joint_modes=len(joint), joint_identical=sum(r['stdout_identical_except_destination'] for r in joint))))


if __name__ == '__main__':
    main()
