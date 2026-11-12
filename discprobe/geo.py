"""`geo`: measure the spiral geometry of a burned DVD from read timing ("ladder").

Under constant rotation, the spindle phase of a target read's completion relative to
a reference read's is the track angle between the ends of the two ECC blocks, plus a
constant c (decode latency difference, ideally ~0):

    phi(X) = Theta(n_X) - Theta(n_R) + c  (mod 360),   Theta(n) = 2n / (S + u),  S = sqrt(u^2 + v n / pi)

with n the channel bit at the end of the block and u = r0/b, v = p/b as in calib.py.
Only the phase modulo 360 is measured, and the nominal geometry mispredicts the angle
between distant sectors by thousands of turns, so targets are taken as a ladder:

  1. Settle the spindle (repeat the reference until its period stops changing).
  2. Measure a target one or two turns from the reference: the nominal model predicts
     it to within a few degrees, which fixes c.
  3. Fit u, v, c (with loose priors on u and v) and take as the next target the
     farthest candidate whose predicted phase is uncertain by less than SAFE_DEG; its
     whole-turn count follows from the prediction. Refit and repeat.

Each new rung shrinks the rate uncertainty, so the reach grows geometrically and some
twenty targets span the readable radius. Every target block re-measures the reference
period; a block taken while the spindle speed changed is retried after settling.

CD audio (a DiscImageStudio picture burn, one CD-DA track): reads use READ CD, each after
one far read that moves the head and the read-ahead away (READ CD has no FUA). The origin
is DiscImageStudio's own: sector k ends at byte 2352 (k + 1) of the burned audio stream,
24.5 channel bits per byte, so u and v are directly the ri and pitch DiscImageStudio uses.
Where a drive's READ CD completes relative to that end is a property of the reading drive,
given as read_offset_bytes x (completion at byte 2352 (k + 1) - x): 0 on an HP BU20N,
-603 on a PLDS DU-8A5LH. Timing cannot see it; check it once per drive with a burned
straight line. None of the Mode 2 data path's 108 + 206 frames apply here.
"""

from __future__ import annotations

import csv
import json
import math
import os
import time

import numpy as np

from . import analysis
from .calib import SECTOR_BITS, CalLayout, theta

BD_SECTOR_PER_UNIT = 32           # a Blu-ray recording unit is 32 sectors, the way a DVD block is 16
BD_SECTOR_BITS = 962136 / 32.0    # channel bits per Blu-ray sector
from .calscan import _dtheta, _report
from .timing import TimingProbe

SAFE_DEG = 25.0
TURN_ABORT_DEG = 90.0       # any rung this far from the refit means a likely whole-turn error
CHI2_ABORT = 25.0           # healthy runs: 0.3-2 simulated, 0.27-0.64 on real discs
MIN_SIGMA_DEG = 0.2         # floor on a target's phase uncertainty (systematics)
# Reference period must match the settled one this closely. Each block's phases use
# that block's own period fit, so this only rejects blocks where the speed jumped. The
# GH70N spins 0.03-0.07 % slower while seeking back and forth than while settling.
PERIOD_TOL = 2e-3
FIRST_TURNS = (1.5, 4.0)    # first rungs, in turns from the reference
SETTLE_READS = 16
# Period-fit coherence is about exp(-sigma^2 / 2) for a phase scatter sigma, so these allow about
# 18 and 22 deg per read. A BW-16D1H-U (12-14 deg, coherence 0.97) never passed 0.99.
SETTLE_COHERENCE = 0.95
MEASURE_COHERENCE = 0.93
MAX_PHASE_STD_DEG = 30.0
MIN_SPACING_SECTORS = 4000  # about a third of a millimetre of radius
SENTINEL_REPS = 3            # check points take this many times the usual reads: two readings are compared
STATE_TOL_DEG = 0.25        # a rung measured again may move this much before the run counts as changed
STATE_SIGMAS = 3.5          # ... and by more than this many standard errors of the difference (3 points at 3 sigma
                            # would call about 1 % of steady runs changed; at 3.5 about 0.14 %)
# Default readable range of a CD-DA picture burn, as fractions of the recorded area: about
# 25.6-57.7 mm on an 80-minute disc. A picture fills the whole disc, so the ladder can reach
# the outer edge (the HP BU20N at 1241 rpm showed no outer-radius read artefacts there).
CD_AUDIO_RANGE = (0.0125, 0.99)
ROTATION_READS = 24
ROTATION_COHERENCE = 0.8    # one outlier takes a clear period to about 0.93 in 24 reads
MIN_ROTATION_RATIO = 1.1    # a span narrower than this can't tell CLV from constant rotation
CLV_RATIO_SLACK = 0.03      # one report's CLV was 0.3 % off the nominal radii, and a period read as twice the turn must not pass
CAV_RATIO_SLACK = 0.05      # outer/inner periods must agree within 5 % for constant rotation


def looks_clv(ratio: float, expected: float) -> bool:
    """Outer over inner period against the radii. A span near a whole ratio can't be told from a period read as whole turns."""
    near_whole = abs(expected - round(expected)) / expected < CLV_RATIO_SLACK
    return not near_whole and abs(ratio - expected) / expected < CLV_RATIO_SLACK


class Ladder:
    def __init__(self, dev, ranges=None, r0_mm=None, pitch_um=None, bit_nm=None, reps=None,
                 max_targets=None, sigma_u=None, sigma_v=None, speed_kbs="default", ref_lba=None,
                 host_delay_ms=25.0, log=print, seed=1, media="dvd", chi2_abort=CHI2_ABORT, sectors=1,
