"""Local synthetic fixture server for test_curve_edit_browser.mjs; no devices."""
from pathlib import Path
import runpy
import sys

from discprobe.webui import Backend, Handler, Server

root = Path(sys.argv[1]).resolve()
helpers = runpy.run_path(str(Path(__file__).with_name("test_curve_edit.py")))
helpers["write_run"](root / "geo", spline=True, offset=1.25)


class FixtureHandler(Handler):
    def do_GET(self):
        if self.path == "/curve-edit-fixture":
            self._send(200, (root / "fixture.html").read_bytes(), "text/html; charset=utf-8")
        else:
            super().do_GET()


server = Server(Backend(root, drive_provider=lambda: []), port=0)
server.RequestHandlerClass = FixtureHandler
(root / "server-url.txt").write_text(f"http://127.0.0.1:{server.server_port}", encoding="utf-8")
try:
    server.serve_forever()
finally:
    server.server_close()
