"""pcal_assist: the seeded read is the frozen reader's tail, and the candidates find the true family."""
import math

import numpy as np
import pytest

from discprobe import pcal, pcal_assist


def synthetic_polar(L, c, noise=0.6, seed=3):
    """The burn target as the reader's polar image would show it, shifted by tau(r) = c + L / r."""
    design = pcal.design_burn()
    radii = np.arange(pcal.R_MIN, pcal.R_MAX + 1e-6, pcal.DR)
    T = pcal._template_f(design, radii)
    nt = T.shape[1]
    rng = np.random.default_rng(seed)
    G = np.zeros((3,) + T.shape, np.float32)
    for i, r in enumerate(radii):
        shift = (c + L / r) / (2 * math.pi) * nt
        k = np.fft.rfftfreq(nt, 1 / nt)
        row = np.fft.irfft(np.fft.rfft(T[i]) * np.exp(-2j * math.pi * k * shift / nt), n=nt)
        for ch, gain in enumerate((1.0, -0.6, 0.4)):
            G[ch, i] = gain * row
    G += rng.normal(0, noise, G.shape).astype(np.float32)
    good = np.ones(T.shape, bool)
    return design, radii, G, good, T


def frozen_read(monkeypatch, design, radii, G, good):
    """Run pcal.read_photo with its geometry replaced by the synthetic polar image."""
    monkeypatch.setattr(pcal, "initial_h", lambda *a, **k: ([np.eye(3)], {}))
    monkeypatch.setattr(pcal, "refine_with_rings",
                        lambda lg, H, d, log=None: (H, {"ring_points": 300, "ring_rms_mm": 0.1, "ring_frac": 0.9}))
    monkeypatch.setattr(pcal, "prepare_polar", lambda lg, H, d=None: (radii, G, good))
    return pcal.read_photo(np.zeros((60, 60, 3), np.uint8), design)


@pytest.mark.parametrize("L,c,noise", [(33.42, 3.6, 0.6), (-12.0, 1.0, 0.6), (20.0, 5.0, 12.0), (20.0, 5.0, 16.0), (20.0, 5.0, 24.0)])
# statuses: ok, ok, poor_angle_coverage, few_inliers, too_few_votes
def test_seeded_read_reproduces_read_photo(monkeypatch, L, c, noise):
    design, radii, G, good, T = synthetic_polar(L, c, noise)
    frozen = frozen_read(monkeypatch, design, radii, G, good)
    mine = pcal_assist.seeded_read(G, T, radii, design.zones, frozen["L_scan_mm"], frozen["c_scan_rad"],
                                   peak_z=frozen["peak_z"], runner_up_ratio=frozen["runner_up_ratio"],
                                   ring_locked=frozen["ring_locked"], design_name=design.name)
    for key in ("status", "n_votes", "L_mm", "c_deg", "n_inliers", "sigma_L_jack_mm", "zone_spread_mm", "max_gap_deg"):
        assert mine.get(key) == frozen.get(key), key


def test_candidates_put_the_true_peak_first_and_its_arrow_where_the_disc_has_it():
    design, radii, G, good, T = synthetic_polar(33.42, 3.6)
    best = pcal_assist.candidates(G, good, T, radii)[0]
    assert abs(best["L_scan_mm"] - 33.42) <= 0.6
    expect = math.degrees(math.pi / 2 + 3.6 + 33.42 / 52.8) % 360
    assert abs((best["arrow_tip_deg"] - expect + 180) % 360 - 180) < 1.0


def test_scan_grid_keeps_the_readers_lattice():
    reader = np.arange(-45.0, 45.0 + 1e-6, 0.6)
    wide = pcal_assist.scan_grid(300 * pcal.CD_FRAME_MM)
    assert wide[0] <= -300 * pcal.CD_FRAME_MM + 0.6 and wide[-1] >= 300 * pcal.CD_FRAME_MM - 0.6
    assert np.array_equal(pcal_assist.scan_grid(), reader)
    assert np.array_equal(wide[np.isin(wide, reader)], reader)


def test_arrow_outline_tip_follows_L_and_c():
    L, c = 33.42, math.radians(30)
    pts = np.array(pcal_assist.arrow_outline(np.eye(3), L, c))
    r = np.hypot(pts[:, 0], pts[:, 1])
    tip = pts[r.argmax()]
    assert abs(r.max() - 52.8) < 0.05
    assert abs(math.degrees(math.atan2(tip[1], tip[0])) - math.degrees(math.pi / 2 + c + L / 52.8)) < 0.05


# ---- the photo API's guided actions: argument checks and the save gate (no photo needed)
class _Fake:
    width, height, token = 100, 80, "t"
    shot = {"id": "p", "input_sha256": "x"}
    record = {"media": "cd", "source_geo": {"sha256": "g"}}
    ring = {"ring_locked": False, "ring_rms_mm": None}
    source = "clicks"
    last = None
    def lines(self): return {"registered": False}
    def register(self, clicks, hub): return {"clicks": clicks, "hub": hub}


def _store(monkeypatch, tmp_path, fake):
    from discprobe import photo, pcal_manual
    run = tmp_path / "run"; (run / "photos").mkdir(parents=True)
    store = photo.PhotoStore(tmp_path)
    monkeypatch.setattr(store, "get", lambda run_id, ident: (run / "photos" / "p.jpg", None, None))
    monkeypatch.setattr(pcal_manual.AlignmentCache, "get", lambda self, folder, path, ident: fake)
    return lambda **k: store.manual_alignment(dict(run="run", photo="p", **k))


def test_guided_actions_check_their_arguments(monkeypatch, tmp_path):
    call = _store(monkeypatch, tmp_path, _Fake())
    assert call(action="lines", token="t") == {"registered": False}
    with pytest.raises(ValueError):
        call(action="lines", token="t", extra=1)
    with pytest.raises(ValueError):
        call(action="lines", token="stale")
    with pytest.raises(ValueError, match="five"):
        call(action="register", token="t", clicks=[[1, 1]] * 4, hub=[5, 5])
    with pytest.raises(ValueError, match="outside"):
        call(action="register", token="t", clicks=[[1, 1]] * 5, hub=[500, 5])
    assert call(action="register", token="t", clicks=[[1, 2]] * 5, hub=[5, 5])["hub"] == (5.0, 5.0)


def test_guided_save_needs_a_trusted_reading(monkeypatch, tmp_path):
    fake = _Fake()
    call = _store(monkeypatch, tmp_path, fake)
    with pytest.raises(ValueError, match="cannot be used"):
        call(action="save_read", token="t")
    fake.last = {"status": "ok", "trusted": False, "index": 0, "L_mm": 33.4}
    with pytest.raises(ValueError, match="cannot be used"):
        call(action="save_read", token="t")
