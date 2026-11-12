"""Where a person stands in the workflow: past results, and the commands to run next.

Reads result folders and prints text; it never touches a drive. The commands it prints use
real paths and values, so they can be copied as they are.
"""

from __future__ import annotations

import datetime
import difflib
import importlib.util
import json
import math
import os
import re
import sys

from . import i18n, iso9660, mmc

RESULT_DIR = re.compile(r"^(?P<kind>[a-z]+)-(?:(?P<tag>.+)-)?(?P<stamp>\d{8}-\d{6})$")
PROG = "python -m discprobe"
# `latest` must not pick these. Results now say when they stopped early; these catch older ones, as far as they can:
# one stopped after 8 rungs says nothing, and looks complete.
MIN_RUNGS = 8
MAX_LATEST_CHI2 = 25.0
# Reports so far: under about 2 deg drives measured well; 3-24 deg (SP80NB80) and 10-14 deg
# (BW-16D1H-U) stopped or gave a wrong geometry.
GOOD_JITTER_DEG = 2.0
BAD_JITTER_DEG = 5.0
NARROW_SPAN_MM = 20.0
# When a varying pitch counts as worth a correction: it at least halves chi2/dof.
PITCH_CLEARLY_BETTER = 0.5
# Angle uncertainty (1 sigma, measured span) a geo verdict may call good. chi2/dof can't tell: a noisy drive
# has wide error bars and still fits. Clean full-span runs here gave 0.10-0.15 deg, and timing's 2 deg of
# jitter works out to about 0.21 (CD, 36 rungs) to 0.28 (DVD, 22 rungs). Past 0.6, about 5 deg of jitter,
# is where the CD run at 3226 rpm sat (0.77) that the drive table says can't be used.
GOOD_SIGMA_DEG = 0.25
BAD_SIGMA_DEG = 0.6
# A Blu-ray run is a straight T^2 line: five zones already leave three checks of its straightness, and a
# disc read at a constant linear speed lands on R^2 0.9999 or better. Its own real run over 23 zones gave
# R^2 0.999998; a run whose speed moved during the measurement falls well under 0.99.
MIN_BD_ZONES = 5
MIN_BD_R2 = 0.99
MATCH_INFO_S = 24 * 3600    # how far from a measurement an `info` run can be and still be taken for the same disc
ALTERNATIVE_SPEEDS = {"dvd": ("3324", "5540", "11080"),
                      "cd": ("1411", "2822", "4234", "5645", "7056", "8467"),
                      "bd": ("8990", "17980", "35960")}
RANDOM_SECTORS = {"dvd": 2295104, "cd": 359600}
# Spare room a random disc needs. CD: on a 359,847-sector disc 359,800 was refused and 359,600 went through.
# DVD: the usual 2,295,104 has burned many times on 2,295,104-sector discs, so it only has to fit. A smaller
# image for a smaller disc still leaves room: a 713,936-sector miniDVD refused its full count by 4 KB.
BURN_ROOM_SECTORS = {"dvd": 0, "cd": 200}
BURN_FILL = 0.98
INSTALL = "python -m pip install numpy pillow scipy opencv-python"
PORTS = ("This repository drives real hardware on Windows and Linux. macOS port: "
         "github.com/NaiveTomcat/discprobe-macos. Anything with --sim works here.")


class Quiet(str):
    """A line of advice that stays in the background."""


class Step(str):
    """A line of the progress list, which has its own colours."""


def quote(path: str) -> str:
    return f'"{path}"' if " " in path else path


def short(path: str) -> str:
    """A path to paste into a command: relative when it is below the current folder. Forward slashes, which
    cmd, PowerShell and Git Bash all take; Git Bash ate the backslashes of `results\\geo-...` (DIS #108)."""
    try:
        rel = os.path.relpath(path)
    except ValueError:      # another drive on Windows
        return quote(os.path.abspath(path).replace("\\", "/"))
    return quote((os.path.abspath(path) if rel.startswith("..") else rel).replace("\\", "/"))


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _parsed(report: dict, key: str) -> dict:
    return (report.get(key) or {}).get("parsed") or {}


class Result:
    def __init__(self, path: str, kind: str, tag: str | None, stamp: str):
        self.path, self.kind, self.tag = path, kind, tag or ""
        self.when = datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S")
        self.summary = _load(os.path.join(path, "summary.json")) or {}
        self.simulated = self.tag.startswith("SIM") or self.summary.get("simulated") is True

    @property
    def fit(self) -> dict:
        return self.summary.get("fit") or {}

    @property
    def is_clv(self) -> bool:
        """A period fit against LBA, rather than an angle map."""
        return self.kind == "geo" and self.fit.get("model") == "clv"

    @property
    def media(self) -> str:
        if self.kind == "geo":
            media = self.fit.get("media")
            if media in ("cd", "dvd", "bd"):
                return media
        family = (self.summary.get("setup") or {}).get("family")
        media = family if family in ("cd", "dvd", "bd") else (self.summary.get("args") or {}).get("media")
        return media if media in ("cd", "dvd", "bd") else "dvd"

    def rungs(self) -> int:
        try:
            with open(os.path.join(self.path, "targets.csv"), encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
        except OSError:
            return 0

    @property
    def stopped(self) -> str | None:
        return self.summary.get("stopped")

    def zones(self) -> int:
        """Zones in a CLV result; the angle ladder has rungs instead."""
        try:
            with open(os.path.join(self.path, "zones.csv"), encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
        except OSError:
            return 0

    def geo_complete(self) -> bool:
        if self.kind != "geo":
            return False
        reached = self.fit.get("completion_status", "target_reached") == "target_reached"
        if self.is_clv:
            if self.media == "cd":
                return False  # experimental radius fit, not a calibrated CD angle map
            r2 = self.fit.get("r2")
            return ("r0_mm" in self.fit and not self.stopped and reached and self.zones() >= 5
                    and isinstance(r2, (int, float)) and not isinstance(r2, bool) and r2 >= 0.99)
        return ("u" in self.fit and not self.stopped and reached and self.rungs() >= MIN_RUNGS
                and (self.fit.get('correction_validation', {}).get('repeat_cv_rms_deg', float('inf')) <= BAD_SIGMA_DEG
                     or self.fit.get("chi2_per_dof", 0) <= MAX_LATEST_CHI2))

    @property
    def sigma(self) -> float | None:
        """How well this run knows the angles across what it measured, in degrees. Smaller is better."""
        return self.fit.get("angle_sigma_measured_span_deg")

    def drive_changed(self) -> bool:
        """The check points read at the start and again at the end disagreed (geo.Ladder.check_state)."""
        return drive_changed(self.fit)

    def reliable(self, radius_range=None) -> bool:
        """Complete, not judged too noisy, and the drive did not change state during the run."""
        from .coverage import range_warning
        local_use = radius_range is not None and self.fit.get('completion_status') in ('candidates_exhausted', 'partial_readable')
        complete = self.geo_complete() or (local_use and 'u' in self.fit and not self.stopped and self.rungs() >= MIN_RUNGS)
        validation = self.fit.get('correction_validation')
        sigma = validation.get('repeat_cv_rms_deg') if validation else self.sigma
        return (complete and (sigma is None or sigma <= BAD_SIGMA_DEG)
                and (radius_range is None or range_warning(self.fit, radius_range) is None)
                and not self.drive_changed())

    def quality(self) -> str:
        if self.is_clv and self.media == "cd":
            return "experimental"
        if not self.geo_complete():
            return "stopped early"
        if self.is_clv:
            return "good" if (self.fit.get("r2") or 0) >= 0.9999 else "usable"
        if self.drive_changed():
            return "drive changed"
        if not self.reliable():
            return "too noisy"
        span = self.fit.get("measured_span_mm") or [0, NARROW_SPAN_MM]
        if span[1] - span[0] < NARROW_SPAN_MM:
            return "narrow span"
        validation = self.fit.get('correction_validation')
        if validation:
            return 'good' if validation.get('repeat_cv_rms_deg', float('inf')) <= GOOD_SIGMA_DEG else 'usable'
        return "good" if self.sigma is not None and self.sigma <= GOOD_SIGMA_DEG and self.fit.get("chi2_per_dof", 0) <= 2 else "usable"

    def rotation(self) -> str | None:
        return ((self.summary.get("period") or {}).get("rotation") or {}).get("mode")

    def describe(self) -> str:
        if self.kind == "geo":
            f = self.fit
            if self.is_clv:
                if "r0_mm" not in f:
                    return "stopped before the period fit"
                state = "" if self.geo_complete() else "  (stopped early)"
                return (f"{self.zones()} zones, R^2 {f.get('r2', 0):.6f}, r0 {f.get('r0_mm', 0):.3f} mm, "
                        f"pitch {f.get('pitch_um', 0):.4f} um{state}")
            if "u" not in f:
                return "stopped before the first fit"
            state = "" if self.geo_complete() else "  (stopped early)"
            span = f.get("measured_span_mm") or ["?", "?"]
            if f.get('correction_validation'):
                validation = f['correction_validation']
                return (f"{self.rungs()} rungs, corrected rms {validation['residual_rms_deg']:.2f} deg, "
                        f"repeat CV {validation['repeat_cv_rms_deg']:.2f} deg, {span[0]}-{span[1]} mm{state}")
            return (f"{self.rungs()} rungs, rms {f.get('residual_rms_deg', 0):.2f} deg, "
                    f"chi2/dof {f.get('chi2_per_dof', 0):.1f}, {span[0]}-{span[1]} mm{state}")
        if self.kind == "timing":
            mode = self.rotation()
            if not mode:
                return "stopped before the rotation test"
            jitter = _jitter(self.summary)
            return mode + (f", jitter {min(jitter):.2f}-{max(jitter):.2f} deg" if jitter else "") + ("  (stopped early)" if self.stopped else "")
        if self.kind == "info":
            inq = _parsed(_load(os.path.join(self.path, "info.json")) or {}, "inquiry")
            return f"{inq.get('vendor', '')} {inq.get('product', '')}".strip()
        return ""


def _jitter(summary: dict) -> list[float]:
    zones = (summary.get("period") or {}).get("zones") or []
    return [z["jitter_deg"] for z in zones if z.get("jitter_deg") is not None]


def scan(out: str = "results") -> list[Result]:
    """Result folders, newest first. Names containing `blind` are held-out data and stay unread."""
    found = []
    try:
        names = os.listdir(out)
    except OSError:
        return []
    for name in names:
        m = RESULT_DIR.match(name)
        path = os.path.join(out, name)
        if m and "blind" not in name.lower() and os.path.isdir(path):
            found.append(Result(path, m["kind"], m["tag"], m["stamp"]))
    return sorted(found, key=lambda r: r.when, reverse=True)


def latest_geo(media: str | None = None, out: str = "results", radius_range=None) -> Result | None:
    """The newest measurement of a real disc that can be relied on, or failing that the newest complete one."""
    runs = [r for r in scan(out) if (r.geo_complete() or (radius_range is not None and r.reliable(radius_range)))
            and not r.simulated and (media is None or r.media == media)]
    return next((r for r in runs if r.reliable(radius_range)), runs[0] if runs else None)


def passed_over(chosen: Result, media: str | None = None, out: str = "results") -> int:
    """Newer complete runs that `latest` left out for being too noisy."""
    return sum(r.geo_complete() and not r.simulated and not r.reliable() and r.when > chosen.when and (media is None or r.media == media) for r in scan(out))


def _simulated(summary: dict) -> bool:
    """Whether a geo summary says it came from a simulated drive.

    `geo --sim` does not record that in its summary yet; the result folder's SIM tag is the only
    signal for now, and the summary field is read as soon as geo writes one. A renamed folder
    therefore still gets through, which is why the two are checked apart.
    """
    for holder in (summary, summary.get("setup") or {}, summary.get("identity") or {}):
        if isinstance(holder, dict) and holder.get("simulated"):
            return True
    return False


def _quality_number(fit: dict, name: str) -> float | None:
    """A quality figure from the fit, or None when this summary predates it."""
    value = fit.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None     # NaN compares false with every limit, so it would pass them all
    return float(value)


def drive_changed(fit: dict) -> bool:
    """A run whose check points moved: the fit can look clean while the geometry is off, and its
    angle uncertainty leaves that out (seen on the GH70N: 0.135 deg claimed, 0.29 deg off)."""
    return ((fit or {}).get("state_check") or {}).get("verdict") == "changed"


DRIVE_CHANGED_BLOCK = ("the drive changed during this run (its check points read differently at the end than at the "
                       "start), so the fit can look clean while the geometry is off. Measure again and install a run "
                       "whose check points held.")


def install_blocker(geo_summary: str, allow_simulated: bool = False, radius_range=None) -> str | None:
    """Why a geo result must not be installed as a DiscImageStudio preset, or None when it may.

    A preset outlives the run it came from: it is used to cut discs, and nothing later says it
    came from a simulated drive, a ladder that stopped, or a fit that `results` calls too
    noisy. Everything else in the tool refuses those three, so the install does too. A CD-DA
    result is allowed: it is what DiscImageStudio's audio path is for, and it passes the same
    checks. A quality figure that is missing is not read as zero; `install_warning` says which
    ones could not be checked.
    """
    path = os.path.abspath(geo_summary)
    folder = os.path.dirname(path)
    summary = _load(path)
    if summary is not None and _simulated(summary) and not allow_simulated:
        return ("this is a simulated run (its summary says so), so the preset would describe a drive that "
                "does not exist. Measure a real disc, then install that result.")
    m = RESULT_DIR.match(os.path.basename(folder))
    if m and (m["tag"] or "").startswith("SIM") and not allow_simulated:
        return ("this is a simulated run (the result folder says SIM), so the preset would describe a drive "
                "that does not exist. Measure a real disc, then install that result.")
    if not summary:
        return None            # not ours to judge: disexport reads the same file and reports what is wrong
    stopped = summary.get("stopped")
    if stopped:
        return (f"this run stopped before the end ({i18n.tr(str(stopped))}), so the ladder never reached the "
                f"fit. Run geo again and install a run that finished.")
    fit = summary.get("fit") or {}
    from .coverage import range_warning
    if radius_range is not None:
        warning = range_warning(fit, radius_range)
        if warning and (fit.get('measured_span_mm') or 'coverage' in fit):
            return warning
