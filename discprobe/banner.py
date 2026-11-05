"""The opening screen of `guide`: a small disc catching the light, in plain ASCII.

The same idea as a real disc's rainbow wedge: two bright lobes sweep round while the colour
follows the radius. Each frame is built off screen and sent in one write, so nothing flickers.
It falls back step by step: true colour, 16 colours, then one still frame with no escapes at all.
Only `guide` shows it, never a measuring command.
"""

from __future__ import annotations

import colorsys
import math
import shutil
import sys
import time

from . import ui

DISC_W, DISC_H = 21, 9
RAMP = ".:-=+*#%"
HOLE, RIM = 0.17, 0.93
FRAMES = 18
FRAME_S = 0.04
STILL_ANGLE = 0.7
TITLE = (r"     _ _                                _",
         r"  __| (_)___  ___       _ __  _ __ ___ | |__   ___",
         r" / _` | / __|/ __|_____| '_ \| '__/ _ \| '_ \ / _ \ ",
         r"| (_| | \__ \ (_|_____| |_) | | | (_) | |_) |  __/",
         r" \__,_|_|___/\___|    | .__/|_|  \___/|_.__/ \___|",
         r"                      |_|")
TAGLINE = "read timing -> disc geometry -> pictures on discs"
TITLE_W = max(len(line) for line in TITLE)
GAP = 2
ANSI16 = ("31", "33", "32", "36", "34", "35")   # a rainbow in six steps


def _cell(x: float, y: float, angle: float):
    """(glyph, hue, brightness) of one character cell, or None outside the disc."""
    radius = math.hypot(x, y)
    if radius > 1 or radius < HOLE:
        return None
    theta = math.atan2(y, x)
    bright = abs(math.cos(theta - angle)) ** 8
    if radius > RIM:
        bright = max(bright, 0.3)
    return RAMP[min(int(bright * len(RAMP)), len(RAMP) - 1)], (radius * 1.4 + theta / math.tau) % 1.0, bright


def _paint(glyph: str, hue: float, bright: float, t: ui.Term) -> str:
    if not t.color:
        return glyph
    if t.truecolor:
        level = 0.25 + 0.75 * bright
        r, g, b = (int(255 * v) for v in colorsys.hsv_to_rgb(hue, 0.15 + 0.75 * bright, level))
        return f"\x1b[38;2;{r};{g};{b}m{glyph}\x1b[0m"
    if bright < 0.2:
        return f"\x1b[2m{glyph}\x1b[0m"
    return f"\x1b[{ANSI16[int(hue * len(ANSI16)) % len(ANSI16)]}m{glyph}\x1b[0m"


def disc_rows(angle: float, t: ui.Term) -> list[str]:
    rows = []
    for row in range(DISC_H):
        y = (row - (DISC_H - 1) / 2) / (DISC_H / 2)
        out = []
        for col in range(DISC_W):
            cell = _cell((col - (DISC_W - 1) / 2) / (DISC_W / 2), y, angle)
            out.append(" " if cell is None else _paint(*cell, t))
        rows.append("".join(out))
    return rows


def _title_rows(t: ui.Term, height: int) -> list[str]:
    lines = [t.style(line.ljust(TITLE_W), "cyan") for line in TITLE] + [t.style(TAGLINE.ljust(TITLE_W), "dim")]
    top = max(0, (height - len(lines)) // 2)
    blank = " " * TITLE_W
    return ([blank] * top + lines + [blank] * height)[:height]


def frame(angle: float, t: ui.Term, columns: int) -> list[str]:
    """The screen for one angle, shaped to the terminal width."""
    if columns > DISC_W + GAP + TITLE_W:
        return [d + " " * GAP + title for d, title in zip(disc_rows(angle, t), _title_rows(t, DISC_H))]
    if columns > TITLE_W:
        return [t.style(line, "cyan") for line in TITLE] + [t.style(TAGLINE, "dim")]
    return [t.style("disc-probe", "cyan"), t.style(TAGLINE[:max(columns - 1, 10)], "dim")]


def show(t: ui.Term | None = None, pause=time.sleep) -> None:
    """Draw the opening screen. Only at a terminal; only moves if the terminal can."""
    t = t or ui.term()
    if not t.interactive:
        return
    columns = shutil.get_terminal_size((80, 24)).columns
    write = t.stream.write
    wide = columns > DISC_W + GAP + TITLE_W
    if t.animate and wide:
        write("\x1b[?25l")
        try:
            write("\n" * (DISC_H - 1))
            for i in range(FRAMES):
                eased = 1 - (1 - i / (FRAMES - 1)) ** 2     # sweeps fast, settles soft
                angle = STILL_ANGLE + math.pi * (eased - 1)
                write(f"\r\x1b[{DISC_H - 1}A" + "\n".join(frame(angle, t, columns)))
                t.stream.flush()
                pause(FRAME_S)
        except KeyboardInterrupt:
            pass        # Ctrl+C only skips the show
        finally:
            write("\x1b[?25h\n\n")
            t.stream.flush()
        return
    write("\n".join(frame(STILL_ANGLE, t, columns)) + "\n\n")
    t.stream.flush()


if __name__ == "__main__":
    show(ui.Term(sys.stdout))
