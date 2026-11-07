"""The opening screen of `guide`: a small disc catching the light.

The disc is built from coloured spaces, with slashes and a few symbols on top: two rainbow wedges
sweep round like the light on a real disc, a streak of / and \\ marks their centre, and small
sparks flash where they pass. A frame is built off screen and sent in one write, and the frame
shown follows the clock, so a slow terminal skips frames instead of running long. It falls back
step by step: half blocks in true colour where the terminal draws them itself, true colour, 16
colours, then plain ASCII, which still turns unless motion is off. With half blocks each cell holds
two square pixels, and the light works as it does on a disc: white along the mirror angle, then the
first order's spectrum, violet to red, and the steps of `guide` done so far dye the track outward.
A window too small for the disc gets the title alone. Only `guide` shows it, never a measuring command.
"""

from __future__ import annotations

import functools
import math
import shutil
import sys
import time

from . import i18n, ui

DISC_W, DISC_H = 25, 12
HOLE, HUB, RIM = 0.14, 0.27, 0.95
CLEAR, MIRROR = 0.21, 0.30      # the see-through ring and the shiny one between the hole and the track
WEDGE = 0.66                    # half the width of the band of light, in radians
TWIST = 0.5                     # how far it bends between hub and rim
CORE = 0.14                     # the white part, as a share of the band
SHOW_S = 1.0
FRAME_S = 0.04
STILL_ANGLE = 0.7
# How far round the colour wheel each kind of disc's light is turned: a CD is cyan and blue, a DVD violet and pink.
HUE_TURN = {"cd": 0.0, "dvd": 0.13}
TRACK_HUE = {"cd": (0.8, 0.78), "dvd": (0.9, 0.88)}     # burned and unburned
TITLE = (r"     _ _                                _",
         r"  __| (_)___  ___       _ __  _ __ ___ | |__   ___",
         r" / _` | / __|/ __|_____| '_ \| '__/ _ \| '_ \ / _ \ ",
         r"| (_| | \__ \ (_|_____| |_) | | | (_) | |_) |  __/",
         r" \__,_|_|___/\___|    | .__/|_|  \___/|_.__/ \___|",
         r"                      |_|")
# The title in blocks, where half blocks and true colour work: eight rows of pixels, two to a cell.
BLOCK_LETTERS = (
    ("....#", "....#", ".####", "#...#", "#...#", "#...#", ".####", "....."),
    ("#", ".", "#", "#", "#", "#", "#", "."),
    (".....", ".....", ".####", "#....", ".###.", "....#", "####.", "....."),
    ("....", "....", ".###", "#...", "#...", "#...", ".###", "...."),
    ("...", "...", "...", "...", "###", "...", "...", "..."),
    (".....", ".....", "####.", "#...#", "#...#", "####.", "#....", "#...."),
    (".....", ".....", "#.###", "##...", "#....", "#....", "#....", "....."),
    (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###.", "....."),
    ("#....", "#....", "####.", "#...#", "#...#", "#...#", "####.", "....."),
    (".....", ".....", ".###.", "#...#", "#####", "#....", ".####", "....."),
)
BLOCK_ROWS = tuple(".".join(letter[y] for letter in BLOCK_LETTERS) for y in range(8))
TITLE_HUES = {"cd": (0.56, 0.74), "dvd": (0.8, 1.02)}   # across the word, from the first letter to the last
SWEEP_WIDTH = 8.0
TAGLINE = "read timing -> disc geometry -> pictures on discs"
TITLE_W = max(len(line) for line in TITLE)
GAP = 2
ANSI16_BG = ("41", "43", "42", "46", "44", "45")   # a rainbow in six steps
SPARKS = "*+."


def _streak(theta: float) -> str:
    """The glyph running outward along this direction; y grows downward on screen."""
    step = int(((theta % math.pi) + math.pi / 8) / (math.pi / 4)) % 4
    return ("-", "\\", "|", "/")[step]


def _cell(x: float, y: float, angle: float, media: str = "dvd"):
    """(glyph, hue, light, part) of one character cell, or None outside the disc and in its hole."""
    radius = math.hypot(x, y)
    if radius > 1 or radius < HOLE:
        return None
    if radius < HUB:
        return " ", 0.0, 0.0, "hub"
    theta = math.atan2(y, x)
    light = abs(math.cos(theta - angle)) ** 10
    hue = (radius * 1.4 + theta / math.tau + HUE_TURN[media]) % 1.0
    if radius > RIM:
        return " ", hue, max(light, 0.25), "rim"
    glyph = " "
    if light > 0.72:
        glyph = _streak(theta)
    elif light > 0.25 and (int(radius * 47) * 7 + int((theta + math.pi) * 13)) % 11 == 0:
        glyph = SPARKS[int(radius * 17) % len(SPARKS)]
    return glyph, hue, light, "body"


def _paint(glyph: str, hue: float, light: float, part: str, t: ui.Term) -> str:
    if not t.color:
        if part == "hub":
            return "."
        if part == "rim":
            return "o"
        return glyph if glyph != " " else ":"
    if t.truecolor:
        if part == "hub":
            r, g, b = 70, 74, 84
        else:
            r, g, b = ui.oklch(0.38 + 0.4 * light, 0.03 + 0.11 * light, hue)
        return f"\x1b[48;2;{r};{g};{b};97m{glyph}\x1b[0m"
    if part == "hub" or light < 0.2:
        return f"\x1b[100;97m{glyph}\x1b[0m"
    return f"\x1b[{ANSI16_BG[int(hue * len(ANSI16_BG)) % len(ANSI16_BG)]};97m{glyph}\x1b[0m"


def _fine(t: ui.Term) -> bool:
    return t.blocks and t.truecolor


@functools.lru_cache(maxsize=None)
def _pixels(burned: float, media: str = "dvd") -> tuple:
    """(radius, angle, share of the pixel on the disc, colour without light) of each half cell, worked out once."""
    pixels = []
    height = DISC_H * 2
    burned_to = MIRROR + (RIM - MIRROR) * burned
    burned_hue, plain_hue = TRACK_HUE[media]
    for py in range(height):
        for px in range(DISC_W):
            x, y = (px + 0.5 - DISC_W / 2) / (DISC_W / 2), (py + 0.5 - height / 2) / (height / 2)
            corners = [math.hypot(x + dx / DISC_W, y + dy / height) for dx in (-0.5, 0.5) for dy in (-0.5, 0.5)]
            cover = sum(HOLE <= r <= 1 for r in corners) / 4
            radius = math.hypot(x, y)
            if cover == 0:
                pixels.append(None)
                continue
            if radius < CLEAR:
                base = ui.oklch(0.33, 0.005, 0.7)
            elif radius < MIRROR:
                base = ui.oklch(0.68, 0.012, 0.7)
            elif radius > RIM:
                base = ui.oklch(0.52, 0.015, 0.7)
            elif radius < burned_to:
                base = ui.oklch(0.27, 0.06, burned_hue)
            else:
                base = ui.oklch(0.42, 0.02, plain_hue)
            pixels.append((radius, math.atan2(y, x), cover, base))
    return tuple(pixels)


@functools.lru_cache(maxsize=None)
def _spectrum() -> tuple:
    return tuple(ui.oklch(0.74, 0.15, i / 64) for i in range(64))


def _lit(pixel, angle: float, turn: float = 0.0) -> tuple[int, int, int] | None:
    if pixel is None:
        return None
    radius, theta, cover, base = pixel
    off = abs((theta - angle + TWIST * radius + math.pi / 2) % math.pi - math.pi / 2) / WEDGE
    if off >= 1 or radius < CLEAR:
        r, g, b = base
    else:
        glow = 1 - off ** 4     # holds to the red end, then falls away
        tone = _spectrum()[int((0.83 + turn - 0.75 * off + 0.1 * (radius - 0.6)) * 64) % 64]
        white = max(0.0, 1 - off / CORE) ** 2
        r, g, b = ((base[i] * (1 - glow) + tone[i] * glow) * (1 - white) + 255 * white for i in range(3))
    return int(r * cover) & 248, int(g * cover) & 248, int(b * cover) & 248      # steps, so most cells repeat between frames


def disc_cells(angle: float, burned: float = 0.0, media: str = "dvd") -> list[list[tuple[str, str]]]:
    """Rows of (code, glyph). A cell is two pixels, the upper in the glyph's colour and the lower behind it."""
    pixels = _pixels(round(burned, 2), media)
    turn = HUE_TURN[media]
    rows = []
    for row in range(DISC_H):
        cells = []
        for col in range(DISC_W):
            top = _lit(pixels[2 * row * DISC_W + col], angle, turn)
            low = _lit(pixels[(2 * row + 1) * DISC_W + col], angle, turn)
            if top and low:
                cells.append((f"38;2;{top[0]};{top[1]};{top[2]};48;2;{low[0]};{low[1]};{low[2]}", "▀"))
            elif top or low:
                r, g, b = top or low
                cells.append((f"38;2;{r};{g};{b}", "▀" if top else "▄"))
            else:
                cells.append(("", " "))
        rows.append(cells)
    return rows


def _changed(old: list[tuple[str, str]], new: list[tuple[str, str]], start: int = 1) -> str:
    """Only the cells that differ, each stretch after a move to its column."""
    out, i = [], 0
    while i < len(new):
        if new[i] == old[i]:
            i += 1
            continue
        end = i
        while end < len(new) and new[end] != old[end]:
            end += 1
        out.append(f"\x1b[{start + i}G{ui._paint_runs(new[i:end])}")
        i = end
    return "".join(out)


def disc_rows(angle: float, t: ui.Term, burned: float = 0.0, media: str = "dvd") -> list[str]:
    if _fine(t):
        return [ui._paint_runs(cells) for cells in disc_cells(angle, burned, media)]
    rows = []
    for row in range(DISC_H):
        y = (row - (DISC_H - 1) / 2) / (DISC_H / 2)
        out = []
        for col in range(DISC_W):
            cell = _cell((col - (DISC_W - 1) / 2) / (DISC_W / 2), y, angle, media)
            out.append(" " if cell is None else _paint(*cell, t))
        rows.append("".join(out))
    return rows


def block_title(media: str = "dvd", now: float | None = None) -> list[list[tuple[str, str]]]:
    """Rows of (code, glyph) for the word in blocks, coloured along it. While the disc turns, light runs along it too."""
    first, last = TITLE_HUES[media]
    width = len(BLOCK_ROWS[0])
    rows = []
    for y in range(0, len(BLOCK_ROWS), 2):
        cells = []
        for x in range(width):
            top, low = BLOCK_ROWS[y][x] == "#", BLOCK_ROWS[y + 1][x] == "#"
            glow = 0.0 if now is None else max(0.0, 1 - abs(x - width * now / SHOW_S * 1.2) / SWEEP_WIDTH)
            r, g, b = ui.oklch(0.74 + 0.16 * glow, 0.15 - 0.1 * glow, first + (last - first) * x / (width - 1))
            glyph = "█" if top and low else "▀" if top else "▄" if low else " "
            cells.append((f"38;2;{r & 248};{g & 248};{b & 248}" if glyph != " " else "", glyph))
        rows.append(cells)
    return rows


def _title_rows(t: ui.Term, height: int, now: float | None, media: str = "dvd") -> list[str]:
    def paint(line):
        return t.style(line, "cyan") if now is None else ui.sweep(line, now, t, "cyan")
    if _fine(t):
        spare = " " * (TITLE_W - len(BLOCK_ROWS[0]))
        word = [ui._paint_runs(cells) + spare for cells in block_title(media, now)]
    else:
        word = [paint(line.ljust(TITLE_W)) for line in TITLE]
    lines = word + [t.style(i18n.pad(i18n.tr(TAGLINE), TITLE_W), "dim")]
    top = max(0, (height - len(lines)) // 2)
    blank = " " * TITLE_W
    return ([blank] * top + lines + [blank] * height)[:height]


def frame(angle: float, t: ui.Term, columns: int, now: float | None = None, burned: float = 0.0, media: str = "dvd") -> list[str]:
    """The screen for one angle, shaped to the terminal width."""
    if columns > DISC_W + GAP + TITLE_W:
        return [d + " " * GAP + title for d, title in zip(disc_rows(angle, t, burned, media), _title_rows(t, DISC_H, now, media))]
    tagline = i18n.tr(TAGLINE)
    if columns > TITLE_W:
        return [t.style(line, "cyan") for line in TITLE] + [t.style(tagline, "dim")]
    return [t.style("disc-probe", "cyan"), t.style(i18n.fit(tagline, max(columns - 1, 10)), "dim")]


def _next_frame(angle: float, t: ui.Term, columns: int, seen: dict, now: float | None, burned: float, media: str = "dvd") -> str:
    """What a frame has to send, from the top row down. Half blocks cost two colours a cell, so only changes go out."""
    if not _fine(t):
        return "\n".join(frame(angle, t, columns, now, burned, media))
    rows = []
    blank = [("", " ")] * DISC_W
    for y, (cells, title) in enumerate(zip(disc_cells(angle, burned, media), _title_rows(t, DISC_H, now, media))):
        out = _changed(seen.get(y, blank), cells)
        if seen.get(("title", y)) != title:
            out += f"\x1b[{DISC_W + GAP + 1}G{title}"
        seen[y], seen["title", y] = cells, title
        rows.append(out)
    return "\n".join(rows)


def show(t: ui.Term | None = None, pause=time.sleep, now=time.monotonic, burned: float = 0.0, media: str = "dvd") -> None:
    """Draw the opening screen. Only at a terminal; only moves if the terminal can. `burned` is how far along the steps are."""
    t = t or ui.term()
    if not t.interactive:
        return
    size = shutil.get_terminal_size((80, 24))
    write = t.stream.write
    roomy = size.columns > DISC_W + GAP + TITLE_W and size.lines > DISC_H + 2
    if not roomy and size.columns > DISC_W + GAP + TITLE_W:     # too low for the disc: the title alone
        write("\n".join(frame(STILL_ANGLE, t, DISC_W + GAP + TITLE_W)) + "\n\n")
        t.stream.flush()
        return
    if t.animate and roomy:
        write("\x1b[?25l")
        try:
            write("\n" * (DISC_H - 1))
            start = now()
            seen = {}
            sync_start, sync_end = (ui.SYNC_START, ui.SYNC_END) if t.sync else ("", "")
            while True:
                spent = now() - start
                eased = 1 - (1 - min(spent / SHOW_S, 1.0)) ** 2     # sweeps fast, settles soft
                angle = STILL_ANGLE + math.pi * (eased - 1)
                settled = spent >= SHOW_S
                body = _next_frame(angle, t, size.columns, seen, None if settled else spent, burned, media)
                write(f"{sync_start}\r\x1b[{DISC_H - 1}A{body}{sync_end}")
                t.stream.flush()
                if settled:
                    break
                pause(FRAME_S)
        except KeyboardInterrupt:
            pass        # Ctrl+C only skips the show
        finally:
            write("\x1b[?25h\n\n")
            t.stream.flush()
        return
    write("\n".join(frame(STILL_ANGLE, t, size.columns, None, burned, media)) + "\n\n")
    t.stream.flush()


if __name__ == "__main__":
    show(ui.Term(sys.stdout))
