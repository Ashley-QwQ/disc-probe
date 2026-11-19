import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from discprobe import burner, device, disc_identity, eraser, info, webui
from discprobe.drive_lock import drive_locks


@pytest.fixture
def r1_media(tmp_path, monkeypatch):
    medium = SimpleNamespace(identifier="01020304", blank=False, capacity=4096, mid="SAMPLE")
    reads = []

    class ReadOnlyDevice:
        def __init__(self, drive):
            self.drive = drive

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    def snapshot(dev):
        action = next(row["action"] for row in drive_locks([dev.drive]) if row["locked"])
        reads.append((action, medium.identifier))
        raw = bytearray(34)
        raw[:2] = (32).to_bytes(2, "big")
        if medium.identifier is not None:
            raw[7] = 0x80
            raw[12:16] = bytes.fromhex(medium.identifier)
        report = {
            "test_unit_ready": {"status": 0},
            "configuration": {"status": 0, "parsed": {"current_profile": 0x1A}},
            "disc_information": {"status": 0, "raw": raw.hex(),
                                 "parsed": {"erasable": True, "disc_status": "empty" if medium.blank else "complete"}},
        }
        if medium.capacity is not None:
            report["capacity"] = {"status": 0, "parsed": {"last_lba": medium.capacity - 1}}
        if medium.mid:
            report["dvd_plus_adip_11"] = {"status": 0, "parsed": {
                "manufacturer_id": medium.mid, "media_type_id": "RW", "product_revision": 1}}
        return report

    monkeypatch.setattr(device, "Device", ReadOnlyDevice)
    monkeypatch.setattr(info, "quick", snapshot)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user-state"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "user-state"))
    monkeypatch.delenv(disc_identity.EXPECTED_ENV, raising=False)
    return medium, reads


@pytest.mark.parametrize(("action", "swap"), [
    ("erase", True), ("erase", False), ("burn", True), ("burn", False),
], ids=["erase_swap_rejected", "erase_same_disc", "burn_swap_rejected", "burn_same_disc"])
def test_r1_core_checks_web_grant_after_taking_write_lock(tmp_path, monkeypatch, r1_media, action, swap):
    medium, reads = r1_media
    medium.blank = action == "burn"
    drive = "/dev/r1-fake"
    image = tmp_path / "iso" / "sample.iso"
    image.parent.mkdir()
    image.write_bytes(bytes(32 * 2048))
    launches = []
    refused = []
    monkeypatch.setattr(eraser, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(eraser, "tool", lambda name: name)
    monkeypatch.setattr(burner, "tool", lambda name: name)

    def launch(argv, **kwargs):
        launches.append((argv[0], medium.identifier))
        if action == "erase":
            medium.blank = True
        return Mock(stdout=(), wait=Mock(return_value=0))

    recorder = burner.LinuxBurner(drive, "dvd", popen=launch, run=lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="Mounted Media: DVD\nDisc status: blank\nFree Blocks: 4096\nWrite Speed #1: 4x", stderr=""))
    monkeypatch.setattr(eraser.subprocess, "Popen", launch)

    def runner(argv, **kwargs):
        packed = json.loads(kwargs["env"][disc_identity.EXPECTED_ENV])
        assert packed["drive"] == drive and packed["identity"]["medium_id"] == "01020304"
        if swap:
            # The web checks saw the same disc. Change the reported identity only before the core takes over.
            medium.identifier = "05060708"
        try:
            if action == "erase":
                eraser.erase(drive, expected_identity=packed["identity"])
            else:
                burner.burn(drive, image, yes_write=True, no_verify=True, recorder=recorder,
                            state_checker=lambda *a, **k: dict(status="completed"), expected_identity=packed["identity"])
        except disc_identity.DiscChanged as exc:
            refused.append(str(exc))
        return Mock(wait=Mock(return_value=int(bool(refused))))

    backend = webui.Backend(tmp_path, runner=runner, drive_provider=lambda: [dict(id=drive)])
    backend.verified_blank[drive] = (float("inf"), "dvd")
    payload = dict(action=action, media="dvd", drive=drive,
                   args={"iso": "iso/sample.iso"} if action == "burn" else {})
    try:
        token = backend.burn_token(payload)["token"]
        job = backend.jobs[backend.start(dict(payload, burn_token=token))["job"]]
        assert job.finished.wait(3)
        assert job.exit == int(swap)
    finally:
        backend.close()
    assert reads[:2] == [("disc", "01020304"), ("disc", "01020304")]
    assert (action, medium.identifier) in reads[2:]
    if swap:
        assert refused == [str(disc_identity.DiscChanged())]
        assert launches == []
    else:
        assert launches == [("dvd+rw-format" if action == "erase" else "growisofs", "01020304")]


@pytest.mark.parametrize("missing", ["identifier", "size"])
def test_r1_missing_stable_evidence_refuses_an_erase_permit(tmp_path, r1_media, missing):
    medium, _ = r1_media
    if missing == "identifier":
        medium.identifier = medium.mid = None
    else:
        medium.capacity = None
    drive = "X:"
    backend = webui.Backend(tmp_path, drive_provider=lambda: [dict(id=drive)])
    try:
        with pytest.raises(webui.APIError, match="无法读取足够的光盘身份信息") as error:
            backend.burn_token(dict(action="erase", drive=drive))
        assert error.value.status == 409
        assert not backend.tokens
    finally:
        backend.close()


def test_r1_windows_erase_checks_identity_before_powershell(monkeypatch, r1_media):
    medium, reads = r1_media
    drive = "X:"
    expected = disc_identity.read_identity(drive)
    monkeypatch.setattr(eraser, "sys", SimpleNamespace(platform="win32"))
    launch = Mock()
    monkeypatch.setattr(eraser.subprocess, "Popen", launch)

    def locate_helper(name):
        medium.identifier = "05060708"
        return name

    monkeypatch.setattr(eraser, "tool", locate_helper)
    with pytest.raises(disc_identity.DiscChanged, match="光驱里的盘和确认时的不是同一张"):
        eraser.erase(drive, expected_identity=expected)
    assert reads[-1] == ("erase", "05060708")
    launch.assert_not_called()


def test_r1_cli_erase_and_burn_keeps_initial_identity(tmp_path, monkeypatch, r1_media):
    from discprobe import __main__ as cli

    medium, reads = r1_media
    image = tmp_path / "cli.iso"
    image.write_bytes(bytes(32 * 2048))
    recorder = SimpleNamespace(inspect=Mock(return_value=dict(blank=False, rewritable=True, speeds_x=[4])),
                               write=Mock(), erase=Mock())
    recorder.inspect.return_value.update(media="dvd", capacity_sectors=4096)

    def supply_recorder(*a):
        assert reads == [("disc", "01020304")]
        medium.identifier = "05060708"
        return recorder

    monkeypatch.setattr(burner, "adapter", supply_recorder)
    args = cli._build_parser()[0].parse_args(
        ["burn", "--drive", "X:", "--iso", str(image), "--yes-write", "--erase"])
    with pytest.raises(SystemExit, match="光驱里的盘和确认时的不是同一张"):
        burner.run(args)
    assert reads[-1] == ("burn", "05060708")
    recorder.erase.assert_not_called()
    recorder.write.assert_not_called()


def test_r1_gh70n_saved_read_has_mid_but_no_valid_disc_identification():
    path = Path(__file__).resolve().parents[1] / "evidence/drive/info_blank_ritekf1.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    identity = disc_identity.from_info(report)
    assert {key: identity[key] for key in ("profile", "mid", "medium_id", "capacity_sectors", "blank", "rewritable")} == {
        "profile": 0x11, "mid": "RITEKF1", "medium_id": None, "capacity_sectors": 2297888,
        "blank": True, "rewritable": False,
    }
