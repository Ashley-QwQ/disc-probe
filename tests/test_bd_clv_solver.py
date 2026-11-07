"""Blu-ray geometry from the spindle period: the T^2 fit, its anchors, and the CLI path.

A BD-R or BD-RE is read at a constant linear speed, so the angle ladder measures nothing it can
use (see `docs/research/BD_CLV_FEASIBILITY.md`). What stays measurable is the time to turn once:
T = 2*pi*r/v with r^2 = r0^2 + p*L*LBA/pi, so T^2 is a straight line in LBA and its slope and
intercept carry two numbers. One anchor -- a standard pitch, or the linear speed -- turns those
into r0 and pitch; without one only the ratios r0/v and p/v^2 are measured.

Runs with pytest, or on its own: `python tests/test_bd_clv_solver.py`.
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from discprobe import clv                                     # noqa: E402

BD_SECTOR_MM = 2.23945          # 30066.75 channel bits of 74.50 nm
TRUTH = dict(r0_mm=24.02, pitch_um=0.3185, v_m_s=39.336)
ZONES = [497408, 1_500_000, 2_500_000, 3_500_000, 4_974_208, 6_000_000, 8_000_000, 10_000_000]
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "bd_discussion_samples", "local_uj272_bd_zones.csv")


def _samples(r0_mm=TRUTH["r0_mm"], pitch_um=TRUTH["pitch_um"], v_m_s=TRUTH["v_m_s"], zones=ZONES):
    out = []
    for lba in zones:
        r = math.sqrt(r0_mm ** 2 + pitch_um * 1e-3 * BD_SECTOR_MM * lba / math.pi)
        out.append(clv.Sample(lba=lba, period_ms=2000 * math.pi * r / (v_m_s * 1000)))
    return out


# --------------------------------------------------------------- the fit itself

def test_round_trip_with_the_speed_given():
    fit = clv.fit_t2(_samples(), sector_mm=BD_SECTOR_MM, v_m_s=TRUTH["v_m_s"])
    assert abs(fit.r0_mm - TRUTH["r0_mm"]) < 0.002
    assert abs(fit.pitch_um - TRUTH["pitch_um"]) < 0.0005
    assert fit.anchor.startswith("linear speed")


def test_round_trip_with_the_pitch_given():
    fit = clv.fit_t2(_samples(), sector_mm=BD_SECTOR_MM, pitch_um=TRUTH["pitch_um"])
    assert abs(fit.v_m_s - TRUTH["v_m_s"]) < 0.01
    assert abs(fit.r0_mm - TRUTH["r0_mm"]) < 0.002
    assert fit.anchor.startswith("pitch")


def test_without_an_anchor_the_two_ratios_are_what_is_measured():
    free = clv.fit_t2(_samples(), sector_mm=BD_SECTOR_MM).as_dict()
    known = clv.fit_t2(_samples(), sector_mm=BD_SECTOR_MM, v_m_s=TRUTH["v_m_s"]).as_dict()
    assert abs(free["r0_over_v_mm_s"] - known["r0_over_v_mm_s"]) < 1e-6
    assert abs(free["pitch_over_v2_um_s2"] - known["pitch_over_v2_um_s2"]) < 1e-9
    assert "none" in free["anchor"]


def test_a_zone_that_misreads_is_dropped():
    bad = _samples()
    bad[3] = clv.Sample(lba=bad[3].lba, period_ms=bad[3].period_ms * 1.06)
    fit = clv.fit_t2(bad, sector_mm=BD_SECTOR_MM, v_m_s=TRUTH["v_m_s"])
    assert 3 in fit.dropped
    assert abs(fit.r0_mm - TRUTH["r0_mm"]) < 0.002


def test_a_disc_that_is_not_clv_is_refused():
    # Under CAV the period is constant, so T^2 does not rise with LBA at all.
    flat = [clv.Sample(lba=lba, period_ms=20.0) for lba in ZONES]
    try:
        clv.fit_t2(flat, sector_mm=BD_SECTOR_MM, v_m_s=TRUTH["v_m_s"])
    except ValueError as e:
        assert "constant linear speed" in str(e)
    else:
        raise AssertionError("a flat period series should not fit")


# --------------------------------------------------------------- the drive's own answer

def test_classify_rotation_from_get_performance():
    assert clv.classify_rotation({"descriptors": [{"start_kBps": 7193, "end_kBps": 7193}]})["mode"] == "CLV"
    assert clv.classify_rotation({"descriptors": [{"start_kBps": 14752, "end_kBps": 35960}]})["mode"] == "CAV"
    mid = clv.classify_rotation({"descriptors": [{"start_kBps": 10000, "end_kBps": 18000}]})
    assert mid["mode"] not in ("CAV", "CLV")
    assert clv.classify_rotation({})["mode"] == "unknown"


# --------------------------------------------------------------- the recorded runs

def _recorded():
    runs = {}
    with open(FIXTURE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["stopped"] or not row["period_ms"]:
                continue
            runs.setdefault(row["run"], []).append(
                (float(row["linear_m_s"]),
                 clv.Sample(lba=int(row["lba"]), period_ms=float(row["period_ms"]),
                            coherence=float(row["coherence"] or 1))))
    return runs


def test_recorded_runs_fit_as_clv():
    fits, harmonic = [], []
    for run, items in _recorded().items():
        speeds = [v for v, _ in items]
        if max(speeds) > 1.3 * statistics.median(speeds):
            harmonic.append(run)
            continue
        fits.append(clv.fit_t2([s for _, s in items], sector_mm=BD_SECTOR_MM, pitch_um=0.32))
    ok = [f for f in fits if f.r2 >= 0.999 and 23.5 <= f.r0_mm <= 24.5]
    assert len(ok) >= 5, f"only {len(ok)} of {len(fits)} runs fitted"
    assert all(10.2 <= f.v_m_s <= 10.5 for f in ok), [round(f.v_m_s, 3) for f in ok]
    assert len(harmonic) >= 3, "the inner-zone harmonics should be left out"


# --------------------------------------------------------------- the CLI, on the simulator

def test_cli_geo_media_bd_on_the_simulated_drive():
    with tempfile.TemporaryDirectory() as out:
        proc = subprocess.run([sys.executable, "-m", "discprobe", "geo", "--sim", "clv", "--media", "bd",
                               "--linear-mm-s", "39336", "--out", out],
                              cwd=ROOT, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        folders = [d for d in os.listdir(out) if d.startswith("geo-")]
        assert len(folders) == 1, folders
        folder = os.path.join(out, folders[0])
        with open(os.path.join(folder, "summary.json"), encoding="utf-8") as f:
            summary = json.load(f)
        fit = summary["fit"]
        assert fit["model"] == "clv" and fit["media"] == "bd"
        assert fit["anchor"].startswith("linear speed")
        # The simulator's disc is off-nominal on purpose: 24.02 mm and 0.3185 um.
        assert abs(fit["r0_mm"] - 24.02) < 0.01, fit["r0_mm"]
        assert abs(fit["pitch_um"] - 0.3185) < 0.001, fit["pitch_um"]
        assert fit["zones_used"] == 9
        # Both the claim and the measurement are recorded; on a real BD-RE they can disagree.
        assert summary["rotation_measured"]["mode"] == "CLV"
        assert os.path.exists(os.path.join(folder, "zones.csv"))
        assert not os.path.exists(os.path.join(folder, "targets.csv"))


def test_a_disc_the_drive_reads_at_constant_angular_velocity_is_refused():
    """A BD-ROM (or a burned BD the drive reads at CAV) has no T^2 line to fit.

    GET PERFORMANCE type 00h already says so, and the run must stop there: measuring nine zones
    of a CAV disc would only produce a fit that cannot exist, after minutes of spinning.
    """
    with tempfile.TemporaryDirectory() as out:
        proc = subprocess.run([sys.executable, "-m", "discprobe", "geo", "--sim", "cav", "--media", "bd",
                               "--out", out],
                              cwd=ROOT, capture_output=True, text=True, timeout=180)
        text = proc.stdout + proc.stderr
        assert proc.returncode == 1, text
        assert "constant angular velocity" in text, text
        # It times two zones to decide, and must not spend the other seven on a fit that cannot exist.
        assert text.count("Zone 0.") == 2, "it kept measuring after two zones disagreed: " + text
        written = [os.path.join(out, d, name) for d in os.listdir(out)
                   for name in ("summary.json", "zones.csv")
                   if os.path.exists(os.path.join(out, d, name))]
        assert not written, "it wrote results for a disc it cannot fit: " + ", ".join(written)


def test_disexport_writes_a_blu_ray_preset():
    """A CLV run is exported as a Blu-ray preset: inner radius, outer radius and the sector count.

    The preset carries no pitch, because DiscImageStudio solves one constant pitch from those three
    numbers; a pitch in the file would be read as a relative shape coefficient instead.
    """
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        os.makedirs(folder)
        with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"fit": {"media": "bd", "model": "clv", "r0_mm": 24.6427, "pitch_um": 0.32,
                               "v_m_s": 7.9054, "r2": 0.999994, "zones_used": 7,
                               "anchor": "pitch 0.32 um"}}, f)
        out = os.path.join(work, "bd_preset.json")
        proc = subprocess.run([sys.executable, "-m", "discprobe", "disexport", "--geo", folder,
                               "--sectors", "12088320", "--output", out],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
        text = proc.stdout + proc.stderr
        assert proc.returncode == 0, text
        assert "Traceback" not in text, text
        with open(out, encoding="utf-8") as f:
            document = json.load(f)
        parameters = document["parameters"]
        assert parameters["totalSectors"] == 12088320
        assert parameters["innerRadiusMm"] == 24.6427
        assert abs(parameters["outerRadiusMm"] - 58.0117) < 1e-3, parameters
        assert "pitchLinear" not in parameters, parameters
        assert document["luminanceMapping"]["invert"] is False


def _zones(staircase_after: float | None = None):
    sector_mm = clv.NOMINAL["bd"].sector_mm
    out = []
    for fraction in (0.05, 0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85, 0.95):
        lba = int(fraction * 12_000_000)
        radius = math.sqrt(24.66 ** 2 + 0.32e-3 * sector_mm * lba / math.pi)
        omega = 2 * math.pi * 10.34 / radius
        if staircase_after is not None and fraction >= 0.5:
            omega = 2 * math.pi * 10.34 / staircase_after
        out.append(clv.Sample(lba=lba, period_ms=2 * math.pi / omega, coherence=1.0, fraction=fraction))
    return out


def test_a_disc_read_in_zones_is_caught_by_a_break():
    fit = clv.fit_t2(_zones(47.0), sector_mm=clv.NOMINAL["bd"].sector_mm, pitch_um=0.32)
    assert fit.break_fit is not None, "the staircase was fitted as one line"
    assert abs(fit.break_fit["break_lba"] - 6_000_000) <= 1_200_000, fit.break_fit
    assert fit.break_fit["improvement"] > 0.9, fit.break_fit


def test_a_clean_line_reports_no_break_and_says_how_far_it_reached_in():
    fit = clv.fit_t2(_zones(), sector_mm=clv.NOMINAL["bd"].sector_mm, pitch_um=0.32)
    assert fit.break_fit is None, fit.break_fit
    assert abs(fit.r0_mm - 24.66) < 0.05, fit.r0_mm
    assert 1.5 < fit.r0_extrapolated_mm < 3.0, fit.r0_extrapolated_mm


def test_an_offset_the_data_cannot_see_is_left_out():
    import random
    rng = random.Random(5)
    zones = [clv.Sample(lba=s.lba, period_ms=s.period_ms + rng.gauss(0.0, 0.02), coherence=1.0)
             for s in _zones()]
    fit = clv.fit_t2(zones, sector_mm=clv.NOMINAL["bd"].sector_mm, pitch_um=0.32, fit_offset=True)
    assert fit.offset_fitted_ms is not None and fit.sigma_offset_ms is not None
    assert abs(fit.offset_fitted_ms) < 3 * fit.sigma_offset_ms, (fit.offset_fitted_ms, fit.sigma_offset_ms)
    assert fit.offset_ms == 0.0, fit.offset_ms
    plain = clv.fit_t2(zones, sector_mm=clv.NOMINAL["bd"].sector_mm, pitch_um=0.32)
    assert abs(fit.r0_mm - plain.r0_mm) < 0.002, (fit.r0_mm, plain.r0_mm)


def test_an_offset_the_data_can_see_is_taken_out():
    shifted = [clv.Sample(lba=s.lba, period_ms=s.period_ms + 1.0, coherence=1.0) for s in _zones()]
    fit = clv.fit_t2(shifted, sector_mm=clv.NOMINAL["bd"].sector_mm, pitch_um=0.32, fit_offset=True)
    assert abs(fit.offset_ms - 1.0) < 0.01, fit.offset_ms
    assert abs(fit.r0_mm - 24.66) < 0.05, fit.r0_mm


def test_cli_reports_the_rotation_before_measuring():
    with tempfile.TemporaryDirectory() as out:
        proc = subprocess.run([sys.executable, "-m", "discprobe", "timing", "--sim", "clv", "--media", "bd",
                               "--out", out, "--max-minutes", "2"],
                              cwd=ROOT, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "CLV" in proc.stdout


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {name}: {e}")
        else:
            print(f"ok    {name}")
    sys.exit(1 if failures else 0)
