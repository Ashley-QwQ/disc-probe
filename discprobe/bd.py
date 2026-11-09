"""Blu-ray main-data scrambling (ISO/IEC 30190), for writing chosen recorded bytes.

The drive XORs the 2048 user bytes of every sector with a scrambling sequence before the 1-7PP
modulation. To make the recorded (scrambled-domain) byte equal Q, the host writes P = Q XOR S.

The register is the ISO/IEC 30190 one: 16 bits, feedback `bit15 ^ bit14 ^ bit12 ^ bit3` shifted in
at the low end, eight steps per byte, the low byte leaving first. The sequence starts fresh at the
first byte of every sector from `seed = (lba + 0x100000) >> 5`, so the 32 sectors of a data block
share one seed and one sequence.

DVD has a 15-bit register and sixteen preset seeds chosen by the sector number (see `dvd.py`); a
Blu-ray burner runs a different one, so a picture compensated with the DVD table comes out as flat
noise on a Blu-ray -- readable, legal, and invisible. This module is the table Blu-ray needs.

The register is linear in its initial state, so the sixteen sequences for the sixteen basis states
can be precomputed once and any sector's mask is an XOR of the ones its seed selects. That is what
makes masking a 12-million-sector image cheap instead of a per-byte loop.
"""

from __future__ import annotations

import numpy as np

SECTOR_BYTES = 2048
DATA_START_PSN = 0x100000     # a Blu-ray's physical sector 0 sits at this LBA offset
BLOCK_SECTORS = 32            # sectors that share one seed


def _sequence(state: int) -> np.ndarray:
    """The 2048 mask bytes one initial register state produces."""
    reg = state & 0xFFFF
    out = np.empty(SECTOR_BYTES, dtype=np.uint8)
    for i in range(SECTOR_BYTES):
        out[i] = reg & 0xFF
        for _ in range(8):
            lsb = ((reg >> 15) ^ (reg >> 14) ^ (reg >> 12) ^ (reg >> 3)) & 1
            reg = ((reg << 1) | lsb) & 0xFFFF
    return out


# The register always starts with bit 15 set (`0x8000 | (seed & 0x7FFF)`), and XOR is linear, so the
# sequence for any seed is the 0x8000 one XORed with the basis sequences of the seed's set bits.
_BASIS = np.stack([_sequence(0x8000)] + [_sequence(1 << k) for k in range(15)])


def seed(lba: int) -> int:
    """The 16-bit register seed of the sector at this LBA, as the drive computes it."""
    return (int(lba) + DATA_START_PSN) >> 5


def sequence(s: int) -> np.ndarray:
    """The 2048 mask bytes of one seed."""
    out = _BASIS[0].copy()
    for k in range(15):
        if (s >> k) & 1:
            out ^= _BASIS[1 + k]
    return out


def masks(lbas: np.ndarray) -> np.ndarray:
    """The (sectors x 2048) mask of a run of consecutive LBAs."""
    seeds = ((np.asarray(lbas, dtype=np.uint64) + np.uint64(DATA_START_PSN)) >> np.uint64(5)).astype(np.uint16)
    out = np.tile(_BASIS[0], (len(seeds), 1))
    for k in range(15):
        chosen = ((seeds >> np.uint16(k)) & np.uint16(1)).astype(bool)
        if chosen.any():
            out[chosen] ^= _BASIS[1 + k]
    return out


def payload_for(q: int, lbas: np.ndarray) -> np.ndarray:
    """User bytes whose recorded main data is all Q, for a run of consecutive sectors."""
    return masks(lbas) ^ np.uint8(q)


def recorded(payload: np.ndarray, lba: int) -> np.ndarray:
    """Recorded-domain bytes the drive will modulate for one sector's payload."""
    return np.asarray(payload, dtype=np.uint8) ^ sequence(seed(lba))

def texture_stats(value: str | int) -> dict:
    """What one recorded byte does to the channel: transitions and the digital sum it leaves.

    The drive scrambles the payload, so the *recorded* byte is the picture texture, and it is the
    recorded byte the 1-7PP modulator sees.  A byte of 0x00 or 0xFF gives seven gaps with no
    transition at all and a digital sum of -8 or +8: the modulator still emits a legal stream, but
    it is a long run for the PLL to coast through, which is what a burnt "pure black" picture runs
    into (L-EC failures, a drive that stops timing).  Mid-grey textures such as A5 and B9 keep six
    and four of the seven gaps changing and the sum within two, so the servo keeps its edges while
    the duty cycle still differs enough to be seen.
    """
    byte = int(value, 16) if isinstance(value, str) else int(value)
    bits = [(byte >> k) & 1 for k in range(7, -1, -1)]        # the byte leaves the host MSB first
    gaps = sum(1 for i in range(7) if bits[i] != bits[i + 1])
    return {"byte": f"{byte:02X}", "gaps_with_a_transition": gaps, "gaps": 7,
            "digital_sum": sum(1 if b else -1 for b in bits),
            "marks": sum(bits)}


def check_textures(dark: str, light: str, *, fewest: int = 3, widest: int = 4) -> dict:
    """Refuse a texture pair that would burn a picture the servo cannot follow."""
    out = {"dark": texture_stats(dark), "light": texture_stats(light)}
    for role, stats in out.items():
        if stats["gaps_with_a_transition"] < fewest or abs(stats["digital_sum"]) > widest:
            raise ValueError(
                f"the {role} texture {stats['byte']} leaves only "
                f"{stats['gaps_with_a_transition']} of 7 gaps with a transition and a digital sum "
                f"of {stats['digital_sum']:+d}; a picture burnt with it can read back as an "
                f"L-EC error. A5 and B9 are the pair that keeps the servo's edges: six and four "
                f"gaps change, sums 0 and +2")
        if stats["byte"] in ("00", "FF"):
            raise ValueError(f"{stats['byte']} is black or white, not a grey: pick a texture with "
                             f"transitions in it (A5 and B9 are the pair)")
    return out
