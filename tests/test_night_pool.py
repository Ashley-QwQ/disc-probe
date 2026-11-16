"""Image-space light behaviour and the exact-paper export safety boundary."""
import ast
import json
import math
import os
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
    assert ns['object_light'](obj('paper'), st)['pool_scale'] == 1.0
    assert ns['object_light'](obj('desk'), st)['pool_scale'] == .557
    sheet=type('Object',(),{'name':'paper','pass_index':3})()
    ns['render_meshes']=[sheet]
    col[...,3]=1
    oid=np.zeros(mask.shape,dtype=np.int32);oid[:,:50]=3
    mixed=ns['compose'](col,mask,st,oid=oid)
    assert mixed[10,0,0]>out[10,0,0]  # paper lines follow the original wide pool
    assert mixed[10,60,0]==pytest.approx(out[10,60,0])


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


@pytest.mark.parametrize('metric', ['rgb', 'alpha', 'over8'])
def test_night_b_gate_uses_unrounded_inclusive_limits(metric):
    source=ROOT/'tools/night_b_export.py'
    nodes=[n for n in ast.parse(source.read_text(encoding='utf-8')).body
           if isinstance(n,ast.FunctionDef) and n.name in {'paper_stats','night_b_matches'}]
    ns={'Image':Image,'np':np}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    base=np.full((1000,1,4),100,dtype=np.uint8);base[...,3]=235
    actual=base.copy()
    if metric=='rgb':actual[:300,0,:3]+=1
    elif metric=='alpha':actual[0,0,3]=255
    else:actual[0,0,0]+=9
    stats=ns['paper_stats'](Image.fromarray(actual),Image.fromarray(base))
    assert ns['night_b_matches'](stats)
    if metric=='rgb':actual[300,0,0]+=1
    elif metric=='alpha':actual[1,0,3]+=1
    else:actual[1,0,0]+=9
    stats=ns['paper_stats'](Image.fromarray(actual),Image.fromarray(base))
    assert not ns['night_b_matches'](stats)


def test_night_b_export_blocks_failed_job_and_never_writes_paper(tmp_path):
    tools=tmp_path/'tools';tools.mkdir()
    export=tools/'night_b_export.py';export.write_bytes((ROOT/'tools/night_b_export.py').read_bytes())
    home=tmp_path/'discprobe/web/home/newplan';home.mkdir(parents=True)
    renders=tmp_path/'renders/F_np_paper';renders.mkdir(parents=True)
    papers={};darks={}
    for n in ('paper','paper_shadow'):
        p=home/f'{n}_paper.webp';d=home/f'{n}_dark.webp'
        Image.new('RGBA',(1000,1),(100,100,100,255)).save(p,lossless=True)
        Image.new('RGBA',(1000,1),(10,20,30,255)).save(d,lossless=True)
        papers[p]=p.read_bytes();darks[d]=d.read_bytes()
        Image.new('RGBA',(1000,1),(100,100,100,255)).save(renders/f'{n}_paper.png')
        Image.new('RGBA',(1000,1),(30,40,50,255)).save(renders/f'{n}_dark.png')
    paper=Image.open(renders/'paper_shadow_paper.png')
    paper.putpixel((0,0),(109,100,100,255));paper.putpixel((1,0),(109,100,100,255))
    paper.save(renders/'paper_shadow_paper.png')
    cmd=[sys.executable,'-B',str(export),str(renders.parent),'--only','newplan','--jobs','F_np_paper','--paper-gate','night-b','--write']
    failed=subprocess.run(cmd,capture_output=True,text=True)
    assert failed.returncode==2,failed.stdout+failed.stderr
    assert all(p.read_bytes()==v for p,v in darks.items())
    # One of 1000 visible pixels may differ by >8: exactly .1 percent is accepted.
    paper.putpixel((1,0),(100,100,100,255));paper.save(renders/'paper_shadow_paper.png')
    passed=subprocess.run(cmd,capture_output=True,text=True)
    assert passed.returncode==0,passed.stdout+passed.stderr
    assert all(p.read_bytes()!=v for p,v in darks.items())
    assert all(p.read_bytes()==v for p,v in papers.items())


@pytest.mark.parametrize('metric,limit',[('rgb_mean',.05),('alpha_mean',.01),('over8_percent',.1)])
def test_recorded_gate_delta_boundaries_and_scope(metric,limit):
    source=ROOT/'tools/night_b_export.py'
    nodes=[n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)
           and n.name in {'night_b_matches','recorded_paper_match'}]
    path='discprobe/web/home/pastworks/tumble_0_dark.webp'
    ns={'math':math,'RECORDED_ONLY':{path},'LOBBY_RECORDED':set()}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    baseline={'rgb_mean':1.4,'alpha_mean':.11,'over8_percent':3.859}
    records={path:{'paper_check':'mean 1.40, alpha mean 0.11, px >8: 3.859%'}}
    measured=dict(baseline);measured[metric]+=limit
    assert ns['recorded_paper_match'](measured,path,records)['paper_accepted']
    measured[metric]+=1e-6
    assert not ns['recorded_paper_match'](measured,path,records)['paper_accepted']
    assert not ns['recorded_paper_match'](baseline,path,{})['paper_accepted']
    assert not ns['recorded_paper_match'](baseline,path,{path:{'paper_check':'unchanged'}})['paper_accepted']
    assert not ns['recorded_paper_match'](baseline,'discprobe/web/home/newplan/top_dark.webp',records)['paper_accepted']


def test_recorded_gate_reads_frozen_git_recipe_not_mutable_manifest(tmp_path):
    tools=tmp_path/'tools';tools.mkdir()
    export=tools/'night_b_export.py';export.write_bytes((ROOT/'tools/night_b_export.py').read_bytes())
    home=tmp_path/'discprobe/web/home/newplan';home.mkdir(parents=True)
    renders=tmp_path/'renders/F_np_top';renders.mkdir(parents=True)
    paper=Image.fromarray(np.random.default_rng(9).integers(0,256,(24,24,3),dtype=np.uint8))
    for name in ('paper','dark'):
        paper.save(home/f'top_{name}.webp',quality=90,method=4,exact=True)
        paper.save(renders/f'top_{name}.png')
    (tools/'night_b_manifest.json').write_text(json.dumps({'pictures':{
        'discprobe/web/home/newplan/top_dark.webp':{'encoding':'(1, 0)','paper_check':'mean 999, alpha mean 999, px >8: 999%'}}}),encoding='utf-8')
    git_dir=subprocess.check_output(['git','rev-parse','--absolute-git-dir'],cwd=ROOT,text=True).strip()
    report=tmp_path/'check.json'
    run=subprocess.run([sys.executable,'-B',str(export),str(renders.parent),'--only','newplan','--jobs','F_np_top',
                        '--paper-gate','night-b-recorded','--check-report',str(report)],env={**os.environ,'GIT_DIR':git_dir},capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    row=json.loads(report.read_text(encoding='utf-8'))[0]
    assert row['encoding']=='(90, 4)' and row['paper_accepted']
    assert row['paper_gate_applied']=='night-b'
    assert row['paper_gate_reference']=='3c3f66a:tools/night_b_manifest.json'
    assert len(row['paper_gate_reference_blob'])==40


@pytest.mark.parametrize('metric,limit',[('rgb_mean',.05),('alpha_mean',.01),('over8_percent',.1)])
def test_lobby_recorded_gate_is_bounded_and_missing_records_fail(metric,limit):
    source=ROOT/'tools/night_b_export.py'
    nodes=[n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)
           and n.name in {'night_b_matches','recorded_paper_match'}]
    path='discprobe/web/home/lobby/lamp_dark.webp'
    ns={'math':math,'RECORDED_ONLY':set(),'LOBBY_RECORDED':{path}}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    base={'rgb_mean':1.32,'alpha_mean':0.,'over8_percent':2.831}
    records={path:{'paper_check':'mean 1.32, alpha mean 0.00, px >8: 2.831%'}}
    at_limit=dict(base);at_limit[metric]+=limit
    assert ns['recorded_paper_match'](at_limit,path,records)['paper_accepted']
    at_limit[metric]+=1e-6
    assert not ns['recorded_paper_match'](at_limit,path,records)['paper_accepted']
    assert not ns['recorded_paper_match'](base,path,{})['paper_accepted']
    assert not ns['recorded_paper_match'](base,'discprobe/web/home/lobby/unapproved_dark.webp',records)['paper_accepted']
    assert ns['recorded_paper_match']({'rgb_mean':.25,'alpha_mean':0.,'over8_percent':0.},path,{})['paper_accepted']


def test_lobby_layer_selection_writes_only_selected_dark_and_does_not_read_missing_layers(tmp_path):
    tools=tmp_path/'tools';tools.mkdir()
    export=tools/'night_b_export.py';export.write_bytes((ROOT/'tools/night_b_export.py').read_bytes())
    home=tmp_path/'discprobe/web/home/lobby';home.mkdir(parents=True)
    (home/'lobby.json').write_text(json.dumps({'layers':[{'name':'base','box':[0,0,8,8]}]}),encoding='utf-8')
    renders=tmp_path/'renders/F_lobby_a';renders.mkdir(parents=True)
    Image.new('RGB',(8,8),(100,100,100)).save(home/'base_paper.webp',lossless=True)
    Image.new('RGB',(8,8),(10,20,30)).save(home/'base_dark.webp',lossless=True)
    Image.new('RGBA',(8,8),(40,50,60,255)).save(home/'lamp_dark.webp',lossless=True)
    paper_before=(home/'base_paper.webp').read_bytes();lamp_before=(home/'lamp_dark.webp').read_bytes()
    Image.new('RGB',(8,8),(100,100,100)).save(renders/'desk_base_paper.png')
    Image.new('RGB',(8,8),(30,40,50)).save(renders/'desk_base_dark.png')
    command=[sys.executable,'-B',str(export),str(renders.parent),'--only','lobby','--lobby-layers','base',
             '--paper-gate','night-b','--write']
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert Image.open(home/'base_dark.webp').getpixel((0,0))[:3]==(30,40,50)
    assert (home/'base_paper.webp').read_bytes()==paper_before and (home/'lamp_dark.webp').read_bytes()==lamp_before
    invalid=subprocess.run([*command[:command.index('--lobby-layers')+1],'unknown',*command[command.index('--paper-gate'):]],capture_output=True,text=True)
    assert invalid.returncode!=0 and 'known, nonempty layer names' in invalid.stdout+invalid.stderr
