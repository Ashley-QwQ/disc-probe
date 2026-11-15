"""Disc family marks: app icons, bare monograms and wordmarks for Disc Probe / Lab / Neo.

Letters are Archivo (wght 800, wdth 125) outlines taken from the font shipped in discprobe/web/fonts,
so the SVGs need no font. The D is drawn: an ink stem with a disc standing in it, like a disc
half out of a drive's slot. Only the disc has colour; each product has its own slice of the
diffraction colours (the page's --dvd / --cd / --bd gradients).

    python discprobe/web/brand/build_marks.py            # writes the SVGs and sheet.html beside this file
    python discprobe/web/brand/build_marks.py --explore  # also writes explore.html (construction variants)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
FONT = HERE.parent / "fonts" / "Archivo-VF.ttf"

# ---- the page's colours (discprobe/web/home/index.html) ----
PAPER = {"bg": "#ebe7e0", "ink": "#1d1b18", "rule": "#cfc9bf"}
INK = {"bg": "#0a1114", "ink": "#eef0ee", "rule": "#202d33"}   # the night ground (STYLE.md): deep petrol
PRODUCTS = {
    "probe": {"name": "PROBE", "letter": "P", "title": "Disc Probe",
              "paper": ["#7262c6", "#8d58b7", "#a150a1", "#b04985", "#ba4765"],
              "ink": ["#a79aff", "#c58ff3", "#dc86db", "#ee81bc", "#f87f9a"]},
    "lab": {"name": "LAB", "letter": "L", "title": "Disc Lab",
            "paper": ["#2f7f95", "#2f9396", "#3c9f88", "#57a874"],
            "ink": ["#6cc6dc", "#6fd3cf", "#82dbb7", "#a3e29b"]},
    "neo": {"name": "NEO", "letter": "N", "title": "Disc Neo",
            "paper": ["#c99a52", "#bf8448", "#a8693c", "#8a5a2e"],
            "ink": ["#ecca86", "#e4bb72", "#d9a75c", "#c98b4f"]},
}

# ---- the drawn D ----
D_OFFSET = 0.125  # disc centre, in cap heights right of the stem's edge. The disc's edge passes through
                  # the stem's two right corners, so its radius is hypot(.5, offset): at .125 it stands 1.5 %
                  # past the cap line and the baseline, the overshoot a round letter has anyway
HUB = 0.40        # where the data area starts (24 mm of 60): inside it the disc is clear
HOLE = 0.125      # centre hole (7.5 mm of 60)
GAP = 0.105       # between the D and the second letter, in cap heights
TRACK = 0.012     # wordmark letter-spacing, in em

_font = instancer.instantiateVariableFont(TTFont(FONT), {"wght": 800, "wdth": 125})
_gs = _font.getGlyphSet()
_cmap = _font.getBestCmap()
UPM = _font["head"].unitsPerEm
CAP = _font["OS/2"].sCapHeight


def n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def bounds(ch: str):
    pen = BoundsPen(_gs)
    _gs[_cmap[ord(ch)]].draw(pen)
    return pen.bounds


def advance(ch: str) -> float:
    return _font["hmtx"][_cmap[ord(ch)]][0]


def glyph(ch: str, x: float, base: float, k: float) -> str:
    """Path data for one letter, its origin at (x, base), k px per font unit."""
    svg_pen = SVGPathPen(_gs, ntos=n)
    _gs[_cmap[ord(ch)]].draw(TransformPen(svg_pen, (k, 0, 0, -k, x, base)))
    return svg_pen.getCommands()


def right_of(cx: float, cy: float, r: float, x: float) -> str:
    """The part of a circle to the right of the vertical line at x."""
    if cx - r >= x:
        return (f"M{n(cx - r)} {n(cy)}A{n(r)} {n(r)} 0 1 1 {n(cx + r)} {n(cy)}"
                f"A{n(r)} {n(r)} 0 1 1 {n(cx - r)} {n(cy)}Z")
    h = math.sqrt(r * r - (cx - x) ** 2)
    return f"M{n(x)} {n(cy - h)}A{n(r)} {n(r)} 0 {1 if cx > x else 0} 1 {n(x)} {n(cy + h)}Z"


STEM = bounds("I")[2] - bounds("I")[0]   # the weight's own stem, in font units


def drawn_d(x: float, base: float, cap_px: float, grad: str, ink: str, *, offset: float = D_OFFSET,
            hub: float = HUB) -> tuple[str, float]:
    """The D: stem and disc. Returns (svg, width)."""
    k = cap_px / CAP
    s = STEM * k
    r = math.hypot(0.5, offset) * cap_px
    cx, cy = x + s + offset * cap_px, base - cap_px / 2
    edge = x + s - 0.01   # tucked a hair under the stem so no seam shows
    disc = right_of(cx, cy, r, edge) + right_of(cx, cy, hub * r, edge)
    return (f'<path fill="url(#{grad})" fill-rule="evenodd" d="{disc}"/>'
            f'<rect x="{n(x)}" y="{n(base - cap_px)}" width="{n(s)}" height="{n(cap_px)}" fill="{ink}"/>'), s + offset * cap_px + r


def d_width(offset: float = D_OFFSET) -> float:
    """In cap heights."""
    return STEM / CAP + offset + math.hypot(0.5, offset)


def gradient(gid: str, stops: list[str], y0: float, y1: float) -> str:
    st = "".join(f'<stop offset="{n(i / (len(stops) - 1))}" stop-color="{c}"/>' for i, c in enumerate(stops))
    return (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="{n(y0)}" x2="0" y2="{n(y1)}">'
            f"{st}</linearGradient>")


def monogram(letter: str, x: float, base: float, cap_px: float, gid: str, ink: str, **kw) -> tuple[str, float]:
    k = cap_px / CAP
    d, w = drawn_d(x, base, cap_px, gid, ink, **kw)
    b = bounds(letter)
    lx = x + w + GAP * cap_px - b[0] * k
    return d + f'<path fill="{ink}" d="{glyph(letter, lx, base, k)}"/>', w + GAP * cap_px + (b[2] - b[0]) * k


def monogram_width(letter: str, offset: float = D_OFFSET) -> float:
    """In cap heights."""
    b = bounds(letter)
    return d_width(offset) + GAP + (b[2] - b[0]) / CAP


def wordmark(word: str, x: float, base: float, cap_px: float, gid: str, ink: str, **kw) -> tuple[str, float]:
    """The drawn D, then ISC, a word space, and the product's name."""
    k = cap_px / CAP
    d, w = drawn_d(x, base, cap_px, gid, ink, **kw)
    pen = x + w + (advance("D") - bounds("D")[2]) * k * 0.8
    paths, last = [], pen
    for ch in "ISC " + word:
        if ch == " ":
            pen += 0.30 * UPM * k
            continue
        paths.append(glyph(ch, pen, base, k))
        last = pen + bounds(ch)[2] * k
        pen += (advance(ch) + TRACK * UPM) * k
    return d + f'<path fill="{ink}" d="{"".join(paths)}"/>', last - x


def svg(w: float, h: float, body: str, defs: str = "", title: str = "") -> str:
    t = f"<title>{title}</title>" if title else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n(w)} {n(h)}" width="{n(w)}" height="{n(h)}" role="img">'
            f"{t}<defs>{defs}</defs>{body}</svg>")


# every tile uses one cap height, set by the widest pair, so the three sit as a family
TILE = 256


def tile(key: str, theme: str, uid: str = "", small: bool = False, **kw) -> str:
    """The app icon. small=True is the drawing for 16 to 32 px: bigger letters, no hairline."""
    p, c = PRODUCTS[key], (PAPER if theme == "paper" else INK)
    gid = f"g-{key}-{theme}{uid}"
    offset = kw.get("offset", D_OFFSET)
    widest = max(monogram_width(q["letter"], offset) for q in PRODUCTS.values())
    cap = (0.86 if small else 0.74) * TILE / widest
    w = monogram_width(p["letter"], offset) * cap
    base = TILE / 2 + cap / 2
    body, _ = monogram(p["letter"], (TILE - w) / 2, base, cap, gid, c["ink"], **kw)
    rx = TILE * (0.17 if small else 0.14)
    plate = f'<rect width="{TILE}" height="{TILE}" rx="{n(rx)}" fill="{c["bg"]}"/>'
    if not small:
        plate += (f'<rect x="1" y="1" width="{TILE - 2}" height="{TILE - 2}" rx="{n(rx - 1)}" fill="none" '
                  f'stroke="{c["rule"]}" stroke-width="2"/>')
    return svg(TILE, TILE, plate + body, gradient(gid, p[theme], base - cap, base), p["title"])


def bare(key: str, theme: str, uid: str = "", **kw) -> str:
    p, c = PRODUCTS[key], (PAPER if theme == "paper" else INK)
    gid = f"m-{key}-{theme}{uid}"
    cap, pad = 100.0, 6.0
    body, w = monogram(p["letter"], pad, pad + cap, cap, gid, c["ink"], **kw)
    return svg(w + 2 * pad, cap + 2 * pad, body, gradient(gid, p[theme], pad, pad + cap), p["title"])


def lockup(key: str, theme: str, uid: str = "", **kw) -> str:
    p, c = PRODUCTS[key], (PAPER if theme == "paper" else INK)
    gid = f"w-{key}-{theme}{uid}"
    cap, pad = 100.0, 6.0
    body, w = wordmark(p["name"], pad, pad + cap, cap, gid, c["ink"], **kw)
    return svg(w + 2 * pad, cap + 2 * pad, body, gradient(gid, p[theme], pad, pad + cap), p["title"])


def explore() -> str:
    rows = []
    variants = [
        ("half disc, colour to the hole", dict(offset=0.0, hub=HOLE)),
        ("half disc, clear hub", dict(offset=0.0)),
        ("offset .125, clear hub", dict(offset=0.125)),
        ("offset .20, clear hub", dict(offset=0.20)),
        ("offset .30, clear hub", dict(offset=0.30)),
    ]
    for i, (label, kw) in enumerate(variants):
        cells = "".join(f'<div class="c">{tile(k, "paper", f"-x{i}", **kw)}</div>' for k in PRODUCTS)
        small = "".join(f'<div class="c s">{tile(k, "paper", f"-y{i}", **kw)}</div>' for k in PRODUCTS)
        rows.append(f"<section><h2>{label}</h2><div class='r'>{cells}{small}</div></section>")
    css = ("body{margin:24px;background:#f6f4ef;font:14px system-ui;color:#1d1b18}h2{font-size:14px;margin:18px 0 8px}"
           ".r{display:flex;gap:16px;align-items:end}.c svg{width:150px;height:150px;display:block}"
           ".c.s svg{width:32px;height:32px}")
    return f"<!doctype html><meta charset=utf-8><title>explore</title><style>{css}</style>" + "".join(rows)


SHEET_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#ebe7e0;color:#1d1b18;font:15px/1.6 system-ui,"Segoe UI","Microsoft YaHei UI","PingFang SC",sans-serif}
main{max-width:1120px;margin:0 auto;padding:48px 32px 96px}
h1{font-size:28px;margin:0 0 4px;font-weight:800}
h2{font-size:18px;margin:56px 0 4px;font-weight:700}
p{margin:0 0 16px;color:#5d5850;max-width:64ch}
.plate{display:flex;flex-wrap:wrap;align-items:center;gap:32px;padding:32px;border:1px solid #cfc9bf}
.plate + .plate{border-top:0}
.plate.white{background:#fbfaf7}.plate.paper{background:#ebe7e0}
.plate.ink{background:#0a1114;border-color:#0a1114}.plate.black{background:#030506;border-color:#030506}
.plate svg{display:block;height:auto}
.t svg{width:176px}.m svg{height:72px;width:auto}.w svg{height:44px;width:auto}
.m{gap:72px}
.col{display:grid;gap:28px}
.ramp{display:flex;flex-wrap:wrap;align-items:flex-end;gap:20px}
.ramp div{display:grid;justify-items:center;gap:6px;font-size:12px;color:#8a847a}
.black .ramp div{color:#7f8780}
.pairs{display:grid;gap:24px}
.pair{display:flex;align-items:center;gap:18px}
.pair svg:first-child{width:56px}.pair svg:last-child{height:26px;width:auto}
@media (max-width:720px){main{padding:32px 16px 64px}.plate{padding:20px;gap:20px}.t svg{width:96px}.m{gap:32px}
.m svg{height:44px}.w svg{height:24px}.pair svg:last-child{height:18px}.pair svg:first-child{width:44px}}
"""


def sheet() -> str:
    count = iter(range(10_000))

    def uid() -> str:
        return f"-s{next(count)}"

    keys = list(PRODUCTS)
    out = ["<!doctype html><html lang='zh-CN'><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width,initial-scale=1'>",
           "<title>Disc family marks</title><style>", SHEET_CSS, "</style><main>",
           "<h1>Disc 家族标识</h1><p>Disc Probe、Disc Lab、Disc Neo 的应用图标、字母标和组合标。"
           "D 是画出来的：一根墨色竖笔，一张盘立在里面。整套标识只有盘有颜色。</p>"]

    out.append("<h2>应用图标</h2><p>夜色为主，纸色给浅色界面。三个图标用同一个字高，按最宽的一对字母定。</p>")
    for theme, plate in (("ink", "black"), ("paper", "white")):
        out.append(f"<div class='plate {plate} t'>" + "".join(tile(k, theme, uid()) for k in keys) + "</div>")

    out.append("<h2>字母标</h2><p>不带底板，用在页眉、文档角标、盘面印字这些地方。</p>")
    for theme in ("ink", "paper"):
        out.append(f"<div class='plate {theme} m'>" + "".join(bare(k, theme, uid()) for k in keys) + "</div>")

    out.append("<h2>组合标</h2><p>字母标里的 D 就是字标的第一个字母，所以折叠时只是其余字母退场、第二个字母靠过来。</p>")
    for theme in ("ink", "paper"):
        out.append(f"<div class='plate {theme} w'><div class='col'>" + "".join(lockup(k, theme, uid()) for k in keys) + "</div></div>")

    out.append("<h2>图标配字标</h2><p>安装包、README 标题、关于页。</p>")
    for theme, plate in (("ink", "black"), ("paper", "white")):
        out.append(f"<div class='plate {plate}'><div class='pairs'>" + "".join(
            f"<div class='pair'>{tile(k, theme, uid())}{lockup(k, theme, uid())}</div>" for k in keys) + "</div></div>")

    out.append("<h2>小尺寸</h2><p>48 px 及以上用标准稿；32 px 及以下换小尺寸稿：字放大，去掉细边。</p>")
    for theme, plate in (("ink", "black"), ("paper", "white")):
        cells = []
        for k in keys:
            for px in (64, 48, 32, 24, 16):
                art = tile(k, theme, uid(), small=px <= 32).replace('width="256" height="256"', f'width="{px}" height="{px}"', 1)
                cells.append(f"<div>{art}<span>{px}</span></div>")
        out.append(f"<div class='plate {plate}'><div class='ramp'>" + "".join(cells) + "</div></div>")
    out.append("</main></html>")
    return "".join(out)


def write_all() -> list[str]:
    done = []
    for key in PRODUCTS:
        for theme in ("paper", "ink"):
            for kind, art in (("icon", tile(key, theme)), ("icon-small", tile(key, theme, small=True)),
                              ("mark", bare(key, theme)), ("wordmark", lockup(key, theme))):
                name = f"disc-{key}-{kind}-{theme}.svg"
                (HERE / name).write_text(art + "\n", encoding="utf-8")
                done.append(name)
    (HERE / "sheet.html").write_text(sheet(), encoding="utf-8")
    done.append("sheet.html")
    return done


if __name__ == "__main__":
    if "--explore" in sys.argv:
        (HERE / "explore.html").write_text(explore(), encoding="utf-8")
        print("explore.html")
    print(" ".join(write_all()))
