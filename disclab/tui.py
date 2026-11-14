"""The Lab's guided console: disc-probe's steps, in its order and with its names, on virtual discs.

It reads like `python -m discprobe guide` and the guided console: where you are ([x] done, <- here), what the
next step does, and one key to run it. Every step is `disclab step <name>` (flow.py), the same code the desk page
runs; all progress is in LAB/state.json, so the page, the CLI and this console can take turns on one lab.
Standard library and lab helpers only.
"""
from __future__ import annotations

import ctypes
import locale
import os
from pathlib import Path
import sys

from . import flow
from .jsonout import run
from .lab import Lab

PROG = "python -m disclab"
STATE = {"blank": ("空白", "blank"), "burned": ("已刻", "written"), "open": ("未封口", "open session"),
         "partial": ("刻了一半", "partly written")}
USED = {"measure_burn": ("测量盘", "measurement disc"), "check_burn": ("检查盘", "check disc"),
        "final_burn": ("成品", "final disc")}
KEYS = ("Enter 运行这一步 · 数字 运行某一步 · s 换空白盘 · t 放盘 · o 弹出/推上托盘 · r 读盘配置 · f 故障 · "
        "p 拍照设置 · i 选图片 · a 依次做完 · b 新的一箩 · q 退出",
        "Enter run this step · number run a step · s swap in a blank · t put a disc in · o open/close the tray · "
        "r reader · f faults · p photo settings · i picture · a run the rest · b new basket · q quit")
LANG = "zh"


def T(zh, en):
    return en if LANG == "en" else zh


def pick(text):
    """Lab messages are written "中文 / English"; show the half in this console's language."""
    text = str(text or "")
    if " / " not in text:
        return text
    zh, en = text.split(" / ", 1)
    return T(zh, en)


def system_is_chinese():
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(name):
            return os.environ[name].lower().startswith("zh")
    if os.name == "nt":
        try:
            return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x04
        except (AttributeError, OSError):
            pass
    return (locale.getlocale()[0] or "").lower().startswith(("zh", "chinese"))


def utf8_console():
    """Write UTF-8, as the disc-probe processes the lab starts do (lab_env sets PYTHONIOENCODING=utf-8).

    On Windows a redirected or piped stdout otherwise gets the ANSI code page (GBK) from this process and
    UTF-8 from its children, and the Chinese in the shared log or console comes out garbled. A real console
    is unaffected (Python writes it as Unicode either way)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def ask(prompt, default=""):
    answer = input(f"{prompt} [{default}]: " if default != "" else f"{prompt}: ").strip()
    return answer or str(default)


def yes(prompt, default=True):
    answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not answer else answer in ("y", "yes", "是", "好")


QUIET = {"box", "tray", "swap", "drive", "status"}     # settings: the console says it in one line instead


def command(lab, name, *args):
    if name in QUIET:
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            result = run([name, "--lab", lab.root, *args])
    else:
        result = run([name, "--lab", lab.root, *args])
    if result["status"] != "ok":
        raise ValueError("; ".join(e.get("message", "") for e in result["errors"]) or "failed")
    return result


def disc_words(lab, disc):
    st = flow.status(lab)
    row = next((d for d in st["box"]["discs"] if d["id"] == disc), None)
    if not row:
        return disc
    used = T(*USED[row["used_for"]]) + T("，", ", ") if row.get("used_for") else ""
    return f"{disc}（{used}{T(*STATE[row['state']])}）" if LANG == "zh" else f"{disc} ({used}{T(*STATE[row['state']])})"


def where(lab, colour=False):
    """The progress block, as disc-probe's guide prints it."""
    st = flow.status(lab)
    b, (name, d) = st["box"], next(iter(st["drives"].items()))
    lines = [T(f"实验盒：{lab.root}", f"Lab: {lab.root}"),
             T(f"{b['media'].upper()} · {b['mid']} · 批次 {b['batch']} · {b['count']} 张，空白 {b['blanks']} 张",
               f"{b['media'].upper()} · {b['mid']} · batch {b['batch']} · {b['count']} discs, {b['blanks']} blank"),
             f"{name} · {d['reader']} · " + (T("托盘里：", "in the tray: ") + disc_words(lab, d["tray"]) if d["tray"]
                                            else T("托盘空着", "tray empty")) + (T(" · 托盘开着", " · tray open") if d["open"] else "")]
    if d["faults"]:
        lines.append(T("注入的故障：", "Injected faults: ") + ", ".join(f"{f['id']} ({f['kind']})" for f in d["faults"]))
    if st["quick"]:
        lines.append(T("快练：只测内圈，不能拍照。", "Quick practice: inner band only, no photos."))
    lines += ["", T(f"{b['family'].upper()} 的进度：", f"Where you are, for {b['family'].upper()}:")]
    stage = None
    width = max(sum(2 if ord(ch) > 0x2E7F else 1 for ch in f"{T(s['zh'], s['en'])} ({s['runs']})") for s in st["flow"]) + 2
    for i, s in enumerate(st["flow"], 1):
        if s["stage"] != stage:
            stage = s["stage"]
            lines.append("  " + T(*[st["stages"][stage]["zh"], st["stages"][stage]["en"]]))
        mark = "x" if s["done"] else "-" if s.get("skip") else " "
        label = f"{T(s['zh'], s['en'])} ({s['runs']})"
        detail = (T(s["skip"]["zh"], s["skip"]["en"]) if s.get("skip") else pick(s.get("detail")))
        if s["current"]:
            detail = (detail + "  " if detail else "") + T("<- 现在到这里", "<- you are here")
        line = f"  {i:>2} [{mark}] {pad(label, width)} {detail}".rstrip()
        if s["current"] and colour:
            line = "\033[1m" + line + "\033[0m"
        lines.append(line)
        if s.get("error") and not s["done"]:
            lines.append(" " * 10 + T("上次没成功：", "last try failed: ") + pick(s["error"]))
    c = next((s for s in st["flow"] if s["current"]), None)
    lines.append("")
    if c:
        lines.append(T("下一步：", "Next: ") + T(c["zh"], c["en"]) + " —— " + T(c["why"]["zh"], c["why"]["en"])
                     if LANG == "zh" else "Next: " + c["en"] + " — " + c["why"]["en"])
        lines.append("  " + f"{PROG} step {c['key']} --lab \"{lab.root}\"")
    else:
        lines.append(T("这一轮练完了。b 建一箩新的再练，或在桌面上看对照真值。", "This round is done. b makes a new basket."))
    return "\n".join(lines)


def pad(text, width):
    w = sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)
    return text + " " * max(1, width - w)


def run_step(lab, key, opts):
    """One step, with disc-probe's checks before it: a blank in the tray, the measurement disc back, a burn confirmed."""
    st = flow.status(lab)
    name, d = next(iter(st["drives"].items()))
    s = next(x for x in st["flow"] if x["key"] == key)
    if key in ("blank", "measure_image", "measure_burn", "check_burn", "final_burn"):
        if not d["tray"] or d["open"] or d["tray_state"] != "blank":
            why = (T(f"{d['tray']} 已经刻过了。", f"{d['tray']} is written. ") if d["tray"] and d["tray_state"] != "blank"
                   else T("托盘里没有空白盘。", "There is no blank in the tray. "))
            if not yes(why + T("从箩里换一张这批的空白盘？", "Swap in a blank from this batch?")):
                return False
            print(T("换盘：", "Swapped in: ") + command(lab, "swap")["outputs"]["disc"])
    if key in ("timing", "geo"):
        m = next((x["id"] for x in st["box"]["discs"] if x["used_for"] == "measure_burn"), None)
        if m and d["tray"] != m:
            print(T(f"把测量盘 {m} 放回光驱。", f"Putting the measurement disc {m} back."))
            command(lab, "tray", "--disc", m)
    if key in ("measure_burn", "check_burn", "final_burn"):
        disc = flow.drive_state(lab)[1]["tray"]
        if not yes(T(f"刻到 {disc}。刻录不能撤销。现在刻？", f"Burn onto {disc}. A burn cannot be undone. Burn now?"), default=False):
            print(T("没有刻。", "Not burned."))
            return False
    print(T(f"== {s['zh']}（{s['runs']}）", f"== {s['en']} ({s['runs']})"), flush=True)
    args = ["step", key]
    if opts.get("picture") and key in ("picture", "final"):
        args += ["--picture", opts["picture"]]
    if key == "photos":
        args += ["--photos", str(opts["photos"]), "--style", opts["style"]]
    rec = command(lab, *args)["outputs"]["step"]
    print(T("好了：", "Done: ") + (pick(rec.get("detail")) or T(s["zh"], s["en"])))
    if key == "photo":
        photo = flow.latest_photo(lab) or {}
        truth = (rec.get("truth") or {})
        if rec.get("offset_mm") is None:
            print(T(f"照片没有给出可信的 L（{rec.get('verdict')}）。p 改拍照设置，再做“拍摄光盘”。",
                    f"The photos gave no usable L ({rec.get('verdict')}). Change the photo settings (p) and photograph again."))
        for p in photo.get("photos", []):
            print(f"   {p['name']}: {p['verdict']} {p.get('status') or ''}")
        if truth.get("L_mm") is not None and rec.get("offset_mm") is not None:
            print(T(f"只在 Lab 里有：真值 L = {truth['L_mm']:+.3f} mm，差 {truth['error_mm']:+.3f} mm。",
                    f"Lab only: true L = {truth['L_mm']:+.3f} mm, off by {truth['error_mm']:+.3f} mm."))
    if key == "score":
        g = (lab.read(lab.root / "scores" / "tui.json") or {}).get("geo", {})
        print(T(f"几何：u 差 {g.get('du_bits', 0):+.3f} bit，v 差 {g.get('dv_rel', 0) * 1e6:+.1f} ppm。",
                f"Geometry: u off {g.get('du_bits', 0):+.3f} bit, v off {g.get('dv_rel', 0) * 1e6:+.1f} ppm."))
    return True


def new_basket(lab_hint):
    root = ask(T("实验目录（新的或空的文件夹，或已有的实验盒）", "Lab folder (new or empty, or an existing lab)"),
               str(lab_hint.root) if lab_hint else str(Path.cwd() / "LAB-practice"))
    candidate = Lab(root)
    if candidate.box_path.exists():
        return candidate
    if candidate.root.exists() and any(candidate.root.iterdir()):
        raise ValueError(T("这个文件夹里有别的东西。选一个空文件夹，或已有的实验盒。",
                           "That folder holds other files. Choose an empty folder or an existing lab."))
    from .box import MEDIA, READERS
    media = ask(T("盘种", "Media") + f" ({', '.join(MEDIA)})", "dvd-r")
    count = int(ask(T("几张", "How many discs"), "3"))
    seed = int(ask(T("随机种子", "Seed"), "1"))
    reader = ask(T("读盘配置", "Reader") + f" ({', '.join(READERS)})", "gh70n")
    if reader not in READERS:
        raise ValueError(T("读盘配置只能是 ", "reader must be one of ") + ", ".join(READERS))
    if count < 1:
        raise ValueError(T("至少一张。", "At least one disc."))
    command(candidate, "box", "--media", media, "--count", count, "--seed", seed, "--reader", reader)
    command(candidate, "swap")
    print(T("建好了，第一张已经放进光驱。", "Made; the first disc is in the drive."))
    return candidate


def settings(lab, key, opts):
    st = flow.status(lab)
    name, d = next(iter(st["drives"].items()))
    if key == "s":
        print(T("换盘：", "Swapped in: ") + command(lab, "swap")["outputs"]["disc"])
    elif key == "t":
        discs = st["box"]["discs"]
        for i, x in enumerate(discs, 1):
            print(f"  {i} {disc_words(lab, x['id'])}" + (T("  <- 在光驱里", "  <- in the drive") if x["drive"] else ""))
        n = int(ask(T("放哪一张", "Which disc"), "1"))
        if not 1 <= n <= len(discs):
            raise ValueError(T("没有这张盘。", "No such disc."))
        command(lab, "tray", "--disc", discs[n - 1]["id"])
    elif key == "o":
        if d["open"]:
            command(lab, "tray", "--disc", d["tray"]) if d["tray"] else command(lab, "tray")
        else:
            command(lab, "tray", "--open")
    elif key == "r":
        print("  " + " · ".join(st["readers"]))
        command(lab, "drive", "--reader", ask(T("读盘配置", "Reader"), d["reader"]))
    elif key == "f":
        for f in d["faults"]:
            print(f"  {f['id']}: {f['kind']} {f['params']}")
        print(T("  加：read_error:{\"r_mm\":[40,41]} · spindle_unsteady · capacity_misreport:{\"offset\":-20000} · "
                "burn_interrupt:{\"fraction\":0.5}；去掉：-ID 或 -all",
                "  add: read_error:{\"r_mm\":[40,41]} · spindle_unsteady · capacity_misreport:{\"offset\":-20000} · "
                "burn_interrupt:{\"fraction\":0.5}; remove: -ID or -all"))
        spec = ask(T("故障", "Fault"), "")
        if spec.startswith("-"):
            command(lab, "drive", "--clear", spec[1:])
        elif spec:
            command(lab, "drive", "--fault", spec)
    elif key == "p":
        opts["photos"] = int(ask(T("拍几张", "How many photos"), opts["photos"]))
        opts["style"] = ask(T("怎么拍（flash 闪光灯 / handheld 手拿室内灯）", "How (flash / handheld)"), opts["style"])
    elif key == "i":
        path = ask(T("图片文件（空着用示例图）", "Picture file (empty: the sample)"), opts.get("picture") or "")
        if path and not Path(path).is_file():
            raise ValueError(T("找不到这个文件。", "File not found."))
        opts["picture"] = path or None


def session(a):
    global LANG
    LANG = a.lang or ("zh" if system_is_chinese() else "en")
    utf8_console()
    lab = Lab(a.lab) if a.lab else None
    colour = not a.plain and sys.stdout.isatty() and (os.name == "nt" or os.environ.get("TERM") not in (None, "dumb"))
    print(T("Disc Lab · 虚拟光盘练习，不消耗真实光盘。步骤和 disc-probe 一一对应。",
            "Disc Lab · practice on virtual discs; no real disc is used. The steps are disc-probe's."))
    if lab and lab.box_path.exists() and a.quick is not None:
        lab.step("flow_config", status="ok", quick=bool(a.quick))
    opts = dict(photos=3, style="flash", picture=None)
    while True:
        try:
            if lab is None or not lab.box_path.exists():
                print(T("先选一个实验盒，或建一箩新的。", "Choose a lab or make a new basket first."))
                lab = new_basket(lab)
                a.lab = str(lab.root)
                if a.quick is not None:
                    lab.step("flow_config", status="ok", quick=bool(a.quick))
                continue
            print()
            print(where(lab, colour))
            print(T(*KEYS))
            choice = ask(">", "").strip().lower()
            if choice in ("q", "0", "quit", "exit"):
                break
            plan = flow.plan(lab)
            if choice in ("", "n", "next"):
                c = next((s for s in plan if s["current"]), None)
                if c is None:
                    print(T("没有要做的步骤了。", "Nothing left to do."))
                    continue
                run_step(lab, c["key"], opts)
            elif choice.isdigit() and 1 <= int(choice) <= len(plan):
                run_step(lab, plan[int(choice) - 1]["key"], opts)
            elif choice == "a":
                while (c := next((s for s in flow.plan(lab) if s["current"]), None)) is not None:
                    if not run_step(lab, c["key"], opts):
                        break
            elif choice == "b":
                lab = new_basket(None)
                a.lab = str(lab.root)
            elif choice in ("s", "t", "o", "r", "f", "p", "i"):
                settings(lab, choice, opts)
            else:
                print(T("没有这个键。", "No such key."))
        except (EOFError, KeyboardInterrupt):
            break
        except (ValueError, IndexError, KeyError, OSError, RuntimeError) as exc:
            if lab and lab.state_path.exists():
                lab.step("tui_action", status="error", error=str(exc))
            print(T("没有成功：", "That did not work: ") + pick(exc))
    print(T(f"结果都在：{lab.root if lab else '（没有实验盒）'}", f"Results: {lab.root if lab else '(no lab)'}"))
    return dict(paths=[str(lab.root / "state.json")] if lab else [])


def add_parser(sub):
    p = sub.add_parser("tui", help="guided practice console: disc-probe's steps on virtual discs")
    p.add_argument("--lab")
    p.add_argument("--plain", action="store_true", help="no colour")
    p.add_argument("--lang", choices=("zh", "en"), help="language (default: the system's)")
    p.add_argument("--quick", action="store_true", default=None,
                   help="small inner-band measurement; quick to run, but no photos")
    p.set_defaults(func=session)
