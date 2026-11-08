"""A local, offline browser disc-art editor and its small file-save bridge.

The browser renders images; this module only serves packaged assets, validates PNG
exports, and prints a command for the existing image workflow. It never accesses a
drive or executes the returned command. No web framework or build step is needed.
"""

from __future__ import annotations

import base64
import binascii
import datetime
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import sys
import tempfile
import threading
import webbrowser

from . import guide, i18n

DISC_DIAMETER_MM = 120.0
GRID_SIZE = 6000
CELL_MM = DISC_DIAMETER_MM / GRID_SIZE
MAX_REQUEST_BYTES = 96 * 1024 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
ASSETS = Path(__file__).with_name("editor_assets")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/editor.css": ("editor.css", "text/css; charset=utf-8"),
    "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
    "/processing.mjs": ("processing.mjs", "text/javascript; charset=utf-8"),
    "/worker.js": ("worker.js", "text/javascript; charset=utf-8"),
}


def _finite(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _json_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def shell_commands(argv: list[str]) -> dict[str, str]:
    """Quote arguments for the three supported shells, including hostile filenames.

    cmd expands %variables% even inside quotes, and !variables! with delayed
    expansion enabled. For those uncommon paths, an ASCII/base64 argument wrapper
    avoids asking the user to change their shell settings. It runs exactly the
    same discprobe arguments, not a command received from the browser.
    """
    if any("\x00" in word or "\r" in word or "\n" in word for word in argv):
        raise ValueError("command arguments may not contain NUL or line breaks")
    powershell = " ".join("'" + word.replace("'", "''") + "'" if i >= 4 else word
                          for i, word in enumerate(argv))
    if any(any(c in word for c in '%!"^') for word in argv):
        payload = base64.b64encode(json.dumps(argv[3:], ensure_ascii=True).encode("ascii")).decode("ascii")
        code = ("import base64,json,runpy,sys;sys.argv=['discprobe']+"
                f"json.loads(base64.b64decode('{payload}'));"
                "runpy.run_module('discprobe',run_name='__main__')")
        cmd = f'python -c "{code}"'
    else:
        cmd = " ".join('"' + word + '"' if i >= 4 else word for i, word in enumerate(argv))
    return {"powershell": powershell, "cmd": cmd, "posix": shlex.join(argv)}


def _slug(value) -> str:
    if not isinstance(value, str):
        raise ValueError("name must be text")
    # Names are labels, never paths. The random directory suffix also avoids
    # Windows device names, collisions, and overwriting an existing artwork.
    return re.sub(r"[^\w .-]+", "-", value, flags=re.UNICODE).strip(" .-")[:64] or "disc"


def _png(value, *, binary: bool):
    """Validate a browser PNG before any export files are created.

    In particular, never silently threshold a grey image submitted as the final
    burn raster. The writer is binary today, so that would lose the user's work.
    """
    from PIL import Image, ImageChops, UnidentifiedImageError
    prefix = "data:image/png;base64,"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("png must be a PNG data URL")
    encoded = value[len(prefix):]
    if len(encoded) > (MAX_PNG_BYTES + 2) // 3 * 4:
        raise ValueError("PNG export is too large")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError("invalid PNG base64") from e
    if len(data) > MAX_PNG_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid or oversized PNG")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "PNG" or im.size != (GRID_SIZE, GRID_SIZE):
                raise ValueError(f"export must be a {GRID_SIZE} x {GRID_SIZE} PNG for the 120 mm canvas")
            if getattr(im, "n_frames", 1) != 1:
                raise ValueError("animated PNG exports are not supported")
            im.load()
            if not binary:
                return im.copy()
            if im.mode == "1" and "transparency" not in im.info:
                return im.copy()
            if im.mode == "L" and "transparency" not in im.info:
                if any(im.histogram()[1:255]):
                    raise ValueError("the final burn PNG must contain only black and white; dither before export")
                return im.convert("1", dither=Image.Dither.NONE)
            rgba = im.convert("RGBA")
            r, g, b, a = rgba.split()
            if a.getextrema() != (255, 255):
                raise ValueError("the final burn PNG must be opaque; composite transparency over the disc background first")
            if (ImageChops.difference(r, g).getextrema() != (0, 0)
                    or ImageChops.difference(r, b).getextrema() != (0, 0)
                    or any(r.histogram()[1:255])):
                raise ValueError("the final burn PNG must contain only black and white; dither before export")
            return r.convert("1", dither=Image.Dither.NONE)
    except (UnidentifiedImageError, SyntaxError, OSError, Image.DecompressionBombError) as e:
        raise ValueError("invalid PNG image") from e


class EditorSession:
    """CLI-owned settings. HTTP callers cannot choose filesystem/geometry paths."""

    def __init__(self, *, media="dvd", geo="latest", correction=None, along_track_frames=0.0,
                 cd_sector="mode2form1", output_dir="art/editor", r_min=None, r_max=56.0, language=None):
        if media not in ("dvd", "cd"):
            raise ValueError("media must be dvd or cd")
        if cd_sector not in ("mode2form1", "mode1"):
            raise ValueError("cd-sector must be mode2form1 or mode1")
        self.media = media
        self.language = language or i18n.active()
        self.minimum_inner = 26.0 if media == "cd" else 24.5
        self.inner = self.minimum_inner if r_min is None else _finite(r_min, "r-min")
        self.outer = _finite(r_max, "r-max")
        self._radii(self.inner, self.outer)
        self.along_track_frames = _finite(along_track_frames, "along-track-frames")
        if media != "cd" and self.along_track_frames:
            raise ValueError("--along-track-frames is for CD")
        self.cd_sector = cd_sector
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.geo_arg = geo
        self.geo_path = None
        self.geometry_status = "missing"
        self.fit = None
        self.warnings = ["The image writer uses a 20 micrometre design grid. This is not a prediction of optical resolution or reflected brightness."]
        self.correction = str(Path(correction).expanduser().resolve()) if correction else None
        self.last_export = None
        self.export_lock = threading.Lock()
        self._geometry()
        if self.correction:
            self._check_correction()
        if media == "cd":
            self.warnings.append("CD needs a measured along-track constant for this drive and burn path; the editor cannot determine it.")

    def _radii(self, inner: float, outer: float) -> None:
        if not self.minimum_inner <= inner < outer <= 58.0:
            raise ValueError(f"radii must satisfy {self.minimum_inner:g} <= r-min < r-max <= 58 mm")

    def _geometry(self) -> None:
        try:
            path = guide.resolve_geo(self.geo_arg, self.media)
        except ValueError:
            self.warnings.append("No measured geometry is selected. You can edit and export now; run geo before using the image command.")
            return
        self.geo_path = str(Path(path).expanduser().resolve())
        try:
            with open(self.geo_path, encoding="utf-8") as f:
                summary = json.load(f)
            fit = summary["fit"]
            if not isinstance(fit, dict) or not all(_finite(fit[k], k) > 0 for k in ("u", "v", "bit_nm_assumed")):
                raise ValueError("invalid geometry numbers")
        except (OSError, ValueError, KeyError, TypeError):
            self.geometry_status = "invalid"
            self.warnings.append("The selected geometry is missing or invalid. Export is available, but no image command will be offered.")
            return
        self.fit = fit
        if fit.get("media", "dvd") != self.media or fit.get("track") == "audio":
            self.geometry_status = "incompatible"
            self.warnings.append("The selected geometry is for another medium or a CD audio track. It cannot be used by the data-track image writer.")
            return
        self.geometry_status = "ready"
        if guide._simulated(summary) or "geo-SIM-" in self.geo_path or summary.get("stopped"):
            self.geometry_status = "invalid"
            self.warnings.append("This geometry is simulated or stopped early. Export is available, but do not burn from this measurement.")
        else:
            blocker = guide.install_blocker(self.geo_path)
            if blocker:
                self.geometry_status = "invalid"
                self.warnings.append("The selected geometry failed the existing measurement-quality checks. Run results or geo before generating a disc image.")

    def _check_correction(self) -> None:
        try:
            with open(self.correction, encoding="utf-8") as f:
                correction = json.load(f)
            lo, hi = correction["radius_valid_mm"]
            if _finite(lo, "correction radius") >= _finite(hi, "correction radius"):
                raise ValueError("invalid correction range")
            coefficients = correction["poly_in_x"]
            if not isinstance(coefficients, list) or not coefficients:
                raise ValueError("empty correction")
            for coefficient in coefficients:
                _finite(coefficient, "correction coefficient")
            if self.fit:
                from . import imagedisc
                if imagedisc.correction_other_run(self.correction, self.fit["u"], self.fit["v"], self.geo_path):
                    raise ValueError("correction belongs to another geometry run")
        except (OSError, ValueError, KeyError, TypeError):
            self.geometry_status = "invalid"
            self.warnings.append("The correction file is invalid or belongs to another geometry. Export is available, but no image command will be offered.")

    def config(self) -> dict:
        return {
            "media": self.media, "discDiameterMm": DISC_DIAMETER_MM, "hubDiameterMm": 15.0,
            "innerRadiusMm": self.inner, "outerRadiusMm": self.outer,
            "minimumInnerRadiusMm": self.minimum_inner, "maximumOuterRadiusMm": 58.0,
            "gridSize": GRID_SIZE, "cellMm": CELL_MM, "language": self.language,
            "workingDirectory": os.getcwd(),
            "outputDirectory": str(self.output_dir), "geometryStatus": self.geometry_status,
            "geometryPath": self.geo_path, "geometryReady": self.geometry_status == "ready",
            "correctionPath": self.correction, "alongTrackFrames": self.along_track_frames,
            "cdSector": self.cd_sector, "warnings": self.warnings,
        }

    def _commands(self, path: Path, outer: float) -> dict[str, str]:
        if self.geometry_status in ("invalid", "incompatible"):
            return {}
        argv = ["python", "-m", "discprobe", "image", "--media", self.media,
                "--geo", self.geo_path or "latest", "--picture", str(path), "--diameter-mm", "120",
                "--r-max", f"{outer:g}", "--output",
                str(Path("iso").resolve() / ("editor-" + path.parent.name + ".iso"))]
        if self.correction:
            argv.extend(["--correction", self.correction])
        if self.media == "cd":
            argv.extend(["--along-track-frames", f"{self.along_track_frames:g}", "--cd-sector", self.cd_sector])
        return shell_commands(argv)

    def export(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("export must be a JSON object")
        if not isinstance(payload.get("finish", False), bool):
            raise ValueError("finish must be true or false")
        name = _slug(payload.get("name", "disc"))
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        encoded_metadata = json.dumps(metadata, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded_metadata) > MAX_METADATA_BYTES:
            raise ValueError("metadata is too large; save the editable project separately")
        if metadata.get("media", self.media) != self.media:
            raise ValueError("the export medium must match this editor session")
        inner = _finite(metadata.get("innerRadiusMm", self.inner), "innerRadiusMm")
        outer = _finite(metadata.get("outerRadiusMm", self.outer), "outerRadiusMm")
        self._radii(inner, outer)
        burn = _png(payload.get("png"), binary=True)
        grey = None
        try:
            grey = _png(payload["grayscalePng"], binary=False) if payload.get("grayscalePng") is not None else None
            with self.export_lock:
                return self._save(name, burn, grey, metadata, inner, outer)
        finally:
            burn.close()
            if grey is not None:
                grey.close()

    def _save(self, name, burn, grey, metadata, inner, outer) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix=name + "-", dir=self.output_dir))
        path = folder / "disc.png"
        grayscale_path = folder / "disc.grayscale.png" if grey is not None else None
        metadata_path = folder / "disc.editor.json"
        created = []
        try:
            for image, target in ((burn, path), (grey, grayscale_path)):
                if image is None:
                    continue
                with target.open("xb") as f:
                    created.append(target)
                    image.save(f, format="PNG")
            commands = self._commands(path, outer)
            command = commands.get("cmd" if sys.platform == "win32" else "posix")
            record = {
                "schema": "discprobe.editor.export/v1",
                "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "media": self.media, "discDiameterMm": DISC_DIAMETER_MM,
                "innerRadiusMm": inner, "outerRadiusMm": outer, "gridSize": GRID_SIZE, "cellMm": CELL_MM,
                "path": str(path), "grayscalePath": str(grayscale_path) if grayscale_path else None,
                "geometryPath": self.geo_path, "geometryStatus": self.geometry_status,
                "correctionPath": self.correction, "alongTrackFrames": self.along_track_frames,
                "cdSector": self.cd_sector, "settings": metadata, "commands": commands,
                "warnings": self.warnings,
            }
            with metadata_path.open("x", encoding="utf-8") as f:
                created.append(metadata_path)
                json.dump(record, f, indent=2, ensure_ascii=False, allow_nan=False)
                f.write("\n")
        except BaseException:
            # Only files in the fresh directory belong to us; never touch older exports.
            for target in created:
                try:
                    target.unlink()
                except OSError:
                    pass
            try:
                folder.rmdir()
            except OSError:
                pass
            raise
        result = {
            "path": str(path), "grayscalePath": str(grayscale_path) if grayscale_path else None,
            "metadataPath": str(metadata_path), "command": command, "commands": commands,
            "ready": self.geometry_status == "ready", "warnings": self.warnings,
        }
        self.last_export = result
        return result


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, session: EditorSession, port=0):
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        self.session = session
        self.token = secrets.token_urlsafe(32)
        self.upload_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), EditorHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.url = self.origin + "/#" + self.token

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(15)
        return sock, address


class EditorHandler(BaseHTTPRequestHandler):
    server_version = "disc-probe-editor"

    def log_message(self, format, *args):
        pass                       # no URL/token/body logging

    def _send(self, code: int, body: bytes, content_type="application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' blob: data:; connect-src 'self'; worker-src 'self'; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _json(self, code: int, value: dict) -> None:
        self._send(code, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))

    def _allowed(self, *, api=False) -> bool:
        if self.headers.get_all("Host", []) != [f"127.0.0.1:{self.server.server_port}"]:
            self._json(403, {"error": "invalid Host"})
            return False
        origins = self.headers.get_all("Origin", [])
        if origins and origins != [self.server.origin]:
            self._json(403, {"error": "cross-origin access is not allowed"})
            return False
        if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
            self._json(403, {"error": "cross-site access is not allowed"})
            return False
        tokens = self.headers.get_all("X-Discprobe-Token", [])
        if api and (len(tokens) != 1 or not hmac.compare_digest(tokens[0].encode("utf-8"), self.server.token.encode("ascii"))):
            self._json(403, {"error": "invalid editor session token; open the URL printed in the terminal"})
            return False
        return True

    def do_GET(self):
        if not self._allowed(api=self.path.startswith("/api/")):
            return
        if self.path == "/api/config":
            self._json(200, self.server.session.config())
        elif self.path in STATIC_FILES:
            filename, mime = STATIC_FILES[self.path]
            try:
                body = (ASSETS / filename).read_bytes()
            except OSError:
                self._json(404, {"error": "editor asset is missing; update the complete disc-probe folder"})
                return
            self._send(200, body, mime)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed(api=True):
            return
        if self.path != "/api/export":
            self._json(404, {"error": "not found"})
            return
        if len(self.headers.get_all("Content-Type", [])) != 1 or self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "export requires application/json"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (self.headers.get("Transfer-Encoding") or len(lengths) != 1
                or len(lengths[0]) > 12 or not lengths[0].isascii() or not lengths[0].isdigit()):
            self._json(411, {"error": "one Content-Length is required"})
            return
        length = int(lengths[0])
        if not 0 < length <= MAX_REQUEST_BYTES:
            self._json(413, {"error": "export request is too large"})
            return
        if not self.server.upload_lock.acquire(blocking=False):
            self._json(409, {"error": "an export is already running; wait for it to finish"})
            return
        try:
            try:
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError("incomplete export request")
                payload = json.loads(data, parse_constant=_json_constant)
                result = self.server.session.export(payload)
            except (ValueError, UnicodeError, RecursionError) as e:
                self._json(400, {"error": str(e)})
                return
            except OSError:
                self._json(500, {"error": "could not save the export; check the output directory and free disk space"})
                return
            self._json(200, result)
            if payload.get("finish", False):
                # shutdown must run outside the serve_forever thread and only after
                # the response has been sent, so the browser keeps the copyable path.
                threading.Thread(target=self.server.shutdown, daemon=True).start()
        finally:
            self.server.upload_lock.release()

    def do_OPTIONS(self):
        self._json(403, {"error": "cross-origin access is not allowed"})


def run(args) -> None:
    session = EditorSession(media=args.media, geo=args.geo, correction=args.correction,
                            along_track_frames=args.along_track_frames, cd_sector=args.cd_sector,
                            output_dir=args.output_dir, r_min=args.r_min, r_max=args.r_max)
    with EditorServer(session, args.port) as server:
        print("Disc artwork editor (local only; no drive is accessed):")
        print(server.url)
        print("Export and continue returns to this terminal. Ctrl+C closes the editor without exporting.")
        for warning in session.warnings:
            print(warning)
        sys.stdout.flush()
        if not args.no_browser:
            try:
                opened = webbrowser.open(server.url)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print("The browser did not open automatically. Copy the local URL above into your browser.")
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            print("Editor closed.")
    if session.last_export:
        result = session.last_export
        print("Artwork saved:")
        print(result["path"])
        if result["command"]:
            print("Next, paste this command in the same terminal:")
            print(result["command"])
        else:
            print("No compatible geometry is selected. Choose a data-disc measurement before making an ISO.")

