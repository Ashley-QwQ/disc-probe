"""The burner seen straight down, its top shell see-through, for the calibration page (2026-11-11).

Derived from interior/render_interior.py (same model, palette, toon fill and image-space outlines); the camera
looks straight down (-Z) with the drive's front at the bottom, the tray closed and the disc clamped. Instead of
cutting the top cover away, the cover is its own layer, which the page draws translucent over everything, so the
mechanism shows through a shell that is still there. A soft drop shadow, baked to the lower left (more left than
down: the lamp is up and to the right, as on the desk scenes), sits on its own layer under everything.

Run headless with Blender 5.2.2+ on a COPY of the video project's disc_explode_render.blend:

    blender -b disc_explode_render.blend --python render_caltop.py -- \\
        --outdir OUT [--long 1400] [--ss 4] [--variants dark,paper] [--device OPTIX] [--r-outer 58.0]
        [--shadow-mm -40,-22] [--shadow-blur 11] [--checks 0]

Layers (straight-alpha RGBA PNGs on one W x H grid; draw in this order):
    shadow_<v>.png     the drive's drop shadow on the desk (soft, offset lower left) + a tight contact shadow
    bg_<v>.png         every static part except the top cover (chassis, closed tray, mechanism, side walls)
    sled_<v>.png       the optical pickup at its INNER position; slides along sled.offset_px
    mid_<v>.png        static pixels in front of the pickup at every position of its travel, behind the disc
    disc_<v>.png       the 120 mm disc alone, opaque; the page draws it translucent to show the pickup
    glow_<v>.png       laser spot at the INNER position (slides with the sled)
    occluders_<v>.png  static pixels in front of the disc (clamp bridge + puck)
    lid_<v>.png        the top cover alone (fill + outlines); the page draws it at low opacity: the see-through shell
    caltop.json        placement (disc centre and radius in px, sled offset, spot, scale, order)
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
LONG = int(arg("--long", "1400"))
SS = int(arg("--ss", "4"))
TRAY_OPEN = 0.0                                  # the tray stays closed (calibration measures a clamped disc)
VARIANTS = arg("--variants", "dark,paper").split(",")
DEVICE = arg("--device", "OPTIX")
SAMPLES = int(arg("--samples", "16"))
COVER_CUT_Z = float(arg("--cover-cut", "0.066"))   # top cover removed above this height (m)
R_OUTER_MM = float(arg("--r-outer", "58.0"))       # lens radius at the OUTER sled position
SHADOW_MM = [float(v) for v in arg("--shadow-mm", "-40,-22").split(",")]   # drop shadow offset on the desk (x, y mm)
SHADOW_BLUR_MM = float(arg("--shadow-blur", "11"))   # its softness (gaussian sigma, mm); long and large (user, 2026-11-11)
CUT_X = float(arg("--cut-x", "0.0015"))            # disc_cut: quarter x > CUT_X, y < centre removed
CHECKS = arg("--checks", "0") == "1"
ANIM = arg("--anim", "0") == "1"                    # render the "disc goes in" animation layers instead (render_caltop_anim.py)
POOL_OFF_MM = [float(v) for v in arg("--pool-off", "22,28").split(",")]   # warm pool centre from the disc centre (x, y mm)
POOL_SIGMA_MM = float(arg("--pool-sigma", "140"))
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
        shadow_rgb="#050807", shadow_alpha=0.42, contact_alpha=0.55,
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
        shadow_rgb="#3a2f22", shadow_alpha=0.24, contact_alpha=0.34,
    ),
}
# The lamp's warm pool on the protagonist (as the lobby's render_desk.py: colour * (amb + gain * f) + add * f,
# f = gaussian of the distance to the pool centre on the desk, weighted vert_w on walls, 1 on top faces). The lamp
# is up and to the right: the pool sits right of and behind the disc centre, the shadows fall lower left.
POOL_STYLE = {
    "dark": dict(amb=(0.8, 0.8, 0.8), gain=(2.0, 1.75, 1.35), add=(0.05, 0.028, 0.006), vert_w=0.55),
    "paper": dict(amb=(0.975, 0.975, 0.975), gain=(0.10, 0.07, 0.025), add=(0.0, 0.0, 0.0), vert_w=0.5),
}
CUR_POOL = None                          # set per variant before materials are built; None = no pool
POOL_C = None                            # pool centre (x, y) in metres; the animation shifts it for moving parts
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
print("[caltop] visible meshes (framing set):", len(render_meshes))


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


# ---------------------------------------------------------------- camera: straight down
VIEW = Vector((0.0, 0.0, -1.0))
RIGHT = Vector((1.0, 0.0, 0.0))
UP = Vector((0.0, 1.0, 0.0))           # the drive's rear at the top of the picture, its front (tray) at the bottom

P = world_verts(render_meshes)
sx, sy = P @ np.array(RIGHT), P @ np.array(UP)
x0, x1, y0, y1 = sx.min(), sx.max(), sy.min(), sy.max()
pad = 0.03 * max(x1 - x0, y1 - y0)
# room for the shadow: it falls left and down by SHADOW_MM plus its blur
blur_m = 2.6 * SHADOW_BLUR_MM / 1000.0
x0 = x0 - pad + min(0.0, SHADOW_MM[0] / 1000.0) - blur_m
y0 = y0 - pad + min(0.0, SHADOW_MM[1] / 1000.0) - blur_m
x1, y1 = x1 + pad, y1 + pad
wext, hext = x1 - x0, y1 - y0
if wext >= hext:
    W, H = LONG, int(round(LONG * hext / wext))
else:
    W, H = int(round(LONG * wext / hext)), LONG
ppu = W / wext if wext >= hext else H / hext
wext, hext = W / ppu, H / ppu
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
del P, sx, sy

cam_data = bpy.data.cameras.new("TopCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(wext, hext)
cam_data.clip_start = 0.01
cam_data.clip_end = 20.0
cam_data.dof.use_dof = False
cam = bpy.data.objects.new("TopCam", cam_data)
scene.collection.objects.link(cam)
cam.location = Vector((cx, cy, 5.0))
cam.rotation_mode = "QUATERNION"
cam.rotation_quaternion = VIEW.to_track_quat("-Z", "Y")
scene.camera = cam
print("[caltop] canvas", W, H, "ppu", ppu)


def to_px(p):
    p = Vector(p)
    return [round(W / 2 + (p.dot(RIGHT) - cx) * ppu, 2), round(H / 2 - (p.dot(UP) - cy) * ppu, 2)]


def dir_px(d, mm=1.0):
    d = Vector(d)
    return [round(d.dot(RIGHT) * ppu / 1000.0 * mm, 5), round(-d.dot(UP) * ppu / 1000.0 * mm, 5)]


# ---------------------------------------------------------------- interior pose
move(tray_objs_all, (0.0, TRAY_OPEN, 0.0))         # tray closed again (frame-1 pose)

# the top cover: whole, on its own layer (drawn translucent by the page); left out of the static parts
cover = bpy.data.objects[COVER]

# disc: the frame-1 disc already sits clamped on the spindle (120 mm, centre on the spindle axis)
disc = bpy.data.objects[DISC_OBJECT]
D_co = world_mesh(disc)
DCX, DCY = [float(v) for v in 0.5 * (D_co.min(0) + D_co.max(0))[:2]]
D_R = float(np.hypot(D_co[:, 0] - DCX, D_co[:, 1] - DCY).max())
D_BOT, D_TOP = float(D_co[:, 2].min()), float(D_co[:, 2].max())
POOL_C = (DCX + POOL_OFF_MM[0] / 1000.0, DCY + POOL_OFF_MM[1] / 1000.0)
print("[caltop] disc centre %.2f %.2f mm, r %.2f mm, z %.2f..%.2f mm"
      % (DCX * 1e3, DCY * 1e3, D_R * 1e3, D_BOT * 1e3, D_TOP * 1e3))

sled = [bpy.data.objects[n] for n in sorted(sled_names) if not bpy.data.objects[n].hide_render]
lens = bpy.data.objects[LENS_OBJECT]
L_co = world_mesh(lens)
LX, LY = [float(v) for v in 0.5 * (L_co.min(0) + L_co.max(0))[:2]]
L_TOP = float(L_co[:, 2].max())
R_INNER = math.hypot(LX - DCX, LY - DCY)
TRAVEL = R_OUTER_MM / 1000.0 - R_INNER
# unit vector from the disc centre through the lens: the pickup travels along it (here ~ -Y)
RAD = Vector((LX - DCX, LY - DCY, 0.0)).normalized()
print("[caltop] lens centre %.2f %.2f mm, top z %.2f, r_inner %.2f mm, travel %.2f mm, dir %s"
      % (LX * 1e3, LY * 1e3, L_TOP * 1e3, R_INNER * 1e3, TRAVEL * 1e3, tuple(round(v, 4) for v in RAD)))

static = [o for o in scene.objects if o.type == "MESH" and not o.hide_render
          and o.name not in sled_names and o not in (disc, cover)]
for i, o in enumerate(static + sled + [disc, cover]):
    o.pass_index = i + 1
ALL_OBJS = static + sled + [disc, cover]
print("[caltop] static %d, sled %d" % (len(static), len(sled)))

LAYER_OBJS = {
    "static": static,
    "sled": sled,
    "disc": [disc],
    "lid": [cover],
    "check_full_inner": static + sled + [disc] + [cover],
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


def pooled(nt, color, is_top):
    """colour * (amb + gain * f) + add * f with the current variant's pool (CUR_POOL) about POOL_C."""
    st = CUR_POOL
    if st is None:
        return color
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    d = nt.nodes.new("ShaderNodeVectorMath")
    d.operation = "SUBTRACT"
    nt.links.new(geo.outputs["Position"], d.inputs[0])
    d.inputs[1].default_value = (POOL_C[0], POOL_C[1], 0.0)
    m0 = nt.nodes.new("ShaderNodeVectorMath")
    m0.operation = "MULTIPLY"
    nt.links.new(d.outputs[0], m0.inputs[0])
    m0.inputs[1].default_value = (1.0, 1.0, 0.0)          # distance on the desk plane
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(m0.outputs[0], dot.inputs[0])
    nt.links.new(m0.outputs[0], dot.inputs[1])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = -1.0 / (2.0 * (POOL_SIGMA_MM / 1000.0) ** 2)
    nt.links.new(dot.outputs["Value"], k.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(k.outputs[0], ex.inputs[0])
    w = nt.nodes.new("ShaderNodeMath")
    w.operation = "MULTIPLY_ADD"
    w.inputs[1].default_value = 1.0 - st["vert_w"]
    w.inputs[2].default_value = st["vert_w"]
    if is_top is None:
        w.inputs[0].default_value = 1.0
    else:
        nt.links.new(is_top, w.inputs[0])
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY"
    nt.links.new(ex.outputs[0], f.inputs[0])
    nt.links.new(w.outputs[0], f.inputs[1])
    cf = nt.nodes.new("ShaderNodeCombineXYZ")
    for ch in "XYZ":
        nt.links.new(f.outputs[0], cf.inputs[ch])
    g = nt.nodes.new("ShaderNodeVectorMath")
    g.operation = "MULTIPLY_ADD"
    nt.links.new(cf.outputs[0], g.inputs[0])
    g.inputs[1].default_value = st["gain"]
    g.inputs[2].default_value = st["amb"]
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY"
    nt.links.new(color, mul.inputs[0])
    nt.links.new(g.outputs[0], mul.inputs[1])
    ad = nt.nodes.new("ShaderNodeVectorMath")
    ad.operation = "MULTIPLY_ADD"
    nt.links.new(cf.outputs[0], ad.inputs[0])
    ad.inputs[1].default_value = st["add"]
    nt.links.new(mul.outputs[0], ad.inputs[2])
    return ad.outputs[0]


def make_toon(name, top, front=None, side=None, pool=True):
    m, nt, emi = new_mat(name)
    if front is None:
        if pool and CUR_POOL is not None:
            rgb = nt.nodes.new("ShaderNodeRGB")
            rgb.outputs[0].default_value = top
            nt.links.new(pooled(nt, rgb.outputs[0], None), emi.inputs["Color"])
        else:
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
    nt.links.new(pooled(nt, mix2.outputs["Result"], is_top.outputs[0]) if pool else mix2.outputs["Result"], emi.inputs["Color"])
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
    global CUR_POOL
    CUR_POOL = POOL_STYLE[v]
    st = VARIANT_STYLE[v]
    mats = {k: toon3("toon_%s_%s" % (k, v), st[k]) for k in ("body", "mech", "tray", "pcb", "sled", "disc")}
    mats["lens"] = make_toon("toon_lens_" + v, hex_lin(st["lens"]))
    mats["led"] = make_toon("toon_led_" + v, hex_lin(st["led"]), pool=False)      # self-lit
    for o in objs:
        if o is disc:
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
    print("[caltop] GPU setup failed, using CPU:", e)
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
    print("[caltop] rendered %s in %.1fs" % (tag, time.time() - t))
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
    print("[caltop] wrote", dst)


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


# ---------------------------------------------------------------- the animation's layers instead (--anim 1)
if ANIM:
    with open(os.path.join(os.getcwd(), "render_caltop_anim.py"), encoding="utf-8") as fh:
        exec(compile(fh.read(), "render_caltop_anim.py", "exec"), globals())
    sys.exit(0)

# ---------------------------------------------------------------- 1. moving parts first (depths)
show(sled)
SL_MASK, SL_A, SL_D = data_passes(sled, "sled")
color_layers(sled, "sled", SL_MASK, [("sled_%s.png", None)])
del SL_MASK

show([disc])
DI_MASK, DI_A, DI_D = data_passes([disc], "disc")
color_layers([disc], "disc", DI_MASK, [("disc_%s.png", None)])
del DI_MASK

show([cover])
LID_MASK, LID_A, _d = data_passes([cover], "lid")
del _d
color_layers([cover], "lid", LID_MASK, [("lid_%s.png", None)])
del LID_MASK

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
print("[caltop] sweep %d steps over %.1f ss-px in %.1fs" % (NSTEP, travel_ss, time.time() - t))


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
print("[caltop] split:", SPLIT)
del ST_D, DI_D, SW_MIN, SW_MAX, AMBIG
color_layers(static, "static", ST_MASK,
             [("bg_%s.png", None), ("mid_%s.png", MID), ("occluders_%s.png", TOP)])
del ST_MASK, TOP, MID, SW_ANY, SL_A

# ---------------------------------------------------------------- 3b. the drop shadow on the desk
# the drive's whole footprint seen from above (static + cover + disc), offset lower left and blurred, plus a
# tight contact shadow hugging the body; straight alpha in the theme's shadow colour


def gauss_blur(a, sigma):
    if sigma <= 0.3:
        return a
    r_ = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r_, r_ + 1) / sigma) ** 2)
    k /= k.sum()
    out = a
    for axis in (0, 1):
        out = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), axis, out)
    return out


foot_ss = (ST_A | LID_A | DI_A).astype(np.float32)
h_, w_ = foot_ss.shape
foot = foot_ss[: h_ // SS * SS, : w_ // SS * SS].reshape(h_ // SS, SS, w_ // SS, SS).mean(axis=(1, 3))[::-1]   # top-down
del foot_ss, ST_A, DI_A, LID_A
pxmm = ppu / 1000.0


def shifted(a, dx_px, dy_px):
    out = np.zeros_like(a)
    dx, dy = int(round(dx_px)), int(round(dy_px))
    ys0, ys1 = max(0, dy), min(a.shape[0], a.shape[0] + dy)
    xs0, xs1 = max(0, dx), min(a.shape[1], a.shape[1] + dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


# screen: +x right, +y down; SHADOW_MM is in desk mm (+y = towards the rear = up on screen)
drop = gauss_blur(shifted(foot, SHADOW_MM[0] * pxmm, -SHADOW_MM[1] * pxmm), SHADOW_BLUR_MM * pxmm)
contact = gauss_blur(shifted(foot, 0.25 * SHADOW_MM[0] * pxmm, -0.25 * SHADOW_MM[1] * pxmm), 1.6 * pxmm)
for v in VARIANTS:
    st = VARIANT_STYLE[v]
    al = np.clip(np.maximum(st["shadow_alpha"] * drop, st["contact_alpha"] * contact), 0, 1)
    al *= (1.0 - foot)                                         # nothing under the drive itself
    rgb = np.broadcast_to(np.array(hex_srgb(st["shadow_rgb"]), dtype=np.float32), al.shape + (3,))
    save_png(np.concatenate([rgb, al[..., None].astype(np.float32)], axis=2)[::-1], os.path.join(OUTDIR, "shadow_%s.png" % v))
del foot, drop, contact

# ---------------------------------------------------------------- 4. one-piece check renders
if CHECKS:
    for name in ("check_full_inner",):
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
info = {
    "image_size": [W, H],
    "pixel_origin": "top-left, y down; final-image pixels; straight down, the drive's front at the bottom",
    "layer_order": [
        {"file": "shadow_%s.png", "blend": "source-over", "moves": False},
        {"file": "bg_%s.png", "blend": "source-over", "moves": False},
        {"file": "sled_%s.png", "blend": "source-over", "moves": "translate by sled.offset_px * t"},
        {"file": "mid_%s.png", "blend": "source-over", "moves": False},
        {"file": "disc_%s.png", "blend": "source-over", "opacity": "about 0.5 to see the pickup through it"},
        {"file": "glow_%s.png", "blend": "dark: lighter; paper: source-over", "moves": "with the sled"},
        {"file": "occluders_%s.png", "blend": "source-over", "moves": False},
        {"file": "lid_%s.png", "blend": "source-over", "opacity": "low (0.15-0.3): the see-through top shell"},
    ],
    "split_counts_supersampled_px": SPLIT,
    "disc": {"centre_px": centre_top, "radius_px": round(D_R * ppu, 2), "radius_mm": round(D_R * 1e3, 2),
             "hole_radius_px": round(0.0075 * ppu, 2),
             "note": "a circle (top view): draw progress and marks in px around centre_px; 1 mm = scale.px_per_mm"},
    "sled": {"file": "sled_%s.png", "radius_mm": [round(R_INNER * 1e3, 2), R_OUTER_MM], "travel_mm": round(TRAVEL * 1e3, 2),
             "offset_px": off, "px_per_mm": dir_px(RAD),
             "direction": "radially outward along %s" % [round(RAD.x, 4), round(RAD.y, 4)],
             "note": "rendered at the INNER position; position(t) = offset_px * t, t = (r_mm - %.2f) / %.2f"
                     % (R_INNER * 1e3, TRAVEL * 1e3)},
    "laser": {"spot_px_inner": to_px((LX, LY, D_TOP)), "spot_px_outer": to_px(tuple(Vector((LX, LY, D_TOP)) + RAD * TRAVEL))},
    "shadow": {"offset_mm": SHADOW_MM, "note": "lamp up right: the shadow falls lower left, more left than down"},
    "scale": {"px_per_mm": round(ppu / 1000.0, 5)},
    "pool": {"centre_px": to_px((POOL_C[0], POOL_C[1], 0.0)), "sigma_px": round(POOL_SIGMA_MM * ppu / 1000.0, 2),
             "sigma_mm": POOL_SIGMA_MM, "style": POOL_STYLE,
             "note": "the lamp's warm pool baked into every layer: lin colour * (amb + gain * f) + add * f, f = exp(-d^2 / 2 sigma^2) on the desk plane (top faces; walls * vert_w)"},
    "render": {"engine": "Cycles, emission-only toon fill, image-space outlines", "supersample": SS, "samples": SAMPLES,
               "line_px": LINE_PX, "source": "derived from interior/render_interior.py"},
}
with open(os.path.join(OUTDIR, "caltop.json"), "w") as fh:
    json.dump(info, fh, indent=2)
print("[caltop] done", OUTDIR, W, H)
