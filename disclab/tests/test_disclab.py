"""Small, isolated lab checks: no real devices, shared lab mutation or full-disc ISOs."""
from __future__ import annotations

import argparse
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import HTTPError

import numpy as np
import pytest

from disclab.__main__ import ROOT, lab_env
from disclab.box import make_box
from disclab.drive import LabDrive
from disclab.lab import Lab, atomic_json
from disclab.physics import Disc
from discprobe import mmc
from discprobe.scsi import DATA_IN, Sense


@pytest.fixture
def lab(tmp_path):
    lab = Lab(tmp_path / "lab with spaces")
    make_box(lab, "dvd-r", 3, seed=17)
    with lab.locked_state() as state:
        state["drives"]["X:"]["tray"] = lab.box()["discs"][0]
    return lab


def run_dp(lab, *args):
    # The dp CLI must itself start with the hook; its child inherits lab_env too.
    result = subprocess.run(
        [sys.executable, "-B", "-m", "disclab", "dp", "--lab", str(lab.root), "--", *map(str, args)],
        cwd=ROOT, env=lab_env(lab), capture_output=True, text=True, encoding="utf-8", timeout=35,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture
def burned(lab, tmp_path):
    iso = tmp_path / "tiny random.iso"
    run_dp(lab, "random", "--sectors", "4096", "--seed", "23", "--output", iso)
    assert iso.stat().st_size == 4096 * 2048
    with iso.open("rb") as image:
        image.seek(16 * 2048 + 1)
        assert image.read(5) == b"CD001"
    result = run_dp(lab, "burn", "--drive", "X:", "--iso", iso, "--yes-write")
    return lab, iso, result


def test_truth_stays_in_answers(lab):
    box, answers = lab.box(), lab.answers()
    assert box["count"] == len(box["discs"]) == len(answers["discs"]) == 3
    assert answers["seed"] == 17
    for truth in answers["discs"].values():
        assert {"u", "v", "b_nm", "ecc_um", "ecc_deg", "varpitch_r_mm", "varpitch_deg"} <= truth.keys()

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    assert not any(k in {"u", "v", "b_nm"} or k.startswith(("ecc", "varpitch")) for k in keys(box))
    # Labels must not leak the numeric truth under another name either.
    public = json.dumps(box)
    for truth in answers["discs"].values():
        for key in ("u", "v", "b_nm", "ecc_um", "ecc_deg", "varpitch_r_mm", "varpitch_deg"):
            assert json.dumps(truth[key]) not in public


def test_blank_info_in_hooked_child(lab):
    out = lab.root / "results"
    result = run_dp(lab, "info", "--drive", "X:", "--out", out)
    report, = out.glob("info-*/info.json")
    info = json.loads(report.read_text(encoding="utf-8"))
    assert info["configuration"]["parsed"]["current_profile"] == 0x11
    assert info["configuration"]["parsed"]["current_profile_name"] == "DVD-R Sequential"
    assert info["dvd_prerecorded_0e"]["parsed"]["manufacturer_id"].strip() == "DLABR01"
    assert info["disc_information"]["parsed"]["disc_status"] == "empty"
    truth = lab.disc_truth(lab.box()["discs"][0])
    assert info["track_1"]["parsed"]["free_blocks"] == truth["capacity"]
    inquiry = info["inquiry"]["parsed"]
    assert f"{inquiry['vendor']} {inquiry['product']}" == "DISCLAB GH70N-LIKE"
    assert "DISCLAB GH70N-LIKE" in result.stdout


def test_small_iso_burn_round_trip(burned):
    lab, iso, result = burned
    match = re.search(r"Read-back sample: (\d+) blocks ok / (\d+) differing / (\d+) unreadable", result.stdout)
    assert match, result.stdout
    assert 0 < int(match[1]) <= 96
    assert match.groups()[1:] == ("0", "0")
    burn = lab.state()["burns"][lab.box()["discs"][0]]
    assert burn["closed"] is True
    session, = burn["sessions"]
    assert Path(session["iso"]) == iso
    assert session["start_lba"] == 0
    assert session["sectors"] == 4096
    assert session["iso_size"] == iso.stat().st_size
    expected = iso.read_bytes()
    with LabDrive(lab, "X:") as drive:
        # Include descriptors and both ends, rather than just one zero-filled block.
        for lba in (0, 16, 17, 20, 127, 2048, 4080):
            count = 16
            reply = drive.execute(mmc.read10(lba, count), count * 2048, DATA_IN)
            assert reply.ok, reply.sense
            assert reply.data == expected[lba * 2048:(lba + count) * 2048]
        for lba, count in ((4096, 1), (4095, 2)):
            reply = drive.execute(mmc.read10(lba, count), count * 2048, DATA_IN)
            assert not reply.ok and reply.sense == Sense(5, 0x21, 0)


def test_hook_refuses_real_drive_and_lists_only_lab(lab):
    script = """
import json, sys
from discprobe.device import list_optical_drives
if sys.platform == 'win32':
    from discprobe.spti import SptiDevice as Device
else:
    from discprobe.sg import SgDevice as Device
try:
    Device('E:')
except OSError as exc:
    assert 'not a lab drive' in str(exc), str(exc)
else:
    raise AssertionError('real drive was allowed')
assert list_optical_drives() == ['X:'], list_optical_drives()
print(json.dumps(dict(drives=list_optical_drives(), refused=True)))
"""
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=lab_env(lab),
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"drives": ["X:"], "refused": True}


def test_true_placement_and_spiral_inverse(lab):
    from disclab.score import placement

    disc = Disc(lab.disc_truth(lab.box()["discs"][0]), {"write_offset_bits": 0.0})
    # The box has real variable pitch; give placement its matching truth correction (degrees).
    corr = lambda r: np.interp(r, disc.vp_r, disc.vp_deg)
    _, eps = placement(disc, disc.u, disc.v, corr)
    assert np.max(np.abs(eps - eps.mean())) < 1e-9
    rng = np.random.default_rng(514)
    bits = rng.uniform(1, disc.t["capacity"] * disc.bps, 12)
    recovered = disc.bit_at(disc.radius(bits), disc.alpha(bits))
    assert np.all(np.abs(recovered - bits) <= 1.0)


def test_flaw_arc_sense_and_retry_timing(burned):
    lab, _, _ = burned
    disc_id = lab.box()["discs"][0]
    answers = lab.answers()
    truth = answers["discs"][disc_id]
    disc = Disc(truth, lab.state()["burns"][disc_id])
    lba = 1024
    n = (lba + 0.5) * disc.bps
    r = float(disc.data_radius(n))
    angle = math.degrees(float(disc.alpha(n))) % 360
    truth["flaw"] = {"r_mm": [r - 0.0001, r + 0.0001], "deg": [angle - 0.1, angle + 0.1]}
    atomic_json(lab.answers_path, answers)
    with LabDrive(lab, "X:") as drive:
        reply = drive.execute(mmc.read10(lba), 2048, DATA_IN)
        assert not reply.ok and reply.sense == Sense(3, 0x11, 0)
        assert reply.duration_us / 1e6 >= 1.5
        # A different point on that spiral still reads normally.
        assert drive.execute(mmc.read10(0), 2048, DATA_IN).ok


def test_small_photo_from_real_burn_map(burned):
    from disclab import burnmap, photos

    lab, _, _ = burned
    disc_id = lab.box()["discs"][0]
    # Recorder already extracts a map; exercise extraction explicitly from the small ISO too.
    path = burnmap.extract_map(lab, disc_id)
    assert path.is_file()
    bmap, _, _, _ = burnmap.load_map(lab, disc_id)
    assert np.any(bmap != burnmap.BLANK)
    image, focal, record = photos.render(lab, disc_id, photos.Pose(width=640, height=480, dist_mm=600))
    assert image.shape == (480, 640, 3)
    assert image.dtype == np.uint8
    assert image.min() < image.max()
    assert focal > 0 and record["disc"] == disc_id


@pytest.mark.parametrize("port", [8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879, 0, 65536])
def test_web_refuses_forbidden_ports(port, monkeypatch, lab):
    from disclab import web

    popen = Mock()
    monkeypatch.setattr(web.subprocess, "Popen", popen)
    with pytest.raises(argparse.ArgumentTypeError):
        web.serve(lab, port)
    popen.assert_not_called()


def test_web_launch_and_interrupt(lab, monkeypatch, capsys):
    from disclab import web

    child = Mock()
    child.wait.side_effect = [KeyboardInterrupt, 0]
    child.poll.side_effect = [None, 0]
    popen = Mock(return_value=child)
    monkeypatch.setattr(web.subprocess, "Popen", popen)
    assert web.serve(lab, 8853, "dvd") == 0
    args, kwargs = popen.call_args
    assert args[0] == [sys.executable, "-B", "-m", "discprobe", "webui", "--local-only", "--port", "8853",
                       "--out", "results", "--media", "dvd"]
    assert kwargs["cwd"] == lab.root
    assert kwargs["env"]["DISCPROBE_DISCLAB"] == str(lab.root)
    assert str(ROOT / "disclab" / "boot") in kwargs["env"]["PYTHONPATH"]
    child.send_signal.assert_called_once_with(web.signal.CTRL_BREAK_EVENT if os.name == "nt" else web.signal.SIGINT)
    assert "http://127.0.0.1:8853/" in capsys.readouterr().out


class Reply(io.BytesIO):
    code = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())


def test_upload_phone_wire_shape_and_computer_auth(tmp_path, monkeypatch, capsys):
    from disclab import web

    photo = tmp_path / "disc + \u6d4b\u8bd5.jpg"
    photo.write_bytes(b"raw JPEG bytes")
    desk, phone = Mock(), Mock()
    desk.open.side_effect = [Reply({"url": "http://192.0.2.1:8853/phone/photo-capability"}),
                             Reply({"photos": [{"name": photo.name}]})]
    phone.open.side_effect = [Reply({}), Reply({"id": "uploaded"})]
    monkeypatch.setattr(web, "build_opener", Mock(side_effect=[desk, phone]))
    assert web.upload("http://127.0.0.1:8853/home/?token=desktop-secret", "geo-X-1", [photo]) == 0
    link = desk.open.call_args_list[0].args[0]
    assert link.get_method() == "GET" and link.full_url.endswith("/api/phone-link?run=geo-X-1")
    assert link.get_header("X-discprobe-token") == "desktop-secret"
    assert phone.open.call_args_list[0].args[0] == "http://127.0.0.1:8853/phone/photo-capability"
    sent = phone.open.call_args_list[1].args[0]
    assert sent.get_method() == "POST" and sent.full_url.endswith("/api/photos?run=geo-X-1")
    assert sent.data == photo.read_bytes()
    assert sent.get_header("Content-type") == "image/jpeg"
    assert sent.get_header("X-photo-token") == "photo-capability"
    assert sent.get_header("X-filename") == "disc%20%2B%20%E6%B5%8B%E8%AF%95.jpg"
    listing = desk.open.call_args_list[-1].args[0]
    assert listing.get_method() == "GET" and listing.full_url.endswith("/api/photos?run=geo-X-1")
    assert listing.get_header("X-discprobe-token") == "desktop-secret"
    assert listing.get_header("X-photo-token") is None
    assert "uploaded" in capsys.readouterr().out


def test_upload_prints_failed_reply_and_final_listing(tmp_path, monkeypatch, capsys):
    from disclab import web

    photo = tmp_path / "duplicate.jpg"
    photo.write_bytes(b"jpeg")
    desk, phone = Mock(), Mock()
    desk.open.side_effect = [Reply({"url": "http://localhost:8853/phone/cap"}), Reply({"photos": []})]
    phone.open.side_effect = [Reply({}), HTTPError("http://localhost", 409, "duplicate", {},
                                                io.BytesIO(b'{"code":"duplicate_photo"}'))]
    monkeypatch.setattr(web, "build_opener", Mock(side_effect=[desk, phone]))
    assert web.upload("http://localhost:8853", "geo-X-1", [photo]) == 1
    output = capsys.readouterr().out
    assert "HTTP 409" in output and "duplicate_photo" in output and "Computer photos:" in output


def test_upload_reports_unavailable_phone_link(tmp_path, monkeypatch):
    from disclab import web

    photo = tmp_path / "disc.jpg"
    photo.write_bytes(b"jpeg")
    desk = Mock()
    desk.open.return_value = Reply({"url": None, "addresses": [], "address": None})
    monkeypatch.setattr(web, "build_opener", Mock(return_value=desk))
    with pytest.raises(ValueError, match="local-only"):
        web.upload("http://localhost:8853", "geo-X-1", [photo])


def test_open_handle_follows_tray_changes(tmp_path):
    # disc-probe's swap keeps one handle and polls TEST UNIT READY while the person changes the disc.
    from disclab.__main__ import main
    lab = Lab(tmp_path / "swap")
    main(["box", "--lab", str(lab.root), "--count", "2", "--seed", "3"])
    first, second = lab.box()["discs"]
    main(["tray", "--lab", str(lab.root), "--drive", "X:", "--disc", first])
    tur = bytes(6)
    with LabDrive(lab, "X:") as drive:
        assert drive.execute(tur).ok and drive.disc_id == first
        main(["tray", "--lab", str(lab.root), "--drive", "X:", "--open"])
        opened = drive.execute(tur)
        assert (opened.sense.key, opened.sense.asc, opened.sense.ascq) == (2, 0x3A, 0x02)
        main(["tray", "--lab", str(lab.root), "--drive", "X:", "--disc", second])
        changed = drive.execute(tur)
        assert (changed.sense.key, changed.sense.asc) == (6, 0x28)
        assert drive.execute(tur).ok and drive.disc_id == second
