"""Random-data image for full-disc timing calibration (`geo`).

Pure single-byte textures make the GH70N retry and change speed, so the ladder needs
a disc that reads like ordinary data. Seeded random bytes everywhere, plus the empty
ISO 9660 header that burning tools require.

Blu-ray takes the same 2048-byte sectors, so one writer covers both; only the capacity
differs, and `geo --media bd` needs a disc recorded out to a radius it can fit a line
through, which for a single layer means most of 25 GB.
"""

from __future__ import annotations

import os

import numpy as np

from . import dvd, iso9660

DEFAULT_SECTORS = 2295104  # fits DVD+R and DVD-R single layer
CHUNK_SECTORS = 8192


def write_iso(path: str, sectors: int = DEFAULT_SECTORS, seed: int = 1, log=print, media="dvd") -> None:
    if media == "cd":
        from . import cd, cdimage
        cd.check_capacity(sectors)
        cdimage._new_paths(path, ".random.json")
    elif media == "bd":
        from .bdexport import BD_SECTORS_PER_LAYER
        if sectors > BD_SECTORS_PER_LAYER:
            raise ValueError(f"{sectors:,} sectors do not fit on a single-layer Blu-ray "
                             f"({BD_SECTORS_PER_LAYER:,}); lower --sectors")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rng = np.random.default_rng(seed)
    done, next_report = 0, 0.0
    with open(path, "xb" if media == "cd" else "wb") as f:
        while done < sectors:
            n = min(CHUNK_SECTORS, sectors - done)
            f.write(rng.integers(0, 256, n * dvd.SECTOR_BYTES, dtype=np.uint8).tobytes())
            done += n
            if done / sectors >= next_report - 1e-9:   # (steps of 0.01 add up to a hair over 1)
                log(f"  {100 * done / sectors:5.1f} %")
                next_report += getattr(log, "every", 0.2)
    iso9660.add(path, sectors, "DISCPROBE_RANDOM")
