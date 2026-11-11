"""Byte identity at the optimized texture, sampling and preview boundaries."""
import math
import tempfile
from pathlib import Path
from itertools import product

import numpy as np

from discprobe import imagedisc as I, cdimage as C, cd
from discprobe.calib import theta, sector_bits, GROUP_BYTES


def reference_sample(design, u, v, bit_mm, lba0, count, correction=None, media="dvd"):
    bits, group_bits = sector_bits(media)
    n = np.arange(lba0, lba0 + count)[:, None].astype(np.float64) * bits + group_bits[None, :]
    s = np.sqrt(u * u + v * n / math.pi)
    th = -theta(n, u, v)
    r = bit_mm * s
    if correction is not None:
        th = th + np.radians(correction(r))
    size = design.shape[0]
    cell = 2 * I.HALF_MM / size
    ix = np.floor((r * np.cos(th) + I.HALF_MM) / cell).astype(np.int64)
    iy = np.floor((I.HALF_MM - r * np.sin(th)) / cell).astype(np.int64)
    ok = (ix >= 0) & (ix < size) & (iy >= 0) & (iy < size)
    return np.where(ok, design[np.clip(iy, 0, size - 1), np.clip(ix, 0, size - 1)], 0).astype(design.dtype)


def _check_texture_and_sampling_identity(textures, correction, media):
    design = np.random.default_rng(3).integers(0, 3, (317, 317), dtype=np.uint8)
    u, v, bit = 180518.44703810455, 5.5912084141730665, .0001333
    for start in (0, 2048, 500003, 2145149):
        labels = reference_sample(design, u, v, bit, start, 3, correction, media)
        np.testing.assert_array_equal(I._sample(design, u, v, bit, start, 3, correction, media), labels)
        stack = np.stack([I.texture_bytes(t, np.arange(start, start + 3)) for t in textures])
        expected = np.take_along_axis(stack, np.repeat(labels.astype(np.int64), GROUP_BYTES, axis=1)[None], 0)[0]
        np.testing.assert_array_equal(I._sector_q(design, textures, u, v, bit, start, 3, correction, media), expected)


def test_texture_and_sampling_identity():
    for textures, correction, media in product(
        [["B9", "A5", "92"], ["8B00", "A5", "4F92"], ["RND", "MIX:92,4F", "A5"]],
        [None, I.Correction([.5, -.03, .1], 25, 55)], ["dvd", "bd"]
    ):
        _check_texture_and_sampling_identity(textures, correction, media)


def _check_cd_texture_identity(textures):
    design = np.random.default_rng(7).integers(0, 3, (317, 317), dtype=np.uint8)
    u, v, bit = 91044.01528414075, 5.419916013017896, .00027766208524226016
    for start in (0, 2048, 300001):
        lbas = np.arange(start, start + 3)
        frame, slot = cd.user_to_physical(lbas[:, None], np.arange(2048)[None, :])
        first, last = int(frame.min()), int(frame.max())
        labels = C._labels(design, u, v, bit, np.arange(first, last + 1)[:, None], np.array([0, 16])[None, :], None)
        labels = labels[frame - first, (slot >= 16).astype(np.int8)]
        rnd = I.texture_bytes("RND", lbas)
        expected = np.empty(labels.shape, np.uint8)
        for i, spec in enumerate(textures):
            mask = labels == i
            expected[mask] = C.texture_bytes(spec, frame[mask], slot[mask], rnd[mask])
        np.testing.assert_array_equal(C._sector_q(design, textures, u, v, bit, start, 3, None), expected)


def test_cd_texture_identity():
    for textures in [["AA", "0D", "92"], ["8B00", "AA", "4F92"], ["RND", "MIX:92,4F", "AA"]]:
        _check_cd_texture_identity(textures)


def test_preview_identity():
    from PIL import Image
    design = np.random.default_rng(1).integers(0, 3, (317, 317), dtype=np.uint8)
    with tempfile.TemporaryDirectory() as folder:
        expected, actual = Path(folder) / "expected.png", Path(folder) / "actual.png"
        Image.fromarray(np.where(design, 0, 255).astype(np.uint8)).resize((120, 120)).save(expected)
        I.preview(design, str(actual), size=120)
        assert actual.read_bytes() == expected.read_bytes()
