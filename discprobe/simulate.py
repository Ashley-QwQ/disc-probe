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
TEXTURE_COLOUR_MODEL = 'discprobe.simulate-v0.1.2.1'
TEXTURE_COLOUR_VERSION = '1.0.0'


@lru_cache(maxsize=1)
def _tables():
    with np.load(Path(__file__).with_name('simulate_lut.npz'), allow_pickle=False) as z:
        return ((z['single']/255.)**2-.02, z['groove'], z['band_edges'], z['band_bytes'])


@lru_cache(maxsize=1)
def _extra_tables():
    path = Path(__file__).with_name('simulate_texture_lut.npz')
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as z:
        return {str(spec): (row/255.)**2-.02 for spec,row in zip(z['specs'], z['rgb'])}


def _normal_spec(spec):
    if not isinstance(spec, str):
        raise ValueError('periods alone do not identify a texture spectrum; pass a hex spec or weighted components')
    try:
        seq = bytes.fromhex(spec)
    except ValueError:
        raise ValueError('texture spec must contain hex bytes') from None
    if not 1 <= len(seq) <= 256:
        raise ValueError('texture spec must contain 1..256 bytes')
    return seq.hex().upper()


def _texture_table(spec):
    if isinstance(spec, dict):
        if set(spec) == {'spec'}:
            return _texture_table(spec['spec'])
        if set(spec) != {'components'} or not isinstance(spec['components'], list) or not 1 <= len(spec['components']) <= 32:
            raise ValueError('mixture needs 1..32 weighted components')
        rows, weights = [], []
        for row in spec['components']:
            if not isinstance(row, dict) or set(row) != {'spec','weight'}:
                raise ValueError('each component needs spec and weight')
            weight = row['weight']
            if isinstance(weight, bool) or not isinstance(weight, (int,float)) or not math.isfinite(weight) or weight < 0:
                raise ValueError('component weights must be finite and nonnegative')
            rows.append(_texture_table(_normal_spec(row['spec'])))
            weights.append(weight)
        if not math.isclose(sum(weights), 1., abs_tol=1e-12):
            raise ValueError('component weights must sum to 1')
        return sum(row*weight for row,weight in zip(rows,weights))
    spec = _normal_spec(spec)
    if len(spec) == 2:
        return _tables()[0][int(spec,16)]
    extra = _extra_tables()
    if spec in extra:
        return extra[spec]
    from .simulate_spectrum import texture_table
    return (texture_table(spec)/255.)**2-.02


def _linear_response(texture_rgb, across, radius):
    # Keep the operation order of release render(), including the approximate groove/room terms.
    rgb = (texture_rgb + GROOVE_GAIN * _tables()[1][across] + .05*.177)*4
    rgb = np.array(rgb, copy=True)
    rgb[(radius < HUB_MM) | (radius >= EDGE_MM)] = 0
    return rgb


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
    single, groove, edges, pairs = _tables()
    k = max(1, math.ceil(FINE_SAMPLES / size))
    labels, x, y, dx, dy = sampled(design, size * k, rotate)
    r = np.hypot(x, y)
    cx, cy = unit(cam, x, y)
    lx, ly = unit(fl, x, y)
    dt = along_track(x, y, cam, fl)
    dr = np.abs((cx + lx) * x + (cy + ly) * y) / np.maximum(r, 1e-9)
    index = np.clip(np.rint(dt / .005).astype(int), 0, 260)
    across = np.clip(np.rint(dr / .005).astype(int), 0, 260)
    # The grooves' own rainbow. It leaves out the along-track part of the view, so its place is only roughly right.
    if isinstance(light, str) and light.lower() == BANDS:
        # Which byte went where is fixed by the pose the disc was designed for, wherever the disc is now.
        zone = np.clip(np.searchsorted(edges, along_track(dx, dy, CAMERA, FLASH)) - 1, 0, len(pairs) - 1)
        bright = single[pairs[zone], index[..., None]].mean(axis=-2)
    else:
        bright = _texture_table(light)[index]
    plain = _texture_table(dark)[index]
    rgb = _linear_response(np.where(labels[..., None], plain, bright), across, r)
    rgb = rgb.reshape(size, k, size, k, 3).mean((1, 3))    # box filter, in linear light
    return Image.fromarray(preview_rgb(rgb))


def preview_rgb(rgb):
    """Existing release tone response, shared by render() and texture_colour()."""
    grey = rgb @ np.array([.2126, .7152, .0722])
    rgb = np.clip(grey[..., None] + PHOTO_SATURATION * (rgb - grey[..., None]), 0, 1)
    rgb = np.where(rgb <= .0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - .055)
    return np.uint8(np.clip(rgb * 255, 0, 255))


def texture_colour(spec_or_periods, delta, *, pose=None, media='dvd'):
    """Return a uniform texture patch's mean display sRGB (three Python ints).

    Hex spec or {'components': [{'spec': 'A5', 'weight': .5}, ...]} selects the
    same full recording spectrum as render(). Periods without a byte spec/power
    spectrum are insufficient and rejected. CD/BD colour models are unavailable.

    Local field: delta is a finite scalar/array in 0..2; pose may contain
    radial_delta (default 0) and radius_mm (default 40), broadcast to delta.
    All supplied samples form ONE output pixel and are averaged in LINEAR light.
    Values above the LUT's 1.3 limit clamp to its last bin, exactly as render().

    Physical patch: pose={'camera': [x,y,z], 'flash': [x,y,z], 'size': 800,
    'patch': [x0,y0,x1,y1]} uses render() pixel coordinates (exclusive end, y down).
    Camera/light positions use y UP, in mm. Defaults are CAMERA/FLASH/800 and the
    one pixel nearest (40,0) mm. Delta checks the patch-centre tangent difference
    to within .005; the fine sample deltas/radial components come from the pose.
    This path uses the SAME ~.06 mm grid, linear box filtering, muting and sRGB
    encoding as render(), then rounds the patch's mean encoded RGB to 0..255.
    """
    if media != 'dvd':
        raise ValueError('texture_colour currently has a DVD model only')
    if pose is not None and not isinstance(pose, dict):
        raise ValueError('pose must be an object')
    p = pose or {}
    dt = np.asarray(delta, dtype=float)
    if not dt.size or not np.isfinite(dt).all() or np.any(dt < 0) or np.any(dt > 2):
        raise ValueError('delta must be finite and in 0..2')
    table = _texture_table(spec_or_periods)
    physical = bool(set(p) & {'camera','flash','size','patch'})
    if physical:
        if set(p) - {'camera','flash','size','patch'}:
            raise ValueError('physical pose accepts camera, flash, size and patch')
        size = p.get('size',800)
        if type(size) is not int or not 200 <= size <= 4096:
            raise ValueError('size must be an integer in 200..4096')
        cam, fl = np.asarray(p.get('camera',CAMERA),float), np.asarray(p.get('flash',FLASH),float)
        if any(v.shape != (3,) or not np.isfinite(v).all() or v[2] <= 0 for v in (cam,fl)):
            raise ValueError('camera and flash need finite coordinates and positive height')
        patch = p.get('patch',[int(size*5/6),size//2,int(size*5/6)+1,size//2+1])
        if not isinstance(patch,(list,tuple)) or len(patch)!=4 or any(type(v) is not int for v in patch):
            raise ValueError('patch needs four integer pixel bounds')
        x0,y0,x1,y1 = patch
        if not (0 <= x0 < x1 <= size and 0 <= y0 < y1 <= size):
            raise ValueError('patch must stay inside the render')
        centre_delta = along_track((x0+x1)/2*120/size-60,60-(y0+y1)/2*120/size,cam,fl)
        if dt.ndim or abs(float(dt)-float(centre_delta)) > .005:
            raise ValueError('delta does not match the physical patch centre')
        k = max(1, math.ceil(FINE_SAMPLES/size))
        x,y = np.meshgrid((np.arange(x0*k,x1*k)+.5)*120/(size*k)-60,
                          60-(np.arange(y0*k,y1*k)+.5)*120/(size*k))
        radius = np.hypot(x,y)
        dt = along_track(x,y,cam,fl)
        cx,cy = unit(cam,x,y); lx,ly = unit(fl,x,y)
        dr = np.abs((cx+lx)*x+(cy+ly)*y)/np.maximum(radius,1e-9)
    else:
        if set(p) - {'radial_delta','radius_mm'}:
            raise ValueError('local pose accepts radial_delta and radius_mm')
        dt,dr,radius = np.broadcast_arrays(dt,np.asarray(p.get('radial_delta',0),float),
                                          np.asarray(p.get('radius_mm',40),float))
        if not np.isfinite(dr).all() or np.any(dr < 0) or np.any(dr > 2) or not np.isfinite(radius).all() or np.any(radius < 0):
            raise ValueError('invalid radial delta or radius')
    index = np.clip(np.rint(dt/.005).astype(int),0,260)
    across = np.clip(np.rint(dr/.005).astype(int),0,260)
    linear = _linear_response(table[index],across,radius)
    if physical:
        linear = linear.reshape(y1-y0,k,x1-x0,k,3).mean((1,3))
        rgb = preview_rgb(linear).mean((0,1))
    else:
        rgb = preview_rgb(linear.reshape(-1,3).mean(0))
    return tuple(int(v) for v in np.rint(rgb))


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
