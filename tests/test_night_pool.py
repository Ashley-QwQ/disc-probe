"""Image-space light behaviour and the exact-paper export safety boundary."""
import ast
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('page,mode', [('newplan', 'top'), ('faxnews', 'fax')])
def test_line_pool_direction_and_silhouette(page, mode):
    path = ROOT / f'discprobe/web/home/{page}/render_{page}.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'lin_to_srgb', 'hex_srgb', 'compose', 'object_light'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(np=np, math=math, MODE=mode, SS=1, PPM=1, POOL={'center':(0, 0), 'sigma':10},
              to_px=lambda *p:[0.5, 0.5], ROLE={'desk':'desk', 'hero':'body', 'paper':'sheet'})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    st = dict(line='#ffffff', line_alpha=.88, line_alpha_far=.35, line_alpha_outline=.6,
              pool_scale=.557, amb=(.64,)*3, gain=(2.4,)*3, add=(0.,)*3,
              hero_light=dict(amb=(1.,)*3,gain=(4.9,)*3,add=(.006,)*3),
              sheet_light=dict(amb=(.55,)*3,gain=(.33,.29,.21),add=(0.,)*3))
    col = np.zeros((100, 100, 4), np.float32)
    col[..., 3] = 1
    mask = np.ones((100, 100), bool)
    out = ns['compose'](col, mask, st)
    assert out[0, 0, 0] == pytest.approx(.88)
    assert out[-1, -1, 0] == pytest.approx(.35)
    # Pool centre is at the top, with top-down rows; no vertical inversion.
    assert out[0, 3, 0] > out[-1, 3, 0]
    col[-1, :, 3] = 0
    outlined = ns['compose'](col, mask, st)
    assert outlined[-2, -2, 0] >= .6
    obj = lambda name:type('Object', (), {'name':name})()
    assert ns['object_light'](obj('desk'), st)['gain'] == (2.4,)*3
    assert ns['object_light'](obj('hero'), st)['gain'] == (4.9,)*3
    assert ns['object_light'](obj('paper'), st)['gain'] == (.33,.29,.21)


def test_strict_export_checks_whole_job_before_writing(tmp_path):
    tools = tmp_path / 'tools'
    tools.mkdir()
    export = tools / 'night_b_export.py'
    export.write_bytes((ROOT / 'tools/night_b_export.py').read_bytes())
    home = tmp_path / 'discprobe/web/home/newplan'
    home.mkdir(parents=True)
    renders = tmp_path / 'renders/F_np_paper'
    renders.mkdir(parents=True)
    originals = {}
    for name in ('paper', 'paper_shadow'):
        Image.new('RGBA', (8,8), (30,50,70,255)).save(home / f'{name}_paper.webp', lossless=True)
        dest = home / f'{name}_dark.webp'
        Image.new('RGBA', (8,8), (4,6,8,255)).save(dest, lossless=True)
        originals[dest] = dest.read_bytes()
        Image.new('RGBA', (8,8), (30,50,70,255)).save(renders / f'{name}_paper.png')
        Image.new('RGBA', (8,8), (20,40,60,255)).save(renders / f'{name}_dark.png')
    # The second picture fails by only one channel step at one pixel.
    mismatch = Image.open(renders / 'paper_shadow_paper.png')
    mismatch.putpixel((2,3),(30,50,71,255))
    mismatch.save(renders / 'paper_shadow_paper.png')
    report = tmp_path / 'check.json'
    cmd = [sys.executable, '-B', str(export), str(renders.parent), '--only', 'newplan',
           '--jobs', 'F_np_paper', '--require-paper-unchanged', '--check-report', str(report), '--write']
    fail = subprocess.run(cmd, capture_output=True, text=True)
    assert fail.returncode == 2, fail.stdout + fail.stderr
    assert all(p.read_bytes() == data for p,data in originals.items())
    rows = json.loads(report.read_text(encoding='utf-8'))
    assert rows[0]['paper_check'] == 'unchanged'
    assert rows[1]['paper_changed_pixels'] == 1
    Image.new('RGBA',(8,8),(30,50,70,255)).save(renders/'paper_shadow_paper.png')
    passed = subprocess.run(cmd, capture_output=True, text=True)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert all(p.read_bytes() != data for p,data in originals.items())


def test_strict_export_reproduces_recorded_lossy_recipe(tmp_path):
    tools=tmp_path/'tools';tools.mkdir()
    export=tools/'night_b_export.py';export.write_bytes((ROOT/'tools/night_b_export.py').read_bytes())
    home=tmp_path/'discprobe/web/home/newplan';home.mkdir(parents=True)
    renders=tmp_path/'renders/F_np_top';renders.mkdir(parents=True)
    pixels=np.random.default_rng(4).integers(0,256,(24,24,3),dtype=np.uint8)
    paper=Image.fromarray(pixels)
    paper.save(home/'top_paper.webp',quality=83,method=3,exact=True)
    paper.save(renders/'top_paper.png')
    paper.save(home/'top_dark.webp',quality=83,method=3,exact=True)
    paper.save(renders/'top_dark.png')
    (tools/'night_b_manifest.json').write_text(json.dumps({'pictures':{
        'discprobe/web/home/newplan/top_dark.webp':{'encoding':'(83, 3)'}}}),encoding='utf-8')
    run=subprocess.run([sys.executable,'-B',str(export),str(renders.parent),'--only','newplan',
                        '--jobs','F_np_top','--require-paper-unchanged'],capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    assert 'paper: unchanged' in run.stdout
