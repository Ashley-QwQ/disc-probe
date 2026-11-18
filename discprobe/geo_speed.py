"""Record geo's requested speed and report the grid evidence for it."""

import json
from pathlib import Path

from . import i18n
from .mmc import BD_1X_KBPS
from .read_completion import drive_registry_paths, inquiry_key

ONE_X_KBPS = {"cd": 176.4, "dvd": 1385, "bd": BD_1X_KBPS}
UNVALIDATED = ("This read speed has not been grid-validated. At a single read speed, the fit can absorb "
               "read delays that vary with radius, leaving no trace in the residuals. Before using this "
               "geometry to burn a picture, burn and check a grid disc.")
KNOWN_BIAS = "Known read-speed bias: {detail}. For geo, use --speed {speed} ({multiple}x)."


def _multiple(speed, media):
    if speed is not None and 0 < speed < 0xFFFF:
        return round(speed / ONE_X_KBPS[media], 2)
    return None


def _entries(root):
    paths = drive_registry_paths(root)
    if root is None:
        paths.append(Path(__file__).resolve().parent / "_presets" / "drives.json")
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            continue
        entries = data.get("geo_read_speed") if isinstance(data, dict) else None
        if isinstance(entries, list):
            yield from (entry for entry in entries if isinstance(entry, dict))


def check(identity, media, requested_kbs, *, simulated=False, root=None):
    key = inquiry_key(identity)
    if not simulated and all(key) and _multiple(requested_kbs, media) is not None:
        for entry in _entries(root):
            speed = entry.get("requested_kBps")
            if (entry.get("media") != media or type(speed) is not int or speed != requested_kbs
                    or inquiry_key(entry) != key):
                continue
            evidence = entry.get("evidence")
            source = entry.get("source")
            if not all(isinstance(value, str) and value.strip() for value in (evidence, source)):
                continue
            status = entry.get("status")
            if status == "validated":
                return dict(status=status, note=None, evidence=evidence, source=source)
            if status == "known_bias":
                detail = entry.get("bias")
                recommended = entry.get("recommended_kBps")
                if not isinstance(detail, str) or not detail.strip() or type(recommended) is not int:
                    continue
                multiple = _multiple(recommended, media)
                if multiple is not None and recommended != speed:
                    note = KNOWN_BIAS.format(detail=detail, speed=recommended, multiple=f"{multiple:g}")
                    return dict(status=status, note=note, evidence=evidence, source=source)
    return dict(status="unvalidated", note=UNVALIDATED)


def _request(probe):
    # --sim preserves the CLI request in args but deliberately sends no speed command.
    args = probe.summary.get("args") or {}
    return args.get("speed", getattr(probe, "speed_kbs", None))


def check_probe(probe, media):
    return check(probe.summary.get("identity"), media, _request(probe), simulated=probe.summary.get("simulated"))


def notice(speed_check):
    if isinstance(speed_check, dict) and speed_check.get("status") in ("known_bias", "unvalidated"):
        note = speed_check.get("note")
        return i18n.tr(note) if isinstance(note, str) and note else None
    return None


def print_notice(speed_check):
    note = notice(speed_check)
    if note:
        print(note, flush=True)


def annotations(probe, media, *, period_ms=None, zones=None):
    identity = probe.summary.get("identity") or {}
    simulated = probe.summary.get("simulated")
    speed = _request(probe)
    read_speed = dict(media=media, requested_kBps=speed, requested_multiple=_multiple(speed, media),
                      period_ms=period_ms, drive=identity.get("drive"), firmware=identity.get("firmware"))
    if simulated:
        read_speed["drive"] = getattr(probe.dev, "name", None)
    if zones is not None:
        read_speed["period_ms_by_zone"] = [{"lba": z["lba"], "period_ms": z["period_ms"]} for z in zones
                                          if z.get("period_ms") is not None]
    return dict(read_speed=read_speed, speed_check=probe.summary.get("speed_check") or check_probe(probe, media))
