"""Read a phone photo of the tile palette target: fit a homography from the disc plane to
the photo, check it by decoding tile IDs, then read every swatch's colour.

Fitting works on a reduced copy of the photo:
1. Rays from the hub find the outer rim; an ellipse through those points gives an affine
   first guess (centre, axes, tilt) that leaves the in-plane rotation and mirroring open.
2. Every rotation (1 degree steps, both mirrorings) is scored by how well the predicted ID
   cells (A5 = -1, 92 = +1) match the high-passed photo. The score is the mean absolute
   local correlation, because A5 and 92 swap brightness from one region to the next.
3. The best guess is refined to a full homography (8 parameters) by Nelder-Mead.
Tiles are then read on the full-resolution photo with tilescan.read_tiles.
"""

from __future__ import annotations

import csv
import json
import math
import os

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.optimize import minimize

from . import scan, tiledisc as T, tilescan
from .imagedisc import CELL_MM, HALF_MM, SIZE

FIT_WIDTH = 1200
DISC_R = 60.0


def load_photo(path):
    from PIL import Image, ImageOps
    if "blind" in os.path.basename(path).lower():
        raise ValueError("refusing to read a file whose name contains 'blind'")
    with Image.open(path) as im:
        return np.asarray(ImageOps.exif_transpose(im).convert("RGB"), dtype=np.float32) / 255.0


def _reduce(rgb, width):
    from PIL import Image
    f = width / rgb.shape[1]
    im = Image.fromarray((rgb * 255).astype(np.uint8)).resize((width, round(rgb.shape[0] * f)), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0, f


def fit_ellipse(pts):
    """Direct least-squares ellipse (Fitzgibbon); returns centre, semi-axes (a >= b), angle of a."""
    x, y = pts[:, 0], pts[:, 1]
    D = np.column_stack([x * x, x * y, y * y, x, y, np.ones_like(x)])
    S = D.T @ D
    C = np.zeros((6, 6)); C[0, 2] = C[2, 0] = 2; C[1, 1] = -1
    w, v = np.linalg.eig(np.linalg.solve(S, C))
    p = np.real(v[:, np.argmax(np.real(w) > 0) if np.any(np.real(w) > 0) else 0])
    a, b, c, d, e, f = p
    den = b * b - 4 * a * c
    x0, y0 = (2 * c * d - b * e) / den, (2 * a * e - b * d) / den
    num = 2 * (a * e * e + c * d * d - b * d * e + den * f)
    root = math.sqrt((a - c) ** 2 + b * b)
    ax1 = -math.sqrt(abs(num * (a + c + root))) / den
    ax2 = -math.sqrt(abs(num * (a + c - root))) / den
    ang = 0.5 * math.atan2(-b, c - a)
    if ax1 < ax2:
        ax1, ax2, ang = ax2, ax1, ang + math.pi / 2
    return x0, y0, abs(ax1), abs(ax2), ang


def rim_points(grey, hub):
    """Outermost strong dark-to-light step along rays from the hub (the disc edge against the room)."""
    h, w = grey.shape
    pts = []
    g = gaussian_filter(grey, 1.5)
    for th in np.linspace(0, 2 * math.pi, 720, endpoint=False):
        r = np.arange(40, 2 * max(h, w), 1.0)
        x, y = hub[0] + r * math.cos(th), hub[1] - r * math.sin(th)
        inside = (x >= 1) & (y >= 1) & (x < w - 2) & (y < h - 2)
        r, x, y = r[inside], x[inside], y[inside]
        if len(r) < 60:
            continue
        d = np.gradient(scan._sample(g, x, y))
        strong = np.nonzero(d > max(0.02, 0.4 * d.max()))[0]
        if len(strong) == 0:
            continue
        j = strong[-1]
        # A ray that leaves the photo before the disc ends gives no rim point.
        if j > len(r) - 4:
            continue
        pts.append((x[j], y[j]))
    return np.array(pts)


def ransac_ellipse(pts, iters=400, tol=4.0, seed=0):
    rng = np.random.default_rng(seed)
    best, best_in = None, 0
    for _ in range(iters):
        sel = pts[rng.choice(len(pts), 6, replace=False)]
        try:
            e = fit_ellipse(sel)
        except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
            continue
        d = _ellipse_dist(pts, e)
        n = int((d < tol).sum())
        if n > best_in:
            best, best_in = e, n
    inl = pts[_ellipse_dist(pts, best) < tol]
    return fit_ellipse(inl), len(inl)


def _ellipse_dist(pts, e):
    x0, y0, a, b, ang = e
    c, s = math.cos(ang), math.sin(ang)
    u = (pts[:, 0] - x0) * c + (pts[:, 1] - y0) * s
    v = -(pts[:, 0] - x0) * s + (pts[:, 1] - y0) * c
    return np.abs(np.hypot(u / a, v / b) - 1) * (a + b) / 2


def affine_h(e, psi, mirror):
    """Homography (disc mm -> image px) of the weak-perspective guess."""
    x0, y0, a, b, ang = e
    R = lambda t: np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    A = R(ang) @ np.diag([a / DISC_R, b / DISC_R]) @ R(psi) @ np.diag([1.0, -1.0 if mirror else 1.0])
    A = A @ np.diag([1.0, -1.0])                      # design y up, image y down
    H = np.eye(3)
    H[:2, :2], H[:2, 2] = A, (x0, y0)
    return H


def ellipse_conic(e):
    """3x3 symmetric conic matrix of an ellipse (x0, y0, a, b, angle)."""
    x0, y0, a, b, ang = e
    c, s = math.cos(ang), math.sin(ang)
    R = np.array([[c, -s], [s, c]])
    M = R @ np.diag([1 / a ** 2, 1 / b ** 2]) @ R.T
    t = np.array([x0, y0])
    C = np.zeros((3, 3))
    C[:2, :2] = M
    C[:2, 2] = C[2, :2] = -M @ t
    C[2, 2] = t @ M @ t - 1
    return C


def conic_ellipse(C):
    M, g = C[:2, :2], C[:2, 2]
    t = -np.linalg.solve(M, g)
    k = t @ M @ t - C[2, 2]
    w, v = np.linalg.eigh(M / k)
    a, b = 1 / math.sqrt(w[0]), 1 / math.sqrt(w[1])
    return float(t[0]), float(t[1]), a, b, math.atan2(v[1, 0], v[0, 0])


def perspective_h(rim, hub, psi, mirror):
    """Homography from the rim ellipse and the image of the disc centre: the polar of the centre
    with respect to the rim conic is the vanishing line; map it to infinity, then the rim is an
    ellipse of an affine view, which fixes everything but rotation and mirroring."""
    C = ellipse_conic(rim)
    l = C @ np.array([hub[0], hub[1], 1.0])
    Hp = np.eye(3)
    Hp[2] = l / l[2]                                   # image -> affinely rectified
    Hpi = np.linalg.inv(Hp)
    e2 = conic_ellipse(Hpi.T @ C @ Hpi)
    c2 = Hp @ np.array([hub[0], hub[1], 1.0])
    e2 = (c2[0] / c2[2], c2[1] / c2[2]) + e2[2:]       # rectified rim is centred on the hub
    return Hpi @ affine_h(e2, psi, mirror)


def project(H, x, y):
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    return (H[0, 0] * x + H[0, 1] * y + H[0, 2]) / w, (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / w


class Scorer:
    def __init__(self, grey, labels, textures, sigma=12.0):
        self.h, self.w = grey.shape
        hp = grey - gaussian_filter(grey, 5)
        self.G = hp / (np.sqrt(gaussian_filter(hp * hp, 15)) + 1e-4)
        self.value = np.zeros(len(textures), np.float32)
        self.value[textures.index("A5")], self.value[textures.index("92")] = -1, 1
        self.labels, self.sigma = labels, sigma
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        self.uv = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5]).astype(np.float64)

    def predicted(self, H):
        Hi = np.linalg.inv(H)
        u, v = self.uv
        w = Hi[2, 0] * u + Hi[2, 1] * v + Hi[2, 2]
        x = (Hi[0, 0] * u + Hi[0, 1] * v + Hi[0, 2]) / w
        y = (Hi[1, 0] * u + Hi[1, 1] * v + Hi[1, 2]) / w
        ix = np.floor((x + HALF_MM) / CELL_MM).astype(np.int64)
        iy = np.floor((HALF_MM - y) / CELL_MM).astype(np.int64)
        ok = (ix >= 0) & (ix < SIZE) & (iy >= 0) & (iy < SIZE) & (w > 0)
        p = np.zeros(ix.shape, np.float32)
        p[ok] = self.value[self.labels[iy[ok], ix[ok]]]
        return p.reshape(self.h, self.w)

    def __call__(self, H):
        P = self.predicted(H)
        local = gaussian_filter(P * self.G, self.sigma)
        norm = gaussian_filter(np.abs(P), self.sigma) + 1e-3
        return float(np.mean(np.abs(local)) / np.mean(norm))


def fit(rgb_small, labels, textures, hub, log=print, auto_hub=False):
    grey = rgb_small.mean(-1)
    pts = rim_points(grey, hub)
    e, n_in = ransac_ellipse(pts)
    if auto_hub:
        # Near head-on, the rim's centre is close to the image of the disc centre: cast again from there.
        hub = (e[0], e[1])
        pts = rim_points(grey, hub)
        e, n_in = ransac_ellipse(pts)
        hub = (e[0], e[1])
    log(f"rim: {len(pts)} points, {n_in} on the ellipse; centre ({e[0]:.0f}, {e[1]:.0f}), axes {e[2]:.0f} x {e[3]:.0f} px")
    sc = Scorer(grey, labels, textures)
    best = (-1, None)
    for mirror in (False, True):
        for deg in range(0, 360, 2):
            s = sc(perspective_h(e, hub, math.radians(deg), mirror))
            if s > best[0]:
                best = (s, (deg, mirror))
    deg, mirror = best[1]
    log(f"rotation sweep: {deg} deg, mirrored {mirror}, score {best[0]:.3f}")
    H0 = perspective_h(e, hub, math.radians(deg), mirror)
    # Refine: 8 homography entries scaled to comparable steps, maximise the score.
    scale = np.array([1e-2, 1e-2, 5.0, 1e-2, 1e-2, 5.0, 2e-5, 2e-5])
    p0 = H0.ravel()[:8] / H0[2, 2]
    def cost(q):
        H = np.append(q * scale, 1.0).reshape(3, 3)
        return -sc(H)
    q = p0 / scale
    for sigma in (12.0, 6.0):
        sc.sigma = sigma
        res = minimize(cost, q, method="Nelder-Mead", options={"maxiter": 3000, "xatol": 1e-3, "fatol": 1e-6})
        q = res.x
        log(f"refine (sigma {sigma}): score {-res.fun:.3f}")
    return np.append(q * scale, 1.0).reshape(3, 3), {"rim_points": len(pts), "rim_inliers": n_in,
                                                     "sweep_deg": deg, "mirrored": mirror}


def analyse(path: str, layout_path: str, out_dir: str, hub=None, log=print) -> dict:
    with open(layout_path, encoding="utf-8") as f:
        lay = json.load(f)
    labels, textures, _ = T.design(lay["palette"])
    rgb = load_photo(path)
    small, fs = _reduce(rgb, FIT_WIDTH)
    hub_s = (hub[0] * fs, hub[1] * fs) if hub else (small.shape[1] / 2, small.shape[0] / 2)
    H_small, info = fit(small, labels, textures, hub_s, log, auto_hub=hub is None)
    H = np.diag([1 / fs, 1 / fs, 1.0]) @ H_small            # full-resolution pixels

    def to_xy(r, a):
        return project(H, r * np.cos(a), r * np.sin(a))

    rows, n_ok = tilescan.read_tiles(lay, rgb, to_xy)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "tiles.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"photo": os.path.basename(path), "homography_disc_mm_to_px": H.tolist(), **info,
               "tiles": len(rows), "ids_ok": int(n_ok)}
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    _overlay(rgb, H, lay, os.path.join(out_dir, "overlay.jpg"), rows)
    log(f"{os.path.basename(path)}: IDs read {n_ok}/{len(rows)}")
    return summary


def _overlay(rgb, H, lay, path, rows):
    from PIL import Image, ImageDraw
    im = Image.fromarray((rgb * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    ok = {(int(r["ring"]), int(r["sector"])): r["id_ok"] for r in rows}
    for k, nsec in enumerate(lay["sectors_per_ring"]):
        r_in, r_out = T.RING_EDGES_MM[k] + T.GAP_MM / 2, T.RING_EDGES_MM[k + 1] - T.GAP_MM / 2
        for j in range(nsec):
            r_mid = (r_in + r_out) / 2
            a0 = j * 2 * math.pi / nsec + T.GAP_MM / 2 / r_mid
            a1 = (j + 1) * 2 * math.pi / nsec - T.GAP_MM / 2 / r_mid
            ts = np.linspace(a0, a1, 12)
            poly = [project(H, r * math.cos(t), r * math.sin(t)) for r, tt in ((r_in, ts), (r_out, ts[::-1])) for t in tt]
            d.line(poly + [poly[0]], fill=(0, 255, 0) if ok[(k, j)] else (255, 60, 60), width=4)
    im.thumbnail((1600, 1600))
    im.save(path, quality=88)
