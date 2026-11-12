"""Read target photographs without accessing a drive; run-scoped photo storage for webui."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from urllib.parse import unquote

from . import ui

READER_SHA256 = "d6375faed8fe489e01854dc09afcbaf057d7042968c5157f5ae56dc8ed4a9f6f"
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/heic": "heic", "image/webp": "webp"}
REASONS = {
    "ok": "The photo passed the reader's checks.",
    "no_rim": "Could not locate the disc. Put the whole disc in the frame and take another photo.",
    "too_few_votes": "Too little readable pattern. Turn the disc and try different lighting.",
    "few_inliers": "Too few consistent parts of the pattern. Take another photo.",
    "rings_not_found": "The target rings could not be located reliably.",
    "weak_peak": "The pattern is too weak to read reliably.",
    "two_peaks": "Two different alignments look plausible. Take another photo.",
    "poor_angle_coverage": "Readable pattern covers too little of the disc. Turn it and take another photo.",
    "poor_radius_coverage": "Readable pattern does not span enough inner and outer rings.",
    "large_residual": "The pattern does not fit the expected geometry.",
    "unstable_L": "The offset changes too much when part of this photo is left out.",
    "shape_not_1_over_r": "Different ring bands do not support one along-track offset.",
    "unreadable_image": "This image could not be decoded. Try exporting it as JPEG or PNG.",
    "duplicate_photo": "This is the same image as another input. Turn the disc and take a different photo.",
}


def rings_arg(values):
    if values is None:
        return None
    if (not isinstance(values, list) or not 2 <= len(values) <= 20
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 25.5 <= v <= 58 for v in values)
            or any(b - a <= 2 for a, b in zip(values, values[1:]))):
        raise ValueError("rings_mm must be increasing radii in 25.5..58 mm, more than 2 mm apart")
    return values


def add_parser(sub):
    sp = sub.add_parser("photo", help="read the along-track residual from target photos (no drive access)")
    sp.add_argument("--run", required=True, help="calibration result directory")
    sp.add_argument("--media", required=True, choices=("cd", "dvd"))
    sp.add_argument("--photos", required=True, nargs="+", help="image files")
    sp.add_argument("--rings-mm", type=float, nargs="+", help="target ring radii; default: the burned PN target")
    sp.add_argument("--burner", help="specific burner identity used for this target (unknown if omitted)")
    sp.add_argument("--burn-path", help="target burn program/path, e.g. DIS or IMAPI (never inferred)")
    sp.add_argument("--burn-mode", help="target burn mode, including sector layout/interleave (never inferred)")
    sp.set_defaults(func=run)


def drive_identity(geo, folder):
    """Use the model AND the recorded device, never the model as a machine identity.

    Older summaries only have a model. Their run name retains the device selected
    by the page (geo-H-YYYYMMDD-HHMMSS on Windows).
    """
    identity = geo.get("identity") or {}
    device = identity.get("device_id") or identity.get("device")
    match = re.fullmatch(r"geo-(.+)-\d{8}-\d{6}", Path(folder).name)
    if not device and match:
        device = match[1] + ":" if re.fullmatch(r"[A-Za-z]", match[1]) else match[1]
    return dict(model=identity.get("drive"), device_id=device,
                serial=identity.get("serial"), firmware=identity.get("firmware"),
                machine=socket.gethostname())


def photo_shift(geo_summary, photo_path=None, *, device_id=None):
    """One provenance gate shared by web and CLI exports. Refusals retain no L.

    No batch/MID participates in the drive comparison. Missing burn details stay
    unknown, scoped to this exact run; they are never guessed from its read method.
    """
    summary = Path(geo_summary).resolve()
    if summary.is_dir():
        summary /= "summary.json"
    path = Path(photo_path).resolve() if photo_path else summary.parent / "photo.json"
    def refused(reason):
        return dict(written=False, reason=reason)
    if not path.is_file():
        return refused("no_photo")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        raw = summary.read_bytes()
        geo = json.loads(raw)
        if not isinstance(record, dict):
            return refused("invalid_photo")
        if record.get("verdict") != "ok":
            return refused("verdict_not_ok")
        frames = record.get("L_frames")
        if type(frames) not in (int, float) or not math.isfinite(frames):
            return refused("missing_L")
        source = record.get("source_geo") or {}
        run = source.get("run_id")
        # The original contract's path is the photo run, not just its basename.
        if (not record.get("path") or Path(record["path"]).resolve() != summary.parent
                or path.parent != summary.parent or (run and run != summary.parent.name)):
            return refused("different_run")
        current = drive_identity(geo, summary.parent)
        original = source.get("drive_identity")
        if not original:
            # A legacy model label cannot establish the original machine.
            return refused("unknown_drive")
        if (not all(isinstance(current[k], str) and current[k] for k in ("model", "device_id"))
                or not all(isinstance(original.get(k), str) and original[k]
                           for k in ("model", "device_id", "machine"))):
            return refused("unknown_drive")
        if original != current or (device_id is not None and device_id != current["device_id"]):
            return refused("different_drive")
        if source.get("sha256") != hashlib.sha256(raw).hexdigest():
            return refused("different_run")
        if record.get("media") != "cd" or geo.get("fit", {}).get("media") != "cd":
            return refused("not_cd")
        provenance = dict(geo_run_id=summary.parent.name, geo_summary=str(summary),
                          geo_sha256=source["sha256"], photo_json=str(path),
                          drive_identity=current, burn_path=record.get("burn_path") or
                          dict(burner=None, path=None, mode=None), verdict="ok",
                          photo_ids=[p["id"] for p in record.get("per_photo", []) if p.get("id")],
                          scope="this geometry run and burn path; independent of disc batch")
        return dict(written=True, frames=frames, provenance=provenance)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return refused("invalid_photo")


def analyze(run_dir, media, photos, rings_mm=None, *, burner=None, burn_path=None, burn_mode=None):
    """Return and persist both the contract result and the original reader diagnostics.

    Geometry is inferred from rings by the frozen reader; geo's fit is not fed back into it.
    Its source summary/hash are retained because this residual belongs to this run and path.
    A provisional reader value never becomes an applicable offset.
    """
    from . import pcal
    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    folder = Path(run_dir).resolve(strict=True)
    if not folder.is_dir() or media not in ("cd", "dvd"):
        raise ValueError("an existing run directory and cd or dvd media are required")
    rings_mm = rings_arg(rings_mm)
    design = pcal.design_burn() if rings_mm is None else pcal.design_pn(rings=rings_mm)
    summary = folder / "summary.json"
    source = summary.read_bytes() if summary.is_file() else None
    geo = json.loads(source) if source else {}
    inputs = list(photos)
    if not inputs:
        raise ValueError("at least one photo is required")
    readings, per_photo, seen = [], [], set()
    for i, (ident, filename) in enumerate(inputs, 1):
        stage = f"reading photo {i}/{len(inputs)}"
        ui.event("progress", stage=stage, fraction=(i - 1) / len(inputs))
        print(stage, flush=True)
        try:
            with open(filename, "rb") as stream:
                checksum = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    checksum.update(chunk)
                digest = checksum.hexdigest()
            duplicate = digest in seen
            seen.add(digest)
            with Image.open(filename) as original:
                f35 = None
                try:
                    f35 = original.getexif().get_ifd(0x8769).get(0xA405)
                except (AttributeError, ValueError, TypeError, KeyError):
                    pass
                image = np.asarray(ImageOps.exif_transpose(original).convert("RGB"))
            focal = float(f35) / 36 * max(image.shape[:2]) if f35 else None
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            reading = {"status": "unreadable_image"}
        else:
            # Copies of one shot cannot satisfy the frozen reader's two-photo requirement.
            reading = ({"status": "duplicate_photo"} if duplicate else
                       pcal.read_photo(image, design, focal_px=focal, log=lambda *p: log(" ".join(map(str, p)))))
        reading["id"] = ident
        readings.append(reading)
        status = reading["status"]
        per_photo.append(dict(id=ident, verdict="ok" if status == "ok" else "unsure",
                              reason=REASONS.get(status, "The reader cannot determine a reliable alignment.")))
        log(f"{ident}: {status}")
    group = pcal.combine(readings)
    accepted = group["status"] == "ok"
    offset = group.get("L_mm") if accepted else None
    result = dict(verdict="ok" if accepted else "unsure", per_photo=per_photo,
                  rings_mm=[r for r, _, _ in design.rings] if any(p.get("H") for p in readings) else None,
                  offset_mm=offset, L_frames=offset / pcal.CD_FRAME_MM if accepted and media == "cd" else None,
                  confidence=None, path=str(folder))
    # No calibrated probability was established by the research; keep confidence unknown.
    record = dict(**result, media=media, reader_sha256=READER_SHA256, photos=readings, group=group,
                  burn_path=dict(burner=burner, path=burn_path, mode=burn_mode),
                  source_geo=dict(sha256=hashlib.sha256(source).hexdigest() if source else None,
                                  run_id=folder.name, drive_identity=drive_identity(geo, folder),
                                  identity=geo.get("identity"), setup=geo.get("setup")))
    target = folder / "photo.json"
    temporary = folder / (".photo-" + secrets.token_hex(8) + ".json")
    try:
        temporary.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    ui.event("progress", stage=f"reading photo {len(inputs)}/{len(inputs)}", fraction=1.0)
    ui.event("result", step="photo", **result)
    log(f"Photo verdict: {result['verdict']}" + (f", offset {offset:+.6f} mm" if offset is not None else
                                              ": " + group.get("why", "take another photo")))
    return result


def log(message):
    ui.event("log", text=message, level="info")
    print(message, flush=True)


def run(args):
    try:
        analyze(args.run, args.media, [(Path(p).stem, p) for p in args.photos], args.rings_mm,
                burner=args.burner, burn_path=args.burn_path, burn_mode=args.burn_mode)
    except Exception as exc:
        ui.event("error", message=str(exc))
        raise


def lan_ip():
    """Discover a private interface without sending packets or contacting an Internet service."""
    try:
        candidates = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return None
    for item in candidates:
        address = ipaddress.ip_address(item[4][0])
        if address.is_private and not (address.is_loopback or address.is_link_local or address.is_unspecified):
            return str(address)
    return None


class PhotoStore:
    """One server lifetime, one unguessable capability per existing calibration run.

    Capabilities expire on close, deletion/replacement of the run, or a changed geo summary.
    They grant only this run's photo page and photo endpoints, never the main LAN session.
    """
    def __init__(self, results):
        self.results = Path(results).resolve()
        self.tokens = {}
        self.devices = {}
        self.lock = threading.RLock()

    def run_dir(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", run_id):
            raise ValueError("invalid run id")
        folder = (self.results / run_id).resolve()
        if folder.parent != self.results or not folder.is_dir():
            raise ValueError("run not found")
        return folder

    def _stamp(self, run_id):
        folder = self.run_dir(run_id)
        stat = folder.stat()
        summary = folder / "summary.json"
        # Hashing also invalidates links when a run is remeasured in place.
        digest = hashlib.sha256(summary.read_bytes()).hexdigest() if summary.is_file() else None
        return (stat.st_dev, stat.st_ino, getattr(stat, "st_birthtime", None), digest)

    def token(self, run_id):
        with self.lock:
            stamp = self._stamp(run_id)
            for token, (run, old) in self.tokens.items():
                if run == run_id and old == stamp:
                    return token
            token = secrets.token_urlsafe(32)
            self.tokens[token] = (run_id, stamp)
            return token

    def token_run(self, token):
        with self.lock:
            item = self.tokens.get(token) if isinstance(token, str) else None
            if item:
                try:
                    if self._stamp(item[0]) == item[1]:
                        return item[0]
                except (OSError, ValueError):
                    pass
                self.tokens.pop(token, None)
        raise ValueError("invalid or expired photo token")

    def use(self, token, agent, device_id=None):
        """A random browser cookie distinguishes devices; user-agent is only a display summary."""
        with self.lock:
            run = self.token_run(token)
            row = self.devices.get(device_id)
            if not row or row['token'] != token:
                device_id = secrets.token_hex(16)
                platform = next((p for p in ('iPhone', 'iPad', 'Android', 'Windows', 'Macintosh', 'Linux') if p in agent), None)
                browser = next((name for marker, name in (('Edg/', 'Edge'), ('Firefox/', 'Firefox'),
                    ('Chrome/', 'Chrome'), ('Safari/', 'Safari')) if marker in agent), None)
                summary = ' · '.join(filter(None, (platform, browser))) or '未知设备 / Unknown device'
                row = dict(id=device_id, run=run, token=token, name=summary, kind='phone',
                           first_seen=time.time() * 1000, photos_sent=0)
                self.devices[device_id] = row
            row['last_seen'] = time.time() * 1000
            return device_id

    def connected(self, run_id):
        with self.lock:
            self.run_dir(run_id)
            rows = []
            for row in self.devices.values():
                if row['run'] != run_id:
                    continue
                try:
                    self.token_run(row['token'])
                except ValueError:
                    continue
                rows.append({k: row[k] for k in ('id', 'name', 'kind', 'first_seen', 'last_seen', 'photos_sent')})
            return dict(devices=sorted(rows, key=lambda r: (r['first_seen'], r['id'])))

    def disconnect(self, device_id):
        with self.lock:
            row = self.devices.get(device_id)
            if not row:
                raise ValueError('device not found')
            run = self.token_run(row['token'])
            # The capability is shared by this run: rotate it, revoking every old link.
            self.tokens = {t: item for t, item in self.tokens.items() if item[0] != run}
            self.devices = {i: r for i, r in self.devices.items() if r['run'] != run}
            self.token(run)
            return dict(disconnected=True, run=run)

    def _folder(self, run_id):
        run = self.run_dir(run_id)
        folder = (run / "photos").resolve()
        if folder.parent != run:
            raise ValueError("photo directory must stay inside the run")
        return folder

    def get(self, run_id, ident):
        if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{32}", ident):
            raise ValueError("invalid photo id")
        folder = self._folder(run_id)
        meta = folder / (ident + ".json")
        if meta.is_symlink() or not meta.is_file():
            raise ValueError("photo not found")
        row = json.loads(meta.read_text(encoding="utf-8"))
        kind = row.get("content_type")
        if kind not in PHOTO_TYPES:
            raise ValueError("invalid photo metadata")
        path = folder / (ident + "." + PHOTO_TYPES[kind])
        if path.is_symlink() or not path.is_file():
            raise ValueError("photo not found")
        return path, kind, {k: row[k] for k in ("id", "name", "url", "time")}

    def listing(self, run_id):
        with self.lock:
            folder = self._folder(run_id)
            rows = [self.get(run_id, p.stem)[2] for p in folder.glob("*.json")]
            return dict(photos=sorted(rows, key=lambda p: (p["time"], p["id"])))

    def upload(self, run_id, data, kind, name, *, token=None, device_id=None):
        if kind not in PHOTO_TYPES:
            raise ValueError("JPEG, PNG, HEIC or WebP required")
        with self.lock:
            if token is not None and self.token_run(token) != run_id:
                raise ValueError('photo token belongs to another run')
            folder = self._folder(run_id)
            folder.mkdir(exist_ok=True)
            ident = secrets.token_hex(16)
            name = unquote(name or "photo").replace("\\", "/").rsplit("/", 1)[-1]
            name = "".join(c for c in name if c.isprintable())[:200] or "photo"
            row = dict(id=ident, name=name, url=f"/api/photos/{run_id}/{ident}", time=time.time(), content_type=kind)
            image = folder / (ident + "." + PHOTO_TYPES[kind])
            image.write_bytes(data)
            try:
                (folder / (ident + ".json")).write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            except Exception:
                image.unlink(missing_ok=True)
                raise
            device = self.devices.get(device_id)
            if device and device['token'] == token:
                device['photos_sent'] += 1
                device['last_seen'] = time.time() * 1000
            return {k: row[k] for k in ("id", "name", "url", "time")}

    def argv(self, args):
        if not isinstance(args, dict) or set(args) - {"run", "media", "photos", "rings_mm"}:
            raise ValueError("invalid photo arguments")
        folder = self.run_dir(args.get("run"))
        if args.get("media") not in ("cd", "dvd"):
            raise ValueError("photo requires cd or dvd media")
        ids = args.get("photos")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(p, str) for p in ids):
            raise ValueError("photos must be a nonempty list of photo ids")
        if len(set(ids)) != len(ids):
            raise ValueError("choose each photo only once")
        paths = [str(self.get(args["run"], ident)[0]) for ident in ids]
        rings = rings_arg(args.get("rings_mm"))
        argv = ["--run", str(folder), "--media", args["media"], "--photos", *paths]
        if rings is not None:
            argv += ["--rings-mm", *map(str, rings)]
        return argv
