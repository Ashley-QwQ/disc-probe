import numpy as np

from discprobe import simulate_a3


def disc(labels):
    return labels.astype(np.uint8)


def test_table_holds_card_and_default_textures():
    t = simulate_a3.tables()
    assert {"A5", "B9", "CC67", "F9"} <= set(t["specs"])
    assert len(t["specs"]) >= 261 and t["xyz"].shape[1:] == (len(t["delta"]), 3)


def test_marks_darken_the_mirror_and_dither_mixes_smoothly():
    y, x = np.indices((6000, 6000))
    left = x < 3000
    labels = np.where(left, 1, 0)
    mats = [dict(id="background", spec="B9"), dict(id="dark", spec="A5")]
    # a pose where neither texture lights up near the sample band: the zero order alone
    img = np.asarray(simulate_a3.render(disc(labels), 200, materials=mats, camera=(0, -200, 120), flash=(-43.66, -180, 120),
                                        fine=False, annulus_mm=[24, 58])).astype(float)
    axis = (np.arange(200) + .5) * .6 - 60
    r = np.hypot(axis[None, :], axis[:, None])
    band = (r > 40) & (r < 50) & (np.abs(axis[:, None]) < 8)
    a5 = img[band & (axis[None, :] < -5)].mean()
    b9 = img[band & (axis[None, :] > 5)].mean()
    assert a5 < b9
    # a 50 % checkerboard of 20 um cells mixes into one even tone, not grain
    checker = ((y + x) % 2).astype(np.uint8)
    out = np.asarray(simulate_a3.render(checker, 200, materials=mats, fine=False, annulus_mm=[24, 58])).astype(float)
    rows = slice(95, 105)
    cols = slice(145, 160)      # x 27 .. 36 mm on the horizontal axis
    assert np.abs(np.diff(out[rows, cols], axis=1)).mean() < 3


def test_unknown_spec_needs_a_period_and_rnd_has_no_light():
    import pytest
    with pytest.raises(ValueError):
        simulate_a3.material_xyz(dict(spec="0102030405060708090A"), np.array([.5]))
    assert not simulate_a3.material_xyz(dict(spec="RND"), np.array([.5])).any()
    assert simulate_a3.material_xyz(dict(spec="0102030405060708090A", period_um=1.2), np.linspace(.1, .9, 50)).any()


def test_burn_colours_follow_period():
    c = simulate_a3.burn_colours([dict(id="a", spec="A5"), dict(id="r", spec="RND")])
    assert c["a"] == c["A5"] and "r" not in c
