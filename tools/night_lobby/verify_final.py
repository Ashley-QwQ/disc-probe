"""Bounded final validation: protected source, exact publication and actual surface checks."""
import ast
import json
from pathlib import Path
import shutil
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_trial import sha,write_json

pre=json.loads((FINAL/'preflight.json').read_text(encoding='utf-8'))
decision=json.loads((FINAL/'export-decision.json').read_text(encoding='utf-8'))
written=set(decision['written_layers']);kept=set(decision['kept_layers'])
assert len(written|kept)==9 and not written&kept
allowed={f'discprobe/web/home/lobby/{name}_dark.webp' for name in written}|{'tools/night_b_manifest.json','tools/night_b_export_report.json'}
unchanged={p:h for p,h in pre['protected'].items() if p not in allowed}
assert all(sha(ROOT/p)==h for p,h in unchanged.items())
for name in kept:assert sha(ROOT/f'discprobe/web/home/lobby/{name}_dark.webp')==sha(FINAL/f'old/{name}_dark.webp')
manifest=json.loads((ROOT/'tools/night_b_manifest.json').read_text(encoding='utf-8'))
assert {p:r for p,r in manifest['pictures'].items() if '/lobby/' not in p}=={p:r for p,r in pre['manifest']['pictures'].items() if '/lobby/' not in p}
before_report={Path(r['file']).as_posix():r for r in pre['export_report'] if Path(r['file']).parts[0]!='lobby'}
after_report={Path(r['file']).as_posix():r for r in json.loads((ROOT/'tools/night_b_export_report.json').read_text(encoding='utf-8')) if Path(r['file']).parts[0]!='lobby'}
assert before_report==after_report
for name,digest in pre['scripts'].items():assert sha(ROOT/'tools/night_lobby'/name)==digest and sha(FINAL/'stage'/name)==digest
scenes=json.loads((FINAL/'scenes.json').read_text(encoding='utf-8'))
assert all(sha(FINAL/'stage'/name)==r['sha256'] for name,r in scenes.items())
for name,r in json.loads((FINAL/'base-reused.json').read_text(encoding='utf-8')).items():
    assert sha(FINAL/'F_lobby_a'/name)==sha(Path(r['source']))==r['sha256']
jobs=[]
for job in ['F_lobby_a','F_lobby_b','F_lobby_c','F_lobby_d','L_round5','L_lobby3','G_lamp']:
    run=json.loads((FINAL/(job+'-run.json')).read_text(encoding='utf-8'))
    assert run['exit']==0 and run['device']=='CPU' and run['threads']==8
    for layer in run['rendered_layers']:
        data=json.loads((FINAL/job/f'render_{layer}.json').read_text(encoding='utf-8'))
        p=data['night_pool_trial'];assert data['ss']==4 and p['amb']==.64 and p['gain']==5.8 and p['add']==0 and p['sigma_dark']==.42 and p['device']=='CPU'
    jobs.append(dict(job=job,seconds=run['seconds'],rendered_layers=run['rendered_layers'],reused_layers=run['reused_layers']))
warm=json.loads((FINAL/'surface-check.json').read_text(encoding='utf-8'))
drive=json.loads((FINAL/'drive-prewrite.json').read_text(encoding='utf-8'))
assert drive['min_contrast']>=6 and not drive['hero_override_required']
actual_drive=json.loads((FINAL/'drive-written.json').read_text(encoding='utf-8'))
assert actual_drive['min_contrast']>=6
assert warm['desktop_warm']['warm_pixels']==0 and warm['kraft_hue']['material_hue_within_3deg']
capture=json.loads((FINAL/'capture.json').read_text(encoding='utf-8'))
assert len(capture)==4 and {r['mode'] for r in capture}=={'lobby','newplan','faxnews','pastworks'}
for r in capture:
    assert r['theme']=='dark' and not r['errors'] and not r['csp']
    assert Image.open(FINAL/(r['name']+'.png')).size==(1440,1000)
for p in (ROOT/'tools/night_lobby').glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
ast.parse((ROOT/'tools/night_b_export.py').read_text(encoding='utf-8'))
write_json(FINAL/'verification.json',dict(written_layers=sorted(written),kept_layers=sorted(kept),
    protected_count=len(unchanged),paper_count=sum('_paper.' in p for p in unchanged),changed_protected=[],
    non_lobby_manifest_unchanged=True,non_lobby_export_report_unchanged=True,scripts_and_scenes_unchanged=True,
    reused_base_exact=True,jobs=jobs,hero_override=False,drive_min_contrast=drive['min_contrast'],
    published_drive_min_contrast=actual_drive['min_contrast'],
    desktop_warm=warm['desktop_warm'],kraft_hue=warm['kraft_hue'],screenshots=4,errors=[],
    free_bytes={d:shutil.disk_usage(d+':/').free for d in ('D','F')}))
print('Verified final publication:',len(written),'written;',len(kept),'retained;',len(unchanged),'protected files unchanged')
