"""What a burn physically put where: a polar map of recorded-domain bytes over the data side of a DVD.

Each cell (r, alpha) holds the recorded byte Q of the user byte nearest that spot (Q = user ^ scramble mask),
when that byte and its two neighbours agree (a single-byte texture such as A5 or B9); MIXED where they differ
(random data or a multi-byte texture); BLANK where nothing was written. Built once per burn, so the ISO file can
be deleted afterwards.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from discprobe import dvd
from discprobe.calib import BYTE_BITS, SECTOR_BITS

from .physics import Disc

MIXED, BLANK = 256, 257
R0, R1, DR = 22.0, 58.6, 0.05
DA_DEG = 0.05


def grid():
    r = np.arange(R0, R1 + DR / 2, DR)
    a = np.radians(np.arange(0, 360, DA_DEG))
    return r, a


def map_path(lab, disc_id):
    return lab.root / "media" / (disc_id.replace(" ", "_") + ".map.npz")


def extract_map(lab, disc_id, log=print):
    st = lab.state()
    burn = st["burns"][disc_id]
    truth = lab.answers()["discs"][disc_id]
    disc = Disc(truth, burn)
    sessions = []
    for s in burn["sessions"]:
        mm = np.memmap(s["iso"], np.uint8, "r")
        sessions.append((s["start_lba"], s["start_lba"] + s["sectors"], mm))
    r, a = grid()
    out = np.full((len(r), len(a)), BLANK, np.uint16)
    nb = len(BYTE_BITS)
    for i0 in range(0, len(r), 16):
        rr, aa = np.meshgrid(r[i0:i0 + 16], a, indexing="ij")
        bit = disc.bit_at(rr, aa)
        sector = np.floor(bit / SECTOR_BITS).astype(np.int64)
        within = bit - sector * SECTOR_BITS
        j = np.clip(np.searchsorted(BYTE_BITS, within), 0, nb - 3)
        val = np.full(rr.shape, BLANK, np.uint16)
        for start, end, mm in sessions:
            m = (sector >= start) & (sector < end)
            if not m.any():
                continue
            sec, jj = sector[m], j[m]
            base = (sec - start) * 2048 + jj
            mask = dvd.MASKS[((sec + dvd.DATA_START_PSN) >> 4) & 0xF]
            q0 = mm[base] ^ mask[np.arange(len(sec)), jj]
            q1 = mm[base + 1] ^ mask[np.arange(len(sec)), jj + 1]
            q2 = mm[base + 2] ^ mask[np.arange(len(sec)), jj + 2]
            v = np.where((q0 == q1) & (q1 == q2), q0.astype(np.uint16), MIXED)
            val[m] = v
        out[i0:i0 + 16] = val
    path = map_path(lab, disc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, map=out, r0=R0, dr=DR, da_deg=DA_DEG, disc=disc_id,
                        sessions=np.array([s["iso"] for s in burn["sessions"]]))
    values, counts = np.unique(out, return_counts=True)
    top = sorted(zip(counts, values), reverse=True)[:5]
    log(f"disclab: burn map of {disc_id}: " + ", ".join(
        f"{'MIXED' if v == MIXED else 'BLANK' if v == BLANK else f'{v:02X}'} {c / out.size:.1%}" for c, v in top))
    return path


def load_map(lab, disc_id):
    z = np.load(map_path(lab, disc_id))
    return z["map"], float(z["r0"]), float(z["dr"]), float(z["da_deg"])
