"""Catalogue tests use temporary files only, never a drive."""
import json
from pathlib import Path
import tempfile
from discprobe import webui_catalog as catalog
from discprobe import guide


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
    assert disc == dict(present=True,media='dvd',kind='DVD-R',mid='TEST MID',blank=True,sectors=1000,
                        capacity_sectors=1000,capacity_source='free space of this blank disc')
    report['track_1']['parsed'].pop('blank')
    report['disc_information']={'parsed':{'disc_status':'empty'}}
    assert catalog.disc_report(report)['blank'] is True
    assert catalog.disc_report({})['present'] is False


def test_measurement_preserves_stop_reason(tmp_path):
    path = write_geo(tmp_path, stopped='medium error at LBA 42')
    run = next(r for r in guide.scan(str(tmp_path / 'results')) if Path(r.path) == path)
    assert catalog.measurement(run)['stopped'] == 'medium error at LBA 42'
