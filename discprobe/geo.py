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
                 read_offset_bytes: float = 0.0, state_check: bool = True, completion_sectors: int = 0):
        self.media = media
        from .read_completion import sectors as check_completion
        self.completion_sectors = check_completion(completion_sectors)
        if media != 'dvd' and completion_sectors:
            raise ValueError('--completion-sectors is for DVD')
        self.state_check = state_check
        self.state = None
        self.chi2_abort = chi2_abort
        self.read_offset_bytes = float(read_offset_bytes)
        self.audio = False  # set by run() when the CD turns out to be a CD-DA track
        is_cd = media == "cd"
        is_bd = media == "bd"
        from . import cd
        from .geometry import NOMINAL as NOM
        r0_mm = r0_mm if r0_mm is not None else (cd.R0_MM if is_cd else NOM["bd" if is_bd else "dvd"].r0_mm)
        pitch_um = pitch_um if pitch_um is not None else (
            cd.PITCH_UM if is_cd else NOM["bd"].pitch_mm * 1000.0 if is_bd else 0.74)
        bit_nm = bit_nm if bit_nm is not None else (cd.BIT_NM if is_cd else 74.5 if is_bd else 133.3)
        reps = reps if reps is not None else (32 if is_cd else 24)
        max_targets = max_targets if max_targets is not None else (36 if is_cd else 22)
        sigma_u = sigma_u if sigma_u is not None else (0.08 if is_cd else 0.01)
        sigma_v = sigma_v if sigma_v is not None else (0.15 if is_cd else 0.03)
        if speed_kbs == "default":
            speed_kbs = 1411 if is_cd else 8990 if is_bd else 5540
        self.block = 1 if is_cd else BD_SECTOR_PER_UNIT if is_bd else 16
        self.spacing = 64 if is_cd else MIN_SPACING_SECTORS
        self.first_turns = (0.5, 1.5) if is_cd else FIRST_TURNS
        self.dev = dev
        self.ranges_arg = ranges
        self.prior = CalLayout(r0_mm=r0_mm, pitch_um=pitch_um, bit_nm=bit_nm)
        self.u0, self.v0 = self.prior.u0, self.prior.v0
        self.sig_u, self.sig_v = sigma_u * self.u0, sigma_v * self.v0
        self.reps = reps
        self.max_targets = max_targets
        self.ref_arg = ref_lba
        self.log = log
        self.tp = TimingProbe(dev, log=lambda *_: None, reps=reps, speed_kbs=speed_kbs,
                              host_delay_ms=host_delay_ms, seed=seed, media=media, sectors=sectors, cd_audio=is_cd)
        self.targets: list[dict] = []
        self.u, self.v, self.c = self.u0, self.v0, 0.0
        self.cov = None
        # Progress counts reference/target pairs, not sectors or all device pauses.
        # Settling and retries are elapsed time, not additional completed work.
        self.progress_total = 0
        self.progress_checks_done = 0
        self.progress_current = 0
        self.progress_stage = "starting"
        self.progress_finished = False
        self.auto_ranges = None   # random stretches found on a disc that isn't all random data

    # ------------------------------------------------------------ geometry helpers

    def _n_end(self, lba: int) -> float:
        """Channel bit at the end of the ECC block holding lba (where the read completes)."""
        if self.audio:
            from .cd import RAW_BYTES, SECTOR_BITS as CD_BITS
            return float((lba + 1) * CD_BITS - self.read_offset_bytes * CD_BITS / RAW_BYTES)
        if self.media == "cd":
            from .cd import read_end_bits
            return float(read_end_bits(lba))
        if self.media == "bd":
            return float((lba // BD_SECTOR_PER_UNIT + 1) * BD_SECTOR_PER_UNIT * BD_SECTOR_BITS)
        return float(((lba // 16 + 1) * 16 + self.completion_sectors) * SECTOR_BITS)

    def _lba_at_turns(self, turns: float) -> int:
        th = theta(self.n_ref, self.u, self.v) + 2 * math.pi * turns
        s = self.u + self.v * th / (2 * math.pi)
        n = math.pi * (s * s - self.u * self.u) / self.v
        if self.audio:
            from .cd import RAW_BYTES, SECTOR_BITS as CD_BITS
            return int((n + self.read_offset_bytes * CD_BITS / RAW_BYTES) // CD_BITS) - 1
        if self.media == "cd":
            from .cd import SECTOR_BITS as CD_BITS, FRAME_BITS, READ_TAIL_FRAMES
            return int((n - READ_TAIL_FRAMES * FRAME_BITS) // CD_BITS) - 1
        if self.media == "bd":
            return int(n // BD_SECTOR_BITS) // BD_SECTOR_PER_UNIT * BD_SECTOR_PER_UNIT
        if not self.completion_sectors:
            return int(n // SECTOR_BITS) // 16 * 16
        return int((n / SECTOR_BITS - self.completion_sectors) // 16) * 16

    def _predict(self, n):
        return float(theta(n, self.u, self.v) - theta(self.n_ref, self.u, self.v)) + self.c

    def _sigma_pred_deg(self, n) -> float:
        if self.cov is None:
            return float("inf")
        du, dv = _dtheta(n, self.u, self.v)
        du0, dv0 = _dtheta(self.n_ref, self.u, self.v)
        g = np.array([du - du0, dv - dv0, 1.0])
        return math.degrees(math.sqrt(max(float(g @ self.cov @ g), 0.0)))

    def _span_variance_after(self, lba: int) -> float:
        """Variance of the accumulated angle across the readable range if lba were measured
        next with the typical per-rung uncertainty (rank-one covariance update)."""
        lo = self._n_end(min(a for a, _ in self.ranges))
        hi = self._n_end(max(b for _, b in self.ranges) - self.block)
        du_lo, dv_lo = _dtheta(lo, self.u, self.v)
        du_hi, dv_hi = _dtheta(hi, self.u, self.v)
        g = np.array([du_hi - du_lo, dv_hi - dv_lo, 0.0])
        n = self._n_end(lba)
        du, dv = _dtheta(n, self.u, self.v)
        du0, dv0 = _dtheta(self.n_ref, self.u, self.v)
        h = np.array([du - du0, dv - dv0, 1.0])
        s2 = math.radians(float(np.median([t["sigma_deg"] for t in self.targets]))) ** 2
        ch = self.cov @ h
        cov = self.cov - np.outer(ch, ch) / (s2 + h @ ch)
        return float(g @ cov @ g)

    def _allowed(self, lba: int) -> int | None:
        """Nearest block-aligned LBA inside the readable ranges."""
        best = None
        for a, b in self.ranges:
            x = min(max(lba, a), b - self.block)
            x -= x % self.block
            if best is None or abs(x - lba) < abs(best - lba):
                best = x
        return best

    # ------------------------------------------------------------ measurement

    def _ref_period(self, times):
        return analysis.estimate_period(times, prior_s=self.T, prior_window=0.02) if self.T else \
            analysis.estimate_period(times)

    def _radius(self, lba: int) -> float:
        return self.prior.bit_nm * 1e-6 * math.sqrt(self.u0 * self.u0 + self.v0 * self._n_end(lba) / math.pi)

    def check_rotation(self) -> None:
        """Stop on clear CLV or inconsistent speeds before fitting any rungs.

        A period too unclear to compare stops nothing here. Whole-turn aliases must
        not be mistaken for CLV; they also cannot establish constant rotation.
        """
        tp = self.tp
        inner = self._allowed(min(a for a, _ in self.ranges))
        outer = self._allowed(max(b for _, b in self.ranges) - self.block)
        expected = self._radius(outer) / self._radius(inner)
        if expected < MIN_ROTATION_RATIO:
            return
        periods = []
        for lba in (inner, outer):
            for _ in range(2):      # the first round may catch the spindle changing speed after the seek
                times = [r.t_end_ns for r in (tp._measure(lba, "rotation") for _ in range(ROTATION_READS)) if tp._usable(r)]
            fit = analysis.estimate_period(times) if len(times) >= 8 else None
            if not fit or fit.coherence < ROTATION_COHERENCE:
                return
            periods.append(fit.period_s)
        ratio = periods[1] / periods[0]
        tp.summary["rotation_check"] = {"inner_lba": inner, "outer_lba": outer, "period_ms": [p * 1e3 for p in periods], "ratio": ratio, "expected_clv": expected}
        if looks_clv(ratio, expected):
            raise RuntimeError(f"the drive is not turning at a constant speed here ({periods[0] * 1e3:.2f} ms a turn at "
                               f"{self._radius(inner):.0f} mm, {periods[1] * 1e3:.2f} ms at {self._radius(outer):.0f} mm), and geo needs it to")
        if abs(ratio - 1) > CAV_RATIO_SLACK:
            raise RuntimeError(f"the drive's speed is not steady ({periods[0] * 1e3:.2f} ms a turn at "
                               f"{self._radius(inner):.0f} mm, {periods[1] * 1e3:.2f} ms at {self._radius(outer):.0f} mm): "
                               "it probably slowed down on a hard-to-read part of the disc")

    def settle(self, max_rounds: int = 10) -> float:
        tp, prev = self.tp, None
        self.T = None
        for i in range(max_rounds):
            times = [r.t_end_ns for r in (tp._measure(self.ref, "settle") for _ in range(SETTLE_READS))
                     if tp._usable(r)]
            fit = analysis.estimate_period(times) if len(times) >= 8 else None
            if fit and fit.coherence > SETTLE_COHERENCE and prev and abs(fit.period_s / prev - 1) < PERIOD_TOL:
                self.T = fit.period_s
                tp.cover_one_turn(fit.period_s)
                self.log(f"Spindle settled: T = {fit.period_s * 1e3:.4f} ms ({60 / fit.period_s:.1f} rpm), "
                         f"jitter {fit.residual_std_s * 1e6:.1f} us")
                return self.T
            prev = fit.period_s if fit and fit.coherence > SETTLE_COHERENCE else None
        raise RuntimeError("the spindle speed never settled; is the read speed fixed (--speed)?")

    def measure(self, lba: int, reps: int | None = None) -> dict | None:
        tp = self.tp
        ref_t, x_t = [], []
        for _ in range(reps or self.reps):
            r = tp._measure(self.ref, "ref")
            if tp._usable(r):
                ref_t.append(r.t_end_ns)
            x = tp._measure(lba, "target")
            if tp._usable(x):
                x_t.append(x.t_end_ns)
            self.progress_current += 1
        fit = self._ref_period(ref_t) if len(ref_t) >= 8 else None
        if not fit or fit.coherence < MEASURE_COHERENCE or abs(fit.period_s / self.T - 1) > PERIOD_TOL or len(x_t) < 8:
            return None
        ph = analysis.robust_circular_mean(analysis.phase_offsets(fit, x_t))
        if ph["mean_deg"] is None or ph["std_deg"] > MAX_PHASE_STD_DEG:
            return None
        self.T = fit.period_s  # follow slow drift of the regulated speed
        return {"lba": lba, "n": self._n_end(lba), "phase_deg": ph["mean_deg"],
                "sigma_deg": max(ph["sem_deg"], MIN_SIGMA_DEG), "sem_deg": ph["sem_deg"], "std_deg": ph["std_deg"],
                "used": ph["used"], "period_ms": round(fit.period_s * 1e3, 5)}

    def _measure_retry(self, lba: int, reps: int | None = None) -> dict | None:
        self.progress_current = 0
        m = self.measure(lba, reps)
        if m is None:
            self.log(f"  LBA {lba}: spindle unsteady or reads failing; settling and retrying")
            self.progress_current = 0
            self.settle()
            m = self.measure(lba, reps)
        self.progress_current = 0
        return m

    # ------------------------------------------------------------ fitting

    def fit(self, iters: int = 15) -> None:
        u, v, c = self.u, self.v, self.c
        n = np.array([t["n"] for t in self.targets])
        y = np.radians([t["unwrapped_deg"] for t in self.targets])
        w = 1 / np.radians([t["sigma_deg"] for t in self.targets])
        for _ in range(iters):
            model = theta(n, u, v) - theta(self.n_ref, u, v) + c
            du, dv = _dtheta(n, u, v)
            du0, dv0 = _dtheta(self.n_ref, u, v)
            J = np.column_stack([du - du0, dv - dv0, np.ones_like(n)]) * w[:, None]
            r = (y - model) * w
            J = np.vstack([J, [1 / self.sig_u, 0, 0], [0, 1 / self.sig_v, 0]])
            r = np.concatenate([r, [(self.u0 - u) / self.sig_u, (self.v0 - v) / self.sig_v]])
            sc = np.sqrt((J ** 2).sum(axis=0))
            step, *_ = np.linalg.lstsq(J / sc, r, rcond=None)
            step /= sc
            u, v, c = u + step[0], v + step[1], c + step[2]
            if np.all(np.abs(step * sc) < 1e-9):
                break
        model = theta(n, u, v) - theta(self.n_ref, u, v) + c
        res = (y - model) * w
        chi2 = float(np.sum(res ** 2))
        dof = max(1, len(n) - 3)
        cov = np.linalg.inv((J / sc).T @ (J / sc)) / np.outer(sc, sc)
        self.u, self.v, self.c = float(u), float(v), float(c)
        self.cov = cov * max(1.0, chi2 / dof)
        self.chi2_dof = chi2 / dof
        for t, m in zip(self.targets, model):
            t["model_deg"] = math.degrees(float(m))
            t["residual_deg"] = t["unwrapped_deg"] - t["model_deg"]

    # ------------------------------------------------------------ the ladder

    def _candidates(self) -> list[int]:
        lo = min(a for a, _ in self.ranges)
        hi = max(b for _, b in self.ranges)
        grid = np.linspace(lo, hi - self.block, 40).astype(int)
        turns = [s * 2 ** k for k in range(0, 18) for s in (1, -1)]
        near = [self._lba_at_turns(t) for t in turns]
        out = set()
        for lba in list(grid) + near:
            x = self._allowed(int(lba))
            if x is not None and abs(x - self.ref) >= self.block:
                out.add(x)
        return sorted(out)

    def _add(self, m: dict, predicted_deg: float) -> None:
        k = round((predicted_deg - m["phase_deg"]) / 360.0)
        m["unwrapped_deg"] = m["phase_deg"] + 360.0 * k
        m["predicted_deg"] = predicted_deg
        self.targets.append(m)

    def _random_parts(self, ranges):
        """Leave out what isn't random data (see content.py); a disc of random data keeps the default range."""
        from . import content
        tp = self.tp
        before, tp._experiment = tp._experiment, "content"
        self.log("Checking which parts of the disc hold random data...")

        def read(lba):
            r = tp._read(lba, 1, label="content")
            return r.data if r.ok else None
        try:
            found = content.random_ranges(read, ranges, block=self.block)
        finally:
            tp._experiment = before
        self.auto_ranges = found
        if found is None:
            return ranges
        if not found:
            raise RuntimeError("no random data found in the recorded area")
        self.log(f"Only part of this disc is random data; measuring just those {len(found)} stretches")
        return found

    def _label_parts(self, ranges):
        """Read the in-band layout marker before any content samples or timed rungs there."""
        if self.media != "dvd":
            return ranges
        from .randomlabel import exclude_ranges
        tp = self.tp
        # setup has already discovered pending or measured layouts before warmup.
        spec = tp.summary.get("random_label")
        if spec is None:
            return ranges
        # Also guard multi-sector reads and the drive's completion block.
        margin = max(3000, tp.sectors + self.completion_sectors + self.block)
        for span in [spec['exclude_lba'], *spec.get('avoid_lba', [])]:
            ranges = exclude_ranges(ranges, span, self.block, margin)
        return ranges

    def run(self) -> dict:
        tp = self.tp
        tp.setup()
        self.audio = self.media == "cd" and tp.audio
        if self.audio:
            self.log(f"CD-DA track: READ CD, origin at the end of each sector in the burned audio stream, "
                     f"read offset {self.read_offset_bytes:g} bytes")
        elif self.read_offset_bytes:
            raise RuntimeError("--read-offset-bytes is for a CD-DA track (DiscImageStudio picture burn); "
                               "this disc is a data disc")
        tp.cache_test()
        if tp.strategy not in ("fua", "plain", "far"):
            self.log(f"warning: cache strategy {tp.strategy}; phases will be noisier")
        last = tp.last_lba
        if self.ranges_arg:
            self.ranges = [(max(0, a), min(b, last + 1)) for a, b in self.ranges_arg]
        elif self.audio:
            self.ranges = [(int(last * CD_AUDIO_RANGE[0]), int(last * CD_AUDIO_RANGE[1]))]
        else:
            self.ranges = [(int(last * 0.03), int(last * 0.85))]
        self.ranges = self._label_parts(self.ranges)
        if not self.ranges_arg and not self.audio and self.media == "dvd":
            self.ranges = self._random_parts(self.ranges)
        self.ranges = [(a - a % self.block, b - b % self.block) for a, b in self.ranges if b - a > 64]
        if not self.ranges:
            raise RuntimeError(f"no readable {self.media.upper()} ranges longer than 64 sectors")
        if self.ref_arg is not None:
            self.ref = self._allowed(self.ref_arg)
        else:
            mid = (min(a for a, _ in self.ranges) + max(b for _, b in self.ranges)) // 2
            if not any(a <= mid < b for a, b in self.ranges):
                # The middle falls in a gap (e.g. between texture rings): take the centre of the
                # nearest range, not its edge, so the first rungs have room on both sides.
                a, b = min(self.ranges, key=lambda r: min(abs(mid - r[0]), abs(mid - r[1])))
                mid = (a + b) // 2
            self.ref = self._allowed(mid)
        self.n_ref = self._n_end(self.ref)
        self.log(f"Reference LBA {self.ref}; readable ranges {self.ranges}")
        self.check_rotation()
        self.settle()
        self.sentinels = []
        self.progress_total = self.max_targets * self.reps
        if self.state_check:
            self.sentinels_first()

        self.progress_stage = "ladder"

        # First rungs: a turn or two away, where the nominal model is good to a few degrees.
        used = {self.ref}
        for i, turns in enumerate(self.first_turns):
            lba = self._allowed(self._lba_at_turns(turns))
            if min(abs(lba - t) for t in used) < self.block:
                # Clamped onto the reference (or a rung) at a range edge: go the other way.
                turns = -turns
                lba = self._allowed(self._lba_at_turns(turns))
            if min(abs(lba - t) for t in used) < self.block:
                raise RuntimeError(f"no room for a rung {abs(turns)} turns from the reference")
            used.add(lba)
            m = self._measure_retry(lba)
            if m is None:
                raise RuntimeError(f"could not measure LBA {lba} near the reference")
            pred = math.degrees(self._predict(m["n"]))
            if i == 0:
                self.c = math.radians(((m["phase_deg"] - pred + 180) % 360) - 180)
                pred = math.degrees(self._predict(m["n"]))
            self._add(m, pred)
            self.log(f"  rung {len(self.targets):2d}: LBA {lba:>8} ({turns:+.1f} turns) phase {m['phase_deg']:8.3f} "
                     f"+/- {m['sigma_deg']:.3f} deg")
        self.fit()

        tried = {t["lba"] for t in self.targets}
        self.completion_status = "target_reached"
        self.failed_candidates = []
        while len(self.targets) < self.max_targets:
            # Skip candidates next to one already measured: a second point there adds little.
            cands = [c for c in self._candidates()
                     if c not in tried and min(abs(c - t) for t in tried) >= self.spacing]
            if not cands:
                self.completion_status = "candidates_exhausted"
                break
            sig = {c: self._sigma_pred_deg(self._n_end(c)) for c in cands}
            safe = [c for c in cands if sig[c] < SAFE_DEG]
            if safe and len(safe) == len(cands):
                # Reach is no longer the limit. Most rungs go where they shrink the uncertainty
                # of the angle across the whole range the most (that favours the ends); every
                # third fills the widest gap, so the middle is checked too (the first real run
                # left 34.6-42.6 and 44-49 mm empty).
                if len(self.targets) % 3 == 0:
                    lba = max(safe, key=lambda c: min(abs(c - t) for t in tried | {self.ref}))
                else:
                    lba = min(safe, key=self._span_variance_after)
            elif safe:
                lba = max(safe, key=lambda c: abs(self._n_end(c) - self.n_ref))
            else:
                bridge = [c for c in self._candidates()
                          if c not in tried and min(abs(c - t) for t in tried) >= self.block]
                sig.update({c: self._sigma_pred_deg(self._n_end(c)) for c in bridge})
                bridge = [c for c in bridge if sig[c] < SAFE_DEG]
                if not bridge:
                    raise RuntimeError("no rung is within the safe 25-degree prediction limit; "
                                       "the whole-turn count is ambiguous; retry with lower noise")
                lba = max(bridge, key=lambda c: abs(self._n_end(c) - self.n_ref))
            tried.add(lba)
            pred = math.degrees(self._predict(self._n_end(lba)))
            m = self._measure_retry(lba)
            if m is None:
                self.failed_candidates.append(lba)
                self.log(f"  LBA {lba}: skipped (no stable measurement)")
                continue
            self._add(m, pred)
            self.fit()
            t = self.targets[-1]
            self.log(f"  rung {len(self.targets):2d}: LBA {lba:>8} predicted +/- {sig[lba]:6.2f} deg, "
                     f"whole turns {round((t['unwrapped_deg']) / 360):>7}, residual {t['residual_deg']:+7.3f} deg, "
                     f"chi2/dof {self.chi2_dof:.2f}")
            # A wrong whole-turn count is partly absorbed by u and v, so the new rung itself can
            # look fine; it shows as an exploding chi2 and large residuals elsewhere. Stop rather
            # than fit through it (simulated: chi2/dof jumps from ~1 to ~360 at the bad rung).
            worst = max(abs(x["residual_deg"]) for x in self.targets)
            if self.chi2_dof > self.chi2_abort or worst > TURN_ABORT_DEG:
                raise RuntimeError(f"after the rung at LBA {lba}: chi2/dof {self.chi2_dof:.1f}, worst residual "
                                   f"{worst:.1f} deg; a whole-turn count is probably wrong, so the fit was stopped")
        if self.sentinels:
            self.check_state()
        result = self.result()
        self.progress_finished = True
        return result

    def sentinels_first(self) -> None:
        """Before the ladder: read the raw phase of three far-apart points (near the inner end, a quarter of
        the way and near the outer end of the range); check_state reads them again at the end. Comparing a
        point with itself needs no whole-turn count, so they can be far from the reference from the start.
        The reference is re-read in every block, so a change in timing common to all reads cancels; what
        moves a point is a change that depends on where the head is. Such a change during the run bends
        the geometry and the fit can't show it: three noisy GH70N runs of one disc fitted tidily yet sat
        0.5-0.8 deg from a clean run (evidence/geo/gh70n-20261107). These points are not fitted."""
        lo = min(a for a, _ in self.ranges)
        hi = max(b for _, b in self.ranges)
        self.sentinels = []
        planned = []
        for f in (0.03, 0.25, 0.97):
            lba = self._allowed(int(lo + f * (hi - lo)))
            if lba is None or abs(lba - self.ref) < self.spacing:
                continue
            planned.append(lba)
        cost = SENTINEL_REPS * self.reps
        self.progress_total += 2 * len(planned) * cost
        self.progress_stage = "reading check points"
        for lba in planned:
            if any(abs(lba - s["lba"]) < self.spacing for s in self.sentinels):
                self.progress_total -= 2 * cost
                continue
            m = self._measure_retry(lba, cost)
            self.progress_checks_done += cost
            if m is not None:
                self.sentinels.append(m)
            else:
                # Only successfully read check points will be read again.
                self.progress_total -= cost
        if self.sentinels:
            self.log("Check points read: " + ", ".join(f"{self._radius(s['lba']):.1f} mm" for s in self.sentinels)
                     + " (read again at the end)")

    def check_state(self) -> None:
        b = self.prior.bit_nm * 1e-6
        sem = lambda x: x.get("sem_deg") if x.get("sem_deg") is not None else x["sigma_deg"]
        self.log("Reading the check points again, to see that the drive stayed in one state...")
        self.progress_stage = "reading check points again"
        out = []
        for s in self.sentinels:
            e = {"lba": s["lba"], "radius_mm": round(b * math.sqrt(self.u ** 2 + self.v * s["n"] / math.pi), 2),
                 "phase_first_deg": s["phase_deg"], "phase_again_deg": None, "period_first_ms": s["period_ms"]}
            m = self._measure_retry(s["lba"], SENTINEL_REPS * self.reps)
            self.progress_checks_done += SENTINEL_REPS * self.reps
            if m is not None:
                e.update(phase_again_deg=m["phase_deg"],
                         change_deg=round((m["phase_deg"] - s["phase_deg"] + 180.0) % 360.0 - 180.0, 3),
                         sigma_deg=round(math.hypot(sem(s), sem(m)), 3), period_again_ms=m["period_ms"])
                self.log(f"  {e['radius_mm']:.1f} mm: moved {e['change_deg']:+.3f} deg (+/- {e['sigma_deg']:.3f})")
            else:
                self.log(f"  {e['radius_mm']:.1f} mm: no stable measurement this time")
            out.append(e)
        done = [e for e in out if e["phase_again_deg"] is not None]
        # The points together: a shift they share (seen against the reference) is a change too, and
        # their weighted mean shows it with less noise than any one of them.
        w = [1 / max(e["sigma_deg"], 1e-3) ** 2 for e in done]
        mean = sum(wi * e["change_deg"] for wi, e in zip(w, done)) / sum(w) if done else None
        mean_sigma = 1 / math.sqrt(sum(w)) if done else None
        if len(done) < 2:
            verdict = "unmeasured"
        elif any(abs(e["change_deg"]) > max(STATE_TOL_DEG, STATE_SIGMAS * e["sigma_deg"]) for e in done)                 or abs(mean) > max(STATE_TOL_DEG, STATE_SIGMAS * mean_sigma):
            verdict = "changed"
        elif all(abs(e["change_deg"]) <= STATE_TOL_DEG and e["sigma_deg"] <= STATE_TOL_DEG for e in done):
            verdict = "steady"
        else:
            verdict = "inconclusive"     # too noisy to tell a change of STATE_TOL_DEG
        self.state = {"verdict": verdict, "tolerance_deg": STATE_TOL_DEG, "sigmas": STATE_SIGMAS, "points": out,
                      "mean_change_deg": None if mean is None else round(mean, 3),
                      "mean_sigma_deg": None if mean_sigma is None else round(mean_sigma, 3)}

    def result(self) -> dict:
        rep = _report(self.u, self.v, self.cov, (self.u, self.v), self.prior, None)
        if self.media == 'dvd' and self.completion_sectors:
            rep['completion_sectors'] = self.completion_sectors
            rep['fit_prior'] = dict(r0_mm=self.prior.r0_mm, pitch_um=self.prior.pitch_um,
                                    sigma_u=self.sig_u / self.u0, sigma_v=self.sig_v / self.v0)
            if getattr(self, 'completion_source', None):
                rep['completion_source'] = self.completion_source
        if self.media == "cd":
            from . import cd
            b = self.prior.bit_nm * 1e-6
            rep["media"] = "cd"
            rep["sector_bits"] = cd.SECTOR_BITS
            if self.audio:
                sectors = self.tp.last_lba + 1
                rep["track"] = "audio"
                rep["origin"] = ("DiscImageStudio audio stream: sector k ends at byte 2352 (k + 1), 24.5 channel "
                                 "bits per byte; the read completes read_offset_bytes before that end")
                rep["read_offset_bytes"] = self.read_offset_bytes
                rep["read_offset_note"] = ("a property of the reading drive (HP BU20N 0, PLDS DU-8A5LH -603); "
                                           "timing cannot see it, so check it once per drive with a burned straight line")
                rep["sectors"] = sectors
            else:
                rep["read_tail_frames"] = cd.READ_TAIL_FRAMES
                rep["read_completion_model_measured"] = False
            lo_n = max(0.0, math.pi * ((25.0 / b) ** 2 - self.u ** 2) / self.v)
            hi_n = math.pi * ((58.0 / b) ** 2 - self.u ** 2) / self.v
            du0, dv0 = _dtheta(lo_n, self.u, self.v)
            du1, dv1 = _dtheta(hi_n, self.u, self.v)
            g = np.array([du1 - du0, dv1 - dv0])
            rep["angle_span_mm"] = [25.0, 58.0]
            rep["angle_sigma_deg"] = math.degrees(math.sqrt(float(g @ self.cov[:2, :2] @ g)))
            nn = np.linspace(lo_n, hi_n, 400)
            rep["nominal_error_deg"] = float(np.ptp(np.degrees(
                theta(nn, self.u, self.v) - theta(nn, self.u0, self.v0))))
            if self.audio:
                rep["dis_equivalent"] = {
                    "bit_nm": self.prior.bit_nm, "sectors": sectors, "inner_radius_mm": self.u * b,
                    "outer_radius_mm": b * math.sqrt(self.u ** 2 + self.v * sectors * cd.SECTOR_BITS / math.pi),
                    "note": "DiscImageStudio CD geometry (constant pitch) of this disc for this sector count, "
                            "as burned and read; right as far as read_offset_bytes is right for this drive"}
            else:
                rep["dis_equivalent"] = {
                    "bit_nm": self.prior.bit_nm, "inner_radius_mm": self.u * b,
                    "outer_radius_mm_for_total_sectors": {
                        str(cd.CAPACITY): b * math.sqrt(self.u ** 2 + self.v * cd.CAPACITY * cd.SECTOR_BITS / math.pi)},
                    "note": "CD forward CIRC reference origin, hardware origin unmeasured; not a DVD preset"}
        if self.media == "bd":
            b = self.prior.bit_nm * 1e-6
            rep["media"] = "bd"
            rep["sector_bits"] = BD_SECTOR_BITS
            rep["block_sectors"] = BD_SECTOR_PER_UNIT
            rep["rungs"] = len(self.targets)
            rep["dis_equivalent"] = {
                "bit_nm": self.prior.bit_nm,
                "inner_radius_mm": self.u * b,
                "pitch_um_estimate": self.v * b * 1e3,
                "outer_radius_mm_for_total_sectors": {
                    str(self.tp.last_lba + 1):
                        b * math.sqrt(self.u ** 2 + self.v * (self.tp.last_lba + 1) * BD_SECTOR_BITS / math.pi)},
                "note": "angular measurement of a disc the drive reads at a constant angular velocity: "
                        "inner radius and pitch come from one fit, and the pitch is only as good as "
                        "the prior it was pulled towards"}
        n_meas = [t["n"] for t in self.targets] + [self.n_ref]
        lo, hi = min(n_meas), max(n_meas)
        du_lo, dv_lo = _dtheta(lo, self.u, self.v)
        du_hi, dv_hi = _dtheta(hi, self.u, self.v)
        g = np.array([du_hi - du_lo, dv_hi - dv_lo])
        b_mm = self.prior.bit_nm * 1e-6
        r_of = lambda n: b_mm * math.sqrt(self.u ** 2 + self.v * n / math.pi)
        rep["measured_span_mm"] = [round(r_of(lo), 3), round(r_of(hi), 3)]
        radii = sorted(r_of(n) for n in n_meas)
        gap = max(zip(radii, radii[1:]), key=lambda p: p[1] - p[0]) if len(radii) > 1 else (radii[0], radii[0])
        rep["largest_gap_mm"] = [round(gap[0], 2), round(gap[1], 2)]
        if self.state is not None:
            rep["state_check"] = self.state
        rep["angle_sigma_measured_span_deg"] = math.degrees(math.sqrt(float(g @ self.cov[:2, :2] @ g)))
        if hasattr(self, "completion_status"):
            rep["completion_status"] = self.completion_status
            rep["failed_candidates"] = self.failed_candidates
        du_0, dv_0 = _dtheta(0.0, self.u, self.v)
        # The end of the last sector in this medium's own channel bits (a DVD or CD counted in Blu-ray
        # sectors put this figure 9 % and 32 % too high; the 6pro audit of 1f7f92e).
        du_t, dv_t = _dtheta(self._n_end(self.tp.last_lba), self.u, self.v)
        g_full = np.array([du_t - du_0, dv_t - dv_0])
        rep["angle_sigma_full_disc_deg"] = math.degrees(math.sqrt(float(g_full @ self.cov[:2, :2] @ g_full)))
        rep["c_deg"] = math.degrees(self.c)
        rep["chi2_per_dof"] = self.chi2_dof
        rep["residual_rms_deg"] = float(np.sqrt(np.mean([t["residual_deg"] ** 2 for t in self.targets])))
        rep["period_ms"] = self.T * 1e3 if self.T else None  # None if a run stopped while resettling
        rep["reference_lba"] = self.ref
        return rep


def write_outputs(ladder: Ladder, out_dir: str, stopped: str | None = None) -> None:
    """`stopped` says why the run ended early. Such a fit can look fine, but only covers what was reached."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "targets.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lba", "n_bits", "phase_deg", "sigma_deg", "std_deg", "used", "predicted_deg",
                    "unwrapped_deg", "model_deg", "residual_deg", "period_ms"])
        for t in ladder.targets:
            w.writerow([t["lba"], f"{t['n']:.0f}", t["phase_deg"], f"{t['sigma_deg']:.3f}", t["std_deg"], t["used"],
                        f"{t['predicted_deg']:.3f}", f"{t['unwrapped_deg']:.3f}", f"{t['model_deg']:.3f}",
                        f"{t['residual_deg']:.3f}", t["period_ms"]])
    res = ladder.result()
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"fit": res, "cache": ladder.tp.summary.get("cache"),
                   "setup": ladder.tp.summary.get("setup"), "identity": ladder.tp.summary.get("identity"),
                   "set_cd_speed": ladder.tp.summary.get("set_cd_speed"),
                   "rotation_check": ladder.tp.summary.get("rotation_check"),
                   **({"random_label": ladder.tp.summary["random_label"]} if "random_label" in ladder.tp.summary else {}),
                   **({"simulated": True} if ladder.tp.summary.get("simulated") else {}),
                   **({"stopped": stopped} if stopped else {})}, f, indent=2, default=float)
    events = ladder.tp.events_as_rows()
    if events:
        with open(os.path.join(out_dir, "events.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(events[0]))
            w.writeheader()
            w.writerows(events)

    from . import ui
    ui.result_event("geo", out_dir, stopped)
