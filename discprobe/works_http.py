"""Token-protected works routes, called only after Handler._allowed()."""
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import i18n, works
from .works_cli import file_bytes


def _object(raw):
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise works.WorkError("invalid work metadata")
    return data


def handle(handler, method):
    url = urlsplit(handler.path)
    path = unquote(url.path)
    if path != "/api/works" and not path.startswith("/api/works/"):
        return False
    store = handler.server.backend.works
    body_read = False
    def body(limit):
        nonlocal body_read
        raw = handler._body(limit)
        body_read = True
        return raw
    def obj():
        raw = body(65536)
        if handler.headers.get_content_type() != "application/json":
            raise works.WorkError("application/json required", 415)
        return _object(raw)
    def optional_obj():
        lengths = handler.headers.get_all("Content-Length", [])
        if handler.headers.get("Transfer-Encoding") or len(lengths) > 1 or any(not n.isdigit() for n in lengths):
            raise works.WorkError("one Content-Length required", 411)
        return obj() if lengths and int(lengths[0]) else {}
    def answer(work):
        if isinstance(work, dict) and "id" in work:
            work = dict(work, thumb_url=f"/api/works/{work['id']}/thumb")
        handler._json(200, work)
    try:
        if path == "/api/works":
            if method == "GET":
                query = parse_qs(url.query)
                rows = store.list(query.get("status", [None])[0], query.get("media", [None])[0], query.get("sort", ["time"])[0])
                answer([dict(w, thumb_url=f"/api/works/{w['id']}/thumb") for w in rows])
            elif method == "POST":
                data = obj()
                if set(data) - {"name", "media", "from"}:
                    raise works.WorkError("invalid work metadata")
                source, raw, source_file = data.get("from"), None, None
                if source is not None:
                    if isinstance(source, dict):
                        raw = works.encoded(source)
                    elif isinstance(source, str) and source.lstrip().startswith("{"):
                        raw = source.encode("utf-8")
                    elif isinstance(source, str):
                        from .webui import local_path
                        source_file = local_path(handler.server.backend.root, source)
                        if Path(source_file).suffix.lower() != ".discdesign":
                            raise works.WorkError("invalid discdesign document")
                        raw = file_bytes(source_file, works.DESIGN_LIMIT)
                    else:
                        raise works.WorkError("invalid discdesign document")
                answer(store.new(data.get("name"), data.get("media", "dvd"), raw, source_file))
            else:
                raise works.WorkError("work route not found", 404)
        elif path == "/api/works/import" and method == "POST":
            raw = body(works.ARCHIVE_LIMIT)
            if handler.headers.get_content_type() not in ("application/zip", "application/octet-stream", "application/json"):
                raise works.WorkError("ZIP or discdesign JSON required", 415)
            # This header is provenance text only; never open a client supplied file path.
            source = handler.headers.get("X-Filename")
            answer(store.import_bytes(raw, source))
        else:
            parts = path.removeprefix("/api/works/").split("/")
            ident = works.valid_id(parts[0])
            suffix = "/".join(parts[1:])
            if not suffix and method == "GET":
                answer(store.show(ident, opened=True))
            elif not suffix and method == "PATCH":
                answer(store.patch(ident, obj()))
            elif not suffix and method == "DELETE":
                answer(store.delete(ident))
            elif suffix == "design" and method == "GET":
                handler._send(200, store.content(ident, "design.discdesign"), "application/json; charset=utf-8")
            elif suffix == "design" and method == "PUT":
                raw = body(works.DESIGN_LIMIT)
                if handler.headers.get_content_type() != "application/json":
                    raise works.WorkError("application/json required", 415)
                answer(store.save(ident, raw, if_match=handler.headers.get("If-Match")))
            elif suffix == "thumb" and method == "GET":
                handler._send(200, store.content(ident, "thumb.png"), "image/png")
            elif suffix == "thumb" and method == "PUT":
                raw = body(works.THUMB_LIMIT)
                if handler.headers.get_content_type() != "image/png":
                    raise works.WorkError("image/png required", 415)
                answer(store.set_thumb(ident, raw))
            elif suffix == "export" and method == "GET":
                handler._send(200, store.export(ident), "application/zip", filename=ident + ".zip")
            elif suffix == "duplicate" and method == "POST":
                data = optional_obj()
                if set(data) - {"name"}:
                    raise works.WorkError("invalid work metadata")
                answer(store.duplicate(ident, data.get("name")))
            elif suffix == "restore" and method == "POST":
                # Accept either an empty request or {} from the page's JSON client.
                if optional_obj():
                    raise works.WorkError("invalid work metadata")
                answer(store.restore(ident))
            else:
                raise works.WorkError("work route not found", 404)
    except (ValueError, OSError, UnicodeError, RecursionError, TypeError, KeyError) as exc:
        # Drain only a small rejected body, as the server's other upload routes do.
        if not body_read:
            length = handler.headers.get("Content-Length", "")
            if length.isdigit() and 0 < int(length) <= 65536:
                handler.connection.settimeout(.2)
                try:
                    handler.rfile.read(int(length))
                except OSError:
                    pass
        status = getattr(exc, "status", 400)
        message = str(exc) if isinstance(exc, works.WorkError) or hasattr(exc, "status") else "invalid works request"
        handler._json(status, dict(error=i18n.tr(message)))
    return True
