"""Layers for the "disc goes into the drive" animation (2026-11-11), on the calibration stage's pixel grid.

Not run on its own: render_caltop.py executes this file in its own namespace when called with --anim 1 (after the
scene freeze, camera, palettes and render helpers are set up, instead of its own layers). Every sprite here is
rendered with the same camera direction and px/mm as caltop.json, and cropped to its own box; anim.json gives each
box's top-left corner in caltop pixels (it may be negative or beyond the stage: the animation shows more desk).

The story, top down, the camera following the disc: the disc lies on the desk in front of the open tray, rises
(the page scales it and pulls its shadow away), the world slides down until the tray is under it, it settles into
the tray's recess, the tray carries it into the drive. The last frame is the calibration stage.

Layers (straight-alpha RGBA PNGs, <name>_<variant>.png):
    under       the drive without its tray (shell, mechanism, pickup at its inner place), and its slot empty
    overbody    the drive parts in front of the tray wherever it slides (bezel top, frame): drawn over tray + disc
    overclamp   the clamp bridge part of those: the stage draws it at the occluders' opacity
    shadowbody  the drive's drop shadow without the tray (desk)
    tray        tray + front plate, OPEN; slides by tray.travel_px to close
    trayshadow  its drop shadow, open (slides with it; draw with mix-blend darken over shadowbody)
    prop_<n>    the desk objects (pen, set square, Penrose block), each with prop_<n>_shadow
The disc itself is the stage's disc layer (cropped by compose_anim.py); the lid is the stage's lid layer.
"""

# tray travel: 140 mm (render_burner_layers.py) leaves half the recess under this model's bezel (the spindle sits
# ~130 mm behind the front); at 200 mm the whole 120 mm recess is out and the tray's tail is still inside
ANIM_TRAY_MM = float(arg("--tray-mm", "200"))
# the disc's start on the desk, this far in front of the open recess: clear of the open tray (its front plate is
# ~137 mm in front of the recess centre, plus the disc's 60 mm radius and a gap)
ANIM_START_MM = float(arg("--start-mm", "215"))
RECESS_GUESS_CLOSED = (0.0, 0.2175)        # 120 mm recess centre of the closed tray (render_burner_layers.py)
GROW_T = SS + 1


def mesh_tris(o):
    oe = o.evaluated_get(deps)
    me = oe.to_mesh()
    mw = oe.matrix_world
    co = [mw @ v.co for v in me.vertices]
    polys = [list(p.vertices) for p in me.polygons]
    oe.to_mesh_clear()
    return co, polys


def run_extreme_up(a, K, op, fill):
    """out[y] = op over a[y .. y+K] along axis 0 (rows; beyond the end counts as fill), by doubling windows."""
    n = a.shape[0]

    def up(x, s):
        o = np.full_like(x, fill)
        if s < n:
            o[: n - s] = x[s:]
        return o
    m, w = a, 1
    while w * 2 <= K + 1:
        m = op(m, up(m, w))
        w *= 2
    return op(m, up(m, K + 1 - w))


def grow(a, rad, op, fill):
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


def shifted(a, dx_px, dy_px):
    out = np.zeros_like(a)
    dx, dy = int(round(dx_px)), int(round(dy_px))
    ys0, ys1 = max(0, dy), min(a.shape[0], a.shape[0] + dy)
    xs0, xs1 = max(0, dx), min(a.shape[1], a.shape[1] + dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


# ---------------------------------------------------------------- boxes on the stage's grid
BOX = [0, 0, W, H]


def set_box(b):
    """Render only the caltop-grid pixel box b = [x0, y0, x1, y1] (integers; may lie outside the stage)."""
    global BOX
    BOX = [int(v) for v in b]
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    r.resolution_x, r.resolution_y = bw * SS, bh * SS
    cam.data.ortho_scale = max(bw, bh) / ppu
    wx = cx + (0.5 * (BOX[0] + BOX[2]) - W / 2) / ppu
    wy = cy - (0.5 * (BOX[1] + BOX[3]) - H / 2) / ppu
    cam.location = Vector((wx, wy, 5.0))


def box_of(objs, margin_px=6, extra=(0, 0, 0, 0)):
    P = np.concatenate([world_mesh(o) for o in objs])
    xs = W / 2 + (P[:, 0] - cx) * ppu
    ys = H / 2 - (P[:, 1] - cy) * ppu
    return [int(math.floor(xs.min() - margin_px - extra[0])), int(math.floor(ys.min() - margin_px - extra[1])),
            int(math.ceil(xs.max() + margin_px + extra[2])), int(math.ceil(ys.max() + margin_px + extra[3]))]


def footprint(alpha_ss):
    h_, w_ = alpha_ss.shape
    f = alpha_ss.astype(np.float32)[: h_ // SS * SS, : w_ // SS * SS]
    return f.reshape(h_ // SS, SS, w_ // SS, SS).mean(axis=(1, 3))[::-1]          # final px, top-down


pxmm = ppu / 1000.0


def drop_shadow(foot, off_mm, blur_mm, st, tag):
    """The drive's shadow recipe (render_caltop.py 3b) for any footprint: a soft drop shadow offset by off_mm, a
    tight contact shadow, nothing under the object itself."""
    drop = gauss_blur(shifted(foot, off_mm[0] * pxmm, -off_mm[1] * pxmm), blur_mm * pxmm)
    contact = gauss_blur(shifted(foot, 0.25 * off_mm[0] * pxmm, -0.25 * off_mm[1] * pxmm), max(0.6, 1.6 * min(1.0, blur_mm / SHADOW_BLUR_MM)) * pxmm)
    al = np.clip(np.maximum(st["shadow_alpha"] * drop, st["contact_alpha"] * contact), 0, 1) * (1.0 - foot)
    rgb = np.broadcast_to(np.array(hex_srgb(st["shadow_rgb"]), dtype=np.float32), al.shape + (3,))
    save_png(np.concatenate([rgb, al[..., None].astype(np.float32)], axis=2)[::-1], os.path.join(OUTDIR, tag))


# ---------------------------------------------------------------- the scene for the animation
static_nt = [o for o in static if o.name not in TRAY_OBJECTS]
tray_objs = [o for o in tray_objs_all if not o.hide_render]
body_set = static_nt + sled
DESK_Z = float(min(world_mesh(o)[:, 2].min() for o in static_nt))
TOP_Z = float(world_mesh(cover)[:, 2].max())
DRIVE_H_MM = (TOP_Z - DESK_Z) * 1e3
SHADOW_PER_MM = [v / DRIVE_H_MM for v in SHADOW_MM]
print("[anim] desk z %.2f mm, drive height %.2f mm, shadow per mm of height %s" % (DESK_Z * 1e3, DRIVE_H_MM, SHADOW_PER_MM))

# the disc in the closed tray's recess (circle fit of the 80 mm ring, then the highest support under it)
T_co, T_polys = mesh_tris(bpy.data.objects[TRAY_BODY])
T_np = np.array([tuple(v) for v in T_co])
gx, gy = RECESS_GUESS_CLOSED
rr = np.hypot(T_np[:, 0] - gx, T_np[:, 1] - gy)
ring = T_np[np.abs(rr - 0.0405) < 0.0005]
sol = np.linalg.lstsq(np.c_[2 * ring[:, 0], 2 * ring[:, 1], np.ones(len(ring))], (ring[:, :2] ** 2).sum(1), rcond=None)[0]
RCX, RCY = float(sol[0]), float(sol[1])
from mathutils.bvhtree import BVHTree
bvh = BVHTree.FromPolygons(T_co, T_polys)
sup = []
for a_ in np.linspace(0, 2 * math.pi, 48, endpoint=False):
    for rad in (0.020, 0.030, 0.045, 0.058):
        loc, _n, _i, _d = bvh.ray_cast(Vector((RCX + rad * math.cos(a_), RCY + rad * math.sin(a_), 0.3)), Vector((0, 0, -1)))
        if loc is not None:
            sup.append(loc.z)
SUPPORT_Z = float(max(sup))
disc2 = disc.copy()
scene.collection.objects.link(disc2)
disc2.matrix_world = Matrix.Translation((RCX - DCX, RCY - DCY, SUPPORT_Z + 0.00005 - D_BOT)) @ disc.matrix_world
disc2.hide_render = False
print("[anim] recess centre closed %.2f %.2f mm (clamped disc %.2f %.2f), support z %.2f mm"
      % (RCX * 1e3, RCY * 1e3, DCX * 1e3, DCY * 1e3, SUPPORT_Z * 1e3))
ALL_OBJS.append(disc2)
disc2.pass_index = len(ALL_OBJS)

# ---------------------------------------------------------------- desk objects (modelled here, mm)
MM = 0.001
PROPS = []


def prop_obj(name, bm, mat_key, prop):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    o["mat_key"] = mat_key
    ALL_OBJS.append(o)
    o.pass_index = len(ALL_OBJS)
    prop["objs"].append(o)
    return o


def prism(poly_mm, z0, z1):
    bm = bmesh.new()
    vs = [bm.verts.new((x * MM, y * MM, z0 * MM)) for x, y in poly_mm]
    f = bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=[f])
    if f.normal.z > 0:
        f.normal_flip()
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=(0, 0, (z1 - z0) * MM))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def ring_prism(outer, inner, z0, z1):
    bm = bmesh.new()
    vo = [bm.verts.new((x * MM, y * MM, z0 * MM)) for x, y in outer]
    vi = [bm.verts.new((x * MM, y * MM, z0 * MM)) for x, y in inner]
    n = len(outer)
    faces = [bm.faces.new((vo[i], vo[(i + 1) % n], vi[(i + 1) % n], vi[i])) for i in range(n)]
    ext = bmesh.ops.extrude_face_region(bm, geom=faces)
    top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=(0, 0, (z1 - z0) * MM))
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def rod(x0, x1, r0, r1, seg=40, cap0=True, cap1=True):
    """A lathe along +x lying on the desk (axis at z = max radius), radii r0 -> r1 (mm)."""
    bm = bmesh.new()
    rings = []
    for x, rr_ in ((x0, r0), (x1, r1)):
        rings.append([bm.verts.new((x * MM, rr_ * math.cos(2 * math.pi * k / seg) * MM, rr_ * math.sin(2 * math.pi * k / seg) * MM))
                      for k in range(seg)])
    for k in range(seg):
        bm.faces.new((rings[0][k], rings[0][(k + 1) % seg], rings[1][(k + 1) % seg], rings[1][k]))
    if cap0:
        bm.faces.new(rings[0][::-1])
    if cap1:
        bm.faces.new(rings[1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def place_prop(prop):
    """Lay the prop's objects on the desk at prop['at_mm'] (relative to the disc's start) turned by prop['rot']."""
    sx, sy = START
    M = (Matrix.Translation((sx + prop["at_mm"][0] * MM, sy + prop["at_mm"][1] * MM, DESK_Z))
         @ Matrix.Rotation(math.radians(prop["rot"]), 4, "Z"))
    for o in prop["objs"]:
        o.matrix_world = M @ o.matrix_world


# where things lie: the open recess, the disc's start in front of it
RCY_OPEN = RCY - ANIM_TRAY_MM * MM
START = (RCX, RCY_OPEN - ANIM_START_MM * MM)

# fountain pen: cap (with clip and band), barrel, grip, nib; about 142 mm, 13 mm across, lying, pointing up right
pen = {"name": "pen", "objs": [], "at_mm": [-112.0, 30.0], "rot": 64.0, "height_mm": 13.0}
R_CAP, R_BAR = 6.5, 6.0
prop_obj("pen_cap", rod(-71, -10, R_CAP - 1.2, R_CAP), "pen", pen)
prop_obj("pen_band", rod(-12, -7, R_CAP + 0.25, R_CAP + 0.25), "metal", pen)
prop_obj("pen_barrel", rod(-7, 44, R_BAR, R_BAR - 0.6), "pen", pen)
prop_obj("pen_grip", rod(44, 56, 4.7, 4.0), "pen", pen)
nib = prism([(55, -3.2), (71, -0.6), (71.5, 0), (71, 0.6), (55, 3.2)], 0, 0.8)
prop_obj("pen_nib", nib, "metal", pen)
prop_obj("pen_clip", prism([(-66, -1.3), (-22, -1.3), (-20, 0), (-22, 1.3), (-66, 1.3)], 0, 1.4), "metal", pen)
for o in pen["objs"]:                       # rods lie with their axis at the cap's radius; nib and clip sit on them
    lift = R_CAP
    if o.name == "pen_nib":
        lift = R_CAP - 1.1
    elif o.name == "pen_clip":
        lift = 2 * R_CAP - 0.3
    o.matrix_world = Matrix.Translation((0, 0, lift * MM)) @ o.matrix_world
PROPS.append(pen)

# metal set square: 45 degree, 110 mm legs, 2.2 mm thick, open inside, engraved ticks along both legs
sq = {"name": "square", "objs": [], "at_mm": [112.0, 18.0], "rot": -17.0, "height_mm": 2.2}
Lq, Bq = 110.0, 19.0
outer = [(0, 0), (Lq, 0), (0, Lq)]
k_ = Bq * (1 + math.sqrt(2))
inner = [(Bq, Bq), (Lq - k_, Bq), (Bq, Lq - k_)]
off = (-Lq / 3, -Lq / 3)
prop_obj("square_plate", ring_prism([(x + off[0], y + off[1]) for x, y in outer], [(x + off[0], y + off[1]) for x, y in inner], 0, 2.2), "square", sq)
ticks = bmesh.new()
for i in range(1, 21):
    t = i * 5.0
    ln = 5.0 if i % 2 == 0 else 3.0
    for (x0_, y0_, x1_, y1_) in ((t - 0.25, 0.6, t + 0.25, 0.6 + ln), (0.6, t - 0.25, 0.6 + ln, t + 0.25)):
        if max(x1_, y1_) > Lq - 8:
            continue
        b_ = prism([(x0_ + off[0], y0_ + off[1]), (x1_ + off[0], y0_ + off[1]), (x1_ + off[0], y1_ + off[1]), (x0_ + off[0], y1_ + off[1])], 2.2, 2.25)
        me_ = bpy.data.meshes.new("tick")
        b_.to_mesh(me_)
        b_.free()
        ticks.from_mesh(me_)
        bpy.data.meshes.remove(me_)
prop_obj("square_ticks", ticks, "tick", sq)
PROPS.append(sq)

# the Penrose block: the person's logo traced into three faces (penrose_shape.py), a low block seen from above
pz = {"name": "penrose", "objs": [], "at_mm": [-128.0, 0.0], "rot": 6.0, "height_mm": 6.0}
with open(os.path.join(os.getcwd(), "props", "penrose.json")) as fh:
    PEN_SHAPE = json.load(fh)
for i, piece in enumerate(PEN_SHAPE["pieces"]):
    prop_obj("penrose_%s" % piece["tone"], prism(piece["poly"], 0, 6.0), "penrose_" + piece["tone"], pz)
PROPS.append(pz)

# final positions: pen and square beside the disc's start; the Penrose block by the drive's front left corner
FRONT_Y = float(min(world_mesh(o)[:, 1].min() for o in static_nt if o.name.startswith(BODY_PREFIX)))
LEFT_X = float(min(world_mesh(o)[:, 0].min() for o in static_nt if o.name.startswith(BODY_PREFIX)))
pz["at_mm"] = [(LEFT_X - START[0]) * 1e3 - 52.0, (FRONT_Y - START[1]) * 1e3 + 48.0]
for p in PROPS:
    place_prop(p)
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()

PROP_STYLE = {
    "dark": dict(pen=("#1b2221", "#141a19", "#171d1c"), metal=("#6d7a77", "#4f5a58", "#57625f"),
                 square=("#55615f", "#3e4846", "#454f4d"), tick="#a9b2ad",
                 penrose_light="#5c6865", penrose_mid="#3e4947", penrose_dark="#252e2d"),
    "paper": dict(pen=("#4a4741", "#36342f", "#3c3a35"), metal=("#f3f1ec", "#d6d1c8", "#cdc7bd"),
                  square=("#e4e1db", "#c8c3ba", "#bfb9af"), tick="#6b665d",
                  penrose_light="#f7f4ee", penrose_mid="#d4cec4", penrose_dark="#a39c91"),
}


def apply_props(v, objs):
    global CUR_POOL
    CUR_POOL = POOL_STYLE[v]
    st = PROP_STYLE[v]
    mats = {}
    for o in objs:
        k = o["mat_key"]
        if k not in mats:
            val = st[k]
            if isinstance(val, tuple):
                mats[k] = toon3("prop_%s_%s" % (k, v), val)
            elif k.startswith("penrose"):
                mats[k] = make_toon("prop_%s_%s" % (k, v), hex_lin(val), hex_lin(val, 0.86), hex_lin(val, 0.8))
            else:
                mats[k] = make_toon("prop_%s_%s" % (k, v), hex_lin(val))
        assign(o, mats[k])


def colour(objs, tag, mask, outputs, painter):
    for v in VARIANTS:
        painter(v, objs)
        col = render_exr("%s_color_%s" % (tag, v), SAMPLES, 1.5)
        for pattern, keep in outputs:
            compose_and_save(col, mask, VARIANT_STYLE[v], os.path.join(OUTDIR, pattern % v), keep)
        del col


SPRITES = {}

# ---------------------------------------------------------------- 1. on the stage box: depths
set_box([0, 0, W, H])
show([disc])
_m, DI_A, DI_D = data_passes([disc], "a_disc")
del _m
show([cover])
_m, LID_A, _d = data_passes([cover], "a_lid")
del _m, _d
show(tray_objs + [disc2])
_m, G_A, G_D = data_passes(tray_objs + [disc2], "a_group")
del _m
# the tray (with the disc) slides from closed (here) out to open: screen down = towards row 0 (bottom-up rows)
K = int(round(ANIM_TRAY_MM * pxmm * SS))
G_A = grow(G_A, GROW_T, np.logical_or, False)
G_D = grow(G_D, GROW_T, np.minimum, np.inf)
SW_ANY = run_extreme_up(G_A, K, np.logical_or, False)
SW_MIN = run_extreme_up(G_D, K, np.minimum, np.inf)
del G_A, G_D
DI_A = grow(DI_A, 3, np.logical_or, False)
DI_D = grow(DI_D, 3, np.minimum, np.inf)

# the disc as the lamp lights it at its start on the desk (the stage's disc layer is it clamped, in the pool);
# the page crossfades the two by the pool's strength where the disc is
POOL_STAGE = POOL_C
show([disc])
_m, _a, _d = data_passes([disc], "a_discstart")
del _a, _d
POOL_C = (POOL_STAGE[0] + DCX - START[0], POOL_STAGE[1] + DCY - START[1])
colour([disc], "a_discstart", _m, [("discstart_%s.png", None)], apply_variant)
POOL_C = POOL_STAGE
SPRITES["discstart"] = {"box": [0, 0, W, H]}
del _m

show(body_set)
B_MASK, B_A, B_D = data_passes(body_set, "a_body")
OVER = B_A & SW_ANY & (B_D < SW_MIN)
CLAMP = OVER & DI_A & (B_D < DI_D)
print("[anim] over %d px_ss (clamp %d)" % (int(OVER.sum()), int(CLAMP.sum())))
colour(body_set, "a_body", B_MASK, [("under_%s.png", ~OVER), ("overbody_%s.png", OVER & ~CLAMP), ("overclamp_%s.png", CLAMP)], apply_variant)
for k in ("under", "overbody", "overclamp"):
    SPRITES[k] = {"box": [0, 0, W, H]}
foot = footprint(B_A | LID_A)
for v in VARIANTS:
    drop_shadow(foot, SHADOW_MM, SHADOW_BLUR_MM, VARIANT_STYLE[v], "shadowbody_%s.png" % v)
SPRITES["shadowbody"] = {"box": [0, 0, W, H]}
del B_MASK, B_A, B_D, OVER, CLAMP, SW_ANY, SW_MIN, DI_A, DI_D, LID_A, foot

# ---------------------------------------------------------------- 2. the tray, open, with its shadow
move(tray_objs + [disc2], (0.0, -ANIM_TRAY_MM * MM, 0.0))
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
sm = [abs(v) * pxmm for v in SHADOW_MM]
blur = 3 * SHADOW_BLUR_MM * pxmm
tb = box_of(tray_objs, 6, (sm[0] + blur, blur, blur, sm[1] + blur))
set_box(tb)
show(tray_objs)
T_MASK, T_A, _d = data_passes(tray_objs, "a_tray")
del _d
colour(tray_objs, "a_tray", T_MASK, [("tray_%s.png", None)], apply_variant)
POOL_C = (POOL_STAGE[0], POOL_STAGE[1] - ANIM_TRAY_MM * MM)        # lit as it is when closed
colour(tray_objs, "a_trayin", T_MASK, [("trayin_%s.png", None)], apply_variant)
POOL_C = POOL_STAGE
SPRITES["trayin"] = {"box": tb}
foot = footprint(T_A)
for v in VARIANTS:
    drop_shadow(foot, SHADOW_MM, SHADOW_BLUR_MM, VARIANT_STYLE[v], "trayshadow_%s.png" % v)
SPRITES["tray"] = {"box": tb}
SPRITES["trayshadow"] = {"box": tb}
del T_MASK, T_A, foot

# ---------------------------------------------------------------- 3. the desk objects
for p in PROPS:
    h_mm = p["height_mm"]
    off_mm = [v * h_mm for v in SHADOW_PER_MM]
    blur_mm = max(1.2, SHADOW_BLUR_MM * h_mm / DRIVE_H_MM)
    m_ = [abs(off_mm[0]) * pxmm + 3 * blur_mm * pxmm, abs(off_mm[1]) * pxmm + 3 * blur_mm * pxmm]
    b = box_of(p["objs"], 6, (m_[0], 3 * blur_mm * pxmm, 3 * blur_mm * pxmm, m_[1]))
    set_box(b)
    show(p["objs"])
    P_MASK, P_A, _d = data_passes(p["objs"], "a_" + p["name"])
    del _d
    colour(p["objs"], "a_" + p["name"], P_MASK, [("prop_%s_%%s.png" % p["name"], None)], apply_props)
    foot = footprint(P_A)
    for v in VARIANTS:
        drop_shadow(foot, off_mm, blur_mm, VARIANT_STYLE[v], "prop_%s_shadow_%s.png" % (p["name"], v))
    SPRITES["prop_" + p["name"]] = {"box": b}
    SPRITES["prop_%s_shadow" % p["name"]] = {"box": b}
    del P_MASK, P_A, foot

# ---------------------------------------------------------------- 4. json
info = {
    "grid": "caltop.json pixels (top-left of the stage image, y down); sprite boxes [x0, y0, x1, y1] in that grid",
    "image_size": [W, H],
    "px_per_mm": round(ppu / 1000.0, 5),
    "sprites": SPRITES,
    "variants": VARIANTS,
    "tray": {"travel_mm": ANIM_TRAY_MM, "travel_px": dir_px((0, 1, 0), ANIM_TRAY_MM),
             "note": "tray / trayshadow are rendered OPEN; add travel_px * t (t 0 open .. 1 closed) to close"},
    "disc": {"clamped_px": to_px((DCX, DCY, D_TOP)), "recess_closed_px": to_px((RCX, RCY, D_TOP)),
             "recess_open_px": to_px((RCX, RCY_OPEN, D_TOP)), "start_px": to_px((START[0], START[1], DESK_Z)),
             "radius_px": round(D_R * ppu, 2),
             "note": "start: lying on the desk; recess_open: in the open tray; recess_closed then clamped: the stage"},
    "shadow": {"offset_mm": SHADOW_MM, "blur_mm": SHADOW_BLUR_MM, "per_mm_height": [round(v, 4) for v in SHADOW_PER_MM],
               "drive_height_mm": round(DRIVE_H_MM, 2),
               "note": "an object h mm above the desk throws its shadow per_mm_height * h mm away (props: h = their height)"},
    "pool": {"centre_px": to_px((POOL_C[0], POOL_C[1], 0.0)), "sigma_px": round(POOL_SIGMA_MM * ppu / 1000.0, 2),
             "style": POOL_STYLE,
             "note": "moving parts come in two lightings: discstart (at start_px) / stage disc (clamped), tray (open) / trayin (closed); crossfade by the pool strength f = exp(-d^2 / 2 sigma^2) at their place"},
    "props": [{"name": p["name"], "height_mm": p["height_mm"], "at_mm_from_start": [round(v, 2) for v in p["at_mm"]], "rot_deg": p["rot"]}
              for p in PROPS],
}
with open(os.path.join(OUTDIR, "anim.json"), "w") as fh:
    json.dump(info, fh, indent=2)
print("[anim] done", OUTDIR)
