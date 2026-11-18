"""Pose-dependent DVD colour matching using the texture library's LED XYZ table."""
from functools import lru_cache
import base64
import json
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import simulate, simulate_a3, texlib

GREEDY_SET = Path('D:/disc-probe-scratch/gamut/greedy_set.json')
DEFAULT_TEXLIB = Path('F:/dp-archive/texlib/latest')
RIG_DATA = Path(__file__).parent / 'web/home/design/pose-swatches.json'
WHITE = np.array([.95047, 1, 1.08883], dtype=np.float32)
SRGB_XYZ = np.array([[.4124564, .3575761, .1804375], [.2126729, .7151522, .0721750],
                     [.0193339, .1191920, .9503041]], dtype=np.float32)
_bayer = np.array([[0, 2], [3, 1]])
for _ in range(2):
    _bayer = np.block([[4*_bayer, 4*_bayer+2], [4*_bayer+3, 4*_bayer+1]])
BAYER = (_bayer + .5) / 64


@lru_cache(maxsize=1)
def rig_data():
    return json.loads(RIG_DATA.read_text(encoding='utf-8'))


def rig_pose(rig):
    data = rig_data()
    error = 'colour picture needs a phone and shooting height in scene.rig'
    if not isinstance(rig, dict):
        raise ValueError(error)
    phone = rig.get('phone')
    if phone == 'custom':
        mm = rig.get('flash_mm')
        distance = math.floor(mm + .5) if type(mm) in (int, float) and math.isfinite(mm) else None
        if distance not in data['custom']['flash_mm']:
            raise ValueError('custom phone needs a flash-to-lens distance of 10–60 mm')
    else:
        distance = next((p['flash_mm'] for p in data['phones'] if p['id'] == phone), None)
    height = next((h for h in data['heights'] if h['id'] == rig.get('height')), None)
    cm = rig.get('height_cm')
    sheet = data['rig']['disc_and_sheet_mm']
    if height is not None:
        z = height['camera_z_mm']
    elif type(cm) in (int, float) and math.isfinite(cm) and sheet < cm * 10 <= 100000:
        z = cm * 10 - sheet
    else:
        raise ValueError(error)
    if distance is None:
        raise ValueError(error)
    y = data['rig']['lens_offset_mm']
    return dict(camera=(0, y, z), flash=(0, y + distance, z))


def work_rig(document):
    scene = document.get('scene')
    return rig_pose(scene.get('rig') if isinstance(scene, dict) else None)


def xyz_lab(xyz, white=WHITE):
    v = xyz / white
    f = np.where(v > (6/29)**3, np.cbrt(v), v / (3*(6/29)**2) + 4/29)
    x, y, z = np.moveaxis(f, -1, 0)
    return np.stack((116*y-16, 500*(x-y), 200*(y-z)), axis=-1)


_srgb = np.arange(256, dtype=np.float32) / 255
LINEAR = np.where(_srgb <= .04045, _srgb / 12.92, ((_srgb + .055) / 1.055)**2.4)


def picture_lab(rgb):
    return xyz_lab(LINEAR[rgb] @ SRGB_XYZ.T)


class Matcher:
    def __init__(self, materials, slots, dither, table):
        self.slots = np.asarray(slots)
        self.dither = dither
        specs = [simulate_a3.canonical(materials[i]['spec']) for i in slots]
        missing = [spec for spec in specs if spec not in table['specs']]
        if missing:
            raise ValueError(f'colour texture {missing[0]} is missing from the active colour table; select --texlib DIR')
        self.delta = table['delta']
        ref = simulate_a3.reference_y(table)
        if not np.isfinite(ref) or ref <= 0:
            raise ValueError('the active colour table needs a positive A5/B9 reference brightness')
        # Normalize the XYZ curves first. Interpolate XYZ, then convert to Lab.
        self.curves = (table['xyz'][[table['specs'][s] for s in specs]] / (ref * WHITE)).transpose(1, 0, 2).astype(np.float32)

    def row(self, dt, target, j, columns):
        grid = self.delta
        hi = np.clip(np.searchsorted(grid, dt, side='right'), 1, len(grid)-1)
        weight = ((dt - grid[hi-1]) / (grid[hi] - grid[hi-1])).astype(np.float32)
        valid = (dt >= grid[0]) & (dt <= grid[-1])
        a, b = self.curves[hi-1], self.curves[hi]
        a += (b-a) * weight[:, None, None]
        a[~valid] = 0
        differences = xyz_lab(a, 1) - target[:, None, :]
        errors = np.einsum('ijk,ijk->ij', differences, differences)
        first = errors.argmin(axis=1)
        if self.dither == 'nearest' or len(self.slots) == 1:
            return self.slots[first]
        indices = np.arange(len(dt))
        d0 = np.sqrt(errors[indices, first])
        errors[indices, first] = np.inf
        second = errors.argmin(axis=1)
        total = d0 + np.sqrt(errors[indices, second])
        weight = np.divide(d0, total, out=np.zeros_like(d0), where=total > 0)
        return self.slots[np.where(weight > BAYER[j % 8, columns % 8], second, first)]


def material_set(source, table):
    if source == 'greedy':
        path = texlib.safe(os.environ.get('DISCPROBE_COLOUR_MATERIALS') or GREEDY_SET)
    else:
        path = texlib.safe(source)
    try:
        loaded = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError as exc:
        raise ValueError(f'colour materials file not found: {path}; use --materials JSON or DISCPROBE_COLOUR_MATERIALS') from exc
    specs = loaded.get('greedy_specs') if isinstance(loaded, dict) else loaded
    if not isinstance(specs, list) or not 1 <= len(specs) <= 254 or any(not isinstance(s, str) for s in specs):
        raise ValueError('colour materials JSON needs 1–254 texture specs (a list or greedy_specs)')
    specs = list(dict.fromkeys(texlib.canonical(s) for s in specs))
    for spec in specs:
        if spec not in table['specs']:
            raise ValueError(f'colour texture {spec} is missing from the active colour table; select --texlib DIR')
    return [dict(id=f'tex:{s}', spec=s) for s in specs]


def palette(source='greedy'):
    table = simulate_a3.tables()
    lib = texlib.library()
    if lib is None:
        raise ValueError('a texture library is required for colour pictures; select --texlib DIR')
    # Older colour tables have no calibration marker. A replacement can declare it in the NPZ.
    fitted = table.get('fitted', False)
    return dict(materials=material_set(source, table),
                table=dict(signature=table['signature'], fitted=fitted))


def design(image, phone, height, materials='greedy', dither='ordered', fit='disc', flash_mm=None):
    """Create a portable editor document. Its source texture specs are pinned by ID."""
    from . import editor_ops

    h = next((h for h in rig_data()['heights'] if math.isclose(h['ruler_cm'], height, abs_tol=.005)), None)
    rig = dict(phone=phone, **(dict(height=h['id']) if h else dict(height_cm=height)))
    if flash_mm is not None:
        rig['flash_mm'] = flash_mm
    pose = rig_pose(rig)
    cam, flash = pose['camera'], pose['flash']
    choices = palette(materials)
    image = texlib.safe(image)
    with Image.open(image) as original:
        picture = ImageOps.exif_transpose(original).convert('RGBA')
        picture.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
    w, h = picture.size
    # Disc fills the outer diameter on both axes. Ring fits the complete picture between hub and rim.
    inner, outer = editor_ops.grid()['annulus_mm']
    aspect = w / h
    if fit == 'disc':
        width, y = 2 * outer * max(1, aspect), 0
        width = min(width, 240, 240 * aspect)
    else:
        # Solve for the largest centered rectangle in the top band, with bottom edge tangent to the hub.
        k = 1 + aspect**2 / 4
        hh = (outer**2-inner**2) / (math.sqrt(inner**2 + k*(outer**2-inner**2)) + inner)
        width, y = hh * aspect, -inner - hh / 2
    layer = dict(id=1, kind='image', name=image.stem, x=0, y=y, width=width,
                 w=w, h=h, raster=dict(width=w, height=h, rgba=base64.b64encode(picture.tobytes()).decode('ascii')))
    doc = editor_ops.migrate(dict(media='dvd', layers=[layer], lookY=cam[1], scene=dict(rig=rig, preset='rig',
        cam=[cam[0], -cam[1], cam[2]], follows=True, flashOffset=[flash[0]-cam[0], flash[1]-cam[1]])))
    doc['materials'].extend(choices['materials'])
    doc['assignments'].append(dict(layer=1, colour=dict(materials=[m['id'] for m in choices['materials']],
                                                       dither=dither, table=choices['table'])))
    return doc
