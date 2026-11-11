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

import datetime
import json
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


def _argv(*args) -> list[str]:
    return [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "discprobe", *map(str, args)]


class Stopped(Exception):
    pass


def run(args) -> None:
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

    def step(name):
        if cancel.is_set():
            raise Stopped("cancelled before " + name)
        i = steps.index(name)
        ui.event("step", name=name, index=i, total=len(steps))
        ui.say(f"\n[{i + 1}/{len(steps)}] {name}", "bold")

    def child(*a) -> int:
        """One step's command, its output on ours; stopped if the run is cancelled (a burn stops itself
        through the same marker, at a point where stopping is safe)."""
        proc = subprocess.Popen(_argv(*a), stdin=subprocess.DEVNULL)
        while proc.poll() is None:
            if cancel.is_set() and a[0] != "burn":
                proc.terminate()
            time.sleep(.2)
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
            since = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(seconds=1)
            code = child(kind, *common(), "--media", args.media, "--out", args.out,
                         *(["--speed", args.speed] if args.speed else []))
            result = measured(kind, since)
            verdict = guide.result_verdict(result, args.media) if result else None
            found[kind] = dict(path=result.path if result else None, verdict=verdict or "unknown", exit=code)
            ui.event("step_result", name=kind, path=found[kind]["path"], verdict=found[kind]["verdict"])
            if code or verdict not in GOOD:
                raise Stopped(f"the {kind} measurement was not usable ({verdict or 'no result'})")

        if args.preset:
            step("preset")
            sectors = capacity
            Path(args.preset).parent.mkdir(parents=True, exist_ok=True)
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


def add_parser(sub) -> None:
    sp = sub.add_parser("calibrate", help="calibrate a disc batch end to end: (burn,) check, timing, geo(, preset)")
    sp.add_argument("--drive", required=True)
    sp.add_argument("--media", choices=("dvd", "cd"), default="dvd")
    sp.add_argument("--iso", help="burn this measurement image first (needs --yes-write and a blank in the drive)")
    sp.add_argument("--yes-write", action="store_true", help="confirm the irreversible burn of --iso")
    sp.add_argument("--burn-speed", type=float, help="write multiple for the burn (default: the lowest)")
    sp.add_argument("--speed", help="read speed for timing and geo (as those commands take it)")
    sp.add_argument("--mid", help="the maker code the disc must have (the batch's)")
    sp.add_argument("--preset", help="also write a DiscImageStudio preset here")
    sp.add_argument("--sectors", type=int, help="whole blank capacity for the preset (default: read-only media capacity, then MID catalogue)")
    sp.add_argument("--transport", choices=["auto", "spti", "imapi"], default="auto")
    sp.add_argument("--sim", choices=["cav", "clv", "cav-nofua", "cav-flush", "cav-audio"],
                    help="run every step on the simulated drive (no burn)")
    sp.add_argument("--out", default="results", help="output directory (default: results)")
    sp.set_defaults(func=run)
