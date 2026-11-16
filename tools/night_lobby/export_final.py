"""Use the production exporter, frozen paper records and a passing-only atomic selection."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_trial import sha,write_json


def run_check(label,gate,layers=None,write=False):
    command=[sys.executable,'-X','utf8','-B','tools/night_b_export.py',str(FINAL),'--only','lobby',
        '--paper-gate',gate,'--check-report',str(FINAL/(label+'.json'))]
    if layers:command+=['--lobby-layers',','.join(layers)]
    if write:command+=['--write']
    with (FINAL/(label+'.log')).open('wb') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    write_json(FINAL/(label+'-run.json'),dict(command=command,exit=result.returncode))
    assert result.returncode in (0,2), (label,result.returncode)
    return json.loads((FINAL/(label+'.json')).read_text(encoding='utf-8'))


def export():
    drive=json.loads((FINAL/'drive-prewrite.json').read_text(encoding='utf-8'))
    assert not drive['hero_override_required'], 'Resolve the actual drive contrast before any writes'
    absolute=run_check('paper-absolute','night-b')
    recorded=run_check('paper-recorded','night-b-recorded')
    assert len(absolute)==len(recorded)==9
    accepted=[Path(r['file']).name.removesuffix('_dark.webp') for r in recorded if r['paper_accepted']]
    colour=json.loads((FINAL/'surface-prewrite.json').read_text(encoding='utf-8'))
    held_for_hue=[]
    if not colour['kraft_hue']['material_hue_within_3deg']:
        held_for_hue=['filebox']
        if 'filebox' in accepted:accepted.remove('filebox')
    assert accepted
    decision=dict(written_layers=accepted,kept_layers=[Path(r['file']).name.removesuffix('_dark.webp') for r in recorded if not r['paper_accepted'] or Path(r['file']).name.removesuffix('_dark.webp') in held_for_hue],
        held_for_kraft_hue=held_for_hue,kraft_candidate=colour['kraft_hue'],
        absolute=absolute,recorded=recorded,gate_reference='3c3f66a:tools/night_b_manifest.json')
    write_json(FINAL/'export-decision.json',decision)
    written=run_check('paper-write','night-b-recorded',accepted,True)
    assert len(written)==len(accepted) and all(r['paper_accepted'] for r in written)
    pre=json.loads((FINAL/'preflight.json').read_text(encoding='utf-8'))
    manifest=copy.deepcopy(pre['manifest'])
    manifest['previous_blender_note']=manifest.get('blender')
    manifest['blender']='5.2.2 LTS. This lobby attempt uses local CPU, 8 threads, including lamp; retained images keep their original provenance. Non-lobby provenance is unchanged.'
    jobs=['F_lobby_a','F_lobby_b','F_lobby_c','F_lobby_d','L_round5','L_lobby3','G_lamp']
    for job in jobs:
        original=copy.deepcopy(manifest['jobs'][job])
        record=json.loads((FINAL/(job+'-run.json')).read_text(encoding='utf-8'))
        entry=manifest['jobs'][job]
        contributed=[name for name in accepted if pre['manifest']['pictures']['discprobe/web/home/lobby/'+name+'_dark.webp']['job'].startswith(job)]
        entry['lobby_pool_final_attempt']=dict(amb=.64,gain=5.8,add=0,sigma=.42,device='CPU',threads=8,
            render=record,published_layers=contributed,source_scene_sha256=record['scene_sha256'])
        if contributed:
            entry.update(previous_night_b_job=original,device='CPU',machine='local Windows CPU, 8 threads',
                script='tools/night_lobby/'+('render_fax_nightb.py' if job.startswith('F_') else 'render_round5_nightb.py'),
                args=entry['args'].replace(' --device OPTIX (default)','')+' --device CPU --variants paper,dark --night-gain 5.8 --night-sigma-scale 1.0',
                used_for='Published lobby layers: '+','.join(contributed))
            if job=='G_lamp':entry['note']='CPU lamp passed the approved paper gate; original job provenance retained in previous_night_b_job.'
    for row in recorded:
        path='discprobe/web/home/'+Path(row['file']).as_posix();entry=manifest['pictures'][path]
        name=Path(path).name.removesuffix('_dark.webp');passed=name in accepted
        attempt=dict(written=passed,paper_stats=row['paper_stats'],paper_gate_applied=row['paper_gate_applied'],
            paper_accepted=row['paper_accepted'],profile=dict(amb=.64,gain=5.8,add=0,sigma=.42),
            sha256=sha(ROOT/path))
        if not passed:
            old_picture=copy.deepcopy(pre['manifest']['pictures'][path])
            old_job=old_picture['job'].split(' ',1)[0]
            attempt['published_source']=dict(retained_original_bytes=True,picture=old_picture,
                job=pre['manifest']['jobs'][old_job])
        if 'paper_recorded_delta' in row:attempt['paper_recorded_delta']=row['paper_recorded_delta']
        if name in held_for_hue:attempt['kept_reason']='Neutral illumination candidate exceeds the required 3-degree kraft hue comparison; original layer retained without material recolouring.'
        entry['lobby_pool_final']=attempt
        if passed:
            entry['encoding']=row['encoding'];entry['paper_check']=row['paper_check']
    manifest['lobby_pool_final']=dict(render_root=str(FINAL),written_layers=accepted,kept_layers=decision['kept_layers'],
        paper_gate='absolute Night B, otherwise frozen 3c3f66a deltas <= .05 / .01 / .1 percentage points',
        drive_hero_override=False,drive_prewrite=drive)
    (ROOT/'tools/night_b_manifest.json').write_text(json.dumps(manifest,indent=1,ensure_ascii=False)+'\n',encoding='utf-8')
    report_path=ROOT/'tools/night_b_export_report.json'
    published=json.loads(report_path.read_text(encoding='utf-8'))
    by_name={Path(row['file']).name:row for row in recorded}
    for row in published:
        key=Path(row['file']).name
        if key in by_name and Path(row['file']).parts[0]=='lobby':
            attempt=copy.deepcopy(by_name[key]);attempt['written']=key.removesuffix('_dark.webp') in accepted
            row['lobby_pool_final_attempt']=attempt
    report_path.write_text(json.dumps(published,indent=1,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Written',accepted,'kept',decision['kept_layers'])


p=argparse.ArgumentParser();p.add_argument('action',choices=['export']);p.parse_args();export()
