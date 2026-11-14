"""Disposable virtual practice workspace and the existing web launcher."""
from __future__ import annotations

import tempfile

from .lab import Lab
from .web import port_number, serve


GUIDE = """练习模式 / Practice mode — 不消耗真实光盘 / No physical discs are used up.
这里开的是 disc-probe 自己的网页，光驱是虚拟的 X:，照网页一步步走即可：
This is disc-probe's own page; the drive is the virtual X:. Follow the page step by step:
  检测空白盘 → 生成测量镜像 → 刻录 → 测转速 → 测几何 → 放进图片 → 预览
  → 生成检查盘 → 换盘 → 刻检查盘 → 拍摄光盘 → 生成成品
拍照这一步用 Lab 渲染的照片：python -m disclab photos --lab LAB --disc <检查盘> --out LAB/photos，
再从网页的手机链接上传（或 python -m disclab upload）。
For the photo step, render photos with `disclab photos` and send them through the page's phone link (or `disclab upload`).
Lab 自己的桌面（光盘箩、刻录机、手机）/ The Lab's own desk: python -m disclab desk --lab LAB
引导式控制台 / Guided console: python -m disclab tui --lab LAB
Ctrl+C 退出；结果留着，下次用同一个 --lab 接着练。/ Ctrl+C stops; results stay, and the same --lab resumes.
"""


def prepare(root=None, media="dvd-r"):
    lab = Lab(root or tempfile.mkdtemp(prefix="disc-lab-practice-"))
    if lab.box_path.exists():
        return lab                     # an existing lab: carry on where it stopped
    if lab.root.exists() and any(lab.root.iterdir()):
        raise ValueError("practice needs a new or empty folder, or an existing lab; this folder holds other files "
                         "/ 练习要用新的或空的文件夹，或者已有的实验盒；这个文件夹里有别的文件")
    from .jsonout import run
    result = run(["box", "--lab", lab.root, "--media", media, "--count", "3", "--seed", "1"])
    if result["status"] != "ok":
        raise RuntimeError(result["errors"])
    run(["tray", "--lab", lab.root, "--disc", lab.box()["discs"][0]])
    return lab


def practice(a):
    from .tui import utf8_console
    utf8_console()
    resumed = bool(a.lab) and Lab(a.lab).box_path.exists()
    lab = prepare(a.lab, a.media)
    # Let the outer API dispatcher report the generated path too.
    a.lab = str(lab.root)
    print(GUIDE, flush=True)
    print(("接着练 / Resuming: " if resumed else "Lab: ") + str(lab.root), flush=True)
    media = lab.box()["media"]
    family = "cd" if media.startswith("cd") else "bd" if media.startswith("bd") else "dvd"
    lab.step("practice", status="started", paths=[str(lab.root)], port=a.port)
    try:
        code = serve(lab, a.port, family, a.lan)
    finally:
        lab.step("practice", status="stopped", paths=[str(lab.root / "results")])
        print(f"练习结果 / Practice results: {lab.root}", flush=True)
    if code:
        raise SystemExit(code)
    return dict(paths=[str(lab.root)], url=f"http://127.0.0.1:{a.port}/home/", guide=GUIDE, exit_code=code)


def add_parser(sub):
    p = sub.add_parser("practice", help="practice on three virtual discs using disc-probe's web page")
    p.add_argument("--media", default="dvd-r")
    p.add_argument("--lab", help="new or empty folder, or an existing lab to resume; omitted creates a retained temporary lab")
    p.add_argument("--port", type=port_number, default=8853)
    p.add_argument("--lan", action="store_true")
    p.set_defaults(func=practice)
