"""Measure how far a burned grid's spokes have wound, from a photograph.

The preset that drew a grid onto a Blu-ray puts a spoke every 30 degrees. If the
geometry the renderer used differs from the disc's own spiral, the spokes do not
land where the design says: they wind into a tight spiral, are no longer radial,
and the letter F smears away. Rotational features (rings) survive; angular ones
do not, so the winding is the only visible trace of the mismatch.

This reads a photograph, finds the 12-fold spoke pattern at each radius, unwraps
its phase, and fits the two errors that can produce it:

    dtheta(r) = 2*pi*(r0_model - r0_disc)*(r - r0)/(p*r)      inner radius off
              + 2*pi*(r - r0)*(1/p_model - 1/p_disc)          track pitch off

The first flattens out towards the rim (the lever arm is (r - r0)/r); the second
keeps growing. Their shapes differ enough that a fit over 25 mm of radius can
separate them, which turns a photograph of one disc into an absolute measurement
of that disc's inner radius and track pitch.

Usage:
    python tools/bd_spoke_shear.py PHOTO --r-in 25 --r-out 57 [--centre X Y]

Exit status is 0 when a phase curve was measured, 1 when the pattern was not
found well enough to trust.
"""

from __future__ import annotations

import argparse
import math
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(
    __import__("os").path.abspath(__file__))))

SPOKES = 12                 # one every 30 degrees in the grid design
FRAME_MM = 588 * 277.66208524226016e-6


def load_gray(path):
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.float64) / 255.0


def find_centre(image, guess_px_per_mm=16.0):
    """Centre and scale from the disc's own outer edge."""
    from discprobe import scan

    try:
        outer, _hole = scan.locate_disc(image, guess_px_per_mm)
    except RuntimeError:
        return None
    return (float(outer["cx"]), float(outer["cy"])), float(outer["rx"]) / scan.DISC_RADIUS_MM


def spoke_phase(image, centre, scale, radii, n_theta=3600):
    """Phase of the 12-fold pattern at each radius, radians."""
    from discprobe import scan

    samples, _theta = scan.polar_rings(image, centre[0], centre[1], scale, scale,
                                       np.asarray(radii, dtype=np.float64),
                                       n_theta=n_theta)
    phases, strengths = [], []
    for line in samples:
        line = np.nan_to_num(np.asarray(line, dtype=np.float64))
        line = line - line.mean()
        spectrum = np.fft.fft(line)
        component = spectrum[SPOKES] * 2.0 / n_theta
        phases.append(math.atan2(component.imag, component.real))
        strengths.append(abs(component) / (np.abs(line).mean() + 1e-12))
    return np.asarray(phases), np.asarray(strengths)


def unwrap_phase(phases, strengths, floor):
    """Unwrap only where the pattern is strong enough to carry an angle."""
    good = strengths > floor
    if good.sum() < 8:
        return None, good
    out = np.array(phases, dtype=np.float64)
    out[~good] = np.nan
    # Fill gaps by interpolating the measured phases, then unwrap once.
    index = np.arange(len(out))
    out = np.interp(index, index[good], out[good])
    return np.unwrap(out), good


def fit_shear(radii, turns, r0_model, pitch_model, iterations=60):
    """Least squares for (delta r0, relative pitch error) in radians of phase."""
    r = np.asarray(radii, dtype=np.float64)
    y = np.asarray(turns, dtype=np.float64) * 2.0 * math.pi

    def column_r0(delta_r0):
        return 2.0 * math.pi * delta_r0 * (r - r0_model) / (pitch_model * r)

    def column_p(relative):
        return 2.0 * math.pi * (r - r0_model) * relative / pitch_model

    delta_r0, relative = 0.0, 0.0
    scale_r0, scale_p = 0.05, 1e-3          # mm, dimensionless: start small
    for _ in range(iterations):
        base = column_r0(delta_r0) + column_p(relative)
        jac = np.column_stack([column_r0(1.0), column_p(1.0)])
        residual = y - base
        step, *_ = np.linalg.lstsq(jac, residual, rcond=None)
        delta_r0 += step[0]
        relative += step[1]
        if abs(step[0]) < 1e-6 and abs(step[1]) < 1e-12:
            break
    model = column_r0(delta_r0) + column_p(relative)
    residual = y - model
    dof = max(1, len(y) - 2)
    variance = float(residual @ residual) / dof
    covariance = variance * np.linalg.pinv(jac.T @ jac)
    return delta_r0, relative, math.sqrt(covariance[0, 0]), math.sqrt(covariance[1, 1]), \
        float(np.sqrt(np.mean(residual ** 2))), float(np.sqrt(np.mean(y ** 2)))


def design_masks(radii, n_theta, r_min, r_max, spacing, line, letter=(-3.0, 33.0, 1.2)):
    """The parts of the grid design, in polar coordinates: rings, spokes, grid, F."""
    x, y, angle = polar_xy(radii, n_theta)
    half = line / 2.0
    near = lambda v: np.abs((v + spacing / 2.0) % spacing - spacing / 2.0) < half
    rings = np.abs(r_range(radii, n_theta) - np.round(r_range(radii, n_theta) / spacing) * spacing) < half
    grid = near(x) | near(y)
    spokes = np.zeros_like(rings)
    for spoke in range(0, 360, 360 // SPOKES):
        offset = np.abs(((angle - spoke + 180.0) % 360.0) - 180.0)
        spokes |= (np.radians(offset) * r_range(radii, n_theta) < max(0.2, half)) & (offset < 90.0)
    fx, fy, stroke = letter
    mark = np.zeros_like(rings)
    mark |= (x >= fx) & (x < fx + stroke) & (y >= fy) & (y < fy + 10.0)
    mark |= (x >= fx) & (x < fx + 6.0) & (y >= fy + 10.0 - stroke) & (y < fy + 10.0)
    mark |= (x >= fx) & (x < fx + 4.5) & (y >= fy + 5.0 - stroke / 2) & (y < fy + 5.0 + stroke / 2)
    inside = (r_range(radii, n_theta) >= r_min) & (r_range(radii, n_theta) <= r_max)
    return {"rings": rings & inside, "spokes": spokes & inside,
            "cartesian grid": grid & inside, "letter F": mark & inside}


def polar_xy(radii, n_theta):
    theta = np.linspace(0.0, 360.0, n_theta, endpoint=False)
    r, t = np.meshgrid(np.asarray(radii, dtype=np.float64), np.radians(theta), indexing="ij")
    return r * np.cos(t), r * np.sin(t), theta


def r_range(radii, n_theta):
    return np.repeat(np.asarray(radii, dtype=np.float64)[:, None], n_theta, axis=1)


def detrended_darkness(image, centre, scale, radii, n_theta):
    """Darkness with the smooth brightness trend removed, in units of its own sigma."""
    from discprobe import scan

    samples, _ = scan.polar_rings(image, centre[0], centre[1], scale, scale,
                                  np.asarray(radii, dtype=np.float64), n_theta=n_theta)
    dark = 1.0 - np.nan_to_num(np.asarray(samples, dtype=np.float64))
    try:
        from scipy import ndimage
    except ImportError:
        dark = dark - dark.mean(axis=1, keepdims=True)
    else:
        dark = dark - ndimage.uniform_filter(dark, size=(41, 1), mode="nearest")
        dark = dark - ndimage.uniform_filter(dark, size=(1, 61), mode="nearest")
    sigma = float(dark.std()) or 1.0
    return dark / sigma


def element_contrast(image, centre, scale, radii, masks, step_deg=0.5):
    """How much darker the design's dark cells are than its light ones, per element."""
    n_theta = masks["spokes"].shape[1]
    dark = detrended_darkness(image, centre, scale, radii, n_theta)
    rows = []
    for name, mask in masks.items():
        if not mask.any():
            rows.append((name, 0.0, 0.0, 0.0))
            continue
        best = (-9.0, 0.0)
        for k in range(int(360.0 / step_deg)):
            shifted = np.roll(mask, int(round(k * step_deg / 360.0 * n_theta)), axis=1)
            value = float(dark[shifted].mean() - dark[~shifted].mean())
            if value > best[0]:
                best = (value, k * step_deg)
        rows.append((name, best[0], best[1], float(mask.mean())))
    return rows


def harmonic_spectrum(image, centre, scale, radii, n_theta=1440, upto=20):
    """Mean angular-harmonic amplitude: is the spoke order standing out at all?"""
    from discprobe import scan

    samples, _ = scan.polar_rings(image, centre[0], centre[1], scale, scale,
                                  np.asarray(radii, dtype=np.float64), n_theta=n_theta)
    lines = np.nan_to_num(np.asarray(samples, dtype=np.float64))
    lines = lines - lines.mean(axis=1, keepdims=True)
    spectra = np.abs(np.fft.rfft(lines, axis=1)).mean(axis=0)
    return spectra[:upto + 1]


def band_phase(radii, phases, strengths, centre_scale=None, bands=6):
    """Mean 12-fold phase and its coherence in equal-width radial bands."""
    edges = np.linspace(radii[0], radii[-1], bands + 1)
    out = []
    for low, high in zip(edges[:-1], edges[1:]):
        keep = (radii >= low) & (radii < high)
        if not keep.any():
            continue
        z = np.mean(np.exp(1j * phases[keep]))
        out.append((low, high, abs(z), math.degrees(math.atan2(z.imag, z.real)) / SPOKES))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photo")
    parser.add_argument("--r-in", type=float, default=25.0)
    parser.add_argument("--r-out", type=float, default=57.0)
    parser.add_argument("--steps", type=int, default=160)
    parser.add_argument("--centre", nargs=2, type=float)
    parser.add_argument("--scale", type=float, help="pixels per mm (default: from the outer edge)")
    parser.add_argument("--guess-px-per-mm", type=float, default=16.0,
                        help="rough scale, only used to find the disc edge (default 16)")
    parser.add_argument("--strength", type=float, default=0.02,
                        help="minimum 12-fold amplitude, relative to the mean (default 0.02)")
    parser.add_argument("--r0-model", type=float, default=24.040539)
    parser.add_argument("--pitch-model", type=float, default=0.320,
                        help="micrometres the preset implied (default 0.320)")
    parser.add_argument("--out")
    parser.add_argument("--bands", type=int, default=6,
                        help="radial bands to report the phase coherence in (default 6)")
    parser.add_argument("--harmonics", action="store_true",
                        help="print the mean angular harmonic amplitude, to see whether the "
                             "spoke order stands out above its neighbours")
    parser.add_argument("--contrast", action="store_true",
                        help="compare each part of the design with the photograph instead of "
                             "measuring the winding")
    parser.add_argument("--design-r-min", type=float, default=26.0)
    parser.add_argument("--design-r-max", type=float, default=56.5)
    parser.add_argument("--design-spacing", type=float, default=5.0,
                        help="millimetres between the design's rings and grid lines (default 5)")
    parser.add_argument("--design-line", type=float, default=0.45,
                        help="design line width in millimetres (default 0.45)")
    args = parser.parse_args(argv)

    image = load_gray(args.photo)
    if args.centre and args.scale:
        centre, scale = tuple(args.centre), args.scale
    else:
        located = find_centre(image, args.guess_px_per_mm)
        if located is None:
            print("could not find the disc's outer edge in this photograph")
            return 1
        centre, scale = located
        if args.centre:
            centre = tuple(args.centre)
        print(f"disc centre {centre[0]:.0f} {centre[1]:.0f} px, {scale:.2f} px/mm")
    if args.scale:
        scale = args.scale

    radii = np.linspace(args.r_in, args.r_out, args.steps)

    if args.harmonics:
        spectrum = harmonic_spectrum(image, centre, scale, radii)
        base = spectrum[1] or 1.0
        print("harmonic amplitude relative to the first:")
        for order in range(1, len(spectrum)):
            mark = "  <- the spoke order" if order == SPOKES else ""
            print(f"  {order:2d}: {spectrum[order] / base:.3f}{mark}")
        near = spectrum[max(1, SPOKES - 1):SPOKES + 2] / base
        print(f"the spoke order is {near[1]:.2f} against neighbours "
              f"{near[0]:.2f} and {near[2]:.2f}: "
              f"{'it stands out' if near[1] > 1.5 * max(near[0], near[2]) else 'it does not stand out'}")
        return 0

    if args.contrast:
        # The spokes may be on the disc and still too faint to see: this says how
        # faint, element by element, so "invisible" can be told from "missing".
        masks = design_masks(radii, 1440, args.design_r_min, args.design_r_max,
                             args.design_spacing, args.design_line)
        print(f"{'element':16s} {'area':>6s} {'dark minus light':>18s} {'best rotation':>14s}")
        for name, value, rotation, area in element_contrast(image, centre, scale, radii, masks):
            print(f"{name:16s} {area * 100:5.1f}% {value:+18.3f} {rotation:13.1f} deg")
        print("values are in sigma of the photograph's own noise: below about 0.05 the "
              "element cannot be seen, whether or not it was burned")
        return 0

    phases, strengths = spoke_phase(image, centre, scale, radii)
    print(f"12-fold amplitude: median {np.median(strengths):.3f}, "
          f"best {strengths.max():.3f} at r {radii[int(np.argmax(strengths))]:.1f} mm")

    for low, high, coherence, mean in band_phase(radii, phases, strengths, bands=args.bands):
        print(f"  {low:5.1f}-{high:5.1f} mm: coherence {coherence:.2f}, "
              f"mean phase {mean:+6.1f} deg")
    unwrapped, good = unwrap_phase(phases, strengths, args.strength)
    if unwrapped is None:
        print("no radius showed a 12-fold pattern strong enough to measure a phase")
        return 1
    turns = unwrapped / (2.0 * math.pi)
    turns = turns - turns[0]
    keep = good.copy()
    keep[:2] = False
    keep[-2:] = False
    if keep.sum() < 8:
        print("too few radii carried the pattern")
        return 1

    pitch_mm = args.pitch_model * 1e-3
    delta_r0, relative, sig_r0, sig_p, rms, spread = fit_shear(
        radii[keep], turns[keep], args.r0_model, pitch_mm)
    print(f"winding over {radii[keep][-1] - radii[keep][0]:.1f} mm: "
          f"{turns[keep][-1] - turns[keep][0]:+.1f} turns")
    print(f"inner radius: model {args.r0_model:.4f} mm minus {delta_r0 * 1000:+.1f} um "
          f"(1 sigma {sig_r0 * 1000:.1f} um) -> {args.r0_model - delta_r0:.4f} mm")
    print(f"track pitch:  model {args.pitch_model:.4f} um times {1 + relative:.6f} "
          f"(1 sigma {sig_p:.1e}) -> {args.pitch_model * (1 + relative):.4f} um")
    print(f"fit rms {rms:.2f} rad against a {spread:.0f} rad peak: "
          f"{'a real phase curve' if spread > 6 * rms else 'not distinguishable from noise'}")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("radius_mm,strength,turns\n")
            for r_mm, strength, turn, used in zip(radii, strengths, turns, keep):
                handle.write(f"{r_mm:.3f},{strength:.4f},{turn:.4f},{1 if used else 0}\n")
        print(f"phase curve written to {args.out}")
    return 0 if spread > 6 * rms else 1


if __name__ == "__main__":
    raise SystemExit(main())
