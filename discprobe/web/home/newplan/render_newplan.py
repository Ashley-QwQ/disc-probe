"""Art for the "new work" page (opened from the lobby's drive): toon fill + image-space lines + baked warm lamp pool,
same look as the lobby (art/desk/render_desk.py) and the burner page (discprobe/web/home/render_burner.py).

Everything is shot straight down with an orthographic camera (looking -Z, screen up = +Y):
  --mode top       the app's burner model (read from a COPY-safe .blend, never saved) with the tray out and a blank
                   disc, on the desk; opaque, 2560 x 1440 -> top_<theme>.png
  --mode paper     a sheet of paper (lying flat) -> paper_<theme>.png + paper_shadow_<theme>.png (1400 x 1700)
  --mode envelope  the string-and-button archive envelope lying on its back, flap open "above" (+Y), as two layers
                   -> envelope_back_<theme>.png, envelope_front_<theme>.png (1600 wide)
  --mode desk      the presets page as one desk scene, a hair off straight down (orthographic, 12 deg from the
                   front): the lobby's letter tray, a lever, the Penrose block, a notebook and the fountain pen, and
                   the two documents that fly in (a sheet for import, a closed archive bag for export); every moving
                   thing on its own layer with its own shadow layer -> desk_<layer>_<theme>.png + desk.json
  --mode tray      the lobby's letter tray (desk-prop-tray/final_bundle/tray.blend, the import/export target) straight down,
                   for the presets sheet -> tray_<theme>.png + tray_shadow_<theme>.png (transparent, own shadow layer)
Each mode writes <mode>.json with placement data (px, origin top-left).

    blender -b [disc_explode_render.blend] --python render_newplan.py -- --mode top --outdir OUT [--ss 2]
        [--variants paper,dark] [--samples 16] [--device OPTIX] [--preview]
"""
import json
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


MODE = arg("--mode", "top")
OUTDIR = os.path.abspath(arg("--outdir", "out"))
VARIANTS = arg("--variants", "paper,dark").split(",")
SAMPLES = int(arg("--samples", "16"))
DEVICE = arg("--device", "OPTIX")
PREVIEW = "--preview" in argv
SS = int(arg("--ss", {"top": "2", "paper": "3", "envelope": "3", "tray": "3", "desk": "2"}[MODE]))
if PREVIEW:
    SS, SAMPLES = 1, 4
os.makedirs(OUTDIR, exist_ok=True)
T0 = time.time()

# ---------------------------------------------------------------- palettes (top tone, side tone) and the pool
# colours from render_burner.py (drive) and render_desk.py (desk, kraft, button, string, sheet, pool gains)
STYLE = {
    "paper": dict(
        body="#f1eee8", body_side="#d0cac0", tray_mul=0.94, cavity="#bfb8ac", led="#b3ab9e",
        desk="#ddd6cb", disc="#f6f4ef", disc_hub="#d4d6d3", disc_rim="#c9cbc8", disc_hole="#9c968c",
        kraft="#d0c0a2", kraft_in="#c3b192", kraft_flap_in="#dbcfb7", kraft_edge="#b3a386",
        button="#f3f0ea", grommet="#aaa59d", string="#efe9de",
        sheet="#f9f8f4", sheet_edge="#dfdbd3", fax="#d9d4ca", fax_edge="#bdb6aa",
        pen="#4a4741", pen_edge="#36342f", metal="#f3f1ec", metal_edge="#d6d1c8",
        penrose_light="#f7f4ee", penrose_mid="#d4cec4", penrose_dark="#a39c91",
        notebook="#5a5650", notebook_edge="#f1ede4", band="#2f2d29", led_off="#a9a296",
        line="#2b2924", line_alpha=1.0,
        amb=(0.975, 0.975, 0.975), gain=(0.075, 0.055, 0.02), add=(0.0, 0.0, 0.0),
        shadow_tint=(0.80, 0.77, 0.72), shadow_rgb="#3a2f22", drop_alpha=0.22, bg="#ebe7e0",
    ),
    "dark": dict(
        body="#222b2a", body_side="#1d2625", tray_mul=0.93, cavity="#111716", led="#d9a75c",
        desk="#1f2726", disc="#4a504e", disc_hub="#353b3a", disc_rim="#3f4543", disc_hole="#101514",
        kraft="#3b352c", kraft_in="#2e2922", kraft_flap_in="#433d33", kraft_edge="#312c25",
        button="#5b625f", grommet="#2f3433", string="#6e736f",
        sheet="#454c4b", sheet_edge="#343a39", fax="#3d4442", fax_edge="#2c3231",
        pen="#1b2221", pen_edge="#141a19", metal="#465150", metal_edge="#323b3a",
        penrose_light="#5c6865", penrose_mid="#3e4947", penrose_dark="#252e2d",
        notebook="#2a3231", notebook_edge="#3e4544", band="#121817", led_off="#141a19",
        line="#d5d9d2", line_alpha=0.55,
        amb=(0.9, 0.9, 0.9), gain=(1.6, 1.4, 1.1), add=(0.035, 0.018, 0.004),
        shadow_tint=(0.62, 0.66, 0.66), shadow_rgb="#050807", drop_alpha=0.40, bg="#161d1c",
    ),
}
LINE_PX = 0.8
CREASE_DEG = 30.0
DEPTH_STEP_M = 0.0004
TOP_NZ = 0.55


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_srgb(h, mul=1.0):
    h = h.lstrip("#")
    return [min(1.0, int(h[i:i + 2], 16) / 255.0 * mul) for i in (0, 2, 4)]


def hex_lin(h, mul=1.0):
    return tuple(srgb_to_linear(c) for c in hex_srgb(h, mul)) + (1.0,)


# ---------------------------------------------------------------- scene per mode
scene = bpy.context.scene
TRAY_OPEN = 0.20                        # m: far enough that the whole disc is out of the bezel
TRAY_OBJECTS = {"KSL210_tray_final-1", "SHELL_tray_door", "SHELL_door_print"}
HIDE_OBJECTS = {"table", "Label_simulated", "SHELL_label_round", "SHELL_sticker_side", "SHELL_sticker_rear",
                "SHELL_door_print", "SHELL_badge", "KSL210_tray-1", "cd-1"}
HIDE_COLLECTIONS = {"Disc", "Overlay", "SW_hidden"}
ROLE = {}                               # object name -> palette key
LAYER = {}                              # object name -> output layer (envelope: back / front)


def mesh_obj(name, bm, role, layer="main"):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    ROLE[name], LAYER[name] = role, layer
    return o


def prism(poly, z0, z1):
    """polygon (x, y) list, CCW, extruded from z0 to z1 (metres)"""
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in poly]
    top = [bm.verts.new((x, y, z1)) for x, y in poly]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bm.normal_update()
    return bm


def ring(r0, r1, z0, z1, cx=0.0, cy=0.0, seg=128):
    """flat annulus (r0 = 0: a disc) as a closed solid"""
    bm = bmesh.new()
    lay = []
    for z in (z0, z1):
        outer = [bm.verts.new((cx + r1 * math.cos(2 * math.pi * k / seg), cy + r1 * math.sin(2 * math.pi * k / seg), z))
                 for k in range(seg)]
        inner = [bm.verts.new((cx + r0 * math.cos(2 * math.pi * k / seg), cy + r0 * math.sin(2 * math.pi * k / seg), z))
                 for k in range(seg)] if r0 > 0 else None
        lay.append((outer, inner))
    (ob, ib), (ot, it) = lay
    for k in range(seg):
        j = (k + 1) % seg
        bm.faces.new((ob[k], ob[j], ot[j], ot[k]))
        if ib:
            bm.faces.new((ib[j], ib[k], it[k], it[j]))
            bm.faces.new((ot[k], ot[j], it[j], it[k]))
            bm.faces.new((ob[j], ob[k], ib[k], ib[j]))
    if not ib:
        bm.faces.new(ot)
        bm.faces.new(ob[::-1])
    bm.normal_update()
    return bm


def tube(points, r, seg=10):
    """round tube along a polyline of (x, y, z)"""
    bm = bmesh.new()
    P = [Vector(p) for p in points]
    rings = []
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        a = t.cross(Vector((0, 0, 1)))
        if a.length < 1e-6:
            a = t.cross(Vector((1, 0, 0)))
        a.normalize()
        b = t.cross(a)
        rings.append([bm.verts.new(p + (a * math.cos(2 * math.pi * k / seg) + b * math.sin(2 * math.pi * k / seg)) * r)
                      for k in range(seg)])
    for i in range(len(rings) - 1):
        for k in range(seg):
            j = (k + 1) % seg
            bm.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bm.normal_update()
    return bm


def rounded_rect(x0, y0, x1, y1, r, n=8, round_top_only=False):
    pts = []
    corners = [((x1 - r, y1 - r), 0), ((x0 + r, y1 - r), 90), ((x0 + r, y0 + r), 180), ((x1 - r, y0 + r), 270)]
    for k, ((cx, cy), a0) in enumerate(corners):
        if round_top_only and k >= 2:
            pts.append((x0, y0) if k == 2 else (x1, y0))
            continue
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


META = {"mode": MODE}

if MODE == "top":
    # ---- the burner model: freeze frame 1, drop animation, hide decals and the original disc, open the tray
    scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    hidden_coll = set()
    for coll in bpy.data.collections:
        if coll.name in HIDE_COLLECTIONS:
            hidden_coll.update(o.name for o in coll.all_objects)
    frozen = {o.name: (o.evaluated_get(deps).matrix_world.copy(), bool(o.hide_render)) for o in scene.objects}
    for o in scene.objects:
        o.animation_data_clear()
        for c in list(o.constraints):
            o.constraints.remove(c)
    for o in scene.objects:
        mw, hide = frozen[o.name]
        o.parent = None
        o.matrix_world = mw
        o.hide_render = hide or o.name in HIDE_OBJECTS or o.name in hidden_coll
        if o.type in ("LIGHT", "FONT", "CAMERA"):
            o.hide_render = True
    if scene.animation_data:
        scene.animation_data_clear()
    for name in TRAY_OBJECTS:
        o = bpy.data.objects.get(name)
        if o:
            o.matrix_world = Matrix.Translation((0.0, -TRAY_OPEN, 0.0)) @ o.matrix_world
    for o in scene.objects:
        if o.type == "MESH" and not o.hide_render:
            ROLE[o.name] = ("led" if o.name == "SHELL_led" else "tray" if o.name in TRAY_OBJECTS else
                            "body" if o.name.startswith("SHELL_") else "cavity")
            LAYER[o.name] = "main"
    # ---- a blank printable disc on the tray (label side up), centre where the model's own disc sits, moved out
    DCX, DCY, DZ0 = 0.0, 0.219 - TRAY_OPEN, 0.0566
    mesh_obj("disc_label", ring(0.0230, 0.0585, DZ0, DZ0 + 0.0012, DCX, DCY), "disc")
    mesh_obj("disc_rim", ring(0.0585, 0.0600, DZ0, DZ0 + 0.0011, DCX, DCY), "disc_rim")
    mesh_obj("disc_hub", ring(0.0075, 0.0230, DZ0, DZ0 + 0.0011, DCX, DCY), "disc_hub")
    mesh_obj("disc_stack", ring(0.0165, 0.0172, DZ0 + 0.0011, DZ0 + 0.0013, DCX, DCY), "disc_rim")
    # ---- the DP mark printed on the label, low-key: the two letters each lie flat (not bent), each turned so its
    # up points away from the disc centre where it sits on the upper half of the label ring; tone near the label
    # (mark_soft_{D,P}_<theme>.png and mark_split.json from make_mark.py); decals with no outlines of their own,
    # under the same pool as the disc
    MARK_R0, MARK_H = 0.038, 0.016                     # baseline radius, letter height (m)
    MARK_TRACK = 1.22                                  # letter spacing along the ring (feet close up on a convex arc)
    R_MID = MARK_R0 + MARK_H / 2
    SPLIT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mark_split.json")))
    zq = DZ0 + 0.0012 + 0.00005
    MARK_LETTERS = {}
    for L_, sp in SPLIT.items():
        w_, s_ = sp["width_h"] * MARK_H, sp["centre_h"] * MARK_H * MARK_TRACK   # width, arc offset of the centre
        th_ = math.pi / 2 - s_ / R_MID                                    # its angle on the ring
        rot_ = th_ - math.pi / 2                                          # up = radial
        cx_, cy_ = DCX + R_MID * math.cos(th_), DCY + R_MID * math.sin(th_)
        ca, sa = math.cos(rot_), math.sin(rot_)
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new()
        vs = [bm.verts.new((cx_ + ca * x - sa * y, cy_ + sa * x + ca * y, zq))
              for x, y in ((-w_ / 2, -MARK_H / 2), (w_ / 2, -MARK_H / 2), (w_ / 2, MARK_H / 2), (-w_ / 2, MARK_H / 2))]
        f = bm.faces.new(vs)
        for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = uv
        bm.normal_update()
        mesh_obj("disc_mark_" + L_, bm, "decal_" + L_)
        MARK_LETTERS[L_] = {"centre": (cx_, cy_), "rot_deg": math.degrees(rot_), "w": w_}
    # ---- desk
    mesh_obj("desk", prism([(-0.6, -0.6), (1.2, -0.6), (1.2, 0.8), (-0.6, 0.8)], -0.02, 0.0), "desk")
    # ---- frame: 2560 x 1440, drive centred at 20 % of the width, tray front at 78 % of the height
    W, H = 2560, 1440
    PPM = 3455.0                          # px per metre: drive (163 mm) ~563 px wide
    tray_front = 0.0805 - TRAY_OPEN - 0.0035
    CX = 0.0 + (W / 2 - 0.20 * W) / PPM
    CY = tray_front + (0.78 * H - H / 2) / PPM
    POOL = dict(center=(CX - 0.02, CY + 0.02), sigma=0.24)
    SHADOW = dict(dx_m=-0.016, dy_m=-0.021, blur_m=0.018)       # lamp up and to the right -> shadow down-left
elif MODE == "paper":
    SW, SH = 0.2600, 0.3209                # sheet in metres (1280 x 1580 px at PPM)
    W, H = 1400, 1700
    PPM = 1280 / SW
    X0, Y0 = 0.338 - SW / 2, -SH / 2       # where the form floats in the top view's world
    mesh_obj("sheet", prism([(X0, Y0), (X0 + SW, Y0), (X0 + SW, Y0 + SH), (X0, Y0 + SH)], 0.0, 0.0003), "sheet")
    CX, CY = X0 + SW / 2, Y0 + SH / 2
    POOL = dict(center=(0.20, 0.02), sigma=0.24)                  # the top view's pool (left of the sheet)
    SHADOW = dict(dx_m=-14 / PPM, dy_m=-22 / PPM, blur_m=26 / PPM)
elif MODE == "envelope":
    # envelope width, height, flap depth (m); lying on its back. Tall (2026-11-11, was 0.240): while the sheet is
    # filed, the bag runs on below the window, its bottom never in sight
    EW, EH, FL = 0.335, float(arg("--env-h", "0.450")), 0.062
    T = 0.0012
    W = 1600
    PPM = (W - 80) / EW
    H = int(round((EH + FL + 0.02) * PPM + 80))
    # back layer: back panel (we see its inside above the pocket), flap opened flat above the top fold
    mesh_obj("env_back", prism([(-EW / 2, 0), (EW / 2, 0), (EW / 2, EH), (-EW / 2, EH)], 0.0, T), "kraft_in", "back")
    fl = rounded_rect(-EW / 2 + 0.004, EH - 0.002, EW / 2 - 0.004, EH + FL, 0.014, round_top_only=True)
    mesh_obj("env_flap", prism(fl, 0.0, T * 0.8), "kraft_flap_in", "back")
    # front layer: pocket with a thumb notch at the top, button with the string wound round it, loose end curling
    PT = EH - 0.012                                    # pocket top edge
    nr = 0.021
    poly = [(-EW / 2, 0), (EW / 2, 0), (EW / 2, PT), (nr, PT)]
    poly += [(nr * math.cos(math.radians(a)), PT - nr * math.sin(math.radians(a))) for a in range(5, 180, 5)]
    poly += [(-nr, PT), (-EW / 2, PT)]
    mesh_obj("env_front", prism(poly, T + 0.0006, 2 * T + 0.0006), "kraft", "front")
    BX, BY, BZ = 0.0, PT - 0.050, 2 * T + 0.0006
    mesh_obj("env_button", ring(0.0, 0.0125, BZ, BZ + 0.0012, BX, BY), "button", "front")
    mesh_obj("env_grommet", ring(0.0018, 0.0042, BZ + 0.0012, BZ + 0.0020, BX, BY), "grommet", "front")
    pts = []
    turns = 2.2
    for i in range(140):                               # wound round the button under its rim, slightly spiralling
        a = 2 * math.pi * turns * i / 139 - math.pi / 2
        rr = 0.0085 + 0.0016 * i / 139
        pts.append((BX + rr * math.cos(a), BY + rr * math.sin(a), BZ + 0.0016 + 0.0004 * math.sin(3 * a)))
    end = Vector(pts[-1])
    ctrl = [end, end + Vector((0.016, 0.006, 0.0004)), Vector((BX + 0.040, BY + 0.020, BZ + 0.0008)),
            Vector((BX + 0.046, BY + 0.040, BZ + 0.0007)), Vector((BX + 0.030, BY + 0.044, BZ + 0.0006)),
            Vector((BX + 0.024, BY + 0.030, BZ + 0.0006))]
    for i in range(len(ctrl) - 1):                     # Catmull-Rom through the loose end
        p0, p1, p2, p3 = ctrl[max(i - 1, 0)], ctrl[i], ctrl[i + 1], ctrl[min(i + 2, len(ctrl) - 1)]
        for k in range(1, 13):
            t = k / 12
            pts.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)))
    mesh_obj("env_string", tube(pts, 0.0011), "string", "front")
    CX, CY = 0.0, (EH + FL) / 2
    POOL = dict(center=(-0.12, EH + 0.05), sigma=0.32)
    SHADOW = None

elif MODE == "tray":
    # the lobby's import/export letter tray (art/desk/skills/desk-prop-tray/final_bundle/tray.blend, objects fax_*:
    # two sheet-metal tiers, sheets on top, a file bag below), real size, shot straight down; open mouth (+X) faces the
    # form on its right
    MATS = {"drive_body": "body", "drive_tray": "tray", "kraft": "kraft", "kraft_flap": "kraft_flap_in",
            "button": "button", "grommet": "grommet", "string": "string", "sheet": "sheet"}
    with bpy.data.libraries.load(os.path.abspath(arg("--blend", "lobby_tray.blend")), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("fax_")]
    parts = []
    for o in dst.objects:
        if o is None or o.type != "MESH":
            continue
        scene.collection.objects.link(o)
        ROLE[o.name], LAYER[o.name] = MATS.get(o.get("mat"), "body"), "main"
        parts.append(o)
    # straight down the top tier hides everything, so the contents are half pulled out of the open mouth (+X),
    # toward the form: the file bag from the lower tier, the top sheets a little askew ("in" and "out")
    pull_in = float(arg("--bag-out", "0.085"))
    for o in parts:
        if o.name.startswith("fax_in_") and o.name != "fax_in_pan":
            o.matrix_world = Matrix.Translation((pull_in, -0.012, 0)) @ o.matrix_world
    for name, dx, dy, deg in (("fax_out_sheet_1", 0.034, 0.0, -2.2), ("fax_out_sheet_2", 0.016, -0.003, 1.4)):
        o = bpy.data.objects.get(name)
        if o is not None:
            c = o.matrix_world @ (sum((v.co for v in o.data.vertices), Vector()) / len(o.data.vertices))
            o.matrix_world = (Matrix.Translation((dx, dy, 0)) @ Matrix.Translation(c) @ Matrix.Rotation(math.radians(deg), 4, "Z")
                              @ Matrix.Translation(-c) @ o.matrix_world)
    # the mouth (where the bag comes out) faces down the picture, toward the person
    rz = Matrix.Rotation(math.radians(float(arg("--tray-rot", "-90"))), 4, "Z")
    for o in parts:
        o.matrix_world = rz @ o.matrix_world
    vs = np.array([tuple(o.matrix_world @ v.co) for o in parts for v in o.data.vertices])
    lo, hi = vs.min(0), vs.max(0)
    sh_ = Matrix.Translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    for o in parts:
        o.matrix_world = sh_ @ o.matrix_world
    lo, hi = lo - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]), hi - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    print("[newplan] tray %.0f x %.0f x %.0f mm, %d parts" % (*((hi - lo) * 1000), len(parts)))
    SHADOW = dict(dx_m=-0.016, dy_m=-0.021, blur_m=0.018)       # same as the burner's: lamp up-right, shadow down-left
    MARGIN = 0.06
    W = int(arg("--width", "1200"))
    PPM = W / (hi[0] - lo[0] + 2 * MARGIN)
    H = int(round((hi[1] - lo[1] + 2 * MARGIN) * PPM))
    CX, CY = 0.0, 0.0
    POOL = dict(center=(hi[0] + 0.14, hi[1] - 0.06), sigma=0.32)  # the pool sits on the form, right of the tray
    TRAY_BOX = (lo, hi)

elif MODE == "desk":
    W, H = 2560, 1440
    PPM = 2900.0                                       # the frame is 0.88 x 0.50 m of desk
    CX, CY = 0.0, 0.0
    TILT = math.radians(float(arg("--tilt", "12")))     # orthographic, seen a little from the front (no perspective)
    mesh_obj("desk", prism([(-0.7, -0.6), (0.7, -0.6), (0.7, 0.6), (-0.7, 0.6)], -0.02, 0.0), "desk", "base")

    def place(objs, dx, dy, deg=0.0, dz=0.0, scale=1.0):
        M = Matrix.Translation((dx, dy, dz)) @ Matrix.Rotation(math.radians(deg), 4, "Z") @ Matrix.Scale(scale, 4)
        for o in objs:
            o.matrix_world = M @ o.matrix_world

    # ---- the letter tray (the lobby's, real size), mouth down toward the person; the bag peeks out of the mouth
    MATS = {"drive_body": "body", "drive_tray": "tray", "kraft": "kraft", "kraft_flap": "kraft_flap_in",
            "button": "button", "grommet": "grommet", "string": "string", "sheet": "sheet"}
    with bpy.data.libraries.load(os.path.abspath(arg("--blend", "lobby_tray.blend")), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("fax_")]
    tray = []
    for o in dst.objects:
        if o is None or o.type != "MESH":
            continue
        scene.collection.objects.link(o)
        n = o.name
        lay = ("bag" if n.startswith("fax_in_") and n != "fax_in_pan" else
               "sheets" if n.startswith("fax_out_sheet") or n == "fax_out_stack" else
               "upper" if n in ("fax_out_pan",) or n.startswith("fax_post") else "base")
        ROLE[n], LAYER[n] = MATS.get(o.get("mat"), "body"), lay
        tray.append(o)
    BAG_OUT = float(arg("--bag-out", "0.040"))
    for o in tray:
        if LAYER[o.name] == "bag":
            o.matrix_world = Matrix.Translation((BAG_OUT, 0, 0)) @ o.matrix_world
    vs = np.array([tuple(o.matrix_world @ v.co) for o in tray if LAYER[o.name] != "bag" for v in o.data.vertices])
    lo, hi = vs.min(0), vs.max(0)
    place(tray, 0, 0, 0, 0)
    for o in tray:                                      # centre the tray body on its origin, base on the desk
        o.matrix_world = Matrix.Translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])) @ o.matrix_world
    TRAY_C = (-0.262, 0.036)
    place(tray, TRAY_C[0], TRAY_C[1], -90.0)            # +X (the mouth) -> -Y (down the picture)

    # ---- the Penrose block (the person's logo, render_caltop_anim.py's shape), a little larger than on the burner page
    with open(os.path.abspath(arg("--penrose", "penrose.json"))) as fh:
        PEN_SHAPE = json.load(fh)
    pz = []
    for piece in PEN_SHAPE["pieces"]:
        pz.append(mesh_obj("penrose_%s" % piece["tone"], prism([(x * 1e-3, y * 1e-3) for x, y in piece["poly"]], 0, 0.006),
                           "penrose_" + piece["tone"], "base"))
    place(pz, 0.040, -0.118, 7.0, 0, 1.75)                # under the document column: fully covered once one lands

    # ---- the lever: a metal plate with a slot, the knob in the middle (moves: its own layer), two LED windows
    LV = (0.272, 0.058)
    PW, PH, PT = 0.058, 0.200, 0.006
    SLX, SLW, SLH = 0.008, 0.010, 0.150                 # slot centre x (from the plate centre), width, length
    plate = rounded_rect(-PW / 2, -PH / 2, PW / 2, PH / 2, 0.010)
    slot = rounded_rect(SLX - SLW / 2, -SLH / 2, SLX + SLW / 2, SLH / 2, SLW / 2 - 1e-4)
    bm = bmesh.new()
    for poly, z0, z1 in ((plate, 0.0, PT),):
        b_ = prism(poly, z0, z1)
        me_ = bpy.data.meshes.new("t"); b_.to_mesh(me_); b_.free(); bm.from_mesh(me_); bpy.data.meshes.remove(me_)
    lever_parts = [mesh_obj("lever_plate", bm, "metal", "base"),
                   mesh_obj("lever_slot", prism(slot, PT, PT + 0.0004), "cavity", "base")]
    LEDS = {"export": (-0.016, 0.068), "import": (-0.016, -0.068)}
    for k, (lx, ly) in LEDS.items():
        lever_parts.append(mesh_obj("led_%s_bezel" % k, ring(0.0034, 0.0052, PT, PT + 0.0012, lx, ly, 48), "metal", "base"))
        lever_parts.append(mesh_obj("led_%s" % k, ring(0.0, 0.0034, PT, PT + 0.0006, lx, ly, 48), "led_off", "base"))
    knob = [mesh_obj("knob_stem", ring(0.0, 0.0035, PT, PT + 0.012, SLX, 0.0, 40), "metal", "knob"),
            mesh_obj("knob_head", ring(0.0, 0.0125, PT + 0.012, PT + 0.020, SLX, 0.0, 64), "pen", "knob"),
            mesh_obj("knob_cap", ring(0.0, 0.0085, PT + 0.020, PT + 0.0208, SLX, 0.0, 64), "metal", "knob")]
    place(lever_parts + knob, LV[0], LV[1], 0)
    KNOB_TRAVEL = SLH / 2 - SLW / 2 - 0.004

    # ---- the notebook (hard cover, an elastic band) and the fountain pen lying on it
    NB = (0.300, -0.138, -12.0)
    nb = [mesh_obj("nb_pages", prism(rounded_rect(-0.050, -0.074, 0.048, 0.074, 0.004), 0.0012, 0.0098), "notebook_edge", "base"),
          mesh_obj("nb_cover_b", prism(rounded_rect(-0.051, -0.075, 0.051, 0.075, 0.005), 0.0, 0.0012), "notebook", "base"),
          mesh_obj("nb_cover_t", prism(rounded_rect(-0.051, -0.075, 0.051, 0.075, 0.005), 0.0098, 0.0110), "notebook", "base"),
          mesh_obj("nb_band", prism([(0.036, -0.0752), (0.042, -0.0752), (0.042, 0.0752), (0.036, 0.0752)], 0.0110, 0.0116), "band", "base")]
    place(nb, NB[0], NB[1], NB[2])

    def rod(x0, x1, r0, r1, seg=40):
        bm = bmesh.new()
        rings = [[bm.verts.new((x, rr * math.cos(2 * math.pi * k / seg), rr * math.sin(2 * math.pi * k / seg))) for k in range(seg)]
                 for x, rr in ((x0, r0), (x1, r1))]
        for k in range(seg):
            bm.faces.new((rings[0][k], rings[0][(k + 1) % seg], rings[1][(k + 1) % seg], rings[1][k]))
        bm.faces.new(rings[0][::-1]); bm.faces.new(rings[1])
        bm.normal_update()
        return bm
    mm = 1e-3
    R_CAP, R_BAR = 6.5 * mm, 6.0 * mm
    pen = [mesh_obj("pen_cap", rod(-71 * mm, -10 * mm, R_CAP - 1.2 * mm, R_CAP), "pen", "base"),
           mesh_obj("pen_band", rod(-12 * mm, -7 * mm, R_CAP + 0.25 * mm, R_CAP + 0.25 * mm), "metal", "base"),
           mesh_obj("pen_barrel", rod(-7 * mm, 44 * mm, R_BAR, R_BAR - 0.6 * mm), "pen", "base"),
           mesh_obj("pen_grip", rod(44 * mm, 56 * mm, 4.7 * mm, 4.0 * mm), "pen", "base"),
           mesh_obj("pen_nib", prism([(55 * mm, -3.2 * mm), (71 * mm, -0.6 * mm), (71.5 * mm, 0), (71 * mm, 0.6 * mm), (55 * mm, 3.2 * mm)], 0, 0.8 * mm), "metal", "base"),
           mesh_obj("pen_clip", prism([(-66 * mm, -1.3 * mm), (-22 * mm, -1.3 * mm), (-20 * mm, 0), (-22 * mm, 1.3 * mm), (-66 * mm, 1.3 * mm)], 0, 1.4 * mm), "metal", "base")]
    for o in pen:
        lift = R_CAP - 1.1 * mm if o.name == "pen_nib" else 2 * R_CAP - 0.3 * mm if o.name == "pen_clip" else R_CAP
        o.matrix_world = Matrix.Translation((0, 0, lift)) @ o.matrix_world
    place(pen, NB[0] + 0.004, NB[1] + 0.006, 62.0, 0.0116)

    # ---- the documents that fly in (centre column): a sheet (import) and the closed archive bag (export)
    # centred between the tray's right edge and the lever plate's left edge
    DOC_X = 0.5 * ((TRAY_C[0] + 0.130) + (LV[0] - PW / 2))
    SH_W, SH_H = 0.290, 0.400
    mesh_obj("doc_sheet", prism(rounded_rect(DOC_X - SH_W / 2, -SH_H / 2, DOC_X + SH_W / 2, SH_H / 2, 0.0015), 0.0, 0.0003), "sheet", "doc_paper")
    EV_W, EV_TOP, EV_H, EV_FL = 0.296, 0.215, 0.600, 0.105
    T_ = 0.0012
    mesh_obj("env_body", prism(rounded_rect(DOC_X - EV_W / 2, EV_TOP - EV_H, DOC_X + EV_W / 2, EV_TOP, 0.003), 0.0, T_), "kraft", "doc_envelope")
    flap = [(DOC_X - EV_W / 2, EV_TOP), (DOC_X + EV_W / 2, EV_TOP), (DOC_X + EV_W / 2 - 0.004, EV_TOP - 0.020),
            (DOC_X + 0.050, EV_TOP - EV_FL), (DOC_X - 0.050, EV_TOP - EV_FL), (DOC_X - EV_W / 2 + 0.004, EV_TOP - 0.020)]
    mesh_obj("env_flap", prism(flap, T_, 2 * T_), "kraft_flap_in", "doc_envelope")
    B1 = (DOC_X, EV_TOP - EV_FL + 0.022)                 # on the flap's tip
    B2 = (DOC_X, EV_TOP - EV_FL - 0.040)                 # on the body below it
    for i, (bx, by) in enumerate((B1, B2)):
        bz = 2 * T_ if i == 0 else T_
        mesh_obj("env_button_%d" % i, ring(0.0, 0.0115, bz, bz + 0.0012, bx, by), "button", "doc_envelope")
        mesh_obj("env_grommet_%d" % i, ring(0.0017, 0.0040, bz + 0.0012, bz + 0.0020, bx, by), "grommet", "doc_envelope")
    pts = []
    for i in range(120):                                 # wound round the lower button, then up round the upper one
        a = 2 * math.pi * 1.6 * i / 119 - math.pi / 2
        pts.append((B2[0] + 0.0082 * math.cos(a), B2[1] + 0.0082 * math.sin(a), T_ + 0.0026))
    for i in range(1, 25):
        t = i / 24
        pts.append((B2[0] + (B1[0] - 0.008 - B2[0]) * t, B2[1] + 0.008 + (B1[1] - B2[1] - 0.008) * t, T_ + 0.0026 + T_ * t))
    for i in range(90):
        a = math.pi + 2 * math.pi * 1.2 * i / 89
        pts.append((B1[0] + 0.0082 * math.cos(a), B1[1] + 0.0082 * math.sin(a), 2 * T_ + 0.0026))
    mesh_obj("env_string", tube(pts, 0.0010), "string", "doc_envelope")
    DOC_TEXT_SHEET = (DOC_X - SH_W / 2 + 0.024, SH_H / 2 - 0.024, DOC_X + SH_W / 2 - 0.024, -SH_H / 2 + 0.024)
    DOC_TEXT_ENV = (DOC_X - EV_W / 2 + 0.026, B2[1] - 0.026, DOC_X + EV_W / 2 - 0.026, -0.248 + 0.020)
    POOL = dict(center=(0.07, 0.08), sigma=0.36)          # the lamp up right shines on the middle of the desk
    SHADOW = dict(dx_m=-0.016, dy_m=-0.021, blur_m=0.018)

# --tumble rx,ry,rz (degrees, envelope mode): the bag turned in 3D, for the past-works page's falling background; one
# layer, a square canvas round the bag's bounding sphere, no shadow (it floats)
TUMBLE = arg("--tumble", "")
if MODE == "envelope" and TUMBLE:
    rx, ry, rz = (math.radians(float(v)) for v in TUMBLE.split(","))
    piv = Matrix.Translation((0.0, (EH + FL) / 2, 0.0))
    rot = piv @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X") @ piv.inverted()
    for o in scene.objects:
        if o.type == "MESH" and o.name in ROLE:
            o.matrix_world = rot @ o.matrix_world
    RAD = 0.5 * math.hypot(EW, EH + FL) + 0.01
    W = H = int(arg("--size", "640"))
    PPM = W / (2 * RAD)
    CX, CY = 0.0, (EH + FL) / 2
    SHADOW = None
render_meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render and o.name in ROLE]
for i, o in enumerate(render_meshes):
    o.pass_index = i + 1
for o in scene.objects:
    if o.type == "MESH" and o.name not in ROLE:
        o.hide_render = True
print("[newplan] %s: %d meshes, canvas %d x %d, %.0f px/m" % (MODE, len(render_meshes), W, H, PPM))

# ---------------------------------------------------------------- camera (straight down)
cam_data = bpy.data.cameras.new("TopCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(W, H) / PPM
cam_data.clip_start = 0.01
cam_data.clip_end = 20.0
cam = bpy.data.objects.new("TopCam", cam_data)
scene.collection.objects.link(cam)
cam.location = (CX, CY, 5.0)
cam.rotation_euler = (0, 0, 0)
scene.camera = cam
if MODE == "desk":
    cam.location = (CX, CY - 5.0 * math.sin(TILT), 5.0 * math.cos(TILT))
    cam.rotation_euler = (TILT, 0.0, 0.0)
if MODE == "tray":
    # not quite straight down: a little height, seen from the upper right looking down-left, a gentle perspective,
    # so that next to the (flat) form it reads as two things lying on the desk
    TILT, AZ, DIST = (math.radians(float(arg("--tilt", "16"))), math.radians(float(arg("--azimuth", "45"))),
                      float(arg("--dist", "1.4")))
    cam_data.type = "PERSP"
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = 36.0
    cam_data.lens = 36.0 * DIST / (W / PPM)            # the desk plane through the tray keeps about the same px/m
    tgt = Vector((CX, CY, 0.02))
    off = Vector((math.sin(TILT) * math.cos(AZ), math.sin(TILT) * math.sin(AZ), math.cos(TILT))) * DIST
    cam.location = tgt + off
    zc = off.normalized()                              # camera back axis; keep world +Y as the picture's up
    xc = Vector((0.0, 1.0, 0.0)).cross(zc).normalized()
    yc = zc.cross(xc)
    cam.rotation_euler = Matrix((xc, yc, zc)).transposed().to_euler()


def to_px(x, y, z=0.0):
    if MODE == "desk":                                   # the tilted orthographic camera: up = (0, cos t, sin t)
        yy = (y - CY) * math.cos(TILT) + z * math.sin(TILT)
        return [round(float(W / 2 + (x - CX) * PPM), 2), round(float(H / 2 - yy * PPM), 2)]
    return [round(float(W / 2 + (x - CX) * PPM), 2), round(float(H / 2 - (y - CY) * PPM), 2)]


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


def toon_pooled(name, top, side, st, grain=0.0, tex_path=None):
    """top tone on up-facing surfaces, side tone elsewhere; times (amb + gain * pool) + add * pool;
    grain > 0: paper fibre noise of that relative amplitude"""
    m, nt, emi = new_mat(name)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(facing_normal(nt), sep.inputs[0])
    is_top = nt.nodes.new("ShaderNodeMath")
    is_top.operation = "GREATER_THAN"
    is_top.inputs[1].default_value = TOP_NZ
    nt.links.new(sep.outputs["Z"], is_top.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(is_top.outputs[0], mix.inputs["Factor"])
    mix.inputs["A"].default_value = side
    mix.inputs["B"].default_value = top
    col = mix.outputs["Result"]
    if tex_path:                                   # colour from an image (a printed decal) instead of the tones
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.name = "decal_tex"
        tex.image = bpy.data.images.load(tex_path, check_existing=True)
        tex.image.alpha_mode = "STRAIGHT"
        tex.interpolation = "Cubic"
        tex.extension = "CLIP"                     # no wrap-around at the decal's edges
        col = tex.outputs["Color"]
    if grain > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 900.0
        tex.inputs["Detail"].default_value = 6.0
        tco = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(tco.outputs["Object"], tex.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = 1.0 - grain
        mr.inputs["To Max"].default_value = 1.0 + grain
        nt.links.new(tex.outputs["Fac"], mr.inputs["Value"])
        gm = nt.nodes.new("ShaderNodeVectorMath")
        gm.operation = "SCALE"
        nt.links.new(col, gm.inputs[0])
        nt.links.new(mr.outputs["Result"], gm.inputs["Scale"])
        col = gm.outputs["Vector"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sp.inputs[0])
    dx = nt.nodes.new("ShaderNodeMath")
    dx.operation = "SUBTRACT"
    nt.links.new(sp.outputs["X"], dx.inputs[0])
    dx.inputs[1].default_value = POOL["center"][0]
    dy = nt.nodes.new("ShaderNodeMath")
    dy.operation = "SUBTRACT"
    nt.links.new(sp.outputs["Y"], dy.inputs[0])
    dy.inputs[1].default_value = POOL["center"][1]
    c2 = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dx.outputs[0], c2.inputs["X"])
    nt.links.new(dy.outputs[0], c2.inputs["Y"])
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(c2.outputs[0], dot.inputs[0])
    nt.links.new(c2.outputs[0], dot.inputs[1])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = -1.0 / (2.0 * POOL["sigma"] ** 2)
    nt.links.new(dot.outputs["Value"], k.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(k.outputs[0], ex.inputs[0])
    cf = nt.nodes.new("ShaderNodeCombineXYZ")
    for ch in "XYZ":
        nt.links.new(ex.outputs[0], cf.inputs[ch])
    g = nt.nodes.new("ShaderNodeVectorMath")
    g.operation = "MULTIPLY_ADD"
    g.inputs[1].default_value = st["gain"]
    g.inputs[2].default_value = st["amb"]
    nt.links.new(cf.outputs[0], g.inputs[0])
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY"
    nt.links.new(col, mul.inputs[0])
    nt.links.new(g.outputs[0], mul.inputs[1])
    ad = nt.nodes.new("ShaderNodeVectorMath")
    ad.operation = "MULTIPLY_ADD"
    nt.links.new(cf.outputs[0], ad.inputs[0])
    ad.inputs[1].default_value = st["add"]
    nt.links.new(mul.outputs[0], ad.inputs[2])
    nt.links.new(ad.outputs[0], emi.inputs["Color"])
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


def palette(role, st):
    if role == "body":
        return hex_lin(st["body"]), hex_lin(st["body_side"])
    if role == "tray":
        return hex_lin(st["body"], st["tray_mul"]), hex_lin(st["body_side"], st["tray_mul"])
    if role in ("cavity", "led"):
        return hex_lin(st[role]), hex_lin(st[role])
    if role.startswith("penrose_"):
        return hex_lin(st[role]), hex_lin(st[role], 0.86)
    side = {"sheet": "sheet_edge", "fax": "fax_edge", "pen": "pen_edge", "metal": "metal_edge", "notebook": "notebook_edge", "kraft": "kraft_edge", "kraft_in": "kraft_edge", "kraft_flap_in": "kraft_edge"}
    return hex_lin(st[role]), hex_lin(st[side.get(role, role)], 0.9 if role not in side else 1.0)


def decal_mat(v, st, letter):
    """the mark image under the same pool as the disc, alpha-blended over it (emission mixed with transparent)"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mark_soft_%s_%s.png" % (letter, v))
    m = toon_pooled("decal_%s_%s" % (letter, v), (1, 1, 1, 1), (1, 1, 1, 1), st, tex_path=path)
    nt = m.node_tree
    emi = [n for n in nt.nodes if n.type == "EMISSION"][0]
    out = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
    tex = nt.nodes["decal_tex"]
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(emi.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def apply_variant(v):
    st = STYLE[v]
    cache = {}
    for o in render_meshes:
        r_ = ROLE[o.name]
        if r_.startswith("decal_"):
            assign(o, decal_mat(v, st, r_[6:]))
            continue
        if r_ not in cache:
            top, side = palette(r_, st)
            cache[r_] = toon_pooled("toon_%s_%s" % (r_, v), top, side, st, grain=0.035 if r_ == "sheet" else
                                    0.02 if r_.startswith("kraft") else 0.0)
        assign(o, cache[r_])


# ---------------------------------------------------------------- render setup
r = scene.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y, r.resolution_percentage = W * SS, H * SS, 100
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
for vl in scene.view_layers[1:]:
    vl.use = False
cyc = scene.cycles
cyc.use_adaptive_sampling = False
cyc.use_denoising = False
cyc.max_bounces = cyc.diffuse_bounces = cyc.glossy_bounces = cyc.transmission_bounces = 0
cyc.transparent_max_bounces = 4
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = DEVICE
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == DEVICE
    cyc.device = "GPU"
except Exception as e:  # noqa: BLE001
    print("[newplan] GPU setup failed, CPU:", e)
    cyc.device = "CPU"
if scene.world is None:
    scene.world = bpy.data.worlds.new("w")
scene.world.use_nodes = True
for n in scene.world.node_tree.nodes:
    if n.type == "BACKGROUND":
        n.inputs["Strength"].default_value = 0.0


def render_exr(tag, samples, filter_width):
    cyc.samples = samples
    cyc.filter_width = filter_width
    path = os.path.join(OUTDIR, "raw_%s_%s.exr" % (MODE, tag))
    r.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    os.remove(path)
    print("[newplan] rendered %s in %.1fs" % (tag, time.time() - t))
    return a.reshape(h, w, 4)[::-1]           # top-down rows


def outline_mask(nrm_px, id_px):
    """as render_burner.py: a line where coverage, object, crease or a depth step changes"""
    alpha = id_px[..., 3] > 0.5
    oid = np.where(alpha, np.rint(id_px[..., 0] * 1000.0), 0).astype(np.int32)
    depth = np.where(alpha, id_px[..., 1], 1e3).astype(np.float64)
    n = nrm_px[..., :3] * 2.0 - 1.0
    n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-6)
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
        diff |= both & ((sl(n, 0, -1) * sl(n, 1, None)).sum(-1) < cos_c)
        jump = np.abs(d_q - d_p)
        dd = np.abs(np.diff(depth, axis=axis))
        pad = np.full_like(sl(dd, 0, 1), 1e9)
        before = np.concatenate([pad, sl(dd, 0, -1)], axis=axis)
        after = np.concatenate([sl(dd, 1, None), pad], axis=axis)
        diff |= both & (jump > 2.0 * np.minimum(before, after) + DEPTH_STEP_M)
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
    edge &= (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) >= 6
    width = max(1, int(round(LINE_PX * SS)))
    out = edge.copy()
    for k in range(1, width):
        sh = (k + 1) // 2 * (1 if k % 2 else -1)
        for axis in (0, 1):
            out |= np.roll(edge, sh, axis=axis)
    return out, oid


def lin_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def box_blur(a, rad):
    """separable box blur, 3 passes ~ Gaussian; a 2-D float array"""
    rad = max(1, int(rad))
    for _ in range(3):
        for axis in (0, 1):
            c = np.cumsum(np.pad(a, [(rad + 1, rad) if i == axis else (0, 0) for i in range(2)], mode="edge"), axis=axis)
            hi = [slice(None)] * 2
            lo = [slice(None)] * 2
            hi[axis] = slice(2 * rad + 1, None)
            lo[axis] = slice(0, -2 * rad - 1)
            a = (c[tuple(hi)] - c[tuple(lo)]) / (2 * rad + 1)
    return a


def shift(a, dx, dy):
    out = np.zeros_like(a)
    h, w = a.shape
    xs, ys = int(round(dx)), int(round(dy))
    out[max(0, ys):h + min(0, ys), max(0, xs):w + min(0, xs)] = a[max(0, -ys):h - max(0, ys), max(0, -xs):w - max(0, xs)]
    return out


def save_png(rgba_ss, dst):
    """premultiplied sRGB at SS -> box-filtered straight-alpha PNG"""
    h, w = rgba_ss.shape[:2]
    f = SS
    rgba = rgba_ss[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
    al = rgba[..., 3:4]
    rgb = np.where(al > 1e-6, rgba[..., :3] / np.maximum(al, 1e-6), 0.0)
    outp = np.concatenate([np.clip(rgb, 0, 1), np.clip(al, 0, 1)], axis=2).astype(np.float32)[::-1]
    oi = bpy.data.images.new("out", outp.shape[1], outp.shape[0], alpha=True, float_buffer=False)
    oi.colorspace_settings.name = "Non-Color"
    oi.alpha_mode = "STRAIGHT"
    oi.pixels.foreach_set(outp.ravel())
    oi.filepath_raw = dst
    oi.file_format = "PNG"
    oi.save()
    bpy.data.images.remove(oi)
    print("[newplan] wrote", dst)


def compose(col, mask, st, shadow=None, opaque=False):
    a = col[..., 3:4]
    straight = np.where(a > 1e-6, col[..., :3] / np.maximum(a, 1e-6), 0.0)
    pm = lin_to_srgb(straight) * a
    if shadow is not None:                      # darken (multiply toward the shadow colour) under the shadow mask
        s = shadow[..., None]
        tint = np.array(st["shadow_tint"], dtype=np.float32)
        pm = pm * (1.0 - s * (1.0 - tint))
    line = np.array(hex_srgb(st["line"]), dtype=np.float32)
    c = (mask.astype(np.float32) * np.float32(st["line_alpha"]))[..., None]
    pm = line * c + pm * (1.0 - c)
    al = c + a * (1.0 - c)
    if opaque:
        bg = np.array(hex_srgb(st["bg"]), dtype=np.float32)
        pm = pm + bg * (1 - al)
        al = np.ones_like(al)
    return np.concatenate([pm, al], axis=2)


def render_layer(names, tag_suffix=""):
    """data passes with only these objects visible -> (mask, oid); returns also the visibility to restore"""
    for o in render_meshes:
        o.hide_render = o.name not in names or ROLE[o.name].startswith("decal")     # printed ink: no outlines
    for o in render_meshes:
        assign(o, NRM)
    nrm = render_exr("normal" + tag_suffix, 1, 0.01)
    for o in render_meshes:
        assign(o, IDM)
    idp = render_exr("id" + tag_suffix, 1, 0.01)
    m_, oid = outline_mask(nrm, idp)
    alpha = idp[..., 3] > 0.5
    return m_, oid, alpha


NRM, IDM = make_normal_mat(), make_id_mat()


def shadow_of(mask, k=1.0):
    return box_blur(shift(mask.astype(np.float32), k * SHADOW["dx_m"] * PPM * SS, -k * SHADOW["dy_m"] * PPM * SS),
                    max(1.0, (0.35 + 0.65 * k) * SHADOW["blur_m"] * PPM * SS / 2))


def drop_shadow(alpha, name, k=1.0):
    s_al = shadow_of(alpha, k)
    for v in VARIANTS:
        st = STYLE[v]
        sc = np.array(hex_srgb(st["shadow_rgb"]), dtype=np.float32)
        al = (s_al * st["drop_alpha"])[..., None]
        save_png(np.concatenate([sc * al, al], axis=2), os.path.join(OUTDIR, "%s_shadow_%s.png" % (name, v)))


if MODE == "desk":
    by = {}
    for o in render_meshes:
        by.setdefault(LAYER[o.name], set()).add(o.name)
    # the base's shadow: only what never moves (the tray, props, lever plate). The bag, the sheets and the knob carry
    # their own shadow layers, or a shadow would stay behind on the desk when they leave
    rest = by["base"] | by["upper"]
    _, oid_all, al_all = render_layer(rest, "_rest")
    desk_id = [o.pass_index for o in render_meshes if o.name == "desk"][0]
    tray_ids = {o.pass_index for o in render_meshes if o.name.startswith("fax_")}
    occ = al_all & (oid_all != desk_id)
    is_tray = np.isin(oid_all, list(tray_ids))
    base_shadow = np.maximum(shadow_of(occ & is_tray, 1.0), shadow_of(occ & ~is_tray, 0.42)) * (oid_all == desk_id)
    del oid_all, al_all, occ, is_tray
    for lname in ("base", "bag", "upper", "sheets", "knob", "doc_paper", "doc_envelope"):
        names = by[lname]
        mask, oid, alpha = render_layer(names, "_" + lname)
        if lname in ("bag", "sheets", "knob", "doc_paper", "doc_envelope"):
            drop_shadow(alpha, "desk_" + lname, {"bag": 0.5, "sheets": 0.5, "knob": 0.45}.get(lname, 0.22))
        for v in VARIANTS:
            apply_variant(v)
            for o in render_meshes:
                o.hide_render = o.name not in names
            col = render_exr("color_%s_%s" % (lname, v), SAMPLES, 1.5)
            out = compose(col, mask, STYLE[v], shadow=base_shadow if lname == "base" else None, opaque=(lname == "base"))
            save_png(out, os.path.join(OUTDIR, "desk_%s_%s.png" % (lname, v)))
            del col, out
        del mask, oid, alpha
    layers = {}
elif MODE == "envelope" and TUMBLE:
    layers = {"tumble": {o.name for o in render_meshes}}
elif MODE == "envelope":
    layers = {"back": {o.name for o in render_meshes if LAYER[o.name] == "back"},
              "front": {o.name for o in render_meshes if LAYER[o.name] == "front"}}
else:
    layers = {"main": {o.name for o in render_meshes}}

for lname, names in layers.items():
    mask, oid, alpha = render_layer(names, "_" + lname)
    shadow = None
    if MODE == "top":                           # drive + disc shadow on the desk only
        desk_id = [o.pass_index for o in render_meshes if o.name == "desk"][0]
        occ = (alpha & (oid != desk_id)).astype(np.float32)
        sh_ = box_blur(shift(occ, SHADOW["dx_m"] * PPM * SS, -SHADOW["dy_m"] * PPM * SS), SHADOW["blur_m"] * PPM * SS / 2)
        shadow = sh_ * (oid == desk_id)
    if MODE in ("paper", "tray"):               # its own layer: a soft drop shadow
        s_al = box_blur(shift(alpha.astype(np.float32), SHADOW["dx_m"] * PPM * SS, -SHADOW["dy_m"] * PPM * SS),
                        SHADOW["blur_m"] * PPM * SS / 2)
        for v in VARIANTS:
            st = STYLE[v]
            sc = np.array(hex_srgb(st["shadow_rgb"]), dtype=np.float32)
            al = (s_al * st["drop_alpha"])[..., None]
            save_png(np.concatenate([sc * al, al], axis=2), os.path.join(OUTDIR, "%s_shadow_%s.png" % (MODE, v)))
    for v in VARIANTS:
        apply_variant(v)
        for o in render_meshes:
            o.hide_render = o.name not in names
        col = render_exr("color_%s_%s" % (lname, v), SAMPLES, 1.5)
        out = compose(col, mask, STYLE[v], shadow=shadow, opaque=(MODE == "top"))
        dst = ("tumble_%s_%%s.png" % arg("--tag", "0") if lname == "tumble" else
               {"top": "top_%s.png", "paper": "paper_%s.png", "tray": "tray_%s.png"}.get(MODE, "envelope_%s_%%s.png" % lname)) % v
        save_png(out, os.path.join(OUTDIR, dst))
        del col, out
    del mask, oid, alpha

# ---------------------------------------------------------------- placement json
META.update({"image_size": [W, H], "px_per_mm": round(PPM / 1000.0, 4), "pixel_origin": "top-left, y down"})
if MODE == "top":
    META["disc"] = {"centre_px": to_px(DCX, DCY), "radius_px": round(0.060 * PPM, 2),
                    "label_radius_px": round(0.0585 * PPM, 2), "label_inner_radius_px": round(0.023 * PPM, 2),
                    "hole_radius_px": round(0.0075 * PPM, 2),
                    "note": "printable disc, label side up; a low-key DP mark is printed along the upper half of "
                            "the label ring (mark_letters, mark_rect_px)"}
    _mv = np.array([o.matrix_world @ v.co for o in render_meshes if o.name.startswith("disc_mark_") for v in o.data.vertices])
    META["mark_rect_px"] = to_px(_mv[:, 0].min(), _mv[:, 1].max()) + to_px(_mv[:, 0].max(), _mv[:, 1].min())
    META["mark_letters"] = {L_: {"centre_px": to_px(*d_["centre"]), "rotation_deg_clockwise": round(-d_["rot_deg"], 1),
                                 "width_px": round(d_["w"] * PPM, 1), "height_px": round(MARK_H * PPM, 1)}
                            for L_, d_ in MARK_LETTERS.items()}
    META["mark_note"] = ("low-key DP mark on the upper half of the label ring: each letter flat, turned so its top "
                         "faces away from the disc centre")
    sh = [o for o in render_meshes if ROLE[o.name] == "body"]
    tr = [o for o in render_meshes if o.name in TRAY_OBJECTS]

    def bbox(objs):
        P = []
        for o in objs:
            P += [o.matrix_world @ v.co for v in o.data.vertices]
        P = np.array(P)
        return to_px(P[:, 0].min(), P[:, 1].max()) + to_px(P[:, 0].max(), P[:, 1].min())
    META["drive_body_rect_px"] = bbox(sh)
    META["tray_rect_px"] = bbox(tr)
    META["rect_note"] = "[left, top, right, bottom] in px"
    META["pool_centre_px"] = to_px(*POOL["center"])
    META["pool_sigma_px"] = round(POOL["sigma"] * PPM, 1)
    META["free_area_note"] = "right of x = %.0f px is plain lit desk (the form floats there)" % (META["drive_body_rect_px"][2] + 40)
elif MODE == "paper":
    l_, t_ = to_px(X0, Y0 + SH)
    r_, b_ = to_px(X0 + SW, Y0)
    META["sheet_rect_px"] = [l_, t_, r_, b_]
    mx, my = round(0.08 * (r_ - l_)), round(0.065 * (b_ - t_))
    META["content_rect_px"] = [l_ + mx, t_ + my, r_ - mx, b_ - my]
    META["inner_margins_px"] = {"left": mx, "right": mx, "top": my, "bottom": my}
    META["shadow_note"] = "paper_shadow_<theme>.png has the same canvas; lift the sheet by moving it up-right of " \
                          "the shadow (light from the upper right)"
elif MODE == "desk":
    def rect_of(names):
        P = np.array([tuple(o.matrix_world @ v.co) for o in render_meshes if o.name in names for v in o.data.vertices])
        pts = [to_px(*p) for p in P]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return [min(xs), min(ys), max(xs), max(ys)]
    names_of = lambda lay: {o.name for o in render_meshes if LAYER[o.name] == lay}
    META["layers"] = ["base", "bag", "upper", "sheets", "knob", "doc_paper", "doc_envelope"]
    META["draw_order"] = ("base (opaque) -> bag_shadow, bag -> upper -> sheets_shadow, sheets -> knob_shadow, knob -> "
                          "doc_*_shadow, doc_*; each moving layer moves together with its shadow")
    META["tray_rect_px"] = rect_of(names_of("upper"))
    META["bag_rect_px"] = rect_of(names_of("bag"))
    META["sheets_rect_px"] = rect_of(names_of("sheets"))
    kx, ky = LV[0] + SLX, LV[1]
    META["knob"] = {"centre_px": to_px(kx, ky, PT + 0.020), "radius_px": round(0.0125 * PPM, 1),
                    "travel_px": round(KNOB_TRAVEL * PPM * math.cos(TILT), 1),
                    "note": "up = export, down = import; the knob layer is drawn at the middle"}
    META["slot_px"] = [to_px(kx, ky + SLH / 2, PT), to_px(kx, ky - SLH / 2, PT)]
    META["leds"] = {k: {"centre_px": to_px(LV[0] + lx, LV[1] + ly, PT), "radius_px": round(0.0034 * PPM, 1)}
                    for k, (lx, ly) in LEDS.items()}
    META["lever_plate_rect_px"] = rect_of({"lever_plate"})
    META["doc_paper_rect_px"] = rect_of(names_of("doc_paper"))
    META["doc_envelope_rect_px"] = rect_of(names_of("doc_envelope"))
    META["doc_paper_text_rect_px"] = to_px(DOC_TEXT_SHEET[0], DOC_TEXT_SHEET[1]) + to_px(DOC_TEXT_SHEET[2], DOC_TEXT_SHEET[3])
    META["doc_envelope_text_rect_px"] = to_px(DOC_TEXT_ENV[0], DOC_TEXT_ENV[1]) + to_px(DOC_TEXT_ENV[2], DOC_TEXT_ENV[3])
    META["camera"] = "orthographic, %g deg from straight down toward the front; up the picture = away from the person" % math.degrees(TILT)
    META["rect_note"] = "[left, top, right, bottom] in px"
elif MODE == "tray":
    lo, hi = TRAY_BOX
    META["tray_rect_px"] = to_px(lo[0], hi[1]) + to_px(hi[0], lo[1])
    META["tray_height_mm"] = round(float(hi[2] - lo[2]) * 1000, 1)
    META["rect_note"] = "[left, top, right, bottom] in px; tray_shadow_<theme>.png has the same canvas"
elif MODE == "envelope":
    META["pocket_top_y_px"] = to_px(0, PT)[1]
    META["back_top_y_px"] = to_px(0, EH)[1]
    META["flap_top_y_px"] = to_px(0, EH + FL)[1]
    META["opening_x_px"] = [to_px(-EW / 2, 0)[0], to_px(EW / 2, 0)[0]]
    META["envelope_rect_px"] = [to_px(-EW / 2, 0)[0], to_px(0, EH + FL)[1], to_px(EW / 2, 0)[0], to_px(0, 0)[1]]
    META["button_centre_px"] = to_px(BX, BY)
    META["layer_note"] = ("draw envelope_back, then the sliding sheet, then envelope_front; a sheet clipped at "
                          "pocket_top_y_px looks inside the pocket")
with open(os.path.join(OUTDIR, "%s.json" % MODE), "w", encoding="utf-8") as fh:
    json.dump(META, fh, indent=2)
print("[newplan] %s done in %.0fs" % (MODE, time.time() - T0))
