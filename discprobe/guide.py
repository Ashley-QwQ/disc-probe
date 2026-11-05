"""Where a person stands in the workflow: past results, and the commands to run next.

Reads result folders and prints text; it never touches a drive. The commands it prints use
real paths and values, so they can be copied as they are.
"""

from __future__ import annotations

import datetime
import difflib
import importlib.util
import json
import os
import re
import sys

RESULT_DIR = re.compile(r"^(?P<kind>[a-z]+)-(?:(?P<tag>.+)-)?(?P<stamp>\d{8}-\d{6})$")
PROG = "python -m discprobe"
# `latest` must not pick these: a run stopped by the whole-turn check still writes a summary.
MIN_RUNGS = 8
MAX_LATEST_CHI2 = 25.0
# Reports so far: under about 2 deg drives measured well; 3-24 deg (SP80NB80) and 10-14 deg
# (BW-16D1H-U) stopped or gave a wrong geometry.
GOOD_JITTER_DEG = 2.0
BAD_JITTER_DEG = 5.0
NARROW_SPAN_MM = 20.0
ALTERNATIVE_SPEEDS = {"dvd": ("3324", "5540", "11080"), "cd": ("1411", "2822", "4234")}
INSTALL = "python -m pip install numpy pillow scipy"
PORTS = ("This repository drives real hardware on Windows only. Ports: Linux github.com/bczhc/disc-probe, "
         "macOS github.com/NaiveTomcat/discprobe-macos. Anything with --sim works here.")


def quote(path: str) -> str:
    return f'"{path}"' if " " in path else path


def short(path: str) -> str:
    """A path to paste into a command: relative when it is below the current folder."""
    try:
        rel = os.path.relpath(path)
    except ValueError:      # another drive on Windows
        return quote(os.path.abspath(path))
    return quote(os.path.abspath(path) if rel.startswith("..") else rel)


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
        self.simulated = self.tag.startswith("SIM")
        self.summary = _load(os.path.join(path, "summary.json")) or {}

    @property
    def fit(self) -> dict:
        return self.summary.get("fit") or {}

    @property
    def media(self) -> str:
        if self.kind == "geo":
            return "cd" if self.fit.get("media") == "cd" else "dvd"
        return "cd" if (self.summary.get("args") or {}).get("media") == "cd" else "dvd"

    def rungs(self) -> int:
        try:
            with open(os.path.join(self.path, "targets.csv"), encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
        except OSError:
            return 0

    def geo_complete(self) -> bool:
        return (self.kind == "geo" and "u" in self.fit and self.rungs() >= MIN_RUNGS
                and self.fit.get("chi2_per_dof", 0) <= MAX_LATEST_CHI2)

    def rotation(self) -> str | None:
        return ((self.summary.get("period") or {}).get("rotation") or {}).get("mode")

    def describe(self) -> str:
        if self.kind == "geo":
            f = self.fit
            if "u" not in f:
                return "stopped before the first fit"
            state = "" if self.geo_complete() else "  (stopped early)"
            span = f.get("measured_span_mm") or ["?", "?"]
            return (f"{self.rungs()} rungs, rms {f.get('residual_rms_deg', 0):.2f} deg, "
                    f"chi2/dof {f.get('chi2_per_dof', 0):.1f}, {span[0]}-{span[1]} mm{state}")
        if self.kind == "timing":
            mode = self.rotation()
            if not mode:
                return "stopped before the rotation test"
            jitter = _jitter(self.summary)
            return mode + (f", jitter {min(jitter):.2f}-{max(jitter):.2f} deg" if jitter else "")
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


def latest_geo(media: str | None = None, out: str = "results") -> Result | None:
    """The newest complete measurement of a real disc."""
    for r in scan(out):
        if r.geo_complete() and not r.simulated and (media is None or r.media == media):
            return r
    return None


def resolve_geo(value: str, media: str | None = None, out: str = "results") -> str:
    """--geo takes a summary.json, a geo result folder, or `latest`. Raises ValueError with what to do."""
    if value.lower() == "latest":
        r = latest_geo(media, out)
        if r is None:
            have = any(x.kind == "geo" for x in scan(out))
            why = "only simulated or stopped runs were found" if have else "there is no geo result yet"
            raise ValueError(f"--geo latest: {why} in {out}. Run geo first, or give a summary.json path.")
        return os.path.join(r.path, "summary.json")
    return os.path.join(value, "summary.json") if os.path.isdir(value) else value


def describe_chosen(path: str) -> str:
    folder = os.path.dirname(path)
    m = RESULT_DIR.match(os.path.basename(folder))
    if not m:
        return short(path)
    return f"{short(path)} ({Result(folder, m['kind'], m['tag'], m['stamp']).describe()})"


def missing_packages() -> list[str]:
    return [pip for module, pip in (("numpy", "numpy"), ("PIL", "pillow"), ("scipy", "scipy"))
            if importlib.util.find_spec(module) is None]


def optical_drives() -> list[str]:
    if sys.platform != "win32":
        return []
    from .spti import list_optical_drives
    return list_optical_drives()


def drive_flag(args=None) -> str:
    """How the next command should name the drive."""
    if args is not None and getattr(args, "sim", None):
        return f"--sim {args.sim}"
    if args is not None and getattr(args, "drive", None):
        return f"--drive {args.drive}"
    drives = optical_drives()
    return f"--drive {drives[0]}" if drives else "--drive E:"


def _carry(args) -> str:
    """Options the next drive command should repeat."""
    parts = [drive_flag(args)]
    if getattr(args, "media", "dvd") == "cd":
        parts.append("--media cd")
    if getattr(args, "transport", "auto") != "auto":
        parts.append(f"--transport {args.transport}")
    if getattr(args, "out", "results") != "results":
        parts.append(f"--out {quote(args.out)}")
    return " ".join(parts)


def _other_speed(args) -> str:
    media = getattr(args, "media", "dvd")
    current = str(getattr(args, "speed", ""))
    return next(s for s in ALTERNATIVE_SPEEDS[media] if s != current)


def sectors_from_info(report: dict) -> tuple[int, str] | None:
    """The sector count `disexport --sectors` wants, from an `info` report, with where it came from."""
    track = _parsed(report, "track_1")
    if track.get("blank") and track.get("free_blocks"):
        return track["track_start"] + track["free_blocks"], "free space of this blank disc"
    atip = _parsed(report, "atip")
    if atip.get("last_leadout_start_lba"):
        return atip["last_leadout_start_lba"], "lead-out in the ATIP"
    cap = _parsed(report, "capacity")
    if cap.get("last_lba"):
        return cap["last_lba"] + 1, "last LBA + 1, the blank size only if this disc was burned full"
    return None


def _sectors_for(summary: dict, out: str) -> tuple[str, str]:
    """A --sectors value for the preset command, and what the reader should check about it."""
    for r in scan(out):
        if r.kind == "info" and not r.simulated:
            found = sectors_from_info(_load(os.path.join(r.path, "info.json")) or {})
            if found:
                return str(found[0]), f"--sectors is from your last `info`: {found[1]}"
    last = (summary.get("setup") or {}).get("last_lba")
    if last:
        return str(last + 1), "--sectors is the recorded size of the measured disc"
    return "<sectors>", "run `info` on a blank disc to find --sectors"


def sectors_hint(geo_path: str) -> str:
    """What to do when a CD preset has no --sectors."""
    sectors, why = _sectors_for(_load(geo_path) or {}, "results")
    return (f"Try --sectors {sectors} ({why}). It must match the count DiscImageStudio uses: "
            "check with its read-from-disc, or run `info` on a blank disc.")


def after_list(drives: list[str]) -> list[str]:
    if not drives:
        return ["Plug the drive in and check that it shows up in Explorer,",
                f"or try the flow on the simulated drive: {PROG} timing --sim cav"]
    lines = ["Next, see what the drive and disc report:", f"  {PROG} info --drive {drives[0]}"]
    if len(drives) > 1:
        lines.append("With several drives, use the letter of the one holding your disc.")
    return lines


def after_info(args, report: dict) -> list[str]:
    lines = []
    found = sectors_from_info(report)
    if found:
        lines += [f"Sector count for disexport --sectors: {found[0]} ({found[1]}).",
                  "It has to match the count DiscImageStudio uses for this disc.", ""]
    cap = _parsed(report, "capacity").get("last_lba")
    if _parsed(report, "track_1").get("blank") or not cap or cap < 1000:
        return lines + ["Nothing is recorded on this disc, so timing cannot use it. Burn a random-data disc first:",
                        f"  {PROG} random --output iso/random.iso"]
    return lines + ["Next, check the drive (1 to 3 minutes):", f"  {PROG} timing {_carry(args)}"]


def after_timing(args, summary: dict) -> list[str]:
    media = getattr(args, "media", "dvd")
    rotation = ((summary.get("period") or {}).get("rotation") or {}).get("mode")
    if not rotation:
        return []
    carry, other = _carry(args), _other_speed(args)
    if rotation != "CAV":
        return [f"Verdict: rotation is {rotation}, not CAV, so sector angles cannot be read at this speed.",
                "Next, try another speed. Some drives never leave one, and the rotation test will show that:",
                f"  {PROG} timing {carry} --speed {other}"]
    jitter = _jitter(summary)
    worst = max(jitter) if jitter else None
    span = f"{min(jitter):.2f}-{worst:.2f} deg" if jitter else ""
    lines = []
    if worst is None:
        lines.append("Verdict: rotation is CAV, but no jitter was measured.")
    elif worst <= GOOD_JITTER_DEG:
        lines.append(f"Verdict: CAV with {span} jitter. This drive looks usable.")
    else:
        lines.append(f"Verdict: CAV, but {span} jitter is noisy. A lower speed may help:" if worst <= BAD_JITTER_DEG
                     else f"Verdict: CAV, but {span} jitter is too high: drives reported at this level stopped early "
                          "or gave a wrong geometry. Try a lower speed or another drive:")
        lines.append(f"  {PROG} timing {carry} --speed {other}")
        if media == "dvd" and getattr(args, "sectors", 1) == 1:
            lines.append(f"  Or read whole ECC blocks, which was cleaner on one drive: {PROG} timing {carry} --sectors 16")
    usual = 1411 if media == "cd" else None
    speed = f" --speed {args.speed}" if getattr(args, "speed", None) not in (None, usual) else ""
    return lines + ["", "Next, measure the geometry:", f"  {PROG} geo {carry}{speed}"]


def after_timing_stop(args, reason: str) -> list[str]:
    flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
    if "cannot read" in reason or "recorded area" in reason or "fails on" in reason or "time limit" in reason:
        return [f"Make a plain data disc: {PROG} random{flag} --output iso/random.iso",
                "Burn it (Windows: right-click the .iso, Burn disc image) and run timing on it."]
    return []


def after_geo(args, res: dict, out: str) -> list[str]:
    media = getattr(args, "media", "dvd")
    geo = short(os.path.join(out, "summary.json"))
    flag = " --media cd" if media == "cd" else ""
    sectors, why = _sectors_for(_load(os.path.join(out, "summary.json")) or {}, getattr(args, "out", "results"))
    span = res.get("measured_span_mm") or [25.8, 54.4]
    lines = []
    if getattr(args, "sim", None):
        lines.append("This was the simulated drive: the commands below show the flow, do not burn from them.")
    if span[1] - span[0] < NARROW_SPAN_MM:
        lines.append(f"This run only covers {span[0]}-{span[1]} mm, so angles outside that are extrapolated.")
    if res["chi2_per_dof"] > 2:
        lines += ["The fit left more than noise. Compare pitch models first, no new measurement needed; if quadratic is",
                  "clearly better, write a correction and add --correction correction.json to the commands below:",
                  f"  python tools/geo_polyfit.py {short(out)}",
                  f"  python tools/geo_polyfit.py {short(out)} --write-correction correction.json --order quadratic", ""]
    lines += ["Next, make a picture ISO from your own image:",
              f"  {PROG} image{flag} --geo {geo} --picture my_picture.png --output iso/picture.iso"]
    if media == "cd":
        lines.append("  CD has one more constant that timing cannot see: read the CD-R part of docs/MANUAL.md first.")
    lines += ["Or export a DiscImageStudio preset:",
              f"  {PROG} disexport --geo {geo} --sectors {sectors} --r-min {span[0]} --r-max {span[1]} "
              "--output dis_preset.json",
              f"  ({why}; it must match the count in DiscImageStudio.)"]
    return lines


def after_geo_stop(args, reason: str) -> list[str]:
    carry, other = _carry(args), _other_speed(args)
    if "never settled" in reason or "near the reference" in reason:
        return ["The drive would not hold one speed. Check it with timing, then try geo at a lower speed:",
                f"  {PROG} timing {carry}", f"  {PROG} geo {carry} --speed {other}",
                "USB slim drives are often too noisy here; an internal drive may simply work."]
    if "whole-turn" in reason or "safe" in reason:
        return ["A whole-turn count went wrong, or the pitch varies more than the model allows. Try a lower speed:",
                f"  {PROG} geo {carry} --speed {other} --reps 32",
                "If it keeps stopping near one LBA, leave that area out with --ranges a-b (see `geo -h`).",
                "A disc whose pitch varies can take a higher limit, for example --chi2-abort 100."]
    if "ranges" in reason:
        return ["--ranges has to overlap the recorded area. See the last LBA with:", f"  {PROG} info {carry}"]
    if "recorded area" in reason or "medium" in reason or "fails on" in reason:
        flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
        return ["geo needs a burned disc of plain data. Make one, burn it and run geo again:",
                f"  {PROG} random{flag} --output iso/random.iso"]
    return [f"See how noisy this drive is: {PROG} timing {carry}"]


def after_random(args) -> list[str]:
    flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
    return ["Burn it onto a blank disc (Windows: right-click the .iso, Burn disc image), filling the disc, and keep",
            "some blanks of the same batch for pictures. Then check the drive with it (1 to 3 minutes):",
            f"  {PROG} timing {drive_flag()}{flag}"]


def after_disexport() -> list[str]:
    return ["Next, check the angle difference above, then enter the preset in DiscImageStudio",
            "(inner and outer radius, sectors, the three pitch terms). Steps: docs/MANUAL.md."]


def guide_lines(media: str = "dvd", out: str = "results") -> list[str]:
    """The workflow with what is already done ticked off, and the next command."""
    flag = " --media cd" if media == "cd" else ""
    random_iso = "iso/cd-random.iso" if media == "cd" else "iso/random.iso"
    results = [r for r in scan(out) if not r.simulated and r.media == media]
    missing = missing_packages()
    drives = optical_drives()
    drive = f"--drive {drives[0]}" if drives else "--drive E:"

    timing = next((r for r in results if r.kind == "timing" and r.rotation()), None)
    timing_good = timing is not None and timing.rotation() == "CAV"
    geo = next((r for r in results if r.geo_complete()), None)
    has_iso = os.path.exists(random_iso)

    rows = [(not missing, "Python packages", ", ".join(missing) + " missing" if missing else "numpy, pillow, scipy"),
            (bool(drives), "Optical drive", " ".join(drives) if drives else
             ("none found" if sys.platform == "win32" else "real drives need Windows or a port")),
            (has_iso or timing is not None, "Random-data disc",
             f"{random_iso} written; burn it" if has_iso and timing is None else
             "measured" if timing else "not made yet"),
            (timing_good, "Drive check (timing)", timing.describe() if timing else "not run yet"),
            (geo is not None, "Geometry (geo)", geo.describe() if geo else "not run yet")]

    if missing:
        commands = [INSTALL]
    elif sys.platform != "win32":
        commands = [f"{PROG} timing --sim cav{flag}", PORTS]
    elif not has_iso and timing is None:
        commands = [f"{PROG} random{flag} --output {random_iso}"]
    elif timing is None:
        commands = [f"{PROG} timing {drive}{flag}"]
    elif not timing_good:
        commands = [f"{PROG} timing {drive}{flag} --speed {ALTERNATIVE_SPEEDS[media][0]}"]
    elif geo is None:
        commands = [f"{PROG} geo {drive}{flag}"]
    else:
        sectors = _sectors_for(geo.summary, out)[0]
        commands = [f"{PROG} image{flag} --geo latest --picture my_picture.png --output iso/picture.iso",
                    f"{PROG} disexport --media {media} --geo latest --sectors {sectors} --output dis_preset.json"]

    other = "cd" if media == "dvd" else "dvd"
    lines = [f"Where you are, for {media.upper()} ({other.upper()}: {PROG} guide --media {other}):", ""]
    lines += [f"  [{'x' if done else ' '}] {name:22s} {detail}" for done, name, detail in rows]
    lines += ["", "Next:"] + [f"  {c}" for c in commands]
    lines += ["", f"All commands: {PROG} -h    One command: {PROG} <command> -h    Details: docs/MANUAL.md"]
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
