"""Cross-branch geometry checks; simulated sectors and temporary files only."""
import json
import math
from pathlib import Path
import tempfile

import numpy as np

from discprobe import discid, randomlabel
from discprobe.calib import theta
from discprobe.coverage import assess_range
from discprobe.geo import Ladder, write_outputs
from discprobe.imagedisc import load_correction
from discprobe.sim import SimDrive


def test_variable_probes_keep_identity_label_holes_and_completion_origin():
    for offset in (16, 65536):
        record = discid.create(code='ALPHA-VP', command='random')
        capacity = 2295104
        slots = {}
        for index, start in enumerate(discid.positions(capacity)):
            raw = discid.encode_copy(record, index)
            slots.update({start+i: raw[i*2048:(i+1)*2048] for i in range(4)})
        label = randomlabel.Label('ALPHA-VP', capacity)
        dev = SimDrive(phi_profile='mild', seed=7, jitter_us=20, outlier_rate=0,
                       rev_period_ms=26, identity_sectors=slots,
                       layout_sectors={randomlabel.START: randomlabel.marker(label.spec)})
        # Translate the simulator's spiral origin at both read edges. The read-end
        # truth is theta(end + offset), independently of Ladder._n_end, without
        # simulating thousands of extra turns of latency for the maximum offset.
        angle = dev.track_angle
        dev.track_angle = lambda sector: angle(sector + offset)
        ladder = Ladder(dev, ranges=[(20000, 2294000)], completion_sectors=offset,
                        speed_kbs=None, log=lambda *_: None)
        original = ladder._measure_retry
        measured = []
        def guarded(lba, reps=None):
            end = ((lba + ladder.tp.sectors - 1)//16+1)*16 + offset
            spans = ladder.tp.reserved_lba
            assert all(end <= a or lba >= z for a, z in spans)
            assert any(a <= lba and lba + 16 <= z for a, z in ladder.ranges)
            measured.append(lba)
            return original(lba, reps)
        ladder._measure_retry = guarded
        result = ladder.run()
        assert result['completion_status'] == 'target_reached'
        assert ladder.correction and len(ladder.probes) > 30
        assert result['completion_sectors'] == offset
        assert ladder.tp.summary['disc_identity']['record'] == record
        assert len(ladder.tp.summary['disc_identity']['copies']) == 4
        assert ladder.tp.summary['random_label']['text'] == 'ALPHA-VP'
        assert set(p['lba'] for p in ladder.probes) <= set(measured)
        assert set(p['lba'] for p in ladder.correction_checks) <= set(measured)
        assert all(abs(p['radius_mm'] - ladder._fit_radius(ladder._n_end(p['lba']))) < 1e-10
                   for p in ladder.probes)
        # Both identity slots and the label band remain holes in claimed coverage.
        for a, z in ladder.tp.reserved_lba:
            if ladder.ranges[0][0] < a < ladder.ranges[-1][1]:
                r = float(ladder._fit_radius(ladder._n_end((a+z)//2)))
                assert not assess_range(result, [r-.001, r+.001])['covered'], (
                    offset, a, z, r, result['coverage']['measured_intervals_mm'])
        with tempfile.TemporaryDirectory(prefix='geo-cross-') as temp:
            write_outputs(ladder, temp)
            saved = json.loads((Path(temp)/'summary.json').read_text())
            assert saved['reserved_lba'] == [list(x) for x in ladder.tp.reserved_lba]
            corr = load_correction(str(Path(temp)/'correction.json'))
            lbas = np.array([int(x) for a,z in ladder.ranges for x in np.linspace(a,z-16,400)])
            ns = np.array([ladder._n_end(int(x)) for x in lbas])
            predicted = np.degrees(theta(ns,ladder.u,ladder.v))-corr(ladder._fit_radius(ns))
            truth = np.array([math.degrees(dev.track_angle(dev._end_sectors((int(x)//16+1)*16))) for x in lbas])
            error = predicted-truth
            assert np.sqrt(np.mean((error-error.mean())**2)) < .5
