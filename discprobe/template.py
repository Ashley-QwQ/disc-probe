"""Offline drawing templates. CLI and HTTP both consume export_files(), byte for byte.

No device access, sector writing, browser renderer or optional package is used.
SVG and PNG are drawn from the same millimetre primitives.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from html import escape
import io
import json
import math
from pathlib import Path
import struct
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import simulate

MARGIN_MM = 0.5
SHEET_MM = 160
VIEW_BOX = (-80, -80, SHEET_MM, SHEET_MM)
DARK_LAYER = 'approximate-pose-dark-zones'
LAYER_STYLES = {DARK_LAYER: {'display': 'none', 'opacity': '.22'}}
INK = '#383630'
CAUTION = '#91613e'
WARNING = ('预测占位色，尚未经照片验证；颜色随盘面位置和姿态改变。 '
           'Placeholder colours, not photo validated; position and pose change the colour.')
DATA = Path(__file__).with_name('template_palette.json')


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be a finite positive number')
    return float(value)


def _count(value, name='sectors'):
    if type(value) is not int or not 1 <= value <= 25_000_000:
        raise ValueError(f'{name} must be an integer in 1..25000000')
    return value


def _preset(data, preset_id):
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get('presets', [*data.get('dvdPresets', []), *data.get('cdPresets', []),
                                     *data.get('bluRayPresets', [])] or [data.get('preset', data)])
    else:
        raise ValueError('geometry must be a JSON object or preset list')
    if not isinstance(entries, list) or not all(isinstance(p, dict) for p in entries):
        raise ValueError('preset entries must be objects')
    if preset_id is not None:
        entries = [p for p in entries if p.get('id') == preset_id]
    if len(entries) != 1 or not isinstance(entries[0], dict):
        raise ValueError('select one preset with --preset-id (or give a single preset JSON)')
    return entries[0]


def geometry(source, media=None, sectors=None, preset_id=None):
    """Read a geo summary/folder or DIS preset; N is an exclusive sector boundary.

    Cubic preset pitch is integrated in radius, as disexport.dis_angle_map does,
    without importing its scipy fitter. Never substitute a nominal disc batch.
    """
    if media is not None and media not in ('dvd', 'cd', 'bd'):
        raise ValueError('media must be dvd, cd or bd')
    path = Path(source)
    if str(source).lower() == 'latest':
        from .guide import resolve_geo
        path = Path(resolve_geo(str(source), media))
    if path.is_dir():
        path /= 'summary.json'
    raw = path.read_bytes()
    data = json.loads(raw)
    notes = []
    if isinstance(data, dict) and data.get('fit'):
        f = data['fit']
        if not isinstance(f, dict) or not isinstance(data.get('setup', {}), dict):
            raise ValueError('geo fit and setup must be objects')
        kind = f.get('media') or (data.get('setup') or {}).get('media') or ('bd' if f.get('model') == 'clv' else 'dvd')
        last = (data.get('setup') or {}).get('last_lba')
        capacity = _count(last + 1, 'batch capacity') if type(last) is int else None
        n = _count(sectors if sectors is not None else capacity)
        if f.get('model') == 'clv':
            if kind != 'bd':
                raise ValueError('only the existing BD CLV geometry is supported')
            from .bdexport import outer_radius_mm
            ri, pitch = _positive(f['r0_mm'], 'r0_mm'), _positive(f['pitch_um'], 'pitch_um')
            radius = lambda count: outer_radius_mm(ri, pitch, count)
        else:
            from .calib import sector_bits
            from . import cd
            u, v = _positive(f['u'], 'u'), _positive(f['v'], 'v')
            bit = _positive(f['bit_nm_assumed'], 'bit_nm_assumed') * 1e-6
            bits = cd.SECTOR_BITS if kind == 'cd' else sector_bits(kind)[0]
            radius = lambda count: bit * math.sqrt(u * u + v * count * bits / math.pi)
            ri = radius(0)
        if data.get('simulated'):
            notes.append('模拟几何 / Simulated geometry')
        if data.get('stopped'):
            notes.append('未完成测量 / Incomplete measurement')
        notes.append('测量比例继承 geo 假定的沿轨长度 / Scale inherits the geo along-track assumption')
    else:
        f = _preset(data, preset_id)
        kind = 'cd' if 'sectors' in f else 'bd' if 'layerCount' in f else 'dvd'
        if f.get('layerCount', 1) != 1:
            raise ValueError('multi-layer presets do not have a single monotonic radius map')
        capacity = _count(f.get('totalSectors', f.get('sectors')), 'preset capacity')
        n = _count(sectors if sectors is not None else capacity)
        ri, ro = (_positive(f[key], key) for key in ('innerRadiusMm', 'outerRadiusMm'))
        if not ri < ro < 60:
            raise ValueError('preset radii must increase inside the 60 mm disc edge')
        coeff = [f.get(key, 0) for key in ('pitchLinear', 'pitchQuadratic', 'pitchCubic')]
        if any(isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) for c in coeff):
            raise ValueError('invalid preset pitch coefficients')
        r = np.linspace(ri, ro, 40001)
        x = (r - ri) / (ro - ri)
        shape = 1 + coeff[0] * x + coeff[1] * x*x + coeff[2] * x*x*x
        if np.any(shape <= 0):
            raise ValueError('preset pitch must be positive throughout the disc')
        length = 2 * math.pi * r / shape
        area = np.r_[0, np.cumsum((length[1:] + length[:-1]) * .5 * np.diff(r))]
        radius = lambda count: float(np.interp(count / capacity, area / area[-1], r))
        notes.append('预设几何；不是新的实测 / Preset geometry, not a new measurement')
    if media is not None and media != kind:
        raise ValueError(f'geometry is {kind}, requested {media}')
    if kind not in ('dvd', 'cd', 'bd'):
        raise ValueError('unknown geometry media')
    if capacity is not None and n > capacity:
        raise ValueError('sectors exceed this batch capacity')
    end = radius(n)
    if not 17 < ri < end < 60:
        raise ValueError('writable radii must increase between the clamp and outer edge')
    if end - ri <= 2 * MARGIN_MM:
        raise ValueError('written annulus is too narrow for the two 0.5 mm safety margins')
    return dict(media=kind, sectors=n, capacity_sectors=capacity, outer_mm=60.0, hole_mm=7.5,
                clamp_mm=17.0, start_mm=ri, end_mm=end, margin_mm=MARGIN_MM,
                safe_start_mm=ri + MARGIN_MM, safe_end_mm=end - MARGIN_MM,
                source_sha256=hashlib.sha256(raw).hexdigest(), notes=notes)


def parse_pose(value):
    if value is None:
        return None
    if value == 'default':
        return dict(camera=list(simulate.CAMERA), flash=list(simulate.FLASH))
    try:
        nums = [float(v) for v in value.split(',')]
    except (AttributeError, ValueError):
        raise ValueError('pose: default or cx,cy,cz,lx,ly,lz in mm (y up)') from None
    if len(nums) != 6 or not all(math.isfinite(v) for v in nums) or nums[2] <= 0 or nums[5] <= 0:
        raise ValueError('pose needs six finite coordinates and positive camera/light heights')
    return dict(camera=nums[:3], flash=nums[3:])


@lru_cache(maxsize=1)
def palette():
    # Committed, small selection from the local merged palette; no absolute source path at runtime.
    return json.loads(DATA.read_text(encoding='utf-8'))


def swatch_files():
    data = palette()
    entries = list(data['swatches'].items())
    gpl = ['GIMP Palette', 'Name: disc-probe approximate materials', 'Columns: 6', '# ' + WARNING]
    blocks = []
    for name, row in entries:
        rgb = row['srgb']
        gpl.append(f'{rgb[0]:3} {rgb[1]:3} {rgb[2]:3}\t{name}')
        label = (name + '\0').encode('utf-16-be')
        body = struct.pack('>H', len(label) // 2) + label + b'RGB ' + struct.pack('>fffH', *(v / 255 for v in rgb), 0)
        blocks.append(struct.pack('>HI', 1, len(body)) + body)
    ase = b'ASEF' + struct.pack('>HHI', 1, 0, len(blocks)) + b''.join(blocks)
    return {'swatches.json': (_json(data) + '\n').encode(), 'swatches.gpl': ('\n'.join(gpl) + '\n').encode(),
            'swatches.ase': ase}


def read_ase(raw):
    """Strict reader for the RGB ASE 1.0 subset emitted here; useful to callers/tests."""
    stream = io.BytesIO(raw)
    if stream.read(8) != b'ASEF\0\1\0\0':
        raise ValueError('ASE 1.0 required')
    def unpack(fmt):
        size = struct.calcsize(fmt)
        chunk = stream.read(size)
        if len(chunk) != size:
            raise ValueError('truncated ASE')
        return struct.unpack(fmt, chunk)
    count, = unpack('>I')
    result = {}
    for _ in range(count):
        kind, length = unpack('>HI')
        end = stream.tell() + length
        n, = unpack('>H')
        label = stream.read(n * 2).decode('utf-16-be')
        if kind != 1 or not label.endswith('\0') or stream.read(4) != b'RGB ':
            raise ValueError('unsupported ASE block')
        r, g, b, mode = unpack('>fffH')
        if mode != 0 or not all(math.isfinite(v) and 0 <= v <= 1 for v in (r, g, b)) or stream.tell() != end:
            raise ValueError('invalid RGB ASE block')
        if label[:-1] in result:
            raise ValueError('duplicate ASE name')
        result[label[:-1]] = [round(255 * v) for v in (r, g, b)]
    if stream.read(1):
        raise ValueError('trailing ASE bytes')
    return result


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)


def scene(g, pose=None):
    """Layers of (circle/line/text, coordinates, stroke, width) in the same mm space."""
    layers = []
    def layer(ident, name):
        items = []
        layers.append((ident, name, items))
        return items
    def circle(items, r, color=INK, width=.14):
        items.append(('circle', [r], color, width))
    def line(items, x1, y1, x2, y2, color=INK, width=.1):
        items.append(('line', [x1, y1, x2, y2], color, width))
    def text(items, x, y, label, size=1.65):
        items.append(('text', [x, y, label], INK, size))
    def hatch(items, inner, outer, test=None, color='#a09a8f', opposite=False):
        # x+y=c for non-writable areas; mirror y for the optional opposite screen.
        # The predicate always sees final SVG coordinates (x right, y down).
        direction = -1 if opposite else 1
        for c in np.arange(-85., 85.01, 1.8):
            dist = c / math.sqrt(2)
            if abs(dist) >= outer:
                continue
            hi = math.sqrt(outer * outer - dist * dist)
            lo = math.sqrt(max(0, inner * inner - dist * dist))
            for a, b in ((-hi, -lo), (lo, hi)):
                if b <= a:
                    continue
                if test is None:
                    spans = [(a, b)]
                else:
                    # Optional pose boundary is an explicitly approximate 0.2 mm sampling.
                    ts = np.linspace(a, b, max(2, math.ceil((b-a) / .2) + 1))
                    spans = []
                    start = None
                    for left, right in zip(ts[:-1], ts[1:]):
                        mid = (left + right) / 2
                        ok = test((dist + mid) / math.sqrt(2), direction*(dist - mid) / math.sqrt(2))
                        if ok and start is None:
                            start = left
                        if not ok and start is not None:
                            spans.append((start, left)); start = None
                    if start is not None:
                        spans.append((start, b))
                for left, right in spans:
                    line(items, (dist+left)/math.sqrt(2), direction*(dist-left)/math.sqrt(2),
                         (dist+right)/math.sqrt(2), direction*(dist-right)/math.sqrt(2), color, .06)
    items = layer('non-writable-hatching', '不可作画区 / Non-writable areas · 45°')
    hatch(items, g['hole_mm'], g['start_mm'])
    hatch(items, g['end_mm'], 60)
    circle(layer('disc-outer-edge', '盘外缘 / Disc outer edge · 120 mm'), 60, INK, .28)
    circle(layer('centre-hole', '中心孔 / Centre hole · 15 mm'), 7.5, INK, .22)
    items = layer('clamping-ring', '装夹环 / Clamping ring · r 7.5–17 mm (nominal)')
    circle(items, 17)
    circle(layer('writable-start', '可刻起点 / Writable start'), g['start_mm'], INK, .22)
    circle(layer('written-end', '本次写入终点 / Written data end'), g['end_mm'], INK, .22)
    items = layer('safe-margin', '安全边距 / Safe margin · 0.5 mm each end')
    circle(items, g['safe_start_mm'], CAUTION)
    circle(items, g['safe_end_mm'], CAUTION)
    if pose:
        periods = [s['periods_um'][0] for s in palette()['swatches'].values() if s['kind'] == 'single']
        items = layer(DARK_LAYER, '姿态暗区（近似，默认关闭） / dark-at-pose (approximate, off)')
        def dark_at_pose(x,y):
            delta = simulate.along_track(x,-y,pose['camera'],pose['flash'])
            return not any(400 <= 1000*period*delta <= 700 for period in periods)
        hatch(items, g['start_mm'], g['end_mm'],
              dark_at_pose,
              '#83654d', opposite=True)
    items = layer('radius-ruler', '半径尺 / Radius ruler · mm')
    line(items, 8, 0, 59, 0, width=.065)
    for r in range(10, 60, 2):
        line(items, r, -.35, r, .35, width=.065)
    for r in (24, 40, 58):
        line(items, r, -.7, r, .7, INK, .08)
        text(items, r-1, 2.4, str(r), 1.5)
    text(items, 62, .7, '半径 / Radius mm', 1.5)
    items = layer('info', '盘外说明 / Info outside disc')
    text(items, -60, -67, 'DISC-PROBE · 绘图模板 / Drawing template', 2.4)
    labels = [f'{g["media"].upper()} · {g["sectors"]:,} 扇区 / sectors',
              f'孔 / Hole Ø15 · 装夹 / Clamp r17 (mm)',
              f'可刻起点 / Writable start: r{g["start_mm"]:.3f} mm',
              f'写入终点 / Written end: r{g["end_mm"]:.3f} mm',
              f'安全 / Safe: r{g["safe_start_mm"]:.3f}–{g["safe_end_mm"]:.3f} mm',
              '两端各留 0.5 mm，应对对齐和边缘误差。',
              '0.5 mm inset each end for alignment / edge uncertainty.',
              '并非测量精度保证 / Not a measurement guarantee.',
              '数据面 · x向右 y向下 / Data side · x right, y down',
              '盘缘 / Edge r60 mm · 45° 禁画区 / Non-writable']
    for i, label in enumerate(labels):
        text(items, -60 if i < 5 else 5, 65 + (i if i < 5 else i-5) * 2.5, label, 1.5)
    if pose:
        text(items, -60, 77.5, '姿态暗区：近似，默认关闭，可画 / Approximate dark zone: off, drawable', 1.3)
        text(items, 5, 77.5, 'Approximate first-order mask · opposite hatch, 22% opacity', 1.3)
    return layers


def _clip_to_disc(ident):
    return ident not in ('info', 'radius-ruler')


def svg_bytes(layers, meta):
    ns = 'http://www.inkscape.org/namespaces/inkscape'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{ns}" width="{SHEET_MM}mm" height="{SHEET_MM}mm" viewBox="{" ".join(map(str, VIEW_BOX))}">',
             '<title>disc-probe 绘图模板 / Drawing template</title>',
             '<metadata>' + escape(_json(meta)) + '</metadata>',
             '<defs><clipPath id="disc-material-clip"><path clip-rule="evenodd" d="M60 0 A60 60 0 1 0 -60 0 A60 60 0 1 0 60 0 Z M7.5 0 A7.5 7.5 0 1 0 -7.5 0 A7.5 7.5 0 1 0 7.5 0 Z"/></clipPath></defs>']
    for ident, name, items in layers:
        clip = ' clip-path="url(#disc-material-clip)"' if _clip_to_disc(ident) else ''
        style = ''.join(f' {k}="{v}"' for k,v in LAYER_STYLES.get(ident, {}).items())
        parts.append(f'<g id="{ident}" inkscape:groupmode="layer" inkscape:label="{escape(name, quote=True)}" fill="none"{clip}{style}>')
        parts.append('<title>' + escape(name) + '</title>')
        for kind, coords, color, width in items:
            style = f'stroke="{color}" stroke-width="{width:g}"'
            if kind == 'circle':
                parts.append(f'<circle cx="0" cy="0" r="{coords[0]:.8f}" {style}/>')
            elif kind == 'line':
                parts.append('<line ' + ' '.join(f'{k}="{v:.8f}"' for k, v in zip(('x1','y1','x2','y2'), coords)) + f' {style}/>')
            else:
                x, y, label = coords
                parts.append(f'<text x="{x:g}" y="{y:g}" fill="{color}" font-family="Microsoft YaHei, sans-serif" font-size="{width:g}">{escape(label)}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    return ('\n'.join(parts) + '\n').encode('utf-8')


def _font(size):
    # Use a CJK system font when present; fail clearly instead of silently dropping Chinese.
    for path in ('C:/Windows/Fonts/msyh.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                 '/System/Library/Fonts/PingFang.ttc'):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise ValueError('PNG needs an installed CJK font (Microsoft YaHei, Noto Sans CJK or PingFang)')


def png_bytes(layers, size):
    # Supersample modest outputs; cap at 4096 to bound memory for the default export.
    factor = min(3, max(1, 4096 // size))
    n = size * factor
    scale = n / SHEET_MM
    disc = Image.new('RGBA', (n, n))
    info = Image.new('RGBA', (n, n))
    fonts = {}
    for ident, _, items in layers:
        if LAYER_STYLES.get(ident, {}).get('display') == 'none':
            continue
        d = ImageDraw.Draw(disc if _clip_to_disc(ident) else info)
        for kind, coords, color, width in items:
            w = max(1, round(width * scale))
            if kind == 'circle':
                r = coords[0] * scale
                # Stroke is centred on the physical circle in SVG and PNG.
                cx, cy = -VIEW_BOX[0]*scale, -VIEW_BOX[1]*scale
                d.ellipse((cx-r-w/2, cy-r-w/2, cx+r+w/2, cy+r+w/2), outline=color, width=w)
            elif kind == 'line':
                d.line(tuple((v - VIEW_BOX[i%2]) * scale for i,v in enumerate(coords)), fill=color, width=w)
            else:
                font_size = max(1, round(width * scale))
                if font_size not in fonts:
                    fonts[font_size] = _font(font_size)
                x, y, label = coords
                d.text(((x-VIEW_BOX[0])*scale, (y-VIEW_BOX[1])*scale), label, fill=color,
                       font=fonts[font_size], anchor='ls')
    def clip_material(im):
        side = im.width
        mm_per_px = SHEET_MM / side
        x = (np.arange(side)+.5)*mm_per_px + VIEW_BOX[0]
        for top in range(0, side, 128):
            bottom = min(side,top+128)
            y = (np.arange(top,bottom)+.5)*mm_per_px + VIEW_BOX[1]
            r2 = y[:,None]**2 + x[None,:]**2
            block = np.array(im.crop((0,top,side,bottom)))
            block[(r2 >= 60**2) | (r2 < 7.5**2)] = 0
            im.paste(Image.fromarray(block), (0,top))
    # Only material layers are clipped. Outside notes and the ruler's margin label remain visible.
    clip_material(disc)
    if factor > 1:
        disc = disc.resize((size, size), Image.Resampling.LANCZOS)
        info = info.resize((size, size), Image.Resampling.LANCZOS)
        clip_material(disc)
    im = Image.alpha_composite(disc, info)
    stream = io.BytesIO()
    im.save(stream, 'PNG', dpi=(size/SHEET_MM*25.4, size/SHEET_MM*25.4))
    return stream.getvalue()


def export_files(geo, *, media=None, sectors=None, size=4096, pose=None, preset_id=None):
    if type(size) is not int or not 256 <= size <= 8192:
        raise ValueError('size must be an integer in 256..8192')
    g = geometry(geo, media, sectors, preset_id)
    p = parse_pose(pose)
    if p and g['media'] != 'dvd':
        raise ValueError('pose prediction is only available for the existing DVD colour model')
    meta = dict(geometry=g, pose=p, png_size=size, axes='x-right-y-down-data-side',
                canvas=dict(view_box_mm=list(VIEW_BOX), disc_bounds_mm=[-60,-60,60,60],
                            disc_crop_px=[size/8,size/8,size*7/8,size*7/8]),
                colour_warning=WARNING, psd='Skipped: Pillow cannot write layered PSD; no new dependency.')
    layers = scene(g, p)
    files = {'template.svg': svg_bytes(layers, meta), 'template.png': png_bytes(layers, size), **swatch_files()}
    readme = f'''disc-probe 绘图模板 / Drawing template
{g['media'].upper()} · {g['sectors']} sectors · 160 × 160 mm sheet · Ø120 mm disc · {size} × {size} px
可刻 / Writable: r{g['start_mm']:.6f}–{g['end_mm']:.6f} mm
安全 / Safe: r{g['safe_start_mm']:.6f}–{g['safe_end_mm']:.6f} mm

PS：打开 PNG，锁定参考层，在新层画。载入 ASE 色板。
Illustrator：打开 SVG，160 mm 纸面中盘径 120 mm；载入 ASE。
Krita：打开 PNG 作参考层，导入 GPL 色板。
Figma：拖入 SVG；组名即参考层。按比例保留整个画框；JSON 提供色值。
Inkscape：打开 SVG；图层面板开关参考层，导入 GPL。
标题和说明在盘外。作画前锁住参考；导入 DP 前隐藏全部模板参考，只导出自己的画。
导入 DP 的画须裁为盘心居中的 120 × 120 mm 正方形，不能把盘外留白一起缩进盘里。
PNG 中盘的框为 ({size/8:g}, {size/8:g})–({size*7/8:g}, {size*7/8:g}) px；纸面留白不是画的一部分。
非作画区用 45° 细斜线。两端各留 0.5 mm 给对齐和边缘误差；不是精度保证。
孔径 15 mm、外径 120 mm、装夹半径 17 mm 是结构示意尺寸；可刻环来自几何。

Photoshop: open PNG, lock it as a reference, draw on a new layer; load ASE swatches.
Illustrator: open the 160 mm SVG sheet (disc diameter 120 mm); load ASE.
Krita: open PNG as a reference and import GPL. Figma: drop SVG and retain the full frame;
named groups are guides; JSON contains the colour values. Inkscape: open SVG + GPL.
Hide ALL template guides before exporting your artwork to DP; crop to the centred 120 mm square.
PNG disc bounds: ({size/8:g}, {size/8:g})–({size*7/8:g}, {size*7/8:g}) px. Exclude the outside notes/margins.
PNG DPI records the 160 mm sheet. In Figma use proportions, not its pixel-to-mm convention.
The physical hole, edge and clamp are nominal dimensions; the drawing annulus comes from the batch.
N sectors means the end of sector N-1, not the capacity of an unrelated disc.
The two 0.5 mm margins allow alignment/edge uncertainty; they are not a calibration guarantee.

{WARNING}
色板之外的颜色不代表可刻材料；DP 当前导入会转灰度/抖动并映射两种纹理。
按 swatches.json 精确恢复材料是后续导入功能；本卡不宣称已能按 RGB 恢复材料。
Other colours are not burnable material IDs. Current DP import converts to greyscale/dither
and two textures. Exact material recovery using swatches.json belongs to the later importer.
灰阶配方同样是参考，不会仅凭 RGB 自动恢复混合材料。
PSD 未生成：现有 Pillow 不能写分层 PSD；未添加依赖。
PSD skipped: installed Pillow cannot write layered PSD; no dependency added.
姿态层（可选）默认关闭：反向斜线、22% 不透明度，只是观察提示，不是禁画区。
PNG 同样不显示默认关闭的暗区；需要观察时在 SVG 中开启该层，图例在盘外。
仅表示所选单周期材料的一阶光不可见，不代表整个盘面全黑。
Optional pose layer is OFF by default (also omitted from PNG), opposite hatch at 22% opacity.
Enable it in SVG to inspect; its legend sits outside the disc. It is drawable, not a forbidden area.
It approximates no visible first order among selected single-period materials,
not absence of reflected light. Only DVD; ignores efficiency, higher orders and photo response.
坐标 / Axes: x right, y down, data side. Pose coordinates use the optical model's y UP.
几何说明 / Geometry notes: {'; '.join(g['notes'])}
'''
    files['README.txt'] = readme.encode('utf-8')
    return files


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, raw)
    return stream.getvalue()


def write(geo, out='disc-template', **options):
    files = export_files(geo, **options)
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (target / name).write_bytes(raw)
    return target
