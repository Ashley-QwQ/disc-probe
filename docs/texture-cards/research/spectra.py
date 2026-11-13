"""Per-texture cross spectra of the mark combs, from the exact encoder, cached in spectra.npz.

For each texture, one ECC block per start state is laid out as on the disc: every sector has
12 random header bytes, 2048 texture bytes and 4 random EDC bytes in 12 rows, each row has 10
random PI bytes, and a random PO row follows each sector. The stream is cut at sync frames
(a frame's polarity is effectively random, so neighbouring frames and tracks do not add
coherently). For each frame and each run length L, c_L(f) = sum over marks of exp(-2 pi i f x)
with x the mark's centre. C[tex, L, L', f] = <c_L conj(c_L')> / frame length in um.
"""

import numpy as np

import common  # noqa: F401  sets priority first
from common import HERE, RUNS, T_UM
import discprobe.efmplus as E  # noqa: E402
from discprobe.imagedisc import texture_bytes  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

FRAME = 1488
NF = 497                      # f = j / (1488 T), up to 2.5 per um
STARTS = [(0, True), (60, False), (-60, True), (30, False)]


def block_rows(spec, seed):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(16):
        q = texture_bytes(spec, np.array([100000 + 16 * seed + s]))[0]
        data = np.concatenate([rng.integers(0, 256, 12).astype(np.uint8), q, rng.integers(0, 256, 4).astype(np.uint8)])
        rows.append(np.hstack([data.reshape(12, 172), rng.integers(0, 256, (12, 10)).astype(np.uint8)]))
        rows.append(rng.integers(0, 256, (1, 182)).astype(np.uint8))
    return np.vstack(rows)


def stream(spec, seed, dsv, land):
    lv, _ = E.encode_rows(block_rows(spec, seed), E.Boundary(1, dsv, land), 0)
    return lv


def marks(lv):
    """(start, length) of the runs of level 0 (marks; 1 = land)."""
    d = np.diff(lv.astype(np.int8))
    st = np.flatnonzero(d == -1) + 1
    en = np.flatnonzero(d == 1) + 1
    if lv[0] == 0:
        st = np.r_[0, st]
    if lv[-1] == 0:
        en = np.r_[en, lv.size]
    return st, en - st


def class_index(length):
    i = np.searchsorted(RUNS, length)
    return np.clip(i, 0, len(RUNS) - 1)


def spectrum(spec):
    n = len(RUNS)
    C = np.zeros((n, n, NF), complex)
    bits = np.zeros(n)          # mark channel bits per class
    nums = np.zeros(n)          # marks per class
    total, frames = 0, 0
    for seed, (dsv, land) in enumerate(STARTS):
        lv = stream(spec, seed, dsv, land)
        st, ln = marks(lv)
        centre2 = 2 * st + ln                         # half-bit grid
        for fr in range(lv.size // FRAME):
            keep = (centre2 >= 2 * fr * FRAME) & (centre2 < 2 * (fr + 1) * FRAME)
            comb = np.zeros((n, 2 * FRAME))
            np.add.at(comb, (class_index(ln[keep]), centre2[keep] - 2 * fr * FRAME), 1.0)
            F = np.fft.rfft(comb, axis=1)[:, :NF]
            C += np.einsum("if,jf->ijf", F, F.conj())
            frames += 1
        cl = class_index(ln)
        np.add.at(bits, cl, ln)
        np.add.at(nums, cl, 1)
        total += lv.size
    return C / (frames * FRAME * T_UM), nums / (total * T_UM), bits / total


def main():
    with open(os.path.join(common.ROOT, "iso", "lut2.tiles.json"), encoding="utf-8") as f:
        palette = json.load(f)["palette"]
    Cs, per_um, share = [], [], []
    t0 = time.time()
    for name in palette:
        C, m, b = spectrum(name)
        Cs.append(C)
        per_um.append(m)
        share.append(b)
        print(f"{name:26s} mark bits {b.sum():.3f}  by run {np.round(b, 3)}  {time.time() - t0:.0f} s", flush=True)
    np.savez_compressed(os.path.join(HERE, "spectra.npz"), C=np.array(Cs).real.astype(np.float32),
                        marks_per_um=np.array(per_um), share=np.array(share), palette=np.array(palette),
                        f=np.arange(NF) / (FRAME * T_UM))


if __name__ == "__main__":
    main()
