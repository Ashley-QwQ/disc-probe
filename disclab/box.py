"""A box of made-up discs, with the truth kept in answers.json.

Spread model (see README.md for which parts are measured and which are assumed):

* Angle geometry is a property of the stamper. Angles depend only on u = r0/b and v = pitch/b (bits per turn
  are fixed when the groove is moulded; shrinkage scales r, pitch and b together). Real evidence: separate
  RITEKF1 discs burned by the GH70N fit u = 180518.44 +/- 0.05 and v = 5.591208 +/- 1e-6 (results/geo-H-*).
  So discs from one stamper share u, v and the variable-pitch curve almost exactly; a box may mix stampers.
* Per disc: shrinkage (mm scale only), eccentricity of the groove against the hole, warp (dish + saddle), dye
  contrast, and flaws (an unreadable arc). A u/v jitter per disc is available (uv_noise) to test sensitivity:
  1e-7 in v alone twists the outer rim 1.6 deg.
* Along-track constant L belongs to the path: the reading drive's completion point and head offset, and the
  writer/mode. It is stored per reader/writer below, never per disc.
"""
from __future__ import annotations

import math

import numpy as np

from .lab import Lab, atomic_json

# Batch means. dvd-r is centred on the real GH70N + RITEKF1 fit; the others are nominal-ish.
MEDIA = {
    "dvd-r": dict(family="dvd", profile=0x11, bits_per_sector=38688, b_nm=133.3, u=180518.44, v=5.591208,
                  capacity=2298496, mid="DLABR01", varpitch_rms_deg=0.04),
    "dvd+r": dict(family="dvd", profile=0x1B, bits_per_sector=38688, b_nm=133.3, u=180320.0, v=5.5600,
                  capacity=2295104, mid="DLAB/R01/001", varpitch_rms_deg=0.04),
    "cd-r": dict(family="cd", profile=0x09, bits_per_sector=588 * 98, b_nm=277.66, u=91043.5, v=5.419946,
                 capacity=359849, mid="ATIP 97:26:66", varpitch_rms_deg=1.5),
    "bd-r": dict(family="bd", profile=0x41, bits_per_sector=30066.75, b_nm=74.5, u=322150.0, v=4.2953,
                 capacity=12219392, mid="DLABBD-R01", varpitch_rms_deg=0.05),
}

# Reading drives. completion_mm/head_mm add up to the path's along-track constant (per family and burn mode).
# The GH70N DVD value (+0.19 mm in total) is the centre of the person's two photo groups (+0.08..+0.12 and
# +0.25..+0.28 mm) and of the sealed blind test (0.19 mm off a +2.291 mm injection). The split between
# completion point and head offset is unknown; only the sum is observable anywhere.
READERS = {
    "gh70n": dict(vendor="DISCLAB", product="GH70N-LIKE", revision="LAB1", mode="cav",
                  rev_period_ms={"dvd": 20.72, "cd": 20.0, "bd": 20.0}, jitter_us=13.0, outlier_rate=0.01,
                  fua_honoured=True, flush_honoured=False, reread_delay_ms=19.5, cache_blocks=6,
                  head_mm=0.06,
                  completion_mm={"dvd": 0.13, "cd:mode2form1": 206 * 0.16326, "cd:mode1": 7 * 0.16326, "bd": 0.0},
                  write_speeds_x={"dvd": [4, 6, 8, 12, 16], "cd": [16, 24, 32, 48], "bd": [2, 4, 6]}),
    "slim-clv": dict(vendor="DISCLAB", product="SLIM-CLV", revision="LAB1", mode="clv", clv_speed_x=4.0,
                     rev_period_ms={"dvd": 20.0, "cd": 20.0, "bd": 20.0}, jitter_us=25.0, outlier_rate=0.02,
                     fua_honoured=True, flush_honoured=False, reread_delay_ms=0.0, cache_blocks=4,
                     head_mm=0.02, completion_mm={"dvd": 0.0, "cd:mode2form1": 0.0, "cd:mode1": 0.0, "bd": 0.0},
                     write_speeds_x={"dvd": [8], "cd": [24], "bd": [4]}),
    "nofua": dict(vendor="DISCLAB", product="NOFUA-CACHE", revision="LAB1", mode="cav",
                  rev_period_ms={"dvd": 13.0, "cd": 20.0, "bd": 20.0}, jitter_us=6.0, outlier_rate=0.01,
                  fua_honoured=False, flush_honoured=False, reread_delay_ms=0.0, cache_blocks=6,
                  head_mm=-0.03, completion_mm={"dvd": 0.0, "cd:mode2form1": 0.0, "cd:mode1": 0.0, "bd": 0.0},
                  write_speeds_x={"dvd": [8], "cd": [24], "bd": [4]}),
    "noisy": dict(vendor="DISCLAB", product="NOISY-CAV", revision="LAB1", mode="cav",
                  rev_period_ms={"dvd": 13.3, "cd": 20.0, "bd": 20.0}, jitter_us=60.0, outlier_rate=0.04,
                  fua_honoured=True, flush_honoured=False, reread_delay_ms=0.0, cache_blocks=6,
                  head_mm=0.0, completion_mm={"dvd": 5.16, "cd:mode2form1": 0.0, "cd:mode1": 0.0, "bd": 0.0},
                  write_speeds_x={"dvd": [8], "cd": [24], "bd": [4]}),
}

# Writing paths. write_offset_bits moves every burn's data along the groove; it cancels when the measuring disc
# and the picture disc went the same way. low_speed_texture_fail: burns at or below this multiple leave textured
# (non-random) sectors beyond the radius unreadable (GH70N + RITEKF1 at 4x: outer 2/3 of a texture disc failed).
WRITERS = {
    "imapi": dict(write_offset_bits=0.0, jitter_bits=8.0, low_speed_x=4.0, low_speed_fail_mm=35.0),
}


def _varpitch(rng, rms_deg, radii):
    """A smooth curve phi(r) in degrees with the given rms (a few slow waves, as the master recorder leaves)."""
    y = np.zeros_like(radii)
    for k in range(1, 5):
        y += rng.normal(0, 1 / k) * np.cos(2 * np.pi * k * (radii - 22) / 37 + rng.uniform(0, 2 * np.pi))
    y -= y.mean()
    return y / (y.std() + 1e-12) * rms_deg


def make_box(lab: Lab, media: str, count: int, seed: int, *, batch: int = 1, stampers: int = 1,
             reader: str = "gh70n", drives=("X:",), stamper_mix=None, short: str = "LAB-A", uv_noise=(0.0, 0.0)):
    if media not in MEDIA:
        raise SystemExit(f"media must be one of {', '.join(MEDIA)}")
    m = MEDIA[media]
    rng = np.random.default_rng([seed, 20261113])
    radii = np.arange(21.0, 60.01, 0.5)
    st = []
    for k in range(stampers):
        # Between stampers of one product the master recorder's CLV speed differs slightly.
        du = 0.0 if k == 0 else rng.normal(0, 120.0)
        dv = 0.0 if k == 0 else rng.normal(0, 1.5e-4)
        st.append(dict(id=f"S{k + 1}", u=m["u"] + du + rng.normal(0, 0.3), v=m["v"] * (1 + dv + rng.normal(0, 2e-7)),
                       b_nm=m["b_nm"] * (1 + rng.normal(0, 1e-3)),
                       varpitch_r_mm=radii.tolist(),
                       varpitch_deg=_varpitch(rng, m["varpitch_rms_deg"], radii).tolist(),
                       capacity=m["capacity"]))
    weights = np.array(stamper_mix if stamper_mix else [0.8] + [0.2 / max(stampers - 1, 1)] * (stampers - 1))
    weights = weights[:stampers] / weights[:stampers].sum()
    discs, labels = {}, []
    for i in range(count):
        disc_id = f"{short} {batch}-{i + 1:02d}"
        k = 0 if i == 0 else int(rng.choice(stampers, p=weights))
        s = st[k]
        flaw = None
        if rng.random() < 0.08:          # an unreadable arc (a scratch or a dye void)
            r_lo = float(rng.uniform(30, 55))
            flaw = dict(r_mm=[r_lo, r_lo + float(rng.uniform(0.2, 1.0))], deg=[float(a := rng.uniform(0, 360)),
                                                                                  float(a + rng.uniform(5, 40))])
        discs[disc_id] = dict(
            media=media, family=m["family"], stamper=s["id"],
            # Bits per turn are moulded in: discs of one stamper share u and v (uv_noise only to test that).
            u=s["u"] + rng.normal(0, uv_noise[0]), v=s["v"] * (1 + rng.normal(0, uv_noise[1])),
            b_nm=s["b_nm"] * (1 + rng.normal(0, 1e-4)),            # shrinkage: scales r, pitch and b together
            bits_per_sector=m["bits_per_sector"], varpitch_r_mm=s["varpitch_r_mm"], varpitch_deg=s["varpitch_deg"],
            capacity=s["capacity"],
            ecc_um=float(abs(rng.normal(0, 18.0))), ecc_deg=float(rng.uniform(0, 360)),
            dish_mm=float(rng.normal(0.12, 0.08)), saddle_mm=float(abs(rng.normal(0, 0.06))),
            saddle_deg=float(rng.uniform(0, 180)),
            contrast_gain=float(np.exp(rng.normal(0, 0.15))),
            zero_order_dark=float(np.clip(rng.normal(0.15, 0.05), 0.03, 0.35)),
            flaw=flaw)
        labels.append(disc_id)
    readers = {name: dict(READERS[name]) for name in READERS}
    answers = dict(
        about="disclab truth. disc-probe never reads this file; scoring and the virtual drives do.",
        seed=seed, media=media, batch=batch, stampers=st, discs=discs, readers=readers, writers=WRITERS,
        photos={})
    box = dict(media=media, batch=batch, mid=m["mid"], count=count, discs=labels,
               note="What is printed on the box. The true parameters are in answers.json, which disc-probe never sees.")
    lab.root.mkdir(parents=True, exist_ok=True)
    atomic_json(lab.box_path, box)
    atomic_json(lab.answers_path, answers)
    with lab.locked_state() as state:
        state["drives"] = {d: dict(reader=reader, tray=None, open=False) for d in drives}
        state.setdefault("burns", {})
        lab.event(state, "box", media=media, count=count, seed=seed)
    return box


def path_L_mm(answers: dict, reader: str, family: str, mode: str | None = None) -> float:
    """The path's along-track constant: reader completion point + head offset (per family and burn mode)."""
    r = answers["readers"][reader]
    key = family if family != "cd" else f"cd:{mode or 'mode2form1'}"
    return float(r["completion_mm"].get(key, 0.0)) + float(r["head_mm"])
