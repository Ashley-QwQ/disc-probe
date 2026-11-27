import pytest

from disclab.drive import burn_seconds

FULL_DVD = 2297888


def test_quick_is_the_default(monkeypatch):
    monkeypatch.delenv("DISCLAB_BURN_TIME", raising=False)
    assert burn_seconds(FULL_DVD, 8, "dvd") == 1.0


def test_real_time_follows_size_and_speed():
    eight = burn_seconds(FULL_DVD, 8, "dvd", "real")
    assert 400 < eight < 450                                   # a full DVD-R at 8x: about 7 minutes of data
    assert burn_seconds(FULL_DVD, 16, "dvd", "real") == pytest.approx(eight / 2)
    assert burn_seconds(FULL_DVD // 2, 8, "dvd", "real") == pytest.approx(eight / 2, rel=1e-6)
    assert 160 < burn_seconds(359600, 24, "cd", "real") < 190


def test_scale_and_floor():
    assert burn_seconds(FULL_DVD, 8, "dvd", "0.1") == pytest.approx(burn_seconds(FULL_DVD, 8, "dvd", "real") * 0.1)
    assert burn_seconds(10, 16, "dvd", "real") == 1.0           # never shorter than the quick burn


@pytest.mark.parametrize("bad", ["0", "-1", "slow"])
def test_bad_settings_are_refused(bad):
    with pytest.raises(ValueError):
        burn_seconds(FULL_DVD, 8, "dvd", bad)
