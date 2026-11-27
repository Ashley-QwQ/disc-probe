"""Replay saved DVD rungs and exports without a device, for byte comparisons."""
import argparse
import csv
import json
import math
import sys
import subprocess
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discprobe.geo import Ladder, write_outputs
from discprobe.disexport import export
from discprobe.sim import SimDrive


def simulated_reference(out):
    """A full deterministic measurement, including events, against the base commit."""
    source = subprocess.run(['git','show','fbb3a43:discprobe/geo.py'],check=True,capture_output=True).stdout
    baseline = types.ModuleType('discprobe._geo_completion_reference')
    baseline.__package__ = 'discprobe'
    exec(compile(source, 'geo-reference.py', 'exec'), baseline.__dict__)
    for count in (1,16):
        for side, factory, writer in [('before',baseline.Ladder,baseline.write_outputs),
                                      ('after',Ladder,write_outputs)]:
            device = SimDrive(mode='cav',seed=7,reread_delay_ms=35.0)
            ladder = factory(device,speed_kbs=None,reps=16,max_targets=14,
                             log=lambda *_:None,sectors=count,state_check=False)
            ladder.run()
            ladder.tp.summary['simulated'] = True
            writer(ladder,str(out/side/f'geo-SIM-read{count}'))


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('output')
    args = ap.parse_args()
    out = Path(args.output)
    runs = [Path('D:/disc-probe/results') / name for name in (
        'geo-H-20261103-145334', 'geo-H-20261106-012546', 'geo-H-20261107-210507')]
    runs += [Path('D:/disc-probe/.claude/worktrees/web-walkthrough/results-real/geo-H-20261111-200909')]
    for run in runs:
        summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
        f = summary['fit']
        ladder = Ladder(None)
        ladder.ref = f['reference_lba']
        ladder.n_ref = ladder._n_end(ladder.ref)
        ladder.T = f['period_ms'] / 1000
        ladder.tp.last_lba = (summary.get('setup') or {}).get('last_lba', 2295103)
        ladder.tp.summary = {k: v for k, v in summary.items() if k != 'fit'}
        ladder.u, ladder.v, ladder.c = f['u'], f['v'], math.radians(f['c_deg'])
        for row in csv.DictReader((run / 'targets.csv').open(encoding='utf-8')):
            t = {k: float(v) for k, v in row.items() if v}
            t['lba'] = int(t['lba'])
            t['n'] = ladder._n_end(t['lba'])
            ladder.targets.append(t)
        ladder.fit()
        dest = out / run.name
        write_outputs(ladder, str(dest))
        # Export both the untouched original summary and the replayed fit.
        for name, source in [('original', run / 'summary.json'), ('replayed', dest / 'summary.json')]:
            export(str(source), 2297888, None, str(dest / (name + '-preset.json')),
                   25.8, 54.4, 'compat', 'Compatibility')
    if out.name == 'after':
        simulated_reference(out.parent)


if __name__ == '__main__':
    main()
