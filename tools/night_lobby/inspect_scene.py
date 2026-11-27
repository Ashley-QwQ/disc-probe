"""Read-only scene preflight and semantic pixel-measurement anchors (Blender)."""
import json
from pathlib import Path
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

scene = bpy.context.scene
meta = json.loads(scene['desk_meta'])
pool = json.loads(scene['pool'])
w, h = meta['image_size']


def project(point):
    p = world_to_camera_view(scene, scene.camera, Vector(point))
    return [p.x * w, (1 - p.y) * h]


meshes = [o for o in scene.objects if o.type == 'MESH']
facing = [o for o in meshes if o.get('kind', 'facing') == 'facing']
bands = [o for o in meshes if o.get('kind') == 'bands']
nolines = [o for o in facing if o.get('nolines') or o.name.endswith(('_string', '_chain'))]
ids = {o.name: i + 1 for i, o in enumerate(o for o in facing if o not in nolines)}
ids.update({o.name: 500 + i for i, o in enumerate(bands)})
ids.update({o.name: 800 + i for i, o in enumerate(nolines)})
objects = []
for o in meshes:
    objects.append(dict(name=o.name, id=ids[o.name], layer=o.get('layer'), mat=o.get('mat'),
                        kind=o.get('kind', 'facing'), vertices=len(o.data.vertices),
                        faces=len(o.data.polygons), bbox_px=[project(o.matrix_world @ Vector(v)) for v in o.bound_box]))
out = dict(blender=bpy.app.version_string, engine=scene.render.engine,
           camera=scene.camera.name, world=scene.world.name if scene.world else None,
           collections=[c.name for c in scene.collection.children], pool=pool, meta=meta,
           pool_center_px=project(pool['center']), objects=objects,
           validation=dict(scope='read-only existing scene; lighting trial only',
                           topology='not_evaluated; unchanged source scene',
                           camera_preserved=True, geometry_modified=False))
Path('F:/dp-archive/tmp/lobbypool/trial/scene-inspection.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('SCENE_PREFLIGHT', bpy.app.version_string, scene.camera.name, meta['image_size'], pool)
