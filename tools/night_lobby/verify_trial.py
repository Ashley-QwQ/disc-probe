"""Verify the review bundle and protected files; do not approve visual appearance."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from PIL import Image
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_trial import ROOT, TRIAL, SOURCE, sha, write_json, protected

before = json.loads((TRIAL/'preflight.json').read_text(encoding='utf-8'))
after = protected()
changed = [p for p,h in before['protected'].items() if after.get(p) != h]
added = sorted(set(after)-set(before['protected']))
assert not changed and not added, (changed,added)
source_ok = {name: sha(SOURCE/name)==entry['sha256'] for name,entry in before['inputs'].items()}
assert all(source_ok.values())
scene = json.loads((TRIAL/'scene-copy.json').read_text(encoding='utf-8'))
assert sha(TRIAL/'stage/room_fax.blend') == scene['sha256']
render = json.loads((TRIAL/'F_lobby_a-run.json').read_text(encoding='utf-8'))
assert render['exit']==0 and render['layers']==['base'] and render['variants']==['paper','dark']
script_checks = {}
for name in ('render_fax_nightb.py','render_round5_nightb.py'):
    original = ast.parse((SOURCE/name).read_text(encoding='utf-8'))
    revised = ast.parse((ROOT/'tools/night_lobby'/name).read_text(encoding='utf-8'))
    def style(tree):
        n = next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VARIANT_STYLE' for t in n.targets))
        return {key.value: {kw.arg: ast.dump(kw.value) for kw in call.keywords} for key,call in zip(n.value.keys,n.value.values)}
    old,new=style(original),style(revised)
    assert old['paper']==new['paper']
    assert {k:v for k,v in old['dark'].items() if k not in ('amb','gain','add')} == {k:v for k,v in new['dark'].items() if k not in ('amb','gain','add')}
    funcs = ('outline_mask','compose_and_save','make_light','facing_tone','band_tone')
    function_equal = {f: ast.dump(next(n for n in original.body if isinstance(n,ast.FunctionDef) and n.name==f)) == ast.dump(next(n for n in revised.body if isinstance(n,ast.FunctionDef) and n.name==f)) for f in funcs}
    assert all(function_equal.values())
    assert sha(ROOT/'tools/night_lobby'/name)==sha(TRIAL/'stage'/name)
    script_checks[name]=dict(paper_style_equal=True, non_light_dark_style_equal=True,functions_equal=function_equal,
                             sha256=sha(ROOT/'tools/night_lobby'/name),stage_equal=True)
paper=json.loads((TRIAL/'paper-check.json').read_text(encoding='utf-8'))
assert len(paper)==1 and paper[0]['paper_gate']=='night-b'
captures=json.loads((TRIAL/'capture.json').read_text(encoding='utf-8'))
assert len(captures)==2
assert captures[0]['substitutions']==[] and captures[1]['substitutions']
assert all('/home/lobby/base_dark.webp' in url for url in captures[1]['substitutions'])
for row in captures:
    assert not row['errors'] and not row['csp'] and row['theme']=='dark'
    assert Image.open(TRIAL/(row['name']+'.png')).size==(1440,1000)
assert captures[0]['worldTransform']==captures[1]['worldTransform']
assert captures[0]['layerTransforms']==captures[1]['layerTransforms']
shot_old=np.asarray(Image.open(TRIAL/'lobby_old_dark.png').convert('RGB'))
shot_new=np.asarray(Image.open(TRIAL/'lobby_trial_dark.png').convert('RGB'))
shot_changed_pixels=int(np.any(shot_old!=shot_new,axis=2).sum())
assert shot_changed_pixels>0
assert sha(TRIAL/'base_trial_dark.png')==sha(TRIAL/'F_lobby_a/desk_base_dark.png')
assert Image.open(TRIAL/'base_trial_dark.png').size==(2560,1791)
assert sha(TRIAL/'base_old_dark.webp')==before['protected']['discprobe/web/home/lobby/base_dark.webp']
for p in (ROOT/'tools/night_lobby').glob('*.py'):
    ast.parse(p.read_text(encoding='utf-8'))
metrics=json.loads((TRIAL/'measurements.json').read_text(encoding='utf-8'))
assert metrics['drive_top']['status'].startswith('UNCHANGED_OVERLAY')
assert sha(Path('D:/disc-probe/art/desk/room_lobby3_final.blend')) == metrics['drive_top']['roi_scene_sha256']
write_json(TRIAL/'verification.json',dict(
    status='PASS' if paper[0]['paper_accepted'] else 'PAPER_GATE_FAILED; review only',
    protected_count=len(before['protected']),paper_count=sum('_paper.' in p for p in before['protected']),
    changed_protected=changed,added_protected=added,original_scripts_unchanged=source_ok,
    scene_copy_unchanged=True,renderer_checks=script_checks,
    base_only_render=True,paper_gate_accepted=paper[0]['paper_accepted'],
    screenshots_1440x1000=True,screenshot_changed_pixels=shot_changed_pixels,
    trial_png_is_raw_output=True,errors=[],csp=[],fixed_layout_equal=True,
    visual_approval='PENDING_REVIEW',drive_layer='UNCHANGED_OVERLAY',
    free_bytes={d:shutil.disk_usage(d+':/').free for d in ('D','F')}))
print('Verified',len(before['protected']),'protected files; paper gate',paper[0]['paper_accepted'])
