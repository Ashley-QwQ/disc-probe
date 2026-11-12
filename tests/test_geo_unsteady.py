"""Rotation and calibration regressions: fake children and simulated drives only."""
import argparse
import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from discprobe import calibrate, geo, webui


REASON = ("the drive's speed is not steady (63.50 ms a turn at 26 mm, 21.18 ms at 56 mm): "
          "it probably slowed down on a hard-to-read part of the disc")


def arguments(*extra):
    parser = argparse.ArgumentParser()
    calibrate.add_parser(parser.add_subparsers())
    return parser.parse_args(['calibrate', '--drive', 'SIM', *extra])


@pytest.mark.parametrize('ratio,reason', [
    (1, None), (1.04, None), (0.96, None),
    (56 / 26, 'the drive is not turning at a constant speed here'),
    (21.18 / 63.50, REASON), (1.06, "the drive's speed is not steady"),
])
def test_rotation_fake_periods(monkeypatch, ratio, reason):
    ladder = geo.Ladder(None)
    ladder.ranges = [(0, 1600)]
    monkeypatch.setattr(ladder, '_radius', lambda lba: 26 if lba == 0 else 56)
    tp = ladder.tp
    monkeypatch.setattr(tp, '_measure', lambda *_: SimpleNamespace(t_end_ns=1))
    monkeypatch.setattr(tp, '_usable', lambda _: True)
    fits = iter([SimpleNamespace(period_s=p, coherence=1) for p in (.06350, .06350 * ratio)])
    monkeypatch.setattr(geo.analysis, 'estimate_period', lambda _: next(fits))
    if reason:
        with pytest.raises(RuntimeError) as error:
            ladder.check_rotation()
        assert str(error.value).startswith(reason)
        if ratio == 56 / 26:
            assert str(error.value) == ("the drive is not turning at a constant speed here (63.50 ms a turn at "
                                       "26 mm, 136.77 ms at 56 mm), and geo needs it to")
    else:
        ladder.check_rotation()
    assert tp.summary['rotation_check']['ratio'] == pytest.approx(ratio)
    assert not ladder.targets


def test_clv_whole_turn_ambiguity_unchanged():
    assert geo.looks_clv(2.1, 2.1)
    assert not geo.looks_clv(2, 2)


@pytest.mark.parametrize('media,audio,last', [('dvd', False, 2251919), ('cd', False, 359999), ('cd', True, 359999)])
def test_avoid_bands_use_geo_radius_model(media, audio, last):
    bands = [(41.2, 45.2), (44, 46), (0, 5), (80, 90)]
    text = calibrate._geo_ranges(media, dict(last_lba=last, first_track_audio=audio), bands)
    ranges = [tuple(map(int, part.split('-'))) for part in text.split(',')]
    model = geo.Ladder(None, media=media)
    model.audio = audio
    for a, b in ranges:
        assert a % model.block == b % model.block == 0
        assert b - a > 64
        for lba in range(a, b, model.block):
            assert not any(lo <= model._radius(lba) <= hi for lo, hi in bands)
    # Both edges of the excluded area remain available, to within one block.
    assert 0 < 41.2 - model._radius(ranges[0][1] - model.block) < .01
    assert 0 < model._radius(ranges[1][0]) - 46 < .01
    assert all(ranges[i][1] <= ranges[i + 1][0] for i in range(len(ranges) - 1))


def test_avoid_all_and_unknown_length():
    with pytest.raises(calibrate.Stopped, match='leaves no readable'):
        calibrate._geo_ranges('dvd', dict(last_lba=2251919), [(0, 100)])
    with pytest.raises(calibrate.Stopped, match='length is unknown'):
        calibrate._geo_ranges('dvd', {}, [(41, 45)])


@pytest.mark.parametrize('band', ['45-41', '41-41', '-1-2', 'nan-45', '41-inf', 'a-b', '1-2-3'])
def test_invalid_avoid_band(band):
    with pytest.raises(SystemExit):
        arguments('--avoid-mm', band)


@pytest.mark.parametrize('speed', [None, '3324', '4x', 'keep'])
def test_calibrate_children_and_stop_reason(monkeypatch, tmp_path, capsys, speed):
    args = arguments(*(['--speed', speed] if speed else []), '--avoid-mm', '41.2-45.2',
                     '--avoid-mm', '44-46', '--out', str(tmp_path))
    assert arguments().speed == 4 and type(arguments().speed).__name__ == '_SpeedX'
    # main normally converts a multiple to its media's kB/s before run().
    if speed == '4x':
        args.speed = 5540
    timing = tmp_path / 'timing'
    timing.mkdir()
    (timing / 'summary.json').write_text(json.dumps({'setup': {'last_lba': 2251919}}))
    calls, events = [], []

    def child(argv, **kwargs):
        cmd = argv[argv.index('discprobe') + 1:]
        calls.append(cmd)
        return SimpleNamespace(poll=lambda: 0 if cmd[0] == 'timing' else 1,
                               returncode=0 if cmd[0] == 'timing' else 1,
                               stdout=io.StringIO('' if cmd[0] == 'timing' else 'stopped: ' + REASON + '\n'))

    monkeypatch.setattr(calibrate.subprocess, 'Popen', child)
    monkeypatch.setattr(calibrate.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=json.dumps({
        'disc': dict(present=True, blank=False, media='dvd', sectors=2251920)})))
    monkeypatch.setattr(calibrate.guide, 'scan', lambda _: [SimpleNamespace(
        kind='timing', when=datetime.datetime.now(), simulated=False, path=str(timing))])
    monkeypatch.setattr(calibrate.guide, 'result_verdict', lambda *a: 'good')
    monkeypatch.setattr(calibrate.ui, 'event', lambda kind, **kw: events.append(dict(type=kind, **kw)))
    monkeypatch.setattr(calibrate.ui, 'say', lambda *a: None)
    with pytest.raises(SystemExit) as error:
        calibrate.run(args)
    assert str(error.value) == REASON
    assert next(e for e in events if e['type'] == 'calibrated')['reason'] == REASON
    # main turns a given 4x into the media's kB/s; the default reaches run() as 4x and is passed on as a multiple
    expected = {'keep': 'keep', '3324': '3324', '4x': '5540', None: '4x'}[speed]
    assert [c[c.index('--speed') + 1] for c in calls] == [expected, expected]
    assert '--ranges' not in calls[0]
    assert calls[1][calls[1].index('--ranges') + 1] == calibrate._geo_ranges(
        'dvd', dict(last_lba=2251919), args.avoid_mm)
    assert f'Read speed for timing: {expected}' in capsys.readouterr().out


def test_web_forwarding(tmp_path):
    argv, _ = webui.command(dict(action='calibrate', drive='SIM', args=dict(
        speed='4x', avoid_mm=['41.2-45.2', '49-53'])), tmp_path, [dict(id='SIM')])
    assert argv[-6:] == ['--speed', '4x', '--avoid-mm', '41.2-45.2', '--avoid-mm', '49-53']
    for bad in ('41-45', [None], ['nan-45'], ['45-41'], ['--help']):
        with pytest.raises(webui.APIError, match='invalid avoid_mm'):
            webui.command(dict(action='calibrate', drive='SIM', args=dict(avoid_mm=bad)),
                          tmp_path, [dict(id='SIM')])


def test_page_calibrate_arguments():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for page argument regressions')
    subprocess.run([node, str(Path(__file__).with_suffix('.mjs'))], check=True, timeout=20)


def test_simulated_calibrate_avoids_bad_band(tmp_path):
    out = tmp_path / 'results'
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, '-m', 'discprobe', 'calibrate', '--drive', 'SIM',
                          '--sim', 'cav', '--avoid-mm', '41.2-45.2', '--out', str(out)],
                         cwd=root, env=dict(os.environ, PYTHONPATH=str(root)),
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'Read speed for timing: 4x' in run.stdout
    assert 'Read speed for geo: 4x' in run.stdout
    import csv
    model = geo.Ladder(None)
    folder = next(out.glob('geo-*'))
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    assert not summary.get('stopped')
    assert not 41.2 <= model._radius(summary['fit']['reference_lba']) <= 45.2
    with (folder / 'targets.csv').open(encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 22
    assert all(not 41.2 <= model._radius(int(row['lba'])) <= 45.2 for row in rows)
