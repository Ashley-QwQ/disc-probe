"""Explicit, isolated write path. Never imported by a measuring transport.

Speed arguments are multiples of 1x; IMAPI reports sectors/second.
No failed write is retried. Platform adapters are injectable for hardware-free tests.
"""
from __future__ import annotations

from .drive_lock import child_env, locked_drive

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

from . import disc_identity, discid, image_output, mmc, ui


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
    from .resources import tool
    script = tool("burn_imapi.ps1")
    return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Drive", drive,
            "-Iso", str(Path(iso).resolve()), "-Speed", f"{speed:g}", "-Burn", "-Reload"]


def cd_sector_type(supported):
    """For a future Windows RawCD adapter: prefer raw P-W, never silently use data mode."""
    for kind in (3, 2):
        if kind in supported:
            return kind
    raise BurnError("CD DAO requires raw P-W (3) or cooked R-W (2).")


def validate_media(info, media, sectors, *, append=False, expect_start=None):
    if append:
        if info.get('blank') is not False or info.get('closed') is not False:
            raise BurnError('Append requires a recorded open DVD, not a blank or closed disc.')
        if expect_start is None or info.get('next_writable') != expect_start:
            raise BurnError(f"NWA mismatch: drive {info.get('next_writable')}, expected {expect_start}.")
    elif info.get("blank") is not True:
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
            raise BurnError("Windows CD DAO burning is not yet implemented; use cdrdao on Linux. "
                            "For the supported external Windows data-CD path, use tools/burn_imapi.ps1 "
                            "with a DP --cd-sector mode2form1 ISO; it writes Mode 2 Form 1, not DAO. "
                            "Never send a Mode 1 image through that path. For DAO use DiscImageStudio or Linux cdrdao.\n"
                            "Windows 集成刻录尚不支持 CD DAO，已在写入前拒绝。外部数据 CD 可使用 tools/burn_imapi.ps1，"
                            "且 DP 镜像必须用 --cd-sector mode2form1 生成；该路径写 Mode 2 Form 1，不是 DAO。"
                            "不要把 Mode 1 镜像交给它。DAO 请用 DiscImageStudio 或 Linux cdrdao。")
        if not re.fullmatch(r"[A-Za-z]:", drive):
            raise BurnError("Windows drive must be a letter followed by a colon.")
        self.drive, self.popen, self.run = drive, popen, run
        self.base = [tool("powershell.exe"), "-NoProfile", "-NonInteractive", "-File",
                     str(Path(__file__).resolve().parent.parent / "tools" / "burn_imapi.ps1"),
                     "-Machine", "-Drive", drive]

    def inspect(self):
        result = self.run(self.base, capture_output=True, text=True, check=False, env=child_env(self.drive))
        if result.returncode:
            raise BurnError("Could not inspect inserted disc.\nDetails: " + result.stdout + result.stderr)
        try:
            report = json.loads(result.stdout.strip())
            if 'current_profile' in report:
                report.update(mmc.rewritable(report['current_profile'], report.get('erasable')))
                from .eraser import inspect
                try:
                    disc = inspect(self.drive)
                    report.update({k:v for k,v in disc.items() if k.startswith('rewritable') or k=='capacity_sectors'})
                except OSError:
                    pass  # MMC erasable evidence stays null if the read is unavailable.
            return report
        except ValueError as exc:
            raise BurnError("IMAPI returned an invalid media report.") from exc

    def write(self, image, speed, cancel, progress, *, keep_open=False, append=False, expect_start=None,
              before_write=None):
        with tempfile.TemporaryDirectory(prefix="discprobe-burn-") as folder:
            marker = Path(folder) / "cancel"
            session = (['-KeepOpen'] if keep_open else []) + (['-Append', '-ExpectStart', str(expect_start)] if append else [])
            patch_args = []
            source = image
            if isinstance(image, discid.PatchedImage):
                source = image.path
                patch_file = Path(folder) / "identity.bin"
                patch_file.write_bytes(image.patch_bundle())
                patch_args = ["-IdentityPatch", str(patch_file), "-IdentityOffset", str(image.patch_offset)]
            if before_write is not None:
                before_write()
            process = self.popen(self.base + patch_args + ["-Burn", "-Iso", str(source), "-Speed", str(speed),
                                            "-CancelFile", str(marker)] + session, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, creationflags=0x08000000,
                                 env=child_env(self.drive))
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
        report = dict(media=self.media if kind else "unknown", blank=blank,
                    **mmc.rewritable(
                        0x0A if re.search(r'CD-RW\b', text) else
                        0x14 if re.search(r'DVD-RW\b', text) else
                        0x1A if re.search(r'DVD\+RW\b', text) else None),
                    free_sectors=free,
                    speeds_x=sorted(set(map(float, speeds))))
        # ATIP/media-tool text identifies the current profile; no supported-profile inference.
        return report

    def write(self, image, speed, cancel, progress, *, before_write=None):
        # cdrdao requires a seekable on-disk data file. Use a private spool of
        # the patched stream; never rewrite the user's ISO or its sidecars.
        if isinstance(image, discid.PatchedImage) and self.media == "cd":
            with tempfile.TemporaryDirectory(prefix="discprobe-stream-") as folder:
                spool = Path(folder) / "disc.iso"
                with image.open("rb") as source, spool.open("xb") as target:
                    while data := source.read(1024 * 1024):
                        if cancel.is_set():
                            raise BurnError("Cancelled while preparing the stream; nothing was written.")
                        target.write(data)
                return self.write(spool, speed, cancel, progress, before_write=before_write)
        if self.media == "cd":
            from . import cd
            if '"' in str(image) or "\n" in str(image) or "\r" in str(image):
                raise BurnError("Image path cannot be represented safely in a cdrdao TOC.")
            toc = cd.write_cdrdao_toc(str(image))
            if not float(speed).is_integer():
                raise BurnError("cdrdao requires an integer CD speed multiplier.")
            argv = [self.writer, "write", "--device", self.drive, "--speed", str(int(speed)), toc]
        else:
            argv = [self.writer, "-dvd-compat", "-speed=" + str(speed), "-Z",
                    self.drive + "=" + ("/dev/fd/0" if isinstance(image, discid.PatchedImage) else str(image))]
            if isinstance(image, discid.PatchedImage):
                argv.insert(1, "-use-the-force-luke=tracksize:" + str(image.stat().st_size // 2048))
        if before_write is not None:
            before_write()
        process = self.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             **({"stdin": subprocess.PIPE} if isinstance(image, discid.PatchedImage) else {}),
                             env={**os.environ, "LC_ALL": "C"}, start_new_session=True)
        feed_errors = []
        feeder = None
        if isinstance(image, discid.PatchedImage):
            def feed():
                try:
                    with image.open("rb") as source:
                        while data := source.read(1024 * 1024):
                            if cancel.is_set():
                                break
                            process.stdin.buffer.write(data)
                except (OSError, ValueError) as exc:
                    feed_errors.append(exc)
                finally:
                    try:
                        process.stdin.close()
                    except OSError as exc:
                        feed_errors.append(exc)
            feeder = threading.Thread(target=feed, daemon=True)
            feeder.start()
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
            if feeder:
                feeder.join()
        if cancel.is_set():
            raise BurnError("Burn cancelled. The cancelled disc is unusable; do not retry it.")
        if code:
            raise BurnError("Burn failed; no retry was attempted.\nDetails: " + "\n".join(diagnostics))
        if feed_errors:
            raise BurnError("Burn stream failed; no retry was attempted: " + str(feed_errors[0]))
        progress(fraction=1, elapsed_s=time.monotonic() - started, eta_s=0, stage="completed")
        return actual  # None means the utility did not report measured throughput.


def adapter(drive, media):
    if sys.platform == "win32":
        return WindowsDVD(drive, media)
    if sys.platform.startswith("linux"):
        return LinuxBurner(drive, media)
    raise BurnError("Burning on macOS/this platform is not yet implemented.")


@locked_drive("info")
def inspect_drive(drive, media):
    return adapter(drive, media).inspect()


def sample_lbas(sectors, samples=96):
    """Up to 96 distinct, evenly spaced 16-sector blocks, including both ends.

    The final block may contain fewer than 16 sectors.
    """
    blocks = max(1, (sectors + 15) // 16)
    count = min(samples, blocks)
    return [16 * (i * (blocks - 1) // max(1, count - 1)) for i in range(count)]


@locked_drive("verify")
def verify_image(drive, image, media, cancel, *, device_factory=None, start_lba=0):
    """Compare user bytes via allowlisted READ(10), without application retries."""
    from . import mmc
    from .geometry import NOMINAL
    if device_factory is None:
        from .device import Device
        device_factory = Device
    sectors = image.stat().st_size // 2048
    lbas = sample_lbas(sectors)
    if isinstance(image, discid.PatchedImage):
        # Always include the whole identity, even when regular samples miss it.
        lbas = sorted(set(lbas) | image.verification_lbas())
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
                    response = dev.execute(mmc.read10(start_lba + lba, count), data_len=count * 2048, timeout_s=10)
                    if not response.ok:
                        raise OSError(f"status {response.status}; sense {response.sense}")
                    if len(response.data) != len(expected):
                        raise OSError(f"short read: {len(response.data)} of {len(expected)} bytes")
                except OSError as exc:
                    failure(start_lba + lba, "unreadable", str(exc))
                else:
                    if response.data == expected:
                        summary["ok"] += 1
                    else:
                        failure(start_lba + lba, "differing", "bytes differ from the ISO")
                ui.event("verify_progress", fraction=(index + 1) / len(lbas), lba=start_lba + lba)
    except OSError as exc:
        summary.update(status="unavailable", error=str(exc),
                       untested=len(lbas) - summary["ok"] - summary["differing"] - summary["unreadable"])
    return summary


def _write_preflight(drive, image, *, media, speed, recorder, cancel, keep_open,
                     append, expect_start, disc_id, disc_id_code, erase, expected_identity):
    """Plan the write and any erase using read-only evidence."""
    if media not in ("dvd", "cd"):
        raise BurnError("Only DVD and CD burning are supported.")
    if (keep_open or append or expect_start is not None) and media != 'dvd':
        raise BurnError('Session options currently support DVD only.')
    if keep_open and append:
        raise BurnError('--append closes the disc; do not combine with --keep-open.')
    if append != (expect_start is not None) or (expect_start is not None and expect_start <= 0):
        raise BurnError('--append requires a positive --expect-start, and vice versa.')
    if erase and append:
        raise BurnError('--erase cannot be combined with --append.')
    try:
        stat = image_output.finished_stat(image)
        image_output.require_checked(image, stat)
        with image.open('rb') as stream:
            stream.read(1)
    except (OSError, ValueError) as exc:
        raise BurnError(str(exc)) from exc
    size = stat.st_size
    try:
        spec = json.loads(image.with_suffix('.image.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        spec = {}
    if not isinstance(spec, dict):
        raise BurnError('镜像布局记录无效。 / Invalid image layout record.')
    if spec.get('state') == 'pending' and not keep_open:
        raise BurnError('Label pending: burn --keep-open, then geo and label.')
    if spec and spec.get('first_lba', 0) != (expect_start or 0):
        raise BurnError('Image first_lba does not match --expect-start.')
    enabled = discid.requested(disc_id, disc_id_code)
    identity = None
    if append and enabled:
        raise BurnError('Identity copies stay in the first session; omit --disc-id when appending the label.')
    if enabled:
        try:
            identity = discid.preflight(image)['record']
            if not identity:
                raise ValueError("Burn identity requires an ISO generated with --disc-id")
        except ValueError as exc:
            raise BurnError(str(exc)) from exc
    elif not append and size >= 25 * 2048:
        try:
            identity = discid.read_image(image)
        except ValueError:
            pass  # no opt-in: send even an unrecognised old ISO exactly as supplied
    if expected_identity is None and (recorder is None or isinstance(recorder, (WindowsDVD, LinuxBurner))):
        expected_identity = disc_identity.expected_for_write(drive, erasing=erase)
    if expected_identity is not None:
        disc_identity.require_identity(expected_identity, erasing=erase)
    recorder = recorder or adapter(drive, media)
    if (keep_open or append) and isinstance(recorder, LinuxBurner):
        raise BurnError('Session options currently require the Windows DVD IMAPI path.')
    info = recorder.inspect()
    erase_recorder = None
    if info.get('blank') is not True and not append and erase:
        from . import eraser
        erase_recorder = recorder if hasattr(recorder, 'erase') else eraser.adapter(drive)
        target = erase_recorder.inspect()
        if target.get('media') != media or info.get('media') != media:
            raise BurnError(f'Wrong disc kind: expected {media}.')
        if not target.get('rewritable'):
            raise BurnError('This disc is not rewritable; erasing is refused.')
        capacity = target.get('capacity_sectors') or info.get('capacity_sectors')
        if isinstance(recorder, LinuxBurner) and media == 'cd' and capacity:
            capacity -= 300  # same closing reserve as LinuxBurner.inspect
        if not capacity or size // 2048 > capacity:
            raise BurnError('The image does not fit, or rewritable capacity is unknown; erasing was refused.')
    else:
        if info.get('blank') is not True and not append and info.get('rewritable'):
            raise BurnError('Recorded rewritable disc: add --erase to erase its contents before burning.')
        validate_media(info, media, size // 2048, append=append, expect_start=expect_start)
    selected = choose_speed(speed, info["speeds_x"], media)
    if isinstance(recorder, LinuxBurner) and media == 'cd':
        if any(char in str(image) for char in '"\n\r'):
            raise BurnError('镜像路径不能写入 cdrdao TOC。 / Image path cannot be represented safely in a cdrdao TOC.')
        if not float(selected).is_integer():
            raise BurnError('cdrdao 要求整数 CD 刻录倍速。 / cdrdao requires an integer CD speed multiplier.')
    if cancel.is_set():
        raise BurnError("Cancelled before writing; nothing was written.")
    source = image
    if enabled:
        try:
            if isinstance(recorder, (WindowsDVD, LinuxBurner)):
                from .device import Device
                from .info import quick
                try:
                    with Device(drive) as dev:
                        fields = discid.media_fields(quick(dev))
                    info.update({k: v for k, v in fields.items() if v is not None})
                except OSError:
                    pass  # unsupported/unreadable MID stays null, never guessed
            source = discid.patch_burn(image, info, speed=speed, selected=selected, media=media, code=disc_id_code)
            identity = source.record
        except ValueError as exc:
            raise BurnError(str(exc)) from exc
        discid.notice()

    log_path, record = _burn_log(drive, image, media)
    if erase_recorder is not None:
        record('burn_preflight', sectors=size // 2048, selected_speed_x=selected)
    else:
        with log_path.open('a', encoding='utf-8'):
            pass
    # Compare against the authorization after the log check, with both locks held.
    if expected_identity is not None:
        disc_identity.check_identity(drive, expected_identity)
    if cancel.is_set():
        raise BurnError("Cancelled before writing; nothing was written.")
    return size, recorder, erase_recorder, info, selected, source, identity, log_path, record, expected_identity


@locked_drive("burn")
def burn(drive, iso, *, media="dvd", speed=None, yes_write=False, recorder=None, cancel=None,
         no_verify=False, verifier=None, keep_open=False, append=False, expect_start=None,
         disc_id=False, disc_id_code=None, state_checker=None, erase=False, expected_identity=None):
    if yes_write is not True:
        raise BurnError("Writing requires explicit --yes-write confirmation.")
    try:
        with image_output.exclusive(iso) as image:
            return _burn_locked(drive, image, media=media, speed=speed, recorder=recorder,
                cancel=cancel or threading.Event(), no_verify=no_verify, verifier=verifier, keep_open=keep_open,
                append=append, expect_start=expect_start, disc_id=disc_id, disc_id_code=disc_id_code,
                state_checker=state_checker, erase=erase, expected_identity=expected_identity)
    except ValueError as exc:
        if isinstance(exc, (BurnError, disc_identity.DiscChanged)):
            raise
        raise BurnError(str(exc)) from exc


def _burn_log(drive, image, media):
    log_path = Path(str(image) + ".burn.jsonl")
    # Capture the generated geometry's evidence once. Re-burning this ISO never
    # consults a newer photo.json or changes its sector map.
    photo_l = None
    for suffix in (".image.json", ".rings.json"):
        try:
            photo_l = json.loads(image.with_suffix(suffix).read_text(encoding="utf-8")).get("photo_l")
        except (OSError, ValueError, AttributeError):
            continue
        if photo_l is not None:
            break
    # Open the durable log before any write. Append to preserve earlier burns of this image.
    def record(kind, **fields):
        stamp = time.time()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(type=kind, time=stamp, drive=drive, media=media,
                                         image=str(image), **({"photo_l": photo_l} if photo_l is not None else {}),
                                         **fields), ensure_ascii=False, allow_nan=False) + "\n")
        ui.event(kind, time=stamp, **dict(fields, log_path=str(log_path),
                                       **({"photo_l": photo_l} if photo_l is not None else {})))
    return log_path, record


def _burn_locked(drive, image, *, media, speed, recorder, cancel, no_verify, verifier, keep_open,
                 append, expect_start, disc_id, disc_id_code, state_checker, erase, expected_identity):
    size, recorder, erase_recorder, info, selected, source, identity, log_path, record, expected_identity = _write_preflight(
        drive, image, media=media, speed=speed, recorder=recorder, cancel=cancel,
        keep_open=keep_open, append=append, expect_start=expect_start, disc_id=disc_id,
        disc_id_code=disc_id_code, erase=erase, expected_identity=expected_identity)
    if erase_recorder is not None:
        from . import eraser
        erased = eraser.erase(drive, cancel=cancel, recorder=erase_recorder, expected_identity=expected_identity)
        # This is a postcondition of erasing, not a prerequisite for starting it.
        info = recorder.inspect()
        if erased.get('overwrite_ready') and info.get('rewritable'):
            info['blank'] = True
            info['free_sectors'] = erased['disc'].get('capacity_sectors') or info.get('free_sectors', 0)
        validate_media(info, media, size // 2048)
    record("burn_speed", requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=None)
    if identity:
        record("disc_identity", id=identity["body"]["id"], identity=identity)
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

    def before_write():
        if expected_identity is not None:
            disc_identity.check_identity(drive, expected_identity, after_erase=erase_recorder is not None)
        if cancel.is_set():
            raise BurnError("Cancelled before writing; nothing was written.")

    try:
        options = dict(keep_open=keep_open, append=append, expect_start=expect_start) if keep_open or append else {}
        if isinstance(recorder, (WindowsDVD, LinuxBurner)):
            options["before_write"] = before_write
        else:
            before_write()
        actual = recorder.write(source, selected, cancel, progress, **options)
    except (BurnError, OSError) as exc:
        elapsed = time.monotonic() - started
        message = str(exc)
        if info.get('rewritable'):
            message = ('This recording did not finish. Erase this rewritable disc before burning again.\n' +
                       message.replace('The cancelled disc is unusable; do not retry it.', ''))
        record("burn_result", result="cancelled" if cancel.is_set() else "failed", reason=message,
               requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=reported,
               elapsed_s=elapsed, verified=False)
        raise BurnError(f"{message}\nElapsed: {elapsed:.1f}s.") from exc
    elapsed = time.monotonic() - started
    record("burn_speed", requested_speed_x=speed, selected_speed_x=selected, actual_speed_x=actual)
    print(f"Write completed in {elapsed:.1f}s; drive/utility reports: "
          f"{str(actual) + 'x' if actual else 'speed not reported'}.", flush=True)
    verification = dict(status="skipped")
    from .recorded import burn_state
    try:
        state = (state_checker or burn_state)(drive, size // 2048, keep_open=keep_open,
                                             start_lba=expect_start or 0)
    except (OSError, ValueError) as exc:
        state = dict(status='unknown', reason=None, unconfirmed=[f'disc state could not be read: {exc}'])
    if state.get('unconfirmed'):
        print('Warning: after the write, ' + '; '.join(state['unconfirmed']) + '. The read-back below is the check that remains.',
              flush=True)
    if not no_verify:
        print("Reading back up to 96 evenly spaced 16-sector blocks plus the identity block; drive retries may take time..."
              if isinstance(source, discid.PatchedImage) else
              "Reading back up to 96 evenly spaced 16-sector blocks; drive retries may take time...", flush=True)
        ui.event("verify_progress", fraction=0, lba=None)
        try:
            verification = (verifier or verify_image)(drive, source, media, cancel,
                **(dict(start_lba=expect_start) if append else {}))
        except OSError as exc:
            expected_lbas = set(sample_lbas(size // 2048))
            if isinstance(source, discid.PatchedImage):
                expected_lbas.update(source.verification_lbas())
            verification = dict(status="unavailable", sampled_blocks=len(expected_lbas),
                                ok=0, differing=0, unreadable=0, failures=[],
                                untested=len(expected_lbas), error=str(exc))
        print(f"Read-back sample: {verification['ok']} blocks ok / {verification['differing']} differing / "
              f"{verification['unreadable']} unreadable; {verification['untested']} untested "
              f"({verification['status']}). This is a sample, not a full-disc check.", flush=True)
        if verification.get("error"):
            print(f"Read-back could not finish: {verification['error']}", flush=True)
        for failure in verification["failures"]:
            print(f"  LBA {failure['lba']} (~{failure['radius_mm']:.2f} mm, nominal): "
                  f"{failure['kind']}: {failure['error']}", flush=True)
        if verification["status"] != "completed" or verification["differing"] or verification["unreadable"]:
            print("Read-back failed or could not finish; this burn did not check out. "
                  "First retry reading this same disc after closing other drive software, or use another available drive. "
                  "Only replace it if the saved write/read logs establish incomplete or unreadable recorded data; "
                  "inspect those logs before another burn.", flush=True)
    else:
        print("Read-back verification skipped (--no-verify).", flush=True)
    result = dict(result="completed", actual_speed_x=actual, requested_speed_x=speed,
                  selected_speed_x=selected, elapsed_s=elapsed, verification=verification,
                  keep_open=keep_open, append=append, first_lba=expect_start or 0,
                  disc_state=state, verified=verification["status"] == "completed" and not
                  (verification["differing"] or verification["unreadable"]), log_path=str(log_path))
    if identity:
        result["identity"] = identity
    reasons = []
    if state['status'] == 'failed':
        reasons.append(state['reason'])
    if not no_verify and (not result['verified'] or verification.get('untested')):
        reasons.append('Read-back failed or could not finish: '
                       f"{verification.get('differing', 0)} differing / {verification.get('unreadable', 0)} unreadable / "
                       f"{verification.get('untested', 0)} untested blocks ({verification['status']}). "
                       'Re-read this same disc and inspect the saved logs before another burn.')
    if reasons:
        result.update(result='failed', reason=' '.join(reasons), disc_state=state)
    elif no_verify:
        print("Burn finished: data written; read-back skipped, so neither the data nor the look of the disc "
              "has been checked.", flush=True)
    else:
        print("Burn finished: data written, read-back sample OK. This checks the data, not what the disc looks like.",
              flush=True)
    record("burn_result", **result)
    if reasons:
        raise BurnError(result['reason'])
    return result


def run(args):
    from .works_link import check_work, burn_completed
    check_work(args)
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
    log_file = Path(str(Path(args.iso).resolve()) + '.burn.jsonl')
    log_offset = log_file.stat().st_size if log_file.is_file() else 0
    try:
        erase = getattr(args, 'erase', False)
        expected = disc_identity.expected_for_write(args.drive, erasing=erase) if args.yes_write else None
        result = burn(args.drive, args.iso, media=args.media, speed=args.speed, yes_write=args.yes_write,
             cancel=cancel, no_verify=args.no_verify, keep_open=args.keep_open,
             append=args.append, expect_start=args.expect_start, erase=erase,
             expected_identity=expected, **discid.options(args))
        burn_completed(args, result)
    except (BurnError, disc_identity.DiscChanged) as exc:
        # A failed attempt may still have written data. File that attempt's report too, without
        # borrowing a previous burn from this image's append-only log.
        try:
            with log_file.open('rb') as stream:
                stream.seek(log_offset)
                rows = [json.loads(line) for line in stream.read().splitlines() if line]
            last = next((r for r in reversed(rows) if r.get('type') == 'burn_result'), None)
            if last:
                burn_completed(args, last)
        except (OSError, ValueError) as error:
            print(f'Could not save failed burn record: {error}', file=sys.stderr)
        from .diagnostics import save_failure
        folder = Path(str(args.iso) + '.diagnostics')
        try:
            folder.mkdir(parents=True, exist_ok=True)
            source = Path(str(args.iso) + '.burn.jsonl')
            if source.is_file() and not source.is_symlink() and source.stat().st_size <= 8 * 1024 * 1024:
                (folder / 'burn.log').write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
            save_failure(folder, str(exc), args)
        except OSError as error:
            print(f'Could not save burn diagnostics: {error}', file=sys.stderr)
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
