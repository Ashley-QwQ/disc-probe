"""Burnable DVD image of a picture, placed with a measured geometry (u = r0/b, v = p/b).

Every 16-byte group of every sector gets the picture's value at its position on the
disc: dark groups are recorded as one texture (A5), light ones as another. Positions
come from the same model the `geo` ladder fits,

    Theta(n) = 2n / (S + u),  S = sqrt(u^2 + v n / pi),  radius = b * S,

so u and v fix every angle exactly; the assumed bit length b only scales the picture
uniformly, which cannot bend a line. The disc turns counter-clockwise as seen by the
optical head (ECMA-267), so seen from the data side the track angle runs clockwise:
the picture is drawn in data-side view with y up, and its rotation on the disc is
arbitrary.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np

from . import dvd, iso9660
from .calib import GROUP_BITS, GROUP_BYTES, SECTOR_BITS, theta

CELL_MM = 0.02
HALF_MM = 60.0
SIZE = int(2 * HALF_MM / CELL_MM)


def _grid_coords():
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    return c[None, :], -c[:, None]  # x right, y up


def grid_design(r_min=24.5, r_max=56.0, spacing=5.0, line=0.3) -> np.ndarray:
    """True = dark. Cartesian grid, radial lines every 30 degrees, circles every
    spacing mm, and a block letter F (asymmetric, so a mirrored burn is obvious)."""
    x, y = _grid_coords()
    r = np.hypot(x, y)
    th = np.degrees(np.arctan2(y, x))
    half = line / 2
    near = lambda v: np.abs((v + spacing / 2) % spacing - spacing / 2) < half
    dark = near(x) | near(y)
    dark |= np.abs(r - np.round(r / spacing) * spacing) < half
    for a in range(0, 360, 30):
        d = np.abs(((th - a + 180) % 360) - 180)
        dark |= (np.radians(d) * r < max(0.2, half)) & (d < 90)
    # Letter F, 10 mm tall, in the upper half (stroke 1.2 mm).
    fx, fy, s = -3.0, 33.0, 1.2
    dark |= (x >= fx) & (x < fx + s) & (y >= fy) & (y < fy + 10)
    dark |= (x >= fx) & (x < fx + 6) & (y >= fy + 10 - s) & (y < fy + 10)
    dark |= (x >= fx) & (x < fx + 4.5) & (y >= fy + 5 - s / 2) & (y < fy + 5 + s / 2)
    return dark & (r >= r_min) & (r <= r_max)


def picture_design(path: str, diameter_mm: float = 116.0, threshold: float = 0.5) -> np.ndarray:
    """A grey picture fitted to a circle of the given diameter, thresholded (dark = True)."""
    from PIL import Image
    with Image.open(path) as im:
        g = np.asarray(im.convert("L").resize((round(diameter_mm / CELL_MM),) * 2), dtype=np.float32) / 255
    out = np.zeros((SIZE, SIZE), bool)
    o = (SIZE - g.shape[0]) // 2
    out[o:o + g.shape[0], o:o + g.shape[1]] = g < threshold
    return out


def load_correction(path: str):
    """phi(r) in degrees from an angle-correction file (polynomial, held constant outside its range)."""
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    lo, hi = c["radius_valid_mm"]
    coef = np.array(c["poly_in_x"])
    return lambda r: np.polyval(coef, (np.clip(r, lo, hi) - 40.0) / 15.0)


def sectors_to_radius(u: float, v: float, bit_nm: float, r_mm: float) -> int:
    s = r_mm / (bit_nm * 1e-6)
    n = math.pi * (s * s - u * u) / v
    return int(n // SECTOR_BITS) // 16 * 16


CHUNK = 2048


def _dark_groups(design, u, v, bit_mm, lba0, count, correction=None):
    lbas = np.arange(lba0, lba0 + count)
    n = lbas[:, None].astype(np.float64) * SECTOR_BITS + GROUP_BITS[None, :]
    s = np.sqrt(u * u + v * n / math.pi)
    th = -theta(n, u, v)  # clockwise in data-side view
    r = bit_mm * s
    if correction is not None:
        # A byte at model angle th shows up at th + phi(r): give it the design there.
        th = th + np.radians(correction(r))
    ix = np.floor((r * np.cos(th) + HALF_MM) / CELL_MM).astype(np.int64)
    iy = np.floor((HALF_MM - r * np.sin(th)) / CELL_MM).astype(np.int64)
    ok = (ix >= 0) & (ix < SIZE) & (iy >= 0) & (iy < SIZE)
    return np.where(ok, design[np.clip(iy, 0, SIZE - 1), np.clip(ix, 0, SIZE - 1)], False)


def write_iso(path: str, design: np.ndarray, u: float, v: float, bit_nm: float, total_sectors: int,
              dark: str = "A5", light: str = "B9", log=print, meta: dict | None = None, correction=None) -> str:
    qd, ql = np.uint8(int(dark, 16)), np.uint8(int(light, 16))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bit_mm = bit_nm * 1e-6
    done, next_report = 0, 0.0
    with open(path, "wb") as f:
        while done < total_sectors:
            n = min(CHUNK, total_sectors - done)
            g = _dark_groups(design, u, v, bit_mm, done, n, correction)
            q = np.where(np.repeat(g, GROUP_BYTES, axis=1), qd, ql)
            presets = ((np.arange(done, done + n) + dvd.DATA_START_PSN) >> 4) & 0xF
            f.write((q ^ dvd.MASKS[presets]).tobytes())
            done += n
            if done / total_sectors >= next_report:
                log(f"  {100 * done / total_sectors:5.1f} %")
                next_report += 0.2
    iso9660.add(path, total_sectors, "DISCPROBE_IMAGE")
    spec = {"kind": "dvd-picture", "u": u, "v": v, "bit_nm": bit_nm, "total_sectors": total_sectors,
            "dark": dark, "light": light, "cell_mm": CELL_MM, **(meta or {})}
    spec_path = os.path.splitext(path)[0] + ".image.json"
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
    return spec_path


def verify_iso(path: str, design: np.ndarray, u: float, v: float, bit_nm: float, total_sectors: int,
               dark: str = "A5", light: str = "B9", samples: int = 300, seed: int = 3, correction=None) -> list[str]:
    """Descramble random sectors and compare every group with an independent recomputation."""
    problems = []
    if os.path.getsize(path) != total_sectors * dvd.SECTOR_BYTES:
        return ["size mismatch"]
    rng = np.random.default_rng(seed)
    qd, ql = int(dark, 16), int(light, 16)
    with open(path, "rb") as f:
        for lba in rng.integers(32, total_sectors, samples):
            f.seek(int(lba) * dvd.SECTOR_BYTES)
            rec = dvd.recorded(np.frombuffer(f.read(dvd.SECTOR_BYTES), dtype=np.uint8), int(lba))
            want = _dark_groups(design, u, v, bit_nm * 1e-6, int(lba), 1, correction)[0]
            got = rec.reshape(-1, GROUP_BYTES)
            if not np.all(np.where(want[:, None], got == qd, got == ql)):
                problems.append(f"LBA {lba} differs from the design")
    return problems


def preview(design: np.ndarray, path: str, size: int = 1200) -> None:
    from PIL import Image
    img = Image.fromarray(np.where(design, 0, 255).astype(np.uint8)).resize((size, size))
    img.save(path)
