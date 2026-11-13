"""Drive-free photo contract tests. Test HTTP servers live only inside these fixtures."""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from PIL import Image

from discprobe import photo, qr, webui

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path("D:/disc-probe/docs/goals/photo-calibration")


def listed(row):
    return {**row, "verdict": None, "status": None, "reason": None}


def test_lan_ips_are_private_unique_and_stable():
    addresses = ["192.168.1.20", "127.0.0.1", "169.254.1.2", "8.8.8.8", "10.0.0.5",
                 "172.16.2.1", "192.168.1.20", "0.0.0.0", "255.255.255.255", "224.0.0.1"]
    candidates = [(None, None, None, None, (a, 0)) for a in addresses]
    with patch.object(photo.socket, "getaddrinfo", return_value=candidates):
        assert photo.lan_ips() == ["10.0.0.5", "172.16.2.1", "192.168.1.20"]
        assert photo.lan_ip() == "10.0.0.5"
    with patch.object(photo.socket, "getaddrinfo", side_effect=OSError):
        assert photo.lan_ips() == [] and photo.lan_ip() is None


def test_lan_ips_put_the_default_route_first():
    """A Hyper-V/WSL switch (172.x) sorts before the Wi-Fi address; phones can only reach the Wi-Fi one."""
    candidates = [(None, None, None, None, (a, 0)) for a in ("172.29.80.1", "192.168.0.101")]

    class Probe:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def connect(self, where): assert where[0] == "192.0.2.1"
        def getsockname(self): return ("192.168.0.101", 50000)
    with patch.object(photo.socket, "getaddrinfo", return_value=candidates), patch.object(photo.socket, "socket", Probe):
        assert photo.lan_ips() == ["192.168.0.101", "172.29.80.1"]


@pytest.mark.parametrize("flags, lan", [([], True), (["--lan"], True), (["--local-only"], False),
                                         (["--lan", "--local-only"], False)])
def test_webui_lan_default_and_local_only(flags, lan, capsys):
    from discprobe.__main__ import main
    # Exercise the real parser and run(), but bind no socket and enumerate no drives.
    with patch.object(webui, "Backend"), patch.object(webui, "Server") as server:
        instance = server.return_value.__enter__.return_value
        instance.server_port = 45678
        instance.token = "session" if lan else None
        main(["webui", *flags])
        assert server.call_args.kwargs["lan"] is lan
        assert "http://127.0.0.1:45678/home/" + ("?token=session" if lan else "") in capsys.readouterr().out


def test_chosen_lan_address_validation(tmp_path):
    with serving(tmp_path, lan=True) as s, patch.object(photo, "lan_ips", return_value=["10.0.0.2", "192.168.1.10"]):
        session = {"X-Discprobe-Token": s.token}
        code, link = json_request(s, "GET", "/api/phone-link?run=geo-test&address=192.168.1.10", headers=session)
        assert code == 200 and link["url"].startswith("http://192.168.1.10:")
        assert link["addresses"] == ["10.0.0.2", "192.168.1.10"] and link["address"] == "192.168.1.10"
        for address in ("", "evil.test", "127.0.0.1", "192.168.1.11", "192.168.1.10%3A80%40evil.test"):
            assert request(s, "GET", "/api/phone-link?run=geo-test&address=" + address, headers=session)[0] == 400


def test_burn_event_records_selected_path_without_drive_access(tmp_path):
    job = webui.Job("fixture", "TEST:", tmp_path)
    job.action, job.media, job.args = "burn", "cd", {"cd_sector": "mode2form1"}
    job.events.write_text(json.dumps(dict(type="burn_result", result="completed")) + "\n", encoding="utf-8")
    with patch.object(webui.sys, "platform", "win32"):
        job.read()
    result = job.history[0]
    assert result["burner"] == "TEST:" and result["burn_path"] == "IMAPI"
    assert result["burn_mode"] == "mode2form1; physical interleave unknown"


@pytest.fixture
def tmp_path():
    # Keep all test writes inside the checkout, including in restricted Windows sessions.
    with tempfile.TemporaryDirectory(prefix="photo-test-", dir=ROOT) as directory:
        yield Path(directory)


def png(grey=110):
    stream = io.BytesIO()
    Image.new("RGB", (48, 48), (grey, grey, grey)).save(stream, format="PNG")
    return stream.getvalue()


def photos_of(listing):
    """The photo rows of a listing; the rest (analysis, adoption, times) has its own tests."""
    return listing["photos"]


def make_run(root, name="geo-test", out="results"):
    folder = root / out / name
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps(dict(identity=dict(drive="test path"), fit=dict(u=1, v=2))), encoding="utf-8")
    return folder


def no_drives():
    raise AssertionError("photo work must not enumerate drives")


@contextlib.contextmanager
def serving(tmp_path, *, lan=False):
    make_run(tmp_path)
    make_run(tmp_path, "geo-other")
    backend = webui.Backend(tmp_path, drive_provider=no_drives)
    server = webui.Server(backend, 0, lan=lan)
    thread = threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=.01), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(3)
        server.server_close()


def request(server, method, path, data=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        conn.request(method, path, body=data, headers=headers or {})
        res = conn.getresponse()
        body = res.read()
        return res.status, body, dict(res.getheaders())
    finally:
        conn.close()


def json_request(server, method, path, data=None, headers=None):
    code, body, _ = request(server, method, path, data, headers)
    return code, json.loads(body)


def upload(server, run="geo-test", *, token=None, name="first.png", grey=110):
    headers = {"Content-Type": "image/png", "X-Filename": name}
    if token:
        headers["X-Photo-Token"] = token
    return json_request(server, "POST", "/api/photos?run=" + run, png(grey), headers)


def test_upload_list_serve_roundtrip_and_local_phone_link(tmp_path):
    with serving(tmp_path) as s:
        assert json_request(s, "GET", "/api/phone-link?run=geo-test") == (200, dict(url=None, qr_svg=None, addresses=[], address=None))
        code, first = upload(s, name="..%2F..%2F%E7%85%A7%E7%89%87.png")
        assert code == 200 and first["name"] == "照片.png"
        assert set(first) == {"id", "name", "url", "time"}
        code, second = upload(s, name="second.png", grey=120)
        assert code == 200
        code, listing = json_request(s, "GET", "/api/photos?run=geo-test")
        assert code == 200 and photos_of(listing) == [listed(first), listed(second)]
        code, body, headers = request(s, "GET", first["url"])
        assert code == 200 and body == png() and headers["Content-Type"] == "image/png"
        assert (tmp_path / "results/geo-test/photos" / (first["id"] + ".png")).read_bytes() == png()
        assert photos_of(json_request(s, "GET", "/api/photos?run=geo-other")[1]) == []
        assert request(s, "GET", first["url"].replace("geo-test", "geo-other"))[0] == 404
        assert request(s, "GET", "/api/photos?run=..%2Foutside")[0] == 404
        assert request(s, "GET", "/api/photos/geo-test/..%2Fsummary.json")[0] == 404


def test_phone_tokens_are_scoped_and_do_not_grant_main_session(tmp_path):
    with serving(tmp_path, lan=True) as s, patch.object(photo, "lan_ips", return_value=["192.168.1.10"]):
        session = {"X-Discprobe-Token": s.token}
        assert request(s, "GET", "/api/phone-link?run=geo-test")[0] == 403
        code, link = json_request(s, "GET", "/api/phone-link?run=geo-test", headers=session)
        assert code == 200 and link["qr_svg"].startswith("<svg")
        assert link == json_request(s, "GET", "/api/phone-link?run=geo-test", headers=session)[1]
        path = urlsplit(link["url"]).path
        token = path.rsplit("/", 1)[1]
        assert len(token) >= 43 and token != s.token
        code, html, headers = request(s, "GET", path)
        assert code == 200 and '拍摄标靶'.encode() in html and b"/home/photowords.mjs" in html
        assert b'capture="environment"' in html and b'__PHOTO_CONFIG__' not in html
        assert b'"run": "geo-test"' in html and 'discprobe_session=' not in headers.get('Set-Cookie', '')
        assert request(s, "GET", "/phone/wrong")[0] == 403
        code, row = upload(s, token=token)
        assert code == 200
        auth = {"X-Photo-Token": token}
        assert json_request(s, "GET", "/api/photos?run=geo-test", headers=auth)[1]["photos"] == [listed(row)]
        assert request(s, "GET", "/home/guidance.mjs", headers=auth)[0] == 200
        assert request(s, "GET", "/home/photowords.mjs", headers=auth)[0] == 200
        assert request(s, "GET", "/home/", headers=auth)[0] == 403
        assert request(s, "GET", row["url"] + "?token=" + token)[1] == png()
        assert request(s, "GET", "/api/photos?run=geo-other", headers=auth)[0] == 403
        assert upload(s, "geo-other", token=token)[0] == 403
        assert request(s, "GET", row["url"].replace("geo-test", "geo-other"), headers=auth)[0] == 403
        for route in ("/api/state", "/api/burn-token", "/api/phone-link?run=geo-other"):
            assert request(s, "GET", route, headers={"X-Discprobe-Token": token})[0] == 403
            assert request(s, "GET", route, headers=auth)[0] == 403
            assert request(s, "GET", route, headers={"Cookie": "discprobe_session=" + token})[0] == 403
        assert request(s, "POST", "/api/run?token=" + token, headers={"Content-Type": "application/json", "Content-Length": "2"})[0] == 403
        assert request(s, "GET", "/api/photos?run=geo-test", headers={"X-Photo-Token": "wrong", **session})[0] == 403
        assert request(s, "GET", "/api/photos?run=geo-test", headers={**auth, "Origin": "http://evil.test"})[0] == 403
        # Updating the calibration invalidates the old link and cannot revive it.
        (tmp_path / "results/geo-test/summary.json").write_text('{}', encoding="utf-8")
        assert request(s, "GET", path)[0] == 403
        new = json_request(s, "GET", "/api/phone-link?run=geo-test", headers=session)[1]
        assert new["url"] != link["url"]
        with patch.object(photo, "lan_ips", return_value=[]):
            assert json_request(s, "GET", "/api/phone-link?run=geo-test", headers=session)[1] == dict(url=None, qr_svg=None, addresses=[], address=None)


def test_upload_body_limit_content_type_and_auth_before_body(tmp_path):
    with serving(tmp_path) as s:
        assert request(s, "POST", "/api/photos?run=geo-test", b"x", {"Content-Type": "text/html"})[0] == 415
        assert request(s, "POST", "/api/photos?run=geo-test", b"", {"Content-Type": "image/png"})[0] == 413
        # Only the declared length is sent: a refused request must not read the oversized body.
        headers = {"Content-Type": "image/png", "Content-Length": str(max(webui.DESIGN_SIDES) + 1)}
        assert request(s, "POST", "/api/photos?run=geo-test", headers=headers)[0] == 413
        assert photos_of(json_request(s, "GET", "/api/photos?run=geo-test")[1]) == []
        for kind, extension in photo.PHOTO_TYPES.items():
            body = b"original bytes " + kind.encode()
            code, row = json_request(s, "POST", "/api/photos?run=geo-test", body, {"Content-Type": kind})
            assert code == 200
            assert (tmp_path / "results/geo-test/photos" / (row["id"] + "." + extension)).read_bytes() == body
    assert not s.backend.photos.tokens


def test_phone_devices_count_and_rotation_revoke_every_old_link(tmp_path):
    with serving(tmp_path, lan=True) as s, patch.object(photo, 'lan_ips', return_value=['192.168.1.10']):
        session = {'X-Discprobe-Token': s.token}
        link = json_request(s, 'GET', '/api/phone-link?run=geo-test', headers=session)[1]
        path = urlsplit(link['url']).path
        token = path.rsplit('/', 1)[1]
        assert json_request(s, 'GET', '/api/phone-devices?run=geo-test', headers=session)[1] == {'devices': []}
        _, _, headers = request(s, 'GET', path, headers={'User-Agent': 'Mozilla iPhone Safari/604'})
        cookie = headers['Set-Cookie'].split(';')[0]
        auth = {'X-Photo-Token': token, 'Cookie': cookie, 'User-Agent': 'Mozilla iPhone Safari/604'}
        assert json_request(s, 'POST', '/api/photos?run=geo-test', png(), {'Content-Type': 'image/png', **auth})[0] == 200
        request(s, 'GET', '/api/photos?run=geo-test', headers=auth)
        # A second browser with the same user-agent still has its own identity.
        request(s, 'GET', path, headers={'User-Agent': auth['User-Agent']})
        rows = json_request(s, 'GET', '/api/phone-devices?run=geo-test', headers=session)[1]['devices']
        assert len(rows) == 2 and rows[0]['id'] != rows[1]['id']
        row = next(r for r in rows if r['photos_sent'] == 1)
        assert row['name'] == 'iPhone · Safari' and row['last_seen'] >= row['first_seen']
        route = '/api/phone-devices/' + row['id'] + '/disconnect'
        for endpoint in ('/api/phone-devices?run=geo-test', '/api/phone-link?run=geo-test'):
            assert request(s, 'GET', endpoint, headers=auth)[0] == 403
        assert json_request(s, 'POST', route, b'{}', {'Content-Type': 'application/json', **auth})[0] == 403
        assert json_request(s, 'POST', route, b'{}', {'Content-Type': 'application/json', **session}) == (200, {'disconnected': True, 'run': 'geo-test'})
        assert request(s, 'GET', path)[0] == 403
        assert request(s, 'GET', '/api/photos?run=geo-test', headers=auth)[0] == 403
        assert json_request(s, 'POST', '/api/photos?run=geo-test', png(), {'Content-Type': 'image/png', **auth})[0] == 403
        assert json_request(s, 'GET', '/api/phone-devices?run=geo-test', headers=session)[1] == {'devices': []}
        new = json_request(s, 'GET', '/api/phone-link?run=geo-test', headers=session)[1]
        assert new['url'] != link['url'] and request(s, 'GET', urlsplit(new['url']).path)[0] == 200
        assert json_request(s, 'GET', '/api/phone-devices?run=geo-other', headers=session)[1] == {'devices': []}
        assert request(s, 'GET', '/api/phone-devices?run=missing', headers=session)[0] == 404
        assert json_request(s, 'POST', route, b'{}', {'Content-Type': 'application/json', **session})[0] == 404


def test_upload_rechecks_token_after_disconnect(tmp_path):
    make_run(tmp_path)
    store = photo.PhotoStore(tmp_path / 'results')
    token = store.token('geo-test')
    device = store.use(token, 'Android Chrome/130')
    store.disconnect(device)
    with pytest.raises(ValueError, match='expired'):
        store.upload('geo-test', png(), 'image/png', 'late.png', token=token, device_id=device)
    assert store.listing('geo-test') == {'photos': []}


@pytest.mark.parametrize("text", ["", "hello", "a" * 25, "a" * 42, "a" * 62, "a" * 84, "a" * 106,
                                 "http://192.168.123.123:65535/phone/" + "_a-7" * 11])
def test_qr_reference_decode(text):
    cv2 = pytest.importorskip("cv2", reason="OpenCV reference QR decoder is unavailable")
    import numpy as np
    pixels = np.pad(np.array(qr.matrix(text), dtype=np.uint8), 4)
    pixels = np.repeat(np.repeat((1 - pixels) * 255, 10, axis=0), 10, axis=1)
    decoded, points, _ = cv2.QRCodeDetector().detectAndDecode(pixels)
    assert points is not None and decoded == text
    assert 'viewBox=' in qr.svg(text)


def test_qr_bounds_and_known_ecc_vector():
    assert qr._ecc([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17], 10) == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]
    with pytest.raises(ValueError, match="106"):
        qr.matrix("a" * 107)


def test_photo_command_nondisc_result_and_events(tmp_path):
    pytest.importorskip("cv2")
    folder = make_run(tmp_path)
    image = tmp_path / "non disc 照片.png"
    image.write_bytes(png())
    events = tmp_path / "events.jsonl"
    process = subprocess.run([sys.executable, "-m", "discprobe", "photo", "--run", str(folder), "--media", "cd", "--photos", str(image)],
                             cwd=ROOT, env={**os.environ, "DISCPROBE_EVENTS": str(events)}, capture_output=True, text=True, timeout=45)
    assert process.returncode == 0, process.stderr
    result = json.loads((folder / "photo.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "unsure" and result["offset_mm"] is None and result["L_frames"] is None
    assert result["per_photo"][0]["reason"] and result["photos"][0]["status"] == "no_rim"
    assert result["source_geo"]["identity"] == dict(drive="test path")
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    assert any(r["type"] == "progress" and r["stage"] == "reading photo 1/1" for r in rows)
    assert any(r["type"] == "result" and r["verdict"] == "unsure" for r in rows)


def test_photo_web_job_result_and_validation(tmp_path):
    pytest.importorskip("cv2")
    with serving(tmp_path) as s:
        row = upload(s)[1]
        payload = dict(action="photo", args=dict(run="geo-test", media="dvd", photos=[row["id"]], rings_mm=None,
                                               burner="TEST:", burn_path="IMAPI", burn_mode="2048-byte data sectors"))
        code, started = json_request(s, "POST", "/api/run", json.dumps(payload), {"Content-Type": "application/json"})
        assert code == 200
        job = s.backend.get_job(started["job"])
        assert job.finished.wait(45)
        assert job.exit == 0 and job.media == "dvd" and job.result["verdict"] == "unsure"
        assert set(job.result) == {"verdict", "per_photo", "rings_mm", "offset_mm", "L_frames", "confidence", "path", "provisional_mm",
                                   "group", "adoption", "application", "seconds"}
        assert job.result["adoption"]["state"] == "none" and job.result["seconds"] >= 0
        assert job.result["per_photo"][0]["id"] == row["id"]
        assert job.result["per_photo"][0]["status"] == "no_rim"
        record = json.loads((tmp_path / "results/geo-test/photo.json").read_text(encoding="utf-8"))
        assert record["burn_path"] == dict(burner="TEST:", path="IMAPI", mode="2048-byte data sectors")
        listing = json_request(s, "GET", "/api/photos?run=geo-test")[1]
        assert listing["verdict"] == "unsure" and listing["read_photos"] == [row["id"]]
        assert listing["analysis"]["state"] == "done" and listing["analysis"]["photos"] == [row["id"]]
        assert listing["analysis"]["seconds"] == pytest.approx(job.finished_at - job.started_at, abs=0.1)
        assert listing["read_at"] >= row["time"] and listing["adoption"]["state"] == "none"
        assert listing["photos"][0] == {**row, **job.result["per_photo"][0]}
        assert any(e["type"] == "result" and e.get("step") == "photo" for e in job.history)
        for change in (dict(run="geo-other"), dict(photos=["../x"]), dict(photos=[]), dict(photos=[row["id"], row["id"]]),
                       dict(media="bd"), dict(rings_mm=[30, 29]), dict(rings_mm=[27, float("nan")]),
                       dict(burner="--help"), dict(burn_mode=[]), dict(burn_path="bad\npath")):
            with pytest.raises(webui.APIError):
                s.backend.start(dict(action="photo", args={**payload["args"], **change}))


def test_provisional_value_is_not_published(tmp_path):
    from discprobe import pcal
    folder = make_run(tmp_path)
    image = tmp_path / "photo.png"
    image.write_bytes(png())
    with patch.object(pcal, "read_photo", return_value=dict(status="ok", L_mm=1.2)):
        result = photo.analyze(folder, "cd", [("one", image)])
    assert result["verdict"] == "unsure" and result["offset_mm"] is None and result["L_frames"] is None
    assert result["provisional_mm"] == 1.2


def test_duplicate_image_cannot_be_two_independent_photos(tmp_path):
    from discprobe import pcal
    folder = make_run(tmp_path)
    first, copy = tmp_path / "first.png", tmp_path / "copy.png"
    first.write_bytes(png())
    copy.write_bytes(png())
    with patch.object(pcal, "read_photo", return_value=dict(status="ok", L_mm=1.2)) as reader:
        result = photo.analyze(folder, "cd", [("first", first), ("copy", copy)])
    assert reader.call_count == 1
    assert result["verdict"] == "unsure" and result["offset_mm"] is None
    assert result["per_photo"][1]["verdict"] == "unsure"


@pytest.mark.parametrize("media", ["cd", "dvd"])
def test_accepted_result_mapping_and_original_diagnostics(tmp_path, media):
    from discprobe import pcal
    folder = make_run(tmp_path)
    record = json.loads((Path(__file__).with_name("data") / "photo_sealed_read_v1.json").read_text(encoding="utf-8"))
    accepted = [p for p in record["photos"] if p["status"] == "ok"]
    inputs = []
    for i in range(2):
        image = tmp_path / f"shot-{i}.png"
        Image.new("RGB", (48, 48), (100 + i, 100, 100)).save(image)
        inputs.append((str(i), image))
    with patch.object(pcal, "read_photo", side_effect=accepted):
        result = photo.analyze(folder, media, inputs)
    assert result["verdict"] == "ok" and result["offset_mm"] == record["group"]["L_mm"]
    assert result["L_frames"] == (record["group"]["L_mm"] / pcal.CD_FRAME_MM if media == "cd" else None)
    assert result["rings_mm"] == [27, 30.5, 34.5, 39, 44, 50.5, 56.5]
    assert result["confidence"] is None
    assert [p["id"] for p in result["per_photo"]] == ["0", "1"]
    assert json.loads((folder / "photo.json").read_text(encoding="utf-8"))["group"] == record["group"]


def test_frozen_coverage_and_geometry_refusal():
    from discprobe import pcal
    import numpy as np
    assert pcal.CRED_SNR == 5.0
    assert pcal.covered_gap_deg(np.array([0., 1., 2.]), np.array([30., 40., 50.])) == 360
    rejected = dict(status="poor_angle_coverage", peak_z=30, votes=[[0, 30, 0, 8, 0]], L_scan_mm=1, runner_up_ratio=.2)
    assert pcal.joint([rejected] * 3)["status"] == "unknown"


def test_sealed_stored_results_reproduce_recorded_group():
    from discprobe import pcal
    fixture = Path(__file__).with_name("data") / "photo_sealed_read_v1.json"
    record = json.loads(fixture.read_text(encoding="utf-8"))
    assert record["reader_sha"] == photo.READER_SHA256
    group = pcal.combine(record["photos"])
    assert group == record["group"]
    assert group["L_mm"] == pytest.approx(-2.098289985790712, abs=1e-9)
    assert abs(group["L_mm"] - (-2.291)) <= .33


def test_sealed_blind_photos_through_command(tmp_path):
    """Optional source-photo reproduction, never substitute saved votes for this test."""
    candidates = [Path(os.environ["DISCPROBE_SEALED_PHOTOS"])] if os.environ.get("DISCPROBE_SEALED_PHOTOS") else [RESEARCH / "sealed", Path("D:/disc-probe/photos")]
    recorded = json.loads((Path(__file__).with_name("data") / "photo_sealed_read_v1.json").read_text(encoding="utf-8"))
    paths = []
    for reading in recorded["photos"]:
        found = next((p for directory in candidates for p in directory.rglob(reading["photo"]) if p.is_file()), None)
        if found is None:
            pytest.skip("Original sealed-test JPGs IMG_7497..7509 are not present; set DISCPROBE_SEALED_PHOTOS to their directory. Saved-vote reproduction is tested separately.")
        paths.append(found)
    pytest.importorskip("cv2")
    folder = make_run(tmp_path)
    process = subprocess.run([sys.executable, "-m", "discprobe", "photo", "--run", str(folder), "--media", "dvd", "--photos", *map(str, paths)],
                             cwd=ROOT, capture_output=True, text=True, timeout=1800)
    assert process.returncode == 0, process.stderr
    result = json.loads((folder / "photo.json").read_text(encoding="utf-8"))
    assert result["verdict"] == recorded["group"]["status"] == "ok"
    assert result["offset_mm"] == pytest.approx(recorded["group"]["L_mm"], abs=.33)
    assert abs(result["offset_mm"] + 2.291) <= .33


def test_duplicate_upload_is_refused_before_it_is_stored(tmp_path):
    with serving(tmp_path) as s:
        first = upload(s)[1]
        code, body = upload(s, name="again.png")
        assert code == 409 and body["code"] == "duplicate_photo" and body["duplicate_of"] == first["id"]
        assert [p["id"] for p in photos_of(json_request(s, "GET", "/api/photos?run=geo-test")[1])] == [first["id"]]
        # The same bytes in another run are that run's own first photo.
        assert upload(s, "geo-other")[0] == 200
        assert upload(s, grey=90)[0] == 200


def test_listing_says_whether_the_computer_page_is_open_and_on_which_run(tmp_path):
    with serving(tmp_path, lan=True) as s, patch.object(photo, "lan_ips", return_value=["192.168.1.10"]):
        session = {"X-Discprobe-Token": s.token}
        token = urlsplit(json_request(s, "GET", "/api/phone-link?run=geo-test", headers=session)[1]["url"]).path.rsplit("/", 1)[1]
        phone = {"X-Photo-Token": token}
        listing = json_request(s, "GET", "/api/photos?run=geo-test", headers=phone)[1]
        assert listing["desk_age"] is None and listing["desk_elsewhere"] is False and listing["analysis"] is None
        # The phone's own polls never count as the computer's page.
        assert json_request(s, "GET", "/api/photos?run=geo-test", headers=phone)[1]["desk_age"] is None
        json_request(s, "GET", "/api/photos?run=geo-test", headers=session)
        listing = json_request(s, "GET", "/api/photos?run=geo-test", headers=phone)[1]
        assert 0 <= listing["desk_age"] < 5 and listing["desk_elsewhere"] is False
        # The computer moved to another run: the old phone is told, and still only sees its own run.
        json_request(s, "GET", "/api/photos?run=geo-other", headers=session)
        listing = json_request(s, "GET", "/api/photos?run=geo-test", headers=phone)[1]
        assert listing["desk_elsewhere"] is True and "geo-other" not in json.dumps(listing)


@pytest.mark.parametrize("record, state", [
    (None, "none"),
    (dict(verdict="ok", group=dict(status="ok", n_ok=2, n_agree=2, spread_mm=.01)), "adopted"),
    (dict(verdict="unsure", group=dict(status="provisional", why="only one photo passed", n_ok=1)), "provisional"),
    (dict(verdict="unsure", group=dict(status="unknown", why="photos disagree", n_ok=2, spread_mm=.4)), "disagree"),
    (dict(verdict="unsure", group=dict(status="unknown", why="the photos' L scans disagree", n_ok=0)), "disagree"),
    (dict(verdict="unsure", group=dict(status="unknown", why="fewer than two photos with a clear peak")), "none"),
])
def test_photo_adoption_of_records_before_the_two_pose_rule(record, state):
    result = webui.photo_adoption(record)
    assert result["state"] == state


@pytest.mark.parametrize("agreement, extra, state, reason", [
    (dict(written=True, L_mm=1.0, photo_ids=["a", "b"]), dict(verdict="ok"), "adopted", None),
    (dict(written=False, reason="one_photo_provisional"), dict(verdict="unsure", provisional_mm=1.2), "provisional", "one_photo_provisional"),
    (dict(written=False, reason="photos_disagree"), dict(verdict="unsure"), "disagree", "photos_disagree"),
    (dict(written=False, reason="same_pose"), dict(verdict="unsure"), "refused", "same_pose"),
    (dict(written=False, reason="duplicate_photo"), dict(verdict="unsure"), "refused", "duplicate_photo"),
    (dict(written=True, L_mm=1.0, photo_ids=["a", "b"]), dict(verdict="unsure"), "refused", "group_not_ok"),
    (dict(written=False, reason="no_accepted_photos"), dict(verdict="unsure"), "none", "no_accepted_photos"),
])
def test_photo_adoption_follows_the_core_two_pose_rule(agreement, extra, state, reason):
    photos = [dict(status="ok", L_mm=1.0), dict(status="ok", L_mm=1.4), dict(status="no_rim")]
    result = webui.photo_adoption(dict(application_agreement=agreement, photos=photos, disc_id="T1", **extra))
    assert result["state"] == state and result["reason"] == reason and result["source"] == "core"
    assert result["n_ok"] == 2 and result["disc_id"] == "T1"
    if state == "provisional":
        assert result["provisional_mm"] == 1.2
    if state == "disagree":
        assert result["spread_mm"] == pytest.approx(.4)
    if state == "adopted":
        assert result["n_agree"] == 2


def test_listing_carries_the_application_gate_and_the_disc_number(tmp_path):
    with serving(tmp_path) as s:
        upload(s)
        listing = json_request(s, "GET", "/api/photos?run=geo-test")[1]
        assert listing["application"] == dict(written=False, reason="no_photo")
        folder = tmp_path / "results/geo-test"
        (folder / "photo.json").write_text(json.dumps(dict(verdict="unsure", media="cd", per_photo=[], photos=[], disc_id="T1",
            provisional_mm=None, application_agreement=dict(written=False, reason="no_accepted_photos"))), encoding="utf-8")
        listing = json_request(s, "GET", "/api/photos?run=geo-test")[1]
        assert listing["disc_id"] == "T1" and listing["adoption"]["state"] == "none"
        assert listing["application"]["written"] is False and listing["application"]["reason"]
        # The gate's reason is a code the pages translate, never a sentence with a colon.
        assert ":" not in listing["application"]["reason"]
