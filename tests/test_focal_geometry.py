"""Physical framing, immutable recorded cells and offline asset consistency."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from discprobe import focal as F, simulate

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def test_pinhole_video_grid_framing_is_unchanged():
    # Projection into 4K video of the original table-plane thirds; lens and paper stay level.
    old_half_grid=F.LEGACY_TABLE_HEIGHT_MM*3840/(6*F.LEGACY_VIDEO_FOCAL_PX)
    assert old_half_grid*F.VIDEO_FOCAL_PX/F.TABLE_HEIGHT_MM == pytest.approx(640)
    assert F.DESIGN_Z_MM+1.2+.1 == pytest.approx(F.TABLE_HEIGHT_MM)
    assert 221 < F.TABLE_HEIGHT_MM < 224
    assert F.VIDEO_FOCAL_PX == 3355


def test_delta_agrees_with_existing_unit_ray_model():
    x=np.array([0.,40.,-40.,19.,-35.])
    y=np.array([45.,0.,0.,-35.,12.])
    np.testing.assert_allclose(F.along_track(x,y),simulate.along_track(x,y,F.CAMERA,F.FLASH),atol=1e-15)
    assert F.along_track(0.,40.) == 0
    np.testing.assert_allclose(F.along_track(x,y),F.along_track(-x,y),atol=1e-15)


def test_generated_geometry_metadata_is_current():
    geometry=module('focal_geometry')
    pose=json.loads((ROOT/'data/focal/pose_1x.json').read_text(encoding='utf-8'))
    assert geometry.pose_data(pose['delta_map']['sha256']) == pose
    assert geometry.WEB.read_text(encoding='utf-8') == geometry.web_text()


@pytest.mark.parametrize('start,stop', [(0,1),(562,564),(1024,1026),(2047,2049),(3532,3534),(4095,4096)])
def test_map_rows_agree_with_independent_unit_ray_model(start,stop):
    rows=F.map_rows(start,stop)
    c=(np.arange(F.MAP_SIZE)+.5)*F.MAP_WIDTH_MM/F.MAP_SIZE-F.MAP_WIDTH_MM/2
    x,y=np.meshgrid(c,-c[start:stop])
    expected=simulate.along_track(x,y,F.CAMERA,F.FLASH).astype(np.float32)
    radius=np.hypot(x,y)
    expected[(radius<24)|(radius>58)]=np.nan
    assert rows.shape == (stop-start,F.MAP_SIZE) and rows.dtype == np.float32
    np.testing.assert_allclose(rows,expected,rtol=0,atol=1e-7,equal_nan=True)


def test_cache_override_and_fresh_hash_check(tmp_path,monkeypatch):
    geometry=module('focal_geometry')
    data=tmp_path/'metadata';data.mkdir()
    (data/'legacy.json').write_bytes((ROOT/'data/focal/legacy.json').read_bytes())
    cache=tmp_path/'cache'
    monkeypatch.setenv(geometry.CACHE_ENV,str(cache))
    monkeypatch.setattr(geometry,'DATA',data)
    monkeypatch.setattr(geometry,'WEB',tmp_path/'geometry.mjs')
    monkeypatch.setattr(F,'MAP_SIZE',64)
    geometry.build()
    path=cache/'delta_map_1x.npy'
    expected=F.map_rows(0,64,size=64)
    np.testing.assert_array_equal(np.load(path,allow_pickle=False),expected)
    pose=json.loads((data/'pose_1x.json').read_text(encoding='utf-8'))
    assert geometry.sha(path) == pose['delta_map']['sha256']
    path.unlink()
    geometry.build(check=True)  # No existing map is required or recreated in check mode.
    assert not path.exists() and not list(cache.iterdir())
    pose['delta_map']['sha256']='0'*64
    (data/'pose_1x.json').write_text(json.dumps(pose),encoding='utf-8')
    with pytest.raises(AssertionError,match='pose_1x.json differs'):
        geometry.build(check=True)


def test_recorded_cells_retain_every_original_texture():
    data=json.loads(module('focal_regression').fixture_bytes())
    assert len(data['materials'])==69
    assert sum(m['source_cells'] for m in data['materials'])==6000**2
    assert data['labels_sha256']=='7138557faf09cc5afa58a2d9c53ae4cabe69e2f7515b426a96817930be99370a'
    assert data['delta_scale']==.93 and data['delta_offset']==0
    for material in data['materials']:
        xy=np.array(material['xy_mm'])
        assert len(xy)>0
        # Actual unchanged 20um cell centres, including rare textures missed by the main lattice.
        indices=xy*50+.5
        np.testing.assert_allclose(indices,np.rint(indices),atol=1e-9)


def test_regression_tracks_all_fixed_blocks_without_refitting():
    result=module('focal_regression').calculate()
    saved=json.loads((ROOT/'tools/focal_data/regression.json').read_text(encoding='utf-8'))
    assert result == saved
    assert len(result['materials'])==69 and len(result['ruler_patches'])==18
    assert {(p['station'],p['colour'],p['arm']) for p in result['ruler_patches']} == {
        (s,c,a) for s in ('S1','S2','S3') for c in ('red','green','blue') for a in ('old','new')}
    assert result['old']['delta_scale']==.93 and result['new']['delta_scale']==1
    # A scalar and a height change are physically different: preserve, do not hide, the residual.
    assert all(p['signed_mean']>0 for p in result['ruler_patches'])
    assert len({round(p['signed_mean'],5) for p in result['ruler_patches']})>3


def test_frozen_photo_and_video_placement_geometry():
    rulers=module('make_rulers')
    old=json.loads((ROOT/'data/focal/legacy.json').read_text(encoding='utf-8'))
    f=old['framing']['disc_bbox_native_px'][0]*old['chosen']['camera'][2]/120
    assert rulers.GX==pytest.approx(8064/6/f*206.5)
    assert rulers.GY==pytest.approx(6048/6/f*206.5)
    assert rulers.GXV==pytest.approx(8064/f*.819/6*207.8)
    assert rulers.GYV==pytest.approx(rulers.GXV*9/16)
    assert rulers.LENS_Y==old['chosen']['camera'][1]
    assert rulers.FLASH_Y==old['chosen']['flash'][1]
