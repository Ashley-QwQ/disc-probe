"""Three US Letter pages (print at 100 %, "actual size") for the showcase 1x pose.

Sheet 1, height ruler: a strip folded into a triangular prism that stands on the table; the mark is the
main lens height above the TABLE: calibrated disc height + 1.2 mm disc + 0.1 mm sheet.
Sheet 2, placement: lies under the disc. Disc outline with a 12 o'clock arrow, the aim cross where the
main lens must be straight above (28.45 mm toward 12 o'clock), and the dot under the flash (76.39 mm).
Original lines are frozen from data/focal/legacy.json; updated heights come from discprobe.focal.
"""
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "D:/dp-dev/tmp/focal/mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, FancyArrow, Polygon, Rectangle

import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from discprobe import focal as F

LEGACY = json.loads((ROOT / "data/focal/legacy.json").read_text(encoding="utf-8"))
pose, FR = LEGACY["chosen"], LEGACY["framing"]
LENS_Y, HEIGHT, FLASH_Y = F.LENS_Y_MM, F.DESIGN_Z_MM, F.FLASH_Y_MM
DISC_T, SHEET_T = F.DISC_MM, F.SHEET_MM
MARK = F.TABLE_HEIGHT_MM
W, H = 215.9, 279.4
_OFF = (-43.66, 19.79)
_rot = math.atan2(FLASH_Y-LENS_Y,0.0)-math.atan2(_OFF[1],_OFF[0])
UP = (-math.sin(_rot),math.cos(_rot))
RIGHT = (math.cos(_rot),math.sin(_rot))
EX, EY = UP, RIGHT
# Frozen placement lines: neither the photo page nor the video page changes.
F_PX = F.LEGACY_PHOTO_FOCAL_PX
GX = FR["frame_native_px"][0]/6/F_PX*F.LEGACY_DISC_HEIGHT_MM
GY = FR["frame_native_px"][1]/6/F_PX*F.LEGACY_DISC_HEIGHT_MM
VIDEO_SHARE = F.VIDEO_SHARE
F_VIDEO = FR["frame_native_px"][0]/F_PX*VIDEO_SHARE
GXV = F_VIDEO/6*F.LEGACY_TABLE_HEIGHT_MM
GYV = F_VIDEO*9/16/6*F.LEGACY_TABLE_HEIGHT_MM


def grid_lines(gx=None, gy=None):
    """The four phone-grid lines on the table, as (point, direction, kind) in disc mm."""
    gx = GX if gx is None else gx
    gy = GY if gy is None else gy
    out = []
    for s_ in (-1, 1):
        out.append(((s_ * gx * EX[0], LENS_Y + s_ * gx * EX[1]), EY, "横线"))
        out.append(((s_ * gy * EY[0], LENS_Y + s_ * gy * EY[1]), EX, "竖线"))
    return out
                                        # US Letter, mm

for name in ("Microsoft YaHei", "SimHei", "DengXian"):
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break


def page():
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_aspect("equal"); ax.axis("off")
    return fig, ax


def check_bar(ax, x, y):
    ax.add_patch(Rectangle((x, y), 100, 3, fc="black"))
    for i in range(11):
        ax.plot([x + 10 * i] * 2, [y + 3, y + 6 if i % 5 else y + 8], "k", lw=0.6)
    ax.text(x + 50, y + 10, "打印校验：这条应正好 100 mm（打印选「实际大小 / 100%」）", ha="center", fontsize=7)


def ruler():
    fig, ax = page()
    x0, face, flap, tab = 22.0, 24.0, 10.0, 6.0
    y0 = 32.0                                              # table level: the prism's bottom edge
    top = y0 + 230.0
    right = x0 + 3 * face + flap
    solid, fold = dict(color="k", lw=0.6), dict(color="k", lw=0.5, ls=(0, (4, 2)))
    # outline (cut): top edge, outer left and right edges, bottom edges of faces 2, 3 and the side flap
    ax.plot([x0, right], [top, top], **solid)
    ax.plot([x0, x0], [y0, top], **solid)
    ax.plot([right, right], [y0, top], **solid)
    ax.plot([x0 + face, right], [y0, y0], **solid)
    # folds: between the faces and the side flap, and the base along face 1's bottom edge
    for i in (1, 2, 3):
        ax.plot([x0 + i * face] * 2, [y0, top], **fold)
    ax.plot([x0, x0 + face], [y0, y0], **fold)
    ax.text(x0 + 3 * face + flap / 2, (y0 + top) / 2, "粘贴边", rotation=90, ha="center", va="center", fontsize=7)
    # base: an equilateral triangle under face 1, with a glue tab on each of its other two sides
    h = face * math.sqrt(3) / 2
    A, B, C = (x0, y0), (x0 + face, y0), (x0 + face / 2, y0 - h)
    for P, Q in ((A, C), (C, B)):
        ax.plot([P[0], Q[0]], [P[1], Q[1]], **fold)
        ux, uy = Q[0] - P[0], Q[1] - P[1]
        n = math.hypot(ux, uy); ux, uy = ux / n, uy / n
        ox, oy = -uy, ux                                   # outward from the triangle for P->Q going round it
        if (ox * (A[0] + B[0] + C[0] - 3 * P[0]) + oy * (A[1] + B[1] + C[1] - 3 * P[1])) > 0:
            ox, oy = -ox, -oy
        inset = 2.5
        pts = [P, (P[0] + ox * tab + ux * inset, P[1] + oy * tab + uy * inset),
               (Q[0] + ox * tab - ux * inset, Q[1] + oy * tab - uy * inset), Q]
        ax.add_patch(Polygon(pts, closed=False, fill=False, **solid))
    ax.text(C[0], y0 - h / 2 + 1, "底", ha="center", va="center", fontsize=7)
    # one scale (face 1), from the table up; the mark on all three faces so it shows from any side
    for mm in range(0, 231):
        L = 7 if mm % 10 == 0 else 4.5 if mm % 5 == 0 else 2.5
        ax.plot([x0, x0 + L], [y0 + mm] * 2, "k", lw=0.35)
        if mm % 10 == 0 and abs(mm - MARK) > 4:
            ax.text(x0 + 8, y0 + mm, f"{mm}", va="center", fontsize=5.5)
    for f in range(3):
        xl = x0 + f * face
        ax.add_patch(Rectangle((xl, y0 + MARK - 0.3), face, 0.6, fc="#e0007a"))
        ax.text(xl + (8 if f == 0 else face / 2), y0 + MARK + 1.6, f"{MARK:.1f}", ha="left" if f == 0 else "center",
                va="bottom", fontsize=6.5, color="#e0007a", weight="bold")
    tx = right + 10
    lines = ["高度尺（主摄 1× 机位，约 22 cm）", "",
             "1. 沿实线剪下；虚线是折线。",
             "2. 三个面折成三棱柱，粘贴边塞到第一面背后，从外面沿接缝",
             "   用透明胶贴上中下三段（别贴在粉色标线上）。",
             "3. 底下的三角形向里折成底面，用透明胶从外面把它的两条边",
             "   贴到侧面下沿（小粘边可剪掉）。底面贴桌，立得稳。",
             f"4. 手机平放、屏幕朝上，主摄镜头玻璃的高度",
             f"   对齐粉色标线 {MARK:.1f} mm（从桌面量）。",
             f"   = 盘面以上 {HEIGHT:.1f} + 盘厚 {DISC_T} + 纸 {SHEET_T}",
             "",
             "手机要和桌面平行（倾斜 0°）。可用水平仪 App",
             "或「测距仪」里的水平功能检查。",
             "",
             "提醒：这个近距机位对位置非常敏感，",
             "镜头偏 1 mm 颜色就会变；请用支架固定，",
             "别手持。先用这把尺子定高度，再微调。"]
    for i, t in enumerate(lines):
        ax.text(tx, top - 6 - i * 6.2, t, fontsize=8 if i else 10, weight="bold" if i == 0 else None, va="top")
    check_bar(ax, tx, 22)
    return fig


def placement(video=False):
    fig, ax = page()
    cx, cy = W / 2, 120.0                                   # disc centre on the page (y up)
    ax.add_patch(Circle((cx, cy), 60, fill=False, lw=1.0))
    ax.add_patch(Circle((cx, cy), 7.5, fill=False, lw=0.6))
    ax.add_patch(Circle((cx, cy), 60.8, fill=False, lw=0.3, ls=":"))
    ax.plot([cx - 3, cx + 3], [cy, cy], "k", lw=0.4); ax.plot([cx, cx], [cy - 3, cy + 3], "k", lw=0.4)
    # 12 o'clock arrow, just outside the rim, pointing at the disc
    ax.add_patch(FancyArrow(cx, cy + 71, 0, -8.5, width=2.2, head_width=7, head_length=4.5, fc="black", ec="black"))
    ax.text(cx + 6, cy + 67, "盘上的 12 点箭头对准这里", va="center", fontsize=7.5, bbox=dict(fc="white", ec="none", pad=0.6))
    # aim cross: main lens straight above it; long arms so they show past the disc edge
    ay = cy + LENS_Y
    col = "#e0007a"
    ax.plot([cx - 95, cx - 62], [ay, ay], color=col, lw=0.9); ax.plot([cx + 62, cx + 95], [ay, ay], color=col, lw=0.9)
    ax.plot([cx - 6, cx + 6], [ay, ay], color=col, lw=0.9); ax.plot([cx, cx], [ay - 6, ay + 6], color=col, lw=0.9)
    ax.plot([cx, cx], [cy + 79, cy + 96], color=col, lw=0.9)          # vertical arm, past the arrow
    ax.text(cx + 97, ay, "瞄准线", va="center", fontsize=7.5, color=col)
    ax.text(cx - 97, ay, "瞄准线", va="center", ha="right", fontsize=7.5, color=col)
    ax.text(cx + 3, cy + 96, "瞄准线", va="top", fontsize=7.5, color=col)
    # flash dot (outside the disc)
    fy = cy + FLASH_Y
    ax.add_patch(Circle((cx, fy), 2.0, fc="#ff9a00", ec="black", lw=0.4))
    ax.text(cx + 4, fy + 0.5, "闪光灯正下方", va="center", ha="left", fontsize=7.5, bbox=dict(fc="white", ec="none", pad=0.6))
    # phone-grid lines (portrait 3x3 grid): where each of the four lines must lie on the table
    gcol = "#0088cc"
    gx, gy = (GXV, GYV) if video else (GX, GY)
    for (px, py), (dx, dy), kind in grid_lines(gx, gy):
        ax.plot([cx + px - 400 * dx, cx + px + 400 * dx], [cy + py - 400 * dy, cy + py + 400 * dy],
                color=gcol, lw=0.7, ls=(0, (6, 3)))
        ang = math.degrees(math.atan2(dy, dx)) % 180
        ang = ang - 180 if ang > 90 else ang
        for sgn in (-1, 1):                                   # a label just outside the disc on each side
            for t in range(0, 300, 2):
                x_, y_ = px + sgn * t * dx, py + sgn * t * dy
                busy = (-2 < x_ < 52 and 60 < y_ < 74) or (-4 < x_ < 30 and FLASH_Y - 5 < y_ < FLASH_Y + 5)   # 12 o'clock / flash text
                if x_ * x_ + y_ * y_ > 68 ** 2 and not busy:
                    if 10 < cx + x_ < W - 10 and 60 < cy + y_ < H - 40:
                        ax.text(cx + x_, cy + y_, "九宫格" + kind, fontsize=6.5, color=gcol, ha="center", va="center",
                                rotation=ang, bbox=dict(fc="white", ec="none", pad=0.6))
                    break
    # which way the phone's top points (portrait, screen up)
    bx, by = cx + 74 * UP[0], cy + LENS_Y + 74 * UP[1]
    ax.add_patch(FancyArrow(bx, by, 16 * UP[0], 16 * UP[1], width=1.6, head_width=5, head_length=4,
                            fc="#0088cc", ec="#0088cc"))
    ax.text(bx + 23 * UP[0], by + 23 * UP[1] + 4, "手机顶端朝这边", fontsize=7.5, color="#0088cc", ha="center",
            bbox=dict(fc="white", ec="none", pad=0.6))
    ax.set_xlim(0, W); ax.set_ylim(0, H)
    tx, ty = 14, 50
    lines = [("放盘指示器·录像（主摄 1×，约 21 cm，竖拍，16:9 视频）" if video else "放盘指示器（主摄 1× 机位，约 21 cm，竖拍，4:3 照片）"), "",
             "1. 这张纸平铺在桌上，盘的数据面朝上放进空心圆，中心孔对准小圆。",
             "2. 盘上画好的 12 点箭头对准上方的黑箭头。",
             f"3. 主摄镜头在十字正上方：盘心向 12 点偏 {LENS_Y:.2f} mm；十字被盘盖住，",
             "   对准露在盘外的三段粉色瞄准线（左、右、上）。九宫格中心点就落在十字上。",
             f"4. 闪光灯在橙点正上方（盘心向 12 点偏 {FLASH_Y:.1f} mm）。开闪光。手机竖拿、屏幕朝上，顶端朝右上（见蓝箭头）。",
             ("5. 打开相机「网格」，录像模式（标准防抖）：九宫格两条横线、两条竖线压在蓝色虚线上，" if video else
              "5. 打开相机「网格」，拍 4:3 照片：九宫格两条横线、两条竖线分别压在蓝色虚线上，"),
             f"   高度、偏移、转角、倾斜就都对了（横线间距 {2*gx:.1f} mm、竖线间距 {2*gy:.1f} mm）。"]
    for i, t in enumerate(lines):
        ax.text(tx, ty - i * 4.8, t, fontsize=8 if i else 10, weight="bold" if i == 0 else None, va="top")
    check_bar(ax, (W - 100) / 2, H - 30)
    return fig


def main():
    global MARK, HEIGHT
    ap = argparse.ArgumentParser(description="Frozen placement pages and updated focal height ruler")
    ap.add_argument('--out', type=Path, default=Path('D:/dp-dev/tmp/focal'))
    ap.add_argument('--legacy', action='store_true', help='old height, same placement pages')
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if args.legacy:
        MARK, HEIGHT=F.LEGACY_TABLE_HEIGHT_MM,F.LEGACY_DISC_HEIGHT_MM
    suffix='old' if args.legacy else 'new'
    out=args.out/f'dp_rulers_1x_{suffix}_letter.pdf'
    with PdfPages(out) as pdf:
        for figure,name in ((ruler(),'height'),(placement(),'placement'),(placement(video=True),'placement_video')):
            if args.legacy and name=='height':
                for text in figure.axes[0].texts:
                    text.set_text(text.get_text().replace('约 22 cm','约 21 cm'))
            pdf.savefig(figure)
            figure.savefig(args.out/f'ruler_{name}_{suffix}.png',dpi=110)
            plt.close(figure)
    print(out,f'mark {MARK:.4f} mm, lens y {LENS_Y:.2f}, flash y {FLASH_Y:.8f}')


if __name__ == '__main__':
    main()
