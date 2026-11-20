"""Coverage and continuation against the Disc Lab reader, without full-disc files."""
import contextlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np

from disclab.box import make_box
from disclab.drive import LabDrive
from disclab.lab import Lab, atomic_json
from discprobe.coverage import assess_range, default_range
from discprobe import geo
from discprobe.geo import Ladder, resume_source, write_outputs


@contextlib.contextmanager
def lab_disc(tmp_path, *, with_gaps):
    with tempfile.TemporaryDirectory(dir=tmp_path, prefix='geo-lab-') as folder:
        lab = Lab(folder)
        make_box(lab, 'dvd-r', 1, seed=178)
        disc = lab.box()['discs'][0]
        answers = lab.answers()
        truth = answers['discs'][disc]
        truth.update(ecc_um=0.0, varpitch_deg=[0.0] * len(truth['varpitch_r_mm']))
        if not with_gaps:
            # With this inner radius the pre-existing search already reaches 24.5 mm.
            truth['u'] -= 1400
        answers['readers']['gh70n'].update(jitter_us=2, outlier_rate=0)
        atomic_json(lab.answers_path, answers)
        with lab.locked_state() as state:
            state['drives']['X:']['tray'] = disc
            state['burns'][disc] = dict(closed=True, sessions=[
                dict(start_lba=0, sectors=2251920, mode='imapi', iso='unused.iso')])

        class Reader(LabDrive):
            def __init__(self):
                super().__init__(lab, 'X:')
                if with_gaps:
                    # The production metadata probe sees an old random-data disc.
                    self.identity_sectors[-1] = b''

            def _content(self, lba, count):
                return b''.join(np.random.default_rng(lba + i).bytes(2048) for i in range(count))

        yield lab, Reader


def read_ladder(reader, **kwargs):
    with reader() as drive:
        ladder = Ladder(drive, speed_kbs=5540, log=lambda _: None, **kwargs)
        fit = ladder.run()
    return ladder, fit


def test_repairs_absent_identity_slots_on_lab_disc(tmp_path):
    with lab_disc(tmp_path, with_gaps=True) as (_, reader):
        ladder, fit = read_ladder(reader)
        assert fit['completion_status'] == 'target_reached'
        assert assess_range(fit, default_range('dvd'))['covered']
        assert len(ladder.targets) > 22
        assert {750144, 1501568} <= {t['lba'] for t in ladder.targets[22:]}


def test_continues_saved_rungs_on_same_lab_disc(tmp_path, monkeypatch):
    with lab_disc(tmp_path, with_gaps=True) as (lab, reader):
        with monkeypatch.context() as patch:
            # Record the equivalent of the previous version stopping at 22 rungs.
            patch.setattr(Ladder, '_fill_coverage', lambda self: None)
            ladder, old = read_ladder(reader)
        run = Path(tmp_path) / 'geo-X-20261119-231212'
        write_outputs(ladder, str(run))
        assessment = assess_range(old, (25.8, 54.4))
        assert len(assessment['extrapolated_mm']) == 2
        previous_bytes = (run / 'targets.csv').read_bytes()
        events = Path(tmp_path) / 'events.jsonl'
        monkeypatch.setenv('DISCPROBE_EVENTS', str(events))
        resume = resume_source(run, 'dvd')
        resumed, new = read_ladder(reader, resume=resume, ref_lba=old['reference_lba'])
        assert assess_range(new, default_range('dvd'))['covered']
        assert [r['lba'] for r in resumed.targets[:22]] == [r['lba'] for r in ladder.targets]
        for i, key in enumerate(('u', 'v')):
            assert abs(new[key] - old[key]) <= math.sqrt(old['covariance_uv'][i][i])
        assert (run / 'targets.csv').read_bytes() == previous_bytes
        rows = list(map(json.loads, events.read_text(encoding='utf-8').splitlines()))
        assert [e['rung'] for e in rows if e['type'] == 'geo_point'] == list(range(23, len(resumed.targets) + 1))
        assert lab.root.is_dir()


def test_lab_disc_with_coverage_does_not_add_rungs(tmp_path):
    with lab_disc(tmp_path, with_gaps=False) as (_, reader):
        ladder, fit = read_ladder(reader)
        assert fit['completion_status'] == 'target_reached'
        assert assess_range(fit, default_range('dvd'))['covered']
        assert len(ladder.targets) == 22


def test_lab_disc_at_coverage_budget_keeps_unmeasured_bands(tmp_path, monkeypatch):
    monkeypatch.setattr(geo, 'MAX_COVERAGE_READS', 1)
    with lab_disc(tmp_path, with_gaps=True) as (_, reader):
        ladder, fit = read_ladder(reader)
        assert len(ladder.targets) == 23
        assert fit['completion_status'] == 'coverage_incomplete'
        assert assess_range(fit, default_range('dvd'))['extrapolated_mm']
