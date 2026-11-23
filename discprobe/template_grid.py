"""120 mm template PNGs and their native-pixel source for the editor."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import math
import mmap
from pathlib import Path
import re
import struct
import tempfile
from threading import Lock
import zlib

import numpy as np
from PIL import Image, ImageDraw, PngImagePlugin

from . import simulate, template
from .colour_input import EmbeddedICC
from .imagedisc import CELL_SIDES as GRID_SIDES, HALF_MM

DISC_MM = 2 * HALF_MM
PNG_LIMIT = 256 * 2**20
PNG_DATA_PREFIX = 'data:image/png;base64,'
PREVIEW_SIDE = 1200
_DECODE_LOCK = Lock()
_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_ARROW = Path(__file__).with_name('web') / 'home' / 'design' / 'direction-arrow.json'


def _chunk(stream, kind, data=b''):
    stream.write(struct.pack('>I', len(data)))
    stream.write(kind)
    stream.write(data)
    stream.write(struct.pack('>I', zlib.crc32(data, zlib.crc32(kind))))


def _png(grid, draw=None):
    """Encode one strip at a time, including the 24,000-square RGBA canvas."""
    side = GRID_SIDES[grid]
    ppm = 1_000_000 // grid
    stream = io.BytesIO()
    stream.write(_SIGNATURE)
    _chunk(stream, b'IHDR', struct.pack('>IIBBBBB', side, side, 8, 6, 0, 0, 0))
    _chunk(stream, b'pHYs', struct.pack('>IIB', ppm, ppm, 1))
    encoder = zlib.compressobj(3)
    rows = 96
    blank = bytes((1 + 4 * side) * rows) if draw is None else None
    for top in range(0, side, rows):
        count = min(rows, side - top)
        if draw:
            with Image.new('RGBA', (side, count)) as strip:
                draw(strip, top)
                scanlines = np.zeros((count, 1 + 4 * side), np.uint8)
                scanlines[:, 1:] = np.asarray(strip).reshape(count, -1)
                data = encoder.compress(scanlines)
        else:
            data = encoder.compress(memoryview(blank)[:count * (1 + 4 * side)])
        if data:
            _chunk(stream, b'IDAT', data)
    _chunk(stream, b'IDAT', encoder.flush())
    _chunk(stream, b'IEND')
    return stream.getvalue()


def _visible_arcs(g, pose, rotate, scale):
    """Sample first-order visibility around the writable ring, in artwork coordinates."""
    periods = [row['periods_um'][0] for row in template.palette()['swatches'].values()
               if row['kind'] == 'single']
    angles = np.arange(1440) * (2 * math.pi / 1440)
    optical = angles + math.radians(rotate)
    for r in np.arange(g['start_mm'] + 2, g['end_mm'], 3):
        delta = scale * simulate.along_track(r * np.cos(optical), r * np.sin(optical), **pose)
        visible = np.any([(0.4 <= delta * p) & (delta * p <= 0.7) for p in periods], axis=0)
        breaks = np.flatnonzero(np.diff(np.r_[False, visible, False]))
        for start, stop in breaks.reshape(-1, 2):
            yield r, start / 4, stop / 4


def _guide(grid, g, pose, rotate, scale):
    side = GRID_SIDES[grid]
    px_per_mm = 1000 / grid
    center = (side - 1) / 2
    circles = [(60, template.INK, .18), (g['hole_mm'], template.INK, .18),
               (g['start_mm'], template.INK, .17), (g['end_mm'], template.INK, .17),
               (g['safe_start_mm'], template.CAUTION, .1), (g['safe_end_mm'], template.CAUTION, .1)]
    arrow = json.loads(_ARROW.read_text(encoding='utf-8'))['data_side_mm']
    arcs = list(_visible_arcs(g, pose, rotate, scale)) if g['media'] == 'dvd' else []

    def draw(strip, top):
        ink = ImageDraw.Draw(strip)
        cy = center - top
        for r, colour, width in circles:
            w = round(width * px_per_mm)
            radius = r * px_per_mm + w / 2
            if cy - radius <= strip.height and cy + radius >= 0:
                ink.ellipse((center-radius, cy-radius, center+radius, cy+radius), outline=colour, width=w)
        for r, start, end in arcs:
            radius = r * px_per_mm
            if cy - radius <= strip.height and cy + radius >= 0:
                ink.arc((center-radius, cy-radius, center+radius, cy+radius), -end, -start,
                        fill=(61, 98, 104, 192), width=round(.09 * px_per_mm))
        if cy - 52.8 * px_per_mm <= strip.height and cy - 43.5 * px_per_mm >= 0:
            points = [(center + x * px_per_mm, cy - y * px_per_mm) for x, y in arrow]
            ink.line(points + points[:1], fill=template.CAUTION, width=round(.15 * px_per_mm))

    return _png(grid, draw)


def _slug(label, fallback):
    return re.sub(r'[^\w-]+', '-', label).strip('-_')[:48] or fallback


def export_files(geo, *, grid, media=None, sectors=None, pose=None, preset_id=None,
                 batch=None, rotate=0, delta_scale=1):
    if type(grid) is not int or grid not in GRID_SIDES:
        raise ValueError('grid must be 5, 10 or 20 µm')
    if batch is not None and (not isinstance(batch, str) or len(batch) > 200):
        raise ValueError('invalid template batch name')
    if type(rotate) not in (int, float) or not math.isfinite(rotate):
        raise ValueError('invalid template rotation')
    if type(delta_scale) not in (int, float) or not math.isfinite(delta_scale) or not 0 < delta_scale <= 10:
        raise ValueError('invalid template diffraction scale')
    g = template.geometry(geo, media, sectors, preset_id, include_batch=True)
    p = template.parse_pose(pose if pose is not None else 'default')
    rotate %= 360
    pose_id = hashlib.sha256(json.dumps([p, float(rotate), float(delta_scale)]).encode()).hexdigest()[:10]
    x, y, z = p['camera']
    camera = f'x{x:g}_y{y:g}_z{z:g}mm_rot{rotate:g}deg'
    batch = batch or preset_id or g.get('batch')
    batch_id = _slug(batch or '', f'{g["media"]}-{g["source_sha256"][:10]}')
    stem = f'dp_template_{grid}um_{batch_id}_{g["sectors"]}s_pose-{camera}-{pose_id}'
    side = GRID_SIDES[grid]
    readme = f'''disc-probe 设计模板 / Design template
{side} × {side} px · {grid} µm/px · {25400 // grid} DPI · 120 × 120 mm
批次 / Batch: {batch or batch_id} · {g['media'].upper()} · {g['sectors']} sectors
可刻环带 / Writable: r{g['start_mm']:.6f}–{g['end_mm']:.6f} mm
机位 / Pose: {json.dumps(p)} · {rotate:g}° CCW · δ × {delta_scale:g} (mm, y up)

打开 *_canvas.png，将 *_guide.png 原尺寸叠在上方。另建图层作画，导出透明 PNG 前隐藏引导层。
保持整张正方形，关闭自动裁边。带原格距的 DPI 可直接导入。若软件清除了 DPI，选“导入模板作品”。
引导层显示内外圆、中心孔、两端 0.5 mm 安全边距和 12 点对准箭头的位置。
DVD 上的弧线是按所选机位预测的一阶可见范围。CD 和 BD 只有几何引导。
数据面向上，x 向右，y 向下。图像中心对应盘心。

Open *_canvas.png and stack *_guide.png above it at its original size. Draw on a new layer and
hide the guide before exporting a transparent PNG. Keep the whole square and turn off trimming.
Regular import recognises the original DPI. If your app drops it, use Import template artwork.
The overlay shows the writable ring, safe margins, centre hole, rim and the 12 o’clock arrow location.
Arcs indicate approximate first-order visibility for DVD at this pose. CD and BD have geometry guides.
Data side up, x right, y down. The centre of the image is the centre of the disc.
One open RGBA layer uses {4 * side**2 / 2**30:.2f} GiB before app overhead.
'''
    return stem, {f'{stem}_canvas.png': _png(grid),
                  f'{stem}_guide.png': _guide(grid, g, p, rotate, delta_scale),
                  f'{stem}_README.txt': readme.encode()}


@contextmanager
def _grid_png(raw, manage_icc):
    # The public Pillow pixel limit remains in place for other formats and imports.
    # This path only permits the three known full-disc sizes, one decode at a time.
    if not raw.startswith(_SIGNATURE) or len(raw) > PNG_LIMIT:
        raise ValueError('expected a full-disc PNG up to 256 MiB')
    with _DECODE_LOCK:
        try:
            source = io.BytesIO(raw)
            im = PngImagePlugin.PngImageFile(source)
        except (OSError, SyntaxError) as exc:
            raise ValueError(f'could not read template PNG: {exc}') from exc
        try:
            if im.width != im.height or im.width not in GRID_SIDES.values():
                raise ValueError('expected a 6000, 12000 or 24000 px square PNG')
            try:
                conversion = EmbeddedICC(im, source, enabled=manage_icc)
                if conversion.high_depth is None:
                    im.load()
            except (OSError, SyntaxError, ValueError) as exc:
                raise ValueError(f'could not read template PNG: {exc}') from exc
            yield im, conversion
        finally:
            im.close()


def preview_png(raw, *, report_icc=None):
    with _grid_png(raw, report_icc is not None) as (im, conversion), Image.new('RGBA', (PREVIEW_SIDE, PREVIEW_SIDE)) as preview:
        if report_icc is not None and (notice := conversion.notice()) is not None:
            report_icc(notice)
        factor = im.width // PREVIEW_SIDE
        band = factor * 8
        for top in range(0, im.height, band):
            block = conversion.band((0, top, im.width, min(top + band, im.height)))
            preview.paste(block.reduce(factor), (0, top // factor))
        stream = io.BytesIO()
        preview.save(stream, 'PNG', compress_level=3)
        bounds = _alpha_bounds(im, conversion)
        return stream.getvalue(), ([v * DISC_MM / im.width - DISC_MM / 2 for v in bounds] if bounds else None)


def _alpha_bounds(im, conversion):
    if conversion.high_depth is not None:
        return conversion.high_depth.bounds()
    if im.mode in ('RGBA', 'LA', 'PA'):
        return im.getbbox()
    if 'transparency' not in im.info:
        return 0, 0, im.width, im.height
    bounds = None
    for top in range(0, im.height, 128):
        block = im.crop((0, top, im.width, min(top + 128, im.height))).convert('RGBA')
        box = block.getbbox()
        if box:
            x0, y0, x1, y1 = box
            bounds = ((min(bounds[0], x0), bounds[1], max(bounds[2], x1), top + y1)
                      if bounds else (x0, top + y0, x1, top + y1))
    return bounds


class NativeRaster:
    def __init__(self, side, bounds, pixels):
        self.side = side
        self.bounds = bounds
        self.pixels = pixels

    def row(self, x, y):
        left, top, right, bottom = self.bounds
        inside = (x >= left) & (x < right) & (y >= top) & (y < bottom)
        rgba = np.zeros((len(x), 4), np.uint8)
        rgba[inside] = self.pixels[y[inside] - top, x[inside] - left]
        return rgba


def _write_pixels(conversion, bounds, stream):
    left, top, right, bottom = bounds
    for y in range(top, bottom, 128):
        stream.write(conversion.band((left, y, right, min(y + 128, bottom))).tobytes())


@contextmanager
def native_raster(raw, scratch=None, *, manage_icc=False):
    """Keep compact artwork in RAM and page dense native artwork through a scratch file."""
    with tempfile.TemporaryFile(dir=scratch) as stream:
        with _grid_png(raw, manage_icc) as (im, conversion):
            side = im.width
            bounds = _alpha_bounds(im, conversion) or (0, 0, 0, 0)
            left, top, right, bottom = bounds
            shape = bottom - top, right - left, 4
            if not shape[0]:
                pixels = np.zeros((1, 1, 4), np.uint8)
            elif math.prod(shape) <= 16 * 2**20:
                pixels = np.asarray(conversion.band(bounds))
            else:
                pixels = None
                _write_pixels(conversion, bounds, stream)
        del conversion
        del raw
        if pixels is not None:
            yield NativeRaster(side, bounds, pixels)
        else:
            stream.flush()
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
                yield NativeRaster(side, bounds, np.ndarray(shape, dtype=np.uint8, buffer=mapping))
