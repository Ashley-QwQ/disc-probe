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
    # The message a reader acts on needs the sector, not the sample index.
    assert fit.as_dict()["zones_dropped_lbas"] == [bad[3].lba]


def test_a_disc_that_is_not_clv_is_refused():
    # Under CAV the period is constant, so T^2 does not rise with LBA at all.
    flat = [clv.Sample(lba=lba, period_ms=20.0) for lba in ZONES]
    try:
        clv.fit_t2(flat, sector_mm=BD_SECTOR_MM, v_m_s=TRUTH["v_m_s"])
    except ValueError as e:
        assert "constant linear speed" in str(e)
    else:
        raise AssertionError("a flat period series should not fit")


def test_the_cross_term_is_in_the_r0_tolerance():
    """Var(r0) = r0^2 [cov_aa/4a^2 + cov_bb/4b^2 - cov_ab/2ab], and the last term is not small.

    Slope and intercept of this fit are strongly anti-correlated: push the line up and it must
    tilt down to keep the far zones where they are. Keeping only the two diagonal terms therefore
    claims a tolerance about a third too tight -- 29.5 um against 41.4 um of true scatter in the
    300-run simulation -- which is why the cross term is carried through `fit_t2`.
    """
    import numpy as np
    jitter = [1.0, -1.3, 0.7, 1.1, -0.9, 0.4, -0.6, 1.5]                 # 2 ppm of period, ~chi2 1
    pts = [clv.Sample(lba=s.lba, period_ms=s.period_ms * (1 + e * 2e-6))
           for s, e in zip(_samples(), jitter)]
    fit = clv.fit_t2(pts, sector_mm=BD_SECTOR_MM, pitch_um=TRUTH["pitch_um"])
    a, b = fit.slope_ms2_per_lba, fit.intercept_ms2
    cov = clv._period_fit(np.array([p.lba for p in pts], float),
                          np.array([p.period_ms for p in pts], float), a, b)[2]
    full = cov[0, 0] / (4 * a * a) + cov[1, 1] / (4 * b * b) - cov[0, 1] / (2 * a * b)
    diagonal = cov[0, 0] / (4 * a * a) + cov[1, 1] / (4 * b * b)
    assert cov[0, 1] < 0, "a rising line through fixed points must have the pair anti-correlated"
    assert full > diagonal, "the cross term has to widen the tolerance, not narrow it"
    assert 1.15 < math.sqrt(full / diagonal) < 1.7, math.sqrt(full / diagonal)
    assert abs(fit.sigma_r0_mm - fit.r0_mm * math.sqrt(full)) < 1e-12, "sigma_r0 must use that formula"


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


def test_a_cav_disc_is_handed_to_the_angular_ladder():
    """A BD-ROM (or a burned BD the drive reads at CAV) has no T^2 line to fit: the period does
    not know the radius. The CLI must notice, time only the two probe zones, and measure the
    spiral from sector addresses instead -- which is the angular ladder, not a CLV fit."""
    with tempfile.TemporaryDirectory() as out:
        proc = subprocess.run([sys.executable, "-m", "discprobe", "geo", "--sim", "cav", "--media", "bd",
                               "--out", out],
                              cwd=ROOT, capture_output=True, text=True, timeout=600)
        text = proc.stdout + proc.stderr
        assert proc.returncode == 0, text[-3000:]
        assert "constant angular velocity" in text, text[-3000:]
        # Three zones get timed before the hand-off: the innermost one, which the drive relocks on
        # after the spindle settle, then the two the rotation verdict reads. A CLV fit would have
        # timed every zone of the ladder (nine by default), so three or fewer says the probe stopped.
        assert text.count("Zone 0.") <= 3, "the probe kept going past the two-zone verdict: " + text[-2000:]
        written = [os.path.join(root, name) for root, _, names in os.walk(out) for name in names
                   if name == "summary.json"]
        assert len(written) == 1, written
        with open(written[0], encoding="utf-8") as f:
            fit = json.load(f)["fit"]
        assert fit["media"] == "bd", fit
        # The simulated disc is 24.02 mm and 0.3185 um on purpose, not the nominal pair.
        assert abs(fit["dis_equivalent"]["inner_radius_mm"] - 24.02) < 0.01, fit["dis_equivalent"]
        assert abs(fit["dis_equivalent"]["pitch_um_estimate"] - 0.3185) < 0.001, fit["dis_equivalent"]

def test_a_random_iso_can_fill_a_blu_ray_layer():
    """A blank Blu-ray has nothing to time, so the path starts by filling one with ordinary data.

    The writer is the DVD one -- Blu-ray also reads 2048-byte sectors -- so the only Blu-ray part
    is the capacity: a request past a single layer is refused before a file is opened.
    """
    with tempfile.TemporaryDirectory() as work:
        out = os.path.join(work, "bd-random.iso")
        proc = subprocess.run([sys.executable, "-m", "discprobe", "random", "--media", "bd",
                               "--sectors", "8192", "--output", out],
                              cwd=ROOT, capture_output=True, text=True, timeout=180)
        text = proc.stdout + proc.stderr
        assert proc.returncode == 0, text
        assert os.path.getsize(out) == 8192 * 2048, os.path.getsize(out)
        with open(out, "rb") as f:
            f.seek(16 * 2048)
            assert f.read(6)[1:] == b"CD001", "the burner needs an ISO 9660 header"
        too_big = os.path.join(work, "no.iso")
        proc = subprocess.run([sys.executable, "-m", "discprobe", "random", "--media", "bd",
                               "--sectors", "20000000", "--output", too_big],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
        text = proc.stdout + proc.stderr
        assert proc.returncode != 0, text
        assert "single-layer Blu-ray" in text, text
        assert "Traceback" not in text, text
        assert not os.path.exists(too_big)


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


def test_the_dial_angle_becomes_a_pitch_in_the_preset():
    """The angle a user can see at the rim is a ppm-scale pitch, and the preset carries it.

    A Blu-ray preset has no pitch field: DiscImageStudio solves one constant pitch from the inner
    radius, the outer radius and the sector count. The timing measured only their product, so the
    pitch the dial implies carries the inner radius with it, and both radii move by a fraction of a
    micron -- which is exactly what a burn needs to close, and what nothing else can measure.
    """
    from discprobe import bdexport
    turns = bdexport.twist_turns(24.05, 58.02, 0.32)
    assert 100_000 < turns < 110_000, turns
    ppm = bdexport.twist_pitch_ppm(24.05, 58.02, 0.32, 126.0)
    assert 11.0 < ppm < 11.5, ppm
    # one hour (30 degrees) is a quarter of the 126, and read nearer the hub the same angle is more
    assert 2.6 < bdexport.twist_pitch_ppm(24.05, 58.02, 0.32, 30.0) < 2.8
    assert bdexport.twist_pitch_ppm(24.05, 58.02, 0.32, 126.0, at_mm=55.0) > ppm


def test_the_calibration_disc_is_a_dial():
    """Three rings and one line: the rings read the radius scale, the line reads the twist."""
    from discprobe import calibdisc
    pic = calibdisc.design()
    assert pic.shape == (calibdisc.SIZE, calibdisc.SIZE)
    assert 0.02 < pic.mean() < 0.08, pic.mean()

    def at(r_mm: float, deg: float) -> bool:
        x = r_mm * math.cos(math.radians(deg))
        y = r_mm * math.sin(math.radians(deg))
        col = int((x + calibdisc.HALF_MM) / calibdisc.CELL_MM)
        row = int((calibdisc.HALF_MM - y) / calibdisc.CELL_MM)
        return bool(pic[row, col])

    for ring in (26.0, 40.0, 55.0):
        assert at(ring, 200.0), ring              # a ring is a whole circle
    assert at(52.0, 90.0)                          # the line, at 12 o'clock, between two rings
    assert not at(52.0, 270.0)                     # and nothing opposite it: the dial has one pointer
    assert not at(52.0, 0.0)                       # nor at 3 o'clock, where only the short tick is
    assert at(46.0, 0.0)                           # the tick, which says which way round the disc is
    assert calibdisc.clock_to_degrees(4.0) == 120.0
    assert calibdisc.clock_to_degrees(1.0) == 30.0


def test_a_blu_ray_sector_is_measured_in_blu_ray_bits():
    """The writer walks the spiral one channel bit at a time, and DVD's 38 688 steps per sector
    walk a Blu-ray 28.7 % too fast: the same 12.2 million sectors then land 6.5 mm too far out,
    every angle in the design smears into the track, and only the circles survive the burn."""
    from discprobe import calib, calibdisc, imagedisc

    assert 2.23 < calib.SECTOR_BITS_BD * 74.5e-6 < 2.25, "a sector is 2.2399 mm of track"
    u, v = calibdisc.geometry()
    bd = imagedisc.sectors_to_radius(u, v, 74.5, 58.0, media="bd")
    dvd = imagedisc.sectors_to_radius(u, v, 74.5, 58.0)
    assert 12.1e6 < bd < 12.3e6, bd
    assert 1.27 < bd / dvd < 1.30, (bd, dvd)


def test_the_calibration_disc_writes_a_burnable_image():
    """A picture on a Blu-ray is ordinary sectors laid out on the spiral with the nominal numbers."""
    with tempfile.TemporaryDirectory() as work:
        out = os.path.join(work, "calib.iso")
        proc = subprocess.run([sys.executable, "-m", "discprobe", "calibdisc", "--sectors", "20000",
                               "--output", out, "--rings", "26,40,55"],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)
        text = proc.stdout + proc.stderr
        assert proc.returncode == 0, text
        assert "Traceback" not in text, text
        assert os.path.getsize(out) == 20000 * 2048
        with open(os.path.join(work, "calib.image.json"), encoding="utf-8") as f:
            spec = json.load(f)
        assert spec["kind"] == "blu-ray-calibration"
        assert spec["r0_mm"] == 24.04 and spec["pitch_um"] == 0.32
        from discprobe import calibdisc
        assert abs(spec["u"] / spec["v"] - calibdisc.geometry()[0] / calibdisc.geometry()[1]) < 1e-6


def test_a_blu_ray_picture_is_masked_with_the_blu_ray_scrambler():
    """The drive XORs a Blu-ray sector with a 16-bit register seeded by the sector number, not with
    DVD's sixteen preset sequences: compensating a picture with the DVD table burns flat noise."""
    from discprobe import bd
    assert bd.seed(0) == (0x100000 >> 5)
    assert len({bd.seed(x) for x in range(96, 128)}) == 1, "32 sectors share one seed"
    assert bd.seed(128) != bd.seed(96), "and the next block does not"
    for lba in (0, 31, 32, 999_999):
        s = bd.seed(lba)
        assert (bd._sequence(0x8000 | (s & 0x7FFF)) == bd.sequence(s)).all()
    with tempfile.TemporaryDirectory() as work:
        from discprobe import calibdisc, imagedisc
        out = os.path.join(work, "pic.iso")
        pic = calibdisc.design(rings=(40.0,))
        u, v = calibdisc.geometry()
        imagedisc.write_iso(out, pic, u, v, 74.5, 4096, log=lambda *a: None, media="bd")
        assert imagedisc.verify_iso(out, pic, u, v, 74.5, 4096, samples=20, media="bd") == []
        # read with the DVD table, every sector differs: the two scramblers really are different
        assert len(imagedisc.verify_iso(out, pic, u, v, 74.5, 4096, samples=4, media="dvd")) == 4


def test_a_picture_texture_keeps_the_servo_its_edges():
    """A picture is recorded as a byte texture, and a flat one burns a disc that will not time.

    The drive scrambles the payload before the 1-7PP modulator, so the texture byte is what the
    channel sees.  00 and FF leave seven gaps with no transition and a digital sum of -8 or +8: a
    long run for the clock recovery to coast through, which is the failure a "pure black" picture
    runs into (L-EC errors, and then `geo` cannot time the disc at all).  A5 and B9 keep six and
    four of the seven gaps changing.
    """
    from discprobe import bd
    dark, light = bd.check_textures("A5", "B9")["dark"], bd.check_textures("A5", "B9")["light"]
    assert dark["gaps_with_a_transition"] == 6 and dark["digital_sum"] == 0, dark
    assert light["gaps_with_a_transition"] == 4 and light["digital_sum"] == 2, light
    for flat in ("00", "FF"):
        try:
            bd.check_textures(flat, "B9")
        except ValueError as e:
            assert "L-EC" in str(e), e
        else:
            raise AssertionError(f"{flat} passed as a picture texture")


def test_the_twist_correction_closes_the_loop_on_the_inner_radius():
    """--twist-deg corrects the pitch and lets the measured shape carry r0 with it."""
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        os.makedirs(folder)
        with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"fit": {"media": "bd", "model": "clv", "r0_mm": 24.6427, "pitch_um": 0.32,
                               "v_m_s": 7.9054, "r2": 0.999994, "zones_used": 7,
                               "anchor": "pitch 0.32 um"}}, f)
        plain = os.path.join(work, "plain.json")
        twisted = os.path.join(work, "twisted.json")
        for out, extra in ((plain, []), (twisted, ["--twist-deg", "126"])):
            proc = subprocess.run([sys.executable, "-m", "discprobe", "disexport", "--geo", folder,
                                   "--sectors", "12088320", "--output", out] + extra,
                                  cwd=ROOT, capture_output=True, text=True, timeout=120)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            assert "Traceback" not in proc.stdout + proc.stderr
        with open(plain, encoding="utf-8") as f:
            before = json.load(f)["parameters"]
        with open(twisted, encoding="utf-8") as f:
            after = json.load(f)["parameters"]
        assert after["totalSectors"] == before["totalSectors"]
        r0_shift_um = 1e3 * (after["innerRadiusMm"] - before["innerRadiusMm"])
        outer_shift_um = 1e3 * (after["outerRadiusMm"] - before["outerRadiusMm"])
        assert 0.11 < r0_shift_um < 0.16, r0_shift_um
        assert 0.30 < outer_shift_um < 0.37, outer_shift_um
        # c = pi r0^2 / (p S) is what the timing measured: r0^2 and p move together.
        eps = (after["innerRadiusMm"] / before["innerRadiusMm"]) ** 2 - 1.0
        assert 1.05e-5 < eps < 1.20e-5, eps


def test_a_twist_angle_does_not_belong_to_a_dvd():
    """The DVD and CD presets already carry a fitted pitch profile, so one angle would be a lie."""
    with tempfile.TemporaryDirectory() as work:
        folder = os.path.join(work, "geo-G-20260101-000000")
        os.makedirs(folder)
        with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"fit": {"media": "cd", "model": "angular", "r0_mm": 25.0}}, f)
        proc = subprocess.run([sys.executable, "-m", "discprobe", "disexport", "--geo", folder,
                               "--sectors", "2295104", "--twist-deg", "126"],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "for Blu-ray" in proc.stderr, proc.stderr
        assert "Traceback" not in proc.stderr, proc.stderr


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


def test_a_dual_layer_disc_is_refused_before_measuring():
    """Two layers read backwards at the break; one line through both describes neither."""
    clv.check_single_layer(12_219_391)                      # the last sector of one layer
    for last in (12_219_392, 24_438_783):
        try:
            clv.check_single_layer(last)
        except ValueError as e:
            assert "dual-layer" in str(e), str(e)
        else:
            raise AssertionError(f"{last} sectors was accepted as one layer")


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
