"""Assisted picture-phi editing. No hardware, reader changes or implicit extrapolation.

Controls fit only a smooth additive offset. Independent observations never enter
that fit; thresholds are fixed before the edit and cannot be supplied by the UI.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from scipy.interpolate import BSpline
from scipy.sparse.linalg import spsolve

COORDINATES = dict(radius="mm", angle="deg", positive="ccw-data-side", meaning="picture-phi")
RMS_LIMIT = .5
MAX_LIMIT = 1.


def digest(value):
    # JavaScript sends 26.0 back as 26: hash numeric values across JSON runtimes.
    def canonical(item):
        if isinstance(item, dict):
            return {key: canonical(value) for key, value in item.items()}
        if isinstance(item, list):
            return [canonical(value) for value in item]
        if isinstance(item, float) and item.is_integer():
            return int(item)
        return item
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def evaluate(core, radii):
    lo, hi = core["radius_valid_mm"]
    r = np.clip(radii, lo, hi)
    if "spline" in core:
        s = core["spline"]
        return BSpline(s["t"], s["c"], s["k"])(r)
    return np.polyval(core["poly_in_x"], (r - 40.) / 15.)


def _model(core):
    if not isinstance(core, dict) or core.get("kind") != "angle-correction":
        raise ValueError("no_automatic_curve: need an angle-correction, not photo L or ring radii")
    digest(core)  # also reject NaN in metadata
    span = np.asarray(core["radius_valid_mm"], dtype=float)
    if span.shape != (2,) or not np.isfinite(span).all() or not 0 < span[0] < span[1] <= 60:
        raise ValueError("invalid_radius_range")
    if ("spline" in core) == ("poly_in_x" in core):
        raise ValueError("ambiguous_curve_representation")
    if "spline" in core:
        s = core["spline"]
        k = s["k"]
        if type(k) is not int or not 1 <= k <= 5:
            raise ValueError("unsupported_spline_degree")
        curve = BSpline(s["t"], s["c"], k)
        n = len(s["t"]) - k - 1
        if np.asarray(s["c"]).ndim != 1 or not np.isfinite(s["t"]).all() or not np.isfinite(s["c"]).all():
            raise ValueError("invalid_spline")
        if s["t"][k] > span[0] or s["t"][n] < span[1]:
            raise ValueError("spline_does_not_cover_range")
        # A strictly increasing Greville grid is needed for the additive fit.
        g = np.array([np.mean(curve.t[i + 1:i + k + 1]) for i in range(n)])
        if np.any(np.diff(g) <= 0):
            raise ValueError("unsupported_discontinuous_spline")
    else:
        c = np.asarray(core["poly_in_x"], dtype=float)
        if c.ndim != 1 or not 1 <= len(c) <= 20 or not np.isfinite(c).all():
            raise ValueError("invalid_polynomial")
    if not np.isfinite(evaluate(core, np.linspace(*span, 257))).all():
        raise ValueError("nonfinite_curve")
    return span


def begin(core, evidence):
    """Lossless envelope. Evidence contains fit_ids and independent checks with IDs.

    Generic callers must supply phi in this module's coordinate convention;
    run_operation supplies those observations from geo's separate check reads.
    """
    lo, hi = _model(core)
    return dict(kind="curve-edit", version=1, coordinates=deepcopy(COORDINATES),
                radius_valid_mm=deepcopy(core["radius_valid_mm"]), source_sha256=digest(core),
                evidence_sha256=digest(evidence), automatic=deepcopy(core),
                controls=[dict(radius_mm=float(r), delta_deg=0.) for r in np.linspace(lo, hi, 5)])


def to_core(edit):
    """Refit controls in the original model's space, preserving metadata and range."""
    core = deepcopy(edit["automatic"])
    lo, hi = _model(core)
    if (edit.get("kind") != "curve-edit" or edit.get("version") != 1
            or edit.get("coordinates") != COORDINATES
            or edit.get("radius_valid_mm") != core["radius_valid_mm"]
            or edit.get("source_sha256") != digest(core)):
        raise ValueError("edited_contract_or_source")
    controls = edit.get("controls")
    if not isinstance(controls, list) or not 4 <= len(controls) <= 64:
        raise ValueError("need_4_to_64_controls")
    r = np.array([p["radius_mm"] for p in controls], dtype=float)
    d = np.array([p["delta_deg"] for p in controls], dtype=float)
    if not np.isfinite(r).all() or not np.isfinite(d).all() or np.any(np.diff(r) <= 0):
        raise ValueError("controls_must_be_finite_and_increasing")
    if r[0] != lo or r[-1] != hi:
        raise ValueError("controls_must_cover_exact_automatic_range")
    if not np.any(d):
        return core
    degree = min(3, core.get("spline", {}).get("k", 3))
    coef = np.polyfit((r - 40.) / 15., d, degree)
    if "poly_in_x" in core:
        core["poly_in_x"] = np.polyadd(core["poly_in_x"], coef).tolist()
    else:
        s = core["spline"]
        k, t = s["k"], np.asarray(s["t"])
        n = len(t) - k - 1
        g = np.array([np.mean(t[i + 1:i + k + 1]) for i in range(n)])
        basis = BSpline.design_matrix(g, t, k)
        delta = spsolve(basis.tocsc(), np.polyval(coef, (g - 40.) / 15.))
        c = np.asarray(s["c"], dtype=float).copy()
        c[:n] += delta
        s["c"] = c.tolist()
    _model(core)
    return core


def preview(edit, evidence):
    """Return candidate and independent validation, never mutate input or files."""
    try:
        if edit.get("evidence_sha256") != digest(evidence):
            raise ValueError("stale_evidence")
        candidate = to_core(edit)
        lo, hi = candidate["radius_valid_mm"]
        checks = evidence.get("checks", [])
        ids = [p["id"] for p in checks]
        if len(ids) < 4 or len(set(ids)) != len(ids):
            raise ValueError("need_4_unique_independent_checks")
        if not evidence.get("fit_ids") or set(ids) & set(evidence["fit_ids"]):
            raise ValueError("validation_overlaps_fit_or_fit_ids_missing")
        if candidate.get("validation", {}).get("thin_intervals_mm") or evidence.get("holes_mm"):
            raise ValueError("unvalidated_holes: remeasure before editing")
        r = np.array([p["radius_mm"] for p in checks], dtype=float)
        truth = np.array([p["phi_deg"] for p in checks], dtype=float)
        if not np.isfinite(r).all() or not np.isfinite(truth).all() or np.any((r < lo) | (r > hi)):
            raise ValueError("invalid_independent_range_or_values")
        ordered = np.sort(r)
        if (len(np.unique(r)) != len(r) or ordered[0] > lo + .2 * (hi - lo)
                or ordered[-1] < hi - .2 * (hi - lo)
                or np.max(np.diff(ordered)) > .4 * (hi - lo)):
            raise ValueError("independent_checks_do_not_cover_range")
        error = evaluate(candidate, r) - truth  # no modulo: reject whole-turn mistakes
        rms, peak = float(np.sqrt(np.mean(error ** 2))), float(np.max(abs(error)))
        passed = bool(np.isfinite(error).all() and rms <= RMS_LIMIT and peak <= MAX_LIMIT)
        validation = dict(passed=passed, reason="ok" if passed else "independent_error_exceeded",
                          count=len(checks), rms_deg=rms, max_deg=peak,
                          rms_limit_deg=RMS_LIMIT, max_limit_deg=MAX_LIMIT,
                          residuals=[dict(id=p["id"], radius_mm=float(radius), error_deg=float(e))
                                     for p, radius, e in zip(checks, r, error)])
        grid = np.linspace(lo, hi, 161)
        return dict(ok=passed, saved=False, validation=validation, candidate=candidate,
                    degree=min(3, candidate.get("spline", {}).get("k", 3)),
                    plot=dict(radius_mm=grid.tolist(), automatic_deg=evaluate(edit["automatic"], grid).tolist(),
                              candidate_deg=evaluate(candidate, grid).tolist()))
    except (ValueError, TypeError, KeyError, np.linalg.LinAlgError) as exc:
        return dict(ok=False, saved=False, validation=dict(passed=False, reason=str(exc)))


def _load_run(run):
    folder = Path(run).resolve()
    current = json.loads((folder / "correction.json").read_text(encoding="utf-8"))
    _model(current)
    baseline = current
    # An explicitly partitioned photo/gridscan data set can use the same engine.
    # A scalar photo-L result cannot produce this file or an automatic phi curve.
    declared = folder / "curve-evidence.json"
    if declared.exists():
        evidence = json.loads(declared.read_text(encoding="utf-8"))
        if "curve_edit" in current:
            baseline = json.loads((folder / "correction.automatic.json").read_text(encoding="utf-8"))
        if (evidence.get("version") != 1 or evidence.get("coordinates") != COORDINATES
                or evidence.get("automatic_sha256") != digest(baseline)
                or not evidence.get("dataset_id") or not evidence.get("source")
                or not evidence.get("input_sha256")):
            raise ValueError("invalid_declared_curve_evidence")
        evidence["run_sha256"] = digest(evidence)
        if "curve_edit" in current and (
                digest(baseline) != current["curve_edit"]["original_sha256"]
                or evidence["run_sha256"] != current["curve_edit"]["run_evidence_sha256"]):
            raise ValueError("stale_original_or_run_evidence")
        return folder, current, baseline, evidence
    probes = json.loads((folder / "probes.json").read_text(encoding="utf-8"))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    evidence_hash = digest(dict(probes=probes, summary=summary))
    if "curve_edit" in current:
        baseline = json.loads((folder / "correction.automatic.json").read_text(encoding="utf-8"))
        if digest(baseline) != current["curve_edit"]["original_sha256"]:
            raise ValueError("stale_original_or_run_evidence")
    if current.get("geo_fit") != {k: summary[k] for k in ("u", "v")}:
        raise ValueError("curve_does_not_match_geo_fit")
    fit_ids = set(summary.get("coverage", {}).get("measured_lbas", []))
    fit_ids.add(summary["reference_lba"])
    fit_ids.update(p["lba"] for p in probes["points"])
    # Geometry targets may not be duplicated in coverage on older runs.
    import csv
    targets = folder / "targets.csv"
    if targets.exists():
        with targets.open(encoding="utf-8", newline="") as handle:
            fit_ids.update(int(p["lba"]) for p in csv.DictReader(handle))
        evidence_hash = digest([evidence_hash, hashlib.sha256(targets.read_bytes()).hexdigest()])
    if "curve_edit" in current and evidence_hash != current["curve_edit"]["run_evidence_sha256"]:
        raise ValueError("stale_original_or_run_evidence")
    intervals = summary.get("coverage", {}).get("measured_intervals_mm", [])
    lo, hi = current["radius_valid_mm"]
    if not intervals or not any(a <= lo + 1e-6 and z >= hi - 1e-6 for a, z in intervals):
        raise ValueError("automatic_range_not_covered_by_measurement")
    # The baseline's residual is measured phase - (base - automatic phi).
    checks = [dict(id=p["lba"], radius_mm=p["radius_mm"],
                   phi_deg=float(evaluate(baseline, p["radius_mm"])) - p["error_deg"])
              for p in probes["independent_checks"]]
    evidence = dict(fit_ids=sorted(fit_ids), checks=checks, run_sha256=evidence_hash,
                    holes_mm=baseline.get("validation", {}).get("thin_intervals_mm", []))
    return folder, current, baseline, evidence


def _atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix=".curve-edit-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run_operation(run, edit=None, save=False):
    """CLI and web share this durable operation; only successful save writes files."""
    lock = None
    try:
        if save:
            lock = Path(run).resolve() / ".curve-edit.lock"
            try:
                lock.touch(exist_ok=False)
            except FileExistsError:
                lock = None
                raise ValueError("curve_edit_busy: retry after the other save") from None
        folder, current, baseline, evidence = _load_run(run)
        initial = begin(current, evidence)
        if edit is None:
            if save:
                raise ValueError("save_requires_edit")
            result = preview(initial, evidence)
            if "plot" not in result:
                grid = np.linspace(*current["radius_valid_mm"], 161)
                values = evaluate(current, grid).tolist()
                result["plot"] = dict(radius_mm=grid.tolist(), automatic_deg=values, candidate_deg=values)
            result.update(edit=initial, available=True)
            result["plot"]["automatic_deg"] = evaluate(baseline, result["plot"]["radius_mm"]).tolist()
            return result
        if not isinstance(edit, dict):
            raise ValueError("edit_must_be_an_object")
        if edit.get("source_sha256") != digest(current) or edit.get("automatic", current) != current:
            raise ValueError("stale_automatic_result: reopen the editor")
        # Thin web requests omit the potentially large spline. The hash binds the
        # controls to this exact persisted result; retain the server's metadata.
        edit = dict(edit, automatic=deepcopy(current))
        result = preview(edit, evidence)
        if "plot" in result:
            result["plot"]["automatic_deg"] = evaluate(baseline, result["plot"]["radius_mm"]).tolist()
        if save and result["ok"]:
            candidate = deepcopy(result["candidate"])
            candidate["validation"] = dict(candidate.get("validation", {}),
                                            independent_checks=result["validation"]["count"],
                                            independent_rms_deg=result["validation"]["rms_deg"],
                                            independent_max_deg=result["validation"]["max_deg"])
            original_hash = digest(baseline)
            candidate["curve_edit"] = dict(version=1, original_sha256=original_hash,
                                            run_evidence_sha256=evidence["run_sha256"],
                                            parent_sha256=digest(current), controls=deepcopy(edit["controls"]),
                                            validation=result["validation"])
            # Detect outside writers too, immediately before touching persistent data.
            _, fresh, _, fresh_evidence = _load_run(run)
            if fresh != current or fresh_evidence != evidence:
                raise ValueError("stale_run_during_save")
            backup = folder / "correction.automatic.json"
            if backup.exists():
                if digest(json.loads(backup.read_text(encoding="utf-8"))) != original_hash:
                    raise ValueError("original_backup_conflict")
            else:
                _atomic_json(backup, baseline)
            history = folder / "curve-edit-history"
            history.mkdir(exist_ok=True)
            _atomic_json(history / (digest(candidate) + ".json"), dict(edit=edit, result=result))
            _atomic_json(folder / "correction.json", candidate)
            result.update(saved=True, path=str(folder / "correction.json"))
        return result
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return dict(ok=False, saved=False, available=False, validation=dict(passed=False, reason=str(exc)))
    finally:
        if lock is not None:
            lock.unlink(missing_ok=True)


def cli(args):
    from . import ui
    try:
        edit = json.loads(args.edit_json) if args.edit_json else (
            json.loads(Path(args.edit).read_text(encoding="utf-8")) if args.edit else None)
        result = run_operation(args.run, edit, args.save)
    except (ValueError, OSError) as exc:
        result = dict(ok=False, saved=False, validation=dict(passed=False, reason=str(exc)))
    ui.event("result", step="curve-edit", **result)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    # Opening an available automatic curve succeeds even if its existing error is high.
    if not result.get("ok") and not result.get("available"):
        raise SystemExit(2)
