"""Independent byte-position checks and frozen pre-change regression hashes."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from discprobe import calib, dvd, imagedisc as I, randomlabel

U, V, BIT = 180518.44703810455, 5.5912084141730665, .0001333
BASELINE = json.loads((Path(__file__).parent / "data/along-track-grid-baseline.json").read_text())


def rows(side, period=2, labels=2):
    return np.broadcast_to((np.arange(side) // period % labels).astype(np.uint8)[:, None], (side, side))


def test_dvd20_frozen_sector_hashes():
    design = rows(6000, 3, 3)
    for case in BASELINE["dvd20"]:
        correction = I.Correction([.5, -.03, .1], 25, 55) if case["corrected"] else None
        lba = case["lba"]
        q = I._sector_q(design, case["textures"], U, V, BIT, lba, 3, correction)
        raw = q ^ I._scramble_masks("dvd", np.arange(lba, lba + 3))
        assert hashlib.sha256(raw.tobytes()).hexdigest() == case["sha256"], case


def test_randomlabel_frozen_hash_and_legacy_constants():
    assert calib.GROUP_BYTES == 16
    np.testing.assert_array_equal(calib.GROUP_BITS, calib.BYTE_BITS.reshape(-1, 16).mean(axis=1))
    np.testing.assert_array_equal(calib.sector_bits("dvd")[1], calib.GROUP_BITS)
    np.testing.assert_array_equal(calib.sector_bits("bd")[1], calib.GROUP_BITS_BD)
    case = BASELINE["randomlabel"]
    raw = np.zeros((4, 2048), np.uint8)
    randomlabel.Label(case["text"], 2295104).patch(raw, case["lba"])
    assert hashlib.sha256(raw.tobytes()).hexdigest() == case["sha256"]


@pytest.mark.parametrize("side", [12000, 24000])
@pytest.mark.parametrize("textures", [["B9", "A5"], ["8B004F", "924FA5"], ["RND", "MIX:92,4F"]])
def test_dvd_stripes_at_byte_positions(side, textures):
    # 10 um stripes tangent to the track near theta=0. The 5 um design has
    # two cells per stripe. A broadcast view avoids a 576 MB test allocation.
    design = rows(side, side // 12000)
    lba, count = 60000, 2
    # 10 um samples byte pairs (4.27 um), 5 um single bytes: positions from BYTE_BITS.
    step = I.group_bytes(design, "dvd")
    assert step == (2 if side == 12000 else 1)
    centres = calib.BYTE_BITS.reshape(-1, step).mean(axis=1)
    bits = np.arange(lba, lba + count)[:, None] * calib.SECTOR_BITS + centres
    s = np.sqrt(U*U + V * bits / math.pi)
    rotation = float(calib.theta(lba * calib.SECTOR_BITS, U, V))
    th = -calib.theta(bits, U, V) + rotation
    iy = np.floor((60 - BIT * s * np.sin(th)) / (120 / side)).astype(int)
    labels = np.repeat((iy // (side // 12000) % 2).astype(np.uint8), step, axis=1)
    # Choose texture bytes at their original columns, not restarted per sample.
    stack = np.stack([I.texture_bytes(t, np.arange(lba, lba + count)) for t in textures])
    expected = np.take_along_axis(stack, labels[None], axis=0)[0]
    correction = I.Correction([math.degrees(rotation)], 0, 100)
    actual = I._sector_q(design, textures, U, V, BIT, lba, count, correction)
    np.testing.assert_array_equal(actual, expected)
    # Check the bytes recovered from the actual writer, not only the sampler.
    I._job_init(dict(design=design, texs=textures, u=U, v=V, bit_mm=BIT,
                     correction=correction, media="dvd", lead_lba=0))
    try:
        _, _, raw = I._job_chunk((lba, count))
        recorded = np.frombuffer(raw, np.uint8).reshape(count, dvd.SECTOR_BYTES) ^ I._scramble_masks("dvd", np.arange(lba, lba + count))
        np.testing.assert_array_equal(recorded, expected)
    finally:
        I._JOB.clear()
    changes = np.flatnonzero(labels[0, 1:] != labels[0, :-1]) + 1
    assert len(changes) > 300
    # The legacy 34 um samples skip transitions and hold each label for 16 bytes.
    old_bits = lba * calib.SECTOR_BITS + calib.BYTE_BITS.reshape(-1, 16).mean(axis=1)
    old_r = BIT * np.sqrt(U*U + V * old_bits / math.pi)
    old_th = -calib.theta(old_bits, U, V) + rotation
    old_y = np.floor((60 - old_r * np.sin(old_th)) / (120 / side)).astype(int)
    old_labels = np.repeat(old_y // (side // 12000) % 2, 16)
    assert np.mean(old_labels != labels[0]) > .3


@pytest.mark.parametrize("um,side,dvd_group,bd_group", [(20, 6000, 16, 16), (10, 12000, 2, 4), (5, 24000, 1, 2)])
def test_group_choice_and_bd_positions(um, side, dvd_group, bd_group):
    design = rows(side)
    assert I.group_bytes(design, "dvd") == dvd_group
    assert I.group_bytes(design, "bd") == bd_group
    bits, offsets = calib.sector_bits("bd", bd_group)
    assert len(offsets) == 2048 // bd_group
    np.testing.assert_allclose(offsets, (np.arange(2048 // bd_group) + .5) * bits / (2048 // bd_group))
    if um < 20:
        assert bits / 2048 * bd_group * .0745 < um / 2
    lba, count = 100003, 3
    n = np.arange(lba, lba + count)[:, None] * bits + offsets
    r = .0000745 * np.sqrt((24 / .0000745)**2 + (.00032 / .0000745) * n / math.pi)
    th = -calib.theta(n, 24 / .0000745, .00032 / .0000745)
    iy = np.floor((60 - r * np.sin(th)) / (um / 1000)).astype(int)
    expected = np.repeat(np.where(iy // 2 % 2, 0xA5, 0xB9), bd_group, axis=1)
    actual = I._sector_q(design, ["B9", "A5"], 24 / .0000745, .00032 / .0000745, .0000745, lba, count, None, "bd")
    np.testing.assert_array_equal(actual, expected)


def test_offsets_validate_and_preserve_legacy():
    np.testing.assert_array_equal(calib.sector_bits("dvd", 1)[1], calib.BYTE_BITS)
    for size in (0, 3, 4096, 1.5, True):
        with pytest.raises(ValueError):
            calib.sector_bits("dvd", size)


@pytest.mark.parametrize("media", ["dvd", "bd"])
def test_fine_writer_bounds_sector_chunks(tmp_path, monkeypatch, media):
    design = rows(24000)
    spans = []
    original = I._sample

    def sample(design, u, v, bit_mm, lba, count, correction=None, media="dvd"):
        spans.append((lba, count))
        return original(design, u, v, bit_mm, lba, count, correction, media)

    monkeypatch.setattr(I, "_sample", sample)
    monkeypatch.setenv("DISCPROBE_WORKERS", "1")
    path = tmp_path / "fine.iso"
    I.write_iso(str(path), design, U, V, BIT * 1e6, 1100, textures=["8B004F", "924FA5"],
                first_lba=32, lead_lba=50, media=media, log=lambda *_: None)
    limit = I.CHUNK * I.group_bytes(design, media) // 16
    assert max(n for _, n in spans) <= limit
    assert sum(n for _, n in spans) == 1100 - 32
    assert not I.verify_iso(str(path), design, U, V, BIT * 1e6, 1100, textures=["8B004F", "924FA5"],
                            first_lba=32, lead_lba=50, media=media, samples=12)
