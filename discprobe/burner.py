"""Explicit, isolated write path. Never imported by a measuring transport.

Speed arguments are multiples of 1x; IMAPI reports sectors/second.
No failed write is retried. Platform adapters are injectable for hardware-free tests.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from . import ui, iso9660


class BurnError(ValueError):
    pass


def choose_speed(requested, supported, media="dvd"):
    speeds = sorted({float(s) for s in supported if math.isfinite(float(s)) and float(s) > 0})
    if not speeds:
        raise BurnError("The inserted disc reports no supported write speeds.")
    if requested is None:
        # Prefer 8x for DVD; a tie goes to the lower speed. CD retains its old default.
        return min(speeds, key=lambda s: abs(s - 8)) if media == "dvd" else speeds[0]
    if not math.isfinite(requested) or requested <= 0:
        raise BurnError("Write speed must be a positive multiple of 1x.")
    nearest = min(speeds, key=lambda s: abs(s - requested))
    if abs(nearest - requested) > max(.03, requested * .01):
        raise BurnError(f"Unsupported write speed {requested}x; supported: {speeds}")
    return nearest


def imapi_cd_command(drive, iso, speed=8):
    """The tested way to burn a CD on Windows (README step 1; KNOWLEDGE, 2026-11-04): this repo's IMAPI2 script at 8x,
    which writes Mode 2 Form 1, the layout our CD images are made for. Windows' own "Burn disc image" picks 40x, and
    that failed on a GH70N with cheap CD-R. The core does not run it itself yet (WindowsDVD refuses CD): it is shown
    to the person, with absolute paths so it works from any folder."""
    script = Path(__file__).resolve().parent.parent / "tools" / "burn_imapi.ps1"
    return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Drive", drive,
            "-Iso", str(Path(iso).resolve()), "-Speed", f"{speed:g}", "-Burn", "-Reload"]


def cd_sector_type(supported):
    """For a future Windows RawCD adapter: prefer raw P-W, never silently use data mode."""
    for kind in (3, 2):
        if kind in supported:
            return kind
    raise BurnError("CD DAO requires raw P-W (3) or cooked R-W (2).")


def validate_media(info, media, sectors):
    if info.get("blank") is not True:
        raise BurnError("A freshly verified blank disc is required.")
    if info.get("media") != media:
        raise BurnError(f"Wrong disc kind: expected {media}.")
    if info.get("free_sectors", 0) < sectors:
        raise BurnError("The image does not fit the free sectors on this disc.")


def parse_progress(line):
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("type") != "progress":
        return None
    try:
        values = [float(event[k]) for k in ("fraction", "elapsed_s", "eta_s")]
    except (KeyError, ValueError, TypeError):
        return None
    if not all(math.isfinite(v) and v >= 0 for v in values) or values[0] > 1:
        return None
    return dict(zip(("fraction", "elapsed_s", "eta_s"), values), stage=event.get("stage", "writing"))


def tool(name):
    path = shutil.which(name)
    if not path:
        raise BurnError(f"Required tool is missing: {name}. Install it before burning.")
    return path


class WindowsDVD:
    def __init__(self, drive, media, *, popen=subprocess.Popen, run=subprocess.run):
        if media != "dvd":
            raise BurnError("Windows CD DAO burning is not yet implemented; use cdrdao on Linux.")
        if not re.fullmatch(r"[A-Za-z]:", drive):
            raise BurnError("Windows drive must be a letter followed by a colon.")
        self.drive, self.popen, self.run = drive, popen, run
        self.base = [tool("powershell.exe"), "-NoProfile", "-NonInteractive", "-File",
                     str(Path(__file__).resolve().parent.parent / "tools" / "burn_imapi.ps1"),
                     "-Machine", "-Drive", drive]

    def inspect(self):
        result = self.run(self.base, capture_output=True, text=True, check=False)
        if result.returncode:
            raise BurnError("Could not inspect inserted disc.\nDetails: " + result.stdout + result.stderr)
        try:
            return json.loads(result.stdout.strip())
        except ValueError as exc:
            raise BurnError("IMAPI returned an invalid media report.") from exc

    def write(self, image, speed, cancel, progress):
        with tempfile.TemporaryDirectory(prefix="discprobe-burn-") as folder:
            marker = Path(folder) / "cancel"
            process = self.popen(self.base + ["-Burn", "-Iso", str(image), "-Speed", str(speed),
                                            "-CancelFile", str(marker)], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, creationflags=0x08000000)
            stop = threading.Event()
            def watch():
                while not stop.wait(.1):
                    if cancel.is_set():
                        marker.touch()
                        return
            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            actual = None
            diagnostics = []
            try:
                for line in process.stdout:
                    diagnostics.append(line.rstrip())
                    event = parse_progress(line)
                    if event:
                        progress(**event)
                    else:
                        try:
                            item = json.loads(line)
                            if item.get("type") == "speed":
                                actual = item["actual_x"]
                                progress(stage="speed", actual_speed_x=actual)
                        except (ValueError, AttributeError, KeyError):
                            pass
                code = process.wait()
            finally:
                stop.set()
                watcher.join()
            if cancel.is_set():
                raise BurnError("Burn cancelled. The cancelled disc is unusable; do not retry it.")
            if code:
                detail = "\n".join(diagnostics)
                hint = (" CD DAO devices may need raw P-W subchannels (type 3)."
                        if "C0AA0301" in detail.upper() else "")
                raise BurnError("IMAPI burn failed; no retry was attempted." + hint + "\nDetails: " + detail)
            # A missing speed report does not turn a completed write into a failed one.
            return actual


class LinuxBurner:
    def __init__(self, drive, media, *, run=subprocess.run, popen=subprocess.Popen):
        if not drive.startswith("/dev/") or any(c in drive for c in "\n\r\x00"):
            raise BurnError("Linux drive must be a /dev/ device path.")
        self.drive, self.media, self.run, self.popen = drive, media, run, popen
        self.writer = tool("cdrdao" if media == "cd" else "growisofs")
        self.inspector = tool("wodim" if media == "cd" else "dvd+rw-mediainfo")

    def inspect(self):
        argv = ([self.inspector, "dev=" + self.drive, "-atip"] if self.media == "cd"
                else [self.inspector, self.drive])
        result = self.run(argv, capture_output=True, text=True, check=False, env={**os.environ, "LC_ALL": "C"})
        text = result.stdout + result.stderr
        if result.returncode:
            raise BurnError("Media inspection failed.\nDetails: " + text)
        if self.media == "dvd":
            kind = re.search(r"Mounted Media:.*DVD", text)
            blank = bool(re.search(r"Disc status:\s*blank\b", text, re.I))
            capacity = re.search(r"Free Blocks:\s*(\d+)", text)
            speeds = re.findall(r"Write Speed #\d+:\s*([\d.]+)x", text)
        else:
            # ATIP identifies recordable media and capacity; disk-info supplies blank state.
            disk = self.run([self.writer, "disk-info", "--device", self.drive],
                            capture_output=True, text=True, check=False,
                            env={**os.environ, "LC_ALL": "C"})
            caps = self.run([self.inspector, "dev=" + self.drive, "-prcap"],
                            capture_output=True, text=True, check=False,
                            env={**os.environ, "LC_ALL": "C"})
            if disk.returncode or caps.returncode:
                raise BurnError("Could not confirm CD blank state and write speeds.\nDetails: " +
                                disk.stdout + disk.stderr + caps.stdout + caps.stderr)
            kind = re.search(r"(?:Current:\s*CD-RW?\b|ATIP info from disk)", text)
            blank = bool(re.search(r"CD-R(?:W)? empty\s*:\s*yes\b", disk.stdout + disk.stderr, re.I))
            capacity = re.search(r"ATIP start of lead out:\s*(\d+)", text)
            speeds = re.findall(r"Write speed #.*?\bCD\s+([\d.]+)x", caps.stdout + caps.stderr, re.I)
        # Leave space for CD DAO closing, as the legacy burn notes require.
        free = max(0, int(capacity[1]) - (300 if self.media == "cd" else 0)) if capacity else 0
        return dict(media=self.media if kind else "unknown", blank=blank,
                    free_sectors=free,
                    speeds_x=sorted(set(map(float, speeds))))

    def write(self, image, speed, cancel, progress):
        if self.media == "cd":
            from . import cd
            if '"' in str(image) or "\n" in str(image) or "\r" in str(image):
                raise BurnError("Image path cannot be represented safely in a cdrdao TOC.")
            toc = cd.write_cdrdao_toc(str(image))
            if not float(speed).is_integer():
                raise BurnError("cdrdao requires an integer CD speed multiplier.")
            argv = [self.writer, "write", "--device", self.drive, "--speed", str(int(speed)), toc]
        else:
            argv = [self.writer, "-dvd-compat", "-speed=" + str(speed), "-Z", self.drive + "=" + str(image)]
        process = self.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env={**os.environ, "LC_ALL": "C"}, start_new_session=True)
        stop = threading.Event()
        def watch():
            while not stop.wait(.1):
                if cancel.is_set():
                    process.send_signal(signal.SIGINT)
                    return
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        started, actual, diagnostics = time.monotonic(), None, []
        try:
            for line in process.stdout:
                diagnostics.append(line.rstrip())
                match = re.search(r"([\d.]+)%.*?([\d.]+)x", line)
                cd_match = re.search(r"Wrote\s+(\d+)\s+of\s+(\d+)\s+MB", line)
                if match:
                    fraction = min(1., float(match[1]) / 100)
                    elapsed = time.monotonic() - started
                    actual = float(match[2])
                    progress(stage="speed", actual_speed_x=actual)
                    progress(fraction=fraction, elapsed_s=elapsed,
                             eta_s=elapsed * (1 - fraction) / fraction if fraction else 0, stage="writing")
                elif cd_match and int(cd_match[2]):
                    fraction = min(.999, int(cd_match[1]) / int(cd_match[2]))
                    elapsed = time.monotonic() - started
                    progress(fraction=fraction, elapsed_s=elapsed,
                             eta_s=elapsed * (1 - fraction) / fraction if fraction else 0, stage="writing")
                ui.say(line.rstrip())
            code = process.wait()
        finally:
            stop.set()
            watcher.join()
        if cancel.is_set():
            raise BurnError("Burn cancelled. The cancelled disc is unusable; do not retry it.")
        if code:
            raise BurnError("Burn failed; no retry was attempted.\nDetails: " + "\n".join(diagnostics))
        progress(fraction=1, elapsed_s=time.monotonic() - started, eta_s=0, stage="completed")
        return actual  # None means the utility did not report measured throughput.


def adapter(drive, media):
    if sys.platform == "win32":
        return WindowsDVD(drive, media)
    if sys.platform.startswith("linux"):
        return LinuxBurner(drive, media)
    raise BurnError("Burning on macOS/this platform is not yet implemented.")


def sample_lbas(sectors, samples=96):
    """Up to 96 distinct, evenly spaced 16-sector blocks, including both ends.

    A short image has one partial block; a non-aligned tail is not sampled.
    """
    blocks = max(1, sectors // 16)
    count = min(samples, blocks)
    return [16 * (i * (blocks - 1) // max(1, count - 1)) for i in range(count)]


def verify_image(drive, image, media, cancel, *, device_factory=None):
    """Compare user bytes via allowlisted READ(10), without application retries."""
    from . import mmc
    from .geometry import NOMINAL
    if device_factory is None:
        from .device import Device
        device_factory = Device
    sectors = image.stat().st_size // 2048
    lbas = sample_lbas(sectors)
    summary = dict(status="completed", sampled_blocks=len(lbas), ok=0, differing=0,
                   unreadable=0, failures=[], radius_model="nominal", untested=0)
    def failure(lba, kind, error):
        summary[kind] += 1
        summary["failures"].append(dict(lba=lba, radius_mm=NOMINAL[media].radius(lba),
                                        kind=kind, error=error))
    try:
        with device_factory(drive) as dev, image.open("rb") as source:
            for index, lba in enumerate(lbas):
                if cancel.is_set():
                    summary.update(status="cancelled", untested=len(lbas) - index)
                    break
                count = min(16, sectors - lba)
                source.seek(lba * 2048)
                expected = source.read(count * 2048)
                try:
                    response = dev.execute(mmc.read10(lba, count), data_len=count * 2048, timeout_s=10)
                    if not response.ok:
                        raise OSError(f"status {response.status}; sense {response.sense}")
                    if len(response.data) != len(expected):
                        raise OSError(f"short read: {len(response.data)} of {len(expected)} bytes")
                except OSError as exc:
                    failure(lba, "unreadable", str(exc))
                else:
                    if response.data == expected:
                        summary["ok"] += 1
                    else:
                        failure(lba, "differing", "bytes differ from the ISO")
                ui.event("verify_progress", fraction=(index + 1) / len(lbas), lba=lba)
    except OSError as exc:
        summary.update(status="unavailable", error=str(exc),
                       untested=len(lbas) - summary["ok"] - summary["differing"] - summary["unreadable"])
    return summary


def burn(drive, iso, *, media="dvd", speed=None, yes_write=False, recorder=None, cancel=None,
         no_verify=False, verifier=None):
    if yes_write is not True:
        raise BurnError("Writing requires explicit --yes-write confirmation.")
    if media not in ("dvd", "cd"):
        raise BurnError("Only DVD and CD burning are supported.")
    image = Path(iso).resolve()
    if not image.is_file() or image.suffix.lower() != ".iso" or Path(str(image) + iso9660.UNFINISHED).exists():
        raise BurnError("Choose a finished ISO image.")
    size = image.stat().st_size
    if not size or size % 2048:
        raise BurnError("ISO size must be a positive multiple of 2048 bytes.")
    recorder = recorder or adapter(drive, media)
    info = recorder.inspect()
    validate_media(info, media, size // 2048)
    selected = choose_speed(speed, info["speeds_x"], media)
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise BurnError("Cancelled before writing; nothing was written.")
    log_path = Path(str(image) + ".burn.jsonl")
    # Open the durable log before any write. Append to preserve earlier burns of this image.
    def record(kind, **fields):
        stamp = time.time()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(type=kind, time=stamp, drive=drive, media=media,
                                         image=str(image), **fields), ensure_ascii=False, allow_nan=False) + "\n")
        ui.event(kind, time=stamp, **dict(fields, log_path=str(log_path)))
    record("burn_speed", requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=None)
    print(f"Requested write speed: {selected:g}x ({'default' if speed is None else f'--speed {speed:g}x'}). "
          f"Burn log: {log_path}", flush=True)
    print("The tray closes for writing. Burning cannot be undone.", flush=True)
    started = time.monotonic()
    reported = None
    def progress(**fields):
        nonlocal reported
        if fields.get("stage") == "speed":
            actual = fields["actual_speed_x"]
            if actual != reported:
                reported = actual
                record("burn_speed", requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=actual)
                print(f"Drive/utility reports write speed: {actual:g}x.", flush=True)
        else:
            ui.event("progress", **fields)
    try:
        actual = recorder.write(image, selected, cancel, progress)
    except BurnError as exc:
        elapsed = time.monotonic() - started
        record("burn_result", result="cancelled" if cancel.is_set() else "failed",
               requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=reported,
               elapsed_s=elapsed, verified=False)
        raise BurnError(f"{exc}\nElapsed: {elapsed:.1f}s.") from exc
    elapsed = time.monotonic() - started
    record("burn_speed", requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=actual)
    print(f"Write completed in {elapsed:.1f}s; drive/utility reports: "
          f"{str(actual) + 'x' if actual else 'speed not reported'}.", flush=True)
    verification = dict(status="skipped")
    if not no_verify:
        print("Reading back up to 96 evenly spaced 16-sector blocks; drive retries may take time...", flush=True)
        ui.event("verify_progress", fraction=0, lba=None)
        try:
            verification = (verifier or verify_image)(drive, image, media, cancel)
        except OSError as exc:
            verification = dict(status="unavailable", sampled_blocks=len(sample_lbas(size // 2048)),
                                ok=0, differing=0, unreadable=0, failures=[],
                                untested=len(sample_lbas(size // 2048)), error=str(exc))
        print(f"Read-back sample: {verification['ok']} blocks ok / {verification['differing']} differing / "
              f"{verification['unreadable']} unreadable; {verification['untested']} untested "
              f"({verification['status']}). This is a sample, not a full-disc check.", flush=True)
        if verification.get("error"):
            print(f"Read-back could not finish: {verification['error']}", flush=True)
        for failure in verification["failures"]:
            print(f"  LBA {failure['lba']} (~{failure['radius_mm']:.2f} mm, nominal): "
                  f"{failure['kind']}: {failure['error']}", flush=True)
        if verification["status"] != "completed" or verification["differing"] or verification["unreadable"]:
            print("The write completed. Reading back failed or could not finish; the picture may still look fine. "
                  "Try burning another blank disc at another speed.", flush=True)
    else:
        print("Read-back verification skipped (--no-verify).", flush=True)
    result = dict(result="completed", actual_speed_x=actual, requested_speed_x=speed,
                  selected_speed_x=selected, elapsed_s=elapsed, verification=verification,
                  verified=verification["status"] == "completed" and not
                  (verification["differing"] or verification["unreadable"]), log_path=str(log_path))
    record("burn_result", **result)
    return result


def run(args):
    if args.media == "cd":
        from . import cd
        cd.set_sector_layout(args.cd_sector)
    cancel = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    stop = threading.Event()
    marker = os.environ.get("DISCPROBE_BURN_CANCEL")
    def watch():
        while not stop.wait(.1):
            if marker and Path(marker).exists():
                cancel.set()
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        burn(args.drive, args.iso, media=args.media, speed=args.speed, yes_write=args.yes_write,
             cancel=cancel, no_verify=args.no_verify)
    except BurnError as exc:
        ui.event("error", message=str(exc))
        raise SystemExit(str(exc)) from None
    finally:
        stop.set()
        watcher.join()
        signal.signal(signal.SIGINT, previous)


def web_child(argv, **kwargs):
    """Preserve job ownership, but request platform cancellation instead of killing Write."""
    from .webui import Child
    class BurnChild(Child):
        def __init__(self, *args, **options):
            self.burn_ready = False
            super().__init__(*args, **options)
            self.burn_ready = True
        def cancel(self):
            if not self.burn_ready:
                return super().cancel()  # Base constructor may need to stop a suspended child.
            if self.process.poll() is None:
                Path(kwargs["env"]["DISCPROBE_BURN_CANCEL"]).touch()
        def close(self):
            # Called only after wait; normal close may release the Windows job handle.
            if self.process.poll() is not None:
                super().close()
    env = kwargs["env"]
    env["DISCPROBE_BURN_CANCEL"] = str(Path(env["DISCPROBE_EVENTS"]).with_name("burn.cancel"))
    return BurnChild(argv, **kwargs)
