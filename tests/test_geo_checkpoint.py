"""Exercise the CLI across an uncatchable process termination."""
import csv
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from discprobe import guide, webui_catalog


CLI = [sys.executable, '-X', 'utf8', '-m', 'discprobe']
PARK_AT_RUNG = """
from pathlib import Path
import sys
import time
from discprobe import ui
from discprobe.__main__ import main

ready, rung, *args = sys.argv[1:]
emit = ui.event

def park(name, **fields):
    emit(name, **fields)
    if name == 'geo_point' and fields['rung'] == int(rung):
        Path(ready).touch()
        while True:
            time.sleep(1)

ui.event = park
main(args)
"""


def run_cli(*args):
    result = subprocess.run([*CLI, *map(str, args)], text=True, encoding='utf-8',
                            capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def table(data):
    return list(csv.DictReader(io.StringIO(data.decode('utf-8'), newline='')))


@pytest.mark.parametrize(('media', 'mode', 'rung'), [('dvd', 'cav', 1), ('dvd', 'cav', 8), ('cd', 'cav-audio', 8)])
def test_killed_measurement_keeps_complete_rungs_and_can_resume(tmp_path, media, mode, rung):
    ready = tmp_path / 'parked'
    results = tmp_path / 'results'
    with (tmp_path / 'geo.log').open('wb') as log:
        child = subprocess.Popen([sys.executable, '-c', PARK_AT_RUNG, str(ready), str(rung),
                                  'geo', '--media', media, '--sim', mode, '--seed', '7', '--out', str(results)],
                                 stdout=log, stderr=subprocess.STDOUT)
        try:
            until = time.monotonic() + 30
            while not ready.is_file() and child.poll() is None and time.monotonic() < until:
                time.sleep(.02)
            assert ready.is_file(), (tmp_path / 'geo.log').read_text(encoding='utf-8')
        finally:
            child.kill()  # TerminateProcess on Windows, SIGKILL on POSIX.
            child.wait(timeout=10)

    run, = guide.scan(str(results))
    folder = Path(run.path)
    assert child.returncode != 0 and not (folder / 'summary.json').exists()
    assert run.stopped == 'measurement interrupted'
    assert run.rungs() == rung and not run.reliable()
    assert run.describe() == f'measurement interrupted after {rung} rungs'
    assert webui_catalog.calibration_issue(run, {})['can_resume'] is True
    trace = (folder / 'events.csv').read_bytes()
    target_csv = (folder / 'targets.csv').read_bytes()
    marker = (folder / 'partial.json').read_bytes()
    assert len(trace) == json.loads(marker)['checkpoint']['events_bytes']
    assert trace.endswith(b'\r\n') and target_csv.endswith(b'\r\n')
    assert len(table(target_csv)) == rung
    assert all(None not in row and None not in row.values() for row in table(trace))
    lbas = [r['lba'] for r in table(target_csv)]
    print(f'{media}: killed at rung {rung}: {len(table(trace))} complete read rows')

    run_cli('geo', '--media', media, '--resume', folder, '--out', results)
    finished, = [r for r in guide.scan(str(results)) if not r.stopped]
    resumed = Path(finished.path)
    assert finished.fit['completion_status'] == 'target_reached'
    assert not (resumed / 'partial.json').exists()
    assert [r['lba'] for r in table((resumed / 'targets.csv').read_bytes())][:rung] == lbas
    assert (resumed / 'events.csv').read_bytes().startswith(trace)
    print(f'{media}: resumed from {rung} to {finished.rungs()} rungs')

    if rung == 8:
        output = tmp_path / 'offline'
        run_cli('geo', '--reapply', folder, '--out', output)
        fit = json.loads((output / 'summary.json').read_bytes())['fit']
        assert fit['completion_status'] == 'interrupted'
        assert fit['completion_adjustment']['method'] == 'events_refit'
        assert (output / 'events.csv').read_bytes() == trace
        assert len(table((output / 'targets.csv').read_bytes())) == rung

    if media == 'dvd' and rung == 8:
        # The public catalogue omits simulator runs. Use the same checkpoint
        # with a laboratory drive identity to exercise its public row and guide.
        fixture = tmp_path / 'catalogue' / 'geo-X-20261123-102936'
        fixture.mkdir(parents=True)
        real = json.loads(marker)
        real.pop('simulated')
        real['args']['drive'] = 'X:'
        (fixture / 'partial.json').write_text(json.dumps(real), encoding='utf-8')
        entry, = webui_catalog.catalogue(tmp_path, fixture.parent)['dvd']
        assert entry['s'] == 'incomplete' and entry['calibration_issue']['can_resume'] is True
        plan = guide.workflow(out=str(fixture.parent), drives=['Y:'])
        task = next(t for t in plan.tasks if t.key == 'geo')
        assert task.detail == 'measurement interrupted after 8 rungs'
        assert task.argv == ['geo', '--drive', 'X:', '--resume', str(fixture), '--out', str(fixture.parent)]
        assert plan.commands[0][1] == task.command()
        state = guide.guide_state(out=str(fixture.parent), drives=['X:'])
        step = next(s for s in state['steps'] if s['id'] == 'geo')
        assert step['detail'] == task.detail and step['verdict'] == 'stopped_early'
    assert (folder / 'partial.json').read_bytes() == marker
    assert (folder / 'targets.csv').read_bytes() == target_csv
    assert (folder / 'events.csv').read_bytes() == trace


def test_calibrate_reports_checkpoint_left_by_terminated_geo_child(tmp_path):
    ready = tmp_path / 'parked'
    results = tmp_path / 'results'
    # Calibrate launches a separate copy of the CLI. Pause only that geo
    # process, immediately after the third durable point has been announced.
    (tmp_path / 'sitecustomize.py').write_text("""
import os
from pathlib import Path
import sys
import time

if sys.argv[1:2] == ['geo']:
    from discprobe import ui
    emit = ui.event
    def park(name, **fields):
        emit(name, **fields)
        if name == 'geo_point' and fields['rung'] == 3:
            ready = Path(os.environ['GEO_TEST_READY'])
            ready.write_text(str(os.getpid()), encoding='utf-8')
            while True:
                time.sleep(1)
    ui.event = park
""", encoding='utf-8')
    env = dict(os.environ, GEO_TEST_READY=str(ready),
               PYTHONPATH=os.pathsep.join((str(tmp_path), str(Path(__file__).resolve().parents[1]))))
    with (tmp_path / 'calibrate.log').open('wb') as log:
        parent = subprocess.Popen([*CLI, 'calibrate', '--drive', 'SIM', '--sim', 'cav',
                                   '--out', str(results)], stdout=log, stderr=subprocess.STDOUT, env=env)
        child_id = None
        try:
            until = time.monotonic() + 40
            while parent.poll() is None and time.monotonic() < until:
                if ready.is_file() and (pid := ready.read_text(encoding='utf-8').strip()).isdigit():
                    child_id = int(pid)
                    break
                time.sleep(.02)
            assert child_id is not None, (tmp_path / 'calibrate.log').read_text(encoding='utf-8')
            os.kill(child_id, signal.SIGTERM if os.name == 'nt' else signal.SIGKILL)
            assert parent.wait(timeout=15) != 0
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=10)
    run, = [r for r in guide.scan(str(results)) if r.kind == 'geo']
    outcome = json.loads((Path(run.path) / 'calibration.json').read_bytes())
    assert outcome['geo']['verdict'] == 'stopped_early'
    assert not outcome['ok'] and run.rungs() == 3
    assert run.stopped == 'measurement interrupted'
