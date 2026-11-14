"""Phone photos of a burned lab disc, rendered from what was burned and where it really is.

Built on docs/goals/photo-calibration/render.py (pinhole camera, barrel distortion, noise, JPEG), with the disc
part replaced by optics:

* Each pixel's ray meets the warped top surface (dish + saddle from the disc's truth), refracts into the
  polycarbonate (n 1.58, 0.6 mm on DVD) and lands on the recording layer at (r, alpha).
* The burn map says which recorded byte is there; A5, B9 and random data have along-track spectra from the A3
  wave model (disclab/data/wave_xyz.npz).
* delta_t = (c + l) . t (c, l: unit vectors to camera and lamp, t: track tangent) picks the colour each texture
  diffracts toward the camera; delta_t < 0.1 shows nothing. delta_r = (c + l) . r with delta_t ~ 0 is the groove's
  rainbow (lambda = pitch * delta_r); both ~ 0 is the lamp's mirror glare. So the visible part of the pattern,
  the rainbow arms and the glare all move with the pose, as on a real disc.
* Flash (fixed to the phone, 34 mm from the lens on an iPhone 17 Pro, the person's measurement) or a room lamp.

Not modelled: polarisation, multilayer dye optics, the true diffraction efficiency against the mirror reflection
(one constant, `tex_gain`), phone tone mapping/HDR/denoise, rolling shutter, the label side, fingers' shadows.
"""
from __future__ import annotations

import io
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .burnmap import BLANK, MIXED, load_map
from .lab import Lab, atomic_json
from .physics import Disc

DATA = Path(__file__).resolve().parent / "data" / "wave_xyz.npz"
TEXTURE_BYTES = {0xA5: "A5", 0xB9: "B9"}


@dataclass
class Pose:
    dist_mm: float = 300.0          # camera centre to disc centre
    tilt_deg: float = 20.0          # camera direction away from the disc normal
    az_deg: float = 0.0             # where the camera is, around the disc (disc frame)
    roll_deg: float = 0.0
    f35_mm: float = 26.0
    width: int = 4032
    height: int = 3024
    shift_frac: float = 0.0         # disc centre moved towards the frame edge
    light: str = "flash"            # flash (on the phone) or lamp (fixed in the room)
    flash_mm: tuple = (34.0, 0.0)   # flash position in the camera's x/y, mm from the lens
    lamp_mm: tuple = (0.0, -900.0, 1500.0)   # room lamp, disc frame
    lamp_radius_mm: float = 40.0
    disc_tilt_deg: tuple = (0.0, 0.0)        # disc not flat on the table (only matters for a room lamp)
    refraction: bool = True
    substrate_mm: float = 0.6
    n_pc: float = 1.58
    tex_gain: float = 1.0
    desaturate: float = 0.4
    veil: float = 0.04              # the room seen in the mirror (and scatter), relative to a bright texture
    veil_rgb: tuple = (0.80, 0.62, 1.0)      # through the dye: DVD-R mirrors look purple
    glare_gain: float = 60.0
    rainbow_gain: float = 6.0
    reflect: int = 2                # dim room things seen in the mirror
    blur_px: float = 1.0
    motion_px: float = 0.0
    noise: float = 1.5
    exposure: float = 1.0           # multiplies the auto exposure
    k1: float = -0.01
    jpeg: int = 90
    fingers: int = 0
    seed: int = 0


def _tables():
    z = np.load(DATA)
    return dict(delta=z["delta"], textures=[str(t) for t in z["textures"]], xyz=z["xyz"][:, :, 0, :],
                cmf_nm=z["cmf_nm"], cmf=z["cmf"], m=z["xyz_to_srgb"])


def _camera(p: Pose, rng):
    W, H = p.width, p.height
    f = p.f35_mm / 36.0 * W
    t, az = math.radians(p.tilt_deg), math.radians(p.az_deg)
    C = np.array([p.dist_mm * math.sin(t) * math.cos(az), p.dist_mm * math.sin(t) * math.sin(az),
                  p.dist_mm * math.cos(t)])
    z = -C / np.linalg.norm(C)
    x = np.cross([0.0, 0.0, 1.0], z)
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0.0, 0.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    roll = math.radians(p.roll_deg)
    Rr = np.array([[math.cos(roll), -math.sin(roll), 0], [math.sin(roll), math.cos(roll), 0], [0, 0, 1.0]])
    R = Rr @ R
    a = rng.uniform(0, 2 * math.pi)
    cx = W / 2 + p.shift_frac * H / 2 * math.cos(a)
    cy = H / 2 + p.shift_frac * H / 2 * math.sin(a)
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    return K, R, C, f


def _smooth(rng, x, y, n=5):
    a = rng.normal(0, 1, (n, n)).astype(np.float32)
    a = cv2.resize(a, (64, 64), interpolation=cv2.INTER_CUBIC)
    a /= np.abs(a).max() + 1e-6
    u = ((x + 62.0) / 124.0 * 63).astype(np.float32)
    v = ((62.0 - y) / 124.0 * 63).astype(np.float32)
    return cv2.remap(a, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _height(disc_t, x, y):
    r2 = (x * x + y * y) / 3600.0
    th = np.arctan2(y, x)
    sd = math.radians(disc_t["saddle_deg"])
    return disc_t["dish_mm"] * r2 + disc_t["saddle_mm"] * r2 * np.cos(2 * (th - sd))


def render(lab: Lab, disc_id: str, pose: Pose, tables=None):
    """Returns (uint8 RGB image, focal px, record of what was drawn)."""
    tables = tables or _tables()
    rng = np.random.default_rng(pose.seed)
    answers = lab.answers()
    truth = answers["discs"][disc_id]
    burn = lab.state()["burns"].get(disc_id)
    disc = Disc(truth, burn)
    bmap, r0, dr, da = load_map(lab, disc_id)
    nr, na = bmap.shape
    W, H = pose.width, pose.height
    K, R, C, f = _camera(pose, rng)
    Ki = np.linalg.inv(K)

    # Disc tilt on the table: the room (lamp) turns relative to the disc; the flash moves with the phone.
    tx, ty = (math.radians(v) for v in pose.disc_tilt_deg)
    Rt = (np.array([[1, 0, 0], [0, math.cos(tx), -math.sin(tx)], [0, math.sin(tx), math.cos(tx)]]) @
          np.array([[math.cos(ty), 0, math.sin(ty)], [0, 1, 0], [-math.sin(ty), 0, math.cos(ty)]]))
    if pose.light == "flash":
        lamp = C + R.T @ np.array([pose.flash_mm[0], pose.flash_mm[1], 0.0])
        lamp_ang = 3.0 / pose.dist_mm
    else:
        lamp = Rt.T @ np.asarray(pose.lamp_mm, float)
        lamp_ang = pose.lamp_radius_mm / np.linalg.norm(lamp)

    # Bounding box of the disc in the image.
    tc = np.linspace(0, 2 * np.pi, 90)
    pts = np.stack([62 * np.cos(tc), 62 * np.sin(tc), np.zeros_like(tc)], 1)
    cam = (R @ (pts - C).T)
    uv = K @ cam
    u_, v_ = uv[0] / uv[2], uv[1] / uv[2]
    x0_, x1_ = int(np.clip(u_.min() - 40, 0, W - 2)), int(np.clip(u_.max() + 40, 1, W))
    y0_, y1_ = int(np.clip(v_.min() - 40, 0, H - 2)), int(np.clip(v_.max() + 40, 1, H))
    yy, xx = np.mgrid[y0_:y1_, x0_:x1_].astype(np.float64)
    if pose.k1:
        dx, dy = xx - W / 2, yy - H / 2
        rho2 = (dx * dx + dy * dy) / (W * W / 4 + H * H / 4)
        g = 1 - pose.k1 * rho2
        xx, yy = W / 2 + dx * g, H / 2 + dy * g
    rays = np.stack([xx, yy, np.ones_like(xx)], -1) @ Ki.T @ R          # world directions (not unit)
    rays /= np.linalg.norm(rays, axis=-1, keepdims=True)

    # Ray meets the warped surface z = h(x, y).
    tpar = -C[2] / rays[..., 2]
    for _ in range(4):
        P = C + rays * tpar[..., None]
        h = _height(truth, P[..., 0], P[..., 1])
        tpar = (h - C[2]) / rays[..., 2]
    S = C + rays * tpar[..., None]
    sx, sy = S[..., 0], S[..., 1]
    if pose.refraction and pose.substrate_mm > 0:
        e = 0.05
        hx = (_height(truth, sx + e, sy) - _height(truth, sx - e, sy)) / (2 * e)
        hy = (_height(truth, sx, sy + e) - _height(truth, sx, sy - e)) / (2 * e)
        nrm = np.stack([-hx, -hy, np.ones_like(hx)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        d = rays
        cosi = -(d * nrm).sum(-1)
        eta = 1.0 / pose.n_pc
        k = 1 - eta * eta * (1 - cosi * cosi)
        tdir = eta * d + (eta * cosi - np.sqrt(np.maximum(k, 0)))[..., None] * nrm
        depth = pose.substrate_mm / np.maximum(-(tdir * nrm).sum(-1), 1e-3)
        Pl = S + tdir * depth[..., None]
        x, y = Pl[..., 0], Pl[..., 1]
    else:
        x, y = sx, sy
    r = np.hypot(x, y)
    alpha = np.arctan2(y, x)

    # What was burned there.
    ir = np.clip(np.round((r - r0) / dr).astype(np.int64), 0, nr - 1)
    ia = np.round(np.degrees(alpha % (2 * np.pi)) / da).astype(np.int64) % na
    code = bmap[ir, ia]
    code = np.where((r < r0) | (r > r0 + dr * (nr - 1)), BLANK, code)

    # Geometry of the light.
    cvec = C - S
    cvec /= np.linalg.norm(cvec, axis=-1, keepdims=True)
    lvec = lamp - S
    ldist = np.linalg.norm(lvec, axis=-1)
    lvec /= ldist[..., None]
    sv = cvec + lvec
    ca, sa = np.cos(alpha), np.sin(alpha)
    d_t = np.abs(-sv[..., 0] * sa + sv[..., 1] * ca)
    d_r = sv[..., 0] * ca + sv[..., 1] * sa
    irr = (np.linalg.norm(lamp) / ldist) ** 2                            # 1 at the disc centre

    # Texture colour against delta_t, the lamp's size blurring delta.
    delta = tables["delta"]
    sig = max(lamp_ang, 0.004) / (delta[1] - delta[0])
    xyz_tab = {name: cv2.GaussianBlur(tables["xyz"][i].reshape(-1, 1, 3).astype(np.float32), (1, 0), sig,
                                      borderType=cv2.BORDER_REPLICATE).reshape(-1, 3)
               for i, name in enumerate(tables["textures"])}
    ref = max(float(xyz_tab["B9"][:, 1].max()), float(xyz_tab["A5"][:, 1].max()))
    di = np.clip((d_t - delta[0]) / (delta[1] - delta[0]), 0, len(delta) - 1)
    lo = np.floor(di).astype(np.int64)
    fr = (di - lo)[..., None]
    hi = np.minimum(lo + 1, len(delta) - 1)
    inside = d_t >= delta[0]
    tex = np.zeros(r.shape + (3,), np.float32)
    names = np.full(code.shape, "", object)
    for byte, name in TEXTURE_BYTES.items():
        m = code == byte
        if m.any():
            tab = xyz_tab[name]
            tex[m] = (tab[lo[m]] * (1 - fr[m]) + tab[hi[m]] * fr[m])
    m = (code == MIXED) | ((code < 256) & ~np.isin(code, list(TEXTURE_BYTES)))
    if m.any():
        tab = xyz_tab["RND"]
        tex[m] = tab[lo[m]] * (1 - fr[m]) + tab[hi[m]] * fr[m]
    tex *= (inside * irr)[..., None] * (pose.tex_gain * truth.get("contrast_gain", 1.0) / ref)

    # Groove rainbow (first radial order, delta_t ~ 0) and the lamp's mirror glare (both ~ 0).
    pitch_um = disc.v * disc.b_mm * 1e3
    w_t = np.exp(-0.5 * (d_t / max(lamp_ang, 0.004)) ** 2)
    lam = pitch_um * np.abs(d_r) * 1000.0
    cmf = np.stack([np.interp(lam, tables["cmf_nm"], tables["cmf"][:, k], left=0, right=0) for k in range(3)], -1)
    grooved = (r > 22.6) & (r < 58.7)
    rain = cmf * (w_t * irr * grooved * pose.rainbow_gain)[..., None]
    # The lamp's mirror image: a disc of the lamp's angular size, soft only at its edge.
    la = max(lamp_ang, 0.004)
    w_g = 1.0 / (1.0 + np.exp(np.clip((np.hypot(d_t, d_r) / 2 - la) / (0.12 * la), -60, 60)))
    glare = (pose.glare_gain * w_g * irr)[..., None] * np.array([0.95, 1.0, 1.05], np.float32)
    vf = np.exp(0.35 * _smooth(rng, sx, sy))                            # the room is not uniform
    veil = (pose.veil * vf)[..., None] * np.asarray(pose.veil_rgb, np.float32)

    # Zero order: the mirror shows the room (veil) and the lamp (glare); a single-byte texture's marks take some
    # of it away. How much more A5 takes than B9 is not known from any model here; the person's photos show the
    # dark chips darker on the purple room reflection, so a per-disc fraction (answers: zero_order_dark) is used.
    dark = float(truth.get("zero_order_dark", 0.15))
    z0 = np.where(code == 0xA5, 1 - dark, np.where(code == BLANK, 1.0, 1 - 0.4 * dark)).astype(np.float32)
    trgb = np.clip(tex @ tables["m"].T, 0, None)
    grey = trgb.mean(-1, keepdims=True)
    trgb = grey + (1 - pose.desaturate) * (trgb - grey)      # phone colour processing, not modelled
    rgb = trgb + np.clip(rain @ tables["m"].T, 0, None) + (glare + veil) * z0[..., None]
    if pose.reflect:
        rf = np.zeros((248, 248), np.float32)
        for _ in range(pose.reflect):
            n = rng.integers(3, 6)
            cen = rng.uniform(40, 208, 2)
            pts = (cen + rng.normal(0, 28, (n, 2))).astype(np.int32)
            cv2.fillPoly(rf, [pts], float(rng.uniform(0, 1)))
        rf = cv2.GaussianBlur(rf, (0, 0), 2.0)
        u = ((sx + 62) / 124 * 247).astype(np.float32)
        v = ((62 - sy) / 124 * 247).astype(np.float32)
        rgb = rgb + 0.05 * cv2.remap(rf, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)[..., None]

    # Surround: table, hole, hub, clear rim.
    table = float(rng.uniform(0.02, 0.15))
    ring = (r > 58.7) & (r <= 60.0)
    hub = (r >= 7.5) & (r < 22.6)
    out = (r > 60.0) | (r < 7.5)
    rgb = np.where(out[..., None], table, rgb)
    rgb = np.where(hub[..., None], np.float32(rng.uniform(0.15, 0.35)) + glare * hub[..., None], rgb)
    rgb = np.where(ring[..., None], 0.5 * table + 0.03, rgb)
    for _ in range(pose.fingers):
        a = rng.uniform(0, 2 * math.pi)
        c_, s_ = math.cos(a), math.sin(a)
        dd = np.abs(-sx * s_ + sy * c_)
        along = sx * c_ + sy * s_
        skin = (dd < rng.uniform(6, 9)) & (along > rng.uniform(44, 54))
        rgb = np.where(skin[..., None], np.array([0.55, 0.42, 0.36], np.float32) * rng.uniform(0.6, 1.0), rgb)

    # Auto exposure on the disc away from glare, then sensor and JPEG.
    disc_px = (r > 24) & (r < 58) & (w_g < 0.01)
    level = float(np.quantile(rgb[disc_px].mean(-1), 0.98)) if disc_px.any() else 1.0
    gain = 0.85 / max(level, 1e-6) * pose.exposure
    img = rgb.astype(np.float32) * gain
    if pose.blur_px:
        img = cv2.GaussianBlur(img, (0, 0), pose.blur_px)
    if pose.motion_px:
        kk = np.zeros((int(2 * pose.motion_px) + 1,) * 2, np.float32)
        kk[len(kk) // 2, :] = 1.0 / len(kk)
        img = cv2.filter2D(img, -1, kk)
    lin = np.clip(img, 0, 1)
    full = np.full((H, W, 3), table * gain, np.float32)
    full[y0_:y1_, x0_:x1_] = lin
    full = np.clip(full, 0, 1)
    enc = np.where(full <= 0.0031308, 12.92 * full, 1.055 * np.power(full, 1 / 2.4) - 0.055) * 255.0
    enc = enc + rng.normal(0, pose.noise, enc.shape).astype(np.float32) * np.sqrt(np.clip(enc / 80.0, 0.2, 4.0))
    img8 = np.clip(enc, 0, 255).astype(np.uint8)
    rec = dict(disc=disc_id, pose=asdict(pose), camera_mm=C.tolist(), lamp_mm=lamp.tolist(),
               focal_px=f, visible_fraction=float(np.mean((d_t[disc_px] > 0.1))) if disc_px.any() else 0.0,
               glare_fraction=float(np.mean(w_g[(r > 24) & (r < 58)] > 0.01)))
    return img8, f, rec


def save_jpeg(img8, path, focal_px, width, quality=90):
    im = Image.fromarray(img8)
    exif = Image.Exif()
    ifd = exif.get_ifd(0x8769)
    ifd[0xA405] = int(round(focal_px / max(img8.shape[:2]) * 36))
    exif[0x0110] = "disclab phone"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=quality, exif=exif)
    return path


STYLES = {
    # The person's photos (IMG_7909-7919): the disc held in one hand under a room lamp, 15-26 cm from a 1x lens,
    # the room's reflection purple through the dye, fingers on the rim.
    "handheld": dict(dist=(150, 260), tilt=(8, 35), blur=(0.8, 2.5), motion=(0, 1.5), noise=(1.0, 3.0),
                     exposure=(0.7, 1.15), veil=(0.10, 0.45), shift=(0.0, 0.3), lamp=0.75, fingers=(0, 4),
                     lamp_off=(15, 60), lamp_dist=(900, 2500)),
    # Steadier, phone flash on, moderate tilt, disc on a table.
    "flash": dict(dist=(200, 320), tilt=(15, 28), blur=(0.6, 1.4), motion=(0, 0.4), noise=(1.0, 2.0),
                  exposure=(0.85, 1.1), veil=(0.05, 0.2), shift=(0.0, 0.15), lamp=0.0, fingers=(0, 1),
                  lamp_off=(15, 60), lamp_dist=(900, 2500)),
}


def random_pose(rng, style="handheld", **fixed):
    s = STYLES[style]
    U = lambda ab: float(rng.uniform(*ab))
    lamp = rng.random() < s["lamp"]
    off, ld, la = math.radians(U(s["lamp_off"])), U(s["lamp_dist"]), U((0, 2 * math.pi))
    p = Pose(dist_mm=U(s["dist"]), tilt_deg=U(s["tilt"]), az_deg=U((0, 360)), roll_deg=U((0, 360)),
             f35_mm=U((24, 26)), blur_px=U(s["blur"]), motion_px=U(s["motion"]), noise=U(s["noise"]),
             exposure=U(s["exposure"]), veil=U(s["veil"]), shift_frac=U(s["shift"]),
             light="lamp" if lamp else "flash",
             lamp_mm=(ld * math.sin(off) * math.cos(la), ld * math.sin(off) * math.sin(la), ld * math.cos(off)),
             lamp_radius_mm=U((20, 80)), fingers=int(rng.integers(*s["fingers"])) if s["fingers"][1] else 0,
             jpeg=int(rng.integers(82, 96)), reflect=int(rng.integers(0, 4)), seed=int(rng.integers(0, 2 ** 31)))
    for k, v in fixed.items():
        setattr(p, k, v)
    return p


def shoot(lab: Lab, disc_id: str, n: int, out_dir, *, seed=0, style="handheld", prefix="IMG", fixed=None, log=print):
    """Render n photos, record each pose in answers.json, return the file paths."""
    rng = np.random.default_rng([seed, abs(hash(disc_id)) % 100000])
    tables = _tables()
    out_dir = Path(out_dir)
    paths, recs = [], {}
    for i in range(n):
        pose = random_pose(rng, style, **(fixed(i, rng) if callable(fixed) else (fixed or {})))
        img, f, rec = render(lab, disc_id, pose, tables)
        name = f"{prefix}_{seed:03d}{i:02d}.jpg"
        path = save_jpeg(img, out_dir / name, f, pose.width, pose.jpeg)
        rec["file"] = str(path)
        recs[f"{out_dir.name}/{name}"] = rec
        paths.append(path)
        log(f"disclab: {name}: tilt {pose.tilt_deg:.1f} deg at {pose.az_deg:.0f} deg, {pose.dist_mm:.0f} mm, "
            f"pattern visible on {rec['visible_fraction']:.0%} of the disc")
    answers = lab.answers()
    answers.setdefault("photos", {}).update(recs)
    atomic_json(lab.answers_path, answers)
    lab.step("photos", status="ok", disc=disc_id, paths=[str(p) for p in paths])
    return paths


def add_parser(sub):
    s = sub.add_parser("photos", help="render phone photos of a burned lab disc")
    s.add_argument("--lab", required=True)
    s.add_argument("--disc", required=True)
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--style", default="handheld", choices=sorted(STYLES))
    s.add_argument("--width", type=int, default=4032, help="render width in pixels")
    s.add_argument("--height", type=int, default=3024, help="render height in pixels")
    s.set_defaults(func=lambda a: dict(paths=[str(p) for p in
        shoot(Lab(a.lab), a.disc, a.n, a.out, seed=a.seed, style=a.style,
              fixed=dict(width=a.width, height=a.height))]))
