"""Offline tests of the browser editor's local bridge; no optical drive is opened.

Run alone with ``python -m discprobe.editor_selftest`` or from the main selftest.
"""

from __future__ import annotations

import base64
import http.client
import io
import json
from pathlib import Path
import re
import shlex
import tempfile
import threading
from unittest import mock

from . import webeditor as editor


def _data_url(image) -> str:
    data = io.BytesIO()
    image.save(data, format="PNG")
    return "data:image/png;base64," + base64.b64encode(data.getvalue()).decode("ascii")


def _geometry(folder, *, media="dvd", **extra) -> Path:
    path = Path(folder) / "measured geometry.json"
    fit = dict(u=180045.0, v=5.55, bit_nm_assumed=133.3, media=media,
               chi2_per_dof=1.0, angle_sigma_measured_span_deg=0.1)
    fit.update(extra)
    path.write_text(json.dumps({"fit": fit}), encoding="utf-8")
    return path


def _refuses(c, func, message):
    try:
        func()
    except ValueError:
        c.check(True, message)
    else:
        c.check(False, message)


def _validation(c, Image):
    print("editor PNG and metadata validation")
    # Small images exercise pixel formats without repeatedly allocating a full
    # 6000-square canvas. The HTTP round trip below uses the real export size.
    with mock.patch.object(editor, "GRID_SIZE", 8):
        for mode, colour in (("1", 1), ("L", 255), ("RGB", (0, 0, 0)), ("RGBA", (255, 255, 255, 255))):
            with Image.new(mode, (8, 8), colour) as image:
                with editor._png(_data_url(image), binary=True) as parsed:
                    c.check(parsed.mode == "1" and parsed.size == (8, 8), f"opaque binary {mode} is accepted without changing levels")
        for mode, colour in (("L", 100), ("RGB", (0, 0, 255)), ("RGBA", (0, 0, 0, 0))):
            with Image.new(mode, (8, 8), colour) as image:
                _refuses(c, lambda: editor._png(_data_url(image), binary=True), f"non-binary or transparent {mode} is refused")
        for mode in ("1", "L"):
            with Image.new(mode, (8, 8), 0) as image:
                image.info["transparency"] = 0
                _refuses(c, lambda: editor._png(_data_url(image), binary=True), f"PNG tRNS transparency in {mode} is also refused")
        with Image.new("L", (8, 8), 100) as image:
            with editor._png(_data_url(image), binary=False) as parsed:
                c.check(parsed.getpixel((0, 0)) == 100, "editable grey export is not thresholded")
        with Image.new("1", (7, 8), 1) as image:
            _refuses(c, lambda: editor._png(_data_url(image), binary=True), "wrong canvas dimensions are refused")
        _refuses(c, lambda: editor._png("data:image/png;base64,!!!", binary=True), "invalid PNG base64 is refused")
        _refuses(c, lambda: editor._png("data:image/jpeg;base64,AAAA", binary=True), "other data URL formats are refused")
        with Image.new("1", (8, 8), 1) as image, tempfile.TemporaryDirectory() as d:
            session = editor.EditorSession(output_dir=d)
            png = _data_url(image)
            for payload in ({"png": png, "metadata": {"outerRadiusMm": float("nan")}},
                            {"png": png, "metadata": {"innerRadiusMm": 1}},
                            {"png": png, "metadata": {"media": "cd"}},
                            {"png": png, "finish": "yes"},
                            {"png": png, "metadata": {"source": "x" * editor.MAX_METADATA_BYTES}}):
                _refuses(c, lambda: session.export(payload), "invalid export metadata is refused before writing")
            c.check(not list(Path(d).iterdir()), "rejected exports leave no files")
            with mock.patch("PIL.Image.Image.save", side_effect=OSError("disk full")):
                try:
                    session.export({"png": png})
                except OSError:
                    pass
                else:
                    c.check(False, "a failed write reports failure")
            c.check(not list(Path(d).iterdir()), "a failed write removes only its new partial export")


def _geometry_and_commands(c):
    print("editor geometry and copyable commands")
    with tempfile.TemporaryDirectory() as d:
        geo = _geometry(d)
        correction = Path(d) / "corrected angle.json"
        correction.write_text(json.dumps({"radius_valid_mm": [25, 56], "poly_in_x": [0]}), encoding="utf-8")
        session = editor.EditorSession(geo=str(geo), correction=str(correction), output_dir=d)
        config = session.config()
        c.check(config["geometryReady"] and config["geometryPath"] == str(geo.resolve()), "an existing geometry is pinned to its absolute path")
        c.check(config["discDiameterMm"] == 120 and config["gridSize"] == 6000 and config["cellMm"] == 0.02,
                "physical canvas and writer grid are explicit")
        path = Path(d) / "export with spaces" / "disc.png"
        argv = shlex.split(session._commands(path, 55)["posix"])
        c.check(argv[argv.index("--picture") + 1] == str(path)
                and argv[argv.index("--diameter-mm") + 1] == "120"
                and argv[argv.index("--correction") + 1] == str(correction)
                and argv[argv.index("--r-max") + 1] == "55", "handoff retains physical scale, picture path, correction, and drawing radius")
        c.check(Path(argv[argv.index("--output") + 1]).parent == Path("iso").resolve(), "generated ISOs remain discoverable by guide")
        _geometry(d, media="cd")
        cd = editor.EditorSession(media="cd", geo=str(geo), along_track_frames=-100, cd_sector="mode1", output_dir=d)
        argv = shlex.split(cd._commands(path, 55)["posix"])
        c.check(cd.config()["innerRadiusMm"] == 26 and argv[argv.index("--along-track-frames") + 1] == "-100"
                and argv[argv.index("--cd-sector") + 1] == "mode1", "CD safety margin, signed along-track constant and sector layout survive handoff")
        other = editor.EditorSession(geo=str(geo), output_dir=d)
        c.check(other.geometry_status == "incompatible" and not other._commands(path, 56), "a different medium is never offered as a burn command")
        _geometry(d, media="cd", track="audio")
        audio = editor.EditorSession(media="cd", geo=str(geo), output_dir=d)
        c.check(audio.geometry_status == "incompatible" and not audio._commands(path, 56), "CD audio-track geometry is not passed to the data-track writer")
        _geometry(d, u=float("nan"))
        invalid = editor.EditorSession(geo=str(geo), output_dir=d)
        c.check(invalid.geometry_status == "invalid" and not invalid._commands(path, 56), "non-finite geometry is not usable")
        geo.write_text(json.dumps({"fit": dict(u=1, v=1, bit_nm_assumed=133.3), "simulated": True}), encoding="utf-8")
        simulated = editor.EditorSession(geo=str(geo), output_dir=d)
        c.check(not simulated._commands(path, 56), "simulated geometry does not yield a ready burn command")
    for options in ({"r_max": 60}, {"media": "cd", "r_min": 25}, {"along_track_frames": 206}, {"r_min": float("inf")}):
        _refuses(c, lambda: editor.EditorSession(**options), "unsafe or non-finite editor dimensions are refused")
    args = ["python", "-m", "discprobe", "image", "--picture", "C:\\A%PATH%!\\my 'picture.png", "--geo", "latest"]
    quoted = editor.shell_commands(args)
    c.check(shlex.split(quoted["posix"]) == args and "''picture" in quoted["powershell"], "POSIX and PowerShell filenames are quoted, not executed")
    encoded = re.search(r"b64decode\('([^']+)'\)", quoted["cmd"]).group(1)
    c.check(json.loads(base64.b64decode(encoded)) == args[3:] and "%PATH%" not in quoted["cmd"], "cmd metacharacters use lossless encoded arguments")
    _refuses(c, lambda: editor.shell_commands(args + ["bad\ncommand"]), "line breaks in command arguments are refused")


def _http(c, Image):
    print("editor local HTTP bridge")
    with tempfile.TemporaryDirectory() as d:
        geo = _geometry(d)
        export_dir = Path(d) / "output exports"
        session = editor.EditorSession(geo=str(geo), output_dir=str(export_dir))
        with editor.EditorServer(session) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            thread.start()

            def request(method, path, body=None, headers=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=8)
                values = {"X-Discprobe-Token": server.token, "Origin": server.origin}
                if headers:
                    values.update(headers)
                connection.request(method, path, body, values)
                response = connection.getresponse()
                result = response.status, response.read(), dict(response.getheaders())
                connection.close()
                return result

            try:
                status, data, headers = request("GET", "/api/config")
                c.check(status == 200 and json.loads(data)["media"] == "dvd", "authenticated config is available")
                c.check(server.server_address[0] == "127.0.0.1" and "#" + server.token in server.url, "service binds loopback and keeps token in URL fragment")
                c.check(headers["Cache-Control"] == "no-store" and "frame-ancestors 'none'" in headers["Content-Security-Policy"], "responses carry cache and embedding protections")
                for route, (filename, mime) in editor.STATIC_FILES.items():
                    code, asset, response_headers = request("GET", route)
                    c.check(code == 200 and asset == (editor.ASSETS / filename).read_bytes()
                            and response_headers["Content-Type"] == mime
                            and response_headers["Cache-Control"] == "no-store",
                            f"packaged {filename} is served intact with its module type and no stale cache")
                for values in ({"X-Discprobe-Token": "wrong"}, {"X-Discprobe-Token": "é"},
                               {"Origin": "http://example.org"}, {"Host": "evil.example"},
                               {"Sec-Fetch-Site": "cross-site"}):
                    c.check(request("GET", "/api/config", headers=values)[0] == 403, "foreign host, origin, site or token is refused")
                c.check(request("GET", "/../../README.md")[0] == 404, "static serving cannot traverse paths")
                c.check(request("GET", "/api/config?path=/etc/passwd")[0] == 404, "there is no arbitrary file-read endpoint")
                c.check(request("POST", "/api/export", "{}")[0] == 415, "exports require JSON content type")
                json_headers = {"Content-Type": "application/json"}
                c.check(request("POST", "/api/export", "{bad", json_headers)[0] == 400, "malformed JSON is rejected")
                c.check(request("POST", "/api/export", '{"png":"bad"}', json_headers)[0] == 400, "malformed images are rejected")
                c.check(request("POST", "/api/export", "", {**json_headers, "Content-Length": str(editor.MAX_REQUEST_BYTES + 1)})[0] == 413,
                        "oversized body is rejected before reading it")
                c.check(request("POST", "/api/export", "", {**json_headers, "Transfer-Encoding": "chunked"})[0] == 411,
                        "ambiguous transfer framing is rejected")
                with server.upload_lock:
                    c.check(request("POST", "/api/export", "{}", json_headers)[0] == 409,
                            "simultaneous exports are refused before allocating multiple full-size images")
                with Image.new("1", (6000, 6000), 1) as image:
                    image.paste(0, (1000, 2000, 1010, 2020))
                    png = _data_url(image)
                with Image.new("L", (6000, 6000), 123) as image:
                    grey = _data_url(image)
                body = json.dumps({"name": "../outside\\my art", "png": png, "grayscalePng": grey,
                                   "metadata": {"outerRadiusMm": 55, "layers": []}, "finish": False})
                status, data, _ = request("POST", "/api/export", body, json_headers)
                result = json.loads(data)
                c.check(status == 200 and result.get("ready") is True, "full-size final and grey PNG export succeeds")
                path = Path(result["path"])
                c.check(path.exists() and path.parent.parent == export_dir and len(list(path.parent.iterdir())) == 3,
                        "all files stay in one new export directory despite path-like names")
                with Image.open(path) as image:
                    c.check(image.size == (6000, 6000) and image.getpixel((1000, 2000)) == 0
                            and image.getpixel((2000, 1000)) == 255, "saved image orientation and binary pixels stay exact")
                # Exercise the actual next command's loader, not a second copy of
                # its geometry math. This must remain pixel-exact: a default
                # 116 mm import would shrink the artwork and shift the ring.
                from . import imagedisc
                design = imagedisc.picture_design(str(path), diameter_mm=120)
                c.check(design.shape == (6000, 6000) and int(design.sum()) == 200
                        and design[2000:2020, 1000:1010].all()
                        and not design[1000, 2000],
                        "export handed to picture_design at 120 mm preserves every marked pixel without scaling or mirroring")
                del design
                with Image.open(result["grayscalePath"]) as image:
                    c.check(image.getpixel((0, 0)) == 123, "separate greyscale PNG retains intermediate tones")
                receipt = json.loads(Path(result["metadataPath"]).read_text(encoding="utf-8"))
                c.check(receipt["outerRadiusMm"] == 55 and receipt["settings"]["layers"] == [], "export receipt records the actual physical settings")
                original = path.read_bytes()
                status, data, _ = request("POST", "/api/export", json.dumps({"name": "../outside\\my art", "png": png, "finish": True}), json_headers)
                final = json.loads(data)
                c.check(status == 200 and final["path"] != str(path) and path.read_bytes() == original,
                        "repeated exports never overwrite an older image")
                thread.join(timeout=3)
                c.check(not thread.is_alive() and Path(final["path"]).exists() and final["command"],
                        "finish responds with a durable file and command, then returns the server to the terminal")
            finally:
                if thread.is_alive():
                    server.shutdown()
                thread.join(timeout=3)


def run(c) -> None:
    try:
        from PIL import Image
    except ImportError:
        print("editor PNG checks skipped: install Pillow")
        return
    _validation(c, Image)
    _geometry_and_commands(c)
    _http(c, Image)


if __name__ == "__main__":
    from .selftest import Checker
    checker = Checker()
    run(checker)
    raise SystemExit(1 if checker.failures else 0)

