"""What a burn physically put where: a polar map of recorded-domain bytes over the data side of a DVD.

Each cell holds a recorded texture identity. Codes 0..255, MIXED=256 (RND),
and BLANK=257 retain their original meanings. Additional uint16 codes index
hex recipes in the NPZ texture_specs/texture_codes arrays. Classification reads
actual descrambled bytes, using sidecar recipes and group size when available;
the sidecar design is never treated as proof of what was written.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import ExitStack
import json

import numpy as np

from discprobe import dvd
from discprobe.calib import BYTE_BITS, SECTOR_BITS

from .physics import Disc
from .tables import canonical

MIXED, BLANK = 256, 257
R0, R1, DR = 22.0, 58.6, 0.05
DA_DEG = 0.05


def classify_runs(runs, columns=None):
    """Shortest exact period <=64, or RND. Require at least two repeats.

    columns supply recorded-row positions, so a recipe's row-reset phase is
    recovered rather than assigning a different identity to every rotation.
    Without columns, identities start at the beginning of each sampled run.
    """
    runs = np.atleast_2d(np.asarray(runs, np.uint8))
    n, width = runs.shape
    result = np.full(n, "RND", object)
    todo = np.ones(n, bool)
    for p in range(1, min(64, width // 2) + 1):
        match = todo & (runs[:, 0] == runs[:, p])
        if p + 1 < width:
            match &= runs[:, 1] == runs[:, p + 1]
        ids = np.flatnonzero(match)
        if not len(ids):
            continue
        good = np.all(runs[ids, :-p] == runs[ids, p:], axis=1)
        for i in ids[good]:
            seq = runs[i, :p]
            if columns is not None:
                col = columns[i] if np.ndim(columns) == 2 else columns
                seq = seq[(np.arange(p) - int(col[0])) % p]
            result[i] = canonical(seq.tobytes().hex())
            todo[i] = False
    return result


def texture_registry(lab, disc_id):
    """Old NPZ maps remain readable without migration or ISO availability."""
    with np.load(map_path(lab, disc_id), allow_pickle=False) as z:
        if "texture_codes" not in z:
            return {}
        return {int(k): str(v) for k, v in zip(z["texture_codes"], z["texture_specs"])}


def grid():
    r = np.arange(R0, R1 + DR / 2, DR)
    a = np.radians(np.arange(0, 360, DA_DEG))
    return r, a


def map_path(lab, disc_id):
    return lab.root / "media" / (disc_id.replace(" ", "_") + ".map.npz")


def extract_map(lab, disc_id, log=print):
    # Release Windows ISO handles even if classification/metadata fails.
    with ExitStack() as resources:
        return _extract_map(lab, disc_id, log, resources)


def _extract_map(lab, disc_id, log, resources):
    st = lab.state()
    burn = st["burns"][disc_id]
    truth = lab.answers()["discs"][disc_id]
    disc = Disc(truth, burn)
    sessions = []
    registry = {MIXED: "RND"}
    by_spec = {"RND": MIXED}

    def encode(spec):
        if spec not in by_spec:
            code = int(spec, 16) if len(spec) == 2 else max([257, *registry]) + 1
            if code > np.iinfo(np.uint16).max:
                raise ValueError("Too many distinct recorded textures in this map")
            by_spec[spec] = code
            registry[code] = spec
        return by_spec[spec]

    for s in burn["sessions"]:
        mm = np.memmap(s["iso"], np.uint8, "r")
        resources.callback(mm._mmap.close)
        sidecar = Path(s["iso"]).with_suffix(".image.json")
        meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        specs = ["RND" if t.strip().upper().startswith("MIX:") else canonical(t)
                 for t in meta.get("textures", [])]
        candidates = []
        cols = (12 + np.arange(2048)) % 172
        for spec in specs:
            if spec != "RND":
                seq = np.frombuffer(bytes.fromhex(spec), np.uint8)
                candidates.append((encode(spec), seq[cols % len(seq)]))
        legacy = bool(specs) and set(specs) <= {"A5", "B9", "RND"}
        sessions.append((s["start_lba"], s["start_lba"] + s["sectors"], mm,
                         candidates, int(meta.get("group_bytes", 0)), legacy))
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
        for start, end, mm, candidates, group, legacy in sessions:
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
            if legacy:
                # Preserve the original three-byte boundary/coincidence rule
                # for existing A5/B9/RND images, including sidecar images.
                pass
            elif candidates:
                # Compare every byte of the design's sampled byte group. Do
                # not mistake a three-byte coincidence for a recipe match.
                width = group or 32
                starts = jj // width * width
                offsets = np.arange(width)
                ix = starts[:, None] + offsets
                valid = ix < 2048
                ix = np.minimum(ix, 2047)
                q = mm[(sec - start)[:, None] * 2048 + ix] ^ np.take_along_axis(mask, ix, axis=1)
                v[:] = MIXED
                for code, template in candidates:
                    hit = np.all((q == template[ix]) | ~valid, axis=1)
                    v[hit] = code
            else:
                # A 128-byte interval wholly inside a recorded row identifies
                # any <=64-byte period. Row boundaries reset texture phase.
                col = (12 + jj) % 172
                starts = np.maximum(jj - col, 0)
                starts = np.minimum(starts, 2048 - 128)
                ix = starts[:, None] + np.arange(128)
                q = mm[(sec - start)[:, None] * 2048 + ix] ^ np.take_along_axis(mask, ix, axis=1)
                found = classify_runs(q, (12 + ix) % 172)
                for spec in np.unique(found):
                    hit = found == spec
                    if spec != "RND":
                        code = encode(spec)
                        if len(spec) > 2:
                            v[hit] = code
                # Keep the original local single-byte rule where the longer
                # interval straddles different drawing regions.
            val[m] = v
        out[i0:i0 + 16] = val
    path = map_path(lab, disc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, map=out, r0=R0, dr=DR, da_deg=DA_DEG, disc=disc_id,
                        sessions=np.array([s["iso"] for s in burn["sessions"]]), schema=2,
                        texture_codes=np.array(list(registry), np.uint16),
                        texture_specs=np.array(list(registry.values())))
    values, counts = np.unique(out, return_counts=True)
    top = sorted(zip(counts, values), reverse=True)[:5]
    log(f"disclab: burn map of {disc_id}: " + ", ".join(
        f"{registry.get(int(v), 'BLANK' if v == BLANK else f'{v:02X}')} {c / out.size:.1%}" for c, v in top))
    return path


def load_map(lab, disc_id):
    with np.load(map_path(lab, disc_id), allow_pickle=False) as z:
        return z["map"], float(z["r0"]), float(z["dr"]), float(z["da_deg"])
