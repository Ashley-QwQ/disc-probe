"""CPU prediction of a two-texture DVD, in data-side view."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

CAMERA = (0., 70., 330.)
FLASH = (-43.66, 89.79, 330.)
HUB_MM, EDGE_MM = 24.6, 57.6
GROOVE_GAIN = .15
BANDS = "bands"     # as --light: bright bytes chosen by viewing angle from a measured chart, as on the figures disc


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
    ix = np.clip(np.floor((dx + 60) / .02).astype(int), 0, 5999)
    iy = np.clip(np.floor((60 - dy) / .02).astype(int), 0, 5999)
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


def render(design, size=800, dark="A5", light="B9", camera=CAMERA, flash=FLASH, rotate=0):
    """Return a model prediction as a Pillow image, with no perspective or camera tone curve."""
    if size < 200 or size > 4096:
        raise ValueError("size must be between 200 and 4096 pixels")
    cam, fl = np.asarray(camera, float), np.asarray(flash, float)
    if cam.shape != (3,) or fl.shape != (3,) or not np.isfinite(cam).all() or not np.isfinite(fl).all() or cam[2] <= 0 or fl[2] <= 0:
        raise ValueError("camera and flash must have finite coordinates and positive height")
    if not math.isfinite(rotate):
        raise ValueError("rotation must be finite")
    with np.load(Path(__file__).with_name("simulate_lut.npz")) as z:
        single = (z["single"] / 255.) ** 2 - .02     # stored as a square root in 8 bits
        groove, edges, pairs = z["groove"], z["band_edges"], z["band_bytes"]
    labels, x, y, dx, dy = sampled(design, size, rotate)
    r = np.hypot(x, y)
    cx, cy = unit(cam, x, y)
    lx, ly = unit(fl, x, y)
    dt = along_track(x, y, cam, fl)
    dr = np.abs((cx + lx) * x + (cy + ly) * y) / np.maximum(r, 1e-9)
    index = np.clip(np.rint(dt / .005).astype(int), 0, 260)
    across = np.clip(np.rint(dr / .005).astype(int), 0, 260)
    # The grooves' own rainbow. It leaves out the along-track part of the view, so its place is only roughly right.
    if light.lower() == BANDS:
        # Which byte went where is fixed by the pose the disc was designed for, wherever the disc is now.
        zone = np.clip(np.searchsorted(edges, along_track(dx, dy, CAMERA, FLASH)) - 1, 0, len(pairs) - 1)
        bright = single[pairs[zone], index[..., None]].mean(axis=-2)
    else:
        bright = single[texture(light), index]
    plain = single[texture(dark), index]
    rgb = (np.where(labels[..., None], plain, bright) + GROOVE_GAIN * groove[across] + .05 * .177) * 4
    rgb = np.clip(rgb, 0, 1)
    rgb = np.where(rgb <= .0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - .055)
    rgb[(r < HUB_MM) | (r >= EDGE_MM)] = 0
    return Image.fromarray(np.uint8(np.clip(rgb * 255, 0, 255)))


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
