"""Second-generation pattern for reading a Blu-ray's track pitch off a photograph.

The first disc taught three things the hard way, and this file is built around them.

1. The picture is torn, not smeared.  A disc does not record a pixel grid: the payload is
   a continuous 1-7PP channel stream along the spiral, and DIS samples the picture once per
   payload byte, which is about 1.1 um of track - 0.0016 deg at 40 mm.  Nothing about that
   limits a thin line.  What kills an angular feature is the pitch error: the picture is
   placed by the geometry the preset assumes, while the disc really turns by
        d(theta)/dr = 2*pi*eps/p
   so with eps = 0.11 per cent the whole picture is sheared by 3.4 turns per millimetre of
   radius, and about 105 turns from the inner to the outer edge.  A 15-degree spoke becomes
   2 520 overlapping involutes and averages to grey.  (For the record, one sector is
   2.240 mm = 3.2 deg at 40 mm, and a 32-sector recording unit is 102.7 deg.)  What survives
   is an angular feature wider than the twist across it, and a circle, because r is constant
   along it.

2. A radial edge turns into a spiral when the pitch is wrong, and the number of
   turns is the measurement:

       d(theta)/dr = 2*pi*eps/p        eps = (p_assumed - p_true)/p_true
       turns over the picture      = 2*pi*(r_out - r_in)*eps/p / (2*pi)

   With 95 300 tracks between 5 and 58 mm, one turn of twist is 1e-5 of pitch,
   so counting turns to a tenth lands near 1 ppm.  Nothing in that formula needs
   the absolute length of anything, only the radius in mm, and a 1 % error in
   that radius is a 1 % error on an already tiny number.

3. The centre has to be right to a few micrometres per millimetre of radius, or
   the twist is not measurable at all.  The first photograph was unwrapped about
   a centre 2.75 mm out, which tilts every ring into a diagonal and made a
   perfectly good disc look blank.  The rings in the design exist to fix that:
   their residuals against a circle give the centre, and the camera scale comes
   from the disc's own edge.

This module both draws the second-generation picture and measures a photograph of
it, and it can render its own synthetic disc so the measurement can be checked
against a known answer before anyone burns anything.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe import scan                                    # noqa: E402

# ---------------------------------------------------------------- the design

PICTURE_MM = 116.0      # picture_design fits a picture's longest side to this
RINGS_MM = (26.0, 40.0, 55.0)
RING_HALF_MM = 0.50     # 0.6 mm wide: wide enough to see, narrow enough to localise
WEDGE_DEG = 60.0        # 60 deg at 25 mm is 12 recording units, above the smear
WEDGE_RADII = (24.6, 58.2)
PITCH_ASSUMED_MM = 0.32e-3   # the pitch a preset is built with; the twist measures what it really is
SPIRALS = 2             # counter-rotating pair, for a scale-free cross-check
WEDGES = ((0.0, 90.0), (150.0, 40.0))   # (centre, width) in degrees; unequal on purpose, see design()


def design(n: int = 2320, rings=RINGS_MM, ring_half=RING_HALF_MM,
           wedges=WEDGES) -> np.ndarray:
    """Dark-on-light boolean picture, longest side PICTURE_MM, centred.

    Two wedges, 90 degrees wide at 0 and 40 degrees wide at 150, and three rings 1 mm wide at 26,
    40 and 55 mm.

    Two wedges, 90 degrees and 40 degrees, not three equal ones. Equal wedges repeat every 120
    degrees, and the twist this disc has accumulated (0.35 turns is 126 degrees) sits almost exactly
    on that period, so a symmetric design would read it as nearly zero. Three unequal wedges are
    worse than they look as well: dark widths 70-60-50 leave light gaps 50-60-70, so a 60 degree
    turn plus a contrast inversion lands close to the original. 90 and 40 have no such partner.

    The wedges are wide on purpose. A disc burned with a pitch that is off by a fraction of a per
    cent twists the picture by a few turns per millimetre of radius (0.11 per cent is 3.4 turns per
    mm), so any angular feature that is narrow in angle is torn into a fine spiral and averages out
    to grey. What survives is a feature whose angular width covers the twist across it, which is why
    the wedges are 60 degrees and the old 15-degree spokes were not.

    The rings are circles, and a circle is the one shape a rotation cannot disturb: r is constant
    along them, so they come out as circles whatever the twist. They are also the scale: their radii
    barely move when the pitch is wrong (10 ppm moves the outermost ring by 0.24 um), so their
    spacing in a photograph measures millimetres per pixel.

    Three rings, not nine: more rings put a fine radial grating into the picture and a pitch error
    that slides the pattern by one ring spacing matches almost as well as the truth.
    """
    out = np.zeros((n, n), bool)
    step = max(1, min(n, 4_000_000 // max(n, 1)))     # keep each block near 4 megapixels
    xs = (np.arange(n) + 0.5) * (PICTURE_MM / n) - PICTURE_MM / 2.0
    for row in range(0, n, step):
        rows = np.arange(row, min(row + step, n))
        yy = (rows + 0.5) * (PICTURE_MM / n) - PICTURE_MM / 2.0
        x = xs[None, :]
        y = yy[:, None]
        r = np.hypot(x, y)
        theta = np.degrees(np.arctan2(y, x)) % 360.0
        block = np.zeros((rows.size, n), bool)
        for ring in rings:
            block |= np.abs(r - ring) <= ring_half
        mark = (r >= WEDGE_RADII[0]) & (r <= WEDGE_RADII[1])
        for centre, width in wedges:
            block |= (np.abs(((theta - centre + 180.0) % 360.0) - 180.0) <= width / 2.0) & mark
        out[row:row + rows.size] = block
    return out


DPI = 2400.0


def pixels_for_dpi(dpi: float = DPI) -> int:
    return int(round(PICTURE_MM / 25.4 * dpi))


def save_design(path: str, n: int | None = None) -> str:
    """Write the picture as a one-bit PNG.  n defaults to 2400 dpi over PICTURE_MM."""
    if n is None:
        n = pixels_for_dpi()
    # design() is True where the disc must be dark, and PIL's mode "1" draws True as white,
    # so invert: black pixels are the burned pattern, which is what the first disc used.
    Image.fromarray(~design(n)).save(path)     # bool -> mode "1", one bit per pixel
    return path


# ---------------------------------------------------------- synthetic discs

def render(eps: float = 0.0, r_in_mm: float = 24.0, pitch_um: float = 0.32,
           n: int = 900, noise: float = 0.0, seed: int = 0) -> np.ndarray:
    """A photograph-like picture of the design, burned with a wrong pitch.

    eps is (p_assumed - p_true)/p_true, applied the way a real disc applies it:
    the sector that lands at radius r was laid out at r_assumed, so the picture
    points show up rotated by 2*pi*(r - r_in)*eps/p_true.
    """
    half = 60.0
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    x = (xx + 0.5) * (2 * half) / n - half
    y = (yy + 0.5) * (2 * half) / n - half
    r = np.hypot(x, y)
    theta = np.arctan2(y, x)
    r_assumed = np.where(r > 0, r * (1.0 - eps), r)
    turn = 2.0 * math.pi * (r_assumed - r_in_mm) * eps / (pitch_um * 1e-3)
    theta_src = theta + turn
    xs = r_assumed * np.cos(theta_src)
    ys = r_assumed * np.sin(theta_src)
    # dark features on a light disc, light background: the rim has to be visible
    # or the centre fit has nothing to start from
    pic = ~design(max(64, int(n * PICTURE_MM / (2 * half))))
    # design() puts pixel i at (i + 0.5)*step - half, so the index for x is (x + half)/step - 0.5.
    # Without the half pixel the picture sits 0.067 mm off the rim that the centre fit locks onto.
    px = (xs + PICTURE_MM / 2) / PICTURE_MM * pic.shape[0] - 0.5
    py = (ys + PICTURE_MM / 2) / PICTURE_MM * pic.shape[1] - 0.5
    inside = (px >= 0) & (px < pic.shape[0] - 1) & (py >= 0) & (py < pic.shape[1] - 1)
    out = np.full((n, n), 0.10)
    # The rim sits at 59 mm, not 60: at 60 it would be tangent to the frame on all four sides, the
    # centre fit would find no edge there, and it would lock onto the frame instead of the disc.
    out[r < 59.0] = 0.82
    out[inside] = pic[py[inside].astype(int), px[inside].astype(int)]
    out = ndimage.gaussian_filter(out, 1.2 * n / 900)
    if noise:
        out += np.random.default_rng(seed).normal(0, noise, out.shape)
    return np.clip(out, 0, 1)


# ------------------------------------------------------------- the measurement

def find_centre(img: np.ndarray, guess=None, scale=None, iterations: int = 14, rings: bool = True,
                fixed_scale: bool = False):
    """Centre from the rim, then refined until every ring is a circle."""
    if guess is None:
        try:
            # locate_disc needs a scale to know where the rim is; the caller's is a measurement, so
            # use it when there is one. Without one, take what the frame allows: a picture of a whole
            # disc has its rim at 60 mm from the centre, so half the short side is 60 mm of disc plus
            # whatever margin the photographer left. The old code assumed 16 px/mm and, on a
            # 15 px/mm picture, looked for a rim outside the frame and put the centre 200 px away.
            want = float(scale) if scale is not None else 0.5 * min(img.shape) / 60.0
            outer, _ = scan.locate_disc(img, want)
            cx, cy = float(outer["cx"]), float(outer["cy"])
            if scale is None:                 # a scale that was given is a measurement, not a guess
                scale = float(outer["rx"]) / 60.0
        except Exception:                     # a picture without a clear rim: assume it fills the frame
            cx, cy = (img.shape[1] - 1) / 2.0, (img.shape[0] - 1) / 2.0
            if scale is None:
                scale = 0.5 * min(img.shape) / 60.0
    else:
        cx, cy = map(float, guess)
        scale = float(scale or 16.0)
    if not fixed_scale:                       # the rim is measured once: it does not move with the centre
        edge = []
        for a in np.linspace(0, 2 * math.pi, 720, endpoint=False):
            rs = np.linspace(scale * 57.0, scale * 64.0, 281)
            v = ndimage.map_coordinates(img, [cy + rs * math.sin(a), cx + rs * math.cos(a)],
                                        order=1, mode="nearest")
            edge.append(rs[int(np.argmax(np.abs(np.gradient(v))))])
        scale = float(np.median(edge)) / 60.0
    # The rings walk the centre in from wherever the rim left it. The scale can only be read off
    # them once they are round, so walk the centre first at the rim's scale - good to a few percent
    # is plenty - and only then believe the rings about it. Three passes on the wide window first:
    # a 4 mm window answers about 0.85 of an offset it covers, so two or three close a 6 mm error,
    # while a 1.2 mm window from that far out answers a tenth and the walk stalls at 40 px.
    for i in range(iterations):
        shift = _ring_shift(img, cx, cy, scale, span=4.0 if i < 3 else 1.2)
        if shift is None:
            break
        cx, cy = cx + shift[0], cy + shift[1]
        if math.hypot(*shift) < 0.02:
            break
    if rings and not fixed_scale:
        scale = _scale_from_rings(img, cx, cy, scale)
        for _ in range(iterations):
            shift = _ring_shift(img, cx, cy, scale)
            if shift is None:
                break
            cx, cy = cx + shift[0], cy + shift[1]
            if math.hypot(*shift) < 0.02:
                break
    return cx, cy, scale


def _scale_from_rings(img, cx, cy, scale, span: float = 0.08, steps: int = 321):
    """Metric scale from the rings, which are at known radii.

    The rim of a Blu-ray is not the edge of its data: the recorded spiral stops at 58 mm while the
    disc goes on to 60. Measuring the scale from the rim therefore lands on whichever edge the
    photograph happens to make sharpest, and a 3.4% scale error turns into a 3.4% pitch error.
    """
    rho = np.arange(scale * 22.0, scale * 61.0, 0.5)
    th = np.linspace(0, 2 * math.pi, 1440, endpoint=False)
    prof = np.empty(rho.size)
    for i, rr in enumerate(rho):
        v = ndimage.map_coordinates(img, [cy + rr * np.sin(th), cx + rr * np.cos(th)],
                                    order=1, mode="nearest")
        prof[i] = np.mean(v)
    prof = prof - ndimage.uniform_filter1d(prof, size=max(3, int(round(3.0 * scale))))
    best = (0.0, scale)
    rings = np.asarray(RINGS_MM, dtype=float)
    for sc in np.linspace(scale * (1 - span), scale * (1 + span), steps):
        pos = (rings * sc - rho[0]) / (rho[1] - rho[0])
        if pos.min() < 1 or pos.max() > rho.size - 2:
            continue
        on = np.interp(pos, np.arange(prof.size), prof)
        # 1.4 ring half-widths out is just past the ring's edge; 0.5 would still be inside a ring
        # that is RING_HALF_MM wide, which is what made this score flat and left the rim's number.
        off = np.interp(pos + 1.4 * RING_HALF_MM * sc / (rho[1] - rho[0]),
                        np.arange(prof.size), prof)
        score = float(off.mean() - on.mean())        # rings are dark: off the ring, not on it, is light
        if score > best[0]:
            best = (score, float(sc))
    return best[1]


def _ring_shift(img, cx, cy, scale, span: float = 1.2, step: float = 0.02):
    """How far to move the centre so the rings stop being ellipses.

    A ring in the design is a thin circle, which in a polar map is a *horizontal band*: at the ring
    radius every angle is dark, so a centroid over the band sits at the ring radius whatever the
    centre is and says nothing. What does move is where the band's two edges are, and they follow
    the offset linearly, r0 + dx*cos(theta) + dy*sin(theta), with gain one. So the estimate is the
    midpoint of the two half-level crossings, and angles that fall inside a wedge are skipped
    because there the whole window is dark and no edge is found.

    The old version used the band centroid. Measured on a synthetic picture it answered
    (-6.6, +6.6) px at the true centre, with a gain near five, so find_centre walked 200 px away.

    `span` is how far either side of the ring the window reaches. It has to cover the offset it is
    being asked about, or the crossings sit outside the window and the answer crawls in at a tenth
    of the truth: from 5.6 mm out a 1.2 mm window answers 0.4 mm. A 4 mm window answers about 0.85
    of it, so find_centre takes three wide passes before narrowing. Widening past 4 mm is not the
    fix: at 6 mm the window reaches the wedge's inner edge and the extra crossing pulls x back.
    """
    offs = np.arange(-span, span + 0.5 * step, step)
    th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    j = np.arange(th.size)
    level = 0.41                                    # mid grey between the blank disc and a ring
    rows, cols = [], []
    for r0 in RINGS_MM:
        rr = (r0 + offs)[:, None] * scale
        prof = ndimage.map_coordinates(img, [cy + rr * s[None, :], cx + rr * c[None, :]],
                                       order=1, mode="nearest")
        above = prof > level
        into = above[:-1, :] & ~above[1:, :]         # light -> dark: the ring's inner edge
        outof = ~above[:-1, :] & above[1:, :]        # dark -> light: its outer edge
        ok = above[0, :] & above[-1, :] & into.any(axis=0) & outof.any(axis=0)
        i0, i1 = np.argmax(into, axis=0), np.argmax(outof, axis=0)
        ok &= i1 > i0
        jk, i0k, i1k = j[ok], i0[ok], i1[ok]
        if jk.size == 0:
            continue
        d = offs[1] - offs[0]
        e0 = offs[i0k] + (level - prof[i0k, jk]) / (prof[i0k + 1, jk] - prof[i0k, jk]) * d
        e1 = offs[i1k] + (level - prof[i1k, jk]) / (prof[i1k + 1, jk] - prof[i1k, jk]) * d
        rows.append(0.5 * (e0 + e1) * scale)
        cols.append(th[jk])
    if not rows:
        return None
    rows = np.concatenate(rows)
    cols = np.concatenate(cols)
    if rows.size < 50:
        return None
    A = np.column_stack([np.cos(cols), np.sin(cols), np.ones_like(cols)])
    coef, *_ = np.linalg.lstsq(A, rows, rcond=None)
    return float(coef[0]), float(coef[1])


def wedge_edges(img, cx, cy, scale, step_mm: float = 0.05):
    """The angular position of each wedge edge, radius by radius."""
    radii = np.arange(WEDGE_RADII[0] + 0.6, WEDGE_RADII[1] - 0.6, step_mm)
    pol, th = scan.polar_rings(img, cx, cy, scale, scale, radii, n_theta=2880)
    p = np.nan_to_num(pol)
    p = p - ndimage.uniform_filter(p, size=(61, 1), mode="nearest")
    p = p / (p.std(axis=1, keepdims=True) + 1e-12)
    return radii, th, p


def design_polar(radii, th, arr=None):
    """The design sampled on the same (radius, angle) grid as a photograph.

    y is negated here, and that is not incidental. design() lays the picture out the way a raster is
    laid out - rows run down the +y axis - while scan.polar_rings reads a photograph at
    cy - r*sin(theta), the way mathematics does. Sampling the design with +sin therefore hands back
    the mirror image of the photograph: its wedge at +150 degrees reappears at -150. A symmetric
    picture is blind to the difference (three equal wedges at 0/120/240, or a pair half a turn
    apart, reflect onto themselves), which is why the three-wedge design never showed it; the two
    unequal wedges do, and read 126 degrees of accumulated twist as -55 ppm.
    """
    arr = design() if arr is None else arr
    n = arr.shape[0]
    half = PICTURE_MM / 2.0
    rr = np.asarray(radii, dtype=float)[:, None]
    tt = np.asarray(th, dtype=float)[None, :]
    xs = rr * np.cos(tt)
    ys = -rr * np.sin(tt)
    px = (xs + half) / PICTURE_MM * n - 0.5
    py = (ys + half) / PICTURE_MM * n - 0.5
    return ndimage.map_coordinates(arr.astype(np.float64), [py.ravel(), px.ravel()],
                                   order=1, mode="constant").reshape(rr.shape[0], tt.shape[1])


def _rotation_curve(p, dpol, radii, track_rad: float = 0.06):
    """Rotation of the picture at each radius, tracked continuously.

    A pitch error of 10 ppm already turns the picture through a whole turn between the inner and
    outer edge, so a per-row peak search has to follow the winding row by row instead of looking
    near one global offset: neighbouring rows are 0.05 mm apart, which is micro-radians of drift.
    """
    nt = p.shape[1]
    corr = np.fft.ifft(np.fft.fft(p, axis=1) * np.conj(np.fft.fft(dpol, axis=1)), axis=1).real
    quality = corr.std(axis=1)
    if quality.sum() <= 0:
        return None
    total = (corr * quality[:, None]).sum(axis=0)
    first = int(np.argmax(total))
    half = max(2, int(round(track_rad / (2 * math.pi) * nt)))
    shifts = np.empty(corr.shape[0])
    peak = np.empty(corr.shape[0])
    prev = float(first)
    for i in range(corr.shape[0]):
        centre = int(round(prev)) if i else first
        idx = (np.arange(centre - half, centre + half + 1)) % nt
        seg = corr[i, idx]
        j = int(np.argmax(seg))
        y0 = seg[(j - 1) % seg.size]
        y1 = seg[j % seg.size]
        y2 = seg[(j + 1) % seg.size]
        denom = y0 - 2 * y1 + y2
        off = 0.0 if denom >= 0 else 0.5 * (y0 - y2) / denom
        k = centre - half + j + off
        # unwrap by construction: keep the step from the previous row inside one turn
        while k - prev > nt / 2.0:
            k -= nt
        while k - prev < -nt / 2.0:
            k += nt
        shifts[i] = k
        peak[i] = y1
        prev = k
    angle = shifts * 2 * math.pi / nt
    return angle, peak, quality


def _block_rotation(p, dpol, radii, block: int = 24):
    """Rotation at a series of radii, each from a whole block of rows.

    One row of a photograph carries too little signal to place an edge, and free tracking drifts.
    Summing a block of rows in the Fourier domain keeps the phase and raises the signal by the
    square root of the number of rows, and the blocks are then unwrapped against each other, which
    is the part that turns a phase measurement into a count of turns.
    """
    nt = p.shape[1]
    x = np.fft.fft(p, axis=1) * np.conj(np.fft.fft(dpol, axis=1))
    n = p.shape[0]
    centres, angles, quality = [], [], []
    prev = None
    for start in range(0, n - block + 1, block):
        sl = slice(start, start + block)
        total = x[sl].sum(axis=0)
        phase = np.angle(np.fft.ifft(total))
        score = np.abs(np.fft.ifft(total))
        j = int(np.argmax(score))
        y0, y1, y2 = score[(j - 1) % nt], score[j], score[(j + 1) % nt]
        denom = y0 - 2 * y1 + y2
        off = 0.0 if denom >= 0 else 0.5 * (y0 - y2) / denom
        k = (j + off) % nt
        a = 2 * math.pi * k / nt
        if prev is not None:
            while a - prev > math.pi:
                a -= 2 * math.pi
            while a - prev < -math.pi:
                a += 2 * math.pi
        angles.append(a)
        prev = a
        centres.append(float(radii[sl].mean()))
        quality.append(float(score[j]))
    return np.array(centres), np.array(angles), np.array(quality)


def _peak_2d(S, ie, ip):
    """Sub-grid position and width of a peak on a grid, from the 3x3 neighbourhood."""
    ie = min(max(int(ie), 1), S.shape[0] - 2)
    ip = min(max(int(ip), 1), S.shape[1] - 2)
    s00 = S[ie, ip]
    a = 0.5 * (S[ie + 1, ip] - S[ie - 1, ip])
    b = 0.5 * (S[ie, ip + 1] - S[ie, ip - 1])
    A = 0.5 * (S[ie + 1, ip] + S[ie - 1, ip]) - s00
    C = 0.5 * (S[ie, ip + 1] + S[ie, ip - 1]) - s00
    B = 0.25 * (S[ie + 1, ip + 1] - S[ie + 1, ip - 1] - S[ie - 1, ip + 1] + S[ie - 1, ip - 1])
    det = A * C - B * B
    de = dp = 0.0
    if det > 0 and A < 0:
        de = float(np.clip(-(C * a - B * b) / det, -1.0, 1.0))
        dp = float(np.clip(-(A * b - B * a) / det, -1.0, 1.0))
    width = math.sqrt(s00 / (-2.0 * A)) if A < 0 else float("inf")
    return de, dp, width, s00


def _global_match(p, dpol, radii, eps_span: float = 1.5e-4, n_eps: int = 601, harmonics: int = 48,
                  n_phi: int = 360):
    """Score every candidate pitch error at once, with the disc's own rotation left free as well.

    Row by row the picture turns by 2*pi*(r - r_ref)*eps/p, which for 10 ppm across a 25 GB disc is
    a whole turn: tracking that row by row accumulates drift. Here every row is kept in the Fourier
    domain and shifted by the candidate angle, and the maximum is the estimate.

    The rotation has to be free because a disc sits at whatever angle it was dropped into its mount.
    The first version fitted the slope alone and nailed the rotation at r_ref to zero, which means a
    disc laid down 150 degrees round came out of the fit as a different pitch error entirely - at
    300 degrees of twist it read +15.5 ppm where the truth was +8.2, and at 60 it read -0.7 where
    the truth was +1.7. One extra matrix product searches the rotation too, and every angle comes
    back within a fifth of a ppm.
    """
    nt = p.shape[1]
    x = np.fft.fft(p, axis=1) * np.conj(np.fft.fft(dpol, axis=1))
    quality = np.abs(x).sum(axis=1)
    if quality.sum() <= 0:
        return None
    w = quality / quality.sum()
    r = np.asarray(radii, dtype=float)
    r_ref = float((w * r).sum())
    dr = r - r_ref
    eps = np.linspace(-eps_span, eps_span, n_eps)
    ks = np.arange(-harmonics, harmonics + 1)
    phase = np.exp(1j * 2 * math.pi * np.outer(dr, eps) / PITCH_ASSUMED_MM)   # (n_radii, n_eps)
    phi = np.arange(n_phi) * (2 * math.pi / n_phi)
    basis = np.exp(-1j * np.outer(ks, phi))                                   # (n_k, n_phi)

    def surface(rows_p, rows_d):
        y = np.fft.fft(rows_p, axis=1) * np.conj(np.fft.fft(rows_d, axis=1))
        a = np.empty((ks.size, n_eps), dtype=complex)
        for i, kk in enumerate(ks):
            a[i] = (y[:, kk % nt] * w) @ (phase ** kk)
        return np.abs(a.T @ basis)               # (n_eps, n_phi), |match| at every (eps, phi)

    S = surface(p, dpol)
    ie, ip = np.unravel_index(int(np.argmax(S)), S.shape)
    de, dp, width, peak = _peak_2d(S, ie, ip)
    step = eps[1] - eps[0]
    best = float(eps[ie] + de * step)
    rot = float((phi[ip] + dp * (2 * math.pi / n_phi)) % (2 * math.pi))

    # A number is not a measurement until it can fail. Scrambling the template row by row destroys
    # the radial phase relation the match depends on while keeping every row's angular content, so
    # the score it reaches is what this photograph would give a picture that is not there.
    rng = np.random.default_rng(12345)
    null = []
    for _ in range(5):
        roll = rng.integers(0, nt, size=dpol.shape[0])
        scrambled = np.stack([np.roll(row, int(o)) for row, o in zip(dpol, roll)])
        null.append(float(surface(p, scrambled).max()))
    null95 = float(np.percentile(null, 95)) if null else 0.0
    sig = float(peak / null95) if null95 > 0 else 0.0
    return dict(eps=best, sigma=float(width * step), score=float(peak), quality=sig,
                null95=null95, rotation=rot, top=[float(eps[ie]), float(peak)],
                n_eps=n_eps, harmonics=harmonics)


def _fit_shift(radii, angle, weight):
    """Slope of the rotation against radius, and what the fit says about its own noise."""
    r = np.asarray(radii, dtype=float)
    w = np.asarray(weight, dtype=float)
    w = w / w.mean()
    x = r - float((w * r).sum() / w.sum())
    sw = w.sum()
    sx = (w * x).sum() / sw
    sxx = (w * x * x).sum() / sw
    sa = (w * angle).sum() / sw
    sxa = (w * x * angle).sum() / sw
    denom = sxx - sx * sx
    if denom <= 0:
        return None
    slope = (sxa - sx * sa) / denom
    resid = angle - (sa + slope * (x - sx))
    dof = max(1, len(r) - 2)
    s2 = float((w * resid * resid).sum() / dof)
    sigma = math.sqrt(s2 / (denom * sw))
    return dict(slope_rad_per_mm=float(slope), sigma_slope=float(sigma),
                rms_rad=math.sqrt(s2), rows=int(len(r)))


def measure_matched(img, centre=None, scale=None, arr=None, verbose=True, eps_span=1.5e-4):
    """Pitch error from one whole-picture match.

    The picture is matched against the design at every candidate pitch error at once, so a single
    number comes out with a formal error of a fraction of a ppm. What it cannot out-run is the
    metric scale of the photograph: the fit returns the pitch error relative to the radius scale it
    was given, so a 0.25 per cent error in that scale moves the answer by about 80 ppm. Pass `scale`
    when it is known (a scanned disc with a measured rim, or a bench setup); otherwise it is taken
    from the rings and is good to a few hundred ppm at best.
    """
    estimated = scale is None
    cx, cy, scale = find_centre(img, centre, scale, rings=estimated, fixed_scale=not estimated)
    radii = np.arange(WEDGE_RADII[0] + 0.6, WEDGE_RADII[1] - 0.6, 0.05)
    n_theta = 2880
    pol, th = scan.polar_rings(img, cx, cy, scale, scale, radii, n_theta=n_theta)
    # Row mean out, row deviation in, and nothing else. A radial high pass used to run here and it
    # was wrong twice: the template is the same at every radius, so the same filter would have left
    # nothing of it, and applied to the photograph alone it deletes the picture exactly when the
    # twist is near zero - the reading that most needs to be believed.
    p = np.nan_to_num(pol)
    p = p - p.mean(axis=1, keepdims=True)
    p = p / (p.std(axis=1, keepdims=True) + 1e-12)
    template = design(rings=()) if arr is None else arr
    dpol = design_polar(radii, th, template)
    keep = np.ones(radii.size, bool)                     # the rings are a tempting grating: a pitch
    for ring in RINGS_MM:                                # error that slides one ring spacing lands on
        keep &= np.abs(radii - ring) > RING_HALF_MM + 0.25   # an alias at p/4.1mm = 78 ppm
    p, dpol, radii = p[keep], dpol[keep], radii[keep]
    dpol = dpol - dpol.mean(axis=1, keepdims=True)
    dpol = dpol / (dpol.std(axis=1, keepdims=True) + 1e-12)
    out = _global_match(p, dpol, radii, eps_span=eps_span)
    if out is None:
        return None
    eps = out["eps"]
    res = dict(method="whole-picture match", centre=[round(cx, 2), round(cy, 2)],
               scale_px_per_mm=round(scale, 5), scale_estimated=estimated,
               radii_mm=[round(float(radii[0]), 2), round(float(radii[-1]), 2)],
               eps=float(eps), eps_sigma=float(out["sigma"]),
               pitch_error_ppm=round(float(eps) * 1e6, 2),
               pitch_sigma_ppm=round(float(out["sigma"]) * 1e6, 2),
               turns=round(float(eps) * (radii[-1] - radii[0]) / PITCH_ASSUMED_MM, 3),
               quality=round(float(out.get("quality", 0.0)), 2),
               rotation=round(float(np.degrees(out.get("rotation", 0.0))) % 360.0, 2),
               pitch_true_um=round(PITCH_ASSUMED_MM * 1000.0 * (1.0 + eps), 6))
    if verbose:
        print(f"pitch error {res['pitch_error_ppm']:+.2f} +/- {res['pitch_sigma_ppm']:.2f} ppm "
              f"({res['turns']:+.2f} turns over {res['radii_mm'][0]:.1f}-{res['radii_mm'][1]:.1f} mm), "
              f"scale {res['scale_px_per_mm']} px/mm" + (" (from the rings)" if estimated else " (given)"))
    return res


def _fit_twist(radii, phase, amp):
    """Pitch error from the wedge phase, without ever unwrapping a whole turn.

    A picture rotated by phi at radius r has 2*phi in the phase of its 2-per-turn harmonic, and a
    pitch error eps rotates it by 2*pi*(r-r_ref)*eps/p. So the measurement is a *slope*, and the
    slope is small: 10 ppm over 32 mm is 0.006 rad. Unwrapping a noisy phase that only moves by
    milliradians is all risk and no help - the first version did that and picked up whole turns of
    noise. Here the residual phase is wrapped into (-pi, pi] and fitted directly, which is exact as
    long as the residual stays small, and the fit's own error says whether the answer is real.
    """
    w = np.asarray(amp, dtype=float) ** 2
    if w.sum() <= 0:
        return None
    w = w / w.mean()
    r = np.asarray(radii, dtype=float)
    r_ref = float((w * r).sum() / w.sum())
    x = r - r_ref
    eps = 0.0
    for _ in range(4):
        model = 2.0 * math.pi * x * eps / PITCH_ASSUMED_MM
        delta = np.angle(np.exp(1j * (2.0 * phase - model)))
        sw = w.sum()
        sx = (w * x).sum() / sw
        sxx = (w * x * x).sum() / sw
        sxd = (w * x * delta).sum() / sw
        sdd = (w * delta * delta).sum() / sw
        denom = sxx - sx * sx
        if denom <= 0:
            return None
        slope = (sxd - sx * (w * delta).sum() / sw) / denom
        inter = (w * delta).sum() / sw - slope * sx
        resid = delta - (inter + slope * x)
        s2 = float((w * resid * resid).sum() / max(1, len(r) - 2))
        eps = float(eps + slope * PITCH_ASSUMED_MM / (4.0 * math.pi))
        sigma = math.sqrt(s2 / (denom * sw)) * PITCH_ASSUMED_MM / (4.0 * math.pi)
    coherence = float(abs((w * np.exp(1j * delta)).sum() / w.sum()))
    return dict(eps=eps, sigma_eps=sigma, coherence=coherence,
                rms_rad=math.sqrt(s2), rows=int(len(r)), r_ref_mm=r_ref,
                span_mm=float(r[-1] - r[0]))


def measure(img: np.ndarray, centre=None, scale=None, verbose: bool = True):
    cx, cy, scale = find_centre(img, centre, scale)
    radii, th, p = wedge_edges(img, cx, cy, scale)
    if p.shape[0] < 20:
        raise SystemExit("the picture is too small to sample the wedges radius by radius")
    phase, amp = _wedge_phase(p, th)
    good = amp >= max(0.05, 0.35 * float(np.median(amp)))
    out = {"centre": [round(cx, 2), round(cy, 2)], "scale_px_per_mm": round(scale, 4),
           "harmonic_amplitude": round(float(np.median(amp)), 4),
           "rows": int(good.sum()), "of_rows": int(len(radii))}
    if good.sum() < 20:
        out.update(turns=None, eps=None, pitch_true_um=None)
        if verbose:
            print(f"centre {out['centre']}  {scale:.3f} px/mm  no wedge pattern found "
                  f"(2-per-turn amplitude {out['harmonic_amplitude']:.3f})")
        return out
    fit = _fit_twist(radii[good], phase[good], amp[good])
    if fit is None:
        out.update(turns=None, eps=None, pitch_true_um=None)
        return out
    eps = fit["eps"]
    out.update(radii_mm=[round(float(radii[good][0]), 2), round(float(radii[good][-1]), 2)],
               turns=round(eps * fit["span_mm"] * 1e3 / PITCH_ASSUMED_MM, 3),
               eps=float(eps), eps_sigma=float(fit["sigma_eps"]),
               pitch_true_um=round(PITCH_ASSUMED_MM * 1000.0 * (1.0 + eps), 6),
               pitch_error_ppm=round(float(eps) * 1e6, 2),
               pitch_sigma_ppm=round(float(fit["sigma_eps"]) * 1e6, 2),
               coherence=round(fit["coherence"], 4), rms_rad=round(fit["rms_rad"], 4))
    if verbose:
        print(f"centre {out['centre']}  {scale:.3f} px/mm  {out['radii_mm'][0]:.1f}-{out['radii_mm'][1]:.1f} mm "
              f"({fit['rows']} rows, amplitude {out['harmonic_amplitude']:.3f})")
        print(f"pitch error {out['pitch_error_ppm']:+.2f} +/- {out['pitch_sigma_ppm']:.2f} ppm  "
              f"(coherence {out['coherence']:.3f}); pitch {out['pitch_true_um']:.6f} um "
              f"vs {PITCH_ASSUMED_MM * 1000:.3f} assumed")
    return out


def _wedge_phase(p, th):
    """Rotation of the two-wedge pattern at each radius, from its second angular harmonic.

    Two 60 deg blocks half a turn apart are invariant under a half turn, so their position lives in
    the phase of the 2-per-turn harmonic: rotating the picture by phi advances that phase by 2*phi.
    Reading that phase beats hunting for the block edges, whose score is a plateau across a 60 deg
    block and therefore lands anywhere the noise likes - which is what the first version did.
    """
    z = (p * np.exp(-2j * th)[None, :]).sum(axis=1)
    amp = np.abs(z) / max(1e-12, float(p.shape[1]))
    return -0.5 * np.angle(z), amp


# ---------------------------------------------------------------- the command

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--design", metavar="PNG", help="write the second-generation picture here")
    ap.add_argument("--size", type=int, default=0,
                    help="picture side in pixels (default 2400 dpi, which is %d for 116 mm)"
                         % pixels_for_dpi())
    ap.add_argument("--measure", metavar="PHOTO", help="measure a photograph of such a disc")
    ap.add_argument("--centre", nargs=2, type=float, metavar=("X", "Y"))
    ap.add_argument("--scale", type=float, help="pixels per mm, if the rim fit is unreliable")
    ap.add_argument("--out", metavar="JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="recover six injected shear angles from synthetic discs")
    args = ap.parse_args(argv)

    if args.design:
        save_design(args.design, args.size or None)
        print(f"wrote {args.design}: {PICTURE_MM:.0f} mm across, "
              f"wedges {', '.join(f'{w:g} deg at {c:g}' for c, w in WEDGES)}, "
              f"{len(RINGS_MM)} rings at {', '.join(f'{x:g}' for x in RINGS_MM)} mm")
        return 0
    if args.selftest:
        # The angles, not the ppm, are what the report quotes: a disc that is eps off nominal
        # shears its outer edge by 2*pi*(r_out-r_in)*eps/p against the inner one, which at
        # +3.46 ppm is 0.35 turns, 126 degrees - the twist the first RITEK disc showed. Testing
        # the six angles the analysis used keeps the two in the same language, and the asymmetric
        # wedges only expose the handedness bug at some of them (the old symmetric design was its
        # own mirror image, so all six passed).
        cases = ((0.0, 0.000), (60.0, 1.646), (126.0, 3.457), (180.0, 4.938),
                 (300.0, 8.230), (330.0, 9.053))
        worst, worst_q = 0.0, 1e9
        for deg, ppm in cases:
            pic = render(eps=ppm * 1e-6, noise=0.02, seed=3)
            got = measure_matched(pic, scale=7.5, verbose=False)
            err = abs(got["pitch_error_ppm"] - ppm)
            worst, worst_q = max(worst, err), min(worst_q, got["quality"])
            print(f"  {deg:5.0f} deg shear, {ppm:+5.3f} ppm -> {got['pitch_error_ppm']:+6.3f} ppm, "
                  f"error {err:.3f} ppm, quality {got['quality']:5.2f}")
        # One far case outside the angle sweep, to keep the sign and the turns right.
        far = -50.0
        got = measure_matched(render(eps=far * 1e-6, noise=0.02, seed=3), scale=7.5, verbose=False)
        err = abs(got["pitch_error_ppm"] - far)
        worst, worst_q = max(worst, err), min(worst_q, got["quality"])
        print(f"  {far:+6.1f} ppm -> {got['pitch_error_ppm']:+6.3f} ppm, error {err:.3f} ppm, "
              f"quality {got['quality']:5.2f}")
        blind = measure_matched(render(eps=1e-5, noise=0.02, seed=3), verbose=False)
        print(f"with the scale taken from the rings instead: +10.00 ppm -> {blind['pitch_error_ppm']:+.2f} ppm "
              f"(scale {blind['scale_px_per_mm']} px/mm, {blind['scale_estimated'] and 'estimated' or 'given'})")
        # How the disc sits on the table must not change the answer. This is the check a hand-placed
        # disc needs, and it is also what the handedness bug broke hardest: a mirrored template only
        # agrees with the design at the placements the mirror happens to preserve.
        base = render(eps=3.457e-6, noise=0.02, seed=3)
        mid = (base.shape[0] - 1) / 2.0
        print("mounting angle, same disc (3.457 ppm):")
        for ang in (37.0, 126.0, 233.0):
            img = ndimage.rotate(base, ang, reshape=False, order=1, mode="nearest")
            got = measure_matched(img, centre=(mid, mid), scale=7.5, verbose=False)
            err = abs(got["pitch_error_ppm"] - 3.457)
            worst, worst_q = max(worst, err), min(worst_q, got["quality"])
            print(f"  turned {ang:5.1f} deg -> {got['pitch_error_ppm']:+6.3f} ppm, error {err:.3f} ppm, "
                  f"quality {got['quality']:5.2f}, reads the mounting as {got['rotation']:5.1f} deg")
        print(f"worst absolute error {worst:.3f} ppm, worst quality {worst_q:.2f} "
              f"(need {0.25:.2f} ppm and quality >= 4.0)")
        return 0 if worst < 0.25 and worst_q >= 4.0 else 1
    if args.measure:
        img = np.asarray(Image.open(args.measure).convert("L"), dtype=np.float64) / 255.0
        # The whole-picture match, not measure(): measure() reads the two-per-turn harmonic, which
        # only exists on the old symmetric design. On this one it answers a number for a picture
        # that is not there - 1.1 ppm where 3.46 was injected, with a coherence of 0.07.
        got = measure_matched(img, args.centre, args.scale, verbose=False)
        if got is None:
            print("no match: the picture does not look like a disc of this design")
            return 1
        print(f"pitch error {got['pitch_error_ppm']:+.2f} +/- {got['pitch_sigma_ppm']:.2f} ppm "
              f"({got['turns']:+.2f} turns over {got['radii_mm'][0]:.1f}-{got['radii_mm'][1]:.1f} mm), "
              f"quality {got['quality']:.2f}, centre {got['centre']}, "
              f"{got['scale_px_per_mm']} px/mm"
              + (" (from the rings)" if got["scale_estimated"] else " (given)"))
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(got, fh, indent=2)
            print(f"wrote {args.out}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
