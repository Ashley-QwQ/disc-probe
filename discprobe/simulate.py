"""CPU prediction of a two-texture DVD, in data-side view."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

CAMERA = (0., 70., 330.)
FLASH = (-43.66, 89.79, 330.)
HUB_MM, EDGE_MM = 24.6, 57.6
GROOVE_GAIN = .15
BANDS = "bands"     # as --light: bright bytes chosen by viewing angle from a measured chart, as on the figures disc
FINE_SAMPLES = 2000     # samples across the disc before averaging down: 0.06 mm, as art/sim_view.py
PHOTO_SATURATION = .6   # a phone records the grating's colours far less pure than the spectrum


def texture(value):
    if len(value) != 2:
        raise ValueError("simulate supports single-byte textures such as A5 or B9, and --light bands")
    try:
        return int(value, 16)
    except ValueError:
        raise ValueError("simulate supports single-byte textures such as A5 or B9") from None


def load_design(path):
    d = np.load(path, mmap_mode="r", allow_pickle=False)
    if d.shape != (6000, 6000) or d.dtype != bool:
        raise ValueError("design must be a boolean 6000 x 6000 array (True = dark)")
    return d


def sampled(design, size, rotate=0):
    a = math.radians(rotate % 360)
    c = (np.arange(size) + .5) * 120 / size - 60
    x, y = np.meshgrid(c, -c)
    dx = x * math.cos(a) + y * math.sin(a)
    dy = -x * math.sin(a) + y * math.cos(a)
    cell = 120 / design.shape[0]
    ix = np.clip(np.floor((dx + 60) / cell).astype(int), 0, design.shape[1]-1)
    iy = np.clip(np.floor((60 - dy) / cell).astype(int), 0, design.shape[0]-1)
    return design[iy, ix], x, y, dx, dy


def unit(p, x, y):
    vx, vy = p[0] - x, p[1] - y
    n = np.sqrt(vx * vx + vy * vy + p[2] * p[2])
    return vx / n, vy / n


def along_track(x, y, camera, flash):
    """The part of (view + light) along the track, which sets the colour a period sends to the camera."""
    cx, cy = unit(camera, x, y)
    lx, ly = unit(flash, x, y)
    return np.abs(-(cx + lx) * y + (cy + ly) * x) / np.maximum(np.hypot(x, y), 1e-9)


@lru_cache(maxsize=1)
def spectral_data():
    with np.load(Path(__file__).with_name("simulate_lut.npz")) as z:
        return ((z["single"] / 255.) ** 2 - .02, z["groove"], z["band_edges"], z["band_bytes"])


def material_response(material, dt, single):
    """Existing byte spectra; unknown recipe spectra use a documented period warp.

    This is not a measured multi-byte spectrum. Keep the approximation in the
    core so CLI, swatches and document previews make exactly the same prediction.
    """
    spec = material["spec"]
    if len(spec) == 2:
        return single[texture(spec), np.clip(np.rint(dt/.005).astype(int), 0, 260)]
    period = material.get("period_um") or material.get("periods_um", [None])[0]
    if not period or not math.isfinite(period) or period <= 0:
        raise ValueError("multi-byte simulation requires a positive material period")
    index = np.clip(np.rint(dt*period/.8528123052898693/.005).astype(int), 0, 260)
    return single[0xA5, index]


def linear_samples(response, across, groove):
    return (response + GROOVE_GAIN * groove[across] + .05 * .177) * 4


def encode_photo(rgb):
    """One shared phone saturation, clipping and sRGB mapping for every consumer."""
    grey = rgb @ np.array([.2126, .7152, .0722])
    rgb = np.clip(grey[..., None] + PHOTO_SATURATION * (rgb - grey[..., None]), 0, 1)
    rgb = np.where(rgb <= .0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - .055)
    return np.uint8(np.clip(rgb * 255, 0, 255))


def material_swatches(materials, camera=CAMERA, flash=FLASH):
    """Tiny 0.06 mm samples around r=40 mm, averaged in linear light, as render()."""
    single, groove, _, _ = spectral_data()
    offsets=np.array([-.06, 0., .06])
    x,y=np.meshgrid(40+offsets,offsets)
    dt=along_track(x,y,camera,flash)
    cx,cy=unit(camera,x,y);lx,ly=unit(flash,x,y)
    across=np.clip(np.rint(np.abs((cx+lx)*x+(cy+ly)*y)/np.hypot(x,y)/.005).astype(int),0,260)
    result={}
    for m in materials:
        linear=linear_samples(material_response(m,dt,single),across,groove).mean((0,1))
        rgb=encode_photo(linear).tolist()
        import colorsys
        hue=colorsys.rgb_to_hsv(*(v/255 for v in rgb))[0]*360
        # Palette grouping only; do not suppress faint orders or groove light in render().
        result[m['id']]=dict(rgb=rgb,hue=hue,dark=max(rgb)<85 or max(rgb)-min(rgb)<12)
    return result


def render(design, size=800, dark="A5", light="B9", camera=CAMERA, flash=FLASH, rotate=0, *, materials=None, fine=True):
    """Return a model prediction as a Pillow image, with no perspective. It is worked out about every 0.06 mm and
    averaged in linear light to the output size, so fine lines and dither mix as they do in a photo, and its colour
    is muted toward what a phone camera records (PHOTO_SATURATION)."""
    if size < 200 or size > 4096:
        raise ValueError("size must be between 200 and 4096 pixels")
    cam, fl = np.asarray(camera, float), np.asarray(flash, float)
    if cam.shape != (3,) or fl.shape != (3,) or not np.isfinite(cam).all() or not np.isfinite(fl).all() or cam[2] <= 0 or fl[2] <= 0:
        raise ValueError("camera and flash must have finite coordinates and positive height")
    if not math.isfinite(rotate):
        raise ValueError("rotation must be finite")
    single, groove, edges, pairs = spectral_data()
    k = max(1, math.ceil(FINE_SAMPLES / size)) if fine else 1
    labels, x, y, dx, dy = sampled(design, size * k, rotate)
    r = np.hypot(x, y)
    cx, cy = unit(cam, x, y)
    lx, ly = unit(fl, x, y)
    dt = along_track(x, y, cam, fl)
    dr = np.abs((cx + lx) * x + (cy + ly) * y) / np.maximum(r, 1e-9)
    index = np.clip(np.rint(dt / .005).astype(int), 0, 260)
    across = np.clip(np.rint(dr / .005).astype(int), 0, 260)
    # The grooves' own rainbow. It leaves out the along-track part of the view, so its place is only roughly right.
    if materials is not None:
        if design.dtype != np.uint8 or not materials or int(labels.max()) >= len(materials):
            raise ValueError("material labels must index the document's material table")
        response=np.zeros((*dt.shape,3))
        for slot in np.unique(labels):
            hit=labels==slot
            response[hit]=material_response(materials[slot],dt[hit],single)
        rgb=linear_samples(response,across,groove)
    elif light.lower() == BANDS:
        # Which byte went where is fixed by the pose the disc was designed for, wherever the disc is now.
        zone = np.clip(np.searchsorted(edges, along_track(dx, dy, CAMERA, FLASH)) - 1, 0, len(pairs) - 1)
        bright = single[pairs[zone], index[..., None]].mean(axis=-2)
    else:
        bright = single[texture(light), index]
    if materials is None:
        plain = single[texture(dark), index]
        rgb = linear_samples(np.where(labels[..., None], plain, bright), across, groove)
    rgb[(r < HUB_MM) | (r >= EDGE_MM)] = 0
    rgb = rgb.reshape(size, k, size, k, 3).mean((1, 3))    # box filter, in linear light
    return Image.fromarray(encode_photo(rgb))


def ideal(design, size):
    d, x, y, _, _ = sampled(design, size)
    r = np.hypot(x, y)
    v = np.where(d, 24, 230).astype(np.uint8)
    v[(r >= 7.5) & ((r < 24.5) | (r > 56))] = 102
    v[(r < 7.5) | (r >= 60)] = 0
    return Image.fromarray(v).convert("RGB")


def sheet(design, picture, size, dark, light, camera, flash):
    canvas = Image.new("RGB", (3 * size, 4 * size + 24), (24, 24, 24))
    if picture:
        with Image.open(picture) as im:
            first = ImageOps.contain(im.convert("RGB"), (size, size - 16))
        tile = Image.new("RGB", (size, size), (24, 24, 24))
        tile.paste(first, ((size - first.width) // 2, 16 + (size - 16 - first.height) // 2))
    else:
        tile = Image.new("RGB", (size, size), (50, 50, 50))
        ImageDraw.Draw(tile).text((6, size // 2), "No original picture", fill="white")
    tiles = [("Original", tile), ("Ideal design", ideal(design, size))]
    for angle in range(0, 360, 36):
        tiles.append((f"{angle} deg", render(design, size, dark, light, camera, flash, angle)))
    for k, (label, tile) in enumerate(tiles):
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 0, min(size - 1, len(label) * 7 + 8), 15), fill=(20, 20, 20))
        draw.text((4, 2), label, fill="white")
        canvas.paste(tile, ((k % 3) * size, (k // 3) * size))
    pose = f"Model prediction, not a photo. Camera {tuple(camera)} mm; flash {tuple(flash)} mm"
    width = int(ImageDraw.Draw(canvas).textlength(pose)) + 8
    footer = Image.new("RGB", (width, 20), (24, 24, 24))
    ImageDraw.Draw(footer).text((4, 3), pose, fill="white")
    if width > canvas.width:
        footer = footer.resize((canvas.width, 20))
    canvas.paste(footer, (0, 4 * size + 2))
    return canvas
