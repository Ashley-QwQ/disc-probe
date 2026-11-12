"""Prototype: read one along-track constant L (and a phi(r) curve) from phone photos of a burned target.

Frozen reader from docs/goals/photo-calibration/pcal_frozen_d6375fae.py.
Original SHA256: d6375faed8fe489e01854dc09afcbaf057d7042968c5157f5ae56dc8ed4a9f6f.
Only packaging changed: relative import, no sys.path mutation. All reader rules are unchanged.

Model. A feature designed at (r, theta) lands on the disc at theta + tau(r), tau(r) = c + L / r + phi(r).
c is the arbitrary rotation, L (mm) the along-track shift (L / frame_mm is the --along-track-frames
residual; sign as in evidence/cd-geo-20261104/grid2-scan/grid_spokes.py), phi(r) what timing left.

Reader:
1. Rim ellipse -> first homography. Rotation stays free.
2. Burned rings refine the homography. Rings do not care about L, so this step needs no guess of L.
3. Polar unroll, log colour, angular high-pass, local normalisation.
4. Scan L: per sector correlation with the template, colour vector magnitude, so polarity may flip
   between sectors and contrast may be purely chromatic.
5. Votes: each (sector, radial zone) cell finds its own tau. Robust fit of c + L/r + nuisance.
6. Leave-one-sector-out and leave-one-zone-out decide whether L can be trusted.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter1d

from . import tilephoto as tp

CD_FRAME_MM = 588 * 277.66e-6          # one CD channel frame along the track at b = 277.66 nm
R_MIN, R_MAX = 25.5, 58.0
NT = 3600                              # polar angle samples
DR = 0.25                              # polar radius step (mm)


# ---------------------------------------------------------------- targets

class Design:
    """Binary or grey pattern on a polar grid, value in [0, 1]. rings: (radius, half width, guard) in mm."""

    def __init__(self, name, value, rings=(), zones=None, min_feature_mm=1.0, radial_free=False):
        self.name, self.value, self.rings, self.radial_free = name, value, list(rings), radial_free
        self.zones = zones or [(R_MIN + i * (R_MAX - R_MIN) / 6, R_MIN + (i + 1) * (R_MAX - R_MIN) / 6) for i in range(6)]
        self.min_feature_mm = min_feature_mm

    def template(self, radii, nt=NT):
        th = np.arange(nt) * 2 * np.pi / nt
        rr, tt = np.meshgrid(radii, th, indexing="ij")
        return self.value(rr, tt).astype(np.float32)


def _best_code(n, rng, tries=300):
    """Balanced binary code with low circular autocorrelation."""
    best, best_s = None, 1e9
    for _ in range(tries):
        c = np.zeros(n, np.float32)
        c[rng.choice(n, n // 2, replace=False)] = 1
        f = np.fft.rfft(c - c.mean())
        a = np.fft.irfft(np.abs(f) ** 2, n=n)
        s = np.abs(a[1:]).max() / a[0]
        if s < best_s:
            best, best_s = c, s
    return best


RING_RADII = (26.0, 29.5, 33.5, 38.0, 43.0, 49.5, 57.5)      # all pairwise differences distinct: one radial slice tells which ring is which


def design_pn(chip_mm=1.4, rings=RING_RADII, ring_half=0.5, guard=0.5, seed=11):
    """Rings cut the disc into zones; each zone has its own pseudo-random spoke code."""
    rng = np.random.default_rng(seed)
    zones, codes = [], []
    for a, b in zip(rings, rings[1:]):
        lo, hi = a + ring_half + guard, b - ring_half - guard
        n = 2 * round(math.pi * (lo + hi) / 2 / chip_mm)
        zones.append((lo, hi))
        codes.append(_best_code(n, rng))

    def value(r, th):
        v = np.zeros(np.broadcast(r, th).shape, np.float32)
        for (lo, hi), c in zip(zones, codes):
            m = (r >= lo) & (r < hi)
            v[m] = c[np.floor((th[m] % (2 * np.pi)) / (2 * np.pi) * len(c)).astype(int) % len(c)]
        for R in rings:
            v[np.abs(r - R) <= ring_half + guard] = 0
            v[np.abs(r - R) <= ring_half] = 1
        return v
    return Design("pn", value, [(R, ring_half, guard) for R in rings], zones, chip_mm, radial_free=True)


def design_cross(arm_mm=0.6, rings=(26.0, 30.0, 34.0, 38.0, 42.0, 46.0, 50.0, 54.0)):
    """Like DiscImageStudio's fine target: rings and a four-armed cross."""
    def value(r, th):
        v = np.zeros(np.broadcast(r, th).shape, np.float32)
        d = np.abs(((th + np.pi / 4) % (np.pi / 2)) - np.pi / 4)
        v[(d * r < arm_mm / 2) & (r >= 24.5) & (r <= 57.5)] = 1
        for R in rings:
            v[np.abs(r - R) <= 0.3] = 1
        return v
    zones = [(a + 0.5, b - 0.5) for a, b in zip((26, 31, 36, 41, 46, 51), (31, 36, 41, 46, 51, 56))]
    return Design("cross", value, [(R, 0.3, 0.6) for R in rings], zones, arm_mm)


def design_spoke30(line_mm=0.6, circles=(30.0, 35.0, 40.0, 45.0, 50.0, 55.0)):
    """Our grid disc's radial lines every 30 degrees and 5 mm circles (without the square grid)."""
    def value(r, th):
        v = np.zeros(np.broadcast(r, th).shape, np.float32)
        d = np.abs(((th + np.pi / 12) % (np.pi / 6)) - np.pi / 12)
        v[(d * r < line_mm / 2) & (r >= 24.5) & (r <= 57.5)] = 1
        for R in circles:
            v[np.abs(r - R) <= line_mm / 2] = 1
        return v
    zones = [(a + 0.5, b - 0.5) for a, b in zip((25, 30, 35, 40, 45, 50), (30, 35, 40, 45, 50, 55))]
    return Design("spoke30", value, [(R, line_mm / 2, 0.8) for R in circles], zones, line_mm)


def design_sin3(ks=(3, 21, 63), phases=(0.0, 90.0, 0.0), weights=(0.3, 0.3, 0.4), rings=(26.0, 32.0, 38.0, 44.0, 50.0, 56.0)):
    """discprobe.spokes: three sinusoids, dithered on the disc. Grey levels here."""
    def value(r, th):
        v = np.full(np.broadcast(r, th).shape, 0.5, np.float32)
        for k, p, w in zip(ks, phases, weights):
            v += 0.5 * w * np.cos(k * th + math.radians(p))
        for R in rings:
            v[np.abs(r - R) < 0.25] = 0.5
        return np.clip(v, 0, 1)
    return Design("sin3", value, [], None, 2.0)


def design_half(amp_deg=25.0, turns=3.0):
    """Like DiscImageStudio's boundary target: half bright, half dark, with a wavy boundary."""
    def value(r, th):
        wob = math.radians(amp_deg) * np.sin(2 * np.pi * turns * (r - 25) / 33)
        return (((th + wob) % (2 * np.pi)) < np.pi).astype(np.float32)
    return Design("half", value, [], None, 5.0)


def design_burn():
    """The version that goes on a disc: its first ring clears the CD file system (26 mm) and its last fits a CD."""
    d = design_pn(rings=(27.0, 30.5, 34.5, 39.0, 44.0, 50.5, 56.5))
    d.name = "pn_burn"
    return d


def design_pn24():
    d = design_pn(chip_mm=2.4)
    d.name = "pn24"
    return d


DESIGNS = {"pn": design_pn, "pn24": design_pn24, "pn_burn": design_burn, "cross": design_cross, "spoke30": design_spoke30, "sin3": design_sin3, "half": design_half}


# ---------------------------------------------------------------- reader: geometry

def _rim_candidates(grey, hub, n=720):
    """For each ray, the strongest few edges of either polarity."""
    h, w = grey.shape
    g = cv2.GaussianBlur(grey, (0, 0), 1.5)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    pts = []
    for th in np.linspace(0, 2 * math.pi, n, endpoint=False):
        r = np.arange(30, 2 * max(h, w), 1.0)
        c, s = math.cos(th), math.sin(th)
        x, y = hub[0] + r * c, hub[1] + r * s
        ok = (x >= 2) & (y >= 2) & (x < w - 3) & (y < h - 3)
        if ok.sum() < 30:
            continue
        xi, yi = x[ok].astype(int), y[ok].astype(int)
        d = np.abs(gx[yi, xi] * c + gy[yi, xi] * s)
        order = np.argsort(d)[::-1]
        taken = []
        for j in order[:40]:
            if d[j] < 0.05:
                break
            if all(abs(j - t) > 6 for t in taken):
                taken.append(j)
            if len(taken) == 6:
                break
        pts.extend((x[ok][j], y[ok][j]) for j in taken)
    return np.array(pts, float)


def find_ellipses(rgb_small, max_out=14, hub=None):
    """Distinct well-supported ellipses. Rays start from hub, or from the frame centre and then the best ellipse."""
    grey = rgb_small.mean(-1)
    h, w = grey.shape
    rng = np.random.default_rng(1)
    out = []
    hubs = [hub if hub is not None else (w / 2, h / 2)]
    for ih in range(1 if hub is not None else 2):
        pts = _rim_candidates(grey, hubs[-1])
        if len(pts) < 60:
            break
        cands = []
        for _ in range(2500):
            sel = pts[rng.choice(len(pts), 6, replace=False)]
            try:
                e = tp.fit_ellipse(sel)
            except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
                continue
            if not (0.05 * min(h, w) < e[3] and e[2] < 1.0 * max(h, w) and e[3] / e[2] > 0.45):
                continue
            cands.append((int((tp._ellipse_dist(pts, e) < 3.0).sum()), e))
        if not cands:
            break
        cands.sort(key=lambda c: -c[0])
        kept = []
        for n, e in cands:
            if n < 40:
                break
            if all(np.hypot(e[0] - k[1][0], e[1] - k[1][1]) > 12 or abs(e[2] - k[1][2]) > 12 or abs(e[3] - k[1][3]) > 12 for k in kept):
                inl = pts[tp._ellipse_dist(pts, e) < 3.0]
                try:
                    e = tp.fit_ellipse(inl)
                except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
                    pass
                kept.append((n, e))
            if len(kept) == max_out:
                break
        out.extend(kept)
        if kept:
            hubs.append((kept[0][1][0], kept[0][1][1]))
    return out


def _radial_profile(lg_small, H, radii):
    """Angle-mean of the radially high-passed log grey, and how much of the per-angle power it keeps."""
    th = np.arange(360) * 2 * np.pi / 360
    pol = polar_sample(lg_small, H, radii, thetas=th).mean(-1)
    hp, m = _nan_hp(pol, 31, 0, wrap=False)
    n = np.maximum(m.sum(1), 1)
    prof = hp.sum(1) / n
    coh = float(np.sqrt(np.mean(prof ** 2)) / (np.sqrt(np.mean(hp[m] ** 2)) + 1e-6)) if m.any() else 0.0
    return prof, coh, float(m.mean())


def concentric_hough(grey, max_edges=7000, seed=2):
    """Centre and shape of the concentric circles of a disc, from any arcs that show. An ellipse family with
    the right aspect and direction becomes circles under an affine map, and then every edge normal passes
    through one point. Spoke edges, wedge edges and clutter have normals that do not meet, so they only add
    a floor. Needs no rim, no hub and no whole circle."""
    g = cv2.GaussianBlur(grey, (0, 0), 1.2)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 88)
    ys, xs = np.nonzero(mag > thr)
    if len(xs) < 200:
        return None
    rng = np.random.default_rng(seed)
    if len(xs) > max_edges:
        i = rng.choice(len(xs), max_edges, replace=False)
        xs, ys = xs[i], ys[i]
    px, py = xs.astype(np.float32), ys.astype(np.float32)
    ux, uy = gx[ys, xs] / mag[ys, xs], gy[ys, xs] / mag[ys, xs]
    h, w = grey.shape
    tmax = 0.8 * max(h, w)
    ts = np.concatenate([np.arange(-tmax, -8, 1.5), np.arange(8, tmax, 1.5)]).astype(np.float32)
    cell = 2.0

    def score(q, ang):
        ca, sa = math.cos(ang), math.sin(ang)
        # A = diag(1, 1/q) R(-ang): rectified = A p; gradients go with the inverse transpose.
        rx = ca * px + sa * py
        ry = (-sa * px + ca * py) / q
        gxr = ca * ux + sa * uy
        gyr = (-sa * ux + ca * uy) * q
        n = np.hypot(gxr, gyr)
        gxr, gyr = gxr / n, gyr / n
        X = rx[:, None] + gxr[:, None] * ts[None, :]
        Y = ry[:, None] + gyr[:, None] * ts[None, :]
        x0, y0 = -2.0 * max(h, w), -4.0 * max(h, w)
        ix = ((X - x0) / cell).astype(np.int32).ravel()
        iy = ((Y - y0) / cell).astype(np.int32).ravel()
        nx, ny = int(4 * max(h, w) / cell), int(8 * max(h, w) / cell)
        ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        acc = np.bincount(iy[ok] * nx + ix[ok], minlength=nx * ny).reshape(ny, nx).astype(np.float32)
        acc = cv2.GaussianBlur(acc, (0, 0), 1.2)
        j = int(acc.argmax())
        jy, jx = np.unravel_index(j, acc.shape)
        floor = float(np.median(acc[max(jy - 30, 0):jy + 31, max(jx - 30, 0):jx + 31])) + 1e-3
        return float(acc[jy, jx] / floor), (x0 + (jx + 0.5) * cell, y0 + (jy + 0.5) * cell)

    best = (0.0, 1.0, 0.0, None)
    qs = [1.0, 0.95, 0.9, 0.84, 0.77, 0.7, 0.62, 0.54]
    for q in qs:
        for ang in ([0.0] if q == 1.0 else np.arange(0, np.pi, np.pi / 8)):
            s_, c = score(q, float(ang))
            if s_ > best[0]:
                best = (s_, q, float(ang), c)
    # Finer steps around the winner.
    _, q0, a0, _ = best
    for dq, da in ((0.03, 0.12), (0.012, 0.05)):
        for q in (best[1] - dq, best[1], min(best[1] + dq, 1.0)):
            for ang in (best[2] - da, best[2], best[2] + da):
                s_, c = score(q, ang)
                if s_ > best[0]:
                    best = (s_, q, ang, c)
    s_, q, ang, c = best
    ca, sa = math.cos(ang), math.sin(ang)
    A = np.array([[ca, sa], [-sa / q, ca / q]])
    Ai = np.linalg.inv(A)
    centre = Ai @ np.array(c)
    # Radial histogram of edges whose normal really points at the centre.
    P = np.column_stack([px - centre[0], py - centre[1]]) @ A.T
    rad = np.hypot(P[:, 0], P[:, 1])
    G = np.column_stack([ca * ux + sa * uy, (-sa * ux + ca * uy) * q])
    G /= np.linalg.norm(G, axis=1, keepdims=True)
    cosang = np.abs(np.sum(G * P, axis=1)) / np.maximum(rad, 1e-3)
    return {"score": s_, "q": q, "ang": ang, "centre": centre, "A": A, "rad": rad[cosang > 0.97]}


def outer_ellipses(luma, hg, max_out=4):
    """Ellipses well outside the hub, in the coordinates of the small image (luma is half of that). The
    concentric family fits only roughly out there, but it tells which edges to look at, and those edges are
    then fitted with their own centre and shape."""
    g = cv2.GaussianBlur(luma, (0, 0), 1.2)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag = np.hypot(gx, gy)
    ys, xs = np.nonzero(mag > np.percentile(mag, 90))
    A, c = hg["A"], hg["centre"]
    P = np.column_stack([xs - c[0], ys - c[1]]) @ A.T
    rad = np.hypot(P[:, 0], P[:, 1])
    N = np.column_stack([gx[ys, xs], gy[ys, xs]]) @ np.linalg.inv(A)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    aligned = np.abs(np.sum(N * P, axis=1)) / np.maximum(rad, 1e-3) > 0.8
    rng = np.random.default_rng(3)
    H_, b_ = np.histogram(rad[aligned], bins=np.arange(0, 2 * max(luma.shape), 6.0))
    rc = 0.5 * (b_[1:] + b_[:-1])
    # Edge count per unit circumference, so big circles are not favoured just for being long.
    dens = gaussian_filter(H_.astype(np.float32), 1.0)
    order = np.argsort(dens * np.sqrt(rc))[::-1]
    out, used = [], []
    for j in order[:40]:
        rho = rc[j]
        if rho < 60 or any(abs(rho - u) < 0.1 * u for u in used):
            continue
        used.append(rho)
        band = aligned & (np.abs(rad - rho) < 0.14 * rho)
        pts = np.column_stack([xs[band], ys[band]]).astype(float)
        if len(pts) < 40:
            continue
        best, n_best = None, 0
        for _ in range(600):
            try:
                e = tp.fit_ellipse(pts[rng.choice(len(pts), 6, replace=False)])
            except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
                continue
            if e[3] / e[2] < 0.4 or e[2] > 2 * max(luma.shape):
                continue
            n = int((tp._ellipse_dist(pts, e) < 1.5).sum())
            if n > n_best:
                best, n_best = e, n
        if best is None or n_best < 30:
            continue
        try:
            e = tp.fit_ellipse(pts[tp._ellipse_dist(pts, best) < 1.5])
        except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
            e = best
        out.append((e[0] * 2, e[1] * 2, e[2] * 2, e[3] * 2, e[4]))
        if len(out) == max_out:
            break
    return out


def initial_h(rgb_small, lg_small, design, focal_small, log=lambda *_: None):
    """First homography from concentric circles. The burned rings' unequal spacing fixes the scale."""
    luma = cv2.resize(lg_small.mean(-1), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    hg = concentric_hough(luma, max_edges=4000)
    if hg is None:
        return None, {"hough": 0.0}
    A, c = hg["A"], hg["centre"] * 2.0
    rad = hg["rad"] * 2.0
    info = {"hough": hg["score"], "q": hg["q"], "ang": hg["ang"], "centre": [float(v) for v in c]}
    Ai = np.linalg.inv(A)

    def make_h(s):
        H = np.eye(3)
        H[:2, :2] = Ai @ np.diag([s, -s])            # design y up, image y down; rotation left free
        H[:2, 2] = c
        return H

    # Radial profile per sector, in rectified pixels. Sectors add by magnitude, so ring polarity may differ.
    rmax = 1.1 * max(rgb_small.shape[:2])
    rho = np.arange(10.0, rmax, 1.0)
    pol = polar_sample(lg_small, make_h(1.0), rho, thetas=np.arange(360) * 2 * np.pi / 360).mean(-1)   # 1 mm = 1 px here
    hp, m = _nan_hp(pol, 21, 0, wrap=False)
    nsec = 12
    prof = np.stack([hp[:, k * 30:(k + 1) * 30].sum(1) / np.maximum(m[:, k * 30:(k + 1) * 30].sum(1), 1) for k in range(nsec)])
    weight = np.stack([m[:, k * 30:(k + 1) * 30].mean(1) for k in range(nsec)])
    # Radii where many sectors show an edge at once. Noise and spoke remains do not line up between sectors.
    loc = np.sqrt(uniform_filter1d(prof * prof, 41, axis=1, mode="nearest"))
    floor = 0.3 * np.percentile(loc, 90, axis=1, keepdims=True) + 1e-5
    strong = np.abs(prof) / (loc + floor) > 1.4
    strong = strong & (weight > 0.5)
    seen = np.maximum((weight > 0.5).sum(0), 1)
    coh = uniform_filter1d(strong.sum(0).astype(np.float32), 3, mode="nearest") / seen
    coh = coh * (seen >= 3)
    idx = [i for i in range(1, len(rho) - 1) if coh[i] >= coh[i - 1] and coh[i] > coh[i + 1] and coh[i] > 0.15]
    # Each coherent radius votes for scale = radius / R, for every R the disc is known to have. Only the true
    # scale gets votes from many rings at once, since the ring spacing has no repeats.
    known = [7.5, 60.0] + [R + d for R, h_, g_ in design.rings for d in (-h_, h_)]
    if not design.rings:
        known += [58.0]
    log_s = np.arange(math.log(1.5), math.log(rmax / 40), 0.004)
    vote = np.zeros_like(log_s)
    for i in idx:
        for R in known:
            v = math.log(rho[i] / R)
            j = int(round((v - log_s[0]) / 0.004))
            if 0 <= j < len(vote):
                vote[j] += coh[i]
    vote = gaussian_filter(vote, 2.0)
    order = [j for j in range(1, len(vote) - 1) if vote[j] >= vote[j - 1] and vote[j] >= vote[j + 1] and vote[j] > 0]
    order.sort(key=lambda j: -vote[j])
    top = []
    for j in order:
        s_ = float(math.exp(log_s[j]))
        if all(abs(s_ - t) > 0.015 * t for t in top):
            top.append(s_)
        if len(top) == 18:
            break
    if not top:
        return None, info
    # Several scales go on to the ring fit, which is what really tells them apart.
    info["scales_small"] = [round(v, 3) for v in top]
    out = []
    # Circles far from the hub are not centred on it under perspective, so the family fits only near the hub.
    # The hub point and any outer ellipse fix the homography, because the polar of a circle's centre is the
    # vanishing line (tilephoto.perspective_h). These come first; the rings have the last word.
    hub = (float(c[0]), float(c[1]))
    for e in outer_ellipses(luma, hg):
        info.setdefault("outer", []).append([round(float(v), 1) for v in e[:4]])
        for radius in sorted({60.0, 58.0} | {R for R, _, _ in design.rings if R > 45}, reverse=True):
            try:
                out.append(tp.perspective_h(e, hub, 0.0, False) @ np.diag([60.0 / radius, 60.0 / radius, 1.0]))
            except Exception:
                pass
    out += [make_h(v) for v in top]
    return out, info


def polar_sample(lg, H, radii, nt=NT, thetas=None):
    """Log colour on (radius, angle). Out of frame or clipped samples are NaN."""
    th = thetas if thetas is not None else np.arange(nt) * 2 * np.pi / nt
    rr, tt = np.meshgrid(radii, th, indexing="ij")
    x, y = rr * np.cos(tt), rr * np.sin(tt)
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    u = ((H[0, 0] * x + H[0, 1] * y + H[0, 2]) / w).astype(np.float32)
    v = ((H[1, 0] * x + H[1, 1] * y + H[1, 2]) / w).astype(np.float32)
    out = cv2.remap(lg, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(-1e3, -1e3, -1e3))
    bad = (out[..., 0] < -100) | (out.max(-1) > math.log(250.0))
    out = out.astype(np.float32)
    out[bad] = np.nan
    return out


def _nan_hp(a, size, axis, wrap=True):
    """a minus its running mean, ignoring NaN. NaN comes out as 0, plus the weight."""
    m = np.isfinite(a)
    mode = "wrap" if wrap else "nearest"
    num = uniform_filter1d(np.where(m, a, 0.0), size=size, axis=axis, mode=mode)
    den = uniform_filter1d(m.astype(np.float32), size=size, axis=axis, mode=mode)
    out = np.where(m & (den > 0.2), a - num / np.maximum(den, 1e-3), 0.0)
    return out.astype(np.float32), m & (den > 0.2)


def refine_with_rings(lg, H, design, log=lambda *_: None):
    """Fit a small plane transform so every ring lands on its radius. Rotation is left alone."""
    info = {"ring_points": 0, "ring_rms_mm": None, "ring_frac": 0.0}
    if not design.rings:
        return H, info
    radii = np.arange(23.5, 60.0, 0.05)
    thetas = np.arange(720) * 2 * np.pi / 720
    for it, win in enumerate((2.6, 1.0, 0.5, 0.3)):
        pol = polar_sample(lg, H, radii, thetas=thetas)                  # (nr, 720, 3)
        # sector means over 6 degrees: spokes average away, rings stay
        m = np.isfinite(pol)
        s = uniform_filter1d(np.where(m, pol, 0).astype(np.float32), size=30, axis=1, mode="wrap")
        d = uniform_filter1d(m.astype(np.float32), size=30, axis=1, mode="wrap")
        pol6 = np.where(d > 0.5, s / np.maximum(d, 1e-3), np.nan)[:, ::15]   # (nr, 48, 3): 15 degree means
        th6 = thetas[::15]
        obs = []
        for R, half, guard in design.rings:
            n = int(round((half + guard) / 0.05)) + 1
            o = np.arange(-n, n + 1) * 0.05
            k = np.where(np.abs(o) <= half, 1.0, -half / max(guard, 1e-3))
            k = (k - k.mean()) / np.linalg.norm(k - k.mean())
            lo = np.searchsorted(radii, R - win - (half + guard))
            hi = np.searchsorted(radii, R + win + (half + guard))
            seg = pol6[lo:hi]
            for j in range(seg.shape[1]):
                col = seg[:, j]
                if np.isfinite(col).mean() < 0.9:
                    continue
                col = np.nan_to_num(col - np.nanmean(col, axis=0))
                # remove a slow radial trend, keeps the ring response
                col = col - uniform_filter1d(col, size=2 * n + 41, axis=0, mode="nearest")
                resp = np.stack([np.convolve(col[:, c], k, mode="same") for c in range(3)], 1)
                mag = np.linalg.norm(resp, axis=1)
                mag[:n] = 0
                mag[-n:] = 0
                i = int(mag.argmax())
                noise = 1.4826 * np.median(np.abs(mag - np.median(mag))) + 1e-5
                if mag[i] < np.median(mag) + 4 * noise or i < 1 or i >= len(mag) - 1:
                    continue
                a, b, c_ = mag[i - 1], mag[i], mag[i + 1]
                off = 0.5 * (a - c_) / (a - 2 * b + c_) if (a - 2 * b + c_) != 0 else 0
                obs.append((R, radii[lo] + (i + off) * 0.05, th6[j], mag[i] / (noise + 1e-5)))
        total = len(design.rings) * pol6.shape[1]
        if len(obs) < 30:
            info.update(ring_points=len(obs), ring_frac=len(obs) / total)
            return H, info
        o = np.array(obs)
        R, r, t = o[:, 0], o[:, 1], o[:, 2]
        rs = r / 40.0
        A = np.column_stack([r, r * np.cos(2 * t), r * np.sin(2 * t), np.cos(t), np.sin(t),
                             rs * rs * np.cos(t), rs * rs * np.sin(t)])
        y = R - r
        w = np.ones(len(y))
        for _ in range(6):
            q, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
            e = y - A @ q
            sc = max(1.4826 * np.median(np.abs(e)), 0.02)
            w = np.sqrt(np.minimum(1.0, 1.5 * sc / np.maximum(np.abs(e), 1e-9)))
        s_, a_, b_, tx, ty, px, py = q
        px, py = px / 1600.0, py / 1600.0
        T = np.array([[1 + s_ + a_, b_, tx], [b_, 1 + s_ - a_, ty], [-px, -py, 1.0]])
        H = H @ np.linalg.inv(T)
        H = H / H[2, 2]
        keep = np.abs(e) < max(3 * sc, 0.15)
        rms = float(np.sqrt(np.mean(e[keep] ** 2)))
        info.update(ring_points=int(keep.sum()), ring_rms_mm=rms, ring_frac=float(keep.sum()) / total)
    return H, info


def prepare_polar(lg, H, design=None, r_min=R_MIN, r_max=R_MAX):
    """Normalised, high-passed polar image. Diffraction wedges are exactly radial, so they look like a burned
    spoke at L = 0: angles with a sharp radial edge are masked, and for targets whose code differs from zone to
    zone (design.radial_free) anything common to all radii is subtracted."""
    radii = np.arange(r_min, r_max + 1e-6, DR)
    pol = polar_sample(lg, H, radii)                                     # (nr, NT, 3)
    good = np.isfinite(pol).all(-1)
    G = np.zeros((3,) + pol.shape[:2], np.float32)
    for c in range(3):
        G[c], m = _nan_hp(pol[..., c], 121, 1)                           # 12 degrees
        good &= m
    G *= good
    grey = np.where(good, np.nanmean(pol, axis=-1), np.nan)
    lp, lm = _nan_hp(grey, 31, 1)
    edge = np.nan_to_num(uniform_filter1d(grey, 31, axis=1, mode="wrap"))   # running mean used only for its slope
    slope = np.abs(np.roll(edge, -30, axis=1) - np.roll(edge, 30, axis=1))
    w = np.median(slope, axis=0)
    mw = np.median(w)
    bad = w > mw + 4 * (1.4826 * np.median(np.abs(w - mw)) + 1e-4)
    bad = uniform_filter1d(bad.astype(np.float32), 31, mode="wrap") > 0
    good &= ~bad[None, :]
    G *= good
    if design is not None and getattr(design, "radial_free", False):
        for c in range(3):
            g = G[c].copy()
            g[~good] = np.nan
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    med = np.nanmedian(g, axis=0)
            G[c] = (G[c] - np.nan_to_num(med)[None, :]) * good
    pw = gaussian_filter(np.sum(G * G, axis=0), (8, 80), mode=("nearest", "wrap"))
    frac = gaussian_filter(good.astype(np.float32), (8, 80), mode=("nearest", "wrap"))
    rms = np.sqrt(pw / np.maximum(frac, 0.05))
    floor = 0.25 * np.median(rms[good]) if good.any() else 1.0
    G = np.clip(G / (rms + floor + 1e-5), -3, 3) * good
    return radii, G, good


# ---------------------------------------------------------------- reader: L scan

def _template_f(design, radii):
    T = design.template(radii)
    T_hp = T - uniform_filter1d(T, 121, axis=1, mode="wrap")
    return T_hp


def scan_L(G, good, T_hp, radii, Ls, kmax=300, nsec=16):
    """Score(L) = max over c of the sum over sectors of the colour-vector correlation magnitude."""
    nr, nt = T_hp.shape
    win = []
    for s in range(nsec):
        a0 = 2 * np.pi * s / nsec
        d = (np.arange(nt) * 2 * np.pi / nt - a0 + np.pi) % (2 * np.pi) - np.pi
        win.append(np.where(np.abs(d) < 2 * np.pi / nsec, 0.5 + 0.5 * np.cos(d * nsec / 2), 0.0))
    win = np.array(win, np.float32)
    usable = np.array([float((good * w[None]).sum()) / max(float(w.sum()) * nr, 1) for w in win])
    # work on 1800 samples and 0.5 mm rings: fast and still resolves the phase
    bin_r = 2
    nr2 = nr // bin_r
    r2 = radii[: nr2 * bin_r].reshape(nr2, bin_r).mean(1)
    k = np.arange(kmax + 1)
    Tf = np.fft.rfft(T_hp[: nr2 * bin_r].reshape(nr2, bin_r, nt).mean(1), axis=1)[:, : kmax + 1]
    F = np.zeros((3, nsec, nr2, kmax + 1), np.complex64)
    for c in range(3):
        g = G[c, : nr2 * bin_r].reshape(nr2, bin_r, nt).mean(1)
        for s in range(nsec):
            if usable[s] > 0.1:
                F[c, s] = np.fft.rfft(g * win[s], axis=1)[:, : kmax + 1]
    F *= np.conj(Tf)[None, None]
    tnorm = np.sqrt(np.sum(np.abs(Tf) ** 2)) + 1e-6
    n2 = 1800
    best = np.zeros(len(Ls))
    best_c = np.zeros(len(Ls))
    ph_k = k[None, :] / r2[:, None]
    for i, L in enumerate(Ls):
        ph = np.exp(1j * L * ph_k).astype(np.complex64)
        X = (F * ph).sum(2)                                              # (3, nsec, k)
        c = np.fft.irfft(X, n=n2, axis=-1)
        m = np.sqrt((c * c).sum(0))                                      # (nsec, n2)
        m = m - np.median(m, axis=1, keepdims=True)
        tot = m.sum(0)
        j = int(tot.argmax())
        best[i], best_c[i] = tot[j] / tnorm, j * 2 * np.pi / n2
    return best, best_c


def _z_peak(score):
    med = np.median(score)
    mad = 1.4826 * np.median(np.abs(score - med)) + 1e-9
    return (score - med) / mad


# ---------------------------------------------------------------- reader: votes

def votes(G, T_hp, radii, zones, c0, L0, nsec=12, half_win_deg=3.0):
    """Each (sector, zone) cell finds its own tau near c0 + L0 / r."""
    nt = T_hp.shape[1]
    shift = np.round(((c0 + L0 / radii) % (2 * np.pi)) / (2 * np.pi) * nt).astype(int)
    # c0 + L0 / r can cross a full turn inside the disc: keep only the part below one sample.
    frac_shift = ((c0 + L0 / radii) - shift * 2 * np.pi / nt + np.pi) % (2 * np.pi) - np.pi
    Gd = np.stack([np.stack([np.roll(G[c, i], -shift[i]) for i in range(len(radii))]) for c in range(3)])
    th = np.arange(nt) * 2 * np.pi / nt
    Tf = np.fft.rfft(T_hp, axis=1)
    out = []
    w_half = int(half_win_deg / 360 * nt)
    far = int(8.0 / 360 * nt)
    for s in range(nsec):
        a0 = 2 * np.pi * (s + 0.5) / nsec
        # sector is fixed in the photo; its position in the detwisted frame moves with radius
        for lo, hi in zones:
            idx = np.nonzero((radii >= lo) & (radii <= hi))[0]
            if len(idx) == 0:
                continue
            rm = radii[idx].mean()
            d = (th + c0 + L0 / rm - a0 + np.pi) % (2 * np.pi) - np.pi
            w = (np.abs(d) < np.pi / nsec).astype(np.float32)
            if float((Gd[0, idx][:, w > 0] != 0).mean()) < 0.5:
                continue
            X = np.zeros((3, nt // 2 + 1), complex)
            for c in range(3):
                X[c] = (np.fft.rfft(Gd[c, idx] * w, axis=1) * np.conj(Tf[idx])).sum(0)
            cc = np.fft.irfft(X, n=nt, axis=-1)
            m = np.sqrt((cc * cc).sum(0))
            lags = np.arange(-w_half, w_half + 1)
            seg = m[lags % nt]
            j = int(seg.argmax())
            off_mask = np.ones(nt, bool)
            off_mask[np.arange(-far, far + 1) % nt] = False
            off = m[off_mask]
            noise = 1.4826 * np.median(np.abs(off - np.median(off))) + 1e-9
            snr = (seg[j] - np.median(off)) / noise
            if 0 < j < len(seg) - 1:
                a, b, c_ = seg[j - 1], seg[j], seg[j + 1]
                sub = 0.5 * (a - c_) / (a - 2 * b + c_) if (a - 2 * b + c_) != 0 else 0.0
            else:
                sub = 0.0
            tau = (lags[j] + sub) * 2 * np.pi / nt + float(frac_shift[idx].mean()) + c0 + L0 / rm - (c0 + L0 / rm)
            out.append((a0, rm, tau + c0 + L0 / rm, snr, j in (0, len(seg) - 1)))
    return out


def _basis(t, r):
    return np.column_stack([np.ones_like(r), 1 / r, np.cos(t) / r, np.sin(t) / r, np.cos(2 * t), np.sin(2 * t)])


def fit_votes(t, r, tau, w0=None):
    """IRLS for tau = c + L/r + ty cos t / r - tx sin t / r + 2-theta terms. Returns params, residuals, covariance."""
    A = _basis(t, r)
    w = np.ones(len(r)) if w0 is None else w0.copy()
    for _ in range(10):
        q, *_ = np.linalg.lstsq(A * w[:, None], tau * w, rcond=None)
        e = tau - A @ q
        sc = max(1.4826 * np.median(np.abs(e)), math.radians(0.05))
        w = np.sqrt(np.minimum(1.0, 1.5 * sc / np.maximum(np.abs(e), 1e-9))) * (1.0 if w0 is None else w0)
    AtA = (A * (w * w)[:, None]).T @ A
    cov = np.linalg.pinv(AtA) * float(np.sum((w * e) ** 2) / max(len(r) - A.shape[1], 1))
    return q, e, cov, sc


# ---------------------------------------------------------------- reader: whole photo

def read_photo(rgb8, design, focal_px=None, L_range=(-45.0, 45.0), log=lambda *_: None):
    """rgb8: uint8 H x W x 3. Returns a dict; 'status' is 'ok' or names why L should not be trusted."""
    h, w = rgb8.shape[:2]
    if focal_px is None:
        focal_px = 26.0 / 36.0 * max(w, h)
    res = {"design": design.name, "status": "no_rim"}
    f = 1200 / w
    small8 = cv2.resize(rgb8, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    small = small8.astype(np.float32) / 255.0
    lg_small = np.log(cv2.GaussianBlur(small8.astype(np.float32), (0, 0), 0.7) + 2.0)
    H0s, init = initial_h(small, lg_small, design, focal_px * f, log)
    res["init"] = init
    if H0s is None:
        return res
    S = np.diag([1 / f, 1 / f, 1.0])

    def px_mm_of(H_):
        x_ = tp.project(H_, np.array([0.0, 40.0]), np.array([0.0, 0.0]))
        return math.hypot(x_[0][1] - x_[0][0], x_[1][1] - x_[1][0]) / 40.0

    # A wrong scale leaves ring residuals like noise in the last search window (0.17 mm rms for +-0.3 mm);
    # the right one falls well below that. So the fit itself picks the scale.
    lg_cache = {}
    tried = []
    for H0s_ in H0s:
        H0 = S @ H0s_
        sig = round(max(0.5, 0.08 * px_mm_of(H0)), 1)
        if sig not in lg_cache:
            lg_cache[sig] = np.log(cv2.GaussianBlur(rgb8.astype(np.float32), (0, 0), sig) + 2.0)
        H1, info = refine_with_rings(lg_cache[sig], H0, design)
        rms = info["ring_rms_mm"] if info["ring_rms_mm"] is not None else 1.0
        lock = info["ring_frac"] * max(0.0, 0.17 - rms)
        tried.append((lock, H1, info, sig))
        if rms < 0.09 and info["ring_frac"] > 0.3:
            break
    tried = sorted(tried, key=lambda t: -t[0])[:3]
    T_hp, step, Ls = None, min(0.6, 0.5 * design.min_feature_mm), np.arange(L_range[0], L_range[1] + 1e-6, min(0.6, 0.5 * design.min_feature_mm))
    # The pattern itself decides among the best geometries: only a right one gives a sharp peak in L.
    best_scan = None
    for lock, H_, info_, sig_ in tried:
        radii, G_, good_ = prepare_polar(lg_cache[sig_], H_, design)
        if T_hp is None:
            T_hp = _template_f(design, radii)
        score_, cs_ = scan_L(G_, good_, T_hp, radii, Ls)
        z_ = float(_z_peak(score_).max())
        if best_scan is None or z_ > best_scan[0]:
            best_scan = (z_, H_, info_, G_, good_, score_, cs_)
        if z_ > 15:
            break
    lg_cache = None
    zmax, H, info, G, good, score, cs = best_scan
    res.update(info)
    res["px_per_mm"] = px_mm_of(H)
    res["H"] = H.tolist()
    res["ring_locked"] = bool(design.rings) and info["ring_rms_mm"] is not None and info["ring_rms_mm"] < 0.145 and info["ring_frac"] > 0.2
    res["usable_frac"] = float(good.mean())
    z = _z_peak(score)
    i = int(score.argmax())
    res["peak_z"] = float(z[i])
    far = np.abs(Ls - Ls[i]) > 6.0
    res["runner_up_ratio"] = float(score[far].max() / max(score[i], 1e-9)) if far.any() else 0.0
    L0, c0 = float(Ls[i]), float(cs[i])
    res["L_scan_mm"] = L0
    res["c_scan_rad"] = c0
    q, e_, cov, sc, V = None, None, None, None, None
    for it in range(3):
        V = None
        # Thirty-degree cells first. With few votes, sixty-degree cells have twice the signal per cell.
        for nsec in (12, 6):
            v = votes(G, T_hp, radii, design.zones, c0, L0, nsec=nsec, half_win_deg=(4.0, 2.0, 1.0)[it])
            V = np.array([x for x in v if x[3] >= 3.5 and not x[4]], float).reshape(-1, 5)
            if len(V) >= 12:
                break
        res["vote_nsec"] = nsec
        if len(V) < 8:
            res.update(n_votes=len(V), votes=V.tolist())
            res["status"] = "too_few_votes"
            return res
        q, e_, cov, sc = fit_votes(V[:, 0], V[:, 1], V[:, 2])
        c0, L0 = float(q[0]), float(q[1])
    t, r, tau = V[:, 0], V[:, 1], V[:, 2]
    res["votes"] = V.tolist()
    keep = np.abs(e_) < max(3 * sc, math.radians(0.3))
    res.update(L_mm=L0, c_deg=math.degrees(c0) % 360, n_votes=int(len(V)), n_inliers=int(keep.sum()),
               rms_deg=float(np.degrees(np.sqrt(np.mean(e_[keep] ** 2)))) if keep.any() else None,
               sigma_L_formal_mm=float(math.sqrt(cov[1, 1])),
               nuisance={"ty_mm": float(q[2]), "tx_mm": float(-q[3]), "c2": math.degrees(q[4]), "s2": math.degrees(q[5])})
    # Leave-one-out: sectors and zones.
    sec = np.unique(t)
    jack = []
    for a in sec:
        m = keep & (t != a)
        if m.sum() >= 8:
            jack.append(fit_votes(t[m], r[m], tau[m])[0][1])
    zon = np.unique(r)
    jz = []
    for a in zon:
        m = keep & (r != a)
        if m.sum() >= 8:
            jz.append(fit_votes(t[m], r[m], tau[m])[0][1])
    jack, jz = np.array(jack), np.array(jz)
    n = len(jack)
    res["sigma_L_jack_mm"] = float(math.sqrt((n - 1) / n * np.sum((jack - jack.mean()) ** 2))) if n > 2 else None
    res["zone_spread_mm"] = float(jz.max() - jz.min()) if len(jz) > 2 else None
    # Coverage, counted only where the pattern is believable: a sector counts when credible inlier votes
    # come from two or more radius zones (2026-11-10: a photo showing 200 deg had 3 of its 34 votes in the
    # covered-up part, and its gap came out as 60 deg).
    cred = keep & (V[:, 3] >= CRED_SNR)
    res["max_gap_deg"] = covered_gap_deg(t[cred], r[cred])
    res["r_span_mm"] = float(r[cred].max() - r[cred].min()) if cred.any() else 0.0
    res["n_zones"] = int(len(np.unique(r[keep])))
    res["sectors"] = int(len(np.unique(t[keep])))
    res["residual_curve"] = [(float(a), float(np.degrees(np.median(e_[keep & (r == a)])))) for a in zon if (keep & (r == a)).any()]
    res["status"] = verdict(res)
    return res


CRED_SNR = 5.0          # a vote this far above its cell's noise counts towards coverage
JOINT_STATUSES = ("ok", "few_inliers", "too_few_votes")   # weak alone, not wrong in geometry


def covered_gap_deg(t, r):
    """Largest angle with no sector covered at two or more radii."""
    covered = sorted({float(a) for a in np.unique(t) if len(np.unique(r[t == a])) >= 2})
    if not covered:
        return 360.0
    ang = np.array(covered)
    return float(np.degrees(np.diff(np.r_[ang, ang[0] + 2 * np.pi]).max()))


# Thresholds are set in sim_run.py against pictures with no pattern at all.
GATE = dict(peak_z=7.0, n_inliers=12, inlier_frac=0.6, max_gap_deg=200.0, r_span_mm=15.0, sigma_jack_mm=0.2,
            zone_spread_mm=0.8, runner_up=0.85, rms_deg=0.8)


def verdict(r):
    """The first reason not to trust this photo, or 'ok'."""
    g = GATE
    if r.get("design", "").startswith("pn") and not r.get("ring_locked") and r.get("peak_z", 0) < 12:
        return "rings_not_found"
    if r.get("peak_z", 0) < g["peak_z"]:
        return "weak_peak"
    if r.get("runner_up_ratio", 1) > g["runner_up"]:
        return "two_peaks"
    if r.get("n_inliers", 0) < g["n_inliers"] or r["n_inliers"] < g["inlier_frac"] * r["n_votes"]:
        return "few_inliers"
    if r.get("max_gap_deg", 360) > g["max_gap_deg"]:
        return "poor_angle_coverage"
    if r.get("r_span_mm", 0) < g["r_span_mm"]:
        return "poor_radius_coverage"
    if r.get("rms_deg") is None or r["rms_deg"] > g["rms_deg"]:
        return "large_residual"
    if r.get("sigma_L_jack_mm") is None or r["sigma_L_jack_mm"] > g["sigma_jack_mm"]:
        return "unstable_L"
    if r.get("zone_spread_mm") is None or r["zone_spread_mm"] > g["zone_spread_mm"]:
        return "shape_not_1_over_r"
    return "ok"


def joint(photos, min_z=7.0, scan_tol_mm=1.5):
    """Pool the cells of several photos of one disc: one L, but each photo keeps its own rotation and pose
    errors. Photos too weak alone can still count here. Their L scans must agree before their votes mix."""
    # A photo refused for its geometry (coverage, unstable L, shape) stays out: photos biased the same way
    # agree with each other, and pooled they only grow more confident (2026-11-10 injection test: three
    # groups of individually refused photos passed jointly, up to 4.4 frames off).
    use = [p for p in photos if (p.get("peak_z") or 0) >= min_z and p.get("votes") and p.get("L_scan_mm") is not None
           and (p.get("runner_up_ratio") or 1) <= GATE["runner_up"] and p.get("status") in JOINT_STATUSES]
    if len(use) < 2:
        return {"status": "unknown", "why": "fewer than two photos with a clear peak", "L_mm": None, "n_ok": len(use)}
    med = float(np.median([p["L_scan_mm"] for p in use]))
    use = [p for p in use if abs(p["L_scan_mm"] - med) <= scan_tol_mm]
    if len(use) < 2:
        return {"status": "unknown", "why": "the photos' L scans disagree", "L_mm": None, "n_ok": 0}

    def solve(sel):
        cols, ys, tags = [], [], []
        k = 0
        n_par = 1 + sum(1 + (4 if len(p["votes"]) >= 10 else 0) for p in sel)
        for p in sel:
            V = np.array(p["votes"], float)
            t, r = V[:, 0], V[:, 1]
            A = np.zeros((len(V), n_par))
            A[:, 0] = 1 / r
            A[:, 1 + k] = 1.0
            k += 1
            if len(V) >= 10:
                A[:, 1 + k] = np.cos(t) / r
                A[:, 2 + k] = np.sin(t) / r
                A[:, 3 + k] = np.cos(2 * t)
                A[:, 4 + k] = np.sin(2 * t)
                k += 4
            cols.append(A)
            # Taus are mod 360 degrees and each photo has its own rotation: take them near the photo's median.
            y = V[:, 2] - V[:, 2].mean()
            ys.append((y + np.pi) % (2 * np.pi) - np.pi)
        A, y = np.vstack(cols), np.concatenate(ys)
        w = np.ones(len(y))
        for _ in range(10):
            q, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
            e = y - A @ q
            sc = max(1.4826 * np.median(np.abs(e)), math.radians(0.05))
            w = np.sqrt(np.minimum(1.0, 1.5 * sc / np.maximum(np.abs(e), 1e-9)))
        return float(q[0]), e, sc, len(y)

    L, e, sc, n = solve(use)
    good = np.abs(e) < max(3 * sc, math.radians(0.3))
    inl = int(good.sum())
    # Coverage of the pooled cells on the disc: each photo's sectors turned by its own rotation.
    ts, rs, k = [], [], 0
    for p in use:
        V = np.array(p["votes"], float)
        c = math.radians(p["c_deg"]) if p.get("c_deg") is not None else p.get("c_scan_rad", 0.0)
        m = good[k:k + len(V)] & (V[:, 3] >= CRED_SNR)
        k += len(V)
        ts.append(np.round(((V[m, 0] - c) % (2 * np.pi)) / (2 * np.pi) * 12) % 12 * (2 * np.pi / 12))
        rs.append(V[m, 1])
    gap = covered_gap_deg(np.concatenate(ts), np.concatenate(rs)) if ts else 360.0
    r_all = np.concatenate([np.array(p["votes"])[:, 1] for p in use])
    span = float(r_all.max() - r_all.min())
    # Leaving any one photo out must not move L, and each photo's rotation should not be what sets it.
    drop = [solve([q for q in use if q is not p])[0] for p in use] if len(use) >= 3 else []
    spread = float(max(drop) - min(drop)) if drop else None
    res = {"L_mm": L, "n_ok": len(use), "n_votes": n, "n_inliers": inl, "r_span_mm": span, "drop_spread_mm": spread, "rms_deg": float(np.degrees(sc)), "max_gap_deg": gap, "mode": "joint"}
    if inl < 12 or inl < 0.6 * n:
        return {**res, "status": "unknown", "why": "few consistent cells", "L_mm": None}
    if gap > GATE["max_gap_deg"]:
        return {**res, "status": "unknown", "why": "the photos together do not go round the disc", "L_mm": None}
    if span < GATE["r_span_mm"]:
        return {**res, "status": "unknown", "why": "cells do not span enough radius", "L_mm": None}
    if spread is None:
        return {**res, "status": "provisional", "why": "only two photos, cannot check by leaving one out"}
    if spread > 2 * CD_FRAME_MM:
        return {**res, "status": "unknown", "why": "L moves when one photo is left out", "L_mm": None}
    return {**res, "status": "ok"}


def combine(photos, tol_mm=2 * CD_FRAME_MM):
    """Vote across photos of one disc. Two trusted photos that agree are enough. Otherwise the cells of all the
    photos are pooled. One photo alone is only provisional, and anything else is 'unknown': take another."""
    ok = [p for p in photos if p.get("status") == "ok"]
    if len(ok) < 2:
        j = joint(photos)
        if j["status"] != "unknown" or not ok:
            return j
    Ls = np.array([p["L_mm"] for p in ok])
    if len(ok) == 1:
        return {"status": "provisional", "why": "only one photo passed", "L_mm": float(Ls[0]), "n_ok": 1}
    med = float(np.median(Ls))
    agree = np.abs(Ls - med) <= tol_mm
    if agree.sum() < max(2, math.ceil(0.6 * len(ok))):
        return {"status": "unknown", "why": "photos disagree", "L_mm": None, "n_ok": len(ok), "spread_mm": float(Ls.max() - Ls.min())}
    return {"status": "ok", "L_mm": float(np.mean(Ls[agree])), "n_ok": len(ok), "n_agree": int(agree.sum()),
            "spread_mm": float(Ls[agree].max() - Ls[agree].min())}


def overlay(rgb8, H, design, path, scale=0.3):
    """Draw the rings where the fit says they are, to check by eye."""
    im = cv2.resize(rgb8, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)[..., ::-1].copy()
    t = np.linspace(0, 2 * np.pi, 361)
    for R, *_ in list(design.rings) + [(60.0,)]:
        x, y = tp.project(H, R * np.cos(t), R * np.sin(t))
        pts = (np.column_stack([x, y]) * scale).astype(np.int32)
        cv2.polylines(im, [pts], True, (0, 255, 0) if R < 60 else (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(path, im, [cv2.IMWRITE_JPEG_QUALITY, 85])


def rectified(rgb8, H, size=1400, half_mm=61.0):
    """The whole disc seen straight on, data side, from wherever the photo was taken. Not visible = black."""
    c = (np.arange(size) + 0.5) / size * 2 * half_mm - half_mm
    x, y = np.meshgrid(c, -c)
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    u = ((H[0, 0] * x + H[0, 1] * y + H[0, 2]) / w).astype(np.float32)
    v = ((H[1, 0] * x + H[1, 1] * y + H[1, 2]) / w).astype(np.float32)
    return cv2.remap(rgb8, u, v, cv2.INTER_AREA if False else cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
