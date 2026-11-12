"""Opt-in, public disc records. No hardware access and no user/host/path capture.

Wire v2: 64-byte fixed header + canonical UTF-8 JSON envelope + NULs to 8192
bytes, in four slots. Wire v1 (JSON without header) remains readable.
sha256 covers canonical(body): sorted keys, compact separators, no NaN.
This detects corruption, not authenticity. Unknown measurements remain null.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import uuid
import math
import struct

LBA = 21
SIZE = 8192
SECTORS = range(LBA, LBA + SIZE // 2048)
# Frozen placement ABI: only N (recorded sectors, not blank-medium capacity)
# is an input. 32-sector alignment contains a slot in one DVD/BD unit.
PLACEMENT = "spread-v2:N>=32768;21;thirds-window512;end-window1024;align32;maximin-angle-dvd-cd-bd;lower-LBA-tie"
MIN_SECTORS = 32768
COPY_COUNT = 4
MAGIC = b"DISCPROBE.ID".ljust(16, b"\0")
HEADER = struct.Struct("<16sIIII32x")  # name, version, index, count, header + JSON length
_SPIRALS = ((24., .00074, 38688 * .0001333),
            (25., .0016, 16.),
            (24., .00032, 962136 * .0000745 / 32))


def positions(total):
    if total < MIN_SECTORS:
        raise ValueError(f"ISO is too short to spread disc identity: need at least {MIN_SECTORS} recorded sectors")
    def phases(lba):
        return [((math.sqrt(r*r + p*lba*s/math.pi) - r) / p) % 1
                for r, p, s in _SPIRALS]
    out = [LBA]
    for index in (1, 2, 3):
        anchor = total * index // 3 if index < 3 else total - 32
        low = anchor - (512 if index < 3 else 1024)
        high = min(total - 32, anchor + (512 if index < 3 else 0))
        candidates = range((low + 31) // 32 * 32, high // 32 * 32 + 1, 32)
        previous = [phases(x) for x in out]
        def score(x):
            return min(min(abs(a-b), 1-abs(a-b)) for old in previous for a,b in zip(phases(x), old))
        out.append(max(candidates, key=lambda x: (score(x), -x)))
    return out


def encode_copy(record, index):
    validate(record)
    data = canonical(record)
    if len(data) > SIZE - HEADER.size:
        raise ValueError("Disc identity exceeds its fixed 8192-byte slot with header")
    return (HEADER.pack(MAGIC, 2, index, COPY_COUNT, HEADER.size + len(data)) + data).ljust(SIZE, b"\0")


def decode_copy(data, index):
    if len(data) != SIZE:
        raise ValueError("Truncated disc identity")
    magic, version, actual, count, length = HEADER.unpack(data[:HEADER.size])
    if (magic != MAGIC or version != 2 or actual != index or count != COPY_COUNT
            or not HEADER.size < length <= SIZE or any(data[32:HEADER.size])
            or any(data[length:])):
        raise ValueError("Invalid disc identity copy header/padding")
    return decode(data[HEADER.size:length])


def sectors_for(total):
    return [s for lba in positions(total) for s in range(lba, lba + 4)]


def layout(total, media="dvd"):
    unit = 32 if media == "bd" else 16
    return dict(formula=PLACEMENT, total_sectors=total,
                overwritten_lba=[[x, x+4] for x in positions(total)],
                physical_lba=[[x//unit*unit, (x//unit+1)*unit] for x in positions(total)])
NOTICE = ("Disc identity writes a random id, design and burn parameters, without personal data; "
          "anyone with the disc can read it.")


def notice():
    from . import i18n
    print(i18n.tr(NOTICE), flush=True)


def filename(value):
    return re.split(r"[\\/]", str(value).rstrip("/\\"))[-1] if value else None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def file_sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def seal(body):
    return {"body": copy.deepcopy(body), "sha256": hashlib.sha256(canonical(body)).hexdigest()}


def encode(record):
    validate(record)
    data = canonical(record)
    if len(data) > SIZE:
        raise ValueError("Disc identity exceeds its fixed 8192-byte slot")
    return data.ljust(SIZE, b"\0")


def validate(record):
    if not isinstance(record, dict) or set(record) != {"body", "sha256"}:
        raise ValueError("Invalid disc identity envelope")
    body = record["body"]
    if not isinstance(body, dict) or body.get("version") != 1:
        raise ValueError("Unsupported disc identity version")
    if not re.fullmatch(r"[0-9a-f]{32}", str(body.get("id", ""))):
        raise ValueError("Invalid disc identity id")
    if not all(isinstance(body.get(key), dict) for key in ("design", "geometry", "generator")):
        raise ValueError("Invalid disc identity body")
    if body.get("burn") is not None and not isinstance(body["burn"], dict):
        raise ValueError("Invalid disc identity burn fields")
    if record["sha256"] != hashlib.sha256(canonical(body)).hexdigest():
        raise ValueError("Disc identity SHA-256 mismatch")
    return record


def decode(data):
    if data.startswith(MAGIC):
        return decode_copy(data, HEADER.unpack(data[:HEADER.size])[2])
    try:
        return validate(json.loads(data.rstrip(b"\0").decode("utf-8")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid disc identity JSON") from exc


def provenance():
    result = {}
    for key, argv in (("version", ["describe", "--tags", "--always"]),
                      ("git_commit", ["rev-parse", "HEAD"])):
        try:
            p = subprocess.run(["git", *argv], cwd=Path(__file__).parent,
                               capture_output=True, text=True, timeout=5)
            result[key] = p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            result[key] = None
    # The commit alone cannot identify local edits; say so explicitly.
    try:
        p = subprocess.run(["git", "diff", "--quiet"], cwd=Path(__file__).parent, timeout=5)
        result["tracked_changes"] = p.returncode != 0
    except (OSError, subprocess.SubprocessError):
        result["tracked_changes"] = None
    return result


def create(*, code=None, command="image", design=None, u=None, v=None, bit_nm=None,
           textures=None, meta=None, seed=None, source=None, preset_id=None):
    """Build from named fields only; never serialize arbitrary args, meta or argv."""
    meta = meta or {}
    completion = meta.get("completion_source")
    if isinstance(completion, dict):
        completion = {**{k: completion[k] for k in ("origin", "vendor", "product", "firmware") if k in completion},
                      **({"source_file": filename(completion['source'])} if completion.get('source') else {})}
    else:
        completion = None
    source = source or meta.get("source_file")
    geo = meta.get("geometry_from")
    summary_hash = None
    if geo:
        geo_path = Path(geo)
        if geo_path.is_dir():
            geo_path /= "summary.json"
        summary_hash = file_sha256(geo_path)
    image_hash = None
    if source:
        image_hash = file_sha256(source)
    rendered_hash = None
    cell = None
    if design is not None:
        from .imagedisc import cell_mm
        cell = cell_mm(design)
        hasher = hashlib.sha256(canonical({"shape": list(design.shape), "dtype": str(design.dtype)}))
        for row in design:
            hasher.update(row.tobytes(order="C"))
        rendered_hash = hasher.hexdigest()
    body = dict(version=1, id=secrets.token_hex(16), code=code,
                design=dict(name=meta.get("identity_design", meta.get("design", command)), source_file=filename(source),
                            image_sha256=image_hash or rendered_hash, rendered_sha256=rendered_hash,
                            image_hash_scope="source_file_bytes" if image_hash else
                                "canonical_shape_dtype_and_C_array_bytes" if rendered_hash else None,
                            cell_mm=cell, textures=textures, palette_version=1),
                geometry=dict(u=u, v=v, bit_nm=bit_nm, preset_id=preset_id or meta.get("preset_id"),
                              completion_sectors=meta.get("completion_sectors"),
                              completion_source=completion,
                              along_track_frames=meta.get("along_track_frames"),
                              geo_run=filename(Path(geo).parent if geo and Path(geo).suffix else geo),
                              summary_sha256=summary_hash),
                generator=dict(**provenance(), command=command, seed=seed), burn=None)
    return seal(body)


def requested(disc_id=False, disc_id_code=None):
    return bool(disc_id or disc_id_code is not None)


def options(args):
    return dict(disc_id=getattr(args, "disc_id", False),
                disc_id_code=getattr(args, "disc_id_code", None))


def extent(read_sectors):
    """Bounded ECMA-119 root lookup, using an injected sector reader."""
    pvd = read_sectors(16, 1)
    if len(pvd) != 2048 or pvd[:7] != b"\x01CD001\x01":
        return None
    total = int.from_bytes(pvd[80:84], "little")
    root = int.from_bytes(pvd[158:162], "little")
    size = int.from_bytes(pvd[166:170], "little")
    count = (size + 2047) // 2048
    if not 0 < size <= 65536 or root < 18 or root + count > total:
        raise ValueError("Invalid ISO root directory")
    data = read_sectors(root, count)
    if len(data) < size:
        raise ValueError("Truncated ISO root directory")
    pos = 0
    while pos < size:
        length = data[pos]
        if not length:
            pos = (pos // 2048 + 1) * 2048
            continue
        rec = data[pos:pos + length]
        if length < 34 or pos % 2048 + length > 2048 or len(rec) < length or 33 + rec[32] > length:
            raise ValueError("Invalid ISO directory record")
        if rec[33:33 + rec[32]] in (b"DISCPROBE.ID;1", b"DISCPROBE.ID"):
            start = int.from_bytes(rec[2:6], "little")
            length = int.from_bytes(rec[10:14], "little")
            if rec[25] & 2 or length != SIZE or start < 21 or start + SIZE // 2048 > total:
                raise ValueError("Invalid disc identity extent")
            return start, length
        pos += rec[0]
    return None


def read(read_sectors, total=None):
    if total is not None:
        result = inspect_copies(read_sectors, total)
        if result['reason'] == 'absent':
            return None
        if result['reason'] != 'ok':
            raise ValueError(result['reason'])
        return result['record']
    found = extent(read_sectors)
    if found is None:
        return None
    data = read_sectors(found[0], SIZE // 2048)
    if len(data) != SIZE:
        raise ValueError("Truncated disc identity")
    return decode(data)


def inspect_copies(read_sectors, total):
    """No filesystem reads. Inspect every address, even after recovering a record."""
    starts = positions(total) if total >= MIN_SECTORS else [LBA]
    copies, valid = [], []
    legacy = False
    for index, lba in enumerate(starts):
        item = dict(index=index, lba=lba, status='missing')
        try:
            data = read_sectors(lba, 4)
            if len(data) != SIZE:
                raise OSError('short read')
            if data.startswith(MAGIC):
                record = decode_copy(data, index)
            elif index == 0 and data.startswith(b'{"body":'):
                record = decode(data)
                legacy = True
            else:
                copies.append(item)
                continue
            valid.append(record)
            item.update(status='ok', sha256=record['sha256'])
        except OSError as exc:
            item.update(status='unreadable', error=str(exc))
        except ValueError as exc:
            # Malformed JSON/header is damaged content too, never a valid copy.
            item.update(status='hash_mismatch', error=str(exc))
        copies.append(item)
    agree = len({canonical(r) for r in valid}) <= 1 if valid else None
    reason = ('ok' if agree else 'valid_copies_disagree') if valid else (
        'absent' if all(c['status'] == 'missing' for c in copies) else 'no_valid_copy')
    if legacy and any(c['status'] == 'ok' for c in copies[1:]):
        reason, agree = 'mixed_copy_formats', False
    return dict(status='present' if reason == 'ok' else 'absent' if reason == 'absent' else 'invalid',
                reason=reason, hash_verified=bool(valid) and agree, all_valid_agree=agree,
                format_version=1 if legacy else 2, copies=copies,
                record=valid[0] if valid and agree else None)


def read_image(path, *, detailed=False):
    with Path(path).open("rb") as stream:
        def sectors(lba, count):
            stream.seek(lba * 2048)
            return stream.read(count * 2048)
        result = inspect_copies(sectors, Path(path).stat().st_size // 2048)
        if detailed:
            return result
        if result['reason'] not in ('ok', 'absent'):
            raise ValueError(result['reason'])
        return result['record']


def read_device(dev, *, detailed=False):
    from . import mmc
    def sectors(lba, count):
        res = dev.execute(mmc.read10(lba, count), data_len=count * 2048, timeout_s=10)
        if not res.ok:
            raise OSError("Disc identity read failed")
        return res.data
    cap = dev.execute(mmc.read_capacity(), data_len=8, timeout_s=10)
    if not cap.ok or len(cap.data) != 8:
        toc = dev.execute(mmc.read_toc(0), data_len=2048, timeout_s=10)
        tracks = mmc.parse_toc(toc.data).get('tracks', []) if toc.ok else []
        ends = [t['start_lba'] for t in tracks if t['track'] == 0xAA]
        if not ends:
            raise OSError('recorded size unavailable')
        total = max(ends)
    else:
        capacity = mmc.parse_capacity(cap.data)
        if capacity.get('block_length') not in (None, 2048):
            raise ValueError('Disc identity requires 2048-byte data sectors')
        total = capacity['last_lba'] + 1
    result = inspect_copies(sectors, total)
    if detailed:
        return result
    if result['reason'] not in ('ok', 'absent'):
        raise ValueError(result['reason'])
    return result['record']


def preflight(path):
    """Require every reserved copy to be intact BEFORE any drive inspection."""
    result = read_image(path, detailed=True)
    if result['reason'] != 'ok':
        raise ValueError('Burn identity requires an intact ISO generated with --disc-id')
    required = result['copies'][:1] if result['format_version'] == 1 else result['copies']
    if any(c['status'] != 'ok' for c in required):
        raise ValueError('Burn identity requires every copy to be patchable')
    return result


def media_fields(report):
    """Only public hardware/media fields from the existing read-only info report."""
    parsed = lambda key: (report.get(key) or {}).get("parsed") or {}
    inq, atip = parsed("inquiry"), parsed("atip")
    from .info import disc_id
    mid = disc_id(parsed("dvd_prerecorded_0e"), parsed("dvd_plus_adip_11"), {})
    profile = parsed("configuration").get("current_profile")
    from . import mmc
    return dict(vendor=inq.get("vendor"), product=inq.get("product"), firmware=inq.get("revision"),
                mid=mid, atip=atip.get("leadin_start_msf"),
                media_type=mmc.PROFILES.get(profile) if profile is not None else None)


class Overlay(io.BufferedIOBase):
    """Seekable read-only view; the source ISO is never opened for writing."""
    def __init__(self, source, patches):
        self.source, self.patches = source, patches

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.source.tell()

    def seek(self, offset, whence=0):
        return self.source.seek(offset, whence)

    def read(self, size=-1):
        start = self.tell()
        data = bytearray(self.source.read(size))
        for offset, patch in self.patches:
            lo, hi = max(start, offset), min(start + len(data), offset + len(patch))
            if lo < hi:
                data[lo - start:hi - start] = patch[lo - offset:hi - offset]
        return bytes(data)

    def close(self):
        self.source.close()
        super().close()


class PatchedImage:
    """Recorder contract: stat(), open('rb'), path, patches and patch_bundle().

    Deliberately not path-like: an adapter cannot silently drop the patch.
    """
    def __init__(self, path, record):
        self.path, self.record = Path(path), record
        result = preflight(path)
        self.patches = ([(LBA*2048, encode(record))] if result['format_version'] == 1 else
                        [(c['lba']*2048, encode_copy(record, c['index'])) for c in result['copies']])
        self.patch_offset, self.patch_bytes = self.patches[0]

    def patch_bundle(self):
        return (b'DPIDPAT2' + struct.pack('<I', len(self.patches)) +
                b''.join(struct.pack('<qI', offset, len(data)) + data for offset, data in self.patches))

    def verification_lbas(self):
        return {offset//2048//16*16 for offset, _ in self.patches}

    def stat(self):
        return self.path.stat()

    def open(self, mode="rb"):
        if mode != "rb":
            raise ValueError("Disc identity view is read-only")
        return Overlay(self.path.open("rb"), self.patches)


def patch_burn(path, info, *, speed, selected, media, code=None):
    record = preflight(path)['record']
    body = copy.deepcopy(record["body"])
    body["generator"]["template_id"] = body["id"]
    body["id"] = secrets.token_hex(16)  # each physical burn is distinct, even from one ISO
    if code is not None:
        body["code"] = code
    body["burn"] = dict(vendor=info.get("vendor"), product=info.get("product"), firmware=info.get("firmware"),
                        requested_speed_x=speed, selected_speed_x=selected,
                        media_type=info.get("media_type", media), mid=info.get("mid"), atip=info.get("atip"),
                        utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    return PatchedImage(path, seal(body))


def match_register(record, path):
    validate(record)
    register = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(register, dict) or not isinstance(register.get('discs'), list):
        raise ValueError("Invalid disc register")
    discs = register['discs']
    body = record["body"]
    exact = [d for d in discs if d.get("id") == body["id"]]
    codes = [d for d in discs if body.get("code") and d.get("code") == body["code"]]
    return dict(id_matches=exact, code_matches=codes,
                note="A code match alone does not establish physical identity")


def append_register(path, record, *, image=None, result=None):
    """Explicit local hook; never invoked just by generating, reading or burning."""
    validate(record)
    body = record["body"]
    if not body.get("burn") or not result or result.get("result") != "completed":
        raise ValueError("Only a completed burn can be appended to the register")
    path = Path(path)
    register = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "discs": []}
    if register.get("schema_version") != 1 or not isinstance(register.get("discs"), list):
        raise ValueError("Unsupported disc register format")
    if any(d.get("id") == body["id"] for d in register["discs"]):
        raise ValueError("Disc id already registered")
    if body.get("code") and any(d.get("code") == body["code"] for d in register["discs"]):
        raise ValueError("Disc code already registered")
    code = re.fullmatch(r"([A-Z0-9]{3,4})-([A-Z]) (\d+)-(\d{2})", body.get("code") or "")
    burn = body["burn"]
    images = []
    if image:
        source = Path(image)
        digest = None
        size = None
        if source.is_file():
            digest, size = file_sha256(source), source.stat().st_size
        images.append(dict(path=filename(image), exists=source.is_file(), bytes=size, sha256=digest,
                           hash_scope="source_ISO_before_burn_stream_patch"))
    entry = dict(id=body["id"], code=body.get("code"),
                 abbr=code[1] if code else None, revision=code[2] if code else None,
                 batch=int(code[3]) if code else None, sequence=int(code[4]) if code else None,
                 design=body["design"]["name"], assignment_status="recorded_at_burn",
                 images=images,
                 media=dict(type=burn["media_type"], mid=burn["mid"], atip=burn["atip"]),
                 burn=dict(**burn, start_utc=burn["utc"],
                           burner=' '.join(str(burn.get(k) or '') for k in ('vendor','product')).strip() or None,
                           reported_speed_x=result.get('actual_speed_x'), result=result['result'],
                           elapsed_seconds=result.get('elapsed_s')),
                 readback=result.get("verification"),
                 geometry=dict(status="recorded_at_generation", parameters=body["geometry"]),
                 identity_record=record)
    register["discs"].append(entry)
    # Exclusive temporary sibling + replace, preserving all other register metadata.
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(register, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return entry
