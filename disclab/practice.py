"""Disposable virtual practice workspace and the existing web launcher."""
from __future__ import annotations

import os
import tempfile

from .lab import Lab
from .web import port_number, serve


GUIDE = """练习模式 / Practice mode — 不消耗真实光盘 / No physical discs are used up.
这里开的是 disc-probe 自己的网页，光驱是虚拟的 X:，照网页一步步走即可：
This is disc-probe's own page; the drive is the virtual X:. Follow the page step by step:
  检测空白盘 → 生成测量镜像 → 刻录 → 测转速 → 测几何 → 放进图片 → 预览
  → 生成检查盘 → 换盘 → 刻检查盘 → 拍摄光盘 → 生成成品 → 换盘 → 刻录成品

换盘 / Changing discs — 虚拟光驱没有弹出键。网页让你换盘时，在另一个终端运行：
The virtual drive has no eject button. When the page asks for another disc, run:
  python -m disclab swap --lab "{lab}"
  （换上箩里下一张空白盘；把测量盘放回去：加 --disc "<盘号>"）
  (puts the next blank in the tray; --disc "<id>" puts a given disc back)
网页会自己认出新盘。 / The page notices the new disc by itself.

拍照 / Photos — 先渲染检查盘的照片，再点网页上的“从电脑添加照片”，选这些 jpg：
Render photos of the check disc, then press "Add a photo from this computer" on the page and pick them:
  python -m disclab photos --lab "{lab}" --disc "<检查盘号>" -n 3 --out "{photos}1"
读不出沿轨常数是常事，通常要补拍一两轮：每轮换个 --seed 和 --out（…2、…3），新旧照片一起选。
No along-track constant is common; expect one or two retakes: a new --seed and --out each time, and pick old and new photos together.
（网页的手机链接和 disclab upload 只在 --lan 下能用。/ The phone link and `disclab upload` work only with --lan.）
{cd}
进度 / Progress — 网页里做到哪一步、和真值差多少：
How far the page got, and how far from the truth:
  python -m disclab status --lab "{lab}"
  python -m disclab score --lab "{lab}" --progress

Lab 自己的桌面（光盘箩、刻录机、手机）/ The Lab's own desk: python -m disclab desk --lab "{lab}"
引导式控制台 / Guided console: python -m disclab tui --lab "{lab}"
Ctrl+C 退出；结果留着，下次用同一个 --lab 接着练。/ Ctrl+C stops; results stay, and the same --lab resumes.
"""

CD_BURN = """
CD 刻录 / Burning a CD — 网页上给的是真刻录机的 PowerShell 命令，练习时别运行它；改用虚拟光驱：
The page shows a PowerShell command for a real burner; do not run it in practice. Use the virtual drive:
  python -m disclab dp --lab "{lab}" -- burn --drive X: --iso "<网页给的镜像 / the page's ISO>" --media cd --yes-write
"""


def guide(lab, media="dvd-r"):
    """The banner, with this lab's own paths in the commands."""
    root = str(lab.root)
    cd = CD_BURN.format(lab=root) if str(media).startswith("cd") else ""
    return GUIDE.format(lab=root, photos=str(lab.root / "photos"), cd=cd)


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
    if getattr(a, "burn_time", None) is not None:
        from .drive import burn_seconds
        burn_seconds(1, 1.0, "dvd", a.burn_time)          # reject a bad value before the page starts
        os.environ["DISCLAB_BURN_TIME"] = str(a.burn_time)
    lab = prepare(a.lab, a.media)
    # Let the outer API dispatcher report the generated path too.
    a.lab = str(lab.root)
    text = guide(lab, lab.box()["media"])
    print(text, flush=True)
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
    return dict(paths=[str(lab.root)], url=f"http://127.0.0.1:{a.port}/home/", guide=text, exit_code=code)


def add_parser(sub):
    p = sub.add_parser("practice", help="practice on three virtual discs using disc-probe's web page")
    p.add_argument("--media", default="dvd-r")
    p.add_argument("--lab", help="new or empty folder, or an existing lab to resume; omitted creates a retained temporary lab")
    p.add_argument("--port", type=port_number, default=8853)
    p.add_argument("--lan", action="store_true")
    p.add_argument("--burn-time", default=None, metavar="quick|real|SCALE",
                   help="how long a virtual burn takes: quick (about a second), real (the time at the chosen speed), "
                        "or a number scaling the real time, e.g. 0.1 / 虚拟刻录用多久：quick 约一秒，real 按所选速度的真实时间，或按比例缩放")
    p.set_defaults(func=practice)
