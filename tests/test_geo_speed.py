"""Geo's read-speed record and notices, with device-free fixtures."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from discprobe import geo_speed, guide, i18n, read_completion
from discprobe.__main__ import main
from discprobe.sim import SimDrive


IDENTITY = {"drive": "HL-DT-ST DVD-RAM GH70N", "firmware": "NYA2"}
STRUCTURED_ID = {"vendor": " hl-dt-st ", "product": "DVD-RAM  GH70N ", "revision": "nya2"}
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("media,speed,identity,status", [
    ("dvd", 5540, IDENTITY, "validated"),
    ("dvd", 11080, STRUCTURED_ID, "known_bias"),
    ("dvd", 5541, IDENTITY, "unvalidated"),
    ("dvd", None, IDENTITY, "unvalidated"),
    ("dvd", 5540, {**IDENTITY, "firmware": "NYA3"}, "unvalidated"),
    ("dvd", 5540, {**IDENTITY, "drive": "OTHER DVD-RAM GH70N"}, "unvalidated"),
    ("dvd", 5540, {**IDENTITY, "drive": "HL-DT-ST DVD-RAM GH70N2"}, "unvalidated"),
    ("cd", 5540, IDENTITY, "unvalidated"),
    ("bd", 5540, IDENTITY, "unvalidated"),
])
def test_bundled_registry_key(tmp_path, monkeypatch, media, speed, identity, status):
    monkeypatch.chdir(tmp_path)
    check = geo_speed.check(identity, media, speed)
    assert check["status"] == status
    if status == "known_bias":
        assert check["source"].endswith("/level4/RESULT.md")
    if status == "validated":
        assert "0.106°" in check["evidence"]


@pytest.mark.parametrize("document", [None, "{", "[]", "{}", '{"geo_read_speed": {}}',
                                      '{"geo_read_speed": [null, {}, {"media": "dvd"}]}'])
def test_missing_or_bad_workspace_registry_falls_back(tmp_path, monkeypatch, document):
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "presets" / "drives.json"
    registry.parent.mkdir()
    if document is not None:
        registry.write_text(document, encoding="utf-8")
    assert geo_speed.check(IDENTITY, "dvd", 5540, root=tmp_path)["status"] == "unvalidated"
    assert geo_speed.check(IDENTITY, "dvd", 5540)["status"] == "validated"


def test_workspace_registry_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "presets" / "drives.json"
    registry.parent.mkdir()
    entry = dict(vendor="HL-DT-ST", product="DVD-RAM GH70N", firmware="NYA2", media="dvd",
                 requested_kBps=5540, status="validated", evidence="workspace evidence", source="local.md")
    registry.write_text(json.dumps({"geo_read_speed": [{**entry, "evidence": []}, entry]}), encoding="utf-8")
    assert geo_speed.check(IDENTITY, "dvd", 5540)["evidence"] == "workspace evidence"
    assert geo_speed.check(IDENTITY, "dvd", 11080)["status"] == "known_bias"
    assert geo_speed.check(IDENTITY, "dvd", 5540, simulated=True)["status"] == "unvalidated"
    assert read_completion.resolve(IDENTITY)[1]["origin"] == "registry"


def test_installed_wheel_registry_location(tmp_path, monkeypatch):
    package = tmp_path / "site-packages" / "discprobe"
    packaged = package / "_presets" / "drives.json"
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes((ROOT / "presets" / "drives.json").read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(geo_speed, "__file__", str(package / "geo_speed.py"))
    monkeypatch.setattr(read_completion, "__file__", str(package / "read_completion.py"))
    assert geo_speed.check(IDENTITY, "dvd", 5540)["status"] == "validated"
    assert geo_speed.check(IDENTITY, "dvd", 11080)["status"] == "known_bias"


@pytest.mark.parametrize("speed,status", [(5540, "validated"), (11080, "known_bias"), (3324, "unvalidated")])
def test_geo_and_guide_notices(tmp_path, monkeypatch, capsys, speed, status):
    from discprobe import __main__ as cli
    from discprobe import device

    dev = SimDrive(seed=7)
    dev.name = "fixture"
    monkeypatch.setattr(device, "raise_priority", lambda: None)
    monkeypatch.setattr(cli, "_open", lambda _args: dev)
    monkeypatch.setattr(cli, "_identity", lambda *_args: IDENTITY)
    monkeypatch.setattr(guide, "optical_drives", lambda: [])
    main(["geo", "--speed", str(speed), "--seed", "7", "--out", str(tmp_path), "--lang", "en"])
    terminal = capsys.readouterr().out
    saved = json.loads(next(tmp_path.glob("geo-*/summary.json")).read_text(encoding="utf-8"))
    record, check = saved["read_speed"], saved["speed_check"]
    assert check["status"] == status
    assert record == {"media": "dvd", "requested_kBps": speed,
                      "requested_multiple": speed / 1385, "period_ms": saved["fit"]["period_ms"], **IDENTITY}
    assert saved["set_cd_speed"]["requested_kBps"] == speed
    lines = guide.guide_lines(out=str(tmp_path))
    if status == "validated":
        assert check["note"] is None
        assert "read speed has not been grid-validated" not in terminal
        assert "Known read-speed bias" not in terminal
        assert not any("read speed" in line or "read-speed bias" in line for line in lines)
    else:
        note = check["note"]
        assert terminal.count(note) == 2
        assert terminal.index(note) < terminal.index("Spindle settled") < terminal.rindex(note)
        assert any(line.strip() == note for line in lines)
        previous = i18n.active()
        try:
            i18n.use("zh")
            note_zh = geo_speed.notice(check)
            assert ("约为 0.3°" if status == "known_bias" else "未经网格验证") in note_zh
            assert any(line.strip() == note_zh for line in guide.guide_lines(out=str(tmp_path)))
        finally:
            i18n.use(previous)
        if status == "known_bias":
            assert "--speed 5540 (4x)" in note


@pytest.mark.parametrize("media,mode,extra,speed,multiple,clv", [
    ("dvd", "cav", ["--speed", "8x"], 11080, 8, False),
    ("dvd", "cav", ["--speed", "keep"], None, None, False),
    ("cd", "cav", [], 1411, 8, False),
    ("cd", "clv", ["--cd-clv", "--linear-mm-s", "19200"], 1411, 8, True),
    ("bd", "clv", [], 8990, 2, True),
    ("bd", "cav", [], 8990, 2, False),
])
def test_simulated_geo(tmp_path, media, mode, extra, speed, multiple, clv):
    run = subprocess.run([sys.executable, "-m", "discprobe", "geo", "--sim", mode, "--media", media,
                          *extra, "--seed", "7", "--out", str(tmp_path), "--lang", "zh"],
                         cwd=ROOT, capture_output=True, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.count("这个读速未经网格验证。") == 2
    saved = json.loads(next(tmp_path.glob("geo-*/summary.json")).read_text(encoding="utf-8"))
    assert saved["simulated"] is True and saved["identity"] is None
    assert saved["speed_check"] == {"status": "unvalidated", "note": geo_speed.UNVALIDATED}
    read_speed = saved["read_speed"]
    assert (read_speed["media"], read_speed["requested_kBps"], read_speed["requested_multiple"]) == (media, speed, multiple)
    assert read_speed["drive"].startswith("SIM-") and read_speed["firmware"] is None
    assert saved.get("set_cd_speed") is None
    if clv:
        assert read_speed["period_ms"] is None
        assert read_speed["period_ms_by_zone"] == [
            {"lba": z["lba"], "period_ms": z["period_ms"]} for z in saved["period"]["zones"] if z.get("period_ms") is not None]
        assert len(read_speed["period_ms_by_zone"]) >= 5
    else:
        assert read_speed["period_ms"] == saved["fit"]["period_ms"] > 0
