"""Download-only news service shared by the CLI and the local web desk.

Connections use a checked, pinned DNS answer (including redirects), never a proxy,
cookie jar or browser headers. The loopback exception is an explicit Python test
argument, unavailable from the CLI, environment or HTTP query.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlsplit

from . import i18n, sectors
from .version import __version__

DEFAULT_SOURCES = (
    "https://raw.githubusercontent.com/Ashley-QwQ/disc-probe/main/news/news.json",
    "https://cdn.jsdelivr.net/gh/Ashley-QwQ/disc-probe@main/news/news.json",
)
BUNDLED = Path(__file__).parent / "web" / "home" / "faxnews"
BUNDLED_SOURCE = "bundled:faxnews/news.json"
PAPER_LIMIT, ASSET_LIMIT, TIMEOUT = 1024 * 1024, 4 * 1024 * 1024, 8
KINDS = {".json": "application/json", ".webp": "image/webp", ".png": "image/png",
         ".jpeg": "image/jpeg", ".jpg": "image/jpeg"}


class NewsError(ValueError):
    pass


def safe_ref(value):
    if not isinstance(value, str) or not value or len(value.encode("utf-16-le", errors="surrogatepass")) // 2 > 400:
        return False
    if re.match(r"^[a-z][a-z0-9+.-]*:", value, re.I):
        return bool(re.match(r"^https?://", value, re.I))
    return not value.startswith("//")


def read_paper(data):
    """Same v1 fields, defaults and 40-item cap as faxnews-data.mjs."""
    def need(ok, field):
        if not ok:
            raise NewsError("invalid paper: " + field)

    def text(v):
        length = lambda s: len(s.encode("utf-16-le", errors="surrogatepass")) // 2
        return (isinstance(v, str) and length(v) <= 600) or (
            isinstance(v, dict) and any(isinstance(v.get(k), str) for k in ("zh", "en"))
            and all(isinstance(s, str) and length(s) <= 600 for s in v.values()))

    def date(v):
        if not isinstance(v, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v):
            return False
        # Date.parse in JS allows a day to overflow within 01..31.
        return 1 <= int(v[5:7]) <= 12 and 1 <= int(v[8:]) <= 31

    def version(v):
        return bool(re.fullmatch(r"v?[0-9]+(?:\.[0-9]+){0,3}(?:-[0-9a-z.]+)?", str(v).strip(), re.I | re.ASCII))

    def number(v):
        try:
            return type(v) in (int, float) and math.isfinite(v)
        except OverflowError:
            return False

    def colour(v):
        return isinstance(v, str) and bool(re.fullmatch(r"#[0-9a-f]{6}", v, re.I))

    need(isinstance(data, dict), "not an object")
    need(data.get("format") == "dp-fax-news", "format")
    need(type(data.get("version")) in (int, float) and data["version"] == 1, "version")
    need(date(data.get("date")), "date")
    out = dict(format="dp-fax-news", version=1, date=data["date"], sample=data.get("sample") is True, release=None)
    r = data.get("release")
    if r is not None:
        need(isinstance(r, dict), "release")
        for k, check in (("version", version), ("date", date), ("headline", text)):
            need(check(r.get(k)), "release." + k)
        need(r.get("url") is None or safe_ref(r["url"]), "release.url")
        need(r.get("summary") is None or text(r["summary"]), "release.summary")
        out["release"] = {k: r[k] for k in ("version", "date", "headline")}
        out["release"].update(summary=r.get("summary") or "")
        # The wire paper is validated again by the frontend. An absent URL must
        # stay absent: safeRef("") is false, even though the JS view defaults to it.
        if r.get("url") is not None:
            out["release"]["url"] = r["url"]
    for key in ("changelog", "skins", "backgrounds", "artworks", "jokes", "coming"):
        rows = data.get(key)
        rows = [] if rows is None else rows
        need(isinstance(rows, list), key)
        out[key] = []
        for i, row in enumerate(rows[:40]):
            w = f"{key}[{i}]"
            if key == "jokes":
                need(text(row), w)
                out[key].append(row)
                continue
            need(isinstance(row, dict), w)
            fields = {"changelog": ("title", "story"), "skins": ("name", "pitch"),
                      "backgrounds": ("name",), "artworks": ("title",), "coming": ("title",)}[key]
            clean = {}
            for k in fields:
                need(text(row.get(k)), w + "." + k)
                clean[k] = row[k]
            optional = {"changelog": (), "skins": ("price",), "backgrounds": (),
                        "artworks": ("by", "disc"), "coming": ("note",)}[key]
            for k in optional:
                need(row.get(k) is None or text(row[k]), w + "." + k)
                clean[k] = row.get(k) or ""
            if key == "changelog":
                need(version(row.get("version")) and date(row.get("date")), w + ".version/date")
                clean.update(version=row["version"], date=row["date"])
            elif key == "skins":
                need(isinstance(row.get("id"), str) and re.fullmatch(r"[a-z0-9-]{1,40}", row["id"]), w + ".id")
                need(safe_ref(row.get("package")), w + ".package")
                sw = row.get("swatches")
                need(isinstance(sw, list) and 2 <= len(sw) <= 6 and all(map(colour, sw)), w + ".swatches")
                size = row.get("size_kb")
                need(size is None or (number(size) and size >= 0), w + ".size_kb")
                clean.update(id=row["id"], package=row["package"], swatches=sw, size_kb=size)
            elif key == "backgrounds":
                p = row.get("pattern")
                need(isinstance(p, dict), w + ".pattern")
                need(p.get("pattern") in ("diamond", "dots", "stripes"), w + ".pattern.pattern")
                coordinates = p.get("coordinates") if p.get("coordinates") is not None else "cartesian"
                need(coordinates in ("cartesian", "polar"), w + ".pattern.coordinates")
                pitch, size, angle = p.get("pitch_mm"), p.get("size_mm"), p.get("angle_deg", 0)
                angle = 0 if angle is None else angle
                need(number(pitch) and .5 <= pitch <= 20, w + ".pattern.pitch_mm")
                need(number(size) and 0 < size <= pitch / 2, w + ".pattern.size_mm")
                need(number(angle) and abs(angle) <= 360, w + ".pattern.angle_deg")
                clean.update(note=row.get("note") if text(row.get("note")) else "",
                             pattern=dict(pattern=p["pattern"], coordinates=coordinates,
                                          pitch_mm=pitch, size_mm=size, angle_deg=angle))
            elif key == "artworks":
                need(safe_ref(row.get("image")), w + ".image")
                clean.update(image=row["image"], caption=row.get("caption") if text(row.get("caption")) else "")
            out[key].append(clean)
    need(out["release"] or any(out[k] for k in ("changelog", "skins", "backgrounds", "artworks", "jokes", "coming")), "nothing to print")
    return out


def _url(value, test_http=False):
    try:
        u = urlsplit(value)
        if (not isinstance(value, str) or any(ord(c) <= 32 for c in value) or "\\" in value
                or u.username is not None or u.password is not None or u.query or u.fragment
                or "?" in value or "#" in value or not u.hostname
                or (u.scheme != "https" and not (test_http and u.scheme == "http" and u.hostname == "127.0.0.1"))):
            raise ValueError()
        _ = u.port
        return u
    except (TypeError, ValueError):
        raise NewsError("source must be HTTPS without query, fragment or credentials") from None


def _resolve(host, port, remaining):
    result = queue.Queue()
    def run():
        try:
            result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError as exc:
            result.put(exc)
    threading.Thread(target=run, daemon=True).start()
    try:
        answer = result.get(timeout=max(.001, remaining))
    except queue.Empty:
        raise NewsError("DNS timeout") from None
    if isinstance(answer, Exception):
        raise answer
    return answer


def _download(url, limit, *, test_http=False, prefix=None):
    deadline = time.monotonic() + TIMEOUT
    sockets = []
    def expire():
        # A per-read socket timeout alone can be kept alive by trickled headers.
        # Shutdown also bounds getresponse(), whose parser may do many reads.
        for transport in sockets[:]:
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    timer = threading.Timer(TIMEOUT, expire)
    timer.daemon = True
    timer.start()
    try:
        return _download_until(url, limit, test_http, prefix, deadline, sockets)
    finally:
        timer.cancel()


def _download_until(url, limit, test_http, prefix, deadline, sockets):
    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise NewsError("timeout (8 seconds)")
        return seconds
    for _ in range(6):
        u = _url(url, test_http)
        if prefix is not None and not _inside(url, prefix):
            raise NewsError("asset redirect outside paper prefix")
        port = u.port or (443 if u.scheme == "https" else 80)
        answers = _resolve(u.hostname, port, remaining())
        if not answers:
            raise NewsError("no DNS address")
        for answer in answers:
            ip = ipaddress.ip_address(answer[4][0])
            if (not ip.is_global or ip.is_multicast or ip.is_reserved) and not (test_http and u.hostname == "127.0.0.1" and str(ip) == "127.0.0.1"):
                raise NewsError("non-public target address refused")
        # Pin the checked numeric address: no second DNS lookup at connection time.
        ip = answers[0][4][0]
        conn = http.client.HTTPConnection(u.hostname, port, timeout=remaining())
        try:
            sock = socket.create_connection((ip, port), timeout=remaining())
            sockets[:] = [sock]
            conn.sock = sock
            if u.scheme == "https":
                sock.settimeout(remaining())
                conn.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
                sockets[:] = [conn.sock]
            conn.sock.settimeout(remaining())
            transport = conn.sock
            conn.putrequest("GET", u.path or "/", skip_accept_encoding=True)
            conn.putheader("User-Agent", f"disc-probe/{__version__}")
            conn.endheaders()
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                target = urljoin(url, response.getheader("Location", ""))
                _url(target, test_http)
                if u.scheme == "https" and urlsplit(target).scheme != "https":
                    raise NewsError("HTTPS downgrade refused")
                url = target
                continue
            if response.status != 200:
                raise NewsError(f"HTTP {response.status}")
            length = response.getheader("Content-Length")
            if length and int(length) > limit:
                raise NewsError(f"too large (limit {limit} bytes)")
            chunks, total = [], 0
            while True:
                if transport.fileno() != -1:
                    transport.settimeout(remaining())
                block = response.read1(min(65536, limit + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise NewsError(f"too large (limit {limit} bytes)")
                chunks.append(block)
            return b"".join(chunks), url
        finally:
            conn.close()
    raise NewsError("too many redirects")


def cache_dir():
    # Reuse DP's existing user state directory, beside games.json.
    return Path(sectors.state_path()).parent / "news"


def _write(path, raw):
    """Unique temporary names keep concurrent web requests from clobbering writes."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(raw)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def _json(raw):
    return json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(NewsError("invalid JSON number")))


def get_news(sources=None, *, cache=None, _test_http=False):
    sources = list(sources) if sources is not None else os.environ.get("DISCPROBE_NEWS_SOURCES", "").split() or list(DEFAULT_SOURCES)
    root = Path(cache) if cache is not None else cache_dir()
    errors = []
    for source in sources:
        try:
            raw, final = _download(source, PAPER_LIMIT, test_http=_test_http)
            paper = read_paper(_json(raw))
            result = dict(paper=paper, source=final, fetched_at=datetime.now(timezone.utc).isoformat(), errors=errors)
            result["from"] = "network"
            try:
                _write(root / "paper.json", json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except OSError:
                pass  # Read-only/full user storage must not discard a good paper.
            return result
        except (ValueError, OSError, http.client.HTTPException, UnicodeError, RecursionError) as exc:
            errors.append(dict(source=source, error=str(exc)))
    try:
        with (root / "paper.json").open("rb") as stream:
            saved = _json(stream.read(PAPER_LIMIT * 2 + 1))
        paper = read_paper(saved["paper"])
        _url(saved["source"], _test_http)
        if not isinstance(saved["fetched_at"], str):
            raise NewsError("invalid cached time")
        return dict(paper=paper, source=saved["source"], fetched_at=saved["fetched_at"], errors=errors, **{"from": "cache"})
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return dict(paper=read_paper(_json((BUNDLED / "news.json").read_bytes())), source=BUNDLED_SOURCE,
                    fetched_at=None, errors=errors, **{"from": "bundled"})


def asset_path(path):
    if not isinstance(path, str) or not path or len(path) > 400:
        raise NewsError("invalid asset path")
    decoded = unquote(path)
    if (decoded != path or any(ord(c) <= 32 for c in path) or any(c in path for c in "\\:?#")
            or path.startswith("/") or any(p in ("", ".", "..") for p in path.split("/"))):
        raise NewsError("asset must stay within paper prefix")
    if Path(path).suffix.lower() not in KINDS:
        raise NewsError("asset type refused")
    return path


def _inside(url, prefix):
    u, p = urlsplit(url), urlsplit(prefix)
    return (u.scheme, u.netloc) == (p.scheme, p.netloc) and u.path.startswith(p.path) and all(
        part not in (".", "..") for part in unquote(u.path).split("/")) and "\\" not in unquote(u.path)


def get_asset(path, source=None, *, cache=None, _test_http=False):
    path = asset_path(path)
    root = Path(cache) if cache is not None else cache_dir()
    if source is None:
        source = get_news(cache=root, _test_http=_test_http)["source"]
    kind = KINDS[Path(path).suffix.lower()]
    if source == BUNDLED_SOURCE:
        target = BUNDLED / path
        with target.open("rb") as stream:
            raw = stream.read(ASSET_LIMIT + 1)
        if len(raw) > ASSET_LIMIT:
            raise NewsError("asset too large")
        return raw, kind
    _url(source, _test_http)
    prefix = urljoin(source, ".")
    url = urljoin(prefix, path)
    if not _inside(url, prefix):
        raise NewsError("asset outside paper prefix")
    dest = root / "assets" / hashlib.sha256(url.encode("utf-8")).hexdigest()
    try:
        raw, _ = _download(url, ASSET_LIMIT, test_http=_test_http, prefix=prefix)
        try:
            _write(dest, raw)
        except OSError:
            pass
        return raw, kind
    except (ValueError, OSError, http.client.HTTPException):
        try:
            with dest.open("rb") as stream:
                raw = stream.read(ASSET_LIMIT + 1)
            if len(raw) > ASSET_LIMIT:
                raise NewsError("cached asset too large")
            return raw, kind
        except OSError:
            raise NewsError("asset unavailable (network and cache)") from None


def add_parser(sub):
    zh = i18n.active() == "zh"
    p = sub.add_parser("news", help="下载传真报纸（只下载）" if zh else "download the fax paper (download only)")
    p.add_argument("--source", action="append", help="报纸 HTTPS 地址，可重复" if zh else "paper HTTPS URL; repeatable")
    p.add_argument("--asset", help="报纸下的附件相对路径" if zh else "relative asset path under the paper")
    p.add_argument("--json", action="store_true", help="输出 JSON" if zh else "print JSON")
    p.set_defaults(func=run)


def run(args):
    import sys
    result = get_news(args.source)
    if args.asset:
        try:
            raw, _ = get_asset(args.asset, result["source"])
            sys.stdout.buffer.write(raw)
            return 0
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        zh = i18n.active() == "zh"
        paper = result["paper"]
        names = {"network": "联网下载", "cache": "上次的报纸", "bundled": "程序自带的样张"}
        print(f"{'DP 日报' if zh else 'DP Daily'} {paper['date']} · {names[result['from']] if zh else result['from']}")
        print(f"{'来源' if zh else 'Source'}: {result['source']}")
        def pick(value):
            if isinstance(value, str):
                return value
            return value.get("zh" if zh else "en", value.get("zh", value.get("en", "")))
        if paper["release"]:
            r = paper["release"]
            print(f"\n{r['version']} · {r['date']} · {pick(r['headline'])}\n{pick(r['summary'])}")
        for row in paper["changelog"][:3]:
            print(f"\n{row['version']} · {pick(row['title'])}\n{pick(row['story'])}")
        if paper["jokes"]:
            print("\n" + pick(paper["jokes"][0]))
        for e in result["errors"]:
            print(f"{'没接通' if zh else 'Could not receive'} {e['source']}: {e['error']}")
    return 0
