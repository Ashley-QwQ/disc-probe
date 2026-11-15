"""Compare unchanged SHOW-E cells: legacy .93/old height against physical new height.

No fitting or texture reselection. Per-material and all 18 ruler-block delta residuals
are numerical prediction checks, not new observations of the burned disc.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe import focal as F, simulate_a3

DATA=ROOT/'tools/focal_data'


def fixture_bytes():
    return gzip.decompress((DATA/'show_e_samples.json.gz').read_bytes())


def residual(x,y):
    old=F.along_track(x,y,(0,F.LENS_Y_MM,F.LEGACY_DISC_HEIGHT_MM),
                      (0,F.FLASH_Y_MM,F.LEGACY_DISC_HEIGHT_MM))*.93
    new=F.along_track(x,y)
    diff=new-old
    return dict(samples=int(diff.size),old_mean=float(old.mean()),new_mean=float(new.mean()),
                signed_mean=float(diff.mean()),abs_p95=float(np.quantile(abs(diff),.95)),
                abs_max=float(abs(diff).max()))


def calculate():
    raw=fixture_bytes()
    fixture=json.loads(raw)
    rows=[]
    for m in fixture['materials']:
        xy=np.array(m['xy_mm'])
        row=dict(label=m['label'],spec=m['spec'],source_cells=m['source_cells'])
        if len(xy):
            row.update(residual(xy[:,0],xy[:,1]))
            if m['period_um']:
                row['max_first_order_wavelength_shift_nm']=row['abs_max']*m['period_um']*1000
        else:
            row['status']='no original cells'
        rows.append(row)
    patches=[]
    # Uniform sampling of each saved ruler block, with the original block boundaries.
    for p in fixture['ruler_patches']:
        r=np.linspace(*p['r_mm'],17)
        a=np.radians(np.linspace(*p['ang_deg'],17))
        x=r[:,None]*np.sin(a)[None,:]
        y=r[:,None]*np.cos(a)[None,:]  # original angles clockwise from 12 o'clock
        patches.append(dict(station=p['station'],colour=p['colour'],arm=p['arm'],
                            **residual(x,y)))
    return dict(schema_version=1,name=fixture['name'],old=dict(focal_px=F.LEGACY_VIDEO_FOCAL_PX,
                camera_z_mm=F.LEGACY_DISC_HEIGHT_MM,delta_scale=.93),
                new=dict(focal_px=F.VIDEO_FOCAL_PX,camera_z_mm=F.DESIGN_Z_MM,table_height_mm=F.TABLE_HEIGHT_MM,delta_scale=1),
                fixture_sha256=hashlib.sha256(raw).hexdigest(),
                geometry_sha256=hashlib.sha256((ROOT/'discprobe/focal.py').read_bytes()).hexdigest(),
                materials=rows,ruler_patches=patches,
                max_abs_delta=max(r.get('abs_max',0) for r in rows),
                interpretation='nonzero spatial residual: changing height is not a scalar; no parameters fitted',
                prior_alpha_preview=fixture['prior_alpha_preview'])


def previews(out):
    from PIL import Image, ImageDraw
    fixture=json.loads(fixture_bytes())
    mats=[dict(id=str(m['label']),spec=m['spec'],period_um=m['period_um']) for m in fixture['materials']]
    # A5/6F etc are table entries; only off-table periods use the original report.
    labels=np.load(DATA/'show_e_preview.npz',allow_pickle=False)['labels']
    old=simulate_a3.render(labels,600,materials=mats,camera=(0,F.LENS_Y_MM,F.LEGACY_DISC_HEIGHT_MM),
                           flash=(0,F.FLASH_Y_MM,F.LEGACY_DISC_HEIGHT_MM),delta_scale=.93,fine=False)
    new=simulate_a3.render(labels,600,materials=mats,camera=F.CAMERA,flash=F.FLASH,fine=False)
    old.save(out/'show_e_old_reconstructed.png');new.save(out/'show_e_new.png')
    canvas=Image.new('RGB',(1200,635),'white')
    canvas.paste(old,(0,35));canvas.paste(new,(600,35))
    draw=ImageDraw.Draw(canvas)
    draw.text((10,10),'OLD: .93, 206.5mm (reconstructed)',fill='black')
    draw.text((610,10),f'NEW: 1, {F.DESIGN_Z_MM:.4f}mm',fill='black')
    canvas.save(out/'show_e_comparison.png')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=Path('D:/dp-dev/tmp/focal'))
    ap.add_argument('--previews',action='store_true')
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    result=calculate()
    (args.out/'regression.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if args.previews:previews(args.out)
    print('fixed-label max abs delta',result['max_abs_delta'],'ruler blocks',len(result['ruler_patches']))


if __name__=='__main__':main()
