"""How the games look. They only say what a cell is; this says how that is drawn on this terminal.

The look falls back as everything else here does: quadrants and bevels where the terminal draws
block characters itself, coloured spaces in true colour or 16 colours, and letters without colour.
A board keeps its own dark colours on any theme, so nothing here has to guess the background.
Loaded when a game opens, so nobody who never plays pays for it.
"""

from __future__ import annotations

import functools

from . import ui

Rgb = tuple[int, int, int]
BOARD: Rgb = (32, 35, 44)
SNAKE_FIELD = ((38, 42, 52), (44, 48, 59))
TRACK_FIELD = ((34, 38, 47), (41, 45, 55))      # blocks stack in columns, which are the disc's tracks
SCALES = ((70, 176, 112), (86, 200, 130))
HEAD: Rgb = (140, 236, 170)
EYES: Rgb = (18, 44, 30)
DEAD: Rgb = (236, 96, 96)
FOOD: Rgb = (246, 112, 96)
HEAD_GLYPHS = {"head_up": "▘▝", "head_down": "▖▗", "head_right": " ▝", "head_left": "▘ "}
BLOCKS = {"block0": (236, 96, 96), "block1": (86, 200, 130), "block2": (250, 190, 70),
          "block3": (96, 124, 230), "block4": (200, 110, 220), "block5": (70, 200, 220)}
ANSI16 = {"field": "100", "snake": "42", "tail": "42", "food": "41", "dead": "41", "head_up": "102", "head_down": "102",
          "head_right": "102", "head_left": "102", "block0": "41", "block1": "42", "block2": "43", "block3": "44", "block4": "45", "block5": "46"}
GLYPHS = {"field": "..", "snake": "##", "tail": "++", "food": "<>", "dead": "XX", "head_up": "@@", "head_down": "@@", "head_right": "@@", "head_left": "@@",
          "block0": "[]", "block1": "##", "block2": "()", "block3": "{}", "block4": "%%", "block5": "@@"}
SECTOR_ANSI = ("41", "43", "42", "46", "44", "45")
SUDOKU_TINTS = ((44, 48, 60), (58, 63, 78))
SUDOKU_CURSOR: Rgb = (92, 122, 232)
SUDOKU_SOLVED = ((44, 104, 76), (54, 124, 90))
SUDOKU_INK = {"given": (236, 239, 246), "mine": (120, 214, 244), "wrong": (255, 128, 128), "solved": (236, 248, 240)}
INK_DARK: Rgb = (18, 20, 26)
EMPTY_TILE: Rgb = (50, 54, 66)


def _paint(text: str, fg: Rgb | None = None, bg: Rgb | None = None, bold: bool = False) -> str:
    codes = (["1"] if bold else []) + ([f"38;2;{fg[0]};{fg[1]};{fg[2]}"] if fg else []) + ([f"48;2;{bg[0]};{bg[1]};{bg[2]}"] if bg else [])
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _lighter(rgb: Rgb, share: float = 0.45) -> Rgb:
    return tuple(round(v + (255 - v) * share) for v in rgb)


def _tile_colour(tile: int) -> Rgb:
    """Down the disc's spectrum, violet first, each doubling one step along."""
    return ui.oklch(0.74, 0.13, (0.83 - (tile - 1) * 0.08) % 1.0) if tile else EMPTY_TILE


def _tile(tile: int, tier: str) -> tuple[str, str]:
    from .sectors import label
    text = label(tile).center(6) if tile else " " * 6
    if tier == "plain":
        return f"[{text[1:5] if tile else ' .. '}] ", " " * 7
    if tier == "ansi":
        code = SECTOR_ANSI[(tile - 1) % len(SECTOR_ANSI)] if tile else "100"
        return f"\x1b[{code};97;1m{text}\x1b[0m ", " " * 7
    colour = _tile_colour(tile)
    top = _paint(text, INK_DARK, colour, True) + _paint(" ", None, BOARD)
    if tier == "fine":
        return top, _paint("▀" * 6, colour, BOARD) + _paint(" ", None, BOARD)
    return top, _paint(" " * 7, None, BOARD)


def _sudoku(digit: int, state: str, selected: bool, tint: int, width: int, height: int, tier: str) -> tuple[str, ...]:
    shown = str(digit) if digit else " "
    if tier == "plain":
        if selected:
            text = f">{shown}<"
        elif state == "wrong":
            text = f"!{shown}!"
        elif digit and state == "given":
            text = f" {shown} "
        elif digit:
            text = f"({shown})"
        else:
            text = " . " if tint else " : "
        return (text.center(width),) + (" " * width,) * (height - 1)
    text = shown.center(width)
    if tier == "ansi":
        back = "44" if selected else "42" if state == "solved" else "100" if tint else "40"
        ink = {"given": "97;1", "mine": "96", "wrong": "91;1", "solved": "97;1"}[state]
        return (f"\x1b[{back};{ink}m{text}\x1b[0m",) + (" " * width,) * (height - 1)
    back = SUDOKU_CURSOR if selected else SUDOKU_SOLVED[tint] if state == "solved" else SUDOKU_TINTS[tint]
    ink = _lighter(SUDOKU_INK[state], 0.5) if selected else SUDOKU_INK[state]
    top = _paint(text, ink, back, state in ("given", "solved"))
    if height == 1:
        return (top,)
    if tier == "fine":     # a half row of gap under each cell keeps them apart and nearly square
        return top, _paint("▀" * width, back, BOARD)
    return top, _paint(" " * width, None, BOARD)


@functools.lru_cache(maxsize=None)
def _cell(kind, tint: int, tier: str, field_is_tracks: bool) -> tuple[str, ...]:
    if isinstance(kind, tuple):
        return _sudoku(*kind[1:], tier)
    if kind.startswith("tile"):
        return _tile(int(kind[4:]), tier)
    if tier == "plain":
        return (GLYPHS[kind],)
    if tier == "ansi":
        return (f"\x1b[{ANSI16[kind]}m  \x1b[0m",)
    fine = tier == "fine"
    field = (TRACK_FIELD if field_is_tracks else SNAKE_FIELD)[tint]
    if kind == "field":
        return (_paint("  ", None, field),)
    if kind == "snake":
        return (_paint("  ", None, SCALES[tint]),)
    if kind == "tail":
        return (_paint("▗▖", SCALES[tint], field) if fine else _paint("  ", None, SCALES[tint]),)
    if kind == "food":
        return (_paint("▘ ", _lighter(FOOD, 0.7), FOOD) if fine else _paint("  ", None, FOOD),)     # with a glint on it
    if kind == "dead":
        return (_paint("▚▞", INK_DARK, DEAD) if fine else _paint("  ", None, DEAD),)
    if kind in HEAD_GLYPHS:
        return (_paint(HEAD_GLYPHS[kind], EYES, HEAD) if fine else _paint("  ", None, HEAD),)
    colour = BLOCKS[kind]
    return (_paint("▔▔", _lighter(colour), colour) if fine else _paint("  ", None, colour),)


def _tier(t: ui.Term) -> str:
    return "plain" if not t.color else "ansi" if not t.truecolor else "fine" if t.blocks else "true"


def paint(game, x: int, y: int, t: ui.Term) -> tuple[str, ...]:
    """The rows of one board cell."""
    return paint_kind(game.cell(x, y), x, y, game, t)


def paint_kind(kind, x: int, y: int, game, t: ui.Term) -> tuple[str, ...]:
    return _cell(kind, game.tint(x, y), _tier(t), getattr(game, "tracks", False))
