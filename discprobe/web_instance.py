"""Discovery for the service started by the command-line and portable launchers."""
from contextlib import ExitStack, nullcontext
import errno
import http.client
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import webbrowser

from .drive_lock import file_lock, user_state
from .i18n import _prepare

TITLE = ("disc-probe 正在运行，关闭此窗口即停止 / "
         "disc-probe is running — close this window to stop")


def _console_title():
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(TITLE)


def _update_file(update):
    # Windows readers outside the startup guard can briefly block rename or unlink.
    for attempt in range(10):
        try:
            return update()
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32) or attempt == 9:
                raise
            time.sleep(.02)


def _publish(path, record):
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(json.dumps(record).encode("ascii"))
        _update_file(lambda: os.replace(name, path))
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def _existing(path):
    try:
        data = json.loads(path.read_bytes())
        if not isinstance(data, dict):
            return None
        pid, started, port, token = (data.get(key) for key in ("pid", "started", "port", "token"))
        if (any(type(value) is not int or value <= 0 for value in (pid, started, port))
                or port > 65535 or not isinstance(token, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
                or (data.get("mode"), data.get("bind")) not in
                (("LAN", "0.0.0.0"), ("local-only", "127.0.0.1"))):
            return None
        # The discovery token only goes to loopback. Do not follow redirects or use proxies.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        try:
            conn.request("GET", "/api/ping", headers={"X-Discprobe-Token": token})
            resp = conn.getresponse()
            if resp.status == 200 and json.loads(resp.read(1024)) == {"pid": pid, "started": started}:
                return data
        finally:
            conn.close()
    except (OSError, ValueError, http.client.HTTPException):
        pass
    return None


def _url(port, token):
    return f"http://127.0.0.1:{port}/home/?token={token}"


def _open(url):
    try:
        opened = webbrowser.open(url)
    except (OSError, webbrowser.Error):
        opened = False
    if not opened:
        print(f"请在浏览器打开此地址。 / Open this address in your browser.\n{url}", flush=True)


def _watch_console(closing, finished):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    @handler_type
    def on_console_event(event):
        if event != 2:  # CTRL_CLOSE_EVENT
            return False
        closing.set()
        finished.wait(4)  # Windows limits how long a console close handler can run.
        return True

    if kernel.SetConsoleCtrlHandler(on_console_event, True):
        return lambda: kernel.SetConsoleCtrlHandler(on_console_event, False)
    return None


def launch(factory, port, *, lan, new_instance=False, open_browser=False):
    _prepare(sys.stdout)
    mode = "LAN" if lan else "local-only"
    path = user_state() / "web-instance.json"
    guard = path.with_suffix(".lock")
    record = None
    worker = None
    closing, finished = threading.Event(), threading.Event()
    unwatch = None
    failures = []
    with ExitStack() as stack:
        try:
            with nullcontext() if new_instance else file_lock(guard, wait=True):
                previous = None if new_instance else _existing(path)
                if previous is None:
                    if not new_instance:
                        _update_file(lambda: path.unlink(missing_ok=True))
                    try:
                        server = factory(port)
                    except OSError as exc:
                        if port == 0 or (exc.errno != errno.EADDRINUSE
                                         and getattr(exc, "winerror", None) not in (10013, 10048)):
                            raise
                        server = factory(0)
                    stack.enter_context(server)
                    if not new_instance:
                        record = dict(port=server.server_port, token=server.lifecycle_token, **server.identity,
                                      mode=mode, bind=server.server_address[0])
                        _publish(path, record)
                    # Start serving before another launcher can probe this instance.
                    def serve():
                        try:
                            server.serve_forever(poll_interval=.1)
                        except BaseException as exc:
                            failures.append(exc)

                    worker = threading.Thread(target=serve)
                    worker.start()
            if previous is not None:
                if previous["mode"] != mode:
                    print(f"已经有一个 {previous['mode']} 模式的在运行，先关掉它再用 {mode} 模式启动。 / "
                          f"A {previous['mode']} instance is running. Quit it before starting in {mode} mode.", flush=True)
                url = _url(previous["port"], previous["token"])
                _open(url)
                print("已经在运行，已打开浏览器。 / Already running. Opened the browser.", flush=True)
                return

            _console_title()
            unwatch = _watch_console(closing, finished)
            url = _url(server.server_port, server.lifecycle_token)
            print(url, flush=True)
            if open_browser:
                _open(url)
            while worker.is_alive() and not closing.is_set():
                worker.join(.2)
            if failures:
                raise failures[0]
        except KeyboardInterrupt:
            pass
        finally:
            try:
                if worker is not None and worker.is_alive():
                    server.shutdown()
                    worker.join()
                stack.close()
            finally:
                try:
                    if record is not None:
                        with file_lock(guard, wait=True):
                            try:
                                current = json.loads(path.read_bytes())
                            except (FileNotFoundError, ValueError):
                                current = None
                            if current == record:
                                _update_file(lambda: path.unlink(missing_ok=True))
                finally:
                    finished.set()
                    if unwatch is not None:
                        unwatch()
