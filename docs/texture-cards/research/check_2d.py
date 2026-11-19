"""Does the single-track incoherent sum in model.py match a real 2D far field of a patch?

Lays out real encoded tracks with the disc's own track-to-track shift (circumference mod the
channel grid, 35.1 bits more per track), renders r(x, y) with a groove and marks of a given
width, takes the 2D FFT and compares the along-track spectrum, summed over a radial band away
from f_r = 0 and the groove orders, with the analytic sum. Prints line ratios between textures
and the fraction of along-track line power that is track-coherent.
"""

import numpy as np

import common  # noqa: F401
from common import PITCH_UM, RUNS, T_UM
import data as D
import model as M
import spectra as S

SUB_Y = 16
TRACKS = 96
FRAMES = 6
R_MM = 40.0


def track_shift_bits(k):
    circ = 2 * np.pi * (R_MM * 1000 + k * PITCH_UM) / T_UM
    return int(np.sum([2 * np.pi * (R_MM * 1000 + j * PITCH_UM) / T_UM for j in range(k)]) % 1e9)


def patch(name, seed, width_um=0.35):
    """Mark mask (tracks x bits at 1 sample per channel bit, SUB_Y samples per track)."""
    nx = FRAMES * 1488
    m = np.zeros((TRACKS * SUB_Y, nx), np.float32)
    y = (np.arange(SUB_Y) - SUB_Y / 2 + 0.5) * PITCH_UM / SUB_Y
    inside = np.abs(y) < width_um / 2
    rng = np.random.default_rng(seed)
    lv = S.stream(name, seed, 0, True)
    for k in range(TRACKS):
        off = int(rng.integers(0, lv.size - nx))
        # Each track starts on a frame boundary of its own random point of the stream, then the
        # real shift between tracks puts the frames at a different x.
        off -= off % 1488
        shift = track_shift_bits(k) % 1488
        seg = np.roll(lv[off:off + nx], shift)
        m[k * SUB_Y:(k + 1) * SUB_Y][inside] = seg == 0
    return m


def far(name, seed):
    m = patch(name, seed)
    r = 1.0 + (0.5 * np.exp(0.7j) - 1) * m
    F = np.fft.fft2(r) / r.size
    P = F.real ** 2 + F.imag ** 2
    fx = np.fft.fftfreq(r.shape[1], T_UM)
    fy = np.fft.fftfreq(r.shape[0], PITCH_UM / SUB_Y)
    return P, fx, fy


def main():
    print("numeric 2D FFT (96 tracks, 6 frames) against the analytic single-track table")
    p = M.full(M.M4, [M.SPEC[k][0] for k in M.M4])
    p["w3"] = p["w4"] = p["w5"] = 1.0
    p["log_se"] = np.log(0.005)
    p["log_sig_d"] = np.log(0.003)
    tab = M.tables(p)
    for name, P_um in (("A5", 0.854), ("66", 1.065), ("B9", 1.420), ("92", 2.131)):
        P, fx, fy = far(name, 7)
        fline = 1 / P_um
        band_y = (np.abs(fy) > 0.3) & (np.abs(fy) < 1.0)
        # radial cuts away from the groove's f_r = 1 / pitch = 1.34
        ix = np.abs(np.abs(fx) - fline) < 0.03 * fline
        line = P[np.ix_(band_y, ix)].sum()
        all_y = P[:, ix].sum()
        off = (np.abs(np.abs(fx) - fline) > 0.1 * fline) & (np.abs(fx) > 0.05) & (np.abs(fx) < 2.5)
        pedestal = np.median(P[np.ix_(band_y, off)].sum(0))
        t = D.PALETTE.index(name)
        k = (np.abs(M.F_GRID - fline) < 0.03 * fline)
        analytic = tab[t, k, :2].mean(1).sum() * M.DF          # f_r 0-0.6 around the band
        print(f"{name:3s} P {P_um:.3f}  numeric line power (0.3<|fr|<1) {line:.3e} of all fr {all_y:.3e}  "
              f"analytic line {analytic:.3e}  ratio {line / analytic:.3e}  "
              f"numeric line / pedestal bin {line / max(pedestal, 1e-12):.0f}")


if __name__ == "__main__":
    main()
