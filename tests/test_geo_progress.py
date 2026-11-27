"""Geometry progress regressions; every read goes to SimDrive."""
import io
import json

import pytest

from discprobe import ui
from discprobe.geo import Ladder, SENTINEL_REPS
from discprobe.sim import SimDrive


@pytest.mark.parametrize('state_check,max_targets,sectors', [(True, 22, 1), (False, 8, 4)])
def test_simulated_geo_progress(monkeypatch, state_check, max_targets, sectors):
    dev = ui.ProgressDevice(SimDrive(jitter_us=0, outlier_rate=0))
    ladder = Ladder(dev, log=lambda *_: None, state_check=state_check,
                    max_targets=max_targets, sectors=sectors)
    status = ui.geo_status(ladder, dev)
    samples = []

    class Observer:
        def tick(self, **kwargs):
            samples.append(status())

        def play(self):
            pass

    dev.progress = Observer()
    original = ladder.measure
    retried = []

    def measure(lba, reps=None):
        result = original(lba, reps)
        # Repeat a full block, including the settling reads in between.
        if not retried:
            retried.append(lba)
            return None
        return result

    monkeypatch.setattr(ladder, 'measure', measure)
    ladder.run()
    samples.append(status())
    assert len(ladder.targets) == max_targets
    assert retried
    assert all(f is None or 0 <= f <= 1 for f, _, _ in samples)
    assert all(eta is None or eta >= 0 for _, _, eta in samples)
    assert all(f is None or f < 1 for f, _, _ in samples[:-1])
    assert samples[-1] == (1.0, 'geometry complete', 0.0)
    assert ladder.progress_total == (max_targets + 2 * len(ladder.sentinels) * SENTINEL_REPS) * ladder.reps
    if state_check:
        checks = [(f, stage) for f, stage, _ in samples if stage == 'reading check points again']
        assert checks
        assert checks[0][0] < checks[-1][0] < 1
        assert ladder.progress_checks_done == 2 * len(ladder.sentinels) * SENTINEL_REPS * ladder.reps


def test_dense_geo_progress_is_monotonic_through_retry(monkeypatch):
    dev = ui.ProgressDevice(SimDrive(phi_profile='i218', rev_period_ms=26, jitter_us=20,
                                    outlier_rate=0, seed=7))
    ladder = Ladder(dev, ranges=[(20000, 2294000)], speed_kbs=None, log=lambda *_: None)
    status = ui.geo_status(ladder, dev)
    fractions = []
    retried = []

    class Observer:
        def tick(self, **kwargs):
            fraction, stage, _ = status()
            if stage == 'measuring angle correction':
                fractions.append(fraction)

        def play(self):
            pass

    dev.progress = Observer()
    original = ladder.measure

    def measure(lba, reps=None):
        result = original(lba, reps)
        if ladder.progress_stage == 'measuring angle correction' and not retried:
            retried.append(lba)
            return None
        return result

    monkeypatch.setattr(ladder, 'measure', measure)
    assert ladder.run()['completion_status'] == 'target_reached'
    assert retried and ladder.correction and len(ladder.probes) > 100
    assert fractions[0] < fractions[-1] < 1
    assert fractions == sorted(fractions)
    assert status() == (1., 'geometry complete', 0.)


def test_rate_and_emitted_progress_are_bounded(monkeypatch, tmp_path):
    rate = ui._Rate()
    monkeypatch.setattr(ui.time, 'monotonic', lambda: 10)
    assert rate.left(0, 22) is None
    monkeypatch.setattr(ui.time, 'monotonic', lambda: 20)
    assert rate.left(23, 22) == 0
    events = tmp_path / 'events.jsonl'
    monkeypatch.setenv('DISCPROBE_EVENTS', str(events))
    for fraction in (1.05, -0.05):
        progress = ui.Progress(lambda: (fraction, 'geo', -5), ui.Term(io.StringIO(), env={'TERM': 'dumb'}))
        progress.tick(force=True)
        progress._render()
        assert progress.left == 0
        progress.close()
    for event in map(json.loads, events.read_text().splitlines()):
        assert 0 <= event['fraction'] <= 1
        assert event['eta_s'] == 0


def test_calibrate_simulator_events(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    events = tmp_path / 'calibrate-events.jsonl'
    env = dict(os.environ, DISCPROBE_EVENTS=str(events),
               PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run(
        [sys.executable, '-m', 'discprobe', 'calibrate', '--drive', 'SIM',
         '--sim', 'cav', '--out', str(tmp_path / 'results')],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90,
    )
    # At the wider 1%-98% default this fixed noisy seed completes all reads but
    # exceeds the unchanged angle-sigma gate. Progress must still reach 100%,
    # and calibration must report the refusal rather than a successful fit.
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'too_noisy' in result.stderr
    rows = list(map(json.loads, events.read_text(encoding='utf-8').splitlines()))
    assert [e['name'] for e in rows if e['type'] == 'step'] == ['check', 'timing', 'geo']
    geo_start = next(i for i, e in enumerate(rows) if e['type'] == 'step' and e['name'] == 'geo')
    progress = [e for e in rows[geo_start:] if e['type'] == 'progress']
    points = [e for e in rows[geo_start:] if e['type'] == 'geo_point']
    assert [e['rung'] for e in points] == list(range(1, 23))
    assert all(24 <= e['radius_mm'] <= 58 and e['sigma_deg'] > 0 for e in points)
    assert progress
    assert all(e['fraction'] is None or 0 <= e['fraction'] <= 1 for e in progress)
    assert all(e['eta_s'] is None or e['eta_s'] >= 0 for e in progress)
    assert progress[-1]['fraction'] == 1
    assert progress[-1]['eta_s'] == 0
    calibrated = next(e for e in rows if e['type'] == 'calibrated')
    assert not calibrated['ok'] and calibrated['geo']['verdict'] == 'too_noisy'


def test_web_progress_bounds():
    from pathlib import Path
    import shutil
    import subprocess

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is needed to execute the web progress regression')
    result = subprocess.run([node, str(Path(__file__).with_suffix('.mjs'))],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
