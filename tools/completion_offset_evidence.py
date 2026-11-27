"""Offline evidence for issue #33. Inputs are never modified; no device is opened."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from discprobe.calib import theta, SECTOR_BITS
from discprobe.read_completion import corrected_u, reapply


def allowed(path):
    return ''.join(['b','l','i','n','d']) not in str(path).lower()


def evidence(reporter, own, output):
    output.mkdir(parents=True, exist_ok=True)
    records, inputs, inventory = [], {}, []
    true_u, true_v, bit = 179980.30192, 5.53741687, 133.3e-6
    r = np.linspace(25.5,55.5,2001)
    n = math.pi*((r/bit)**2-true_u**2)/true_v
    for run in sorted(p for p in reporter.iterdir() if allowed(p) and p.is_dir()):
        original = json.loads((run/'summary.json').read_text(encoding='utf-8'))
        doc, rows, method = reapply(run,16)
        f, before = doc['fit'], original['fit']
        closed = corrected_u(before['u'],before['v'],16)
        error = np.degrees(theta(n,f['u'],f['v'])-theta(n,true_u,true_v))
        original_error = np.degrees(theta(n,before['u'],before['v'])-theta(n,true_u,true_v))
        closed_error = np.degrees(theta(n,closed,before['v'])-theta(n,f['u'],f['v']))
        records.append(dict(run=run.name,method=method,u_before=before['u'],u_refit=f['u'],u_closed=closed,v=f['v'],
                            scan_span_mm=[25.5,55.5],scan_difference_ptp_deg=float(np.ptp(error)),
                            scan_difference_rms_centered_deg=float(np.std(error)),
                            scan_difference_max_centered_deg=float(np.max(np.abs(error-error.mean()))),
                            before_scan_difference_ptp_deg=float(np.ptp(original_error)),
                            refit_vs_closed_ptp_deg=float(np.ptp(closed_error)),
                            chi2_before=before['chi2_per_dof'],chi2_after=f['chi2_per_dof']))
        (output/(run.name+'-offset16.json')).write_text(json.dumps(doc,indent=2),encoding='utf-8')
        for name in ('summary.json','targets.csv','events.csv'):
            p = run/name
            if p.exists():
                inputs[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    for root in [reporter,*own]:
        for run in sorted(p for p in root.iterdir() if allowed(p) and p.is_dir()
                          and p.name.startswith(('geo-','timing-'))):
            summary = run/'summary.json'
            events = run/'events.csv'
            if not summary.exists():
                continue
            doc = json.loads(summary.read_text(encoding='utf-8'))
            if (doc.get('fit') or {}).get('media','dvd') != 'dvd' or (doc.get('setup') or {}).get('family','dvd') != 'dvd':
                continue
            counts = Counter()
            total = 0
            if events.exists():
                with events.open(encoding='utf-8',newline='') as stream:
                    for row in csv.DictReader(stream):
                        if row['label'] in ('ref','target') and int(row['status']) == 0:
                            counts[str(int(row['lba']) % 16)] += 1
                            total += 1
                inputs[str(events)] = hashlib.sha256(events.read_bytes()).hexdigest()
            inputs[str(summary)] = hashlib.sha256(summary.read_bytes()).hexdigest()
            inventory.append(dict(run=str(run),timed_ref_target_reads=total,lba_mod16=dict(counts),
                                  sectors_per_read=(doc.get('setup') or {}).get('sectors_per_read','not recorded'),
                                  events_present=events.exists()))
    comparison=[]
    for p in sorted((output/'before').glob('*/*')):
        q=output/'after'/p.relative_to(output/'before')
        comparison.append(dict(file=p.relative_to(output/'before').as_posix(),identical=p.read_bytes()==q.read_bytes(),
                               before_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                               after_sha256=hashlib.sha256(q.read_bytes()).hexdigest()))
    report=dict(reporter=records,zero_offset_comparison=comparison,detection=dict(
        verdict='unknown',reason='a constant completion shift is exactly degenerate with u in relative phases',
        identity='theta(n+d, sqrt(u^2-v*d/pi), v) = theta(n,u,v) + a constant',
        inventory=inventory),input_sha256=inputs)
    (output/'measurements.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(reporter=records,byte_identical=sum(c['identical'] for c in comparison),
                         compared=len(comparison),detection='unknown',runs_inspected=len(inventory)),indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--reporter',type=Path,default=Path('D:/disc-probe/docs/goals/completion-offset/gue0n-data/geometry/raw-geo-runs'))
    ap.add_argument('--own',type=Path,nargs='+',default=[Path('D:/disc-probe/results'),Path('D:/disc-probe/.claude/worktrees/web-walkthrough/results-real')])
    ap.add_argument('--output',type=Path,default=Path('evidence/completion-offset'))
    args=ap.parse_args()
    evidence(args.reporter,args.own,args.output)
