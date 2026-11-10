"""Toon-style isometric still of the optical burner for the disc-probe web home page.

Run headless with Blender 5.2.2+ on a COPY of
docs/goals/video/hero/render_pack/disc_explode_render.blend:

    blender -b disc_explode_render.blend --python render_burner.py -- \
        --outdir OUT [--long 1600] [--ss 4] [--open 0.14] [--variants paper,dark] [--device OPTIX]

What it does
  * Freezes the scene at frame 1 (fully assembled pose), drops all animation,
    hides the disc, the table and the labels/stickers.
  * Slides the tray (tray body + tray door) out of the bezel by --open metres (-Y).
  * Flat "toon" fill: every material becomes an emission shader with one tone for
    up-facing surfaces, one for front-facing (-Y) and one for side-facing (+X).
  * True isometric orthographic camera looking along (-1, +1, -1), i.e. from the
    (+X, -Y, +Z) corner: the drive front (-Y) and the open tray face the lower-left.
  * Outlines are found in image space, not with Freestyle (Freestyle doubled and
    dashed the edges of the thin sheet-metal cover). Two extra 1-sample renders
    encode the facing normal and object id + view depth; a line is drawn where
    coverage, object, depth (step), normal (crease > 30 deg) or tone class changes.
    That gives one clean line per edge whatever is hidden behind it.
  * Cycles, emission only: no lights, no bounces, no reflections, no DOF.
    Everything is rendered at --ss x the target size, composited in sRGB with
    premultiplied alpha and box-filtered down; output is straight-alpha RGBA PNG.
  * Writes burner_<variant>.png and burner.json (placement data).
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

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
os.makedirs(OUTDIR, exist_ok=True)

# ---------------------------------------------------------------- palettes
VARIANT_STYLE = {
    "paper": dict(
        top="#f1eee8", front="#d9d4cb", side="#d0cac0",
        tray_mul=0.94, cavity="#bfb8ac", led="#b3ab9e",
        line="#2b2924", line_alpha=1.0,
    ),
    "dark": dict(
        top="#222b2a", front="#1a2221", side="#1d2625",
        tray_mul=0.93, cavity="#111716", led="#d9a75c",
        line="#d5d9d2", line_alpha=0.55,
    ),
}
LINE_PX = 0.8            # outline width in final pixels
CREASE_DEG = 30.0        # normal change between neighbouring pixels that counts as an edge
DEPTH_STEP_M = 0.0004    # depth jump (beyond the local slope) that counts as an edge
TOP_NZ = 0.55            # normal.z above this -> "top" tone

# Objects that move with the tray when it opens.
TRAY_OBJECTS = {"KSL210_tray_final-1", "SHELL_tray_door", "SHELL_door_print"}
# Decorative decals that would only add noise in a flat render.
HIDE_OBJECTS = {"table", "Label_simulated", "SHELL_label_round", "SHELL_sticker_side",
                "SHELL_sticker_rear", "SHELL_door_print", "SHELL_badge",
                "KSL210_tray-1", "cd-1"}
HIDE_COLLECTIONS = {"Disc", "Overlay", "SW_hidden"}
# Shell parts get the body palette; everything else visible is "inside" (cavity tone).
BODY_PREFIX = "SHELL_"
LED_OBJECT = "SHELL_led"


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_srgb(h, mul=1.0):
    h = h.lstrip("#")
    return [min(1.0, int(h[i:i + 2], 16) / 255.0 * mul) for i in (0, 2, 4)]


def hex_lin(h, mul=1.0):
    return tuple(srgb_to_linear(c) for c in hex_srgb(h, mul)) + (1.0,)


# ---------------------------------------------------------------- scene freeze
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
print("[burner] visible meshes:", len(render_meshes))

# ---------------------------------------------------------------- shaders


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
    """World normal flipped toward the viewer: N * (1 - 2*backfacing)."""
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
    add = nt.nodes.new("ShaderNodeMath")          # +X side vs -Y front: nx + ny > 0
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
    """Emission = facing normal * 0.5 + 0.5."""
    m, nt, emi = new_mat("data_normal")
    vm = nt.nodes.new("ShaderNodeVectorMath")
    vm.operation = "MULTIPLY_ADD"
    vm.inputs[1].default_value = (0.5, 0.5, 0.5)
    vm.inputs[2].default_value = (0.5, 0.5, 0.5)
    nt.links.new(facing_normal(nt), vm.inputs[0])
    nt.links.new(vm.outputs["Vector"], emi.inputs["Color"])
    return m


def make_id_mat():
    """Emission R = object pass index / 1000, G = view Z depth (m), B = 1."""
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


def apply_variant(v):
    st = VARIANT_STYLE[v]
    body = make_toon("toon_body_" + v, hex_lin(st["top"]), hex_lin(st["front"]), hex_lin(st["side"]))
    tm = st["tray_mul"]
    tray = make_toon("toon_tray_" + v, hex_lin(st["top"], tm), hex_lin(st["front"], tm),
                     hex_lin(st["side"], tm))
    cavity = make_toon("toon_cavity_" + v, hex_lin(st["cavity"]))
    led = make_toon("toon_led_" + v, hex_lin(st["led"]))
    for o in render_meshes:
        if o.name == LED_OBJECT:
            assign(o, led)
        elif o.name in TRAY_OBJECTS:
            assign(o, tray)
        elif o.name.startswith(BODY_PREFIX):
            assign(o, body)
        else:
            assign(o, cavity)


def apply_single(mat):
    for o in render_meshes:
        assign(o, mat)


# ---------------------------------------------------------------- camera
VIEW = Vector((-1.0, 1.0, -1.0)).normalized()          # camera forward
RIGHT = VIEW.cross(Vector((0, 0, 1))).normalized()     # screen right
UP = RIGHT.cross(VIEW).normalized()                    # screen up


def world_verts(objs):
    pts = []
    for o in objs:
        oe = o.evaluated_get(deps)
        me = oe.to_mesh()
        n = len(me.vertices)
        if n:
            co = np.empty(n * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            mw = np.array(oe.matrix_world)
            pts.append(co @ mw[:3, :3].T + mw[:3, 3])
        oe.to_mesh_clear()
    return np.concatenate(pts)


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
ppu = W / wext if wext >= hext else H / hext          # final pixels per Blender unit (m)
wext, hext = W / ppu, H / ppu                           # keep pixels exactly square
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)

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


def to_px(p):
    """World point -> final-image pixel (origin top-left, y down)."""
    p = Vector(p)
    return [round(W / 2 + (p.dot(RIGHT) - cx) * ppu, 2), round(H / 2 - (p.dot(UP) - cy) * ppu, 2)]


# ---------------------------------------------------------------- render setup
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
except Exception as e:  # CPU fallback
    print("[burner] GPU setup failed, using CPU:", e)
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
    print("[burner] rendered %s in %.1fs" % (tag, time.time() - t))
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)  # bottom-up rows, as Blender stores them


# ---------------------------------------------------------------- outline mask


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
        # pairs (p, q) = (i, i+1) along this axis
        a_p, a_q = sl(alpha, 0, -1), sl(alpha, 1, None)
        d_p, d_q = sl(depth, 0, -1), sl(depth, 1, None)
        both = a_p & a_q
        diff = a_p != a_q
        diff |= both & (sl(oid, 0, -1) != sl(oid, 1, None))
        diff |= both & (sl(tone, 0, -1) != sl(tone, 1, None))
        diff |= both & ((sl(n, 0, -1) * sl(n, 1, None)).sum(-1) < cos_c)
        # depth step beyond the local slope (planes keep a constant first difference)
        jump = np.abs(d_q - d_p)
        dd = np.abs(np.diff(depth, axis=axis))
        pad = np.full_like(sl(dd, 0, 1), 1e9)
        before = np.concatenate([pad, sl(dd, 0, -1)], axis=axis)
        after = np.concatenate([sl(dd, 1, None), pad], axis=axis)
        slope = np.minimum(before, after)
        diff |= both & (jump > 2.0 * slope + DEPTH_STEP_M)
        # mark the pixel nearer to the camera (the occluder / the object side)
        near_p = d_p <= d_q
        mp = diff & near_p
        mq = diff & ~near_p
        idx_p = [slice(None)] * 2
        idx_q = [slice(None)] * 2
        idx_p[axis] = slice(0, -1)
        idx_q[axis] = slice(1, None)
        edge[tuple(idx_p)] |= mp
        edge[tuple(idx_q)] |= mq

    # drop speckles (tessellation noise on fillets): keep an edge pixel only if its
    # 7x7 neighbourhood holds >= 6 edge pixels, which any real line through it does
    k = 7
    e = edge.astype(np.int32)
    c = np.pad(e, ((k // 2 + 1, k // 2), (k // 2 + 1, k // 2))).cumsum(0).cumsum(1)
    box = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    edge &= box >= 6

    # thicken the 1 px edge to LINE_PX final pixels
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


def compose_and_save(color_px, mask, st, dst):
    a = color_px[..., 3:4]
    straight = np.where(a > 1e-6, color_px[..., :3] / np.maximum(a, 1e-6), 0.0)
    pm = lin_to_srgb(straight) * a                       # premultiplied sRGB
    line = np.array(hex_srgb(st["line"]), dtype=np.float32)
    c = (mask.astype(np.float32) * np.float32(st["line_alpha"]))[..., None]
    pm = line * c + pm * (1.0 - c)
    al = c + a * (1.0 - c)
    rgba = np.concatenate([pm, al], axis=2)
    h, w = rgba.shape[:2]
    f = SS
    rgba = rgba[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
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
    print("[burner] wrote", dst)


# data passes: 1 sample, near-zero filter -> exact per-pixel values
apply_single(make_normal_mat())
nrm_px = render_exr("normal", 1, 0.01)
apply_single(make_id_mat())
id_px = render_exr("id", 1, 0.01)
t = time.time()
MASK = outline_mask(nrm_px, id_px)
print("[burner] outline mask %.1fs, %d px" % (time.time() - t, MASK.sum()))
del nrm_px, id_px

for v in VARIANTS:
    apply_variant(v)
    col = render_exr("color_" + v, SAMPLES, 1.5)
    compose_and_save(col, MASK, VARIANT_STYLE[v], os.path.join(OUTDIR, "burner_%s.png" % v))
    del col

# ---------------------------------------------------------------- placement json
shell = [o for o in render_meshes if o.name.startswith(BODY_PREFIX) and o.name not in TRAY_OBJECTS]
S = world_verts(shell)
bx0, by0, bx1, by1 = S[:, 0].min(), S[:, 1].min(), S[:, 0].max(), S[:, 1].max()
T = world_verts([o for o in render_meshes if o.name in TRAY_OBJECTS])
tx0, ty0, tx1 = T[:, 0].min(), T[:, 1].min(), T[:, 0].max()
MM = 1000.0                          # scene unit is the metre; the model is CAD millimetres
axis_factor = math.sqrt(2.0 / 3.0)   # isometric foreshortening of each world axis

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
with open(os.path.join(OUTDIR, "burner.json"), "w") as fh:
    json.dump(info, fh, indent=2)
print("[burner] done", OUTDIR, W, H)
