import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'evidence/editor'

def main():
    shots=E/'screenshots'
    if len(sys.argv)>1 and sys.argv[1]=='integration':
        capture=json.loads((shots/'browser-compose.json').read_text(encoding='utf8'))
        work=E/'browser-work.discdesign';work.write_text(json.dumps(capture['document']),encoding='utf8')
        target=E/'browser-cli.npy'
        subprocess.run([sys.executable,'-m','discprobe','compose',str(work),'--out',str(target)],check=True,cwd=ROOT,capture_output=True)
        cli=np.load(target,mmap_mode='r');api=np.load(ROOT/capture['saved']['design_npy'],mmap_mode='r')
        result=dict(page_sha256=capture['page_sha256'],cli_sha256=hashlib.sha256(cli.tobytes()).hexdigest(),api_sha256=hashlib.sha256(api.tobytes()).hexdigest(),shape=list(cli.shape),textures=len(capture['saved']['textures']))
        result['pass']=len({result[k] for k in ('page_sha256','cli_sha256','api_sha256')})==1
        (E/'browser-compose-parity.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        print(json.dumps(result));assert result['pass']
        del cli,api
        target.unlink();target.with_suffix('.textures.json').unlink()
        (shots/'browser-compose.json').unlink()
        return
    records=[]
    names=['empty','imports','rectangle','lasso','ring','sector','colour','ring-material','diamond','materials','undo']
    for theme in ('light','dark'):
        for lang in ('zh','en'):
            board=Image.new('RGB',(1440,1280),(235,231,224));draw=ImageDraw.Draw(board)
            for i,name in enumerate(names):
                p=shots/f'{theme}-{lang}-{name}.png'
                with Image.open(p) as im:
                    assert im.size==(2880,1800),(p,im.size)
                    records.append(dict(file=p.name,width=im.width,height=im.height,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
                    im.thumbnail((470,294));x=(i%3)*480;y=(i//3)*320;board.paste(im,(x,y+20));draw.text((x+5,y+3),name,fill=(29,27,24))
            board.save(E/f'contact-{theme}-{lang}.png')
    (E/'screenshot-manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    errors=json.loads((shots/'browser-errors.json').read_text(encoding='utf8'));assert not errors,errors
    print(f'{len(records)} screenshots verified at 1440x900, scale 2; no Runtime exceptions')

if __name__=='__main__':main()
