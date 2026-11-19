import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from discprobe import burner, device, disc_identity, eraser, info, webui
from discprobe.drive_lock import FileLocked, drive_locks, file_lock
from tests.iso_fixture import write_checked_iso


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
    write_checked_iso(image, bytes(32 * 2048))
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
    write_checked_iso(image, bytes(32 * 2048))
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


@pytest.mark.parametrize("log_blocked", [True, False])
def test_r1_burn_preflight_and_adapter_check_locked_identity(tmp_path, monkeypatch, r1_media, log_blocked):
    medium, _ = r1_media
    medium.blank = True
    drive = "/dev/r1-fake"
    expected = disc_identity.read_identity(drive)
    image = write_checked_iso(tmp_path / "sample.iso", bytes(32 * 2048))
    log = Path(str(image) + ".burn.jsonl")
    checks = []
    launch = Mock()
    monkeypatch.setattr(burner, "tool", lambda name: name)
    recorder = burner.LinuxBurner(drive, "dvd", popen=launch, run=lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="Mounted Media: DVD\nDisc status: blank\nFree Blocks: 4096\nWrite Speed #1: 4x", stderr=""))
    real_check = disc_identity.check_identity
    real_write = recorder.write

    def check(drive, identity, **kwargs):
        assert log.is_file()
        assert any(row["locked"] and row["action"] == "burn" for row in drive_locks([drive]))
        with pytest.raises(FileLocked), file_lock(Path(str(image) + ".lock")):
            pytest.fail("burn preflight released its image lock")
        checks.append(medium.identifier)
        real_check(drive, identity, **kwargs)

    def late_swap(*args, **kwargs):
        medium.identifier = "05060708"
        return real_write(*args, **kwargs)

    monkeypatch.setattr(disc_identity, "check_identity", check)
    monkeypatch.setattr(recorder, "write", late_swap)
    if log_blocked:
        log.mkdir()
    error = OSError if log_blocked else disc_identity.DiscChanged
    with pytest.raises(error):
        burner.burn(drive, image, yes_write=True, recorder=recorder, expected_identity=expected)
    assert checks == ([] if log_blocked else ["01020304", "05060708"])
    launch.assert_not_called()


def test_r1_gh70n_saved_read_has_mid_but_no_valid_disc_identification():
    path = Path(__file__).resolve().parents[1] / "evidence/drive/info_blank_ritekf1.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    identity = disc_identity.from_info(report)
    assert {key: identity[key] for key in ("profile", "mid", "medium_id", "capacity_sectors", "blank", "rewritable")} == {
        "profile": 0x11, "mid": "RITEKF1", "medium_id": None, "capacity_sectors": 2297888,
        "blank": True, "rewritable": False,
    }


def test_r1_erasing_a_write_once_disc_says_it_cannot_be_erased():
    # DVD-R (profile 0x11): a write-once disc gets its own words, not the "not enough identity" refusal
    identity = dict(media="dvd", profile=0x11, blank=False, rewritable=False, read_at_ns=1,
                    capacity_sectors=2298496, mid="RITEKF1")
    with pytest.raises(disc_identity.DiscChanged, match="这张盘不能擦除") as error:
        disc_identity.require_identity(identity, erasing=True)
    assert "only rewritable discs" in str(error.value)
    assert disc_identity.require_identity(identity) is identity      # burning it is still allowed


@pytest.mark.parametrize(("sense", "words"), [
    ("2/3A/00", "No disc in the drive"), ("2/3A/02", "tray is open"), ("2/3A/01", "finds no disc"),
    ("2/04/01", "not ready yet")])
def test_r1_empty_or_loading_drive_says_so_instead_of_missing_identity(sense, words):
    # With no disc the refusal should name the real cause, as info does, not "not enough identity".
    identity = disc_identity.from_info({"test_unit_ready": {"status": 2, "sense": sense}})
    with pytest.raises(disc_identity.DiscChanged, match=words) as error:
        disc_identity.require_identity(identity)
    assert "Not enough disc identity" not in str(error.value)
    assert disc_identity.matches(identity, {**identity, "not_ready": None}) is True  # not an identity field


def test_r1_other_tur_failures_keep_the_identity_refusal():
    identity = disc_identity.from_info({"test_unit_ready": {"status": 2, "sense": "3/11/00"}})
    with pytest.raises(disc_identity.DiscChanged, match="Not enough disc identity"):
        disc_identity.require_identity(identity)


def test_r1_refusal_before_the_burn_log_is_quiet(tmp_path, monkeypatch, capsys):
    image = write_checked_iso(tmp_path / "sample.iso", bytes(32 * 2048))
    monkeypatch.setattr(disc_identity, "read_identity", lambda drive: disc_identity.from_info(
        {"test_unit_ready": {"status": 2, "sense": "2/3A/00"}}))
    args = SimpleNamespace(drive="X:", iso=str(image), media="dvd", speed=None, yes_write=True, no_verify=False,
                           keep_open=False, append=False, expect_start=None, erase=False, cd_sector=None,
                           disc_id=False, disc_id_code=None, work=None)
    from discprobe import works_link
    monkeypatch.setattr(works_link, "check_work", lambda args: None)
    with pytest.raises(SystemExit, match="No disc in the drive"):
        burner.run(args)
    assert "Could not save failed burn record" not in capsys.readouterr().err
    assert not Path(str(image) + ".burn.jsonl").exists()
    assert (tmp_path / "sample.iso.diagnostics").is_dir()


def test_empty_drive_stop_advises_inserting_the_disc():
    from discprobe import diagnostics, mmc
    for reason in (mmc.NO_DISC, mmc.TRAY_OPEN, mmc.NOT_RECOGNISED, mmc.LOADING):
        assert diagnostics.advice(f"x / {reason}.").startswith("Put the disc in")
    assert "last resort" in diagnostics.advice("Not enough disc identity information to authorize writing.")
