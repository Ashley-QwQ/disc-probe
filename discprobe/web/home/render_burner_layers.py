"""Layered toon render of the optical burner for the disc-probe web home page.

Same camera, canvas, framing, palette and outline method as render_burner.py, but the
drive is split into separately rendered layers so the page can slide the tray:

    burner_body_<v>.png      drive shell + interior, tray and tray front plate hidden; the few
                             see-through pixels inside the empty slot get the cavity tone
    burner_tray_<v>.png      tray + its front plate only, fully OPEN (--open metres out along -Y)
    burner_traydisc_<v>.png  the same open tray with one 120 mm disc lying in its recess
    check_full_<v>.png       the unsplit scene again (only to verify it matches burner_<v>.png)
    burner.json              every key render_burner.py writes, plus the layer / slide / clip data

Run headless with Blender 5.2.2+ on a COPY of
docs/goals/video/hero/render_pack/disc_explode_render.blend:

    blender -b disc_explode_render.blend --python render_burner_layers.py -- \
        --outdir OUT [--long 1600] [--ss 4] [--open 0.14] [--variants paper,dark] [--device OPTIX]

Registration: the camera is framed on the unsplit scene (tray open, no disc), exactly as
render_burner.py does, so all layers share one pixel grid with burner_<v>.png. Each layer
gets its own normal / id passes, so its outlines are those of the objects it contains;
compositing tray over body with the clip polygon in burner.json reproduces the full render.

Clipping the tray (see "tray_clip" in burner.json): project any tray point along the view
direction onto the bezel front plane. A point outside the drive always lands left of the
slot's right edge and below the slot's top edge; a point inside the drive is visible only
through the slot, i.e. when it lands inside the slot. So the visible part of the tray, at
any slide position, is the tray layer cut by one fixed screen-space region: left of the
vertical through the slot's top-right corner and below the slot's top edge line.
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

# ---------------------------------------------------------------- arguments
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


OUTDIR = os.path.abspath(arg("--outdir", "out"))
LONG = int(arg("--long", "1600"))          # final long side, px
SS = int(arg("--ss", "4"))                 # supersampling factor
TRAY_OPEN = float(arg("--open", "0.14"))   # metres the tray slides out (-Y)
VARIANTS = arg("--variants", "paper,dark").split(",")
DEVICE = arg("--device", "OPTIX")
SAMPLES = int(arg("--samples", "16"))
LAYERS = arg("--layers", "full,body,tray,traydisc").split(",")
DISC_DIAMETER = float(arg("--disc", "0.120"))
os.makedirs(OUTDIR, exist_ok=True)

# ---------------------------------------------------------------- palettes (as render_burner.py)
VARIANT_STYLE = {
    "paper": dict(
        top="#f1eee8", front="#d9d4cb", side="#d0cac0",
        tray_mul=0.94, cavity="#bfb8ac", led="#b3ab9e",
        line="#2b2924", line_alpha=1.0,
        disc_top="#f7f7f4", disc_front="#e0dfda", disc_side="#d8d7d2",
    ),
    "dark": dict(
        top="#222b2a", front="#1a2221", side="#1d2625",
        tray_mul=0.93, cavity="#111716", led="#d9a75c",
        line="#d5d9d2", line_alpha=0.55,
        disc_top="#323a39", disc_front="#262d2c", disc_side="#29302f",
    ),
}
LINE_PX = 0.8
CREASE_DEG = 30.0
DEPTH_STEP_M = 0.0004
TOP_NZ = 0.55

TRAY_OBJECTS = {"KSL210_tray_final-1", "SHELL_tray_door", "SHELL_door_print"}
TRAY_BODY = "KSL210_tray_final-1"
TRAY_DOOR = "SHELL_tray_door"
BEZEL = "SHELL_bezel"
HIDE_OBJECTS = {"table", "Label_simulated", "SHELL_label_round", "SHELL_sticker_side",
                "SHELL_sticker_rear", "SHELL_door_print", "SHELL_badge",
                "KSL210_tray-1", "cd-1"}
HIDE_COLLECTIONS = {"Disc", "Overlay", "SW_hidden"}
BODY_PREFIX = "SHELL_"
LED_OBJECT = "SHELL_led"
DISC_OBJECT = "body"          # the polycarbonate disc mesh of the "Disc" collection
# 120 mm recess of the tray, closed position, from a circle fit of the tray mesh
# (the 80 mm recess ring r = 40.5 mm and the 120 mm recess ring are concentric there)
RECESS_GUESS_CLOSED = (0.0, 0.2175)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_srgb(h, mul=1.0):
    h = h.lstrip("#")
    return [min(1.0, int(h[i:i + 2], 16) / 255.0 * mul) for i in (0, 2, 4)]


def hex_lin(h, mul=1.0):
    return tuple(srgb_to_linear(c) for c in hex_srgb(h, mul)) + (1.0,)


# ---------------------------------------------------------------- scene freeze (as render_burner.py)
scene = bpy.context.scene
scene.frame_set(1)
deps = bpy.context.evaluated_depsgraph_get()

hidden_coll_objs = set()
for coll in bpy.data.collections:
    if coll.name in HIDE_COLLECTIONS:
        hidden_coll_objs.update(o.name for o in coll.all_objects)

frozen = {o.name: (o.evaluated_get(deps).matrix_world.copy(), bool(o.hide_render))
          for o in scene.objects}
for o in scene.objects:
    o.animation_data_clear()
    for c in list(o.constraints):
        o.constraints.remove(c)
for o in scene.objects:
    mw, hide = frozen[o.name]
    o.parent = None
    o.matrix_world = mw
    o.hide_render = hide or o.name in HIDE_OBJECTS or o.name in hidden_coll_objs
    if o.type in ("LIGHT", "FONT"):
        o.hide_render = True
for o in bpy.data.objects:
    if o.data is not None and getattr(o.data, "animation_data", None):
        o.data.animation_data_clear()
if scene.animation_data:
    scene.animation_data_clear()

for name in TRAY_OBJECTS:  # open the tray
    o = bpy.data.objects.get(name)
    if o:
        o.matrix_world = Matrix.Translation((0.0, -TRAY_OPEN, 0.0)) @ o.matrix_world

bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()

render_meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
for i, o in enumerate(render_meshes):
    o.pass_index = i + 1
print("[layers] visible meshes:", len(render_meshes))


def world_mesh(o):
    oe = o.evaluated_get(deps)
    me = oe.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(oe.matrix_world)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    polys = [tuple(p.vertices) for p in me.polygons]
    oe.to_mesh_clear()
    return co, polys


def world_verts(objs):
    return np.concatenate([world_mesh(o)[0] for o in objs])


# ---------------------------------------------------------------- shaders (as render_burner.py)


def new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Strength"].default_value = 1.0
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    return m, nt, emi


def facing_normal(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    flip = nt.nodes.new("ShaderNodeMath")
    flip.operation = "MULTIPLY_ADD"
    flip.inputs[1].default_value = -2.0
    flip.inputs[2].default_value = 1.0
    nt.links.new(geo.outputs["Backfacing"], flip.inputs[0])
    scl = nt.nodes.new("ShaderNodeVectorMath")
    scl.operation = "SCALE"
    nt.links.new(geo.outputs["Normal"], scl.inputs[0])
    nt.links.new(flip.outputs[0], scl.inputs["Scale"])
    return scl.outputs["Vector"]


def make_toon(name, top, front=None, side=None):
    m, nt, emi = new_mat(name)
    if front is None:
        emi.inputs["Color"].default_value = top
        return m
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(facing_normal(nt), sep.inputs[0])
    is_top = nt.nodes.new("ShaderNodeMath")
    is_top.operation = "GREATER_THAN"
    is_top.inputs[1].default_value = TOP_NZ
    nt.links.new(sep.outputs["Z"], is_top.inputs[0])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    nt.links.new(sep.outputs["X"], add.inputs[0])
    nt.links.new(sep.outputs["Y"], add.inputs[1])
    is_side = nt.nodes.new("ShaderNodeMath")
    is_side.operation = "GREATER_THAN"
    is_side.inputs[1].default_value = 0.0
    nt.links.new(add.outputs[0], is_side.inputs[0])
    mix1 = nt.nodes.new("ShaderNodeMix")
    mix1.data_type = "RGBA"
    nt.links.new(is_side.outputs[0], mix1.inputs["Factor"])
    mix1.inputs["A"].default_value = front
    mix1.inputs["B"].default_value = side
    mix2 = nt.nodes.new("ShaderNodeMix")
    mix2.data_type = "RGBA"
    nt.links.new(is_top.outputs[0], mix2.inputs["Factor"])
    nt.links.new(mix1.outputs["Result"], mix2.inputs["A"])
    mix2.inputs["B"].default_value = top
    nt.links.new(mix2.outputs["Result"], emi.inputs["Color"])
    return m


def make_normal_mat():
    m, nt, emi = new_mat("data_normal")
    vm = nt.nodes.new("ShaderNodeVectorMath")
    vm.operation = "MULTIPLY_ADD"
    vm.inputs[1].default_value = (0.5, 0.5, 0.5)
    vm.inputs[2].default_value = (0.5, 0.5, 0.5)
    nt.links.new(facing_normal(nt), vm.inputs[0])
    nt.links.new(vm.outputs["Vector"], emi.inputs["Color"])
    return m


def make_id_mat():
    m, nt, emi = new_mat("data_id")
    info = nt.nodes.new("ShaderNodeObjectInfo")
    cam = nt.nodes.new("ShaderNodeCameraData")
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = 1000.0
    nt.links.new(info.outputs["Object Index"], div.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(div.outputs[0], comb.inputs["X"])
    nt.links.new(cam.outputs["View Z Depth"], comb.inputs["Y"])
    comb.inputs["Z"].default_value = 1.0
    nt.links.new(comb.outputs[0], emi.inputs["Color"])
    return m


def assign(o, mat):
    if len(o.material_slots) == 0:
        o.data.materials.append(mat)
    for slot in o.material_slots:
        slot.material = mat


def apply_variant(v, objs):
    st = VARIANT_STYLE[v]
    body = make_toon("toon_body_" + v, hex_lin(st["top"]), hex_lin(st["front"]), hex_lin(st["side"]))
    tm = st["tray_mul"]
    tray = make_toon("toon_tray_" + v, hex_lin(st["top"], tm), hex_lin(st["front"], tm),
                     hex_lin(st["side"], tm))
    cavity = make_toon("toon_cavity_" + v, hex_lin(st["cavity"]))
    led = make_toon("toon_led_" + v, hex_lin(st["led"]))
    disc = make_toon("toon_disc_" + v, hex_lin(st["disc_top"]), hex_lin(st["disc_front"]),
                     hex_lin(st["disc_side"]))
    for o in objs:
        if o.name == DISC_OBJECT:
            assign(o, disc)
        elif o.name == LED_OBJECT:
            assign(o, led)
        elif o.name in TRAY_OBJECTS:
            assign(o, tray)
        elif o.name.startswith(BODY_PREFIX):
            assign(o, body)
        else:
            assign(o, cavity)


def apply_single(mat, objs):
    for o in objs:
        assign(o, mat)


# ---------------------------------------------------------------- camera (framed on the unsplit scene)
VIEW = Vector((-1.0, 1.0, -1.0)).normalized()
RIGHT = VIEW.cross(Vector((0, 0, 1))).normalized()
UP = RIGHT.cross(VIEW).normalized()

P = world_verts(render_meshes)
sx, sy = P @ np.array(RIGHT), P @ np.array(UP)
x0, x1, y0, y1 = sx.min(), sx.max(), sy.min(), sy.max()
pad = 0.015 * max(x1 - x0, y1 - y0)
x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
wext, hext = x1 - x0, y1 - y0
if wext >= hext:
    W, H = LONG, int(round(LONG * hext / wext))
else:
    W, H = int(round(LONG * wext / hext)), LONG
ppu = W / wext if wext >= hext else H / hext
wext, hext = W / ppu, H / ppu
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
del P, sx, sy

cam_data = bpy.data.cameras.new("IsoCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(wext, hext)
cam_data.clip_start = 0.01
cam_data.clip_end = 20.0
cam_data.dof.use_dof = False
cam = bpy.data.objects.new("IsoCam", cam_data)
scene.collection.objects.link(cam)
cam.location = Vector(RIGHT) * cx + Vector(UP) * cy - VIEW * 5.0
cam.rotation_mode = "QUATERNION"
cam.rotation_quaternion = VIEW.to_track_quat("-Z", "Y")
scene.camera = cam
print("[layers] canvas", W, H, "ppu", ppu)


def to_px(p):
    p = Vector(p)
    return [round(W / 2 + (p.dot(RIGHT) - cx) * ppu, 2), round(H / 2 - (p.dot(UP) - cy) * ppu, 2)]


def dir_px(d, mm=1.0):
    """Screen offset (final px) of a world step d (unit vector) of `mm` millimetres."""
    d = Vector(d)
    return [round(d.dot(RIGHT) * ppu / 1000.0 * mm, 3), round(-d.dot(UP) * ppu / 1000.0 * mm, 3)]


# ---------------------------------------------------------------- disc into the open tray
tray_obj = bpy.data.objects[TRAY_BODY]
T_co, T_polys = world_mesh(tray_obj)

# recess centre: circle fit of the 80 mm-recess ring (r = 40.5 mm), which is exact in the mesh
gx, gy = RECESS_GUESS_CLOSED[0], RECESS_GUESS_CLOSED[1] - TRAY_OPEN
rr = np.hypot(T_co[:, 0] - gx, T_co[:, 1] - gy)
ring = T_co[np.abs(rr - 0.0405) < 0.0005]
A = np.c_[2 * ring[:, 0], 2 * ring[:, 1], np.ones(len(ring))]
sol = np.linalg.lstsq(A, (ring[:, :2] ** 2).sum(1), rcond=None)[0]
RCX, RCY = float(sol[0]), float(sol[1])
ring_r = float(np.sqrt(sol[2] + sol[0] ** 2 + sol[1] ** 2))
print("[layers] recess centre (open) %.3f %.3f mm, ring r %.3f mm, n=%d"
      % (RCX * 1e3, RCY * 1e3, ring_r * 1e3, len(ring)))

# support height: highest tray surface under the disc footprint (drop rays from above)
bvh = BVHTree.FromPolygons([Vector(v) for v in T_co], T_polys)
DR = DISC_DIAMETER / 2.0
hits = []
for gxm in np.arange(-DR, DR + 1e-9, 0.001):
    for gym in np.arange(-DR, DR + 1e-9, 0.001):
        if math.hypot(gxm, gym) > DR - 0.0005:
            continue
        loc, nrm, idx, dist = bvh.ray_cast(Vector((RCX + gxm, RCY + gym, 0.2)), Vector((0, 0, -1)))
        if loc is not None:
            hits.append((loc.z, math.hypot(gxm, gym)))
hits = np.array(hits)
SUPPORT_Z = float(hits[:, 0].max())
zs, cnt = np.unique(np.round(hits[:, 0] * 1e3, 2), return_counts=True)
print("[layers] tray surface under disc (z mm: rays):", dict(zip(zs.tolist(), cnt.tolist())))
print("[layers] support z %.3f mm (max at r=%.1f mm)" % (SUPPORT_Z * 1e3, hits[hits[:, 0].argmax(), 1] * 1e3))

disc = bpy.data.objects[DISC_OBJECT]
D_co = world_mesh(disc)[0]
dc = 0.5 * (D_co.min(0) + D_co.max(0))
d_r = float(np.hypot(D_co[:, 0] - dc[0], D_co[:, 1] - dc[1]).max())
d_bot = float(D_co[:, 2].min())
s = DR / d_r
print("[layers] model disc: diameter %.2f mm, thickness %.2f mm, scale x%.4f in X/Y"
      % (2 * d_r * 1e3, (D_co[:, 2].max() - d_bot) * 1e3, s))
disc.matrix_world = (Matrix.Translation((RCX, RCY, SUPPORT_Z + 0.00005))
                     @ Matrix.Diagonal((s, s, 1.0, 1.0))
                     @ Matrix.Translation((-dc[0], -dc[1], -d_bot))
                     @ disc.matrix_world)
disc.pass_index = len(render_meshes) + 1
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
D_co = world_mesh(disc)[0]
DISC_INFO = {
    "centre_mm": [round(float(v) * 1e3, 2) for v in 0.5 * (D_co.min(0) + D_co.max(0))[:2]],
    "diameter_mm": round(float(np.hypot(D_co[:, 0] - RCX, D_co[:, 1] - RCY).max()) * 2e3, 2),
    "bottom_z_mm": round(float(D_co[:, 2].min()) * 1e3, 3),
    "top_z_mm": round(float(D_co[:, 2].max()) * 1e3, 3),
    "model_diameter_mm": round(2 * d_r * 1e3, 2),
    "xy_scale": round(s, 5),
}
print("[layers] disc placed:", DISC_INFO)

# ---------------------------------------------------------------- layer membership
tray_objs = [o for o in render_meshes if o.name in TRAY_OBJECTS]
LAYER_OBJS = {
    "full": list(render_meshes),
    "body": [o for o in render_meshes if o.name not in TRAY_OBJECTS],
    "tray": tray_objs,
    "traydisc": tray_objs + [disc],
}
ALL_OBJS = list(render_meshes) + [disc]
LAYER_FILE = {"full": "check_full_%s.png", "body": "burner_body_%s.png",
              "tray": "burner_tray_%s.png", "traydisc": "burner_traydisc_%s.png"}


# bezel slot (front plane and opening), needed for the body fill and the json
B = world_mesh(bpy.data.objects[BEZEL])[0]
front_y = float(B[:, 1].min())                               # bezel front plane
fr = B[(np.abs(B[:, 1] - front_y) < 5e-5) & (np.abs(B[:, 0]) < 0.070)
       & (B[:, 2] > 0.033) & (B[:, 2] < 0.062)]               # slot outline on the front face
sl_x0, sl_x1 = float(fr[:, 0].min()), float(fr[:, 0].max())
sl_z0, sl_z1 = float(fr[:, 2].min()), float(fr[:, 2].max())
tun = B[(np.abs(np.abs(B[:, 0]) - sl_x1) < 1e-4) & (B[:, 2] > sl_z0) & (B[:, 2] < sl_z1)]
tunnel_d = float(tun[:, 1].max() - front_y) if len(tun) else 0.0
print("[layers] slot x %.2f..%.2f z %.2f..%.2f mm, front y %.2f, tunnel %.2f mm"
      % (sl_x0 * 1e3, sl_x1 * 1e3, sl_z0 * 1e3, sl_z1 * 1e3, front_y * 1e3, tunnel_d * 1e3))


def slot_mask(inset_px=1.0):
    """Final-image pixels well inside the slot opening (a parallelogram on screen)."""
    tl = np.array(to_px((sl_x0, front_y, sl_z1)))
    trr = np.array(to_px((sl_x1, front_y, sl_z1)))
    bl = np.array(to_px((sl_x0, front_y, sl_z0)))
    yy, xx = np.mgrid[0:H, 0:W]
    px = np.stack([xx + 0.5 - tl[0], yy + 0.5 - tl[1]], -1)
    M = np.linalg.inv(np.array([trr - tl, bl - tl]).T)
    ab = px @ M.T
    ea = inset_px / np.linalg.norm(trr - tl)
    eb = inset_px / np.linalg.norm(bl - tl)
    return ((ab[..., 0] > ea) & (ab[..., 0] < 1 - ea) & (ab[..., 1] > eb) & (ab[..., 1] < 1 - eb))


def show_layer(name):
    keep = set(o.name for o in LAYER_OBJS[name])
    for o in ALL_OBJS:
        o.hide_render = o.name not in keep


# ---------------------------------------------------------------- render setup (as render_burner.py)
r = scene.render
r.engine = "CYCLES"
r.resolution_x = W * SS
r.resolution_y = H * SS
r.resolution_percentage = 100
r.film_transparent = True
r.use_motion_blur = False
r.use_freestyle = False
r.use_compositing = False
r.use_sequencer = False
r.image_settings.file_format = "OPEN_EXR"
r.image_settings.color_mode = "RGBA"
r.image_settings.color_depth = "32"
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
for vl in scene.view_layers[1:]:
    vl.use = False

cyc = scene.cycles
cyc.use_adaptive_sampling = False
cyc.use_denoising = False
cyc.max_bounces = 0
cyc.diffuse_bounces = 0
cyc.glossy_bounces = 0
cyc.transmission_bounces = 0
cyc.transparent_max_bounces = 4
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = DEVICE
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == DEVICE
    cyc.device = "GPU"
except Exception as e:
    print("[layers] GPU setup failed, using CPU:", e)
    cyc.device = "CPU"
if scene.world:
    scene.world.use_nodes = True
    for n in scene.world.node_tree.nodes:
        if n.type == "BACKGROUND":
            n.inputs["Strength"].default_value = 0.0


def render_exr(tag, samples, filter_width):
    cyc.samples = samples
    cyc.filter_width = filter_width
    path = os.path.join(OUTDIR, "raw_%s.exr" % tag)
    r.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("[layers] rendered %s in %.1fs" % (tag, time.time() - t))
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    os.remove(path)
    return a.reshape(h, w, 4)


# ---------------------------------------------------------------- outline mask (as render_burner.py)


def outline_mask(nrm_px, id_px):
    alpha = id_px[..., 3] > 0.5
    oid = np.where(alpha, np.rint(id_px[..., 0] * 1000.0), 0).astype(np.int32)
    depth = np.where(alpha, id_px[..., 1], 1e3).astype(np.float64)
    n = nrm_px[..., :3] * 2.0 - 1.0
    n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-6)
    tone = np.where(n[..., 2] > TOP_NZ, 2, np.where(n[..., 0] + n[..., 1] > 0, 1, 0))
    cos_c = math.cos(math.radians(CREASE_DEG))
    edge = np.zeros(alpha.shape, dtype=bool)

    for axis in (0, 1):
        def sl(a, lo, hi):
            idx = [slice(None)] * a.ndim
            idx[axis] = slice(lo, hi)
            return a[tuple(idx)]
        a_p, a_q = sl(alpha, 0, -1), sl(alpha, 1, None)
        d_p, d_q = sl(depth, 0, -1), sl(depth, 1, None)
        both = a_p & a_q
        diff = a_p != a_q
        diff |= both & (sl(oid, 0, -1) != sl(oid, 1, None))
        diff |= both & (sl(tone, 0, -1) != sl(tone, 1, None))
        diff |= both & ((sl(n, 0, -1) * sl(n, 1, None)).sum(-1) < cos_c)
        jump = np.abs(d_q - d_p)
        dd = np.abs(np.diff(depth, axis=axis))
        pad_ = np.full_like(sl(dd, 0, 1), 1e9)
        before = np.concatenate([pad_, sl(dd, 0, -1)], axis=axis)
        after = np.concatenate([sl(dd, 1, None), pad_], axis=axis)
        slope = np.minimum(before, after)
        diff |= both & (jump > 2.0 * slope + DEPTH_STEP_M)
        near_p = d_p <= d_q
        mp = diff & near_p
        mq = diff & ~near_p
        idx_p = [slice(None)] * 2
        idx_q = [slice(None)] * 2
        idx_p[axis] = slice(0, -1)
        idx_q[axis] = slice(1, None)
        edge[tuple(idx_p)] |= mp
        edge[tuple(idx_q)] |= mq

    k = 7
    e = edge.astype(np.int32)
    c = np.pad(e, ((k // 2 + 1, k // 2), (k // 2 + 1, k // 2))).cumsum(0).cumsum(1)
    box = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    edge &= box >= 6

    width = max(1, int(round(LINE_PX * SS)))
    out = edge.copy()
    for k in range(1, width):
        sh = (k + 1) // 2 * (1 if k % 2 else -1)
        for axis in (0, 1):
            out |= np.roll(edge, sh, axis=axis)
    return out


# ---------------------------------------------------------------- compositing (as render_burner.py)


def lin_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def compose_and_save(color_px, mask, st, dst, fill=None):
    """fill = (mask in top-down final pixels, sRGB colour): paint the colour under those pixels,
    used to close the few see-through holes (side screw holes) visible through the empty slot."""
    a = color_px[..., 3:4]
    straight = np.where(a > 1e-6, color_px[..., :3] / np.maximum(a, 1e-6), 0.0)
    pm = lin_to_srgb(straight) * a
    line = np.array(hex_srgb(st["line"]), dtype=np.float32)
    c = (mask.astype(np.float32) * np.float32(st["line_alpha"]))[..., None]
    pm = line * c + pm * (1.0 - c)
    al = c + a * (1.0 - c)
    rgba = np.concatenate([pm, al], axis=2)
    h, w = rgba.shape[:2]
    f = SS
    rgba = rgba[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
    al = rgba[..., 3:4]
    if fill is not None:
        fm = fill[0][::-1][..., None]                    # Blender rows are bottom-up
        under = np.array(fill[1], dtype=np.float32)
        rgba = np.where(fm, np.concatenate([rgba[..., :3] + under * (1.0 - al), np.ones_like(al)], 2), rgba)
        al = rgba[..., 3:4]
    rgb = np.where(al > 1e-6, rgba[..., :3] / np.maximum(al, 1e-6), 0.0)
    outp = np.concatenate([np.clip(rgb, 0, 1), al], axis=2).astype(np.float32)
    oi = bpy.data.images.new("out", outp.shape[1], outp.shape[0], alpha=True, float_buffer=False)
    oi.colorspace_settings.name = "Non-Color"
    oi.alpha_mode = "STRAIGHT"
    oi.pixels.foreach_set(outp.ravel())
    oi.filepath_raw = dst
    oi.file_format = "PNG"
    oi.save()
    bpy.data.images.remove(oi)
    print("[layers] wrote", dst)


SLOT_FILL = slot_mask(0.5)
for layer in LAYERS:
    show_layer(layer)
    objs = LAYER_OBJS[layer]
    apply_single(make_normal_mat(), objs)
    nrm_px = render_exr(layer + "_normal", 1, 0.01)
    apply_single(make_id_mat(), objs)
    id_px = render_exr(layer + "_id", 1, 0.01)
    mask = outline_mask(nrm_px, id_px)
    del nrm_px, id_px
    for v in VARIANTS:
        apply_variant(v, objs)
        col = render_exr("%s_color_%s" % (layer, v), SAMPLES, 1.5)
        fill = (SLOT_FILL, hex_srgb(VARIANT_STYLE[v]["cavity"])) if layer == "body" else None
        compose_and_save(col, mask, VARIANT_STYLE[v], os.path.join(OUTDIR, LAYER_FILE[layer] % v), fill)
        del col
    del mask

# ---------------------------------------------------------------- placement json
show_layer("full")
shell = [o for o in render_meshes if o.name.startswith(BODY_PREFIX) and o.name not in TRAY_OBJECTS]
S = world_verts(shell)
bx0, by0, bx1, by1 = S[:, 0].min(), S[:, 1].min(), S[:, 0].max(), S[:, 1].max()
T = world_verts(tray_objs)
tx0, ty0, tx1 = T[:, 0].min(), T[:, 1].min(), T[:, 0].max()
MM = 1000.0
axis_factor = math.sqrt(2.0 / 3.0)

info = {
    "image_size": [W, H],
    "pixel_origin": "top-left, y down; values in final-image pixels",
    "projection": "true isometric orthographic; camera looks along (-1,+1,-1) from the (+X,-Y,+Z) "
                  "corner; drive front is -Y (lower-left on screen), its +X side faces lower-right",
    "footprint_floor": {
        "note": "drive body (shell) footprint on the floor plane z=0, tray excluded; "
                "left/right as seen when facing the drive front",
        "front_left": to_px((bx0, by0, 0.0)),
        "front_right": to_px((bx1, by0, 0.0)),
        "rear_right": to_px((bx1, by1, 0.0)),
        "rear_left": to_px((bx0, by1, 0.0)),
        "size_mm": [round((bx1 - bx0) * MM, 1), round((by1 - by0) * MM, 1)],
    },
    "tray_footprint_floor": {
        "note": "open tray outline dropped straight down onto z=0 (part of it falls below the image)",
        "front_left": to_px((tx0, ty0, 0.0)),
        "front_right": to_px((tx1, ty0, 0.0)),
        "rear_right": to_px((tx1, by0, 0.0)),
        "rear_left": to_px((tx0, by0, 0.0)),
        "tray_out_mm": round((by0 - ty0) * MM, 1),
    },
    "scale": {
        "px_per_mm_view_plane": round(ppu / MM, 5),
        "px_per_mm_along_each_world_axis": round(ppu / MM * axis_factor, 5),
        "note": "model mm; a 1 mm step along X, Y or Z spans px_per_mm_along_each_world_axis pixels",
    },
    "screen_axes": {
        k: [round(Vector(d).dot(RIGHT) * ppu / MM, 5), round(-Vector(d).dot(UP) * ppu / MM, 5)]
        for k, d in (("+X_mm", (1, 0, 0)), ("+Y_mm", (0, 1, 0)), ("+Z_mm", (0, 0, 1)))
    },
    "features_px": {},
    "render": {
        "engine": "Cycles, emission-only toon fill, image-space outlines",
        "supersample": SS, "samples": SAMPLES, "tray_open_m": TRAY_OPEN, "line_px": LINE_PX,
    },
}
info["screen_axes"]["note"] = ("pixel offset of a 1 mm step along each world axis; +Y runs from the "
                               "drive front to its rear (the tray comes out along -Y)")
for feat in (LED_OBJECT, "SHELL_eject_button"):
    o = bpy.data.objects.get(feat)
    if o and not o.hide_render:
        info["features_px"][feat] = to_px(world_verts([o]).mean(axis=0))
info["features_px"]["note"] = "LED and eject button sit behind the open tray in this view (not visible)"

# ---- layer data
door =world_mesh(bpy.data.objects[TRAY_DOOR])[0]
door_t = float(door[:, 1].max() - door[:, 1].min())
tray_all = world_verts(tray_objs)
tz0, tz1 = float(tray_all[:, 2].min()), float(tray_all[:, 2].max())
mid_z = 0.5 * (tz0 + tz1)
slide = dir_px((0, 1, 0), TRAY_OPEN * MM)
tr = to_px((sl_x1, front_y, sl_z1))                          # slot top-right corner
ax = info["screen_axes"]["+X_mm"]
# The clip is inset by CLIP_INSET px from the slot's top and right edges: the bezel outline is
# centred on the geometric edge, and the inset lets its inner half show (measured best match
# of body + clipped tray against the unsplit render).
CLIP_INSET = 0.5
cr = [round(tr[0] - CLIP_INSET, 2), round(tr[1] + CLIP_INSET - CLIP_INSET * ax[1] / ax[0], 2)]
left_y = round(cr[1] - cr[0] * ax[1] / ax[0], 2)             # inset slot-top line at image x = 0

info["tray_travel_mm"] = round(TRAY_OPEN * MM, 2)
info["tray_slide_px"] = slide
info["tray_slide_note"] = ("add tray_slide_px * t (t = 0 open .. 1 closed) to the position of the tray "
                           "layers to close the tray; the layers are rendered at t = 0")
info["front_plane_px"] = {
    "left": to_px((sl_x0, front_y, mid_z)),
    "right": to_px((sl_x1, front_y, mid_z)),
    "note": "bezel front plane (y = %.2f mm) at the tray's mid height (z = %.2f mm), at the left and "
            "right ends of the tray slot (x = %.2f / %.2f mm)" % (front_y * MM, mid_z * MM, sl_x0 * MM,
                                                                sl_x1 * MM),
}
info["bezel_thickness_px"] = dir_px((0, -1, 0), door_t * MM)
info["bezel_thickness_note"] = ("screen offset of the tray front plate's thickness (%.2f mm) along -Y; "
                                "closed, the plate sits flush in the slot from the front plane %.2f mm "
                                "inward; the slot itself is a %.2f mm deep tunnel in the bezel"
                                % (door_t * MM, door_t * MM, tunnel_d * MM))
info["slot_px"] = {
    "top_left": to_px((sl_x0, front_y, sl_z1)),
    "top_right": tr,
    "bottom_right": to_px((sl_x1, front_y, sl_z0)),
    "bottom_left": to_px((sl_x0, front_y, sl_z0)),
    "size_mm": [round((sl_x1 - sl_x0) * MM, 2), round((sl_z1 - sl_z0) * MM, 2)],
    "note": "tray slot opening on the bezel front plane (rounded corners, r ~1.5 mm, ignored)",
}
info["tray_clip"] = {
    "polygon_px": [cr, [0.0, left_y], [0.0, float(H)], [cr[0], float(H)]],
    "inset_px": CLIP_INSET,
    "note": "fixed screen-space clip for the tray layers at ANY slide position (clip-path in canvas "
            "pixels; it does not move with the tray): left of the vertical through the slot's "
            "top-right corner and below the slot's top edge line, both inset %.1f px so the bezel "
            "outline stays whole. Tray outside the drive always falls inside it; tray inside the "
            "drive is visible only through the slot, which is exactly this region. Draw: body "
            "layer, then the clipped tray layer on top." % CLIP_INSET,
}
info["disc"] = DISC_INFO
info["disc"]["centre_px"] = to_px((RCX, RCY, DISC_INFO["top_z_mm"] / MM))
info["disc"]["note"] = ("disc in burner_traydisc_*: label side up in the tray's 120 mm recess, tray open; "
                        "centre_px is the centre of its top face")
info["layers"] = [LAYER_FILE[l] % v for l in ("body", "tray", "traydisc") for v in VARIANTS]
info["layers_note"] = ("transparent PNGs on the same %dx%d pixel grid as burner_<theme>.png. body = "
                       "drive without tray/front plate; tray = tray + front plate, open; traydisc = "
                       "open tray with one disc" % (W, H))
# Blender has no Pillow: the .webp copies are made afterwards on the workstation with
# Image.save(path, "WEBP", lossless=True, method=6)
info["layers_webp"] = [n.replace(".png", ".webp") for n in info["layers"]]
info["layers_webp_note"] = ("lossless WebP copies of the layer PNGs (Pillow, lossless=True, method=6), "
                            "pixel-identical where alpha > 0")
with open(os.path.join(OUTDIR, "burner.json"), "w") as fh:
    json.dump(info, fh, indent=2)
print("[layers] done", OUTDIR, W, H)
