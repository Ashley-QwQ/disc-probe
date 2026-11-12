"""Simulated optical drive, to exercise the timing pipeline without hardware.

Models a spindle (CAV with slow drift, or CLV that re-locks after each seek), seek
times that are random and long, a read cache with read-ahead that may or may not
honour FUA, decode latency, host jitter and occasional large outliers. The disc
geometry is deliberately off-nominal, so the measured phases have to come from the
timing, not from the probe's nominal model.
"""

from __future__ import annotations

import math
import random
import struct

from . import mmc
from .geometry import DVD_SECTOR_MM, ONE_X_MM_S, Spiral
from .scsi import ScsiResult, Sense, check_allowed

TWO_PI = 2.0 * math.pi

# I218_POST.md, data-side picture correction (the track angle has the opposite sign).
I218_RADIUS = (24.5, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
               39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 57.9)
I218_PHI = (-135.8, -111.4, -65, -28.9, -16.2, -12.5, -7.8, -4.4, -2, 1.6, 7.1,
            9.7, 10.9, 11.2, 9.5, 3.9, 0, -3.7, -8.5, -11.6, -13.5, -17.2, -19.6,
            -21, -20.5, -19.7, -20.2, -19.9, -18.5, -15.9, -11.9, -7.3, -1.5, 5.2, 11.6)


def pitch_profile(name):
    """A callable phi(radius_mm), in picture degrees; custom callables are accepted too."""
    if callable(name):
        return name
    if name == 'i218':
        from scipy.interpolate import PchipInterpolator
        # Continue the edge tangent; clipping would manufacture another sharp bend.
        p = PchipInterpolator(I218_RADIUS, I218_PHI)
        def profile(r):
            edge = min(max(r, I218_RADIUS[0]), I218_RADIUS[-1])
            return float(p(edge) + p.derivative()(edge) * (r - edge))
        return profile
    if name == 'mild':
        return lambda r: 3.0 * math.sin((r - 24.5) * TWO_PI / 33.4)
    if name == 'step':
        return lambda r: 2.0 * (1 + math.tanh((r - 49.9) / 0.035))
    if name is None or name == 'constant':
        return lambda r: 0.0
    raise ValueError(f'unknown pitch profile: {name}')


class SimDrive:
    def __init__(self, mode: str = "cav", fua_honoured: bool = True, flush_honoured: bool = False, seed: int = 1,
                 jitter_us: float = 60.0, outlier_rate: float = 0.01,
                 rev_period_ms: float | None = None, clv_speed_x: float | None = None,
                 capacity: int | None = None, cache_blocks: int | None = None, reread_delay_ms: float = 0.0,
                 media="dvd", cd_u=None, cd_v=None, cd_audio: bool = False, cd_read_offset_bytes: float = 0.0,
                 patterns=(), block: int | None = None, state_change_after_reads: int | None = None,
        self.phi_profile = pitch_profile(phi_profile)
