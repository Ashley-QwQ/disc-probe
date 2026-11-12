"""Catalogue tests use temporary files only, never a drive."""
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock
from discprobe import webui_catalog as catalog
from discprobe import guide
from discprobe import webui


def write_geo(root, stamp='20261107-101500', **overrides):
    path = Path(root) / 'results' / ('geo-H-' + stamp)
    path.mkdir(parents=True)
    data = dict(fit=dict(media='dvd', u=180000, v=5.5, chi2_per_dof=1,
        measured_span_mm=[25,56], angle_sigma_measured_span_deg=.1),
        identity=dict(disc='TEST <MID>', drive='Fake drive'), setup=dict(last_lba=999))
    data.update(overrides)
    (path / 'summary.json').write_text(json.dumps(data), encoding='utf-8')
    (path / 'targets.csv').write_text('header\n' + 'point\n'*10)
    return path


def test_empty_and_presets():
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
        root=Path(tmp)
        assert catalog.catalogue(root, root/'results') == dict(dvd=[],cd=[],bd=[])
        (root/'presets').mkdir()
        (root/'presets'/'one.json').write_text(json.dumps({'preset':{'id':'p','displayName':'Long <name>', 'totalSectors':100}}))
        (root/'presets'/'broken.json').write_text('{')
        rows=catalog.catalogue(root,root/'results')
        assert rows['dvd'][0]['name'] == 'Long <name>'
        assert rows['dvd'][0]['s'] == 'unknown'
        assert rows['dvd'][0]['left'] is None


def test_results_identity_verdict_and_counter():
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
        root=Path(tmp)
        path=write_geo(root)
        write_geo(root, '20261108-101500', stopped='cancelled')
        write_geo(root, '20261109-101500', simulated=True)
        rows=catalog.catalogue(root,root/'results')
        assert len(rows['dvd']) == 1
        entry=rows['dvd'][0]
        assert entry['s'] == guide.result_verdict(guide.scan(str(root/'results'))[-1]) == 'good'
        assert entry['drive'] == 'Fake drive' and entry['sectors'] == 1000
        assert entry['last'] == '2026-11-07'
        catalog.save_entry(root,root/'results',dict(id=entry['id'],name='My batch',left=13))
        saved=catalog.catalogue(root,root/'results')['dvd'][0]
        assert saved['left'] == 13 and saved['name'] == 'My batch'
        (root/'presets').mkdir()
        (root/'presets'/'export.json').write_text(json.dumps({'preset':{'id':'linked','displayName':'Linked', 'totalSectors':1000}}))
        catalog.save_entry(root,root/'results',dict(id=entry['id'],preset='presets/export.json'))
        linked=catalog.catalogue(root,root/'results')['dvd']
        assert len(linked)==1 and linked[0]['name']=='My batch' and linked[0]['left']==13
        # the core reports the preset by its absolute path: stored relative, still one batch
        catalog.save_entry(root,root/'results',dict(id=entry['id'],preset=str((root/'presets'/'export.json').resolve())))
        assert json.loads((root/'catalogue.json').read_text())[entry['id']]['preset'] == 'presets/export.json'
        assert len(catalog.catalogue(root,root/'results')['dvd']) == 1
        # an absolute path saved by an older page links the preset too
        (root/'catalogue.json').write_text(json.dumps({entry['id']: {'preset': str((root/'presets'/'export.json').resolve())}}))
        assert len(catalog.catalogue(root,root/'results')['dvd']) == 1
        assert (path/'summary.json').exists()
        for bad in [dict(id=entry['id'],left=True),dict(id='missing',name='x'),dict(id=entry['id'],name='')]:
            try: catalog.save_entry(root,root/'results',bad)
            except ValueError: pass
            else: raise AssertionError('bad metadata accepted')


def test_unidentified_results_stay_separate():
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
        root=Path(tmp)
        write_geo(root, identity={})
        write_geo(root,'20261108-101500',identity={})
        rows=catalog.catalogue(root,root/'results')['dvd']
        assert len(rows)==2 and all(x['mid'] is None for x in rows)


def test_info_report_blank_capacity_and_family():
    report={k:{'parsed':v} for k,v in dict(configuration=dict(current_profile=0x11,current_profile_name='DVD-R'),
        track_1=dict(blank=True,track_start=0,free_blocks=1000),
        dvd_prerecorded_0e=dict(manufacturer_id='TEST MID')).items()}
    disc=catalog.disc_report(report)
    assert disc == dict(present=True,media='dvd',kind='DVD-R',mid='TEST MID',blank=True,sectors=1000,closed=None,
                        capacity_sectors=1000,capacity_source='free space of this blank disc',drive_name=None)
    report['track_1']['parsed'].pop('blank')
    report['disc_information']={'parsed':{'disc_status':'empty'}}
    assert catalog.disc_report(report)['blank'] is True
    assert catalog.disc_report({})['present'] is False
    for status, closed in (('complete', True), ('incomplete', False), ('empty', None)):
        report['disc_information']={'parsed':{'disc_status':status}}
        assert catalog.disc_report(report)['closed'] is closed


def test_measurement_preserves_stop_reason(tmp_path):
    path = write_geo(tmp_path, stopped='medium error at LBA 42')
    run = next(r for r in guide.scan(str(tmp_path / 'results')) if Path(r.path) == path)
    assert catalog.measurement(run)['stopped'] == 'medium error at LBA 42'


def test_history_saved_runs_and_explicit_burn_links(tmp_path):
    old = write_geo(tmp_path, '20261107-101500', stopped='read failed')
    new = write_geo(tmp_path, '20261108-101500')
    write_geo(tmp_path, '20261109-101500', identity={'disc': 'OTHER', 'drive': 'Fake drive'})
    write_geo(tmp_path, '20261110-101500', simulated=True)
    iso = tmp_path / 'iso'
    iso.mkdir()
    (iso / 'art.image.json').write_text(json.dumps({'geometry_from': str(new / 'summary.json')}))
    results = [dict(result='completed', verification=dict(status='completed', ok=96, differing=0, unreadable=0, untested=0)),
               dict(result='completed', verification=dict(status='completed', ok=95, differing=1, unreadable=0, untested=0)),
               dict(result='failed'), dict(result='cancelled'), dict(result='completed', verification=dict(status='skipped'))]
    log = iso / 'art.iso.burn.jsonl'
    records = [dict(type='burn_result', time=1794230000+i, log_path=str(log), **r) for i, r in enumerate(results)]
    log.write_text('\n'.join(json.dumps(r) for r in records) + '\n{truncated', encoding='utf-8')
    # A durable web result duplicates one engine record; it is still one burn.
    job = tmp_path / '.webui-jobs/j-one'; job.mkdir(parents=True)
    (job / 'burn.json').write_text(json.dumps(dict(records[0], media='dvd', identity={'disc':'TEST <MID>', 'drive':'Fake drive'})))
    (iso / 'unlinked.iso.burn.jsonl').write_text(json.dumps(dict(records[0], time=1794239999)))
    rows = catalog.catalogue(tmp_path, tmp_path / 'results')['dvd']
    batch = next(r for r in rows if r['mid'] == 'TEST <MID>')
    events = batch['history']
    assert len(events) == 7
    assert [e['state'] for e in events if e['kind'] == 'calibrate'] == ['needs', 'ok']
    assert [e['state'] for e in events if e['kind'] == 'burn'] == ['ok', 'needs', 'needs', 'needs', 'unknown']
    assert all(set(e) == {'kind', 'state', 'when', 'label'} for e in events)
    assert all(e['kind'] == 'calibrate' for e in next(r for r in rows if r['mid'] == 'OTHER')['history'])


def test_history_unidentified_runs_stay_separate(tmp_path):
    write_geo(tmp_path, identity={})
    write_geo(tmp_path, '20261108-101500', identity={})
    rows = catalog.catalogue(tmp_path, tmp_path / 'results')['dvd']
    assert len(rows) == 2 and all(len(r['history']) == 1 for r in rows)


def test_web_burn_history_survives_server_lifetime(tmp_path):
    write_geo(tmp_path)
    (tmp_path / 'iso').mkdir()
    (tmp_path / 'iso/image.iso').write_bytes(bytes(2048))
    event = dict(type='burn_result', result='completed', time=1794230000,
                 verification=dict(status='completed', ok=96, differing=0, unreadable=0, untested=0))
    def runner(argv, **kw):
        Path(kw['env']['DISCPROBE_EVENTS']).write_text(json.dumps(event) + '\n')
        return Mock(wait=Mock(return_value=0), close=Mock())
    backend = webui.Backend(tmp_path, runner=runner,
        drive_provider=lambda:[dict(id='H:', disc=dict(blank=True, mid='TEST <MID>', drive_name='Fake drive'))])
    try:
        ident = backend.start(dict(action='burn', media='dvd', drive='H:', args=dict(iso='iso/image.iso'),
                                   burn_token=backend.burn_token()['token']))['job']
        assert backend.jobs[ident].finished.wait(3)
    finally:
        backend.close()
    saved = json.loads(next((tmp_path / '.webui-jobs').glob('*/burn.json')).read_text())
    assert saved['time'] == event['time'] and saved['identity']['disc'] == 'TEST <MID>'
    # Reading catalogue data needs neither this Backend instance nor any drive access.
    events = catalog.catalogue(tmp_path, tmp_path / 'results')['dvd'][0]['history']
    assert [e['kind'] for e in events] == ['calibrate', 'burn']
    assert events[-1]['state'] == 'ok'
