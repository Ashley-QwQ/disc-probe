"""`discprobe calibrate`: the calibration of one disc batch, start to end, as one command.

The steps are the commands a person would run by hand, run here in order as child processes with this
process's environment, so each one's progress, questions and output reach whoever runs this (a terminal,
or the web page through the job's events file) exactly as when run alone:

    burn     (only with --iso and --yes-write) the measurement image onto the blank in the drive
    check    the disc is there, written, and (with --mid) of the expected batch       `discprobe disc`
    timing   rotation: cache, FUA and the CAV check                                     `discprobe timing`
    geo      the spiral geometry                                                       `discprobe geo`
    preset   (only with --preset) a DiscImageStudio preset from the geometry           `discprobe disexport`

Between steps it emits `step` events (name, index, total) and, per measured step, `step_result` (its
folder and verdict); at the end `calibrated` with everything found. A step that fails stops the run.
Because the whole chain is one process, the page that started it can be closed or reloaded: the job goes
on, and the page finds it again in /api/state.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from . import guide, ui
from .capacity import catalogue_capacity, positive_sectors

GOOD = ("good", "usable")
DEFAULT_READ_SPEED = "4x"  # 4x of the disc's own kind (DVD: 5540 kB/s, as geo-H-20261111-200909 set successfully; CD: 706)


def _avoid_band(text: str) -> tuple[float, float]:
    try:
        a, b = map(float, text.split("-"))
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError("give a radius band in mm as A-B, with 0 <= A < B") from None
    return a, b


def _geo_ranges(media: str, setup: dict, bands) -> str:
    """Subtract bands from geo's default span, using its read-completion radius model.

    Binary search on block-aligned LBAs also covers CD data's frame tail and CD-DA's
    different origin. Expand exclusions to whole blocks so rounding cannot put a
    rung back inside a band. The setup is from timing, not the blank's capacity.
    """
    from .geo import CD_AUDIO_RANGE, Ladder

    last = setup.get("last_lba")
    if type(last) is not int or last <= 0:
        raise Stopped("the readable disc length is unknown; cannot apply --avoid-mm")
    model = Ladder(None, media=media)
    model.audio = media == "cd" and setup.get("first_track_audio") is True
    block = model.block
    lo, hi = CD_AUDIO_RANGE if model.audio else (0.03, 0.85)
    ranges = [(int(last * lo) // block * block, int(last * hi) // block * block)]

    def boundary(radius, inclusive=False):
        a, b = 0, last // block + 1
        while a < b:
            mid = (a + b) // 2
            r = model._radius(mid * block)
            if r < radius or (inclusive and r == radius):
                a = mid + 1
            else:
                b = mid
        return a * block

    for a, b in bands:
        start, end = boundary(a), boundary(b, inclusive=True)
        ranges = [(lo, hi) for lo, hi in ranges for lo, hi in
                  ((lo, min(hi, start)), (max(lo, end), hi)) if hi - lo > 64]
    if not ranges:
        raise Stopped("--avoid-mm leaves no readable geo ranges longer than 64 sectors")
    return ",".join(f"{a}-{b}" for a, b in ranges)


def _argv(*args) -> list[str]:
    return [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "discprobe", *map(str, args)]


class Stopped(Exception):
    pass


def run(args) -> None:
    if getattr(args, "geo", None):
        return save_preset(args)
    if not args.drive:
        raise SystemExit("--drive is required unless exporting an existing --geo run")
    cancel = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    marker = os.environ.get("DISCPROBE_BURN_CANCEL")          # the page's cancel, as for a burn job
    stop_watch = threading.Event()

    def watch():
        while not stop_watch.wait(.2):
            if marker and Path(marker).exists():
                cancel.set()
    threading.Thread(target=watch, daemon=True).start()
    steps = (["burn"] if args.iso else []) + ["check", "timing", "geo"] + (["preset"] if args.preset else [])
    found: dict = {}
    child_reason = None

    def step(name):
        if cancel.is_set():
            raise Stopped("cancelled before " + name)
        i = steps.index(name)
        ui.event("step", name=name, index=i, total=len(steps))
        ui.say(f"\n[{i + 1}/{len(steps)}] {name}", "bold")

    def child(*a) -> int:
        """One step's command, its output on ours; stopped if the run is cancelled (a burn stops itself
        through the same marker, at a point where stopping is safe)."""
        nonlocal child_reason
        child_reason = None
        # A rotation stop precedes geo's first fit, so there may be no summary.json.
        # Relay stdout while retaining its plain stop sentence for the job event.
        proc = subprocess.Popen(_argv(*a), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

        def relay():
            nonlocal child_reason
            for line in proc.stdout:
                print(line, end="", flush=True)
                if line.startswith("stopped: "):
                    child_reason = line[len("stopped: "):].strip()

        reader = threading.Thread(target=relay, daemon=True) if getattr(proc, "stdout", None) else None
        if reader:
            reader.start()
        while proc.poll() is None:
            if cancel.is_set() and a[0] != "burn":
                proc.terminate()
            time.sleep(.2)
        if reader:
            reader.join()
            proc.stdout.close()
        if cancel.is_set():
            raise Stopped("cancelled during " + a[0])
        return proc.returncode

    def measured(kind, since) -> guide.Result | None:
        runs = [r for r in guide.scan(args.out) if r.kind == kind and r.when >= since and (args.sim or not r.simulated)]
        return runs[0] if runs else None

    def common():
        return ["--drive", args.drive, *(["--transport", args.transport] if args.transport != "auto" else []),
                *(["--sim", args.sim] if args.sim else [])]

    def read_disc() -> dict:
        seen = subprocess.run(_argv("disc", *common()), stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
        line = next((ln for ln in reversed(seen.stdout.splitlines()) if ln.startswith("{")), None)
        return (json.loads(line) if line else {}).get("disc") or {}

    # READ CAPACITY on a written disc is its readable length, never a preset capacity.
    capacity = args.sectors
    capacity_source = '--sectors' if capacity is not None else None
    try:
        if capacity is not None and not positive_sectors(capacity):
            raise Stopped('--sectors must be a positive sector count below 4294967295')
        if args.iso:
            step("burn")
            if not args.yes_write:
                raise Stopped("burning needs --yes-write")
            if capacity is None:
                blank = read_disc()
                capacity = blank.get("capacity_sectors") if blank.get("blank") is True else None
                capacity_source = 'blank disc before burning' if capacity else None
            code = child("burn", "--drive", args.drive, "--iso", args.iso, "--media", args.media, "--yes-write",
                         *(["--speed", args.burn_speed] if args.burn_speed else []))
            if code:
                raise Stopped("the burn did not finish")

        step("check")
        disc = read_disc()
        ui.event("disc", **disc)
        if not disc.get("present"):
            raise Stopped("no disc is ready in the drive")
        if disc.get("blank") is True:
            raise Stopped("the disc in the drive is blank, not a measurement disc")
        if disc.get("media") != args.media:
            raise Stopped(f"the disc is a {disc.get('media')} disc, not {args.media}")
        if args.mid and disc.get("mid") != args.mid:
            raise Stopped(f"the disc's maker code is {disc.get('mid')}, not {args.mid}")
        found["disc"] = disc
        if capacity is None and positive_sectors(disc.get('capacity_sectors')):
            capacity, capacity_source = disc['capacity_sectors'], disc.get('capacity_source')
        if capacity is None:
            known = catalogue_capacity(disc.get('mid'), args.media)
            if known:
                capacity, capacity_source = known
        if args.preset and not positive_sectors(capacity):
            raise Stopped("recordable capacity is unknown; give --sectors with the blank disc's whole capacity "
                          "(not the burned length), or record it by MID in presets/catalogue.json")
        ui.say(f"{disc.get('kind')} · {disc.get('mid') or 'unknown maker code'} · {disc.get('sectors')} sectors")

        for kind in ("timing", "geo"):
            step(kind)
            # a multiple stays a multiple ("4x": its kB/s follow the disc's kind in timing/geo)
            speed = "keep" if args.speed is None else f"{args.speed:g}x" if type(args.speed).__name__ == "_SpeedX" else str(args.speed)
            print(f"Read speed for {kind}: {speed} (kB/s unless given as a multiple)", flush=True)
            ranges = []
            if kind == "geo" and args.avoid_mm:
                timing = found["timing"]["path"]
                with open(Path(timing) / "summary.json", encoding="utf-8") as stream:
                    setup = json.load(stream).get("setup") or {}
                ranges = ["--ranges", _geo_ranges(args.media, setup, args.avoid_mm)]
                print("Geo readable LBA ranges after --avoid-mm: " + ranges[1], flush=True)
            since = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(seconds=1)
            code = child(kind, *common(), "--media", args.media, "--out", args.out,
                         "--speed", speed, *ranges)
            result = measured(kind, since)
            verdict = guide.result_verdict(result, args.media) if result else None
            found[kind] = dict(path=result.path if result else None, verdict=verdict or "unknown", exit=code)
            ui.event("step_result", name=kind, path=found[kind]["path"], verdict=found[kind]["verdict"])
            if code or verdict not in GOOD:
                reason = getattr(result, "stopped", None) if result else None
                raise Stopped(reason or child_reason or f"the {kind} measurement was not usable ({verdict or 'no result'})")

        if args.preset:
            step("preset")
            sectors = capacity
            Path(args.preset).parent.mkdir(parents=True, exist_ok=True)
            if getattr(args, "photo", None):
                # The explicit photo path is checked against the newly measured
                # geometry, so a previous run's L will be refused.
                saved = save_preset(argparse.Namespace(**{**vars(args), "geo": found["geo"]["path"],
                                                          "sectors": sectors, "iso": None}))
                code = 0 if saved else 1
            else:
                code = child("disexport", "--geo", found["geo"]["path"], "--sectors", sectors, "--output", args.preset)
            if code or not Path(args.preset).is_file():
                raise Stopped("the preset was not written")
            found["preset"] = args.preset
            found["sectors"] = sectors
            found["capacity_source"] = capacity_source
        ui.event("calibrated", ok=True, **found)
        ui.say("\nCalibrated.", "green")
    except Stopped as why:
        ui.event("calibrated", ok=False, reason=str(why), **found)
        ui.event("error", message=str(why))
        raise SystemExit(str(why)) from None
    finally:
        stop_watch.set()
        signal.signal(signal.SIGINT, previous)


def save_preset(args):
    """Drive-free CLI parity with the photo step's save, including the quality gate.

    The main disexport parser is outside this task's edit scope. It discovers
    photo.json beside --geo automatically; calibrate --geo provides explicit
    photo selection and a selected-device check without a parser monkey patch.
    """
    from . import disexport
    from .__main__ import _export_gate
    if not args.preset or not positive_sectors(args.sectors):
        raise SystemExit("saving --geo needs --preset and --sectors (whole blank capacity)")
    if getattr(args, "iso", None):
        raise SystemExit("--geo exports an existing run; it cannot be combined with --iso")
    args.geo = guide.resolve_geo(args.geo, getattr(args, "media", None))
    args.install = False
    _export_gate(args)
    with open(args.geo, encoding="utf-8") as stream:
        fit = json.load(stream)["fit"]
    media = fit.get("media", "dvd")
    if getattr(args, "media", None) and args.media != media:
        raise SystemExit("--media does not match the geo run")
    span = fit.get("measured_span_mm", (25.8, 54.4)) if media == "cd" else (25.8, 54.4)
    lo = getattr(args, "r_min", None)
    hi = getattr(args, "r_max", None)
    lo, hi = span[0] if lo is None else lo, span[1] if hi is None else hi
    if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo < hi):
        raise SystemExit("fit radii must be finite, positive and --r-min less than --r-max")
    Path(args.preset).parent.mkdir(parents=True, exist_ok=True)
    out = disexport.export(args.geo, args.sectors, None, args.preset,
                           lo, hi,
                           "discprobe-" + media, media.upper() + " (drive-timing calibration)",
                           photo_path=getattr(args, "photo", None), device_id=getattr(args, "drive", None))
    decision = out["source"].get("photo_shift", dict(written=False, reason="not_cd"))
    ui.event("result", step="preset", path=args.preset, verdict="unknown", photo_shift=decision)
    print(f"Preset saved: {args.preset}", flush=True)
    print(f"Along-track constant written: {decision['frames']:g} frames (from photo; independent of disc batch; "
           "rephotograph after changing drives)" if decision["written"] else
           f"Along-track constant not written: {decision['reason']}", flush=True)
    return out


def add_parser(sub) -> None:
    from .__main__ import _speed

    sp = sub.add_parser("calibrate", help="calibrate a disc batch end to end: (burn,) check, timing, geo(, preset)")
    sp.add_argument("--drive", help="selected drive identity; required for measuring, checked when saving photo L")
    sp.add_argument("--media", choices=("dvd", "cd"), default="dvd")
    sp.add_argument("--iso", help="burn this measurement image first (needs --yes-write and a blank in the drive)")
    sp.add_argument("--yes-write", action="store_true", help="confirm the irreversible burn of --iso")
    sp.add_argument("--burn-speed", type=float, help="write multiple for the burn (default: DVD nearest supported to 8x, CD lowest)")
    sp.add_argument("--speed", type=_speed, default=DEFAULT_READ_SPEED,
                    help="read speed for timing and geo, in kB/s or a multiple like 4x (default: 4x of the disc's kind)")
    sp.add_argument("--avoid-mm", action="append", type=_avoid_band, default=[], metavar="A-B",
                    help="exclude radius band A-B in mm from geo rungs (repeatable; uses geo's nominal radius/LBA model)")
    sp.add_argument("--mid", help="the maker code the disc must have (the batch's)")
    sp.add_argument("--preset", help="also write a DiscImageStudio preset here")
    sp.add_argument("--geo", help="export this existing geo run without accessing a drive; needs --preset and --sectors")
    sp.add_argument("--photo", help="photo.json to apply only for verdict ok, the same geo run and specific drive; "
                    "refusals save without L. With --geo this is drive-free. Without --photo, calibrate/disexport "
                    "discover photo.json beside the geo summary; unknown L is never assumed zero")
    sp.add_argument("--r-min", type=float, help="with --geo: lower fit radius in mm")
    sp.add_argument("--r-max", type=float, help="with --geo: upper fit radius in mm")
    sp.add_argument("--sectors", type=int, help="whole blank capacity for the preset (default: read-only media capacity, then MID catalogue)")
    sp.add_argument("--transport", choices=["auto", "spti", "imapi"], default="auto")
    sp.add_argument("--sim", choices=["cav", "clv", "cav-nofua", "cav-flush", "cav-audio"],
                    help="run every step on the simulated drive (no burn)")
    sp.add_argument("--out", default="results", help="output directory (default: results)")
    sp.set_defaults(func=run)
