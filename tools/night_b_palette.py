"""Night colours "B, deep teal" (2026-11-14, chosen in the Disc logo session) for the baked dark-theme art.

The old dark theme was an olive-teal grey (page #161d1c, hue ~186 deg in OKLCH). B moves the grey family to hue
~228 deg and lowers the ground: page #0a1114, second layer #121a1e. One rule maps every old dark-theme grey in the
render scripts, so the drive, desk, trays and shadows keep their relative tones and the page edge meets the art:

  * only the cool greys of the old palette move: OKLCH hue 150-215 deg, chroma < 0.035, lightness < 0.70;
    warm materials (kraft, copper LED, lamp shade, glows), the line colour and coloured parts keep their values,
    so nothing turns grey (the person's rule, see memory lobby-line-style);
  * lightness follows one monotone curve: ground #161d1c -> #0a1114, desk #1f2726 -> #111a1e; faces a step
    brighter than the desk drop less (drive top #222b2a, L .28 -> .245), as in night-compare B; above L 0.6 unchanged;
  * hue -> 228 deg, chroma x 1.35 (B is a touch more saturated than the old grey), at most 0.03;
  * a few exact pairs (the page colours) are pinned so the picture edge equals the CSS value byte for byte.

Paper under the lamp: in B a sheet the lamp falls on is light (#ece6d8 at its brightest, ink #22231f on it); see
LIT_PAPER and the scripts' "sheet_light".

    python tools/night_b_palette.py               # table of every remapped colour in the render scripts
    python tools/night_b_palette.py --apply       # rewrite the dark blocks in place (idempotent: run once)
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUE = 228.0
# the ground drops most (L .223 -> .172); lit faces just above the desk tone drop less, so a drive reads brighter
# against the desk than before (night-compare B: desk .211, drive faces .203 / .253 / .300)
L_CURVE = [(0.0, 0.0), (0.129, 0.100), (0.198, 0.155), (0.223, 0.172), (0.265, 0.211), (0.280, 0.245),
           (0.320, 0.290), (0.424, 0.400), (0.60, 0.60), (1.0, 1.0)]
PINNED = {
    "#161d1c": "#0a1114",   # page
    "#1f2827": "#121a1e",   # second layer
    "#1f2726": "#111a1e",   # desk top (night-compare B "desk")
    "#2c3634": "#202d33",   # rule
    "#46514e": "#3a4a51",   # strong rule
    "#ecebe4": "#eef0ee",   # ink
    "#aeb3ab": "#a6b0b3",   # ink 2
    "#7f8780": "#7b868a",   # ink 3
    "#d9a75c": "#e0ab5c",   # copper (CSS; the baked LED keeps its own colour, see KEEP)
}
KEEP = {"#d9a75c"}          # in the render scripts the copper LED is a lit lamp, not text: unchanged
# lit paper (the form sheets on the new-work, presets and past-works pages): the paper theme's sheet tones, lit by
# its own light so the brightest point is about #ece6d8 and it falls off away from the lamp
LIT_PAPER = dict(sheet="#f9f8f4", sheet_edge="#dfdbd3")


def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _l2s(c):
    c = min(1.0, max(0.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_oklch(h):
    h = h.lstrip("#")
    r, g, b = (_s2l(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def from_oklch(L, C, H):
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return "#" + "".join("%02x" % round(_l2s(x) * 255) for x in (r, g, bl))


def _curve(L):
    for (x0, y0), (x1, y1) in zip(L_CURVE, L_CURVE[1:]):
        if L <= x1:
            return y0 + (y1 - y0) * (L - x0) / (x1 - x0)
    return L


def remap(h, css=False):
    """old dark-theme colour -> B; colours outside the old grey family come back unchanged"""
    h = h.lower()
    if h in PINNED and (css or h not in KEEP):
        return PINNED[h]
    L, C, H = to_oklch(h)
    if not (150.0 <= H <= 215.0 and C < 0.035 and L < 0.70) and C > 0.004:
        return h
    if L >= 0.70:
        return h
    return from_oklch(_curve(L), min(0.03, C * 1.35), HUE)


HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
# (file, regex that finds the start of the dark block); the block ends at the first line indented less than or as
# much as its opening line that closes it. Roles listed in SKIP keep their colours (coloured materials).
SCRIPTS = [
    ("discprobe/web/home/render_burner.py", r'^    "dark": dict\('),
    ("discprobe/web/home/render_burner_layers.py", r'^    "dark": dict\('),
    ("discprobe/web/home/interior/render_interior.py", r'^    "dark": dict\('),
    ("discprobe/web/home/caltop/render_caltop.py", r'^    "dark": dict\('),
    ("discprobe/web/home/caltop/render_caltop_anim.py", r'^    "dark": dict\('),
    ("discprobe/web/home/newplan/render_newplan.py", r'^    "dark": dict\('),
    ("discprobe/web/home/faxnews/render_faxnews.py", r'^    "dark": dict\('),
]
SKIP_ROLES = ("pcb=", "lens=", "glow_", "line=", "sign_text=")


def rewrite_block(text, start_re):
    lines = text.split("\n")
    out, i, n = [], 0, 0
    pat = re.compile(start_re)
    while i < len(lines):
        if pat.match(lines[i]):
            head = HEX.sub(lambda m: remap(m.group(0)), lines[i])     # roles on the opening line (PROP_STYLE)
            n += head != lines[i]
            out.append(head)
            indent = len(lines[i]) - len(lines[i].lstrip())
            i += 1
            while i < len(lines):
                ln = lines[i]
                if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
                    break
                if not any(ln.strip().startswith(s) for s in SKIP_ROLES):
                    new = HEX.sub(lambda m: remap(m.group(0)), ln)
                    n += new != ln
                    ln = new
                out.append(ln)
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), n


def table():
    seen = {}
    for rel, start in SCRIPTS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        new, _ = rewrite_block(text, start)
        for a, b in zip(HEX.findall(text), HEX.findall(new)):
            if a.lower() != b:
                seen.setdefault((a.lower(), b), []).append(Path(rel).name)
    for (a, b), files in sorted(seen.items()):
        La, Ca, Ha = to_oklch(a)
        Lb, Cb, Hb = to_oklch(b)
        print(f"{a} -> {b}   L {La:.3f}->{Lb:.3f}  C {Ca:.4f}->{Cb:.4f}  H {Ha:5.1f}->{Hb:5.1f}  {','.join(sorted(set(files)))}")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        for rel, start in SCRIPTS:
            p = ROOT / rel
            new, n = rewrite_block(p.read_text(encoding="utf-8"), start)
            p.write_text(new, encoding="utf-8")
            print(f"{rel}: {n} lines")
    elif len(sys.argv) > 1 and sys.argv[1].startswith("#"):
        for h in sys.argv[1:]:
            print(h, "->", remap(h, css=True))
    else:
        table()
