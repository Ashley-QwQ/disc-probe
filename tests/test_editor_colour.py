import base64
import json

import numpy as np
from PIL import Image
import pytest

from discprobe import editor_colour as C, editor_ops as E, imagedisc


def grey_xyz(lightness):
    return C.WHITE * ((lightness + 16) / 116)**3


@pytest.fixture
def table(monkeypatch):
    xyz = np.array([[C.WHITE, C.WHITE], [C.WHITE, C.WHITE],
                    [grey_xyz(40), grey_xyz(40)], [grey_xyz(60), grey_xyz(60)]])
    value = dict(specs={'B9': 0, 'A5': 1, '8B00': 2, '92': 3}, delta=np.array([0., 1.5]), xyz=xyz)
    monkeypatch.setattr(C, 'active_table', lambda document: value)
    return value


def work(mode):
    materials = [dict(id=ident,spec=spec) for ident,spec in
                 [('background','B9'),('dark','A5'),('tex:8B00','8B00'),('tex:92','92')]]
    # Opaque on the left, transparent on the right.
    rgba = base64.b64encode(bytes([119,119,119,255,119,119,119,0])).decode()
    return E.migrate(dict(media='dvd', scene={'rig': {'phone': 'iphone17pro', 'height': '30'}},
        layers=[dict(id=1,kind='image',width=120,height=120,raster=dict(width=2,height=1,rgba=rgba))],
        materials=materials, assignments=[dict(layer=1,colour=dict(dither=mode, materials=['tex:8B00','tex:92']))]))


@pytest.mark.parametrize('mode', ['nearest', 'ordered'])
def test_colour_labels_and_clip(mode, table):
    g = E.grid(32)
    doc = work(mode)
    actual = E.compose(doc, g)
    y,x = np.indices(actual.shape)
    axis = (np.arange(32) + .5)*g['cell_mm']-60
    r = np.hypot(axis[:, None], axis[None, :])
    hit = (r >= 24) & (r < 58) & (x < 16)
    # sRGB #777777 is just above L*=50, so L*=60 wins the nearest comparison.
    expected = 3 if mode == 'nearest' else np.where(C.BAYER[y%8, x%8] < .5, 2, 3)
    np.testing.assert_array_equal(actual, np.where(hit, expected, 0))
    np.testing.assert_array_equal(actual, E.compose(doc, g))


def test_colour_rig_and_fill_order(table):
    doc = work('nearest')
    g = E.grid(40)
    colour = E.compose(doc, g)
    doc['assignments'].insert(0, dict(layer=1, material='dark'))
    np.testing.assert_array_equal(E.compose(doc, g), colour)
    doc['assignments'].append(dict(layer=1, material='dark'))
    np.testing.assert_array_equal(E.compose(doc, g), colour != 0)
    del doc['scene']
    with pytest.raises(ValueError, match=r'phone and shooting height in scene\.rig'):
        E.compose(doc, g)


def test_xyz_interpolates_before_lab_and_pose_changes_labels(table):
    # The lower and upper ends swap their lightness. This makes placement follow delta.
    table['xyz'][2, 1] = grey_xyz(65)
    table['xyz'][3, 1] = grey_xyz(35)
    table['delta'] = np.array([0., .6])
    doc = work('nearest')
    g = E.grid(64)
    first = E.compose(doc, g)
    doc['scene']['rig']['height'] = '70'
    assert np.any(first != E.compose(doc, g))
    matcher = C.Matcher(doc['materials'], [2, 3], 'nearest', table, relative=False)
    target = C.xyz_lab((table['xyz'][2, 0]+table['xyz'][2, 1])/2)
    np.testing.assert_array_equal(matcher.row(np.array([.3]), target[None,:], 0, np.array([0])), [2])


def test_colour_design_compose_and_image(tmp_path, monkeypatch):
    from discprobe import __main__ as cli
    from test_editor_texlib import make_library

    library = tmp_path / 'texlib'
    make_library(library)
    monkeypatch.delenv('DISCPROBE_TEXLIB', raising=False)
    monkeypatch.setenv('DISCPROBE_HOME', str(tmp_path))
    monkeypatch.setenv('DISCPROBE_WORKERS', '1')
    picture = tmp_path / 'tiny.png'
    Image.new('RGB', (7, 7), '#ed4915').save(picture)
    mats = tmp_path / 'candidates.json'
    mats.write_text(json.dumps({'greedy_specs':['A5','B9','8B00']}), encoding='utf-8')
    doc, labels, iso = (tmp_path / name for name in ('tiny.json','tiny.npy','tiny.iso'))
    monkeypatch.setitem(imagedisc.CELL_SIDES, 20, 120)
    monkeypatch.setattr(imagedisc, 'sectors_to_radius', lambda *args: 80)
    override = ['--table', str(library / 'colour_table.npz')]
    cli.main(['colour-design',str(picture),'--phone','iphone17pro','--height','22.3','--materials',str(mats), *override,
              '--fit','ring','--dither','nearest','-o',str(doc)])
    saved = json.loads(doc.read_text(encoding='utf-8'))
    assert saved['scene']['rig'] == {'phone':'iphone17pro','height':'21'}
    assert E.validate(saved)['assignments'][0]['colour']['dither'] == 'nearest'
    with monkeypatch.context() as patch:
        # Override the label grid size only. Keep the real CLI, composer and writer.
        patch.setattr(E, 'round', lambda _: 120, raising=False)
        cli.main(['compose',str(doc),'--out',str(labels), *override])
    assert np.load(labels).shape == (120,120)
    textures = json.loads(labels.with_suffix('.textures.json').read_text(encoding='utf-8'))['textures']
    assert textures == ['B9','A5','A5','B9','8B00']
    geo = tmp_path / 'geo.json'
    geo.write_text(json.dumps(dict(fit=dict(u=180518.44,v=5.591208,bit_nm_assumed=133.3,
                                          measured_span_mm=[24,58]))), encoding='utf-8')
    cli.main(['image','--geo',str(geo),'--design-npy',str(labels),'--textures',*textures,
              '--no-photo-l','--output',str(iso)])
    with iso.open('rb') as f:
        f.seek(16*2048 + 1)
        assert f.read(5) == b'CD001'
    assert iso.stat().st_size == 80*2048


def test_relative_lightness_retains_levels_inside_small_range(table):
    table['xyz'][2, :] = grey_xyz(10)
    table['xyz'][3, :] = grey_xyz(30)
    mats = work('nearest')['materials']
    target = np.array([[25, 0, 0], [75, 0, 0]], dtype=np.float32)
    for relative, expected in [(False, [3, 3]), (True, [2, 3])]:
        match = C.Matcher(mats, [2, 3], 'nearest', table, relative=relative)
        np.testing.assert_array_equal(match.row(np.array([.4,.4]), target, 0, np.arange(2)), expected)


def test_packed_fitted_palette_without_texlib(monkeypatch):
    monkeypatch.delenv('DISCPROBE_TEXLIB', raising=False)
    monkeypatch.delenv('DISCPROBE_COLOUR_TABLE', raising=False)
    monkeypatch.delenv('DISCPROBE_COLOUR_MATERIALS', raising=False)
    palette = C.palette()
    table = C.active_table()
    assert palette['table']['fitted'] and palette['table']['mapping'] == 'relative'
    assert [m['spec'] for m in palette['materials']] == list(table['specs'])
    assert table['xyz'].shape == (58, 341, 3)
    assert table['delta_scale'] == .93
