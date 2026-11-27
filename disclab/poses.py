"""Does the photo L follow the pose? One burned target disc, a sweep of camera azimuths at fixed tilt and light,
read by the frozen reader, with the optical effects switched off one at a time.

    python -m disclab poses --lab LAB --disc "LAB-A 1-02" --geo GEO_DIR

The person's 11 photos split into two groups whose L differ by about 0.17 mm. Here every image of one sweep
shares the disc, the light, the noise seed and everything else; only where the phone is changes.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor
import os
from pathlib import Path

import numpy as np

from .lab import Lab, atomic_json

VARIANTS = {
    "full": {},
    "no_refraction": {"refraction": False},
    "flat_disc": {"_flat": True},
    "neither": {"refraction": False, "_flat": True},
}


def _one(job):
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    import cv2
    cv2.setNumThreads(1)
    from discprobe import pcal
    from . import photos
    lab_root, disc, pose_kw, variant = job[:4]
    lab = Lab(lab_root)
    pose = photos.Pose(**pose_kw)
    ch = dict(VARIANTS[variant])
    flat = ch.pop("_flat", False)
    for k, v in ch.items():
        setattr(pose, k, v)
    if flat:
        answers = lab.answers()
        answers["discs"][disc].update(dish_mm=0.0, saddle_mm=0.0)
        lab.answers = lambda a=answers: a
    img, f, rec = photos.render(lab, disc, pose)
    ok, buf = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, pose.jpeg])
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)[..., ::-1]
    res = pcal.read_photo(np.ascontiguousarray(img), pcal.design_burn(), focal_px=f)
    return dict(variant=variant, az=pose.az_deg, turn=job[4] if len(job) > 4 else None, tilt=pose.tilt_deg, light=pose.light, status=res["status"],
                L_mm=res.get("L_mm"), peak_z=res.get("peak_z"), ring_rms_mm=res.get("ring_rms_mm"),
                max_gap_deg=res.get("max_gap_deg"), nuisance=res.get("nuisance"),
                visible=rec["visible_fraction"])


def _turned(base, a):
    """The disc turned by a degrees under a fixed phone and lamp: in the disc frame both move by -a."""
    p = dict(base)
    p["az_deg"] = (base["az_deg"] - a) % 360
    x, y, z = base["lamp_mm"]
    c, s_ = math.cos(math.radians(-a)), math.sin(math.radians(-a))
    p["lamp_mm"] = (x * c - y * s_, x * s_ + y * c, z)
    p["seed"] = base["seed"]
    return p


def sweep(lab: Lab, disc, geo_dir, *, azimuths=range(0, 360, 45), tilt=25.0, dist=200.0, light="lamp",
          variants=("full", "no_refraction", "flat_disc", "neither"), workers=2, seed=7, out=None, from_photo=None):
    from .loop import truth_L
    if from_photo:
        base = dict(lab.answers()["photos"][from_photo]["pose"])
        base = {k: (tuple(v) if isinstance(v, list) else v) for k, v in base.items()}
        base.update(fingers=0)
        jobs = [(str(lab.root), disc, _turned(base, float(a)), v, float(a)) for v in variants for a in azimuths]
    else:
        base = dict(dist_mm=dist, tilt_deg=tilt, roll_deg=10.0, f35_mm=25.0, light=light,
                    lamp_mm=(1500 * math.sin(math.radians(35)), 0.0, 1500 * math.cos(math.radians(35))),
                    lamp_radius_mm=40.0, fingers=0, reflect=0, veil=0.25, blur_px=1.2, noise=1.5, jpeg=92,
                    seed=seed, k1=-0.01)
        jobs = [(str(lab.root), disc, dict(base, az_deg=float(a)), v) for v in variants for a in azimuths]
    with ProcessPoolExecutor(workers) as ex:
        rows = list(ex.map(_one, jobs))
    truth = truth_L(lab, Path(geo_dir), disc)
    for r in rows:
        r["err_mm"] = None if r["L_mm"] is None else r["L_mm"] - truth["L_mm"]
    summary = {}
    for v in variants:
        Ls = [r["L_mm"] for r in rows if r["variant"] == v and r["L_mm"] is not None]
        oks = [r["L_mm"] for r in rows if r["variant"] == v and r["status"] == "ok"]
        summary[v] = dict(n=sum(r["variant"] == v for r in rows), with_L=len(Ls), ok=len(oks),
                          L_min=min(Ls) if Ls else None, L_max=max(Ls) if Ls else None,
                          L_spread=(max(Ls) - min(Ls)) if Ls else None,
                          ok_spread=(max(oks) - min(oks)) if len(oks) > 1 else None)
    result = dict(disc=disc, geo=str(geo_dir), truth_L_mm=truth["L_mm"], base=base, summary=summary, rows=rows)
    if out:
        atomic_json(out, result)
    return result


def add_parser(sub):
    s = sub.add_parser("poses", help="sweep the camera around one target disc and see how photo L moves")
    s.add_argument("--lab", required=True)
    s.add_argument("--disc", required=True)
    s.add_argument("--geo", required=True)
    s.add_argument("--tilt", type=float, default=25.0)
    s.add_argument("--dist", type=float, default=200.0)
    s.add_argument("--light", default="lamp", choices=("lamp", "flash"))
    s.add_argument("--step", type=float, default=45.0)
    s.add_argument("--variants", nargs="+", default=list(VARIANTS))
    s.add_argument("--workers", type=int, default=2)
    s.add_argument("--out", required=True)
    s.add_argument("--from-photo", help="answers.json photo key: start from that photo's pose and turn the disc")

    def go(a):
        res = sweep(Lab(a.lab), a.disc, a.geo, azimuths=np.arange(0, 360, a.step), tilt=a.tilt, dist=a.dist,
                    light=a.light, variants=a.variants, workers=a.workers, out=a.out,
                    from_photo=a.from_photo)
        print(f"truth L {res['truth_L_mm']:+.3f} mm")
        for r in res["rows"]:
            print(f"{r['variant']:14s} az {r['az']:5.0f}: {r['status']:22s} L "
                  + (f"{r['L_mm']:+.3f} (err {r['err_mm']:+.3f})" if r["L_mm"] is not None else "   -  ")
                  + (f"  turned {r['turn']:.0f}" if r.get("turn") is not None else ""))
        print(json.dumps(res["summary"], indent=2))
        return dict(result=res, paths=[str(Path(a.out).resolve())])
    s.set_defaults(func=go)
