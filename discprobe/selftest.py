"""Self-test: parser checks on hand-built responses, then the full timing run on the
simulated drive, compared against the simulator's true geometry."""

from __future__ import annotations

import math

from . import analysis, mmc, timing
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


def _ladder(c: Checker):
    print("ladder geometry measurement on the simulated drive (35 ms re-read overhead)")
    import numpy as np
    from .calib import SECTOR_BITS, theta
    from .geo import Ladder
    sim = SimDrive(mode="cav", seed=7, reread_delay_ms=35.0)
    lad = Ladder(sim, speed_kbs=None, reps=16, max_targets=14, log=lambda *_: None)
    res = lad.run()
    b = 133.6e-6  # the simulator's off-nominal geometry
    n = np.linspace(0, 0.85 * sim.capacity * SECTOR_BITS, 400)
    e = np.degrees(theta(n, lad.u, lad.v) - theta(n, 23.93 / b, 0.735e-3 / b))
    span = float(e.max() - e.min())
    c.check(span < 1.5, f"{len(lad.targets)} rungs, angle error over 0-85 % of the disc {span:.3f} deg "
                        f"(reported 1 sigma {res['angle_sigma_measured_span_deg']:.3f}, "
                        f"chi2/dof {res['chi2_per_dof']:.2f})")


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


def run() -> bool:
    c = Checker()
    _parsers(c)
    _harmonics(c)
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
        _ladder(c)
        _ladder_abort(c)
        _disexport(c)
        _efmplus(c)
        _tiles(c)
        from . import cd_selftest
        cd_selftest.run(c)
    try:
        from . import scan_selftest
    except ImportError as e:
        print(f"spoke scan checks skipped ({e}; needs numpy and Pillow)")
    else:
        scan_selftest.run(c)
        from . import cal_selftest, rings_selftest
        rings_selftest.run(c)
        cal_selftest.run(c)
    from . import ui_selftest
    ui_selftest.run(c)
    print(f"\n{'all checks passed' if c.failures == 0 else f'{c.failures} check(s) failed'}")
    return c.failures == 0
