"""Full-area numerical gates and the actual CLI/page image geometry path."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from discprobe import presets, imagedisc, webui_catalog
from discprobe import __main__ as cli
from test_presets import DATA, specimen


@pytest.mark.parametrize('file', ['18-community-3.json', '27-pitch-linear.json', '28-pitch-cubic.json'])
def test_correction_full_area_sign_range_and_original_export(file, tmp_path):
    from discprobe.dispitch import sector_map
    from discprobe.disexport import target_angle
    result = presets.import_file((DATA/file).read_text(encoding='utf8'), file, tmp_path)
    row = result['entries'][0]
    assert row['image_compatible'] and row['fit']['calibrated'] is False
    saved = Path(result['written'][0]['path'])
    document = json.loads(saved.read_text(encoding='utf8'))
    correction = imagedisc.load_correction(presets.linked_correction(saved, document))
    p, fit = row['preset'], row['fit']
    bit, bits = presets.density(row['media'])
    n = np.linspace(0, p.get('sectors', p.get('totalSectors'))*bits, 20001)
    r_dis, theta_dis = sector_map(p, row['media'], bit, bits)
    r_dp = bit*1e-6*np.sqrt(fit['u']**2 + fit['v']*n/np.pi)
    # Same signed angles as _sample, without any modulo or free rotation.
    error = np.max(np.abs(np.degrees(-theta_dis+target_angle(n, fit['u'], fit['v'], bit))-correction(r_dp)))
    assert error <= .01
    assert np.max(np.abs(r_dis-r_dp)) <= .005
    assert document['source']['comparison'] == row['comparison']
    assert correction(r_dp[0]-10) == correction(r_dp[0])
    assert correction(r_dp[-1]+10) == correction(r_dp[-1])
    assert presets.export_file(saved)['preset'] == p


def test_refuse_radius_and_unwrapped_over360_with_numbers(tmp_path):
    p = {**specimen(), 'pitchLinear': .01}
    row = presets.parse(json.dumps(p), media='dvd')['entries'][0]
    assert row['valid'] and not row['image_compatible']
    assert row['comparison']['max_radius_error_mm'] > .005
    assert row['comparison']['max_angle_error_deg'] <= .01  # radius alone refuses
    result = presets.import_file((DATA/'51-unwrapped-over360.json').read_text(encoding='utf8'), 'extreme', tmp_path)
    row = result['entries'][0]
    assert row['valid'] and not row['image_compatible']
    assert row['comparison']['max_angle_error_deg'] > 360
    assert row['comparison']['max_radius_error_mm'] > .005
    saved = Path(result['written'][0]['path'])
    document = json.loads(saved.read_text(encoding='utf8'))
    assert 'correction' not in document
    assert document['source']['comparison'] == row['comparison']
    assert any('archive only' in s for s in row['issues'])
    with pytest.raises(SystemExit):
        cli._geo_fit(SimpleNamespace(geo=str(saved), correction=None), 'dvd')


def test_image_and_page_geometry_use_link_automatically(tmp_path):
    result = presets.import_file((DATA/'27-pitch-linear.json').read_text(encoding='utf8'), 'variable', tmp_path/'presets')
    saved = Path(result['written'][0]['path'])
    groups = webui_catalog.catalogue(tmp_path, tmp_path/'results')
    entry = groups['dvd'][0]
    assert entry['image_compatible'] and entry['imported'] and entry['s'] == 'unknown'
    assert entry['geo'] == str(saved.relative_to(tmp_path))
    # This is the path the page hands to its image job. Run the actual image handler,
    # stopping at the writer so this test never creates a disc-sized file.
    args = SimpleNamespace(geo=str(tmp_path/entry['geo']), media='dvd', correction=None,
        along_track_frames=0, design=None, design_npy=None, picture=None, r_max=56,
        line_mm=.3, cell_um=None, start_lba=0, random_below_mm=0,
        textures=None, dark='A5', light='B9', output=str(tmp_path/'image.iso'))
    with patch.object(imagedisc, 'grid_design', return_value=np.zeros((2, 2), dtype=bool)), \
         patch.object(imagedisc, 'write_iso', side_effect=RuntimeError('writer reached')) as writer:
        with pytest.raises(RuntimeError, match='writer reached'):
            cli.cmd_image(args)
    corr = writer.call_args.kwargs['correction']
    assert isinstance(corr, imagedisc.Correction)
    assert args.correction == str(saved.with_name(saved.stem+'-correction.json'))
    assert np.max(np.abs(corr(np.linspace(24, 58, 100)))) > 100
    assert writer.call_args.kwargs['meta']['correction'] == args.correction
    Path(args.correction).unlink()
    with pytest.raises(SystemExit):
        cli._geo_fit(SimpleNamespace(geo=str(saved), correction=None), 'dvd')
    assert not webui_catalog.catalogue(tmp_path, tmp_path/'results')['dvd'][0]['image_compatible']


def test_cli_json_and_chinese_listing_include_residuals(tmp_path):
    from test_presets import cli as run
    path = DATA/'18-community-3.json'
    result = run('import', path, '--dry-run', '--json')
    assert result.returncode == 0
    c = json.loads(result.stdout)['entries'][0]['comparison']
    assert 0 < c['max_angle_error_deg'] <= .01 and 0 < c['max_radius_error_mm'] <= .005
    result = run('import', path, '--dry-run', '--lang', 'zh')
    assert '近似：角度 ≤' in result.stdout and '半径 ≤' in result.stdout
    assert '从 DIS 导入，换算成 DP 修正（未经 DP 实测）' in result.stdout
    assert 'L 未知' in result.stdout


def test_exact_constant_dvd_arc_primitive_and_lowest_degree():
    from scipy.optimize import brentq
    from discprobe.dispitch import sector_map
    from discprobe.disexport import target_angle
    p = specimen()
    bit, bits = presets.density('dvd')
    ri, ro = p['innerRadiusMm'], p['outerRadiusMm']
    length = p['totalSectors']*bits*bit*1e-6
    # C# DvdTrackGeometry's constant-pitch exact arc primitive.
    def primitive(r, b):
        return (r*np.hypot(r, b)+b*b*np.arcsinh(r/b))/2
    b = brentq(lambda b: (primitive(ro,b)-primitive(ri,b))/b-length, 1e-12, 1,
               xtol=1e-18, rtol=1e-14)
    r, theta = sector_map(p, 'dvd', bit, bits)
    assert np.max(np.abs((primitive(r,b)-primitive(ri,b))/b/length-np.linspace(0,1,20001))) < 1e-10
    assert np.max(np.abs(np.degrees(theta-(r-ri)/b))) < 1e-5
    row = presets.parse((DATA/'18-community-3.json').read_text(encoding='utf8'))['entries'][0]
    p, fit = row['preset'], row['fit']
    bit, bits = presets.density('cd')
    r, theta = sector_map(p, 'cd', bit, bits)
    n = np.linspace(0,p['sectors']*bits,20001)
    r_dp = bit*1e-6*np.sqrt(fit['u']**2+fit['v']*n/np.pi)
    x = (r_dp-40)/15
    phi = np.degrees(target_angle(n,fit['u'],fit['v'],bit)-theta)
    for degree in range(row['comparison']['polynomial_degree']):
        poly = np.polynomial.Chebyshev.fit(x,phi,degree)
        assert np.max(np.abs(phi-poly(x))) > .01
