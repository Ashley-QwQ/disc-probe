"""A look at a finished picture design before it is burned: a small disc at the terminal, and what may surprise.

A burn can't be undone, and a picture on its side, all black or stretched shows at a glance on even a small
disc. Everything here only advises, nothing stops an image being made. The limits are first guesses, kept
wide so a warning means something; a few real discs should settle them. Loaded only after a design is made.
"""

from __future__ import annotations

import shutil

import numpy as np

from . import imagedisc, ui

THUMB_PIXELS = 40           # across; half blocks hold two to a cell, plain text one
HOLE_MM = 7.5
PAPER, INK, UNDRAWABLE = (226, 229, 236), (24, 26, 32), (92, 96, 108)
RAMP = " .:-=+*#%@"
MOST_NOTES = 3
SHARE_ALL_DARK, SHARE_ALL_LIGHT = 0.95, 0.02
SHARE_LOST = 0.10
SHARE_GREY = 0.5
SMALLEST_SPAN = 0.25        # of the picture's diameter
SMALLEST_SIDE_PX, LARGEST_SIDE_PX = 600, 20000


def _radius_mm(pixels: int) -> np.ndarray:
    c = (np.arange(pixels) + 0.5) / pixels * 2 * imagedisc.HALF_MM - imagedisc.HALF_MM
    return np.hypot(c[None, :], c[:, None])


def _inner_mm(args) -> float:
    return 26.0 if getattr(args, "media", "dvd") == "cd" else 24.5


def thumbnail(design: np.ndarray, r_min: float, r_max: float, t: ui.Term) -> list[str]:
    """Rows of the disc as it will be drawn, from the data side like the preview. Grey cannot be drawn on."""
    block = imagedisc.SIZE // THUMB_PIXELS
    dark = design[:block * THUMB_PIXELS, :block * THUMB_PIXELS].reshape(THUMB_PIXELS, block, THUMB_PIXELS, block).mean(axis=(1, 3))
    radius = _radius_mm(THUMB_PIXELS)
    on_disc = (radius <= imagedisc.HALF_MM) & (radius >= HOLE_MM)
    drawable = (radius >= r_min) & (radius <= r_max)
    if t.blocks and t.truecolor:
        def pixel(y, x):
            if not on_disc[y, x]:
                return None
            if not drawable[y, x]:
                return UNDRAWABLE
            share = dark[y, x]
            return tuple(round(a + (b - a) * share) for a, b in zip(PAPER, INK))
        rows = []
        for y in range(0, THUMB_PIXELS, 2):
            cells = []
            for x in range(THUMB_PIXELS):
                top, low = pixel(y, x), pixel(y + 1, x)
                if top and low:
                    cells.append((f"38;2;{top[0]};{top[1]};{top[2]};48;2;{low[0]};{low[1]};{low[2]}", "▀"))
                elif top or low:
                    r, g, b = top or low
                    cells.append((f"38;2;{r};{g};{b}", "▀" if top else "▄"))
                else:
                    cells.append(("", " "))
            rows.append("  " + ui._paint_runs(cells))
        return rows
    rows = []
    for y in range(0, THUMB_PIXELS, 2):
        row = ""
        for x in range(THUMB_PIXELS):
            if not on_disc[y, x]:
                row += " "
            elif not drawable[y, x]:
                row += "."
            else:
                row += RAMP[min(int((dark[y, x] + dark[y + 1, x]) / 2 * len(RAMP)), len(RAMP) - 1)]
        rows.append("  " + row)
    return rows


def _source_notes(path: str, diameter_mm: float = 116.0) -> list[str]:
    """What only the original file can tell. A file that can't be read again just adds nothing."""
    from PIL import Image
    notes = []
    limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None       # the file `image` has just loaded, so the same size has to pass here
    try:
        with Image.open(path) as im:
            width, height = im.size
            small = np.asarray(im.convert("L").resize((128, 128)), dtype=np.float32) / 255
    except OSError:
        return []
    finally:
        Image.MAX_IMAGE_PIXELS = limit
    if abs(width / height - 1) > 0.02:
        notes.append(f"{width} x {height} is not square: it keeps its shape, its longer side fills {diameter_mm:g} mm, and the short sides stay light.")
    if max(width, height) < SMALLEST_SIDE_PX:
        notes.append(f"The picture is only {width} x {height} pixels, so its edges will look blocky once enlarged.")
    elif max(width, height) > LARGEST_SIDE_PX:
        notes.append(f"The picture is {width} x {height} pixels, far more than a disc can show, so fine lines may vanish.")
    if ((small > 0.35) & (small < 0.65)).mean() > SHARE_GREY:
        notes.append("Much of the picture is mid grey, and it comes out only black or white. More contrast first may keep the detail.")
    return notes


def notes(design: np.ndarray, picture: str | None, diameter_mm: float, r_min: float, r_max: float) -> list[str]:
    """What may surprise, the most serious first."""
    step = 25
    d = design[::step, ::step]
    radius = _radius_mm(d.shape[0])
    ring = (radius >= r_min) & (radius <= r_max)
    found = []
    share = d[ring].mean() if ring.any() else 0.0
    if share > SHARE_ALL_DARK:
        found.append("Almost all of it came out dark, so little will show on the disc.")
    elif share < SHARE_ALL_LIGHT:
        found.append("Almost all of it came out light, so little will show on the disc.")
    total = d.sum()
    source = _source_notes(picture, diameter_mm) if picture else []
    if total:
        outside, inside = (d & (radius > r_max)).sum() / total, (d & (radius < r_min)).sum() / total
        if outside >= SHARE_LOST:
            found.append(f"About {outside * 100:.0f}% of its dark area falls outside the part of the disc that can be drawn on, so it is cut off.")
        if inside >= SHARE_LOST:
            found.append(f"About {inside * 100:.0f}% of its dark area falls in the middle of the disc, where nothing can be drawn.")
        rows, cols = np.flatnonzero(d.any(axis=1)), np.flatnonzero(d.any(axis=0))
        span = max(rows[-1] - rows[0], cols[-1] - cols[0]) * step * imagedisc.CELL_MM
        if span < SMALLEST_SPAN * diameter_mm:
            found.append("It only fills a small part of the disc. Check that is what you want.")
    return (found + source)[:MOST_NOTES]


def show(design: np.ndarray, args) -> None:
    t = ui.term()
    r_min, r_max = _inner_mm(args), getattr(args, "r_max", 56.0)
    size = shutil.get_terminal_size((80, 24))
    ui.say()
    if size.columns >= THUMB_PIXELS + 4 and size.lines >= THUMB_PIXELS // 2 + 6:
        ui.say("What will go on the disc (grey can't be drawn on):", "dim")
        for row in thumbnail(design, r_min, r_max, t):
            print(row, file=t.stream)
    for note in notes(design, getattr(args, "picture", None), getattr(args, "diameter_mm", 116.0), r_min, r_max):
        ui.say(note, "yellow")
