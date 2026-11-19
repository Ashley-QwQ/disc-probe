from contextlib import closing, contextmanager
import http.client
import json
import socket
import threading
import time
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from discprobe import photo, webui
from tests.test_photo import make_run, png


@contextmanager
def serve(backend, *, lan=False):
    server = webui.Server(backend, 0, lan=lan)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def call(server, path, payload=None, *, headers=None, address="127.0.0.1", raw=None):
    with closing(http.client.HTTPConnection(address, server.server_port, timeout=5)) as conn:
        body = json.dumps(payload) if payload is not None else raw
        conn.request("GET" if body is None else "POST", path, body,
                     {"Content-Type": "application/json", **(headers or {})})
        response = conn.getresponse()
        data = response.read()
        if response.getheader("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return response.status, data


def test_finding_1_backend_requires_the_reviewed_directory_for_one_export(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    for folder in (source, other):
        (folder / "sample.txt").write_bytes(b"sample")
    (tmp_path / "summary.json").write_text(json.dumps({
        "fit": {"media": "dvd", "u": 180000, "v": 5.5, "bit_nm_assumed": 133.3},
    }), encoding="utf-8")
    runner = Mock(return_value=Mock(wait=Mock(return_value=0)))
    backend = webui.Backend(tmp_path, drive_provider=lambda: [], runner=runner)
    with serve(backend) as server:
        def layout(folder):
            code, result = call(server, "/api/files-layout",
                                {"folder": str(folder), "geo": "summary.json", "writable_sectors": 4096})
            assert code == 200, result
            return result

        def permit(result):
            code, approved = call(server, "/api/files-authorize", {"review": result["review"]})
            assert code == 200, approved
            return approved["token"]

        def run(result, token=None):
            return call(server, "/api/run", {
                "action": "image", "files_token": token, "args": {
                    "geo": "summary.json", "files": result["folder"],
                    "writable_sectors": result["writable_sectors"], "files_plan_sha256": result["layout_sha256"],
                },
            })

        first = layout(source)
        assert run(first)[0] == 403
        assert run(layout(other), permit(first)) == (409, {"error": "files changed; review and confirm the files list again"})
        first = layout(source)
        token = permit(first)
        (source / "sample.txt").write_bytes(b"sample updated")
        assert run(layout(source), token)[0] == 409
        runner.assert_not_called()
        first = layout(source)
        token = permit(first)
        status, job = run(first, token)
        assert status == 200, job
        assert backend.jobs[job["job"]].finished.wait(3)
        assert run(first, token) == (403, {"error": "confirm the files list before exporting"})
        assert runner.call_count == 1


def test_finding_2_burn_grant_matches_one_job(tmp_path):
    iso = tmp_path / "iso"
    iso.mkdir()
    for name in ("first.iso", "second.iso"):
        (iso / name).write_bytes(bytes(2048))
    disc = {"blank": True, "rewritable": True, "media": "dvd", "medium_id": "sample-a"}
    runner = Mock(return_value=Mock(wait=Mock(return_value=0)))
    backend = webui.Backend(tmp_path, runner=runner,
                            drive_provider=lambda: [dict(id=drive, disc=disc) for drive in ("X:", "Y:")])
    original = dict(action="burn", drive="X:", media="dvd", args={"iso": "iso/first.iso"})
    mismatch = "burn token does not match the action, drive, media or ISO"
    with serve(backend) as server:
        def permit(action=original):
            status, response = call(server, "/api/burn-token", action)
            assert status == 200, response
            return response["token"]

        def run(action, token):
            return call(server, "/api/run", dict(action, burn_token=token))

        for alternate in (dict(original, action="erase", args={}), dict(original, action="calibrate"),
                          dict(original, args=dict(original["args"], erase=True)),
                          dict(original, drive="Y:"),
                          dict(original, args={"iso": "iso/second.iso"})):
            assert run(alternate, permit()) == (403, {"error": mismatch})
        token = permit()
        (iso / "first.iso").write_bytes(bytes(4096))
        assert run(original, token) == (403, {"error": mismatch})
        token = permit()
        disc["medium_id"] = "sample-b"
        assert run(original, token) == (403, {"error": "burn token does not match the current medium"})
        runner.assert_not_called()
        token = permit()
        status, job = run(original, token)
        assert status == 200, job
        assert run(original, token) == (403, {"error": "valid burn token required"})
        assert backend.jobs[job["job"]].finished.wait(3)
        for action in (dict(original, action="erase", args={}),
                       dict(original, args=dict(original["args"], erase=True)),
                       dict(original, action="calibrate", args=dict(original["args"], erase=True))):
            status, job = run(action, permit(action))
            assert status == 200, job
            assert backend.jobs[job["job"]].finished.wait(3)
        assert runner.call_count == 4


@pytest.mark.parametrize("lan", [False, True])
def test_finding_3_only_listener_hosts_before_authorization(tmp_path, lan):
    with serve(webui.Backend(tmp_path, drive_provider=lambda: []), lan=lan) as server:
        port = server.server_port
        token = {"X-Discprobe-Token": server.lifecycle_token}
        for host in ("evil.example", "127.0.0.1.evil", "192.0.2.1", "localhost:1"):
            if ":" not in host:
                host = f"{host}:{port}"
            assert call(server, "/api/ping", headers={**token, "Host": host}) == (403, {"error": "invalid Host"})
        assert call(server, "/api/ping", headers={**token, "Host": f"localhost:{port}"})[0] == 200


def test_finding_4_partial_headers_expire_and_leave_room_for_a_normal_request(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "HEADER_SECONDS", 1.25)
    monkeypatch.setattr(webui, "HEADER_CONNECTIONS", 8)
    monkeypatch.setattr(webui, "HEADER_LOCAL_RESERVE", 2)
    with serve(webui.Backend(tmp_path, drive_provider=lambda: []), lan=True) as server:
        sockets = []
        try:
            for _ in range(6):
                connection = socket.create_connection(("127.0.0.1", server.server_port), timeout=3)
                sockets.append(connection)
                connection.sendall(b"GET /api/ping HTTP/1.1\r\n")
            end = time.monotonic() + 1
            while len(server.header_pending) != len(sockets) and time.monotonic() < end:
                time.sleep(.01)
            assert len(server.header_pending) == len(sockets)
            before = time.monotonic()
            assert call(server, "/api/ping", headers={"X-Discprobe-Token": server.lifecycle_token})[0] == 200
            assert time.monotonic() - before < webui.HEADER_SECONDS
            for connection in sockets:
                assert connection.recv(1) == b""
        finally:
            for connection in sockets:
                connection.close()


def test_finding_4_remote_slots_cannot_take_the_loopback_reserve(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "HEADER_CONNECTIONS", 4)
    monkeypatch.setattr(webui, "HEADER_LOCAL_RESERVE", 1)
    start = Mock()
    monkeypatch.setattr(webui.ThreadingHTTPServer, "process_request", start)
    with webui.Server(webui.Backend(tmp_path, drive_provider=lambda: []), 0, lan=True) as server:
        reject = Mock()
        monkeypatch.setattr(server, "shutdown_request", reject)
        remote = ("192.0.2.1", 1234)
        local = ("127.0.0.1", 1234)
        first, second, third, excess, desktop, another = (object() for _ in range(6))
        for ticket in (first, second, third, excess):
            server.process_request(ticket, remote)
        for ticket in (desktop, another):
            server.process_request(ticket, local)
        assert server.header_pending == {first, second, third, desktop}
        assert start.call_count == 4
        assert [call.args for call in reject.call_args_list] == [(excess,), (another,)]
        server.headers_done(first)
        server.process_request(excess, remote)
        assert excess in server.header_pending


def test_finding_3_4_phone_page_and_upload_on_the_lan_listener(tmp_path):
    addresses = photo.lan_ips()
    if not addresses:
        pytest.skip("LAN interface unavailable")
    run = "geo-test"
    make_run(tmp_path, run)
    with serve(webui.Backend(tmp_path, drive_provider=lambda: []), lan=True) as server:
        main = {"X-Discprobe-Token": server.token}
        status, link = call(server, f"/api/phone-link?run={run}", headers=main)
        assert status == 200
        url = urlsplit(link["url"])
        assert url.hostname in addresses
        status, page = call(server, url.path, address=url.hostname)
        assert status == 200 and b"geo-test" in page
        phone = {"X-Photo-Token": url.path.rsplit("/", 1)[1], "Content-Type": "image/png",
                 "X-Filename": "fixture.png"}
        status, uploaded = call(server, f"/api/photos?run={run}", headers=phone, address=url.hostname, raw=png())
        assert status == 200 and uploaded["name"] == "fixture.png"
        status, listing = call(server, f"/api/photos?run={run}", headers=main)
        assert status == 200 and len(listing["photos"]) == 1
