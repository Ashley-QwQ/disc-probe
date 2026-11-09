"""One disc that calibrates itself: three rings to read radii by, one line to read the twist by.

The drive can only ever measure the product of the inner radius squared and the pitch -- `geo` gives
one number, `c = pi r0^2 / (p S)`, and how that product splits between the two is invisible to it.
The split is a property of the stamper that pressed the disc, so it is fixed for a whole brand and
grade, and it only has to be read once per brand. This module builds the disc that reads it: a
picture written with the nominal numbers, whose marks show, once burned, how far the real disc is
from them.

The rings sit at three known radii, so a mark that lands at the wrong radius says the radius scale
is off. The line starts at 12 o'clock and runs to the rim: if the disc's pitch is a few ppm off the
nominal one, the picture is sheared and the far end of the line points at 1 o'clock, 2 o'clock, 4
o'clock -- one hour is 30 degrees, and `disexport --twist-deg` turns that reading back into a pitch.
The same disc is what `geo` times, so both halves of the calibration come off one burn and one
brand: nothing has to be measured twice and no second disc is spent.

The payload is ordinary sector data that happens to be a picture (`imagedisc` writes the same kind
of thing for DVDs); the drive reads it back at exactly the same speed as any other data.
"""

from __future__ import annotations

import os

import numpy as np

from . import bd, imagedisc

CELL_MM = imagedisc.CELL_MM
HALF_MM = imagedisc.HALF_MM
SIZE = imagedisc.SIZE

# The same numbers `bd_defaults` hands to `geo` and `disexport`: the standard pitch of the format and
# the inner radius a full, unspared single-layer BD-R starts at.
NOMINAL_R0_MM = 24.04
NOMINAL_PITCH_UM = 0.32
NOMINAL_SECTORS = 12_219_392
# A blank 25 GB single-layer BD-R holds NOMINAL_SECTORS of data and nothing over for a lead-out,
# so a burner refuses the whole layer ("1.19 MB over"); leave the last 19 392 sectors to it.
BURNABLE_SECTORS = 12_200_000


def design(rings=(26.0, 40.0, 55.0), ring_half_mm: float = 0.35,
           line_deg: float = 90.0, line_half_mm: float = 0.7,
           line_from_mm: float = 25.5, line_to_mm: float = 56.5,
           tick_deg: float = 0.0, tick_half_mm: float = 0.5,
           tick_from_mm: float = 44.0, tick_to_mm: float = 48.0) -> np.ndarray:
    """True = dark. Three rings, one long line at 12 o'clock, one short tick at 3 o'clock.

    The tick is there so the disc says which way round it is: without it, a disc seen from the wrong
    side has the line leaning the other way and the reading comes out mirrored. The long line is
    the vernier; the tick only tells clockwise from counter-clockwise.
    """
    x, y = imagedisc._grid_coords()          # x right, y up; row index runs downwards in the array
    r = np.hypot(x, y)
    th = np.degrees(np.arctan2(y, x)) % 360.0
    dark = np.zeros((SIZE, SIZE), dtype=bool)
    for rr in rings:
        dark |= np.abs(r - rr) <= ring_half_mm

    def arm(centre_deg: float, half_mm: float, lo: float, hi: float) -> np.ndarray:
        # A constant width, not a constant angle: a line that is a fixed fraction of a turn would be
        # a wedge, and a wedge's far end is not a pointer.
        delta = np.abs(((th - centre_deg + 180.0) % 360.0) - 180.0)
        width_mm = r * np.radians(delta)
        return (width_mm <= half_mm) & (r >= lo) & (r <= hi)

    dark |= arm(line_deg, line_half_mm, line_from_mm, line_to_mm)
    if tick_deg is not None:
        dark |= arm(tick_deg, tick_half_mm, tick_from_mm, tick_to_mm)
    return dark


def split_picture(boundary_deg: float = 90.0) -> np.ndarray:
    """True = dark. Half the disc dark, the other half light, divided along one diameter.

    A line is a thin thing: when the preset is off, it winds into a spiral a few hundredths of a
    millimetre wide and disappears into the disc's own texture. The edge between a dark half and a
    light half is a whole diameter of ink, and the same shear turns it into a handful of arms that
    are easy to count by eye -- which is the point of this picture. `boundary_deg` is the diameter
    the edge lies on: 90 puts it at 12-6 o'clock, so a disc that is dark on the left reads at once.
    """
    x, y = imagedisc._grid_coords()
    r = np.hypot(x, y)
    th = np.degrees(np.arctan2(y, x)) % 360.0
    delta = ((th - float(boundary_deg) + 180.0) % 360.0) - 180.0
    return (delta < 0.0) & (r <= 57.0)      # the rim only, so the preview looks like the disc


def geometry(r0_mm: float = NOMINAL_R0_MM, pitch_um: float = NOMINAL_PITCH_UM,
             bit_nm: float = 74.5) -> tuple[float, float]:
    """The (u, v) the DVD writer already understands, from a Blu-ray spiral.

    Both formats are the same spiral: `u = r0 / b` and `v = p / b` with `b` the channel bit length,
    so `r = b sqrt(u^2 + v n / pi)` and the accumulated angle is `2 pi (r - r0) / p`, exactly what
    `calib.theta` computes. Nothing in the writer has to know it is writing a Blu-ray.
    """
    bit_mm = bit_nm * 1e-6
    return r0_mm / bit_mm, pitch_um * 1e-3 / bit_mm


def write(path: str, *, sectors: int = BURNABLE_SECTORS, r0_mm: float = NOMINAL_R0_MM,
          pitch_um: float = NOMINAL_PITCH_UM, bit_nm: float = 74.5, rings=(26.0, 40.0, 55.0),
          line_deg: float = 90.0, split: bool = False, dark: str = "A5", light: str = "B9",
          log=print, preview: str | None = None) -> dict:
    """Write the calibration picture as a burnable image and say what it is.

    With `preview`, the same picture is also saved as a PNG: a disc image bakes in one scrambling
    table and one texture pair, while a PNG can be handed to whatever the user already burns
    pictures with, and it costs nothing to keep beside the image."""
    u, v = geometry(r0_mm, pitch_um, bit_nm)
    textures = bd.check_textures(dark, light)
    pic = split_picture(line_deg) if split else design(rings=rings, line_deg=line_deg)
    if preview:
        imagedisc.preview(pic, preview)
    meta = {"kind": "blu-ray-calibration", "r0_mm": r0_mm, "pitch_um": pitch_um,
            "rings": list(rings), "line_deg": line_deg, "split": bool(split),
            "note": ("burned with the nominal numbers; half the disc is dark, and the shear turns "
                     "that edge into arms you can count") if split else
                    "burned with the nominal numbers; the line's far end points at the twist"}
    spec = imagedisc.write_iso(path, pic, u, v, bit_nm, int(sectors), dark=dark, light=light,
                               log=log, meta=meta, media="bd")
    return {"path": os.path.abspath(path), "spec": os.path.abspath(spec), "u": u, "v": v,
            "textures": textures,
            "preview": os.path.abspath(preview) if preview else None,
            "r0_mm": r0_mm, "pitch_um": pitch_um, "sectors": int(sectors),
            "dark_fraction": float(pic.mean())}


def clock_to_degrees(hour: float) -> float:
    """A clock reading turned into the twist it shows: 1 o'clock is 30 degrees, 4 o'clock is 120.

    The dial goes clockwise in the model's sense, which is the sense a disc plays in. Reading the
    other way round is what the short tick at 3 o'clock is for.
    """
    return 30.0 * ((float(hour) - 12.0) % 12.0)

