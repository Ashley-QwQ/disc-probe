"""CIELAB L* on fixed semantic masks; distinguish new base from unchanged drive."""
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, binary_dilation, maximum_filter, minimum_filter

ROOT = Path(__file__).resolve().parents[2]
TRIAL = Path(os.environ.get('LOBBY_TRIAL', 'F:/dp-archive/tmp/lobbypool/trial'))
HOME = ROOT / 'discprobe/web/home/lobby'
inspection = json.loads((TRIAL / 'scene-inspection.json').read_text(encoding='utf-8'))
metadata = json.loads((HOME / 'lobby.json').read_text(encoding='utf-8'))
w, h = metadata['size']
coverage = np.load(TRIAL / 'desk-coverage.npy')
desk = binary_erosion(coverage >= .999, iterations=3)
# Exclude actual foreground alpha, plus a 3px boundary guard.
obscured = np.zeros((h,w),dtype=bool)
for layer in metadata['layers']:
    if layer['name'] == 'base' or layer.get('hidden'):
        continue
    x0,y0,x1,y1 = layer['box']
    alpha = np.asarray(Image.open(HOME/(layer['name']+'_dark.webp')).convert('RGBA'))[...,3]
    obscured[y0:y1,x0:x1] |= alpha > 0
desk &= ~binary_dilation(obscured,iterations=3)
center = inspection['pool_center_px']
ys, xs = np.nonzero(desk)
distance = (xs - center[0]) ** 2 + (ys - center[1]) ** 2
chosen = int(distance.argmin())
cx, cy = int(xs[chosen]), int(ys[chosen])
near = desk & (np.indices((h,w))[0] >= cy-2) & (np.indices((h,w))[0] <= cy+2) & (np.indices((h,w))[1] >= cx-2) & (np.indices((h,w))[1] <= cx+2)


def lightness(rgb):
    s = np.asarray(rgb, dtype=np.float64)[..., :3] / 255
    linear = np.where(s <= .04045, s / 12.92, ((s + .055) / 1.055) ** 2.4)
    y = linear @ np.array([.2126,.7152,.0722])
    f = np.where(y > (6/29)**3, np.cbrt(y), y/(3*(6/29)**2)+4/29)
    return 116*f-16


def point(rgb, x, y):
    return dict(x=int(x),y=int(y),rgb=rgb[y,x,:3].tolist(),L_star=float(lightness(rgb[y,x])))


corners = {'top_left':[0,0,5,5], 'top_right':[w-5,0,w,5],
           'bottom_left':[0,h-5,5,h], 'bottom_right':[w-5,h-5,w,h]}
rows = {}
images=[('old',TRIAL/'base_old_dark.webp'),('trial_png',TRIAL/'base_trial_dark.png'),
        ('trial_webp',TRIAL/'base_trial_dark.webp')]
if (TRIAL/'base_trial1_dark.png').exists():images.append(('trial1_png',TRIAL/'base_trial1_dark.png'))
for name, path in images:
    rgb = np.asarray(Image.open(path).convert('RGB'))
    l = lightness(rgb)
    rows[name] = dict(center_target_px=center, nearest_visible_desktop=point(rgb,cx,cy),
        distance_px=float(distance[chosen]**.5), center_patch_median_L_star=float(np.median(l[near])),
        center_patch_pixels=int(near.sum()),corners={key:dict(box=b, median_L_star=float(np.median(l[b[1]:b[3],b[0]:b[2]]))) for key,b in corners.items()})
polys = json.loads((TRIAL/'drive-top-polygons.json').read_text(encoding='utf-8'))
mask = Image.new('L',(w,h))
draw = ImageDraw.Draw(mask)
for poly in polys['polygons']:
    draw.polygon([tuple(p) for p in poly],fill=255)
mask = binary_erosion(np.asarray(mask)>0,iterations=3)
layer = next(l for l in metadata['layers'] if l['name']=='newplan')
x0,y0,x1,y1 = layer['box']
drive = np.asarray(Image.open(HOME/'newplan_dark.webp').convert('RGBA'))
mask = mask[y0:y1,x0:x1] & (drive[...,3] == 255)
# The mesh contains internal creases. Exclude their bright image-space outlines
# and their 3px neighbourhood rather than reporting line ink as surface brightness.
rgb = drive[...,:3].astype(np.int16)
local_range = (maximum_filter(rgb,size=(7,7,1))-minimum_filter(rgb,size=(7,7,1))).max(axis=2)
mask &= local_range <= 6
assert mask.any()
l = lightness(drive)
ys,xs = np.nonzero(mask)
hi = np.argmax(l[mask]); lo = np.argmin(l[mask])
drive_result = dict(status='UNCHANGED_OVERLAY; no new drive render in base-only trial',
    source='discprobe/web/home/lobby/newplan_dark.webp',roi_scene=polys['source'],
    roi_scene_sha256=polys['sha256'], pixels=int(mask.sum()), erosion_px=3,
    line_guard='7x7 local RGB range <=6 in every channel; exclude internal outline/crease neighbourhoods',
    brightest={**point(drive,int(xs[hi]),int(ys[hi])), 'global_xy':[int(xs[hi]+x0),int(ys[hi]+y0)]},
    darkest={**point(drive,int(xs[lo]),int(ys[lo])), 'global_xy':[int(xs[lo]+x0),int(ys[lo]+y0)]})
Image.fromarray(mask.astype(np.uint8)*255).save(TRIAL/'drive-top-mask.png')
Image.fromarray(desk.astype(np.uint8)*255).save(TRIAL/'visible-desk-mask.png')
out=dict(method='sRGB inverse transfer -> D65 Y (.2126,.7152,.0722) -> CIELAB L*; raw base desktop ID=1, full SS coverage eroded 3px; visible foreground alpha>0 dilated 3px excluded; corners 5x5 median; drive projected top-cover faces eroded 3px',
         base=rows, drive_top=drive_result)
(TRIAL/'measurements.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
