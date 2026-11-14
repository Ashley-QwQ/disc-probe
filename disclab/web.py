"""Development web launcher and photo uploader for the standalone Disc Lab package."""
from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .lab import Lab

FORBIDDEN_PORTS = frozenset({8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879})
PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".heic": "image/heic", ".heif": "image/heic", ".webp": "image/webp"}


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535 or port in FORBIDDEN_PORTS:
        raise argparse.ArgumentTypeError(f"port {port} is forbidden or outside 1..65535")
    return port


def serve(lab: Lab, port=8853, media="dvd", lan=False):
    from .__main__ import lab_env

    port = port_number(port)
    # The page's workspace is its working directory: run it inside the lab, so results/, iso/ and photos stay
    # there. --lan (the product's default, token-guarded) is needed for the phone link.
    argv = [sys.executable, "-B", "-m", "discprobe", "webui", *([] if lan else ["--local-only"]),
            "--port", str(port), "--out", "results", "--media", media]
    print(f"http://127.0.0.1:{port}/home/", flush=True)
    lab.step("web", status="started", paths=[str(lab.root / "results")], url=f"http://127.0.0.1:{port}/home/")
    child = subprocess.Popen(argv, cwd=lab.root, env=lab_env(lab), stdout=sys.stdout, stderr=sys.stderr,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    # Windows background launchers receive CTRL_BREAK (SIGBREAK), rather than SIGINT.
    previous_break = signal.signal(signal.SIGBREAK, signal.default_int_handler) if os.name == "nt" else None
    try:
        try:
            while True:
                try:
                    # Bounded waits let Windows dispatch console signals while the child serves.
                    return child.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
        except KeyboardInterrupt:
            if child.poll() is None:
                child.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)
            # A requested stop is successful even when Windows reports its console-control exit status.
            return 0
    finally:
        try:
            if child.poll() is None:
                child.kill()
                child.wait()
        finally:
            if os.name == "nt":
                signal.signal(signal.SIGBREAK, previous_break)
            lab.step("web", status="stopped")


def upload(url, run, photos, *, details=None):
    """Use the phone's raw-body upload protocol, then poll as the computer page."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("--url must be the computer page's http(s) URL")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    desk_headers = {}
    session = parse_qs(parsed.query).get("token", [None])[0]
    if session:
        desk_headers["X-Discprobe-Token"] = session
    paths = [Path(p) for p in photos]
    for path in paths:
        if path.suffix.lower() not in PHOTO_TYPES:
            raise ValueError(f"unsupported photo type: {path}")
        if not path.is_file():
            raise ValueError(f"photo not found: {path}")
    desk = build_opener(HTTPCookieProcessor(CookieJar()))
    phone = build_opener(HTTPCookieProcessor(CookieJar()))
    query = "?run=" + quote(run, safe="")
    with desk.open(Request(origin + "/api/phone-link" + query, headers=desk_headers), timeout=30) as reply:
        link = json.load(reply).get("url")
    if not link:
        raise ValueError("server returned no phone link (--local-only disables phone tokens)")
    phone_path = urlsplit(link).path
    if not phone_path.startswith("/phone/") or not phone_path.removeprefix("/phone/"):
        raise ValueError("server returned an invalid phone link")
    token = phone_path.removeprefix("/phone/")
    # Keep the supplied computer origin: a LAN address in the link need not be reachable here.
    with phone.open(origin + phone_path, timeout=30) as reply:
        reply.read()
    failed = False
    replies = details if details is not None else []
    for path in paths:
        headers = {"X-Photo-Token": token, "Content-Type": PHOTO_TYPES[path.suffix.lower()],
                   "X-Filename": quote(path.name, safe="-_.!~*'()")}
        request = Request(origin + "/api/photos" + query, data=path.read_bytes(), headers=headers, method="POST")
        try:
            reply = phone.open(request, timeout=120)
        except HTTPError as exc:
            reply = exc
            failed = True
        with reply:
            body = reply.read().decode('utf-8')
            replies.append(dict(path=str(path.resolve()), status=reply.code, body=body))
            print(f"{path.name}: HTTP {reply.code} {body}", flush=True)
    with desk.open(Request(origin + "/api/photos" + query, headers=desk_headers), timeout=30) as reply:
        body = reply.read().decode("utf-8")
        replies.append(dict(listing=json.loads(body)))
        print("Computer photos: " + body, flush=True)
    return 1 if failed else 0


def _upload_command(args):
    replies = []
    try:
        code = upload(args.url, args.run, args.photos, details=replies)
    except (ValueError, OSError, URLError) as exc:
        raise SystemExit(str(exc)) from exc
    return dict(replies=replies, run=args.run, paths=[str(Path(p).resolve()) for p in args.photos], exit_code=code)

def add_parser(sub):
    parser = sub.add_parser("web", help="serve disc-probe's unchanged page against a lab (development only)")
    parser.add_argument("--lab", required=True)
    parser.add_argument("--port", type=port_number, default=8853)
    parser.add_argument("--media", choices=("dvd", "cd", "bd"), default="dvd")
    parser.add_argument("--lan", action="store_true",
                        help="listen on the LAN like the product does (token-guarded), so phone links work")
    parser.set_defaults(func=lambda a: dict(exit_code=serve(Lab(a.lab), a.port, a.media, a.lan),
                                          url=f"http://127.0.0.1:{a.port}/home/",
                                          paths=[str(Lab(a.lab).root / "results")]))

    parser = sub.add_parser("upload", help="send lab photos using the phone upload protocol")
    parser.add_argument("--url", required=True, help="computer page URL, including its session token if needed")
    parser.add_argument("--lab", help="optional lab whose progress should record this upload")
    parser.add_argument("--run", required=True)
    parser.add_argument("--photos", nargs="+", required=True)
    parser.set_defaults(func=_upload_command)
