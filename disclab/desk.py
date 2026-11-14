"""The Lab's desk page (`disclab desk`) and the drive settings it needs (`disclab drive`).

The page is a translator, like disc-probe's own: every button becomes one `python -m disclab <command> --json`
process, and everything it shows comes from those replies (mostly `status`). Closing the page stops nothing;
the lab folder's state.json is the only memory. The server adds no state of its own beyond which lab folder it
is pointed at and the jobs it is running.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .lab import Lab, atomic_json

WEB = Path(__file__).parent / "web"
# What the page may run. Each is a disclab subcommand; --lab and --json are added here, never by the page.
ALLOWED = {"status", "step", "swap", "tray", "drive", "photos", "score", "faults", "box"}
LONG = {"step", "photos", "faults", "score", "box"}
FAULT_KINDS = ("read_error", "spindle_unsteady", "capacity_misreport", "burn_interrupt")


# ------------------------------------------------------------------ disclab drive

def cmd_drive(a):
    """Reader profile and injected faults of the lab's virtual drive."""
    lab = Lab(a.lab)
    from .box import READERS
    from .scenario import load_scenario
    with lab.locked_state() as st:
        name = a.drive or next(iter(st["drives"]))
        d = st["drives"].setdefault(name, dict(reader="gh70n", tray=None, open=False))
        if a.reader:
            if a.reader not in READERS:
                raise SystemExit("读盘配置只能是 " + "、".join(READERS) + " / reader must be one of " + ", ".join(READERS))
            d["reader"] = a.reader
            lab.event(st, "tray", drive=name, disc=d.get("tray"), open=d.get("open", False), reader=a.reader)
    answers = lab.answers()
    faults = list(answers.get("faults", []))
    if a.clear:
        faults = [f for f in faults if a.clear != "all" and f["id"] != a.clear]
    if a.fault:
        kind, _, params = a.fault.partition(":")
        try:
            params = json.loads(params) if params else {}
        except json.JSONDecodeError as exc:
            raise SystemExit(f"故障参数不是 JSON：{exc} / fault params must be JSON") from None
        fid = a.id or f"{kind.replace('_', '-')}-{len(faults) + 1}"
        faults.append(dict(id=fid, kind=kind, params=params))
    if a.fault or a.clear:
        box = lab.box()
        probe = dict(version=1, discs=dict(media=box["media"], count=box["count"], batch=box["batch"]), faults=faults)
        with tempfile.TemporaryDirectory(dir=lab.root) as tmp:
            path = Path(tmp) / "faults.json"
            path.write_text(json.dumps(probe), encoding="utf-8")
            try:
                faults = load_scenario(path)["faults"]
            except (ValueError, KeyError, TypeError) as exc:
                raise SystemExit(f"故障设置不对：{exc} / invalid fault: {exc}") from None
        answers["faults"] = faults
        atomic_json(lab.answers_path, answers)
        lab.step("drive_faults", status="ok", faults=[f["id"] for f in faults], paths=[str(lab.answers_path)])
    st = lab.state()
    return dict(drive=name, reader=st["drives"][name].get("reader"), faults=faults, kinds=list(FAULT_KINDS),
                readers=sorted(READERS))


# ------------------------------------------------------------------ jobs

class Jobs:
    """One long command at a time (a drive does one thing at a time); quick reads run alongside."""

    def __init__(self):
        self.jobs, self.lock = {}, threading.Lock()
        self.busy = None

    def start(self, argv, lab_root):
        with self.lock:
            if self.busy and self.jobs[self.busy]["state"] == "running":
                raise RuntimeError("光驱正忙：" + " ".join(self.jobs[self.busy]["argv"]))
            jid = uuid.uuid4().hex[:10]
            job = dict(id=jid, argv=argv, state="running", log="", result=None, t0=time.time(), t1=None)
            self.jobs[jid] = job
            self.busy = jid
        threading.Thread(target=self._run, args=(job, lab_root), daemon=True).start()
        return job

    def _run(self, job, lab_root):
        argv = [sys.executable, "-B", "-m", "disclab", *job["argv"], "--lab", str(lab_root), "--json"]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        root = Path(__file__).resolve().parent.parent
        proc = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        job["pid"] = proc.pid

        def pump():
            for line in proc.stderr:
                job["log"] = (job["log"] + line)[-20000:]
        t = threading.Thread(target=pump, daemon=True)
        t.start()
        out = proc.stdout.read()
        proc.wait()
        t.join(timeout=5)
        try:
            job["result"] = json.loads(out.strip().splitlines()[-1]) if out.strip() else None
        except (json.JSONDecodeError, IndexError):
            job["result"] = dict(status="error", errors=[dict(type="Output", message=out[-2000:])])
        job["state"] = "done" if job["result"] and job["result"].get("status") == "ok" else "failed"
        job["t1"] = time.time()

    def view(self, jid):
        job = self.jobs.get(jid)
        if not job:
            return None
        return {k: job[k] for k in ("id", "argv", "state", "log", "result", "t0", "t1")}


def run_quick(argv, lab_root):
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    res = subprocess.run([sys.executable, "-B", "-m", "disclab", *argv, "--lab", str(lab_root), "--json"], cwd=root,
                         env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=120)
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return dict(status="error", errors=[dict(type="Output", message=(res.stdout + res.stderr)[-2000:])])


# ------------------------------------------------------------------ server

class Desk:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.jobs = Jobs()
        self.thumbs = {}

    def switch(self, root):
        root = Path(root).resolve()
        if root.parent != self.lab.root.parent:
            raise ValueError("只能换到同一个文件夹里的实验盒")
        self.lab = Lab(root)

    def new_lab_root(self):
        base = self.lab.root
        stem = base.name.rsplit("-", 1)[0] if base.name.rsplit("-", 1)[-1].isdigit() else base.name
        for n in range(2, 1000):
            cand = base.parent / f"{stem}-{n}"
            if not cand.exists():
                return cand
        raise ValueError("too many labs")


def handler_for(desk: Desk):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if not isinstance(body, (bytes, bytearray)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def do_GET(self):
            url = urlsplit(self.path)
            q = parse_qs(url.query)
            if url.path in ("/", "/index.html"):
                return self.static("index.html")
            if url.path == "/api/status":
                return self.send(200, run_quick(["status"], desk.lab.root) | dict(busy=self.busy()))
            if url.path.startswith("/api/job/"):
                job = desk.jobs.view(url.path.rsplit("/", 1)[-1])
                return self.send(200 if job else 404, job or dict(error="no such job"))
            if url.path == "/api/file":
                return self.file(q.get("path", [""])[0], int(q.get("w", ["0"])[0] or 0))
            if url.path == "/api/labs":
                parent = desk.lab.root.parent
                labs = sorted(p.name for p in parent.iterdir() if (p / "box.json").exists())
                return self.send(200, dict(current=desk.lab.root.name, labs=labs, folder=str(parent)))
            return self.static(url.path.lstrip("/"))

        def busy(self):
            jid = desk.jobs.busy
            job = desk.jobs.view(jid) if jid else None
            return job if job and job["state"] == "running" else None

        def static(self, rel):
            path = (WEB / rel).resolve()
            if not path.is_relative_to(WEB.resolve()) or not path.is_file():
                return self.send(404, dict(error="not found"))
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix in (".js", ".mjs"):
                ctype = "text/javascript"
            if ctype.startswith("text/"):
                ctype += "; charset=utf-8"
            self.send(200, path.read_bytes(), ctype)

        def file(self, raw, width):
            path = Path(raw).resolve()
            if not path.is_relative_to(desk.lab.root) or not path.is_file():
                return self.send(404, dict(error="not in this lab"))
            if width and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                key = (str(path), path.stat().st_mtime, width)
                if key not in desk.thumbs:
                    from io import BytesIO
                    from PIL import Image
                    im = Image.open(path)
                    im.thumbnail((width, width * 4))
                    buf = BytesIO()
                    im.convert("RGB").save(buf, "JPEG", quality=85)
                    desk.thumbs[key] = buf.getvalue()
                return self.send(200, desk.thumbs[key], "image/jpeg")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send(200, path.read_bytes(), ctype)

        def do_POST(self):
            url = urlsplit(self.path)
            try:
                if url.path == "/api/run":
                    req = json.loads(self.body() or b"{}")
                    argv = [str(x) for x in req.get("argv", [])]
                    if not argv or argv[0] not in ALLOWED or any(x in ("--lab", "--json") for x in argv):
                        return self.send(400, dict(error="not allowed: " + " ".join(argv)))
                    if argv[0] == "box":
                        root = desk.new_lab_root()
                        job = desk.jobs.start(argv, root)
                        job["new_lab"] = str(root)
                        threading.Thread(target=self.adopt, args=(job, root), daemon=True).start()
                        return self.send(200, dict(job=job["id"], lab=str(root)))
                    if argv[0] in LONG:
                        job = desk.jobs.start(argv, desk.lab.root)
                        return self.send(200, dict(job=job["id"]))
                    return self.send(200, run_quick(argv, desk.lab.root))
                if url.path == "/api/lab":
                    desk.switch(desk.lab.root.parent / json.loads(self.body())["name"])
                    return self.send(200, dict(lab=str(desk.lab.root)))
                if url.path == "/api/picture":
                    name = Path(self.headers.get("X-Filename") or "picture.png").name
                    if Path(name).suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".pgm"):
                        return self.send(400, dict(error="不是图片"))
                    dest = desk.lab.root / "designs" / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(self.body())
                    return self.send(200, dict(path=str(dest)))
            except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                return self.send(409, dict(error=str(exc)))
            return self.send(404, dict(error="not found"))

        def adopt(self, job, root):
            while job["state"] == "running":
                time.sleep(0.2)
            if job["state"] == "done" and (root / "box.json").exists():
                desk.lab = Lab(root)
                run_quick(["swap"], root)
    return H


def serve(lab: Lab, port: int):
    from .web import port_number
    port = port_number(port)
    if not lab.box_path.exists():
        raise SystemExit("这里还没有实验盒。先建一箩：python -m disclab box --lab LAB --count 3")
    desk = Desk(lab)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler_for(desk))
    url = f"http://127.0.0.1:{port}/"
    print(url, flush=True)
    lab.step("desk", status="started", url=url, paths=[str(lab.root)])
    # Windows background launchers stop with CTRL_BREAK (SIGBREAK): treat it as Ctrl+C, as `web` does
    previous = signal.signal(signal.SIGBREAK, signal.default_int_handler) if os.name == "nt" else None
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if os.name == "nt":
            signal.signal(signal.SIGBREAK, previous)
        httpd.server_close()
        lab.step("desk", status="stopped", paths=[str(lab.root)])
    return dict(url=url, exit_code=0, paths=[str(desk.lab.root)])


def add_parser(sub):
    p = sub.add_parser("desk", help="the Lab's desk page: disc basket, burner and phone, over the --json commands")
    p.add_argument("--lab", required=True)
    p.add_argument("--port", type=int, default=8857)
    p.set_defaults(func=lambda a: serve(Lab(a.lab), a.port))

    p = sub.add_parser("drive", help="the virtual drive's reader profile and injected faults")
    p.add_argument("--lab", required=True)
    p.add_argument("--drive")
    p.add_argument("--reader", help="reader profile: gh70n, slim-clv, nofua, noisy")
    p.add_argument("--fault", help="KIND or KIND:{json params}, e.g. read_error:{\"r_mm\":[40,41]}")
    p.add_argument("--id", help="id for the new fault")
    p.add_argument("--clear", help="remove a fault by id, or 'all'")
    p.set_defaults(func=cmd_drive)
