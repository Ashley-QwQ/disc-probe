import hashlib
import json
from pathlib import Path
import re
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/editor/round2'
NAMES=['empty','imports','tool-select','tool-rectangle','tool-lasso','tool-ring','tool-sector','tool-colour','tool-shape','tool-pen','tool-hand','ring-material','diamond','materials','layers-selections']

def main():
    manifest=[]
    for theme in ('light','dark'):
        for lang in ('zh','en'):
            board=Image.new('RGB',(1440,1600),(235,231,224));draw=ImageDraw.Draw(board)
            for i,name in enumerate(NAMES):
                path=OUT/f'{theme}-{lang}-{name}.png'
                with Image.open(path) as im:
                    assert im.size==(2880,1800)
                    manifest.append(dict(file=path.name,width=im.width,height=im.height,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    im.thumbnail((470,294));x=(i%3)*480;y=(i//3)*320;board.paste(im,(x,y+20));draw.text((x+5,y+3),name,fill=(29,27,24))
            board.save(OUT/f'contact-{theme}-{lang}.png')
    assert json.loads((OUT/'browser-errors.json').read_text(encoding='utf8'))==[]
    (OUT/'screenshot-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(f'{len(manifest)} screenshots; 1440x900 scale2; no Runtime exceptions')

def read_log(path):
    raw=path.read_bytes()
    return raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')

def failures(path):
    return [line.split('FAIL',1)[1].strip() for line in read_log(path).splitlines() if re.match(r'^\s*FAIL\s',line)]

def compare():
    baseline=failures(OUT/'selftest-base-ac41295.txt');current=failures(OUT/'selftest-current.txt')
    key=lambda line:re.sub(r' \(\d+ checks\)','',line.split(' -- ',1)[0])
    old={key(line):line for line in baseline};new={key(line):line for line in current}
    result=dict(base_commit='ac41295e2f5fee816a878ce61f727dd39c60dc71',baseline_failed_checks=len(baseline),current_failed_checks=len(current),
        unchanged_failures=[old[k] for k in sorted(old.keys()&new.keys()) if old[k]==new[k]],
        changed_failures=[dict(check=k,baseline=old[k],current=new[k]) for k in sorted(old.keys()&new.keys()) if old[k]!=new[k]],
        new_failures=[new[k] for k in sorted(new.keys()-old.keys())],removed_failures=[old[k] for k in sorted(old.keys()-new.keys())],
        editor_selftest_pass=any('ok    test_editor_ops passes' in s for s in read_log(OUT/'selftest-current.txt').splitlines()))
    (OUT/'selftest-comparison.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':
    import sys
    compare() if len(sys.argv)>1 and sys.argv[1]=='compare' else main()
