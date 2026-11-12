"""No fixtures: these checks also run in the bundled zero-argument selftest."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request

import numpy as np
from PIL import Image
from discprobe import editor_ops as E, simulate, webui

ROOT=Path(__file__).resolve().parents[1]


def test_release_renderer_unchanged():
    y,x=np.indices((6000,6000),sparse=True)
    design=((y//75+x//111)%2).astype(bool)
    legacy=simulate.render(design,200,rotate=17)
    # Recorded from the unchanged release renderer before this refactor.
    assert hashlib.sha256(legacy.tobytes()).hexdigest()=='5d7e5166d3b4e3be5d0ed96ba611b633bc4b2106f7eed0d9c8ec2e6f0f97c0ef'
    labelled=simulate.render(design.astype(np.uint8),200,rotate=17,
                             materials=[dict(id='background',spec='B9'),dict(id='dark',spec='A5')])
    assert labelled.tobytes()==legacy.tobytes()


def test_document_preview_http_cli():
    palette=json.loads((ROOT/'discprobe/web/home/design/swatches.json').read_text(encoding='utf8'))
    assert palette['display_colours']==simulate.material_swatches(list(palette['swatches'].values()))
    material=next(dict(m,period_um=m['periods_um'][0]) for m in palette['swatches'].values() if 1.5<m['periods_um'][0]<1.7)
    grid=E.grid(60)
    mask=E.selection(dict(tool='ring',inner=32,outer=46),grid)
    document=E.migrate(dict(version=2,media='dvd',cell=.02,maskGrid=grid,layers=[],
        materials=[dict(id='background',spec='B9',rgb=[205,200,190]),dict(material,rgb=material['srgb'])],
        selections=[dict(id='ring',name='Ring',bits=base64.b64encode(mask).decode())],
        assignments=[dict(selection='ring',material=material['id'])]))
    pose=dict(camera=[20,85,330],flash=[-23.66,104.79,330],rotate=17)
    payload=dict(document=document,pose=pose,size=200,quality='full')
    with tempfile.TemporaryDirectory(prefix='dp-editor-preview-') as folder:
        root=Path(folder).resolve()
        backend=webui.Backend(root,drive_provider=lambda:[])
        with webui.Server(backend,0) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            def post(path,body,origin=None):
                headers={'Content-Type':'application/json'}
                if origin:headers['Origin']=origin
                req=urllib.request.Request(url+path,json.dumps(body).encode(),headers)
                with urllib.request.urlopen(req,timeout=90) as response:
                    return response.read(),dict(response.headers)
            try:
                api,headers=post('/api/editor-preview',payload)
                assert headers['Content-Type']=='image/png' and headers['X-Editor-Cache']=='miss'
                again,cached=post('/api/editor-preview',payload)
                assert again==api and cached['X-Editor-Cache']=='hit'
                work=root/'作品 with spaces.json';out=root/'render.png'
                work.write_text(json.dumps(document),encoding='utf8')
                command=[sys.executable,'-m','discprobe','simulate','--work',str(work),'--size','200','--rotate','17',
                         '--camera',*map(str,pose['camera']),'--flash',*map(str,pose['flash']),'--output',str(out)]
                subprocess.run(command,cwd=ROOT,check=True,capture_output=True,timeout=90)
                assert out.read_bytes()==api,'CLI and HTTP PNG bytes differ'
                with Image.open(io.BytesIO(api)) as image:
                    assert image.size==(200,200)
                    # The unpatterned region includes the release model's groove rainbow.
                    a=np.array(image).astype(int);axis=(np.arange(200)+.5)*120/200-60
                    r=np.hypot(axis[:,None],axis[None,:])
                    assert np.ptp(a,axis=-1)[(r>48)&(r<57)].max()>15
                draft,_=post('/api/editor-preview',dict(payload,quality='draft'))
                assert draft!=api,'quick render must be refined with linear-light fine samples'
                moved,_=post('/api/editor-preview',dict(payload,pose=dict(pose,camera=[30,85,330]),quality='draft'))
                assert moved!=draft
                changed=json.loads(json.dumps(document));changed['assignments']=[]
                changed_bytes,changed_headers=post('/api/editor-preview',dict(payload,document=changed,quality='draft'))
                assert changed_headers['X-Editor-Document']!=headers['X-Editor-Document'] and changed_bytes!=draft
                colours,_=post('/api/editor-swatches',dict(pose=pose))
                colours=json.loads(colours)['colours']
                assert colours[material['id']]==simulate.material_swatches([material],pose['camera'],pose['flash'])[material['id']]
                for bad in [None,dict(payload,document=None),dict(payload,pose=[]),dict(payload,size=True),dict(payload,quality='other'),dict(payload,pose=dict(camera=[0,0,0]))]:
                    try:post('/api/editor-preview',bad)
                    except urllib.error.HTTPError as exc:assert exc.code==400
                    else:raise AssertionError('invalid preview accepted')
                try:post('/api/editor-preview',payload,origin='https://example.invalid')
                except urllib.error.HTTPError as exc:assert exc.code==403
                else:raise AssertionError('cross-origin preview accepted')
                evidence=ROOT/'evidence/editor/round4';evidence.mkdir(parents=True,exist_ok=True)
                (evidence/'render-parity.json').write_text(json.dumps(dict(size=200,pose=pose,
                    http_png_sha256=hashlib.sha256(api).hexdigest(),cli_png_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                    png_bytes_identical=True,cache_hit=True,model='discprobe.simulate.render',fine_samples=simulate.FINE_SAMPLES),indent=2),encoding='utf8')
            finally:
                server.shutdown();thread.join(timeout=5)
