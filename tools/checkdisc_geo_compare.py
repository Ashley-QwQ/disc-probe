"""Offline default-range evidence; run before/after with the same simulator seed."""
import argparse
import json
import inspect
from pathlib import Path
import sys
import textwrap
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discprobe.geo import Ladder
from discprobe.sim import SimDrive
from discprobe.coverage import assess_range


def main():
    p = argparse.ArgumentParser()
    p.add_argument('label', choices=('before', 'after'))
    args = p.parse_args()
    rows = []
    for media in ('dvd', 'cd'):
        dev = SimDrive(media=media, seed=7, reread_delay_ms=35.0)
        ladder = Ladder(dev, media=media, speed_kbs=None, log=lambda *_: None)
        if args.label == 'before':
            # Reproduce the former default in memory; keep all reads, range
            # filtering and completion logic identical, without editing sources.
            import discprobe.geo as module
            source = textwrap.dedent(inspect.getsource(Ladder.run))
            added = ('    elif self.media in ("dvd", "cd"):\n'
                     '        self.ranges = [(int(last * 0.01), int(last * 0.98))]\n')
            if added in source:
                source = source.replace(added, '', 1)
                scope = dict(vars(module))
                exec(compile(source, '<legacy default ranges>', 'exec'), scope)
                ladder.run = types.MethodType(scope['run'], ladder)
        start = time.perf_counter()
        fit = ladder.run()
        rows.append(dict(media=media, seed=7, ranges=ladder.ranges,
                         coverage=fit['coverage'], targets=len(ladder.targets),
                         chi2_per_dof=fit['chi2_per_dof'],
                         angle_sigma_measured_span_deg=fit['angle_sigma_measured_span_deg'],
                         angle_sigma_full_disc_deg=fit['angle_sigma_full_disc_deg'],
                         common_span_mm=[27., 54.],
                         common_span_sigma_deg=assess_range(fit, [27., 54.])['conditional_angle_sigma_deg'],
                         wall_seconds=time.perf_counter()-start,
                         simulated_seconds=dev._clock-1000.0, media_reads=dev.media_reads))
    dest = Path(__file__).resolve().parents[1]/'docs/goals/checkdisc'
    dest.mkdir(parents=True, exist_ok=True)
    (dest/f'geo-{args.label}.json').write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
