"""Portable numbered prompts. All durable progress belongs to LAB/state.json."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from .jsonout import run, last_step as latest, geo_folder
from .lab import Lab


MENU = """
Disc Lab / 虚拟光盘练习
1 Choose/create box / 选择或创建实验盒
2 Insert disc / 放入虚拟盘
3 Burn measurement disc / 刻录测量盘
4 Timing / 时序测量
5 Geo / 几何测量
6 Sample picture ISO / 示例图片 ISO
7 Lab target, virtual burn, photos / 双纹理靶、虚拟刻录、照片
8 Photo L / 照片读取 L
9 Picture with L, virtual burn / 带 L 图片、虚拟刻录
10 Scores against truth / 对照真值评分
11 Walk the whole flow / 依次执行完整流程
0 Exit / 退出
"""


def ask(prompt, default=""):
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or str(default)


def command(lab, name, *args):
    result = run([name, "--lab", lab.root, *args])
    if result["status"] != "ok":
        raise ValueError(result["errors"])
    return result


def dp(lab, *args):
    return command(lab, "dp", "--", *args)


def selected(lab):
    drive, state = next(iter(lab.state()["drives"].items()))
    if not state.get("tray") or state.get("open"):
        raise ValueError("insert a disc first / 请先放盘")
    return drive, state["tray"]


def fresh(lab):
    for disc in lab.box()["discs"]:
        if disc not in lab.state()["burns"]:
            return disc
    raise ValueError("no unused virtual disc; create a new box / 没有空虚拟盘，请创建新盒")


def quick_mode(lab):
    settings = lab.state().get("steps", {}).get("tui_config", [])
    return bool(settings and settings[-1].get("quick"))


def picture_range(lab, folder, family):
    """Fit the drawing to a measured island using the product's public image options."""
    fit = lab.read(folder / "summary.json")["fit"]
    islands = (fit.get("coverage") or {}).get("measured_intervals_mm") or [fit["measured_span_mm"]]
    lo, hi = max(islands, key=lambda span: span[1] - span[0])
    lo, hi = lo + 0.05, min(hi - 0.05, 57.5)
    if hi <= lo or hi < 24.7:
        raise ValueError("measured interval is too small; read more of this disc")
    options = ["--r-max", str(hi - 0.6)]
    if family == "dvd":
        options += ["--random-below-mm", str(lo)]
    return options


def action(lab, choice):
    quick = quick_mode(lab)
    drive = next(iter(lab.state()["drives"]))
    from .box import MEDIA
    family = MEDIA[lab.box()["media"]]["family"]
    if lab.box()["media"].startswith("bd") and choice in {"6", "7", "8", "9"}:
        raise ValueError("picture/photo workflow currently supports DVD/CD; BD can use CLI timing/geo")
    if choice == "2":
        discs = lab.box()["discs"]
        for i, disc in enumerate(discs, 1):
            print(f"{i} {disc}")
        number = int(ask("Disc number / 盘号", "1"))
        if not 1 <= number <= len(discs):
            raise ValueError("disc number is outside this box")
        disc = discs[number - 1]
        command(lab, "tray", "--drive", drive, "--disc", disc)
    elif choice == "3":
        _, disc = selected(lab)
        if disc in lab.state()["burns"]:
            raise ValueError("disc already written; insert an unused virtual disc")
        iso = lab.root / "iso" / f"measurement-{disc.replace(' ', '_')}.iso"
        dp(lab, "random", "--output", iso, *(["--sectors", "65536"] if quick else []))
        dp(lab, "burn", "--drive", drive, "--iso", iso, "--yes-write")
    elif choice == "4":
        selected(lab)
        dp(lab, "timing", "--drive", drive, "--media", family, "--out", lab.root / "results",
           *(["--reps", "4", "--period-reads", "4", "--targets", "0.2,0.7"] if quick else []))
    elif choice == "5":
        _, disc = selected(lab)
        from .loop import geo
        with (lab.root / "tui.log").open("a", encoding="utf-8") as log:
            folder, code = geo(lab, drive, disc, log, reps=8 if quick else None,
                               max_targets=6 if quick else None)
        if code:
            raise ValueError(f"geo exit {code}: {folder}")
        command(lab, "score", "--disc", disc, "--geo", folder)
    elif choice == "6":
        folder = geo_folder(lab)
        image = lab.root / "iso" / "sample.iso"
        dp(lab, "image", "--geo", folder / "summary.json", "--picture",
           Path(__file__).parent / "data" / "sample.pgm", "--output", image,
           "--media", family, "--no-photo-l", *picture_range(lab, folder, family))
        lab.step("sample_picture", status="ok", paths=[str(image), str(image.with_suffix(".image.json"))])
    elif choice == "7":
        print("Lab A5/B9 two-texture target only. checkdisc target cannot be rendered yet.\n"
              "只渲染实验盒双纹理靶，目前不能渲染 checkdisc 靶。")
        if quick:
            raise ValueError("quick mode measures only an inner band; the 26.2–57.2 mm photo target needs a full measurement")
        from .target import target_npy
        design = target_npy(lab.root / "designs" / "photo-target.npy")
        folder = geo_folder(lab)
        disc = fresh(lab)
        image = lab.root / "iso" / f"photo-target-{disc.replace(' ', '_')}.iso"
        dp(lab, "image", "--geo", folder / "summary.json", "--design-npy", design,
           "--output", image, "--media", family, "--no-photo-l",
           *picture_range(lab, folder, family))
        command(lab, "tray", "--drive", drive, "--disc", disc)
        dp(lab, "burn", "--drive", drive, "--iso", image, "--yes-write")
        command(lab, "photos", "--disc", disc, "-n", "3", "--style", "flash",
                "--out", lab.root / "photos" / "tui" / disc.replace(" ", "_"))
    elif choice == "8":
        row = latest(lab, "photos")
        disc = row["disc"]
        from .loop import copy_run
        folder = copy_run(geo_folder(lab), lab.root / "runs" / "tui" / disc.replace(" ", "_"))
        dp(lab, "photo", "--run", folder, "--media", family, "--photos", *row["paths"],
           "--disc-id", disc, "--burner", drive, "--burn-path", "IMAPI",
           "--burn-mode", "dvd-dao" if family == "dvd" else "cd-mode2form1")
    elif choice == "9":
        row = latest(lab, "photo_L")
        folder = Path(row["paths"][0]).parent
        rec = lab.read(folder / "photo.json")
        if rec.get("offset_mm") is None:
            raise ValueError(f"photo L was not applied: {rec.get('verdict')}; refusal preserved")
        disc = fresh(lab)
        image = lab.root / "iso" / f"picture-L-{disc.replace(' ', '_')}.iso"
        dp(lab, "image", "--geo", folder / "summary.json", "--picture",
           Path(__file__).parent / "data" / "sample.pgm", "--output", image, "--media", family,
           *picture_range(lab, folder, family))
        decision = lab.read(image.with_suffix(".image.json")).get("photo_l", {})
        if not decision.get("written"):
            raise ValueError(f"image did not apply photo L: {decision.get('reason')}; refusal preserved")
        command(lab, "tray", "--drive", drive, "--disc", disc)
        dp(lab, "burn", "--drive", drive, "--iso", image, "--yes-write")
        lab.step("picture_L", status="ok", disc=disc, paths=[str(image.with_suffix(".image.json"))])
    elif choice == "10":
        show_scores(lab)
    else:
        raise ValueError("unknown menu number / 无此菜单项")


def show_scores(lab):
    return command(lab, "score", "--progress")


def session(a):
    lab = Lab(a.lab) if a.lab else None
    # Colour only on terminals advertising ANSI support; Windows plain prompts also work in pipes.
    colour = not a.plain and sys.stdout.isatty() and os.environ.get("TERM") not in (None, "dumb")
    print("No physical discs are used up / 不消耗真实光盘。")
    print("Measurement, photo target and final picture use separate virtual discs (minimum 3).")
    if lab and lab.box_path.exists() and a.quick is not None:
        lab.step("tui_config", status="ok", quick=bool(a.quick))
    while True:
        print(("\033[36m" + MENU + "\033[0m") if colour else MENU)
        if lab:
            print(f"Lab: {lab.root}")
        try:
            choice = ask("Action / 操作", "0")
            if choice == "0":
                break
            if choice == "1":
                root = ask("Lab folder / 实验盒目录", str(lab.root) if lab else
                           str(Path.cwd() / "LAB-tui"))
                candidate = Lab(root)
                if not candidate.box_path.exists():
                    if candidate.root.exists() and any(candidate.root.iterdir()):
                        raise ValueError("choose an empty folder / 请选择空目录")
                    media = ask("Media / 盘种", "dvd-r")
                    count = int(ask("Disc count / 数量", "3"))
                    seed = int(ask("Seed / 种子", "1"))
                    reader = ask("Reader profile / 读盘配置", "gh70n")
                    from .box import READERS
                    if reader not in READERS:
                        raise ValueError("reader must be one of " + ", ".join(READERS))
                    if count < 1:
                        raise ValueError("count must be positive")
                    command(candidate, "box", "--media", media, "--count", count,
                            "--seed", seed, "--reader", reader)
                lab = candidate
                a.lab = str(lab.root)
                if a.quick is not None or not lab.state().get("steps", {}).get("tui_config"):
                    lab.step("tui_config", status="ok", quick=bool(a.quick))
            elif lab is None or not lab.box_path.exists():
                print("Choose/create a box first / 请先选择或创建实验盒。")
            elif choice == "11":
                command(lab, "tray", "--disc", fresh(lab))
                for step in ("3", "4", "5", "6", "7", "8", "9", "10"):
                    print(f"Flow step / 流程步骤 {step}")
                    try:
                        action(lab, step)
                    except (ValueError, RuntimeError) as exc:
                        print(f"Step {step}: {exc}")
                        if step != "9":
                            break
            else:
                action(lab, choice)
        except (EOFError, KeyboardInterrupt):
            break
        except (ValueError, IndexError, KeyError, OSError, RuntimeError) as exc:
            if lab and lab.state_path.exists():
                lab.step("tui_action", status="error", action=choice, error=str(exc))
            print(f"Action failed / 操作失败: {exc}")
    print(f"Results / 结果: {lab.root if lab else '(no lab)'}")
    return dict(paths=[str(lab.root / "state.json")] if lab else [])


def add_parser(sub):
    p = sub.add_parser("tui", help="portable numbered practice menus")
    p.add_argument("--lab")
    p.add_argument("--plain", action="store_true", help="disable ANSI colour")
    p.add_argument("--quick", action="store_true", default=None,
                   help="small inner-band practice; scores include extrapolation")
    p.set_defaults(func=session)
