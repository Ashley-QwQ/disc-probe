"""Self-test: parser checks on hand-built responses, then the full timing run on the
simulated drive, compared against the simulator's true geometry."""

from __future__ import annotations

import math
import sys

from . import analysis, mmc, timing, ui
from .scsi import check_allowed
from .sim import SimDrive

PHASE_SEM_FACTOR = 4.5


class Checker:
    def __init__(self):
        self.failures = 0

    def check(self, cond: bool, what: str):
        print(("  ok    " if cond else "  FAIL  ") + what)
        if not cond:
            self.failures += 1


class Report:
    """At a terminal: results in colour, each section set apart from the rows of ok. Scripts never pass through here."""

    def __init__(self, stream, t):
        self.stream, self.t = stream, t
        self.line = ""
        self.started = False

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def _styled(self, line: str) -> str:
        for head, style in (("  ok    ", "green"), ("  FAIL  ", "red")):
            if line.startswith(head):
                return "  " + self.t.style(head.strip(), style) + head[2 + len(head.strip()):] + line[len(head):]
        if line == "all checks passed":
            return self.t.style(line, "green")
        if line.endswith("check(s) failed"):
            return self.t.style(line, "red")
        if not line or line[0].isspace() or line[0] == "\x1b":
            return line
        first, self.started = not self.started, True
        return ("" if first else "\n") + self.t.style(line, "bold")

    def write(self, text: str) -> int:
        self.line += text
        *whole, self.line = self.line.split("\n")
        for line in whole:
            self.stream.write(self._styled(line) + "\n")
        return len(text)

    def flush(self) -> None:
        if self.line:
            self.stream.write(self.line)
            self.line = ""
        self.stream.flush()


def _report(c: Checker):
    print("results at a terminal")
    import io

    class Colour:
        def style(self, text, name):
            return f"<{name}>{text}</>"
    out = io.StringIO()
    r = Report(out, Colour())
    r.write("parsers\n  ok    one\n  FAIL  two\nnext sec")
    r.write("tion\n  worst 1 deg\n\nall checks passed\n3 check(s) failed\n")
    want = ("<bold>parsers</>\n  <green>ok</>    one\n  <red>FAIL</>  two\n\n<bold>next section</>\n  worst 1 deg\n\n"
            "<green>all checks passed</>\n<red>3 check(s) failed</>\n")
    c.check(out.getvalue() == want, "ok is green, FAIL red, and a section stands apart")


def _parsers(c: Checker):
    print("parsers")
    atip = bytes([0, 26, 0, 0, 0x55, 0x40, 0x80, 0, 97, 26, 66, 0, 79, 59, 74, 0] + [0] * 14)
    a = mmc.parse_atip(atip)
    c.check(a["leadin_start_msf"] == "97:26:66" and a["leadin_start_lba"] == -11634, "ATIP lead-in time")
    c.check(a["last_leadout_start_lba"] == 359849, "ATIP lead-out = CD80 capacity")
    c.check(mmc.msf_to_lba(0, 2, 0) == 0, "MSF 00:02:00 is LBA 0")

    perf = bytes([0, 0, 0, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x2B, 0x48,
                  0, 0x23, 0x05, 0x3F, 0, 0, 0x56, 0x90])
    d = mmc.parse_get_performance(perf, 0x00)["descriptors"][0]
    c.check(d["start_kBps"] == 11080 and d["end_kBps"] == 22160 and d["end_over_start"] == 2.0,
            "GET PERFORMANCE descriptor")

    phys = bytearray(4 + 2048)
    phys[4:8] = bytes([0x25, 0x0F, 0x00, 0x00])
    phys[9:12] = (0x030000).to_bytes(3, "big")
    phys[13:16] = (0x26053F).to_bytes(3, "big")
    p = mmc.parse_dvd_physical(bytes(phys))
    c.check(p["book_type"] == "DVD-R" and p["track_density"] == "0.74 um/track"
            and p["data_start_psn"] == "0x030000" and p["data_end_psn"] == "0x26053F", "DVD physical format")

    pre = bytearray(4 + 40)
    pre[4] = 1
    pre[20], pre[21:27] = 3, b"MCC 03"
    pre[28], pre[29:35] = 4, b"RG20\x00\x00"
    c.check(mmc.parse_dvd_r_prerecorded(bytes(pre)).get("manufacturer_id") == "MCC 03RG20\x00\x00",
            "DVD-R MID from Field IDs 3 and 4")

    for op, name in ((0x2A, "WRITE(10)"), (0xAA, "WRITE(12)"), (0x5B, "CLOSE TRACK"), (0x04, "FORMAT UNIT")):
        try:
            check_allowed(bytes([op] + [0] * 9))
            c.check(False, f"{name} refused")
        except PermissionError:
            c.check(True, f"{name} refused")


def _circ_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _sim_run(c: Checker, mode: str, fua: bool, expect_strategy: str, expect_rotation: str,
             flush: bool = False, sectors: int = 1, reread_ms: float = 0.0):
    print(f"simulated drive: {mode}, FUA {'honoured' if fua else 'ignored'}, "
          f"zero-length flush {'honoured' if flush else 'ignored'}, {sectors}-sector reads"
          + (f", {reread_ms} ms firmware overhead per media read" if reread_ms else ""))
    sim = SimDrive(mode=mode, fua_honoured=fua, flush_honoured=flush, seed=7, reread_delay_ms=reread_ms)
    probe = timing.TimingProbe(sim, log=lambda *_: None, sectors=sectors)
    s = probe.run()
    c.check(s["cache"]["strategy"] == expect_strategy, f"cache strategy {s['cache']['strategy']}")
    rot = s["period"]["rotation"]
    c.check(rot["mode"] == expect_rotation,
            f"rotation {rot['mode']} (period ratio {rot.get('period_ratio_outer_inner')})")
    if mode == "cav":
        for z in s["period"]["zones"]:
            c.check(abs(z["period_ms"] - 6.6) < 0.01, f"zone {z['fraction']}: T {z['period_ms']} ms")
        worst = 0.0
        for t in s["phase"]["targets"]:
            truth = sim.true_phase_deg(t["ref_lba"], t["target_lba"])
            err = _circ_diff(t["phase"]["mean_deg"], truth)
            worst = max(worst, err)
            # Across seeds the errors are unbiased and spread about 1.1-1.2x the reported
            # sem, so the bound scales with it.
            c.check(err < max(PHASE_SEM_FACTOR * t["phase"]["sem_deg"], 1.0),
                    f"target {t['target_fraction']}: measured {t['phase']['mean_deg']:.2f}, "
                    f"true {truth:.2f}, error {err:.2f} deg (sem {t['phase']['sem_deg']})")
        print(f"  worst phase error {worst:.2f} deg")
    return s


def _harmonics(c: Checker):
    print("period estimation")
    period = 0.0071
    import random
    rng = random.Random(3)
    t, times = 0.0, []
    for _ in range(50):
        t += period * rng.randint(3, 17)
        times.append(int((t + rng.gauss(0, 50e-6)) * 1e9))
    fit = analysis.estimate_period(times)
    c.check(fit is not None and abs(fit.period_s - period) < 2e-6,
            f"fundamental found among harmonics: {fit.period_s * 1e3:.5f} ms")
    c.check(fit is not None and 30 < fit.residual_std_s * 1e6 < 80, f"jitter {fit.residual_std_s * 1e6:.1f} us")




def _grid_acceptance(c: Checker):
    print("grid acceptance coverage and deviations")
    import csv
    import importlib.util
    import os
    import tempfile
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, "evidence", "eval_grid.py")
    if not os.path.exists(script):
        print("  (skipped: evidence/ is not part of this copy)")
        return
    spec = importlib.util.spec_from_file_location("eval_grid", script)
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    # The limits were set so that grid 1 fails and grid 2 passes; grid 3 is the registered result. Grid 2's
    # scans have no usable rings at 27-29, 35-37, 45-47 and 49-51 mm, so it can no longer be judged at all.
    for disc, expected in (("grid1", "FAIL"), ("grid2", "INCOMPLETE"), ("grid3", "PASS")):
        scans = sorted(os.path.join(root, "evidence", "gridscan", f) for f in os.listdir(os.path.join(root, "evidence", "gridscan"))
                       if f.startswith(disc + "_scan") and f.endswith(".phi.csv"))
        if scans:
            c.check(ev.evaluate(scans)["status"] == expected, f"{disc} scans: {expected}")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "rings.csv")
        for name in ("outer", "band", "missing", "flat"):
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["radius_mm", "phi_rel_deg", "good"])
                for i in range(300):
                    r = 25.0 + (i + 0.5) / 10
                    phi = 5.0 if name == "outer" and r >= 50 else 2.0 if name == "band" and 40 <= r < 41 else 0.0
                    w.writerow([r, phi, int(name != "missing" or r < 31)])
            result = ev.evaluate([path])
            expected = {"outer": "FAIL", "band": "FAIL", "missing": "INCOMPLETE", "flat": "PASS"}[name]
            c.check(result["status"] == expected, f"{name} grid: {result['status']}")

def _pitch_fit(c: Checker):
    print("pitch model numerical fit")
    import importlib.util
    import os
    import numpy as np
    spec = importlib.util.spec_from_file_location(
        "geo_polyfit", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "geo_polyfit.py"))
    polyfit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(polyfit)
    fit, model = polyfit.fit, polyfit.model
    u, v, rc, rs = 180000.0, 5.5, 300000.0, 112000.0
    n = np.linspace(2e8, 8e9, 29)
    y = model(n, u, v, [0.0, 0.0004], rc, rs)[0]
    s = np.full(len(n), math.radians(0.3))
    f = fit(n, y, s, u, v, 2, rc, rs)
    predicted = model(n, f["u"], f["v"], f["b"], rc, rs)[0]
    delta = np.degrees(predicted - y)
    c.check(np.ptp(delta) < 0.01, f"quadratic pitch prediction error {np.ptp(delta):.6f} deg")
    c.check(math.isfinite(f["span_sigma_deg"]) and f["span_sigma_deg"] > 0,
            "quadratic span uncertainty includes fitted pitch parameters")



def _zone_conflict(c: Checker):
    print("rotation zone consistency")
    probe = timing.TimingProbe(SimDrive(), log=lambda *_: None)
    zones = [dict(fraction=f, period_ms=t, coherence=1.0, nominal_radius_mm=r)
             for f, t, r in ((0.1, 20, 25), (0.5, 30, 40), (0.9, 20, 55))]
    c.check(probe._classify(zones)["mode"] != "CAV", "middle zone period conflict is not CAV")
    zones[1].pop("period_ms")
    c.check(probe._classify(zones)["mode"] == "unknown", "missing middle zone is unknown")
    zones[1]["period_ms"] = 20
    zones[1]["coherence"] = 0.1
    c.check(probe._classify(zones)["mode"] == "unknown", "incoherent middle zone is unknown")
    _whole_turn_zone(c, probe)


def _zone_from_times(fraction, lba, times):
    zone = {"fraction": fraction, "lba": lba, "nominal_radius_mm": round(timing.NOMINAL["dvd"].radius(lba), 3)}
    zone.update(analysis.estimate_period(times).summary())
    return zone


def _whole_turn_zone(c: Checker, probe):
    """A zone completing only every k turns is CAV at the shorter period; a real speed change is not."""
    import json
    import os
    import random
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evidence", "drive",
                        "gh70n_three_turn_zone.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            real = json.load(f)["zones"]
        times = [z["t_end_ns"] for z in real]
        zones = [_zone_from_times(z["fraction"], z["lba"], t) for z, t in zip(real, times)]
        c.check(probe._classify(zones)["mode"].startswith("mixed"), "GH70N three-turn zone alone looks mixed")
        probe._resolve_multiples(zones, times)
        inner = zones[0]
        c.check(probe._classify(zones)["mode"] == "CAV" and inner.get("completes_every_turns") == 3
                and abs(inner["period_ms"] - zones[1]["period_ms"]) < 0.02,
                f"GH70N three-turn zone resolved: T {inner['period_ms']} ms, every {inner.get('completes_every_turns')} turns")
    else:
        print("  (skipped the GH70N record: evidence/ is not part of this copy)")
    rnd = random.Random(4)

    def completions(period_ms, step=1):
        n, out = 0, []
        for _ in range(60):
            n += step * rnd.randint(1, 4)
            out.append(round((n * period_ms + rnd.gauss(0, 0.02)) * 1e6))
        return out
    # CLV whose outer zone happens to turn at exactly half the inner speed: the middle zone still differs.
    times = [completions(20.0), completions(30.0), completions(40.0)]
    zones = [_zone_from_times(f, lba, t)
             for f, lba, t in zip((0.05, 0.5, 0.95), (107248, 1072560, 2037888), times)]
    probe._resolve_multiples(zones, times)
    c.check(probe._classify(zones)["mode"] != "CAV", "a speed change landing on a whole multiple is not CAV")

def _timer_tick(c: Checker):
    print("timer tick diagnosis")
    for strategy in ("plain", "evict"):
        for period in (15.625, 7.8125, 15.625 / 3, 10.0):
            logs = []
            probe = timing.TimingProbe(SimDrive(), log=logs.append)
            probe.strategy = strategy
            probe.summary = {"period": {}}
            probe._check_period([{"period_ms": period}])
            c.check(bool(logs) == (period != 10.0), f"{strategy} period {period:.4f} ms")


def _ladder_safe_unwrap(c: Checker):
    print("ladder safe unwrapping")
    import numpy as np
    from types import SimpleNamespace
    from .geo import Ladder
    from .calib import theta
    class PhaseOracle(Ladder):
        # Only replace the instrument. Selection, unwrapping and fitting are production code.
        def __init__(self, seed=3, sigma=1.0, readable=None):
            super().__init__(None, max_targets=22, log=lambda *_: None, state_check=False)
            self.tp = SimpleNamespace(
                setup=lambda: None, cache_test=lambda: None, strategy="fua",
                last_lba=2295103, summary={}, audio=False)
            self.rng = np.random.default_rng(seed)
            self.sigma = sigma
            self.truth_u, self.truth_v = 23.93 / .0001336, .000735 / .0001336
            self.readable, self.failed, self.pred_sigmas = readable, [], []
    
        def check_rotation(self):
            pass

        def _random_parts(self, ranges):    # all random data
            return ranges

        def settle(self, *args, **kwargs):
            self.T = .02
            return self.T
    
        def _measure_retry(self, lba):
            if self.readable and not any(a <= lba <= b for a, b in self.readable):
                self.failed.append(lba)
                return None
            n = self._n_end(lba)
            phase = math.degrees(theta(n, self.truth_u, self.truth_v)
                                 - theta(self.n_ref, self.truth_u, self.truth_v))
            self.pred_sigmas.append(self._sigma_pred_deg(n))
            return dict(lba=lba, n=n,
                        phase_deg=(phase + self.rng.normal(0, self.sigma)) % 360,
                        sigma_deg=self.sigma, std_deg=self.sigma * math.sqrt(24),
                        used=24, period_ms=20.0)
    
    ladder = PhaseOracle()
    try:
        ladder.run()
    except RuntimeError as exc:
        c.check("ambiguous" in str(exc), "unsafe DVD rung stops before committing a whole turn")
    else:
        errors = [abs(t["unwrapped_deg"] - math.degrees(theta(t["n"], ladder.truth_u, ladder.truth_v)
                  - theta(ladder.n_ref, ladder.truth_u, ladder.truth_v)) - math.degrees(ladder.c))
                  for t in ladder.targets]
        c.check(max(ladder.pred_sigmas[2:]) < 25 and max(errors) < 180,
                "bridged DVD rungs stay safe and on the correct whole-turn branch")
    partial = PhaseOracle(seed=0, sigma=0.2, readable=[(850000, 1200000)])
    fit = partial.run()
    c.check(fit["completion_status"] == "candidates_exhausted" and bool(fit["failed_candidates"]),
            "exhausted candidates are recorded as partial")


def _ladder(c: Checker):
    print("ladder geometry measurement on the simulated drive (35 ms re-read overhead)")
    import numpy as np
    from .calib import SECTOR_BITS, theta
    from .geo import Ladder
    # The ladder's own accuracy, with the reads of the end-of-run state check left out (they only change
    # which random draws the rungs get; checked separately below).
    sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0)
    lad = Ladder(sim, speed_kbs=None, reps=16, max_targets=14, log=lambda *_: None, state_check=False)
    res = lad.run()
    b = 133.6e-6  # the simulator's off-nominal geometry
    n = np.linspace(0, 0.85 * sim.capacity * SECTOR_BITS, 400)
    e = np.degrees(theta(n, lad.u, lad.v) - theta(n, 23.93 / b, 0.735e-3 / b))
    span = float(e.max() - e.min())
    from .geo import _dtheta
    g_end = np.subtract(_dtheta((sim.capacity // 16) * 16 * SECTOR_BITS, lad.u, lad.v), _dtheta(0.0, lad.u, lad.v))
    full = float(np.degrees(np.sqrt(g_end @ lad.cov[:2, :2] @ g_end)))
    c.check(abs(res["angle_sigma_full_disc_deg"] - full) < 1e-9 * max(1.0, full),
            f"the full-disc sigma counts DVD sectors in DVD channel bits ({res['angle_sigma_full_disc_deg']:.4f} deg)")
    c.check(span < 1.5, f"{len(lad.targets)} rungs, angle error over 0-85 % of the disc {span:.3f} deg "
                        f"(reported 1 sigma {res['angle_sigma_measured_span_deg']:.3f}, "
                        f"chi2/dof {res['chi2_per_dof']:.2f})")
    # Check points read at the start and again at the end: a drive that changes state partway through
    # (a latency that grows with radius) bends the geometry while chi2 stays where it was.
    verdicts = []
    for kw in ({}, {"state_change_after_reads": 500, "state_us_per_mm": 1.0}):
        sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0, jitter_us=8.0, outlier_rate=0.0, **kw)
        run = Ladder(sim, speed_kbs=None, reps=16, max_targets=14, log=lambda *_: None).run()
        verdicts.append((run["state_check"]["verdict"], run["chi2_per_dof"]))
    c.check([v for v, _ in verdicts] == ["steady", "changed"],
            f"check points: a steady drive reads as {verdicts[0][0]}, one that changes partway as {verdicts[1][0]} "
            f"(chi2/dof {verdicts[0][1]:.2f} and {verdicts[1][1]:.2f}, so the fit alone can't tell)")
    sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0)
    whole = Ladder(sim, speed_kbs=None, reps=16, max_targets=14, log=lambda *_: None, sectors=16, state_check=False)
    whole.run()
    e = np.degrees(theta(n, whole.u, whole.v) - theta(n, lad.u, lad.v))
    span = float(e.max() - e.min())
    c.check(span < 1.5, f"reading whole ECC blocks gives the same geometry: {span:.3f} deg apart over 0-85 % of the disc")
    # A one-disc trial disc: texture rings between random ones, then a picture appended outside them.
    from .rings import RingLayout
    layout = RingLayout(textures=("A5", "RND", "B9", "RND", "66", "RND", "64", "RND", "E4", "RND", "92", "RND"),
                        groups=2, ring_width_mm=1.04, start_mm=25.0, filler="RND").build()
    patterns = [(r["lba_start"], r["lba_end"], int(r["texture"], 16)) for r in layout.rings if r["texture"] != "RND"]
    patterns.append((layout.total_sectors, sim.capacity, 0xB9))
    sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0, patterns=patterns)
    rings = Ladder(sim, speed_kbs=None, reps=16, max_targets=14, log=lambda *_: None)
    rings.run()
    on_pattern = [t["lba"] for t in rings.targets if any(a <= t["lba"] < b for a, b, _ in patterns)]
    outside = [(a, b) for a, b in rings.auto_ranges or [] if any(a < e and s < b for s, e, _ in patterns)]
    c.check(len(rings.auto_ranges or []) == 12 and not on_pattern and not outside,
            f"texture-ring disc: {len(rings.auto_ranges or [])} random stretches found, "
            f"{len(on_pattern)} rungs and {len(outside)} stretches on a pattern")
    # Measured only out to 50 mm, so judge it there, as the plain run is judged over its range.
    measured = np.linspace(min(t["n"] for t in rings.targets), max(t["n"] for t in rings.targets), 300)
    e = np.degrees(theta(measured, rings.u, rings.v) - theta(measured, 23.93 / b, 0.735e-3 / b))
    c.check(float(e.max() - e.min()) < 1.5, f"angle error over the measured span {float(e.max() - e.min()):.3f} deg")
    plain = Ladder(SimDrive(mode="cav", seed=7, patterns=[(500000, 520000, 0xA5)]), speed_kbs=None, log=lambda *_: None)
    plain.tp.setup()
    found = plain._random_parts([(68000, 1950000)])
    c.check(len(found) == 2 and found[0][1] <= 500000 - 2900 and found[1][0] >= 520000 + 2900,
            f"one 0.5 mm picture band splits the range in two: {found}")


def _ladder_cd_audio(c: Checker):
    print("ladder on a simulated CD-DA track (DiscImageStudio picture burn, drive read offset -603 bytes)")
    from . import cd
    from .geo import Ladder
    from .timing import NoReadableDisc, TimingProbe
    b = cd.BIT_NM * 1e-6
    ri, pitch, x = 24.911653, 1.4926e-3, -603.0   # a banana CD-R, read on a PLDS DU-8A5LH
    u, v = ri / b, pitch / b

    def sim(**kw):
        return SimDrive(mode="cav", seed=7, reread_delay_ms=35.0, media="cd", cd_audio=True, cd_u=u, cd_v=v,
                        cd_read_offset_bytes=x, **kw)

    def run(offset, **kw):
        lad = Ladder(sim(**kw), media="cd", speed_kbs=None, reps=16, max_targets=24, host_delay_ms=35.0,
                     read_offset_bytes=offset, log=lambda *_: None)
        return lad, lad.run()

    lad, res = run(x)
    sectors = res["sectors"]
    dis = res["dis_equivalent"]
    ro = b * math.sqrt(u * u + v * sectors * cd.SECTOR_BITS / math.pi)
    d_ri, d_ro = (dis["inner_radius_mm"] - ri) * 1e6, (dis["outer_radius_mm"] - ro) * 1e6
    c.check(res["track"] == "audio" and lad.tp.strategy == "far" and abs(d_ri) < 50 and abs(d_ro) < 50,
            f"{len(lad.targets)} rungs with far reads: ri {d_ri:+.0f} nm, ro {d_ro:+.0f} nm from the truth "
            f"(chi2/dof {res['chi2_per_dof']:.2f})")
    # Timing cannot see the offset: left at 0, the same reads fit a spiral shifted along the track by
    # 603 bytes, i.e. u^2 + v d / pi with d = 603 * 24.5 channel bits (theta(n + d)).
    _, res0 = run(0.0)
    want = (math.sqrt(u * u - v * x * cd.SECTOR_BITS / cd.RAW_BYTES / math.pi) - u) * b * 1e6
    got = (res0["dis_equivalent"]["inner_radius_mm"] - ri) * 1e6
    c.check(abs(got - want) < 50, f"read offset left at 0 moves ri by {got:+.0f} nm (expected {want:+.0f} nm)")
    lad6, res6 = run(x, cache_blocks=6)
    d6 = (res6["dis_equivalent"]["inner_radius_mm"] - ri) * 1e6
    c.check(lad6.tp.strategy == "far" and lad6.tp.far_count == 2 and abs(d6) < 50,
            f"a cache that keeps the target past one far read: {lad6.tp.far_count} far reads, ri {d6:+.0f} nm")
    big = TimingProbe(sim(cache_blocks=40), log=lambda *_: None, media="cd", cd_audio=True, reps=8)
    big.setup()
    big.cache_test()
    c.check(big.strategy == "evict", f"a cache that even four far reads leave in place falls back to {big.strategy}")
    try:
        TimingProbe(sim(), log=lambda *_: None, media="cd").setup()
        refused = False
    except NoReadableDisc:
        refused = True
    c.check(refused, "timing --media cd still refuses an audio track (only geo reads one)")
    data = Ladder(SimDrive(mode="cav", seed=7, media="cd"), media="cd", speed_kbs=None, read_offset_bytes=-603,
                  log=lambda *_: None)
    try:
        data.run()
        refused = False
    except RuntimeError as e:
        refused = "--read-offset-bytes" in str(e)
    c.check(refused, "--read-offset-bytes is refused on a data CD")
    _audio_fit_uses(c, res, x)


def _audio_fit_uses(c: Checker, res: dict, x: float):
    import contextlib
    import io
    import json
    import os
    import tempfile
    from argparse import Namespace
    from . import guide, i18n
    from .__main__ import _refuse_audio_fit, cmd_disexport, cmd_image, cmd_tiles
    from .disexport import export
    dis = res["dis_equivalent"]
    with tempfile.TemporaryDirectory() as d:
        geo, out = os.path.join(d, "summary.json"), os.path.join(d, "preset.json")
        with open(geo, "w", encoding="utf-8") as fh:
            json.dump({"fit": res}, fh)
        span = res["measured_span_mm"]
        e = export(geo, res["sectors"], None, out, span[0], span[1], "t", "t")
        d_ri = (e["preset"]["innerRadiusMm"] - dis["inner_radius_mm"]) * 1e6
        d_ro = (e["preset"]["outerRadiusMm"] - dis["outer_radius_mm"]) * 1e6
        c.check(abs(d_ri) < 50 and abs(d_ro) < 50, f"the preset from an audio fit is dis_equivalent: ri {d_ri:+.0f} nm, ro {d_ro:+.0f} nm")
        c.check("along-track" not in e["preset"]["description"] and e["source"]["read_offset_bytes"] == x, "and names the read offset, no along-track constant")
        try:
            export(geo, res["sectors"], None, out, span[0], span[1], "t", "t", along_track_frames=206)
            refused = False
        except ValueError as err:
            refused = "--read-offset-bytes" in str(err)
        c.check(refused, "disexport --along-track-frames is refused on an audio fit")
        try:
            export(geo, res["sectors"] // 2, None, out, span[0], span[1], "t", "t")
            refused = False
        except ValueError:
            refused = True
        c.check(refused, "--sectors far too small for the span is refused with a reason")
        told = io.StringIO()
        with contextlib.redirect_stdout(told):
            cmd_disexport(Namespace(geo=geo, media="cd", sectors=res["sectors"], correction=None, output=out, r_min=None,
                                    r_max=None, id=None, name=None, along_track_frames=0, install=False,
                                    dis_presets=None, replace=False))
        said = told.getvalue()
        c.check("no along-track constant is needed" in said and "may come out" not in said and "--along-track-frames" not in said,
                "disexport on an audio fit does not warn about the along-track constant")
        for cmd, name in ((cmd_image, "image"), (cmd_tiles, "tiles")):
            try:
                cmd(Namespace(geo=geo, media="cd"))
                refused = False
            except SystemExit as err:
                refused = "audio track" in str(err.code) or err.code == 1
            c.check(refused, f"{name} --media cd refuses an audio fit")
        data = {k: v for k, v in res.items() if k != "track"}
        _refuse_audio_fit(data)     # returns: a data CD fit carries on
        args = Namespace(media="cd", read_offset_bytes=x, speed=None, drive="E:", out=d)
        run = os.path.join(d, "geo-E-20260101-100000")
        lines = guide.after_geo(args, {**res, "chi2_per_dof": 1.0, "angle_sigma_measured_span_deg": 0.1}, run)
        text = "\n".join(lines)
        c.check("disexport" in text and "one more constant" not in text and " image --media cd --geo" not in text,
                "geo on an audio track points at the preset, not at a picture ISO")
        noisy = guide.after_geo(args, {**res, "chi2_per_dof": 1.0, "angle_sigma_measured_span_deg": 0.5}, run)
        c.check(any("geo" in s and "--read-offset-bytes -603" in s for s in noisy), "a retry keeps the read offset")
    try:
        i18n.use("zh")
        c.check(all(i18n.tr(s) != s for s in lines if "disexport" not in s and "Enter the same" not in s and "--sectors is" not in s and s.strip()),
                "that advice has Chinese")
    finally:
        i18n.use("en")


def _geo_rotation(c: Checker):
    print("geo checks the spindle before it starts")
    from .geo import Ladder, looks_clv
    from . import __main__ as cli
    from . import guide
    from argparse import Namespace
    c.check(looks_clv(2.122, 2.128) and not looks_clv(1.0, 2.115), "CLV's period follows the radius, a constant speed's doesn't")
    c.check(not looks_clv(2.0, 2.115) and not looks_clv(1 / 3, 2.115), "a period read as whole turns isn't taken for CLV")
    c.check(not looks_clv(2.0, 2.02), "and where the radii are about 2 to 1 it can't tell, so it carries on")
    clv = Ladder(SimDrive(mode="clv", seed=7), speed_kbs=5540, reps=8, max_targets=6, log=lambda *_: None)
    try:
        clv.run()
        reason = ""
    except RuntimeError as e:
        reason = str(e)
    c.check("not turning at a constant speed" in reason and not clv.targets, f"CLV stops before any rung: {reason[:70]}")
    told = guide.after_geo_stop(Namespace(speed=5540, drive="E:", media="dvd"), reason)
    c.check(any("--speed keep" in x for x in told) and any("put it back" in x for x in told), "and says to reload and keep the speed")
    alone = guide.after_geo_stop(Namespace(speed=None, drive="E:", media="dvd"), reason)
    c.check(not any("--speed keep" in x for x in alone) and any("Another drive" in x for x in alone), "if it was left alone already, it doesn't suggest that again")
    narrow = Ladder(SimDrive(mode="clv", seed=7), speed_kbs=5540, reps=8, ranges=[(1000000, 1100000)], log=lambda *_: None)
    narrow.tp.setup()
    narrow.ranges = narrow.ranges_arg
    narrow.check_rotation()
    c.check("rotation_check" not in narrow.tp.summary, "a span too narrow to tell isn't judged")
    cav = Ladder(SimDrive(mode="cav", seed=7), speed_kbs=None, reps=8, max_targets=6, log=lambda *_: None)
    res = cav.run()
    c.check(cav.tp.summary["rotation_check"]["ratio"] < 1.01 and res is not None, "constant rotation carries on")
    c.check("set_cd_speed" not in cav.tp.summary, "--speed keep sends no speed command")
    c.check(cli._speed("keep") is None and cli._speed("KEEP") is None and cli._speed("5540") == 5540, "keep is understood")
    set_one = Ladder(SimDrive(mode="cav", seed=7), speed_kbs=5540, reps=8, max_targets=4, log=lambda *_: None)
    set_one.run()
    c.check(set_one.tp.summary["set_cd_speed"]["requested_kBps"] == 5540, "the default still sets 4x")


def _correction_run(c: Checker):
    print("a correction from another geo run")
    import contextlib
    import importlib.util
    import io
    import json
    import os
    import numpy as np
    import tempfile
    from argparse import Namespace
    from . import __main__ as cli
    from . import imagedisc as I
    tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "geo_polyfit.py")
    spec = importlib.util.spec_from_file_location("geo_polyfit", tool)
    polyfit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(polyfit)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "correction.json")
        geo = os.path.join(d, "geo-E-20261107-133324", "summary.json")

        def older(source):
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"source": source, "radius_valid_mm": [25, 54], "poly_in_x": [0.0]}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            polyfit.write_phi_correction(path, np.linspace(26, 54, 8), np.zeros(8), 2, "results/geo-E-20261107-133324", {"u": 180000.0, "v": 5.5})
        c.check(I.correction_other_run(path, 180000.0, 5.5, geo) is None, "the run it was made from passes")
        c.check(I.correction_other_run(path, 180001.0, 5.5, geo) == "geo-E-20261107-133324", "any other run is named")
        older("tools/geo_polyfit.py results\\geo-E-20261107-133324\\")
        c.check(I.correction_other_run(path, 1.0, 1.0, geo) is None and I.correction_from_timing(path), "an older file is judged by its folder: the same one passes")
        older("tools/geo_polyfit.py results/geo-E-20260101-000000")
        c.check(I.correction_other_run(path, 1.0, 1.0, geo) == "geo-E-20260101-000000", "and another is named")
        older("tools/geo_polyfit.py .")
        c.check(I.correction_other_run(path, 1.0, 1.0, geo) is None, "a folder name that says nothing is no reason to warn")
        older(["a_phi.csv"])
        c.check(I.correction_other_run(path, 1.0, 1.0, geo) is None and not I.correction_from_timing(path), "a grid-scan correction isn't checked")
        older("tools/geo_polyfit.py results/geo-E-20260101-000000")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._warn_other_run(Namespace(correction=path, geo=geo), {"u": 1.0, "v": 1.0})
        c.check("another geo run" in out.getvalue() and "--write-correction" in out.getvalue(), "the warning says how to make it again")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._warn_other_run(Namespace(correction=os.path.join(d, "missing.json"), geo=geo), {"u": 1.0, "v": 1.0})
            cli._warn_other_run(Namespace(correction=None, geo=geo), {"u": 1.0, "v": 1.0})
        c.check(out.getvalue() == "", "no file or a missing one says nothing here")
        # A grid burned with that timing correction, scanned: the new file is the timing one plus the scan's wave.
        from .gridscan import fit_correction
        with contextlib.redirect_stdout(io.StringIO()):
            polyfit.write_phi_correction(path, np.linspace(26, 54, 8), 0.3 * ((np.linspace(26, 54, 8) - 40) / 15) ** 2,
                                         2, "results/geo-E-20261107-133324", {"u": 180000.0, "v": 5.5})
        phi = os.path.join(d, "phi.csv")
        r = np.arange(25.5, 55.5, 0.1)
        wave = 0.07 * np.sin(2 * np.pi * r / 10)
        with open(phi, "w", encoding="utf-8") as f:
            f.write("radius_mm,phi_rel_deg,peak_strength,good\n" + "".join(f"{a:.2f},{b:.4f},5,1\n" for a, b in zip(r, wave)))
        stacked = os.path.join(d, "stacked.json")
        out = fit_correction([phi], stacked, degree=12, base=path)
        fit_correction([phi], os.path.join(d, "scan.json"), degree=12)
        alone = I.load_correction(os.path.join(d, "scan.json"))
        grid = np.linspace(27, 54, 50)
        both = I.load_correction(stacked)(grid) - I.load_correction(path)(grid) - alone(grid)
        # The base is held constant outside its own range, so the sum has corners one polynomial only approximates.
        c.check(np.ptp(both) < 0.02 and out["base_fit_error_deg"] < 0.02,
                f"--base adds the scans to the burned correction ({np.ptp(both):.4f} deg off)")
        c.check(I.correction_other_run(stacked, 180001.0, 5.5, geo) == "geo-E-20261107-133324",
                "and still names the geo run that correction belongs to")
        # A grid-scan correction keeps the u, v of the geometry its grid was burned with, and is checked
        # against the run it is used with (the 6pro audit of 1f7f92e: an old one was added silently).
        os.makedirs(os.path.dirname(geo), exist_ok=True)
        with open(geo, "w", encoding="utf-8") as f:
            json.dump({"fit": {"u": 180000.0, "v": 5.5}}, f)
        scanned = os.path.join(d, "scanned.json")
        fit_correction([phi], scanned, degree=4, geometry=geo)
        c.check(I.correction_other_run(scanned, 180000.0, 5.5, geo) is None, "a scan correction passes with its own geometry")
        c.check(I.correction_other_run(scanned, 180001.0, 5.5, geo) == "geo-E-20261107-133324",
                "and names the run its grid was burned with when used with another")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._warn_other_run(Namespace(correction=scanned, geo=geo), {"u": 180001.0, "v": 5.5})
        c.check("grid burned with another geo run" in out.getvalue(), "the warning says the scans belong to another run")
        bare = os.path.join(d, "bare.json")
        fit_correction([phi], bare, degree=4)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._warn_other_run(Namespace(correction=bare, geo=geo), {"u": 180001.0, "v": 5.5})
        c.check("could not be checked" in out.getvalue(), "one that records no geometry says it could not be checked")
        # A merge of runs whose check points moved keeps that verdict, so `disexport` still refuses it.
        from . import guide
        runs = []
        for k, verdict in enumerate(("changed", "steady")):
            run = os.path.join(d, f"geo-E-2026010{k + 1}-000000")
            os.makedirs(run)
            fit = {"u": 180000.0, "v": 5.5, "bit_nm_assumed": 133.3, "state_check": {"verdict": verdict}}
            with open(os.path.join(run, "summary.json"), "w", encoding="utf-8") as f:
                json.dump({"fit": fit, "setup": {"last_lba": 2295103}}, f)
            runs.append((run, fit))
        data = [(np.linspace(1e9, 6e10, 10), None, None, fit) for _, fit in runs]
        joint = {"u": 180000.0, "v": 5.5, "cov": np.eye(2) * 1e-6, "c": [0.0, 0.0], "chi2": 1.0, "dof": 10, "rms_deg": 0.1}
        merged = polyfit.merged_summary(data, [run for run, _ in runs], joint)
        c.check(merged["fit"]["state_check"]["verdict"] == "changed" and runs[0][0] in merged["fit"]["state_check"]["runs"]
                and guide.drive_changed(merged["fit"]), "a merge keeps a source run's moved check points")


def _install_details(c: Checker):
    print("preset install: the details")
    import contextlib
    import io
    import json
    import os
    import tempfile
    from argparse import Namespace
    from . import __main__ as cli
    from . import cd, disinstall, guide
    dvd = {"totalSectors": 1008, "sectors": 9999, "usableSectors": 1984}
    c.check(disinstall._drop_unusable_fields(dvd, False) == ["sectors", "usableSectors"] and dvd == {"totalSectors": 1008}, "a leftover sectors on a DVD preset doesn't set its total")
    fine = {"totalSectors": 1008, "sectors": 16, "usableSectors": 992}
    c.check(disinstall._drop_unusable_fields(fine, False) == ["sectors"] and fine["usableSectors"] == 992, "and doesn't cost a usableSectors that fits")
    c.check(guide._quality_number({"x": float("nan")}, "x") is None and guide._quality_number({"x": float("inf")}, "x") is None and guide._quality_number({"x": 0.5}, "x") == 0.5, "a quality figure of NaN or infinity counts as missing")
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            b = cd.BIT_NM * 1e-6
            folder = "geo-test-20260101-000000"
            os.mkdir(folder)
            summary = os.path.join(folder, "summary.json")
            with open(summary, "w", encoding="utf-8") as f:
                json.dump({"fit": {"u": 25.14 / b, "v": 1.4969e-3 / b, "bit_nm_assumed": cd.BIT_NM, "media": "cd", "measured_span_mm": [26.7, 54.4],
                                   "chi2_per_dof": 1.0, "angle_sigma_measured_span_deg": 0.1}}, f)
            with open(os.path.join(folder, "targets.csv"), "w", encoding="utf-8") as f:
                f.write("header\n" + "row\n" * 22)
            with open("dis_preset.json", "w", encoding="utf-8") as f:
                f.write("mine")

            def export(**kw):
                args = dict(geo=summary, sectors=359602, correction=None, output=None, r_min=None, r_max=None, id=None, name=None,
                            along_track_frames=0, media=None, install=False, dis_presets=None, replace=False)
                with contextlib.redirect_stdout(io.StringIO()):
                    cli.cmd_disexport(Namespace(**{**args, **kw}))
            export(install=True, dis_presets="presets.json")
            with open("dis_preset.json", encoding="utf-8") as f:
                kept = f.read()
            c.check(kept == "mine" and os.path.exists("presets.json"), "--install alone leaves a dis_preset.json in the folder as it was")
            export()
            with open("dis_preset.json", encoding="utf-8") as f:
                c.check("preset" in json.load(f), "without --install the default file is written as before")
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(["geo", "--sim", "cav", "--seed", "5", "--max-targets", "8", "--out", "sim"])
            run = os.path.join("sim", os.listdir("sim")[0])
            with open(os.path.join(run, "summary.json"), encoding="utf-8") as f:
                c.check(json.load(f).get("simulated") is True, "a simulated geo says so in its summary")
            os.rename(run, "geo-E-20260101-000000")
            c.check(guide.Result("geo-E-20260101-000000", "geo", "E", "20260101-000000").simulated, "so a renamed folder still counts as simulated")
            blocker = guide.install_blocker(os.path.join("geo-E-20260101-000000", "summary.json"))
            c.check(blocker is not None and "simulated" in blocker, "and can't be installed")
        finally:
            os.chdir(here)


def _incomplete_folder(c: Checker):
    print("a folder with files missing")
    import os
    import shutil
    import subprocess
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": ""}
    with tempfile.TemporaryDirectory() as d:
        # The packaged Python takes modules only from its fixed path, never the current folder, so there the
        # child would run the whole copy instead. It once ran `selftest`, which ran this again, thousands deep.
        first = subprocess.run([sys.executable, "-c", "import sys; print(sys.path[0])"], cwd=d, capture_output=True,
                               encoding="utf-8", env=env).stdout.strip()
        if first not in ("", d):
            print("  (skipped: this Python doesn't look in the current folder for modules)")
            return
        folder = os.path.join(d, "discprobe")
        os.mkdir(folder)
        for name in ("__main__.py", "guide.py", "mmc.py"):     # as in a real half-deleted copy: no __init__.py, no i18n.py
            shutil.copy(os.path.join(here, name), folder)
        # The check runs on import, before any command, and --help can't start anything if it isn't reached.
        got = subprocess.run([sys.executable, "-m", "discprobe", "--help"], cwd=d, capture_output=True, encoding="utf-8",
                             env=env)
    c.check(got.returncode == 1 and "incomplete" in got.stderr and "Traceback" not in got.stderr, "it says the files are incomplete, not a traceback")


def _cdprobe(c: Checker):
    print("cdprobe: DiscImageStudio project and probe pattern for a CD probe disc")
    import json
    import os
    import struct
    import tempfile
    import zlib
    from . import cdprobe
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "probe.discproj")
        res = cdprobe.write(path, 359849, size=512)
        doc = json.load(open(path, encoding="utf-8"))
        # Every field DiscImageStudio v1.4.0-v1.4.2 has for a CD/DVD project (it rejects unknown ones).
        shape = {"schemaVersion", "name", "discFamily", "geometry", "layers", "outputs", "calibrationSessionPath",
                 "thumbnailPngBase64", "createdUtc", "modifiedUtc", "tone", "bluRay"}
        sub = {"geometry": {"innerRadiusMm", "outerRadiusMm", "sectors", "pitchLinear", "pitchQuadratic", "pitchCubic"},
               "outputs": {"outputPath", "writeCue", "dataDirectory", "volumeLabel", "interleave"},
               "tone": {"ditherStrength", "levels", "brightness", "srgbLinearization"}}
        layer = {"id", "name", "imagePath", "visible", "translateXMm", "translateYMm", "rotationDeg", "scale"}
        g, ly = doc["geometry"], doc["layers"][0]
        c.check(set(doc) == shape and all(set(doc[k]) == v for k, v in sub.items()) and len(doc["layers"]) == 1
                and set(ly) == layer and doc["discFamily"] == "cd" and doc["schemaVersion"] == 2,
                "the project has exactly DiscImageStudio's CD project fields")
        pitch = cdprobe.pitch_um(g["innerRadiusMm"], g["outerRadiusMm"], g["sectors"])
        c.check(g["sectors"] == 359849 and g["innerRadiusMm"] == 24.92 and abs(pitch - 1.4865) < 1e-9
                and g["pitchLinear"] == g["pitchQuadratic"] == g["pitchCubic"] == 0
                and ly["scale"] == 1 and ly["rotationDeg"] == 0 and ly["translateXMm"] == ly["translateYMm"] == 0
                and ly["imagePath"].endswith("probe.png") and doc["outputs"]["outputPath"].endswith("probe.wav")
                and doc["tone"]["levels"] == 2 and doc["outputs"]["interleave"] is True,
                f"generic burn values: ri 24.92 mm, ro {g['outerRadiusMm']:.4f} mm, pitch {pitch:.4f} um, "
                f"one layer at 100 %")
        data = open(res["pattern"], "rb").read()
        chunks, k = {}, 8
        while k < len(data):
            n, t = struct.unpack(">I4s", data[k:k + 8])
            chunks.setdefault(t, []).append(data[k + 8:k + 8 + n])
            k += 12 + n
        w, h, depth, colour = struct.unpack(">IIBB", chunks[b"IHDR"][0][:10])
        key, _, text = chunks[b"tEXt"][0].partition(b"\x00")
        feat = json.loads(text)
        c.check(data[:8] == b"\x89PNG\r\n\x1a\n" and (w, h, depth, colour) == (512, 512, 8, 0)
                and key.decode() == cdprobe.TEXT_KEY and feat["band"] == [g["innerRadiusMm"], g["outerRadiusMm"]]
                and len(feat["spokes"]) == 12 and "gauge" in feat,
                "the pattern is a 512 px greyscale PNG carrying its features for the project's band")
        raw = zlib.decompress(b"".join(chunks[b"IDAT"]))
        mmpx = 2 * feat["span_mm"] / w

        def pixel(r, deg):     # image frame: x right, y down, angle clockwise on screen
            x, y = r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg))
            i, j = round(x / mmpx + w / 2 - 0.5), round(y / mmpx + h / 2 - 0.5)
            return raw[j * (w + 1) + 1 + i]
        c.check(pixel(42.5, 0) == 0 and pixel(42.5, 15) == 255 and pixel(42.5, 165) == 0 and pixel(42.5, 180) == 255,
                "spoke 0 is black on white; from 105 to 285 deg the band is inverted (background black, spoke 180 white)")
        refused = []
        for kwargs in (dict(sectors=500), dict(sectors=359849, radii=(40.0, 42.0))):
            try:
                cdprobe.write(os.path.join(d, "bad.discproj"), size=64, **kwargs)
            except ValueError:
                refused.append(True)
        try:
            cdprobe.write(path, 359849, size=64)
        except FileExistsError:
            refused.append(True)
        c.check(len(refused) == 3, "a bad sector count, non-CD radii and an existing project are refused")


def _unreadable(c: Checker):
    print("timing stops early on unreadable discs and non-CAV drives")
    from .scsi import ScsiResult, Sense
    from .timing import NoReadableDisc, TimingProbe

    class Bad:
        """Every read fails like a picture disc on a GP65NB60: 3/11/00 after 7.5 s."""
        def __init__(self, fail_first_only=False):
            self.sim, self.reads, self.only_first = SimDrive(mode="cav", seed=7), 0, fail_first_only

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            if cdb[0] in (0x28, 0xA8):
                self.reads += 1
                if not self.only_first or self.reads == 1:
                    return ScsiResult(2, b"", Sense(3, 0x11, 0), 0, int(7.5e9))
            return self.sim.execute(cdb, data_len, direction, timeout_s)

        def __getattr__(self, name):
            return getattr(self.sim, name)

    bad = Bad()
    try:
        TimingProbe(bad, log=lambda *_: None).run()
        c.check(False, "an unreadable disc was not detected")
    except NoReadableDisc as e:
        c.check("random-data" in str(e) and bad.reads <= 12, f"unreadable disc stopped after {bad.reads} reads")
    one = Bad(fail_first_only=True)
    probe = TimingProbe(one, log=lambda *_: None, reps=4, period_reads=20, targets=(0.5,))
    probe.setup()
    c.check(probe.method == "read12", "one medium error does not switch the read command to READ(10)")

    class SlowLink:
        """A cache hit costs 8 ms over this link, as on an SDRW-08D2S-U."""
        def __init__(self):
            self.sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0)

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            res = self.sim.execute(cdb, data_len, direction, timeout_s)
            if cdb[0] in (0x28, 0xA8) and res.t_end_ns - res.t_start_ns < 3_000_000:
                res.t_end_ns = res.t_start_ns + 8_000_000
            return res

        def __getattr__(self, name):
            return getattr(self.sim, name)

    slow = TimingProbe(SlowLink(), log=lambda *_: None)
    slow.setup()
    slow.cache_test()
    c.check(slow.strategy == "fua", f"slow cache hits are still recognised as cached (strategy {slow.strategy})")
    clv = TimingProbe(SimDrive(mode="clv", seed=7), log=lambda *_: None, reps=4, targets=(0.5,), stop_if_not_cav=True)
    s = clv.run()
    c.check("phase" not in s and s["period"]["rotation"]["mode"] == "CLV", "a CLV drive stops before the phase test")
    zone = lambda frac, period, coh, r: {"fraction": frac, "period_ms": period, "coherence": coh, "nominal_radius_mm": r}
    clear = [zone(0.05, 25.0, 0.99, 26.0), zone(0.5, 25.0, 0.99, 42.0), zone(0.95, 25.0, 0.99, 57.0)]
    drifting = [zone(0.05, 25.0, 0.3, 26.0), zone(0.5, 25.0, 0.99, 42.0), zone(0.95, 25.0, 0.99, 57.0)]
    c.check(clv._classify(clear)["mode"] == "CAV" and clv._classify(drifting)["mode"] == "unknown",
            "a zone with no clear period gives unknown, not CAV from the other two")


def _ladder_abort(c: Checker):
    print("ladder stops on a wrong whole-turn count")
    from .geo import Ladder

    class OffByOneTurn(Ladder):
        def _add(self, m, predicted_deg):
            if len(self.targets) == 5:      # sixth rung: pretend the prediction picked the wrong turn
                predicted_deg += 360.0
            super()._add(m, predicted_deg)

    sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0)
    lad = OffByOneTurn(sim, speed_kbs=None, reps=16, max_targets=10, log=lambda *_: None)
    try:
        lad.run()
        c.check(False, "a one-turn error was not detected")
    except RuntimeError as e:
        c.check("whole-turn" in str(e), f"stopped after {len(lad.targets)} rungs: {str(e)[:60]}...")


def _disexport(c: Checker):
    print("DiscImageStudio preset export")
    from .disexport import fit_preset
    u, v = 24.06 / 133.3e-6, 0.7453e-3 / 133.3e-6
    f = fit_preset(u, v, 133.3, 2298496, 25.8, 54.4)
    c.check(f["max_angle_diff_deg"] < 0.005 and max(abs(f["pitchLinear"]), abs(f["pitchQuadratic"]), abs(f["pitchCubic"])) < 1e-7
            and abs(f["innerRadiusMm"] - 24.06) < 1e-5,
            f"constant-pitch map exports with ~zero cubic terms, max angle difference {f['max_angle_diff_deg']:.4f} deg")
    f = fit_preset(u, v, 133.3, 2298496, 25.8, 54.4, lambda r: 0.7 * (((r - 40.0) / 14.0) ** 2 - 0.5) * 2)
    c.check(f["full_angle_diff_deg"] >= f["outside_angle_diff_deg"] >= 0, "full-capacity conversion difference is reported")
    c.check(f["max_angle_diff_deg"] < 0.05 and max(abs(f["pitchLinear"]), abs(f["pitchQuadratic"]), abs(f["pitchCubic"])) > 1e-6,
            f"an angle correction reaches the exported pitch terms, max angle difference {f['max_angle_diff_deg']:.4f} deg")
    import json
    import os
    import tempfile
    from . import cd
    from .disexport import export
    r0, p, sectors = 25.14, 1.4969e-3, 359602
    u, v = r0 / (cd.BIT_NM * 1e-6), p / (cd.BIT_NM * 1e-6)
    with tempfile.TemporaryDirectory() as d:
        geo, out = os.path.join(d, "summary.json"), os.path.join(d, "preset.json")
        with open(geo, "w", encoding="utf-8") as fh:
            json.dump({"fit": {"u": u, "v": v, "bit_nm_assumed": cd.BIT_NM, "media": "cd"}}, fh)
        e = export(geo, sectors, None, out, 26.7, 54.4, "t", "t")
        q = e["preset"]
        # DiscImageStudio's constant-pitch CD formula: p = pi (ro^2 - ri^2) / (1200 mm/s * sectors / 75)
        dis_p = math.pi * (q["outerRadiusMm"] ** 2 - q["innerRadiusMm"] ** 2) / (q["linearVelocityMmPerSecond"] * sectors / 75)
        c.check(abs(dis_p - p) < 1e-9 and q["sectors"] == sectors and "totalSectors" not in q
                and e["fit"]["max_angle_diff_deg"] < 0.005,
                f"CD fit exports as a CD preset, outer {q['outerRadiusMm']:.3f} mm, pitch {dis_p * 1e3:.5f} um by the DIS formula")
        shifted = export(geo, sectors, None, out, 26.7, 54.4, "t", "t", along_track_frames=206)["preset"]
        frames = (u * u - (shifted["innerRadiusMm"] / (cd.BIT_NM * 1e-6)) ** 2) * math.pi / v / cd.FRAME_BITS
        c.check(abs(frames - 206) < 1, f"along-track constant reaches the CD preset ({frames:.1f} of 206 frames)")
        os.remove(out)
        with open(geo, "w", encoding="utf-8") as fh:
            json.dump({"fit": {"u": u, "v": v, "bit_nm_assumed": 133.3}}, fh)   # sector length does not match the fit
        try:
            export(geo, sectors, None, out, 26.7, 54.4, "t", "t")
            refused = False
        except ValueError:
            refused = not os.path.exists(out)
        c.check(refused, "a preset that misses the measured map is refused and not written")


def _disinstall(c: Checker):
    print("DiscImageStudio preset install")
    import glob
    import json
    import os
    import tempfile
    from . import disinstall

    def backups(path):
        return sorted(glob.glob(path + ".*.bak"))

    preset = {"id": "t-cd", "displayName": "T", "description": "test", "sectors": 359602,
              "innerRadiusMm": 25.14, "outerRadiusMm": 54.4, "linearVelocityMmPerSecond": 1200,
              "pitchLinear": 1e-8, "pitchQuadratic": -2e-8, "pitchCubic": 1e-8}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "presets", "disc-presets.json")
        r = disinstall.install(preset, path)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        c.check(r["action"] == "added" and doc["schemaVersion"] == 4 and doc["cdPresets"] == [preset]
                and doc["bluRayPresets"] == [], "install creates the user preset file and adds the preset")
        with open(path, "rb") as f:
            before = f.read()
        r = disinstall.install(preset, path)
        with open(path, "rb") as f:
            after = f.read()
        c.check(r["action"] == "unchanged" and after == before and not backups(path),
                "installing the same preset again changes nothing")
        changed = {**preset, "description": "other"}
        try:
            disinstall.install(changed, path)
            refused = False
        except disinstall.InstallError:
            refused = True
        c.check(refused, "a same-id preset with different values is refused")
        r = disinstall.install(changed, path, replace=True)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        c.check(r["action"] == "replaced" and doc["cdPresets"][0]["description"] == "other",
                "--replace overwrites the existing preset")
        first = backups(path)
        c.check(len(first) == 1, "the file is backed up before it is rewritten")
        r = disinstall.install({**preset, "description": "third"}, path, replace=True)
        second = backups(path)
        c.check(len(second) == 2 and first[0] in second,
                "a second install adds a backup instead of overwriting the first")
        with open(first[0], encoding="utf-8") as f:
            c.check(json.load(f)["cdPresets"][0]["description"] == "test",
                    "the first backup still holds the file as it was before any install")

        # A file the install leaves alone keeps its comments, so nothing was lost to report.
        commented = os.path.join(d, "commented", "disc-presets.json")
        os.makedirs(os.path.dirname(commented))
        with open(commented, "w", encoding="utf-8") as f:
            f.write('{\n  // same preset, with a comment\n  "schemaVersion": 4,\n  "cdPresets": [\n    '
                    + json.dumps(preset) + ',\n  ],\n  "dvdPresets": [],\n  "bluRayPresets": [],\n'
                    '  "disabledCdPresetIds": [],\n  "disabledDvdPresetIds": [],\n'
                    '  "disabledBluRayPresetIds": []\n}\n')
        with open(commented, "rb") as f:
            before = f.read()
        r = disinstall.install(preset, commented)
        with open(commented, "rb") as f:
            after = f.read()
        c.check(r["action"] == "unchanged" and r["dropped"] == [] and after == before,
                "a file that is not rewritten does not report lost comments")

        # A field DiscImageStudio's newer schema has and this tool does not write.
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        doc["cdPresets"][0]["usableSectors"] = 330000
        doc["cdPresets"][0]["description"] = "test"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        r = disinstall.install(preset, path)
        c.check(r["action"] == "unchanged", "an extra field the tool does not write does not make a preset differ")
        r = disinstall.install({**preset, "description": "fourth"}, path, replace=True)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        c.check(doc["cdPresets"][0]["usableSectors"] == 330000 and r["kept"] == ["usableSectors"],
                "--replace keeps a field this tool does not write")

        # A usable sector count the merged preset cannot hold: DiscImageStudio refuses the whole
        # file over it, so it is dropped and said out loud rather than kept.
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        doc["cdPresets"][0]["usableSectors"] = 400000
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        r = disinstall.install({**preset, "description": "fifth"}, path, replace=True)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        c.check(r["dropped_fields"] == ["usableSectors"] and "usableSectors" not in doc["cdPresets"][0]
                and r["kept"] == [], "a usableSectors the new total cannot hold is dropped, not written")
        drop = disinstall._drop_unusable_fields
        c.check(drop({"sectors": 1008, "usableSectors": 1984}) == ["usableSectors"],
                "1984 usable sectors against 1008 total is dropped")
        c.check(drop({"totalSectors": 1000, "usableSectors": 1001}) == ["usableSectors"],
                "a usableSectors above the total is dropped")
        c.check(drop({"totalSectors": 1008, "usableSectors": 990}) == ["usableSectors"],
                "a DVD usableSectors that is not a multiple of 16 is dropped")
        c.check(drop({"sectors": 1008, "usableSectors": 1008}) == [], "a usableSectors that fits is kept")

        with open(path, "w", encoding="utf-8") as f:
            f.write('{\n  // schema 3\n  "schemaVersion": 3,\n  /* no Blu-ray list yet */\n  "cdPresets": [\n'
                    + json.dumps(preset) + ',\n  ],\n  "dvdPresets": [],\n'
                    '  "disabledCdPresetIds": ["t-cd"]\n}\n')
        r = disinstall.install(preset, path)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        c.check(r["action"] == "enabled" and r["upgraded"] and doc["schemaVersion"] == 4
                and doc["bluRayPresets"] == [] and doc["disabledCdPresetIds"] == [],
                "comments are read, schema 3 is upgraded, and a disabled id is enabled")
        c.check(r["dropped"] == ["comments", "trailing commas"],
                "the install reports the comments and trailing commas the rewrite did not keep")

        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"schemaVersion": 4, "cdPresets": []}) + "\n/* unterminated\n")
        with open(path, "rb") as f:
            before = f.read()
        try:
            disinstall.install(preset, path)
            bad = False
        except disinstall.InstallError as e:
            bad = "no closing */" in str(e)
        with open(path, "rb") as f:
            after = f.read()
        c.check(bad and after == before, "an unterminated /* comment is refused and the file is left alone")

        try:
            disinstall.refuse_same_file(path, path)
            bad = False
        except disinstall.InstallError as e:
            bad = "same file" in str(e)
        c.check(bad, "--output and --dis-presets on one file are refused")
        missing = os.path.join(d, "not", "there.json")
        try:
            disinstall.refuse_same_file(missing, os.path.join(d, "not", ".", "there.json"))
            bad = False
        except disinstall.InstallError:
            bad = True
        c.check(bad, "two names for a file that does not exist yet are compared as paths")

        dvd = {"id": "t-dvd", "displayName": "T", "description": "test", "totalSectors": 2295104,
               "innerRadiusMm": 24.0, "outerRadiusMm": 58.0, "channelBitLengthNm": 133.3,
               "pitchLinear": 0.0, "pitchQuadratic": 0.0, "pitchCubic": 0.0}
        r = disinstall.install(dvd, os.path.join(d, "other", "disc-presets.json"))
        with open(r["path"], encoding="utf-8") as f:
            doc = json.load(f)
        c.check(r["action"] == "added" and doc["dvdPresets"] == [dvd], "a DVD preset goes into dvdPresets")
        try:
            disinstall.install({**preset, "pitchLinear": -2.0}, path)
            bad = False
        except disinstall.InstallError:
            bad = True
        c.check(bad, "a pitch that goes negative is refused")


def _install_blocker(c: Checker):
    print("Refusing presets from results nobody should trust")
    import json
    import os
    import tempfile
    from . import guide

    def result(root, tag, summary, rungs=12):
        folder = os.path.join(root, f"geo-{tag}-20260101-000000")
        os.makedirs(folder)
        with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f)
        with open(os.path.join(folder, "targets.csv"), "w", encoding="utf-8") as f:
            f.write("lba,n_bits\n" + "".join(f"{1000 + 100 * i},{i}\n" for i in range(rungs)))
        return os.path.join(folder, "summary.json")

    fit = {"u": 90000.0, "v": 5.7, "chi2_per_dof": 1.2, "angle_sigma_measured_span_deg": 0.2}
    good = {"fit": fit, "stopped": None}
    with tempfile.TemporaryDirectory() as root:
        c.check(guide.install_blocker(result(root, "SIM-cav-cda", good)) is not None,
                "a simulated run is refused")
        c.check("simulated" in guide.install_blocker(result(root, "SIM-cav-cda-1", good)),
                "and the reason says it was simulated")
        stopped = guide.install_blocker(result(root, "G", {**good, "stopped": "could not measure the reference"}))
        c.check(stopped is not None and "stopped" in stopped, "a run that stopped before the fit is refused")
        c.check(guide.install_blocker(result(root, "G-1", {"stopped": None})) is not None,
                "a run with no geometry fit is refused")
        c.check(guide.install_blocker(result(root, "G-2", good, rungs=3)) is not None,
                "a run with too few points is refused")
        c.check(guide.install_blocker(result(root, "G-3", {"fit": {**fit, "chi2_per_dof": 40.0}})) is not None,
                "a run whose fit leaves a large chi2 is refused")
        c.check(guide.install_blocker(result(root, "G-4", {"fit": {**fit, "angle_sigma_measured_span_deg": 1.5}}))
                is not None, "a run too noisy to rely on is refused")
        c.check(guide.install_blocker(result(root, "G-5", good)) is None,
                "a complete, quiet run of a real disc is installed")
        audio = {"fit": {**fit, "track": "audio"}, "stopped": None}
        c.check(guide.install_blocker(result(root, "G-6", audio)) is None,
                "a CD-DA result is allowed: it is what the audio path of DiscImageStudio is for")
        # The source is not in the summary yet, so a renamed folder is caught by the field once
        # geo writes one; until then the folder name is the only signal.
        sim = guide.install_blocker(result(root, "G-7", {**good, "simulated": True}))
        c.check(sim is not None and "summary says so" in sim,
                "a summary that records a simulated drive is refused even in a renamed folder")
        plain = result(root, "G-8", good)
        c.check(guide.install_warning(plain) is None, "a summary with both quality figures needs no warning")
        thin = result(root, "G-9", {"fit": {k: v for k, v in fit.items()
                                            if k not in ("chi2_per_dof", "angle_sigma_measured_span_deg")}})
        warning = guide.install_warning(thin)
        c.check(guide.install_blocker(thin) is None and warning is not None
                and "no chi2_per_dof" in warning,
                "a summary without quality figures installs, and says which check did not run")
        c.check(guide.install_blocker(result(root, "G-10", {"fit": {**fit, "chi2_per_dof": None}})) is None,
                "a chi2 of None is not read as zero, so the run is not refused for it")


def _bd_clv(c: Checker):
    print("Blu-ray CLV geometry: periods against LBA")
    import json
    import math
    import os
    from . import clv

    # Round trip on data built from a known disc: the fit has to give it back.
    truth_r0, truth_pitch, truth_v = 24.02, 0.3185, 39.336
    sector_mm = clv.NOMINAL["bd"].sector_mm
    samples = []
    for lba in [497408, 1_500_000, 2_500_000, 3_500_000, 4_974_208, 6_000_000, 8_000_000, 10_000_000]:
        r = math.sqrt(truth_r0 ** 2 + truth_pitch * 1e-3 * sector_mm * lba / math.pi)
        samples.append(clv.Sample(lba=lba, period_ms=2000 * math.pi * r / (truth_v * 1000)))
    by_speed = clv.fit_t2(samples, sector_mm=sector_mm, v_m_s=truth_v)
    c.check(abs(by_speed.r0_mm - truth_r0) < 0.002 and abs(by_speed.pitch_um - truth_pitch) < 0.0005,
            f"with the linear speed given, r0 {by_speed.r0_mm:.4f} mm and pitch {by_speed.pitch_um:.4f} um "
            f"come back (truth {truth_r0} mm, {truth_pitch} um)")
    by_pitch = clv.fit_t2(samples, sector_mm=sector_mm, pitch_um=truth_pitch)
    c.check(abs(by_pitch.v_m_s - truth_v) < 0.01 and abs(by_pitch.r0_mm - truth_r0) < 0.002,
            f"with the pitch given, the speed {by_pitch.v_m_s:.3f} m/s comes back (truth {truth_v})")
    free, speed_d = clv.fit_t2(samples, sector_mm=sector_mm), by_speed.as_dict()
    c.check(abs(free.as_dict()["pitch_over_v2_um_s2"] - speed_d["pitch_over_v2_um_s2"]) < 1e-9
            and abs(free.as_dict()["r0_over_v_mm_s"] - speed_d["r0_over_v_mm_s"]) < 1e-6,
            "with neither anchor the two ratios are still measured, and the fit says what stayed unknown")
    outlier = list(samples)
    outlier[3] = clv.Sample(lba=samples[3].lba, period_ms=samples[3].period_ms * 1.06)
    caught = clv.fit_t2(outlier, sector_mm=sector_mm, v_m_s=truth_v)
    c.check(3 in caught.dropped and abs(caught.r0_mm - truth_r0) < 0.002,
            "one zone timed 6% long is dropped and the rest still fit")

    # The drive's own answer, before any timing: GET PERFORMANCE type 00h.
    cav = {"descriptors": [{"start_kBps": 14752, "end_kBps": 35960}]}
    clv_perf = {"descriptors": [{"start_kBps": 7193, "end_kBps": 7193}]}
    mid = {"descriptors": [{"start_kBps": 10000, "end_kBps": 18000}]}
    c.check(clv.classify_rotation(clv_perf)["mode"] == "CLV", "a flat performance ratio reads as CLV")
    c.check(clv.classify_rotation(cav)["mode"] == "CAV", "58/24 on a BD reads as CAV")
    c.check(clv.classify_rotation(mid)["mode"] not in ("CAV", "CLV"), "a ratio in between is neither, and is not fitted")
    c.check(clv.classify_rotation({})["mode"] == "unknown", "a drive that reports nothing is not guessed at")

    # The 39 zones this drive left in the repository: a real regression set.
    import statistics
    path = os.path.join(os.path.dirname(__file__), "..", "tests", "data", "bd_discussion_samples",
                        "local_uj272_bd_zones.csv")
    if not os.path.exists(path):
        c.check(False, "the recorded BD zone set is in the tree")
        return
    runs = {}
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            run, profile, req, frac, lba, radius, period, rpm, v, coh, jitter, method, block, last, stopped = \
                line.rstrip("\n").split(",")
            if stopped or not period:
                continue
            runs.setdefault(run, []).append((float(v), clv.Sample(lba=int(lba), period_ms=float(period),
                                                                  coherence=float(coh or 1))))
    clean, harmonic = [], []
    for run, items in runs.items():
        speeds = [v for v, _ in items]
        if max(speeds) > 1.3 * statistics.median(speeds):
            harmonic.append(run)     # the inner zone turned at twice the outer rate: not a CLV fit
            continue
        try:
            clean.append(clv.fit_t2([s for _, s in items], sector_mm=sector_mm, pitch_um=0.32))
        except ValueError:
            pass
    ok = [f for f in clean if f.r2 >= 0.999 and 23.5 <= f.r0_mm <= 24.5]
    if not ok:
        c.check(False, "no recorded run fit as CLV")
        return
    c.check(len(ok) >= 5 and all(10.2 <= f.v_m_s <= 10.5 for f in ok),
            f"{len(ok)} of {len(runs)} recorded runs fit as a straight line in T^2 with r0 "
            f"{min(f.r0_mm for f in ok):.3f}-{max(f.r0_mm for f in ok):.3f} mm at 10.2-10.5 m/s")
    c.check(len(harmonic) >= 3,
            f"the {len(harmonic)} runs whose inner zone turned at twice the outer rate are left out")
    # What the line says about itself: how far inside the first zone the answer sits, and whether one
    # line describes the periods at all (a drive reading in zones holds one angular speed per zone,
    # so its periods step instead of rising smoothly).
    fit = ok[0]
    c.check(fit.r_first_mm is not None and 0.5 < fit.r0_extrapolated_mm < 3.0,
            f"the first zone sits {fit.r0_extrapolated_mm:.2f} mm outside r0, which the fit reports")
    c.check(fit.break_fit is None, "a clean CLV run shows no break in its periods")
    sector_mm = clv.NOMINAL["bd"].sector_mm

    def periods(constant_omega_after: float | None = None):
        out = []
        for fraction in (0.05, 0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85, 0.95):
            lba = int(fraction * 12_000_000)
            radius = math.sqrt(24.66 ** 2 + 0.32e-3 * sector_mm * lba / math.pi)
            # radius in mm over a speed in m/s is a period in ms, so omega is v/r in rad/ms and
            # the turn is 2*pi/omega: the same numbers a real zone reports, not 2*pi times smaller.
            omega = 10.34 / (radius if constant_omega_after is None or fraction < 0.5 else constant_omega_after)
            out.append(clv.Sample(lba=lba, period_ms=2 * math.pi / omega, coherence=1.0))
        return out

    # The tolerance has to mean something: a nine-zone simulation whose truth is known should
    # scatter by about what the fit says it will. Twenty minutes of noise on a 15 ms turn.
    import random
    rng = random.Random(11)
    strayed, told = [], []
    for _ in range(120):
        noisy = [clv.Sample(lba=s.lba, period_ms=s.period_ms + rng.gauss(0.0, 0.02), coherence=1.0)
                 for s in periods()]
        try:
            fit_n = clv.fit_t2(noisy, sector_mm=sector_mm, pitch_um=0.32)
        except ValueError:
            continue
        strayed.append(fit_n.r0_mm - 24.66)
        told.append(fit_n.sigma_r0_mm)
    scatter = (sum(d * d for d in strayed) / len(strayed)) ** 0.5 * 1000
    claimed = sum(told) / len(told) * 1000
    c.check(0.6 <= claimed / scatter <= 1.5,
            f"the tolerance tracks the scatter it is meant to describe: {claimed:.0f} um claimed "
            f"against {scatter:.0f} um seen over {len(strayed)} simulations")

    stepped = clv.fit_t2(periods(47.0), sector_mm=sector_mm, pitch_um=0.32)
    c.check(stepped.break_fit is not None and abs(stepped.break_fit["break_lba"] - 6_000_000) <= 1_200_000
            and stepped.break_fit["improvement"] > 0.9,
            "a disc read in zones is caught: the periods break between two lines instead of one")


def _tests_folder(c: Checker):
    """The files in tests/, which nothing runs by hand: run them here so every check sees them."""
    print("tests/: the files nobody runs, run here")
    import glob
    import importlib.util
    import os
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")
    files = sorted(glob.glob(os.path.join(folder, "test_*.py")))
    if not files:
        c.check(True, "no tests/ folder beside the package, so there is nothing to run")
        return
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(f"discprobe_tests_{name}", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:                                       # noqa: BLE001 - a test runner
            c.check(False, f"{name} imports ({type(e).__name__}: {e})")
            continue
        checks = [(n, f) for n, f in sorted(vars(module).items()) if n.startswith("test_") and callable(f)]
        failed = []
        for n, fn in checks:
            try:
                fn()
            except Exception as e:                                   # noqa: BLE001 - a test runner
                failed.append(f"{n}: {type(e).__name__}: {e}")
        c.check(bool(checks), f"{name} has checks to run")
        c.check(not failed, f"{name} passes ({len(checks)} checks)" +
                (" -- " + "; ".join(failed[:3]) if failed else ""))


def _bd_export(c: Checker):
    print("Blu-ray preset: three numbers DiscImageStudio turns back into a spiral")
    import json
    import os
    import tempfile
    from . import bdexport

    fit = {"model": "clv", "media": "bd", "r0_mm": 24.6427, "pitch_um": 0.32, "v_m_s": 7.9054,
           "r2": 0.999994, "zones_used": 7, "anchor": "pitch 0.32 um", "pitch_um_anchor": 0.32}
    params = bdexport.parameters(fit, 12_088_320)
    c.check(abs(params["outerRadiusMm"] - 58.0117) < 1e-3,
            "outer radius follows from inner, pitch and sectors")
    c.check("pitchLinear" not in params and "channelBitLengthNm" not in params,
            "no pitch coefficient: DiscImageStudio reads those as a shape, not as a pitch")
    c.check(params["usableSectors"] == 12_088_320 - 1024,
            "a preset leaves room for the lead-out, so a full project does not overburn")
    # 24.0 -> 58.0 over a full layer is the standard 0.320 um pitch, so the constants agree with each other.
    length = bdexport.track_length_mm(bdexport.BD_SECTORS_PER_LAYER)
    implied = (58.0 ** 2 - 24.0 ** 2) * 3.141592653589793 / length * 1e3
    c.check(abs(implied - bdexport.BD_NOMINAL_PITCH_UM) < 2e-4,
            f"the standard radii and pitch close their own identity ({implied:.5f} um)")
    try:
        bdexport.check(12_088_321, 24.6, 58.0)
    except bdexport.BdPresetError:
        c.check(True, "a sector count that is not a multiple of 32 is refused")
    else:
        c.check(False, "a sector count that is not a multiple of 32 is refused")
    try:
        bdexport.parameters({"model": None}, 12_088_320)
    except bdexport.BdPresetError:
        c.check(True, "a fit with no radius and no pitch is refused as a Blu-ray preset")
    else:
        c.check(False, "a fit with no radius and no pitch is refused as a Blu-ray preset")
    angular = {"model": None, "media": "bd", "rungs": 9, "chi2_per_dof": 1.10,
               "dis_equivalent": {"inner_radius_mm": 24.02, "pitch_um_estimate": 0.3185}}
    params = bdexport.parameters(angular, 12_088_320)
    c.check(abs(params["innerRadiusMm"] - 24.02) < 1e-9 and
            abs(params["outerRadiusMm"] - bdexport.outer_radius_mm(24.02, 0.3185, 12_088_320)) < 1e-6,
            "an angular u/v fit is converted from the radius and pitch it already carries")
    preset = bdexport.preset(fit, 12_088_320, "discprobe-bd-re", "BD-RE", "selftest")
    entry = bdexport.catalog_entry(preset)
    c.check(set(entry) == {"id", "displayName", "description", "totalSectors", "innerRadiusMm",
                           "outerRadiusMm", "invertMapping", "usableSectors"},
            "the catalog entry is the flat record disc-presets.json keeps")
    document = bdexport.document(preset)
    c.check(set(document["parameters"]) == {"totalSectors", "layerCount", "innerRadiusMm",
                                            "outerRadiusMm", "startAngleDegrees", "usableSectors"} and
            document["luminanceMapping"] == {"invert": False},
            "the written document is the shape the preset library's Import reads")
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, bdexport.FILE_NAME)
        first = bdexport.install(preset, path)
        before = open(path, "rb").read()
        again = bdexport.install(preset, path)
        c.check(first["action"] == "added" and first["created"] and again["action"] == "unchanged",
                "installing the same preset twice changes nothing")
        c.check(open(path, "rb").read() == before, "an unchanged install does not rewrite the file")
        replaced = bdexport.install(bdexport.preset(dict(fit, r0_mm=24.65), 12_088_320,
                                                    "discprobe-bd-re", "BD-RE", "selftest"), path, replace=True)
        c.check(replaced["action"] == "replaced" and open(replaced["backup"], "rb").read() == before,
                "a replacement keeps the file it replaced as a backup")
        try:
            bdexport.install(bdexport.preset(dict(fit, r0_mm=24.66), 12_088_320,
                                             "discprobe-bd-re", "BD-RE", "selftest"), path)
        except bdexport.BdPresetError:
            c.check(True, "a different preset under the same id needs --replace")
        else:
            c.check(False, "a different preset under the same id needs --replace")
        other = os.path.join(work, "other.json")
        with open(other, "w", encoding="utf-8") as f:
            f.write('{"schemaVersion": 2, "presets": []}')
        try:
            bdexport.install(preset, other)
        except bdexport.BdPresetError:
            c.check(open(other, encoding="utf-8").read() == '{"schemaVersion": 2, "presets": []}',
                    "a catalog of another schema is left untouched")
        else:
            c.check(False, "a catalog of another schema is left untouched")
    from . import guide
    # The angle ladder's own result: rungs and chi2/dof are the figures install_blocker reads.
    angular = {"fit": {"media": "bd", "rungs": 9, "chi2_per_dof": 1.10,
                       "dis_equivalent": {"inner_radius_mm": 24.02, "pitch_um_estimate": 0.3185}}}
    with tempfile.TemporaryDirectory() as root:
        folder = os.path.join(root, "geo-G-20260101-000000")
        os.makedirs(folder)
        with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(angular, f)
        path = os.path.join(folder, "summary.json")
        c.check(guide.install_blocker(path) is None,
                "an angular Blu-ray result is installable: rungs and chi2/dof are its figures")
        c.check(guide.install_warning(path) is None, "and nothing is left unchecked for it")
        thin = {"fit": {**angular["fit"], "rungs": 3}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(thin, f)
        c.check(guide.install_blocker(path) is not None, "an angular result with too few rungs is refused")


def _efmplus(c: Checker):
    print("EFMPlus modulation with DSV control")
    import numpy as np
    from . import efmplus as E
    sync = [w for group in E.SYNC for kind in group for w in kind]
    c.check(len(set(sync)) == 32, f"all 32 sync codes are distinct ({len(set(sync))})")
    trans =[bin(E.main(q, 1)[0]).count("1") for q in (0xA5, 0x92)]
    c.check(trans == [5, 2], f"A5 / 92 code words have {trans[0]} / {trans[1]} transitions")
    rng = np.random.default_rng(3)
    b, bad, worst, runs = E.Boundary(), 0, 0, []
    for i in range(120):
        lv, nb = E.encode_frame(rng.integers(0, 256, 91).astype(np.uint8), E.ROW_SYNC[i % 13][i % 2], b)
        bad += nb.dsv - b.dsv != 2 * int(lv.sum()) - lv.size
        runs.append(np.diff(np.flatnonzero(np.diff(lv.astype(int)) != 0)))
        worst, b = max(worst, abs(nb.dsv)), nb
    r = np.concatenate(runs)
    c.check(bad == 0 and r.min() >= 3 and r.max() <= 14,
            f"levels and DSV agree, run lengths {r.min()}T-{r.max()}T")
    c.check(worst <= 200, f"DSV stays bounded on random data (max |DSV| {worst} at frame ends)")


def _tiles(c: Checker):
    print("tile palette target")
    import math
    import numpy as np
    from . import imagedisc, tiledisc as T
    palette = ["A5", "92", "B9", "66", "MIX:A5,62,B1,61,65,A7", "MIX:92,87,83,8D,60", "8B", "2AE304", "ED00"]
    labels, textures, lay = T.design(palette)
    wrong, n = 0, 0
    for k, nsec in enumerate(lay["sectors_per_ring"]):
        r_in, r_out = T.RING_EDGES_MM[k] + T.GAP_MM / 2, T.RING_EDGES_MM[k + 1] - T.GAP_MM / 2
        for j in range(nsec):
            def cell(row, col):
                r = r_in + (row + 0.5) / T.ROWS * (r_out - r_in)
                span = 2 * math.pi / nsec - T.GAP_MM / r
                a = j * 2 * math.pi / nsec + T.GAP_MM / 2 / r + (col + 0.5) / T.COLS * span
                ix = int((r * math.cos(a) + imagedisc.HALF_MM) / imagedisc.CELL_MM)
                iy = int((imagedisc.HALF_MM - r * math.sin(a)) / imagedisc.CELL_MM)
                return textures[labels[iy, ix]]
            bits = [int(cell(2 * (s % 3), s // 3) == "A5" and cell(2 * (s % 3) + 1, s // 3) == "92") for s in range(1, 11)]
            swatches = [cell(2 * (i % 3), T.ID_COLS + i // 3) for i in range(9)]
            wrong += T.decode_slots(bits) != (k, j) or swatches != palette
            n += 1
    c.check(wrong == 0, f"all {n} tile IDs and palettes read back from the rasterised design")
    g = T.geometry({"shuffle_seed": 3})
    count = np.zeros((9, 9), np.int64)
    ok = True
    for k, nsec in enumerate(T.sectors_per_ring(g)):
        for j in range(nsec):
            slots = T.swatch_slots(k, j, 9, g)
            cells = T.tile_cells(k, j, 9, g)
            for i, s in enumerate(slots):
                col, pair = divmod(int(s), 3)
                ok &= bool((cells[2 * pair:2 * pair + 2, T.ID_COLS + col] == i).all())
            count[np.arange(9), slots] += 1
    blocks = sum(T.sectors_per_ring(g)) // 9
    c.check(ok and (count >= blocks).all(), f"shuffled swatches: each texture once per tile, every slot at least "
                                            f"{blocks}x per texture (Latin squares)")
    q = imagedisc.texture_bytes("2AE304", np.array([5]))[0]
    c.check(bytes(q[160:163]).hex() in ("2ae304", "e3042a", "042ae3") and len(set(q[:160:3].tolist())) == 1,
            "repeated sequences keep their phase along a data-frame row")
    mix = imagedisc.texture_bytes("MIX:92,87", np.array([5, 6]))
    c.check(set(np.unique(mix).tolist()) == {0x92, 0x87}, "random mixes draw only from their byte list")
    import os
    import tempfile
    u, v, bit = 180518.45, 5.5912083, 133.3
    with tempfile.TemporaryDirectory() as d:
        whole, tail = os.path.join(d, "whole.iso"), os.path.join(d, "tail.iso")
        design = imagedisc.grid_design()
        imagedisc.write_iso(whole, design, u, v, bit, 2400, log=lambda *_: None)
        imagedisc.write_iso(tail, design, u, v, bit, 2400, log=lambda *_: None, first_lba=1600)
        with open(whole, "rb") as f:
            f.seek(1600 * 2048)
            same = f.read() == open(tail, "rb").read()
        c.check(same and not imagedisc.verify_iso(tail, design, u, v, bit, 2400, samples=40, first_lba=1600),
                "an image started at a later LBA is that part of the whole image, byte for byte")
        from . import content, dvd
        lead = os.path.join(d, "lead.iso")
        imagedisc.write_iso(lead, design, u, v, bit, 2400, log=lambda *_: None, lead_lba=800)
        with open(lead, "rb") as f, open(whole, "rb") as g:
            data, ref = f.read(), g.read()
        start = [content.is_random(k, data[k * 2048:(k + 1) * 2048]) for k in range(32, 800, 50)]
        c.check(all(start) and data[800 * 2048:] == ref[800 * 2048:]
                and not imagedisc.verify_iso(lead, design, u, v, bit, 2400, samples=40, lead_lba=800),
                "below lead_lba it is random data, from there the same picture")
        mostly = bytes(range(256)) + bytes([0x92]) * (2048 - 256)
        rng = np.random.default_rng(5)
        c.check(not content.is_random(4000, mostly) and all(
                    content.is_random(k, rng.integers(0, 256, 2048, dtype=np.uint8).tobytes()) for k in range(200)),
                "a sector that is mostly one texture byte is not random, and 200 random sectors all are")
        # The pool of worker processes, forced on for a small image: the same file, byte for byte, with a
        # random lead-in and an angle correction (which has to travel to the workers).
        corr = imagedisc.Correction([0.3, -0.2, 0.1], 26.0, 56.0)
        serial, pooled = os.path.join(d, "serial.iso"), os.path.join(d, "pooled.iso")
        before = imagedisc.PARALLEL_MIN_SECTORS, os.environ.get("DISCPROBE_WORKERS")
        try:
            os.environ["DISCPROBE_WORKERS"] = "1"
            imagedisc.write_iso(serial, design, u, v, bit, 5 * imagedisc.CHUNK + 300, log=lambda *_: None,
                                lead_lba=3000, correction=corr)
            imagedisc.PARALLEL_MIN_SECTORS = 0
            os.environ["DISCPROBE_WORKERS"] = "2"
            imagedisc.write_iso(pooled, design, u, v, bit, 5 * imagedisc.CHUNK + 300, log=lambda *_: None,
                                lead_lba=3000, correction=corr)
        finally:
            imagedisc.PARALLEL_MIN_SECTORS = before[0]
            if before[1] is None:
                os.environ.pop("DISCPROBE_WORKERS", None)
            else:
                os.environ["DISCPROBE_WORKERS"] = before[1]
        with open(serial, "rb") as f, open(pooled, "rb") as g:     # past the file system, which holds the time
            c.check(f.read()[32 * 2048:] == g.read()[32 * 2048:],
                    "two worker processes write the same image as one, byte for byte")


def _prediction(c):
    import numpy as np
    from . import simulate
    print("disc view prediction")
    with np.load(__import__("pathlib").Path(simulate.__file__).with_name("simulate_lut.npz")) as z:
        red = z["single"][0x92, 60]
    c.check(abs(2.13 * .30 * 1000 - 639) < 1 and red[0] > red[1] and red[0] > red[2], "2.13 um at delta .30 is red")
    design = np.zeros((6000, 6000), bool)
    design[800:2700, 3200:5000] = True
    a = simulate.render(design, 200)
    b = simulate.render(design, 200, rotate=360)
    c.check(np.array_equal(a, b), "one full turn returns the same prediction")
    sheet = simulate.sheet(design, None, 200, "A5", "B9", simulate.CAMERA, simulate.FLASH)
    c.check(sheet.size == (600, 824), "sheet has 12 square tiles and a footer without an original")
    try:
        simulate.texture("RND")
    except ValueError as e:
        c.check("single-byte" in str(e), "unsupported texture has a clear error")
    else:
        c.check(False, "unsupported texture has a clear error")


def run() -> bool:
    t, stream = ui.term(), sys.stdout
    if t.color:
        sys.stdout = Report(stream, t)
    try:
        return _run()
    finally:
        sys.stdout.flush()
        sys.stdout = stream


def _run() -> bool:
    c = Checker()
    _parsers(c)
    _report(c)
    _incomplete_folder(c)
    _harmonics(c)
    _timer_tick(c)
    _zone_conflict(c)
    _sim_run(c, "cav", True, "fua", "CAV")
    _sim_run(c, "cav", True, "fua", "CAV", sectors=16)
    _sim_run(c, "cav", True, "fua", "CAV", reread_ms=35.0)
    _sim_run(c, "cav", False, "flush", "CAV", flush=True)
    _sim_run(c, "cav", False, "evict", "CAV")
    _sim_run(c, "clv", True, "fua", "CLV")
    _unreadable(c)
    _cdprobe(c)
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("ladder check skipped (needs numpy)")
    else:
        _pitch_fit(c)
        _grid_acceptance(c)
        _ladder_safe_unwrap(c)
        _ladder(c)
        _ladder_abort(c)
        _ladder_cd_audio(c)
        _geo_rotation(c)
        _disexport(c)
        _install_details(c)
        _correction_run(c)
        _disinstall(c)
        _install_blocker(c)
        _bd_clv(c)
        _bd_export(c)
        _tests_folder(c)
        _efmplus(c)
        _tiles(c)
        from . import cd_selftest
        cd_selftest.run(c)
    try:
        from . import scan_selftest
    except ImportError as e:
        print(f"spoke scan checks skipped ({e}; needs numpy and Pillow)")
    else:
        _prediction(c)
        scan_selftest.run(c)
        from . import cal_selftest, rings_selftest
        rings_selftest.run(c)
        cal_selftest.run(c)
    from . import ui_selftest
    ui_selftest.run(c)
    print(f"\n{'all checks passed' if c.failures == 0 else f'{c.failures} check(s) failed'}")
    return c.failures == 0
