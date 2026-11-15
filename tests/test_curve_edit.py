"""Synthetic-only curve editing, independent rejection and durable CLI/API parity."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from scipy.interpolate import make_interp_spline

from discprobe.curve_edit import begin, digest, evaluate, preview, run_operation, to_core
from discprobe.imagedisc import load_correction
from discprobe.webui import APIError, Backend, command


def automatic(spline=False):
    core = dict(kind="angle-correction", radius_valid_mm=[26., 56.],
                source="geo automatic repeated probes", geo_fit=dict(u=180000., v=5.5),
                meaning="picture phi(r), degrees counter-clockwise; track angle is base minus phi",
                validation=dict(thin_intervals_mm=[]), extra={"preserve": [1, "原始"]})
    if spline:
        r = np.linspace(26, 56, 13)
        s = make_interp_spline(r, np.sin(r / 7) * .1)
        core["spline"] = dict(t=s.t.tolist(), c=s.c.tolist(), k=s.k)
    else:
        core["poly_in_x"] = [.03, -.02, .1]
        core["x"] = "(r_mm - 40) / 15"
    return core


def evidence(core, offset=0.):
    r = np.linspace(27., 55., 15)
    return dict(fit_ids=list(range(100)), checks=[dict(id=100 + i, radius_mm=float(x),
                phi_deg=float(evaluate(core, x)) + offset) for i, x in enumerate(r)])


def write_run(folder, spline=False, offset=1.25):
    folder.mkdir(exist_ok=True)
    core = automatic(spline)
    data = evidence(core, offset)
    probes = dict(points=[dict(lba=i) for i in range(10)], failed=[],
                  independent_checks=[dict(lba=p["id"], radius_mm=p["radius_mm"], error_deg=-offset)
                                      for p in data["checks"]])
    summary = dict(u=180000., v=5.5, reference_lba=1, coverage=dict(measured_lbas=list(range(10)),
                   measured_intervals_mm=[[26., 56.]]))
    for name, value in [("correction.json", core), ("probes.json", probes), ("summary.json", summary)]:
        (folder / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return core


@pytest.mark.parametrize("spline", [False, True])
def test_lossless_roundtrip_and_no_input_mutation(spline):
    core = automatic(spline)
    saved = deepcopy(core)
    edit = begin(core, evidence(core))
    assert to_core(json.loads(json.dumps(edit))) == core
    assert edit["controls"][0]["delta_deg"] == 0
    assert core == saved


@pytest.mark.parametrize("spline", [False, True])
def test_known_offset_recovered_independently(spline):
    core = automatic(spline)
    data = evidence(core, 1.25)
    edit = begin(core, data)
    assert not preview(edit, data)["ok"]
    for p in edit["controls"]:
        p["delta_deg"] = 1.25
    result = preview(edit, data)
    assert result["ok"] and result["validation"]["rms_deg"] < 1e-12
    r = np.linspace(26, 56, 2001)
    assert np.max(abs(evaluate(result["candidate"], r) - evaluate(core, r) - 1.25)) < 2e-12
    assert core == automatic(spline)
    if spline:
        assert result["candidate"]["spline"]["t"] == core["spline"]["t"]


@pytest.mark.parametrize("spline", [False, True])
def test_cubic_offset_in_original_space(spline):
    core = automatic(spline)
    data = evidence(core)
    delta = lambda r: .2 * ((r - 40) / 15) ** 3 - .1 * (r - 40) / 15
    for p in data["checks"]:
        p["phi_deg"] += delta(p["radius_mm"])
    edit = begin(core, data)
    for p in edit["controls"]:
        p["delta_deg"] = delta(p["radius_mm"])
    result = preview(edit, data)
    assert result["ok"] and result["validation"]["rms_deg"] < 1e-12


@pytest.mark.parametrize("mutation,reason", [
    (lambda e: e["checks"].clear(), "need_4_unique"),
    (lambda e: e["checks"].append(deepcopy(e["checks"][0])), "need_4_unique"),
    (lambda e: e["fit_ids"].append(100), "overlaps_fit"),
    (lambda e: e["fit_ids"].clear(), "fit_ids_missing"),
    (lambda e: e["checks"][0].update(radius_mm=25.), "invalid_independent_range"),
    (lambda e: e["checks"][0].update(phi_deg=float('nan')), "nan"),
    (lambda e: e.update(holes_mm=[[30, 35]]), "unvalidated_holes"),
    (lambda e: [p.update(radius_mm=40 + i / 20) for i, p in enumerate(e["checks"])], "do_not_cover_range"),
])
def test_bad_evidence_rejected(mutation, reason):
    core = automatic()
    data = evidence(core)
    mutation(data)
    try:
        edit = begin(core, data)
    except ValueError as exc:
        assert reason in str(exc)
        return
    result = preview(edit, data)
    assert not result["ok"] and reason in result["validation"]["reason"]


@pytest.mark.parametrize("mutation", [
    lambda e: e.update(version=2),
    lambda e: e["coordinates"].update(angle="rad"),
    lambda e: e.update(radius_valid_mm=[25, 57]),
    lambda e: e["automatic"].update(source="fake"),
    lambda e: e["controls"][0].update(radius_mm=27),
    lambda e: e["controls"][2].update(delta_deg=float('inf')),
    lambda e: e["controls"][2].update(radius_mm=26),
])
def test_bad_edit_rejected(mutation):
    core = automatic()
    data = evidence(core)
    edit = begin(core, data)
    mutation(edit)
    assert not preview(edit, data)["ok"]


@pytest.mark.parametrize("spline", [False, True])
def test_save_failure_byte_preservation_and_reopen(tmp_path, spline):
    run = tmp_path / "geo"
    write_run(run, spline)
    initial_bytes = (run / "correction.json").read_bytes()
    initial = run_operation(run)
    assert initial["available"] and not initial["ok"]
    edit = initial["edit"]
    for p in edit["controls"]:
        p["delta_deg"] = -5.
    bad = run_operation(run, edit, save=True)
    assert not bad["ok"] and not bad["saved"]
    assert (run / "correction.json").read_bytes() == initial_bytes
    assert not (run / "correction.automatic.json").exists()
    assert not (run / ".curve-edit.lock").exists()
    for p in edit["controls"]:
        p["delta_deg"] = 1.25
    good = run_operation(run, edit, save=True)
    assert good["ok"] and good["saved"]
    saved = (run / "correction.json").read_bytes()
    assert json.loads((run / "correction.automatic.json").read_text(encoding="utf-8")) == json.loads(initial_bytes)
    assert len(list((run / "curve-edit-history").glob("*.json"))) == 1
    loader = load_correction(str(run / "correction.json"))
    assert float(loader(40.)) == pytest.approx(float(evaluate(automatic(spline), 40.)) + 1.25)
    from discprobe.disexport import target_angle
    n = np.array([2e10, 3e10])
    base = target_angle(n, 180000., 5.5, 133.6)
    changed = target_angle(n, 180000., 5.5, 133.6, loader)
    radius = 133.6e-6 * np.sqrt(180000. ** 2 + 5.5 * n / np.pi)
    assert np.max(abs(base - changed - np.radians(loader(radius)))) < 1e-9
    reopened = run_operation(run)
    assert reopened["ok"] and reopened["available"]
    assert not run_operation(run, edit, save=True)["saved"]  # stale editor
    assert (run / "correction.json").read_bytes() == saved
    second = reopened["edit"]
    assert run_operation(run, second, save=True)["saved"]
    # Independent target remains anchored to original reads across multiple edits.
    next_edit = run_operation(run)["edit"]
    for p in next_edit["controls"]:
        p["delta_deg"] = 2.
    assert not run_operation(run, next_edit, save=True)["saved"]


def test_changed_evidence_and_target_overlap(tmp_path):
    run = tmp_path / "geo"
    write_run(run, offset=0.)
    edit = run_operation(run)["edit"]
    original = (run / "correction.json").read_bytes()
    (run / "targets.csv").write_text("lba\n100\n", encoding="utf-8")
    result = run_operation(run, edit, save=True)
    assert not result["saved"] and result["validation"]["reason"] == "stale_evidence"
    result = run_operation(run)
    assert not result["ok"] and 'overlaps_fit' in result["validation"]["reason"]
    assert (run / "correction.json").read_bytes() == original


def test_web_command_whitelist_and_cli(tmp_path):
    run = tmp_path / "geo"
    write_run(run)
    edit = run_operation(run)["edit"]
    for p in edit["controls"]:
        p["delta_deg"] = 1.25
    argv, drive = command(dict(action="curve-edit", args=dict(run="geo", edit_json=edit, save=True)), tmp_path, [])
    assert drive is None and "--save" in argv and json.loads(argv[argv.index('--edit-json') + 1]) == edit
    for args in [dict(run="../escape"), dict(run="geo", force=True), dict(run="geo", save=True), dict(run="geo", edit_json=[])]:
        with pytest.raises(APIError):
            command(dict(action="curve-edit", args=args), tmp_path, [])
    path = tmp_path / "edit.json"
    path.write_text(json.dumps(edit), encoding="utf-8")
    result = subprocess.run([sys.executable, "-B", "-m", "discprobe", "curve-edit", "--run", str(run), "--edit", str(path), "--save"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["saved"]


def test_actual_backend_child_result_and_no_drive_query(tmp_path):
    write_run(tmp_path / "geo", offset=0.)
    def forbidden():
        raise AssertionError("curve-edit must not enumerate drives")
    backend = Backend(tmp_path, drive_provider=forbidden)
    try:
        ident = backend.start(dict(action="curve-edit", args=dict(run="geo")))["job"]
        job = backend.get_job(ident)
        assert job.finished.wait(20)
        assert job.exit == 0 and job.result["edit"]["kind"] == "curve-edit"
        assert job.result["validation"]["count"] == 15
        edit = job.result["edit"]
        bad = deepcopy(edit)
        for p in bad["controls"]:
            p["delta_deg"] = 360.
        before = (tmp_path / "geo" / "correction.json").read_bytes()
        ident = backend.start(dict(action="curve-edit", args=dict(run="geo", edit_json=bad, save=True)))["job"]
        job = backend.get_job(ident)
        assert job.finished.wait(20) and job.exit == 2 and not job.result["saved"]
        assert (tmp_path / "geo" / "correction.json").read_bytes() == before
    finally:
        backend.close()


def test_declared_photo_holdout_same_cli_contract(tmp_path):
    core = automatic()
    core["source"] = ["photo-training.csv"]
    data = evidence(core, .75)
    data.update(version=1, coordinates=begin(core, data)["coordinates"], automatic_sha256=digest(core),
                dataset_id="synthetic-photo-split-v1", source="synthetic frozen photo points",
                input_sha256={"synthetic-training": "1" * 64, "synthetic-holdout": "2" * 64})
    (tmp_path / "correction.json").write_text(json.dumps(core), encoding="utf-8")
    (tmp_path / "curve-evidence.json").write_text(json.dumps(data), encoding="utf-8")
    edit = run_operation(tmp_path)["edit"]
    for p in edit["controls"]:
        p["delta_deg"] = .75
    assert run_operation(tmp_path, edit, True)["saved"]
    assert run_operation(tmp_path)["ok"]
    # A changed split or input manifest cannot silently reuse the old observations.
    data["dataset_id"] = "different"
    (tmp_path / "curve-evidence.json").write_text(json.dumps(data), encoding="utf-8")
    assert not run_operation(tmp_path)["available"]


@pytest.mark.parametrize("degree", [1, 2])
def test_lower_degree_spline_offset(degree):
    core = automatic()
    r = np.linspace(26, 56, 11)
    s = make_interp_spline(r, np.sin(r / 9), k=degree)
    core.pop("poly_in_x")
    core["spline"] = dict(t=s.t.tolist(), c=s.c.tolist(), k=s.k)
    data = evidence(core, .25)
    edit = begin(core, data)
    for p in edit["controls"]:
        p["delta_deg"] = .25
    result = preview(edit, data)
    assert result["ok"] and result["degree"] == degree
    assert result["validation"]["rms_deg"] < 1e-12


def test_thin_json_request_and_numeric_canonical_hash(tmp_path):
    write_run(tmp_path / "geo", offset=0.)
    edit = run_operation(tmp_path / "geo")["edit"]
    assert digest(dict(r=26.0, n=-0.0)) == digest(dict(r=26, n=0))
    edit.pop("automatic")
    assert run_operation(tmp_path / "geo", edit, True)["saved"]
