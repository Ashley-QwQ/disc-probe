"""Bounded second base trial: prepare, render candidates/formal, and measure fixed points."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
TRIAL=Path('F:/dp-archive/tmp/lobbypool/trial2')
PREVIOUS=TRIAL.parent/'trial'
os.environ['LOBBY_TRIAL']=str(TRIAL)
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_trial import protected,sha,write_json,BLENDER,EXCLUDED


def files(root):
    for parent,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if EXCLUDED not in str(Path(parent)/d).lower()]
        for name in names:
            p=Path(parent)/name
            if EXCLUDED not in str(p).lower():yield p


def prepare():
    assert not (TRIAL/'preflight.json').exists(), 'Preserve existing evidence'
    (TRIAL/'stage').mkdir(parents=True,exist_ok=True)
    old=json.loads((PREVIOUS/'preflight.json').read_text(encoding='utf-8'))
    free={d:shutil.disk_usage(d+':/').free for d in ('D','F')}
    assert min(free.values())>=5_000_000_000
    old.update(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               free_bytes=free,protected=protected(),
               previous_bundle={p.relative_to(ROOT).as_posix():sha(p) for p in files(ROOT/'docs/cards/lobby-pool-trial')})
    write_json(TRIAL/'preflight.json',old)
    for name in ('scene-inspection.json','desk-coverage.npy','drive-top-polygons.json','scene-copy.json','base_old_dark.webp'):
        shutil.copyfile(PREVIOUS/name,TRIAL/name)
    shutil.copyfile(PREVIOUS/'stage/room_fax.blend',TRIAL/'stage/room_fax.blend')
    copy=json.loads((TRIAL/'scene-copy.json').read_text(encoding='utf-8'))
    assert sha(TRIAL/'stage/room_fax.blend')==copy['sha256']
    copy['reused_from']=str(PREVIOUS/'stage/room_fax.blend')
    write_json(TRIAL/'scene-copy.json',copy)
    write_json(TRIAL/'reused-geometry.json',{name:{'source':str(PREVIOUS/name),'sha256':sha(TRIAL/name)}
        for name in ('scene-inspection.json','desk-coverage.npy','drive-top-polygons.json')})
    # Only the established illumination profile changes; no capability/version change.
    (TRIAL/'route').mkdir(exist_ok=True)
    for name in ('blender_capabilities.json','task_route.json'):
        shutil.copyfile(PREVIOUS/'route'/name,TRIAL/'route'/name)
    write_json(TRIAL/'route/stage_state.json',dict(schema_version='1.0',stage='lighting_trial2',
        scope='base only; original segment sigma .42; fixed amb .64/add 0; neutral gain calibrated numerically',
        geometry='unchanged',camera='unchanged',visual_review='pending'))
    print('Prepared trial2, input hashes preserved',free)


def render(gain,ss,label,variants):
    assert min(shutil.disk_usage(d+':/').free for d in ('D','F'))>=5_000_000_000
    output=TRIAL/label
    assert not output.exists(), 'Never overwrite a render attempt'
    command=[str(BLENDER),'-b',str(TRIAL/'stage/room_fax.blend'),'--disable-autoexec','-t','8',
        '--python-exit-code','1','--python',str(TRIAL/'stage/render_fax_nightb.py'),'--',
        '--layers','base','--ss',str(ss),'--no-mist','--force','--device','CPU','--variants',variants,
        '--night-gain',str(gain),'--night-sigma-scale','1.0','--outdir',str(output)]
    env=dict(os.environ,TEMP=str(TRIAL),TMP=str(TRIAL),PYTHONDONTWRITEBYTECODE='1')
    start=time.monotonic()
    with (TRIAL/(label+'.log')).open('wb') as log:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    record=dict(command=command,exit=result.returncode,seconds=round(time.monotonic()-start,3),
        layers=['base'],variants=variants.split(','),device='CPU',threads=8,ss=ss,gain=gain,sigma=.42)
    write_json(TRIAL/(label+'-run.json'),record)
    print(label,record,flush=True)
    assert result.returncode==0
    measure_one(output/'desk_base_dark.png',label,gain,ss)


def measure_one(path,label,gain,ss):
    import numpy as np
    from PIL import Image
    tree=ast.parse((ROOT/'tools/night_lobby/measure_trial.py').read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='lightness')
    ns={'np':np}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<L*>','exec'),ns)
    rgb=np.asarray(Image.open(path).convert('RGB'))
    l=ns['lightness'](rgb)
    x,y=842,1074
    result=dict(label=label,gain=gain,ss=ss,sigma=.42,xy=[x,y],rgb=rgb[y,x].tolist(),
        center_L_star=float(l[y,x]),corners_L_star=[float(np.median(p)) for p in
            (l[:5,:5],l[:5,-5:],l[-5:,:5],l[-5:,-5:])])
    result['target_passed']=15.5<=result['center_L_star']<=17 and max(result['corners_L_star'])<=7
    write_json(TRIAL/(label+'-metrics.json'),result)
    print(json.dumps(result,indent=2),flush=True)


def select():
    labels=['candidate-g4-r1','candidate-g5_5']
    first,second=[json.loads((TRIAL/(name+'-metrics.json')).read_text(encoding='utf-8')) for name in labels]
    luminance=lambda lightness:((lightness+16)/116)**3
    fit=first['gain']+(luminance(16.1)-luminance(first['center_L_star']))*(second['gain']-first['gain'])/(luminance(second['center_L_star'])-luminance(first['center_L_star']))
    record=dict(gain=round(fit,1),amb=.64,add=0,sigma=.42,sigma_scale=1.,candidate_labels=labels,
        target_center=[15.5,17],target_corners_max=7,fitted_gain_for_L16_1=fit,
        reason='Two SS1 candidates; linear luminance fit to L*=16.1 then round gain to one decimal; independently verify SS4 output',
        formal_ss=4,formal_variants=['paper','dark'])
    if (TRIAL/'selection.json').exists():
        existing=json.loads((TRIAL/'selection.json').read_text(encoding='utf-8'))
        assert existing['gain']==record['gain'] and abs(existing['fitted_gain_for_L16_1']-fit)<1e-12
    else:write_json(TRIAL/'selection.json',record)
    print('Selected gain',record['gain'],'fit',fit)


parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['prepare','render','select'])
parser.add_argument('--gain',type=float,default=4.)
parser.add_argument('--ss',type=int,default=1)
parser.add_argument('--label',default='candidate-g4')
parser.add_argument('--variants',default='dark')
a=parser.parse_args()
if a.action=='prepare':prepare()
elif a.action=='select':select()
else:render(a.gain,a.ss,a.label,a.variants)
