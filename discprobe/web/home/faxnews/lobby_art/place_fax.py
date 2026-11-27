"""Lobby scene for the news-fax prototype: round5 + file box moved 250 mm toward -Y + the news fax (0.9x) on the
left wing + (optional) a parcel box right of the monitor. Never saves over its input.
  blender -b room_round5.blend --python place_fax.py -- --fax fax_news.blend --out room_fax.blend [--parcel]"""
import bpy, bmesh, json, math, sys
from mathutils import Matrix, Vector
argv = sys.argv[sys.argv.index("--") + 1:]
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
FAX_AT, FAX_S, FAX_ROT = (1.250, -2.400, 0.750), 0.9, 0.0
FILEBOX_DY, FILEBOX_DX = -0.250, 0.090    # along the wing toward the viewer, and toward its front edge (stays in the picture)
PARCEL_AT, PARCEL_ROT = (2.250, -0.520, 0.750), math.radians(-8)
sc = bpy.context.scene
for o in sc.objects:
    if o.get("layer") == "filebox" and o.parent is None:
        o.location.y += FILEBOX_DY
        o.location.x += FILEBOX_DX
# the news fax
with bpy.data.libraries.load(arg("--fax"), link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith("fax_")]
root = Matrix.Translation(FAX_AT) @ Matrix.Rotation(math.radians(FAX_ROT), 4, "Z") @ Matrix.Scale(FAX_S, 4)
fax = []
for o in dst.objects:
    if o is None: continue
    if o.name == "fax_paper":                  # the sheet hidden in the paper path: not in the lobby
        bpy.data.objects.remove(o); continue
    sc.collection.objects.link(o)
    fax.append(o)
for o in fax:
    if o.parent is None:                          # matrix_world is not evaluated yet for appended objects: use the basis
        o.matrix_basis = root @ o.matrix_basis
for o in fax:
    o["layer"] = "faxnews"
    o["kind"] = "facing"
    o["cull"] = 0
    o["nolines"] = 0
    if "mat" not in o: print("[place] no mat on", o.name)
bpy.context.view_layer.update()
info = {"fax_objects": [o.name for o in fax], "filebox_dy_mm": FILEBOX_DY * 1000, "filebox_dx_mm": FILEBOX_DX * 1000, "fax_at_mm": [v * 1000 for v in FAX_AT],
        "fax_scale": FAX_S, "fax_rot_deg": FAX_ROT}
# world vertices (mm) for hotspots, and the screen face for the printed label
def verts(objs):
    out = []
    for o in objs:
        if o.type != "MESH": continue
        m = o.matrix_world
        out += [[round(c * 1000, 1) for c in (m @ v.co)] for v in o.data.vertices]
    return out
info["fax_verts_mm"] = verts(fax)
scr = json.load(open(arg("--parts"), encoding="utf-8"))
face = next(p for p in scr["parts"] if p["name"] == "fax_screen")["face_mm"]["corners_uv00_uv10_uv11_uv01"]
info["fax_screen_corners_mm"] = [[round(c * 1000, 1) for c in root @ Vector([x / 1000 for x in p])] for p in face]
fb = [o for o in sc.objects if o.get("layer") == "filebox"]
info["filebox_verts_mm"] = verts(fb)
if "--parcel" in argv:
    def box(name, size, at, mat, layer="parcel"):
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
        bmesh.ops.translate(bm, vec=Vector(at), verts=bm.verts)
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        o = bpy.data.objects.new(name, me); sc.collection.objects.link(o)
        o["layer"], o["mat"], o["kind"], o["cull"], o["nolines"] = layer, mat, "facing", 0, 0
        return o
    W, D, H = 0.280, 0.200, 0.160       # a shoebox-sized parcel, real size
    parts = [
        box("parcel_box", (W, D, H), (0, 0, H / 2), "kraft"),
        box("parcel_tape_top", (W + 0.002, 0.048, 0.0010), (0, 0, H + 0.0009), "string"),
        box("parcel_tape_l", (0.0012, 0.048, 0.070), (-W / 2 - 0.0006, 0, H - 0.035), "string"),
        box("parcel_tape_r", (0.0012, 0.048, 0.070), (W / 2 + 0.0006, 0, H - 0.035), "string"),
        box("parcel_label", (0.090, 0.060, 0.0006), (0.070, -0.055, H + 0.0017), "sheet"),
    ]
    pm = Matrix.Translation(PARCEL_AT) @ Matrix.Rotation(PARCEL_ROT, 4, "Z")
    for o in parts: o.matrix_basis = pm @ o.matrix_basis
    bpy.context.view_layer.update()
    info["parcel_verts_mm"] = verts(parts)
    info["parcel_at_mm"] = [v * 1000 for v in PARCEL_AT]
    lab = [Vector((0.070 + dx * 0.045, -0.055 + dy * 0.030, H + 0.0020)) for dx, dy in ((-1, 1), (1, 1), (1, -1), (-1, -1))]
    info["parcel_label_corners_mm"] = [[round(c * 1000, 1) for c in pm @ p] for p in lab]
bpy.ops.wm.save_as_mainfile(filepath=arg("--out"), copy=True)
json.dump(info, open(arg("--out").replace(".blend", "_place.json"), "w"))
print("[place] saved", arg("--out"), len(fax), "fax objects")
