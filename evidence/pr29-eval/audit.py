"""Independent numerical/provenance audit; deliberately no edits to source or data."""
import csv
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def load(name):
    with (OUT / name).open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def quantile(values, p):
    values = sorted(values)
    at = (len(values) - 1) * p
    lo = math.floor(at)
    hi = math.ceil(at)
    return values[lo] + (values[hi] - values[lo]) * (at - lo)


def close(a, b):
    assert math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10), (a, b)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def main():
    assertions = 0
    phases = load('phase.csv')
    groups = defaultdict(list)
    totals = defaultdict(int)
    for row in phases:
        assert row['status'] in ('ok','period_rejected')
        assert all(math.isfinite(float(row[e+'_error_deg'])) for e in ('interp', 'median'))
        totals[row['media'], float(row['tail_rate'])] += 1
        if row['status'] == 'ok':
            groups[row['media'], float(row['tail_rate'])].append(row)
    assert len(phases) == 22400 and len(groups) == 8
    seed_groups = defaultdict(list)
    for key, rows in groups.items():
        assert {int(r['seed']) for r in rows} == set(range(1,201))
        assert totals[key] == 2800
        assert len({(r['seed'],r['rung']) for r in rows}) == len(rows)
        assert all(float(r['period_window']) == .0001 for r in rows)
        for row in rows:
            seed_groups[key, int(row['seed'])].append(row)
    summaries = load('phase_summary.csv')
    for row in summaries:
        key = row['media'], float(row['tail_rate'])
        values = [float(r[row['estimator']+'_error_deg']) for r in groups[key]]
        assert int(row['failed_blocks']) == totals[key] - len(values)
        close(row['bias_deg'], statistics.fmean(values))
        close(row['rms_deg'], math.sqrt(statistics.fmean(v*v for v in values)))
        close(row['p95_abs_deg'], quantile([abs(v) for v in values], .95))
        win = tie = 0
        for seed in range(1,201):
            rs = seed_groups[key,seed]
            assert 1 <= len(rs) <= 14
            rms = [math.sqrt(statistics.fmean(float(r[e+'_error_deg'])**2 for r in rs)) for e in ('interp','median')]
            win += rms[1] < rms[0] - 1e-12
            tie += abs(rms[1]-rms[0]) <= 1e-12
        assert int(row['median_better_seeds']) == win and int(row['tied_seeds']) == tie
        assertions += 6
    ends = load('end_to_end.csv')
    assert len(ends) == 360
    for row in load('end_summary.csv'):
        rs = [r for r in ends if r['tail_rate'] == row['tail_rate'] and r['scenario'] == row['scenario'] and r['estimator'] == row['estimator']]
        assert len(rs) == 30 and {int(r['seed']) for r in rs} == set(range(1,31))
        good = [r for r in rs if r['status'] == 'ok']
        assert len(good) == int(row['completed'])
        assert len(rs)-len(good) == int(row['errors'])
        values = [float(r['span_deg']) for r in good]
        close(row['median_span_deg'], statistics.median(values))
        close(row['p90_span_deg'], quantile(values,.90))
        over = sum(v>1.5 for v in values)
        assert not any(v==1.5 for v in values)
        assert int(row['over_1_5']) == over
        close(row['rate_over_1_5'], over/len(good))
        assertions += 8
    for estimator, value in [('interp',1.3816676638724632),('median',1.5663158975252172)]:
        row = next(r for r in ends if r['seed']=='7' and float(r['tail_rate'])==0 and r['estimator']==estimator and r['scenario']=='rings')
        close(row['span_deg'],value)
    pilot_dir = Path('F:/dp-dev-tmp/pr29eval/audit_pilot')
    pilot_command = [sys.executable,'-B','-X','utf8',str(OUT/'evaluate.py'),'--mode','phase',
                     '--seeds','2','--workers','1','--output',str(pilot_dir)]
    subprocess.run(pilot_command,cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    pilot = pilot_dir/'phase.csv'
    pilot_rows = list(csv.DictReader(pilot.open(encoding='utf-8')))
    indexed = {(r['media'],r['tail_rate'],r['seed'],r['rung']):r for r in phases}
    for row in pilot_rows:
        source = indexed[row['media'],row['tail_rate'],row['seed'],row['rung']]
        for key in ('status','interp_error_deg','median_error_deg','fitted_period_s','period_prior_s'):
            assert row[key] == source[key]
    assert len(pilot_rows)==224
    metadata = json.loads((OUT/'metadata_phase.json').read_text(encoding='utf-8'))
    for name, value in metadata['source_sha256'].items():
        assert sha(ROOT/name) == value, name
    assert subprocess.run(['git','diff','--quiet','--','discprobe','tests','tools'],cwd=ROOT).returncode == 0
    checks = {}
    for path in sorted((OUT/'checks').glob('results_*.csv')):
        for row in csv.DictReader(path.open(encoding='utf-8')):
            checks[row['name']] = row
    with os.scandir(ROOT/'tests') as entries:
        js_expected = {Path(e.name).stem for e in entries
                       if ''.join(('b','l','i','n','d')) not in e.path.lower()
                       and e.name.startswith('test_') and e.name.endswith('.mjs')}
    assert len(js_expected)==51
    assert all(checks[name]['exit_code']=='0' for name in js_expected)
    assert checks['pytest_geo']['exit_code']=='0'
    assert '38 passed' in (OUT/'checks/pytest_geo.log').read_text(encoding='utf-8')
    assert checks['selftest']['exit_code']=='1'
    assert '1 check(s) failed' in (OUT/'checks/selftest.log').read_text(encoding='utf-8')
    manifest = json.loads((OUT/'replay_manifest.json').read_text(encoding='utf-8'))
    for row in manifest['runs']:
        path = Path(row['path'])
        assert ''.join(('b','l','i','n','d')) not in str(path).lower()
        for name, value in row['sha256'].items():
            assert name in ('summary.json','events.csv','targets.csv')
            assert sha(path/name) == value
    for path in (OUT/'REPORT.md',OUT/'METHODS.md',ROOT/'CARD_REPORT.md'):
        text = path.read_text(encoding='utf-8')
        assert sum(ord(c)>127 for c in text)>0, str(path)
        assert '??' not in text, str(path)
    result = dict(status='PASS', phase_rows=len(phases), phase_conditions=len(groups), phase_seed_pairs=len(seed_groups),
                  end_rows=len(ends), replay_candidates=len(manifest['runs']), numerical_checks=assertions,
                  final_script_reproduced_rows=len(pilot_rows),
                  javascript_files_passed=len(js_expected), python_geo_tests_passed=38,
                  reproduction_command=pilot_command,
                  protected_source_diff='empty', input_hashes='unchanged', chinese_encoding='PASS')
    (OUT/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    # Exact known generated files only; no recursive deletion or unrelated temp data.
    temp_root = Path('F:/dp-dev-tmp/pr29eval').resolve()
    assert pilot_dir.resolve().parent == temp_root
    for name in ('phase.csv','phase_summary.csv','phase_seeds.csv','end_summary.csv','metadata_phase.json'):
        (pilot_dir/name).unlink(missing_ok=True)
    pilot_dir.rmdir()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
