import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from discprobe import editor_ops as E
from discprobe import editor_pattern as P

ROOT=Path(__file__).resolve().parents[1]
VECTORS=json.loads((ROOT/'tests/fixtures/editor-vectors.json').read_text(encoding='utf8'))

def js(tmp_path,request):
    source=tmp_path/'request.json';out=tmp_path/'page.raw'
    source.write_text(json.dumps(request),encoding='utf8')
    subprocess.run(['node',str(ROOT/'tests/editor_runner.mjs'),str(source),str(out)],check=True,capture_output=True,timeout=240)
    return out.read_bytes()

@pytest.mark.parametrize('v',VECTORS,ids=lambda v:v['name'])
def test_selection_parity(tmp_path,v):
    py=E.selection(v['definition'],v['grid'],v.get('rgba'))
    assert py.tobytes()==js(tmp_path,dict(action='selection',**v))

@pytest.mark.parametrize('operation',['replace','add','subtract','intersect'])
def test_boolean_parity(tmp_path,operation):
    a=E.selection(VECTORS[0]['definition'],VECTORS[0]['grid']).ravel()
    b=E.selection(VECTORS[3]['definition'],VECTORS[3]['grid']).ravel()
    assert E.boolean_mask(a,b,operation).tobytes()==js(tmp_path,dict(action='boolean',a=a.tolist(),b=b.tolist(),operation=operation))

def test_migration(tmp_path):
    old=dict(version=1,format='disc-probe design',layers=[dict(kind='image',name='legacy')])
    py=E.migrate(old);page=json.loads(js(tmp_path,dict(action='migrate',document=old)))
    assert py==page
    assert E.migrate(py)==py
    with pytest.raises(ValueError):E.migrate(dict(version=3,layers=[]))

def document():
    px=bytes([0,0,0,255,255,255,255,255,190,20,20,255,30,40,50,100])
    mats=[dict(id='background',spec='B9',rgb=[205,200,190]),dict(id='dark',spec='A5',rgb=[40,40,40],period_um=.85),dict(id='red',spec='92',rgb=[190,20,20],period_um=1.8)]
    mg=E.grid(96);mask=E.selection(dict(tool='ring',inner=31,outer=45),mg)
    return E.migrate(dict(version=2,media='dvd',materials=mats,maskGrid=mg,
        selections=[dict(id='ring',name='环',bits=base64.b64encode(mask).decode())],
        layers=[dict(id=1,kind='image',sourceKind='svg',svg='<svg xmlns="http://www.w3.org/2000/svg"/>',x=-15,y=10,width=54,height=48,rot=17,raster=dict(width=2,height=2,rgba=base64.b64encode(px).decode())),
                dict(id=2,kind='image',sourceKind='shape',x=15,y=-15,width=44,height=36,rot=-11,shape=dict(type='ellipse'))],
        assignments=[dict(layer=2,material='red'),dict(selection='ring',pattern=dict(version=1,pattern='diamond',coordinates='cartesian',pitch_mm=5,size_mm=.75,angle_deg=17,origin_mm=[0,0],phase_mm=[.31,-.27],reference_radius_mm=40,materials=['red','dark']))]))

def test_compose_parity(tmp_path):
    d=document();g=E.grid(144)
    py=E.compose(d,g)
    assert py.tobytes()==js(tmp_path,dict(action='compose',document=d,grid=g))
    d['layers'].reverse();d['layers'][0]['opacity']=.49;d['layers'][1]['visible']=False
    assert E.compose(d,g).tobytes()==js(tmp_path,dict(action='compose',document=d,grid=g))

def grey_document(mode, **tone):
    """A grey ramp with a band of half-transparent pixels and one template-coloured stripe, turned 23 degrees."""
    w, h = 96, 40
    px = np.zeros((h, w, 4), np.uint8)
    px[:, :, :3] = np.linspace(0, 255, w).astype(np.uint8)[None, :, None]
    px[:, :, 3] = 255
    px[5:9, :, 3] = 0                        # transparent: skipped by the diffusion
    px[20:23, 10:80, :3] = [190, 20, 20]     # the template colour: wins over the dither
    d = document()
    d['layers'] = [dict(id=1, kind='image', x=-6, y=4, width=70, height=70 * h / w, rot=23, opacity=.8, w=w, h=h,
                        raster=dict(width=w, height=h, rgba=base64.b64encode(px.tobytes()).decode()),
                        tone=dict(dither=mode, **tone))]
    d['assignments'] = [a for a in d['assignments'] if 'selection' in a]
    d['materials'][2]['template_name'] = 'DP-16 test'        # a downloaded template's colour
    return d

def test_only_template_colours_are_matched(tmp_path):
    d = grey_document('threshold')
    d['materials'][2].pop('template_name')                   # a palette swatch's import colour: no match
    d['assignments'] = []                                    # (the ring's pattern fill uses that material too)
    py = E.compose(d, E.grid(300))
    assert not (py == 2).any()
    assert py.tobytes() == js(tmp_path, dict(action='compose', document=d, grid=E.grid(300)))

@pytest.mark.parametrize('mode', ['floyd-steinberg', 'blue-noise', 'ordered', 'clustered', 'threshold'])
def test_tone_dither_parity(tmp_path, mode):
    from discprobe import editor_tone as T
    for tone in (dict(), dict(brightness=-30, contrast=40, highlights=25, shadows=-60, strength=70)):
        d = grey_document(mode, **tone); g = E.grid(300)
        py = E.compose(d, g)
        assert py.tobytes() == js(tmp_path, dict(action='compose', document=d, grid=g))
        dark = py == 1
        assert 0.15 < dark[(py == 0) | dark].mean() < 0.85 if mode != 'threshold' else True
        assert (py == 2).any()                                   # the template colour survived the dither
    assert T.table(T.DEFAULT_TONE) == list(range(256))

def test_tone_tables_and_tiles(tmp_path):
    from discprobe import editor_tone as T
    import random
    rng = random.Random(5)
    tones = [dict(brightness=rng.randint(-100, 100), contrast=rng.randint(-100, 100), highlights=rng.randint(-100, 100),
                  shadows=rng.randint(-100, 100)) for _ in range(40)]
    page = json.loads(js(tmp_path, dict(action='tone', tones=tones)))
    assert page['tables'] == [T.table(t) for t in tones]
    assert page['tiles'] == {k: v[1] for k, v in T.TILES.items()}
    with pytest.raises(ValueError):
        E.validate({**grey_document('nope')})

@pytest.mark.parametrize('kind',['rectangle','ellipse','polygon','line','stroke'])
def test_shape_compose(tmp_path,kind):
    d=document();d['assignments']=[];d['layers']=d['layers'][1:]
    d['layers'][0]['shape']=dict(type=kind,points=[[-.4,-.4],[.4,.1],[-.1,.4]],stroke=.06)
    assert E.compose(d,E.grid(96)).tobytes()==js(tmp_path,dict(action='compose',document=d,grid=E.grid(96)))

@pytest.mark.parametrize('kind',['flow','ox','merge','sync'])
def test_effect_compose(tmp_path,kind):
    d=document();d['assignments']=[dict(layer=2,effect=dict(kind=kind,y1=55,y2=100))]
    assert E.compose(d,E.grid(96)).tobytes()==js(tmp_path,dict(action='compose',document=d,grid=E.grid(96)))

def test_cli_full_disc(tmp_path):
    d=document();work=tmp_path/'作品 with spaces.json';out=tmp_path/'design.npy'
    work.write_text(json.dumps(d),encoding='utf8')
    subprocess.run([sys.executable,'-m','discprobe','compose',str(work),'--out',str(out)],cwd=ROOT,check=True,capture_output=True,timeout=240)
    labels=np.load(out,allow_pickle=False)
    page=js(tmp_path,dict(action='compose',document=d,grid=E.grid(6000)))
    assert labels.dtype==np.uint8 and labels.shape==(6000,6000)
    assert labels.tobytes()==page
    evidence=ROOT/'evidence/editor';evidence.mkdir(exist_ok=True)
    (evidence/'compose-parity.json').write_text(json.dumps(dict(shape=list(labels.shape),dtype=str(labels.dtype),mismatched_cells=0,python_sha256=hashlib.sha256(labels.tobytes()).hexdigest(),page_js_sha256=hashlib.sha256(page).hexdigest()),indent=2),encoding='utf8')

PATTERNS=sorted((ROOT/'tests/fixtures/editor-patterns').glob('*.json'))
@pytest.mark.parametrize('source',PATTERNS,ids=lambda p:p.stem)
def test_pattern_prototype(tmp_path,source):
    v=json.loads(source.read_text(encoding='utf8'))
    if source.stem.startswith('invalid-'):
        with pytest.raises((ValueError,TypeError)):P.validate(v['fill'])
        with pytest.raises(subprocess.CalledProcessError):js(tmp_path,dict(action='pattern',**v))
    else:
        assert P.render(v['fill'],v['grid']).tobytes()==js(tmp_path,dict(action='pattern',**v))

def test_invalid_document():
    d=document();d['layers'][0].pop('raster')
    with pytest.raises(ValueError,match='SVG requires'):E.validate(d)
    d=document();d['selections'][0]['bits']='AA=='
    with pytest.raises(ValueError,match='mask bits'):E.validate(d)

def test_backend_texture_arguments(tmp_path):
    from discprobe import webui
    d=document();d['assignments'][0]['layer']=999
    with pytest.raises(ValueError,match='assignment target'):E.validate(d)
    argv,_=webui.command(dict(action='image',media='dvd',args=dict(geo='latest',design_npy='design.npy',textures=['B9','A5','9292'])),tmp_path,[])
    assert argv[argv.index('--textures')+1:argv.index('--textures')+4]==['B9','A5','9292']


# The bundled selftest calls zero-argument test functions. Keep the same assertions
# available there, including all parametrized cases, without changing that runner.
def _standalone(fn):
    import functools
    import inspect
    import itertools
    import tempfile
    @functools.wraps(fn)
    def run(*args,**kwargs):
        if args or kwargs:return fn(*args,**kwargs)
        parameters=inspect.signature(fn).parameters
        marks=[m for m in getattr(fn,'pytestmark',[]) if m.name=='parametrize']
        cases=[dict()]
        for mark in marks:
            names=[n.strip() for n in mark.args[0].split(',')]
            cases=[{**case,**dict(zip(names,(value,) if len(names)==1 else value))} for case,value in itertools.product(cases,mark.args[1])]
        with tempfile.TemporaryDirectory(prefix='dp-editor-selftest-') as folder:
            for case in cases:
                if 'tmp_path' in parameters:case['tmp_path']=Path(folder).resolve()
                fn(**case)
    return run

for _name,_fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):globals()[_name]=_standalone(_fn)
