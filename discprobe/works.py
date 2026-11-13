"""Durable, drive-free works library. All readers share the writer's recovery lock."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile

DESIGN_LIMIT = 64 * 1024 * 1024
THUMB_LIMIT = 4 * 1024 * 1024
ARCHIVE_LIMIT = 256 * 1024 * 1024
ID = re.compile(r"w-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", re.ASCII)
ASSET = re.compile(r"assets/[0-9a-f]{64}", re.ASCII)
STATUSES = ("draft", "iso_ready", "burned", "done", "failed")
_locks = {}
_locks_guard = threading.Lock()


class WorkError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def data_root(results="results"):
    """The CLI defaults to ./results; works are its sibling, or HOME/works."""
    return Path(os.environ.get("DISCPROBE_HOME") or Path(results).resolve().parent).resolve()


def valid_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise WorkError("invalid work id")
    return value


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def atomic(path, data):
    """Unique temporary on the same volume, flush, then publish in one replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def redirected(path):
    """Also reject Windows junctions on Python 3.11 (before Path.is_junction)."""
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def read_design(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= DESIGN_LIMIT:
        raise WorkError("invalid design size", 413)
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
        if (not isinstance(doc, dict) or doc.get("format") != "disc-probe design"
                or type(doc.get("version")) is not int or doc["version"] not in (1, 2)
                or not isinstance(doc.get("layers"), list) or len(doc["layers"]) > 16
                or any(not isinstance(layer, dict) for layer in doc["layers"])):
            raise ValueError()
        if doc.get("media", "dvd") not in ("dvd", "cd", "bd"):
            raise ValueError()
        if doc.get("cell", .02) not in (.02, .01, .005):
            raise ValueError()
        # Reject non-finite JSON values even in fields the preview does not use.
        json.dumps(doc, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError):
        raise WorkError("invalid discdesign document") from None
    return doc


def assets(doc):
    """Keep the original embedded bytes too; never rewrite the portable document."""
    found = {}
    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and value.startswith("data:"):
            try:
                header, body = value.split(",", 1)
                if not header.endswith(";base64"):
                    raise ValueError()
                raw = base64.b64decode(body, validate=True)
            except ValueError:
                raise WorkError("invalid embedded image") from None
            found["assets/" + hashlib.sha256(raw).hexdigest()] = raw
    visit(doc)
    for layer in doc["layers"]:
        if layer.get("raster"):
            try:
                raw = base64.b64decode(layer["raster"]["rgba"], validate=True)
            except (ValueError, KeyError, TypeError):
                raise WorkError("invalid embedded image") from None
            found["assets/" + hashlib.sha256(raw).hexdigest()] = raw
        if isinstance(layer.get("svg"), str):
            raw = layer["svg"].encode("utf-8")
            found["assets/" + hashlib.sha256(raw).hexdigest()] = raw
    return found


def thumbnail(doc):
    """Use the core compositor at preview resolution, without changing image L."""
    import copy
    import numpy as np
    from PIL import Image
    from . import editor_ops, imagedisc
    small = copy.deepcopy(doc)
    try:
        for layer in small["layers"]:
            raster = layer.get("raster")
            if raster:
                w, h = raster["width"], raster["height"]
                if type(w) is not int or type(h) is not int or not 0 < w * h <= 36_000_000:
                    raise ValueError()
                raw = base64.b64decode(raster["rgba"], validate=True)
                if len(raw) != w * h * 4:
                    raise ValueError()
                image = Image.frombytes("RGBA", (w, h), raw)
            elif layer.get("picture"):
                with Image.open(io.BytesIO(base64.b64decode(layer["picture"].split(",", 1)[1], validate=True))) as opened:
                    if opened.width * opened.height > 36_000_000:
                        raise ValueError()
                    opened.thumbnail((512, 512))
                    image = opened.convert("RGBA")
            else:
                continue
            image.thumbnail((512, 512))
            layer["raster"] = dict(width=image.width, height=image.height,
                                   rgba=base64.b64encode(image.tobytes()).decode("ascii"))
            layer.setdefault("w", image.width)
            layer.setdefault("h", image.height)
        labels = editor_ops.compose(small, g=editor_ops.grid(512))
        output = io.BytesIO()
        output.name = "thumb.png"
        imagedisc.preview(np.asarray(labels != 0), output, size=512)
        return output.getvalue()
    except (ValueError, OSError, KeyError, TypeError, IndexError, OverflowError, ZeroDivisionError):
        raise WorkError("cannot render design thumbnail") from None


def check_thumb(raw):
    from PIL import Image
    if not 0 < len(raw) <= THUMB_LIMIT:
        raise WorkError("invalid thumbnail size", 413)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.size != (512, 512):
                raise ValueError()
            image.verify()
    except (ValueError, OSError):
        raise WorkError("thumbnail must be a 512 x 512 PNG") from None
    return raw


class Store:
    def __init__(self, results="results"):
        self.root = data_root(results) / "works"
        with _locks_guard:
            self._thread_lock = _locks.setdefault(str(self.root), threading.RLock())

    def _geo_ref(self, doc):
        # Old portable files may carry another computer's absolute path. Keep
        # it in the verbatim design, but only link metadata inside this data root.
        value = doc.get("geo")
        if not isinstance(value, str) or not value or "\x00" in value:
            return None
        path = Path(value.replace("\\", "/"))
        if path.is_absolute():
            try:
                path = path.relative_to(self.root.parent)
            except ValueError:
                return None
        elif path.drive:
            return None
        path = Path(os.path.normpath(path))
        if ".." in path.parts or ":" in path.as_posix():
            return None
        return path.as_posix()

    def _safe(self, path):
        path = Path(path)
        # A symlink/junction can redirect even a syntactically valid id.
        if redirected(path) or not path.resolve().is_relative_to(self.root.resolve()):
            raise WorkError("unsafe work path")
        parent = path
        while parent != self.root:
            if redirected(parent):
                raise WorkError("unsafe work path")
            parent = parent.parent
        return path

    @contextmanager
    def _locked(self):
        with self._thread_lock:
            if redirected(self.root):
                raise WorkError("unsafe work path")
            self.root.mkdir(parents=True, exist_ok=True)
            lock_path = self._safe(self.root / ".lock")
            with lock_path.open("a+b") as lock:
                if os.name == "nt":
                    import msvcrt
                    if lock.seek(0, 2) == 0:
                        lock.write(b"0")
                        lock.flush()
                    while True:
                        try:
                            lock.seek(0)
                            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            time.sleep(.025)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    trash = self._safe(self.root / ".trash")
                    trash.mkdir(exist_ok=True)
                    for folder in (*self.root.iterdir(), *trash.iterdir()):
                        if ID.fullmatch(folder.name):
                            self._safe(folder)
                            if self._safe(folder / ".pending.json").is_file():
                                self._recover(folder)
                    yield
                    self._expire_trash()
                finally:
                    if os.name == "nt":
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)

    def _folder(self, ident, trash=False):
        path = self._safe(self.root / (".trash" if trash else "") / valid_id(ident))
        if not path.is_dir():
            raise WorkError("work not found", 404)
        return path

    def _read(self, folder):
        return json.loads(self._safe(folder / "work.json").read_bytes())

    def _history(self, folder):
        raw = self._safe(folder / "history.jsonl").read_bytes()
        return [json.loads(line) for line in raw.splitlines() if line]

    def _recover(self, folder):
        """Replay a flushed intent before any reader can see a multi-file save."""
        pending = self._safe(folder / ".pending.json")
        txn = json.loads(pending.read_bytes())
        for name, value in txn["files"].items():
            if name not in ("work.json", "design.discdesign", "thumb.png") and not ASSET.fullmatch(name):
                raise WorkError("unsafe work path")
            atomic(self._safe(folder / name), base64.b64decode(value, validate=True))
        event = txn["event"]
        history = self._safe(folder / "history.jsonl")
        raw = history.read_bytes()
        # A crash may leave an incomplete final append. Preserve the committed prefix.
        complete = raw[:raw.rfind(b"\n") + 1]
        if raw != complete:
            with history.open("r+b") as stream:
                stream.truncate(len(complete))
        last = json.loads(complete.splitlines()[-1]) if complete else {}
        if last.get("event_id") != event["event_id"]:
            with history.open("ab") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        if txn.get("move"):
            target = self._safe(self.root / txn["move"])
            if target != folder:
                os.replace(folder, target)
                pending = target / pending.name
        pending.unlink()

    def _event(self, kind, **fields):
        return dict(type=kind, time=stamp(), event_id=secrets.token_hex(16), **fields)

    def _update(self, folder, work, kind, files=None, move=None, **fields):
        now = datetime.fromisoformat(stamp())
        previous = datetime.fromisoformat(work["updated_at"])
        # If-Match must advance even on a coarse or backwards-adjusted clock.
        work["updated_at"] = max(now, previous + timedelta(microseconds=1)).isoformat(timespec="microseconds")
        writes = dict(files or {})
        writes["work.json"] = encoded(work)  # metadata is published after the content
        atomic(folder / ".pending.json", encoded(dict(
            files={k: base64.b64encode(v).decode("ascii") for k, v in writes.items()},
            event=self._event(kind, **fields), move=move)))
        self._recover(folder)
        return work

    def _new_id(self):
        while True:
            ident = datetime.now(timezone.utc).strftime("w-%Y%m%d-%H%M%S-") + secrets.token_hex(2)
            if not (self.root / ident).exists() and not (self.root / ".trash" / ident).exists():
                return ident

    def _publish(self, ident, files):
        folder = Path(tempfile.mkdtemp(prefix=".new-", dir=self.root))
        try:
            for name, raw in files.items():
                atomic(folder / name, raw)
            (folder / "assets").mkdir(exist_ok=True)
            os.replace(folder, self._safe(self.root / ident))
        finally:
            if folder.exists():
                shutil.rmtree(folder)

    def new(self, name, media="dvd", raw=None, source_file=None):
        self._name(name)
        if media not in ("cd", "dvd", "bd"):
            raise WorkError("invalid work media")
        raw = raw if raw is not None else encoded(dict(format="disc-probe design", version=2, media=media, layers=[]))
        doc = read_design(raw)
        files = assets(doc)
        files.update({"design.discdesign": raw, "thumb.png": thumbnail(doc)})
        with self._locked():
            ident, now = self._new_id(), stamp()
            work = dict(id=ident, name=name, created_at=now, updated_at=now, opened_at=now,
                        media=doc.get("media", media), disc_type="-R", batch=None,
                        geo_run=self._geo_ref(doc), photo_l=None, cell_um=round(doc.get("cell", .02) * 1000),
                        status="draft", discs=[], source_file=source_file)
            self._validate_meta(work)
            first_event = json.dumps(self._event("created"), ensure_ascii=False).encode("utf-8") + b"\n"
            files.update({"work.json": encoded(work), "history.jsonl": first_event})
            self._publish(ident, files)
            return work

    def list(self, status=None, media=None, sort="time"):
        if status and status not in STATUSES or media and media not in ("cd", "dvd", "bd") or sort not in ("time", "name"):
            raise WorkError("invalid work filter")
        with self._locked():
            rows = [self._read(p) for p in self.root.iterdir() if ID.fullmatch(p.name) and p.is_dir()]
            rows = [w for w in rows if (not status or w["status"] == status) and (not media or w["media"] == media)]
            return sorted(rows, key=lambda w: (w["name"].casefold(), w["id"]) if sort == "name" else (w["updated_at"], w["id"]), reverse=sort == "time")

    def show(self, ident, *, opened=False):
        with self._locked():
            folder = self._folder(ident)
            work = self._read(folder)
            if opened:
                work["opened_at"] = stamp()
                atomic(folder / "work.json", encoded(work))
            return dict(work, history=self._history(folder)[-50:])

    def content(self, ident, name):
        if name not in ("design.discdesign", "thumb.png"):
            raise WorkError("unsafe work path")
        with self._locked():
            return self._safe(self._folder(ident) / name).read_bytes()

    def save(self, ident, raw, thumb=None, if_match=None):
        doc = read_design(raw)
        files = assets(doc)
        files.update({"design.discdesign": raw, "thumb.png": check_thumb(thumb) if thumb is not None else thumbnail(doc)})
        with self._locked():
            folder = self._folder(ident)
            work = self._read(folder)
            if if_match is not None and if_match.strip('"') != work["updated_at"]:
                raise WorkError("another window changed this work", 409)
            work.update(media=doc.get("media", work["media"]), geo_run=self._geo_ref(doc),
                        cell_um=round(doc.get("cell", .02) * 1000))
            self._validate_meta(work)
            return self._update(folder, work, "saved", files)

    def set_thumb(self, ident, raw):
        check_thumb(raw)
        with self._locked():
            folder = self._folder(ident)
            return self._update(folder, self._read(folder), "thumbnail", {"thumb.png": raw})

    @staticmethod
    def _name(name):
        if not isinstance(name, str) or not name.strip() or len(name) > 256 or any(ord(c) < 32 for c in name):
            raise WorkError("invalid work name")

    def _validate_meta(self, work):
        try:
            json.dumps(work, allow_nan=False)
        except (ValueError, TypeError):
            raise WorkError("invalid work metadata") from None
        self._name(work.get("name"))
        valid_id(work.get("id"))
        if (work.get("media") not in ("cd", "dvd", "bd") or work.get("disc_type") not in ("-R", "+R", "RW")
                or work.get("status") not in STATUSES or work.get("cell_um") not in (20, 10, 5)
                or not isinstance(work.get("discs"), list)):
            raise WorkError("invalid work metadata")
        if work.get("status") == "failed" and not work.get("note", "").strip():
            raise WorkError("failed work needs a reason")
        geo = work.get("geo_run")
        if geo is not None and (not isinstance(geo, str) or ":" in geo or "\\" in geo or geo.startswith("/") or ".." in geo.split("/")):
            raise WorkError("geo run must be relative to the data directory")
        for key in ("created_at", "updated_at", "opened_at"):
            try:
                if datetime.fromisoformat(work[key]).tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise WorkError("invalid work metadata") from None

    def patch(self, ident, changes):
        if not isinstance(changes, dict) or not changes or set(changes) - {"name", "status", "note", "disc_type", "batch", "geo_run", "photo_l", "cell_um"}:
            raise WorkError("invalid work metadata")
        if "note" in changes and (not isinstance(changes["note"], str) or len(changes["note"]) > 4096):
            raise WorkError("invalid work metadata")
        if changes.get("status") == "failed" and not changes.get("note", "").strip():
            raise WorkError("failed work needs a reason")
        with self._locked():
            folder = self._folder(ident)
            work = self._read(folder)
            work.update(changes)
            self._validate_meta(work)
            return self._update(folder, work, "renamed" if set(changes) == {"name"} else "marked", changes=changes)

    def _files(self, folder):
        names = ["work.json", "design.discdesign", "thumb.png", "history.jsonl"]
        asset_dir = self._safe(folder / "assets")
        names += ["assets/" + p.name for p in asset_dir.iterdir() if ASSET.fullmatch("assets/" + p.name)]
        return {name: self._safe(folder / name).read_bytes() for name in sorted(names)}

    def duplicate(self, ident, name=None):
        with self._locked():
            folder = self._folder(ident)
            files = self._files(folder)
            work = self._read(folder)
            work.update(id=self._new_id(), name=name if name is not None else work["name"],
                        created_at=stamp(), updated_at=stamp(), opened_at=stamp())
            self._validate_meta(work)
            files["work.json"] = encoded(work)
            files["history.jsonl"] += json.dumps(self._event("duplicated", source=ident), ensure_ascii=False).encode("utf-8") + b"\n"
            self._publish(work["id"], files)
            return work

    def delete(self, ident):
        with self._locked():
            folder = self._folder(ident)
            work = self._read(folder)
            work["deleted_at"] = stamp()
            return self._update(folder, work, "deleted", move=".trash/" + ident)

    def restore(self, ident):
        with self._locked():
            folder = self._folder(ident, trash=True)
            if (self.root / ident).exists():
                raise WorkError("work id already exists", 409)
            work = self._read(folder)
            work.pop("deleted_at", None)
            return self._update(folder, work, "restored", move=ident)

    def purge_trash(self):
        """Explicit maintenance: never remove a work before its 30-day grace period."""
        with self._locked():
            return self._expire_trash()

    def _expire_trash(self):
        removed = []
        for folder in (self.root / ".trash").iterdir():
            if ID.fullmatch(folder.name):
                self._safe(folder)
                when = self._read(folder).get("deleted_at")
                if when and datetime.fromisoformat(when) < datetime.now(timezone.utc) - timedelta(days=30):
                    # Validate every child before any recursive removal.
                    for path in folder.rglob("*"):
                        self._safe(path)
                    shutil.rmtree(folder)
                    removed.append(folder.name)
        return removed

    def export(self, ident):
        with self._locked():
            files = self._files(self._folder(ident))
            if len(files) > 1024 or sum(map(len, files.values())) > ARCHIVE_LIMIT:
                raise WorkError("invalid archive size", 413)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in files.items():
                    archive.writestr(name, raw)
            raw = output.getvalue()
            if len(raw) > ARCHIVE_LIMIT:
                raise WorkError("invalid archive size", 413)
            return raw

    def import_bytes(self, raw, source_file=None):
        if not 0 < len(raw) <= ARCHIVE_LIMIT:
            raise WorkError("invalid archive size", 413)
        if not raw.startswith(b"PK"):
            doc = read_design(raw)
            name = Path(source_file).stem if source_file else "Untitled"
            return self.new(name, doc.get("media", "dvd"), raw, source_file)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 1024 or sum(e.file_size for e in entries) > ARCHIVE_LIMIT:
                    raise WorkError("invalid archive size", 413)
                names = [e.filename for e in entries]
                required = {"work.json", "design.discdesign", "thumb.png", "history.jsonl"}
                if (len(set(names)) != len(names) or not required <= set(names) or any(
                        n not in required and not ASSET.fullmatch(n) for n in names)
                        or any((e.external_attr >> 16) & 0o170000 == 0o120000 for e in entries)):
                    raise WorkError("unsafe work archive")
                files = {e.filename: archive.read(e) for e in entries}
            work = json.loads(files["work.json"])
            if not isinstance(work, dict):
                raise ValueError()
            self._validate_meta(work)
            if "deleted_at" in work:
                raise ValueError()
            doc = read_design(files["design.discdesign"])
            check_thumb(files["thumb.png"])
            for name, value in files.items():
                if ASSET.fullmatch(name) and hashlib.sha256(value).hexdigest() != name.split("/")[1]:
                    raise ValueError()
            if any(files.get(name) != value for name, value in assets(doc).items()):
                raise ValueError()
            if files["history.jsonl"] and not files["history.jsonl"].endswith(b"\n"):
                raise ValueError()
            for line in files["history.jsonl"].splitlines():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError()
                json.dumps(event, allow_nan=False)
        except WorkError:
            raise
        except (ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise WorkError("invalid work archive") from None
        with self._locked():
            ident = work["id"]
            if (self.root / ident).exists() or (self.root / ".trash" / ident).exists():
                raise WorkError("work id already exists", 409)
            self._publish(ident, files)
            return work

    def link(self, ident, iso, *, kind="iso", drive=None, speed=None, disc_code=None, result="completed", **details):
        path = Path(iso).resolve()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        record = dict(iso_path=str(path), iso_sha256=digest.hexdigest(), time=stamp(),
                      drive=drive, speed=speed, disc_code=disc_code, result=result, type=kind, **details)
        with self._locked():
            # A queued job may finish after the user sends its work to the trash.
            folder = self._safe(self.root / valid_id(ident))
            if not folder.is_dir():
                folder = self._folder(ident, trash=True)
            work = self._read(folder)
            work["discs"].append(record)
            work["status"] = "burned" if kind == "burn" else "iso_ready"
            return self._update(folder, work, kind, record=record)
