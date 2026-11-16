"""Blender: compare new decoded ID coverage with the frozen first-round mask."""
import hashlib
import json
from pathlib import Path
import bpy
import numpy as np

root=Path('F:/dp-archive/tmp/lobbypool/trial2')
image=bpy.data.images.load(str(root/'F_lobby_a/raw_base_id.exr'),check_existing=False)
image.colorspace_settings.name='Non-Color'
w,h=image.size
a=np.empty(w*h*4,np.float32)
image.pixels.foreach_get(a)
bpy.data.images.remove(image)
a=a.reshape(h,w,4)
mask=(np.rint(a[...,0]*1000)==1)&(a[...,3]>.99)
coverage=mask.reshape(1791,4,2560,4).mean(axis=(1,3))[::-1].astype(np.float32)
expected=np.load(root/'desk-coverage.npy')
changed=int(np.count_nonzero(coverage!=expected))
record=dict(decoded_coverage_changed_pixels=changed,shape=list(coverage.shape),
    max_difference=float(np.max(np.abs(coverage-expected))),
    note='Compare decoded desktop-ID coverage, not EXR container hashes; camera/scene byte hashes separately protected')
(root/'geometry-check.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('GEOMETRY_CHECK',record)
assert changed==0
