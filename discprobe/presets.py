"""Drive-free DIS preset interchange, shared by the CLI and the web sheet.

The original preset is authoritative. A derived DP fit is never a measurement and
is only exposed to image generation when its residuals are within explicit limits.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from . import disinstall, i18n

LISTS = {"cdPresets": "cd", "dvdPresets": "dvd", "bluRayPresets": "bd"}
PITCH = ("pitchLinear", "pitchQuadratic", "pitchCubic")
COMMON = {"id", "displayName", "description", "innerRadiusMm", "outerRadiusMm",
          "displayNameResourceKey", "descriptionResourceKey", "contributor", "usableSectors", *PITCH}
FIELDS = {"cd": COMMON | {"sectors", "linearVelocityMmPerSecond"},
          "dvd": COMMON | {"totalSectors", "channelBitLengthNm"},
          "bd": COMMON | {"totalSectors", "invertMapping"}}
NOMINAL_IDS = {"cd-80", "cd-74", "dvd-5-120mm", "dvd-5-80mm", "bd-r-sl-25gb",
               "user-custom-cd", "user-custom-dvd", "user-custom-bd"}


def _number(value):
    return disinstall._number(value)


def validate(preset, media):
    """DIS catalog limits, including defaults; do not alter the original dictionary."""
    if not isinstance(preset, dict):
        raise ValueError("preset must be an object")
    for key in ("id", "displayName", "description"):
        if not isinstance(preset.get(key), str) or not preset[key].strip():
            raise ValueError(f"{key} must be nonblank text")
    if preset["id"] == "__manual__":
        raise ValueError("id __manual__ is reserved by DIS")
    for key in ("displayNameResourceKey", "descriptionResourceKey", "contributor"):
        value = preset.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} must be null or nonblank text")
    key = "sectors" if media == "cd" else "totalSectors"
    total = preset.get(key)
    limit = 2**63 - 1 if media == "cd" else 2**32 - 1
    if type(total) is not int or not 0 < total <= limit:
        raise ValueError(f"{key} must be a positive integer <= {limit}")
    if (media == "cd" and "totalSectors" in preset) or (media != "cd" and "sectors" in preset):
        raise ValueError("conflicting sector fields")
    ri, ro = preset.get("innerRadiusMm"), preset.get("outerRadiusMm")
    if not (_number(ri) and _number(ro) and 0 < ri < ro):
        raise ValueError("radii must satisfy 0 < innerRadiusMm < outerRadiusMm")
    if media == "bd" and (ro > 60 or total > 12219392 or total % 32):
        raise ValueError("BD needs outer <= 60 mm and totalSectors a multiple of 32 <= 12219392")
    usable = preset.get("usableSectors")
    alignment = {"cd": 1, "dvd": 16, "bd": 32}[media]
    if usable is not None and (type(usable) is not int or not 0 < usable <= total or usable % alignment):
        raise ValueError(f"usableSectors must be positive, <= total, and a multiple of {alignment}")
    pitch = [preset.get(k, 0) for k in PITCH]
    if not all(_number(v) for v in pitch) or not disinstall._pitch_positive(*pitch):
        raise ValueError("pitch must be finite and positive throughout 0 <= x <= 1")
    density = "linearVelocityMmPerSecond" if media == "cd" else "channelBitLengthNm"
    if density in preset and (not _number(preset[density]) or preset[density] <= 0):
        raise ValueError(f"{density} must be finite and positive")
    if "invertMapping" in preset and type(preset["invertMapping"]) is not bool:
        raise ValueError("invertMapping must be a boolean")


def media_of(preset, hint=None):
    if hint:
        return hint
    if "sectors" in preset:
        return "cd"
    if "invertMapping" in preset or "layerCount" in preset:
        return "bd"
    if "totalSectors" in preset:
        # Catalog BD has no mandatory discriminator in a standalone object.
        if "channelBitLengthNm" not in preset:
            raise ValueError("ambiguous standalone DVD/BD preset; pass --media dvd or --media bd")
        return "dvd"
    raise ValueError("cannot identify media; use a catalog or --media")


def density(media):
    if media == "cd":
        from . import cd
        return cd.BIT_NM, cd.SECTOR_BITS
    if media == "bd":
        from . import bdexport
        return bdexport.BD_CHANNEL_BIT_LENGTH_NM, bdexport.BD_BITS_PER_RECORDING_UNIT / 32
    from .calib import SECTOR_BITS
    return 133.3, SECTOR_BITS


def geometry(preset, media, *, with_correction=False):
    """Area-equivalent base and full-area residuals against the DIS geometry.

    CD/DVD use DIS's exact arc model and a bounded angle correction. BD is unchanged.
    """
    import numpy as np
    from .disexport import dis_angle_map, target_angle
    bit, bits = density(media)
    ri, ro = preset["innerRadiusMm"], preset["outerRadiusMm"]
    total = preset.get("sectors", preset.get("totalSectors"))
    b = bit * 1e-6
    u = ri / b
    v = math.pi * (ro**2 - ri**2) / (total * bits * b**2)
    if not all(math.isfinite(x) and x > 0 for x in (u, v)):
        raise ValueError("geometry exceeds DP numerical range")
    fit = dict(media=media, model="dis_import", u=u, v=v, bit_nm_assumed=bit,
               r0_mm_at_bit=ri, pitch_um_at_bit=v * b * 1000,
               measured_span_mm=None, calibrated=False, capacity_sectors=total)
    if media != 'bd':
        from .dispitch import convert
        comparison, correction = convert(preset, media, fit, bit, bits)
        return (fit, comparison, correction) if with_correction else (fit, comparison)
    model = dis_angle_map(ri, ro, *(preset.get(k, 0) for k in PITCH), total, bit, bits)
    if model is None or not all(np.isfinite(x).all() for x in model):
        raise ValueError("geometry exceeds DP numerical range")
    n = np.linspace(0, total * bits, 20001)
    delta = np.degrees(np.interp(n, model[0], model[1]) - target_angle(n, u, v, bit))
    delta -= delta.mean()  # an overall rotation is free, as in disexport
    radii = np.interp(n, model[0], np.linspace(ri, ro, len(model[0])))
    radius_error = np.max(np.abs(radii - b * np.sqrt(u*u + v*n / math.pi)))
    comparison = dict(max_angle_error_deg=float(np.max(np.abs(delta))),
                      max_radius_error_mm=float(radius_error), samples=len(n), polynomial_degree=None)
    correction = None
    return (fit, comparison, correction) if with_correction else (fit, comparison)


def parse(text, filename="disc-presets.json", media=None):
    """Preview every item, including invalid entries, without filesystem writes."""
    if media is not None and media not in LISTS.values():
        raise ValueError("media must be cd, dvd or bd")
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2*1024*1024:
        raise ValueError("preset file must be UTF-8 text <= 2 MiB")
    try:
        data = json.loads(disinstall._strip_trailing_commas(disinstall._strip_comments(text.lstrip('\ufeff'))),
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))
    except (json.JSONDecodeError, disinstall._UnclosedComment) as exc:
        raise ValueError(f"invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("file must hold a preset object or a DIS catalog")
    schema = data.get("schemaVersion")
    items = []
    if any(key in data for key in LISTS):
        if type(schema) is not int or schema not in (2, 3, 4):
            raise ValueError("unsupported schemaVersion; expected 2, 3 or 4")
        for key in ("cdPresets", "dvdPresets", *(["bluRayPresets"] if schema == 4 else [])):
            if not isinstance(data.get(key), list):
                raise ValueError(f"{key} must be a list")
        for key, kind in LISTS.items():
            values = data.get(key, [])
            if not isinstance(values, list):
                raise ValueError(f"{key} must be a list")
            disabled = data.get(disinstall.FAMILIES[kind][1], [])
            if not isinstance(disabled, list) or any(not isinstance(x, str) or not x.strip() for x in disabled):
                raise ValueError(f"disabled {kind} ids must be a text list")
            items.extend((p, kind, p.get("id") in disabled if isinstance(p, dict) else False) for p in values)
    else:
        value = data.get("preset", data)
        if not isinstance(value, dict):
            raise ValueError("preset must be an object")
        if "parameters" in value:
            raise ValueError("legacy BD parameters document is not a catalog preset; export its catalog entry")
        items = [(value, media_of(value, media), False)]
    rows, seen = [], set()
    for index, (original, kind, disabled) in enumerate(items):
        row = dict(index=index, media=kind, preset=copy.deepcopy(original), valid=False,
                   disabled=disabled, issues=[], schema=schema)
        try:
            validate(original, kind)
            ident = (kind, original["id"])
            if ident in seen:
                row["issues"].append("Duplicate id in file; select by index. No entry is overwritten.")
            seen.add(ident)
            unknown = sorted(set(original) - FIELDS[kind])
            row["unknown_fields"] = unknown
            row["mid"] = original.get("mid", original.get("MID"))
            if row["mid"] is None:
                row["issues"].append("MID unknown; DIS has no MID field.")
            if kind == "cd":
                row["issues"].append("L unknown; DIS has no along-track constant.")
            if disabled:
                row["issues"].append("Disabled in DIS; import requires explicit selection.")
            nominal = original["id"] in NOMINAL_IDS or "标准" in original["displayName"]
            row["status"] = "nominal" if nominal else "unverified"
            row["issues"].append("Nominal, not calibrated." if nominal else "Imported values; calibration not verified by DP.")
            row["fit"], row["comparison"], correction = geometry(original, kind, with_correction=True)
            from .dispitch import ANGLE_LIMIT_DEG, RADIUS_LIMIT_MM
            bounded = (row['comparison']['max_angle_error_deg'] <= ANGLE_LIMIT_DEG and
                       row['comparison']['max_radius_error_mm'] <= RADIUS_LIMIT_MM)
            if kind != 'bd' and not bounded:
                row['issues'].append('DP approximation exceeds 0.01 deg angle or 0.005 mm radius; archive only.')
            if correction is not None:
                row['correction'] = correction
                if bounded:
                    row['issues'].append('Imported from DIS, converted to DP correction (not measured by DP).')
                    if not nominal:
                        row['status'] = 'converted_unverified'
            if unknown:
                row["issues"].append("Unknown fields retained; geometry use and DIS installation refused: " + ", ".join(unknown))
            if kind == "dvd" and original.get("channelBitLengthNm", 133.3) != 133.3:
                row["issues"].append("DIS generation uses 133.3 nm; stored channelBitLengthNm retained only.")
            if kind == "cd" and original.get("linearVelocityMmPerSecond", 1200) != 1200:
                row["issues"].append("DIS generation uses 1200 mm/s; stored linearVelocityMmPerSecond retained only.")
            row["image_compatible"] = bounded and not unknown and kind != "bd"
            if kind == "bd":
                row["issues"].append("BD geometry maps to r0/pitch; DP image command has no BD writer.")
            row["fit"]["image_compatible"] = row["image_compatible"]
            row['fit']['correction_required'] = row['image_compatible'] and correction is not None
            row["valid"] = True
        except (ValueError, TypeError, OverflowError) as exc:
            row["issues"].append(str(exc))
        rows.append(row)
    return dict(file=str(filename), schema=schema, entries=rows)


def import_file(text, filename, directory="presets", *, selected=None, dry_run=False, media=None):
    report = parse(text, filename, media)
    rows = report["entries"]
    if selected is None:
        selected = [r["index"] for r in rows if r["valid"] and not r["disabled"]]
    if not isinstance(selected, list) or any(type(i) is not int or not 0 <= i < len(rows) for i in selected):
        raise ValueError("selection must contain preset indexes")
    if len(set(selected)) != len(selected):
        raise ValueError("selection contains repeated indexes")
    if any(not rows[i]["valid"] for i in selected):
        raise ValueError("selection contains a refused preset")
    report["written"], report["duplicates"] = [], []
    if dry_run or not selected:
        return report
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    for i in selected:
        row = rows[i]
        preset = row["preset"]
        # Opaque names cannot escape the preset folder, collide on case, or be Windows device names.
        digest = hashlib.sha256((row["media"] + '\0' + preset["id"]).encode()).hexdigest()[:24]
        path = root / ("dis-" + digest + ".json")
        source = dict(origin="imported from DIS", file=str(filename), preset_id=preset["id"],
                      schema=report["schema"], media=row["media"], status=row["status"],
                      along_track_frames=None if row["media"] == "cd" else None,
                      issues=row["issues"], comparison=row["comparison"])
        document = dict(preset=preset, fit=row["fit"], source=source)
        correction_path = path.with_name(path.stem + '-correction.json')
        if row['image_compatible'] and row.get('correction'):
            document['correction'] = correction_path.name
        if path.exists() or ('correction' in document and correction_path.exists()):
            report['duplicates'].append(dict(index=i, path=str(path), reason='already exists; left unchanged'))
            continue
        try:
            if 'correction' in document:
                with correction_path.open('x', encoding='utf-8') as stream:
                    json.dump(row['correction'], stream, indent=2, allow_nan=False)
                    stream.write('\n')
            with path.open("x", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write('\n')
        except FileExistsError:
            report["duplicates"].append(dict(index=i, path=str(path), reason="already exists; left unchanged"))
        else:
            report["written"].append(dict(index=i, path=str(path)))
    return report


def linked_correction(path, document):
    """Resolve the DP-only sibling link, failing closed if it is broken or mismatched."""
    name = document.get('correction')
    if name is None:
        if (document.get('fit') or {}).get('correction_required'):
            raise ValueError('converted DIS preset is missing its correction link')
        return None
    parent = Path(path).resolve().parent
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError('DIS correction must name a sibling file')
    target = (parent / name).resolve()
    if target.parent != parent:
        raise ValueError('DIS correction must stay beside its preset')
    correction = json.loads(target.read_text(encoding='utf-8'))
    fit, base = document['fit'], correction.get('geo_fit') or {}
    if any(not math.isclose(fit[k], base.get(k, 0), rel_tol=1e-12) for k in ('u', 'v')):
        raise ValueError('DIS correction base does not match its preset')
    return str(target)


def build_export(path, *, sectors=None, correction=None, media=None, preset_id="discprobe-import", name="disc-probe", for_install=False):
    """Existing {preset, fit, source} files are authoritative; geo runs use disexport/bdexport."""
    from . import bdexport, disexport, guide
    path = Path(path)
    if path.is_dir():
        path = path / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("DP preset must be an object")
    for key in ("source", "fit"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            raise ValueError(f"DP {key} must be an object")
    if isinstance(data.get("preset"), dict):
        if correction:
            raise ValueError("a saved preset already contains its exported corrections; use its geo to refit")
        original = copy.deepcopy(data["preset"])
        kind = media_of(original, media or (data.get("source") or {}).get("media") or
                        (data.get("fit") or {}).get("media"))
        if "layerCount" in original and (data.get("source") or {}).get("origin") != "imported from DIS":
            original = bdexport.catalog_entry(original)
        validate(original, kind)
        return dict(preset=original, media=kind, source=data.get("source", {}), fit=data.get("fit", {}))
    fit = data.get("fit") or {}
    kind = media or fit.get("media", "dvd")
    blocker = guide.install_blocker(str(path), allow_simulated=not for_install)
    if blocker:
        raise ValueError("Cannot export geo: " + blocker)
    total = sectors or ((data.get("setup") or {}).get("last_lba", -1) + 1)
    if type(total) is not int or total <= 0:
        raise ValueError("geo export needs --sectors (whole disc capacity)")
    if kind == "bd" or fit.get("model") == "clv":
        if correction:
            raise ValueError("BD cannot represent an angle correction")
        out = bdexport.export(str(path), total, None, preset_id, name)
        out["preset"] = bdexport.catalog_entry(out["preset"])
        kind = "bd"
    else:
        span = fit.get("measured_span_mm") or [fit.get("r0_mm_at_bit", 24.5), 58.0]
        out = disexport.export(str(path), total, correction, None, *span, preset_id, name)
    validate(out["preset"], kind)
    return {**out, "media": kind}


def export_file(path, *, output=None, install=False, dis_presets=None, replace=False, **options):
    if (dis_presets or replace) and not install:
        raise ValueError("--dis-presets and --replace require --install")
    if output and disinstall.same_file(str(path), str(output)):
        raise ValueError("output must not overwrite the DP source preset")
    if output and Path(output).exists():
        raise FileExistsError(f"output already exists: {output}")
    if install and output:
        disinstall.refuse_same_file(str(output), disinstall.target_path(dis_presets))
    result = build_export(path, for_install=install, **options)
    if install:
        unknown = set(result["preset"]) - FIELDS[result["media"]]
        if unknown:
            raise ValueError("DIS rejects unknown fields; save as file instead: " + ", ".join(sorted(unknown)))
        result["installation"] = disinstall._install_validated(result["preset"], dis_presets, replace, result["media"])
    if output:
        with Path(output).open("x", encoding="utf-8") as stream:
            json.dump(result["preset"], stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        result["written"] = str(output)
    return result


def command(args):
    try:
        if args.operation == "import":
            result = import_file(Path(args.file).read_text(encoding="utf-8-sig"), args.file,
                                 args.directory, selected=args.select, dry_run=args.dry_run, media=args.media)
        else:
            result = export_file(args.file, output=args.output, install=args.install,
                                 dis_presets=args.dis_presets, replace=args.replace, sectors=args.sectors,
                                 correction=args.correction, media=args.media, preset_id=args.id, name=args.name)
        if args.json:
            # ASCII JSON escapes keep emoji/Chinese lossless on legacy Windows pipes.
            print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        elif args.operation == "import":
            for row in result["entries"]:
                print(i18n.tr("Preset {index}: {media}").format(index=row["index"], media=row["media"]))
                print(json.dumps(row["preset"], ensure_ascii=False))
                if row.get('comparison'):
                    c = row['comparison']
                    print(i18n.tr('Approximation: angle <= {angle} deg, radius <= {radius} mm').format(
                        angle=f"{c['max_angle_error_deg']:.9g}", radius=f"{c['max_radius_error_mm']:.9g}"))
                for issue in row["issues"]:
                    print("  " + i18n.tr(issue))
            print(i18n.tr("Written: {written}; duplicates left unchanged: {duplicates}").format(
                written=len(result["written"]), duplicates=len(result["duplicates"])))
        else:
            print(json.dumps(result["preset"], ensure_ascii=False, indent=2))
            if result.get("installation"):
                print(i18n.tr("Preset installed; restart DiscImageStudio."))
                print(json.dumps(result["installation"], ensure_ascii=False))
        if args.operation == "import" and result["entries"] and not any(r["valid"] for r in result["entries"]):
            raise SystemExit(1)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        if args.json:
            print(json.dumps(dict(error=str(exc)), ensure_ascii=True))
        else:
            print(i18n.tr("Preset operation failed: {reason}").format(reason=i18n.tr(str(exc))))
        raise SystemExit(1) from None


def add_parser(sub):
    parser = sub.add_parser("presets", help="import DIS presets or export DP presets")
    actions = parser.add_subparsers(dest="operation", required=True)
    for operation in ("import", "export"):
        p = actions.add_parser(operation)
        p.add_argument("file")
        p.add_argument("--json", action="store_true")
        p.add_argument("--media", choices=("cd", "dvd", "bd"), help="media of a standalone preset")
        p.set_defaults(func=command)
        if operation == "import":
            p.add_argument("--directory", default="presets")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--select", type=int, nargs="+", help="zero-based preview indexes (default: valid enabled presets)")
        else:
            p.add_argument("--output", help="save one DIS object here; refuses existing files")
            p.add_argument("--install", action="store_true")
            p.add_argument("--dis-presets")
            p.add_argument("--replace", action="store_true")
            p.add_argument("--sectors", type=int)
            p.add_argument("--correction")
            p.add_argument("--id", default="discprobe-import")
            p.add_argument("--name", default="disc-probe")
