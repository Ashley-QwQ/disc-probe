"""Local workflow API. Commands are argv lists; hardware access only follows /api/run.

Events and answers are JSONL files in a private per-job directory. The service never
infers that a saved info report proves the disc currently in a drive is blank.
"""
from __future__ import annotations

import hmac
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, unquote, urlsplit

from . import guide, i18n, iso9660, webui_catalog


_VERSION = None


def version():
    """This copy's release, shown after the folded wordmark: the newest tag of its git checkout
    ("v0.1.2.1"), with "-dev" when there are commits after that tag; empty outside a checkout."""
    global _VERSION
    if _VERSION is None:
        try:
            out = subprocess.run(["git", "describe", "--tags", "--match", "v*"], cwd=Path(__file__).parent,
                                 capture_output=True, text=True, timeout=5)
            tag = out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            tag = ""
        m = re.fullmatch(r"(v[\d.]+)(-\d+-g[0-9a-f]+)?", tag)
        _VERSION = (m.group(1) + ("-dev" if m.group(2) else "")) if m else ""
    return _VERSION

ACTIONS = {"info", "timing", "geo", "random", "image", "disexport", "cdprobe", "burn", "swap", "calibrate"}
DRIVE_ACTIONS = {"info", "timing", "geo", "burn", "swap", "calibrate"}
# Deliberately exclude force/install/replace, raw transport commands and arbitrary flags.
OPTIONS = {
    "info": {},
    "swap": {"minutes": "minutes"},       # read-only: TEST UNIT READY while the disc is changed
    "timing": {"speed": "speed", "reps": "count", "period_reads": "count", "max_minutes": "minutes"},
    "geo": {"speed": "speed", "reps": "count", "max_targets": "count", "bd_zones": "count"},
    "random": {"sectors": "sectors", "seed": "seed", "output": "path"},
    "image": {"geo": "geo", "picture": "path", "design": "path", "design_npy": "path", "output": "path",
              "diameter_mm": "diameter", "r_max": "radius", "along_track_frames": "frames",
              "dark": "texture", "light": "texture"},
    "disexport": {"geo": "geo", "sectors": "sectors", "output": "path", "r_min": "radius", "r_max": "radius"},
    "cdprobe": {"sectors": "sectors", "output": "path", "size": "size"},
    "burn": {"iso": "path", "speed": "burn_speed", "cd_sector": "cd_layout", "no_verify": "flag"},
    # the whole calibration in one job (calibrate.py); with `iso` it burns first, under the burn's rules
    "calibrate": {"iso": "path", "burn_speed": "burn_speed", "speed": "speed", "mid": "mid", "preset": "path",
                  "sectors": "sectors"},
}
DESIGN_BYTES = 6000 * 6000 // 8      # imagedisc.SIZE squared, one bit per cell (checked in the tests)
# a design upload by its length: one bit per cell, at 20, 10 or 5 um (imagedisc.CELL_SIDES)
DESIGN_SIDES = {side * side // 8: side for side in (6000, 12000, 24000)}
LIMITS = {"count": (1, 1000), "sectors": (1, 25_000_000), "seed": (0, 2**32 - 1),
          "minutes": (0.1, 120), "diameter": (1, 120), "radius": (1, 58),
          "frames": (-10000, 10000), "size": (64, 8192)}


# escapes in a job's output: SGR (colour) ones, and the rest (OSC titles and taskbar progress, cursor moves)
SGR = re.compile(r"\x1b\[[0-9;]*m")
NOT_SGR = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-ln-z]|\x1b[()][A-Za-z0-9]|\x1b[=>78]")


class APIError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def local_path(root: Path, value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value:
        raise APIError("invalid path")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root or path.name.startswith("-"):
        raise APIError("path must stay inside the workspace")
    return str(path)


def command(payload, root: Path, drives) -> tuple[list[str], str | None]:
    if not isinstance(payload, dict) or set(payload) - {"action", "drive", "media", "args", "burn_token"}:
        raise APIError("invalid run request")
    action, media = payload.get("action"), payload.get("media", "dvd")
    if not isinstance(action, str) or action not in ACTIONS:
        raise APIError("action is not allowed")
    if media not in ("dvd", "cd", "bd"):
        raise APIError("invalid media")
    if action in ("image", "cdprobe") and media == "bd":
        raise APIError("this action has no Blu-ray path")
    if action == "cdprobe" and media != "cd":
        raise APIError("cdprobe requires cd media")
    if action == "calibrate" and media == "bd":
        raise APIError("this action has no Blu-ray path")
    drive = payload.get("drive")
    if drive is not None and (not isinstance(drive, str) or drive not in [d["id"] for d in drives]):
        raise APIError("unknown drive")
    if action in DRIVE_ACTIONS and not drive:
        raise APIError("drive is required")
    args = payload.get("args", {})
    if not isinstance(args, dict) or set(args) - OPTIONS[action].keys():
        raise APIError("argument is not allowed")
    # -P: the workspace (the child's cwd) is not put in front of the import path, so a checkout of
    # another version there cannot stand in for this one (PYTHONPATH, set in start(), names this copy)
    argv = [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "discprobe", action]
    if action in DRIVE_ACTIONS:
        argv += ["--drive", drive]
    if action in {"timing", "geo", "random", "image", "disexport", "calibrate"}:
        argv += ["--media", media]
    for name, value in args.items():
        if value is None:
            continue
        rule = OPTIONS[action][name]
        if rule == "flag":
            if type(value) is not bool:
                raise APIError("invalid " + name)
            if value:
                argv += ["--" + name.replace("_", "-")]
            continue
        if rule in ("path", "geo"):
            value = "latest" if rule == "geo" and value == "latest" else local_path(root, value)
        elif rule == "cd_layout":
            if value not in ("mode2form1", "mode1"):
                raise APIError("invalid CD sector layout")
        elif rule == "burn_speed":
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 56:
                raise APIError("invalid write speed (multiples of 1x)")
        elif rule == "speed":
            if action == "geo" and value == "keep":
                pass
            elif type(value) is int and 1 <= value <= 65535:
                pass
            elif isinstance(value, str) and re.fullmatch(r"(?:[1-9]|[1-4][0-9]|5[0-6])x", value):
                pass
            else:
                raise APIError("invalid speed")
        elif rule == "mid":
            if not isinstance(value, str) or not re.fullmatch(r"[\x20-\x7e]{1,64}", value):
                raise APIError("invalid " + name)
        elif rule == "texture":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{2}", value):
                raise APIError("invalid " + name)
        else:
            lo, hi = LIMITS[rule]
            integer = rule in ("count", "sectors", "seed", "size")
            if (type(value) not in (int, float) or (integer and type(value) is not int)
                    or not lo <= value <= hi or not math.isfinite(value)):
                raise APIError("invalid " + name)
        argv += ["--" + name.replace("_", "-"), str(value)]
    if action == "disexport" and args.get("r_min") is not None and args.get("r_max") is not None:
        if args["r_min"] >= args["r_max"]:
            raise APIError("r_min must be less than r_max")
    for name in {"image": ("geo",), "disexport": ("geo", "sectors"), "cdprobe": ("sectors",)}.get(action, ()):
        if args.get(name) is None:
            raise APIError(name + " is required")
    if sum(bool(args.get(name)) for name in ("picture", "design", "design_npy")) > 1:
        raise APIError("choose picture or design")
    return argv, drive


class Child:
    """Own one process tree: a Windows job object or a POSIX session."""
    def __init__(self, argv, *, env, cwd, stdout):
        self.lock = threading.Lock()
        self.handle = None
        flags = subprocess.CREATE_NO_WINDOW | 4 if os.name == "nt" else 0  # suspended until owned
        self.process = subprocess.Popen(argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                        stdout=stdout, stderr=subprocess.STDOUT,
                                        creationflags=flags, start_new_session=os.name != "nt")
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k.CreateJobObjectW.restype = wintypes.HANDLE
            k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            class Accounting(ctypes.Structure):
                _fields_ = [(name, ctypes.c_longlong) for name in
                            ("user", "kernel", "period_user", "period_kernel")] + [
                                (name, wintypes.DWORD) for name in
                                ("faults", "total", "active", "terminated")]
            k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                    ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
            self.accounting = Accounting
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel = k
            self.handle = k.CreateJobObjectW(None, None)
            if not self.handle or not k.AssignProcessToJobObject(self.handle, int(self.process._handle)):
                self.process.kill()
                self.process.wait()
                if self.handle:
                    k.CloseHandle(self.handle)
                raise OSError("could not own the child process tree")
            resume = ctypes.WinDLL("ntdll").NtResumeProcess
            resume.argtypes = [wintypes.HANDLE]
            if resume(int(self.process._handle)) != 0:
                self.cancel()
                raise OSError("could not resume the child process")

    def wait(self):
        return self.process.wait()

    def cancel(self):
        with self.lock:
            if os.name == "nt":
                if self.handle:
                    self.kernel.TerminateJobObject(self.handle, 1)
                    # TerminateJobObject is asynchronous. Wait for descendants too:
                    # they can still hold output files after the main process exits.
                    import ctypes
                    counts = self.accounting()
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if not self.kernel.QueryInformationJobObject(
                                self.handle, 1, ctypes.byref(counts), ctypes.sizeof(counts), None):
                            raise OSError("could not query the child process tree")
                        if not counts.active:
                            break
                        time.sleep(0.01)
                    else:
                        raise OSError("child process tree did not stop")
            else:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def close(self):
        # Descendants must not outlive their job, even if its main process has exited.
        self.cancel()
        with self.lock:
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None


class Job:
    def __init__(self, ident, drive, folder):
        self.id, self.drive, self.folder = ident, drive, folder
        self.events = folder / "events.jsonl"
        self.answers = folder / "answers.jsonl"
        self.output = folder / "output.log"
        self.events.touch()
        self.output_offset = 0
        self.levels = {}    # text -> level of a log event, waiting for the same line on stdout
        self.child = None
        self.finished = threading.Event()
        self.exit = None
        self.offset = 0
        self.history = []
        self.action = None
        self.args = {}
        self.media = "dvd"
        self.result = None
        self.before = set()
        self.progress = None
        self.asks = {}

    def read(self):
        # Only consume complete lines; the child may still be appending one. A job folder that is gone
        # (cleaned up by hand) has nothing more to say; it must not stop the event stream for every page.
        try:
            stream = self.events.open("rb")
        except FileNotFoundError:
            return
        with stream:
            stream.seek(self.offset)
            while True:
                line = stream.readline()
                if not line.endswith(b"\n"):
                    break
                self.offset = stream.tell()
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    continue
                event["job"] = self.id
                if event["type"] == "progress":
                    self.progress = event
                elif event["type"] == "ask" and isinstance(event.get("id"), str):
                    self.asks[event["id"]] = event
                elif event["type"] == "answer":
                    self.asks.pop(event.get("id"), None)
                elif event["type"] == "log":
                    # The same line is printed on stdout, which is where the page reads the log from.
                    self.levels[str(event.get("text", "")).strip()] = event.get("level", "info")
                    continue
                self.history.append(event)
        self.read_output()

    def read_output(self):
        """The command-line output, line by line, as log events: the page shows what a terminal would."""
        try:
            stream = self.output.open("rb")
        except OSError:
            return
        with stream:
            stream.seek(self.output_offset)
            while True:
                line = stream.readline()
                if not line.endswith(b"\n"):
                    break
                self.output_offset = stream.tell()
                raw = line.decode("utf-8", "replace").rstrip("\r\n").rsplit("\r", 1)[-1].rstrip()
                # colour codes (SGR) are kept for the terminal page as `ansi`; every other escape (the
                # taskbar's progress, cursor moves) is dropped; `text` is the line as plain words
                coloured = NOT_SGR.sub("", raw)
                text = SGR.sub("", coloured)
                if text.strip():
                    # n keeps two identical lines apart (the page drops events it has already seen)
                    event = dict(type="log", job=self.id, text=text, n=len(self.history),
                                 level=self.levels.pop(text.strip(), "info"))
                    if coloured != text:
                        event["ansi"] = coloured
                    self.history.append(event)


def read_disc_child(root: Path, drive: str) -> dict:
    """`discprobe disc` in a child process (the drive is opened the way every job opens it, never in the
    server): which disc is in the drive, read-only, nothing written."""
    here = str(Path(__file__).resolve().parent.parent)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in (here, env.get("PYTHONPATH")) if p)
    env["DISCPROBE_PLAIN"] = "1"
    argv = [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "discprobe", "disc", "--drive", drive]
    try:
        done = subprocess.run(argv, cwd=str(root), env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=90,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        raise APIError("the drive did not answer in time", 504) from None
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise APIError("could not read the drive: " + (done.stderr or done.stdout).strip()[-300:], 502)


class Backend:
    def __init__(self, root=None, *, media="dvd", out="results", runner=Child, drive_provider=None, disc_reader=None):
        self.root = Path(root or Path.cwd()).resolve()
        self.media = media
        self.out = local_path(self.root, out)
        self.runner = runner
        # Only enumerate device names here; the disc in a drive is read when the page asks (read_disc).
        self.drive_provider = drive_provider or (lambda: [dict(id=d, name=d, disc=None) for d in guide.optical_drives()])
        self.lock = threading.RLock()
        self.jobs = {}
        self.tokens = {}
        # drive -> (expiry, media): a read-only inspection just found a blank disc there
        self.verified_blank = {}
        # drive -> what the last read of its disc found (`discprobe disc`, or an `info` job), with when. Only
        # shown to the page; a burn never relies on it (it needs verified_blank or the provider's own disc).
        self.discs = {}
        self.reading = set()                 # drives being read right now: busy for jobs
        self.disc_reader = disc_reader or (lambda drive: read_disc_child(self.root, drive))
        self.closed = False
        self.folder = self.root / ".webui-jobs"

    def state(self, media=None):
        """The workflow for one disc type. The page asks for the type of the work it has open; the server's
        --media is only the default, so one server serves DVD, CD and BD alike."""
        media = media or self.media
        if media not in ("dvd", "cd", "bd"):
            raise APIError("invalid media")
        drives = self.drive_provider()
        state = guide.guide_state(media, self.out, drives=[d["id"] for d in drives])
        with self.lock:
            state["drives"] = [dict(d, disc=d.get("disc") or self.discs.get(d["id"])) for d in drives]
        with self.lock:
            state["jobs"] = [dict(id=j.id, drive=j.drive, action=j.action, media=j.media, exit=j.exit, result=j.result) for j in self.jobs.values()]
        state["catalogue"] = webui_catalog.catalogue(self.root, self.out)
        state["version"] = version()
        state["platform"] = sys.platform          # which shell the terminal page looks like (win32: PowerShell)
        return state

    def read_disc(self, payload) -> dict:
        """Which disc is in a drive, read now (read-only). The answer is kept for /api/state until the drive's
        disc may have changed (a burn or a swap on it)."""
        drive = payload.get("drive") if isinstance(payload, dict) else None
        if not isinstance(drive, str) or drive not in [d["id"] for d in self.drive_provider()]:
            raise APIError("unknown drive")
        with self.lock:
            if drive in self.reading or any(j.drive == drive and j.exit is None for j in self.jobs.values()):
                raise APIError("drive busy", 409)
            self.reading.add(drive)
        try:
            found = self.disc_reader(drive)
        finally:
            with self.lock:
                self.reading.discard(drive)
        disc = found.get("disc") if isinstance(found, dict) else None
        report = dict(disc or dict(present=False), tray=found.get("tray", "unknown") if isinstance(found, dict) else "unknown",
                      read_at=round(time.time()))
        with self.lock:
            self.discs[drive] = report
        return dict(drive=drive, disc=report)

    def job_state(self, ident):
        with self.lock:
            job = self.get_job(ident)
            job.read()
            return dict(job=ident, action=job.action, media=job.media, exit=job.exit,
                        events=list(job.history), result=job.result)

    def burn_token(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = {t: expiry for t, expiry in self.tokens.items() if expiry > now}
            token = secrets.token_urlsafe(32)
            self.tokens[token] = now + 30
            return dict(token=token, expires_in=30)

    def start(self, payload):
        drives = self.drive_provider()
        argv, drive = command(payload, self.root, drives)
        if payload["action"] in {"info", "timing", "geo", "calibrate"}:
            argv += ["--out", self.out]
        # what writes to a disc: a burn, or a calibration that starts with one
        writes = payload["action"] == "burn" or (payload["action"] == "calibrate" and bool(payload.get("args", {}).get("iso")))
        with self.lock:
            if self.closed:
                raise APIError("service is closing", 503)
            if drive and (drive in self.reading or any(j.drive == drive and j.exit is None for j in self.jobs.values())):
                raise APIError("drive busy", 409)
            if writes:
                token = payload.get("burn_token")
                if not isinstance(token, str) or self.tokens.pop(token, 0) <= time.monotonic():
                    raise APIError("valid burn token required", 403)
                disc = next(d.get("disc") for d in drives if d["id"] == drive)
                fresh = self.verified_blank.get(drive)
                fresh_ok = fresh is not None and fresh[0] > time.monotonic() and fresh[1] == payload.get("media", "dvd")
                if not fresh_ok and (not disc or disc.get("blank") is not True):
                    raise APIError("a verified blank disc is required", 409)
                from . import burner
                if payload.get("media", "dvd") not in ("dvd", "cd"):
                    raise APIError("burn requires dvd or cd media")
                image = payload.get("args", {}).get("iso")
                if not image:
                    raise APIError("burn is not implemented without an ISO; iso is required")
                self.iso_file(image)
                argv += (["--media", payload.get("media", "dvd")] if payload["action"] == "burn" else []) + ["--yes-write"]
            if not self.folder.resolve().is_relative_to(self.root):
                raise APIError("job directory must stay inside the workspace")
            self.folder.mkdir(exist_ok=True)
            ident = "j-" + secrets.token_hex(8)
            folder = Path(tempfile.mkdtemp(prefix=ident + "-", dir=self.folder))
            job = Job(ident, drive, folder)
            job.action, job.media, job.args = payload["action"], payload.get("media", "dvd"), payload.get("args", {})
            job.before = {r.path: result_signature(r) for r in guide.scan(self.out)}
            if payload["action"] == "disexport" and job.args.get("output"):
                Path(local_path(self.root, job.args["output"])).parent.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update(DISCPROBE_EVENTS=str(job.events), DISCPROBE_ANSWERS=str(job.answers), DISCPROBE_JOB=ident)
            # Force plain child output; events have their own progress outlet.
            env["DISCPROBE_PLAIN"] = "1"
            env["PYTHONUNBUFFERED"] = "1"     # each line reaches output.log, and so the page, as it is printed
            env["FORCE_COLOR"] = "3"          # the core's colours (true colour) in its lines, for the page's terminal
            # The child runs `-m discprobe` from the workspace, which may hold another copy of the package (an
            # older checkout without event output). Put this server's own copy first so both run the same code.
            here = str(Path(__file__).resolve().parent.parent)
            env["PYTHONPATH"] = os.pathsep.join(p for p in (here, env.get("PYTHONPATH")) if p)
            self.jobs[ident] = job
            try:
                with (folder / "output.log").open("wb") as output:
                    runner = burner.web_child if writes and self.runner is Child else self.runner
                    job.child = runner(argv, env=env, cwd=str(self.root), stdout=output)
            except Exception:
                del self.jobs[ident]
                raise
            threading.Thread(target=self._watch, args=(job,), daemon=True).start()
            return dict(job=ident)

    def iso_file(self, value: str) -> dict:
        """Size of a finished ISO under iso/, for the page to show; nothing is read from it."""
        path = Path(local_path(self.root, value))
        if path.suffix.lower() != ".iso" or not path.is_relative_to((self.root / "iso").resolve()):
            raise APIError("not an ISO in iso/")
        if not path.is_file() or Path(str(path) + iso9660.UNFINISHED).exists():
            raise APIError("not found", 404)
        size = path.stat().st_size
        return dict(path=path.relative_to(self.root).as_posix(), bytes=size, sectors=size // 2048)

    def save_design(self, packed: bytes) -> dict:
        """Keep a design the page drew (one bit per cell of 20, 10 or 5 µm, row by row, dark = 1) as image
        --design-npy reads it; its length says the cell size."""
        import numpy as np
        cells = DESIGN_SIDES.get(len(packed))
        if cells is None:
            raise APIError("a design is %s bytes" % " or ".join(str(n) for n in DESIGN_SIDES), 413)
        dark = np.unpackbits(np.frombuffer(packed, np.uint8)).reshape(cells, cells).view(bool)
        folder = self.root / "designs"
        if not folder.resolve().is_relative_to(self.root):
            raise APIError("design directory must stay inside the workspace")
        folder.mkdir(exist_ok=True)
        path = folder / ("web-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3) + ".npy")
        np.save(path, dark)
        return dict(design_npy=path.relative_to(self.root).as_posix(), dark_share=round(float(dark.mean()), 4))

    def _watch(self, job):
        code = job.child.wait()
        job.child.close()
        with self.lock:
            # Even a failed write may have changed the disc. Invalidate before publishing
            # completion or interpreting reports, which can themselves be incomplete.
            if job.action in {"burn", "swap", "calibrate"}:
                self.discs.pop(job.drive, None)
                self.verified_blank.pop(job.drive, None)
            job.read()
            job.exit = code
            # info has no engine result event; associate only newly created reports on this job's device.
            candidates = [r for r in guide.scan(self.out) if job.before.get(r.path) != result_signature(r)
                          and r.kind == job.action and r.tag == guide_drive_tag(job.drive)
                          and not r.simulated]
            if candidates:
                run = candidates[0]
                job.result = dict(path=str(Path(run.path).relative_to(self.root)).replace("\\", "/"),
                                  verdict=guide.result_verdict(run, job.media) or "unknown")
                if job.action in {"geo", "timing"}:
                    job.result["measurement"] = webui_catalog.measurement(run)
                if job.action == "info":
                    job.result["disc"] = webui_catalog.disc_report(guide._load(str(Path(run.path) / "info.json")) or {})
                    self.discs[job.drive] = dict(job.result["disc"], tray="ready", read_at=round(time.time()))
                job.history.append(dict(type="result", job=job.id, step=job.action, **job.result))
            elif job.action == "calibrate":
                # what the core found, from its last `calibrated` event: the measured folders, their
                # verdicts and the geometry's points for the page's chart
                done = next((e for e in reversed(job.history) if e.get("type") == "calibrated"), None)
                if done:
                    rel = lambda p: str(Path(p).resolve().relative_to(self.root)).replace("\\", "/") if p else None
                    # the preset as the catalogue names it (relative to the workspace), so the batch links to it
                    result = dict(ok=bool(done.get("ok")), reason=done.get("reason"), disc=done.get("disc"),
                                  preset=rel(done.get("preset")))
                    for kind in ("timing", "geo"):
                        part = done.get(kind) or {}
                        if part.get("path"):
                            run = next((r for r in guide.scan(self.out) if Path(r.path).resolve() == Path(part["path"]).resolve()), None)
                            result[kind] = dict(path=rel(part["path"]), verdict=part.get("verdict"),
                                                measurement=webui_catalog.measurement(run) if run else None)
                    result["verdict"] = (result.get("geo") or {}).get("verdict", "unknown")
                    result["path"] = (result.get("geo") or {}).get("path")
                    job.result = result
                    job.history.append(dict(type="result", job=job.id, step="calibrate", **result))
            elif job.action in {"random", "disexport"} and code == 0:
                output = job.args.get("output")
                if output and Path(local_path(self.root, output)).is_file():
                    job.result = dict(path=output, verdict="unknown")
                    job.history.append(dict(type="result", job=job.id, step=job.action, **job.result))
            job.asks.clear()
            job.history += [dict(type="done", job=job.id, exit=code), dict(type="state")]
            job.finished.set()

    def get_job(self, ident):
        try:
            return self.jobs[ident]
        except KeyError:
            raise APIError("unknown job", 404) from None

    def cancel(self, ident):
        with self.lock:
            job = self.get_job(ident)
            if job.exit is None:
                job.child.cancel()
            return dict(job=ident, cancelled=True)

    def answer(self, ident, payload):
        with self.lock:
            job = self.get_job(ident)
            job.read()
            if (not isinstance(payload, dict) or set(payload) != {"id", "yes"}
                    or type(payload["yes"]) is not bool or not isinstance(payload["id"], str)):
                raise APIError("answer requires id and boolean yes")
            if job.exit is not None or payload["id"] not in job.asks:
                raise APIError("question is no longer pending", 409)
            with job.answers.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload) + "\n")
            job.asks.pop(payload["id"])
            return dict(answered=True)

    def events(self, cursors, reconnect=False):
        with self.lock:
            result = []
            # Poll saved results and the injected inventory only. No SCSI info command
            # runs in an HTTP/background thread.
            files = []
            for root in (Path(self.out), self.root / "iso"):
                if root.is_dir():
                    for path in root.glob("*/*") if root.name != "iso" else root.glob("*"):
                        try:
                            stat = path.stat()
                            files.append((str(path), stat.st_mtime_ns, stat.st_size))
                        except FileNotFoundError:
                            pass
            for path in [self.root / "catalogue.json", *sorted((self.root / "presets").glob("*.json"))]:
                if path.is_file():
                    stat = path.stat()
                    files.append((str(path), stat.st_mtime_ns, stat.st_size))
            fingerprint = (json.dumps(self.drive_provider(), sort_keys=True), sorted(files))
            previous = cursors.get("_state")
            if previous is not None and fingerprint != previous:
                result.append(dict(type="state"))
            cursors["_state"] = fingerprint
            for job in self.jobs.values():
                job.read()
                if reconnect:
                    result += ([job.progress] if job.progress else []) + list(job.asks.values())
                    if job.exit is not None:
                        result.append(dict(type="done", job=job.id, exit=job.exit))
                else:
                    result += job.history[cursors.get(job.id, 0):]
                cursors[job.id] = len(job.history)
            return result

    def close(self):
        with self.lock:
            self.closed = True
            jobs = list(self.jobs.values())
            for job in jobs:
                if job.exit is None:
                    job.child.cancel()
        for job in jobs:
            job.child.wait()
            job.finished.wait(10)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, backend, port=8765, *, lan=False):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("invalid port")
        self.backend = backend
        self.token = secrets.token_urlsafe(32) if lan else None
        super().__init__(("0.0.0.0" if lan else "127.0.0.1", port), Handler)

    def server_close(self):
        self.backend.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = "discprobe-webui"

    def log_message(self, *args):
        pass  # URLs may carry the LAN token for EventSource/static requests.

    def end_headers(self):
        # Share authentication with subresources, redirects and event streams too.
        if getattr(self, "_set_session_cookie", False):
            self.send_header("Set-Cookie", f"discprobe_session={self.server.token}; Path=/; HttpOnly; SameSite=Strict")
        super().end_headers()

    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _allowed(self):
        self._set_session_cookie = False
        host = self.headers.get("Host", "")
        if not self.server.token and host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
            raise APIError("invalid Host", 403)
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            raise APIError("cross-origin request refused", 403)
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise APIError("cross-site request refused", 403)
        if self.server.token:
            query = parse_qs(urlsplit(self.path).query)
            tokens = (self.headers.get("X-Discprobe-Token", ""), query.get("token", [""])[0])
            expected = self.server.token.encode("ascii")
            self._set_session_cookie = any(hmac.compare_digest(token.encode("utf-8"), expected) for token in tokens)
            if not self._set_session_cookie:
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get("Cookie", ""))
                except CookieError:
                    pass
                session = cookie.get("discprobe_session")
                if not session or not hmac.compare_digest(session.value.encode("utf-8"), expected):
                    raise APIError("invalid session token", 403)

    def do_GET(self):
        try:
            self._allowed()
            url = urlsplit(self.path)
            path = unquote(url.path)
            backend = self.server.backend
            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/home/" + ("?" + url.query if url.query else ""))
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            elif path == "/api/state":
                self._json(200, backend.state(parse_qs(urlsplit(self.path).query).get("media", [None])[0]))
            elif path == "/api/greetings":
                # the terminal's greetings, so the page picks by the viewer's own clock (see greetings.py)
                from . import greetings
                self._json(200, dict(first_time=[list(e) for e in greetings.FIRST_TIME],
                                     week=[[list(e) for e in day] for day in greetings.WEEK],
                                     slots="late night 22-05, early 05-09, morning 09-12, afternoon 12-18, evening 18-22",
                                     first_day="Monday"))
            elif path == "/api/catalogue":
                self._json(200, webui_catalog.catalogue(backend.root, backend.out))
            elif re.fullmatch(r"/api/jobs/j-[0-9a-f]+", path):
                self._json(200, backend.job_state(path.rsplit("/", 1)[1]))
            elif path == "/api/burn-token":
                self._json(200, backend.burn_token())
            elif path == "/api/burn-speeds" or re.fullmatch(r"/api/drives/[^/]+/speeds", path):
                from . import burner
                drive = (parse_qs(urlsplit(self.path).query).get("drive", [""])[0]
                         if path == "/api/burn-speeds" else path.split("/")[3])
                if drive not in [d["id"] for d in backend.drive_provider()]:
                    raise APIError("unknown drive", 404)
                with backend.lock:
                    if drive in backend.reading or any(j.drive == drive and j.exit is None for j in backend.jobs.values()):
                        raise APIError("drive busy", 409)
                    try:
                        media = parse_qs(urlsplit(self.path).query).get("media", ["dvd"])[0]
                        if media not in ("dvd", "cd"):
                            raise APIError("invalid media")
                        report = burner.adapter(drive, media).inspect()
                        # A blank disc found by this read-only, user-requested check authorizes a burn
                        # on this drive for two minutes; the burner checks the disc again before writing.
                        if isinstance(report, dict) and report.get("blank") is True:
                            backend.verified_blank[drive] = (time.monotonic() + 120, media)
                        else:
                            backend.verified_blank.pop(drive, None)
                        self._json(200, report)
                    except burner.BurnError as exc:
                        raise APIError(str(exc), 409) from exc
            elif path == "/api/events":
                self._events()
            elif path == "/api/iso":
                self._json(200, backend.iso_file(parse_qs(urlsplit(self.path).query).get("path", [""])[0]))
            elif path == "/api/burn-command":
                # the command a person runs to burn this ISO where the core cannot (a CD on Windows): the core's own
                # words (burner.imapi_cd_command, as guide.burn_steps prints it), never assembled by the page
                import subprocess
                from . import burner
                query = parse_qs(urlsplit(self.path).query)
                drive = query.get("drive", [""])[0]
                if drive not in [d["id"] for d in backend.drive_provider()]:
                    raise APIError("unknown drive", 404)
                if query.get("media", ["cd"])[0] != "cd":
                    raise APIError("only CDs are burned outside the core")
                iso = backend.iso_file(query.get("iso", [""])[0])
                argv = burner.imapi_cd_command(drive, backend.root / iso["path"])
                self._json(200, dict(command=subprocess.list2cmdline(argv), argv=argv))
            elif path.startswith("/api/"):
                raise APIError("not found", 404)
            else:
                root = Path(__file__).with_name("web").resolve()
                relative = path.lstrip("/") + ("index.html" if path.endswith("/") else "")
                target = (root / relative).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    self._send(404, b"Not found\n", "text/plain; charset=utf-8")
                else:
                    self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        except APIError as exc:
            self._json(exc.status, dict(error=i18n.tr(str(exc))))
        except (ConnectionError, TimeoutError):
            pass

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.connection.settimeout(5)
        cursors = {}
        first = True
        while not self.server.backend.closed:
            events = self.server.backend.events(cursors, reconnect=first)
            first = False
            for event in events:
                self.wfile.write(("event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.write(b": heartbeat\n\n")
            self.wfile.flush()
            time.sleep(0.25)

    def _body(self, limit):
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
            raise APIError("one Content-Length required", 411)
        length = int(lengths[0])
        if not 0 < length <= limit:
            raise APIError("invalid request size", 413)
        self.connection.settimeout(30)
        chunks, left = [], length
        while left:
            chunk = self.rfile.read(min(left, 1 << 20))
            if not chunk:
                raise APIError("request body ended early")
            chunks.append(chunk)
            left -= len(chunk)
        return b"".join(chunks)

    def do_POST(self):
        try:
            self._allowed()
            if urlsplit(self.path).path == "/api/design":
                if self.headers.get_content_type() != "application/octet-stream":
                    raise APIError("application/octet-stream required", 415)
                self._json(200, self.server.backend.save_design(self._body(max(DESIGN_SIDES))))
                return
            if self.headers.get_content_type() != "application/json":
                raise APIError("application/json required", 415)
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
                raise APIError("one Content-Length required", 411)
            length = int(lengths[0])
            if not 0 < length <= 65536:
                raise APIError("invalid request size", 413)
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            backend = self.server.backend
            if path == "/api/catalogue":
                with backend.lock:
                    result = webui_catalog.save_entry(backend.root, backend.out, payload)
            elif path == "/api/run":
                result = backend.start(payload)
            elif path == "/api/disc":
                result = backend.read_disc(payload)
            else:
                match = re.fullmatch(r"/api/jobs/(j-[0-9a-f]+)/(?P<action>cancel|answer)", path)
                if not match:
                    raise APIError("not found", 404)
                result = backend.cancel(match[1]) if match["action"] == "cancel" else backend.answer(match[1], payload)
            self._json(200, result)
        except APIError as exc:
            self._json(exc.status, dict(error=i18n.tr(str(exc))))
        except (ValueError, UnicodeError, RecursionError):
            self._json(400, dict(error=i18n.tr("invalid JSON request")))
        except OSError:
            self._json(500, dict(error=i18n.tr("job I/O failed")))


def result_signature(run):
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(Path(run.path).glob("*.json")))


def guide_drive_tag(drive):
    # Mirrors _outdir's device tag; never opens the device.
    return (drive or "").replace(":", "")


def run(args):
    backend = Backend(media=args.media, out=args.out)
    with Server(backend, args.port, lan=args.lan) as server:
        url = f"http://127.0.0.1:{server.server_port}/home/"
        if server.token:
            url += "?token=" + server.token
        print(url, flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
