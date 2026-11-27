"""No external network: mirrors are loopback fixtures behind a Python-only switch."""
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from discprobe import news, webui
from discprobe.version import __version__


@pytest.fixture
def mirror():
    state = SimpleNamespace(routes={}, requests=[])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            state.requests.append((self.path, dict(self.headers)))
            code, body, headers = state.routes.get(self.path, (404, b"missing", {}))
            self.send_response(code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionError, OSError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    state.paper = json.loads((news.BUNDLED / "news.json").read_text(encoding="utf-8"))
    state.routes["/news/news.json"] = (200, json.dumps(state.paper).encode(), {})
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def test_mirrors_cache_sample_and_private_headers(mirror, tmp_path):
    urls = [mirror.url + "/missing", mirror.url + "/news/news.json"]
    got = news.get_news(urls, cache=tmp_path, _test_http=True)
    assert got["from"] == "network" and got["source"] == urls[1]
    assert got["fetched_at"] and got["errors"] == [{"source": urls[0], "error": "HTTP 404"}]
    for path, headers in mirror.requests:
        assert "?" not in path
        assert headers == {"Host": f"127.0.0.1:{mirror.url.rsplit(':', 1)[1]}", "User-Agent": f"disc-probe/{__version__}"}
    cached = news.get_news([urls[0]], cache=tmp_path, _test_http=True)
    assert cached["from"] == "cache" and cached["fetched_at"] == got["fetched_at"]
    assert cached["paper"] == got["paper"] and cached["source"] == urls[1]
    (tmp_path / "paper.json").unlink()
    sample = news.get_news([urls[0]], cache=tmp_path, _test_http=True)
    assert sample["from"] == "bundled" and sample["source"] == news.BUNDLED_SOURCE
    assert sample["fetched_at"] is None and sample["paper"]["sample"]


@pytest.mark.parametrize("body,headers,reason", [
    (b"x", {"Content-Length": str(news.PAPER_LIMIT + 1)}, "too large"),
    (b"x" * (news.PAPER_LIMIT + 1), {}, "too large"),
    (b"not JSON", {}, "expecting value"),
    (b'{"format":"rss","version":1}', {}, "format"),
    (b"[" * 2000, {}, "expecting value"),
], ids=["large-header", "large-body", "bad-json", "bad-format", "deep-json"])
def test_bad_mirror_retries(mirror, tmp_path, body, headers, reason):
    mirror.routes["/bad"] = (200, body, headers)
    got = news.get_news([mirror.url + "/bad", mirror.url + "/news/news.json"], cache=tmp_path, _test_http=True)
    assert got["from"] == "network" and len(got["errors"]) == 1
    assert reason in got["errors"][0]["error"].lower()


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/a", "https://127.0.0.1/a", "https://10.0.0.1/a", "https://169.254.169.254/a",
    "https://[::1]/a", "https://user:pass@example.com/a", "https://example.com/a?q=1",
    "https://example.com/a#f", "file:///a", "https://example.com/a?", "https://example.com/\\a",
])
def test_ssrf_and_url_rejection(url, tmp_path):
    assert news.get_news([url], cache=tmp_path)["from"] == "bundled"


def test_dns_mixed_answers_and_rebinding(monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("must reject mixed DNS before connecting"))
    got = news.get_news(["https://mixed.example/news.json"], cache=tmp_path)
    assert "non-public" in got["errors"][0]["error"]


def test_connects_to_checked_numeric_address(monkeypatch, tmp_path):
    monkeypatch.setattr(news, "_resolve", lambda *a: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))])
    targets = []
    def connect(address, **kwargs):
        targets.append(address)
        raise OSError("fixture stops before external connection")
    monkeypatch.setattr(socket, "create_connection", connect)
    news.get_news(["https://changing.example/news.json"], cache=tmp_path)
    assert targets == [("1.1.1.1", 443)]


def test_https_downgrade_refused(mirror, tmp_path, monkeypatch):
    # Only the TLS transport is substituted; the real HTTP redirect handler and
    # downloader run against the loopback fixture. No certificate bypass in production.
    monkeypatch.setattr(news.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=lambda sock, **k: sock))
    mirror.routes["/redirect"] = (302, b"", {"Location": mirror.url + "/news/news.json"})
    source = mirror.url.replace("http://", "https://") + "/redirect"
    got = news.get_news([source], cache=tmp_path, _test_http=True)
    assert got["from"] == "bundled" and "downgrade" in got["errors"][0]["error"]
    assert [p for p, _ in mirror.requests] == ["/redirect"]


def test_redirects(mirror, tmp_path):
    mirror.routes["/redirect"] = (302, b"", {"Location": "/news/news.json"})
    got = news.get_news([mirror.url + "/redirect"], cache=tmp_path, _test_http=True)
    assert got["from"] == "network" and got["source"].endswith("/news/news.json")
    mirror.routes["/redirect"] = (302, b"", {"Location": "http://10.0.0.1/news.json"})
    got = news.get_news([mirror.url + "/redirect"], cache=tmp_path, _test_http=True)
    assert "HTTPS" in got["errors"][0]["error"]
    mirror.routes["/redirect"] = (302, b"", {"Location": "/redirect"})
    assert "too many redirects" in news.get_news([mirror.url + "/redirect"], cache=tmp_path, _test_http=True)["errors"][0]["error"]


@pytest.mark.parametrize("path", ["../escape.json", "a/../../escape.png", "/a.png", "//x/a.png",
    "a/%2e%2e/x.json", "a\\b.json", "x.svg", "https://example.com/x.json", "x.json?q=1", "a/./x.png"])
def test_asset_paths_rejected(path):
    with pytest.raises(news.NewsError):
        news.get_asset(path, news.BUNDLED_SOURCE)


def test_asset_network_cache_and_bundle(mirror, tmp_path):
    source = mirror.url + "/news/news.json"
    mirror.routes["/news/skins/a.json"] = (200, b'{"skin":true}', {})
    assert news.get_asset("skins/a.json", source, cache=tmp_path, _test_http=True) == (b'{"skin":true}', "application/json")
    del mirror.routes["/news/skins/a.json"]
    assert news.get_asset("skins/a.json", source, cache=tmp_path, _test_http=True)[0] == b'{"skin":true}'
    mirror.routes["/news/art/b.png"] = (302, b"", {"Location": "/elsewhere.png"})
    with pytest.raises(news.NewsError):
        news.get_asset("art/b.png", source, cache=tmp_path, _test_http=True)
    assert all(p != "/elsewhere.png" for p, _ in mirror.requests)
    mirror.routes["/news/art/b.png"] = (200, b"x", {"Content-Length": str(news.ASSET_LIMIT + 1)})
    with pytest.raises(news.NewsError):
        news.get_asset("art/b.png", source, cache=tmp_path, _test_http=True)
    raw, kind = news.get_asset("skins/kraft-office.json", news.BUNDLED_SOURCE)
    assert kind == "application/json" and json.loads(raw)["format"] == "dp-skin"


def test_source_precedence_and_state_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("DISCPROBE_NEWS_SOURCES", "https://a.example/news.json https://b.example/news.json")
    seen = []
    def fail(url, *a, **k):
        seen.append(url)
        raise news.NewsError("offline")
    monkeypatch.setattr(news, "_download", fail)
    news.get_news()
    assert seen == ["https://a.example/news.json", "https://b.example/news.json"]
    seen.clear()
    news.get_news(["https://c.example/news.json"])
    assert seen == ["https://c.example/news.json"]
    assert news.cache_dir() == tmp_path / "disc-probe" / "news"


def test_total_deadline_includes_trickled_headers(monkeypatch, tmp_path):
    class Slow(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def do_GET(self):
            try:
                self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                for _ in range(30):
                    self.wfile.write(b"X-Slow: yes\r\n")
                    self.wfile.flush()
                    time.sleep(.03)
            except OSError:
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(news, "TIMEOUT", .15)
    try:
        start = time.monotonic()
        got = news.get_news([f"http://127.0.0.1:{server.server_port}/news.json"], cache=tmp_path, _test_http=True)
        assert time.monotonic() - start < .7
        assert got["from"] == "bundled" and len(got["errors"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cli_json_language_and_asset_errors(monkeypatch, tmp_path):
    import os
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), DISCPROBE_NO_TUTORIAL="1", PYTHONUTF8="1")
    command = [sys.executable, "-X", "utf8", "-m", "discprobe", "news", "--source", "https://127.0.0.1/news.json"]
    result = subprocess.run(command + ["--json"], capture_output=True, env=env, timeout=10)
    assert result.returncode == 0
    assert json.loads(result.stdout)["from"] == "bundled"
    for language in ("zh", "en"):
        result = subprocess.run(command + ["--lang", language], capture_output=True, env=env, timeout=10)
        assert result.returncode == 0
        sample = json.loads((news.BUNDLED / "news.json").read_bytes())
        assert sample["release"]["headline"][language] in result.stdout.decode("utf-8")
    result = subprocess.run(command + ["--asset", "../outside.json"], capture_output=True, env=env, timeout=10)
    assert result.returncode == 1 and not result.stdout and b"prefix" in result.stderr
    result = subprocess.run(command + ["--asset", "skins/kraft-office.json"], capture_output=True, env=env, timeout=10)
    assert result.returncode == 0 and result.stdout == (news.BUNDLED / "skins/kraft-office.json").read_bytes()


def test_schema_limits_and_clean_copy(mirror):
    sample = mirror.paper
    clean = news.read_paper(dict(sample, extra="discard", jokes=["x"] * 41))
    assert "extra" not in clean and len(clean["jokes"]) == 40
    for edit in (lambda p: p.update(version=True), lambda p: p.update(date="２０２６-１１-１６"),
                 lambda p: p["jokes"].append("x" * 601),
                 lambda p: p["skins"][0].update(package="javascript:alert(1)"),
                 lambda p: p["artworks"][0].update(image="//evil.example/a.png"),
                 lambda p: p["backgrounds"][0]["pattern"].update(size_mm=30),
                 lambda p: p["changelog"][0].update(story="😀" * 301)):
        bad = copy.deepcopy(sample)
        edit(bad)
        with pytest.raises(news.NewsError):
            news.read_paper(bad)
    minimal = dict(format="dp-fax-news", version=1.0, date="2026-11-16",
                   release=dict(version="1.0", date="2026-11-16", headline="Hello"))
    wire = news.read_paper(minimal)
    assert "url" not in wire["release"]
    assert news.read_paper(wire) == wire


def test_http_adapters_and_responsiveness(monkeypatch, tmp_path):
    started, release = threading.Event(), threading.Event()
    def get(sources=None):
        if sources == ["https://slow.example/news.json"]:
            started.set()
            assert release.wait(5)
        return {"paper": {}, "from": "bundled", "source": news.BUNDLED_SOURCE, "fetched_at": None, "errors": []}
    monkeypatch.setattr(news, "get_news", get)
    server = webui.Server(SimpleNamespace(close=lambda: None), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            conn.request("GET", path)
            r = conn.getresponse()
            return r.status, r.read(), r.getheader("Content-Type")
        finally:
            conn.close()
    slow = threading.Thread(target=lambda: request("/api/news?source=https%3A%2F%2Fslow.example%2Fnews.json"))
    try:
        slow.start()
        assert started.wait(3)
        status, raw, _ = request("/api/version")
        assert status == 200 and "core_version" in json.loads(raw)
        status, raw, kind = request("/api/news/asset?path=skins/kraft-office.json&source=" + quote(news.BUNDLED_SOURCE))
        assert status == 200 and json.loads(raw)["format"] == "dp-skin"
        assert kind == "application/json"
        assert request("/api/news/asset?path=../escape.json")[0] == 400
        release.set()
        slow.join(3)
        assert not slow.is_alive()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()
