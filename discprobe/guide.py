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
    if fit.get("model") == "clv" and fit.get("media") == "cd":
        return CD_CLV_LIMIT
    from .coverage import range_warning
    if radius_range is not None:
        warning = range_warning(fit, radius_range)
        if warning and (fit.get('measured_span_mm') or 'coverage' in fit):
            return warning
    if fit.get("model") == "clv":
        # A Blu-ray run is judged by the T^2 line it fitted, not by an angle ladder: the figures are
        # the zone count and R^2 (`clv.ClvFit`), and a run of that kind has no chi2/dof or angle sigma.
        if _quality_number(fit, "r0_mm") is None:
            return "this run has no geometry fit in its summary.json, so there is nothing to install."
        zones = _quality_number(fit, "zones_used") or 0
        if zones < MIN_BD_ZONES:
            return (f"this run fitted {zones:g} zones, fewer than the {MIN_BD_ZONES} a straight T^2 line needs "
                    f"before `results` trusts it (`geo --media bd --bd-zones` sets how many). A preset is not the "
                    f"place to try one.")
        r2 = _quality_number(fit, "r2")
        if r2 is not None and r2 < MIN_BD_R2:
            return (f"this run's T^2 line only reaches R^2 {r2:.5f}; a disc read at a constant linear speed gives "
                    f"0.999 or better. The spindle speed probably moved during the run, so measure it again.")
        brk = fit.get("break_fit")
        if isinstance(brk, dict) and brk.get("break_lba") is not None:
            return (f"this run's periods step at sector {int(brk['break_lba']):,} instead of rising smoothly: two "
                    f"lines describe it with {float(brk.get('improvement', 0.0)) * 100:.0f}% less residual. A drive "
                    f"reading in zones holds one angular speed per zone, and a preset built on that would place the "
                    f"spiral wrongly.")
        return None
    if drive_changed(fit):
        return DRIVE_CHANGED_BLOCK
    if fit.get("media") == "bd" and isinstance(fit.get("dis_equivalent"), dict):
        # A Blu-ray the drive reads at a constant angular velocity: the angle ladder measured
        # u = r0/b and v = p/b, so the figures to judge are the rung count and chi2/dof.
        anchors = fit["dis_equivalent"]
        if _quality_number(anchors, "inner_radius_mm") is None or _quality_number(anchors, "pitch_um_estimate") is None:
            return "this run's summary has neither an inner radius nor a pitch to build a preset from."
        rungs = _quality_number(fit, "rungs") or 0
        if rungs < MIN_BD_ZONES:
            return (f"this run fitted {rungs:g} rungs, fewer than the {MIN_BD_ZONES} the angle ladder needs "
                    f"before `results` trusts it. A preset is not the place to try one.")
        chi2 = _quality_number(fit, "chi2_per_dof")
        if chi2 is not None and chi2 > MAX_LATEST_CHI2:
            return (f"this run's angle fit leaves chi2/dof {chi2:.1f}; `results` already treats it as unusable, "
                    f"and a preset is not the place to try it.")
        return None
    if "u" not in fit:
        return "this run has no geometry fit in its summary.json, so there is nothing to install."
    status = fit.get('completion_status', 'target_reached')
    if status != 'target_reached' and not (radius_range is not None and status in ('candidates_exhausted', 'partial_readable')):
        return "this run exhausted its candidates before reaching the target; measure again before installing a preset."
    rungs = None
    try:
        with open(os.path.join(folder, "targets.csv"), encoding="utf-8") as f:
            rungs = max(0, sum(1 for _ in f) - 1)
    except OSError:
        pass
    if rungs is not None and rungs < MIN_RUNGS:
        return (f"this run measured {rungs} points, fewer than the {MIN_RUNGS} `results` needs before it trusts a "
                f"fit. A preset is not the place to try one, and another run is the way to get there.")
    validation = fit.get('correction_validation')
    chi2 = _quality_number(fit, "chi2_per_dof") if not validation else None
    if chi2 is not None and chi2 > MAX_LATEST_CHI2:
        return (f"this run's fit leaves chi2/dof {chi2:.1f}; `results` already treats it as unusable, and a "
                f"preset is not the place to try it.")
    sigma = (_quality_number(validation, 'repeat_cv_rms_deg') if validation else
             _quality_number(fit, "angle_sigma_measured_span_deg"))
    if sigma is not None and sigma > BAD_SIGMA_DEG:
        return (f"this run is too noisy to rely on: angles are known to only {sigma:.2f} deg over the measured "
                f"span ({_angle(sigma)}). Another speed usually helps; `results` lists what you have.")
    return None


def install_warning(geo_summary: str) -> str | None:
    """What could not be checked before installing, or None when everything could.

    Said out loud rather than left silent: a summary written before a figure existed would
    otherwise look like a run that passed the check.
    """
    fit = ((_load(os.path.abspath(geo_summary)) or {}).get("fit") or {})
    if fit.get("model") == "clv":
        # A constant-linear-speed run has no chi2/dof or angle sigma by construction: its figures are
        # the zone count and R^2, and `install_blocker` checks both, so nothing is unchecked here.
        return None
    if fit.get("media") == "bd" and isinstance(fit.get("dis_equivalent"), dict):
        # The angle ladder on a Blu-ray: rung count and chi2/dof are both checked by install_blocker.
        return None
    missing = [name for name in ("chi2_per_dof", "angle_sigma_measured_span_deg")
               if _quality_number(fit, name) is None]
    if not missing:
        return None
    return (f"this summary has no {' or '.join(missing)}, so that quality check did not run: it was measured by "
            f"an older version of geo. The preset is still written; judge the run with `results` before using it.")


def info_runs(out: str = "results") -> list[Result]:
    return [r for r in scan(out) if r.kind == "info"]


def _info_identity(run: Result) -> dict:
    report = _load(os.path.join(run.path, "info.json")) or {}
    inq = _parsed(report, "inquiry")
    from .info import disc_id
    return {"drive": f"{inq.get('vendor', '')} {inq.get('product', '')}".strip() or None,
            "disc": disc_id(_parsed(report, "dvd_prerecorded_0e"), _parsed(report, "dvd_plus_adip_11"), _parsed(report, "atip")),
            "last_lba": _parsed(report, "capacity").get("last_lba")}


def identity_of(run: Result, infos: list[Result] | None = None) -> dict:
    """{disc, drive, inferred}. Older runs use the nearest `info` of the same disc on that device."""
    known = run.summary.get("identity") or {}
    if known.get("disc") and known.get("drive"):
        return {"disc": known["disc"], "drive": known["drive"], "inferred": False}
    disc, drive = known.get("disc"), known.get("drive")
    last_lba = (run.summary.get("setup") or {}).get("last_lba")
    same_device = [i for i in (info_runs() if infos is None else infos) if i.tag == run.tag]
    for i in sorted(same_device, key=lambda i: abs((i.when - run.when).total_seconds())):
        who = _info_identity(i)
        drive = drive or who["drive"]
        if abs((i.when - run.when).total_seconds()) <= MATCH_INFO_S and last_lba is not None and who["last_lba"] == last_lba and who["disc"]:
            disc = disc or who["disc"]
            break
    tag = run.tag + ":" if run.tag and re.fullmatch("[A-Za-z]", run.tag) else run.tag
    return {"disc": disc or "unknown disc", "drive": drive or (f"drive {tag}" if tag else "unknown drive"), "inferred": True}


def resolve_geo(value: str, media: str | None = None, out: str = "results", radius_range=None) -> str:
    """--geo takes a summary.json, a geo result folder, or `latest`. Raises ValueError with what to do."""
    if value.lower() == "latest":
        r = latest_geo(media, out, radius_range=radius_range)
        if r is None:
            have = any(x.kind == "geo" for x in scan(out))
            partial = [x for x in scan(out) if x.kind == 'geo' and not x.simulated and
                       x.fit.get('completion_status') in ('candidates_exhausted', 'partial_readable')]
            if partial:
                spans = [(x.fit.get('coverage') or {}).get('measured_intervals_mm', x.fit.get('measured_span_mm')) for x in partial]
                raise ValueError(f'--geo latest: only partial measurements cover radii {spans} mm. '
                                 'Use an explicit summary.json within its measured intervals; outside is extrapolation.')
            why = "only simulated or stopped runs were found" if have else "there is no geo result yet"
            raise ValueError(f"--geo latest: {why} in {out}. Run geo first, or give a summary.json path.")
        return os.path.join(r.path, "summary.json")
    return os.path.join(value, "summary.json") if os.path.isdir(value) else value


def describe_chosen(path: str) -> str:
    folder = os.path.dirname(path)
    m = RESULT_DIR.match(os.path.basename(folder))
    if not m:
        return short(path)
    return f"{short(path)} ({i18n.tr(Result(folder, m['kind'], m['tag'], m['stamp']).describe())})"


def missing_packages() -> list[str]:
    return [pip for module, pip in (("numpy", "numpy"), ("PIL", "pillow"))
            if importlib.util.find_spec(module) is None]


def optical_drives() -> list[str]:
    if sys.platform not in ("win32", "linux"):
        return []
    from .device import list_optical_drives
    return list_optical_drives()


def drive_flag(args=None) -> str:
    """How the next command should name the drive."""
    if args is not None and getattr(args, "sim", None):
        return f"--sim {args.sim}"
    if args is not None and getattr(args, "drive", None):
        return f"--drive {args.drive}"
    drives = optical_drives()
    return f"--drive {drives[0]}" if drives else ("--drive /dev/sr0" if sys.platform == "linux" else "--drive E:")


def _carry(args, media: str | None = None) -> str:
    """Options the next drive command should repeat."""
    parts = [drive_flag(args)]
    media = media or getattr(args, "media", "dvd")
    if media == "cd":
        parts.append("--media cd")
    elif media == "bd":
        parts.append("--media bd")
    if getattr(args, "sectors", 1) == 16:
        parts.append("--sectors 16")
    if getattr(args, "transport", "auto") != "auto":
        parts.append(f"--transport {args.transport}")
    if getattr(args, "out", "results") != "results":
        parts.append(f"--out {quote(args.out)}")
    return " ".join(parts)


def _carry_geo(args) -> str:
    """_carry, plus what only geo takes."""
    offset = getattr(args, "read_offset_bytes", 0.0)
    return _carry(args) + (f" --read-offset-bytes {offset:g}" if offset else "")


CD_CLV_LIMIT = ("Experimental CD CLV geometry gives an anchored radius and constant pitch, not a calibrated "
                "sector-angle map. It cannot determine the along-track constant or pitch variation. "
                "Use another drive for CAV geometry and calibrate in DiscImageStudio before burning a picture.")


def speed_advice(args, family: str | None = None, summary: dict | None = None) -> dict:
    """Remember completed rotation tests in the selected results root; never open a drive."""
    media = family if family in ALTERNATIVE_SPEEDS else getattr(args, "media", "dvd")
    current = str(getattr(args, "speed", ""))
    sim = getattr(args, "sim", None)
    endpoint = str(getattr(args, "drive", "") or "").casefold()
    identity = (summary or {}).get("identity") or {}
    tried = {}
    for run in scan(getattr(args, "out", "results")):
        old = run.summary.get("args") or {}
        mode = (run.rotation() if run.kind == "timing" else
                ((run.summary.get("rotation_measured") or run.summary.get("rotation_check") or {}).get("mode")))
        reason = str(run.summary.get('stopped') or '')
        if not mode and any(word in reason for word in ('never settled', 'speed is not steady', 'constant speed', 'no clear period')):
            mode = 'unstable'
        if run.kind not in ("timing", "geo") or run.media != media or not mode:
            continue
        if run.kind == "timing" and run.stopped and mode != 'unstable':
            continue
        if sim:
            if old.get("sim") != sim:
                continue
        elif run.simulated or not endpoint or str(old.get("drive") or run.summary.get("device") or "").casefold() != endpoint:
            continue
        previous = run.summary.get("identity") or {}
        if any(identity.get(k) and previous.get(k) and identity[k] != previous[k] for k in ("drive", "firmware")):
            continue
        speed = str(old.get("speed", ""))
        if speed.isdigit():
            tried.setdefault(speed, mode)  # newest verdict wins
    rotation = (((summary or {}).get("period") or {}).get("rotation") or {}).get("mode")
    if current.isdigit() and (not summary or (rotation and not summary.get("stopped"))):
        tried[current] = rotation or tried.get(current)
    rotation = rotation or tried.get(current)
    choices = [s for s in ALTERNATIVE_SPEEDS[media] if s not in tried]
    if media == "cd" and rotation == "CLV":
        choices.sort(key=lambda s: (int(s) <= int(current) if current.isdigit() else False, int(s)))
    return dict(media=media, tried=sorted(tried, key=int), next_speed=choices[0] if choices else None,
                exhausted=not choices,
                all_clv=all(tried.get(s) == "CLV" for s in ALTERNATIVE_SPEEDS[media]))


def _other_speed(args, family: str | None = None) -> str | None:
    return speed_advice(args, family)["next_speed"]


def _speed_word(args) -> str:
    """How to name _other_speed. It is a higher one when this run is already at the lowest we list."""
    current = getattr(args, "speed", None)
    other = _other_speed(args)
    return "a lower speed" if current and other and int(other) < current else "a different speed"


def _clv_next(args, advice: dict) -> list[str]:
    media, other = advice["media"], advice["next_speed"]
    carry = _carry(args, media)
    lines = []
    if other:
        lines += ["Next, try an untried speed (kB/s):",
                  f"  {PROG} timing {carry} --speed {other}"]
        if media == "cd":
            lines.append("A higher CD speed may allow CAV.")
    elif advice["all_clv"]:
        lines.append(f"This drive appears to keep a constant linear speed for {media.upper()}s at every speed tried.")
    else:
        lines.append("Every speed on the list has been tried. No untried speed remains; try another drive.")
    if not other:
        lines.append("Try another drive. timing --force only continues diagnostic sampling; it does not force CAV or make CLV sector angles valid.")
    if media == "bd":
        speed = f" --speed {args.speed}" if getattr(args, "speed", None) else " --speed keep"
        lines += ["CLV can still give anchored Blu-ray geometry:", f"  {PROG} geo {carry}{speed} --bd-zones 25"]
    elif media == "cd":
        lines += [CD_CLV_LIMIT,
                  "For research, geo --media cd --cd-clv needs an independently known --linear-mm-s or an explicit --pitch-um anchor. A requested read speed is not a measured anchor."]
    return lines


def sectors_from_info(report: dict) -> tuple[int, str] | None:
    """The sector count `disexport --sectors` wants, from an `info` report, with where it came from."""
    track = _parsed(report, "track_1")
    if track.get("blank") and track.get("free_blocks"):
        return track["track_start"] + track["free_blocks"], "free space of this blank disc"
    atip = _parsed(report, "atip")
    if atip.get("last_leadout_start_lba"):
        return atip["last_leadout_start_lba"], "lead-out in the ATIP; `info` on a blank disc gives a closer count"
    cap = _parsed(report, "capacity")
    if cap.get("last_lba"):
        return cap["last_lba"] + 1, "last LBA + 1, the blank size only if this disc was burned full"
    return None


def _sectors_for(summary: dict, out: str) -> tuple[str, str]:
    """A --sectors value for the preset command, and what the reader should check about it."""
    fit_media = (summary.get("fit") or {}).get("media")
    media = fit_media if fit_media in ("cd", "dvd", "bd") else "dvd"
    for r in scan(out):
        if r.kind == "info" and not r.simulated:
            report = _load(os.path.join(r.path, "info.json")) or {}
            found = sectors_from_info(report)
            profile = _parsed(report, "configuration").get("current_profile")
            # The newest `info` may be of the other kind of disc: its count would be far off.
            if found and mmc.media_family(profile) in (media, "unknown"):
                return str(found[0]), f"--sectors is from your last `info`: {found[1]}"
    last = (summary.get("setup") or {}).get("last_lba")
    if last:
        return str(last + 1), "--sectors is how much was burned on the measured disc. A blank can hold more: `info` on a blank gives its count."
    return "<sectors>", "run `info` on a blank disc to find --sectors"


def _random_for_blank(report: dict) -> list[str]:
    """What to say and the command for a random-data disc that fits this blank."""
    family = mmc.media_family(_parsed(report, "configuration").get("current_profile"))
    media = "cd" if family == "cd" else "dvd"
    flag, iso = (" --media cd", "iso/cd-random.iso") if media == "cd" else ("", "iso/random.iso")
    found = sectors_from_info(report)
    if found and _parsed(report, "track_1").get("blank") and found[0] - RANDOM_SECTORS[media] < BURN_ROOM_SECTORS[media]:
        sectors = int(found[0] * BURN_FILL) // 16 * 16
        return ["Nothing is recorded on this disc, so timing cannot use it. The usual random disc would not fit, so make a smaller one:",
                f"  {PROG} random{flag} --sectors {sectors} --output {iso}"]
    return ['An existing recorded plain-data disc can be measured without a new burn. '
            'If none is available, nothing is recorded on this blank for timing; make a random-data disc:',
            f"  {PROG} random{flag} --output {iso}"]


def sectors_hint(geo_path: str) -> str:
    """What to do when a preset command has no --sectors."""
    sectors, why = _sectors_for(_load(geo_path) or {}, "results")
    if sectors == "<sectors>":
        return "Run `info` on a blank disc to get the count, and enter the same number in DiscImageStudio."
    return (f"Try --sectors {sectors} ({why}). Enter the same number in DiscImageStudio. "
            "`info` on a blank disc is the count to go by: one user found read-from-disc there too high.")


def after_list(drives: list[str]) -> list[str]:
    if not drives:
        return [("Plug the drive in and check that it shows up in Explorer," if sys.platform == "win32" else
                 "Plug the drive in and check that its device path appears under /dev,"),
                f"or try the flow on the simulated drive: {PROG} timing --sim cav"]
    lines = ["Next, see what the drive and disc report:", f"  {PROG} info --drive {drives[0]}"]
    if len(drives) > 1:
        lines.append("With several drives, use the letter of the one holding your disc." if sys.platform == "win32" else
                     "With several drives, use the device path of the one holding your disc.")
    return lines


def after_info(args, report: dict) -> list[str]:
    if mmc.not_ready((report.get("test_unit_ready") or {}).get("sense")):
        return []
    lines = []
    found = sectors_from_info(report)
    if found:
        lines += [f"Sector count for disexport --sectors: {found[0]} ({found[1]}).",
                  "Enter the same number in DiscImageStudio. A blank disc's `info` is the count to go by: one user found read-from-disc there too high.", ""]
    cap = _parsed(report, "capacity").get("last_lba")
    if _parsed(report, "track_1").get("blank") or not cap or cap < 1000:
        return lines + _random_for_blank(report)
    return lines + ["Next, check the drive (1 to 3 minutes):", f"  {PROG} timing {_carry(args)}"]


def after_timing(args, summary: dict) -> list[str]:
    media = getattr(args, "media", "dvd")
    rotation = ((summary.get("period") or {}).get("rotation") or {}).get("mode")
    if not rotation:
        return []
    family = (summary.get("setup") or {}).get("family")
    blu_ray = family == "bd"
    advice = speed_advice(args, family, summary)
    carry, other = _carry(args, advice["media"]), advice["next_speed"]
    simulated = ["This was the simulated drive, so the verdict below says nothing about your own drive.", ""] if getattr(args, "sim", None) else []
    if rotation != "CAV":
        return simulated + [f"Verdict: rotation is {rotation}, not CAV, so sector angles cannot be read at this speed.",
                            *_clv_next(args, advice)]
    jitter = _jitter(summary)
    worst = max(jitter) if jitter else None
    span = f"{min(jitter):.2f}-{worst:.2f} deg" if jitter else ""
    lines = list(simulated)
    if worst is None:
        lines.append("Verdict: rotation is CAV, but no jitter was measured.")
    elif worst <= GOOD_JITTER_DEG:
        lines.append(f"Verdict: CAV with {span} jitter. This drive looks usable.")
    else:
        lines.append(f"Verdict: CAV, but {span} jitter is noisy. Another speed may help:" if worst <= BAD_JITTER_DEG
                     else f"Verdict: CAV, but {span} jitter is too high: drives reported at this level stopped early "
                          "or gave a wrong geometry. Try another speed or another drive:")
        lines.append(f"  {PROG} timing {carry} --speed {other}" if other else
                     "Every speed on the list has been tried. No untried speed remains; try another drive.")
        if media == "dvd" and not blu_ray and getattr(args, "sectors", 1) == 1:
            lines.append(f"  Or read whole ECC blocks, which was cleaner on one drive: {PROG} timing {carry} --sectors 16")
    if blu_ray:
        return lines + ["", "Next, measure the geometry (a straight T^2 line over 25 zones, about 2 minutes):",
                        f"  {PROG} geo {carry} --bd-zones 25"]
    usual = 1411 if media == "cd" else None
    speed = f" --speed {args.speed}" if getattr(args, "speed", None) not in (None, usual) else ""
    note = ["  It sets 4x first. If that takes this drive out of constant rotation, it stops and says what to do."] if media == "dvd" and getattr(args, "speed", None) is None else []
    return lines + ["", "Next, measure the geometry:", f"  {PROG} geo {carry}{speed}", *note]


def after_timing_stop(args, reason: str) -> list[str]:
    media = getattr(args, "media", "dvd")
    flag = {"cd": " --media cd", "bd": " --media bd"}.get(media, "")
    iso = {"cd": "iso/cd-random.iso", "bd": "iso/bd-random.iso"}.get(media, "iso/random.iso")
    if "cannot read" in reason or "recorded area" in reason or "fails on" in reason or "time limit" in reason:
        return ['First reuse an existing recorded data disc; close other drive software, reload and check the saved command errors.',
                'Retry reading at an untried speed or with another available drive. Do not burn to fix a timeout.',
                f'Only if no usable recorded data remains and no existing data disc is available, make one: {PROG} random{flag} --output {iso}']
    return []


def compare_pitch(out: str, with_sigma: bool = False) -> tuple | None:
    """chi2/dof of the constant-pitch and quadratic-pitch fits of a finished run, by tools/geo_polyfit.py."""
    from .resources import tool
    path = str(tool("geo_polyfit.py"))
    try:
        spec = importlib.util.spec_from_file_location("geo_polyfit", path)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        n, y, s, fit = tool.load(out)
        scale = fit["bit_nm_assumed"] * 1e-6
        ratios = []
        for order in (0, 2):
            f = tool.fit(n, y, s, fit["u"], fit["v"], order, tool.RC_MM / scale, tool.RS_MM / scale)
            ratios.append(f["chi2"] / f["dof"])
        return (ratios[0], ratios[1], f["span_sigma_deg"]) if with_sigma else (ratios[0], ratios[1])
    except Exception:       # only advice depends on this; the measurement is already saved
        return None


def geo_summary(res: dict, rungs: int) -> str:
    span = res["measured_span_mm"]
    if res.get('correction_validation'):
        validation = res['correction_validation']
        value = validation.get('independent_rms_deg')
        check = f'{value:.2f}' if value is not None else 'unknown'
        return (f"Measured {rungs} points across {span[0]}-{span[1]} mm with a variable-pitch correction; "
                f"independent check rms {check} deg. Model bias between samples is not bounded.")
    return (f"Measured {rungs} points across {span[0]}-{span[1]} mm: angles known to about "
            f"{res['angle_sigma_measured_span_deg']:.2f} deg, points {res['residual_rms_deg']:.2f} deg from the fit on average.")


def _angle(sigma: float) -> str:
    return f"{sigma:.2f} deg is about {math.radians(sigma) * 50:.2f} mm at 50 mm radius"


def _noisy(sigma: float) -> str:
    return (f"too noisy to rely on: {_angle(sigma)}." if sigma > BAD_SIGMA_DEG
            else f"usable, but noisy: {_angle(sigma)}.")


def _state_lines(res: dict, lines: list[str], retry: list[str]) -> list[str]:
    """The check points read at the start and again at the end (geo.Ladder.check_state). A drive whose timing
    changed during the run in a way that depends on the radius bends the geometry while the fit still looks
    clean, so "changed" replaces the verdict."""
    sc = res.get("state_check")
    if not sc:
        return lines
    moved = [p for p in sc["points"] if p.get("change_deg") is not None]
    worst = max(moved, key=lambda p: abs(p["change_deg"])) if moved else None
    if sc["verdict"] == "changed":
        alone = abs(worst["change_deg"]) > max(sc["tolerance_deg"], sc["sigmas"] * worst["sigma_deg"])
        what = (f"the point at {worst['radius_mm']} mm read {worst['change_deg']:+.2f} deg differently at the end "
                "than at the start, more than its noise" if alone else
                f"the check points read {sc['mean_change_deg']:+.2f} deg differently on average at the end than at "
                "the start, more than their noise")
        return [line for line in lines if not line.startswith("Verdict:")] + [
            f"Verdict: not settled. The drive changed during the run: {what}. The fit can look clean anyway, and "
            "its angle uncertainty leaves this out, so the geometry can be further off than it says.",
            "Measure again later, after the drive has been idle for a while, or eject and reload the disc first:", *retry]
    if sc["verdict"] == "steady":
        return lines + [f"Points read at the start and again at the end agree within {sc['tolerance_deg']} deg, "
                        "so the drive stayed in one state."]
    if sc["verdict"] == "inconclusive":
        return lines + [f"Points read at the start and again at the end can't show a change of "
                        f"{sc['tolerance_deg']} deg: the reads were too noisy"
                        + (f" (largest difference {worst['change_deg']:+.2f} deg)." if worst else ".")]
    return lines + ["The points read at the start could not all be read again at the end, so it is not known "
                    "whether the drive stayed in one state."]


def after_geo(args, res: dict, out: str) -> list[str]:
    media = getattr(args, "media", "dvd")
    summary = _load(os.path.join(out, "summary.json")) or {}
    m = RESULT_DIR.match(os.path.basename(out))
    real_and_whole = m and not getattr(args, "sim", None) and Result(out, m["kind"], m["tag"], m["stamp"]).reliable()
    geo = "latest" if real_and_whole else short(out)
    flag = " --media cd" if media == "cd" else ""
    sectors, why = _sectors_for(summary, getattr(args, "out", "results"))
    span = res.get("measured_span_mm") or [25.8, 54.4]
    correction = ""
    lines = []
    if res.get('correction_file'):
        s = res['correction_validation']
        correction = ' --correction ' + short(os.path.join(out, res['correction_file']))
        lines = ["Track pitch varies. Extra repeated points were measured and a smooth angle correction was saved.",
                 f"Correction residual: rms {s['residual_rms_deg']:.3f} deg, max {s['residual_max_deg']:.3f} deg; repeat CV {s['repeat_cv_rms_deg']:.3f} deg.",
                 f"Extra probing took {s['elapsed_s']:.1f} s. Thin radius intervals (mm): {s['thin_intervals_mm']}.",
                 f"Measured radius range: {span[0]}-{span[1]} mm. Outside measured intervals is extrapolation.",
                 "The correction is used automatically with this geometry. To disable extra probing on a new run, use geo --no-auto-correction.",
                 "A cubic-pitch DIS preset may not reproduce this spline; check its conversion error before use.",
                 f"  {PROG} image{flag} --geo {short(out)}{correction} --picture my_picture.png --output iso/picture.iso"]
        if res.get('completion_status', 'target_reached') != 'target_reached':
            lines.insert(0, 'Partial measurement: the correction did not pass all coverage or independent checks.')
        return _state_lines(res, lines, [])
    if getattr(args, "sim", None):
        lines.append("This was the simulated drive: the verdict and commands below show the flow, do not burn from them.")
    compared = compare_pitch(out) if res["chi2_per_dof"] > 2 else None
    sigma = res["angle_sigma_measured_span_deg"]
    other = _other_speed(args)
    retry = ([f"  {PROG} geo {_carry_geo(args)} --speed {other}"] if other else
             ["Every speed on the list has been tried. No untried speed remains; try another drive."])
    word = _speed_word(args)
    too_noisy = sigma > BAD_SIGMA_DEG
    if res["chi2_per_dof"] <= 2:
        if sigma <= GOOD_SIGMA_DEG:
            lines.append(f"Verdict: good. The model is compatible with the measured points, and {_angle(sigma)}.")
        else:
            lines += [f"Verdict: {_noisy(sigma)}", f"For a cleaner run, try {word} or another drive:", *retry]
    elif compared is None:
        lines.append("Verdict: not settled. More than noise is left, and the comparison below could not run here.")
    elif compared[1] <= PITCH_CLEARLY_BETTER * compared[0]:
        detailed = compare_pitch(out, with_sigma=True)
        corrected = detailed[2] if detailed is not None else None
        if corrected is None:
            lines.append("Verdict: correction uncertainty is unknown. Refit the measured points before relying on it.")
        else:
            lines.append("Verdict: good once corrected." if corrected <= GOOD_SIGMA_DEG
                         else f"Verdict: a correction helps, but it stays noisy: {_angle(corrected)}.")
    elif too_noisy:
        lines.append(f"Verdict: {_noisy(sigma)}")
    else:
        lines.append("Verdict: usable, but noisy.")
    lines = _state_lines(res, lines, retry)
    if span[1] - span[0] < NARROW_SPAN_MM:
        lines.append(f"This run only covers {span[0]}-{span[1]} mm, so angles outside that are extrapolated.")
    lines.append(f"Measured radius range: {span[0]}-{span[1]} mm. Outside measured intervals is extrapolation.")
    if res.get('completion_status', 'target_reached') != 'target_reached':
        lines.insert(0, 'Partial measurement: candidates ran out; use only the measured radius intervals.')
    if res["chi2_per_dof"] > 2:
        if compared is None:
            lines += ["The fit left more than noise. Compare pitch models first, no new measurement needed; if quadratic is",
                      "clearly better, write a correction and add --correction correction.json to the commands below:",
                      f"  python tools/geo_polyfit.py {short(out)}",
                      f"  python tools/geo_polyfit.py {short(out)} --write-correction correction.json --order quadratic"]
        elif compared[1] <= PITCH_CLEARLY_BETTER * compared[0]:
            correction = " --correction correction.json"
            lines += [f"A varying track pitch fits clearly better (fit error ratio {compared[0]:.1f} -> {compared[1]:.1f}). "
                      "Write a correction first; the commands below use it:",
                      f"  python tools/geo_polyfit.py {short(out)} --write-correction correction.json --order quadratic"]
            if corrected is None or corrected > GOOD_SIGMA_DEG:
                lines += [f"For a cleaner run, try {word} or another drive:", *retry]
        elif too_noisy:
            lines += [f"A varying track pitch does not fit better (fit error ratio {compared[0]:.1f} -> {compared[1]:.1f}), so the "
                      f"extra scatter is probably read noise. Try {word} or another drive:", *retry]
        else:
            lines += [f"A varying track pitch does not fit better (fit error ratio {compared[0]:.1f} -> {compared[1]:.1f}), so the "
                      f"extra scatter is probably read noise. You can carry on. For a cleaner run, try {word}:", *retry]
    lines.append("")
    preset = [f"  {PROG} disexport --geo {geo}{correction} --sectors {sectors} --r-min {span[0]} --r-max {span[1]} "
              "--output dis_preset.json",
              "  Enter the same --sectors in DiscImageStudio.",
              f"  {why}"]
    picture = f"  {PROG} image{flag} --geo {geo}{correction} --picture my_picture.png --output iso/picture.iso"
    if res.get("track") == "audio":
        return lines + ["Next, export a DiscImageStudio preset. This was measured on the audio track, so no other constant is needed:",
                        *preset,
                        f"It is right as far as --read-offset-bytes ({res.get('read_offset_bytes', 0.0):g}) is right for this drive: "
                        "check it once with a burned straight line.",
                        "image and tiles do not take this result: they write a data track, which counts from another origin."]
    where = f"Put the picture in {os.getcwd()}, or give its full path (in quotes if it has spaces):"
    if media == "cd":
        return lines + ["Next, export a DiscImageStudio preset. CD has one more constant that timing cannot see, and fine",
                        "calibration there settles it on one more blank disc (the CD route in README.md):", *preset,
                        "Or make a picture ISO now (replace my_picture.png); radial lines may come out twisted without that constant:",
                        where, picture]
    return lines + ["Next, make a picture ISO (replace my_picture.png with your image):", where, picture,
                    f"To move or size the picture on the disc first: {PROG} edit my_picture.png",
                    "Or export a DiscImageStudio preset:", *preset]


def after_geo_stop(args, reason: str, unreadable=()) -> list[str]:
    """`unreadable`: LBAs that gave a medium error. Plain random data rarely does, so with no --ranges the
    likelier cause is a disc that holds something else too (texture rings, a picture, a second session),
    and its other textures read at another latency; another speed would not help."""
    if reason in mmc.NOT_READY:
        return []
    carry, other, word = _carry(args), _other_speed(args), _speed_word(args)
    if other is None and any(s in reason for s in ("never settled", "near the reference", "whole-turn", "safe")):
        return ["Every speed on the list has been tried. No untried speed remains; try another drive."]
    again = _carry_geo(args)
    if "not turning at a constant speed" in reason:
        if getattr(args, "speed", None) is None:
            return ["This drive isn't holding a constant speed even when left alone, so geo can't measure on it with this disc.",
                    "Another drive is the better bet."]
        return ["Setting the speed can take a drive out of constant rotation, and many keep it until the disc is reloaded.",
                "Eject the disc and put it back, check that timing says CAV, then run geo without setting a speed:",
                f"  {PROG} timing {carry}", f"  {PROG} geo {again} --speed keep"]
    if unreadable and not (getattr(args, "ranges", None) or getattr(args, "rings_layout", None)):
        where = ", ".join(str(lba) for lba in list(unreadable)[:3])
        flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
        return [f"Reads at LBA {where} failed with a medium error, which plain random data rarely gives.",
                "If this disc holds anything else (texture rings, a picture, a second session), measure only its random part:",
                f"  {PROG} geo {again}{f' --speed {args.speed}' if getattr(args, 'speed', None) else ''} --ranges a-b,c-d",
                "For a texture-ring disc, --rings-layout with its .rings.json file does that for you.",
                'First retry the failed reads on this same disc with another available drive or read speed.',
                f"Only if recorded data is unreadable and no existing data disc is available, replace it: {PROG} random{flag} --output iso/random.iso"]
    if "never settled" in reason or "near the reference" in reason:
        return [f"The drive would not hold one speed. Check it with timing, then try geo at {word}:",
                f"  {PROG} timing {carry}", f"  {PROG} geo {again} --speed {other}",
                "USB slim drives are often too noisy here; an internal drive may simply work."]
    if "whole-turn" in reason or "safe" in reason:
        return [f"A whole-turn count went wrong, or the pitch varies more than the model allows. Try {word}:",
                f"  {PROG} geo {again} --speed {other} --reps 32",
                "If it keeps stopping near one LBA, leave that area out with --ranges a-b (see `geo -h`).",
                "Variable pitch is followed automatically, with closer rungs and repeated correction probes. Keep the whole-turn safety limit."]
    if "ranges" in reason:
        return ["--ranges has to overlap the recorded area. See the last LBA with:", f"  {PROG} info {carry}"]
    if "recorded area" in reason or "medium" in reason or "fails on" in reason:
        flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
        return ['geo needs readable plain data. Check an existing recorded disc and its saved info first; retry the read on the same disc.',
                f"Only if no usable recorded data remains and no existing data disc is available, make one: {PROG} random{flag} --output iso/random.iso"]
    return [f"See how noisy this drive is: {PROG} timing {carry}"]


def burner_hint() -> list[str]:
    """Windows' burn window can open on another drive, and then it looks as if there were no burner."""
    if sys.platform != "win32":
        return []
    drives = optical_drives()
    return [Quiet(f"In the burn window, check the burner is {drives[0] if len(drives) == 1 else 'your optical drive'}: it can point at another drive.")]


def burn_steps(output: str, media: str = "dvd") -> list[str]:
    """Platform-specific burn instructions; the caller supplies the ISO and disc type."""
    if sys.platform == "win32" and media == "cd":
        from .burner import imapi_cd_command
        import subprocess
        drive = drive_flag().removeprefix("--drive ")
        return ["Burn it at 8x with the IMAPI script (Windows' own Burn disc image picks 40x, which failed on a GH70N with cheap CD-R):",
                "  " + subprocess.list2cmdline(imapi_cd_command(drive, output)),
                "The tray opens when it is done; -Reload pulls it back in."]
    if sys.platform == "win32":
        return ["(Windows: right-click the .iso, Burn disc image).", *burner_hint()]
    if sys.platform != "linux":
        return ["Burn it with your system's image-burning tool."]
    drive = drive_flag().removeprefix("--drive ")
    if media == "cd":
        toc = os.path.splitext(output)[0] + ".toc"
        return ["Burn it with cdrdao and the toc written next to the ISO:",
                f"  cdrdao write --device {drive} {quote(toc)}",
                "The toc burns the sectors in the layout the ISO was made for (--cd-sector, default Mode 2 Form 1, as IMAPI writes). "
                "Other burners such as xorriso write Mode 1, and the textures come out as noise. "
                "cdrdao with this layout has been checked on a real disc on Windows, not yet on Linux."]
    return ["Unmount the disc before burning. For example, use this command-line image burner:",
            f"  growisofs -dvd-compat -Z {drive}={quote(output)}"]


def after_random(args) -> list[str]:
    flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
    fits = "If the burner says it does not fit, make a smaller one with --sectors."
    if sys.platform not in ("win32", "linux"):
        return ["Burn it onto a blank disc with your system's burning tool, and keep some blanks of the same batch for pictures.",
                fits, PORTS, f"  {PROG} timing --sim cav{flag}"]
    if sys.platform == "linux" or getattr(args, "media", "dvd") == "cd":     # a CD on Windows: the IMAPI script, not the right-click
        return ["Burn it onto a blank disc, and keep some blanks of the same batch for pictures.",
                *burn_steps(getattr(args, "output", "iso/random.iso"), getattr(args, "media", "dvd")), fits,
                "Then check the drive with it (1 to 3 minutes):", f"  {PROG} timing {drive_flag()}{flag}"]
    return ["Burn it onto a blank disc (Windows: right-click the .iso, Burn disc image), and keep some blanks of the same batch for pictures.",
            *burner_hint(), fits, "Then check the drive with it (1 to 3 minutes):", f"  {PROG} timing {drive_flag()}{flag}"]


def after_edit(path: str, media: str = "dvd") -> list[str]:
    flag = " --media cd" if media == "cd" else ""
    return ["Next, make the disc image from it (you can open the design again with edit first):",
            f"  {PROG} image{flag} --geo latest --design {short(path)} --output iso/picture.iso"]


def after_image(output: str, preview: str, geometry: str, picture: str | None = None, design: str | None = None,
                media: str = "dvd", simulated: str | None = None) -> list[str]:
    """What to do with a finished picture ISO. One made from a simulated run must not reach a disc.
    Made from a picture or a design file, it also says how to place it with edit, since that is what a look at it asks,
    and on a DVD how to see a simulated photo of it (`simulated` when one was just made)."""
    lines = [f"Next, check the preview: {short(preview)}"]
    flag = " --media cd" if media == "cd" else ""
    if simulated:
        lines += [f"And the simulated photo (a model, not a measurement): {short(simulated)}"]
    elif media != "cd" and (design or picture):
        source = f"--design {short(design)}" if design else f"--picture {short(picture)}"
        sheet = short(os.path.splitext(output)[0] + ".simulated.png")
        lines += ["To see roughly how it may look in a photo (a model, not a measurement; about ten seconds):",
                  f"  {PROG} simulate {source} --sheet {sheet}"]
    if design:
        lines += ["To change where it sits, its size or turn, open the design again, then make the ISO the same way:",
                  f"  {PROG} edit{flag} {short(design)}"]
    elif picture:
        lines += ["To move, size or turn it on the disc, or change where grey turns dark:",
                  f"  {PROG} edit{flag} {short(picture)}",
                  "It saves a design file. Then make the ISO again with --design and that file instead of --picture."]
    if "geo-SIM-" in geometry:
        return lines + ["This geometry came from the simulated drive, so it only shows the flow: do not burn this ISO."]
    return lines + [f"If it looks right, burn {short(output)} to a blank disc from the batch you measured",
                    *burn_steps(output, media),
                    "Once it is burned, this says how to look at it and what to do next:", f"  {PROG} guide"]


# Said by `guide` once a picture ISO exists: the program has long exited by the time the burn is done.
AFTER_BURN = ("How to look at it, not straight on, which only shows your own reflection:",
              "  Turn off the room lights and hold a small light, such as a phone torch, right beside your eyes.",
              "  Hold the disc about a metre away and tilt it a little, so it reflects the dark and not the light or you.",
              "  Turn it slowly: when the surface goes dark, the picture shows. The rainbow fan is the grooves, not your picture.",
              "  The preview shows the data side, the side you are looking at.",
              "What you may see:",
              "  The picture, in the right place: done. More pictures from this batch start at `image`, with no new measurement.",
              "  No picture: check three things in this order before burning anything: the light (the most likely cause), then the burn report (written, closed, read back), then the geometry.",
              "  Twisted or broken lines: check it was the same batch and the same burner. If so, the geometry may be off.",
              "  Burn the grid test on another blank only if the light and the burn report are fine and the lines are still twisted. Its straight lines tell a wrong geometry from a wrong picture:",
              f"  {PROG} image --geo latest --output iso/grid.iso",
              "  The burn failed or stopped: a DVD+R, DVD-R or CD-R can't be used again, so take a new blank. Failing again? Try another burn speed; slower is not always better.")


# The web page's start-here guide (web/home/guidance.mjs) says the same four things in the same order.
def tutorial_lines() -> list[str]:
    return ["Before you start, four things:",
            "  How the picture forms: the data side is a tight spiral of tracks, like a diffraction grating. Light on it spreads into a rainbow by angle,",
            "  and disc-probe decides what is written where, so that at the right angle the picture shows. It shows in the dark, under a small light.",
            "  What you need: a burner on Windows or Linux that can also read the disc, and blank discs from one box. DVD-R has worked best.",
            "  How many discs: the goal is the finished picture on disc 3, or on disc 4 if the error is large. It is a goal, not a promise.",
            "  Disc 1 measures, disc 2 is a check you photograph, disc 3 is the picture.",
            "  A bad photo (too dark, not the whole disc, glare) is retaken, not re-burned.",
            "Already use DiscImageStudio? Run the web page (python -m discprobe webui) and use Import / Export on the desk to bring its preset in.",
            "",
            "1. Burn a random-data disc. It is not your picture yet: it is how the program learns this kind of disc.",
            f"  {PROG} random --output iso/random.iso",
            "  This uses up the disc: a DVD+R, DVD-R or CD-R can't be erased.",
            *burn_steps("iso/random.iso"),
            "2. Check the drive with that disc, 1 to 3 minutes. You want CAV and low jitter.",
            f"  {PROG} timing {drive_flag()}",
            "3. Measure the disc's spiral, about 5 minutes.",
            f"  {PROG} geo {drive_flag()}",
            "4. Turn your picture into an ISO, check the preview, and burn it on another blank from the same box.",
            f"  {PROG} image --geo latest --picture my_picture.png --output iso/picture.iso",
            "  This is disc 2. Photograph it (the web page reads the photos) to see how far off it is; the finished picture is disc 3.",
            "5. Look at the disc in the dark. It takes a knack, and `guide` explains it when you get there.",
            "  No picture? Check the light, then the burn report, then the geometry. disc-probe says why before it suggests another burn.",
            "",
            "On a Blu-ray (experimental) the same shape comes out of read timing instead of a picture:",
            f"  {PROG} random --media bd --output iso/bd-random.iso",
            "  Burn that to a BD-R, then:",
            f"  {PROG} geo {drive_flag()} --media bd --bd-zones 25",
            f"  {PROG} disexport --geo latest --sectors <sectors> --output dis_preset.json",
            "  The timing pins the shape; the two radii still come from the disc itself, so read the limits in docs/MANUAL.md before burning a picture with that preset.",
            "",
            "While a measurement runs, press g for a game. They do not disturb it.",
            f"Lost? {PROG} guide shows where you are and what comes next.",
            f"To read this again: {PROG} tutorial",
            ""]


def _tutorial_mark() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "disc-probe", "tutorial_offered")


def tutorial_offered() -> bool:
    return bool(os.environ.get("DISCPROBE_NO_TUTORIAL")) or os.path.exists(_tutorial_mark())


def remember_tutorial_offered() -> None:
    """Asked once, whatever the answer. If this cannot be saved it is asked again, which does no harm."""
    try:
        os.makedirs(os.path.dirname(_tutorial_mark()), exist_ok=True)
        with open(_tutorial_mark(), "w", encoding="utf-8"):
            pass
    except OSError:
        pass


def progress_lines(media: str = "dvd", out: str = "results") -> list[str]:
    """The steps as `guide` shows them, to go before the next command."""
    return [Step("Your progress:"), *(Step(line) for line in guide_lines(media, out, notes=True) if line.startswith(("  [x]", "  [ ]"))), ""]


def picture_iso() -> str | None:
    """The newest picture ISO under iso/, by the preview made beside it. Held-out files stay unread."""
    try:
        names = os.listdir("iso")
    except OSError:
        return None
    found = [os.path.join("iso", name[:-len(".preview.png")] + ".iso") for name in names
             if name.endswith(".preview.png") and "blind" not in name.lower()]
    found = [path for path in found if os.path.exists(path) and not os.path.exists(path + iso9660.UNFINISHED)]
    return max(found, key=os.path.getmtime) if found else None


def after_selftest() -> list[str]:
    missing = missing_packages()
    if missing:
        return [f"Those were only the checks that run without {', '.join(missing)}. Install what is missing and run it again:",
                f"  {INSTALL}"]
    return [f"Next, see where you are: {PROG} guide"]


def after_disexport(cd_constant_open: bool = False, installed: bool = False) -> list[str]:
    if installed:
        lines = []
    else:
        lines = ["Next, check the angle difference above (well under 0.1 deg is fine), then enter the preset in DiscImageStudio",
                 "(inner and outer radius, sectors, the three pitch terms), or run with --install to write it there. "
                 "Steps: docs/MANUAL.en.md."]
    if cd_constant_open:
        lines.append("On the CD route you can skip --along-track-frames: fine calibration in DiscImageStudio settles that constant.")
    return lines


def after_cdprobe(project: str) -> list[str]:
    return [f"Next, open {short(project)} in DiscImageStudio and burn it, as it is, on a blank of the type to",
            "calibrate (lowest speed). Then measure the burned disc on the drive that reads it:",
            f"  {PROG} geo {drive_flag()} --media cd"]


def result_verdict(run, media="dvd"):
    if run is None:
        return None
    if run.kind == "geo":
        return run.quality().replace(" ", "_")
    if run.stopped:
        return "stopped_early"
    if not run.rotation():
        return "unknown"
    if run.rotation() != ("CLV" if media == "bd" else "CAV"):
        return "too_noisy"
    jitter = _jitter(run.summary)
    return "good" if jitter and max(jitter) <= GOOD_JITTER_DEG else "usable"


def guide_state(media: str = "dvd", out: str = "results", *, drives=None) -> dict:
    """Disk-derived workflow, shared by the CLI and HTTP service. No drive is opened."""
    if media not in ("dvd", "cd", "bd"):
        raise ValueError("media must be dvd, cd or bd")
    random_iso = {"cd": "iso/cd-random.iso", "bd": "iso/bd-random.iso"}.get(media, "iso/random.iso")
    results = [r for r in scan(out) if not r.simulated and r.media == media]
    missing = missing_packages()
    drives = optical_drives() if drives is None else drives
    drive = f"--drive {drives[0]}" if drives else ("--drive /dev/sr0" if sys.platform == "linux" else "--drive E:")

    timing = next((r for r in results if r.kind == "timing" and r.rotation() and not r.stopped), None)
    # A Blu-ray is read at a constant linear speed, so CLV is the good answer there, not CAV: the run
    # that counts is the one that finished, and its own verdict says whether the disc is usable.
    timing_good = timing is not None and (not timing.stopped if media == "bd" else timing.rotation() == "CAV")
    geo = next((r for r in results if r.geo_complete()), None)
    has_iso = os.path.exists(random_iso) and not os.path.exists(random_iso + iso9660.UNFINISHED)

    picture = picture_iso()
    latest_timing = timing or next((r for r in results if r.kind == "timing"), None)
    latest_geometry = geo or next((r for r in results if r.kind == "geo"), None)
    verdict = lambda run: result_verdict(run, media)

    steps = [
        dict(id="packages", done=not missing, label="Python packages",
             detail=", ".join(missing) + " missing" if missing else "numpy, pillow"),
        dict(id="drive", done=bool(drives), label="Optical drive",
             detail=" ".join(drives) if drives else "none found"),
        dict(id="random_disc", done=timing is not None, label="Random-data disc",
             detail="measured" if timing else f"{random_iso} written; burn it" if has_iso else "not made yet"),
        dict(id="timing", done=timing_good, label="Drive check (timing)",
             detail=timing.describe() if timing else "not run yet", verdict=verdict(latest_timing),
             result=latest_timing.path if latest_timing else None),
        dict(id="geo", done=geo is not None, label="Geometry (geo)",
             detail=geo.describe() if geo else "not run yet", verdict=verdict(latest_geometry),
             result=latest_geometry.path if latest_geometry else None),
        # Batch identity and photo import do not exist yet; CD always needs this constant.
        dict(id="photo_l", needed=media == "cd", done=False, label="Photograph L", detail="not measured yet"),
        dict(id="picture_iso", done=picture is not None, label="Picture ISO (image)",
             detail=short(picture) if picture else "not made yet"),
        dict(id="burn", done=False, label="Burn it on a blank", detail="from the batch you measured")]
    current = next(s["id"] for s in steps if not s["done"] and s.get("needed", True))
    action = {"packages": None, "drive": "info", "random_disc": "timing" if has_iso else "random",
              "timing": "timing", "geo": "geo", "photo_l": None, "picture_iso": "image", "burn": "burn"}[current]
    return dict(media=media, drives=[dict(id=d, name=d, disc=None) for d in drives], steps=steps,
                current=current, next=dict(action=action, label=i18n.tr(next(s["label"] for s in steps if s["id"] == current)),
                                           minutes={"timing": 3, "geo": 5}.get(current)),
                jobs=[], counter=None)


class Task:
    """A step of the workflow: what `guide` prints, and what the console needs to run it.

    `action` says what Enter does in the console: "run" runs `argv` as a disc-probe command,
    "shell" is a line to copy (installing packages is pip's job), "form" opens the picture
    form, and "burn" is done by a disc burner outside this program.
    """

    def __init__(self, key, name, done, detail, action="run", argv=None, form=None,
                 shell=None, why="", takes="", current=False):
        self.key = key
        self.name, self.done, self.detail = name, done, detail
        self.action, self.argv, self.form, self.shell = action, argv, form, shell
        self.why, self.takes, self.current = why, takes, current

    def command(self) -> str | None:
        """The line a person would type, or None when the step has no command of ours."""
        if self.action == "shell":
            return self.shell
        if self.argv:
            return f"{PROG} " + " ".join(quote(part) if " " in part else part for part in self.argv)
        return None


class Plan:
    """Where the workflow stands for one disc type, and the commands that move it on."""

    def __init__(self, media, out, tasks, commands, has_iso, geo, picture, timing=None, random_iso=""):
        self.media, self.out = media, out
        self.tasks, self.commands = tasks, commands
        self.has_iso, self.geo, self.picture = has_iso, geo, picture
        self.timing, self.random_iso = timing, random_iso

    def current(self) -> "Task | None":
        """The first step still open: where a person would start."""
        return next((task for task in self.tasks if not task.done), None)


def workflow(media: str = "dvd", out: str = "results", notes: bool = True, *, drives=None) -> Plan:
    """The steps as objects, for `guide` to print and for the console to show and run."""
    flag = {"cd": " --media cd", "bd": " --media bd"}.get(media, "")
    media_args = ["--media", media] if media in ("cd", "bd") else []
    random_iso = {"cd": "iso/cd-random.iso", "bd": "iso/bd-random.iso"}.get(media, "iso/random.iso")
    results = [r for r in scan(out) if not r.simulated and r.media == media]
    missing = missing_packages()
    drives = optical_drives() if drives is None else drives
    drive = f"--drive {drives[0]}" if drives else ("--drive /dev/sr0" if sys.platform == "linux" else "--drive E:")

    timing = next((r for r in results if r.kind == "timing" and r.rotation() and not r.stopped), None)
    # A Blu-ray is read at a constant linear speed, so CLV is the good answer there, not CAV: the run
    # that counts is the one that finished, and its own verdict says whether the disc is usable.
    timing_good = timing is not None and (not timing.stopped if media == "bd" else timing.rotation() == "CAV")
    geo = next((r for r in results if r.geo_complete()), None)
    has_iso = os.path.exists(random_iso) and not os.path.exists(random_iso + iso9660.UNFINISHED)

    # A written file is not yet a disc. Scripts keep the tick they always saw.
    disc_done = timing is not None or (has_iso and not notes)
    tasks = [
        Task("packages", "Python packages", not missing,
             ", ".join(missing) + " missing" if missing else "numpy, pillow",
             action="shell", shell=INSTALL,
             why="Timing and drawing use numpy and Pillow; photo reading also needs SciPy and OpenCV.",
             takes="once, about a minute"),
        Task("drive", "Optical drive", bool(drives),
             " ".join(drives) if drives else
             ("none found" if sys.platform in ("win32", "linux") else "real drives need Windows or Linux"),
             argv=["list"],
             why="Shows the optical drives this computer can see, and the name each one uses.",
             takes="a second"),
        Task("disc", "Random-data disc", disc_done,
             f"{random_iso} written; burn it" if has_iso and timing is None else
             "measured" if timing else "not made yet",
             action="burn" if has_iso else "run",
             argv=None if has_iso else ["random", *media_args, "--output", random_iso],
             why="A disc of random data lets the drive's timing be measured without a pattern of its own getting in the way.",
             takes="a few seconds to write; burning is up to your burner"),
        Task("timing", "Drive check (timing)", timing_good,
             timing.describe() if timing else "not run yet",
             argv=["timing", *(["--drive", drives[0]] if drives else []), *media_args],
             why="Reads the disc at several speeds and radii to see whether this drive reports clean times and keeps a steady speed.",
             takes="1 to 3 minutes"),
        Task("geo", "Geometry (geo)", geo is not None,
             geo.describe() if geo else "not run yet",
             argv=["geo", *(["--drive", drives[0]] if drives else []), *media_args,
                   *(["--bd-zones", "25"] if media == "bd" else [])],
             why="Finds how the disc's spiral is laid out, so a picture can be put where it will actually appear.",
             takes="about 5 minutes"),
    ]
    picture = picture_iso() if notes else None
    if notes:       # scripts keep the steps they always saw. The burn is the person's own, so nothing here can tick it.
        tasks += [
            Task("picture", "Picture ISO (image)", picture is not None,
                 short(picture) if picture else "not made yet",
                 action="form", form="image", argv=["image", *media_args, "--geo", "latest",
                                                     "--picture", "my_picture.png", "--output", "iso/picture.iso"],
                 why="Turns a picture into the ISO that gets burned onto the disc. Nothing is burned yet.",
                 takes="about a minute"),
            Task("burn", "Burn it on a blank", False, "from the batch you measured",
                 action="burn",
                 why="Burn the ISO on a blank from the batch you measured, then look at the data side in the dark.",
                 takes="as long as your burner takes"),
        ]
        current = next((task for task in tasks if not task.done), None)
        if current is not None:
            current.current = True

    if media == "bd" and geo is not None:
        sectors = _sectors_for(geo.summary, out)[0]
        commands = [("Export a DiscImageStudio Blu-ray preset (enter the same --sectors there; `info` on a blank disc gives the count):",
                     f"{PROG} disexport --media bd --geo latest --sectors {sectors} --output dis_preset.json"),
                    ("This preset carries the shape of the spiral, not its scale: the pitch is the 0.3200 um prior and "
                     "the inner radius rides on a timing offset the fit cannot see.", None),
                    ("Do not burn a picture with it yet. Calibrate against the disc first: one BD-R and one look at the "
                     "edge is 106 turns of difference on a real disc (docs/MANUAL.md).", None)]
    elif missing:
        commands = [("Install the Python packages disc-probe uses:", INSTALL)]
    elif sys.platform not in ("win32", "linux"):
        commands = [("Try the flow on the simulated drive:", f"{PROG} timing --sim cav{flag}"), (None, PORTS)]
    elif not has_iso and timing is None:
        commands = [("Make the random-data disc: write this file, then burn it:", f"{PROG} random{flag} --output {random_iso}")]
    elif timing is None:
        commands = [(f"Burn {random_iso} to a disc and load it, then check this drive (1 to 3 minutes):", f"{PROG} timing {drive}{flag}")]
    elif not timing_good:
        from argparse import Namespace
        saved_args = {**(timing.summary.get("args") or {}), "media": media, "out": out}
        saved_args.setdefault("drive", drives[0] if drives else None)
        args = Namespace(**saved_args)
        commands = [(None, line.strip()) for line in after_timing(args, timing.summary)]
    elif geo is None:
        measure = (f"{PROG} geo {drive} --media bd --bd-zones 25" if media == "bd"
                   else f"{PROG} geo {drive}{flag}")
        commands = [("Measure the disc's spiral (about 5 minutes):", measure)]
    else:
        sectors = _sectors_for(geo.summary, out)[0]
        first = ("CD still needs one more constant, so the preset below is the usual way on (the CD route in README.md). A picture ISO:"
                 if media == "cd" else "Another picture ISO:" if picture else "Make a picture ISO (replace my_picture.png with your image):")
        commands = [(f"Burn {short(picture)} on a blank from the batch you measured. Burned it already? See below.", None)] if picture else []
        commands += [(first, f"{PROG} image{flag} --geo latest --picture my_picture.png --output iso/picture.iso"),
                    ("Or export a preset for DiscImageStudio (enter the same --sectors there; `info` on a blank disc gives the count):",
                     f"{PROG} disexport --media {media} --geo latest --sectors {sectors} --output dis_preset.json")]
    return Plan(media, out, tasks, commands, has_iso, geo, picture, timing=timing, random_iso=random_iso)


def guide_lines(media: str = "dvd", out: str = "results", notes: bool = False) -> list[str]:
    """The workflow with what is already done ticked off, and the next command; `notes` says what each does."""
    plan = workflow(media, out, notes)
    other = "cd" if media == "dvd" else "dvd"
    lines = [f"Where you are, for {media.upper()} ({other.upper()}: {PROG} guide --media {other}):", ""]
    for task in plan.tasks:
        detail = f"{i18n.tr(task.detail)}  <- {i18n.tr('you are here')}" if task.current else task.detail
        lines.append(f"  [{'x' if task.done else ' '}] {i18n.pad(i18n.tr(task.name), 22)} {i18n.tr(detail)}")
    lines += ["", "Next:"]
    for note, command in plan.commands:
        lines += ([f"  {note}"] if notes and note else []) + ([f"  {command}"] if command else [])
    if media == "bd" and plan.geo is not None:
        lines += ["", "  This preset gives the shape of the spiral, not its scale (docs/MANUAL.md).",
                  "  Do not burn a picture with it: on one real BD the angle was off by 106 turns."]
    if sys.platform == "linux" and plan.timing is None:
        lines += ["", *burn_steps(plan.random_iso, media)]
    if plan.picture and plan.geo:
        if sys.platform == "linux":
            lines += ["", *burn_steps(plan.picture, media)]
        lines += ["", *AFTER_BURN]
    lines += ["", f"All commands: {PROG} -h    One command: {PROG} <command> -h    Details: docs/MANUAL.en.md"]
    return lines


def parser_hint(message: str, argv: list[str], commands=(), options=()) -> str | None:
    """A way out of an argparse error, for people at a terminal."""
    m = re.search(r"invalid choice: '([^']*)'", message)
    if m and commands:
        close = difflib.get_close_matches(m[1], list(commands), n=1, cutoff=0.5)
        return f"Did you mean: {PROG} {close[0]}" if close else f"See the commands with: {PROG} -h"
    if "required" in message and "--geo" in message:
        return f"Use your last measurement: {PROG} {' '.join(argv)} --geo latest"
    if "required" in message and "<command>" in message:
        return f"Not sure where to start? {PROG} guide"
    m = re.search(r"unrecognized arguments: (\S+)", message)
    if m:
        close = difflib.get_close_matches(m[1].split("=")[0], list(options), n=1, cutoff=0.6)
        if close:
            return f"Did you mean {close[0]}?"
        return f"See the options with: {PROG} {argv[0]} -h" if argv else None
    return None
