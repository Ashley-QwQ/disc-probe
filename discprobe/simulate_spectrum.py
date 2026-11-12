"""Private numeric spectrum backend owned by simulate; no device or file writing.

Existing spectrum integration/CIE/LED code: docs/goals/ask-colour-ideal/reply_fable/scripts/colourlib.py.
Existing in-memory ECC model: tools/dsv_block.py. Same three ECC positions as art/sim_view.py.
The single-byte release LUT is retained, never regenerated at render time.
"""
from functools import lru_cache
import numpy as np
from . import dvd, efmplus

T_DVD_UM = 0.1333
T_CD_UM = 0.27766
NM = np.arange(380.0, 731.0, 2.0)

XYZ_TO_SRGB = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])


def _lobe(x, mu, s1, s2):
    t = (x - mu) * np.where(x < mu, s1, s2)
    return np.exp(-0.5 * t * t)


def cmf(nm):
    x = 1.056 * _lobe(nm, 599.8, 0.0264, 0.0323) + 0.362 * _lobe(nm, 442.0, 0.0624, 0.0374) - 0.065 * _lobe(nm, 501.1, 0.0490, 0.0382)
    y = 0.821 * _lobe(nm, 568.8, 0.0213, 0.0247) + 0.286 * _lobe(nm, 530.9, 0.0613, 0.0322)
    z = 1.217 * _lobe(nm, 437.0, 0.0845, 0.0278) + 0.681 * _lobe(nm, 459.0, 0.0385, 0.0725)
    return np.stack([x, y, z], -1)


def led(nm):
    # Fixed to the release model's default LED; environment variables cannot change it.
    return np.exp(-0.5 * ((nm - 450) / 12) ** 2) + 0.75 * np.exp(-0.5 * ((nm - 560) / 55) ** 2)


_E = led(NM)
_CMF = cmf(NM)
WHITE_XYZ = (_E[:, None] * _CMF).sum(0)
_M = XYZ_TO_SRGB / (XYZ_TO_SRGB @ WHITE_XYZ)[:, None]      # flash white -> (1, 1, 1)


def spectrum_from_psd(freq_per_T, psd, delta, T_um, blur_rel=0.02):
    """Relative spectral power reaching the camera at NM for a waveform PSD, at one delta (or an array of deltas).
    The PSD is integrated exactly over the frequency interval of each wavelength bin (lines are far narrower
    than a bin, so sampling it would alias): bin power = lambda / (delta T) * integral of S df.
    blur_rel is the relative spread of delta (source size, pixel extent, pose error)."""
    delta = np.atleast_1d(np.asarray(delta, float))
    freq_per_T = np.asarray(freq_per_T, float)
    width = np.gradient(freq_per_T)
    edges = np.r_[freq_per_T[0] - width[0] / 2, freq_per_T + width / 2]
    cp = np.r_[0.0, np.cumsum(psd * width)]
    lam_um = NM / 1000.0
    half = (NM[1] - NM[0]) / 2000.0
    f_hi = np.abs(delta)[:, None] * T_um / (lam_um[None, :] - half)
    f_lo = np.abs(delta)[:, None] * T_um / (lam_um[None, :] + half)
    power = np.interp(f_hi, edges, cp) - np.interp(f_lo, edges, cp)
    s = power * lam_um[None, :] / (np.maximum(np.abs(delta)[:, None], 1e-9) * T_um)
    if blur_rel > 0:
        x = np.log(NM)
        k = np.exp(-0.5 * ((x[:, None] - x[None, :]) / blur_rel) ** 2)
        k /= k.sum(0, keepdims=True)              # each source wavelength keeps its power
        s = s @ k.T
    return s


def rgb_from_spectrum(s):
    """Linear RGB (sRGB primaries, flash white = 1,1,1) of spectra s[..., len(NM)] times the flash."""
    xyz = (s * _E) @ _CMF
    return xyz @ _M.T



EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def rs_generator(n):
    g = [1]
    for k in range(n):
        out = [0] * (len(g) + 1)
        for i, c in enumerate(g):
            out[i] ^= c
            if c:
                out[i + 1] ^= EXP[LOG[c] + k]
        g = out
    return g


def rs_parity(data, g):
    n = len(g) - 1
    reg = [0] * n
    for d in data:
        fb = int(d) ^ reg[0]
        reg = reg[1:] + [0]
        if fb:
            for i in range(n):
                if g[i + 1]:
                    reg[i] ^= EXP[LOG[g[i + 1]] + LOG[fb]]
    return reg


G_PI, G_PO, G_IED = rs_generator(10), rs_generator(16), rs_generator(2)


def edc(data):
    reg = 0
    for byte in data:
        for k in range(7, -1, -1):
            top = (reg >> 31) & 1
            reg = ((reg << 1) & 0xFFFFFFFF) | ((int(byte) >> k) & 1)
            if top:
                reg ^= 0x80000011
    for _ in range(32):
        top = (reg >> 31) & 1
        reg = (reg << 1) & 0xFFFFFFFF
        if top:
            reg ^= 0x80000011
    return reg


def recording_rows(payload, lba):
    """208 x 182 bytes in recording order: 12 data rows then one PO row, per sector."""
    data = np.zeros((192, 172), np.uint8)
    for s in range(16):
        psn = lba + s + dvd.DATA_START_PSN
        ident = [0x00, (psn >> 16) & 255, (psn >> 8) & 255, psn & 255]
        head = ident + rs_parity(ident, G_IED) + [0] * 6
        main = payload[s * 2048:(s + 1) * 2048]
        crc = edc(head + [int(b) for b in main])
        frame = np.array(head + list(dvd.recorded(main, lba + s)) + [(crc >> k) & 255 for k in (24, 16, 8, 0)], np.uint8)
        data[12 * s:12 * (s + 1)] = frame.reshape(12, 172)
    po = np.array([rs_parity(data[:, c], G_PO) for c in range(172)], np.uint8).T
    full = np.vstack([data, po])
    rows = np.zeros((208, 182), np.uint8)
    for r in range(208):
        rows[r, :172] = full[r]
        rows[r, 172:] = rs_parity(full[r], G_PI)
    order = []
    for s in range(16):
        order += list(range(12 * s, 12 * (s + 1))) + [192 + s]
    return rows[order]



@lru_cache(maxsize=128)
def texture_table(spec):
    """261 sqrt-encoded uint8 RGB samples, using the release LUT convention."""
    sequence = np.frombuffer(bytes.fromhex(spec), np.uint8)
    col = (12 + np.arange(2048)) % 172
    q = np.broadcast_to(sequence[col % len(sequence)], (16, 2048)).copy()
    acc = 0
    for lba in (64000, 900000, 1700000):
        lbas = np.arange(lba, lba+16)
        payload = q ^ dvd.MASKS[((lbas + dvd.DATA_START_PSN) >> 4) & 15]
        levels, _ = efmplus.encode_rows(recording_rows(payload.ravel(), lba))
        x = levels.astype(np.float64)*2-1
        f = np.fft.rfftfreq(x.size)
        density = np.abs(np.fft.rfft(x))**2 / x.size * 2
        acc = acc + rgb_from_spectrum(spectrum_from_psd(f, density, np.linspace(0, 1.3, 261), .1333))
    encoded = np.uint8(np.clip(np.rint(np.sqrt(np.maximum(0, acc/3+.02))*255), 0, 255))
    return encoded
