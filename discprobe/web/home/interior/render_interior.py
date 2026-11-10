"""Toon "inside the burner while it burns" layers for the disc-probe web home page.

Same camera, canvas, palette logic and outline method as ../render_burner.py and
../render_burner_layers.py, so every layer here registers pixel-for-pixel with burner_<theme>.png.
The canvas is framed exactly as those scripts frame it (tray open, no disc); the interior itself
is then rendered with the tray CLOSED, the disc clamped and the top cover cut away.

Run headless with Blender 5.2.2+ on a COPY of
docs/goals/video/hero/render_pack/disc_explode_render.blend:

    blender -b disc_explode_render.blend --python render_interior.py -- \
        --outdir OUT [--long 1600] [--ss 4] [--variants dark,paper] [--device OPTIX]
        [--cover-cut 0.066] [--r-outer 58.0] [--cut-x 0.0015]

Layers (straight-alpha RGBA PNGs on one W x H grid; draw in this order):
    bg_<v>.png         every static part (chassis, closed tray, mechanism, shell, cut-down cover walls)
    sled_<v>.png       the moving optical pickup (KSS-151 module) at its INNER position
    mid_<v>.png        static pixels that lie in front of the pickup at EVERY position of its travel
                       but behind the disc (closed tray floor, rails, ...): drawn over the sled
    disc_<v>.png       the 120 mm disc alone, opaque; the page draws it translucent to show the sled
    disc_cut_<v>.png   alternative: the disc with its front-right quarter cut out (opaque cutaway)
    glow_<v>.png       laser spot (core + halo + short beam) at the INNER position, for additive blend
    occluders_<v>.png  static pixels in front of the disc (clamp bridge + puck): drawn last
    interior.json      placement data (disc centre/ellipse/plane matrix, sled offset, mm range, order)
    check_*_<v>.png    one-piece renders of the whole scene, only to verify the layer composite

How the occluder split works: the static parts are rendered once, together. Their view depth
(1-sample id pass) is compared per supersampled pixel with the disc's depth and with the pickup's
depth swept over its whole travel (orthographic camera: a translation is an exact image shift
plus a constant depth offset). Static pixels nearer than the disc -> occluders; nearer than the
pickup at every position (and behind the disc) -> mid. Everything static is also in bg, so the
stack is exact whatever opacity the page gives the disc.
"""
import json
import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- arguments
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


OUTDIR = os.path.abspath(arg("--outdir", "out"))
LONG = int(arg("--long", "1600"))
SS = int(arg("--ss", "4"))
TRAY_OPEN = float(arg("--open", "0.14"))        # ONLY used to frame the canvas like burner_*.png
VARIANTS = arg("--variants", "dark,paper").split(",")
DEVICE = arg("--device", "OPTIX")
SAMPLES = int(arg("--samples", "16"))
COVER_CUT_Z = float(arg("--cover-cut", "0.066"))   # top cover removed above this height (m)
R_OUTER_MM = float(arg("--r-outer", "58.0"))       # lens radius at the OUTER sled position
CUT_X = float(arg("--cut-x", "0.0015"))            # disc_cut: quarter x > CUT_X, y < centre removed
CHECKS = arg("--checks", "1") == "1"
os.makedirs(OUTDIR, exist_ok=True)

# ---------------------------------------------------------------- palettes
# body / disc / line / led are those of render_burner_layers.py; the interior parts get their own
# three-tone fills so the mechanism reads (one flat cavity tone was enough when only the tray
# slot showed the inside).
VARIANT_STYLE = {
    "dark": dict(
        body=("#222b2a", "#1a2221", "#1d2625"),
        mech=("#2c3735", "#222b2a", "#263030"),
        tray=("#1b2221", "#151b1a", "#181e1d"),
        pcb=("#1d2b25", "#16221d", "#19261f"),
        sled=("#4b5856", "#36413f", "#3d4846"),
        disc=("#323a39", "#262d2c", "#29302f"),
        lens="#8fb6c9", led="#d9a75c",
        line="#d5d9d2", line_alpha=0.55,
        glow_core="#fff3ea", glow_halo="#ff5a3c", glow_bloom="#ff3b30",
    ),
    "paper": dict(
        body=("#f1eee8", "#d9d4cb", "#d0cac0"),
        mech=("#e6e2da", "#cdc7bc", "#c5bfb3"),
        tray=("#d8d3c9", "#c1baae", "#bab3a7"),
        pcb=("#dde3d6", "#c3cbbd", "#bcc4b5"),
        sled=("#fbfaf7", "#e4e0d8", "#dcd7ce"),
        disc=("#f7f7f4", "#e0dfda", "#d8d7d2"),
        lens="#6f98ad", led="#b3ab9e",
        line="#2b2924", line_alpha=1.0,
        glow_core="#fff6ef", glow_halo="#f0442c", glow_bloom="#e8321f",
    ),
}
LINE_PX = 0.8
CREASE_DEG = 30.0
DEPTH_STEP_M = 0.0004
TOP_NZ = 0.55

TRAY_OBJECTS = {"KSL210_tray_final-1", "SHELL_tray_door", "SHELL_door_print"}
TRAY_BODY = "KSL210_tray_final-1"
HIDE_OBJECTS = {"table", "Label_simulated", "SHELL_label_round", "SHELL_sticker_side",
                "SHELL_sticker_rear", "SHELL_door_print", "SHELL_badge",
                "KSL210_tray-1", "cd-1"}
HIDE_COLLECTIONS = {"Disc", "Overlay", "SW_hidden"}
BODY_PREFIX = "SHELL_"
LED_OBJECT = "SHELL_led"
PCB_OBJECTS = {"SHELL_main_pcb", "KSL210_sled_and_spindle PCB-1", "KSL210_traymotor_PCB-1"}
COVER = "SHELL_top_cover"
DISC_OBJECT = "body"                     # polycarbonate disc mesh of the "Disc" collection (120 mm)
SLED_ROOT = "KSS151_module-1"            # empty; every mesh below it moves with the pickup
LENS_OBJECT = "kss151_focussing_lens-1"
DATA_PLANE_BELOW_TOP = 0.0001            # laser spot plane: 0.1 mm under the label face (CD data)


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
sled_names = set()


def _walk(o):
    for c in o.children:
        if c.type == "MESH":
            sled_names.add(c.name)
        _walk(c)


_walk(bpy.data.objects[SLED_ROOT])          # hierarchy is read before parents are cleared

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


def move(objs, d):
    for o in objs:
        o.matrix_world = Matrix.Translation(d) @ o.matrix_world


tray_objs_all = [bpy.data.objects[n] for n in TRAY_OBJECTS if n in bpy.data.objects]
move(tray_objs_all, (0.0, -TRAY_OPEN, 0.0))       # open: only to reproduce the canvas framing
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()

render_meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
print("[interior] visible meshes (framing set):", len(render_meshes))


def world_mesh(o):
    oe = o.evaluated_get(deps)
    me = oe.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(oe.matrix_world)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    oe.to_mesh_clear()
    return co


def world_verts(objs):
    return np.concatenate([world_mesh(o) for o in objs])


# ---------------------------------------------------------------- camera (identical framing)
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
print("[interior] canvas", W, H, "ppu", ppu)


def to_px(p):
    p = Vector(p)
    return [round(W / 2 + (p.dot(RIGHT) - cx) * ppu, 2), round(H / 2 - (p.dot(UP) - cy) * ppu, 2)]


def dir_px(d, mm=1.0):
    d = Vector(d)
    return [round(d.dot(RIGHT) * ppu / 1000.0 * mm, 5), round(-d.dot(UP) * ppu / 1000.0 * mm, 5)]


shell = [o for o in render_meshes if o.name.startswith(BODY_PREFIX) and o.name not in TRAY_OBJECTS]
S_ = world_verts(shell)
FOOT = {"front_left": to_px((S_[:, 0].min(), S_[:, 1].min(), 0.0)),
        "rear_right": to_px((S_[:, 0].max(), S_[:, 1].max(), 0.0))}
print("[interior] footprint check (compare burner.json):", FOOT)
del S_

# ---------------------------------------------------------------- interior pose
move(tray_objs_all, (0.0, TRAY_OPEN, 0.0))         # tray closed again (frame-1 pose)

# top cover: boolean away everything above COVER_CUT_Z (keeps the side and rear walls)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
cut_me = bpy.data.meshes.new("cover_cutter")
bm.to_mesh(cut_me)
bm.free()
cutter = bpy.data.objects.new("cover_cutter", cut_me)
scene.collection.objects.link(cutter)
cutter.matrix_world = Matrix.Translation((0.0, 0.19, COVER_CUT_Z + 0.05)) @ Matrix.Diagonal((0.4, 0.4, 0.1, 1.0))
cutter.hide_render = True
cover = bpy.data.objects[COVER]
for solver in ("EXACT", "MANIFOLD", "FLOAT"):
    for m in list(cover.modifiers):
        cover.modifiers.remove(m)
    mod = cover.modifiers.new("cover_cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        mod.solver = solver
    except Exception as e:
        print("[interior] solver", solver, "unavailable:", e)
        continue
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    t = time.time()
    C = world_mesh(cover)
    ok = len(C) > 1000 and C[:, 2].max() <= COVER_CUT_Z + 1e-5
    print("[interior] cover cut solver %s: %d verts, z max %.3f mm, %.1fs, ok=%s"
          % (solver, len(C), C[:, 2].max() * 1e3, time.time() - t, ok))
    if ok:
        break
COVER_SOLVER = solver

# disc: the frame-1 disc already sits clamped on the spindle (120 mm, centre on the spindle axis)
disc = bpy.data.objects[DISC_OBJECT]
D_co = world_mesh(disc)
DCX, DCY = [float(v) for v in 0.5 * (D_co.min(0) + D_co.max(0))[:2]]
D_R = float(np.hypot(D_co[:, 0] - DCX, D_co[:, 1] - DCY).max())
D_BOT, D_TOP = float(D_co[:, 2].min()), float(D_co[:, 2].max())
print("[interior] disc centre %.2f %.2f mm, r %.2f mm, z %.2f..%.2f mm"
      % (DCX * 1e3, DCY * 1e3, D_R * 1e3, D_BOT * 1e3, D_TOP * 1e3))

# disc_cut: copy with the front-right quarter (x > CUT_X, y < centre) removed
disc_cut = disc.copy()
disc_cut.data = disc.data.copy()
disc_cut.name = "disc_cut"
scene.collection.objects.link(disc_cut)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
qme = bpy.data.meshes.new("quarter_cutter")
bm.to_mesh(qme)
bm.free()
qcut = bpy.data.objects.new("quarter_cutter", qme)
scene.collection.objects.link(qcut)
qx0, qx1, qy0, qy1 = CUT_X, DCX + 0.1, DCY - 0.1, DCY
qcut.matrix_world = (Matrix.Translation((0.5 * (qx0 + qx1), 0.5 * (qy0 + qy1), 0.5 * (D_BOT + D_TOP)))
                     @ Matrix.Diagonal((qx1 - qx0, qy1 - qy0, 0.02, 1.0)))
qcut.hide_render = True
for solver in ("EXACT", "MANIFOLD", "FLOAT"):
    for m in list(disc_cut.modifiers):
        disc_cut.modifiers.remove(m)
    mod = disc_cut.modifiers.new("quarter", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = qcut
    try:
        mod.solver = solver
    except Exception:
        continue
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    Q = world_mesh(disc_cut)
    inq = (Q[:, 0] > CUT_X + 1e-4) & (Q[:, 1] < DCY - 1e-4)
    ok = len(Q) > 100 and not inq.any()
    print("[interior] disc quarter cut solver %s: %d verts, ok=%s" % (solver, len(Q), ok))
    if ok:
        break

sled = [bpy.data.objects[n] for n in sorted(sled_names) if not bpy.data.objects[n].hide_render]
lens = bpy.data.objects[LENS_OBJECT]
L_co = world_mesh(lens)
LX, LY = [float(v) for v in 0.5 * (L_co.min(0) + L_co.max(0))[:2]]
L_TOP = float(L_co[:, 2].max())
R_INNER = math.hypot(LX - DCX, LY - DCY)
TRAVEL = R_OUTER_MM / 1000.0 - R_INNER
# unit vector from the disc centre through the lens: the pickup travels along it (here ~ -Y)
RAD = Vector((LX - DCX, LY - DCY, 0.0)).normalized()
print("[interior] lens centre %.2f %.2f mm, top z %.2f, r_inner %.2f mm, travel %.2f mm, dir %s"
      % (LX * 1e3, LY * 1e3, L_TOP * 1e3, R_INNER * 1e3, TRAVEL * 1e3, tuple(round(v, 4) for v in RAD)))

static = [o for o in scene.objects if o.type == "MESH" and not o.hide_render
          and o.name not in sled_names and o not in (disc, disc_cut, cutter, qcut)]
for i, o in enumerate(static + sled + [disc, disc_cut]):
    o.pass_index = i + 1
ALL_OBJS = static + sled + [disc, disc_cut]
print("[interior] static %d, sled %d" % (len(static), len(sled)))

LAYER_OBJS = {
    "static": static,
    "sled": sled,
    "disc": [disc],
    "disc_cut": [disc_cut],
    "check_full_inner": static + sled + [disc],
    "check_cut_inner": static + sled + [disc_cut],
    "check_cut_outer": static + sled + [disc_cut],
}


def show(objs):
    keep = set(o.name for o in objs)
    for o in ALL_OBJS:
        o.hide_render = o.name not in keep


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
    camd = nt.nodes.new("ShaderNodeCameraData")
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = 1000.0
    nt.links.new(info.outputs["Object Index"], div.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(div.outputs[0], comb.inputs["X"])
    nt.links.new(camd.outputs["View Z Depth"], comb.inputs["Y"])
    comb.inputs["Z"].default_value = 1.0
    nt.links.new(comb.outputs[0], emi.inputs["Color"])
    return m


def assign(o, mat):
    if len(o.material_slots) == 0:
        o.data.materials.append(mat)
    for slot in o.material_slots:
        slot.material = mat


def toon3(name, tones):
    return make_toon(name, *(hex_lin(t) for t in tones))


def apply_variant(v, objs):
    st = VARIANT_STYLE[v]
    mats = {k: toon3("toon_%s_%s" % (k, v), st[k]) for k in ("body", "mech", "tray", "pcb", "sled", "disc")}
    mats["lens"] = make_toon("toon_lens_" + v, hex_lin(st["lens"]))
    mats["led"] = make_toon("toon_led_" + v, hex_lin(st["led"]))
    for o in objs:
        if o in (disc, disc_cut):
            k = "disc"
        elif o.name == LENS_OBJECT:
            k = "lens"
        elif o.name in sled_names:
            k = "sled"
        elif o.name == LED_OBJECT:
            k = "led"
        elif o.name in PCB_OBJECTS:
            k = "pcb"
        elif o.name == TRAY_BODY:
            k = "tray"
        elif o.name.startswith(BODY_PREFIX):
            k = "body"
        else:
            k = "mech"
        assign(o, mats[k])


def apply_single(mat, objs):
    for o in objs:
        assign(o, mat)


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
    print("[interior] GPU setup failed, using CPU:", e)
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
    print("[interior] rendered %s in %.1fs" % (tag, time.time() - t))
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    os.remove(path)
    return a.reshape(h, w, 4)          # bottom-up rows


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


# ---------------------------------------------------------------- compositing


def lin_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def save_png(rgba_straight_bottom_up, dst):
    outp = rgba_straight_bottom_up.astype(np.float32)
    oi = bpy.data.images.new("out", outp.shape[1], outp.shape[0], alpha=True, float_buffer=False)
    oi.colorspace_settings.name = "Non-Color"
    oi.alpha_mode = "STRAIGHT"
    oi.pixels.foreach_set(outp.ravel())
    oi.filepath_raw = dst
    oi.file_format = "PNG"
    oi.save()
    bpy.data.images.remove(oi)
    print("[interior] wrote", dst)


def compose_and_save(color_px, mask, st, dst, keep=None):
    """keep: supersampled bool mask (bottom-up rows); pixels outside it are made transparent
    before the box filter, so split layers keep the antialiasing of the one-piece render."""
    a = color_px[..., 3:4]
    straight = np.where(a > 1e-6, color_px[..., :3] / np.maximum(a, 1e-6), 0.0)
    pm = lin_to_srgb(straight) * a
    line = np.array(hex_srgb(st["line"]), dtype=np.float32)
    c = (mask.astype(np.float32) * np.float32(st["line_alpha"]))[..., None]
    pm = line * c + pm * (1.0 - c)
    al = c + a * (1.0 - c)
    rgba = np.concatenate([pm, al], axis=2)
    if keep is not None:
        rgba *= keep[..., None].astype(np.float32)
    h, w = rgba.shape[:2]
    f = SS
    rgba = rgba[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
    al = rgba[..., 3:4]
    rgb = np.where(al > 1e-6, rgba[..., :3] / np.maximum(al, 1e-6), 0.0)
    save_png(np.concatenate([np.clip(rgb, 0, 1), al], axis=2), dst)


def data_passes(objs, tag):
    apply_single(make_normal_mat(), objs)
    nrm = render_exr(tag + "_normal", 1, 0.01)
    apply_single(make_id_mat(), objs)
    idp = render_exr(tag + "_id", 1, 0.01)
    mask = outline_mask(nrm, idp)
    del nrm
    alpha = idp[..., 3] > 0.5
    depth = np.where(alpha, idp[..., 1], np.inf).astype(np.float32)
    del idp
    return mask, alpha, depth


def color_layers(objs, tag, mask, outputs):
    """outputs: list of (filename pattern with %s for the variant, keep mask or None)."""
    for v in VARIANTS:
        apply_variant(v, objs)
        col = render_exr("%s_color_%s" % (tag, v), SAMPLES, 1.5)
        for pattern, keep in outputs:
            compose_and_save(col, mask, VARIANT_STYLE[v], os.path.join(OUTDIR, pattern % v), keep)
        del col


# ---------------------------------------------------------------- 1. moving parts first (depths)
show(sled)
SL_MASK, SL_A, SL_D = data_passes(sled, "sled")
color_layers(sled, "sled", SL_MASK, [("sled_%s.png", None)])
del SL_MASK

show([disc])
DI_MASK, DI_A, DI_D = data_passes([disc], "disc")
color_layers([disc], "disc", DI_MASK, [("disc_%s.png", None)])
del DI_MASK

show([disc_cut])
m, _a, _d = data_passes([disc_cut], "disc_cut")
del _a, _d
color_layers([disc_cut], "disc_cut", m, [("disc_cut_%s.png", None)])
del m

# ---------------------------------------------------------------- 2. sweep the pickup depth over its travel
# image rows are bottom-up (Blender): a screen offset (dx, dy) in top-down pixels is (dx, -dy) here
step = dir_px(RAD, 1.0)                                       # final px per mm along the travel
travel_ss = math.hypot(*step) * TRAVEL * 1000.0 * SS
NSTEP = int(math.ceil(travel_ss / 0.75)) + 1
ys_, xs_ = np.nonzero(SL_A)
by0, by1, bx0, bx1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
del ys_, xs_
HSS, WSS = SL_A.shape
ox_max = int(round(step[0] * TRAVEL * 1000.0 * SS))
oy_max = int(round(-step[1] * TRAVEL * 1000.0 * SS))
cy0, cy1 = max(0, min(by0, by0 + oy_max) - 2 * SS - 4), min(HSS, max(by1, by1 + oy_max) + 2 * SS + 4)
cx0, cx1 = max(0, min(bx0, bx0 + ox_max) - 2 * SS - 4), min(WSS, max(bx1, bx1 + ox_max) + 2 * SS + 4)
crop_a = SL_A[cy0:cy1, cx0:cx1]
crop_d = SL_D[cy0:cy1, cx0:cx1]
sw_any = np.zeros_like(crop_a)
sw_min = np.full(crop_a.shape, np.inf, dtype=np.float32)
sw_max = np.full(crop_a.shape, -np.inf, dtype=np.float32)
hh, ww = crop_a.shape
dview = float(Vector((RAD.x, RAD.y, 0.0)).dot(VIEW))          # depth change per metre of travel
t = time.time()
for k in range(NSTEP):
    dm = TRAVEL * k / (NSTEP - 1)
    ox = int(round(step[0] * dm * 1000.0 * SS))
    oy = int(round(-step[1] * dm * 1000.0 * SS))
    ys0, ys1 = max(0, -oy), min(hh, hh - oy)
    xs0, xs1 = max(0, -ox), min(ww, ww - ox)
    a = crop_a[ys0:ys1, xs0:xs1]
    dd = crop_d[ys0:ys1, xs0:xs1] + np.float32(dview * dm)
    tgt = (slice(ys0 + oy, ys1 + oy), slice(xs0 + ox, xs1 + ox))
    sw_any[tgt] |= a
    sw_min[tgt] = np.where(a, np.minimum(sw_min[tgt], dd), sw_min[tgt])
    sw_max[tgt] = np.where(a, np.maximum(sw_max[tgt], dd), sw_max[tgt])
print("[interior] sweep %d steps over %.1f ss-px in %.1fs" % (NSTEP, travel_ss, time.time() - t))


def grow(a, rad, op, fill):
    """Square (2*rad+1) neighbourhood filter, separable: op = np.maximum / np.minimum / np.logical_or."""
    out = a
    for axis in (0, 1):
        acc = out.copy()
        n = out.shape[axis]
        for s in range(1, rad + 1):
            for sgn in (1, -1):
                src = [slice(None)] * 2
                dst = [slice(None)] * 2
                if sgn > 0:
                    src[axis], dst[axis] = slice(0, n - s), slice(s, n)
                else:
                    src[axis], dst[axis] = slice(s, n), slice(0, n - s)
                acc[tuple(dst)] = op(acc[tuple(dst)], out[tuple(src)])
        out = acc
    return out


# Outlines are drawn up to 1 supersampled px outside a layer's alpha, and the page slides the sled
# with subpixel (bilinear) resampling, which spreads it by up to 1 more final px. Grow the moving
# parts' coverage by that much (the disc by its outline + filter fringe), carrying the NEAREST depth found in the neighbourhood, so the static
# pixels that hide them also hide their outline fringe.
GROW_SLED = SS + 1
sw_any = grow(sw_any, GROW_SLED, np.logical_or, False)
sw_min = grow(sw_min, GROW_SLED, np.minimum, np.inf)
sw_max = grow(sw_max, GROW_SLED, np.maximum, -np.inf)
GROW_DISC = 3            # 1 px outline fringe + the 1.5 px pixel filter of the colour pass
DI_A = grow(DI_A, GROW_DISC, np.logical_or, False)
DI_D = grow(DI_D, GROW_DISC, np.minimum, np.inf)
SW_ANY = np.zeros_like(SL_A)
SW_MIN = np.full(SL_A.shape, np.inf, dtype=np.float32)
SW_MAX = np.full(SL_A.shape, -np.inf, dtype=np.float32)
SW_ANY[cy0:cy1, cx0:cx1] = sw_any
SW_MIN[cy0:cy1, cx0:cx1] = sw_min
SW_MAX[cy0:cy1, cx0:cx1] = sw_max
del crop_a, crop_d, sw_any, sw_min, sw_max, SL_D

# ---------------------------------------------------------------- 3. static parts, split by depth
show(static)
ST_MASK, ST_A, ST_D = data_passes(static, "static")
TOP = ST_A & DI_A & (ST_D < DI_D)                       # static in front of the disc
MID = ST_A & ~TOP & SW_ANY & (ST_D < SW_MIN)            # in front of the pickup wherever it goes
AMBIG = ST_A & ~TOP & SW_ANY & (ST_D >= SW_MIN) & (ST_D < SW_MAX)
SPLIT = {"occluders_px_ss": int(TOP.sum()), "mid_px_ss": int(MID.sum()),
         "ambiguous_px_ss": int(AMBIG.sum())}
if AMBIG.any():
    ay, ax = np.nonzero(AMBIG)
    SPLIT["ambiguous_bbox_px"] = [round(ax.min() / SS, 1), round((HSS - ay.max()) / SS, 1),
                                  round(ax.max() / SS, 1), round((HSS - ay.min()) / SS, 1)]
    del ay, ax
print("[interior] split:", SPLIT)
del ST_D, DI_D, SW_MIN, SW_MAX, AMBIG
color_layers(static, "static", ST_MASK,
             [("bg_%s.png", None), ("mid_%s.png", MID), ("occluders_%s.png", TOP)])
del ST_MASK, TOP, MID, ST_A, SW_ANY, SL_A, DI_A

# ---------------------------------------------------------------- 4. one-piece check renders
if CHECKS:
    for name in ("check_full_inner", "check_cut_inner", "check_cut_outer"):
        objs = LAYER_OBJS[name]
        outer = name.endswith("outer")
        if outer:
            move(sled, tuple(RAD * TRAVEL))
        show(objs)
        m, _a, _d = data_passes(objs, name)
        del _a, _d
        color_layers(objs, name, m, [(name + "_%s.png", None)])
        del m
        if outer:
            move(sled, tuple(-RAD * TRAVEL))

# ---------------------------------------------------------------- 5. glow layer (drawn, not rendered)
Z_SPOT = D_TOP - DATA_PLANE_BELOW_TOP
spot_in = (LX, LY, Z_SPOT)
lens_top_in = (LX, LY, L_TOP)
A = np.array([dir_px((1, 0, 0)), dir_px((0, 1, 0))]).T            # 2x2: plane mm -> screen px
Ainv = np.linalg.inv(A)
GLOW = dict(core_mm=0.7, halo_mm=2.6, bloom_mm=7.0, core_a=1.0, halo_a=0.85, bloom_a=0.30,
            beam_px=1.6, beam_a=0.55)


def glow_image(st):
    """Straight-alpha RGBA (top-down) for additive drawing: three gaussian discs on the disc plane
    (so they are iso ellipses on screen) plus a thin vertical beam from the lens top to the spot."""
    sp = np.array(to_px(spot_in))
    lt = np.array(to_px(lens_top_in))
    R = int(GLOW["bloom_mm"] * 3.2 * ppu / 1000.0) + 4
    gx0, gy0 = int(sp[0]) - R, int(min(sp[1], lt[1])) - R
    gx1, gy1 = int(sp[0]) + R, int(max(sp[1], lt[1])) + R
    S2 = 4                                                           # in-image supersampling
    yy, xx = np.mgrid[gy0 * S2:gy1 * S2, gx0 * S2:gx1 * S2]
    px = (xx + 0.5) / S2 - sp[0]
    py = (yy + 0.5) / S2 - sp[1]
    mm = np.einsum("ij,jhw->ihw", Ainv, np.stack([px, py]))
    rr = np.hypot(mm[0], mm[1])
    layers = []
    for key, col in (("bloom", st["glow_bloom"]), ("halo", st["glow_halo"]), ("core", st["glow_core"])):
        a = GLOW[key + "_a"] * np.exp(-(rr / GLOW[key + "_mm"]) ** 2)
        layers.append((a, np.array(hex_srgb(col), dtype=np.float32)))
    bx = (xx + 0.5) / S2
    by = (yy + 0.5) / S2
    within = (by >= sp[1]) & (by <= lt[1])
    ba = GLOW["beam_a"] * np.clip(1.0 - np.abs(bx - sp[0]) / (GLOW["beam_px"] / 2.0 + 0.5), 0, 1) * within
    layers.insert(0, (ba, np.array(hex_srgb(st["glow_halo"]), dtype=np.float32)))
    pm = np.zeros(px.shape + (3,), dtype=np.float32)
    al = np.zeros(px.shape, dtype=np.float32)
    for a, col in layers:                                           # "over" in premultiplied space
        pm = col * a[..., None] + pm * (1 - a[..., None])
        al = a + al * (1 - a)
    h2, w2 = al.shape
    pm = pm.reshape(h2 // S2, S2, w2 // S2, S2, 3).mean(axis=(1, 3))
    al = al.reshape(h2 // S2, S2, w2 // S2, S2).mean(axis=(1, 3))
    out = np.zeros((H, W, 4), dtype=np.float32)
    ys0, ys1, xs0, xs1 = max(gy0, 0), min(gy1, H), max(gx0, 0), min(gx1, W)
    sub = (slice(ys0 - gy0, ys1 - gy0), slice(xs0 - gx0, xs1 - gx0))
    a_ = al[sub][..., None]
    out[ys0:ys1, xs0:xs1, :3] = np.where(a_ > 1e-6, pm[sub] / np.maximum(a_, 1e-6), 0)
    out[ys0:ys1, xs0:xs1, 3] = al[sub]
    return out


for v in VARIANTS:
    g = glow_image(VARIANT_STYLE[v])
    save_png(g[::-1], os.path.join(OUTDIR, "glow_%s.png" % v))

# ---------------------------------------------------------------- 6. json
off = [round(c * TRAVEL * 1000.0, 3) for c in dir_px(RAD)]
centre_top = to_px((DCX, DCY, D_TOP))
centre_spot = to_px((DCX, DCY, Z_SPOT))
info = {
    "image_size": [W, H],
    "pixel_origin": "top-left, y down; final-image pixels; same grid as ../burner_<theme>.png "
                    "(not mirrored: the page mirrors everything itself)",
    "framing_check": {"footprint_front_left": FOOT["front_left"], "footprint_rear_right": FOOT["rear_right"],
                      "note": "must equal footprint_floor.front_left / rear_right in ../burner.json"},
    "layer_order": [
        {"file": "bg_%s.png", "blend": "source-over", "moves": False},
        {"file": "sled_%s.png", "blend": "source-over", "moves": "translate by sled.offset_px * t"},
        {"file": "mid_%s.png", "blend": "source-over", "moves": False},
        {"file": "disc_%s.png (or disc_cut_%s.png)", "blend": "source-over",
         "opacity": "0.45-0.6 to see the pickup through it (disc_%s); 1.0 for disc_cut_%s",
         "moves": "static; spin is drawn on top of it (see disc.spin)"},
        {"file": "glow_%s.png", "blend": "dark: lighter (additive); paper: source-over (additive "
                                          "light on a near-white page only bleaches it)",
         "moves": "translate by sled.offset_px * t, together with the sled"},
        {"file": "occluders_%s.png", "blend": "source-over", "moves": False},
    ],
    "layer_notes": {
        "bg": "all static parts: bottom pan, main PCB, chassis, closed tray, mechanism, sled motor and "
              "gears, guide rod and rail, spindle, clamp bridge, bezel and the top cover cut at z = %.1f mm "
              "(side and rear walls kept, lid removed; boolean solver %s)" % (COVER_CUT_Z * 1e3, COVER_SOLVER),
        "mid": "the subset of bg that is in front of the pickup at every point of its travel and behind "
               "the disc (tray floor around the pickup slot, rail, rod clamp...). Pixel-identical to bg "
               "where it is opaque.",
        "occluders": "the subset of bg in front of the disc: clamp bridge and puck. The bezel and the "
                     "cut-down walls never overlap the disc or the pickup in this view.",
        "split_counts_supersampled_px": SPLIT,
    },
    "disc": {
        "centre_px_top_face": centre_top,
        "centre_px_data_plane": centre_spot,
        "centre_mm": [round(DCX * 1e3, 3), round(DCY * 1e3, 3)],
        "radius_mm": round(D_R * 1e3, 2),
        "z_mm": [round(D_BOT * 1e3, 3), round(D_TOP * 1e3, 3)],
        "hole_radius_mm": 7.5,
        "plane_matrix_px_per_mm": {"a": A[0, 0], "b": A[1, 0], "c": A[0, 1], "d": A[1, 1],
                                   "note": "screen offset = [a c; b d] * [dx_mm, dy_mm] for a step "
                                           "(dx, dy) in the disc plane (+X right side of drive, +Y "
                                           "towards its rear). Canvas: ctx.setTransform(a, b, c, d, "
                                           "cx, cy) then draw in disc-plane millimetres."},
        "ellipse_px": {"semi_major_x": round(D_R * 1e3 * math.hypot(A[0, 0], A[0, 1]), 2),
                       "semi_minor_y": round(D_R * 1e3 * math.hypot(A[1, 0], A[1, 1]), 2),
                       "note": "top face outline: axis-aligned ellipse around centre_px_top_face"},
        "spin": "a plain toon disc shows no rotation; draw marks (label print, a sheen wedge, a sector "
                "tick) in disc-plane mm with plane_matrix and rotate them by theta: M * R(theta) * M^-1 "
                "about the centre. Seen from above (label side) a disc turns clockwise, i.e. theta "
                "decreasing in this un-mirrored image (and increasing after the page's mirror).",
        "cut": {"file": "disc_cut_%s.png",
                "removed": "quarter x > %.1f mm, y < centre (front-right, nearest the viewer)" % (CUT_X * 1e3),
                "note": "the lens path runs %.1f mm inside the remaining disc's cut face, so the spot "
                        "sits at the cut edge; do not rotate this layer" % ((CUT_X - LX) * 1e3)},
    },
    "sled": {
        "file": "sled_%s.png",
        "radius_mm": [round(R_INNER * 1e3, 2), R_OUTER_MM],
        "travel_mm": round(TRAVEL * 1e3, 2),
        "direction": "radially outward along %s (towards the drive front)" % [round(RAD.x, 4), round(RAD.y, 4)],
        "offset_px": off,
        "px_per_mm": dir_px(RAD),
        "lens_top_px_inner": to_px(lens_top_in),
        "lens_top_px_outer": to_px(tuple(Vector(lens_top_in) + RAD * TRAVEL)),
        "note": "layer is rendered at the INNER position; position(t) = offset_px * t, t = "
                "(r_mm - %.2f) / %.2f. Model check: the module clears every static part up to 19.7 mm of "
                "travel (r 45 mm); beyond that it intersects the guide-rod end clamp (CAD detail), and the "
                "base plate from 35 mm (r 60). The layers hide this." % (R_INNER * 1e3, TRAVEL * 1e3),
    },
    "laser": {
        "spot_px_inner": to_px(spot_in),
        "spot_px_outer": to_px(tuple(Vector(spot_in) + RAD * TRAVEL)),
        "spot_plane_z_mm": round(Z_SPOT * 1e3, 3),
        "beam_px": [to_px(lens_top_in), to_px(spot_in)],
        "beam_note": "lens top to disc spot is only %.2f mm (%.1f px), drawn as a short vertical line in "
                     "glow; visible only through a translucent disc or at the cut edge" %
                     ((Z_SPOT - L_TOP) * 1e3, (Z_SPOT - L_TOP) * 1e3 * ppu / 1000 * math.sqrt(2 / 3)),
        "glow_png": "glow_%s.png = core + halo + bloom + beam at the INNER spot; slide with the sled",
        "glow_params_mm": GLOW,
        "colours": {v: {k: VARIANT_STYLE[v][k] for k in ("glow_core", "glow_halo", "glow_bloom")}
                    for v in VARIANTS},
        "diffraction": "draw on the page, in disc-plane mm with plane_matrix: a short arc of the track "
                       "circle through the spot (radius r, +-25 deg around the spot), as 5-7 thin "
                       "concentric bands at r-1.5 .. r+1.5 mm coloured red..violet, alpha falling off "
                       "with arc distance from the spot (gaussian sigma ~8 mm), blend 'lighter'. Its "
                       "curvature depends on r, so it cannot be a pre-rendered sliding PNG.",
    },
    "scale": {"px_per_mm_view_plane": round(ppu / 1000.0, 5),
              "px_per_mm_along_each_world_axis": round(ppu / 1000.0 * math.sqrt(2 / 3), 5)},
    "render": {"engine": "Cycles, emission-only toon fill, image-space outlines", "supersample": SS,
               "samples": SAMPLES, "line_px": LINE_PX, "cover_cut_z_mm": COVER_CUT_Z * 1e3},
}
with open(os.path.join(OUTDIR, "interior.json"), "w") as fh:
    json.dump(info, fh, indent=2)
print("[interior] done", OUTDIR, W, H)
