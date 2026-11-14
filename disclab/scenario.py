"""Strict, versioned scenario input. Default boxes still use make_box unchanged."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from .box import MEDIA, READERS, make_box
from .faultmodel import KINDS
from .lab import Lab, atomic_json

DEFAULTS = dict(media="dvd-r", count=12, seed=1, batch=1, stampers=1,
                reader="gh70n", drives=["X:"], uv_noise=[0.0, 0.0])
PARAMETERS = {"u", "v", "b_nm", "start_radius_mm", "ecc_um", "ecc_deg",
              "dish_mm", "saddle_mm", "saddle_deg"}
READER_KEYS = {"vendor", "product", "firmware", "mode", "jitter_us", "outlier_rate",
               "write_speeds_x", "completion_mm", "head_mm"}


def obj(value, keys, where):
    if not isinstance(value, dict) or set(value) - set(keys):
        raise ValueError(f"{where}: expected an object with keys {', '.join(sorted(keys))}")
    return value


def number(v, where, lo=None, hi=None, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or (
            integer and not isinstance(v, int)) or (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ValueError(f"{where}: invalid number {v!r}")
    return v


def pair(value, where, lo=None, hi=None, integer=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{where}: expected [start, end]")
    for v in value:
        number(v, where, lo, hi, integer)
    if value[0] >= value[1]:
        raise ValueError(f"{where}: start must be less than end")


def parameters(value):
    obj(value, PARAMETERS, "parameters")
    for k, v in value.items():
        number(v, k, 1e-12 if k in {"u", "v", "b_nm", "start_radius_mm"} else
               0 if k in {"ecc_um", "saddle_mm"} else None)
    if "start_radius_mm" in value and "u" in value and "b_nm" not in value:
        raise ValueError("parameters: specify b_nm when combining u and start_radius_mm")
    if "start_radius_mm" in value and "u" in value and "b_nm" in value and not math.isclose(
            value["start_radius_mm"], value["u"] * value["b_nm"] * 1e-6, rel_tol=1e-10):
        raise ValueError("parameters: start_radius_mm conflicts with u and b_nm")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def arcs(value):
    if not isinstance(value, list):
        raise ValueError("defect_arcs: expected a list")
    for arc in value:
        obj(arc, {"r_mm", "deg"}, "defect arc")
        pair(arc.get("r_mm"), "r_mm", 0, 100)
        pair(arc.get("deg"), "deg")
        if arc["deg"][1] - arc["deg"][0] > 360:
            raise ValueError("defect arc: angular width must be at most 360 degrees")


def state_spec(value, base, capacity):
    if isinstance(value, str):
        value = {"state": value}
    value = copy.deepcopy(obj(value, {"state", "iso", "random", "sectors", "seed", "fraction"}, "initial_state"))
    state = value.get("state", "blank")
    if not isinstance(state, str) or state not in {"blank", "burned", "open", "partial"}:
        raise ValueError("initial_state: unknown state")
    value["state"] = state
    if state == "blank":
        if set(value) != {"state"}:
            raise ValueError("blank state cannot have image or fraction settings")
        return value
    if "iso" in value and any(k in value for k in ("random", "sectors", "seed")):
        raise ValueError("initial_state: ISO and random settings conflict")
    if "random" in value and value["random"] is not True:
        raise ValueError("initial_state.random must be true")
    if "iso" in value:
        if not isinstance(value["iso"], str):
            raise ValueError("initial_state.iso must be a local path")
        if value["iso"].startswith(("\\\\", "//")) or "://" in value["iso"]:
            raise ValueError("initial_state.iso must be a local filesystem path")
        path = (base / value["iso"]).resolve()
        if not path.is_file() or path.suffix.lower() != ".iso" or not path.stat().st_size or path.stat().st_size % 2048:
            raise ValueError("initial_state.iso must be an existing sector-aligned local ISO")
        value["iso"] = str(path)
        sectors = path.stat().st_size // 2048
    else:
        sectors = number(value.setdefault("sectors", min(4096, capacity)), "initial sectors", 32, capacity, True)
        number(value.setdefault("seed", 1), "initial seed", 0, integer=True)
        value["random"] = True
    if sectors > capacity:
        raise ValueError("initial image exceeds disc capacity")
    if state == "partial":
        number(value.setdefault("fraction", 0.5), "partial fraction", 0, 1 - 1e-12)
    elif "fraction" in value:
        raise ValueError("initial_state.fraction requires partial state")
    return value


def load_scenario(path, cli=None):
    if str(path).startswith(("\\\\", "//")) or "://" in str(path):
        raise ValueError("scenario must be a local filesystem path")
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    obj(raw, {"version", "discs", "drive", "drives", "faults"}, "scenario")
    if type(raw.get("version", 1)) is not int or raw.get("version", 1) != 1:
        raise ValueError("scenario.version must be 1")
    raw = copy.deepcopy(raw)
    # Explicit CLI values fill absent fields; two explicit, different values are an error.
    for key, value in (cli or {}).items():
        if value is None:
            continue
        if key == "drives":
            target, field = raw, key
        elif key == "reader":
            target, field = raw.setdefault("drive", {}), "profile"
        else:
            target, field = raw.setdefault("discs", {}), key
        if not isinstance(target, dict):
            raise ValueError("scenario sections must be objects")
        if field in target and target[field] != value:
            raise ValueError(f"--{key.replace('_', '-')} conflicts with scenario value")
        target[field] = value
    d = obj(raw.setdefault("discs", {}), {"media", "count", "seed", "batch", "stampers", "mid", "capacity",
              "parameters", "defect_arcs", "initial_state", "overrides", "uv_noise"}, "discs")
    for key in ("media", "count", "seed", "batch", "stampers", "uv_noise"):
        d.setdefault(key, copy.deepcopy(DEFAULTS[key]))
    if not isinstance(d["media"], str) or d["media"] not in MEDIA:
        raise ValueError("discs.media: unsupported media")
    for key in ("count", "seed", "batch", "stampers"):
        number(d[key], key, 0 if key == "seed" else 1, integer=True)
    number(d.setdefault("capacity", MEDIA[d["media"]]["capacity"]), "capacity", 32, 0xFFFFFF - 0x30000, True)
    if d["media"] == "cd-r" and d["capacity"] > 1151849:
        raise ValueError("CD capacity exceeds the MSF representation")
    if not isinstance(d["uv_noise"], list) or len(d["uv_noise"]) != 2:
        raise ValueError("uv_noise must contain two numbers")
    for v in d["uv_noise"]:
        number(v, "uv_noise", 0)
    mid = d.setdefault("mid", MEDIA[d["media"]]["mid"])
    if not isinstance(mid, str) or not mid.isascii() or not mid:
        raise ValueError("MID must be a nonempty ASCII string")
    if d["media"] == "dvd+r":
        parts = mid.split("/")
        if len(parts) != 3 or len(parts[0]) > 8 or len(parts[1]) > 3 or not parts[2].isdigit() or int(parts[2]) > 255:
            raise ValueError("DVD+R MID must be maker/type/revision (8/3/0..255)")
    elif len(mid) > (12 if d["media"].startswith("dvd") else 64):
        raise ValueError("MID is too long")
    if d["media"] == "cd-r":
        match = re.fullmatch(r"ATIP (\d{2}):(\d{2}):(\d{2})", mid)
        if not match or int(match[2]) > 59 or int(match[3]) > 74:
            raise ValueError("CD MID must be ATIP mm:ss:ff (seconds 00..59, frames 00..74)")
    parameters(d.setdefault("parameters", {}))
    arcs(d.setdefault("defect_arcs", []))
    overrides = d.setdefault("overrides", [{} for _ in range(d["count"])])
    if not isinstance(overrides, list) or len(overrides) != d["count"]:
        raise ValueError("discs.overrides must have one object per disc")
    initial = d.get("initial_state", "blank")
    initial = initial if isinstance(initial, list) else [initial] * d["count"]
    if len(initial) != d["count"]:
        raise ValueError("initial_state must have one entry per disc")
    d["initial_state"] = []
    for index, override in enumerate(overrides):
        obj(override, {"parameters", "defect_arcs", "capacity", "mid", "initial_state"}, "disc override")
        obj(override.get("parameters", {}), PARAMETERS, "disc parameters")
        effective = {**d["parameters"], **override.get("parameters", {})}
        parameters(effective)
        if "mid" in override:
            raise ValueError("per-disc MID is set by discs.mid; mixed MID boxes are not supported")
        arcs(override.get("defect_arcs", []))
        cap = number(override.get("capacity", d["capacity"]), "disc capacity", 32, 0xFFFFFF - 0x30000, True)
        if d["media"] == "cd-r" and cap > 1151849:
            raise ValueError("CD capacity exceeds the MSF representation")
        d["initial_state"].append(state_spec(override.get("initial_state", initial[index]), path.parent, cap))
    drive = obj(raw.setdefault("drive", {}), {"profile", "overrides", "burn_failure"}, "drive")
    if not isinstance(drive.setdefault("profile", "gh70n"), str) or drive["profile"] not in READERS:
        raise ValueError("drive.profile: unsupported profile")
    r = obj(drive.setdefault("overrides", {}), READER_KEYS, "drive.overrides")
    for k, width in (("vendor", 8), ("product", 16), ("firmware", 4)):
        if k in r and (not isinstance(r[k], str) or not r[k].isascii() or len(r[k]) > width):
            raise ValueError(f"drive {k} must be ASCII, at most {width} characters")
    if "mode" in r:
        r["mode"] = str(r["mode"]).lower()
        if r["mode"] not in {"cav", "clv"}:
            raise ValueError("drive mode must be CAV or CLV")
    for k in ("jitter_us", "outlier_rate", "head_mm"):
        if k in r:
            number(r[k], k, 0 if k != "head_mm" else -20, 1 if k == "outlier_rate" else 20 if k == "head_mm" else None)
    if "completion_mm" in r:
        obj(r["completion_mm"], {"dvd", "cd:mode1", "cd:mode2form1", "bd"}, "completion_mm")
        for v in r["completion_mm"].values():
            number(v, "completion_mm")
    if "write_speeds_x" in r:
        obj(r["write_speeds_x"], {"dvd", "cd", "bd"}, "write_speeds_x")
        for family, values in r["write_speeds_x"].items():
            if not isinstance(values, list) or not values:
                raise ValueError("write speeds must be a nonempty list")
            for v in values:
                number(v, "write speed", 0.01, 65535 / (2 * {"dvd": 1385, "cd": 176, "bd": 4495}[family]))
    failure = obj(drive.setdefault("burn_failure", {"kind": "none"}), {"kind", "fraction", "report_success"}, "burn_failure")
    if not isinstance(failure.get("kind"), str) or failure["kind"] not in {"none", "stop_at", "fail_close"}:
        raise ValueError("burn_failure.kind must be none, stop_at, or fail_close")
    if failure["kind"] == "stop_at":
        number(failure.setdefault("fraction", 0.5), "stop_at fraction", 0, 1 - 1e-12)
    elif set(failure) != {"kind"}:
        raise ValueError("only stop_at accepts fraction or report_success")
    if "report_success" in failure and not isinstance(failure["report_success"], bool):
        raise ValueError("report_success must be boolean")
    drives = raw.setdefault("drives", ["X:"])
    if not isinstance(drives, list) or not drives or any(
            not isinstance(v, str) or len(v) != 2 or v[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" or v[1] != ":" for v in drives) or len(set(drives)) != len(drives):
        raise ValueError("drives must be unique virtual drive names such as X:")
    faults = raw.setdefault("faults", [])
    if not isinstance(faults, list):
        raise ValueError("faults must be a list")
    ids = set()
    allowed = {"read_error": {"lba", "r_mm"}, "spindle_unsteady": {"amplitude", "rate_hz", "time_s", "lba", "mode"},
               "capacity_misreport": {"offset", "sectors"}, "burn_interrupt": {"fraction", "report_success"}}
    labels = {f"LAB-A {d['batch']}-{i + 1:02d}" for i in range(d["count"])}
    for f in faults:
        obj(f, {"id", "kind", "params"}, "fault")
        fid = f.get("id")
        if not isinstance(fid, str) or not fid or len(fid) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in fid) or fid in ids:
            raise ValueError("fault id must be unique, 1..64 letters, digits, underscores or hyphens")
        ids.add(fid)
        kind = f.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError("unknown fault kind")
        p = obj(f.setdefault("params", {}), allowed[kind] | {"disc"}, "fault params")
        if "disc" in p and (not isinstance(p["disc"], str) or p["disc"] not in labels):
            raise ValueError("fault disc must name an existing disc label")
        if kind == "read_error":
            if ("lba" in p) == ("r_mm" in p):
                raise ValueError("read_error requires exactly one of lba or r_mm")
            key = "lba" if "lba" in p else "r_mm"
            pair(p[key], key, 0, 0xFFFFFFFF if key == "lba" else 100, key == "lba")
        elif kind == "spindle_unsteady":
            number(p.setdefault("amplitude", 0.15), "amplitude", 1e-9, 0.8)
            number(p.setdefault("rate_hz", 1.0), "rate_hz", 1e-9)
            number(p.setdefault("time_s", 0), "time_s", 0)
            number(p.setdefault("lba", 0), "spindle lba", 0, 0xFFFFFFFF, True)
            if not isinstance(p.setdefault("mode", "drift"), str) or p["mode"] not in {"drift", "jump"}:
                raise ValueError("spindle mode must be drift or jump")
        elif kind == "capacity_misreport":
            if ("offset" in p) == ("sectors" in p):
                raise ValueError("capacity_misreport requires exactly one of offset or sectors")
            number(p.get("sectors", p.get("offset")), "reported capacity", 1 if "sectors" in p else -0xFFFFFFFF, 0xFFFFFFFF, True)
        else:
            number(p.setdefault("fraction", 0.5), "burn fraction", 0, 1 - 1e-12)
            if not isinstance(p.setdefault("report_success", False), bool):
                raise ValueError("report_success must be boolean")
    return raw


def make_scenario_box(lab, scenario):
    """Apply validated settings after the unchanged seeded box generator."""
    from .__main__ import dp
    d, drive = scenario["discs"], scenario["drive"]
    box = make_box(lab, d["media"], d["count"], d["seed"], batch=d["batch"], stampers=d["stampers"],
                   reader=drive["profile"], drives=scenario["drives"], uv_noise=d["uv_noise"])
    answers = lab.answers()
    answers["scenario"] = copy.deepcopy(scenario)
    answers["faults"] = copy.deepcopy(scenario["faults"])
    reader = answers["readers"][drive["profile"]]
    for k, value in drive["overrides"].items():
        key = "revision" if k == "firmware" else k
        if isinstance(value, dict):
            reader[key].update(value)
        else:
            reader[key] = value
    reader["burn_failure"] = drive["burn_failure"]
    initial_burns = {}
    for index, disc_id in enumerate(box["discs"]):
        t = answers["discs"][disc_id]
        override = d["overrides"][index]
        t["capacity"] = override.get("capacity", d["capacity"])
        t["mid"] = d["mid"]
        params = {**d["parameters"], **override.get("parameters", {})}
        t.update({k: v for k, v in params.items() if k != "start_radius_mm"})
        if "start_radius_mm" in params:
            wanted_u = params["start_radius_mm"] / (t["b_nm"] * 1e-6)
            if "u" in params and not math.isclose(params["u"], wanted_u, rel_tol=1e-10):
                raise ValueError("start_radius_mm conflicts with u for this disc")
            t["u"] = wanted_u
        t["flaw"] = None
        t["defect_arcs"] = override.get("defect_arcs", d["defect_arcs"])
        initial = d["initial_state"][index]
        t["initial_state"] = copy.deepcopy(initial)
        if initial["state"] == "blank":
            continue
        image = lab.root / "iso" / f"initial-{index + 1}.iso"
        image.parent.mkdir(parents=True, exist_ok=True)
        if "iso" in initial:
            shutil.copyfile(initial["iso"], image)
        else:
            dp(lab, ["random", "--sectors", initial["sectors"], "--seed", initial["seed"], "--output", image], capture=True)
        size = image.stat().st_size
        sectors = size // 2048
        if initial["state"] == "partial":
            sectors = int(sectors * initial["fraction"])
        t["initial_state"].update(image=str(image), sha256=sha256_file(image), written_sectors=sectors)
        session = dict(iso=str(image), iso_size=size, iso_mtime=image.stat().st_mtime, start_lba=0,
                       sectors=sectors, speed_x=8.0, writer="imapi", mode="dvd" if t["family"] == "dvd" else "mode2form1",
                       drive=scenario["drives"][0], write_offset_bits=0.0, low_speed_fail_mm=None)
        initial_burns[disc_id] = dict(sessions=[session], closed=initial["state"] == "burned")
    for stamper in answers["stampers"]:
        stamper["capacity"] = d["capacity"]
    atomic_json(lab.answers_path, answers)
    box["mid"] = d["mid"]
    atomic_json(lab.box_path, box)
    with lab.locked_state() as st:
        st["burns"] = initial_burns
    return box


def create_from_args(a):
    values = {k: getattr(a, k, None) for k in DEFAULTS}
    if not a.scenario:
        values = {k: DEFAULTS[k] if v is None else v for k, v in values.items()}
        values["uv_noise"] = tuple(values["uv_noise"])
        return make_box(Lab(a.lab), **values)
    scenario = load_scenario(a.scenario, values)
    return make_scenario_box(Lab(a.lab), scenario)


def configure_box(parser):
    parser.add_argument("--scenario", type=Path, help="version 1 scenario JSON; conflicting flags are refused")
    parser.set_defaults(**{k: None for k in DEFAULTS})
