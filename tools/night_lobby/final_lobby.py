"""Prepare and run the seven lobby jobs on CPU; never traverse excluded paths."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
PREVIOUS=FINAL.parent/'trial2'
os.environ['LOBBY_TRIAL']=str(FINAL)
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_trial import sha,write_json,protected,BLENDER,EXCLUDED
JOBS=['L_lobby3','F_lobby_a','F_lobby_b','F_lobby_c','F_lobby_d','L_round5','G_lamp']


def prepare():
    assert not (FINAL/'preflight.json').exists(), 'Preserve existing evidence'
    stage=FINAL/'stage';stage.mkdir(parents=True,exist_ok=True)
    free={d:shutil.disk_usage(d+':/').free for d in ('D','F')}
    assert min(free.values())>=5_000_000_000
    manifest=json.loads((ROOT/'tools/night_b_manifest.json').read_text(encoding='utf-8'))
    write_json(FINAL/'preflight.json',dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        free_bytes=free,protected=protected(),manifest=manifest,
        export_report=json.loads((ROOT/'tools/night_b_export_report.json').read_text(encoding='utf-8')),
        scripts={n:sha(ROOT/'tools/night_lobby'/n) for n in ['render_fax_nightb.py','render_round5_nightb.py','night_b_palette.py','glow_review.json']}))
    old=FINAL/'old';old.mkdir(exist_ok=True)
    for layer in ('base','fax','faxnews','filebox','lamp','newplan','parcel','screen','screen_on'):
        shutil.copyfile(ROOT/f'discprobe/web/home/lobby/{layer}_dark.webp',old/f'{layer}_dark.webp')
    for name in ('render_fax_nightb.py','render_round5_nightb.py','night_b_palette.py','glow_review.json'):
        shutil.copyfile(ROOT/'tools/night_lobby'/name,stage/name)
    shutil.copyfile(PREVIOUS/'stage/room_fax.blend',stage/'room_fax.blend')
    shutil.copyfile(Path('D:/disc-probe/art/desk/room_lobby3_final.blend'),stage/'room_lobby3_final.blend')
    remote_names=['room_fax_parcel.blend','room_round5.blend']
    with (FINAL/'scene-copy.log').open('wb') as log:
        source=subprocess.Popen(['ssh','-o','BatchMode=yes','x79',
            'tar cf - -C /home/knappy/nightb/stage '+' '.join(remote_names)],stdout=subprocess.PIPE,stderr=log)
        target=subprocess.Popen(['tar','xf','-','-C',str(stage)],stdin=source.stdout,stdout=log,stderr=log)
        source.stdout.close(); assert target.wait()==0;assert source.wait()==0
    scenes={}
    for name in remote_names:
        remote='/home/knappy/nightb/stage/'+name
        size=int(subprocess.check_output(['ssh','-o','BatchMode=yes','x79','stat -c %s '+remote],timeout=30))
        digest=subprocess.check_output(['ssh','-o','BatchMode=yes','x79','sha256sum '+remote],timeout=30).decode('ascii').split()[0]
        assert (stage/name).stat().st_size==size and sha(stage/name)==digest
        scenes[name]=dict(remote='x79:'+remote,bytes=size,sha256=digest)
    for name in ('room_fax.blend','room_lobby3_final.blend'):
        scenes[name]=dict(bytes=(stage/name).stat().st_size,sha256=sha(stage/name))
    write_json(FINAL/'scenes.json',scenes)
    # Accepted SS4 base is reused byte for byte; other F_lobby_a layers are rendered below.
    a=FINAL/'F_lobby_a';a.mkdir(exist_ok=True)
    reused={}
    for name in ('desk_base_paper.png','desk_base_dark.png','render_base.json'):
        shutil.copyfile(PREVIOUS/'F_lobby_a'/name,a/name)
        reused[name]=dict(source=str(PREVIOUS/'F_lobby_a'/name),sha256=sha(a/name))
    write_json(FINAL/'base-reused.json',reused)
    for name in ('scene-inspection.json','desk-coverage.npy','drive-top-polygons.json'):
        shutil.copyfile(PREVIOUS/name,FINAL/name)
    print('Prepared final lobby jobs',free,scenes,flush=True)


def render(job):
    pre=json.loads((FINAL/'preflight.json').read_text(encoding='utf-8'))
    entry=pre['manifest']['jobs'][job]
    args=shlex.split(entry['args'].replace(' --device OPTIX (default)',''))
    if job=='F_lobby_a':args[args.index('--layers')+1]='faxnews,filebox'
    if '--glow' in args:args[args.index('--glow')+1]=str(FINAL/'stage/glow_review.json')
    scene=Path(entry['scene']).name
    script='render_fax_nightb.py' if job.startswith('F_') else 'render_round5_nightb.py'
    output=FINAL/job
    if job!='F_lobby_a':assert not output.exists(), 'Never overwrite a job'
    assert min(shutil.disk_usage(d+':/').free for d in ('D','F'))>=5_000_000_000
    command=[str(BLENDER),'-b',str(FINAL/'stage'/scene),'--disable-autoexec','-t','8','--python-exit-code','1',
        '--python',str(FINAL/'stage'/script),'--']+args+['--device','CPU','--variants','paper,dark',
        '--night-gain','5.8','--night-sigma-scale','1.0','--outdir',str(output)]
    env=dict(os.environ,TEMP=str(FINAL),TMP=str(FINAL),PYTHONDONTWRITEBYTECODE='1')
    start=time.monotonic()
    with (FINAL/(job+'.log')).open('wb') as log:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    record=dict(job=job,command=command,exit=result.returncode,seconds=round(time.monotonic()-start,3),
        manifest_args=entry['args'],rendered_layers=args[args.index('--layers')+1].split(','),
        reused_layers=['base'] if job=='F_lobby_a' else [],device='CPU',threads=8,
        scene_sha256=sha(FINAL/'stage'/scene),script_sha256=sha(FINAL/'stage'/script))
    write_json(FINAL/(job+'-run.json'),record)
    print(job,result.returncode,record['seconds'],flush=True)
    assert result.returncode==0


parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['prepare','render','all'])
parser.add_argument('--job',choices=JOBS)
a=parser.parse_args()
if a.action=='prepare':prepare()
elif a.action=='render':render(a.job)
else:
    for job in JOBS:
        if not (FINAL/(job+'-run.json')).exists():render(job)
