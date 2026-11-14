"""Run disc-probe through dp and score each fault against private lab truth."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid

from .lab import Lab, atomic_json

# Match reasons and explicit warnings, never a command name or a suggested next command.
EXPECTED = {
    "read_error": [r"3/11/00", r"medium error", r"unreadable", r"cannot read this disc"],
    "spindle_unsteady": [r"spindle did not reach a steady speed", r"spindle speed never settled", r"no (?:clear|stable) period",
                         r"speed may be changing", r"rotation.*(?:mixed|unknown)",
                         r"cache/false period", r"reference has no clear period"],
    "capacity_misreport": [r"capacity.*(?:mismatch|inconsisten|wrong)", r"5/21/00", r"out of range"],
    "burn_interrupt": [r"write interrupted", r"session close failed", r"5/21/00",
                       r"read.back.*failed", r"[1-9][0-9]* unreadable"],
}
COMMANDS = {
    "read_error": ("info", "timing", "geo", "burn"),
    "spindle_unsteady": ("info", "timing", "geo"),
    "capacity_misreport": ("info", "timing", "geo"),
    "burn_interrupt": ("burn", "burn-no-verify"),
}


def classify(outcome, patterns):
    """Pure classifier; missing output is an unexplained failure, never an unaffected PASS."""
    if outcome.get("traceback") or outcome.get("timed_out"):
        return "crash"
    reason = "\n".join(outcome.get("reasons", []))
    if outcome.get("warned_or_stopped") and any(re.search(p, reason, re.I) for p in patterns):
        return "detected"
    if outcome.get("returncode", 1) != 0 or not outcome.get("assessed", False):
        return "crash"
    return "silent_wrong" if outcome["wrong"] else "unaffected"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _outputs(root):
    """Only files written by this command, in its unique workspace."""
    files = sorted(root.rglob("*.json")) + sorted(root.rglob("*.jsonl"))
    records, evidence = [], []
    for path in files:
        if path.name not in {"failure.json", "summary.json", "info.json"} and not path.name.endswith(".burn.jsonl"):
            continue
        try:
            values = [_read_json(path)] if path.suffix == ".json" else [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if any(not isinstance(v, dict) for v in values):
                raise ValueError("expected output objects")
        except (ValueError, TypeError) as exc:
            values = [{"invalid_output": str(exc)}]
        records.extend((path, v) for v in values)
        evidence.append(str(path))
    return records, evidence


def _reasons(records, stdout, stderr):
    reasons = []
    for path, value in records:
        if path.name == "failure.json":
            reasons.append(str(value.get("reason", "")))
        if value.get("stopped"):
            reasons.append(str(value["stopped"]))
        rotation = (value.get("period") or {}).get("rotation") or {}
        if rotation.get("mode") not in (None, "CAV"):
            reasons.append("rotation " + str(rotation))
        for entry in (value.get("phase") or {}).get("targets", []):
            if entry.get("error"):
                reasons.append(entry["error"])
        verification = value.get("verification") or {}
        if verification.get("unreadable") or verification.get("differing") or verification.get("error"):
            reasons.append("read-back failed: " + json.dumps(verification))
    # Stderr is diagnostic output. Stdout is restricted to actual warning/failure lines.
    if stderr.strip():
        reasons.append(stderr)
    for line in stdout.splitlines():
        if re.search(r"spindle did not|^warning:|^stopped:|^rotation:.*(?:unknown|mixed)|read.back.*(?:failed|[1-9][0-9]* unreadable)", line, re.I):
            reasons.append(line)
    return reasons


def _written(burn):
    return max((s["start_lba"] + s["sectors"] for s in (burn or {}).get("sessions", [])), default=0)


def _fixture(source, root, fault, command):
    """Independent assay: preserve the source; isolate one fault and reset process-open counters."""
    from .__main__ import dp
    lab = Lab(root / "lab")
    lab.root.mkdir(parents=True)
    answers, state, box = copy.deepcopy(source.answers()), copy.deepcopy(source.state()), source.box()
    disc_id = fault["params"].get("disc", box["discs"][0])
    drive = next(iter(state["drives"]))
    for value in state["drives"].values():
        value["opens"] = 0
    state["drives"][drive].update(tray=disc_id, open=False)
    answers["faults"] = [fault]
    atomic_json(lab.box_path, box)
    atomic_json(lab.answers_path, answers)
    atomic_json(lab.state_path, state)
    t = answers["discs"][disc_id]
    sectors = min(4096, t["capacity"] - (249 if t["family"] == "cd" else 0))
    if sectors < 32:
        raise ValueError("fault assay requires at least 32 writable sectors")
    burn_command = command.startswith("burn")
    generated = burn_command or not _written(state.get("burns", {}).get(disc_id))
    image = root / "assay.iso"
    if generated:
        res = dp(lab, ["random", "--sectors", sectors, "--seed", answers["seed"], "--output", image], check=False, capture=True, timeout=120)
        (root / "prepare.stdout.txt").write_text(res.stdout, encoding="utf-8")
        (root / "prepare.stderr.txt").write_text(res.stderr, encoding="utf-8")
        if res.returncode or not image.is_file():
            raise RuntimeError("Disc Lab could not prepare the local assay ISO")
        if burn_command:
            state.setdefault("burns", {}).pop(disc_id, None)
        else:
            state.setdefault("burns", {})[disc_id] = dict(closed=True, sessions=[dict(
                iso=str(image), iso_size=image.stat().st_size, iso_mtime=image.stat().st_mtime,
                start_lba=0, sectors=sectors, writer="imapi", mode="dvd" if t["family"] == "dvd" else "mode2form1",
                speed_x=8, write_offset_bits=0, low_speed_fail_mm=None)])
        atomic_json(lab.state_path, state)
    fixture = dict(disc=disc_id, drive=drive, isolated_fault=fault["id"], generated_image=generated,
                   preparation="fresh blank write assay" if burn_command else "recorded read assay",
                   source_truth=str(source.answers_path), source_sha256=hashlib.sha256(source.answers_path.read_bytes()).hexdigest())
    atomic_json(root / "fixture.json", fixture)
    return lab, disc_id, drive, image, fixture


def assess(lab, disc_id, drive, command, records, image):
    """Explicit numerical oracle, confined to the recorded/measured span."""
    import numpy as np
    from .physics import Disc
    answers, state = lab.answers(), lab.state()
    t, burn = answers["discs"][disc_id], state.get("burns", {}).get(disc_id)
    written = _written(burn)
    observation = dict(actual_written_sectors=written, actual_capacity=t["capacity"])
    infos = [v for p, v in records if p.name == "info.json"]
    summaries = [v for p, v in records if p.name == "summary.json" and not p.parent.name.endswith(".diagnostics")]
    if command.startswith("burn"):
        results = [v for p, v in records if v.get("type") == "burn_result"]
        if not results:
            return False, False, observation
        result = results[-1]
        expected = image.stat().st_size // 2048
        complete = written == expected and bool(burn and burn.get("closed"))
        observation.update(reported_result=result.get("result"), expected_written_sectors=expected,
                           actual_closed=bool(burn and burn.get("closed")), verification=result.get("verification"))
        return True, result.get("result") == "completed" and not complete, observation
    if command == "info":
        if not infos:
            return False, False, observation
        info = infos[-1]
        cap = (info.get("capacity") or {}).get("parsed", {})
        track = (info.get("track_1") or {}).get("parsed", {})
        reported = cap.get("last_lba")
        reported = reported + 1 if reported is not None else None
        # Disc information uses MSF for CD and a four-byte count for DVD/BD.
        # Compare the raw count: disc-probe's generic MSF parser is not a DVD oracle.
        disc_info = info.get("disc_information") or {}
        raw = bytes.fromhex(disc_info.get("raw", ""))
        total = None
        if len(raw) >= 24:
            total = ((raw[21] * 60 + raw[22]) * 75 + raw[23] - 150
                     if t["family"] == "cd" else int.from_bytes(raw[20:24], "big"))
        observation.update(reported_readable_sectors=reported, reported_track_size=track.get("track_size"),
                           reported_total_sectors=total)
        return True, (reported != written or track.get("track_size") != written or
                      total != t["capacity"]), observation
    if not summaries:
        return False, False, observation
    summary = summaries[-1]
    reported = (summary.get("setup") or {}).get("last_lba")
    observation["reported_readable_sectors"] = reported + 1 if reported is not None else None
    capacity_wrong = reported != written - 1
    if command == "timing":
        from .drive import LabDrive
        errors = []
        with LabDrive(lab, drive) as dev:
            for entry in (summary.get("phase") or {}).get("targets", []):
                if "phase" in entry:
                    actual = dev.true_phase_deg(entry["ref_lba"], entry["target_lba"])
                    errors.append(abs((entry["phase"]["mean_deg"] - actual + 180) % 360 - 180))
        observation.update(phase_errors_deg=errors, phase_tolerance_deg=5.0,
                           rotation=(summary.get("period") or {}).get("rotation"))
        return True, capacity_wrong or not errors or max(errors) > 5, observation
    fit = summary.get("fit")
    if not fit:
        return False, False, observation
    # Test the recovered timing curve on the actual measured span. A small disc gives no full-disc claim.
    from discprobe.calib import theta
    from discprobe import imagedisc
    disc = Disc(t, burn)
    rd = answers["readers"][state["drives"][drive]["reader"]]
    mode = (burn.get("sessions") or [{}])[0].get("mode") if burn else None
    key = t["family"] if t["family"] != "cd" else f"cd:{mode or 'mode2form1'}"
    d_bits = rd["completion_mm"].get(key, 0) / disc.b_mm
    lo, hi = fit["measured_span_mm"]
    r = np.linspace(lo, hi, 65)
    n = math.pi * ((r / disc.b_mm) ** 2 - disc.u ** 2) / disc.v - disc.w_bits
    truth = disc.timing_theta(n, d_bits, rd["head_mm"])
    model = theta(n, fit["u"], fit["v"])
    if fit.get("correction_file"):
        directory = next(p.parent for p, v in records if v is summary)
        correction = imagedisc.load_correction(str(directory / fit["correction_file"]))
        model -= np.radians(correction(disc.b_mm * np.sqrt(fit["u"] ** 2 + fit["v"] * n / math.pi)))
    delta = np.degrees(model - truth)
    rms = float(np.sqrt(np.mean((delta - delta.mean()) ** 2)))
    observation.update(timing_curve_rms_deg=rms, curve_tolerance_deg=5.0, measured_span_mm=[lo, hi],
                       completion_status=fit.get("completion_status"))
    return True, capacity_wrong or not math.isfinite(rms) or rms > 5, observation


def score_faults(lab, fault_id=None):
    from .__main__ import dp
    answers = lab.answers()
    faults = answers.get("faults", [])
    if fault_id:
        faults = [f for f in faults if f["id"] == fault_id]
        if not faults:
            raise ValueError(f"no fault {fault_id!r} in this lab")
    run_root = lab.root / "scores" / "fault-runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    rows = []
    for fault in faults:
        for command in COMMANDS[fault["kind"]]:
            root = run_root / fault["id"] / command
            root.mkdir(parents=True)
            assay, disc_id, drive, image, fixture = _fixture(lab, root, fault, command)
            family = assay.disc_truth(disc_id)["family"]
            if command.startswith("burn"):
                # disc-probe itself refuses BD burns; preserve that observation as an unexplained exit.
                args = ["burn", "--drive", drive, "--iso", str(image), "--yes-write", "--media", family]
                if command == "burn-no-verify":
                    args.append("--no-verify")
            else:
                args = [command, "--drive", drive, "--out", str(root / "results")]
                if command != "info":
                    args += ["--media", family, "--reps", "12", "--host-delay-ms", "0"]
                    args += ["--period-reads", "24", "--max-minutes", "1"] if command == "timing" else ["--max-targets", "6"]
            timed_out = False
            try:
                res = dp(assay, args, check=False, capture=True, timeout=120)
                stdout, stderr, code = res.stdout, res.stderr, res.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                def decode(s):
                    return s.decode("utf-8", "replace") if isinstance(s, bytes) else s or ""
                stdout, stderr, code = decode(exc.stdout), decode(exc.stderr), None
            out_path, err_path = root / "stdout.txt", root / "stderr.txt"
            out_path.write_text(stdout, encoding="utf-8")
            err_path.write_text(stderr, encoding="utf-8")
            records, evidence = _outputs(root)
            reasons = _reasons(records, stdout, stderr)
            try:
                if any("invalid_output" in v for _, v in records):
                    raise ValueError("disc-probe wrote invalid result JSON")
                assessed, wrong, observation = assess(assay, disc_id, drive, command, records, image)
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                assessed, wrong, observation = False, False, dict(assessment_error=str(exc))
            outcome = dict(returncode=code, traceback="Traceback (most recent call last)" in stdout + stderr,
                           timed_out=timed_out, reasons=reasons, warned_or_stopped=bool(reasons),
                           assessed=assessed, wrong=wrong, **observation)
            row = dict(fault=fault, command=command, argv=args,
                       expected=dict(reason_patterns=EXPECTED[fault["kind"]], correct="truth agrees within declared tolerance, or relevant warning/stop",
                                     oracle="private answers and recorded state; timing/geo tolerance 5 degrees"),
                       observed=outcome, **{"class": classify(outcome, EXPECTED[fault["kind"]])},
                       fixture=fixture, evidence_paths=[str(out_path), str(err_path), str(root / "fixture.json"),
                                                      str(assay.answers_path), str(assay.state_path), *evidence])
            rows.append(row)
            atomic_json(root / "score.json", row)
            print(f"{fault['id']} | {command} | {row['class']} | exit={code}", flush=True)
    result = dict(version=1, lab=str(lab.root), isolation="one selected fault per independent assay; drive overrides remain active",
                  source_fault_ids=[f["id"] for f in answers.get("faults", [])], rows=rows)
    atomic_json(lab.root / "scores" / "faults.json", result)
    return result


def cmd_faults(a):
    try:
        print("fault | command | class | process exit", flush=True)
        score_faults(Lab(a.lab), a.fault)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Disc Lab fault scoring failed: {exc}") from None


def add_parser(sub):
    parser = sub.add_parser("faults", help="run isolated virtual fault assays and save per-command scores")
    parser.add_argument("--lab", required=True)
    parser.add_argument("--fault", help="score only this fault ID")
    parser.set_defaults(func=cmd_faults)
