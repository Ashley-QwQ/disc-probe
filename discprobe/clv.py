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

BD_1X_MM_S = ONE_X_MM_S["bd"]        # 66 Mb/s of channel bits at 74.50 nm


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
            "sigma_r0_mm": None if self.sigma_r0_mm is None else round(self.sigma_r0_mm, 6),
            "sigma_pitch_um": None if self.sigma_pitch_um is None else round(self.sigma_pitch_um, 6),
            "sigma_v_m_s": None if self.sigma_v_m_s is None else round(self.sigma_v_m_s, 5),
            # The two quantities the fit really measures, anchor or no anchor.
            "pitch_over_v2_um_s2": round(1e6 * self.pitch_um * 1e-3 / self.v_m_s ** 2, 9),
            "r0_over_v_mm_s": round(self.r0_mm / self.v_m_s, 6),
        }
        if self.pitch_um_anchor is not None:
            out["pitch_um_anchor"] = self.pitch_um_anchor
        if self.v_m_s_anchor is not None:
            out["v_m_s_anchor"] = self.v_m_s_anchor
        return out


def fit_t2(samples, *, sector_mm: float, pitch_um: float | None = None, v_m_s: float | None = None,
           drop_outliers: bool = True, clip: float = 4.0) -> ClvFit:
    """Fit T^2 = a*LBA + b, then anchor it.

    `pitch_um` and `v_m_s` are alternatives; give at most one. With a pitch, the fit returns
    the linear speed and the start radius. With a speed, it returns the pitch and the start
    radius. With neither it returns both pinned to whatever speed the reader assumed, and
    says so in `anchor`.
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
    pred = a * x[keep] + b
    ss_res = float(((y[keep] - pred) ** 2).sum())
    ss_tot = float(((y[keep] - y[keep].mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    if a <= 0 or b <= 0:
        raise ValueError(f"the line through these periods has no positive slope and intercept "
                         f"(slope {a:.3e}, intercept {b:.3e}); a disc read at constant linear speed should give both")

    sigma_a = sigma_b = None
    dof = int(keep.sum()) - 2
    if dof > 0 and ss_res > 0:
        s2 = ss_res / dof
        xtx = np.array([[np.sum(x[keep] ** 2), np.sum(x[keep])], [np.sum(x[keep]), int(keep.sum())]])
        cov = s2 * np.linalg.inv(xtx)
        sigma_a, sigma_b = math.sqrt(abs(cov[0, 0])), math.sqrt(abs(cov[1, 1]))

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
    r0_sigma = None
    if sigma_b is not None:
        terms = [(sigma_b / (2 * b)) ** 2]
        if v_sigma is not None and v:
            terms.append((v_sigma / v) ** 2)
        r0_sigma = r0 * math.sqrt(sum(terms))
    return ClvFit(r0_mm=r0, pitch_um=pitch, v_m_s=v, slope_ms2_per_lba=float(a), intercept_ms2=float(b),
                  r2=r2, n=int(keep.sum()), anchor=anchor,
                  pitch_um_anchor=pitch_um, v_m_s_anchor=v_m_s,
                  sigma_r0_mm=r0_sigma, sigma_pitch_um=pitch_sigma, sigma_v_m_s=v_sigma,
                  dropped=tuple(int(i) for i in np.nonzero(~keep)[0]),
                  samples=tuple(pts))


def fit_from_summary(summary: dict, *, media: str = "bd", pitch_um: float | None = None,
                     v_m_s: float | None = None) -> ClvFit:
    """Re-fit a finished `timing` run: its summary.json already holds one period per zone."""
    zones = (summary.get("period") or {}).get("zones") or []
    samples = [Sample(lba=int(z["lba"]), period_ms=float(z["period_ms"]), coherence=float(z.get("coherence", 1.0)),
                      fraction=z.get("fraction")) for z in zones if z.get("period_ms")]
    if len(samples) < 2:
        raise ValueError("this run has no zones with a period (was it stopped before the period test?)")
    return fit_t2(samples, sector_mm=NOMINAL[media].sector_mm, pitch_um=pitch_um, v_m_s=v_m_s)


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


class ClvLadder:
    """Measure a CLV disc: one period per zone, then the T^2 fit.

    Mirrors `geo.Ladder` closely enough for the CLI and the result folders, but it reads one
    sector per zone and repeats nothing: the spindle period does not depend on the read length.
    """

    def __init__(self, dev, *, media="bd", zones=DEFAULT_ZONES, reps=None, period_reads=60,
                 speed_kbs=None, pitch_um=None, v_m_s=None, r0_mm=None, log=print,
                 time_limit_s=None, host_delay_ms=35.0, seed=1):
        self.media = media
        self.zones = tuple(zones)
        self.pitch_um = pitch_um
        self.v_m_s = v_m_s
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
        self.tp.period_test(zones=self.zones)
        self.summary["period"] = self.tp.summary.get("period")
        samples = [Sample(lba=int(z["lba"]), period_ms=float(z["period_ms"]),
                          coherence=float(z.get("coherence", 1.0)), fraction=z.get("fraction"))
                   for z in self.summary["period"]["zones"] if z.get("period_ms")]
        if len(samples) < 2:
            raise RuntimeError(f"only {len(samples)} of {len(self.zones)} zones gave a period; "
                               "the drive may be changing speed, or the disc may be too noisy to time")
        self.fit = fit_t2(samples, sector_mm=NOMINAL[self.media].sector_mm,
                          pitch_um=self.pitch_um, v_m_s=self.v_m_s)
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
               "identity": run.summary.get("identity")}
    if run.summary.get("simulated"):
        payload["simulated"] = True
    if run.fit is not None:
        # `geo` results carry the fitted parameters at the top level; `results` and `disexport`
        # look there. A CLV fit has no u/v, so the keys are named differently on purpose.
        payload["fit"].update({"media": run.media})
    if stopped:
        payload["stopped"] = stopped
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=float)
