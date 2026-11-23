"""Pose-dependent DVD colour matching using the packaged fitted LED XYZ table."""
from functools import lru_cache
import base64
import json
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image

from . import simulate, simulate_a3, texlib

ASSETS = Path(__file__).with_name('colour_print')
DEFAULT_TABLE = ASSETS / 'table.npz'
DEFAULT_MATERIALS = ASSETS / 'materials.json'
RIG_DATA = Path(__file__).parent / 'web/home/design/pose-swatches.json'
DIRECTION_ARROW = RIG_DATA.with_name('direction-arrow.json')
WHITE = np.array([.95047, 1, 1.08883], dtype=np.float32)
SRGB_XYZ = np.array([[.4124564, .3575761, .1804375], [.2126729, .7151522, .0721750],
                     [.0193339, .1191920, .9503041]], dtype=np.float32)
SRGB_LIGHTNESS = 100.
SRGB_CHROMA = 134.  # D65 Lab chroma of the most saturated sRGB cube corner, rounded up.
CHROMA_PRIORITY = .55
VIVID_LUMA_COST = 9000.  # Squared Lab error paid per reference Y below the brightest candidate.
VIVID_SHADOW_LIGHTNESS = 20.  # Fade the brightness preference to zero at source black.
EDGE_RADIUS_MM = .42  # Wide standard deviation; the narrow side of the difference uses one third.
EDGE_LIGHTNESS = 8.   # Maximum correction in source Lab L* before mapping to the local range.
EDGE_GAIN = 2.
EDGE_MAX_SOURCE_SIGMA = 24.  # Bound work for a large bitmap scaled down to a tiny spot on the disc.
EDGE_LEVELS = 5
SOURCE_COLOURS = 256
COST_SIGMA_DELTA = .0125
BLEND_SIGMA_DELTA = .010
SWITCH_COST = 1200.   # Squared distance paid once per material change along the delta table.
BLEND_MATERIALS = 4
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
    def __init__(self, materials, slots, dither, table, *, relative=True):
        self.slots = np.asarray(slots)
        self.dither = dither
        self.relative = relative
        specs = [simulate_a3.canonical(materials[i]['spec']) for i in slots]
        missing = [spec for spec in specs if spec not in table['specs']]
        if missing:
            raise ValueError(f'colour texture {missing[0]} is missing from the active colour table; select --table FILE')
        self.delta = table['delta']
        ref = simulate_a3.reference_y(table)
        if not np.isfinite(ref) or ref <= 0:
            raise ValueError('the active colour table needs a positive A5/B9 reference brightness')
        # Normalize the XYZ curves first. Interpolate XYZ, then convert to Lab.
        curves = table['xyz'][[table['specs'][s] for s in specs]] / (ref * WHITE)
        self.curves = np.ascontiguousarray(curves.transpose(1, 0, 2), dtype=np.float32)

    def row(self, dt, target, j, columns):
        grid = self.delta
        valid = (dt >= grid[0]) & (dt <= grid[-1])
        if self.relative and not valid.all():
            # Outside the table every curve is zero. Resolve the identical candidates in input order.
            labels = np.full(len(dt), self.slots[0], dtype=self.slots.dtype)
            if valid.any():
                labels[valid] = self.row(dt[valid], target[valid], j, columns[valid])
            return labels
        hi = np.clip(np.searchsorted(grid, dt, side='right'), 1, len(grid)-1)
        weight = ((dt - grid[hi-1]) / (grid[hi] - grid[hi-1])).astype(np.float32)
        a, b = self.curves[hi-1], self.curves[hi]
        a += (b-a) * weight[:, None, None]
        if not self.relative:
            a[~valid] = 0
        differences = xyz_lab(a, 1)
        if self.relative:
            light = differences[:, :, 0]
            low, high = light.min(axis=1), light.max(axis=1)
            chroma = np.sqrt(np.einsum('ijk,ijk->ij', differences[:, :, 1:], differences[:, :, 1:]).max(axis=1))
            target = target.copy()
            target[:, 0] = low + (high-low)*np.clip(target[:, 0]/SRGB_LIGHTNESS, 0, 1)
            target[:, 1:] *= np.minimum(chroma/SRGB_CHROMA, 1)[:, None]
        differences -= target[:, None, :]
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


def picture_codes(rgba, width_mm, height_mm):
    """Bound the source palette, retaining exact flat colours when they fit, and prepare a signed edge band."""
    from scipy.ndimage import gaussian_filter

    alpha = rgba[..., 3].astype(np.float32) / 255
    rgb = np.where(alpha[..., None] > 0, rgba[..., :3], np.uint8(0))
    picture = Image.fromarray(rgb).quantize(SOURCE_COLOURS, dither=Image.Dither.NONE)
    codes = np.array(picture, dtype=np.uint16)
    palette = picture_lab(np.array(picture.getpalette(), dtype=np.uint8).reshape(-1, 3))
    if not EDGE_LIGHTNESS:
        return codes + SOURCE_COLOURS * (EDGE_LEVELS // 2), palette

    sigma = (min(EDGE_MAX_SOURCE_SIGMA, EDGE_RADIUS_MM * codes.shape[0] / height_mm),
             min(EDGE_MAX_SOURCE_SIGMA, EDGE_RADIUS_MM * codes.shape[1] / width_mm))
    light = palette[codes, 0] * alpha
    opaque = (alpha == 1).all()

    def mean(scale):
        s = tuple(v*scale for v in sigma)
        result = gaussian_filter(light, s, mode='nearest')
        if not opaque:
            weight = gaussian_filter(alpha, s, mode='nearest')
            np.divide(result, np.maximum(weight, 1e-5), out=result)
        return result

    # Opposite signs on the two sides of a step, falling back to zero inside a flat region.
    edge = np.clip(EDGE_GAIN * (mean(1/3) - mean(1)) / EDGE_LIGHTNESS, -1, 1)
    middle = EDGE_LEVELS // 2
    level = np.rint(middle * edge + middle).astype(np.uint16)
    return codes + SOURCE_COLOURS * level, palette


def stable_path(cost):
    """Minimum-cost sequence along δ, with a fixed charge each time the dominant material changes."""
    batch, nodes, states = cost.shape
    score = cost[:, 0].copy()
    prior = np.empty((batch, nodes, states), dtype=np.uint8)
    rows, columns = np.arange(batch), np.arange(states)
    for node in range(1, nodes):
        best = score.argmin(axis=1)
        other = score[rows, best, None] + SWITCH_COST
        prior[:, node] = np.where(other < score, best[:, None], columns)
        score = cost[:, node] + np.minimum(score, other)
        score -= score.min(axis=1, keepdims=True)
    path = np.empty((batch, nodes), dtype=np.uint8)
    path[:, -1] = score.argmin(axis=1)
    for node in range(nodes-1, 0, -1):
        path[:, node-1] = prior[rows, node, path[:, node]]
    return path


class AngleMatcher(Matcher):
    """Prepare the angular trajectory once per source colour and edge level, then look it up by row."""
    def __init__(self, materials, slots, dither, table, rgba, width_mm, height_mm, *, vivid=False):
        from scipy.ndimage import gaussian_filter1d

        super().__init__(materials, slots, dither, table)
        self.codes, source = picture_codes(rgba, width_mm, height_mm)
        # Use a uniform grid for smoothing, including when a caller provides a non-uniform override.
        self.nodes = np.linspace(self.delta[0], self.delta[-1], len(self.delta))
        self.step = float(self.nodes[1]-self.nodes[0])
        hi = np.clip(np.searchsorted(self.delta,self.nodes,side='right'),1,len(self.delta)-1)
        weight = ((self.nodes-self.delta[hi-1])/(self.delta[hi]-self.delta[hi-1])).astype(np.float32)
        xyz = self.curves[hi-1] + (self.curves[hi]-self.curves[hi-1])*weight[:, None, None]
        lab = xyz_lab(xyz, 1)
        low = lab[..., 0].min(axis=1)
        span = lab[..., 0].max(axis=1) - low
        chroma = np.sqrt(np.square(lab[..., 1:]).sum(axis=2).max(axis=1))
        squeeze = CHROMA_PRIORITY * (1-np.clip(span/SRGB_LIGHTNESS, 0, 1))
        chroma_scale = np.minimum(chroma/SRGB_CHROMA*(1+.35*squeeze), 1)
        if vivid:
            y = xyz[..., 1]
            light_shortfall = VIVID_LUMA_COST * (y.max(axis=1, keepdims=True) - y)
        luma_weight = 1-.65*squeeze
        codes = np.unique(self.codes)
        count = min(BLEND_MATERIALS,len(slots)) if dither=='ordered' else 1
        self.choices = np.zeros((int(codes[-1])+1,len(self.nodes),count), dtype=np.uint8)
        self.cdf = np.zeros(self.choices.shape, dtype=np.float32)
        middle = EDGE_LEVELS // 2

        # Keep temporary cost tensors bounded even for a full-colour photograph.
        for start in range(0, len(codes), 32):
            keys = codes[start:start+32]
            goal = source[keys % SOURCE_COLOURS].copy()
            goal[:,0] += EDGE_LIGHTNESS * ((keys // SOURCE_COLOURS).astype(np.float32)-middle)/middle
            target = np.repeat(goal[:,None,:],len(self.nodes),axis=1)
            target[...,0] = low + span*np.clip(target[...,0]/SRGB_LIGHTNESS,0,1)
            if vivid:
                source_chroma = np.linalg.norm(goal[:, 1:], axis=1)
                limit = np.minimum(1, chroma[None, :] / np.maximum(source_chroma[:, None], 1e-9))
                target[..., 1:] *= limit[..., None]
            else:
                target[...,1:] *= chroma_scale[None,:,None]
            difference = lab[None,:,:,:] - target[:,:,None,:]
            difference[...,0] *= luma_weight[None,:,None]
            raw = np.einsum('bdki,bdki->bdk',difference,difference)
            if vivid:
                preference = np.clip(source[keys % SOURCE_COLOURS, 0] / VIVID_SHADOW_LIGHTNESS, 0, 1)
                raw += preference[:, None, None] * light_shortfall[None, :, :]
            cost = gaussian_filter1d(raw,COST_SIGMA_DELTA/self.step,axis=1,mode='nearest') if COST_SIGMA_DELTA else raw.copy()
            first = stable_path(cost) if SWITCH_COST else cost.argmin(axis=2)
            if count == 1:
                self.choices[keys,:,0] = self.slots[first]
                continue

            batch, node = np.arange(len(keys))[:,None], np.arange(len(self.nodes))
            cost[batch,node,first] = np.inf
            second = cost.argmin(axis=2)
            a, b = np.sqrt(raw[batch,node,first]), np.sqrt(raw[batch,node,second])
            mix = np.divide(a,a+b,out=np.zeros_like(a),where=a+b>0)
            if SWITCH_COST:
                mix = np.minimum(mix,.5)   # Keep the chosen trajectory dominant.
            shares = np.zeros_like(raw)
            shares[batch,node,first] = 1-mix
            shares[batch,node,second] = mix
            if BLEND_SIGMA_DELTA:
                shares = gaussian_filter1d(shares,BLEND_SIGMA_DELTA/self.step,axis=1,mode='nearest')
            best = np.argpartition(shares,-count,axis=2)[:,:,-count:]
            best.sort(axis=2)  # Steady slot order keeps the Bayer phase when the ranks cross.
            weights = np.take_along_axis(shares,best,axis=2)
            total = weights.sum(axis=2,keepdims=True)
            self.choices[keys] = self.slots[best]
            self.cdf[keys] = np.cumsum(weights,axis=2)/total

    def row(self, dt, source_codes, j, columns):
        valid = (dt >= self.delta[0]) & (dt <= self.delta[-1])
        result = np.full(len(dt), -1, dtype=int)
        node = np.rint((dt[valid]-self.nodes[0])/self.step).astype(int).clip(0,len(self.nodes)-1)
        codes = source_codes[valid]
        if self.choices.shape[2] == 1:
            result[valid] = self.choices[codes,node,0]
        else:
            phase = BAYER[j%8,columns[valid]%8]
            which = (phase[:,None] >= self.cdf[codes,node,:-1]).sum(axis=1)
            result[valid] = self.choices[codes,node,which]
        return result


def material_set(source, table):
    path = texlib.safe(source or os.environ.get('DISCPROBE_COLOUR_MATERIALS') or DEFAULT_MATERIALS)
    try:
        loaded = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError as exc:
        raise ValueError(f'colour materials file not found: {path}; use --materials JSON or DISCPROBE_COLOUR_MATERIALS') from exc
    if isinstance(loaded, dict) and 'scenarios' in loaded:
        loaded = loaded['scenarios'].get('0.000', {})
    rows = loaded.get('materials', loaded.get('greedy_specs')) if isinstance(loaded, dict) else loaded
    if not isinstance(rows, list) or not 1 <= len(rows) <= 254:
        raise ValueError('colour materials JSON needs 1–254 texture specs')
    specs = [row.get('spec') if isinstance(row, dict) else row for row in rows]
    if any(not isinstance(s, str) for s in specs):
        raise ValueError('each colour material needs a hex texture spec')
    specs = list(dict.fromkeys(texlib.canonical(s) for s in specs))
    for spec in specs:
        if spec not in table['specs']:
            raise ValueError(f'colour texture {spec} is missing from the active colour table; select --table FILE')
    return [dict(id=f'tex:{s}', spec=s) for s in specs]


def legacy_colour(colour):
    table = colour.get('table')
    return isinstance(table, dict) and table.get('fitted') is False and not table.get('mapping')


def active_table(document=None, path=None):
    path = path or os.environ.get('DISCPROBE_COLOUR_TABLE')
    colours = [a['colour'] for a in document['assignments'] if 'colour' in a] if document else []
    if not path and colours and all(legacy_colour(c) for c in colours):
        return simulate_a3.tables()
    path = path or DEFAULT_TABLE
    try:
        table = simulate_a3.load_table(path)
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError(f'could not load colour print table: {path}: {exc}') from exc
    if (table['xyz'].shape != (len(table['specs']), len(table['delta']), 3) or len(table['delta']) < 2
            or not np.isfinite(table['xyz']).all() or not np.all(np.diff(table['delta']) > 0)
            or not .5 <= table.get('delta_scale', 1.) <= 1.5):
        raise ValueError('invalid colour print table')
    return table


def palette(source=None, table_path=None):
    table = active_table(path=table_path)
    return dict(materials=material_set(source, table),
                table=dict(signature=table['signature'], fitted=table['fitted'], mapping='perceptual' if table['fitted'] else 'relative'))


def design(image, phone, height, materials=None, dither='ordered', fit='disc', flash_mm=None, table_path=None,
           *, mapping='perceptual', report_icc=None):
    """Create a portable editor document. Its source texture specs are pinned by ID."""
    from . import editor_ops
    from .colour_input import EmbeddedICC

    h = next((h for h in rig_data()['heights'] if math.isclose(h['ruler_cm'], height, abs_tol=.005)), None)
    rig = dict(phone=phone, **(dict(height=h['id']) if h else dict(height_cm=height)))
    if flash_mm is not None:
        rig['flash_mm'] = flash_mm
    pose = rig_pose(rig)
    cam, flash = pose['camera'], pose['flash']
    choices = palette(materials, table_path)
    if mapping not in ('perceptual', 'vivid'):
        raise ValueError('colour mapping must be perceptual or vivid')
    if mapping == 'vivid' and not choices['table']['fitted']:
        raise ValueError('vivid colour mapping requires a fitted colour table')
    image = texlib.safe(image)
    with image.open('rb') as stream, Image.open(stream) as original:
        conversion = EmbeddedICC(original, stream)
        picture = conversion.picture()
        if report_icc is not None and (notice := conversion.notice()) is not None:
            report_icc(notice)
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
    colour = dict(materials=[m['id'] for m in choices['materials']], dither=dither, table=choices['table'])
    if mapping == 'vivid':
        colour['mapping'] = mapping
    doc['assignments'].append(dict(layer=1, colour=colour))
    return doc


def add_direction_arrow(doc):
    """Add the direction arrow to a newly generated colour work, or return a reason to skip it."""
    from .i18n import tr

    definition = json.loads(DIRECTION_ARROW.read_text(encoding='utf-8'))
    points = definition['data_side_mm']
    xs, ys = zip(*points)
    left, right, tail, tip = min(xs), max(xs), min(ys), max(ys)
    inner, outer = doc['annulus_mm']
    shift = max(0, tip - (outer - definition['rim_margin_mm']))
    if tail - shift < inner - 1e-9:
        return 'The writable ring is too narrow for the direction arrow.'

    material = definition['material']
    if len(doc['materials']) >= 256:
        return 'The direction arrow needs one more material slot.'
    width, height = right - left, tip - tail
    layer = dict(id=2, kind='image', sourceKind='shape', name=tr('Direction arrow'),
                 x=(left + right) / 2, y=shift - (tip + tail) / 2, width=width, height=height,
                 w=round(width * 100), h=round(height * 100), rot=0, visible=True, locked=False, opacity=1,
                 shape=dict(type='polygon', directionArrow=True,
                            points=[[(x - left) / width - .5, (tip - y) / height - .5] for x, y in points]))
    doc['materials'].append(material)
    doc['layers'].append(layer)
    doc['assignments'].append(dict(layer=layer['id'], material=material['id']))
    return None
