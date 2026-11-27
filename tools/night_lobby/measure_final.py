"""Measure actual exported lobby surfaces; keep warm materials out of desk checks."""
import argparse
import ast
import json
import io
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion,maximum_filter,minimum_filter

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
HOME=ROOT/'discprobe/web/home/lobby'
meta=json.loads((HOME/'lobby.json').read_text(encoding='utf-8'))
boxes={r['name']:r['box'] for r in meta['layers']}
tree=ast.parse((ROOT/'tools/night_lobby/measure_trial.py').read_text(encoding='utf-8'))
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='lightness')
ns={'np':np};exec(compile(ast.Module(body=[node],type_ignores=[]),'<CIELAB>','exec'),ns)
lightness=ns['lightness']


def oklch(rgb):
    a=np.asarray(rgb,dtype=np.float64)/255
    a=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
    lms=a@np.array([[.4122214708,.5363325363,.0514459929],
        [.2119034982,.6806995451,.1073969566],[.0883024619,.2817188376,.6299787005]]).T
    lab=np.cbrt(lms)@np.array([[.2104542553,.793617785,-.0040720468],
        [1.9779984951,-2.428592205,.4505937099],[.0259040371,.7827717662,-.808675766]]).T
    return lab[...,0],np.hypot(lab[...,1],lab[...,2]),np.degrees(np.arctan2(lab[...,2],lab[...,1]))%360


def drive(prewrite):
    x0,y0,x1,y1=boxes['newplan']
    path=FINAL/'L_lobby3/desk_newplan_dark.png' if prewrite else HOME/'newplan_dark.webp'
    image=Image.open(path).convert('RGBA')
    if prewrite:image=image.crop((x0,y0,x1,y1))
    a=np.asarray(image)
    mask=np.asarray(Image.open(FINAL.parent/'trial2/drive-top-mask.png'))>0
    rgb=a[...,:3].astype(np.int16)
    local=(maximum_filter(rgb,size=(7,7,1))-minimum_filter(rgb,size=(7,7,1))).max(2)
    mask&=(a[...,3]==255)&(local<=6)
    l=lightness(a)
    base=np.asarray(Image.open(FINAL/'F_lobby_a/desk_base_dark.png' if prewrite else HOME/'base_dark.webp').convert('RGB'))
    desktop=float(lightness(base[1074,842]))
    ys,xs=np.nonzero(mask);values=l[mask]
    lo=int(values.argmin());hi=int(values.argmax())
    row=dict(source=str(path),surface='top-cover upward faces, 3px edge and internal-line guard',pixels=int(mask.sum()),
        desktop=dict(xy=[842,1074],L_star=desktop),
        brightest=dict(xy=[int(xs[hi]+x0),int(ys[hi]+y0)],L_star=float(values[hi])),
        darkest=dict(xy=[int(xs[lo]+x0),int(ys[lo]+y0)],L_star=float(values[lo])),
        min_contrast=float(values[lo]-desktop),required_contrast=6.,hero_override_required=bool(values[lo]-desktop<6))
    (FINAL/('drive-prewrite.json' if prewrite else 'drive-written.json')).write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(row,indent=2))


def surfaces(prewrite=False):
    def candidate(layer):
        image=Image.open(FINAL/f'F_lobby_a/desk_{layer}_dark.png').convert('RGB' if layer=='base' else 'RGBA').crop(boxes[layer])
        stream=io.BytesIO();image.save(stream,'WEBP',quality=92,method=6,exact=True)
        return np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert('RGB' if layer=='base' else 'RGBA'))
    # Exact desk object ID only: lamp shade, kraft bags, LED and props cannot enter this mask.
    desk=binary_erosion(np.load(FINAL/'desk-coverage.npy')>=.999,iterations=3)
    for layer in meta['layers']:
        if layer['name']=='base' or layer.get('hidden'):continue
        x0,y0,x1,y1=layer['box']
        alpha=np.asarray(Image.open(HOME/(layer['name']+'_dark.webp')).convert('RGBA'))[...,3]
        desk[y0:y1,x0:x1]&=~(alpha>0)
    desk=binary_erosion(desk,iterations=3)
    rgb=candidate('base') if prewrite else np.asarray(Image.open(HOME/'base_dark.webp').convert('RGB'))
    _,c,h=oklch(rgb)
    warm=desk&(h>=30)&(h<=90)&(c>.02)
    desk_row=dict(mask='desk_top object ID=1, full SS coverage, eroded, visible foreground alpha excluded; no kraft/shade/LED',
        pixels=int(desk.sum()),warm_pixels=int(warm.sum()),ratio=float(warm.sum()/desk.sum()),threshold='H in [30,90], C > .02')
    Image.fromarray(desk.astype(np.uint8)*255).save(FINAL/'desktop-only-mask.png')
    x0,y0,x1,y1=boxes['filebox']
    mask=binary_erosion(np.load(FINAL/'kraft-mask.npy'),iterations=3)[y0:y1,x0:x1]
    old=np.asarray(Image.open(FINAL/'old/filebox_dark.webp').convert('RGBA'))
    new=candidate('filebox') if prewrite else np.asarray(Image.open(HOME/'filebox_dark.webp').convert('RGBA'))
    for a in (old,new):
        signed=a[...,:3].astype(np.int16)
        ranges=(maximum_filter(signed,size=(7,7,1))-minimum_filter(signed,size=(7,7,1))).max(2)
        mask&=(ranges<=6)&(a[...,3]==255)
    _,co,ho=oklch(old[...,:3]);_,cn,hn=oklch(new[...,:3])
    # Kraft itself is a dark, low-chroma brown; the desk's .02 warmth threshold
    # must not discard those kraft pixels from this separate hue comparison.
    mask&=(co>.005)&(cn>.005)
    delta=(hn-ho+180)%360-180
    def mean_hue(values):return float(np.degrees(np.arctan2(np.sin(np.radians(values)).mean(),np.cos(np.radians(values)).mean()))%360)
    old_h=mean_hue(ho[mask]);new_h=mean_hue(hn[mask]);shift=abs((new_h-old_h+180)%360-180)
    kraft=dict(mask='semantic kraft-family filebox IDs, full coverage, eroded 3px, alpha=255, 7x7 RGB range<=6, C>.005 in both images',
        pixels=int(mask.sum()),old_hue_deg=old_h,new_hue_deg=new_h,mean_hue_shift_deg=shift,
        median_abs_paired_delta_deg=float(np.median(np.abs(delta[mask]))),
        p95_abs_paired_delta_deg=float(np.percentile(np.abs(delta[mask]),95)),
        max_abs_paired_delta_deg=float(np.max(np.abs(delta[mask]))),
        fraction_over_3deg=float((np.abs(delta[mask])>3).mean()),material_hue_within_3deg=bool(shift<=3))
    Image.fromarray(mask.astype(np.uint8)*255).save(FINAL/'kraft-comparison-mask.png')
    result=dict(desktop_warm=desk_row,kraft_hue=kraft)
    (FINAL/('surface-prewrite.json' if prewrite else 'surface-check.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


p=argparse.ArgumentParser();p.add_argument('action',choices=['drive-prewrite','drive-written','surfaces','prewrite-surfaces']);args=p.parse_args()
if args.action in ('surfaces','prewrite-surfaces'):surfaces(args.action=='prewrite-surfaces')
else:drive(args.action=='drive-prewrite')
