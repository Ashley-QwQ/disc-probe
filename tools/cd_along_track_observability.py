"""How much can a CD timing ladder tell about the along-track constant?

The ladder fits u = r0/b and v = p/b to phases

    phi(X) = Theta(n_X) - Theta(n_ref) + c,   Theta(n) = 2 n / (S + u),  S = sqrt(u^2 + v n / pi)

with n = ((LBA+1)*98 + 108)*588 for a CD data track (cd.read_end_bits). Any constant offset
delta in the channel bit at which a read really completes, or any offset in where the burner
put sector 0 along the groove, enters the model only as n -> n + delta.  This script measures
how well the ladder can tell such a shift from a change of r0:

  * simulate noiseless phases for a known (r0, p) with an offset delta frames,
  * fit (u, v, c) exactly as geo.Ladder.fit does,
  * report the fitted r0, the residual rms, and the shift the fit absorbed.

The along-track constant that `--along-track-frames d` carries is the same delta, applied to
the preset by u'^2 = u^2 - v*d*FRAME_BITS/pi (disexport.py:136).  That is a change of the
preset's start radius by

    d(r0^2) = -p * d * 588 * b / pi        ->   dr0 = -1.66 nm per frame at r0 = 25 mm.

so 206 frames (the GH70N value) is 0.34 um of inner radius.  The sign convention is the one
the fit sees: data `d` frames further along the groove fits with r0 **larger** by 1.66 nm per
frame, and the same `d` handed to `--along-track-frames` moves the preset back down by that
much.  The question this script answers is how large that is against the ladder's own
resolution.

    python tools/cd_along_track_observability.py
    python tools/cd_along_track_observability.py --frames -400 400 41 --noise-deg 0.25
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe import cd
from discprobe.calib import theta


def n_end(lbas, tail_frames: float = cd.READ_TAIL_FRAMES) -> np.ndarray:
    return ((np.asarray(lbas, dtype=float) + 1.0) * cd.FRAMES_PER_SECTOR + tail_frames) * cd.FRAME_BITS


def ladder_lbas(n: int = 30, lo: int = 5000, hi: int = 150000) -> np.ndarray:
    """A grid of targets like geo's candidate list (no ladder-ordering needed here)."""
    return np.unique(np.linspace(lo, hi, n).astype(np.int64))


def fit_uvc(n, y, sigma_deg, u0, v0, sig_u, sig_v, iters: int = 25):
    """geo.Ladder.fit, without the ladder bookkeeping."""
    u, v, c = u0, v0, 0.0
    w = 1.0 / np.radians(np.full(len(n), sigma_deg))
    for _ in range(iters):
        model = theta(n, u, v) - theta(n[0], u, v) + c
        du, dv = _dtheta(n, u, v)
        du0, dv0 = _dtheta(n[0], u, v)
        J = np.column_stack([du - du0, dv - dv0, np.ones_like(n)]) * w[:, None]
        r = (y - model) * w
        J = np.vstack([J, [1 / sig_u, 0, 0], [0, 1 / sig_v, 0]])
        r = np.concatenate([r, [(u0 - u) / sig_u, (v0 - v) / sig_v]])
        sc = np.sqrt((J ** 2).sum(axis=0))
        step, *_ = np.linalg.lstsq(J / sc, r, rcond=None)
        step /= sc
        u, v, c = u + step[0], v + step[1], c + step[2]
        if np.all(np.abs(step * sc) < 1e-12):
            break
    model = theta(n, u, v) - theta(n[0], u, v) + c
    res = y - model
    chi2 = float(np.sum((res * w) ** 2))
    dof = max(1, len(n) - 3)
    cov = np.linalg.inv((J / sc).T @ (J / sc)) / np.outer(sc, sc)
    return dict(u=u, v=v, c=c, cov=cov * max(1.0, chi2 / dof), chi2_dof=chi2 / dof,
                rms_deg=float(np.degrees(np.sqrt(np.mean(res ** 2)))))


def _dtheta(n, u, v):
    s = np.sqrt(u * u + v * np.asarray(n, dtype=float) / math.pi)
    # dTheta/du and dTheta/dv of Theta = 2 n / (S + u); dS/du = u/S, dS/dv = n/(2 pi S).
    ds_du, ds_dv = u / s, np.asarray(n, dtype=float) / (2.0 * math.pi * s)
    den = (s + u) ** 2
    return -2.0 * n * (ds_du + 1.0) / den, -2.0 * n * ds_dv / den


def simulate(delta_frames: float, r0_mm: float, pitch_um: float, noise_deg: float, seed: int = 0):
    b = cd.BIT_NM * 1e-6
    u_t, v_t = r0_mm / b, pitch_um * 1e-3 / b
    lbas = ladder_lbas()
    n = n_end(lbas)
    delta_bits = delta_frames * cd.FRAME_BITS
    # True angles: the data sits delta_bits further along the groove than the model assumes.
    true = theta(n + delta_bits, u_t, v_t) - theta(n[0] + delta_bits, u_t, v_t)
    # Only the phase modulo one turn is measured.  The ladder unwraps with the nominal model,
    # which is what geo does for its first rung.
    u0, v0 = 25.0 / b, 1.6e-3 / b
    pred = theta(n, u0, v0) - theta(n[0], u0, v0)
    measured = np.mod(true, 2 * math.pi)
    k = np.round((pred - measured) / (2 * math.pi))
    y = measured + 2 * math.pi * k
    if noise_deg:
        rng = np.random.default_rng(seed)
        y = y + np.radians(noise_deg) * rng.standard_normal(len(y))
    fit = fit_uvc(n, y, noise_deg or 0.2, u0, v0, 0.08 * u0, 0.15 * v0)
    fit["r0_mm"] = fit["u"] * b
    fit["pitch_um"] = fit["v"] * b * 1e3
    fit["dr0_um"] = (fit["r0_mm"] - r0_mm) * 1e3
    fit["sigma_u_mm"] = math.sqrt(max(fit["cov"][0, 0], 0.0)) * b
    # What `--along-track-frames delta` would do to the preset fitted from this disc: the
    # same number moves it back down, which is the operation being demonstrated.
    u_shift = math.sqrt(max(fit["u"] ** 2 - fit["v"] * delta_frames * cd.FRAME_BITS / math.pi, 0.0))
    fit["r0_after_export_mm"] = u_shift * b
    return fit


def scan(frames, **kw):
    rows = []
    for d in frames:
        f = simulate(d, **kw)
        rows.append((d, f["r0_mm"], f["dr0_um"], f["pitch_um"], f["rms_deg"], f["sigma_u_mm"],
                     f["r0_after_export_mm"]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--r0-mm", type=float, default=25.0)
    ap.add_argument("--pitch-um", type=float, default=1.6)
    ap.add_argument("--noise-deg", type=float, default=0.0,
                    help="per-rung phase noise (0 = noiseless; a real CD rung is 0.2-0.9 deg)")
    ap.add_argument("--seed", type=int, default=0,
                    help="random seed for --noise-deg (default 0: the same noise every run)")
    ap.add_argument("--frames", type=float, nargs="+", default=[-2000, -400, -100, 0, 100, 206, 400, 2000],
                    help="along-track offsets to try, in frames")
    a = ap.parse_args()

    b = cd.BIT_NM * 1e-6
    print(f"CD: b {cd.BIT_NM:.2f} nm, one frame {cd.FRAME_BITS * b:.6f} mm of track, "
          f"r0 {a.r0_mm} mm, pitch {a.pitch_um} um")
    print(f"nominal u {a.r0_mm / b:.0f}, v {a.pitch_um * 1e-3 / b:.4f}")
    slope_nm = a.pitch_um * 1e-3 * cd.FRAME_BITS * b / math.pi / (2 * a.r0_mm) * 1e6
    print(f"analytic: the ladder absorbs {slope_nm:+.4f} nm of r0 per frame "
          f"({slope_nm * 206 / 1e3:.3f} um over 206 frames); --along-track-frames removes it again")
    print("analytic rotation of the DIS model for d frames: "
          f"{2 * math.pi * slope_nm * 1e-6 / (a.pitch_um * 1e-3) * 180 / math.pi:.2f} deg per frame "
          "at 25 mm, scaling as 1/r\n")

    rows = scan(a.frames, r0_mm=a.r0_mm, pitch_um=a.pitch_um, noise_deg=a.noise_deg, seed=a.seed)
    hdr = ("d frames   fitted r0 mm   dr0 um   pitch um   rms deg   sigma_r0 um   r0 after export mm")
    print(hdr)
    print("-" * len(hdr))
    for d, r0, dr0, p, rms, su, rx in rows:
        print(f"{d:8.1f}   {r0:12.6f}  {dr0:+8.3f}  {p:8.4f}  {rms:8.4f}  {su * 1e3:11.3f}  {rx:18.6f}")

    # Sensitivity: how much does the fit's r0 move per frame of delta, and how does the
    # residual grow?  The two together say whether timing can see the offset at all.
    u_of_d = np.array([r[2] for r in rows])
    rms_of_d = np.array([r[4] for r in rows])
    # Beyond roughly half the ladder spacing the turns can no longer be counted, the fit
    # falls back to the prior, and r0 stops moving; those rows say nothing about the slope.
    usable = rms_of_d < 1.0
    slope_fit_nm = None
    if usable.sum() >= 2:
        A = np.c_[np.ones(int(usable.sum())), np.array([r[0] for r in rows])[usable]]
        coef, *_ = np.linalg.lstsq(A, u_of_d[usable], rcond=None)
        slope_fit_nm = coef[1] * 1e3                     # nm of r0 per frame
        print(f"\nfitted dr0/dframe = {slope_fit_nm:+.4f} nm/frame over the {int(usable.sum())} offsets "
              f"that still unwrap (analytic {slope_nm:+.4f})")
    else:
        print(f"\nfewer than two offsets still unwrap, no fitted slope (analytic {slope_nm:+.4f} nm/frame)")
    print(f"residual rms over the whole scan: {rms_of_d.min():.4f} .. {rms_of_d.max():.4f} deg"
          f"{'' if usable.all() else '; the rest lost the turn count and fit the prior instead'}")
    # What the ladder pins down is the combination r0 + (dr0/frame) * d: every offset that
    # still unwraps fits with rms 0 and a different r0, so the split between the two is
    # arbitrary and the constant cannot be read off timing.
    per_frame = abs(slope_fit_nm if slope_fit_nm is not None else slope_nm)
    print(f"\n=> the ladder measures r0 + (dr0/frame) * d and nothing that splits the two:")
    print(f"   every d that still unwraps fits equally well with r0 moved by {per_frame:.3f} nm per frame,")
    print(f"   and the residuals do not move.  A 206-frame value is {206 * per_frame / 1000:.2f} um of r0")
    print("   -- a whole DIS radial-line twist at 25-58 mm -- so C has to come from somewhere")
    print("   other than timing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
