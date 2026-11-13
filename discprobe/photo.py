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
PHOTO_L_POLICY = "two-poses-v1"
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
    sp.add_argument("--disc-id", help="physical target disc identifier shared by these photos")
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


def photo_l(geo_summary, photo_path=None, *, device_id=None, media=None, frozen=None):
    """The application gate for picture ISOs and presets. Refusals retain no L.

    No batch/MID participates in the drive comparison. Missing burn details stay
    unknown, scoped to this exact run; they are never guessed from its read method.
    """
    summary = Path(geo_summary).resolve()
    if summary.is_dir():
        summary /= "summary.json"
    path = Path(photo_path).resolve() if photo_path else summary.parent / "photo.json"
    def refused(reason):
        return dict(written=False, reason=reason)
    try:
        raw = summary.read_bytes()
        geo = json.loads(raw)
        fit = geo.get("fit") or {}
        wanted = media or fit.get("media", "dvd")
        if wanted not in ("cd", "dvd") or fit.get("media") == "bd":
            return refused("unsupported_media: photo L supports CD and DVD only")
        if fit.get("model") == "clv":
            return refused("unsupported_model: CLV has no calibrated angle map")
        if frozen is None and not path.is_file():
            return refused("no_photo")
        if frozen is not None:
            if not isinstance(frozen, dict) or frozen.get("written") is not True:
                return refused("invalid_saved_photo_L")
            provenance = frozen["provenance"]
            digest = hashlib.sha256(json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if (digest != frozen.get("provenance_sha256") or provenance.get("policy") != PHOTO_L_POLICY
                    or provenance.get("L_mm") != frozen.get("L_mm")):
                return refused("invalid_saved_photo_L")
            path = Path(provenance["photo_json"]).resolve()
            record = dict(path=str(Path(provenance["geo_summary"]).parent), media=provenance["media"],
                          verdict=provenance["verdict"], offset_mm=provenance["L_mm"],
                          L_frames=frozen.get("frames"), photos=provenance["photos"],
                          reader_version=provenance["reader_version"], reader_sha256=provenance["reader_sha256"],
                          disc_id=provenance["disc_id"], burn_path=provenance["burn_path"],
                          source_geo=dict(run_id=provenance["geo_run_id"], sha256=provenance["geo_sha256"],
                                          drive_identity=provenance["drive_identity"]))
            photo_hash = provenance["photo_sha256"]
        else:
            photo_raw = path.read_bytes()
            record = json.loads(photo_raw)
            photo_hash = hashlib.sha256(photo_raw).hexdigest()
        if not isinstance(record, dict):
            return refused("invalid_photo")
        if record.get("media") != wanted or fit.get("media", "dvd") != wanted:
            return refused("different_media")
        if record.get("verdict") != "ok":
            return refused("verdict_not_ok")
        if record.get("group", {}).get("status") not in (None, "ok"):
            return refused("verdict_not_ok")
        offset = record.get("offset_mm")
        if not _finite(offset):
            return refused("missing_L")
        if wanted == "cd":
            from .pcal import CD_FRAME_MM
            if not _finite(record.get("L_frames")):
                return refused("missing_L")
            if not math.isclose(record["L_frames"] * CD_FRAME_MM, offset, abs_tol=1e-9):
                return refused("inconsistent_L")
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
        burn = record.get("burn_path") or {}
        if not all(isinstance(burn.get(k), str) and burn[k].strip() for k in ("burner", "path", "mode")):
            return refused("unknown_burn_path")
        if not isinstance(record.get("disc_id"), str) or not record["disc_id"].strip():
            return refused("unknown_disc")
        for shot in record.get("photos", []):
            if shot.get("status") == "ok":
                if not shot.get("disc_id"):
                    return refused("unknown_disc")
                if shot["disc_id"] != record["disc_id"]:
                    return refused("different_disc")
        agreement = photo_agreement(record.get("photos", []))
        if not agreement["written"]:
            return agreement
        if not math.isclose(offset, agreement["L_mm"], abs_tol=1e-9):
            return refused("inconsistent_L")
        provenance = dict(geo_run_id=summary.parent.name, geo_summary=str(summary),
                          geo_sha256=source["sha256"], photo_json=str(path),
                          photo_sha256=photo_hash, media=wanted,
                          reader_version=record.get("reader_version", "v1"),
                          reader_sha256=record.get("reader_sha256"), policy=PHOTO_L_POLICY, L_mm=offset,
                          disc_id=record["disc_id"], drive_identity=current, burn_path=burn, verdict="ok",
                          photo_ids=agreement["photo_ids"],
                          input_sha256=agreement["input_sha256"],
                          photos=[{k: p.get(k) for k in ("id", "disc_id", "status", "L_mm", "zone_spread_mm", "c_deg", "input_sha256")}
                                  for p in record["photos"] if p.get("status") == "ok"],
                          scope="this geometry run and burn path; independent of disc batch")
        if provenance["reader_version"] != "v1" or provenance["reader_sha256"] != READER_SHA256:
            return refused("unknown_reader")
        digest = hashlib.sha256(json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        result = dict(written=True, L_mm=offset, provenance=provenance, provenance_sha256=digest,
                      reader_version=provenance["reader_version"])
        if wanted == "cd":
            from .pcal import CD_FRAME_MM
            result["frames"] = offset / CD_FRAME_MM
            from .cd import FRAME_BITS, SECTOR_BITS
            result["channel_bits"] = result["frames"] * FRAME_BITS
        else:
            from .calib import SECTOR_BITS
            bit = fit.get("bit_nm_assumed")
            if not _finite(bit) or bit <= 0:
                return refused("unknown_channel_bit_length")
            result["channel_bits"] = offset / (bit * 1e-6)
        result["sectors"] = result["channel_bits"] / SECTOR_BITS
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return refused("invalid_photo")


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def photo_agreement(photos):
    """No pooling or outlier selection: every individually accepted shot must agree.

    The stated spread is the full radial-zone spread (not a probability). Each
    interval has half that width. Require overlap for every pair and at least
    10 degrees of measured disc rotation, plus distinct original input hashes.
    """
    use = [p for p in photos if p.get("status") == "ok"]
    def no(reason):
        return dict(written=False, reason=reason)
    if len(use) < 2:
        return no("one_photo_provisional" if use else "no_accepted_photos")
    if any(not all(_finite(p.get(k)) for k in ("L_mm", "zone_spread_mm", "c_deg"))
           or p["zone_spread_mm"] < 0 for p in use):
        return no("unknown_spread_or_pose")
    hashes = [p.get("input_sha256") for p in use]
    if any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes):
        return no("unknown_photo_input")
    if len(set(hashes)) != len(use):
        return no("duplicate_photo")
    different = False
    for i, a in enumerate(use):
        for b in use[i + 1:]:
            if abs(a["L_mm"] - b["L_mm"]) > (a["zone_spread_mm"] + b["zone_spread_mm"]) / 2:
                return no("photos_disagree")
            different |= abs((a["c_deg"] - b["c_deg"] + 180) % 360 - 180) >= 10
    if not different:
        return no("same_pose")
    lo = max(p["L_mm"] - p["zone_spread_mm"] / 2 for p in use)
    hi = min(p["L_mm"] + p["zone_spread_mm"] / 2 for p in use)
    # The mean may fall outside a narrow member's interval; use the intersection.
    value = min(hi, max(lo, sum(p["L_mm"] for p in use) / len(use)))
    return dict(written=True, L_mm=value, photo_ids=[p.get("id") for p in use], input_sha256=hashes)


def photo_shift(geo_summary, photo_path=None, *, device_id=None):
    """CD frame adapter for DIS; eligibility is decided only by photo_l."""
    decision = photo_l(geo_summary, photo_path, device_id=device_id)
    if decision["written"] and "frames" not in decision:
        return dict(written=False, reason="not_cd")
    return decision


def shifted_u(fit, decision):
    """theta(n-d), modulo a free rotation; d is channel bits, never CD frames on DVD."""
    if not decision.get("written"):
        return fit["u"]
    if fit.get("model") == "clv" or fit.get("media", "dvd") not in ("cd", "dvd"):
        raise ValueError("Photo L needs a CD or DVD constant-pitch angle map")
    if fit.get("media") == "cd":
        from .pcal import CD_FRAME_MM
        from .cd import FRAME_BITS
        d = decision["L_mm"] / CD_FRAME_MM * FRAME_BITS
    else:
        d = decision["L_mm"] / (fit["bit_nm_assumed"] * 1e-6)
    squared = fit["u"] ** 2 - fit["v"] * d / math.pi
    if not math.isfinite(squared) or squared <= 0:
        raise ValueError("Photo L moves the geometry origin outside the supported spiral")
    return math.sqrt(squared)


def image_photo_l(geo_summary, output, *, media, device_id=None, disabled=False, suffix=".image.json"):
    """Reuse this output's immutable accepted evidence when reopening the same run."""
    if disabled:
        return dict(written=False, reason="opted_out")
    saved = Path(output).with_suffix(suffix)
    if saved.is_file():
        try:
            decision = json.loads(saved.read_text(encoding="utf-8")).get("photo_l")
            if decision and decision.get("written"):
                return photo_l(geo_summary, device_id=device_id, media=media, frozen=decision)
        except (OSError, ValueError, TypeError, AttributeError):
            return dict(written=False, reason="invalid_saved_photo_L")
    return photo_l(geo_summary, device_id=device_id, media=media)


def analyze(run_dir, media, photos, rings_mm=None, *, burner=None, burn_path=None, burn_mode=None, disc_id=None):
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
        digest = None
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
        reading["disc_id"] = disc_id
        reading["input_sha256"] = digest
        readings.append(reading)
        status = reading["status"]
        per_photo.append(dict(id=ident, verdict="ok" if status == "ok" else "unsure", status=status,
                              reason=REASONS.get(status, "The reader cannot determine a reliable alignment.")))
        log(f"{ident}: {status}")
    group = pcal.combine(readings)
    agreement = photo_agreement(readings)
    accepted = agreement["written"] and group["status"] == "ok"
    offset = agreement.get("L_mm") if accepted else None
    result = dict(verdict="ok" if accepted else "unsure", per_photo=per_photo,
                  rings_mm=[r for r, _, _ in design.rings] if any(p.get("H") for p in readings) else None,
                  offset_mm=offset, L_frames=offset / pcal.CD_FRAME_MM if accepted and media == "cd" else None,
                  confidence=None, path=str(folder))
    single = [p for p in readings if p.get("status") == "ok"]
    result["provisional_mm"] = single[0].get("L_mm") if len(single) == 1 else None
    # No calibrated probability was established by the research; keep confidence unknown.
    record = dict(**result, media=media, reader_version="v1", reader_sha256=READER_SHA256,
                  photos=readings, group=group, application_agreement=agreement, disc_id=disc_id,
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
                                              ": " + agreement.get("reason", group.get("why", "take another photo"))))
    if result["provisional_mm"] is not None:
        log(f"Provisional photo L: {result['provisional_mm']:+.6f} mm; take another pose before applying it.")
    return result


def log(message):
    ui.event("log", text=message, level="info")
    print(message, flush=True)


def run(args):
    try:
        analyze(args.run, args.media, [(Path(p).stem, p) for p in args.photos], args.rings_mm,
                burner=args.burner, burn_path=args.burn_path, burn_mode=args.burn_mode,
                disc_id=getattr(args, "disc_id", None))
    except Exception as exc:
        ui.event("error", message=str(exc))
        raise


def lan_ips():
    """Discover a private interface without sending packets or contacting an Internet service."""
    try:
        candidates = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return []
    addresses = set()
    for item in candidates:
        try:
            address = ipaddress.IPv4Address(item[4][0])
        except ValueError:
            continue
        if address.is_private and not (address.is_loopback or address.is_link_local
                                       or address.is_unspecified or address.is_reserved or address.is_multicast):
            addresses.add(address)
    # A virtual switch (Hyper-V / WSL, often 172.x) sorts before the Wi-Fi address and phones can't reach it.
    # Put first the address the default route leaves from: a UDP connect picks the route and sends nothing.
    first = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))           # TEST-NET-1, never contacted
            first = ipaddress.IPv4Address(probe.getsockname()[0])
    except (OSError, ValueError):
        pass
    return [str(address) for address in sorted(addresses, key=lambda a: (a != first, a))]


def lan_ip():
    return next(iter(lan_ips()), None)


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
            try:
                record = json.loads((folder.parent / "photo.json").read_text(encoding="utf-8"))
                readings = {p["id"]: p for p in record.get("per_photo", [])}
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                record, readings = {}, {}
            for row in rows:
                reading = readings.get(row["id"], {})
                row.update({key: reading.get(key) for key in ("verdict", "status", "reason")})
            result = dict(photos=sorted(rows, key=lambda p: (p["time"], p["id"])))
            if record.get("verdict"):
                result["verdict"] = record["verdict"]
            return result

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
        if not isinstance(args, dict) or set(args) - {"run", "media", "photos", "rings_mm", "burner", "burn_path", "burn_mode", "disc_id"}:
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
        for key in ("burner", "burn_path", "burn_mode", "disc_id"):
            value = args.get(key)
            if value is not None:
                if (not isinstance(value, str) or not 1 <= len(value) <= 500
                        or value.startswith("-") or any(ord(c) < 32 for c in value)):
                    raise ValueError("invalid " + key)
                argv += ["--" + key.replace("_", "-"), value]
        return argv
