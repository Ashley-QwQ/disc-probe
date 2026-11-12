"""Label placement and measurement isolation, entirely without a drive."""
import datetime
import json
import subprocess
import types

import numpy as np
import pytest

from discprobe import content, iso9660, randomdisc, randomlabel as L
from discprobe.geo import Ladder
from discprobe.sim import SimDrive


@pytest.fixture
def fixed_iso_clock(monkeypatch):
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 12, 12, tzinfo=tz)
    monkeypatch.setattr(iso9660, "datetime", types.SimpleNamespace(datetime=Clock, timezone=datetime.timezone))


class TestRandomLabel:
    @pytest.mark.parametrize("media", ["dvd", "cd"])
    @pytest.mark.parametrize("seed", [0, 1, 42])
    @pytest.mark.parametrize("sectors", [64, 8193, 17003])
    def test_unlabelled_matches_base_commit(self, tmp_path, fixed_iso_clock, media, seed, sectors):
        # Execute the actual pre-change writer, including its chunk sizes and CD path checks.
        source = subprocess.check_output(["git", "show", "4cd5ab3:discprobe/randomdisc.py"], text=True)
        original = {"__package__": "discprobe"}
        exec(compile(source, "base_randomdisc", "exec"), original)
        before, after = tmp_path / "before.iso", tmp_path / "after.iso"
        original["write_iso"](str(before), sectors, seed, log=lambda *_: None, media=media)
        randomdisc.write_iso(str(after), sectors, seed, log=lambda *_: None, media=media)
        assert before.read_bytes() == after.read_bytes()
        assert not after.with_suffix(".image.json").exists()


    def test_label_changes_only_band_and_keeps_rng_stream(self, tmp_path, monkeypatch, fixed_iso_clock):
        # Shift the LBA band down to exercise a complete ISO, including both chunk boundaries,
        # in 40 MB. The unscaled, full-capacity case is also checked by the evidence script.
        monkeypatch.setattr(L, "START", 8000)
        monkeypatch.setattr(L, "END", 17000)
        monkeypatch.setattr(L, "MIN_SECTORS", 20000)
        from discprobe import labelsession
        monkeypatch.setattr(labelsession, 'measured_label', lambda text, sectors, geo: L.Label(text, sectors))
        before, after = tmp_path / "plain.iso", tmp_path / "label.iso"
        randomdisc.write_iso(str(before), 20000, 3, log=lambda *_: None)
        randomdisc.write_iso(str(after), 20000, 3, log=lambda *_: None, label="MEAS-A 2-01 disc-probe", geo="test-fit")
        a = np.fromfile(before, np.uint8).reshape(-1, 2048)
        b = np.fromfile(after, np.uint8).reshape(-1, 2048)
        changed = np.flatnonzero(np.any(a != b, axis=1))
        assert np.array_equal(changed, np.arange(L.START, L.END))
        spec = json.loads(after.with_suffix(".image.json").read_text())
        assert L.read_marker(b[L.START].tobytes(), 20000) == spec
        assert not content.is_random(L.START + 1, b[L.START + 1].tobytes())
        randomdisc.write_iso(str(after), 20000, 3, log=lambda *_: None)
        assert not after.with_suffix(".image.json").exists()
        assert before.read_bytes() == after.read_bytes()


    def test_metadata_detects_damage_and_old_discs(self):
        spec = L.Label("disc-probe", 2295104).spec
        raw = L.marker(spec)
        assert L.read_marker(raw, 2295104) == spec
        assert L.read_marker(bytes(2048), 2295104) is None
        damaged = raw.replace(b"disc-probe", b"disk-probe")
        with pytest.raises(ValueError, match="damaged"):
            L.read_marker(damaged, 2295104)
        with pytest.raises(ValueError, match="damaged"):
            L.read_marker(raw, L.END - 1)

    @pytest.mark.parametrize("sidecar", ["incomplete JSON", "[]", '{"kind":"other"}'])
    def test_plain_writer_ignores_unrelated_sidecars(self, tmp_path, sidecar):
        path = tmp_path / "plain.iso"
        spec = path.with_suffix(".image.json")
        spec.write_text(sidecar)
        randomdisc.write_iso(str(path), 64, log=lambda *_: None)
        assert path.stat().st_size == 64 * 2048
        assert spec.read_text() == sidecar


    @pytest.mark.parametrize("text,media,sectors", [("", "dvd", 2295104), ("中文", "dvd", 2295104),
        ("x\ny", "dvd", 2295104), ("x", "cd", 359600), ("x", "bd", 2295104),
        ("x", "dvd", L.END - 1), ("x", "dvd", L.MIN_SECTORS - 1), ("x" * 181, "dvd", 2295104)])
    def test_invalid_label_leaves_output_untouched(self, tmp_path, text, media, sectors):
        path = tmp_path / "keep.iso"
        path.write_bytes(b"keep")
        with pytest.raises(ValueError):
            randomdisc.write_iso(str(path), sectors, label=text, media=media)
        assert path.read_bytes() == b"keep"


    def test_default_band_is_outside_geo_default_and_aligned(self):
        assert L.START > int((2295104 - 1) * .85) + 3000
        assert L.START % 16 == L.END % 16 == 0
        full = [(60000, 2295104)]
        safe = L.exclude_ranges(full, [L.START, L.END])
        assert len(safe) == 2
        assert all(b <= L.START - 3000 or a >= L.END + 3000 for a, b in safe)
        seen = []
        def read(lba):
            assert not L.START - 3000 <= lba < L.END + 3000
            seen.append(lba)
            return np.random.default_rng(lba).bytes(2048)
        assert content.random_ranges(read, safe) is None
        assert seen

    def test_default_geo_keeps_original_ranges_without_layout_read(self, monkeypatch):
        ladder = Ladder(SimDrive(), log=lambda *_: None)
        def unexpected():
            raise AssertionError("default geo must not add an outer-edge read")
        monkeypatch.setattr(ladder.tp, "load_layout", unexpected)
        ranges = [(int(2295103 * .03), int(2295103 * .85))]
        assert ladder._label_parts(ranges) == ranges

    def test_unreadable_marker_excludes_band_conservatively(self, monkeypatch):
        ladder = Ladder(SimDrive(layout_sectors={L.START: b''}), log=lambda *_: None)
        ladder.tp.setup()
        monkeypatch.setattr(ladder.tp, "_read", lambda *a, **k: types.SimpleNamespace(ok=False))
        ladder.tp.load_layout()
        assert ladder.tp.summary["random_label"]["unreadable_marker"]
        safe = ladder._label_parts([(60000, 2295104)])
        assert all(b <= L.START or a >= L.END for a, b in safe)


    @pytest.mark.parametrize("ranges", [None, [(60000, 2295104)]])
    def test_geo_and_timing_simulation_never_sample_label(self, monkeypatch, ranges):
        ladder = Ladder(SimDrive(jitter_us=0, outlier_rate=0), ranges=ranges,
                        max_targets=8, state_check=False, log=lambda *_: None)
        raw = L.marker(L.Label("MEAS-A 2-01 disc-probe", 2295104).spec)
        ladder.dev.layout_sectors = {L.START: raw}
        read = ladder.tp._read
        def guarded(lba, count=1, fua=False, label=""):
            if label != "layout":
                assert lba + max(count, 16) <= L.START or lba >= L.END
            result = read(lba, count, fua, label)
            if label == "layout":
                result.data = raw if lba == L.START else bytes(2048)
            return result
        monkeypatch.setattr(ladder.tp, "_read", guarded)
        ladder.run()
        if ranges:
            assert ladder.tp.summary["random_label"]["text"] == "MEAS-A 2-01 disc-probe"
        assert all(not (a < L.END and b > L.START) for a, b in ladder.ranges)
        ladder.tp.load_layout()
        ladder.tp.period_reads = 20
        ladder.tp.period_test()
        ladder.tp.phase_test()
        assert all(not L.START <= z["lba"] < L.END for z in ladder.tp.zones)


    def test_polar_glyph_sampling_and_inverse_mapping(self):
        label = L.Label("MEAS-A 2-01 disc-probe", 2295104)
        assert label.spec["height_mm"] == 2.4
        glyphs, band = label.design(size=600)
        assert glyphs[band].any()
        assert (~glyphs[band]).any()
        u, v = 180518.4692643996, 5.591207637041575
        from discprobe.calib import theta, SECTOR_BITS
        n = np.array([L.START, L.END]) * SECTOR_BITS
        shear = np.degrees(theta(n, u, v) - theta(n, L.U, L.V))
        assert abs(shear[1] - shear[0]) > 4900  # disproves the small-shear assumption


def test_random_label_contract():
    """Also runnable by the built-in selftest, whose runner supplies no fixtures."""
    spec = L.Label("MEAS-A 2-01 disc-probe", 2295104).spec
    assert L.read_marker(L.marker(spec), 2295104) == spec
    assert L.START > int(2295103 * .85) + 3000
    assert len(L.exclude_ranges([(60000, 2295104)], [L.START, L.END])) == 2
