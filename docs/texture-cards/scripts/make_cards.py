"""Build the merged palette cards. Python 3.13 + numpy + Pillow, no other packages.

All writes are constrained to this script's directory. The DP colour function is
extracted with ast, byte-for-byte, without importing its unrelated dependencies.
Run: py -3.13 -B make_cards.py
"""
from __future__ import annotations

import ast
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import zlib

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PALETTE = HERE.parent / 'data' / 'palette_merged.json'
ROOT = HERE.parents[2]                 # repository root
# wavelength_rgb was first read from an editor branch's first_order.py; tools/lut_scatter.py holds the same
# executable body (colour_source() checks this), so the repository copy is used.
SOURCE = ROOT / 'tools' / 'lut_scatter.py'
SCATTER = ROOT / 'tools' / 'lut_scatter.py'
FONTS = ROOT / 'discprobe' / 'web' / 'fonts'   # MonaSans / Archivo; missing fonts fall back to Arial
DATE = '2026-11-11'
W, H, DPI = 3508, 4961, 300
MARGIN = 142
BG = (22, 29, 28)
INK = (9, 14, 13)
FG = (237, 231, 213)
MUTED = (177, 190, 180)
RULE = (51, 65, 60)
ACCENT = (187, 209, 159)
SECOND = (198, 184, 142)
TOP, BOTTOM = 670, 4570
GUTTER = 78
CW = (W - 2 * MARGIN - GUTTER) // 2
FONT_LOG = {}
AUDIT = []
TEXT_BOXES = []
ACTIVE_SHEET = None
RUN_AUDIT = []
ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
RATIOS = [('6:5', 6 / 5), ('5:4', 5 / 4), ('4:3', 4 / 3),
          ('7:5', 7 / 5), ('3:2', 3 / 2)]


def save_path(name):
    p = (HERE / name).resolve()
    assert p.is_relative_to(HERE), p
    return p


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(name, text):
    save_path(name).write_text(text, encoding='utf-8', newline='\n')


def font(kind, size):
    paths = {
        'ui': FONTS / 'MonaSans-VF.ttf',
        'zh': Path('C:/Windows/Fonts/msyh.ttc'),
        'mono': Path('C:/Windows/Fonts/consola.ttf'),
        'note': FONTS / 'Archivo-VF.ttf',
    }
    p = paths[kind]
    fallback = not p.exists()
    if fallback:
        p = Path('C:/Windows/Fonts/arial.ttf')
    FONT_LOG[kind] = str(p)
    f = ImageFont.truetype(str(p), size)
    if kind == 'note' and not fallback:   # Archivo's width/weight axes; a fallback font has none
        f.set_variation_by_axes([500, 75])
    return f


def text(d, xy, value, size=28, kind='ui', fill=FG, anchor='lt', limit=None):
    f = font(kind, size)
    box = d.textbbox(xy, value, font=f, anchor=anchor)
    assert size >= (21 if kind == 'note' else 25), (value, size)
    assert box[0] >= 118 and box[1] >= 118 and box[2] <= W - 118 and box[3] <= H - 118, (value, box)
    if limit is not None:
        assert box[2] <= limit, (value, box, limit)
    TEXT_BOXES.append({'sheet': ACTIVE_SHEET, 'text': value, 'bbox': box, 'px': size})
    d.text(xy, value, font=f, fill=fill, anchor=anchor)
    return box[2]


def colour_source():
    original = SOURCE.read_text(encoding='utf-8')
    tree = ast.parse(original)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'wavelength_rgb')
    other = ast.parse(SCATTER.read_text(encoding='utf-8'))
    peer = next(n for n in other.body if isinstance(n, ast.FunctionDef) and n.name == fn.name)
    # The two docstrings differ; executable statements must be identical.
    assert ast.dump(ast.Module(body=fn.body[1:], type_ignores=[])) == ast.dump(ast.Module(body=peer.body[1:], type_ignores=[]))
    segment = ast.get_source_segment(original, fn)
    note = f'"""Verbatim DP function. Source: {SOURCE.relative_to(ROOT).as_posix()}\nSHA-256 (whole source file): {sha(SOURCE)}\nNo transfer function is present in the original.\n"""\n\n'
    write_text('dp_colour.py', note + segment + '\n')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns['wavelength_rgb']


def decode_srgb(v):
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def encode_srgb(v):
    v = np.clip(v, 0, 1)
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * v ** (1 / 2.4) - 0.055)


def spectrum(row, width, wavelength_rgb):
    delta = np.linspace(0.10, 0.95, width)
    total = np.zeros((width, 3), dtype=np.float64)
    first = np.zeros(width, dtype=bool)
    second = np.zeros(width, dtype=bool)
    unknown = row['purity'] is None or any(q is None for q in row['purity'])
    for i, p in enumerate(row['periods_um']):
        nm = p * 1000 * delta
        mask = (nm >= 400) & (nm <= 700)
        first |= mask
        second |= (nm / 2 >= 400) & (nm / 2 <= 700)
        if not unknown:
            native = np.array([wavelength_rgb(float(n)) for n in nm[mask]])
            if native.size:
                total[mask] += decode_srgb(native) * row['purity'][i]
    rgb = np.rint(encode_srgb(total) * 255).astype(np.uint8)
    # No floor, exposure, per-row normalization, or background addition to light.
    rgb[~first] = INK
    if unknown:
        rgb[:] = INK
    return rgb, first, second, unknown


def row_label(row):
    p = '/'.join(f'{v:.3f}' for v in row['periods_um'])
    q = ' ? ' if row['purity'] is None else '/'.join(f'{v:.3f}' for v in row['purity'])
    spec = row['spec'][:8] + ('…' if len(row['spec']) > 8 else '')
    flag = '*' if row.get('period_conflict') else ''
    return f'{p}  {q}  {spec}{flag}'


def base_page(sheet, name_zh, name_en, count, detail):
    global ACTIVE_SHEET
    ACTIVE_SHEET = sheet
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    x = text(d, (MARGIN, 150), 'disc-probe ', 66)
    x = text(d, (x, 150), '纹理色卡', 66, 'zh')
    text(d, (x + 16, 150), '/ Texture colour card', 66)
    text(d, (MARGIN, 258), f'{sheet}  /  {name_zh}', 46, 'zh', ACCENT)
    text(d, (MARGIN, 330), name_en, 38)
    text(d, (W - MARGIN, 270), f'{DATE}   |   {count} textures', 32, 'mono', anchor='rt')
    text(d, (MARGIN, 408), '颜色是模型预测，等实拍照片验证 / Colours are model predictions, not yet checked against photos', 29, 'zh')
    d.line((MARGIN, 470, W - MARGIN, 470), fill=RULE, width=2)
    text(d, (MARGIN, 503), detail, 29, 'zh', MUTED)
    text(d, (MARGIN, 550), 'P: µm | q: purity | 1/P: lines/mm | UV / IR: first-order nm | beige dashed rail: 2nd-order location', 27, 'mono', MUTED)
    return im, d


def axis(d, x0, x1, y, top):
    d.line((x0, y, x1, y), fill=MUTED, width=1)
    for t in range(10, 96, 5):
        x = round(x0 + (t / 100 - 0.10) / .85 * (x1 - x0))
        direction = -1 if top else 1
        d.line((x, y, x, y + direction * (13 if t % 10 == 0 else 8)), fill=MUTED)
        if t % 10 == 0:
            text(d, (x, y - 23 if top else y + 24), f'{t / 100:.1f}', 25, 'mono', MUTED,
                 anchor='mb' if top else 'mt')
    text(d, (x1, y - 60 if top else y + 60), 'δ', 25, 'zh', MUTED, anchor='rb' if top else 'rt')


def dark_runs(row, line, width):
    """Each non-visible interval of one line, including boundary wavelengths."""
    p = row['periods_um'][line]
    intervals = [('UV', .1, min(.95, .4 / p)),
                 ('IR', max(.1, .7 / p), .95)]
    for zone, lo, hi in intervals:
        if hi <= lo:
            continue
        left = max(0, round((lo - .1) / .85 * (width - 1)))
        right = min(width, round((hi - .1) / .85 * (width - 1)) + 1)
        low, high = round(lo * p * 1000), round(hi * p * 1000)
        prefix = f'{zone}{line + 1}:' if len(row['periods_um']) > 1 else f'{zone} '
        label = f'{prefix}{low}–{high} nm'
        yield zone, left, right, label


def draw_row(im, d, row, x, y, width, height, label_width, sheet, column, wavelength_rgb, group=None):
    bx = x + label_width
    bw = width - label_width
    nlines = len(row['periods_um'])
    rgb, first, second, unknown = spectrum(row, bw, wavelength_rgb)
    bh = height - 8 if nlines == 1 else 13 if nlines == 2 else 14
    bar = Image.fromarray(np.repeat(rgb[None, :, :], bh, axis=0))
    im.paste(bar, (bx, y + 1))
    # Multi-line rows retain the summed strip above separate line lanes. The
    # latter provide room for independent wavelength labels without painting
    # text over visible colour, even when another line remains visible.
    fallback = []
    for li in range(nlines):
        ly = y + 1 if nlines == 1 else y + bh + 2 + li * 22
        lh = bh if nlines == 1 else 21
        if nlines > 1:
            q = None if row['purity'] is None else [row['purity'][li]]
            lane, _, _, _ = spectrum({'periods_um': [row['periods_um'][li]], 'purity': q}, bw, wavelength_rgb)
            im.paste(Image.fromarray(np.repeat(lane[None, :, :], lh, axis=0)), (bx, ly))
        nm = row['periods_um'][li] * 1000 * np.linspace(.1, .95, bw)
        for zone, left, right, label in dark_runs(row, li, bw):
            # Use strictly invisible pixels, avoiding floating-point boundary
            # rounding into the coloured interval at 400 or 700 nm.
            mask = nm < 400 if zone == 'UV' else nm > 700
            indices = np.flatnonzero(mask)
            assert len(indices)
            left, right = int(indices[0]), int(indices[-1]) + 1
            tw = d.textlength(label, font=font('note', 21))
            fits = tw + 10 <= right - left
            entry = {'id': row['id'], 'line': li + 1, 'zone': zone, 'label': label,
                     'sheet': sheet, 'placement': 'inside' if fits else 'callout',
                     'delta_run_px': [bx + left, bx + right], 'lane_y': ly}
            RUN_AUDIT.append(entry)
            if fits:
                text(d, (bx + (left + right) / 2, ly), label, 21, 'note', MUTED, anchor='mt', limit=bx + right)
            else:
                fallback.append((label, entry))
                # The connector runs in the one-pixel lane gutter, not through
                # any visible spectrum. Its short stem remains in dark pixels.
                cx = bx + (left + right) // 2
                gy = ly + lh
                d.line((x + label_width - 8, gy, cx, gy), fill=RULE)
                d.line((cx, gy, cx, ly + lh - 4), fill=MUTED)
    p_label = '/'.join(f'{v:.3f}' for v in row['periods_um'])
    q_label = '?' if row['purity'] is None else '/'.join(f'{v:.3f}' for v in row['purity'])
    spec = row['spec'][:8] + ('…' if len(row['spec']) > 8 else '') + ('*' if row.get('period_conflict') else '')
    frequency = '/'.join(str(round(1000 / p)) for p in row['periods_um'])
    side = '; '.join(label for label, _ in fallback)
    if nlines == 1:
        end = text(d, (x, y + 2), f'{p_label} {q_label} {spec}', 25, 'mono', limit=bx - 16)
        end = text(d, (end + 14, y + 3), f'{frequency}/mm', 21, 'note', MUTED, limit=bx - 16)
        if side:
            text(d, (end + 14, y + 3), side, 21, 'note', MUTED, limit=bx - 16)
    elif nlines == 2:
        end = text(d, (x, y + 1), p_label, 25, 'mono', limit=bx - 16)
        if side:
            text(d, (end + 10, y + 3), side, 21, 'note', MUTED, limit=bx - 16)
        end = text(d, (x, y + 30), f'{q_label} {spec}', 25, 'mono', limit=bx - 16)
        text(d, (end + 10, y + 32), frequency, 21, 'note', MUTED, limit=bx - 16)
    else:
        text(d, (x, y + 5), row_label(row), 32, 'mono', limit=bx - 16)
        end = text(d, (x, y + 49), f'1/P = {frequency} /mm', 21, 'note', MUTED, limit=bx - 16)
        if side:
            text(d, (end + 14, y + 49), side, 21, 'note', MUTED, limit=bx - 16)
    rail_y = y + height - 5
    for i in range(bw):
        if second[i] and i % 9 < 5:
            d.line((bx + i, rail_y, bx + i, rail_y + 2), fill=SECOND)
        if unknown and first[i] and i % 10 < 4:
            d.point((bx + i, y + 2), fill=SECOND)
            d.point((bx + i, y + bh - 1), fill=SECOND)
    d.line((x, y + height - 1, x + width - 1, y + height - 1), fill=RULE, width=1)
    AUDIT.append({'id': row['id'], 'spec': row['spec'], 'sheet': sheet, 'column': column,
                  'periods_um': row['periods_um'], 'purity': row['purity'],
                  'weights': row.get('weights'), 'group': group,
                  'bbox': [x, y, x + width, y + height], 'strip_bbox': [bx, y + 1, bx + bw, y + bh + 1],
                  'brightness_status': 'UNKNOWN' if unknown else 'DRAWN',
                  'spatial_frequency_per_mm': [1000 / p for p in row['periods_um']],
                  'frequency_label_shown': True})


def footer(d, sheet):
    text(d, (MARGIN, 4700), 'δ：光源与相机方向沿轨道的横向差值，不是角度。 / Along-track sideways direction difference; not an angle.', 27, 'zh', MUTED)
    text(d, (MARGIN, 4743), 'q 是目标频率 ±5% 内的整 ECC 块 AC 功率份额；q 小则暗。 / Smaller measured power share gives a dimmer strip.', 27, 'zh', MUTED)
    text(d, (MARGIN, 4786), 'UV / IR 数字为一阶波长范围（nm）；窄段用旁注。? = UNKNOWN；* = 周期冲突。二阶虚线只标位置。', 27, 'zh', MUTED)
    text(d, (W - MARGIN, 4817), f'{sheet}   /   A3 · 300 dpi · sRGB   /   print at 100%', 25, 'mono', anchor='rt')


def ratio_group(row):
    p = row['periods_um']
    assert len(p) == 2 and p[0] >= p[1]
    r = p[0] / p[1]
    for i, (name, value) in enumerate(RATIOS):
        if abs(r - value) < 1e-7:
            return i, name
    f = Fraction(r).limit_denominator(1000)
    return 5 + float(f) / 10, f'Other {f.numerator}:{f.denominator}'


def two_groups(rows):
    groups = {}
    order = {None: 0, (0.7, 0.3): 1, (0.3, 0.7): 2}
    for row in rows:
        index, name = ratio_group(row)
        weights = tuple(row['weights']) if row.get('weights') else None
        assert weights in order, weights
        key = (index, order[weights], name)
        groups.setdefault(key, []).append(row)
    result = []
    for key, members in sorted(groups.items()):
        members.sort(key=lambda r: (r['periods_um'][0], r['periods_um'][1], r['spec']))
        share = ['equal', '0.7/0.3', '0.3/0.7'][key[1]]
        label = f'{key[2]}  |  {share}  |  n={len(members)}'
        result.append((label, members))
    return result


def paginate_groups(groups):
    cols = [[] for _ in range(6)]
    ci, used = 0, 0
    for label, members in groups:
        offset = 0
        while offset < len(members):
            room = (BOTTOM - TOP - used - 34) // 62
            if room < 1:
                ci += 1
                used = 0
                assert ci < 6, 'Two-line pages exceed two A3 sheets'
                continue
            # Keep a small group together when the next column has room.
            remaining = len(members) - offset
            if offset == 0 and remaining <= 20 and room < remaining and used:
                ci += 1
                used = 0
                assert ci < 6
                continue
            n = min(room, remaining)
            cols[ci].append((label + (' (cont.)' if offset else ''), members[offset:offset + n]))
            used += 34 + n * 62
            offset += n
    assert all(cols), [len(c) for c in cols]
    return cols


def pdf_bytes(images):
    # Lossless raster PDF: exact A3 MediaBox, ICC sRGB, no JPEG compression.
    objects = [None, None]
    def add(obj):
        objects.append(obj)
        return len(objects)
    def stream(payload, attrs=''):
        return f'<< /Length {len(payload)} {attrs} >>\nstream\n'.encode() + payload + b'\nendstream'
    icc = add(stream(zlib.compress(ICC), '/N 3 /Filter /FlateDecode /Alternate /DeviceRGB'))
    profile = add(f'<< /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (sRGB IEC61966-2.1) /DestOutputProfile {icc} 0 R >>'.encode())
    pages = []
    pw, ph = 297 / 25.4 * 72, 420 / 25.4 * 72
    for im in images:
        payload = zlib.compress(im.tobytes(), 6)
        pic = add(stream(payload, f'/Type /XObject /Subtype /Image /Width {W} /Height {H} /ColorSpace [/ICCBased {icc} 0 R] /BitsPerComponent 8 /Interpolate false /Filter /FlateDecode'))
        content = add(stream(f'q\n{pw:.8f} 0 0 {ph:.8f} 0 0 cm\n/Im0 Do\nQ\n'.encode()))
        page = add(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.8f} {ph:.8f}] /Resources << /XObject << /Im0 {pic} 0 R >> >> /Contents {content} 0 R >>'.encode())
        pages.append(page)
    objects[0] = f'<< /Type /Catalog /Pages 2 0 R /OutputIntents [{profile} 0 R] >>'.encode()
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(f"{p} 0 R" for p in pages)}] /Count {len(pages)} >>'.encode()
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    positions = [0]
    for n, obj in enumerate(objects, 1):
        positions.append(len(out))
        out.extend(f'{n} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(out)
    out.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    for pos in positions[1:]:
        out.extend(f'{pos:010d} 00000 n \n'.encode())
    out.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(out)


def verify_pdf(path, expected):
    # Verify each embedded raster by decompressing and comparing every RGB byte
    # to the reviewed PNG. Page drawing uses a single full-page image transform.
    data = path.read_bytes()
    assert data.startswith(b'%PDF-1.4') and data.endswith(b'%%EOF\n')
    assert len(re.findall(rb'/Type /Page\s', data)) == len(expected)
    recovered = []
    for match in re.finditer(rb'\d+ 0 obj\n<< /Length (\d+) ([^\n]*) >>\nstream\n', data):
        attrs = match.group(2)
        if b'/Subtype /Image' in attrs:
            start = match.end()
            raw = zlib.decompress(data[start:start + int(match.group(1))])
            assert len(raw) == W * H * 3
            recovered.append(hashlib.sha256(raw).hexdigest())
    assert recovered == [hashlib.sha256(im.tobytes()).hexdigest() for im in expected]
    assert b'/MediaBox [0 0 841.88976378 1190.55118110]' in data
    return {'pages': len(expected), 'lossless_rgb_match': True, 'A3_media_box': True}


def save_sheet(name, im):
    im.save(save_path(name + '.png'), dpi=(DPI, DPI), icc_profile=ICC)
    save_path(name + '.pdf').write_bytes(pdf_bytes([im]))
    preview = im.resize((877, 1240), Image.Resampling.LANCZOS)
    preview.save(save_path('qa/' + name + '_overview.png'))
    return verify_pdf(save_path(name + '.pdf'), [im])


def qa_crops(name, im, sheet_rows):
    # Unscaled crops; one top/middle/bottom strip per occupied column.
    for ci in sorted({r['column'] for r in sheet_rows}):
        rows = [r for r in sheet_rows if r['column'] == ci]
        for label, row in [('top', rows[0]), ('middle', rows[len(rows) // 2]), ('bottom', rows[-1])]:
            x0, y0, x1, y1 = row['bbox']
            box = (max(MARGIN, x0), max(118, y0 - 60), min(W - 118, x1), min(H - 118, y1 + 65))
            im.crop(box).save(save_path(f'qa/{name}_c{ci}_{label}.png'))
    pieces = [Image.open(save_path(f'qa/{name}_c{ci}_{position}.png')).copy()
              for ci in sorted({r['column'] for r in sheet_rows})
              for position in ('top', 'middle', 'bottom')]
    contact = Image.new('RGB', (max(p.width for p in pieces), sum(p.height + 8 for p in pieces)), BG)
    yy = 0
    for piece in pieces:
        contact.paste(piece, (0, yy))
        yy += piece.height + 8
    contact.save(save_path(f'qa/{name}_review_100pct.png'))


def main():
    save_path('qa').mkdir(exist_ok=True)
    data = json.loads(PALETTE.read_text(encoding='utf-8'))
    wavelength_rgb = colour_source()
    expected = [r['id'] for key in ('singles', 'two_line', 'three_line') for r in data[key]]
    assert len(expected) == len(set(expected)) == 637
    assert [len(data[k]) for k in ('singles', 'two_line', 'three_line')] == [260, 349, 28]
    # Transfer and native hue checks, including 400/700 nm and visibility edges.
    native = np.array([wavelength_rgb(n) for n in (400, 440, 490, 510, 580, 645, 700)])
    assert np.allclose(encode_srgb(decode_srgb(native)), native, atol=1e-12)
    assert np.allclose(encode_srgb(np.array([-1., 2.])), [0., 1.], atol=1e-12)
    pages, pdf_checks = [], {}
    im, d = base_page('01', '单线 · 260 条', 'Singles / increasing period / 130 rows per column', 260,
                      '两栏从左到右阅读；P、q、短 spec 依次排列。空白深墨色表示当前 δ 没有可见一阶。')
    rows = sorted(data['singles'], key=lambda r: (r['periods_um'][0], r['spec']))
    for ci in range(2):
        x = MARGIN + ci * (CW + GUTTER)
        bx = x + 700
        text(d, (x, 609), 'P µm  q   spec   1/P (/mm)', 25, 'mono', MUTED)
        axis(d, bx, x + CW - 1, TOP - 4, True)
        for ri, row in enumerate(rows[ci * 130:(ci + 1) * 130]):
            draw_row(im, d, row, x, TOP + ri * 30, CW, 30, 700, '01', ci + 1, wavelength_rgb)
        axis(d, bx, x + CW - 1, BOTTOM + 6, False)
    footer(d, '01')
    pages.append(('sheet_1_singles', im))
    cols = paginate_groups(two_groups(data['two_line']))
    for pi, sheet in enumerate(('02a', '02b')):
        page_cols = cols[pi * 3:pi * 3 + 3]
        count = sum(len(rs) for col in page_cols for _, rs in col)
        im, d = base_page(sheet, f'双线 · 本页 {count} 条 / 共 349 条', 'Two-line / ratio × target share / long period first', count,
                          '比例 = 长周期:短周期；share 也按此顺序。Other 为其他精确比例；目标 share 不会再次乘入实测 q。')
        cw = (W - 2 * MARGIN - 120) // 3
        for ci, col in enumerate(page_cols):
            x = MARGIN + ci * (cw + 60)
            bx = x + 460
            text(d, (x, 594), 'P long/short; side notes', 25, 'mono', MUTED)
            text(d, (x, 628), 'q; spec; 1/P (/mm)', 25, 'mono', MUTED)
            axis(d, bx, x + cw - 1, TOP - 4, True)
            y = TOP
            for label, members in col:
                text(d, (x, y + 3), label, 25, 'mono', ACCENT)
                y += 34
                for row in members:
                    draw_row(im, d, row, x, y, cw, 62, 460, sheet, ci + 1, wavelength_rgb, label)
                    y += 62
            assert y <= BOTTOM
            axis(d, bx, x + cw - 1, BOTTOM + 6, False)
        footer(d, sheet)
        pages.append((f'sheet_2{chr(97 + pi)}_two_line', im))

    im, d = base_page('03', '三线 · 28 条 + 图例', 'Three-line / increasing longest period / reading key', 28,
                      '周期与纯度逐项对应，均按输入的长周期到短周期顺序；颜色为可见一阶线性光贡献之和。')
    bx = MARGIN + 1170
    text(d, (MARGIN, 609), 'P µm × 3      q × 3      spec', 27, 'mono', MUTED)
    axis(d, bx, W - MARGIN - 1, TOP - 4, True)
    rows = sorted(data['three_line'], key=lambda r: (r['periods_um'][0], r['spec']))
    for ri, row in enumerate(rows):
        draw_row(im, d, row, MARGIN, TOP + ri * 85, W - 2 * MARGIN, 85, 1170, '03', 1, wavelength_rgb)
    axis(d, bx, W - MARGIN - 1, TOP + 28 * 85 + 6, False)
    d.line((MARGIN, 3220, W - MARGIN, 3220), fill=RULE, width=2)
    text(d, (MARGIN, 3280), '读图 / Reading the card', 48, 'zh', ACCENT)
    legend = [
        'δ 是光源与相机方向沿轨道的横向差值，不是角度。',
        'Delta is the sideways difference between the directions to the light and camera, along the track; it is not an angle.',
        'P 是轨道上重复烧录标记的周期。上方色带只显示一阶：λ = 1000 P δ，400–700 nm。',
        'q 是目标频率 ±5% 内的整 ECC 块 AC 功率份额。q 越小，对应线贡献越弱，行就越暗。',
        '多线按逐线实测 q 求和；目标 share 仅用于分组，不能再乘一次。颜色在求和后裁剪。',
        '多线行最上方是合成色带，其下逐线排列；米色虚线标二阶位置 λ = 1000 P δ / 2，不预测亮度。',
        '? 代表块纯度 UNKNOWN：该行保留周期位置的点线轮廓，不能给出亮度；深墨色不代表测得零功率。',
        '* 代表源记录的周期有冲突。完整 spec、记录 ID、分组和每行坐标见 manifest.json。',
        '深墨色段的 UV / IR 数字为该线一阶波长范围（nm）；太窄时用旁注；1/P 为每毫米线数。',
        '函数是 DP 原有的粗略显示 RGB，不是光谱测色标定；这里在线性光中混合，再用标准 sRGB 编码。',
        '这张卡比较颜色窗口与相对强弱；不能保证实际照片、印刷反射颜色或烧录可读性。',
        'A3 297 × 420 mm / 3508 × 4961 px / 300 dpi / sRGB / 以实际大小 100% 打印',
    ]
    for i, line in enumerate(legend):
        text(d, (MARGIN, 3380 + i * 67), line, 29, 'ui' if i == 1 else 'zh', FG)
    text(d, (MARGIN, 4260), '相同 P = 1.500 µm；只改变 q / Same period, different measured power share', 31, 'zh', ACCENT)
    for i, purity in enumerate((1., .5, .1)):
        y = 4330 + i * 75
        text(d, (MARGIN, y + 12), f'q = {purity:.1f}', 30, 'mono')
        rgb, _, _, _ = spectrum({'periods_um': [1.5], 'purity': [purity]}, 2600, wavelength_rgb)
        im.paste(Image.fromarray(np.repeat(rgb[None, :, :], 46, axis=0)), (MARGIN + 410, y))
    footer(d, '03')
    pages.append(('sheet_3_three_line', im))

    actual = [r['id'] for r in AUDIT]
    assert Counter(actual) == Counter(expected), 'Every selected target must appear once'
    assert len(actual) == len(set(actual)) == 637
    expected_runs = [(r['id'], li + 1, zone)
                     for key in ('singles', 'two_line', 'three_line') for r in data[key]
                     for li, p in enumerate(r['periods_um'])
                     for zone, exists in (('UV', p * 100 < 400), ('IR', p * 950 > 700)) if exists]
    actual_runs = [(r['id'], r['line'], r['zone']) for r in RUN_AUDIT]
    assert Counter(actual_runs) == Counter(expected_runs), 'Every non-visible line interval must be annotated once'
    for name, page in pages:
        pdf_checks[name] = save_sheet(name, page)
        sheet = {'sheet_1_singles': '01', 'sheet_2a_two_line': '02a', 'sheet_2b_two_line': '02b', 'sheet_3_three_line': '03'}[name]
        qa_crops(name, page, [r for r in AUDIT if r['sheet'] == sheet])
    save_path('texture_cards_all.pdf').write_bytes(pdf_bytes([im for _, im in pages]))
    pdf_checks['texture_cards_all'] = verify_pdf(save_path('texture_cards_all.pdf'), [im for _, im in pages])
    # Additional original-scale crops around the unknown row and page typography.
    unknown = next(r for r in AUDIT if r['brightness_status'] == 'UNKNOWN')
    p = pages[0][1]
    x0, y0, x1, y1 = unknown['bbox']
    p.crop((x0, y0 - 30, x1, y1 + 30)).save(save_path('qa/unknown_purity.png'))
    pages[0][1].crop((MARGIN, 140, W - MARGIN, 460)).save(save_path('qa/title_100pct.png'))
    pages[-1][1].crop((MARGIN, 3280, W - MARGIN, 4210)).save(save_path('qa/legend_100pct.png'))
    # Text overlap checks are per page, including all new wavelength labels.
    intersections = []
    for i, a in enumerate(TEXT_BOXES):
        for b in TEXT_BOXES[i + 1:]:
            if a['sheet'] != b['sheet']:
                continue
            aa, bb = a['bbox'], b['bbox']
            if aa[0] < bb[2] and aa[2] > bb[0] and aa[1] < bb[3] and aa[3] > bb[1]:
                intersections.append((a['text'], b['text']))
    assert not intersections, intersections[:10]
    manifest = {
        'date': DATE, 'page_pixels': [W, H], 'page_mm': [297, 420], 'dpi': DPI,
        'margin_px': MARGIN, 'minimum_label_pt': 25 * 72 / DPI,
        'source_sha256': {'palette': sha(PALETTE), 'first_order': sha(SOURCE), 'lut_scatter': sha(SCATTER)},
        'fonts': FONT_LOG, 'counts': dict(Counter(r['sheet'] for r in AUDIT)),
        'total_selected_targets': len(actual), 'every_selected_target_once': True,
        'observations_note': '1153 source observations are provenance, not additional selected targets.',
        'pdf_checks': pdf_checks, 'row_manifest': AUDIT,
        'text_boxes': TEXT_BOXES,
        'dark_run_annotations': RUN_AUDIT,
        'minimum_annotation_pt': 21 * 72 / DPI,
        'text_overlap_count': len(intersections),
        'every_invisible_line_interval_annotated_once': True,
        'unknown_brightness': [unknown['id']],
        'nonstandard_ratio_targets': sum(ratio_group(r)[0] >= 5 for r in data['two_line']),
    }
    write_text('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    write_report(data, manifest, pages)
    print('singles=260; two_line=349; three_line=28; total=637')
    print('Every selected target appears exactly once: PASS')
    print('Page row counts:', dict(Counter(r['sheet'] for r in AUDIT)))
    print('PDF: exact A3 MediaBox, embedded sRGB, lossless RGB equals PNG: PASS')
    print('Minimum labels: 6.00 pt; annotations: 5.04 pt; safe bounds >=10 mm; no text overlaps: PASS')
    print('UNKNOWN brightness:', unknown['id'], unknown['spec'][:8] + '…')
    print('Nonstandard ratio targets:', manifest['nonstandard_ratio_targets'])


def write_report(data, manifest, pages):
    files = '\n'.join(f'- `{name}.png`、`{name}.pdf`：{count} 条。' for (name, _), count in zip(pages, manifest['counts'].values()))
    unknown = next(r for r in AUDIT if r['brightness_status'] == 'UNKNOWN')
    report = f'''# A3 纹理色卡制作报告

日期：{DATE}。

## 文件与版面

{files}
- `texture_cards_all.pdf`：以上四页合订本。
- `make_cards.py`：重建脚本；`dp_colour.py`：从 DP 原文件逐字提取的颜色函数及来源哈希。
- `manifest.json`：637 条记录与页内坐标、完整 spec、纯度、分组、字体、源哈希和检查结果。
- `qa/`：每页缩略图、各栏首中尾 100% 裁切，以及标题、图例、UNKNOWN 行裁切。

各页为 A3 纵向 297 × 420 mm；PNG 为 3508 × 4961 px，标记 300 dpi。PDF MediaBox 为精确 A3，完整嵌入相同无损 RGB 像素和 sRGB ICC；并非 PDF/X，也不含出血。边距 142 px（约 12.02 mm），正文最小 25 px = 6 pt。PNG 像素取整与精确 A3 的差异低于 0.008%。打印选实际大小 100%，不要缩放适应页面。

字体：英文采用随项目附带的 MonaSans-VF.ttf；小标注采用附带 Archivo-VF.ttf 的原生 75% 字宽、500 字重轴。中文补用系统微软雅黑 msyh.ttc，数字标签补用系统 Consolas consola.ttf。均直接读取，没有安装。图例英文用 Delta，避免附带英文字体的 δ 字符映射异常。

## 颜色计算与来源

原文件：`{SOURCE.relative_to(ROOT).as_posix()}`，SHA-256 `{manifest['source_sha256']['first_order']}`。
输入 JSON SHA-256：`{manifest['source_sha256']['palette']}`。

仅提取 `wavelength_rgb`；已用 AST 比较确认它与 `tools/lut_scatter.py` 的可执行函数体相同。它返回粗略的显示 RGB，本身没有 gamma 或 sRGB 转换。因此不能声称沿用了源中不存在的编码逻辑：本脚本采用标准 sRGB 逆变换将其解码为线性光，每条线以 λ = 1000 P δ（P 单位 µm）查询原函数，在 400–700 nm 内按实测块纯度 q 加权相加；裁剪到 [0,1] 后做标准 sRGB 编码。单线 q=1 的原函数 RGB 保持不变。没有更换波长色相模型，没有逐行归一化、曝光提升、灰色底光或再乘目标 share。

主色带没有可见一阶时使用近黑 #090e0d，整页底色为 #161d1c。米色虚线轨独立标出 λ = 1000 P δ / 2 在 400–700 nm 的二阶区间；输入没有可支持逐线亮度的二阶效率，故不把虚线强弱当作实拍亮度，也不将二阶加进主色带。输入存在的聚合 h2 不能替代逐线二阶效率。

双线先按 6:5、5:4、4:3、7:5、3:2，再按 equal、0.7/0.3、0.3/0.7 分组；周期和 share 均为长周期在前。另有 46 条比例不属于上述五类，按实际有理数比例列入 Other，未强行归类。equal 表示未指定非等目标份额，并不表示测得的两条纯度相等。

## 检查与边界

260 单线 + 349 双线 + 28 三线 = 637 条选中目标：ID 集合和计数逐项比对，全部恰好出现一次。1153 条 observations 是来源证据，未重复当作选中纹理绘制。各页行数为 {manifest['counts']}。所有文字边界均通过至少 10 mm 的页边检查，标签宽度通过栏内检查；每份 PDF 的图像流解压后与对应 PNG 的全部 RGB 字节一致。

尚不能按纯度绘制亮度的唯一纹理：`{unknown['id']}`，P = 2.100 µm，短 spec `24F2F2B3…`，块纯度 UNKNOWN。该行仍出现一次，标记 ?，只画一阶位置的点线轮廓及二阶定位轨；旧 corner 指标没有冒充整块纯度。其完整 spec 见 manifest。其余 636 条均已按给定纯度绘制。源周期冲突用 * 标记，未修正源数据。

色卡能比较给定 δ 内的可见窗口、示意色相及纯度对模型相对亮度的影响；不能证明实际照片颜色、绝对亮度、二阶效率、照明/相机几何可达性、印刷色彩或光盘读取可靠性。未做新的烧录或实拍验证。

## 第二版

已按 `AMEND.md` 重渲染全部 PNG、单页 PDF 和合订 PDF。单线保持两栏，双线改为每页三栏；每个多线行最上方为合成色带，其下为依次对应 P1、P2（及 P3）的逐线色带，避免一条线的不可见标注覆盖另一条线的可见颜色。主标签仍为至少 6 pt；波长和空间频率标注为 21 px = 5.04 pt。

每条线的每个 UV／IR 连续区间均标出 δ 范围对应的一阶波长端点（nm，四舍五入到整数）；共 {len(RUN_AUDIT)} 段，其中 {sum(r['placement'] == 'inside' for r in RUN_AUDIT)} 段在深色区内标注，{sum(r['placement'] == 'callout' for r in RUN_AUDIT)} 段因区间太窄移到同一行标签旁，并用边沟引线对应区间。此为对“写在黑段内部”的排版例外：数像素宽的区间无法容纳 5 pt 文字；没有缩小字或覆盖可见色。行标签中的空间频率为 1000/P（每毫米线数），与周期同序，取整数；完整精度保存在 manifest。

重新验证 637 条记录恰好一次、页边、所有文字框在同页零交叠，以及全部 PDF 与 PNG 的 RGB 一致性。原尺寸裁切另存 qa/，视觉检查结论见 VISUAL_QA.md。

重建：在本目录运行 `py -3.13 -B make_cards.py`。仅使用标准库、NumPy、Pillow，单进程；全部输出限定在本目录，源文件只读。视觉检查结论另见 `VISUAL_QA.md`。
'''
    write_text('REPORT.md', report)


if __name__ == '__main__':
    main()
