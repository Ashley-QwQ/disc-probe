"""Disposable virtual practice workspace and the existing web launcher."""
from __future__ import annotations

import tempfile

from .lab import Lab
from .web import port_number, serve


GUIDE = """练习模式 / Practice mode — 不消耗真实光盘 / No physical discs are used up.
1. 查看虚拟光驱和盘片 / Inspect the virtual drive and inserted disc.
2. 生成测量 ISO、虚拟刻录，运行 timing 和 geo / Generate, virtually burn, then timing and geo.
3. 用图片生成 ISO；换一张虚拟盘刻录 / Make a picture ISO and burn another virtual disc.
4. 可用 disclab tui 生成实验盒的双纹理靶照片、读取 L、比较分数。
   Use disclab tui for the lab's simplified two-texture photos, photo L and truth scores.
   checkdisc 的多字节纹理目前不能拍照渲染 / The checkdisc target cannot be rendered yet.
Ctrl+C 退出；保留结果供检查 / Stop with Ctrl+C; results remain for inspection.
"""


def prepare(root=None, media="dvd-r"):
    lab = Lab(root or tempfile.mkdtemp(prefix="disc-lab-practice-"))
    if lab.root.exists() and any(lab.root.iterdir()):
        raise ValueError("practice needs a new or empty lab folder; existing results are preserved")
    from .jsonout import run
    result = run(["box", "--lab", lab.root, "--media", media, "--count", "3", "--seed", "1"])
    if result["status"] != "ok":
        raise RuntimeError(result["errors"])
    run(["tray", "--lab", lab.root, "--disc", lab.box()["discs"][0]])
    return lab


def practice(a):
    lab = prepare(a.lab, a.media)
    # Let the outer API dispatcher report the generated path too.
    a.lab = str(lab.root)
    print(GUIDE, flush=True)
    print(f"Lab: {lab.root}", flush=True)
    family = "cd" if a.media.startswith("cd") else "bd" if a.media.startswith("bd") else "dvd"
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
    p.add_argument("--lab", help="new or empty folder; omitted creates a retained temporary lab")
    p.add_argument("--port", type=port_number, default=8853)
    p.add_argument("--lan", action="store_true")
    p.set_defaults(func=practice)
