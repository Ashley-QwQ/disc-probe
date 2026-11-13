"""The whole path on lab discs, scored against the answers.

    python -m disclab loop geo   --lab LAB              every disc: burn the random image, geo, score
    python -m disclab loop photo --lab LAB              disc 1 geo -> target on discs 2..k -> photos -> photo L
                                                        -> picture ISO (with and without photo L) -> score
    python -m disclab loop poses --lab LAB              one target disc, two pose families: does L follow the pose?

Everything disc-probe does goes through its own CLI in child processes (python -m discprobe ...), against the
lab's virtual drive. Results land in LAB/results, LAB/runs, LAB/scores.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

from .lab import Lab, atomic_json

SCRATCH_ISO = Path("C:/disc-probe-scratch/disclab/iso")
FALSE_ACCEPT_MM = 0.326          # the pcal studies' "wrong" line (two CD frames)
BELOW_NORMAL = 0x4000


def _env(lab):
    from .__main__ import lab_env
    return lab_env(lab)


def dp(lab, args, *, log=None, check=True):
    from .__main__ import ROOT
    argv = [sys.executable, "-B", "-m", "discprobe", *map(str, args)]
    t = time.time()
    res = subprocess.run(argv, cwd=ROOT, env=_env(lab), text=True, encoding="utf-8", errors="replace",
                         stdin=subprocess.DEVNULL, capture_output=True,
                         creationflags=BELOW_NORMAL if os.name == "nt" else 0)
    if log:
        log.write(f"$ discprobe {' '.join(map(str, args))}  ({time.time() - t:.1f}s, exit {res.returncode})\n")
        log.write(res.stdout[-6000:] + res.stderr[-3000:] + "\n")
        log.flush()
    if check and res.returncode:
        raise RuntimeError(f"discprobe {args[0]} failed ({res.returncode}): {(res.stdout + res.stderr)[-1500:]}")
    return res


def tray(lab, drive, disc):
    with lab.locked_state() as st:
        st["drives"][drive].update(tray=disc, open=False)
        lab.event(st, "tray", drive=drive, disc=disc)


def newest(folder: Path, prefix: str, after: float):
    found = [p for p in folder.glob(prefix + "*") if p.is_dir() and p.stat().st_mtime >= after - 1]
    if not found:
        raise RuntimeError(f"no new {prefix}* in {folder}")
    return max(found, key=lambda p: p.stat().st_mtime)


def burn(lab, drive, disc, iso, log, speed=None):
    st = lab.state()
    if disc in st.get("burns", {}):
        return
    tray(lab, drive, disc)
    dp(lab, ["burn", "--drive", drive, "--iso", iso, "--yes-write", *(["--speed", speed] if speed else [])], log=log)


def geo(lab, drive, disc, log, ranges="wide"):
    tray(lab, drive, disc)
    t = time.time()
    extra = []
    if ranges == "wide":
        cap = max(s["start_lba"] + s["sectors"] for s in lab.state()["burns"][disc]["sessions"])
        extra = ["--ranges", f"{int(cap * 0.03) // 16 * 16}-{int(cap * 0.97) // 16 * 16}"]
    res = dp(lab, ["geo", "--drive", drive, "--out", lab.root / "results", *extra], log=log, check=False)
    folder = newest(lab.root / "results", f"geo-{drive.rstrip(':')}-", t)
    return folder, res.returncode


def random_iso(lab, log):
    path = SCRATCH_ISO / "random.iso"
    if not path.exists():
        dp(lab, ["random", "--output", path], log=log)
    return path


def loop_geo(lab: Lab, drive="X:", ranges="wide", discs=None):
    from .score import geo_score
    log = open(lab.root / "loop-geo.log", "a", encoding="utf-8")
    iso = random_iso(lab, log)
    discs = discs or lab.box()["discs"]
    rows = []
    for d in discs:
        burn(lab, drive, d, iso, log)
        folder, code = geo(lab, drive, d, log, ranges)
        s = geo_score(lab, d, folder)
        s["exit"] = code
        rows.append(s)
        vt, pl = s["vs_timing_measured_span"], s["placement_on_target"]
        print(f"{d}: du {s['du_bits']:+.3f} bit, dv {s['dv_rel']:+.1e}; vs timing {vt['rms_deg']:.3f} deg rms "
              f"{vt['pp_deg']:.3f} pp; on disc L {pl['L_mm']:+.3f} mm (path {s['path_L_mm']:+.3f}), "
              f"rest {pl['residual_after_L_rms_deg']:.3f} rms; geo says resid {s['geo_reported']['residual_rms_deg']:.3f}"
              f" sigma {s['geo_reported']['angle_sigma_deg']:.3f}", flush=True)
    atomic_json(lab.root / "scores" / f"geo-{ranges}.json", rows)
    return rows


# ---------------------------------------------------------------- photo path

def copy_run(geo_dir: Path, dest: Path) -> Path:
    target = dest / geo_dir.name
    if not target.exists():
        target.mkdir(parents=True)
        for f in geo_dir.iterdir():
            if f.is_file() and f.name not in ("photo.json",):
                shutil.copy2(f, target / f.name)
    return target


def read_photos(lab, run: Path, photos, disc, log):
    args = ["photo", "--run", run, "--media", "dvd", "--photos", *photos, "--disc-id", disc,
            "--burner", "X:", "--burn-path", "IMAPI", "--burn-mode", "dvd-dao"]
    dp(lab, args, log=log)
    return json.loads((run / "photo.json").read_text(encoding="utf-8"))


def truth_L(lab, geo_dir, target):
    """The along-track part of the placement error a picture from this geo would have on `target`."""
    from .score import decompose, geo_model, placement
    from .physics import Disc
    u, v, corr, _ = geo_model(geo_dir)
    disc = Disc(lab.answers()["discs"][target], lab.state()["burns"].get(target))
    r, eps = placement(disc, u, v, corr)
    return decompose(r, eps)


def picture_score(lab, sidecar: Path, disc):
    from .score import decompose, placement
    from .physics import Disc
    from discprobe import imagedisc
    spec = json.loads(sidecar.read_text(encoding="utf-8"))
    corr = imagedisc.load_correction(spec["correction"]) if spec.get("correction") else None
    d = Disc(lab.answers()["discs"][disc], lab.state()["burns"].get(disc))
    r, eps = placement(d, spec["u"], spec["v"], corr)
    out = decompose(r, eps)
    out["photo_l"] = {k: spec.get("photo_l", {}).get(k) for k in ("written", "L_mm", "reason")}
    return out


def loop_photo(lab: Lab, drive="X:", geo_disc=None, targets=None, n_photos=6, style="handheld", seed=0,
               picture_disc=None, workers=3, tag="photo"):
    log = open(lab.root / f"loop-{tag}.log", "a", encoding="utf-8")
    discs = lab.box()["discs"]
    geo_disc = geo_disc or discs[0]
    targets = targets or discs[1:7]
    iso = random_iso(lab, log)
    burn(lab, drive, geo_disc, iso, log)
    marker = lab.root / "scores" / f"{tag}-geo.txt"
    if marker.is_file():
        geo_dir = Path(marker.read_text(encoding="utf-8").strip())
    else:
        geo_dir, _ = geo(lab, drive, geo_disc, log)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(geo_dir), encoding="utf-8")
    print(f"geo of {geo_disc}: {geo_dir.name}", flush=True)
    from .target import target_npy
    design = target_npy(lab.root / "designs" / "pn_burn.npy")
    t_iso = SCRATCH_ISO / f"target-{lab.root.name}.iso"
    if any(t not in lab.state().get("burns", {}) for t in targets):
        dp(lab, ["image", "--geo", geo_dir / "summary.json", "--design-npy", design, "--output", t_iso,
                 "--no-photo-l"], log=log)
    for t in targets:
        burn(lab, drive, t, t_iso, log)
    t_iso.unlink(missing_ok=True)          # the burn maps keep what was written; disk space is short
    from . import photos as P
    sets = {}
    for i, t in enumerate(targets):
        out = lab.root / "photos" / tag / t.replace(" ", "_")
        existing = sorted(out.glob("IMG_*.jpg")) if out.is_dir() else []
        paths = existing if len(existing) == n_photos else             P.shoot(lab, t, n_photos, out, seed=seed * 100 + i, style=style, log=lambda *a: None)
        sets[t] = [str(p) for p in paths]
        print(f"rendered {len(paths)} photos of {t}", flush=True)

    def one(t):
        run = copy_run(geo_dir, lab.root / "runs" / tag / t.replace(" ", "_"))
        if (run / "photo.json").is_file():
            return t, run, json.loads((run / "photo.json").read_text(encoding="utf-8"))
        rec = read_photos(lab, run, sets[t], t, log)
        return t, run, rec
    with ThreadPoolExecutor(workers) as ex:
        done = list(ex.map(one, targets))
    answers = lab.answers()
    rows = []
    for t, run, rec in done:
        truth = truth_L(lab, geo_dir, t)
        per = []
        for p in rec["photos"]:
            key = f"{Path(sets[t][0]).parent.name}/{p['name']}"
            pose = answers["photos"].get(key, {}).get("pose", {})
            err = (p["L_mm"] - truth["L_mm"]) if p.get("L_mm") is not None else None
            per.append(dict(name=p["name"], status=p["status"], L_mm=p.get("L_mm"), err_mm=err,
                            false_accept=bool(p["status"] == "ok" and err is not None and abs(err) > FALSE_ACCEPT_MM),
                            tilt=pose.get("tilt_deg"), az=pose.get("az_deg"), dist=pose.get("dist_mm"),
                            blur=pose.get("blur_px")))
        agreement = rec.get("application_agreement") or {}
        row = dict(target=t, run=str(run), truth=truth, photos=per, verdict=rec["verdict"],
                   applied_L_mm=rec.get("offset_mm"), reason=agreement.get("reason"),
                   applied_err_mm=(rec["offset_mm"] - truth["L_mm"]) if rec.get("offset_mm") is not None else None)
        rows.append(row)
        ok = [q for q in per if q["status"] == "ok"]
        print(f"{t}: truth L {truth['L_mm']:+.3f} mm; ok {len(ok)}/{len(per)}; "
              + ", ".join(f"{q['L_mm']:+.3f}" for q in ok)
              + f"; group {rec['verdict']}" + (f" L {rec['offset_mm']:+.3f} (err {row['applied_err_mm']:+.3f})"
                                              if rec.get('offset_mm') is not None else f" ({agreement.get('reason')})"),
              flush=True)
    # Picture ISOs from the first run with an applied L: with and without photo L, scored on a picture disc.
    applied = [r for r in rows if r["applied_L_mm"] is not None]
    pictures = {}
    if applied:
        run = Path(applied[0]["run"])
        pic_disc = picture_disc or discs[-1]
        for flag, name in ((["--no-photo-l"], "nophoto"), ([], "photo")):
            out = SCRATCH_ISO / f"picture-{lab.root.name}-{name}.iso"
            # The default grid starts at 24.5 mm, inside geo's measured span only with a wider read; use the
            # target design so the finished disc can be photographed and read again.
            dp(lab, ["image", "--geo", run / "summary.json", "--design-npy", design, "--output", out, *flag], log=log)
            pictures[name] = picture_score(lab, out.with_suffix(".image.json"), pic_disc)
            if name == "photo" and pic_disc not in lab.state().get("burns", {}):
                burn(lab, drive, pic_disc, out, log)
                out.unlink(missing_ok=True)
            print(f"picture ({name}) on {pic_disc}: rms {pictures[name]['rms_deg']:.3f} deg, "
                  f"pp {pictures[name]['pp_deg']:.3f} deg, L left {pictures[name]['L_mm']:+.3f} mm", flush=True)
            if name == "nophoto":
                out.unlink(missing_ok=True)
    summary = summarise(rows)
    summary["pictures"] = pictures
    atomic_json(lab.root / "scores" / f"{tag}.json", dict(summary=summary, rows=rows))
    print(json.dumps(summary, indent=2), flush=True)
    return rows


def summarise(rows):
    per = [p for r in rows for p in r["photos"]]
    ok = [p for p in per if p["status"] == "ok"]
    errs = [abs(p["err_mm"]) for p in ok if p["err_mm"] is not None]
    statuses = {}
    for p in per:
        statuses[p["status"]] = statuses.get(p["status"], 0) + 1
    groups = [r for r in rows if r["applied_L_mm"] is not None]
    return dict(photos=len(per), accepted=len(ok), accept_rate=len(ok) / max(len(per), 1),
                false_accepts=sum(p["false_accept"] for p in per),
                accepted_mae_mm=float(np.mean(errs)) if errs else None,
                accepted_max_mm=float(np.max(errs)) if errs else None, statuses=statuses,
                groups=len(rows), groups_applied=len(groups),
                group_false_applied=sum(abs(r["applied_err_mm"]) > FALSE_ACCEPT_MM for r in groups),
                group_abs_err_mm=[round(abs(r["applied_err_mm"]), 4) for r in groups],
                reasons={r["target"]: r["reason"] for r in rows if r["applied_L_mm"] is None})


def add_parser(sub):
    s = sub.add_parser("loop", help="run the whole path on lab discs and score it")
    s.add_argument("what", choices=("geo", "photo"))
    s.add_argument("--lab", required=True)
    s.add_argument("--drive", default="X:")
    s.add_argument("--ranges", default="wide", choices=("wide", "default"))
    s.add_argument("--targets", type=int, default=6, help="photo: how many target discs (after the geo disc)")
    s.add_argument("--photos", type=int, default=6)
    s.add_argument("--style", default="handheld")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--tag", default="photo")
    s.add_argument("--workers", type=int, default=3)

    def go(a):
        lab = Lab(a.lab)
        if a.what == "geo":
            loop_geo(lab, a.drive, a.ranges)
        else:
            discs = lab.box()["discs"]
            loop_photo(lab, a.drive, discs[0], discs[1:1 + a.targets], a.photos, a.style, a.seed,
                       workers=a.workers, tag=a.tag)
    s.set_defaults(func=go)
