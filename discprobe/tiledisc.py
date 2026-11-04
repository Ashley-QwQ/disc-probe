"""Self-locating texture palette target: the disc is tiled with small patches, each
carrying its own ID and one swatch of every candidate texture.

Any photo that shows even a part of the disc yields, for every readable tile, where it
sits (ring, sector, hence the local track direction) and how every texture looks under
that tile's light and viewing angle. Comparing swatches inside one tile cancels uneven
lighting and stray rainbow.

Tile layout, in tile coordinates (row 0 = inner edge, column 0 = smallest angle, angle
counter-clockwise in the data-side view):

    6 rows x 7 columns of cells. Cells pair up radially (rows 0-1, 2-3, 4-5).
    Columns 0-3, 12 pairs ("slots", slot = 3 * column + pair):
        slot 0      A5 / A5   finder
        slot 1-10   ID bits, differential: 1 = A5 inner / 92 outer, 0 = 92 inner / A5 outer
        slot 11     92 / 92   finder
    Columns 4-6, 9 pairs: one swatch per palette texture, index = 3 * (column - 4) + pair.

ID bits (MSB first): ring (2 bits), sector (6 bits), parity of all 8, parity of bits 0, 2, 4, 6.
Each bit is read by comparing the two cells of its pair, so it survives the light/dark
flips and colour changes that diffraction causes.
"""

from __future__ import annotations

import json
import math

import numpy as np

from .imagedisc import CELL_MM, HALF_MM, SIZE

RING_EDGES_MM = (25.0, 33.0, 41.0, 49.0, 57.0)
TILE_MM = 8.0
GAP_MM = 0.5
ROWS, COLS, ID_COLS = 6, 7, 4
BACKGROUND = "RND"


def sectors_per_ring() -> list[int]:
    return [round(2 * math.pi * (a + b) / 2 / TILE_MM) for a, b in zip(RING_EDGES_MM, RING_EDGES_MM[1:])]


def id_bits(ring: int, sector: int) -> list[int]:
    b = [(ring >> 1) & 1, ring & 1] + [(sector >> k) & 1 for k in range(5, -1, -1)]
    return b + [sum(b) & 1, (b[0] ^ b[2] ^ b[4] ^ b[6])]


def tile_cells(ring: int, sector: int, n_palette: int) -> np.ndarray:
    """ROWS x COLS cell contents: -1 = A5, -2 = 92, k >= 0 = palette swatch k."""
    cells = np.zeros((ROWS, COLS), np.int64)
    slots = [(1, 1)] + [(1, 0) if b else (0, 1) for b in id_bits(ring, sector)] + [(0, 0)]
    for s, (inner_a5, outer_a5) in enumerate(slots):
        col, pair = divmod(s, 3)
        cells[2 * pair, col] = -1 if inner_a5 else -2
        cells[2 * pair + 1, col] = -1 if outer_a5 else -2
    for k in range(min(n_palette, 3 * (COLS - ID_COLS))):
        col, pair = divmod(k, 3)
        cells[2 * pair:2 * pair + 2, ID_COLS + col] = k
    return cells


def design(palette: list[str]) -> tuple[np.ndarray, list[str], dict]:
    """Label map (SIZE x SIZE uint8), texture list for the labels, and the layout record."""
    textures = [BACKGROUND, "A5", "92"] + [t for t in palette if t not in ("A5", "92", BACKGROUND)]
    index = {t: i for i, t in enumerate(textures)}
    pal_label = np.array([index[t] for t in palette])
    nsec = sectors_per_ring()
    tables = [np.stack([np.where(c == -1, 1, np.where(c == -2, 2, pal_label[np.clip(c, 0, None)]))
                        for c in (tile_cells(k, j, len(palette)) for j in range(n))])
              for k, n in enumerate(nsec)]
    labels = np.zeros((SIZE, SIZE), np.uint8)
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    x = c[None, :]
    for y0 in range(0, SIZE, 500):
        y = -c[y0:y0 + 500, None]
        r = np.hypot(x, y)
        th = np.arctan2(y, x) % (2 * math.pi)
        out = np.zeros(r.shape, np.uint8)
        for k, n in enumerate(nsec):
            r_in, r_out = RING_EDGES_MM[k] + GAP_MM / 2, RING_EDGES_MM[k + 1] - GAP_MM / 2
            dth = 2 * math.pi / n
            j = np.floor(th / dth).astype(np.int64) % n
            a = th - j * dth - GAP_MM / 2 / np.maximum(r, 1e-6)
            span = dth - GAP_MM / np.maximum(r, 1e-6)
            m = (r >= r_in) & (r < r_out) & (a >= 0) & (a < span)
            row = np.clip(((r - r_in) / (r_out - r_in) * ROWS).astype(np.int64), 0, ROWS - 1)
            col = np.clip((a / np.where(m, span, 1) * COLS).astype(np.int64), 0, COLS - 1)
            out[m] = tables[k][j[m], row[m], col[m]]
        labels[y0:y0 + 500] = out
    layout = {"kind": "tile-palette-target", "ring_edges_mm": list(RING_EDGES_MM), "sectors_per_ring": nsec,
              "gap_mm": GAP_MM, "rows": ROWS, "cols": COLS, "id_cols": ID_COLS, "palette": palette,
              "background": BACKGROUND, "angle": "counter-clockwise from +x in the data-side view, y up",
              "id_bits": "ring(2) sector(6) parity(all) parity(0,2,4,6); 1 = A5 inner / 92 outer",
              "slots": "slot = 3 * column + pair; slot 0 = A5/A5, slot 11 = 92/92, slots 1-10 = ID bits",
              "swatch": "index = 3 * (column - id_cols) + pair"}
    return labels, textures, layout


def decode_slots(pairs: list[int]) -> tuple[int, int] | None:
    """Ring and sector from the 10 ID bits (1/0 per slot 1-10), or None if a parity fails."""
    b = list(pairs)
    if len(b) != 10 or (sum(b[:8]) & 1) != b[8] or (b[0] ^ b[2] ^ b[4] ^ b[6]) != b[9]:
        return None
    return (b[0] << 1) | b[1], int("".join(map(str, b[2:8])), 2)


def preview(labels: np.ndarray, textures: list[str], path: str, size: int = 1600) -> None:
    from PIL import Image
    colours = {"RND": (128, 128, 128), "A5": (25, 25, 60), "92": (235, 225, 200)}
    rng = np.random.default_rng(4)
    lut = np.array([colours.get(t, tuple(int(v) for v in rng.integers(40, 230, 3))) for t in textures], np.uint8)
    Image.fromarray(lut[labels]).resize((size, size), Image.NEAREST).save(path)


def save_layout(layout: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2)
