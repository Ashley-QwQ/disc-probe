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

from .drive_lock import drive_locks, file_lock, user_state
from .i18n import _prepare

TITLE = ("disc-probe 正在运行，关闭此窗口即停止 / "
         "disc-probe is running — close this window to stop")
DEFAULT_PORT = 8765


def _path():
    return user_state() / "web-instance.json"


def _read(path):
    # The writer side retries in _update_file; a reader can likewise hit the record while
    # Windows is replacing or deleting it (access denied / sharing violation). Look again.
    for attempt in range(10):
        try:
            data = json.loads(path.read_bytes())
            return data if isinstance(data, dict) else None
        except (FileNotFoundError, ValueError):
            return None
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32) or attempt == 9:
                raise
            time.sleep(.02)


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
        data = _read(path)
        if data is None:
            return None
        pid, started, port, token = (data.get(key) for key in ("pid", "started", "port", "token"))
        if (any(type(value) is not int or value <= 0 for value in (pid, started, port))
                or port > 65535 or not isinstance(token, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
                or (data.get("mode"), data.get("bind")) not in
                (("LAN", "0.0.0.0"), ("local-only", "127.0.0.1"))):
            return None
        code, reply = _request(data, "/api/ping", timeout=1, limit=1024)
        if code == 200 and reply == {"pid": pid, "started": started}:
            return data
    except (OSError, ValueError, http.client.HTTPException):
        pass
    return None


def _request(record, route, payload=None, *, timeout=5, limit=1024 * 1024):
    # The discovery token only goes to loopback. Do not follow redirects or use proxies.
    conn = http.client.HTTPConnection("127.0.0.1", record["port"], timeout=timeout)
    try:
        headers = {"X-Discprobe-Token": record["token"]}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn.request("GET" if payload is None else "POST", route,
                     body=None if payload is None else json.dumps(payload), headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read(limit))
    finally:
        conn.close()


def _url(port, token):
    return f"http://127.0.0.1:{port}/home/?token={token}"


def _open(url):
    # The launcher already printed the address; on a headless Linux host it is sufficient.
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
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


def _conflicts(previous, config):
    saved = previous.get("config")
    if not isinstance(saved, dict):
        saved = {"mode": previous["mode"]}
    names = {"root": "工作目录 / working directory", "mode": "--local-only"}
    return [names.get(key, "--" + key.replace("_", "-")) for key, value in config.items()
            if key in saved and saved[key] != value]


def launch(factory, config, *, new_instance=False, open_browser=False):
    _prepare(sys.stdout)
    mode, port = config["mode"], config["port"]
    path = _path()
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
                                      mode=mode, bind=server.server_address[0], config=config)
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
                if changed := _conflicts(previous, config):
                    flags = ", ".join(changed)
                    _prepare(sys.stderr)
                    print(f"已有实例在用另一套参数（{flags}），要换请先运行 discprobe webui stop。 / "
                          f"The running instance uses different settings ({flags}). Run discprobe webui stop before changing them.",
                          file=sys.stderr, flush=True)
                url = _url(previous["port"], previous["token"])
                print(url, flush=True)
                if open_browser:
                    _open(url)
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
                            if _read(path) == record:
                                _update_file(lambda: path.unlink(missing_ok=True))
                finally:
                    finished.set()
                    if unwatch is not None:
                        unwatch()


def _task_text(tasks):
    return ", ".join(f"{task['action']} {task['drive'] or ''} {task['job'] or ''}".strip() for task in tasks)


def status(args):
    _prepare(sys.stdout)
    record = _existing(_path())
    result = dict(running=record is not None, **{
        key: record[key] if record else None for key in ("pid", "port", "token", "started", "mode", "bind")
    }, url=_url(record["port"], record["token"]) if record else None, tasks=[])
    if record:
        try:
            code, data = _request(record, "/api/status")
            if code == 404:
                # An older service can answer ping but may not yet offer status.
                data = {"drives": drive_locks(), "tasks": []}
            elif code != 200:
                raise ValueError(data.get("error", f"HTTP {code}"))
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise SystemExit(f"无法读取服务状态。 / Could not read service status: {exc}") from None
        result.update(drives=data["drives"], tasks=data["tasks"])
    else:
        from .guide import optical_drives
        result["drives"] = drive_locks(optical_drives() if os.environ.get("DISC_PROBE_NO_DRIVES") != "1" else ())
    if args.json:
        print(json.dumps(result))
        return
    if record:
        print(f"正在运行 / Running: pid {result['pid']}, {result['mode']}, {result['started']} ns")
        print(result["url"])
    else:
        print("服务未运行。 / Service is not running.")
    if result["tasks"]:
        print("进行中的任务 / Active tasks: " + _task_text(result["tasks"]))
    for drive in result["drives"]:
        owner = (f"pid {drive['pid']}, {drive['action']}" if drive["pid"] is not None
                 else "持有者未知 / holder unknown")
        print(f"{drive['drive']}  {owner if drive['locked'] else '空闲 / idle'}")


def stop(args):
    _prepare(sys.stdout)
    path = _path()
    record = _existing(path)
    if record is None:
        print("服务未运行。 / Service is not running.")
        return
    try:
        code, data = _request(record, "/api/quit", {"force": args.force})
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise SystemExit(f"无法停止服务。 / Could not stop the service: {exc}") from None
    if code != 200 or data.get("exited") is not True:
        _prepare(sys.stderr)
        raise SystemExit(data.get("error") or f"Could not stop the service (HTTP {code}).")
    # The HTTP response acknowledges the request. Registry cleanup follows child shutdown.
    deadline = time.monotonic() + 20
    while True:
        try:
            current = _read(path)
        except PermissionError:
            current = record  # Windows is still deleting or replacing it: keep waiting
        if current != record:
            break
        if time.monotonic() >= deadline:
            _prepare(sys.stderr)
            raise SystemExit("服务仍在退出。 / The service is still shutting down.")
        time.sleep(.05)
    print("服务已停止。 / Service stopped.")
