"""The practice flow, step by step, with disc-probe's own names.

One list of steps for every front end: `disclab step` (CLI), the numbered TUI and the desk page all read
`plan()` and run `run_step()`. The steps, their order and their names follow disc-probe's web page (new work
-> calibrate -> design -> preview -> check disc -> photos -> final burn), so what is practised here is what is
done on a real drive. Every step calls disc-probe through `disclab dp`, or a lab command (photos, score), and
leaves a `flow` record in LAB/state.json; nothing is kept by the front end.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import time

from .lab import Lab

SAMPLE = Path(__file__).parent / "data" / "sample.pgm"

# key, stage, zh, en, what it runs, where it happens on the desk, what it needs first
STEPS = [
    ("blank", "measure", "检测空白盘", "Check the blank disc", "info", "burner", ()),
    ("measure_image", "measure", "生成测量镜像", "Make the measurement image", "random", "burner", ("blank",)),
    ("measure_burn", "measure", "刻录测量盘", "Burn the measurement disc", "burn", "burner", ("measure_image",)),
    ("timing", "measure", "测转速", "Measure rotation", "timing", "burner", ("measure_burn",)),
    ("geo", "measure", "测几何", "Measure geometry", "geo", "burner", ("timing",)),
    ("picture", "picture", "放进图片", "Put in a picture", "image", "burner", ("geo",)),
    ("checkdisc", "check", "生成检查盘", "Make the check disc", "checkdisc", "burner", ("geo",)),
    ("check_burn", "check", "刻检查盘", "Burn the check disc", "burn", "burner", ("checkdisc",)),
    ("photos", "photo", "拍摄光盘", "Photograph the disc", "lab photos", "phone", ("check_burn",)),
    ("photo", "photo", "读出沿轨常数", "Read the along-track constant", "photo", "phone", ("photos",)),
    ("final", "final", "生成成品", "Make the final file", "image", "burner", ("photo", "picture")),
    ("final_burn", "final", "刻录成品", "Burn the final disc", "burn", "burner", ("final",)),
    ("score", "truth", "对照真值", "Compare with the truth", "lab score", "basket", ("geo",)),
]
KEYS = [s[0] for s in STEPS]
STAGES = {
    "measure": ("准备测量盘 · 测转速 · 测几何", "Measure the disc"),
    "picture": ("放进图片", "Put in a picture"),
    "check": ("先刻一张检查盘", "Burn a check disc first"),
    "photo": ("拍照", "Photos"),
    "final": ("生成成品并刻录", "Make and burn the final disc"),
    "truth": ("对照真值（只在 Lab 里有）", "Compare with the truth (Lab only)"),
}
# What each step is for, in the words disc-probe's pages use; the TUI and the page show the same line.
WHY = {
    "blank": ("光驱里放一张这批的空白盘，读出它能写多少扇区。", "Put a blank from this batch in the drive and read how many sectors it holds."),
    "measure_image": ("随机数据，每一张都不一样；几十秒。", "Random data, different on every disc; tens of seconds."),
    "measure_burn": ("把随机数据刻满这张盘。刻录不能撤销。", "Burn the random data onto this disc. A burn cannot be undone."),
    "timing": ("确认这台光驱读盘时转速稳定，1 到 3 分钟。", "Check that this drive turns steadily while reading; 1 to 3 minutes."),
    "geo": ("逐圈读出盘面螺旋的位置，约 5 分钟。", "Reads where the spiral lies, turn by turn; about 5 minutes."),
    "picture": ("把图片变成要刻的文件，现在还不刻。", "Turns a picture into the file to burn. Nothing is burned yet."),
    "checkdisc": ("第一次用这台光驱配这批盘时，先刻一张检查盘，用手机拍 3 张以上。",
                  "The first time with this drive and batch: burn a check disc and take 3 or more photos."),
    "check_burn": ("换一张这批的空白盘，刻上检查盘。", "Swap in another blank from this batch and burn the check disc."),
    "photos": ("在 Lab 里由虚拟手机拍下这张盘，不同角度拍几张。", "In the Lab a virtual phone photographs the disc from a few angles."),
    "photo": ("从照片读出沿轨方向的偏差 L。之后生成的刻录文件会自动修正它。",
              "Reads the along-track offset L from the photos. Files made afterwards correct it."),
    "final": ("用测好的几何和照片读出的 L 生成成品文件。", "Makes the final file from the geometry and the L from the photos."),
    "final_burn": ("换一张这批的空白盘，刻上成品。", "Swap in another blank from this batch and burn the final file."),
    "score": ("Lab 知道每张盘的真值：看测量和照片差了多少。", "The Lab knows every disc's truth: see how far the measurement and photos were off."),
}


def info(key):
    for s in STEPS:
        if s[0] == key:
            return dict(key=s[0], stage=s[1], zh=s[2], en=s[3], runs=s[4], place=s[5], needs=list(s[6]),
                        why=dict(zip(("zh", "en"), WHY[key])))
    raise ValueError(f"no step {key!r}; steps: {', '.join(KEYS)}")


# ------------------------------------------------------------------ state

def records(lab: Lab, key=None):
    rows = lab.state().get("steps", {}).get("flow", [])
    return [r for r in rows if key is None or r.get("key") == key]


def last_ok(lab: Lab, key):
    for r in reversed(records(lab, key)):
        if r.get("status") == "ok":
            return r
    return None


def quick_mode(lab: Lab) -> bool:
    steps = lab.state().get("steps", {})
    rows = steps.get("flow_config", []) or steps.get("tui_config", [])
    return bool(rows and rows[-1].get("quick"))


def drive_state(lab: Lab, drive=None):
    drives = lab.state().get("drives", {})
    if not drives:
        raise ValueError("这个实验盒没有光驱 / this lab has no drive")
    name = drive or next(iter(drives))
    return name, drives[name]


def family(lab: Lab) -> str:
    from .box import MEDIA
    return MEDIA[lab.box()["media"]]["family"]


def disc_state(lab: Lab, disc: str) -> str:
    """blank, burned, open or partial, from what the virtual recorder wrote (public, not truth)."""
    burn = lab.state().get("burns", {}).get(disc)
    if not burn:
        return "blank"
    if burn.get("failure"):
        return "partial"
    return "burned" if burn.get("closed", True) else "open"


def blank_discs(lab: Lab):
    return [d for d in lab.box()["discs"] if disc_state(lab, d) == "blank"]


def plan(lab: Lab):
    """Every step with done / current / detail; `current` is the first one still open."""
    done_at = {}
    out = []
    for s in STEPS:
        key, needs = s[0], s[6]
        row = last_ok(lab, key)
        # a step counts only if it was done after what it needs (a new geo makes the old picture stale)
        ok = row is not None and all(n in done_at and row["t"] >= done_at[n] for n in needs)
        if key == "photos" and ok:
            # photos that gave no L are not enough: take more (they add up), as disc-probe's phone page asks
            tried = [r["t"] for r in records(lab, "photo") if r.get("offset_mm") is None and r.get("run")]
            ok = not tried or row["t"] > max(tried)
        if key == "photo" and ok:
            ok = row.get("offset_mm") is not None
        if ok:
            done_at[key] = row["t"]
        step = info(key)
        step.update(done=ok, detail=(row or {}).get("detail", ""), disc=(row or {}).get("disc"),
                    error=None, current=False)
        last = (records(lab, key) or [None])[-1]
        if last and last.get("status") == "error" and not ok:
            step["error"] = last.get("message")
        out.append(step)
    fam = family(lab) if lab.box_path.exists() else "dvd"
    for step in out:
        if fam != "dvd" and step["key"] in ("checkdisc", "check_burn", "photos", "photo", "final", "final_burn"):
            step["skip"] = dict(zh="检查盘和拍照目前只用于 DVD。", en="The check disc and photos are DVD only for now.")
    current = next((s for s in out if not s["done"] and not s.get("skip")), None)
    if current:
        current["current"] = True
    return out


def status(lab: Lab):
    """Everything a front end draws, public only: the box, the drive, the discs, the flow and the scores."""
    box = lab.box()
    st = lab.state()
    answers = lab.answers()
    discs = []
    trays = {d.get("tray"): name for name, d in st.get("drives", {}).items() if d.get("tray")}
    for disc in box["discs"]:
        burn = st.get("burns", {}).get(disc) or {}
        isos = [Path(s["iso"]).name for s in burn.get("sessions", [])]
        used = next((r["key"] for r in reversed(records(lab)) if r.get("disc") == disc and r.get("status") == "ok"
                     and r["key"] in ("measure_burn", "check_burn", "final_burn")), None)
        discs.append(dict(id=disc, state=disc_state(lab, disc), isos=isos, drive=trays.get(disc), used_for=used))
    drives = {}
    for name, d in st.get("drives", {}).items():
        faults = [dict(id=f["id"], kind=f["kind"], params=f.get("params", {})) for f in answers.get("faults", [])]
        drives[name] = dict(reader=d.get("reader"), tray=d.get("tray"), open=bool(d.get("open")),
                            tray_state=disc_state(lab, d["tray"]) if d.get("tray") else None, faults=faults)
    from .box import MEDIA, READERS
    flow = plan(lab)
    return dict(box=dict(media=box["media"], family=family(lab), mid=box.get("mid"), batch=box.get("batch"),
                         discs=discs, count=len(discs), blanks=sum(d["state"] == "blank" for d in discs)),
                drives=drives, readers=sorted(READERS), media=sorted(MEDIA), quick=quick_mode(lab),
                flow=flow, current=next((s["key"] for s in flow if s["current"]), None),
                stages={k: dict(zh=v[0], en=v[1]) for k, v in STAGES.items()},
                photos=photo_sets(lab), photo=latest_photo(lab), pictures=pictures(lab))


def photo_sets(lab: Lab):
    rows = lab.state().get("steps", {}).get("photos", [])
    return [dict(disc=r.get("disc"), paths=r.get("paths", []), t=r.get("t"), style=r.get("style"))
            for r in rows if r.get("status") == "ok"][-6:]


def latest_photo(lab: Lab):
    """The newest reader result, as written by disc-probe, with the Lab's truth once it is scored."""
    row = next((r for r in reversed(records(lab, "photo")) if r.get("run")), None)
    if not row:
        return None
    rec = {}
    path = Path(row["paths"][0]) if row.get("paths") else None
    if path and path.exists():
        rec = lab.read(path)
    out = dict(disc=row.get("disc"), verdict=rec.get("verdict"), offset_mm=rec.get("offset_mm"),
               frames=rec.get("frames"), photos=[dict(name=p.get("name") or p.get("id"), verdict=p.get("verdict") or ("ok" if p.get("status") == "ok" else "retake"),
                                                       status=p.get("status"), reason=p.get("reason"), L_mm=p.get("L_mm"))
                                                  for p in rec.get("photos", [])],
               path=str(path) if path else None)
    if row.get("truth"):
        out["truth"] = row["truth"]
    return out


def pictures(lab: Lab):
    out = []
    for key in ("picture", "final"):
        row = last_ok(lab, key)
        if row:
            out.append(dict(key=key, paths=row.get("paths", []), detail=row.get("detail"), disc=row.get("disc")))
    return out


# ------------------------------------------------------------------ running a step

class StepError(ValueError):
    """A step that cannot go on; the message says what to do, in disc-probe's words."""


def _cmd(lab, name, *args):
    from .jsonout import run
    result = run([name, "--lab", lab.root, *args])
    if result["status"] != "ok":
        msg = "; ".join(e.get("message", "") for e in result["errors"]) or "failed"
        raise StepError(msg)
    return result


def _dp(lab, *args):
    return _cmd(lab, "dp", "--", *args)


def _need_tray_blank(lab, drive):
    _, d = drive_state(lab, drive)
    if d.get("open") or not d.get("tray"):
        raise StepError("托盘里没有盘。从光盘箩里拿一张这批的空白盘放进去。 / The tray is empty: put a blank from the basket in.")
    if disc_state(lab, d["tray"]) != "blank":
        raise StepError(f"{d['tray']} 已经刻过了。先换一张这批的空白盘。 / {d['tray']} is already written: swap in a blank from this batch.")
    return d["tray"]


def _need_tray(lab, drive):
    _, d = drive_state(lab, drive)
    if d.get("open") or not d.get("tray"):
        raise StepError("托盘里没有盘。 / The tray is empty.")
    return d["tray"]


def _geo_folder(lab):
    row = last_ok(lab, "geo")
    if not row:
        raise StepError("先测几何。 / Measure geometry first.")
    return Path(row["paths"][0])


def picture_range(lab, folder):
    """Fit the drawing to the measured island, with disc-probe's public image options."""
    fit = lab.read(folder / "summary.json")["fit"]
    islands = (fit.get("coverage") or {}).get("measured_intervals_mm") or [fit["measured_span_mm"]]
    lo, hi = max(islands, key=lambda span: span[1] - span[0])
    lo, hi = lo + 0.05, min(hi - 0.05, 57.5)
    if hi <= lo or hi < 24.7:
        raise StepError("测到的范围太窄，放不下图片。这张盘要多测一些。 / The measured span is too narrow for a picture.")
    options = ["--r-max", f"{hi - 0.6:.2f}"]
    if family(lab) == "dvd":
        options += ["--random-below-mm", f"{lo:.2f}"]
    return options


def free_iso(lab, iso):
    """Delete a burned ISO once nothing reads it any more; the recorder kept its first sectors."""
    try:
        Path(iso).unlink(missing_ok=True)
    except OSError:
        pass


def run_step(lab: Lab, key: str, *, drive=None, picture=None, photos=3, style="flash", seed=0, keep_iso=False):
    """Run one step. Returns the flow record; raises StepError with a sentence saying what to do."""
    step = info(key)
    st = plan(lab)
    me = next(s for s in st if s["key"] == key)
    refusal = me["skip"]["zh"] + " / " + me["skip"]["en"] if me.get("skip") else None
    for need in step["needs"]:
        prev = next(s for s in st if s["key"] == need)
        if not prev["done"] and refusal is None:
            refusal = f"先完成“{prev['zh']}”。 / Do “{prev['en']}” first."
    if refusal:
        lab.step("flow", key=key, status="error", message=refusal)
        raise StepError(refusal)
    drive, _ = drive_state(lab, drive)
    fam = family(lab)
    quick = quick_mode(lab)
    rec = dict(key=key, drive=drive)
    started = time.time()
    try:
        out = _STEP[key](lab, drive, fam, quick, dict(picture=picture, photos=photos, style=style, seed=seed,
                                                      keep_iso=keep_iso))
        rec.update(out)
        rec.update(status="ok", seconds=round(time.time() - started, 1))
    except StepError as exc:
        rec.update(getattr(exc, "record", {}))
        rec.update(status="error", message=str(exc))
        lab.step("flow", **rec)
        raise
    except SystemExit as exc:
        rec.update(status="error", message=str(exc))
        lab.step("flow", **rec)
        raise StepError(str(exc)) from None
    lab.step("flow", **rec)
    return rec


def _blank(lab, drive, fam, quick, o):
    disc = _need_tray_blank(lab, drive)
    out = lab.root / "results"
    r = _dp(lab, "info", "--drive", drive, "--out", out)
    return dict(disc=disc, paths=r["outputs"].get("paths", []), detail=f"{disc} 是空白盘 / {disc} is blank")


def _measure_image(lab, drive, fam, quick, o):
    disc = _need_tray_blank(lab, drive)
    iso = lab.root / "iso" / f"measurement-{disc.replace(' ', '_')}.iso"
    args = ["random", "--output", iso]
    if fam != "dvd":
        args += ["--media", fam]
    if quick:
        args += ["--sectors", "65536"]
    _dp(lab, *args)
    return dict(disc=disc, paths=[str(iso)], iso=str(iso), detail=iso.name)


def _burn(lab, drive, iso, key):
    disc = _need_tray_blank(lab, drive)
    _dp(lab, "burn", "--drive", drive, "--iso", iso, "--yes-write")
    if disc_state(lab, disc) == "blank":
        raise StepError("光驱没有写进去。 / The drive wrote nothing.")
    return dict(disc=disc, paths=[str(iso)], iso=str(iso), detail=f"{Path(iso).name} → {disc}")


def _measure_burn(lab, drive, fam, quick, o):
    return _burn(lab, drive, last_ok(lab, "measure_image")["iso"], "measure_burn")


def _timing(lab, drive, fam, quick, o):
    disc = _need_tray(lab, drive)
    if disc != last_ok(lab, "measure_burn")["disc"]:
        raise StepError("托盘里不是测量盘。把测量盘放回去。 / The measurement disc is not in the tray.")
    _dp(lab, "timing", "--drive", drive, "--media", fam, "--out", lab.root / "results",
        *(["--reps", "4", "--period-reads", "4", "--targets", "0.2,0.7"] if quick else []))
    return dict(disc=disc, detail="")


def _geo(lab, drive, fam, quick, o):
    disc = _need_tray(lab, drive)
    if disc != last_ok(lab, "measure_burn")["disc"]:
        raise StepError("托盘里不是测量盘。把测量盘放回去。 / The measurement disc is not in the tray.")
    from .loop import geo
    with (lab.root / "flow.log").open("a", encoding="utf-8") as log:
        folder, code = geo(lab, drive, disc, log, reps=8 if quick else None, max_targets=6 if quick else None)
    if code:
        raise StepError(f"测几何没有成功（退出码 {code}），详情在 {folder}。 / Geometry failed: see {folder}.")
    fit = lab.read(folder / "summary.json").get("fit", {})
    span = fit.get("measured_span_mm")
    detail = f"{span[0]:.1f}–{span[1]:.1f} mm" if span else ""
    return dict(disc=disc, paths=[str(folder)], detail=detail)


def _picture(lab, drive, fam, quick, o):
    folder = _geo_folder(lab)
    src = Path(o["picture"]) if o.get("picture") else SAMPLE
    if not src.is_file():
        raise StepError(f"找不到图片：{src} / picture not found")
    image = lab.root / "iso" / "picture.iso"
    _dp(lab, "image", "--geo", folder / "summary.json", "--picture", src, "--output", image,
        "--media", fam, "--no-photo-l", *picture_range(lab, folder))
    sidecar = image.with_suffix(".image.json")
    preview = sorted(image.parent.glob(image.stem + "*preview*.png"))
    lab.step("sample_picture", status="ok", paths=[str(image), str(sidecar)])
    return dict(paths=[str(image), str(sidecar), *map(str, preview)], picture=str(src), iso=str(image),
                detail=src.name)


def _checkdisc(lab, drive, fam, quick, o):
    if quick:
        raise StepError("快练只测了内圈，检查盘要整盘测量。 / Quick practice measured only an inner band; the check disc needs a whole-disc measurement.")
    folder = _geo_folder(lab)
    iso = lab.root / "iso" / "check.iso"
    _dp(lab, "checkdisc", "--geo", folder / "summary.json", "--output", iso)
    return dict(paths=[str(iso)], iso=str(iso), detail=iso.name)


def _check_burn(lab, drive, fam, quick, o):
    rec = _burn(lab, drive, last_ok(lab, "checkdisc")["iso"], "check_burn")
    if not o["keep_iso"]:
        # the measurement disc's bytes are read only for measuring (a re-measure needs them); once the check
        # disc is burned the measurement is settled, and the 4.7 GB image goes
        free_iso(lab, last_ok(lab, "measure_image")["iso"])
    return rec


def _photos(lab, drive, fam, quick, o):
    disc = last_ok(lab, "check_burn")["disc"]
    out = lab.root / "photos" / disc.replace(" ", "_") / time.strftime("%Y%m%d-%H%M%S")
    taken = [r for r in records(lab, "photos") if r.get("status") == "ok" and r.get("disc") == disc]
    seed = o["seed"] + 101 * len(taken)          # another set of poses for each retake
    r = _cmd(lab, "photos", "--disc", disc, "-n", str(o["photos"]), "--style", o["style"], "--seed", str(seed),
             "--out", out)
    paths = r["outputs"].get("paths", [])
    total = len(paths) + sum(len(_jpegs(r)) for r in taken if r["t"] > last_ok(lab, "check_burn")["t"])
    return dict(disc=disc, paths=paths, seed=seed, detail=f"这张盘共 {total} 张 / {total} photos of this disc", style=o["style"])


def _jpegs(row):
    return [p for p in row.get("paths", []) if p.lower().endswith((".jpg", ".jpeg", ".png"))]


def _photo(lab, drive, fam, quick, o):
    shots = last_ok(lab, "photos")
    disc = shots["disc"]
    since = last_ok(lab, "check_burn")["t"]
    photos = [p for r in records(lab, "photos") if r.get("status") == "ok" and r.get("disc") == disc
              and r["t"] > since for p in _jpegs(r)]
    from .loop import copy_run
    run_dir = copy_run(_geo_folder(lab), lab.root / "runs" / disc.replace(" ", "_") / time.strftime("%Y%m%d-%H%M%S"))
    _dp(lab, "photo", "--run", run_dir, "--media", fam, "--photos", *photos, "--disc-id", disc,
        "--burner", drive, "--burn-path", "IMAPI", "--burn-mode", "dvd-dao" if fam == "dvd" else "cd-mode2form1")
    rec = lab.read(run_dir / "photo.json")
    truth = None
    try:
        from .loop import truth_L
        t = truth_L(lab, _geo_folder(lab), disc)
        truth = dict(L_mm=t.get("L_mm", t.get("along_mm")), detail=t)
    except Exception:
        truth = None
    est = rec.get("offset_mm")
    detail = (f"L = {est:+.3f} mm" if est is not None
              else f"没有给出 L：{rec.get('verdict')} / no L: {rec.get('verdict')}")
    if est is not None and truth and truth.get("L_mm") is not None:
        truth["error_mm"] = est - truth["L_mm"]
    out = dict(disc=disc, paths=[str(run_dir / "photo.json")], run=str(run_dir), verdict=rec.get("verdict"),
               offset_mm=est, truth=truth, detail=detail, photos=len(photos))
    if est is None:
        usable = sum(p.get("status") == "ok" for p in rec.get("photos", []))
        raise _Refused(out, f"{len(photos)} 张里能用 {usable} 张，还读不出可信的 L。回到“拍摄光盘”再拍几张不同角度的。"
                            f" / {usable} of {len(photos)} photos usable; no reliable L yet. Photograph the disc again from other angles.")
    return out


class _Refused(StepError):
    """A step that ran and left a result, but not one the next step may use; the record keeps the result."""

    def __init__(self, record, message):
        super().__init__(message)
        self.record = record


def _final(lab, drive, fam, quick, o):
    row = last_ok(lab, "photo")
    if row.get("offset_mm") is None:
        raise StepError(f"照片没有给出可信的 L（{row.get('verdict')}），回手机再拍几张。 / The photos gave no usable L: take more.")
    run_dir = Path(row["run"])
    src = Path(o["picture"]) if o.get("picture") else Path(last_ok(lab, "picture").get("picture") or SAMPLE)
    image = lab.root / "iso" / "final.iso"
    _dp(lab, "image", "--geo", run_dir / "summary.json", "--picture", src, "--output", image, "--media", fam,
        *picture_range(lab, run_dir))
    sidecar = image.with_suffix(".image.json")
    decision = lab.read(sidecar).get("photo_l", {})
    if not decision.get("written"):
        raise StepError(f"沿轨常数没写进去：{decision.get('reason')}。 / The along-track constant was not written: {decision.get('reason')}.")
    lab.step("picture_L", status="ok", paths=[str(sidecar)])
    if not o["keep_iso"]:                 # the preview's own burn file is not burned: the final file replaces it
        pic = last_ok(lab, "picture")
        if pic and pic.get("iso") and Path(pic["iso"]) != image:
            free_iso(lab, pic["iso"])
    return dict(paths=[str(image), str(sidecar)], iso=str(image), picture=str(src),
                detail=f"L = {decision.get('L_mm', row['offset_mm']):+.3f} mm 已写入 / L = {decision.get('L_mm', row['offset_mm']):+.3f} mm written")


def _final_burn(lab, drive, fam, quick, o):
    rec = _burn(lab, drive, last_ok(lab, "final")["iso"], "final_burn")
    if not o["keep_iso"]:
        free_iso(lab, last_ok(lab, "checkdisc")["iso"])
    return rec


def _score(lab, drive, fam, quick, o):
    r = _cmd(lab, "score", "--progress")
    return dict(paths=r["outputs"].get("paths", []), detail="")


_STEP = dict(blank=_blank, measure_image=_measure_image, measure_burn=_measure_burn, timing=_timing, geo=_geo,
             picture=_picture, checkdisc=_checkdisc, check_burn=_check_burn, photos=_photos, photo=_photo,
             final=_final, final_burn=_final_burn, score=_score)


# ------------------------------------------------------------------ CLI

def cmd_status(a):
    lab = Lab(a.lab)
    if not lab.box_path.exists():
        raise SystemExit("这里还没有实验盒。先建一箩光盘：python -m disclab box --lab LAB")
    return dict(status=status(lab))


def cmd_step(a):
    lab = Lab(a.lab)
    if a.quick is not None:
        lab.step("flow_config", status="ok", quick=bool(a.quick))
    key = a.key
    if key == "next":
        key = next((s["key"] for s in plan(lab) if s["current"]), None)
        if key is None:
            return dict(step=None, status=status(lab))
    try:
        rec = run_step(lab, key, drive=a.drive, picture=a.picture, photos=a.photos, style=a.style, seed=a.seed,
                       keep_iso=a.keep_iso)
    except StepError as exc:
        raise SystemExit(str(exc)) from None
    return dict(step=rec, status=status(lab))


def cmd_swap(a):
    """Take a blank from the basket and put it in the tray (disc-probe's “换一张空白盘”)."""
    lab = Lab(a.lab)
    drive, _ = drive_state(lab, a.drive)
    disc = a.disc or next(iter(blank_discs(lab)), None)
    if disc is None:
        raise SystemExit("箩里没有空白盘了。建一箩新的。 / No blank left in the basket: make a new one.")
    from .jsonout import run
    r = run(["tray", "--lab", lab.root, "--drive", drive, "--disc", disc])
    if r["status"] != "ok":
        raise SystemExit(r["errors"][-1]["message"])
    return dict(disc=disc, drive=drive, status=status(lab))


def add_parser(sub):
    p = sub.add_parser("status", help="the box, drive, discs and practice flow, for a front end")
    p.add_argument("--lab", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("step", help="run one practice step by name (disc-probe's order), or 'next'")
    p.add_argument("key", choices=KEYS + ["next"])
    p.add_argument("--lab", required=True)
    p.add_argument("--drive")
    p.add_argument("--picture", help="picture file for 放进图片 / 生成成品 (default: the lab's sample)")
    p.add_argument("--photos", type=int, default=3, help="拍摄光盘: how many photos")
    p.add_argument("--style", default="flash", help="拍摄光盘: flash, handheld, room, ...")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--quick", action="store_true", default=None, help="small inner-band measurement (no photos)")
    p.add_argument("--keep-iso", action="store_true", help="keep burned ISOs (default frees them once unused)")
    p.set_defaults(func=cmd_step)

    p = sub.add_parser("swap", help="put a blank from the basket into the tray")
    p.add_argument("--lab", required=True)
    p.add_argument("--drive")
    p.add_argument("--disc", help="this disc instead of the next blank")
    p.set_defaults(func=cmd_swap)
