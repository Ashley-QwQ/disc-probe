"""Render all Letter PDF pages and compare against the original read-only PDF.

PyMuPDF is used when this Windows host has no pdftoppm. The original document is
an optional one-time reference; future checks can use --reference with the old PDF.
"""
import argparse
import json
from pathlib import Path
import sys

import pymupdf as fitz
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe import focal as F
from discprobe.hashing import file_sha256


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=Path('D:/dp-dev/tmp/focal'))
    ap.add_argument('--reference',type=Path,default=Path('D:/disc-probe/docs/goals/showcase/template/dp_rulers_1x_21cm_letter.pdf'))
    args=ap.parse_args();out=args.out
    docs=[fitz.open(args.reference),fitz.open(out/'dp_rulers_1x_new_letter.pdf')]
    assert all(len(d)==3 for d in docs)
    pairs=[];differences=[]
    for i in range(3):
        pages=[]
        for name,doc in zip(('original','new'),docs):
            page=doc[i]
            assert abs(page.rect.width-612)<.01 and abs(page.rect.height-792)<.01
            pix=page.get_pixmap(matrix=fitz.Matrix(110/72,110/72),alpha=False)
            im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            im.save(out/f'pdf_{name}_page{i+1}.png');pages.append(im)
        a,b=map(np.array,pages)
        diff=np.any(a!=b,axis=2)
        differences.append(dict(page=i+1,different_pixels=int(diff.sum()),total_pixels=int(diff.size)))
        pair=Image.new('RGB',(pages[0].width*2,pages[0].height+30),'#dddddd')
        for j,im in enumerate(pages):pair.paste(im,(j*im.width,30))
        draw=ImageDraw.Draw(pair);draw.text((10,8),'ORIGINAL',fill='black');draw.text((pages[0].width+10,8),'NEW',fill='black')
        pairs.append(pair)
    assert differences[0]['different_pixels']>0
    assert all(d['different_pixels']==0 for d in differences[1:]),differences
    combined=Image.new('RGB',(pairs[0].width,sum(p.height for p in pairs)),'white')
    y=0
    for p in pairs:combined.paste(p,(0,y));y+=p.height
    combined.save(out/'rulers_comparison.png')
    text=docs[1][0].get_text()
    assert f'{F.TABLE_HEIGHT_MM:.1f}' in text and f'{F.DESIGN_Z_MM:.1f}' in text
    result=dict(renderer='PyMuPDF (pdftoppm unavailable on this host)',pages=differences,
                paper='US Letter 612 x 792 pt, 100 percent',
                reference=str(args.reference),reference_sha256=file_sha256(args.reference))
    (out/'rulers_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
