"""Recover completed writes of a check disc linked to a particular geo run."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

from . import i18n

BURN_FIELDS = ("burner", "path", "mode")
NO_BURNS = "No completed check-disc burn was found for this measurement. Burn the check disc first."
LEGACY_BURN = ("This check disc was burned by the command line before 1.0.0. "
               "Its recording method cannot be confirmed. Burn a new check disc.")
UNKNOWN_BURN = "The recorder did not report its recording method. Burn a new check disc with a supported recorder."
CHOOSE_BURN = "Choose a completed check-disc burn from --list-burns."
NEED_DISC = "Enter the number written on the disc with --disc-id."


def known_field(value):
    if (isinstance(value, str) and value.strip() and value.strip().lower() != "unknown"
            and len(value) <= 500 and not any(ord(c) < 32 for c in value)):
        return value
    return None


def disc_number_arg(value):
    if value is None:
        return None
    if not known_field(value) or len(value.strip()) > 40 or value.lstrip().startswith("-"):
        raise ValueError(i18n.tr("Enter a disc number of 1 to 40 characters."))
    return value.strip()


def valid_record_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def record_id(log, stamp):
    return hashlib.sha256(json.dumps([str(log), stamp], separators=(",", ":")).encode()).hexdigest()


def _timestamp(stamp):
    return type(stamp) in (int, float) and 0 < stamp < 253402300800 and math.isfinite(stamp)


def _rows(log):
    try:
        with log.open("rb") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def _web_records(root, wanted):
    """A legacy web result is evidence only for its exact engine event."""
    matches = {}
    for report in (root / ".webui-jobs").glob("*/burn.json"):
        try:
            if not report.resolve().is_relative_to(root):
                continue
            row = json.loads(report.read_text(encoding="utf-8"))
            if not isinstance(row, dict) or row.get("result") != "completed":
                continue
            log, stamp = row.get("log_path"), row.get("time")
            if not isinstance(log, str) or not _timestamp(stamp) or (log, stamp) not in wanted:
                continue
            details = dict(burner=known_field(row.get("burner")), path=known_field(row.get("burn_path")),
                           mode=known_field(row.get("burn_mode")))
            if all(details.values()):
                matches.setdefault((log, stamp), []).append(details)
        except (OSError, ValueError):
            continue
    return {key: rows[0] for key, rows in matches.items() if len(rows) == 1}


def listing(root, run, *, burn_log=None):
    root, summary = Path(root).resolve(), Path(run).resolve() / "summary.json"
    if not summary.is_file():
        raise ValueError(i18n.tr("Use the geo run folder with its summary.json."))
    # The default follows checkdisc's ISO directory. The CLI can point to an explicit log
    # when the ISO was generated elsewhere. The desktop API never takes a log path.
    logs = [Path(burn_log).resolve()] if burn_log is not None else (root / "iso").glob("*.iso.burn.jsonl")
    completed = []
    for path in logs:
        if not path.name.lower().endswith(".iso.burn.jsonl"):
            continue
        try:
            log = path.resolve()
            image = path.with_name(path.name.removesuffix(".burn.jsonl")).resolve()
            spec = image.with_suffix(".image.json").resolve()
            if burn_log is None and not all(p.is_relative_to(root) for p in (log, image, spec)):
                continue
            raw = spec.read_bytes()
            doc = json.loads(raw)
            if not isinstance(doc, dict) or doc.get("check_disc") is not True:
                continue
            geo = Path(doc["geometry_from"])
            if (root / geo).resolve() != summary:
                continue
            digest = hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, TypeError, KeyError):
            continue
        for row in _rows(log):
            stamp = row.get("time")
            if (row.get("type") == "burn_result" and row.get("result") == "completed"
                    and row.get("media") == "dvd" and _timestamp(stamp)
                    and row.get("image") == str(image) and row.get("log_path") == str(log)
                    and row.get("check_spec_sha256", digest) == digest):
                completed.append((log, stamp, row))

    legacy_keys = {(str(log), stamp) for log, stamp, row in completed
                   if not any(k in row for k in BURN_FIELDS)}
    old = _web_records(root, legacy_keys) if legacy_keys else {}
    counts = Counter((log, stamp) for log, stamp, _ in completed)
    records, unavailable = [], set()
    for log, stamp, row in completed:
        if counts[log, stamp] != 1:
            unavailable.add("unknown_burn")
            continue
        source = "iso-burn-log"
        details = {k: known_field(row.get(k)) for k in BURN_FIELDS}
        if (str(log), stamp) in legacy_keys:
            source = "webui-job"
            details = old.get((str(log), stamp))
            if not details:
                unavailable.add("legacy_burn")
                continue
        if not all(details.values()):
            unavailable.add("unknown_burn")
            continue
        records.append(dict(id=record_id(log, stamp), time=stamp, log_path=str(log),
                            disc_id=known_field(row.get("disc_id")), source=source, **details))
    records.sort(key=lambda row: (row["time"], row["id"]), reverse=True)
    return dict(burns=records, unavailable=sorted(unavailable))


def select(root, run, ident, *, disc_id=None, burn_log=None):
    saved = listing(root, run, burn_log=burn_log)
    if not saved["burns"]:
        reason = (LEGACY_BURN if "legacy_burn" in saved["unavailable"] else
                  UNKNOWN_BURN if "unknown_burn" in saved["unavailable"] else NO_BURNS)
        raise ValueError(i18n.tr(reason))
    record = next((r for r in saved["burns"] if r["id"] == ident), None)
    if record is None:
        raise ValueError(i18n.tr(CHOOSE_BURN))
    number = disc_number_arg(disc_id) if disc_id is not None else record["disc_id"]
    if not number:
        raise ValueError(i18n.tr(NEED_DISC))
    evidence = {k: record[k] for k in ("id", "time", "source", "log_path")}
    evidence.update(recorded_disc_id=record["disc_id"], disc_id_overridden=(
        record["disc_id"] is not None and number != record["disc_id"]))
    return dict(burner=record["burner"], burn_path=record["path"], burn_mode=record["mode"],
                disc_id=number, burn_record=evidence)
