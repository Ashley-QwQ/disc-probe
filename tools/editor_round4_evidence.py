"""Release provenance, screenshot matrix, and exact CLI parity at canvas size."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from PIL import Image,ImageDraw
from tools.editor_round2_evidence import failures,read_log

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/editor/round4'
RELEASE=Path('C:/Users/ADMINI~1/AppData/Local/Temp/claude/0fa2f3b7e932577a/fde171e6-4972-4732-87f2-afa80208e6c0/scratchpad/rel0121')
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def evidence():
    sources=[]
    for name,target in [('disc-probe-simulated-dvd.png','release-reference.png'),('disc-probe-simulated-sheet.png','release-sheet-reference.png')]:
        source=RELEASE/name;shutil.copyfile(source,OUT/target)
        sources.append(dict(file=target,original=str(source),sha256=digest(source),release='v0.1.2.1'))
    source=ROOT/'docs/showcase/figures_design.png'
    sources.append(dict(file=str(source.relative_to(ROOT)),sha256=digest(source),use='bundled artwork imported as a layer; width 116 mm, clockwise rotation 36 degrees'))
    sources.append(dict(file='discprobe/simulate.py',sha256=digest(ROOT/'discprobe/simulate.py'),use='shared CLI/API optical renderer'))
    (OUT/'provenance.json').write_text(json.dumps(sources,indent=2),encoding='utf8')
    manifest=[]
    for theme in ['light','dark']:
        for lang in ['zh','en']:
            prefix=f'{theme}-{lang}'
            for state in ['ring-progress','ring-lamp','picture-lamp']:
                path=OUT/f'{prefix}-{state}.png'
                with Image.open(path) as image:assert image.size==(2880,1800)
                manifest.append(dict(file=path.name,width=2880,height=1800,sha256=digest(path)))
            for state in ['ring','picture']:
                checks=json.loads((OUT/f'{prefix}-{state}-checks.json').read_text(encoding='utf8'))
                assert checks['passed'] and checks['phase']=='ready' and checks['radialChroma']>15
                assert [(r['size'],r['quality']) for r in checks['requests']]==[(200,'draft'),(checks['size'],'full')]
            sheet=Image.new('RGB',(2340,940),'#ebe7e0');draw=ImageDraw.Draw(sheet)
            with Image.open(OUT/f'{prefix}-picture-lamp.png') as image:sheet.paste(image.convert('RGB').resize((1440,900)),(0,40))
            with Image.open(OUT/'release-reference.png') as image:sheet.paste(image.convert('RGB').resize((900,900)),(1440,40))
            draw.text((12,12),f'Editor core simulation / {theme} / {lang} / bundled figures artwork',fill='#1d1b18')
            draw.text((1452,12),'v0.1.2.1 release image / reference',fill='#1d1b18')
            sheet.save(OUT/f'{prefix}-picture-vs-release.png')
    sheet=Image.new('RGB',(1440,940),'#ebe7e0');draw=ImageDraw.Draw(sheet)
    for n,theme in enumerate(['light','dark']):
        for i,state in enumerate(['ring-lamp','picture-lamp']):
            with Image.open(OUT/f'{theme}-zh-{state}.png') as image:sheet.paste(image.convert('RGB').resize((720,450)),(i*720,n*470+20))
            draw.text((i*720+8,n*470+4),f'{theme} / {state}',fill='#1d1b18')
    sheet.save(OUT/'contact.png')
    (OUT/'screenshots.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    assert json.loads((OUT/'browser-errors.json').read_text(encoding='utf8'))==[]
    print('12 screenshots, four release comparisons, no browser exceptions')


def parity():
    results=[]
    for state in ['ring','picture']:
        checks=json.loads((OUT/f'light-zh-{state}-checks.json').read_text(encoding='utf8'))
        target=OUT/f'cli-{state}.png';pose=checks['pose']
        subprocess.run([sys.executable,'-m','discprobe','simulate','--work',str(OUT/f'light-zh-{state}-work.json'),
                        '--size',str(checks['size']),'--camera',*map(str,pose['camera']),'--flash',*map(str,pose['flash']),
                        '--output',str(target)],cwd=ROOT,check=True,capture_output=True,timeout=180)
        actual=digest(target);expected=checks['requests'][-1]['png_sha256']
        assert actual==expected
        results.append(dict(state=state,size=checks['size'],http_png_sha256=expected,cli_png_sha256=actual,png_bytes_identical=True))
    (OUT/'canvas-cli-parity.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print('Ring and picture: CLI PNG bytes equal the actual canvas API images')


def compare():
    base=failures(ROOT/'evidence/editor/round2/selftest-base-ac41295.txt');current=failures(OUT/'selftest.txt')
    result=dict(base_commit='ac41295',baseline_failed_checks=len(base),current_failed_checks=len(current),
                unchanged=sorted(set(base)&set(current)),new_failures=sorted(set(current)-set(base)),
                removed_failures=sorted(set(base)-set(current)),
                editor_ops_pass='ok    test_editor_ops passes' in read_log(OUT/'selftest.txt'),
                editor_preview_pass='ok    test_editor_preview passes' in read_log(OUT/'selftest.txt'))
    (OUT/'selftest-comparison.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    assert len(base)==len(current)==11 and not result['new_failures'] and not result['removed_failures'] and result['editor_ops_pass'] and result['editor_preview_pass']
    print('Selftest: same 11 baseline failures; no new failures; both editor modules pass')


if __name__=='__main__':
    {'parity':parity,'compare':compare}.get(sys.argv[1] if len(sys.argv)>1 else '',evidence)()
