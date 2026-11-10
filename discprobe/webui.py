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
from urllib.parse import parse_qs, unquote, urlsplit

from . import guide, i18n, iso9660

ACTIONS = {"info", "timing", "geo", "random", "image", "disexport", "cdprobe", "burn"}
DRIVE_ACTIONS = {"info", "timing", "geo", "burn"}
# Deliberately exclude force/install/replace, raw transport commands and arbitrary flags.
OPTIONS = {
    "info": {},
    "timing": {"speed": "speed", "reps": "count", "period_reads": "count", "max_minutes": "minutes"},
    "geo": {"speed": "speed", "reps": "count", "max_targets": "count", "bd_zones": "count"},
    "random": {"sectors": "sectors", "seed": "seed", "output": "path"},
    "image": {"geo": "geo", "picture": "path", "design": "path", "design_npy": "path", "output": "path",
              "diameter_mm": "diameter", "r_max": "radius", "along_track_frames": "frames",
              "dark": "texture", "light": "texture"},
    "disexport": {"geo": "geo", "sectors": "sectors", "output": "path", "r_min": "radius", "r_max": "radius"},
    "cdprobe": {"sectors": "sectors", "output": "path", "size": "size"},
    "burn": {},
}
DESIGN_BYTES = 6000 * 6000 // 8      # imagedisc.SIZE squared, one bit per cell (checked in the tests)
LIMITS = {"count": (1, 1000), "sectors": (1, 25_000_000), "seed": (0, 2**32 - 1),
          "minutes": (0.1, 120), "diameter": (1, 120), "radius": (1, 58),
          "frames": (-10000, 10000), "size": (64, 8192)}


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
    drive = payload.get("drive")
    if drive is not None and (not isinstance(drive, str) or drive not in [d["id"] for d in drives]):
        raise APIError("unknown drive")
    if action in DRIVE_ACTIONS and not drive:
        raise APIError("drive is required")
    args = payload.get("args", {})
    if not isinstance(args, dict) or set(args) - OPTIONS[action].keys():
        raise APIError("argument is not allowed")
    argv = [sys.executable, "-m", "discprobe", action]
    if action in DRIVE_ACTIONS:
        argv += ["--drive", drive]
    if action in {"timing", "geo", "random", "image", "disexport"}:
        argv += ["--media", media]
    for name, value in args.items():
        if value is None:
            continue
        rule = OPTIONS[action][name]
        if rule in ("path", "geo"):
            value = "latest" if rule == "geo" and value == "latest" else local_path(root, value)
        elif rule == "speed":
            if type(value) is int and 1 <= value <= 65535:
                pass
            elif isinstance(value, str) and re.fullmatch(r"(?:[1-9]|[1-4][0-9]|5[0-6])x", value):
                pass
            else:
                raise APIError("invalid speed")
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
        self.events.touch()
        self.child = None
        self.finished = threading.Event()
        self.exit = None
        self.offset = 0
        self.history = []
        self.progress = None
        self.asks = {}

    def read(self):
        # Only consume complete lines; the child may still be appending one.
        with self.events.open("rb") as stream:
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
                if event["type"] != "answer":
                    self.history.append(event)


class Backend:
    def __init__(self, root=None, *, media="dvd", out="results", runner=Child, drive_provider=None):
        self.root = Path(root or Path.cwd()).resolve()
        self.media = media
        self.out = local_path(self.root, out)
        self.runner = runner
        # Only enumerate device names; no info polling or drive opening on page load.
        self.drive_provider = drive_provider or (lambda: [dict(id=d, name=d, disc=None) for d in guide.optical_drives()])
        self.lock = threading.RLock()
        self.jobs = {}
        self.tokens = {}
        self.closed = False
        self.folder = self.root / ".webui-jobs"

    def state(self):
        drives = self.drive_provider()
        state = guide.guide_state(self.media, self.out, drives=[d["id"] for d in drives])
        state["drives"] = drives
        with self.lock:
            state["jobs"] = [dict(id=j.id, drive=j.drive, exit=j.exit) for j in self.jobs.values()]
        return state

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
        if payload["action"] in {"info", "timing", "geo"}:
            argv += ["--out", self.out]
        with self.lock:
            if self.closed:
                raise APIError("service is closing", 503)
            if drive and any(j.drive == drive and j.exit is None for j in self.jobs.values()):
                raise APIError("drive busy", 409)
            if payload["action"] == "burn":
                token = payload.get("burn_token")
                if not isinstance(token, str) or self.tokens.pop(token, 0) <= time.monotonic():
                    raise APIError("valid burn token required", 403)
                disc = next(d.get("disc") for d in drives if d["id"] == drive)
                if not disc or disc.get("blank") is not True:
                    raise APIError("a verified blank disc is required", 409)
                # This branch contains no burn command. Never pretend a saved report authorizes a write.
                raise APIError("burn is not implemented by this engine", 501)
            if not self.folder.resolve().is_relative_to(self.root):
                raise APIError("job directory must stay inside the workspace")
            self.folder.mkdir(exist_ok=True)
            ident = "j-" + secrets.token_hex(8)
            folder = Path(tempfile.mkdtemp(prefix=ident + "-", dir=self.folder))
            job = Job(ident, drive, folder)
            env = os.environ.copy()
            env.update(DISCPROBE_EVENTS=str(job.events), DISCPROBE_ANSWERS=str(job.answers), DISCPROBE_JOB=ident)
            # Force plain child output; events have their own progress outlet.
            env["DISCPROBE_PLAIN"] = "1"
            self.jobs[ident] = job
            try:
                with (folder / "output.log").open("wb") as output:
                    job.child = self.runner(argv, env=env, cwd=str(self.root), stdout=output)
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
        """Keep a design the page drew (one bit per 20 µm cell, row by row, dark = 1) as image --design-npy reads it."""
        import numpy as np
        from . import imagedisc
        if len(packed) != DESIGN_BYTES:
            raise APIError("a design is %d bytes" % DESIGN_BYTES, 413)
        cells = imagedisc.SIZE
        dark = np.unpackbits(np.frombuffer(packed, np.uint8))[:cells * cells].reshape(cells, cells).astype(bool)
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
            job.read()
            job.exit = code
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
        host = self.headers.get("Host", "")
        if not self.server.token and host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
            raise APIError("invalid Host", 403)
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            raise APIError("cross-origin request refused", 403)
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise APIError("cross-site request refused", 403)
        if self.server.token:
            token = self.headers.get("X-Discprobe-Token", "")
            query = parse_qs(urlsplit(self.path).query)
            token = token or query.get("token", [""])[0]
            if not hmac.compare_digest(token.encode("utf-8"), self.server.token.encode("ascii")):
                raise APIError("invalid session token", 403)

    def do_GET(self):
        try:
            self._allowed()
            path = unquote(urlsplit(self.path).path)
            backend = self.server.backend
            if path == "/api/state":
                self._json(200, backend.state())
            elif path == "/api/burn-token":
                self._json(200, backend.burn_token())
            elif path == "/api/events":
                self._events()
            elif path == "/api/iso":
                self._json(200, backend.iso_file(parse_qs(urlsplit(self.path).query).get("path", [""])[0]))
            elif path.startswith("/api/"):
                raise APIError("not found", 404)
            else:
                root = Path(__file__).with_name("web").resolve()
                target = (root / (path.lstrip("/") or "index.html")).resolve()
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
                self._json(200, self.server.backend.save_design(self._body(DESIGN_BYTES)))
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
            if path == "/api/run":
                result = backend.start(payload)
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


def run(args):
    backend = Backend(media=args.media, out=args.out)
    with Server(backend, args.port, lan=args.lan) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        if server.token:
            url += "?token=" + server.token
        print(url, flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
