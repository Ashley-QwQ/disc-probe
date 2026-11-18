"""Exercise real launcher processes and Disc Lab drives on loopback."""
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from disclab.__main__ import lab_env
from disclab.practice import prepare
from discprobe.drive_lock import DriveBusy, drive_operation, require_available

ROOT = Path(__file__).resolve().parents[1]
CLI = ("-m", "discprobe", "webui", "--port", "0")
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
    except (FileNotFoundError, ValueError):
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


def wait_primary(path, child):
    def attempt():
        if child.poll() is not None:
            pytest.fail(f"server exited {child.returncode}: {child.stderr.read()}")
        data = record(path)
        if not data or data["pid"] != child.pid:
            return
        try:
            if request(address(data), "/api/ping") == (200, {"pid": child.pid, "started": data["started"]}):
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
        with process(lab, *LAUNCHER, "--local-only") as second:
            out, err = second.communicate(timeout=10)
            assert second.returncode == 0, err
        assert "已经在运行，已打开浏览器" in out
        assert calls.read_text(encoding="utf-8").splitlines() == [
            f"http://127.0.0.1:{data['port']}/home/?token={data['token']}"]
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
        with process(lab, *CLI, "--local-only") as mismatch:
            out, err = mismatch.communicate(timeout=10)
            assert mismatch.returncode == 0, err
        assert "先关掉它再用 local-only 模式启动" in out
        assert len(calls.read_text(encoding="utf-8").splitlines()) == 2
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
    with process(lab, *CLI, "--local-only", DISCLAB_BURN_TIME="40") as first:
        primary = wait_primary(state, first)
        a = address(primary)
        with process(lab, *CLI, "--local-only", "--new-instance") as second:
            url = urlsplit(second.stdout.readline().strip())
            b = url.port, parse_qs(url.query)["token"][0]
            assert request(b, "/api/ping")[1]["pid"] == second.pid
            assert record(state) == primary
            assert request(a, "/api/quit", {}, authenticated=False)[0] == 403
            assert request(a, "/api/burn-speeds?drive=X%3A")[1]["blank"]
            token = request(a, "/api/burn-token")[1]["token"]
            status, job = request(a, "/api/run", dict(action="burn", drive="X:", media="dvd",
                                  args=dict(iso="iso/run.iso", speed=8), burn_token=token))
            assert status == 200, job
            path = "/api/jobs/" + job["job"]

            def active():
                snapshot = request(a, path)[1]
                assert snapshot["exit"] is None, snapshot
                return any(e["type"] == "burn_speed" for e in snapshot["events"])

            eventually(active)
            assert request(a, "/api/quit", {})[1]["code"] == "tasks_running"
            status, refused = request(b, "/api/run", dict(action="info", drive="X:"))
            assert status == 409 and refused["code"] == "drive_busy", refused
            assert "正在：刻录" in refused["error"] and "action: burn" in refused["error"]
            assert request(b, "/api/burn-speeds?drive=X%3A") == (409, refused)
            done = eventually(lambda: (s if (s := request(a, path)[1])["exit"] is not None else None))
            assert done["exit"] == 0, done
            status, disc = request(b, "/api/disc", {"drive": "X:"})
            assert status == 200 and disc["disc"]["blank"] is False, disc
            shutdown(second, b)
            assert record(state) == primary
        shutdown(first, a)
    assert not state.exists()
