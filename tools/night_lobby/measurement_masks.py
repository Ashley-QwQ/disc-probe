"""Extract desk ID coverage and project unchanged drive top from the existing scene."""
import json
import hashlib
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

TRIAL = Path('F:/dp-archive/tmp/lobbypool/trial')
scene = bpy.context.scene
meta = json.loads(scene['desk_meta'])
w, h = meta['image_size']
image = bpy.data.images.load(str(TRIAL / 'F_lobby_a/raw_base_id.exr'), check_existing=False)
image.colorspace_settings.name = 'Non-Color'
iw, ih = image.size
a = np.empty(iw * ih * 4, np.float32)
image.pixels.foreach_get(a)
bpy.data.images.remove(image)
a = a.reshape(ih, iw, 4)
ss = iw // w
mask = (np.rint(a[:, :, 0] * 1000) == 1) & (a[:, :, 3] > .99)
coverage = mask.reshape(h, ss, w, ss).mean(axis=(1, 3))[::-1]
np.save(TRIAL / 'desk-coverage.npy', coverage.astype(np.float32))
del a, mask, coverage
# The committed visible drive was rendered from this scene, not the base scene.
drive_scene = Path('D:/disc-probe/art/desk/room_lobby3_final.blend')
drive_sha = hashlib.sha256(drive_scene.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(drive_scene), use_scripts=False)
scene = bpy.context.scene
assert json.loads(scene['desk_meta'])['image_size'] == [w, h]
top = bpy.data.objects['drv_SHELL_top_cover']
normal_matrix = top.matrix_world.to_3x3().inverted().transposed()
polys = []
for poly in top.data.polygons:
    normal = (normal_matrix @ poly.normal).normalized()
    if normal.z <= .55:
        continue
    pts = []
    for i in poly.vertices:
        q = world_to_camera_view(scene, scene.camera, top.matrix_world @ top.data.vertices[i].co)
        pts.append([q.x * w, (1 - q.y) * h])
    polys.append(pts)
(TRIAL / 'drive-top-polygons.json').write_text(json.dumps(dict(
    source=str(drive_scene) + ': drv_SHELL_top_cover world normal z > .55',
    sha256=drive_sha, caveat='unchanged old newplan layer, not newly rendered in this base-only round',
    polygons=polys), indent=2) + '\n', encoding='utf-8')
print('MASKS', w, h, ss, len(polys))
