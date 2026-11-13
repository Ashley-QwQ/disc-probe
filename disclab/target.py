"""The photo target as a design for `image --design-npy`: the same code as the reader's template.

disc-probe has no command that writes this target (only docs/goals/photo-calibration/make_target.py, outside the
repository), so the lab makes the design the same way and burns it through `image --design-npy`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def target_npy(path) -> Path:
    path = Path(path)
    if path.exists():
        return path
    from discprobe import pcal
    from discprobe.imagedisc import CELL_MM, HALF_MM, SIZE
    d = pcal.design_burn()
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    out = np.zeros((SIZE, SIZE), bool)
    for y0 in range(0, SIZE, 500):
        y = -c[y0:y0 + 500, None]
        x = c[None, :]
        r = np.hypot(x, y)
        th = np.arctan2(y, x) % (2 * np.pi)
        out[y0:y0 + 500] = (d.value(r, th) > 0.5) & (r >= 26.2) & (r <= 57.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, out)
    return path
