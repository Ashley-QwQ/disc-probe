"""Geometry for a disc the drive reads at constant linear speed (BD, and some CD modes).

The ladder in `geo` measures angles. It needs the spindle to hold the *angular* rate, so that
the angle between two positions is a property of the disc; under CLV the drive holds the
linear rate instead and the angle is what the radius makes it. What stays linear is the
period: at radius r the drive takes T = 2*pi*r/v to turn once, and r^2 grows linearly with
the sector index, so

    T^2 = (2*pi*r0/v)^2 + (4*pi*p*L/v^2) * LBA                        (L = mm of track per sector)

A straight line through (LBA, T^2) therefore carries two numbers, and they say

    p/v^2 = a/(4*pi*L)          r0/v = sqrt(b)/(2*pi)

One anchor turns those into a size: a standard pitch gives v, a measured linear speed gives
p. With neither, scaling v scales r0 by v and p by v^2 and the fit cannot tell the
difference -- the same kind of degeneracy the CD along-track constant has, in the other
direction. `fit_t2` always reports which anchor it was given and what stayed unknown.

The estimator is deliberately narrow: it wants the *time to turn once*, which `timing` already
measures per zone (the spindle period is not a function of the read length, so one sector is
enough), and it fits those periods against LBA. No new drive commands, and nothing here runs
unless a caller asks for it -- reading `summary.json` from a finished run needs no drive.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

from . import analysis, mmc, timing
from .geometry import NOMINAL, ONE_X_MM_S

# Zones to measure unless the caller says otherwise. Spread over the recorded area: the fit
# needs a long baseline, and the ends of the disc are where a wrong pitch shows up most.
DEFAULT_ZONES = (0.05, 0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85, 0.95)

BD_1X_MM_S = ONE_X_MM_S["bd"]
BD_SECTORS_PER_LAYER = 12_219_392        # 66 Mb/s of channel bits at 74.50 nm
BREAK_MIN_RMS_MS = 0.005                 # a step smaller than this is under the read timing
BREAK_MIN_IMPROVEMENT = 0.5              # two lines have to halve what one line leaves
BREAK_MIN_F = 20.0

# Below this the period is not the spindle's: a drive still spinning up, a read that spans a
# non-integral number of turns, or a disc the reader cannot follow all show up here first. On
# a real BD-RE the first zone after spin-up came back at coherence 0.54 and put the fit 7 mm
# off; the other eight were 0.81 to 0.99 and fit to R^2 0.99999.
COHERENCE_FLOOR = 0.90


@dataclass(frozen=True)
class Sample:
    """One zone: the sector that was read and how long the spindle took to come round again."""
    lba: int
    period_ms: float
    coherence: float = 1.0
    fraction: float | None = None


@dataclass(frozen=True)
class ClvFit:
    """What a straight line through (LBA, T^2) says about the disc."""
    r0_mm: float
    pitch_um: float
    v_m_s: float
    slope_ms2_per_lba: float
    intercept_ms2: float
    r2: float
    n: int
    anchor: str
    pitch_um_anchor: float | None = None
    v_m_s_anchor: float | None = None
    sigma_r0_mm: float | None = None
    sigma_pitch_um: float | None = None
    sigma_v_m_s: float | None = None
    offset_ms: float | None = None
    sigma_offset_ms: float | None = None
    offset_fitted_ms: float | None = None
    r_first_mm: float | None = None
    r0_extrapolated_mm: float | None = None
    break_fit: dict | None = None
    dropped: tuple[int, ...] = ()
    samples: tuple[Sample, ...] = field(default=(), repr=False)

    def as_dict(self) -> dict:
        out = {
            "model": "clv", "method": "T^2 against LBA",
            "anchor": self.anchor,
            "r0_mm": round(self.r0_mm, 6), "pitch_um": round(self.pitch_um, 6),
            "v_m_s": round(self.v_m_s, 5),
            "slope_ms2_per_lba": self.slope_ms2_per_lba, "intercept_ms2": self.intercept_ms2,
            "r2": round(self.r2, 8), "zones_used": self.n, "zones_dropped": list(self.dropped),
            # The indices are into the sample list; sector addresses are what a reader can find
            # again in zones.csv, so both are written.
            "zones_dropped_lbas": [self.samples[i].lba for i in self.dropped
                                   if 0 <= i < len(self.samples)],
            "sigma_r0_mm": None if self.sigma_r0_mm is None else round(self.sigma_r0_mm, 6),
            "sigma_pitch_um": None if self.sigma_pitch_um is None else round(self.sigma_pitch_um, 6),
            "sigma_v_m_s": None if self.sigma_v_m_s is None else round(self.sigma_v_m_s, 5),
            "r_first_mm": None if self.r_first_mm is None else round(self.r_first_mm, 6),
            "r0_extrapolated_mm": None if self.r0_extrapolated_mm is None else round(self.r0_extrapolated_mm, 6),
            "break_fit": None if self.break_fit is None else {
                "break_lba": self.break_fit["break_lba"],
                "improvement": round(self.break_fit["improvement"], 4),
                "f": round(self.break_fit["f"], 2)},
            # The two quantities the fit really measures, anchor or no anchor.
            "pitch_over_v2_um_s2": round(1e6 * self.pitch_um * 1e-3 / self.v_m_s ** 2, 9),
            "r0_over_v_mm_s": round(self.r0_mm / self.v_m_s, 6),
        }
        if self.pitch_um_anchor is not None:
            out["pitch_um_anchor"] = self.pitch_um_anchor
        if self.v_m_s_anchor is not None:
            out["v_m_s_anchor"] = self.v_m_s_anchor
        if self.offset_ms is not None:
            out["offset_ms"] = round(self.offset_ms, 6)
            out["offset_fitted_ms"] = None if self.offset_fitted_ms is None else round(self.offset_fitted_ms, 6)
            out["sigma_offset_ms"] = None if self.sigma_offset_ms is None else round(self.sigma_offset_ms, 6)
        return out


def _break_fit(x, y):
    """Best one-break straight-line pair through (x, y), and what it buys over one line.

    A disc read in zones holds one angular velocity per zone, so its periods step instead of
    rising smoothly, and one line through them leaves a staircase. Two lines with a break
    between two zones describes that; the improvement says whether the data wanted them.
    Returns None when there are too few points to place a break at all.
    """
    n = len(x)
    if n < 6:
        return None
    sse_one = float(((y - np.polyval(np.polyfit(x, y, 1), x)) ** 2).sum())
    best = None
    for k in range(2, n - 2):          # at least two points on each side
        a1, b1 = np.polyfit(x[:k], y[:k], 1)
        a2, b2 = np.polyfit(x[k:], y[k:], 1)
        sse = float(((y[:k] - np.polyval([a1, b1], x[:k])) ** 2).sum()
                    + ((y[k:] - np.polyval([a2, b2], x[k:])) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, k, a1, a2)
    sse_two, k, a1, a2 = best
    dof_one, dof_two = n - 2, n - 4
    if sse_two <= 0 or dof_two <= 0 or sse_one <= 0:
        return None
    # Floating-point dust passes every statistical test: a perfectly clean line has sse_one ~ 1e-25
    # and a "break" that "explains" most of it. Only a step the measurement could actually have
    # seen is worth reporting, so the plain line has to leave a residual worth explaining.
    rms_one = math.sqrt(sse_one / n)
    if rms_one < BREAK_MIN_RMS_MS:
        return None
    f = ((sse_one - sse_two) / 2) / (sse_two / dof_two)
    improvement = 1.0 - sse_two / sse_one
    if improvement < BREAK_MIN_IMPROVEMENT or f < BREAK_MIN_F:
        return None
    return {"break_lba": int(x[k]), "improvement": improvement, "f": float(f),
            "slope_in": float(a1), "slope_out": float(a2), "sse_one": sse_one, "sse_two": sse_two,
            "rms_ms": rms_one}

def _period_fit(x, t, a0: float, b0: float, iterations: int = 40):
    """Gauss-Newton for t = sqrt(a*x + b); returns (a, b, covariance).

    The measurement error is on the *period*, not on its square: a zone whose turn took T ms came
    back with T + noise, and squaring it makes the outer zones -- where T is larger -- relatively
    noisier than the fit assumes. Fitting t itself puts the noise where it lives, and the
    covariance below is then the one that matches what the drive actually does.
    """
    params = np.array([a0, b0], dtype=np.float64)
    for _ in range(iterations):
        a, b = params
        s = np.sqrt(np.maximum(a * x + b, 1e-9))
        j = np.column_stack([x / (2 * s), 1.0 / (2 * s)])
        step, *_ = np.linalg.lstsq(j, t - s, rcond=None)
        scale = 1.0
        for _ in range(30):
            cand = params + scale * step
            if cand[0] > 0 and cand[1] > 0:
                break
            scale *= 0.5
        else:
            break
        converged = np.allclose(cand, params, rtol=0.0, atol=1e-14)
        params = cand
        if converged:
            break
    a, b = float(params[0]), float(params[1])
    s = np.sqrt(np.maximum(a * x + b, 1e-9))
    j = np.column_stack([x / (2 * s), 1.0 / (2 * s)])
    resid = t - s
    dof = len(x) - 2
    if dof <= 0 or not np.isfinite(resid).all():
        return a, b, None
    s2 = float((resid ** 2).sum() / dof)
    try:
        cov = s2 * np.linalg.inv(j.T @ j)
    except np.linalg.LinAlgError:
        return a, b, None
    return a, b, cov

def _offset_fit(x, t, a0: float, b0: float, iterations: int = 40):
    """Gauss-Newton for t = sqrt(a*x + b) + eps; returns (eps, sigma_eps).

    The model is nearly linear in eps, so a handful of steps settle it. The interesting part is
    sigma: on a short run the offset trades one-for-one against the intercept (a larger eps
    lowers r0), and a large sigma is the fit saying "these zones cannot tell the two apart".
    """
    params = np.array([a0, b0, 0.0], dtype=np.float64)
    for _ in range(iterations):
        a, b, eps = params
        s = np.sqrt(np.maximum(a * x + b, 1e-9))
        j = np.column_stack([x / (2 * s), 1.0 / (2 * s), np.ones_like(x)])
        step, *_ = np.linalg.lstsq(j, t - (s + eps), rcond=None)
        scale = 1.0
        for _ in range(30):
            cand = params + scale * step
            if cand[0] > 0 and cand[1] > 0:
                break
            scale *= 0.5
        else:
            break
        converged = np.allclose(cand, params, rtol=0.0, atol=1e-13)
        params = cand
        if converged:
            break
    a, b, eps = params
    s = np.sqrt(np.maximum(a * x + b, 1e-9))
    j = np.column_stack([x / (2 * s), 1.0 / (2 * s), np.ones_like(x)])
    dof = len(x) - 3
    sigma = None
    if dof > 0:
        s2 = float(((t - (s + eps)) ** 2).sum()) / dof
        try:
            sigma = math.sqrt(abs(s2 * np.linalg.inv(j.T @ j)[2, 2]))
        except np.linalg.LinAlgError:
            sigma = None
    return float(eps), sigma


def fit_t2(samples, *, sector_mm: float, pitch_um: float | None = None, v_m_s: float | None = None,
           drop_outliers: bool = True, clip: float = 4.0, fit_offset: bool = False) -> ClvFit:
    """Fit T^2 = a*LBA + b, then anchor it.

    `pitch_um` and `v_m_s` are alternatives; give at most one. With a pitch, the fit returns
    the linear speed and the start radius. With a speed, it returns the pitch and the start
    radius. With neither it returns both pinned to whatever speed the reader assumed, and
    says so in `anchor`.

    The line is fitted in the *period*, not in its square. The drive's error is on the turn it timed,
    so squaring it makes the outer zones -- where the turn is longer -- relatively noisier than a
    least-squares fit assumes, and the outer zones then pull the intercept as if they were as good as
    the inner ones. A 200-trial simulation (20 us of noise on a 15 ms turn, nine zones, truth known)
    scattered by 42 um while the covariance claimed 38 um, so read the 1 sigma figure as mildly
    optimistic; the selftest keeps the claim inside 0.6-1.5x of what the simulation does, which is
    enough to catch a change that breaks it.

    `fit_offset` asks a third question: does the period carry a constant epsilon on top of the
    turn time? A run of a real BD-RE put r0 at 24.68 mm against a 24.0 mm standard, and a
    constant offset and a disc that really starts further out look the same to two parameters.
    Fitting (a, b, epsilon) together lets the data separate them, but it costs a degree of
    freedom, so it wants five zones or more; with fewer the answer is noise dressed as a number.
    """
    pts = [s for s in samples if s.period_ms and s.lba >= 0]
    if len(pts) < 2:
        raise ValueError("a T^2 fit needs at least two zones with a period")
    x = np.array([s.lba for s in pts], dtype=np.float64)
    y = np.array([s.period_ms for s in pts], dtype=np.float64) ** 2
    keep = np.ones(len(pts), dtype=bool)
    for _ in range(3 if drop_outliers else 0):
        a, b = np.polyfit(x[keep], y[keep], 1)
        resid = y - (a * x + b)
        scale = 1.4826 * np.median(np.abs(resid[keep] - np.median(resid[keep])))
        if scale <= 0 or np.count_nonzero(keep) < 3:
            break
        nxt = np.abs(resid) <= clip * scale
        if nxt.sum() < 3 or np.array_equal(nxt, keep):
            break
        keep = nxt
    a, b = np.polyfit(x[keep], y[keep], 1)
    t = np.array([s.period_ms for s in pts], dtype=np.float64)
    a, b = _period_fit(x[keep], t[keep], a, b)[:2]
    offset = sigma_offset = offset_fitted = None
    if fit_offset:
        if int(keep.sum()) < 5:
            raise ValueError(f"fitting the offset needs at least five zones; this run has "
                             f"{int(keep.sum())} (three parameters against that many points leaves nothing to check)")
        offset_fitted, sigma_offset = _offset_fit(x[keep], t[keep], a, b)
        offset = offset_fitted
        if sigma_offset is None or abs(offset_fitted) < 3.0 * sigma_offset:
            # An offset the data cannot tell from zero still moves r0 by eps*v/(2*pi), which on a
            # Blu-ray is 0.4 mm for 0.25 ms: a thousand times the radius it is standing next to.
            # Leave it out unless it is worth three sigma, and say which happened.
            offset = 0.0
        y = (t - offset) ** 2
        a, b = _period_fit(x[keep], t[keep] - offset, a, b)[:2]
    pred = a * x[keep] + b
    ss_res = float(((y[keep] - pred) ** 2).sum())
    ss_tot = float(((y[keep] - y[keep].mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    if a <= 0 or b <= 0:
        raise ValueError(f"the line through these periods has no positive slope and intercept "
                         f"(slope {a:.3e}, intercept {b:.3e}); a disc read at constant linear speed should give both")

    cov = _period_fit(x[keep], t[keep] if not fit_offset else t[keep] - offset, a, b)[2]
    sigma_a, sigma_b = ((None, None) if cov is None
                        else (math.sqrt(abs(cov[0, 0])), math.sqrt(abs(cov[1, 1]))))

    if pitch_um is not None:
        # p is the anchor: T = 2*pi*r/v with r^2 = r0^2 + p*L*LBA/pi, so
        # a = 4*pi*p*L/v^2. With p and L in mm and a in ms^2/LBA, v comes out in mm/ms = m/s.
        p_mm = pitch_um * 1e-3
        v = math.sqrt(4 * math.pi * p_mm * sector_mm / a)
        pitch, pitch_sigma = pitch_um, None
        v_sigma = 0.5 * sigma_a / a * v if sigma_a is not None else None
        anchor = f"pitch {pitch_um:g} um"
    elif v_m_s is not None:
        v = float(v_m_s)
        pitch_mm = a * v ** 2 / (4 * math.pi * sector_mm)
        pitch, v_sigma = pitch_mm * 1e3, None
        pitch_sigma = 1e3 * pitch_mm * sigma_a / a if sigma_a is not None else None
        anchor = f"linear speed {v:g} m/s"
    else:
        # No anchor: report the shape at the standard 1x speed and say what that means.
        v = BD_1X_MM_S / 1000.0
        pitch_mm = a * v ** 2 / (4 * math.pi * sector_mm)
        pitch, pitch_sigma = pitch_mm * 1e3, None
        v_sigma = None
        anchor = f"none: p and r0 are pinned to {v:g} m/s (1x), so only p/v^2 and r0/v are measured"

    r0 = math.sqrt(b) * v / (2 * math.pi)
    # How far inside the first measured zone does that radius sit? r0 is the fit's curvature,
    # not a place the read head ever visited, and the further out the first zone is, the more the
    # answer leans on the model rather than on a measurement.
    first_lba = float(x[keep].min())
    r_first = math.sqrt(r0 * r0 + pitch * 1e-3 * sector_mm * first_lba / math.pi)
    r0_sigma = None
    if cov is not None:
        # r0 = v*sqrt(b)/(2*pi) with v = k/sqrt(a): slope and intercept move together, and leaving
        # the cross term out has been measured to undersell the tolerance by a third on a nine-zone
        # simulation whose truth was known.
        variance = ((cov[0, 0] / (4 * a * a)) + (cov[1, 1] / (4 * b * b)) - (cov[0, 1] / (2 * a * b)))
        r0_sigma = r0 * math.sqrt(max(variance, 0.0))
    break_fit = _break_fit(x[keep], y[keep])
    return ClvFit(r0_mm=r0, pitch_um=pitch, v_m_s=v, slope_ms2_per_lba=float(a), intercept_ms2=float(b),
                  r2=r2, n=int(keep.sum()), anchor=anchor,
                  pitch_um_anchor=pitch_um, v_m_s_anchor=v_m_s,
                  sigma_r0_mm=r0_sigma, sigma_pitch_um=pitch_sigma, sigma_v_m_s=v_sigma,
                  offset_ms=offset, sigma_offset_ms=sigma_offset, offset_fitted_ms=offset_fitted,
                  r_first_mm=r_first, r0_extrapolated_mm=max(0.0, r_first - r0),
                  break_fit=break_fit,
                  dropped=tuple(int(i) for i in np.nonzero(~keep)[0]),
                  samples=tuple(pts))


def fit_from_summary(summary: dict, *, media: str = "bd", pitch_um: float | None = None,
                     v_m_s: float | None = None, fit_offset: bool = False) -> ClvFit:
    """Re-fit a finished `timing` run: its summary.json already holds one period per zone."""
    zones = (summary.get("period") or {}).get("zones") or []
    samples = [Sample(lba=int(z["lba"]), period_ms=float(z["period_ms"]), coherence=float(z.get("coherence", 1.0)),
                      fraction=z.get("fraction")) for z in zones if z.get("period_ms")]
    if len(samples) < 2:
        raise ValueError("this run has no zones with a period (was it stopped before the period test?)")
    return fit_t2(samples, sector_mm=NOMINAL[media].sector_mm, pitch_um=pitch_um, v_m_s=v_m_s,
                  fit_offset=fit_offset)


def classify_rotation(perf: dict, *, media: str = "bd", r_inner_mm: float = 24.0,
                      r_outer_mm: float = 58.0) -> dict:
    """Decide CAV or CLV from GET PERFORMANCE before measuring anything.

    Type 00h reports the nominal read rate at the start and the end of a range. Under CAV the
    rate grows with the radius, so the ratio is the radius ratio (58.0/24.0 = 2.42 on a full
    BD); under CLV it is 1.0000. A real drive is one or the other, and a ratio in between says
    the range spans a speed change (ZCLV), which no single straight line can fit.
    """
    desc = (perf or {}).get("descriptors") or []
    usable = [d for d in desc if d.get("start_kBps") and d.get("end_kBps")]
    if not usable:
        return {"mode": "unknown", "reason": "the drive reported no performance descriptors"}
    d = usable[0]
    ratio = d["end_kBps"] / d["start_kBps"]
    cav = r_outer_mm / r_inner_mm
    out = {"mode": "unknown", "ratio": round(ratio, 4), "cav_ratio": round(cav, 4),
           "start_kBps": d["start_kBps"], "end_kBps": d["end_kBps"],
           "range_lba": [d.get("start_lba"), d.get("end_lba")]}
    if abs(ratio - 1.0) < 0.02:
        out["mode"] = "CLV"
        out["reason"] = "the nominal rate is flat across the range, so the spindle holds the linear speed"
    elif abs(ratio - cav) / cav < 0.10:
        out["mode"] = "CAV"
        out["reason"] = f"the nominal rate grows by {ratio:.3f}, close to the radius ratio {cav:.3f}"
    else:
        out["reason"] = (f"the rate grows by {ratio:.3f}, between 1.000 (CLV) and {cav:.3f} (CAV): the range "
                         "probably spans a speed change, so measure a narrower one")
    return out


class ConstantAngularVelocity(RuntimeError):
    """The disc turns at a constant angular velocity, so the period carries no radius.

    The angular ladder is the instrument for that disc: it measures phase against sector
    addresses instead of a period against a radius. `geo --media bd` catches this and runs it.
    """


def classify_from_zones(zones: list[dict]) -> dict:
    """Decide CAV or CLV from two measured zones, not from what the drive claims.

    GET PERFORMANCE type 00h reports the nominal rate, and on at least one drive (MATSHITA
    BD-MLT UJ272 reading a BD-RE) it says CAV while the disc actually turns at a constant
    linear speed: the nominal figure is the drive's maximum, not the strategy it picked. So
    the period itself has to decide. Under CLV the period grows with the radius; under CAV it
    stays put, and the ratio between the two zones says which.
    """
    usable = [z for z in zones if z.get("period_ms") and z.get("nominal_radius_mm")]
    if len(usable) < 2:
        return {"mode": "unknown", "reason": "fewer than two zones gave a period"}
    first, last = usable[0], usable[-1]
    t_ratio = last["period_ms"] / first["period_ms"]
    r_ratio = last["nominal_radius_mm"] / first["nominal_radius_mm"]
    out = {"mode": "unknown", "period_ratio": round(t_ratio, 4), "radius_ratio": round(r_ratio, 4),
           "zones": [round(first.get("fraction") or 0, 3), round(last.get("fraction") or 0, 3)]}
    if abs(t_ratio / r_ratio - 1.0) < 0.10:
        out["mode"] = "CLV"
        out["reason"] = f"the period grew by {t_ratio:.3f} with the radius's {r_ratio:.3f}"
    elif abs(t_ratio - 1.0) < 0.05:
        out["mode"] = "CAV"
        out["reason"] = f"the period barely moved ({t_ratio:.3f}) across a radius ratio of {r_ratio:.3f}"
    else:
        out["reason"] = (f"the period grew by {t_ratio:.3f}, between 1.000 (CAV) and {r_ratio:.3f} (CLV): "
                         "the zones probably straddle a speed change")
    return out


class ClvLadder:
    """Measure a CLV disc: one period per zone, then the T^2 fit.

    Mirrors `geo.Ladder` closely enough for the CLI and the result folders, but it reads one
    sector per zone and repeats nothing: the spindle period does not depend on the read length.
    """

    def __init__(self, dev, *, media="bd", zones=DEFAULT_ZONES, reps=None, period_reads=60,
                 speed_kbs=None, pitch_um=None, v_m_s=None, r0_mm=None, log=print,
                 time_limit_s=None, host_delay_ms=35.0, seed=1, fit_offset=False):
        self.media = media
        self.zones = tuple(zones)
        self.pitch_um = pitch_um
        self.v_m_s = v_m_s
        self.fit_offset = fit_offset
        self.log = log
        self.r0_mm = r0_mm
        self.tp = timing.TimingProbe(dev, reps=reps or 24, period_reads=period_reads, speed_kbs=speed_kbs,
                                     media=media, log=log, time_limit_s=time_limit_s,
                                     host_delay_ms=host_delay_ms, seed=seed)
        self.summary: dict = {}
        self.fit: ClvFit | None = None
        self.rotation: dict | None = None

    def precheck(self) -> dict:
        """Ask the drive, before any timing, whether this disc is CLV at all."""
        res = self.tp._cmd(mmc.get_performance(0x10, 0x00), 8 + 16 * 16)
        perf = mmc.parse_get_performance(res.data, 0x00) if res.ok else {}
        rotation = classify_rotation(perf, media=self.media)
        rotation["from"] = "GET PERFORMANCE type 00h"
        self.rotation = rotation
        self.log(f"Rotation by performance: {rotation['mode']}" + (f" ({rotation['reason']})" if "reason" in rotation else ""))
        return rotation

    def precheck_by_measuring(self) -> dict:
        """Time two zones and let the periods decide, before spending the whole ladder on it."""
        # Not the very first zone: a drive coming out of spin-up is still ramping and its period
        # says nothing (on the UJ272 the 0.05 zone read 0.49 coherence). Halfway out and the
        # outside edge are settled, and the radius ratio is wide enough to tell CAV from CLV.
        zones = self.zones if len(self.zones) < 3 else (self.zones[len(self.zones) // 2], self.zones[-1])
        self.tp.period_test(zones=zones, announce_rotation=False)
        shape = classify_from_zones(self.tp.summary.get("period", {}).get("zones") or [])
        self.summary["rotation_measured"] = shape
        self.log(f"Rotation by two zones: {shape['mode']}" + (f" ({shape['reason']})" if "reason" in shape else ""))
        if shape["mode"] == "CAV":
            raise ConstantAngularVelocity(
                "the disc turns at a constant angular velocity (" + shape["reason"] + "), so the completion "
                "period carries no radius and there is no spiral to fit; disc-probe has no angular ladder for "
                "BD sectors, so this disc cannot be measured with --media bd")
        return shape

    def run(self) -> dict:
        self.tp.setup()
        self.summary["setup"] = self.tp.summary.get("setup")
        self.summary["set_cd_speed"] = self.tp.summary.get("set_cd_speed")
        if self.rotation is None:
            self.precheck()
        self.summary["rotation_check"] = self.rotation
        self.tp.cache_test()
        self.summary["cache"] = self.tp.summary.get("cache")
        self.tp.settle_spindle()
        self.summary["settle"] = self.tp.summary.get("settle")
        self.precheck_by_measuring()
        self.tp.period_test(zones=self.zones, announce_rotation=False)
        self.summary["period"] = self.tp.summary.get("period")
        samples = [Sample(lba=int(z["lba"]), period_ms=float(z["period_ms"]),
                          coherence=float(z.get("coherence", 1.0)), fraction=z.get("fraction"))
                   for z in self.summary["period"]["zones"] if z.get("period_ms")]
        unstable = [z.get("fraction") for z in self.summary["period"]["zones"]
                    if z.get("period_ms") and float(z.get("coherence", 1.0)) < COHERENCE_FLOOR]
        if unstable:
            self.summary["zones_unstable"] = unstable
            self.log(f"Left out {len(unstable)} zones whose period was not the spindle's "
                     f"(coherence below {COHERENCE_FLOOR}): " + ", ".join(f"{u:.2f}" for u in unstable))
        # The rotation, judged again on the zones the fit kept: the precheck saw two of them, and
        # this sees the ones that held still, which is the better evidence of the two.
        kept = [z for z in self.summary["period"]["zones"]
                if z.get("period_ms") and float(z.get("coherence", 1.0)) >= COHERENCE_FLOOR]
        shape = classify_from_zones(kept)
        self.summary["rotation_measured"] = shape
        self.log(f"Rotation over the zones kept: {shape['mode']}"
                 + (f" ({shape['reason']})" if "reason" in shape else ""))

        samples = [s for s in samples if s.coherence >= COHERENCE_FLOOR]
        if len(samples) < 2:
            raise RuntimeError(f"only {len(samples)} of {len(self.zones)} zones gave a period that "
                               f"belongs to the spindle (coherence {COHERENCE_FLOOR} or better); "
                               "the drive may be changing speed, or the disc may be too noisy to time")
        self.fit = fit_t2(samples, sector_mm=NOMINAL[self.media].sector_mm,
                          pitch_um=self.pitch_um, v_m_s=self.v_m_s, fit_offset=self.fit_offset)
        self.summary["fit"] = self.fit.as_dict()
        self.summary["fit"]["media"] = self.media
        return self.summary["fit"]


def write_outputs(run: "ClvLadder", out_dir: str, stopped: str | None = None) -> None:
    """Same shape as `geo.write_outputs`, so `results` and `guide` can read both."""
    os.makedirs(out_dir, exist_ok=True)
    zones = (run.summary.get("period") or {}).get("zones") or []
    with open(os.path.join(out_dir, "zones.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fraction", "lba", "period_ms", "rpm", "coherence", "jitter_us", "nominal_radius_mm"])
        for z in zones:
            w.writerow([z.get("fraction"), z.get("lba"), z.get("period_ms"), z.get("rpm"),
                        z.get("coherence"), z.get("jitter_us"), z.get("nominal_radius_mm")])
    payload = {"fit": run.summary.get("fit"), "setup": run.summary.get("setup"),
               "cache": run.summary.get("cache"), "settle": run.summary.get("settle"),
               "period": run.summary.get("period"), "rotation_check": run.summary.get("rotation_check"),
               "rotation_measured": run.summary.get("rotation_measured"),
               "identity": run.summary.get("identity")}
    if run.summary.get("zones_unstable"):
        payload["zones_unstable"] = run.summary["zones_unstable"]
    if run.summary.get("simulated"):
        payload["simulated"] = True
    if run.fit is not None:
        # `geo` results carry the fitted parameters at the top level; `results` and `disexport`
        # look there. A CLV fit has no u/v, so the keys are named differently on purpose.
        payload["fit"].update({"media": run.media})
        last = (payload.get("setup") or {}).get("last_lba")
        r0_mm, pitch_um = payload["fit"].get("r0_mm"), payload["fit"].get("pitch_um")
        if last and r0_mm and pitch_um:
            # Where the spiral would end: a radius the fit never saw, so it is a check on the model
            # rather than a measurement. A full 25 GB layer should land on 58.0 mm.
            outer = math.sqrt(r0_mm * r0_mm + pitch_um * 1e-3 * NOMINAL[run.media].sector_mm * int(last) / math.pi)
            payload["derived"] = {"outer_radius_mm": round(outer, 6), "last_lba": int(last),
                                  "full_layer": run.media == "bd" and int(last) + 1 == BD_SECTORS_PER_LAYER}
            run.summary["derived"] = payload["derived"]
    if stopped:
        payload["stopped"] = stopped
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=float)
