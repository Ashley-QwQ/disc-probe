"""Render the lobby desk layers (toon, burner style) from desk_scene.blend.

    blender -b desk_scene.blend --python render_desk.py -- --outdir renders
        [--layers base,sheets,open,stack,stack_top] [--variants paper,dark] [--ss 4] [--samples 16]
        [--device OPTIX] [--force] [--layers full]   (full = everything in one render, for checking)

Method (as render_burner.py / render_hand.py):
  * camera, canvas and all placement data come from the .blend (build_desk.py);
  * colour = emission only, 3 tones by facing (top n.z > 0.55, front -Y, side +X); imported props get
    3 bands on N.L with blurred normals instead; the lamp's warm pool is baked into every material as a
    Gaussian of the distance to the pool centre on the desk;
  * shadows (base layer only): two extra direct-light renders, white diffuse, with and without shadows,
    every object casting but only the layer's objects seen by the camera; shadow = 1 - lit / unlit,
    banded, then mixed toward the layer rendered without the pool and darkened. Paper: soft overhead room
    light; dark: the lamp's bulb (point light);
  * outlines in image space from a 1-sample normal pass and an object-id + depth pass (coverage, object,
    depth step, crease > 30 deg, facing-tone change; no tone lines inside banded props);
  * rendered at --ss x size, composited in sRGB with premultiplied alpha, box-filtered down, straight
    alpha PNG. Big buffers are processed in horizontal strips to keep memory low.
Writes desk_<layer>_<variant>.png and render_<layer>.json (timings, layer bbox). Skips existing PNGs
unless --force.
"""
import json
import math
import os
import sys
import time

import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import night_b_palette as _NB   # tools/night_b_palette.py, copied next to this script
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


OUTDIR = os.path.abspath(arg("--outdir", "renders"))
LAYERS = arg("--layers", "all").split(",")
# --glow glow.json: the monitor switched on (lobby v3 "screen_on"): the screen face self-lit in face_<theme>, and a
# cool spill baked into every surface: colour * (1 + gain * g) + add * g, g = Gaussian of the distance to pos_mm
# (sigma_mm) times max(0, n . direction to pos_mm)
GLOW = json.load(open(arg("--glow", ""))) if arg("--glow", "") else None
MIST = "--no-mist" not in argv
HOLDOUT_BASE = "--no-holdout" not in argv  # object layers cut by the base layer's geometry in front of them           # 8-bit view-depth PNGs per layer (free: from the id pass)
VARIANTS = arg("--variants", "paper,dark").split(",")
SS = int(arg("--ss", "4"))
SAMPLES = int(arg("--samples", "16"))
SHADOW_SAMPLES = int(arg("--shadow-samples", "8"))
DEVICE = arg("--device", "OPTIX")
FORCE = "--force" in argv
NIGHT_GAIN = float(arg("--night-gain", "5.8"))
NIGHT_SIGMA_SCALE = float(arg("--night-sigma-scale", "1.0"))
os.makedirs(OUTDIR, exist_ok=True)
T0 = time.time()

VARIANT_STYLE = {
    "paper": dict(
        desk=("#ddd6cb", "#c9c1b4", "#c1b8aa"),
        kraft=("#d0c0a2", "#bcab8e", "#b3a386"),
        kraft_flap=("#d5c6aa", "#c0b094", "#b8a88c"),
        kraft_flap_in=("#dbcfb7", "#c6b99f", "#beb197"),
        cavity=("#9a8c76", "#85786a", "#8b7e6c"),
        cavity_wall=("#8c7f6b", "#7b6f61", "#817464"),
        button=("#f3f0ea", "#dfdbd3", "#d7d3ca"),
        grommet=("#aaa59d", "#8f8a83", "#98938b"),
        string=("#efe9de", "#dad3c5", "#d3cbbd"),
        sheet=("#f9f8f4", "#e6e3dc", "#dfdbd3"),
        lamp_shade=("#b88a66", "#a2714d", "#976846"),
        lamp_metal=("#827d76", "#6c6761", "#645f59"),
        prop_tint="#d8d2c8",
        line="#2b2924", line_alpha=1.0,
        amb=(0.975, 0.975, 0.975), gain=(0.075, 0.055, 0.02), add=(0.0, 0.0, 0.0), vert_w=0.5,
        shadow_mul=0.84, shadow_keep=0.0,
        light_dir=(-0.35, -0.55, 1.0),
        bg="#ebe7e0",
        wall=("#f1eee8", "#e2ddd4", "#d8d2c8"), floor=("#d3ccc0", "#c2baac", "#bab2a4"),
        skirting=("#efebe4", "#d9d3c9", "#d0c9be"), casing=("#f0ece5", "#ddd7cd", "#d3ccc1"),
        door=("#ddd5c7", "#cbc2b3", "#c2b9a9"), door_panel=("#e3dccf", "#d0c8b9", "#c8bfb0"),
        metal=("#8c877f", "#76716a", "#6e6963"), metal_light=("#b3aea6", "#9d988f", "#958f87"),
        sign=("#f2efe9", "#dfdad1", "#d6d1c7"), sign_text=("#4a4740",) * 3,
        bin=("#c9c4bb", "#b4aea4", "#aca69b"), screen_frame=("#6f6c67", "#5d5a55", "#57544f"),
        screen_face=("#3c4140",) * 3, drawer=("#e2d8c6", "#cdc1ad", "#c4b8a3"),
        box=("#bdb7ad", "#a7a197", "#9f998f"), pen=("#45423c", "#38352f", "#3c3933"),
        pen_metal=("#b8b3aa", "#a19c93", "#99948b"), glass=("#e6ecea", "#d4dbd9", "#ccd3d1"),
        handle=("#5d5850", "#4c4842", "#524d46"), lamp_glow=("#ebe6dc",) * 3,
        panel_frame=("#a59f95", "#8f897f", "#878177"), panel_face=("#e9e5dd", "#d8d3c9", "#d0cbc1"),
        book_cover=("#8e978c", "#7a8378", "#737c71"), album_cover=("#a5958a", "#8f8076", "#87786e"),
        pages=("#f4f1ea", "#e2ddd3", "#dad5ca"), photo=("#8d918e", "#7c807d", "#767a77"),
        # lobby v3: the burner page's drive (render_burner.py palette) with a blank disc, and the stage floor
        # (page background / ambient, so it meets the page edge with no seam away from the lamp)
        drive_body=("#f1eee8", "#d9d4cb", "#d0cac0"), drive_tray=("#e3e0da", "#ccc7bf", "#c4beb5"),
        drive_cavity=("#bfb8ac",) * 3, drive_led=("#b3ab9e",) * 3,
        disc=("#f6f4ef", "#e3e0da", "#dbd8d2"), disc_hub=("#d4d6d3", "#c3c5c2", "#bbbdba"),
        disc_rim=("#c9cbc8", "#b8bab7", "#b0b2af"), stage=("#eeeae3",) * 3,
    ),
    "dark": dict(
        desk=("#111a1e", "#091013", "#0b1317"),
        kraft=("#3b352c", "#2c2822", "#312c25"),
        kraft_flap=("#3e382e", "#2e2a23", "#332e27"),
        kraft_flap_in=("#433d33", "#322d26", "#37322a"),
        cavity=("#16130f", "#110f0c", "#13110d"),
        cavity_wall=("#13110e", "#0f0d0b", "#11100c"),
        button=("#545e62", "#3e4549", "#444c4f"),
        grommet=("#272c2f", "#191d1f", "#202527"),
        string=("#697175", "#4e5558", "#545b5f"),
        sheet=("#3d4549", "#2c3236", "#31383b"),
        lamp_shade=("#6f5a3e", "#584631", "#5f4c36"),
        lamp_metal=("#333b3e", "#22292c", "#272e32"),
        prop_tint="#353f43",
        line="#d5d9d2", line_alpha=0.55,
        amb=(0.64, 0.64, 0.64), gain=(NIGHT_GAIN,) * 3, add=(0.0, 0.0, 0.0), vert_w=0.55,
        shadow_mul=0.86, shadow_keep=0.3,
        shadow_light_height_mm=900,   # fake: shadows cast from above the bulb, so they stay short
        light_dir=None,            # bands toward the bulb
        bg="#0a1114",
        wall=("#212b30", "#0f181c", "#131c20"), floor=("#090f12", "#060b0e", "#070d10"),
        skirting=("#1e292e", "#0e1619", "#10181c"), casing=("#222c31", "#111a1e", "#172025"),
        door=("#1c272b", "#0e171b", "#111a1e"), door_panel=("#212b30", "#111a1e", "#172025"),
        metal=("#42494d", "#2e3639", "#343c3f"), metal_light=("#575f62", "#3f464a", "#454d50"),
        sign=("#1e2d34", "#101d23", "#16242b"), sign_text=("#9cc4a6",) * 3,
        bin=("#242c30", "#161d20", "#1d2327"), screen_frame=("#21282b", "#13181b", "#181f22"),
        screen_face=("#04090b",) * 3, drawer=("#1f292d", "#10181c", "#141c20"),
        box=("#293135", "#1d2327", "#21282b"), pen=("#535b5f", "#3f4548", "#454c4f"),
        pen_metal=("#6a7276", "#51595d", "#586064"), glass=("#334147", "#253137", "#2a353b"),
        handle=("#32393c", "#23292c", "#282e31"), lamp_glow=("#f4d495",) * 3,
        panel_frame=("#262d31", "#171d20", "#1e2426"), panel_face=("#1c262a", "#0f171b", "#121a1e"),
        book_cover=("#243841", "#192930", "#1d2d34"), album_cover=("#3e3632", "#2f2926", "#342d2a"),
        pages=("#41494d", "#2f3639", "#343b3e"), photo=("#20282b",) * 3,
        drive_body=("#182227", "#0d161a", "#0f191e"), drive_tray=("#131c20", "#0b1317", "#0d161b"),
        drive_cavity=("#070d10",) * 3, drive_led=("#d9a75c",) * 3,
        disc=("#42494d", "#30383b", "#353d40"), disc_hub=("#2d3437", "#21282b", "#252c30"),
        disc_rim=("#373e41", "#272e32", "#2b3236"), stage=("#0d1518",) * 3,
    ),
}
LINE_PX = 0.8
CREASE_DEG = 30.0
DEPTH_STEP_M = 0.0004
TOP_NZ = 0.55
BANDS = (0.15, 0.55)
BAND_ID0 = 500                     # pass_index >= this: banded (imported) object
STRIP = 1024                       # rows per strip at supersampled size (multiple of SS)
NOPOOL = {"lamp_glow", "sign_text"}  # self-lit: no pool, no shadow darkening of their own colour
THIN_FAR = 0.6                     # far lines lose up to this share of their outer sub-pixel ring

scene = bpy.context.scene
META = json.loads(scene["desk_meta"])
POOL = json.loads(scene["pool"])
BULB = Vector(scene["bulb"])
Wpx, Hpx = META["image_size"]
FADE = json.loads(scene["fade"]) if "fade" in scene else None     # baked aerial perspective (build_room.py)
CAM_OFF = float(scene.get("cam_view_offset", 0.0))
ROOM = "room" in scene.get("desk_meta", "") and "fade" in scene
if ROOM:                                   # v2 room scene: the room is dimmer away from the lamp at night
    VARIANT_STYLE["dark"].update(amb=(0.64, 0.64, 0.64), gain=(NIGHT_GAIN,) * 3, add=(0.0, 0.0, 0.0),
                                 shadow_light_height_mm=None)
    VARIANT_STYLE["paper"].update(gain=(0.02, 0.015, 0.005))      # lamp off in the paper theme
    if any(o.get("mat") == "stage" for o in scene.objects):        # lobby v3 (desk on a stage floor): the paper
        VARIANT_STYLE["paper"].update(light_dir=(-0.12, -0.2, 1.0))  # room light nearly overhead, shadow under the desk


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_srgb(h, mul=1.0):
    h = h.lstrip("#")
    return [min(1.0, int(h[i:i + 2], 16) / 255.0 * mul) for i in (0, 2, 4)]


def hex_lin(h, mul=1.0):
    return tuple(srgb_to_linear(c) for c in hex_srgb(h, mul)) + (1.0,)


# ---------------------------------------------------------------- objects
meshes = [o for o in scene.objects if o.type == "MESH"]
for o in [o for o in scene.objects if o.type == "LIGHT"]:
    bpy.data.objects.remove(o)
facing_objs = [o for o in meshes if o.get("kind", "facing") == "facing"]
band_objs = [o for o in meshes if o.get("kind") == "bands"]
# thin tubes (strings, chain) get no facing-tone lines: they would flip tone around the tube and turn
# the whole string into line colour. Their ids go in the "no tone lines" range with the props.
NOLINES = [o for o in facing_objs if o.get("nolines") or o.name.endswith(("_string", "_chain"))]
for i, o in enumerate([o for o in facing_objs if o not in NOLINES]):
    o.pass_index = i + 1
for i, o in enumerate(band_objs):
    o.pass_index = BAND_ID0 + i
for i, o in enumerate(NOLINES):
    o.pass_index = BAND_ID0 + 300 + i
LIGHT_OBJS = set(o.name for o in meshes if o.name.startswith("lamp_") or o.get("light", 0))

# blurred normals for imported props (as render_hand.py)
for o in band_objs:
    it = int(o.get("smooth", 20))
    if it <= 0:
        continue
    ng = bpy.data.node_groups.new("smooth_normals_" + o.name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    nn = ng.nodes.new("GeometryNodeInputNormal")
    bl = ng.nodes.new("GeometryNodeBlurAttribute")
    bl.data_type = "FLOAT_VECTOR"
    bl.inputs["Iterations"].default_value = it
    st_ = ng.nodes.new("GeometryNodeStoreNamedAttribute")
    st_.data_type = "FLOAT_VECTOR"
    st_.domain = "POINT"
    st_.inputs["Name"].default_value = "smooth_n"
    vin = [i for i in bl.inputs if i.name == "Value" and i.type == "VECTOR"][0]
    vout = [q for q in bl.outputs if q.name == "Value" and q.type == "VECTOR"][0]
    ng.links.new(nn.outputs["Normal"], vin)
    ng.links.new(gi.outputs[0], st_.inputs["Geometry"])
    ng.links.new(vout, [i for i in st_.inputs if i.name == "Value" and i.type == "VECTOR"][0])
    ng.links.new(st_.outputs["Geometry"], go.inputs[0])
    o.modifiers.new("smooth_normals", "NODES").node_group = ng

# ---------------------------------------------------------------- shader building blocks


def new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def emission(nt, color_socket=None, color=None):
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Strength"].default_value = 1.0
    if color_socket is not None:
        nt.links.new(color_socket, emi.inputs["Color"])
    elif color is not None:
        emi.inputs["Color"].default_value = color
    return emi.outputs[0]


def finish(nt, out, shader, cull):
    """backface -> transparent for culled objects"""
    if cull:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
        nt.links.new(shader, mix.inputs[1])
        nt.links.new(tr.outputs[0], mix.inputs[2])
        shader = mix.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])


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


def smooth_normal(nt):
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = "smooth_n"
    vt = nt.nodes.new("ShaderNodeVectorTransform")
    vt.vector_type = "NORMAL"
    vt.convert_from = "OBJECT"
    vt.convert_to = "WORLD"
    nt.links.new(at.outputs["Vector"], vt.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeVectorMath")
    nz.operation = "NORMALIZE"
    nt.links.new(vt.outputs["Vector"], nz.inputs[0])
    # fall back to the shading normal when the attribute is missing (length 0)
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    nt.links.new(at.outputs["Vector"], ln.inputs[0])
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 1e-6
    nt.links.new(ln.outputs["Value"], gt.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "VECTOR"
    nt.links.new(gt.outputs[0], mix.inputs["Factor"])
    nt.links.new(facing_normal(nt), mix.inputs[4])
    nt.links.new(nz.outputs["Vector"], mix.inputs[5])
    return mix.outputs[1]


def facing_tone(nt, nrm, top, front, side):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nrm, sep.inputs[0])
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
    return mix2.outputs["Result"], is_top.outputs[0]


def band_tone(nt, nrm, light, mid, shadow, light_dir):
    if light_dir is None:      # toward the bulb
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sub = nt.nodes.new("ShaderNodeVectorMath")
        sub.operation = "SUBTRACT"
        sub.inputs[0].default_value = tuple(BULB)
        nt.links.new(geo.outputs["Position"], sub.inputs[1])
        ldir = nt.nodes.new("ShaderNodeVectorMath")
        ldir.operation = "NORMALIZE"
        nt.links.new(sub.outputs[0], ldir.inputs[0])
        lsock = ldir.outputs[0]
    else:
        lsock = None
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(nrm, dot.inputs[0])
    if lsock is not None:
        nt.links.new(lsock, dot.inputs[1])
    else:
        dot.inputs[1].default_value = tuple(Vector(light_dir).normalized())
    remap = nt.nodes.new("ShaderNodeMath")
    remap.operation = "MULTIPLY_ADD"
    remap.inputs[1].default_value = 0.5
    remap.inputs[2].default_value = 0.5
    nt.links.new(dot.outputs["Value"], remap.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = shadow
    cr.elements[1].position = (BANDS[0] + 1) / 2
    cr.elements[1].color = mid
    e = cr.elements.new((BANDS[1] + 1) / 2)
    e.color = light
    nt.links.new(remap.outputs[0], ramp.inputs["Fac"])
    # weight for the pool: like a top face when the smoothed normal points up
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nrm, sep.inputs[0])
    is_top = nt.nodes.new("ShaderNodeMath")
    is_top.operation = "GREATER_THAN"
    is_top.inputs[1].default_value = TOP_NZ
    nt.links.new(sep.outputs["Z"], is_top.inputs[0])
    return ramp.outputs["Color"], is_top.outputs[0]


def glowed(nt, color, v):
    """the screen's spill: colour * (1 + gain * g) + add * g (see GLOW)"""
    if not GLOW or v is None:
        return color
    gp = GLOW[v]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = tuple(c / 1000.0 for c in GLOW["pos_mm"])
    nt.links.new(geo.outputs["Position"], sub.inputs[1])
    d2 = nt.nodes.new("ShaderNodeVectorMath")
    d2.operation = "DOT_PRODUCT"
    nt.links.new(sub.outputs[0], d2.inputs[0])
    nt.links.new(sub.outputs[0], d2.inputs[1])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = -1.0 / (2.0 * (GLOW["sigma_mm"] / 1000.0) ** 2)
    nt.links.new(d2.outputs["Value"], k.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(k.outputs[0], ex.inputs[0])
    nz = nt.nodes.new("ShaderNodeVectorMath")
    nz.operation = "NORMALIZE"
    nt.links.new(sub.outputs[0], nz.inputs[0])
    nd = nt.nodes.new("ShaderNodeVectorMath")
    nd.operation = "DOT_PRODUCT"
    nt.links.new(facing_normal(nt), nd.inputs[0])
    nt.links.new(nz.outputs[0], nd.inputs[1])
    cl = nt.nodes.new("ShaderNodeClamp")
    nt.links.new(nd.outputs["Value"], cl.inputs["Value"])
    g = nt.nodes.new("ShaderNodeMath")
    g.operation = "MULTIPLY"
    nt.links.new(ex.outputs[0], g.inputs[0])
    nt.links.new(cl.outputs[0], g.inputs[1])
    cg = nt.nodes.new("ShaderNodeCombineXYZ")
    for ch in "XYZ":
        nt.links.new(g.outputs[0], cg.inputs[ch])
    f = nt.nodes.new("ShaderNodeVectorMath")             # 1 + gain * g
    f.operation = "MULTIPLY_ADD"
    nt.links.new(cg.outputs[0], f.inputs[0])
    f.inputs[1].default_value = tuple(gp["gain"])
    f.inputs[2].default_value = (1.0, 1.0, 1.0)
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY"
    nt.links.new(color, mul.inputs[0])
    nt.links.new(f.outputs[0], mul.inputs[1])
    ad = nt.nodes.new("ShaderNodeVectorMath")
    ad.operation = "MULTIPLY_ADD"
    nt.links.new(cg.outputs[0], ad.inputs[0])
    ad.inputs[1].default_value = tuple(gp["add"])
    nt.links.new(mul.outputs[0], ad.inputs[2])
    return ad.outputs[0]


def pooled(nt, color, is_top, st, use_pool, v=None):
    """colour * (amb + gain * pool(P) * w) + add * pool(P) * w; w = 1 on top faces, vert_w elsewhere.
    With --glow and v given, the screen's spill on top (also without the pool)."""
    if not use_pool:
        return glowed(nt, color, v)
    return glowed(nt, pooled_lamp(nt, color, is_top, st, v), v)


def pooled_lamp(nt, color, is_top, st, v):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    p3 = POOL.get("mode") == "3d"
    dx = nt.nodes.new("ShaderNodeMath")
    dx.operation = "SUBTRACT"
    nt.links.new(sep.outputs["X"], dx.inputs[0])
    dx.inputs[1].default_value = POOL["center"][0]
    dy = nt.nodes.new("ShaderNodeMath")
    dy.operation = "SUBTRACT"
    nt.links.new(sep.outputs["Y"], dy.inputs[0])
    dy.inputs[1].default_value = POOL["center"][1]
    c2 = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dx.outputs[0], c2.inputs["X"])
    nt.links.new(dy.outputs[0], c2.inputs["Y"])
    if p3:
        dz = nt.nodes.new("ShaderNodeMath")
        dz.operation = "SUBTRACT"
        nt.links.new(sep.outputs["Z"], dz.inputs[0])
        dz.inputs[1].default_value = POOL["center"][2]
        nt.links.new(dz.outputs[0], c2.inputs["Z"])
    dvec = c2.outputs[0]
    if POOL.get("mode") == "segment":      # distance to the segment a..b (an elongated pool)
        A, B = Vector(POOL["a"]), Vector(POOL["b"])
        AB = B - A
        ap = nt.nodes.new("ShaderNodeVectorMath")
        ap.operation = "SUBTRACT"
        nt.links.new(geo.outputs["Position"], ap.inputs[0])
        ap.inputs[1].default_value = tuple(A)
        tdot = nt.nodes.new("ShaderNodeVectorMath")
        tdot.operation = "DOT_PRODUCT"
        nt.links.new(ap.outputs[0], tdot.inputs[0])
        tdot.inputs[1].default_value = tuple(AB / max(AB.length_squared, 1e-12))
        tcl = nt.nodes.new("ShaderNodeClamp")
        nt.links.new(tdot.outputs["Value"], tcl.inputs["Value"])
        sc = nt.nodes.new("ShaderNodeVectorMath")
        sc.operation = "SCALE"
        sc.inputs[0].default_value = tuple(AB)
        nt.links.new(tcl.outputs[0], sc.inputs["Scale"])
        dd = nt.nodes.new("ShaderNodeVectorMath")
        dd.operation = "SUBTRACT"
        nt.links.new(ap.outputs[0], dd.inputs[0])
        nt.links.new(sc.outputs[0], dd.inputs[1])
        dvec = dd.outputs[0]
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(dvec, dot.inputs[0])
    nt.links.new(dvec, dot.inputs[1])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    # Card T review 2: original width by default; paper and lines stay unchanged.
    sigma = POOL["sigma"] * (NIGHT_SIGMA_SCALE if v == "dark" else 1.0)
    k.inputs[1].default_value = -1.0 / (2.0 * sigma ** 2)
    nt.links.new(dot.outputs["Value"], k.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(k.outputs[0], ex.inputs[0])
    w = nt.nodes.new("ShaderNodeMath")              # w = vert_w + (1 - vert_w) * is_top
    w.operation = "MULTIPLY_ADD"
    w.inputs[1].default_value = 1.0 - st["vert_w"]
    w.inputs[2].default_value = st["vert_w"]
    nt.links.new(is_top, w.inputs[0])
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY"
    nt.links.new(ex.outputs[0], f.inputs[0])
    nt.links.new(w.outputs[0], f.inputs[1])
    g = nt.nodes.new("ShaderNodeVectorMath")         # amb + gain * f
    g.operation = "MULTIPLY_ADD"
    g.inputs[1].default_value = st["gain"]
    g.inputs[2].default_value = st["amb"]
    cf = nt.nodes.new("ShaderNodeCombineXYZ")
    for ch in "XYZ":
        nt.links.new(f.outputs[0], cf.inputs[ch])
    nt.links.new(cf.outputs[0], g.inputs[0])
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY"
    nt.links.new(color, mul.inputs[0])
    nt.links.new(g.outputs[0], mul.inputs[1])
    ad = nt.nodes.new("ShaderNodeVectorMath")            # + add * f
    ad.operation = "MULTIPLY_ADD"
    nt.links.new(cf.outputs[0], ad.inputs[0])
    ad.inputs[1].default_value = st["add"]
    nt.links.new(mul.outputs[0], ad.inputs[2])
    return ad.outputs[0]


MAT_CACHE = {}


def toon_mat(o, v, use_pool):
    st = VARIANT_STYLE[v]
    cull = int(o.get("cull", 0))
    if o.get("kind") == "bands":
        tint = (o.get("tint_dark") or st["prop_tint"]) if v == "dark" else (o.get("tint") or st["prop_tint"])
        if v == "dark":                # night B: per-object dark tints stored in the .blend follow the same rule
            tint = _NB.remap(tint)
        key = ("band", tint, v, use_pool, cull)
        if key not in MAT_CACHE:
            m, nt, out = new_mat("toon_band_%s_%s_%d_%d" % (tint, v, use_pool, cull))
            col, is_top = band_tone(nt, smooth_normal(nt), hex_lin(tint), hex_lin(tint, 0.88),
                                    hex_lin(tint, 0.74), st["light_dir"])
            finish(nt, out, emission(nt, pooled(nt, col, is_top, st, use_pool, v)), cull)
            MAT_CACHE[key] = m
        return MAT_CACHE[key]
    mk = o.get("mat", "desk")
    if GLOW and mk == "screen_face":           # the screen itself: self-lit, flat
        key = ("screen_on", v)
        if key not in MAT_CACHE:
            m, nt, out = new_mat("toon_screen_on_%s" % v)
            finish(nt, out, emission(nt, color=hex_lin(GLOW[v]["face"])), cull)
            MAT_CACHE[key] = m
        return MAT_CACHE[key]
    use_pool = use_pool and mk not in NOPOOL
    key = ("facing", mk, v, use_pool, cull)
    if key not in MAT_CACHE:
        m, nt, out = new_mat("toon_%s_%s_%d_%d" % (mk, v, use_pool, cull))
        tones = [hex_lin(c) for c in st[mk]]
        col, is_top = facing_tone(nt, facing_normal(nt), *tones)
        finish(nt, out, emission(nt, pooled(nt, col, is_top, st, use_pool, v)), cull)
        MAT_CACHE[key] = m
    return MAT_CACHE[key]


def data_mat(kind, o):
    cull = int(o.get("cull", 0))
    band = o.get("kind") == "bands"
    key = ("data", kind, cull, band)
    if key in MAT_CACHE:
        return MAT_CACHE[key]
    m, nt, out = new_mat("data_%s_%d_%d" % (kind, cull, band))
    if kind == "normal":
        vm = nt.nodes.new("ShaderNodeVectorMath")
        vm.operation = "MULTIPLY_ADD"
        vm.inputs[1].default_value = (0.5, 0.5, 0.5)
        vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(smooth_normal(nt) if band else facing_normal(nt), vm.inputs[0])
        sh = emission(nt, vm.outputs["Vector"])
    elif kind == "id":
        info = nt.nodes.new("ShaderNodeObjectInfo")
        cam = nt.nodes.new("ShaderNodeCameraData")
        div = nt.nodes.new("ShaderNodeMath")
        div.operation = "DIVIDE"
        div.inputs[1].default_value = 1000.0
        nt.links.new(info.outputs["Object Index"], div.inputs[0])
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(div.outputs[0], comb.inputs["X"])
        nt.links.new(cam.outputs["View Z Depth"], comb.inputs["Y"])
        if FADE:      # B = fade coordinate: dot(world position, fade axis), metres
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            fd = nt.nodes.new("ShaderNodeVectorMath")
            fd.operation = "DOT_PRODUCT"
            nt.links.new(geo.outputs["Position"], fd.inputs[0])
            fd.inputs[1].default_value = tuple(FADE["axis"])
            nt.links.new(fd.outputs["Value"], comb.inputs["Z"])
        else:
            comb.inputs["Z"].default_value = 1.0
        sh = emission(nt, comb.outputs[0])
    elif kind == "flat":  # constant: lit == unlit, so no shadow
        sh = emission(nt, color=(1.0, 1.0, 1.0, 1.0))
    else:  # white diffuse for the shadow passes
        d = nt.nodes.new("ShaderNodeBsdfDiffuse")
        d.inputs["Color"].default_value = (0.8, 0.8, 0.8, 1.0)
        sh = d.outputs[0]
    finish(nt, out, sh, cull)
    MAT_CACHE[key] = m
    return m


def assign(o, mat):
    if len(o.material_slots) == 0:
        o.data.materials.append(mat)
    for slot in o.material_slots:
        slot.material = mat


# ---------------------------------------------------------------- render setup
r = scene.render
r.engine = "CYCLES"
r.resolution_x = Wpx * SS
r.resolution_y = Hpx * SS
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
cyc = scene.cycles
cyc.use_adaptive_sampling = False
cyc.use_denoising = False
cyc.max_bounces = 0
cyc.diffuse_bounces = 0
cyc.glossy_bounces = 0
cyc.transmission_bounces = 0
cyc.transparent_max_bounces = 8
if DEVICE == "CPU":
    cyc.device = "CPU"
else:
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = DEVICE
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == DEVICE
        cyc.device = "GPU"
    except Exception as e:
        print("[desk] GPU setup failed, using CPU:", e)
        cyc.device = "CPU"
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
for n in scene.world.node_tree.nodes:
    if n.type == "BACKGROUND":
        n.inputs["Strength"].default_value = 0.0

TIMES = {}


def render_exr(tag, samples, filter_width, channels=4, dtype=np.float32):
    cyc.samples = samples
    cyc.filter_width = filter_width
    path = os.path.join(OUTDIR, "raw_%s.exr" % tag)
    r.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    TIMES[tag] = round(time.time() - t, 1)
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    # Keep raw EXRs in this round.
    a = a.reshape(h, w, 4)
    if channels == 1:
        a = np.ascontiguousarray(a[..., 0])
    if dtype != np.float32:
        a = a.astype(dtype)
    print("[desk] rendered %s in %.1fs (total %.0fs)" % (tag, TIMES[tag], time.time() - T0))
    return a  # bottom-up rows


def set_visibility(cam_objs, casters=None, no_shadow=(), holdout=()):
    """holdout: objects seen by the camera as holdouts (they cut the layer where they are in front of it)"""
    cam_names = set(o.name for o in cam_objs)
    cast_names = cam_names if casters is None else set(o.name for o in casters)
    hold_names = set(o.name for o in holdout) - cam_names
    for o in meshes:
        on = o.name in cam_names or o.name in cast_names or o.name in hold_names
        o.hide_render = not on
        o.is_holdout = o.name in hold_names
        o.visible_camera = o.name in cam_names or o.name in hold_names
        o.visible_shadow = o.name in cast_names and o.name not in no_shadow
        o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
        o.visible_volume_scatter = False


# ---------------------------------------------------------------- outlines (strip-wise)


def thicken(edge, width):
    o_ = edge.copy()
    for kk in range(1, width):
        sh = (kk + 1) // 2 * (1 if kk % 2 else -1)
        for ax in (0, 1):
            o_ |= np.roll(edge, sh, axis=ax)
    return o_


def outline_mask(nrm_px, id_px):
    """-> (full line mask, inner line mask one sub-pixel thinner, fade coordinate in mm or None)"""
    H, Wd = id_px.shape[:2]
    out = np.zeros((H, Wd), dtype=bool)
    inner = np.zeros((H, Wd), dtype=bool)
    fcoord = np.zeros((H, Wd), dtype=np.float32) if FADE else None
    margin = 8
    width = max(1, int(round(LINE_PX * SS)))
    cos_c = math.cos(math.radians(CREASE_DEG))
    for s0 in range(0, H, STRIP):
        a0, a1 = max(0, s0 - margin), min(H, s0 + STRIP + margin)
        idp = id_px[a0:a1]
        alpha = idp[..., 3] > 0.5
        oid = np.where(alpha, np.rint(idp[..., 0] * 1000.0), 0).astype(np.int32)
        depth = np.where(alpha, idp[..., 1], 1e3).astype(np.float32)
        n = nrm_px[a0:a1, :, :3].astype(np.float32) * 2.0 - 1.0
        n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-6)
        tone = np.where(n[..., 2] > TOP_NZ, 2, np.where(n[..., 0] + n[..., 1] > 0, 1, 0)).astype(np.int8)
        facing = oid < BAND_ID0
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
            diff |= both & sl(facing, 0, -1) & sl(facing, 1, None) & (sl(tone, 0, -1) != sl(tone, 1, None))
            diff |= both & ((sl(n, 0, -1) * sl(n, 1, None)).sum(-1) < cos_c)
            jump = np.abs(d_q - d_p)
            dd = np.abs(np.diff(depth, axis=axis))
            pad_ = np.full_like(sl(dd, 0, 1), 1e9)
            before = np.concatenate([pad_, sl(dd, 0, -1)], axis=axis)
            after = np.concatenate([sl(dd, 1, None), pad_], axis=axis)
            slope = np.minimum(before, after)
            diff |= both & (jump > 2.0 * slope + DEPTH_STEP_M)
            near_p = d_p <= d_q
            idx_p = [slice(None)] * 2
            idx_q = [slice(None)] * 2
            idx_p[axis] = slice(0, -1)
            idx_q[axis] = slice(1, None)
            edge[tuple(idx_p)] |= diff & near_p
            edge[tuple(idx_q)] |= diff & ~near_p
        k = 7
        e = edge.astype(np.int32)
        c = np.pad(e, ((k // 2 + 1, k // 2), (k // 2 + 1, k // 2))).cumsum(0).cumsum(1)
        box = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
        edge &= box >= 6
        r0, r1 = s0 - a0, s0 - a0 + min(STRIP, H - s0)
        out[s0:s0 + r1 - r0] = thicken(edge, width)[r0:r1]
        inner[s0:s0 + r1 - r0] = thicken(edge, max(1, width - 1))[r0:r1]
        if FADE:
            fc = np.where(alpha, idp[..., 2] * 1000.0, -1e9).astype(np.float32)
            fill = fc
            for _ in range(2):          # line pixels just outside an object take its fade coordinate
                g = fill.copy()
                for ax in (0, 1):
                    g = np.maximum(g, np.maximum(np.roll(fill, 1, ax), np.roll(fill, -1, ax)))
                fill = g
            fcoord[s0:s0 + r1 - r0] = np.where(alpha, fc, fill)[r0:r1]
    return out, inner, fcoord


def fade_amount(fc, v):
    """baked aerial perspective: share of the theme background mixed in (0 = none)"""
    p = FADE[v]
    t = np.clip((fc - p["near_mm"]) / (p["far_mm"] - p["near_mm"]), 0.0, 1.0)
    return (p["max"] * t * t * (3 - 2 * t)).astype(np.float32)


def save_rgba(outp, dst):
    oi = bpy.data.images.new("out", outp.shape[1], outp.shape[0], alpha=True, float_buffer=False)
    oi.colorspace_settings.name = "Non-Color"
    oi.alpha_mode = "STRAIGHT"
    oi.pixels.foreach_set(outp.ravel())
    oi.filepath_raw = dst
    oi.file_format = "PNG"
    oi.save()
    bpy.data.images.remove(oi)


def save_mist(id_px, dst):
    """8-bit view depth: 255 * (d - near) / (far - near), alpha-weighted over the sub-pixels."""
    near, far = META["depth"]["near_mm"], META["depth"]["far_mm"]
    H, Wd = id_px.shape[:2]
    f = SS
    out = np.zeros((H // f, Wd // f, 4), dtype=np.float32)
    for s0 in range(0, H, STRIP):
        blk = id_px[s0:s0 + STRIP]
        a = (blk[..., 3] > 0.5).astype(np.float32)
        d = np.clip(((blk[..., 1] + CAM_OFF) * 1000.0 - near) / (far - near), 0, 1) * a
        h, w = a.shape
        A = a[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f).mean(axis=(1, 3))
        D = d[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f).mean(axis=(1, 3))
        g = np.where(A > 1e-6, D / np.maximum(A, 1e-6), 0)
        out[s0 // f: s0 // f + h // f] = np.stack([g, g, g, A], -1)
    save_rgba(out, dst)


# ---------------------------------------------------------------- compositing


def lin_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def compose_and_save(color_px, masks, st, dst, shadow=None, v=None):
    """masks = (full, inner, fade coordinate); shadow = (nopool_px, lit, unlit) at the supersampled size."""
    mask, inner, fcoord = masks
    H, Wd = mask.shape
    f = SS
    out = np.zeros((H // f, Wd // f, 4), dtype=np.float32)
    line = np.array(hex_srgb(st["line"]), dtype=np.float32)
    bg = np.array(hex_srgb(st.get("bg", "#000000")), dtype=np.float32)
    for s0 in range(0, H, STRIP):
        s1 = min(H, s0 + STRIP)
        col = color_px[s0:s1].astype(np.float32)
        if shadow is not None:
            nop, lit, unlit = shadow
            ul = unlit[s0:s1]
            S = np.where(ul > 1e-5, 1.0 - lit[s0:s1] / np.maximum(ul, 1e-5), 0.0)
            S = np.clip((S - 0.3) / 0.4, 0.0, 1.0)
            S = (S * S * (3 - 2 * S))[..., None].astype(np.float32)
            shaded = nop[s0:s1].astype(np.float32) * (1.0 - st["shadow_keep"]) + col * st["shadow_keep"]
            shaded[..., :3] *= st["shadow_mul"]
            col = col * (1.0 - S) + shaded * S
        a = col[..., 3:4]
        straight = np.where(a > 1e-6, col[..., :3] / np.maximum(a, 1e-6), 0.0)
        pm = lin_to_srgb(straight).astype(np.float32) * a
        fd = fade_amount(fcoord[s0:s1], v)[..., None] if fcoord is not None else None
        m_in = inner[s0:s1].astype(np.float32)
        ring = (mask[s0:s1] & ~inner[s0:s1]).astype(np.float32)
        if fd is not None:      # far lines a little thinner: their outer sub-pixel ring fades out
            ring = ring * (1.0 - THIN_FAR * fd[..., 0] / max(FADE[v]["max"], 1e-6))
        c = ((m_in + ring) * np.float32(st["line_alpha"]))[..., None]
        pm = line * c + pm * (1.0 - c)
        al = c + a * (1.0 - c)
        if fd is not None:      # baked aerial perspective toward the theme background, lines included
            pm = pm * (1.0 - fd) + bg * al * fd
        rgba = np.concatenate([pm, al], axis=2)
        h, w = rgba.shape[:2]
        out[s0 // f: s0 // f + h // f] = rgba[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
    al = out[..., 3:4]
    rgb = np.where(al > 1e-6, out[..., :3] / np.maximum(al, 1e-6), 0.0)
    save_rgba(np.concatenate([np.clip(rgb, 0, 1), al], axis=2).astype(np.float32), dst)
    ys, xs = np.nonzero(al[::-1, :, 0] > 0.002)       # top-down bbox
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None
    print("[desk] wrote", dst, "bbox", bbox)
    return bbox


# ---------------------------------------------------------------- lights for the shadow passes


def make_light(v):
    for o in [o for o in scene.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o)
    if v == "paper":
        ld = bpy.data.lights.new("room", "SUN")
        ld.angle = math.radians(4.0)
        ld.energy = 3.0
        lo = bpy.data.objects.new("room", ld)
        d = Vector(VARIANT_STYLE["paper"]["light_dir"]).normalized()
        lo.rotation_mode = "QUATERNION"
        lo.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    else:
        ld = bpy.data.lights.new("bulb", "POINT")
        ld.shadow_soft_size = 0.018
        ld.energy = 200.0
        lo = bpy.data.objects.new("bulb", ld)
        hgt = VARIANT_STYLE["dark"].get("shadow_light_height_mm")
        lo.location = BULB if hgt is None else Vector((BULB.x, BULB.y, META["desk_top"]["height_mm"] / 1000.0
                                                       + hgt / 1000.0))
    scene.collection.objects.link(lo)
    lo.visible_camera = False
    return ld


def set_shadow(ld, on):
    for attr in ("use_shadow",):
        if hasattr(ld, attr):
            setattr(ld, attr, on)
    if hasattr(ld, "cycles") and hasattr(ld.cycles, "cast_shadow"):
        ld.cycles.cast_shadow = on


# ---------------------------------------------------------------- layers
LAYER_NAMES = sorted(set(o["layer"] for o in meshes), key=lambda n: (n != "base", n))
LAYER_SET = {n: [o for o in meshes if o["layer"] == n] for n in LAYER_NAMES}
LAYER_SET["full"] = list(meshes)
if LAYERS == ["all"]:
    LAYERS = LAYER_NAMES
FILE = {n: "desk_%s_%%s.png" % n for n in LAYER_NAMES}
FILE["full"] = "check_full_%s.png"
if MIST:
    os.makedirs(os.path.join(OUTDIR, "mist"), exist_ok=True)

for layer in LAYERS:
    todo = [v for v in VARIANTS if FORCE or not os.path.exists(os.path.join(OUTDIR, FILE[layer] % v))]
    if not todo:
        print("[desk] skip", layer)
        continue
    objs = LAYER_SET[layer]
    TIMES.clear()
    t_layer = time.time()
    # object layers are cut by the backdrop (desk, walls) wherever it is in front of them
    HOLD = LAYER_SET["base"] if (layer not in ("base", "full") and HOLDOUT_BASE) else []
    set_visibility(objs, holdout=HOLD)
    for o in objs:
        assign(o, data_mat("normal", o))
    nrm = render_exr(layer + "_normal", 1, 0.01, dtype=np.float16)
    for o in objs:
        assign(o, data_mat("id", o))
    idp = render_exr(layer + "_id", 1, 0.01)
    t = time.time()
    masks = outline_mask(nrm, idp)
    TIMES["outline_mask"] = round(time.time() - t, 1)
    if MIST and "depth" in META:
        t = time.time()
        save_mist(idp, os.path.join(OUTDIR, "mist", "mist_%s.png" % layer))
        TIMES["mist_png"] = round(time.time() - t, 1)
    del nrm, idp
    info = {"layer": layer, "variants": {}}
    for v in todo:
        st = VARIANT_STYLE[v]
        set_visibility(objs, holdout=HOLD)
        for o in objs:
            assign(o, toon_mat(o, v, True))
        col = render_exr("%s_color_%s" % (layer, v), SAMPLES, 1.5, dtype=np.float16)
        shadow = None
        if layer in ("base", "full"):
            for o in objs:
                assign(o, toon_mat(o, v, False))
            nop = render_exr("%s_nopool_%s" % (layer, v), SAMPLES, 1.5, dtype=np.float16)
            ld = make_light(v)
            no_sh = LIGHT_OBJS if v == "dark" else ()
            set_visibility(objs, casters=meshes, no_shadow=no_sh)
            for o in meshes:   # non-base objects seen by the camera (full check only) get no shadow
                assign(o, data_mat("diffuse" if o["layer"] == "base" or o not in objs else "flat", o))
            set_shadow(ld, True)
            lit = render_exr("%s_lit_%s" % (layer, v), SHADOW_SAMPLES, 1.5, channels=1)
            if layer == 'base':
                set_visibility(objs, casters=[o for o in meshes if o.get('layer')=='fax' or o.name.startswith('rug_')])
                changed_lit = render_exr('%s_changed_casters_%s' % (layer,v), SHADOW_SAMPLES, 1.5, channels=1)
            set_shadow(ld, False)
            unlit = render_exr("%s_unlit_%s" % (layer, v), SHADOW_SAMPLES, 1.5, channels=1)
            for o in [o for o in scene.objects if o.type == "LIGHT"]:
                bpy.data.objects.remove(o)
            if layer == 'base':
                footprint=np.zeros((Hpx,Wpx),dtype=np.float32)
                for row in range(0,Hpx*SS,STRIP):
                    ul=unlit[row:row+STRIP]; ml=changed_lit[row:row+STRIP]
                    strength=np.where(ul>1e-5,1-ml/np.maximum(ul,1e-5),0)
                    strength=np.clip((strength-.3)/.4,0,1)
                    strength=strength*strength*(3-2*strength)
                    hh,ww=strength.shape
                    footprint[row//SS:row//SS+hh//SS]=strength.reshape(hh//SS,SS,ww//SS,SS).mean(axis=(1,3))
                np.save(os.path.join(OUTDIR,'changed_shadow_%s.npy'%v),footprint[::-1])
                del changed_lit,footprint
            shadow = (nop, lit, unlit)
        t = time.time()
        bbox = compose_and_save(col, masks, st, os.path.join(OUTDIR, FILE[layer] % v), shadow, v)
        TIMES["compose_" + v] = round(time.time() - t, 1)
        info["variants"][v] = {"file": FILE[layer] % v, "bbox_px": bbox}
        del col, shadow
    del masks
    info["times_s"] = dict(TIMES)
    info["layer_total_s"] = round(time.time() - t_layer, 1)
    info["ss"], info["samples"] = SS, SAMPLES
    info["night_pool_trial"] = {"amb": 0.64, "gain": NIGHT_GAIN, "add": 0,
                                "sigma_scale_dark": NIGHT_SIGMA_SCALE, "sigma_original": POOL["sigma"],
                                "sigma_dark": POOL["sigma"] * NIGHT_SIGMA_SCALE,
                                "paper_and_lines_unchanged": True, "device": cyc.device}
    with open(os.path.join(OUTDIR, "render_%s.json" % layer), "w") as fh:
        json.dump(info, fh, indent=2)
with open(os.path.join(OUTDIR, "desk_meta.json"), "w", encoding="utf-8") as fh:
    json.dump(META, fh, indent=2, ensure_ascii=False)
print("[desk] done in %.0fs" % (time.time() - T0))
