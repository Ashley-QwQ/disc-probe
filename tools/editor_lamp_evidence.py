"""Hash the eight current captures and assemble paired view contact sheets."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from tools.editor_round2_evidence import failures,read_log

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/editor/lamp'
manifest=[]
for theme,lang in [('light','zh'),('dark','zh'),('light','en'),('dark','en')]:
    sheet=Image.new('RGB',(1440,480),'#ebe7e0')
    draw=ImageDraw.Draw(sheet)
    for i,view in enumerate(['design','lamp']):
        path=OUT/f'{theme}-{lang}-ring-{view}.png'
        with Image.open(path) as image:
            assert image.size==(2880,1800)
            sheet.paste(image.convert('RGB').resize((720,450)),(i*720,30))
        draw.text((i*720+12,8),f'{theme} / {lang} / {view}',fill='#1d1b18')
        manifest.append(dict(file=path.name,size=[2880,1800],sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    sheet.save(OUT/f'{theme}-{lang}-comparison.png')
(OUT/'screenshots.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
assert json.loads((OUT/'browser-errors.json').read_text(encoding='utf8'))==[]
print('8 screenshots: 2880 x 1800; four paired sheets; browser exceptions: 0')
if (OUT/'selftest.txt').exists():
    baseline=failures(ROOT/'evidence/editor/round2/selftest-base-ac41295.txt')
    current=failures(OUT/'selftest.txt')
    result=dict(base_commit='ac41295',baseline_failed_checks=len(baseline),current_failed_checks=len(current),
                unchanged=sorted(set(baseline)&set(current)),new_failures=sorted(set(current)-set(baseline)),
                removed_failures=sorted(set(baseline)-set(current)),
                editor_selftest_pass='ok    test_editor_ops passes' in read_log(OUT/'selftest.txt'))
    (OUT/'selftest-comparison.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    assert len(baseline)==len(current)==11 and not result['new_failures'] and not result['removed_failures'] and result['editor_selftest_pass']
    print('selftest: same 11 baseline failures; no new failures; editor checks pass')
