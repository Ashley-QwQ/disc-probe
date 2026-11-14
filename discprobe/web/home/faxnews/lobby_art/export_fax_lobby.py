"""Merge the news-fax lobby renders into the page's lobby folder (lobby.json version 2).

  python export_fax_lobby.py <final dir> <final_parcel dir> <place json> <place_parcel json> <web lobby dir> [--write]

Changes only: base (the fax and the moved file box cast their shadows), filebox (moved 250 mm along -Y: picture,
box, hotspot and label move by the same pixels), the new faxnews layer and target (label on its display), the new
parcel layer and target (hidden until a skin is delivered; its own contact shadow baked into its picture), and the
letter tray's hotspot, which becomes the union of the tray's and the card's own outlines so the parcel can sit in
the gap. Everything else in lobby.json and every other picture is left as it is.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from shapely.geometry import MultiPoint, Polygon
from shapely.ops import unary_union

fin, finp, place, placep, web = map(Path, sys.argv[1:6])
WRITE = "--write" in sys.argv
THEMES = ("paper", "dark")
HERE = Path(__file__).resolve().parent
M = json.loads((HERE / "lobby_orig.json").read_text(encoding="utf-8"))      # always from the committed one: idempotent
O = np.array([1190.43, 673.28])
AX = np.array([[0.48349, 0.29767], [0.48349, -0.29767], [0.0, -0.53881]])     # px per mm of +X, +Y, +Z
VIEW = np.array([-0.557208, 0.557208, -0.615662])
px = lambda p: O + np.asarray(p, float) @ AX                                     # noqa: E731
R = lambda p: [round(float(p[0]), 1), round(float(p[1]), 1)]                     # noqa: E731
P1, P2 = json.loads(place.read_text()), json.loads(placep.read_text())
layer = {l["name"]: l for l in M["layers"]}
out = {}                                                                          # file name -> image


def main_run(idx, gap=120):
    """first and last index of the longest run of idx whose steps are <= gap (export_lobby.py: drops stray specks,
    such as the renderer's line wrapped round the picture's edge)"""
    runs, start = [], idx[0]
    for p_, q_ in zip(idx[:-1], idx[1:]):
        if q_ - p_ > gap:
            runs.append((start, p_)); start = q_
    runs.append((start, idx[-1]))
    return max(runs, key=lambda r: r[1] - r[0])


def alpha_box(imgs, pad=2):
    bbs = []
    for im in imgs:
        a = np.asarray(im)[..., 3] > 4
        rows, cols = main_run(np.where(a.sum(1) >= 3)[0]), main_run(np.where(a.sum(0) >= 3)[0])
        bbs.append((cols[0], rows[0], cols[1] + 1, rows[1] + 1))
    W, H = M["size"]
    return [max(0, int(min(b[0] for b in bbs)) - pad), max(0, int(min(b[1] for b in bbs)) - pad),
            min(W, int(max(b[2] for b in bbs)) + pad), min(H, int(max(b[3] for b in bbs)) + pad)]


def hull_px(verts_mm):
    pts = px(np.asarray(verts_mm)[::3])
    h = MultiPoint([tuple(p) for p in pts]).convex_hull
    return [R(p) for p in list(h.exterior.coords)[:-1]]


def depth_of(verts_mm, ref_name, ref_verts_mm):
    """depth (mm along the view axis) of a part, relative to a layer whose depth lobby.json already gives"""
    c = lambda v: (np.min(v, 0) + np.max(v, 0)) / 2                            # noqa: E731
    return round(layer[ref_name]["depth"] + float(np.dot(c(np.asarray(verts_mm)) - c(np.asarray(ref_verts_mm)), VIEW)), 1)


# ---- base: the new render, checked against the committed one (changes only near the file box and the fax)
for t in THEMES:
    new = Image.open(fin / f"desk_base_{t}.png").convert("RGB")
    old = Image.open(HERE / f"base_orig_{t}.webp").convert("RGB")
    d = np.abs(np.asarray(new, int) - np.asarray(old, int)).max(2)
    ys, xs = np.where(d > 6)
    print(f"base {t}: {int((d > 6).sum())} px differ by > 6/255, bbox x {xs.min() if len(xs) else '-'}..{xs.max() if len(xs) else '-'}"
          f" y {ys.min() if len(ys) else '-'}..{ys.max() if len(ys) else '-'}; max {d.max()}")
    out[f"base_{t}.webp"] = new
# ---- the file box: same picture, moved; its hotspot and label move with it
dfb = np.array([P1.get("filebox_dx_mm", 0.0), P1["filebox_dy_mm"], 0.0]) @ AX
imgs = {t: Image.open(fin / f"desk_filebox_{t}.png").convert("RGBA") for t in THEMES}
box = alpha_box(imgs.values())
for t in THEMES: out[f"filebox_{t}.webp"] = imgs[t].crop(box)
layer["filebox"]["box"] = box
layer["filebox"]["depth"] = round(layer["filebox"]["depth"] + P1.get("filebox_dx_mm", 0.0) * VIEW[0] + P1["filebox_dy_mm"] * VIEW[1], 1)
tg = M["targets"]["filebox"]
tg["hotspot"] = [R(np.array(p) + dfb) for p in tg["hotspot"]]
tg["label"]["quad"] = [R(np.array(p) + dfb) for p in tg["label"]["quad"]]
print("filebox moved by px", R(dfb), "box", box)
# ---- the news fax
imgs = {t: Image.open(fin / f"desk_faxnews_{t}.png").convert("RGBA") for t in THEMES}
box = alpha_box(imgs.values())
for t in THEMES: out[f"faxnews_{t}.webp"] = imgs[t].crop(box)
fb_new = (np.asarray(P1["filebox_verts_mm"]))
fax_layer = {"name": "faxnews", "box": box, "depth": depth_of(P1["fax_verts_mm"], "filebox", fb_new)}
c = P1["fax_screen_corners_mm"]                       # uv00 uv10 uv11 uv01 -> TL TR BR BL = uv01 uv11 uv10 uv00
fax_target = {"layer": "faxnews", "tier": 2, "hotspot": hull_px(P1["fax_verts_mm"]),
              "label": {"text": "新闻", "quad": [R(px(c[3])), R(px(c[2])), R(px(c[1])), R(px(c[0]))], "face": "display"}}
# ---- the parcel: its picture over its own contact shadow (the base with the parcel, where it differs from without)
pimgs = {}
HAVE_PARCEL = (finp / "desk_parcel_paper.png").exists() and (finp / "desk_parcel_dark.png").exists()
for t in (THEMES if HAVE_PARCEL else ()):
    with_p = np.asarray(Image.open(finp / f"desk_base_{t}.png").convert("RGB"), float)
    without = np.asarray(out[f"base_{t}.webp"], float)
    diff = np.abs(with_p - without).max(2)
    near = np.zeros_like(diff, bool)
    hp = hull_px(P2["parcel_verts_mm"]); xs = [p[0] for p in hp]; ys = [p[1] for p in hp]
    near[int(min(ys)) - 120:int(max(ys)) + 160, int(min(xs)) - 160:int(max(xs)) + 120] = True
    a = np.clip((diff - 1.0) / 6.0, 0, 1) * near
    a = ndimage.gaussian_filter(a, 1.0)
    rgba = np.dstack([with_p, a * 255]).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA")
    im.alpha_composite(Image.open(finp / f"desk_parcel_{t}.png").convert("RGBA"))
    pimgs[t] = im
box = alpha_box(pimgs.values()) if HAVE_PARCEL else [0, 0, 1, 1]
for t in (THEMES if HAVE_PARCEL else ()): out[f"parcel_{t}.webp"] = pimgs[t].crop(box)
if not HAVE_PARCEL: print("parcel renders not there yet: parcel layer left out")
pc = P2["parcel_label_corners_mm"]
parcel_layer = {"name": "parcel", "box": box, "depth": depth_of(P2["parcel_verts_mm"], "filebox", fb_new), "hidden": True}
parcel_target = {"layer": "parcel", "tier": 3, "optional": True, "hotspot": hull_px(P2["parcel_verts_mm"]),
                 "label": {"text": "包裹", "quad": [R(px(p)) for p in pc], "face": "label"}}
# ---- the letter tray's hotspot: the tray's and the card's own outlines, joined (it was one hull over both). Their
# pictures touch, so the outlines come from their world boxes (round5 scene: tray x 2634..3006, y -950..-450,
# z 750..887; tent card x 2346..2634, y -1094..-902, z 750..906 mm), each convex, then joined.
def box_hull(x0, x1, y0, y1, z0, z1):
    return MultiPoint([tuple(px((x, y, z))) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]).convex_hull
u = unary_union([box_hull(2634, 3006, -950, -450, 750, 887).buffer(4), box_hull(2346, 2634, -1094, -902, 750, 906).buffer(4)]).simplify(1.0)
old_fax = Polygon(M["targets"]["fax"]["hotspot"])
print("letter tray hotspot: area %.0f -> %.0f px2, new outline inside the old hull: %s" % (old_fax.area, u.area, old_fax.buffer(12).contains(u)))
M["targets"]["fax"]["hotspot"] = [R(p) for p in list(u.exterior.coords)[:-1]]
# ---- gaps at 1280 px wide (the 40 px rule), every pair
polys = {k: Polygon(t["hotspot"]) for k, t in M["targets"].items()}
polys["faxnews"], polys["parcel"] = Polygon(fax_target["hotspot"]), Polygon(parcel_target["hotspot"])
keys = list(polys)
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        g = polys[keys[i]].distance(polys[keys[j]]) * 1280 / M["size"][0]
        if g < 40: print(f"  gap {keys[i]}/{keys[j]}: {g:.1f} px at 1280")
# ---- write
M["layers"] = [l for l in M["layers"] if l["name"] not in ("faxnews", "parcel")] + [fax_layer] + ([parcel_layer] if HAVE_PARCEL else [])
M["targets"] = {**{k: v for k, v in M["targets"].items() if k not in ("faxnews", "parcel")}, "faxnews": fax_target, **({"parcel": parcel_target} if HAVE_PARCEL else {})}
M["source"] = (M.get("source", "") + "; news fax prototype: art/desk/review-20261111/round5 + fax_news.blend 0.9x on the left wing,"
               " file box -250 mm Y, parcel right of the monitor (render_round5.py unchanged but for CPU and the shadow casters)")
if WRITE:
    for name, im in out.items():
        im.save(web / name, "WEBP", quality=92, method=6, exact=True)
    (web / "lobby.json").write_text(json.dumps(M, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written", len(out), "pictures and lobby.json")
else:
    print("dry run: nothing written")
