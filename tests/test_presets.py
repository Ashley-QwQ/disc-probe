"""Drive-free interchange tests. All write targets and install backups are temporary."""
import contextlib
import http.client
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from discprobe import disexport, disinstall, presetio_api, presets, webui

DATA = Path(__file__).parent / 'data' / 'dis-presets'
FIXTURES = sorted(DATA.glob('*.json'))
REFUSED = {'45-bad-json.json', '46-wrong-type.json', '47-negative-radius.json',
           '48-bad-pitch.json', '49-bd-odd.json', '50-future-schema.json',
           '16-community-1.json', '17-community-2.json', '19-community-4.json', '20-community-5.json'}


@pytest.mark.parametrize('path', FIXTURES, ids=lambda p: p.name)
def test_every_mock_and_exact_field_round_trip(path, tmp_path):
    text = path.read_text(encoding='utf-8')
    try:
        preview = presets.import_file(text, path.name, tmp_path / 'preview', dry_run=True)
    except ValueError as exc:
        assert path.name in REFUSED and str(exc)
        return
    assert not (tmp_path / 'preview').exists()
    valid = [row for row in preview['entries'] if row['valid']]
    assert bool(valid) == (path.name not in REFUSED)
    if not valid:
        assert all(row['issues'] for row in preview['entries'])
    # Each item uses an isolated folder, so duplicate ids can both be round-tripped.
    for row in valid:
        report = presets.import_file(text, path.name, tmp_path / str(row['index']), selected=[row['index']])
        saved = Path(report['written'][0]['path'])
        result = presets.export_file(saved, output=tmp_path / f'export-{row["index"]}.json')
        assert result['preset'] == row['preset']
        assert json.loads((tmp_path / f'export-{row["index"]}.json').read_text(encoding='utf-8')) == row['preset']
        document = json.loads(saved.read_text(encoding='utf-8'))
        assert document['source']['schema'] == preview['schema']
        assert document['source']['origin'] == 'imported from DIS'
        assert document['source']['preset_id'] == row['preset']['id']
        assert document['fit']['calibrated'] is False


def specimen(media='dvd'):
    path = next(p for p in FIXTURES if f'builtin-{media}-0.' in p.name)
    return presets.parse(path.read_text(encoding='utf-8'))['entries'][0]['preset']


def test_fixture_count_and_documented_expectations():
    assert len(FIXTURES) == 51
    readme = (DATA / 'README.md').read_text(encoding='utf-8')
    assert all(path.name in readme for path in FIXTURES)
    assert all(f'| {name} | refuse |' in readme for name in REFUSED)


@pytest.mark.parametrize('media', ['cd', 'dvd', 'bd'])
def test_dp_dis_dp_full_area_angle_tolerance(media, tmp_path):
    """Compare continuous DP geometry on 20,001 sector positions over the full data area."""
    from discprobe import bdexport
    p = specimen(media)
    fit, _ = presets.geometry(p, media)
    total = p.get('sectors', p.get('totalSectors'))
    bit, bits = presets.density(media)
    if media == 'bd':
        dp = bdexport.preset({}, total, 'roundtrip', 'roundtrip', 'test',
                            inner_mm=p['innerRadiusMm'], pitch_um=fit['pitch_um_at_bit'])
        dis = bdexport.catalog_entry(dp)
    else:
        converted = disexport.fit_preset(fit['u'], fit['v'], bit, total,
                                        p['innerRadiusMm'], p['outerRadiusMm'], sector_bits=bits)
        dis = disexport.preset_json(converted, total, bit, 'roundtrip', 'roundtrip', 'test', media)
    back = presets.parse(json.dumps(dis), media=media)['entries'][0]
    assert back['valid']
    map_ = disexport.dis_angle_map(dis['innerRadiusMm'], dis['outerRadiusMm'],
                                  *(dis.get(k, 0) for k in presets.PITCH), total, bit, bits)
    n = np.linspace(0, total * bits, 20001)
    delta = np.degrees(np.interp(n, map_[0], map_[1]) - disexport.target_angle(n, fit['u'], fit['v'], bit))
    delta -= delta.mean()
    error = float(np.max(np.abs(delta)))
    # BD's smaller pitch amplifies dis_angle_map's fixed 40,001-radius interpolation floor.
    assert error < .003, (media, error)
    assert back['comparison']['max_angle_error_deg'] < .003
    returned = back['fit']
    roundtrip = np.degrees(disexport.target_angle(n, returned['u'], returned['v'], bit)
                           - disexport.target_angle(n, fit['u'], fit['v'], bit))
    roundtrip -= roundtrip.mean()
    assert np.max(np.abs(roundtrip)) < .003


def test_unknowns_nominal_pitch_and_l_are_not_invented(tmp_path):
    p = specimen('cd')
    row = presets.parse(json.dumps(p))['entries'][0]
    assert row['status'] == 'nominal'
    assert 'L unknown' in ' '.join(row['issues'])
    varying = presets.parse(json.dumps({**p, 'pitchLinear': .001}))['entries'][0]
    assert varying['valid'] and varying['image_compatible']
    assert varying['comparison']['max_angle_error_deg'] <= .01
    assert varying['comparison']['baseline_max_angle_error_deg'] > 1
    future = {**p, 'futureGeometry': {'coefficient': 2}}
    imported = presets.import_file(json.dumps(future), 'future.json', tmp_path)
    path = imported['written'][0]['path']
    assert presets.export_file(path)['preset'] == future
    with pytest.raises(ValueError, match='unknown fields'):
        presets.export_file(path, install=True, dis_presets=tmp_path / 'dis.json')
    assert not (tmp_path / 'dis.json').exists()


@pytest.mark.parametrize('change,reason', [
    ({'totalSectors': True}, 'positive integer'), ({'totalSectors': 2**32}, 'positive integer'),
    ({'usableSectors': 17}, 'multiple of 16'), ({'outerRadiusMm': 1}, 'radii'),
    ({'pitchLinear': float('inf')}, 'pitch'), ({'pitchLinear': -4, 'pitchQuadratic': 4}, 'pitch'),
    ({'displayNameResourceKey': ''}, 'nonblank'), ({'id': '__manual__'}, 'reserved'),
])
def test_refused_values(change, reason):
    p = {**specimen(), **change}
    with pytest.raises(ValueError, match=reason):
        presets.validate(p, 'dvd')


def test_comments_bom_and_types():
    text = json.dumps(specimen())
    row = presets.parse('\ufeff/*DIS*/' + text[:-1] + ',}')['entries'][0]
    assert row['valid']
    for text in ['[]', 'null', '{"cdPresets":{}}', '{"schemaVersion":4,"cdPresets":[],"dvdPresets":[]}']:
        with pytest.raises(ValueError): presets.parse(text)


def test_duplicate_ids_disabled_selection_and_opaque_names(tmp_path):
    p = {**specimen(), 'id': '../../CON:💿'}
    text = json.dumps({'schemaVersion': 4, 'cdPresets': [], 'dvdPresets': [p, {**p, 'outerRadiusMm': 57}], 'bluRayPresets': []})
    report = presets.import_file(text, 'duplicates.json', tmp_path)
    assert len(report['written']) == 1 and len(report['duplicates']) == 1
    path = Path(report['written'][0]['path'])
    original = path.read_bytes()
    again = presets.import_file(text, 'duplicates.json', tmp_path)
    assert not again['written'] and len(again['duplicates']) == 2
    assert path.read_bytes() == original and path.parent == tmp_path
    with pytest.raises(ValueError): presets.import_file(text, 'x', tmp_path, selected=[-1])
    with pytest.raises(ValueError): presets.import_file(text, 'x', tmp_path, selected=[0, 0])
    disabled = dict(schemaVersion=4, cdPresets=[], dvdPresets=[p], bluRayPresets=[], disabledDvdPresetIds=[p['id']])
    assert not presets.import_file(json.dumps(disabled), 'x', tmp_path / 'disabled')['written']


def cli(*args, cwd=None):
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    return subprocess.run([sys.executable, '-B', '-m', 'discprobe', 'presets', *map(str, args)],
                          cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8')


@pytest.mark.parametrize('media', ['cd', 'dvd', 'bd'])
def test_cli_dryrun_json_duplicates_and_install_backup(media, tmp_path):
    source = tmp_path / 'source.json'; source.write_text(json.dumps(specimen(media)), encoding='utf-8')
    folder = tmp_path / 'presets'
    result = cli('import', source, '--media', media, '--directory', folder, '--dry-run', '--json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['entries'][0]['valid'] and not folder.exists()
    result = cli('import', source, '--media', media, '--directory', folder, '--json')
    assert result.returncode == 0, result.stderr
    saved = json.loads(result.stdout)['written'][0]['path']
    again = cli('import', source, '--media', media, '--directory', folder, '--json')
    assert len(json.loads(again.stdout)['duplicates']) == 1
    target = tmp_path / 'DiscImageStudio' / 'disc-presets.json'
    target.parent.mkdir()
    target.write_text(json.dumps(dict(schemaVersion=4, cdPresets=[], dvdPresets=[], bluRayPresets=[])), encoding='utf-8')
    before = target.read_bytes()
    result = cli('export', saved, '--install', '--dis-presets', target, '--json')
    assert result.returncode == 0, result.stderr + result.stdout
    installed = json.loads(result.stdout)['installation']
    assert Path(installed['backup']).read_bytes() == before
    key = disinstall.FAMILIES[media][0]
    assert json.loads(target.read_text(encoding='utf-8'))[key][0] == specimen(media)
    unchanged = target.read_bytes()
    result = cli('export', saved, '--install', '--dis-presets', target, '--json')
    assert json.loads(result.stdout)['installation']['action'] == 'unchanged'
    assert target.read_bytes() == unchanged
    doc = json.loads(Path(saved).read_text(encoding='utf-8')); doc['preset']['outerRadiusMm'] -= .001
    Path(saved).write_text(json.dumps(doc), encoding='utf-8')
    refused = cli('export', saved, '--install', '--dis-presets', target, '--json')
    assert refused.returncode == 1 and 'already' in json.loads(refused.stdout)['error']
    replaced = cli('export', saved, '--install', '--dis-presets', target, '--replace', '--json')
    assert json.loads(replaced.stdout)['installation']['action'] == 'replaced'
    assert len(list(target.parent.glob('*.bak'))) == 2


def test_cli_chinese_and_refusals(tmp_path):
    p = tmp_path / 'source.json'; p.write_text(json.dumps(specimen('cd')), encoding='utf-8')
    result = cli('import', p, '--dry-run', '--lang', 'zh')
    assert result.returncode == 0 and 'L 未知' in result.stdout and '标称值' in result.stdout
    p.write_text('{', encoding='utf-8')
    result = cli('import', p, '--dry-run', '--json')
    assert result.returncode == 1 and 'invalid JSON' in json.loads(result.stdout)['error']
    p.write_text(json.dumps({**specimen(), 'innerRadiusMm': 'wrong'}), encoding='utf-8')
    result = cli('import', p, '--directory', tmp_path / 'refused', '--json')
    assert result.returncode == 1 and not json.loads(result.stdout)['entries'][0]['valid']
    assert not (tmp_path / 'refused').exists()


def test_api_parity_paths_and_isolated_http(tmp_path):
    lock = threading.RLock()
    backend = SimpleNamespace(root=tmp_path, lock=lock, close=lambda: None)
    with webui.Server(backend, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            connection.request('GET', '/api/presets'); response = connection.getresponse()
            assert response.status == 200 and json.loads(response.read()) == {'version': 1, 'presets': []}
            payload = dict(operation='preview', filename='test.json', text=json.dumps(specimen('cd')))
            connection.request('POST', '/api/presets', json.dumps(payload), {'Content-Type': 'application/json'})
            response = connection.getresponse(); preview = json.loads(response.read())
            assert response.status == 200 and not (tmp_path / 'presets').exists()
            assert 'L 未知' in ' '.join(preview['entries'][0]['issues_zh'])
            payload.update(operation='import', selected=[0])
            connection.request('POST', '/api/presets', json.dumps(payload), {'Content-Type': 'application/json'})
            response = connection.getresponse(); result = json.loads(response.read())
            assert response.status == 200 and len(result['written']) == 1
            listed = presetio_api.listing(tmp_path)['presets'][0]
            exported = presetio_api.handle(tmp_path, dict(operation='export', path=listed['path']))
            assert exported['preset'] == specimen('cd')
            connection.request('POST', '/api/presets', json.dumps(dict(operation='export', path='../outside.json')),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse(); assert response.status == 400; response.read()
            connection.request('POST', '/api/presets', '{}', {'Content-Type': 'text/plain'})
            response = connection.getresponse(); assert response.status == 415; response.read()
            connection.close()
        finally:
            server.shutdown(); thread.join(5)
    assert not thread.is_alive()


def test_source_output_collision_and_existing_file(tmp_path):
    p = tmp_path / 'dp.json'
    presets.import_file(json.dumps(specimen()), 'x', tmp_path / 'presets')
    source = next((tmp_path / 'presets').glob('*.json'))
    with pytest.raises(ValueError, match='source'):
        presets.export_file(source, output=source)
    p.write_text('protected', encoding='utf-8')
    with pytest.raises(FileExistsError): presets.export_file(source, output=p)
    assert p.read_text(encoding='utf-8') == 'protected'


def test_geo_export_reuses_corrected_builder_and_quality_gates(tmp_path):
    bit = 133.3
    geo = tmp_path / 'summary.json'
    fit = dict(media='dvd', u=24/(bit*1e-6), v=.00074/(bit*1e-6), bit_nm_assumed=bit,
               measured_span_mm=[25, 56], chi2_per_dof=1, angle_sigma_measured_span_deg=.1)
    geo.write_text(json.dumps(dict(fit=fit)), encoding='utf-8')
    correction = tmp_path / 'correction.json'
    correction.write_text(json.dumps(dict(poly_in_x=[.02, 0], radius_valid_mm=[24, 58])), encoding='utf-8')
    result = presets.build_export(geo, sectors=2295104, correction=str(correction))
    direct = disexport.export(str(geo), 2295104, str(correction), None, 25, 56, 'discprobe-import', 'disc-probe')
    assert result['preset'] == direct['preset']
    assert result['source']['correction'] == 'correction.json'
    assert 'grid-scan angle correction' in result['preset']['description']
    geo.write_text(json.dumps(dict(fit=fit, simulated=True)), encoding='utf-8')
    with pytest.raises(ValueError, match='simulated'):
        presets.export_file(geo, sectors=2295104, install=True, dis_presets=tmp_path / 'DIS.json')
    assert not (tmp_path / 'DIS.json').exists()
    geo.write_text(json.dumps(dict(fit=fit, stopped='test stop')), encoding='utf-8')
    with pytest.raises(ValueError, match='stopped'):
        presets.build_export(geo, sectors=2295104)


def test_ambiguous_standalone_media_requires_choice():
    p = {k:v for k,v in specimen('bd').items() if k != 'invertMapping'}
    with pytest.raises(ValueError, match='ambiguous'):
        presets.parse(json.dumps(p))
    assert presets.parse(json.dumps(p), media='bd')['entries'][0]['media'] == 'bd'


def test_cli_json_works_in_ascii_windows_pipes(tmp_path):
    path = tmp_path / 'emoji.json'
    path.write_text(json.dumps({**specimen(), 'displayName': '中文 💿'}), encoding='utf-8')
    env = {**os.environ, 'PYTHONIOENCODING': 'ascii', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-m', 'discprobe', 'presets', 'import', str(path), '--dry-run', '--json'],
                            env=env, capture_output=True, text=True, encoding='ascii')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['entries'][0]['preset']['displayName'] == '中文 💿'


@pytest.mark.parametrize('source', ['legacy provenance text', {'media': 'unknown'}, None])
def test_catalogue_media_hint_is_optional_and_imported_bd_is_correct(tmp_path, source):
    from discprobe import webui_catalog
    folder = tmp_path / 'presets'; folder.mkdir()
    (folder / 'dp.json').write_text(json.dumps(dict(preset=specimen(), source=source)), encoding='utf-8')
    report = presets.import_file(json.dumps(specimen('bd')), 'bd.json', folder, media='bd')
    groups = webui_catalog.catalogue(tmp_path, tmp_path / 'results')
    assert len(groups['dvd']) == 1 and len(groups['bd']) == 1
