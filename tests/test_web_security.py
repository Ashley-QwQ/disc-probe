"""Real response headers; no drive enumeration or network beyond loopback."""
import base64
import hashlib
import http.client
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from discprobe.web_security import content_security_policy, fax_origins
from discprobe import webui
from disclab import desk

ROOT = Path(__file__).resolve().parents[1]


def html_pages(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if 'b' + 'lind' not in d.lower()]
        for name in files:
            if 'b' + 'lind' not in name.lower() and name.endswith('.html'):
                yield Path(base) / name


def test_hashes_normalize_html_newlines_and_never_allow_inline_script(monkeypatch):
    monkeypatch.delenv('DISCPROBE_FAX_ORIGINS', raising=False)
    raw = b'<script>\r\nconsole.log("test")\r\n</script>'
    h = base64.b64encode(hashlib.sha256(b'\nconsole.log("test")\n').digest()).decode()
    policy = content_security_policy(raw, fax=True)
    assert "'sha256-" + h + "'" in policy
    assert "connect-src 'self';" in policy
    assert "frame-ancestors 'none'" in policy
    assert 'unsafe-inline' not in policy.split('script-src ', 1)[1].split(';')[0]


@pytest.mark.parametrize('value', ['https:', 'https://*.example', "https://x;img-src", 'https://user@x', 'https://x/path', 'https://x?foo=1', 'https://x/#f'])
def test_fax_allowlist_rejects_non_origins(monkeypatch, value):
    monkeypatch.setenv('DISCPROBE_FAX_ORIGINS', value)
    with pytest.raises(ValueError):
        fax_origins()


def test_only_explicit_fax_origins_are_allowed(monkeypatch):
    monkeypatch.setenv('DISCPROBE_FAX_ORIGINS', 'https://news.example https://skins.example:8443/')
    assert fax_origins() == ['https://news.example', 'https://skins.example:8443']
    assert "connect-src 'self';" in content_security_policy(b'', fax=True)
    assert "connect-src 'self';" in content_security_policy(b'')


def request(server, path):
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
    try:
        conn.request('GET', path)
        response = conn.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        conn.close()


def test_every_html_response_has_exact_policy_including_phone_and_lab(tmp_path, monkeypatch):
    monkeypatch.delenv('DISCPROBE_FAX_ORIGINS', raising=False)
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    run = tmp_path / 'results/geo-X-20261115-120000'
    run.mkdir(parents=True)
    (run / 'summary.json').write_text('{}', encoding='utf-8')
    token = backend.photos.token(run.name)
    dp = webui.Server(backend, 0)
    lab = desk.ThreadingHTTPServer(('127.0.0.1', 0), desk.handler_for(SimpleNamespace()))
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (dp, lab)]
    for thread in threads:
        thread.start()
    try:
        pages = list(html_pages(ROOT / 'discprobe/web'))
        assert pages
        cases = [(dp, '/' + p.relative_to(ROOT / 'discprobe/web').as_posix(), True) for p in pages
                 if p != ROOT / 'discprobe/web/phone/index.html']
        assert request(dp, '/phone/index.html')[0] == 403  # template is not a token-bearing page
        cases += [(dp, '/phone/' + token, True), (lab, '/', False), (lab, '/index.html', False)]
        for server, path, fax in cases:
            code, body, headers = request(server, path)
            assert code == 200, path
            assert headers['Content-Type'].startswith('text/html'), path
            assert headers['Content-Security-Policy'] == content_security_policy(body, fax=fax), path
        assert request(lab, '/shared.js')[0] == 200
    finally:
        for server in (dp, lab):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
