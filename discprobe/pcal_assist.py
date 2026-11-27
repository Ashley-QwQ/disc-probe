"""A photo reading a person can steer by hand (photo page, "align by hand").

The person does what eyes do well and the program does the rest:
  1. register()     - the person clicks the outermost burned ring a few times and the centre; the frozen reader's
                      ring fit polishes the homography. It locks when clicks are within about 0.5 mm.
  2. candidates()   - the frozen L scan (pcal.scan_L) lists the best (L, c) peaks; each is drawn as the
                      12 o'clock arrow where that peak puts it, and the person says which outline sits on the arrow.
  3. seeded_read()  - the frozen reader's own vote, fit, leave-one-out and verdict, run from the chosen peak.
                      From the reader's own seed it reproduces read_photo exactly (tests/test_pcal_assist.py).

Nothing here loosens a gate: a person can fix the registration and pick a peak, never pass a photo.
Only frozen functions of pcal are called; pcal.py is not changed. Design and measurements:
D:/dp-dev/tmp/manual-align/DESIGN.md (11-22).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from . import pcal
from . import tilephoto as tp

ARROW_FILE = Path(pcal.__file__).parent / "web" / "home" / "design" / "direction-arrow.json"
RIM_MM = 60.0
CD_LIMIT_MM = 300 * pcal.CD_FRAME_MM


def arrow_polygon():
    """The direction arrow on the data side, design millimetres, tip at 12 o'clock (90 degrees)."""
    return np.array(json.loads(ARROW_FILE.read_text(encoding="utf-8"))["data_side_mm"], float)


def project(H, x, y):
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    return (H[0, 0] * x + H[0, 1] * y + H[0, 2]) / w, (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / w


def disc_to_image(H, r, theta):
    """Image pixels of disc points given in polar design coordinates (mm, radians)."""
    x, y = project(H, r * np.cos(theta), r * np.sin(theta))
    return np.column_stack([x, y])


def px_per_mm(H):
    o = H @ [0, 0, 1]
    q = H @ [40, 0, 1]
    return float(np.linalg.norm(q[:2] / q[2] - o[:2] / o[2]) / 40)


def log_image(rgb8, H):
    """The reader's log colour image at the blur it would choose for this registration."""
    sigma = round(max(0.5, 0.08 * px_per_mm(H)), 1)
    return np.log(cv2.GaussianBlur(rgb8.astype(np.float32), (0, 0), sigma) + 2.0)


def handedness(H):
    """+1 or -1: whether design x, y map to the image as a turn or a mirror. The reader's own homographies
    are -1 (data side seen through the polycarbonate, image y down)."""
    o, a, b = (np.array(project(H, *p)) for p in ((0, 0), (40, 0), (0, 40)))
    return float(np.sign((a - o)[0] * (b - o)[1] - (a - o)[1] * (b - o)[0]))


# ---------------------------------------------------------------- 1. registration from clicks

def snap_edge(rgb8, hub, clicks, snap_px=None):
    """Move each click along the ray from the hub to the strongest edge within snap_px."""
    h, w = rgb8.shape[:2]
    scale = 1000.0 / max(h, w)
    small = cv2.resize(rgb8, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA).astype(np.float32).mean(-1)
    small = cv2.GaussianBlur(small, (0, 0), 1.0)
    gx, gy = cv2.Sobel(small, cv2.CV_32F, 1, 0), cv2.Sobel(small, cv2.CV_32F, 0, 1)
    reach = 12.0 if snap_px is None else snap_px * scale
    hx, hy = hub[0] * scale, hub[1] * scale
    out = []
    for x, y in clicks:
        d = np.array([x * scale - hx, y * scale - hy])
        r0 = float(np.linalg.norm(d))
        if r0 < 20:
            continue
        u = d / r0
        rs = np.arange(r0 - reach, r0 + reach, 0.5)
        xs, ys = hx + rs * u[0], hy + rs * u[1]
        ok = (xs > 1) & (ys > 1) & (xs < small.shape[1] - 2) & (ys < small.shape[0] - 2)
        if ok.sum() < 5:
            continue
        xi, yi = xs[ok].astype(int), ys[ok].astype(int)
        g = np.abs(gx[yi, xi] * u[0] + gy[yi, xi] * u[1])
        j = int(g.argmax())
        out.append((xs[ok][j] / scale, ys[ok][j] / scale))
    return np.array(out, float).reshape(-1, 2)


def register(rgb8, clicks, hub_click, design, radius_mm=None, snap=False):
    """Homography from clicks on one circle of known radius (at least five, spread round) and on the centre,
    then the frozen ring fit. Default circle: the outermost burned ring, which lies on the data layer. The disc
    edge is a poor choice: thickness, bevel and fingers put eyeballed edge clicks at 59.5-67.8 mm in the data
    plane on two CD photos (2026-11-22), and neither locked. snap=True moves each click to the strongest edge along its ray, which
    suits the disc edge only; near the rings it lands on code edges."""
    if len(clicks) < 5:
        raise ValueError("click the ring at least five times, spread around it")
    radius = design.rings[-1][0] if radius_mm is None else float(radius_mm)
    pts = snap_edge(rgb8, hub_click, clicks) if snap else np.asarray(clicks, float).reshape(-1, 2)
    if len(pts) < 5:
        raise ValueError("too few clicks landed near an edge")
    e = tp.fit_ellipse(pts)
    H0 = tp.perspective_h(e, np.asarray(hub_click, float), 0.0, False) @ np.diag([RIM_MM / radius, RIM_MM / radius, 1.0])
    if handedness(H0) > 0:
        H0 = H0 @ np.diag([1.0, -1.0, 1.0])
    H, info = pcal.refine_with_rings(log_image(rgb8, H0), H0, design)
    locked = info["ring_rms_mm"] is not None and info["ring_rms_mm"] < 0.145 and info["ring_frac"] > 0.2
    return dict(H=H, ring_rms_mm=info["ring_rms_mm"], ring_frac=info["ring_frac"], ring_locked=bool(locked),
                clicked_points=pts.tolist(), radius_mm=radius, px_per_mm=px_per_mm(H))


def overlay_lines(H, design, n=240):
    """Rim and burned rings as image polylines, for the person to check the registration."""
    t = np.linspace(0, 2 * math.pi, n + 1)
    rings = [disc_to_image(H, np.full_like(t, R), t).tolist() for R, _, _ in design.rings]
    return dict(rim=disc_to_image(H, np.full_like(t, RIM_MM), t).tolist(), rings=rings)


# ---------------------------------------------------------------- 2. candidates

def polar(rgb8, H, design):
    radii, G, good = pcal.prepare_polar(log_image(rgb8, H), H, design)
    return radii, G, good, pcal._template_f(design, radii)


def arrow_tip_deg(L, c):
    return math.degrees(math.pi / 2 + c + L / 52.8) % 360


def arrow_outline(H, L, c, step_mm=0.1):
    """The arrow where (L, c) says it is: every edge sampled finely, since L / r bends straight edges."""
    poly = arrow_polygon()
    pts = []
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        n = max(2, int(np.linalg.norm(b - a) / step_mm))
        s = np.linspace(0, 1, n, endpoint=False)[:, None]
        p = a + s * (b - a)
        r = np.hypot(p[:, 0], p[:, 1])
        th = np.arctan2(p[:, 1], p[:, 0]) + c + L / r
        pts.append(disc_to_image(H, r, th))
    return np.vstack(pts + [pts[0][:1]]).tolist()


def scan_grid(limit_mm=45.0):
    """The reader's own L grid (read_photo: -45..45 mm in 0.6 mm steps), widened on the same lattice when asked.
    peak_z is a robust z over the whole grid, so only the default range reproduces the reader's peak_z."""
    Ls = np.arange(-45.0, 45.0 + 1e-6, 0.6)
    extra = int(math.ceil(max(0.0, limit_mm - 45.0) / 0.6))
    if extra:
        Ls = np.concatenate([-45.0 - 0.6 * np.arange(extra, 0, -1), Ls, 45.0 + 0.6 * np.arange(1, extra + 1)])
    return Ls


def candidates(G, good, T_hp, radii, limit_mm=45.0, k=4, family_deg=3.0):
    """Peaks of the frozen L scan. Peaks whose arrows land within family_deg of each other are one family:
    the person can tell families apart by the arrow but not the L sidelobes inside one (about 3 mm apart
    on the pn_burn target), so those stay for the vote fit to decide."""
    Ls = scan_grid(limit_mm)
    score, cs = pcal.scan_L(G, good, T_hp, radii, Ls)
    z = pcal._z_peak(score)
    peaks = [i for i in range(len(Ls)) if (i == 0 or score[i] >= score[i - 1]) and (i == len(Ls) - 1 or score[i] >= score[i + 1])]
    peaks.sort(key=lambda i: -score[i])
    families = []
    for i in peaks[:40]:
        tip = arrow_tip_deg(Ls[i], cs[i])
        for f in families:
            if abs((tip - f["arrow_tip_deg"] + 180) % 360 - 180) <= family_deg:
                f["sidelobes_mm"].append(round(float(Ls[i]), 2))
                break
        else:
            if len(families) < k:
                far = np.abs(Ls - Ls[i]) > 6.0
                families.append(dict(L_scan_mm=float(Ls[i]), c_scan_rad=float(cs[i]), peak_z=float(z[i]),
                                     runner_up_ratio=float(score[far].max() / max(score[i], 1e-9)) if far.any() else 0.0,
                                     arrow_tip_deg=tip, sidelobes_mm=[]))
    return families


# ---------------------------------------------------------------- 3. seeded read

def seeded_read(G, T_hp, radii, zones, L0, c0, *, peak_z, runner_up_ratio, ring_locked, design_name="pn_burn"):
    """read_photo after its L scan, unchanged, started from (L0, c0). The verdict is pcal.verdict."""
    res = {"design": design_name, "ring_locked": bool(ring_locked), "peak_z": float(peak_z),
           "runner_up_ratio": float(runner_up_ratio), "L_scan_mm": float(L0), "c_scan_rad": float(c0)}
    q, e_, cov, sc, V = None, None, None, None, None
    for it in range(3):
        V = None
        for nsec in (12, 6):
            v = pcal.votes(G, T_hp, radii, zones, c0, L0, nsec=nsec, half_win_deg=(4.0, 2.0, 1.0)[it])
            V = np.array([x for x in v if x[3] >= 3.5 and not x[4]], float).reshape(-1, 5)
            if len(V) >= 12:
                break
        res["vote_nsec"] = nsec
        if len(V) < 8:
            res.update(n_votes=len(V), votes=V.tolist())
            res["status"] = "too_few_votes"
            return res
        q, e_, cov, sc = pcal.fit_votes(V[:, 0], V[:, 1], V[:, 2])
        c0, L0 = float(q[0]), float(q[1])
    t, r, tau = V[:, 0], V[:, 1], V[:, 2]
    res["votes"] = V.tolist()
    keep = np.abs(e_) < max(3 * sc, math.radians(0.3))
    res.update(L_mm=L0, c_deg=math.degrees(c0) % 360, n_votes=int(len(V)), n_inliers=int(keep.sum()),
               rms_deg=float(np.degrees(np.sqrt(np.mean(e_[keep] ** 2)))) if keep.any() else None,
               sigma_L_formal_mm=float(math.sqrt(cov[1, 1])),
               nuisance={"ty_mm": float(q[2]), "tx_mm": float(-q[3]), "c2": math.degrees(q[4]), "s2": math.degrees(q[5])})
    sec = np.unique(t)
    jack = []
    for a in sec:
        m = keep & (t != a)
        if m.sum() >= 8:
            jack.append(pcal.fit_votes(t[m], r[m], tau[m])[0][1])
    zon = np.unique(r)
    jz = []
    for a in zon:
        m = keep & (r != a)
        if m.sum() >= 8:
            jz.append(pcal.fit_votes(t[m], r[m], tau[m])[0][1])
    jack, jz = np.array(jack), np.array(jz)
    n = len(jack)
    res["sigma_L_jack_mm"] = float(math.sqrt((n - 1) / n * np.sum((jack - jack.mean()) ** 2))) if n > 2 else None
    res["zone_spread_mm"] = float(jz.max() - jz.min()) if len(jz) > 2 else None
    cred = keep & (V[:, 3] >= pcal.CRED_SNR)
    res["max_gap_deg"] = pcal.covered_gap_deg(t[cred], r[cred])
    res["r_span_mm"] = float(r[cred].max() - r[cred].min()) if cred.any() else 0.0
    res["n_zones"] = int(len(np.unique(r[keep])))
    res["sectors"] = int(len(np.unique(t[keep])))
    res["residual_curve"] = [(float(a), float(np.degrees(np.median(e_[keep & (r == a)])))) for a in zon if (keep & (r == a)).any()]
    res["status"] = pcal.verdict(res)
    return res


def vote_cells(H, votes, zones, nsec, n=12):
    """Each vote as a closed image polygon (its sector at its zone), for the green layer."""
    out = []
    half = math.pi / nsec
    for a0, rm, _, snr, _ in votes:
        lo, hi = min(zones, key=lambda z: abs((z[0] + z[1]) / 2 - rm))
        th = np.linspace(a0 - half, a0 + half, n)
        ring = np.vstack([disc_to_image(H, np.full(n, lo), th), disc_to_image(H, np.full(n, hi), th[::-1])])
        out.append(dict(snr=float(snr), poly=ring.tolist()))
    return out
