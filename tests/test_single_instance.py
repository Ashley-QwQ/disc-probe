"""Exercise real launcher processes and Disc Lab drives on loopback."""
from contextlib import contextmanager
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from disclab.__main__ import lab_env
from disclab.practice import prepare
from discprobe.drive_lock import DriveBusy, drive_operation, require_available
from discprobe import web_instance, webui
from discprobe.image_output import mark_checked

ROOT = Path(__file__).resolve().parents[1]
CLI = ("-m", "discprobe", "webui", "--port", "0")
CONTROL = ("-m", "discprobe", "webui")
LAUNCHER = (str(ROOT / "tools" / "launch_web.py"),)


def eventually(attempt, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = attempt()
        if value:
            return value
        time.sleep(.04)
    pytest.fail("condition did not become true")


def request(instance, path, payload=None, *, authenticated=True):
    port, token = instance
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        headers = {"X-Discprobe-Token": token} if authenticated else {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn.request("GET" if payload is None else "POST", path,
                     body=None if payload is None else json.dumps(payload), headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


def record(path):
    try:
        return json.loads(path.read_bytes())
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def address(data):
    return data["port"], data["token"]


@pytest.fixture
def lab(tmp_path):
    virtual = prepare(tmp_path / "lab")
    private = tmp_path / "user"
    state = private / "disc-probe" / "web-instance.json"
    browser_calls = tmp_path / "browser.txt"
    shim = tmp_path / "webbrowser.py"
    shim.write_text(
        "import builtins\nimport os\n"
        "def open(url):\n"
        "    with builtins.open(os.environ['DP_TEST_BROWSER'], 'a', encoding='utf-8') as log:\n"
        "        log.write(url + '\\n')\n"
        "    return True\n", encoding="utf-8")
    env = lab_env(virtual, dict(os.environ, LOCALAPPDATA=str(private), DISCPROBE_HOME=str(virtual.root),
                               DP_TEST_BROWSER=str(browser_calls), PYTHONPATH=str(tmp_path)))
    env.pop("DISC_PROBE_NO_DRIVES", None)  # The Lab boot hook exposes only virtual drives.
    env.setdefault("DISPLAY", ":0")  # Existing browser-open tests use a stub on headless Linux too.
    return virtual, env, state, browser_calls


@contextmanager
def process(lab, *args, **env_changes):
    virtual, env, _, _ = lab
    child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", *args], cwd=virtual.root,
                             env=dict(env, **env_changes), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=15)


def control(lab, *args):
    with process(lab, *CONTROL, *args) as child:
        out, err = child.communicate(timeout=15)
        return child.returncode, out, err


def wait_primary(path, child, *, child_is_service=True):
    def attempt():
        if child.poll() is not None:
            pytest.fail(f"server exited {child.returncode}: {child.stderr.read()}")
        data = record(path)
        if not data or (child_is_service and data["pid"] != child.pid):
            return
        try:
            if request(address(data), "/api/ping") == (200, {"pid": data["pid"], "started": data["started"]}):
                return data
        except OSError:
            pass
    return eventually(attempt)


def shutdown(child, instance):
    assert request(instance, "/api/quit", {}) == (200, {"exited": True})
    assert child.wait(timeout=10) == 0


def test_second_launcher_only_opens_the_existing_browser(lab):
    _, _, state, calls = lab
    with process(lab, *CLI, "--local-only") as first:
        data = wait_primary(state, first)
        assert data["mode"] == "local-only" and data["bind"] == "127.0.0.1"
        assert request(address(data), "/api/ping", authenticated=False)[0] == 403
        expected = f"http://127.0.0.1:{data['port']}/home/?token={data['token']}"
        with process(lab, *CLI, "--local-only") as second:
            out, err = second.communicate(timeout=10)
            assert (second.returncode, out.strip(), err) == (0, expected, "")
        assert not calls.exists()
        with process(lab, *LAUNCHER, "--port", "0", "--local-only") as second:
            out, err = second.communicate(timeout=10)
            assert (second.returncode, out.strip(), err) == (0, expected, "")
        assert calls.read_text(encoding="utf-8").splitlines() == [expected]
        assert record(state) == data
        shutdown(first, address(data))
    assert not state.exists()


def test_simultaneous_starts_and_mode_mismatch(lab):
    _, _, state, calls = lab
    with process(lab, *CLI) as a, process(lab, *CLI) as b:
        eventually(lambda: a.poll() is not None or b.poll() is not None)
        first, second = (b, a) if a.poll() is not None else (a, b)
        assert second.returncode == 0
        data = wait_primary(state, first)
        assert data["mode"] == "LAN" and data["bind"] == "0.0.0.0"
        with process(lab, *CLI, "--local-only", "--media", "cd", "--open") as mismatch:
            out, err = mismatch.communicate(timeout=10)
            assert mismatch.returncode == 0, err
        assert "要换请先运行 discprobe webui stop" in err and "--local-only" in err and "--media" in err
        assert out.strip().startswith(f"http://127.0.0.1:{data['port']}/")
        assert calls.read_text(encoding="utf-8").splitlines() == [out.strip()]
        shutdown(first, address(data))


def test_force_kill_recovery_and_occupied_port(lab):
    _, _, state, calls = lab
    with process(lab, *CLI, "--local-only") as first:
        orphan = wait_primary(state, first)
        first.kill()
        first.wait(timeout=10)
    assert record(state) == orphan
    with socket.socket() as occupied:
        if os.name == "nt":
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("127.0.0.1", orphan["port"]))
        occupied.listen()
        with process(lab, "-m", "discprobe", "webui", "--local-only", "--port", str(orphan["port"])) as next_child:
            data = wait_primary(state, next_child)
            assert data["started"] != orphan["started"] and data["port"] != orphan["port"]
            shutdown(next_child, address(data))
    assert not state.exists() and not calls.exists()


@pytest.mark.parametrize("damage", ["reused_pid", "wrong_start", "partial_json", "wrong_token"])
def test_invalid_identity_cannot_reopen_or_remove_a_successor(lab, damage):
    _, _, state, calls = lab
    with process(lab, *CLI, "--local-only") as first:
        actual = wait_primary(state, first)
        forged = dict(actual)
        if damage == "reused_pid":
            forged.update(pid=os.getpid(), started=1)  # another live process
        elif damage == "wrong_start":
            forged["started"] -= 1
        elif damage == "wrong_token":
            forged["token"] = "A" * 43 if actual["token"] != "A" * 43 else "B" * 43
        state.write_text("{" if damage == "partial_json" else json.dumps(forged), encoding="utf-8")
        with process(lab, *CLI, "--local-only") as second:
            data = wait_primary(state, second)
            shutdown(first, address(actual))
            assert record(state) == data
            shutdown(second, address(data))
    assert not state.exists() and not calls.exists()


def test_drive_lock_conflict_releases_on_crash_and_other_drive_can_run(lab, tmp_path):
    virtual, env, state_path, calls = lab
    # A second drive with an empty tray is enough for a real Disc Lab read.
    with virtual.locked_state() as state:
        state["drives"]["Y:"] = dict(state["drives"]["X:"], tray=None)
    script = ("from discprobe.drive_lock import drive_operation; import time; "
              "exec(\"with drive_operation('x:', 'timing'):\\n print('ready', flush=True)\\n time.sleep(60)\")")
    with process(lab, "-c", script) as holder:
        assert holder.stdout.readline().strip() == "ready"
        with process(lab, "-m", "discprobe", "info", "--drive", "X:") as refused:
            out, err = refused.communicate(timeout=5)
            assert refused.returncode == 75, (out, err)
            assert f"pid {holder.pid}" in err and "计时测量" in err and "action: timing" in err
        with process(lab, "-m", "discprobe", "disc", "--drive", "Y:") as other:
            out, err = other.communicate(timeout=5)
            assert other.returncode == 0, err
            assert not json.loads(out)["disc"]
        separate = prepare(tmp_path / "separate-lab")
        other_lab = (separate, dict(env, DISCPROBE_DISCLAB=str(separate.root)), state_path, calls)
        with process(other_lab, "-m", "discprobe", "disc", "--drive", "X:") as other:
            out, err = other.communicate(timeout=5)
            assert other.returncode == 0 and json.loads(out)["disc"]["present"], err
        holder.kill()
        holder.wait(timeout=5)
    with process(lab, "-m", "discprobe", "disc", "--drive", "X:") as again:
        out, err = again.communicate(timeout=5)
        assert again.returncode == 0 and json.loads(out)["disc"]["present"], err


def test_one_operation_is_reentrant(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with drive_operation("X:", "burn"), drive_operation("x:/", "verify"):
        with pytest.raises(DriveBusy, match="action: burn") as exc:
            require_available("X")
        assert exc.value.code == "drive_busy"
    require_available("x")


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell"), reason="Windows PowerShell required")
def test_standalone_windows_helper_uses_the_core_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    helper = ROOT / "tools" / "drive_lock.ps1"
    command = (
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
        f". '{helper}'; "
        "try { $lease = Open-DiscProbeDriveLock 'x:' 'erase'; 'ready'; "
        "Start-Sleep -Seconds 60 } "
        "catch { [Console]::Error.WriteLine($_.Exception.Message); exit 75 } "
        "finally { Close-DiscProbeDriveLock $lease }"
    )
    argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    with drive_operation("X:", "burn"):
        refused = subprocess.run(argv, check=False, capture_output=True, text=True, encoding="utf-8", timeout=10)
        assert refused.returncode == 75 and "正在：刻录" in refused.stderr and "action: burn" in refused.stderr
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8") as holder:
        try:
            assert holder.stdout.readline().strip() == "ready"
            with pytest.raises(DriveBusy, match=f"pid {holder.pid}.*action: erase"):
                require_available("X:")
        finally:
            holder.kill()
            holder.wait(timeout=10)
    require_available("X:")


def test_virtual_burn_blocks_other_instance_and_quit_until_finished(lab):
    virtual, _, state, _ = lab
    iso = virtual.root / "iso" / "run.iso"
    iso.parent.mkdir()
    with iso.open("wb") as stream:
        stream.truncate(2 * 1024 * 1024)
    mark_checked(iso, [])
    with process(lab, *CLI, "--local-only", DISCLAB_BURN_TIME="75") as first:
        primary = wait_primary(state, first)
        a = address(primary)
        with process(lab, *CLI, "--local-only", "--new-instance") as second:
            url = urlsplit(second.stdout.readline().strip())
            b = url.port, parse_qs(url.query)["token"][0]
            assert request(b, "/api/ping")[1]["pid"] == second.pid
            assert record(state) == primary
            assert request(a, "/api/quit", {}, authenticated=False)[0] == 403
            assert request(a, "/api/burn-speeds?drive=X%3A")[1]["blank"]
            payload = dict(action="burn", drive="X:", media="dvd", args=dict(iso="iso/run.iso", speed=8))
            token = request(a, "/api/burn-token", payload)[1]["token"]
            status, job = request(a, "/api/run", dict(payload, burn_token=token))
            assert status == 200, job
            path = "/api/jobs/" + job["job"]

            def active():
                snapshot = request(a, path)[1]
                assert snapshot["exit"] is None, snapshot
                return any(e["type"] == "burn_speed" for e in snapshot["events"])

            eventually(active)
            assert request(a, "/api/quit", {})[1]["code"] == "tasks_running"
            code, _, err = control(lab, "stop")
            assert code == 1 and f"burn X: {job['job']}" in err
            code, _, err = control(lab, "stop", "--force")
            assert code == 1 and "光驱正在写入" in err and "burn X:" in err
            status, refused = request(b, "/api/run", dict(action="info", drive="X:"))
            assert status == 409 and refused["code"] == "drive_busy", refused
            assert "正在：刻录" in refused["error"] and "action: burn" in refused["error"]
            assert request(b, "/api/burn-speeds?drive=X%3A") == (409, refused)
            done = eventually(lambda: (s if (s := request(a, path)[1])["exit"] is not None else None), seconds=30)
            assert done["exit"] == 0, done
            status, disc = request(b, "/api/disc", {"drive": "X:"})
            assert status == 200 and disc["disc"]["blank"] is False, disc
            shutdown(second, b)
            assert record(state) == primary
        stopped = control(lab, "stop"); assert stopped[0] == 0, stopped
        assert first.wait(timeout=10) == 0
    assert not state.exists()


def test_busy_port_falls_back_and_reuse_keeps_the_registered_port(lab):
    _, _, state, _ = lab
    with socket.socket() as occupied:
        if os.name == "nt":
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        requested = occupied.getsockname()[1]
        options = ("--local-only", "--port", str(requested))
        with process(lab, *CONTROL, *options) as child:
            data = wait_primary(state, child)
            assert data["port"] != requested and data["config"]["port"] == requested
            code, out, err = control(lab, *options)
            assert code == 0 and not err and urlsplit(out.strip()).port == data["port"]
            stopped = control(lab, "stop"); assert stopped[0] == 0, stopped
            assert child.wait(timeout=10) == 0
    assert not state.exists()


@pytest.mark.parametrize("option", ["flag", "environment"])
def test_no_drives_applies_to_core(lab, option):
    _, _, state, _ = lab
    args = ["--no-drives"] if option == "flag" else []
    env = {"DISC_PROBE_NO_DRIVES": "1"} if option == "environment" else {}
    with process(lab, *CLI, "--local-only", *args, **env) as child:
        data = wait_primary(state, child)
        assert data["config"]["no_drives"] is True
        assert request(address(data), "/api/state", authenticated=False)[1]["drives"] == []
        status, out, err = control(lab, "status", "--json")
        assert (status, err) == (0, "") and json.loads(out)["drives"] == []
        shutdown(child, address(data))


def test_status_json_and_force_stop_of_read_only_task(lab):
    virtual, _, state, _ = lab
    with virtual.locked_state() as lab_state:
        lab_state["drives"]["Y:"] = dict(lab_state["drives"]["X:"], tray=None)
    with process(lab, *CLI, "--local-only") as child:
        data = wait_primary(state, child)
        link = address(data)
        assert request(link, "/api/status", authenticated=False)[0] == 403
        code, job = request(link, "/api/run", {"action": "swap", "drive": "X:"})
        assert code == 200, job
        eventually(lambda: any(
            row["action"] == "swap" and row["locked"]
            for row in request(link, "/api/status")[1]["drives"] if row["drive"] == "X:"
        ))
        code, out, err = control(lab, "status", "--json")
        assert (code, err) == (0, "")
        status = json.loads(out)
        assert status["running"] is True
        assert {k: status[k] for k in ("pid", "port", "token", "started", "mode", "bind")} == {
            k: data[k] for k in ("pid", "port", "token", "started", "mode", "bind")}
        assert urlsplit(status["url"]).port == data["port"]
        rows = {r["drive"]: r for r in status["drives"]}
        assert rows["X:"]["locked"] and rows["X:"]["action"] == "swap" and rows["X:"]["pid"] != child.pid
        assert rows["Y:"] == dict(drive="Y:", locked=False, pid=None, action=None)
        assert status["tasks"] == [dict(action="swap", drive="X:", job=job["job"], writes_drive=False)]
        code, _, err = control(lab, "stop")
        assert code == 1 and "swap X:" in err
        code, out, err = control(lab, "stop", "--force")
        assert (code, err) == (0, "") and "Service stopped." in out
        assert child.wait(timeout=10) == 0
    assert not state.exists()
    code, out, err = control(lab, "status", "--json")
    assert (code, err) == (0, "")
    stopped = json.loads(out)
    assert not stopped["running"] and stopped["token"] is None and not stopped["tasks"]
    assert {r["drive"] for r in stopped["drives"]} == {"X:", "Y:"}
    assert not any(r["locked"] for r in stopped["drives"])


def test_force_stop_protects_a_writer_running_outside_the_server(lab):
    _, _, state, _ = lab
    script = ("from discprobe.drive_lock import drive_operation; import time; "
              "exec(\"with drive_operation('X:', 'erase'):\\n print('ready', flush=True)\\n time.sleep(60)\")")
    with process(lab, *CLI, "--local-only") as child:
        data = wait_primary(state, child)
        with process(lab, "-c", script) as holder:
            assert holder.stdout.readline().strip() == "ready"
            code, out, err = control(lab, "status", "--json")
            assert (code, err) == (0, "")
            status = json.loads(out)
            assert not status["tasks"]
            assert status["drives"] == [dict(drive="X:", locked=True, pid=holder.pid, action="erase")]
            code, _, err = control(lab, "stop", "--force")
            assert code == 1 and "erase X:" in err
            holder.kill()
            holder.wait(timeout=5)
        assert record(state) == data and control(lab, "stop", "--force")[0] == 0
        assert child.wait(timeout=10) == 0


def test_linux_browser_open_requires_display(monkeypatch, capsys):
    monkeypatch.setattr(web_instance, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    calls = []
    monkeypatch.setattr(web_instance.webbrowser, "open", lambda url: calls.append(url) or True)
    url = "http://127.0.0.1:8765/home/"
    web_instance._open(url)
    assert calls == [] and capsys.readouterr().out == ""
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    web_instance._open(url)
    assert calls == [url]


def test_linux_drive_permission_tip_uses_only_permission_metadata(monkeypatch, capsys):
    checks = []
    def access(path, mode):
        checks.append((path, mode))
        return path == "/dev/sr1"
    monkeypatch.setattr(webui, "os", SimpleNamespace(access=access, R_OK=os.R_OK, W_OK=os.W_OK))
    webui._warn_linux_drive_permissions([{"id": n} for n in ("/dev/sr0", "/dev/sr1", "X:")])
    assert checks == [("/dev/sr0", os.R_OK | os.W_OK), ("/dev/sr1", os.R_OK | os.W_OK)]
    err = capsys.readouterr().err
    assert "加入 cdrom 组" in err and "/dev/sr0" in err and "/dev/sr1" not in err


@pytest.mark.skipif(os.name != "nt", reason="Windows batch file")
@pytest.mark.parametrize("batch_first", [False, True])
def test_actual_winpack_batch_and_cli_share_one_server(lab, batch_first):
    virtual, env, state, calls = lab
    virtual = prepare(virtual.root.with_name("验收 Windows 包"))
    env = lab_env(virtual, dict(env, DISCPROBE_HOME=str(virtual.root)))
    lab = virtual, env, state, calls
    spec = importlib.util.spec_from_file_location("winpack", ROOT / "tools" / "build_winpack.py")
    winpack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(winpack)
    winpack.write_start(virtual.root)
    batch = virtual.root / "开始 Start (Windows).bat"
    guard, launch = batch.read_bytes().splitlines()
    assert guard.startswith(b":; ") and b"-m discprobe webui --open" in launch
    python = virtual.root / "python"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(python), str(Path(sys.executable).parent)],
                   check=True, capture_output=True)
    argv = ["cmd.exe", "/d", "/c", "call", str(batch), "--port", "0", "--local-only"]
    try:
        options = dict(cwd=virtual.root.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8")
        if batch_first:
            with subprocess.Popen(argv, **options) as bat:
                try:
                    data = wait_primary(state, bat, child_is_service=False)
                    code, out, err = control(lab, "--local-only", "--port", "0")
                    assert (code, err) == (0, "")
                    assert record(state) == data
                    assert request(address(data), "/api/disc", {"drive": "X:"})[1]["disc"]["present"]
                    stopped = control(lab, "stop"); assert stopped[0] == 0, stopped; assert bat.wait(timeout=10) == 0
                finally:
                    if bat.poll() is None:
                        if record(state):
                            control(lab, "stop")
                        bat.kill()
        else:
            with process(lab, *CLI, "--local-only") as child:
                data = wait_primary(state, child)
                bat = subprocess.run(argv, **options, timeout=15)
                assert (bat.returncode, bat.stderr) == (0, "")
                out = bat.stdout
                assert record(state) == data
                assert request(address(data), "/api/disc", {"drive": "X:"})[1]["disc"]["present"]
                stopped = control(lab, "stop"); assert stopped[0] == 0, stopped; assert child.wait(timeout=10) == 0
        assert calls.read_text(encoding="utf-8").splitlines() == [out.strip()]
    finally:
        python.rmdir()  # Remove the junction itself.
