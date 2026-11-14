"""Compare what disc-probe measured with the answers.

Placement error. imagedisc gives user bit n the design at th(n) = -theta(n; u, v) + phi_corr(r) (plus the photo
shift of u when photo L was applied). The bit really is at alpha(n) = -theta_g(n + w) on the disc it is burned on.
So a feature designed at th lands at th + eps(n), eps = alpha - th: the tau(r) of pcal. eps is split into a
rotation c (harmless), an along-track part L/r, and what is left (bends a picture).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from discprobe.calib import theta

from .box import path_L_mm
from .lab import Lab, atomic_json
from .physics import Disc


def geo_model(geo_dir):
    """(u, v, phi_corr callable in degrees or None) of a geo run, as image would use them."""
    from discprobe import imagedisc
    geo_dir = Path(geo_dir)
    s = json.loads((geo_dir / "summary.json").read_text(encoding="utf-8"))
    fit = s["fit"]
    corr = None
    name = fit.get("correction_file")
    if name and (geo_dir / name).is_file():
        corr = imagedisc.load_correction(str(geo_dir / name))
    return float(fit["u"]), float(fit["v"]), corr, s


def placement(disc: Disc, u, v, corr, radii=None, bit_nm=None):
    """eps(r) in radians for a picture made with (u, v, corr) and burned on `disc`."""
    radii = np.linspace(25.0, 57.5, 131) if radii is None else np.asarray(radii)
    b_mm = disc.b_mm
    # The bit index at each true radius of this disc (data radius), then what image assumed for that bit.
    s_true = radii / b_mm
    m = math.pi * (s_true ** 2 - disc.u ** 2) / disc.v          # groove bit at that radius
    n = m - disc.w_bits                                         # user bit
    th_model = theta(n, u, v)
    s_model = np.sqrt(u * u + v * n / math.pi)
    r_model = (bit_nm * 1e-6 if bit_nm else b_mm) * s_model
    phi = np.radians(corr(r_model)) if corr is not None else 0.0
    eps = th_model - phi - disc.theta_g(n + disc.w_bits)
    return radii, eps


def decompose(radii, eps, lo=26.0, hi=57.0):
    m = (radii >= lo) & (radii <= hi)
    A = np.column_stack([np.ones(m.sum()), 1 / radii[m]])
    q, *_ = np.linalg.lstsq(A, eps[m], rcond=None)
    res = eps[m] - A @ q
    centred = eps[m] - eps[m].mean()
    return dict(c_deg=math.degrees(q[0]), L_mm=float(q[1]),
                rms_deg=float(np.degrees(np.sqrt(np.mean(centred ** 2)))),
                pp_deg=float(np.degrees(centred.max() - centred.min())),
                residual_after_L_rms_deg=float(np.degrees(np.sqrt(np.mean(res ** 2)))),
                residual_after_L_pp_deg=float(np.degrees(res.max() - res.min())))


def geo_score(lab: Lab, disc_id: str, geo_dir, *, target_disc=None, reader=None):
    """How far geo's geometry is from (a) what timing could see on the measured disc and (b) where the data of
    `target_disc` (default: the same disc) really is. (b) includes the path's along-track constant."""
    answers = lab.answers()
    st = lab.state()
    u, v, corr, summary = geo_model(geo_dir)
    fit = summary["fit"]
    measured = Disc(answers["discs"][disc_id], st["burns"].get(disc_id))
    target_id = target_disc or disc_id
    target = Disc(answers["discs"][target_id], st["burns"].get(target_id))
    reader = reader or st["drives"][next(iter(st["drives"]))]["reader"]
    burn = st["burns"].get(disc_id) or {}
    mode = (burn.get("sessions") or [{}])[0].get("mode")
    L_path = path_L_mm(answers, reader, measured.family, mode)
    rd = answers["readers"][reader]
    key = measured.family if measured.family != "cd" else f"cd:{mode or 'mode2form1'}"
    d_bits = float(rd["completion_mm"].get(key, 0.0)) / measured.b_mm
    radii = np.linspace(25.0, 57.5, 131)
    # (a) timing truth: what geo is meant to recover, ignoring eccentricity's 1-cycle (not a function of r).
    s_true = radii / measured.b_mm
    n = math.pi * (s_true ** 2 - measured.u ** 2) / measured.v - measured.w_bits
    timing = measured.theta_g(n + measured.w_bits + d_bits) + np.arcsin(rd["head_mm"] / radii)
    phi = np.radians(corr(measured.b_mm * np.sqrt(u * u + v * n / math.pi))) if corr is not None else 0.0
    e_timing = theta(n, u, v) - phi - timing
    lo, hi = fit.get("measured_span_mm", [26.0, 57.0])
    out = dict(disc=disc_id, target=target_id, geo=str(geo_dir), u=u, v=v, true_u=measured.u, true_v=measured.v,
               du_bits=u - measured.u, dv_rel=v / measured.v - 1, path_L_mm=L_path,
               geo_reported=dict(residual_rms_deg=fit.get("residual_rms_deg"), angle_sigma_deg=fit.get("angle_sigma_deg"),
                                 chi2_per_dof=fit.get("chi2_per_dof"), status=fit.get("completion_status"),
                                 correction=fit.get("correction_file")),
               vs_timing_measured_span=decompose(radii, e_timing, lo, hi),
               vs_timing_full=decompose(radii, e_timing))
    r2, eps = placement(target, u, v, corr, radii)
    out["placement_on_target"] = decompose(r2, eps)
    return out


def progress_score(lab):
    from .loop import picture_score, truth_L
    from .jsonout import geo_folder, last_step
    folder = geo_folder(lab)
    disc = last_step(lab, "geo")["disc"]
    result = dict(geo=geo_score(lab, disc, folder), photos=[], pictures={})
    steps = lab.state().get("steps", {})
    for row in steps.get("photo_L", []):
        if row.get("status") != "ok":
            continue
        rec = lab.read(row["paths"][0])
        truth = truth_L(lab, Path(row["paths"][0]).parent, row["disc"])
        measured = rec.get("offset_mm")
        result["photos"].append(dict(disc=row["disc"], truth_L_mm=truth["L_mm"],
                                     measured_L_mm=measured, verdict=rec.get("verdict"),
                                     reason=rec.get("application_agreement"),
                                     error_mm=measured - truth["L_mm"] if measured is not None else None,
                                     photos=[dict(name=p.get("name"), status=p.get("status"),
                                                  L_mm=p.get("L_mm"), truth_L_mm=truth["L_mm"],
                                                  error_mm=p["L_mm"] - truth["L_mm"] if p.get("L_mm") is not None else None)
                                             for p in rec.get("photos", [])]))
    for kind in ("sample_picture", "picture_L"):
        for row in steps.get(kind, [])[-1:]:
            sidecar = next(Path(p) for p in row["paths"] if p.endswith(".image.json"))
            target = row.get("disc") or next((d for d in lab.box()["discs"] if d != disc), disc)
            result["pictures"][kind] = dict(target=target, **picture_score(lab, sidecar, target))
    path = lab.root / "scores" / "tui.json"
    atomic_json(path, result)
    lab.step("scores", status="ok", paths=[str(path)])
    print("Measured / truth / error — 测量值 / 真值 / 误差")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def add_parser(sub):
    s = sub.add_parser("score", help="compare measurements with the answers")
    s.add_argument("--lab", required=True)
    s.add_argument("--disc")
    s.add_argument("--geo", help="geo result folder")
    s.add_argument("--progress", action="store_true", help="geo, photo L and picture scores from state.json")
    s.add_argument("--target", help="the disc a picture made from this geo is burned on")
    def go(a):
        lab = Lab(a.lab)
        if a.progress:
            result = progress_score(lab)
            return dict(result=result, paths=[str(lab.root / "scores" / "tui.json")])
        if not a.disc or not a.geo:
            raise ValueError("score requires --disc and --geo, or --progress")
        result = geo_score(lab, a.disc, a.geo, target_disc=a.target)
        path = lab.root / "scores" / "score.json"
        atomic_json(path, result)
        lab.step("scores", status="ok", paths=[str(path)])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return dict(result=result, paths=[str(path)])
    s.set_defaults(func=go)
