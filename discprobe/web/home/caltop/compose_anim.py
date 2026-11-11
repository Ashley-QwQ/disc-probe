"""Local step after the two glassbox runs (run_caltop.sh): the stage layers (out_pool/) and the animation layers
(out_anim/) become the web files.

    python -I compose_anim.py [--stage out_pool] [--anim out_anim] [--to .]

Writes, next to this file:
    <stage layer>_<v>.webp + caltop.json      the calibration stage (lit by the lamp's pool), as before
    anim/<sprite>_<v>.webp + anim/anim.json   the animation sprites, each cut to its own pixels
    anim/disc*_<v>.webp                       the disc alone (stage lighting / start lighting) and its two shadows
    anim/pool_<v>.webp                        the lamp's pool on the desk (quarter size: the page scales it 4x)
    anim/desk_<v>.webp                        a tileable desk grain (alpha over the page colour)
    anim/final_<v>.webp                       the last frame baked into one image: props + the stage as the page
                                              draws it (disc, clamp and shell at their opacities); pool and grain
                                              stay separate (they are larger than any picture)
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


STAGE = os.path.join(HERE, arg("--stage", "out_pool"))
ANIMD = os.path.join(HERE, arg("--anim", "out_anim"))
TO = os.path.join(HERE, arg("--to", "."))
OUTA = os.path.join(TO, "anim")
os.makedirs(OUTA, exist_ok=True)
V = ["dark", "paper"]
PAGE = {"paper": "#ebe7e0", "dark": "#161d1c"}           # --paper in index.html
INK = {"paper": "#1d1b18", "dark": "#ecebe4"}
SHADOW = {"dark": ("#050807", 0.42, 0.55), "paper": ("#3a2f22", 0.24, 0.34)}   # render_caltop.py VARIANT_STYLE
STAGE_OPACITY = {"disc": 0.62, "occluders": 0.45, "lid": 0.2}                 # index.html .cs-art rules
STAGE_ORDER = ["shadow", "bg", "sled", "mid", "disc", "occluders", "lid"]


def load(path):
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255.0


def save_webp(a, path):
    Image.fromarray(np.clip(np.rint(a * 255), 0, 255).astype(np.uint8), "RGBA").save(path, lossless=True, method=6)


def hexf(h):
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)], dtype=np.float32)


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def cut(a, box):
    """Trim transparent margins; returns the trimmed image and its box."""
    ys, xs = np.nonzero(a[..., 3] > 1 / 512)
    if not len(ys):
        return a[:1, :1], [box[0], box[1], box[0] + 1, box[1] + 1]
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return a[y0:y1, x0:x1], [box[0] + int(x0), box[1] + int(y0), box[0] + int(x1), box[1] + int(y1)]


def over(dst, dbox, src, sbox, opacity=1.0):
    """Straight-alpha src over dst (both RGBA float), boxes in the same grid; dst modified in place."""
    x0, y0 = max(dbox[0], sbox[0]), max(dbox[1], sbox[1])
    x1, y1 = min(dbox[2], sbox[2]), min(dbox[3], sbox[3])
    if x0 >= x1 or y0 >= y1:
        return
    d = dst[y0 - dbox[1]:y1 - dbox[1], x0 - dbox[0]:x1 - dbox[0]]
    s = src[y0 - sbox[1]:y1 - sbox[1], x0 - sbox[0]:x1 - sbox[0]]
    sa = s[..., 3:4] * opacity
    da = d[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    d[..., :3] = np.where(oa > 1e-6, rgb, 0)
    d[..., 3:4] = oa


# ---------------------------------------------------------------- the stage, lit
cal = json.load(open(os.path.join(STAGE, "caltop.json")))
for k in ["shadow", "bg", "sled", "mid", "disc", "glow", "occluders", "lid"]:
    for v in V:
        save_webp(load(os.path.join(STAGE, "%s_%s.png" % (k, v))), os.path.join(TO, "%s_%s.webp" % (k, v)))
json.dump(cal, open(os.path.join(TO, "caltop.json"), "w"), indent=2)
W, H = cal["image_size"]
print("stage", W, H)

# ---------------------------------------------------------------- animation sprites
an = json.load(open(os.path.join(ANIMD, "anim.json")))
pxmm = an["px_per_mm"]
sprites = {}
img = {}                                        # (name, variant) -> (array, box), for the final frame
for name, s in an["sprites"].items():
    full = {v: load(os.path.join(ANIMD, "%s_%s.png" % (name, v))) for v in V}
    boxes = [cut(full[v], s["box"])[1] for v in V]          # one box for both themes (same geometry)
    b = [min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)]
    o = s["box"]
    for v in V:
        a = full[v][b[1] - o[1]:b[3] - o[1], b[0] - o[0]:b[2] - o[0]]
        save_webp(a, os.path.join(OUTA, "%s_%s.webp" % (name, v)))
        img[(name, v)] = (a, b)
    sprites[name] = {"box": b}

# the disc alone: stage lighting (the stage's disc layer) and start lighting, cut round the clamped centre
cx, cy = cal["disc"]["centre_px"]
R = cal["disc"]["radius_px"]
db = [int(math.floor(cx - R - 4)), int(math.floor(cy - R - 4)), int(math.ceil(cx + R + 4)), int(math.ceil(cy + R + 4))]
for name, src in (("disc", lambda v: load(os.path.join(STAGE, "disc_%s.png" % v))),
                  ("discstart", lambda v: load(os.path.join(ANIMD, "discstart_%s.png" % v)))):
    for v in V:
        full = src(v)
        save_webp(full[db[1]:db[3], db[0]:db[2]], os.path.join(OUTA, "%s_%s.webp" % (name, v)))
    sprites[name] = {"box": db}

# the disc's shadow: its ring on the desk, near (lying) and far (at the top of its flight)
APEX_MM = 30.0
per = an["shadow"]["per_mm_height"]
hole = cal["disc"]["hole_radius_px"]


def blur(a, sigma):
    if sigma <= 0.3:
        return a
    r_ = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r_, r_ + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda x: np.convolve(x, k, mode="same"), 0, a)
    return np.apply_along_axis(lambda x: np.convolve(x, k, mode="same"), 1, a)


def ring_shadow(sigma_px, alpha, v):
    pad = int(math.ceil(3 * sigma_px)) + 4
    n = int(math.ceil(2 * R)) + 2 * pad
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    rr = np.hypot(xx - n / 2, yy - n / 2)
    foot = np.clip(R - rr + 0.5, 0, 1) * np.clip(rr - hole + 0.5, 0, 1)
    al = np.clip(blur(foot, sigma_px) * alpha, 0, 1)
    rgb = np.broadcast_to(hexf(SHADOW[v][0]), al.shape + (3,))
    return np.concatenate([rgb, al[..., None]], axis=2), n


for name, sigma_mm, which in (("discshadow_near", 1.0, 2), ("discshadow_far", max(1.2, an["shadow"]["blur_mm"] * APEX_MM / an["shadow"]["drive_height_mm"]), 1)):
    for v in V:
        a, n = ring_shadow(sigma_mm * pxmm, SHADOW[v][which], v)
        save_webp(a, os.path.join(OUTA, "%s_%s.webp" % (name, v)))
    sprites[name] = {"box": [round(cx - n / 2), round(cy - n / 2), round(cx - n / 2) + n, round(cy - n / 2) + n],
                     "note": "centred on the disc centre; offset by the height (shadow.per_mm_height * h mm)"}

# the lamp's pool on the desk: page colour * (1 + gain f) + add f (amb 1 on the desk, so it meets the page seamlessly)
pc, ps = an["pool"]["centre_px"], an["pool"]["sigma_px"]
Q = 4
half = int(math.ceil(3.2 * ps / Q))
yy, xx = (np.mgrid[0:2 * half, 0:2 * half] + 0.5 - half) * Q
f = np.exp(-(xx ** 2 + yy ** 2) / (2 * ps ** 2))[..., None]
for v in V:
    st = an["pool"]["style"][v]
    bg = lin(hexf(PAGE[v]))
    tgt = bg * (1 + np.array(st["gain"]) * f) + np.array(st["add"]) * f
    tgt_s = srgb(tgt)
    bg_s = hexf(PAGE[v])
    al = np.clip(np.abs(tgt_s - bg_s).max(axis=2, keepdims=True) * 40, 0, 1)    # opaque where it differs visibly
    rgb = np.where(al > 1e-4, bg_s + (tgt_s - bg_s) / np.maximum(al, 1e-4), bg_s)
    save_webp(np.concatenate([np.clip(rgb, 0, 1), al], axis=2), os.path.join(OUTA, "pool_%s.webp" % v))
sprites["pool"] = {"box": [round(pc[0] - half * Q), round(pc[1] - half * Q), round(pc[0] + half * Q), round(pc[1] + half * Q)],
                   "scale": Q, "note": "quarter-size picture; draw it over its whole box"}

# desk grain: periodic noise, long along x (the desk's grain runs across), a little speckle
rng = np.random.default_rng(7)
N = 512
fy, fx = np.meshgrid(np.fft.fftfreq(N), np.fft.fftfreq(N), indexing="ij")
grain = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * np.exp(-((fx / 0.004) ** 2 + (fy / 0.06) ** 2))))
speck = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * np.exp(-((fx ** 2 + fy ** 2) / 0.12 ** 2))))
g = (grain - grain.mean()) / grain.std() * 0.8 + (speck - speck.mean()) / speck.std() * 0.35
for v, amt in (("paper", 0.016), ("dark", 0.022)):      # a hint of grain, not brushed metal
    al = np.clip((g + 2.0) / 4.0, 0, 1) * amt
    rgb = np.broadcast_to(hexf(INK[v]), al.shape + (3,))
    save_webp(np.concatenate([rgb, al[..., None]], axis=2).astype(np.float32), os.path.join(OUTA, "desk_%s.webp" % v))

# ---------------------------------------------------------------- the last frame in one picture
props = [p["name"] for p in an["props"]]
final_layers = []
for p in props:
    final_layers.append(("prop_%s_shadow" % p, 1.0, "anim"))
for p in props:
    final_layers.append(("prop_%s" % p, 1.0, "anim"))
for k in STAGE_ORDER:
    final_layers.append((k, STAGE_OPACITY.get(k, 1.0), "stage"))
boxes = [sprites[n]["box"] for n, _o, src in final_layers if src == "anim"] + [[0, 0, W, H]]
fb = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
for v in V:
    out = np.zeros((fb[3] - fb[1], fb[2] - fb[0], 4), dtype=np.float32)
    for n, o, src in final_layers:
        if src == "anim":
            a, b = img[(n, v)]
        else:
            a, b = load(os.path.join(STAGE, "%s_%s.png" % (n, v))), [0, 0, W, H]
        over(out, fb, a, b, o)
    save_webp(out, os.path.join(OUTA, "final_%s.webp" % v))
sprites["final"] = {"box": fb, "note": "the last frame without pool and grain: props + the stage at the page's opacities"}

# the drive's body on the stage grid (no shadow): the page centres this, not the whole picture
cal["body_px"] = sprites["under"]["box"]
json.dump(cal, open(os.path.join(TO, "caltop.json"), "w"), indent=2)

meta = dict(an)
meta["sprites"] = sprites
meta["apex_mm"] = APEX_MM
meta["stage_opacity"] = STAGE_OPACITY
json.dump(meta, open(os.path.join(OUTA, "anim.json"), "w"), indent=2)
print("wrote", OUTA, "sprites:", ", ".join(sorted(sprites)))
