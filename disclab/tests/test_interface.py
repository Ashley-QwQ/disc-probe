"""CLI contract, persisted progress and portable front ends on virtual drives only."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from unittest.mock import Mock
from urllib.request import urlopen

import pytest

from disclab.__main__ import ROOT, main
from disclab.lab import Lab
from disclab.web import FORBIDDEN_PORTS


def cli(*args, input=None, timeout=90):
    return subprocess.run([sys.executable, "-B", "-m", "disclab", *map(str, args)],
                          cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                          input=input, text=True, encoding="utf-8", capture_output=True, timeout=timeout)


def envelope(result, status="ok"):
    value = json.loads(result.stdout)
    assert set(value) == {"status", "lab", "outputs", "scores", "errors"}
    assert value["status"] == status, result.stdout + result.stderr
    assert isinstance(value["outputs"], dict) and isinstance(value["scores"], dict)
    assert isinstance(value["errors"], list)
    assert (result.returncode == 0) == (status == "ok")
    return value


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    lab = tmp_path_factory.mktemp("api") / "lab with spaces \u6d4b\u8bd5"
    box = envelope(cli("box", "--json", "--lab", lab, "--count", "1", "--seed", "17"))
    assert box["outputs"]["box"]["count"] == 1
    # The unchanged scorer samples radii starting at 25 mm. A 4096-sector DVD
    # remains below that grid; 65536 reaches it without creating a full disc.
    result = envelope(cli("loop", "geo", "--json", "--lab", lab, "--iso-sectors", "65536",
                          "--reps", "8", "--max-targets", "6"))
    assert result["scores"]["geo-wide"][0]["exit"] == 0
    return Lab(lab), result["scores"]["geo-wide"][0]


@pytest.mark.parametrize("command", ["tray", "env", "dp", "score", "photos", "poses", "tui", "upload"])
def test_command_envelopes(measured, command, monkeypatch):
    lab, row = measured
    args = [command, "--json", "--lab", lab.root]
    if command == "tray":
        args += ["--disc", row["disc"]]
    elif command == "dp":
        args += ["--", "random", "--sectors", "4096", "--output", lab.root / "iso" / "api.iso"]
    elif command == "score":
        args += ["--disc", row["disc"], "--geo", row["geo"]]
    elif command == "photos":
        args += ["--disc", row["disc"], "-n", "1", "--width", "640", "--height", "480",
                 "--out", lab.root / "photos" / "api"]
    elif command == "poses":
        # Exercise parser, dispatch, saved scores and stdout isolation without a full-resolution sweep.
        from disclab import poses
        monkeypatch.setattr(poses, "sweep", lambda *a, **k: dict(truth_L_mm=0.19, rows=[], summary={}))
        args += ["--disc", row["disc"], "--geo", row["geo"], "--out", lab.root / "scores" / "poses.json"]
    elif command == "upload":
        from disclab import web
        from disclab.tests.test_disclab import Reply
        photo = lab.root / "upload.jpg"
        photo.write_bytes(b"test payload")
        desk, phone = Mock(), Mock()
        desk.open.side_effect = [Reply({"url": "http://localhost/phone/cap"}), Reply({"photos": []})]
        phone.open.side_effect = [Reply({}), Reply({"id": "test"})]
        monkeypatch.setattr(web, "build_opener", Mock(side_effect=[desk, phone]))
        args += ["--url", "http://localhost", "--run", Path(row["geo"]).name, "--photos", photo]
    elif command == "tui":
        args += ["--plain"]
        monkeypatch.setattr("sys.stdin", io.StringIO("0\n"))
    if command in {"poses", "upload", "tui"}:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(list(map(str, args)))
        result = subprocess.CompletedProcess(args, 0, output.getvalue(), "")
    else:
        result = cli(*args)
    value = envelope(result)
    assert value["lab"] == str(lab.root)
    assert value["outputs"]


@pytest.mark.parametrize("args", [
    ["no-such-command", "--json"], ["web", "--json", "--lab", "unused", "--port", "0"],
    ["dp", "--json", "--lab", "unused", "--", "no-such-command"],
    ["tray", "--json", "--lab", "unused", "--disc", "missing"],
])
def test_errors_are_single_json_object(args):
    value = envelope(cli(*args), "error")
    assert value["errors"][0]["message"]


def test_json_help():
    value = envelope(cli("tui", "--json", "--help"))
    assert "--plain" in value["outputs"]["help"]


def test_json_compatibility_error(monkeypatch, capsys):
    from disclab import compat

    def unavailable():
        raise SystemExit("Disc Lab requires the matching disc-probe version")

    monkeypatch.setattr(compat, "require_discprobe", unavailable)
    with pytest.raises(SystemExit) as stopped:
        main(["box", "--json", "--lab", "unused"])
    assert stopped.value.code == 1
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "error"
    assert value["errors"][0]["type"] == "CompatibilityError"


def _flow_done(lab, *keys, **last):
    """Record practice steps as done (oldest first), the last one with extra fields."""
    for k in keys[:-1]:
        lab.step("flow", key=k, status="ok")
        time.sleep(0.002)
    lab.step("flow", key=keys[-1], status="ok", **last)


PRE_PHOTO = ("blank", "measure_image", "measure_burn", "timing", "geo", "picture", "checkdisc", "check_burn", "photos")


def test_global_json_and_photo_refusal(tmp_path, monkeypatch):
    from disclab import flow
    from disclab.lab import atomic_json
    lab = Lab(tmp_path / "refused lab")
    envelope(cli("--json", "box", "--lab", lab.root, "--count", "3"))
    rec = lab.root / "runs" / "refused" / "photo.json"
    atomic_json(rec, dict(offset_mm=None, verdict="rejected", photos=[]))
    _flow_done(lab, *PRE_PHOTO, "photo", disc=lab.box()["discs"][1], paths=[str(rec)], run=str(rec.parent),
               offset_mm=None, verdict="rejected")
    before = lab.answers_path.read_bytes()
    dispatch = Mock()
    monkeypatch.setattr(flow, "_dp", dispatch)
    # a reading without L does not count as done: the final file waits, and the flow goes back to more photos
    with pytest.raises(flow.StepError, match="Read the along-track constant"):
        flow.run_step(lab, "final")
    assert next(s for s in flow.plan(lab) if s["current"])["key"] == "photos"
    dispatch.assert_not_called()
    assert lab.answers_path.read_bytes() == before
    assert not lab.state()["burns"]
    assert flow.records(lab, "final")[-1]["status"] == "error"


def test_packaged_sample(tmp_path):
    import zipfile
    from PIL import Image
    from disclab.package import build
    package = build(tmp_path / "disc-lab.zip")
    with zipfile.ZipFile(package) as archive:
        sample = archive.read("disclab/data/sample.pgm")
        assert "disclab/API.md" in archive.namelist()
        names = set(archive.namelist())
        assert {"disclab/web/index.html", "disclab/web/lab.js", "disclab/web/lobby/lobby.json",
                "disclab/web/lobby/phone_dark.webp", "disclab/web/fonts/OFL-Archivo.txt"} <= names
    with Image.open(io.BytesIO(sample)) as image:
        assert image.size == (64, 64)
        assert image.getextrema() == (0, 255)


def test_steps_preserve_existing_keys(measured):
    lab, row = measured
    with lab.locked_state() as state:
        state["extension"] = {"retain": True}
    envelope(cli("env", "--json", "--lab", lab.root))
    state = lab.state()
    assert state["extension"] == {"retain": True}
    assert {"drives", "burns", "events", "steps"} <= state.keys()
    for kind in ("box", "burn", "tray", "geo", "scores", "env"):
        records = state["steps"][kind]
        assert records and all(isinstance(r["t"], (float, int)) for r in records)
    burn = state["steps"]["burn"][0]
    assert burn["disc"] == row["disc"] and burn["iso"]
    assert Path(state["steps"]["geo"][-1]["paths"][-1]).name == "summary.json"


def test_scripted_tui_box_geo_picture_score(tmp_path):
    lab = tmp_path / "tui lab \u6d4b\u8bd5"
    # disc-probe's steps in its order: Enter runs the step "you are here"; the burn asks first (y)
    script = "\n".join([str(lab), "dvd-r", "3", "1", "gh70n",
                        "", "", "", "y", "", "", "", "13", "q"]) + "\n"
    result = cli("tui", "--plain", "--quick", "--lang", "en", "--json", input=script)
    envelope(result)
    assert "did not work" not in result.stderr, result.stdout + result.stderr
    # the console's own words for the steps (disc-probe's guide), not the web page's
    assert "Geometry (geo)" in result.stderr and "Drive check (timing)" in result.stderr
    assert "<- you are here" in result.stderr
    assert "\x1b[" not in result.stderr
    state = Lab(lab).state()
    assert {"box", "burn", "timing", "geo", "sample_picture", "scores"} <= state["steps"].keys()
    scores = Lab(lab).read(lab / "scores" / "tui.json")
    assert scores["geo"]["true_u"] > 0
    assert "sample_picture" in scores["pictures"]
    assert Path(next(iter(state["burns"].values()))["sessions"][0]["iso"]).exists()
    resumed = cli("tui", "--lab", lab, "--plain", "--lang", "zh", input="13\nq\n")
    assert "没有成功" not in resumed.stdout and "盘面几何 (geo)" in resumed.stdout and "空盘 (info)" in resumed.stdout


def test_image_must_confirm_applied_L(measured, monkeypatch):
    from disclab import flow
    from disclab.lab import atomic_json
    lab, row = measured
    folder = Path(row["geo"])
    photo = folder / "photo.json"
    atomic_json(photo, dict(offset_mm=0.19, verdict="ok"))
    _flow_done(lab, *PRE_PHOTO, "photo", disc=row["disc"], paths=[str(photo)], run=str(folder),
               offset_mm=0.19, verdict="ok")
    before = lab.state()["burns"]

    def image_without_L(lab, *args):
        assert args[0] == "image"
        image = Path(args[args.index("--output") + 1])
        atomic_json(image.with_suffix(".image.json"), dict(photo_l=dict(written=False, reason="identity_mismatch")))

    monkeypatch.setattr(flow, "_dp", image_without_L)
    with pytest.raises(flow.StepError, match="identity_mismatch"):
        flow.run_step(lab, "final")
    assert lab.state()["burns"] == before


def test_loop_photo_envelope(measured, monkeypatch, capsys):
    from disclab import loop
    lab, _ = measured
    monkeypatch.setattr(loop, "loop_photo", lambda *a, **k: [])
    main(["loop", "photo", "--json", "--lab", str(lab.root)])
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "ok" and value["outputs"]["rows"] == []


def test_practice_default_lab_uses_temp_root(tmp_path, monkeypatch, capsys):
    import tempfile
    from disclab import practice
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(practice, "serve", lambda *a: 0)
    main(["practice", "--json"])
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "ok"
    assert Path(value["lab"]).parent == tmp_path
    assert Lab(value["lab"]).box()["count"] == 3
    assert Lab(value["lab"]).state()["steps"]["practice"][-1]["status"] == "ok"


def free_port():
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in FORBIDDEN_PORTS:
            return port


@pytest.mark.parametrize("command", ["web", "practice"])
def test_server_start_stop_json(tmp_path, command):
    lab = tmp_path / command
    if command == "web":
        envelope(cli("box", "--json", "--lab", lab, "--count", "2"))
    port = free_port()
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        child = subprocess.Popen([sys.executable, "-B", "-m", "disclab", command, "--json",
                                  "--lab", str(lab), "--port", str(port)], cwd=ROOT, stdout=out, stderr=err,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert child.poll() is None, stderr.read_text(encoding="utf-8")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/home/", timeout=1) as reply:
                        assert reply.status == 200
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("local practice server did not start")
        finally:
            if child.poll() is None:
                child.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            child.wait(timeout=15)
    result = subprocess.CompletedProcess([], child.returncode, stdout.read_text(encoding="utf-8"),
                                         stderr.read_text(encoding="utf-8"))
    value = envelope(result)
    assert value["outputs"]["url"].endswith(f":{port}/home/")
    assert any(r["status"] == "stopped" for r in Lab(lab).state()["steps"]["web"])
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0
    if command == "practice":
        assert Lab(lab).box()["count"] == 3
        assert "No physical discs are used up" in result.stderr
        assert "Practice results:" in result.stderr
        other = tmp_path / "other files"
        other.mkdir()
        (other / "notes.txt").write_text("keep", encoding="utf-8")
        envelope(cli("practice", "--json", "--lab", other, "--port", free_port()), "error")
        assert [p.name for p in other.iterdir()] == ["notes.txt"]
