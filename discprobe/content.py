"""Which parts of a DVD hold plain random data.

geo needs them. A picture or texture reads at another latency than random data, and the default range
of a disc that holds one (a texture-ring disc, or one with a picture appended) would put rungs on it.
Pictures and textures are written as bytes in the scrambled domain, so undoing the scrambling of a sector
read back gives one or two byte values over and over; random data stays random either way. Unrecorded
or zero-filled sectors (between sessions) are plain before the undoing, so both views must look random.
"""

from __future__ import annotations

import numpy as np

from . import dvd

MIN_DISTINCT = 200      # 2048 random bytes take about 250 values; a texture 1, a picture 2
# ...and no value much more often than the 8 times each one averages: 32 is about 8.5 standard deviations
# out. Without it a sector of one texture byte with 256 different bytes in front passed (the 6pro audit
# of 1f7f92e: 87.5 % 0x92 counted as random).
MAX_SAME = 32
SAMPLES = 160           # about 0.25 mm apart over the default range, finer than any texture ring so far
MARGIN_SECTORS = 3000   # kept away from each edge, as geo does for texture rings
MIN_SECTORS = 20000     # shorter stretches (under about 0.5 mm) are left out


def is_random(lba: int, data: bytes) -> bool:
    if len(data) < dvd.SECTOR_BYTES:
        return False
    raw = np.frombuffer(data[:dvd.SECTOR_BYTES], np.uint8)
    plain = raw ^ dvd.MASKS[dvd.preset_index(lba)]
    return _spread(raw) and _spread(plain)


def _spread(b: np.ndarray) -> bool:
    counts = np.bincount(b, minlength=256)
    return int((counts > 0).sum()) >= MIN_DISTINCT and int(counts.max()) <= MAX_SAME


def random_ranges(read, ranges, block: int = 16, samples: int = SAMPLES, margin: int = MARGIN_SECTORS,
                  min_sectors: int = MIN_SECTORS):
    """The random stretches inside `ranges`, each pulled in by `margin`, or None when every sample is random.

    read(lba) returns the sector's 2048 bytes, or None when it can't be read (counted as not random).
    Samples are spread evenly; each change between neighbours is then narrowed to one block by bisection.
    A pattern narrower than the sample spacing can be missed.
    """
    seen = {}

    def random_at(lba):
        if lba not in seen:
            data = read(lba)
            seen[lba] = data is not None and is_random(lba, data)
        return seen[lba]

    def edge(a, b):
        """First block after a whose state differs from a's, with b known to differ."""
        state = random_at(a)
        while b - a > block:
            m = max(a + block, (a + b) // 2 // block * block)
            if m >= b:
                break
            if random_at(m) == state:
                a = m
            else:
                b = m
        return b

    out = []
    for lo, hi in ranges:
        grid = sorted({int(x) // block * block for x in np.linspace(lo, hi - block, samples)})
        flags = [random_at(x) for x in grid]
        start = None
        for i, (x, f) in enumerate(zip(grid, flags)):
            if f and start is None:
                start = lo if i == 0 else edge(grid[i - 1], x)
            elif not f and start is not None:
                out.append((start, edge(grid[i - 1], x)))
                start = None
        if start is not None:
            out.append((start, hi))
    if all(seen.values()):
        return None
    return [(a + margin, b - margin) for a, b in out if b - a - 2 * margin >= min_sectors]
