"""Scenario and fault contracts; all devices and writes are virtual."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from discprobe import mmc
from discprobe.scsi import Sense
from disclab.__main__ import ROOT, main
from disclab.drive import LabDrive, LabRecorder
from disclab.faults import EXPECTED, classify, score_faults
from disclab.lab import Lab, atomic_json
from disclab.scenario import load_scenario, make_scenario_box


def spec(tmp_path, raw):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def make_lab(tmp_path, kind=None, params=None, initial="burned", extra=None):
    image = tmp_path / "source.iso"
    image.write_bytes(bytes(range(256)) * (2048 * 128 // 256))
    raw = dict(discs=dict(count=1, seed=17, capacity=512,
                         initial_state="blank" if initial == "blank" else dict(state=initial, iso=str(image))),
               faults=[dict(kind=kind, params=params or {}, id="test")] if kind else [])
    if extra:
        raw.update(extra)
    scenario = load_scenario(spec(tmp_path, raw))
    lab = Lab(tmp_path / "lab")
    make_scenario_box(lab, scenario)
    with lab.locked_state() as st:
        st["drives"]["X:"]["tray"] = lab.box()["discs"][0]
    return lab, image


@pytest.mark.parametrize("seed,expected", [
    (1, "57e4f31cebbeee62b1f79cc13f8e3f4080f16dba1b1683e3a6c8257e8d8f32e6"),
    (17, "77ea33de110150344a670549e0a1ec6d5d6f07394142336ddefdf320a1bd77ef"),
])
def test_default_box_bytes_match_prechange(tmp_path, seed, expected):
    # Hashes captured from the unchanged generator before this task's edits.
    lab = Lab(tmp_path / "default")
    main(["box", "--lab", str(lab.root), "--count", "3", "--seed", str(seed)])
    assert hashlib.sha256(lab.answers_path.read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("flag,value", [("--count", "2"), ("--seed", "18"), ("--reader", "noisy"), ("--media", "cd-r")])
def test_cli_refuses_explicit_conflicts_before_writing(tmp_path, flag, value):
    path = spec(tmp_path, dict(discs=dict(count=1, seed=17, media="dvd-r"), drive=dict(profile="gh70n")))
    lab = tmp_path / "refused"
    with pytest.raises(SystemExit, match="conflicts") as exc:
        main(["box", "--lab", str(lab), "--scenario", str(path), flag, value])
    assert "\n" not in str(exc.value)
    assert not lab.exists()


def test_cli_fills_absent_fields_and_accepts_equal_values(tmp_path):
    path = spec(tmp_path, {"discs": {"count": 2}})
    lab = Lab(tmp_path / "filled")
    main(["box", "--lab", str(lab.root), "--scenario", str(path), "--count", "2", "--seed", "9"])
    assert lab.answers()["seed"] == 9 and lab.box()["count"] == 2


@pytest.mark.parametrize("raw", [
    {"oops": 1}, {"discs": {"media": "dvd"}}, {"discs": {"count": True}},
    {"version": True},
    {"discs": {"count": 1, "overrides": [{"parameters": []}]}},
    {"discs": {"initial_state": {"state": []}}},
    {"drive": {"burn_failure": {"kind": []}}},
    {"faults": [{"kind": "read_error", "id": "a", "params": {"lba": [1, 2], "disc": []}}]},
    {"faults": [{"kind": "spindle_unsteady", "id": "a", "params": {"mode": []}}]},
    {"discs": {"seed": -1}}, {"discs": {"initial_state": ["blank", "burned"]}},
    {"discs": {"parameters": {"u": 3, "b_nm": 100, "start_radius_mm": 24}}},
    {"discs": {"parameters": {"u": 3, "start_radius_mm": 24}}},
    {"discs": {"initial_state": {"state": "blank", "random": True}}},
    {"drive": {"overrides": {"outlier_rate": 2}}},
    {"drive": {"overrides": {"vendor": "TOO-LONG-VENDOR"}}},
    {"drive": {"burn_failure": {"kind": "stop_at", "fraction": 1}}},
    {"faults": [{"kind": "read_error", "id": "bad/path", "params": {"lba": [1, 2]}}]},
    {"faults": [{"kind": "read_error", "id": "a", "params": {}}]},
    {"faults": [{"kind": "read_error", "id": "a", "params": {"lba": [1, 1]}}]},
    {"faults": [{"kind": "capacity_misreport", "id": "a", "params": {"offset": 1, "sectors": 32}}]},
    {"faults": [{"kind": "spindle_unsteady", "id": "a", "params": {"amplitude": float("nan")}}]},
    {"faults": [{"kind": "burn_interrupt", "id": "a", "params": {"report_success": "yes"}}]},
    {"faults": [{"kind": "burn_interrupt", "id": "same"}, {"kind": "burn_interrupt", "id": "same"}]},
])
def test_invalid_scenarios(tmp_path, raw):
    with pytest.raises(ValueError):
        load_scenario(spec(tmp_path, raw))


@pytest.mark.parametrize("initial,closed,sectors", [("blank", False, 0), ("burned", True, 128), ("open", False, 128), ("partial", False, 64)])
def test_initial_states_and_content(tmp_path, initial, closed, sectors):
    lab, image = make_lab(tmp_path, initial=initial)
    truth = lab.disc_truth(lab.box()["discs"][0])
    assert truth["initial_state"]["state"] == initial
    with LabDrive(lab, "X:") as drive:
        assert drive._written_sectors() == sectors
        assert bool(drive.burn and drive.burn["closed"]) == closed
        if sectors:
            reply = drive.execute(mmc.read10(sectors - 1), 2048)
            assert reply.ok and reply.data == image.read_bytes()[(sectors - 1) * 2048:sectors * 2048]
            assert drive.execute(mmc.read10(sectors), 2048).sense == Sense(5, 0x21, 0)


def test_parameter_and_drive_overrides(tmp_path):
    raw = dict(discs=dict(count=1, mid="CUSTOM", capacity=4096,
                         parameters=dict(b_nm=130, start_radius_mm=24, v=5.5, ecc_um=4, dish_mm=0.2, saddle_mm=0.3),
                         defect_arcs=[dict(r_mm=[23, 25], deg=[0, 360])]),
               drive=dict(profile="noisy", overrides=dict(vendor="LAB", product="CUSTOM", firmware="V2",
                   mode="CLV", jitter_us=2, outlier_rate=0, write_speeds_x={"dvd": [6, 8]},
                   completion_mm={"dvd": 0.3}, head_mm=0.1)))
    lab = Lab(tmp_path / "custom")
    make_scenario_box(lab, load_scenario(spec(tmp_path, raw)))
    t = next(iter(lab.answers()["discs"].values()))
    assert t["u"] * t["b_nm"] * 1e-6 == pytest.approx(24)
    assert t["dish_mm"] == 0.2 and t["capacity"] == 4096 and t["mid"] == "CUSTOM"
    with lab.locked_state() as st:
        st["drives"]["X:"]["tray"] = lab.box()["discs"][0]
    with LabDrive(lab, "X:") as dev:
        result = dev.execute(mmc.inquiry(), 96)
        assert b"CUSTOM" in result.data and b"V2" in result.data
        assert dev.mode == "clv" and dev.reader["completion_mm"]["dvd"] == 0.3


@pytest.mark.parametrize("params", [{"lba": [32, 33]}, {"r_mm": [0, 100]}])
def test_read_error_exact_sense_and_whole_range(tmp_path, params):
    lab, _ = make_lab(tmp_path, "read_error", params)
    with LabDrive(lab, "X:") as drive:
        # The narrow error lies between the old four-point flaw sampling positions.
        res = drive.execute(mmc.read12(1, 64), 64 * 2048)
        assert res.sense == Sense(3, 0x11, 0) and res.duration_us >= 1.6e6
        with pytest.raises(PermissionError):
            drive.execute(bytes([0x2A]) + bytes(9))


@pytest.mark.parametrize("params,expected", [({"offset": 20}, 148), ({"sectors": 100}, 100)])
def test_capacity_misreport_does_not_change_read_boundary(tmp_path, params, expected):
    lab, _ = make_lab(tmp_path, "capacity_misreport", params)
    with LabDrive(lab, "X:") as dev:
        cap = mmc.parse_capacity(dev.execute(mmc.read_capacity(), 8).data)
        assert cap["last_lba"] + 1 == expected
        track = dev._track_information(128)
        assert mmc.parse_track_information(track)["track_size"] == expected
        assert int.from_bytes(dev._disc_information(128)[20:24], "big") == (532 if "offset" in params else 100)
        assert dev.execute(mmc.read10(128), 2048).sense == Sense(5, 0x21, 0)
        assert dev.execute(mmc.read10(127), 2048).ok
        assert dev.truth["capacity"] == 512


@pytest.mark.parametrize("mode", ["jump", "drift"])
def test_spindle_activation_and_continuity(tmp_path, mode):
    lab, _ = make_lab(tmp_path, "spindle_unsteady", dict(amplitude=0.3, rate_hz=1, time_s=1, lba=32, mode=mode))
    with LabDrive(lab, "X:") as dev:
        base = dev._w
        dev.execute(mmc.read10(0, fua=True), 2048)
        assert dev._spindle_factor == 1
        dev.idle(1.25)
        dev.execute(mmc.read10(64, fua=True), 2048)
        assert abs(dev._w / base - 1) > 0.01
        assert dev._omega(dev._clock) > 0


@pytest.mark.parametrize("success", [False, True])
def test_burn_interrupt_persists_only_prefix(tmp_path, monkeypatch, success):
    lab, image = make_lab(tmp_path, "burn_interrupt", dict(fraction=0.25, report_success=success), initial="blank")
    monkeypatch.setattr("disclab.drive.time.sleep", lambda _: None)
    recorder = LabRecorder(lab, "X:", "dvd")
    if success:
        assert recorder.write(image, 8, threading.Event(), lambda **kw: None) == 8
    else:
        with pytest.raises(OSError, match="write interrupted"):
            recorder.write(image, 8, threading.Event(), lambda **kw: None)
    with LabDrive(lab, "X:") as dev:
        assert dev._written_sectors() == 32 and dev.burn["closed"] is False
        assert dev.execute(mmc.read10(31), 2048).data == image.read_bytes()[31 * 2048:32 * 2048]
        assert dev.execute(mmc.read10(32), 2048).sense == Sense(5, 0x21, 0)


@pytest.mark.parametrize("kind,expected", [("stop_at", 32), ("fail_close", 128)])
def test_drive_failure_behaviour(tmp_path, monkeypatch, kind, expected):
    behaviour = dict(kind=kind)
    if kind == "stop_at":
        behaviour["fraction"] = 0.25
    lab, image = make_lab(tmp_path, initial="blank", extra=dict(drive=dict(burn_failure=behaviour)))
    monkeypatch.setattr("disclab.drive.time.sleep", lambda _: None)
    with pytest.raises(OSError, match="interrupted|close failed"):
        LabRecorder(lab, "X:", "dvd").write(image, 8, threading.Event(), lambda **kw: None)
    with LabDrive(lab, "X:") as dev:
        assert dev._written_sectors() == expected and not dev.burn["closed"]


@pytest.mark.parametrize("outcome,expected", [
    (dict(returncode=1, reasons=["medium errors (3/11/00)"], warned_or_stopped=True), "detected"),
    (dict(returncode=0, reasons=["unreadable"], warned_or_stopped=False, assessed=True, wrong=True), "silent_wrong"),
    (dict(returncode=0, assessed=True, wrong=True), "silent_wrong"),
    (dict(returncode=0, assessed=True, wrong=False), "unaffected"),
    (dict(returncode=1, reasons=["no ISO found"], warned_or_stopped=True), "crash"),
    (dict(returncode=0, assessed=False), "crash"),
    (dict(returncode=1, traceback=True, reasons=["3/11/00"], warned_or_stopped=True), "crash"),
    (dict(returncode=None, timed_out=True), "crash"),
])
def test_classifier_synthetic_outcomes(outcome, expected):
    assert classify(outcome, EXPECTED["read_error"]) == expected


def test_small_end_to_end_scenario(tmp_path):
    lab, _ = make_lab(tmp_path, "burn_interrupt", dict(fraction=0.4, report_success=True), initial="blank")
    def unchanged():
        # The scorer works on copies: truth and the lab's drive/burn state stay as they were. The command
        # record under "steps" (written for every command, for front ends) is the only addition.
        state = json.loads(lab.state_path.read_text(encoding="utf-8"))
        state.pop("steps", None)
        return [lab.answers_path.read_bytes(), state]
    before = unchanged()
    completed = subprocess.run([sys.executable, "-B", "-m", "disclab", "faults", "--lab", str(lab.root), "--fault", "test"],
                               cwd=ROOT, text=True, capture_output=True, encoding="utf-8", timeout=90)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    scores = json.loads((lab.root / "scores" / "faults.json").read_text(encoding="utf-8"))
    # The scorer's mechanics, not disc-probe's behaviour of the day: disc-probe 0.1.2.1 missed the
    # no-verify case (silent_wrong); the fault fixes of 2026-11-14 detect it.
    rows = [(r["command"], r["class"]) for r in scores["rows"]]
    assert [c for c, _ in rows] == ["burn", "burn-no-verify"]
    assert rows[0][1] == "detected" and rows[1][1] in ("detected", "silent_wrong")
    for row in scores["rows"]:
        assert row["observed"]["actual_written_sectors"] < row["observed"]["expected_written_sectors"]
        assert all(Path(p).is_file() for p in row["evidence_paths"])
    assert before == unchanged()
    with pytest.raises(ValueError, match="no fault"):
        score_faults(lab, "missing")


def test_examples_parse():
    files = sorted((ROOT / "disclab" / "examples" / "scenarios").glob("*.json"))
    assert len(files) == 5
    assert sorted(len(load_scenario(p)["faults"]) for p in files) == [1, 1, 1, 1, 4]


def test_spindle_stop_and_unrelated_capacity_warning():
    outcome = dict(returncode=1, warned_or_stopped=True,
                   reasons=["the spindle speed never settled; is the read speed fixed (--speed)?"])
    assert classify(outcome, EXPECTED["spindle_unsteady"]) == "detected"
    outcome.update(returncode=0, assessed=True, wrong=True)
    assert classify(outcome, EXPECTED["capacity_misreport"]) == "silent_wrong"


def test_combined_faults_and_disc_selection(tmp_path):
    raw = dict(discs=dict(count=2, capacity=512), faults=[
        dict(id="r", kind="read_error", params=dict(lba=[32, 64], disc="LAB-A 1-02")),
        dict(id="c", kind="capacity_misreport", params=dict(offset=20)),
        dict(id="s", kind="spindle_unsteady", params=dict(mode="jump", amplitude=0.2)),
        dict(id="w", kind="burn_interrupt", params=dict(fraction=0.5, report_success=True))])
    lab = Lab(tmp_path / "combined")
    make_scenario_box(lab, load_scenario(spec(tmp_path, raw)))
    image = tmp_path / "combined.iso"
    image.write_bytes(b"x" * 128 * 2048)
    with lab.locked_state() as st:
        for disc_id in lab.box()["discs"]:
            st.setdefault("burns", {})[disc_id] = dict(closed=True, sessions=[dict(
                start_lba=0, sectors=128, iso=str(image), iso_size=image.stat().st_size)])
    for i, disc_id in enumerate(lab.box()["discs"]):
        with lab.locked_state() as st:
            st["drives"]["X:"]["tray"] = disc_id
        with LabDrive(lab, "X:") as dev:
            assert mmc.parse_capacity(dev.execute(mmc.read_capacity(), 8).data)["last_lba"] == 147
            result = dev.execute(mmc.read10(32, fua=True), 2048)
            assert result.sense == (Sense(3, 0x11, 0) if i else None)
            assert dev._spindle_factor == pytest.approx(1.2)


@pytest.mark.parametrize("media,mid", [("dvd+r", "TEST/R01/001"), ("cd-r", "ATIP 97:25:01"), ("bd-r", "TEST-BD")])
def test_other_media_scenario_readback(tmp_path, media, mid):
    image = tmp_path / "other.iso"
    image.write_bytes(b"q" * 128 * 2048)
    raw = dict(discs=dict(media=media, mid=mid, count=1, capacity=1024, initial_state=dict(state="burned", iso=str(image))),
               faults=[dict(id="r", kind="read_error", params=dict(lba=[32, 64]))])
    lab = Lab(tmp_path / "other")
    make_scenario_box(lab, load_scenario(spec(tmp_path, raw)))
    with lab.locked_state() as st:
        st["drives"]["X:"]["tray"] = lab.box()["discs"][0]
    with LabDrive(lab, "X:") as dev:
        assert dev.mid == mid
        assert dev.execute(mmc.read10(0), 2048).data == b"q" * 2048
        assert dev.execute(mmc.read10(32), 2048).sense == Sense(3, 0x11, 0)
        if media == "cd-r":
            assert dev._atip()[8:11] == bytes([97, 25, 1])


def test_info_oracle_checks_physical_capacity_even_when_readable_count_agrees(tmp_path):
    from disclab.faults import assess

    lab, image = make_lab(tmp_path, "capacity_misreport", {"sectors": 128})
    with LabDrive(lab, "X:") as dev:
        info = dict(capacity=dict(parsed=dict(last_lba=127)),
                    track_1=dict(parsed=dict(track_size=128)),
                    disc_information=dict(raw=dev._disc_information(128).hex()))
    assessed, wrong, observation = assess(lab, lab.box()["discs"][0], "X:", "info",
                                         [(tmp_path / "info.json", info)], image)
    assert assessed and wrong
    assert observation["reported_readable_sectors"] == observation["actual_written_sectors"] == 128
    assert observation["reported_total_sectors"] == 128 and observation["actual_capacity"] == 512


def test_geo_oracle_includes_eccentricity_on_measured_span(tmp_path):
    from disclab.faults import assess
    from disclab.physics import Disc

    lab, image = make_lab(tmp_path)
    answers = lab.answers()
    disc_id = lab.box()["discs"][0]
    truth = answers["discs"][disc_id]
    truth.update(ecc_um=10000, ecc_deg=45, varpitch_deg=[0] * len(truth["varpitch_deg"]))
    answers["readers"]["gh70n"]["completion_mm"]["dvd"] = 0
    answers["readers"]["gh70n"]["head_mm"] = 0
    atomic_json(lab.answers_path, answers)
    disc = Disc(truth)
    # A nominal spiral omitting a deliberate 10 mm eccentricity is inaccurate,
    # even when its u/v and reported capacity agree with the nominal truth.
    span = [float(disc.data_radius(0)), float(disc.data_radius(128 * disc.bps))]
    summary = dict(setup=dict(last_lba=127), fit=dict(u=disc.u, v=disc.v, measured_span_mm=span))
    assessed, wrong, observation = assess(lab, disc_id, "X:", "geo",
                                         [(tmp_path / "summary.json", summary)], image)
    assert assessed and wrong and observation["timing_curve_rms_deg"] > 5


@pytest.mark.parametrize("profile", ["gh70n", "slim-clv"])
def test_spindle_jump_latches_and_preserves_phase_at_each_update(tmp_path, profile):
    lab, _ = make_lab(tmp_path, "spindle_unsteady",
                      dict(mode="jump", amplitude=0.3, time_s=1, lba=32),
                      extra=dict(drive=dict(profile=profile)))
    with LabDrive(lab, "X:") as dev:
        dev.idle(2)
        dev.execute(mmc.read10(64, fua=True), 2048)
        assert dev._spindle_factor == pytest.approx(1.3)
        # A later read below the threshold cannot switch an activated fault off.
        phase, start = dev._phase(dev._clock), dev._clock
        dev._read(start, 0, 1, True)
        assert dev._spindle_factor == pytest.approx(1.3)
        assert dev._phase(start) == pytest.approx(phase)
        if profile == "slim-clv":
            radius = dev.spiral.radius(0)
            assert dev._w == pytest.approx(dev.clv_speed_mm_s / radius * 1.3)


def test_zero_fraction_interruption_and_deleted_iso_do_not_expose_unwritten_data(tmp_path, monkeypatch):
    lab, image = make_lab(tmp_path, "burn_interrupt", dict(fraction=0, report_success=True), initial="blank")
    monkeypatch.setattr("disclab.drive.time.sleep", lambda _: None)
    LabRecorder(lab, "X:", "dvd").write(image, 8, threading.Event(), lambda **kw: None)
    image.unlink()
    with LabDrive(lab, "X:") as dev:
        assert dev._written_sectors() == 0 and not dev.burn["closed"]
        assert dev.execute(mmc.read10(0), 2048).sense == Sense(5, 0x21, 0)


def test_timeout_is_persisted_as_product_crash(tmp_path, monkeypatch):
    from disclab import faults

    lab, _ = make_lab(tmp_path, "read_error", {"lba": [32, 64]})
    monkeypatch.setitem(faults.COMMANDS, "read_error", ("info",))

    def timeout(*args, **kw):
        raise subprocess.TimeoutExpired("virtual info", 120, output=b"partial output", stderr=b"stalled")

    monkeypatch.setattr("disclab.__main__.dp", timeout)
    report = score_faults(lab)
    row, = report["rows"]
    assert row["class"] == "crash" and row["observed"]["timed_out"]
    assert json.loads((lab.root / "scores/faults.json").read_text(encoding="utf-8")) == report
    assert Path(row["evidence_paths"][0]).read_text(encoding="utf-8") == "partial output"
