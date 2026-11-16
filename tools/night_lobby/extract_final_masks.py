"""Blender background: filebox kraft-only IDs, excluding lines and other materials."""
import json
from pathlib import Path
import bpy
import numpy as np

root=Path('F:/dp-archive/tmp/lobbypool/final')
inventory=json.loads((root/'scene-inspection.json').read_text(encoding='utf-8'))
objects=[o for o in inventory['objects'] if o['layer']=='filebox' and str(o['mat']).startswith('kraft')]
ids=[o['id'] for o in objects]
assert ids
image=bpy.data.images.load(str(root/'F_lobby_a/raw_filebox_id.exr'),check_existing=False)
image.colorspace_settings.name='Non-Color'
w,h=image.size
a=np.empty(w*h*4,np.float32);image.pixels.foreach_get(a)
bpy.data.images.remove(image)
a=a.reshape(h,w,4)
mask=np.isin(np.rint(a[...,0]*1000).astype(np.int32),ids)&(a[...,3]>.99)
coverage=mask.reshape(1791,4,2560,4).mean(axis=(1,3))[::-1]
safe=coverage>=.999
np.save(root/'kraft-mask.npy',safe)
(root/'kraft-mask.json').write_text(json.dumps(dict(objects=objects,ids=ids,pixels=int(safe.sum()),
    method='F_lobby_a filebox raw object IDs, all SS subpixels, alpha>.99; host measurement erodes 3px'),indent=2)+'\n',encoding='utf-8')
print('KRAFT_MASK',ids,int(safe.sum()))
