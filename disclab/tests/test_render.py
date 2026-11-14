"""Renderer contracts: stored pre-change pixels and recorded texture identities."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from disclab import burnmap, photos
from disclab.box import make_box
from disclab.lab import Lab
from disclab.lab import atomic_json


def legacy_image(tmp_path, code, light):
    lab = Lab(tmp_path / f"legacy-{code}-{light}")
    make_box(lab, "dvd-r", 3, seed=17)
    disc = lab.box()["discs"][0]
    path = burnmap.map_path(lab, disc)
    path.parent.mkdir(parents=True, exist_ok=True)
    pattern = np.full((75, 360), code, np.uint16)
    pattern[:, 80:110] = burnmap.BLANK
    np.savez_compressed(path, map=pattern, r0=22., dr=.5, da_deg=1.)
    pose = photos.Pose(width=320, height=240, seed=294, light=light,
                       dist_mm=260, tilt_deg=23, az_deg=37, roll_deg=12, flash_mm=(34., 0.))
    return photos.render(lab, disc, pose)[0]


@pytest.mark.parametrize("code", [0xA5, 0xB9, burnmap.MIXED])
@pytest.mark.parametrize("light", ["flash", "lamp"])
def test_legacy_photo_pixels(tmp_path, code, light):
    hashes = json.loads((Path(photos.DATA).parent / "legacy_photo_hashes.json").read_text())
    digest = hashlib.sha256(legacy_image(tmp_path, code, light).tobytes()).hexdigest()
    assert digest == hashes[f"{code}-{light}"]


def test_period_classification_and_row_phase():
    from disclab.tables import canonical
    rng = np.random.default_rng(712)
    cols = np.arange(12, 140)
    specs = ["A5", "CC67", "A37062", bytes(range(64)).hex().upper()]
    runs = []
    for spec in specs:
        seq = np.frombuffer(bytes.fromhex(spec), np.uint8)
        runs.append(seq[cols % len(seq)])
    runs.append(rng.integers(0, 256, 128, dtype=np.uint8))
    assert list(burnmap.classify_runs(runs, cols)) == specs + ["RND"]
    assert canonical("A5A5") == "A5"
    assert canonical(" cc67cc67 ") == "CC67"
    assert list(burnmap.classify_runs([[0xA5, 0xA5], [1, 2]])) == ["A5", "RND"]
    with pytest.raises(ValueError): canonical("00" * 65)


@pytest.mark.parametrize("sidecar", [True, False])
def test_extract_recorded_textures(tmp_path, monkeypatch, sidecar):
    from discprobe import dvd
    from discprobe.imagedisc import texture_bytes
    from discprobe.calib import BYTE_BITS, SECTOR_BITS
    lab = Lab(tmp_path / "synthetic")
    make_box(lab, "dvd-r", 3, seed=17)
    disc = lab.box()["discs"][0]
    specs = ["A5", "A37062", "CC67", "RND"]
    q = np.stack([texture_bytes(s, np.array([i]))[0] for i, s in enumerate(specs)])
    iso = tmp_path / "recipes.iso"
    mask = dvd.MASKS[((np.arange(4) + dvd.DATA_START_PSN) >> 4) & 15]
    (q ^ mask).tofile(iso)
    if sidecar:
        iso.with_suffix(".image.json").write_text(json.dumps(dict(textures=specs, group_bytes=32)))
    with lab.locked_state() as state:
        state["burns"][disc] = dict(sessions=[dict(iso=str(iso), start_lba=0, sectors=4)])
    class SyntheticDisc:
        def __init__(self, *args): pass
        def bit_at(self, rr, aa): return rr * SECTOR_BITS + BYTE_BITS[128]
    monkeypatch.setattr(burnmap, "Disc", SyntheticDisc)
    monkeypatch.setattr(burnmap, "grid", lambda: (np.arange(4), np.array([0.])))
    burnmap.extract_map(lab, disc)
    result = burnmap.load_map(lab, disc)[0][:, 0]
    registry = burnmap.texture_registry(lab, disc)
    assert result[0] == 0xA5
    assert result[3] == burnmap.MIXED
    assert [registry[int(c)] for c in result] == specs
    iso.unlink()  # The map contains everything required for later photos.
    assert burnmap.texture_registry(lab, disc) == registry


def test_flat_along_track_matches_discprobe():
    from discprobe.simulate import along_track
    rng = np.random.default_rng(828)
    xy = rng.uniform(-58, 58, (300, 2))
    S = np.column_stack([xy, np.zeros(len(xy))])
    camera = np.array([82., 33., 280.])
    lamp = camera + np.array([34., 0., 0.])
    c, l = camera - S, lamp - S
    c /= np.linalg.norm(c, axis=1, keepdims=True)
    l /= np.linalg.norm(l, axis=1, keepdims=True)
    ours = photos.delta_t(c + l, np.arctan2(xy[:, 1], xy[:, 0]))
    expected = along_track(xy[:, 0], xy[:, 1], camera, lamp)
    assert np.max(np.abs(ours - expected)) < 5e-16


def test_xyz_interpolation_has_dark_domain_edges():
    xyz = np.array([[1., 2., 3.], [3., 4., 5.]])
    result = photos.interpolate_xyz(np.array([.1, .95]), xyz, np.array([.099, .1, .525, .95, .951]))
    np.testing.assert_allclose(result, [[0, 0, 0], [1, 2, 3], [2, 3, 4], [3, 4, 5], [0, 0, 0]])


def test_small_multi_texture_photo_is_not_blank(tmp_path, monkeypatch):
    from discprobe import dvd
    from discprobe.imagedisc import texture_bytes
    from discprobe.calib import BYTE_BITS, SECTOR_BITS
    from disclab.tables import lookup, TEXTURES
    lab = Lab(tmp_path / "check region")
    make_box(lab, "dvd-r", 3, seed=17)
    disc = lab.box()["discs"][0]
    iso = tmp_path / "check-region.iso"
    q = np.stack([texture_bytes(s, np.array([i]))[0] for i, s in enumerate([TEXTURES[0], "F9"])])
    mask = dvd.MASKS[((np.arange(2) + dvd.DATA_START_PSN) >> 4) & 15]
    (q ^ mask).tofile(iso)
    with lab.locked_state() as state:
        state["burns"][disc] = dict(sessions=[dict(iso=str(iso), start_lba=0, sectors=2)])
    class RegionDisc:
        def __init__(self, *args): pass
        def bit_at(self, rr, aa): return (aa >= np.pi).astype(int) * SECTOR_BITS + BYTE_BITS[128]
    # Spread the two retained sampled sectors over a visible region, so this
    # tests extraction -> retained identities -> render with a 4 KiB ISO.
    monkeypatch.setattr(burnmap, "Disc", RegionDisc)
    monkeypatch.setattr(burnmap, "DR", .5)
    monkeypatch.setattr(burnmap, "DA_DEG", 1.)
    path = burnmap.extract_map(lab, disc, log=lambda *a: None)
    iso.unlink()
    pose = photos.Pose(width=320, height=240, seed=294, dist_mm=260, tilt_deg=23,
                       noise=0, veil=0, glare_gain=0, rainbow_gain=0, reflect=0)
    image, _, record = photos.render(lab, disc, pose)
    assert record["texture_model"].startswith("A3 v3")
    assert image.std() > 10
    assert np.count_nonzero(image.max(-1) - image.min(-1) > 20) > 100
    assert lookup("F9")["xyz"].shape == (1025, 2, 3)
    with np.load(path) as z:
        content = {k: z[k] for k in z.files}
    content["map"] = np.full_like(content["map"], burnmap.BLANK)
    np.savez_compressed(path, **content)
    blank = photos.render(lab, disc, pose)[0]
    assert np.count_nonzero(np.max(image.astype(int) - blank.astype(int), axis=-1) > 20) > 100


@pytest.mark.parametrize("sidecar", [False, True])
def test_legacy_map_matches_original_byte_rule(tmp_path, monkeypatch, sidecar):
    from discprobe import dvd
    from discprobe.calib import BYTE_BITS, SECTOR_BITS
    lab = Lab(tmp_path / "old-map")
    make_box(lab, "dvd-r", 3, seed=17)
    disc = lab.box()["discs"][0]
    q = np.full(2048, 0xA5, np.uint8)
    q[80:160] = 0xB9
    q[160:] = np.random.default_rng(91).integers(0, 256, 1888, dtype=np.uint8)
    iso = tmp_path / "old.iso"
    (q ^ dvd.MASKS[(dvd.DATA_START_PSN >> 4) & 15]).tofile(iso)
    if sidecar:
        iso.with_suffix(".image.json").write_text(json.dumps(dict(textures=["A5", "B9", "RND"], group_bytes=32)))
    with lab.locked_state() as state:
        state["burns"][disc] = dict(sessions=[dict(iso=str(iso), start_lba=0, sectors=1)])
    indices = np.array([0, 32, 78, 79, 80, 128, 158, 159, 160, 256, 512])
    class OldDisc:
        def __init__(self, *args): pass
        def bit_at(self, rr, aa): return np.broadcast_to(BYTE_BITS[indices], rr.shape)
    monkeypatch.setattr(burnmap, "Disc", OldDisc)
    monkeypatch.setattr(burnmap, "grid", lambda: (np.array([22.]), indices))
    burnmap.extract_map(lab, disc, log=lambda *a: None)
    expected = np.where((q[indices] == q[indices+1]) & (q[indices+1] == q[indices+2]),
                        q[indices].astype(np.uint16), burnmap.MIXED)
    np.testing.assert_array_equal(burnmap.load_map(lab, disc)[0][0], expected)


def test_unshipped_texture_needs_source(monkeypatch):
    from disclab.tables import lookup
    monkeypatch.delenv("DISCLAB_A3_SOURCE", raising=False)
    with pytest.raises(RuntimeError, match="exported A3 source"):
        lookup("0102030405")


def test_flash_default_and_explicit_legacy_pose():
    import argparse
    parser = argparse.ArgumentParser()
    photos.add_parser(parser.add_subparsers())
    args = ["photos", "--lab", "LAB", "--disc", "disc", "--out", "out"]
    assert photos.Pose().flash_mm == (-43.66, 19.79)
    assert tuple(parser.parse_args(args).flash_mm) == photos.Pose().flash_mm
    assert tuple(parser.parse_args(args + ["--flash-mm", "34", "0"]).flash_mm) == (34., 0.)


def test_failed_extraction_releases_iso(tmp_path):
    lab = Lab(tmp_path / "failed-extraction")
    make_box(lab, "dvd-r", 3, seed=17)
    disc = lab.box()["discs"][0]
    iso = tmp_path / "invalid-meta.iso"
    iso.write_bytes(bytes(2048))
    iso.with_suffix(".image.json").write_text("{")
    with lab.locked_state() as state:
        state["burns"][disc] = dict(sessions=[dict(iso=str(iso), start_lba=0, sectors=1)])
    with pytest.raises(json.JSONDecodeError):
        burnmap.extract_map(lab, disc)
    iso.unlink()  # Windows refuses this while a memmap still holds the file.


def test_shipped_table_against_direct_wave_model(tmp_path):
    """Opt-in source computation; CI without the research export can skip it."""
    import os
    source = os.environ.get("DISCLAB_A3_SOURCE")
    if not source:
        pytest.skip("direct model check needs DISCLAB_A3_SOURCE")
    from disclab.tables import wave_model, operator, lookup
    W = wave_model(source, os.environ.get("DISCLAB_WAVE_CACHE", tmp_path))
    op, _ = operator(W)
    # No spectral checkpoint/compute() reuse: encode all eight blocks anew.
    masses = []
    for seed in range(W.SAMPLES):
        lv, (lo, hi), _ = W.recorded_block("A37062", seed)
        masses.append(W.rebin_power(lv[lo:hi]))
    expected = W.xyz_from_mass(np.mean(masses, axis=0), op)
    np.testing.assert_allclose(lookup("A37062")["xyz"], expected, rtol=6e-8, atol=1e-10)
