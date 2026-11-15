"""Night B: copy the re-rendered dark pictures into the web folder, encoded the way each committed picture was.

    python tools/night_b_export.py RENDERS [--write] [--only lobby,caltop,...]

RENDERS holds one folder per render job (the names in tools/night_b_manifest.json "jobs"). Without --write it only
checks. For every picture it also runs the PAPER render of the same job through the same crop and encoding and
compares it with the committed paper picture: that is the proof the job's arguments, scene and Blender version match
what made the committed art (the paper pictures themselves are never written).

Encoding follows the committed file: lossless WebP (VP8L) stays lossless (Pillow lossless=True, method=6); a lossy
one is re-encoded with the quality / method whose paper re-encode comes closest to the committed paper file's size.
The lobby layers are cropped with lobby.json's boxes, the news fax handset with fax.json's, so no placement data
changes. The calibration stage and its animation go through caltop/compose_anim.py (it writes both themes; the paper
outputs are checked to be unchanged).
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "discprobe" / "web" / "home"
REN = Path(sys.argv[1])
WRITE = "--write" in sys.argv
ONLY = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
REPORT = []


def kind(p: Path) -> str:
    head = p.read_bytes()[:40]
    if head[12:16] == b"VP8L":
        return "lossless"
    if head[12:16] == b"VP8X":       # extended: look for the first image chunk
        data = p.read_bytes()
        return "lossless" if data.find(b"VP8L") >= 0 and data.find(b"VP8 ") < 0 else "lossy"
    return "lossy"


def encode(im: Image.Image, how) -> bytes:
    b = io.BytesIO()
    if how == "lossless":
        im.save(b, "WEBP", lossless=True, method=6)
    else:
        q, m = how
        im.save(b, "WEBP", quality=q, method=m, exact=True)
    return b.getvalue()


_LOSSY = {}


def match_lossy(paper: Image.Image, committed: Path):
    """quality / method of a committed lossy picture: the paper re-encode closest in size (once per family of names)"""
    import re
    key = (committed.parent, re.sub(r"\d+", "#", committed.name))
    if key in _LOSSY:
        return _LOSSY[key]
    size = committed.stat().st_size
    best = None
    for m in (4, 6):
        for q in range(80, 97):
            n = len(encode(paper, (q, m)))
            if best is None or abs(n - size) < best[0]:
                best = (abs(n - size), (q, m))
    _LOSSY[key] = best[1]
    print("  lossy %s: quality %d method %d (paper size off by %d bytes)" % (committed.parent.name, best[1][0], best[1][1], best[0]))
    return best[1]


def diff(a: Image.Image, b: Image.Image):
    if a.size != b.size:
        return "SIZE %s vs %s" % (a.size, b.size)
    x = np.asarray(a.convert("RGBA"), np.int16)
    y = np.asarray(b.convert("RGBA"), np.int16)
    vis = (x[..., 3] > 8) | (y[..., 3] > 8)
    d = np.abs(x - y)
    return "mean %.2f, alpha mean %.2f, px >8: %.3f%%" % (d[..., :3][vis].mean() if vis.any() else 0,
                                                         d[..., 3].mean(), 100 * (d.max(2) > 8)[vis].mean() if vis.any() else 0)


def put(dst: Path, dark: Image.Image, paper: Image.Image, also_png=False):
    """dst = committed dark .webp (or .png); encode dark like it; check the paper render against the paper file"""
    pdst = dst.with_name(dst.name.replace("_dark.", "_paper."))
    if dst.suffix == ".png":
        enc = None
    else:
        how = kind(dst)
        if how == "lossy":
            how = match_lossy(paper, pdst) if pdst.exists() else (90, 4)
        enc = how
    check = diff(Image.open(io.BytesIO(encode(paper, enc))) if enc else paper, Image.open(pdst)) if pdst.exists() else "no paper file"
    REPORT.append(dict(file=str(dst.relative_to(HOME)), encoding=str(enc or "png"), paper_check=check,
                       old_dark=diff(dark, Image.open(dst)) if dst.exists() else "new"))
    print("%-48s %-14s paper: %s" % (dst.relative_to(HOME), enc or "png", check))
    if WRITE:
        if enc:
            dst.write_bytes(encode(dark, enc))
        else:
            dark.save(dst, optimize=True)
        if also_png:
            dark.save(dst.with_suffix(".png"), optimize=True)


def new_file(dst: Path, im: Image.Image):
    REPORT.append(dict(file=str(dst.relative_to(HOME)), encoding="lossless", paper_check="new picture", old_dark="new"))
    print("%-48s new" % dst.relative_to(HOME))
    if WRITE:
        dst.write_bytes(encode(im, "lossless"))


def ld(p) -> Image.Image:
    return Image.open(p).convert("RGBA")


def want(group):
    return ONLY is None or group in ONLY


# ---------------------------------------------------------------- library / burn page drive
if want("burner"):
    for v in ("dark",):
        b = REN / "F_burner"
        put(HOME / "burner_dark.webp", ld(b / "burner_dark.png"), ld(b / "burner_paper.png"), also_png=True)
    L = REN / "F_burner_layers"
    for n in ("body", "tray", "traydisc"):
        put(HOME / f"burner_{n}_dark.webp", ld(L / f"burner_{n}_dark.png"), ld(L / f"burner_{n}_paper.png"), also_png=True)
    for n in ("shadow", "trayshadow", "traydiscshadow"):
        for t in ("paper", "dark"):
            new_file(HOME / f"burner_{n}_{t}.webp", ld(L / f"burner_{n}_{t}.png"))
    old = json.loads((HOME / "burner.json").read_text(encoding="utf-8"))
    new = json.loads((L / "burner.json").read_text(encoding="utf-8"))
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    print("burner.json keys that change:", changed)
    if WRITE:
        (HOME / "burner.json").write_text(json.dumps(new, indent=2), encoding="utf-8")

# ---------------------------------------------------------------- drive interior (calibration cutaway)
if want("interior"):
    I = REN / "F_interior"
    for c in sorted((HOME / "interior").glob("*_dark.webp")):
        f = I / c.name.replace(".webp", ".png")
        put(c, ld(f), ld(I / f.name.replace("_dark", "_paper")), also_png=True)

# ---------------------------------------------------------------- calibration stage + animation (compose_anim.py)
if want("caltop"):
    C, A = REN / "F_caltop", REN / "F_caltop_anim"
    for src, sub in ((C, "out_pool"), (A, "out_anim")):
        for dst in sorted((HOME / "caltop" / sub).glob("*_dark.png")):
            f = src / dst.name
            pap = HOME / "caltop" / sub / f.name.replace("_dark", "_paper")
            REPORT.append(dict(file=str(dst.relative_to(HOME)), encoding="png",
                               paper_check=diff(ld(src / f.name.replace("_dark", "_paper")), ld(pap)) if pap.exists() else "-",
                               old_dark=diff(ld(f), ld(dst)) if dst.exists() else "new"))
            print("%-48s png        paper: %s" % (dst.relative_to(HOME), REPORT[-1]["paper_check"]))
            if WRITE:
                shutil.copyfile(f, dst)
        for j in src.glob("*.json"):
            if (HOME / "caltop" / sub / j.name).exists() and WRITE:
                shutil.copyfile(j, HOME / "caltop" / sub / j.name)
    if WRITE:
        before = {p: p.read_bytes() for p in (HOME / "caltop").rglob("*_paper.webp")}
        subprocess.run([sys.executable, "-I", "compose_anim.py"], cwd=HOME / "caltop", check=True)
        moved = [str(p.relative_to(HOME)) for p, b in before.items() if p.read_bytes() != b]
        print("compose_anim: paper webps changed:", moved or "none")
        REPORT.append(dict(file="caltop/*_paper.webp", encoding="compose_anim", paper_check="changed: %s" % (moved or "none"), old_dark="-"))

# ---------------------------------------------------------------- new work, presets desk, past works
if want("newplan"):
    T, P, E = REN / "F_np_top", REN / "F_np_paper", REN / "F_np_env"
    put(HOME / "newplan/top_dark.webp", ld(T / "top_dark.png").convert("RGB"), ld(T / "top_paper.png").convert("RGB"))
    for n in ("paper", "paper_shadow"):
        put(HOME / f"newplan/{n}_dark.webp", ld(P / f"{n}_dark.png"), ld(P / f"{n}_paper.png"))
    for n in ("envelope_back", "envelope_front"):
        put(HOME / f"newplan/{n}_dark.webp", ld(E / f"{n}_dark.png"), ld(E / f"{n}_paper.png"))
if want("presetio"):
    D = REN / "F_np_desk"
    for f in sorted((HOME / "presetio/desk").glob("desk_*_dark.webp")):
        n = f.name.replace(".webp", ".png")
        put(f, ld(D / n), ld(D / n.replace("_dark", "_paper")))
if want("pastworks"):
    E = REN / "F_pw_env"
    for n in ("envelope_back", "envelope_front"):
        put(HOME / f"pastworks/{n}_dark.webp", ld(E / f"{n}_dark.png"), ld(E / f"{n}_paper.png"))
    for i in range(10):
        J = REN / f"F_tumble{i}"
        put(HOME / f"pastworks/tumble_{i}_dark.webp", ld(J / f"tumble_{i}_dark.png"), ld(J / f"tumble_{i}_paper.png"))

# ---------------------------------------------------------------- the news fax's own page
if want("faxnews"):
    X = REN / "F_fax_top"
    meta = json.loads((HOME / "faxnews/fax.json").read_text(encoding="utf-8"))
    put(HOME / "faxnews/top_dark.webp", ld(X / "top_dark.png").convert("RGB"), ld(X / "top_paper.png").convert("RGB"))
    for n in ("handset", "handset_shadow"):
        box = meta[n]["box"]
        put(HOME / f"faxnews/{n}_dark.webp", ld(X / f"{n}_dark.png").crop(box), ld(X / f"{n}_paper.png").crop(box))

# ---------------------------------------------------------------- the lobby (crops from lobby.json)
if want("lobby"):
    lob = json.loads((HOME / "lobby/lobby.json").read_text(encoding="utf-8"))
    box = {l["name"]: l["box"] for l in lob["layers"]}
    # each layer from the room that made the committed one: base, faxnews, filebox, screen (+ on) and the parcel from
    # the news-fax room; the fax layer (letter tray, 328a829) from the round-5 room (L_round5); the lamp and new-work
    # layers (0d17dd6) from the lobby3_final room (L_lobby3), whose renders they match
    src = {"base": "F_lobby_a", "faxnews": "F_lobby_a", "filebox": "F_lobby_a", "fax": "L_round5", "lamp": "G_lamp",
           "newplan": "L_lobby3", "screen": "F_lobby_c", "screen_on": "F_lobby_d"}
    for name, job in src.items():
        fn = "desk_screen_%s.png" if name == "screen_on" else "desk_%s_%%s.png" % name
        d, p = ld(REN / job / (fn % "dark")), ld(REN / job / (fn % "paper"))
        if name == "base":
            d, p = d.convert("RGB"), p.convert("RGB")
        put(HOME / f"lobby/{name}_dark.webp", d.crop(box[name]), p.crop(box[name]))
    # the parcel: its picture over its own contact shadow (export_fax_lobby.py: where the base with the parcel
    # differs from the base without it, near the parcel)
    from scipy import ndimage
    pb = box["parcel"]
    ims = {}
    for t in ("paper", "dark"):
        with_p = np.asarray(ld(REN / "F_lobby_b" / f"desk_base_{t}.png").convert("RGB"), float)
        without = np.asarray(ld(REN / "F_lobby_a" / f"desk_base_{t}.png").convert("RGB"), float)
        dd = np.abs(with_p - without).max(2)
        near = np.zeros_like(dd, bool)
        near[max(0, pb[1] - 60):pb[3] + 60, max(0, pb[0] - 60):pb[2] + 60] = True
        a = ndimage.gaussian_filter(np.clip((dd - 1.0) / 6.0, 0, 1) * near, 1.0)
        im = Image.fromarray(np.dstack([with_p, a * 255]).astype(np.uint8), "RGBA")
        im.alpha_composite(ld(REN / "F_lobby_b" / f"desk_parcel_{t}.png"))
        ims[t] = im.crop(pb)
    put(HOME / "lobby/parcel_dark.webp", ims["dark"], ims["paper"])

out = ROOT / "tools" / "night_b_export_report.json"
if WRITE:  # merge: a run with --only replaces its own pictures' rows and keeps the others
    old = {r["file"]: r for r in json.loads(out.read_text(encoding="utf-8"))} if out.exists() else {}
    old.update({r["file"]: r for r in REPORT})
    out.write_text(json.dumps(sorted(old.values(), key=lambda r: r["file"]), indent=1, ensure_ascii=False),
                   encoding="utf-8")
print(len(REPORT), "pictures", "(written)" if WRITE else "(check only)")
