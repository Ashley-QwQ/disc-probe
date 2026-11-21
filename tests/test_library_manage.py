import json
import os
from argparse import Namespace
from pathlib import Path
import subprocess
import sys

import pytest

from discprobe import __main__ as cli, geo as core_geo, library, webui, webui_catalog, works
from tests.test_webui_catalog import write_geo


def rows(root):
    return webui_catalog.catalogue(root, root / 'results')['dvd']


def test_legacy_gap_capacity_and_save_are_separate(tmp_path):
    root = tmp_path
    presets = root / 'presets'
    presets.mkdir()
    (presets / 'catalogue.json').write_text('{"RITEKF1":{"media":"dvd","capacity_sectors":2295104}}')
    geo = write_geo(root, setup={'last_lba': 2251919}, identity={'disc': 'RITEKF1', 'drive': 'GH70N'},
                    fit=dict(media='dvd', u=180518.44, v=5.59, c_deg=0, period_ms=20, reference_lba=1024,
                             measured_span_mm=[24.63, 57.26], angle_sigma_measured_span_deg=.11,
                             coverage={'measured_intervals_mm': [[24.63, 36.88], [40.43, 47.13], [49.57, 57.26]]}))
    entry, = rows(root)
    assert entry['s'] == 'incomplete' and entry['drive_id'] == 'H:'
    assert (entry['capacity_sectors'], entry['sectors']) == (2295104, 2251920)
    assert entry['left'] is None and entry['history'][0]['state'] == 'needs'
    assert entry['calibration_issue']['missing_mm'] == [[36.88, 40.43], [47.13, 49.57]]
    output = 'presets/calibration-1795148366899.json'
    with pytest.raises(webui.APIError, match='did not pass'):
        webui.command(dict(action='disexport', args=dict(geo=str(geo), output=output, sectors=2295104)), root, [])
    assert not (root / output).exists()
    (root / output).write_text('{}')
    with pytest.raises(ValueError, match='did not pass'):
        webui_catalog.save_entry(root, root / 'results', dict(id=entry['id'], preset=output))


def test_latest_refusal_visible_with_a_previous_usable_fit(tmp_path):
    original = write_geo(tmp_path)
    refused = write_geo(tmp_path, stamp='20261108-101500')
    (refused / 'calibration.json').write_bytes(works.encoded(dict(ok=False, reason='preset conversion failed')))
    entry, = rows(tmp_path)
    assert entry['s'] == 'good' and entry['geo'] == original.relative_to(tmp_path).as_posix()
    assert entry['calibration_issue']['previous_usable']
    assert entry['calibration_issue']['reason'] == 'preset conversion failed'
    assert [event['state'] for event in entry['history']] == ['ok', 'needs']


@pytest.mark.parametrize('temporary_limits', [False, True])
def test_resume_refreshes_only_ranges_excluded_by_calibration(tmp_path, monkeypatch, temporary_limits):
    source = write_geo(tmp_path)
    if temporary_limits:
        (source / 'calibration.json').write_bytes(works.encoded(dict(ok=False, avoid_mm=[[36, 40]])))
    bounds = '20000-700000,1000000-2100000'
    saved = dict(args=dict(ranges=bounds, speed=5540), fit=dict(reference_lba=34000))
    monkeypatch.setattr(core_geo, 'resume_source', lambda *args: (saved, []))
    args = Namespace(resume=str(source), media='dvd', sim='cav', read_offset_bytes=0, sectors=16,
                     rings_layout=None)

    def before_open(chosen):
        assert chosen.ranges == (None if temporary_limits else bounds)
        assert chosen.speed == 5540 and chosen.ref_lba == 34000
        assert saved.get('refresh_excluded_ranges', False) is temporary_limits
        raise RuntimeError('checked before opening')

    monkeypatch.setattr(cli, '_open', before_open)
    with pytest.raises(RuntimeError, match='checked before opening'):
        cli.cmd_geo(args)


@pytest.mark.parametrize('cascade', [False, True])
def test_batch_delete_and_restore_all_owned_records(tmp_path, monkeypatch, cascade):
    root = tmp_path
    monkeypatch.setenv('DISCPROBE_HOME', str(root))
    a = write_geo(root)
    b = write_geo(root, stamp='20261108-101500', stopped='cancelled')
    timing = root / 'results/timing-H-20261107-101400'
    timing.mkdir()
    (timing / 'summary.json').write_text('{}')
    preset = root / 'presets/calibration-100.json'
    preset.parent.mkdir()
    preset.write_text('{"preset":{"id":"p","displayName":"Test"}}')
    (a / 'calibration.json').write_bytes(works.encoded(dict(ok=True, timing={'path': str(timing)}, preset=str(preset))))
    entry, = rows(root)
    webui_catalog.save_entry(root, root / 'results', dict(id=entry['id'], name='Test batch', left=3))
    manager = library.Library(root, root / 'results')
    work = manager.works.new('Picture')
    manager.works.patch(work['id'], dict(geo_run=(b / 'summary.json').relative_to(root).as_posix()))
    before = manager.preview(entry['id'])
    assert len(before['files']) == 4 and before['works'] == [dict(id=work['id'], name='Picture')]
    with pytest.raises(works.WorkError, match='choose whether'):
        manager.delete(entry['id'])
    with pytest.raises(works.WorkError, match='changed'):
        manager.delete(entry['id'], revision='stale', with_works=cascade)
    removed = manager.delete(entry['id'], revision=before['revision'], with_works=cascade)
    assert rows(root) == []
    assert not any(path.exists() for path in (a, b, timing, preset))
    assert bool(manager.works.list()) != cascade
    assert manager.trashed()[0]['trash_id'] == removed['trash_id']
    manager.restore(removed['trash_id'])
    assert all(path.exists() for path in (a, b, timing, preset))
    assert manager.works.show(work['id'])['geo_run'].endswith('/summary.json')
    assert rows(root)[0]['left'] == 3 and manager.trashed() == []


def test_shared_preset_restore_conflict_and_explicit_permanent(tmp_path, monkeypatch):
    monkeypatch.setenv('DISCPROBE_HOME', str(tmp_path))
    folder = tmp_path / 'presets'
    folder.mkdir()
    source = folder / 'combined.json'
    source.write_bytes(works.encoded({'presets': [{'id': ident, 'displayName': ident} for ident in ('a', 'b')]}))
    manager = library.Library(tmp_path, tmp_path / 'results')
    removed = manager.delete('preset:a')
    assert source.exists() and [r['id'] for r in rows(tmp_path)] == ['preset:b']
    manager.restore(removed['trash_id'])
    assert len(rows(tmp_path)) == 2
    source.write_text('{"preset":{"id":"a","displayName":"a"}}')
    removed = manager.delete('preset:a')
    source.write_text('replacement')
    with pytest.raises(works.WorkError, match='occupied'):
        manager.restore(removed['trash_id'])
    assert source.read_text() == 'replacement'
    source.unlink()
    manager.restore(removed['trash_id'])
    assert manager.delete('preset:a', permanent=True)['trash_id'] is None
    assert not source.exists() and manager.trashed() == []


def test_interrupted_multi_file_move_completes_before_catalogue_read(tmp_path, monkeypatch):
    monkeypatch.setenv('DISCPROBE_HOME', str(tmp_path))
    run = write_geo(tmp_path)
    second = write_geo(tmp_path, stamp='20261108-101500')
    manager = library.Library(tmp_path, tmp_path / 'results')
    entry, = rows(tmp_path)
    rename = library.os.rename

    def power_loss(source, destination):
        if source == second:
            raise KeyboardInterrupt
        return rename(source, destination)

    with monkeypatch.context() as m:
        m.setattr(library.os, 'rename', power_loss)
        with pytest.raises(KeyboardInterrupt):
            manager.delete(entry['id'])
    assert not run.exists() and second.exists()
    assert manager.rows()['dvd'] == []
    trash, = manager.trashed()
    manager.restore(trash['trash_id'])
    assert run.is_dir() and second.is_dir()


def test_cli_json_batch_and_work_lifecycle(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, DISCPROBE_HOME=str(tmp_path), PYTHONPATH=str(repo))

    def cli(*args):
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'discprobe', '--lang', 'en', *args, '--json'],
                                cwd=tmp_path, env=env, capture_output=True, check=True)
        return json.loads(result.stdout)

    write_geo(tmp_path)
    ident = cli('library', 'list')['dvd'][0]['id']
    undo = cli('library', 'delete', ident)['trash_id']
    assert cli('library', 'restore', undo)['restored']
    work = cli('works', 'new', 'A work')['id']
    assert cli('works', 'delete', work)['deleted_at']
    assert cli('works', 'list', '--trash')[0]['id'] == work
    assert cli('works', 'restore', work)['id'] == work
    assert cli('works', 'delete', work, '--permanent')['permanent']
    assert cli('works', 'list', '--trash') == []
