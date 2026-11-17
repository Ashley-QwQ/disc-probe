import base64
import json
import subprocess
import sys

import numpy as np
import pytest

from discprobe import editor_ops, simulate_a3 as A, texlib
from discprobe.editor_preview import Renderer, lamp_tables


LONG = bytes(range(96)).hex().upper()


def make_library(root, signature='fixture-v1', scale=1):
    root.mkdir(exist_ok=True)
    with np.load(A.TABLE, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    data['specs'] = np.array(['A5', 'B9', '8B00', LONG])  # actual inferred U192
    data['xyz'] = np.stack([data['xyz'][i] * scale for i in [0, 1, 2, 0]])
    data['signature'] = np.array(signature)
    np.savez(root / 'colour_table.npz', **data)
    rows = []
    for i, spec in enumerate(data['specs']):
        rows.append(dict(id=f'fixture-{i}', rev=1, spec=str(spec), spec_canonical=str(spec),
                         kind='ladder', grade='converged' if i == 0 else 'best_so_far',
                         periods_um=[.85], purity=[.5],
                         a3v3=dict(same_spec=i < 2),
                         colour=dict(burn_srgb='#8899aa', burn_y=.5,
                                     stability_at_burn=dict(de05=5, fades_out=False),
                                     srgb_by_delta=['#8899aa']*18, y_by_delta=[.5]*18,
                                     stability_de05=[5]*18, fades_out=[False]*18)))
    (root / 'textures.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
    return rows


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / 'library with spaces'
    make_library(root)
    monkeypatch.setenv('DISCPROBE_TEXLIB', str(root))
    A.tables.cache_clear()
    yield root
    A.tables.cache_clear()


def test_fallback_and_wide_specs(lib, monkeypatch):
    assert LONG in A.tables()['specs']
    assert len(A.tables()['specs']) == 4
    assert texlib.resolve('fixture-3') == LONG
    assert texlib.resolve('tex:'+LONG) == LONG
    old = texlib.legacy_materials()[0]
    assert texlib.resolve(old['id']) == old['spec']
    monkeypatch.setenv('DISCPROBE_TEXLIB', str(lib / 'absent'))
    assert len(A.tables()['specs']) == 261
    monkeypatch.delenv('DISCPROBE_TEXLIB')
    assert len(A.tables()['specs']) == 261
    monkeypatch.setenv('DISCPROBE_TEXLIB', str(lib))
    (lib / 'colour_table.npz').write_bytes(b'not an npz')
    assert len(A.tables()['specs']) == 261


def test_live_source_cache_and_browser_table(lib):
    renderer = Renderer()
    one = renderer.swatches()
    a = A.tables()['xyz'].copy()
    make_library(lib, 'fixture-v2', 2)
    two = renderer.swatches()
    assert one['signature'] != two['signature']
    assert A.tables()['signature'] == 'fixture-v2'
    np.testing.assert_array_equal(A.tables()['xyz'], a*2)
    packed = lamp_tables()
    assert LONG in packed['meta']['specs']
    assert packed['meta']['signature'] == 'fixture-v2'
    xyz = np.frombuffer(base64.b64decode(packed['xyz']), dtype='<f4').reshape(4,341,3)
    np.testing.assert_array_equal(xyz, A.tables()['xyz'])


def test_saved_spec_survives_winner_change(lib):
    m = next(m for m in texlib.materials(texlib.library()) if m['spec'] == LONG)
    doc = editor_ops.validate(editor_ops.migrate(dict(version=2, materials=[m], layers=[])))
    rows = make_library(lib, 'fixture-v2')
    rows[-1]['spec'] = rows[-1]['spec_canonical'] = 'A5'
    rows[-1]['rev'] = 2
    (lib / 'textures.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
    assert texlib.resolve('fixture-3') == 'A5'
    loaded = editor_ops.validate(json.loads(json.dumps(doc)))
    assert loaded['materials'][0]['spec'] == LONG
    assert A.known(loaded['materials'][0])


def test_metrics_do_not_treat_unknown_as_stable(lib):
    r = texlib.library()['rows'][0]
    assert texlib.metrics(r, .42)['stability'] == 5
    r = json.loads(json.dumps(r))
    r['colour']['stability_de05'][7] = None
    assert texlib.metrics(r, .42)['stability'] is None
    assert texlib.metrics(r, .99)['y'] is None


def test_cli_find_show_and_simulate(lib, tmp_path):
    def cli(*args):
        return subprocess.run([sys.executable,'-B','-X','utf8','-m','discprobe',*args],
                              check=True,capture_output=True,text=True,encoding='utf-8',timeout=90)
    rows = json.loads(cli('textures','find','--texlib',str(lib),'--grade','best_so_far',
                         '--kind','ladder','--near','#8899aa','--delta','.4','--max-de05','15',
                         '--min-y','.1','--top','2','--json').stdout)
    assert len(rows) == 2
    assert rows[0]['delta_E'] == 0
    assert json.loads(cli('textures','show','fixture-3','--json').stdout)[0]['spec'] == LONG
    labels = tmp_path / 'labels.npy'
    np.save(labels, np.zeros((6000,6000), dtype=bool))
    output = tmp_path / 'preview.png'
    cli('simulate','--design-npy',str(labels),'--light','fixture-3','--texlib',str(lib),
        '--size','200','--output',str(output))
    assert output.read_bytes().startswith(b'\x89PNG')


def test_work_limit_is_explicit():
    with pytest.raises(ValueError, match='256'):
        editor_ops.validate(editor_ops.migrate(dict(version=2,layers=[],materials=[
            dict(id=str(i),spec='A5',rgb=[0,0,0]) for i in range(257)])))


@pytest.mark.parametrize('media',['dvd','cd'])
def test_sequence_ring_writer_and_independent_verifier(tmp_path, media):
    from discprobe import rings,cdrings
    module = rings if media=='dvd' else cdrings
    layout=module.RingLayout(textures=('A5','92','8B00') if media=='dvd' else ('0D','AA','8B00'))
    # Small synthetic layout, same alignment as the physical writer. No large ISO fixture.
    layout.rings=[dict(index=0,group=0,texture='8B00',lba_start=32,lba_end=64)]
    layout.total_sectors=64
    output=tmp_path / (media+'.iso')
    module.write_iso(str(output),layout,log=lambda _:None)
    assert module.verify_iso(str(output),layout)==[]


def test_cli_reference_resolution_on_material_commands(lib, monkeypatch, tmp_path):
    from discprobe import __main__ as cli
    captured=[]
    def run(args):captured.append(args)
    monkeypatch.setattr(cli,'cmd_image',run)
    monkeypatch.setattr(cli,'cmd_tiles',run)
    monkeypatch.setattr(cli,'cmd_rings',run)
    old=texlib.legacy_materials()[0]
    cli.main(['image','--geo',str(tmp_path/'absent'),'--dark','fixture-3','--light',old['id'],'--textures','fixture-3','8B00'])
    assert captured[-1].dark==LONG and captured[-1].light==old['spec']
    assert captured[-1].textures==[LONG,'8B00']
    cli.main(['tiles','--geo',str(tmp_path/'absent'),'--palette','fixture-3',old['id']])
    assert captured[-1].palette==[LONG,old['spec']]
    cli.main(['rings','--textures','A5,92,fixture-3'])
    assert captured[-1].textures=='A5,92,'+LONG


def test_extended_texture_sheet_uses_the_selected_materials(lib,monkeypatch):
    from PIL import Image
    from discprobe import simulate
    seen=[]
    def render(design,size,*,materials,camera,flash,rotate):
        seen.append((materials,rotate))
        return Image.new('RGB',(size,size))
    monkeypatch.setattr(A,'render',render)
    mats=[dict(id='light',spec=LONG),dict(id='dark',spec='A5')]
    sheet=simulate.sheet(np.zeros((200,200),dtype=bool),None,200,'A5',LONG,simulate.CAMERA,simulate.FLASH,materials=mats)
    assert sheet.size==(600,824)
    assert len(seen)==10 and all(m==mats for m,_ in seen)


def test_invalid_transform_table_falls_back(lib):
    with np.load(lib/'colour_table.npz',allow_pickle=False) as z:
        data={k:z[k] for k in z.files}
    data['xyz_to_srgb']=np.eye(2)
    np.savez(lib/'colour_table.npz',**data)
    assert len(A.tables()['specs'])==261
