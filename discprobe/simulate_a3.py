"""Lamp-view prediction of a work document with the A3 v3 texture model, seen straight down (no perspective).

The optics are those of Disc Lab's phone photos (disclab/photos.py) on a flat disc:

* each texture's first- and higher-order light against delta_t, the along-track part of (to camera + to flash),
  from the A3 v3 wave model (the same tables as the Disc Neo colour cards, LED lamp); simulate_a3v3.npz;
* the grooves' own rainbow (delta_t ~ 0, lambda = pitch * delta_r) and the flash's mirror glare;
* the mirror showing the room, darkened where marks were written (A5 more than other textures). This is what
  makes a burned DVD-R look purple-brown with darker chips in photos, at poses where no texture diffracts.

Each sample is the share of every material over its own square of burn cells (simulate.coverage), so a dither
mixes as the eye sees it. Prediction only; not checked against photos of this document.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .simulate import CAMERA, FLASH, EDGE_MM, HUB_MM, FINE_SAMPLES, coverage, unit

TABLE = Path(__file__).with_name("simulate_a3v3.npz")
A5_PERIOD_UM = .8528123052898693
PITCH_UM = .74          # DVD track pitch
TEX_GAIN = 1.0
DESATURATE = .4         # phone colour processing, as Disc Lab
VEIL = .04              # the room in the mirror, relative to a bright texture
VEIL_RGB = (.80, .62, 1.0)   # through the dye: DVD-R mirrors look purple
GLARE_GAIN = 60.
RAINBOW_GAIN = 6.
ZERO_ORDER_DARK = .15   # how much of the mirror A5's marks take away (Disc Lab's default disc)
OTHER_DARK = .4         # other textures, relative to A5 (Disc Lab: B9 and recorded data)


@lru_cache(maxsize=1)
def tables():
    with np.load(TABLE, allow_pickle=False) as z:
        specs = [str(s) for s in z["specs"]]
        return dict(specs={s: i for i, s in enumerate(specs)}, delta=z["delta"].astype(float), xyz=z["xyz"].astype(float),
                    cmf_nm=z["cmf_nm"].astype(float), cmf=z["cmf"].astype(float), m=z["xyz_to_srgb"].astype(float),
                    signature=str(z["signature"]))


def canonical(spec):
    if spec.strip().upper() == "RND":
        return "RND"
    seq = bytes.fromhex(spec)
    for period in range(1, len(seq) + 1):
        if len(seq) % period == 0 and seq == seq[:period] * (len(seq) // period):
            return seq[:period].hex().upper()
    return seq.hex().upper()


def material_xyz(material, d_t):
    """XYZ (LED, A3 v3) a material sends to the camera at along-track factor d_t. A spec the table does not hold
    uses A5's curve stretched to the material's period: an approximation, flagged in the render's record."""
    t = tables()
    spec = canonical(material["spec"])
    if spec == "RND":
        # recorded random data: no dominant period, its light spread too thin to show; only the mirror darkens
        return np.zeros(np.shape(d_t) + (3,))
    if spec in t["specs"]:
        curve, scale = t["xyz"][t["specs"][spec]], 1.
    else:
        period = material.get("period_um") or (material.get("periods_um") or [None])[0]
        if not period or not math.isfinite(period) or period <= 0:
            raise ValueError(f"texture {spec} is not in the A3 v3 table and has no period")
        curve, scale = t["xyz"][t["specs"]["A5"]], period / A5_PERIOD_UM
    v = d_t * scale
    return np.stack([np.interp(v, t["delta"], curve[:, k], left=0, right=0) for k in range(3)], -1)


def known(material):
    return canonical(material["spec"]) in tables()["specs"]


def render(design, size=800, *, materials, camera=CAMERA, flash=FLASH, rotate=0, fine=True, annulus_mm=None,
           paper=False, edge_mm=EDGE_MM, delta_scale=1.):
    """Physical geometry uses scale=1. delta_scale is retained for explicit legacy-work replay;
    it affects texture lookup only, not the grooves' rainbow or mirror glare."""
    if size < 200 or size > 4096:
        raise ValueError("size must be between 200 and 4096 pixels")
    if design.dtype != np.uint8 or not materials or int(design.max()) >= len(materials):
        raise ValueError("material labels must index the document's material table")
    t = tables()
    cam, fl = np.asarray(camera, float), np.asarray(flash, float)
    k = max(1, math.ceil(FINE_SAMPLES / size)) if fine else 1
    n = size * k
    c = (np.arange(n) + .5) * 120 / n - 60
    x, y = np.meshgrid(c, -c)
    a = math.radians(rotate % 360)
    dx = x * math.cos(a) + y * math.sin(a)
    dy = -x * math.sin(a) + y * math.cos(a)
    r = np.hypot(x, y)
    alpha = np.arctan2(y, x)
    ca, sa = np.cos(alpha), np.sin(alpha)
    cx, cy = unit(cam, x, y)
    lx, ly = unit(fl, x, y)
    svx, svy = cx + lx, cy + ly
    d_t = np.abs(-svx * sa + svy * ca)
    d_r = svx * ca + svy * sa
    ldist = np.sqrt((fl[0] - x) ** 2 + (fl[1] - y) ** 2 + fl[2] ** 2)
    irr = (np.linalg.norm(fl) / ldist) ** 2
    lamp_ang = max(3. / np.linalg.norm(cam), .004)

    a5 = t["xyz"][t["specs"]["A5"]]
    ref = max(float(a5[:, 1].max()), float(t["xyz"][t["specs"]["B9"]][:, 1].max()))
    tex = np.zeros(r.shape + (3,))
    attenuation = np.zeros(r.shape)
    # shares over each output pixel's square (what the eye or a phone pixel mixes), read at its fine samples
    for slot, share in coverage(design, size, dx, dy):
        m = materials[slot]
        tex += share[..., None] * material_xyz(m, d_t * delta_scale)
        attenuation += share * (1. if canonical(m["spec"]) == "A5" else OTHER_DARK)
    tex *= (irr * TEX_GAIN / ref)[..., None]
    blank = np.zeros(r.shape, bool) if annulus_mm is None else (r < annulus_mm[0]) | (r >= annulus_mm[1])
    tex[blank] = 0
    attenuation[blank] = 0

    w_t = np.exp(-.5 * (d_t / lamp_ang) ** 2)
    lam = PITCH_UM * np.abs(d_r) * 1000.
    cmf = np.stack([np.interp(lam, t["cmf_nm"], t["cmf"][:, j], left=0, right=0) for j in range(3)], -1)
    grooved = (r > 22.6) & (r < 58.7)
    rain = cmf * (w_t * irr * grooved * RAINBOW_GAIN)[..., None]
    w_g = 1. / (1. + np.exp(np.clip((np.hypot(d_t, d_r) / 2 - lamp_ang) / (.12 * lamp_ang), -60, 60)))
    glare = (GLARE_GAIN * w_g * irr)[..., None] * np.array([.95, 1., 1.05])
    veil = VEIL * np.asarray(VEIL_RGB)
    z0 = np.clip(1 - ZERO_ORDER_DARK * attenuation, 0, 1)

    m = t["m"]
    trgb = np.clip(tex @ m.T, 0, None)
    grey = trgb.mean(-1, keepdims=True)
    trgb = grey + (1 - DESATURATE) * (trgb - grey)
    rgb = trgb + np.clip(rain @ m.T, 0, None) + (glare + veil) * z0[..., None]
    rgb = rgb.reshape(size, k, size, k, 3).mean((1, 3))
    rs = r.reshape(size, k, size, k).mean((1, 3))
    clear = w_g.reshape(size, k, size, k).max((1, 3)) < .01
    disc = (rs > 24) & (rs < 58) & clear
    level = float(np.quantile(rgb[disc].mean(-1), .98)) if disc.any() else 1.
    rgb = np.clip(rgb * (.85 / max(level, 1e-6)), 0, 1)
    rgb[(rs < HUB_MM) | (rs >= edge_mm)] = 1 if paper else 0
    enc = np.where(rgb <= .0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - .055)
    return Image.fromarray(np.uint8(np.clip(np.rint(enc * 255), 0, 255)))


def _patch_light(materials, camera, flash, at, delta_scale):
    """Each material's own light (XYZ) at one point, relative to the brightest of A5 and B9 at their best angle."""
    t = tables()
    cam, fl = np.asarray(camera, float), np.asarray(flash, float)
    x, y = np.array([[at[0]]]), np.array([[at[1]]])
    alpha = np.arctan2(y, x)
    cx, cy = unit(cam, x, y)
    lx, ly = unit(fl, x, y)
    d_t = np.abs(-(cx + lx) * np.sin(alpha) + (cy + ly) * np.cos(alpha))
    ldist = np.sqrt((fl[0] - x) ** 2 + (fl[1] - y) ** 2 + fl[2] ** 2)
    irr = (np.linalg.norm(fl) / ldist) ** 2
    ref = max(float(t["xyz"][t["specs"][s]][:, 1].max()) for s in ("A5", "B9"))
    return [material_xyz(mat, d_t * delta_scale)[0, 0] * irr[0, 0] * TEX_GAIN / ref for mat in materials]


def swatch_signal(materials, camera=CAMERA, flash=FLASH, at=(40., 0.), delta_scale=1.):
    """How bright each material's own light is at that point (Y, relative to a bright texture at its best angle).
    Below VEIL it is fainter than the room seen in the mirror, so the patch shows the mirror, not a colour."""
    return {mat["id"]: float(xyz[1]) for mat, xyz in zip(materials, _patch_light(materials, camera, flash, at, delta_scale))}


def swatches(materials, camera=CAMERA, flash=FLASH, at=(40., 0.), delta_scale=1.):
    """Display colour of each material on its own at one point of the disc (default r = 40 mm), with the mirror
    and the exposure of a render of that pose: what the lamp view shows for a patch of it there. delta_scale as
    render()."""
    t = tables()
    m = t["m"]
    linear = {}
    for mat, tex in zip(materials, _patch_light(materials, camera, flash, at, delta_scale)):
        rgb = np.clip(tex @ m.T, 0, None)
        rgb = rgb.mean() + (1 - DESATURATE) * (rgb - rgb.mean())
        att = 1. if canonical(mat["spec"]) == "A5" else OTHER_DARK
        linear[mat["id"]] = rgb + VEIL * np.asarray(VEIL_RGB) * (1 - ZERO_ORDER_DARK * att)
    level = max([float(v.mean()) for v in linear.values()] + [VEIL])
    out = {}
    import colorsys
    for ident, v in linear.items():
        v = np.clip(v * (.85 / level), 0, 1)
        enc = np.where(v <= .0031308, 12.92 * v, 1.055 * v ** (1 / 2.4) - .055)
        rgb = [int(c) for c in np.rint(enc * 255)]
        hue = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[0] * 360
        out[ident] = dict(rgb=rgb, hue=hue, dark=max(rgb) < 85 or max(rgb) - min(rgb) < 12)
    return out



def burn_colours(materials):
    """The colour each material shows when it lights up (its brightest viewing angle in the A3 v3 table), at a
    common display brightness: the colour the Disc Neo card gives it. Keyed by material id and canonical spec.
    RND and textures without light get none."""
    t = tables()
    m = t["m"]
    out = {}
    for mat in materials:
        curve = material_xyz(mat, t["delta"])
        if not curve[:, 1].max() > 0:
            continue
        rgb = np.clip(curve[int(np.argmax(curve[:, 1]))] @ m.T, 0, None)
        rgb = rgb.mean() + (1 - DESATURATE) * (rgb - rgb.mean())
        v = np.clip(rgb * (.85 / max(float(rgb.max()), 1e-9)), 0, 1)
        enc = np.where(v <= .0031308, 12.92 * v, 1.055 * v ** (1 / 2.4) - .055)
        out[mat["id"]] = out[canonical(mat["spec"])] = [int(c) for c in np.rint(enc * 255)]
    return out
