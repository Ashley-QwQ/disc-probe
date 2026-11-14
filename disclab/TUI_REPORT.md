# Disc Lab TUI 本机实测报告

2026-11-13，Windows，Python 3.13，disc-probe 0.1.2.1。本次继续工作树已有实现，未重新起步。没有提交、推送、stash、reset 或切换分支；没有修改 `discprobe/`、并行任务保留文件或原有测试文件。

## 本次验收结果

通过标准输入运行 `python -B -m disclab tui --plain --quick`，完成建盒 → 放盘 → 测量 ISO 及虚拟刻录 → timing → geo → 内置帆船图片 ISO → 对照真值评分。首次退出码为 0；重新打开同一实验盒，执行评分并退出，退出码为 0。输出没有 Action failed，也没有 ANSI 转义。

`state.json` 实际包含 `box`、`tray`、`burn`、`timing`、`geo`、`pictures`、`sample_picture`、`scores` 等带时间戳的记录。重新进入后使用同一文件恢复；没有另存 TUI 私有状态。geo 的 u 测量值为 180518.614900600，真值为 180518.406367390，误差为 0.208533210 bit；v 相对误差为 -4.2296615e-05。完整分数见下方转录及 `LAB/scores/tui.json`。

本次短流程中的示例图片只生成 ISO，未刻录到第二张盘；其落点评分是对该目标盘真值的预测。完整菜单中的动作 7 会另生成并虚拟刻录简化照片靶，动作 9 在 L 被接受且图片旁车文件确认 `photo_l.written: true` 后刻录最终图片。不能把短流程解释为已完成照片校准或带 L 图片刻录。

## 磁盘、镜像和范围

本次执行显式把 TMP、TEMP、pytest basetemp 和 pytest cache 指向 D 盘 scratch。新增实验盒、转录、辅助脚本、打包输出及 ISO 均位于 D 盘；Python 禁止写入字节码缓存。渲染使用已有 `wave_xyz.npz`，没有重建波模型缓存；指定的 render-wave-cache 仍留在 D 盘。

一般烧录及接口测试使用 4,096 扇区。geo 评分和 TUI 短流程使用 65,536 扇区（128 MiB）：原有评分器的半径网格从 25 mm 开始，4,096 扇区的 DVD 内圈覆盖不到该网格，不能在保持原评分公式的前提下用于这一检查。示例图片 ISO 为 96,796,672 字节。原有示例测试保持原来的 65,536 扇区；本次未创建任何全盘 ISO。

quick 仅测量内圈；图片通过既有 image 参数限制在实测区间。全盘分数仍包含外推，不能当作全盘精度。完整照片靶需要全盘测量，完整练习可能保留每个数 GB 的 ISO，后续 timing/info 需要这些字节；既有 loop 的 ISO 清理行为保持不变。

checkdisc 多字节纹理靶目前不能渲染，TUI 明确说明使用实验盒自己的 A5/B9 简化双纹理靶。没有修改评分公式、阈值、读取器 verdict 或证据以取得通过。

## 原运行留下的完整照片证据

保留并检查了 `_package_checks/tui-full-vx7b_vy3` 的原始输入、stdout、stderr、实验盒及照片结果。本次没有重跑全盘路径。原输入为建盒后执行菜单 11，再执行 10；原 stdout 记录全盘测量、timing、geo、靶盘虚拟刻录、三张照片及照片读取。组 verdict 为 `unsure`，`offset_mm` 为 `None`；动作 9 的拒绝保留，不能声称带 L 最终图片已经完成。

以下为保留文件中的逐照片结果，没有改变状态：

```json
[
  {
    "id": "IMG_00000",
    "verdict": "unsure",
    "status": "too_few_votes",
    "reason": "Too little readable pattern. Turn the disc and try different lighting."
  },
  {
    "id": "IMG_00001",
    "verdict": "ok",
    "status": "ok",
    "reason": "The photo passed the reader's checks."
  },
  {
    "id": "IMG_00002",
    "verdict": "unsure",
    "status": "too_few_votes",
    "reason": "Too little readable pattern. Turn the disc and try different lighting."
  }
]
```

原 stdout SHA-256：`f8da27c78cac2544872fcea7f7e6bd3499d1c9da9f809c741898608caa8242af`。
原 stderr SHA-256：`c0e94387b57c8363328a0f680d6c5968912c0a37146eea94a2d558a7a8d4aaef`。
照片结果 SHA-256：`52913c27d077a193942548409214d2059bec4a5c59d789b4f20980c580c0e41d`。

## 自动测试

`python -B -m pytest disclab/tests -q`：**53 passed in 86.26s (0:01:26)**。原有 30 个测试全部保留且通过，新增 23 个测试通过。pytest 临时目录和缓存通过运行参数重定向到 D 盘 scratch；最终原始日志为 `SCRATCH/pytest-acceptance.txt`。

此前一次全套复验中，报告转录里的相对 JSON 路径使用 Windows 双反斜杠，被原有可移植性检查识别为机器路径；仅在报告中统一路径分隔符后重新运行全套测试通过。原始转录及其哈希没有改变，也没有修改该测试。

保留原有 30 个测试，增加逐命令 JSON 格式、错误及帮助、版本不兼容、全局选项、状态扩展键保护、小图照片、脚本 TUI/恢复、照片 L 拒绝保护、图片应用 L 的二次检查、示例资源打包、本机 web/practice 启停及默认临时目录测试。脚本 TUI 测试实际以 `--json` 运行，验证子进程日志不污染唯一的 stdout JSON 对象；下方另保留人类可读模式转录。

poses 格式测试使用扫描函数替身，loop photo 格式测试使用循环函数替身；upload 格式测试使用协议回复替身。真实小图渲染及原有上传协议测试继续执行。web/practice 测试真实启动本机服务器，选择非禁用的临时空闲端口，检查 HTTP 200、停止后的单个 JSON 对象及端口释放。所有设备操作都走虚拟光驱；没有真实刻录或外网请求。CPU 密集工作顺序执行，子任务最多使用 3 个工作进程。

## 本次短流程原始转录

原件保存在 D 盘 scratch 的 `tui/acceptance-657hv2wi`，有 `input.txt`、`stdout.txt`、`stderr.txt`、恢复转录及 `manifest.json`。下方只替换机器绝对路径为 LAB、REPO、SCRATCH 标记，并统一路径分隔符为正斜杠；未改动其他输出。原件 SHA-256：

```json
{
  "input.txt": "e956a03611d7d47187ff18b45711baee4d08628bd319227f6a8ffcc3fdb519f2",
  "resume-stderr.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "resume-stdout.txt": "d696b428a87bc82973f30c5e8f9a99ac500b483ae1ce78073ef853e874399a26",
  "stderr.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "stdout.txt": "76286fe7d0055eb5273f37a0c6db047e122a6d67286717ea196aa4a2f009bb40"
}
```

### stdin

```text
1
LAB
dvd-r
3
1
gh70n
2
1
3
4
5
6
10
0
```

### stdout

```text
No physical discs are used up / 不消耗真实光盘。
Measurement, photo target and final picture use separate virtual discs (minimum 3).

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

Action / 操作 [0]: Lab folder / 实验盒目录 [REPO/LAB-tui]: Media / 盘种 [dvd-r]: Disc count / 数量 [3]: Seed / 种子 [1]: Reader profile / 读盘配置 [gh70n]: {
  "media": "dvd-r",
  "batch": 1,
  "mid": "DLABR01",
  "count": 3,
  "discs": [
    "LAB-A 1-01",
    "LAB-A 1-02",
    "LAB-A 1-03"
  ],
  "note": "What is printed on the box. The true parameters are in answers.json, which disc-probe never sees."
}

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

Lab: LAB
Action / 操作 [0]: 1 LAB-A 1-01
2 LAB-A 1-02
3 LAB-A 1-03
Disc number / 盘号 [1]: {"X:": {"reader": "gh70n", "tray": "LAB-A 1-01", "open": false}}

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

Lab: LAB
Action / 操作 [0]: $ discprobe random --output LAB/iso/measurement-LAB-A_1-01.iso --sectors 65536
Preparing the design and image data; this may take a few seconds...
Writing LAB/iso/measurement-LAB-A_1-01.iso: 65536 sectors of seeded random data
Random-mirror length: 65536 sectors; random --sectors controls this file, not the geometric total or blank writable capacity.
   12.5 %
   25.0 %
   50.0 %
   62.5 %
   87.5 %
  100.0 %
Burn it, then run `geo` on it.
(Windows: right-click the .iso, Burn disc image).
In the burn window, check the burner is X:: it can point at another drive.
$ discprobe burn --drive X: --iso LAB/iso/measurement-LAB-A_1-01.iso --yes-write
Requested write speed: 8x (default). Burn log: LAB/iso/measurement-LAB-A_1-01.iso.burn.jsonl
The tray closes for writing. Burning cannot be undone.
Drive/utility reports write speed: 8x.
disclab: burn map of LAB-A 1-01: BLANK 95.5%, MIXED 4.5%, B6 0.0%
Write completed in 2.0s; drive/utility reports: 8.0x.
Reading back up to 96 evenly spaced 16-sector blocks; drive retries may take time...
Read-back sample: 96 blocks ok / 0 differing / 0 unreadable; 0 untested (completed). This is a sample, not a full-disc check.

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

Lab: LAB
Action / 操作 [0]: $ discprobe timing --drive X: --media dvd --out LAB/results --reps 4 --period-reads 4 --targets 0.2,0.7
Disc: DVD-R Sequential, last LBA 65535, reading with read12
Cache: plain p50 88.0 us, fua p50 41423.6 us -> strategy fua
Spindle steady: T = 20.719 ms (2895.8 rpm)
Zone 0.05 (LBA 3264): no period found
Zone 0.50 (LBA 32752): no period found
Zone 0.95 (LBA 62256): no period found
Rotation: unknown (zones [0.05, 0.5, 0.95] have no clear period; the speed may be changing, try a fixed --speed)
Rotation is unknown, not CAV, so the phase test would not give disc angles; skipping it. Try another --speed, or pass --force to run it anyway.

Raw events and summary: LAB/results/timing-X-20261113-194648
Stopped: rotation is unknown, not CAV
Diagnostics: LAB/results/timing-X-20261113-194648/diagnostics.zip
Next: Reuse this disc. Try one untried read speed from timing history, then another available drive. For CLV CD, use DiscImageStudio calibration; experimental CD CLV cannot supply sector angles.

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

Lab: LAB
Action / 操作 [0]: {
  "disc": "LAB-A 1-01",
  "target": "LAB-A 1-01",
  "geo": "LAB/results/geo-X-20261113-194649",
  "u": 180518.61490059955,
  "v": 5.590971016282156,
  "true_u": 180518.40636738966,
  "true_v": 5.591207505433649,
  "du_bits": 0.2085332098940853,
  "dv_rel": -4.229661504495663e-05,
  "path_L_mm": 0.19,
  "geo_reported": {
    "residual_rms_deg": 0.09959192521788014,
    "angle_sigma_deg": 403.29756412743114,
    "chi2_per_dof": 0.49592757838468854,
    "status": "target_reached",
    "correction": null
  },
  "vs_timing_measured_span": {
    "c_deg": 8.30382658180875,
    "L_mm": -3.876962480080739,
    "rms_deg": 0.04398684899786063,
    "pp_deg": 0.08797369799572126,
    "residual_after_L_rms_deg": 3.1805546814635168e-15,
    "residual_after_L_pp_deg": 0.0
  },
  "vs_timing_full": {
    "c_deg": 310.0571406488503,
    "L_mm": -160.59908662628877,
    "rms_deg": 56.991282901724595,
    "pp_deg": 186.7394078912822,
    "residual_after_L_rms_deg": 18.598514859600083,
    "residual_after_L_pp_deg": 64.77366932829051
  },
  "placement_on_target": {
    "c_deg": 310.05714057270296,
    "L_mm": -160.40908654796604,
    "rms_deg": 56.931042552050364,
    "pp_deg": 186.51169378245555,
    "residual_after_L_rms_deg": 18.598514864233227,
    "residual_after_L_pp_deg": 64.77366934398093
  }
}

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

Lab: LAB
Action / 操作 [0]: $ discprobe image --geo LAB/results/geo-X-20261113-194649/summary.json --picture REPO/disclab/data/sample.pgm --output LAB/iso/sample.iso --media dvd --no-photo-l --r-max 24.63640941482473 --random-below-mm 24.402210647681777
Preparing the design and image data; this may take a few seconds...
Photo L not applied: opted_out; the photo constant remains unknown.
Random data up to 24.4022 mm (LBA 13424); the picture starts there.
picture sample.pgm, 20 um cells, geometry u 180518.615, v 5.5909710 from LAB/results/geo-X-20261113-194649/summary.json; 47264 sectors (0.10 GB), dark A5, light B9
    4.3 %
   21.7 %
   43.3 %
   60.7 %
   82.3 %
  100.0 %
Verified: sampled sectors match the design
Spec: LAB/iso/sample.image.json
Preview (data-side view): LAB/iso/sample.preview.png

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

Lab: LAB
Action / 操作 [0]: Measured / truth / error — 测量值 / 真值 / 误差
{
  "geo": {
    "disc": "LAB-A 1-01",
    "target": "LAB-A 1-01",
    "geo": "LAB/results/geo-X-20261113-194649",
    "u": 180518.61490059955,
    "v": 5.590971016282156,
    "true_u": 180518.40636738966,
    "true_v": 5.591207505433649,
    "du_bits": 0.2085332098940853,
    "dv_rel": -4.229661504495663e-05,
    "path_L_mm": 0.19,
    "geo_reported": {
      "residual_rms_deg": 0.09959192521788014,
      "angle_sigma_deg": 403.29756412743114,
      "chi2_per_dof": 0.49592757838468854,
      "status": "target_reached",
      "correction": null
    },
    "vs_timing_measured_span": {
      "c_deg": 8.30382658180875,
      "L_mm": -3.876962480080739,
      "rms_deg": 0.04398684899786063,
      "pp_deg": 0.08797369799572126,
      "residual_after_L_rms_deg": 3.1805546814635168e-15,
      "residual_after_L_pp_deg": 0.0
    },
    "vs_timing_full": {
      "c_deg": 310.0571406488503,
      "L_mm": -160.59908662628877,
      "rms_deg": 56.991282901724595,
      "pp_deg": 186.7394078912822,
      "residual_after_L_rms_deg": 18.598514859600083,
      "residual_after_L_pp_deg": 64.77366932829051
    },
    "placement_on_target": {
      "c_deg": 310.05714057270296,
      "L_mm": -160.40908654796604,
      "rms_deg": 56.931042552050364,
      "pp_deg": 186.51169378245555,
      "residual_after_L_rms_deg": 18.598514864233227,
      "residual_after_L_pp_deg": 64.77366934398093
    }
  },
  "photos": [],
  "pictures": {
    "sample_picture": {
      "target": "LAB-A 1-02",
      "c_deg": 310.23238982511447,
      "L_mm": -160.49047342583154,
      "rms_deg": 56.95815277353521,
      "pp_deg": 186.60798959070982,
      "residual_after_L_rms_deg": 18.60251736105277,
      "residual_after_L_pp_deg": 64.78761903403276,
      "photo_l": {
        "written": false,
        "L_mm": null,
        "reason": "opted_out"
      }
    }
  }
}

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

Lab: LAB
Action / 操作 [0]: Results / 结果: LAB
```

### stderr

```text
(empty)
```

### 恢复后的 stdin

```text
10
0
```

### 恢复后的 stdout

```text
No physical discs are used up / 不消耗真实光盘。
Measurement, photo target and final picture use separate virtual discs (minimum 3).

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

Lab: LAB
Action / 操作 [0]: Measured / truth / error — 测量值 / 真值 / 误差
{
  "geo": {
    "disc": "LAB-A 1-01",
    "target": "LAB-A 1-01",
    "geo": "LAB/results/geo-X-20261113-194649",
    "u": 180518.61490059955,
    "v": 5.590971016282156,
    "true_u": 180518.40636738966,
    "true_v": 5.591207505433649,
    "du_bits": 0.2085332098940853,
    "dv_rel": -4.229661504495663e-05,
    "path_L_mm": 0.19,
    "geo_reported": {
      "residual_rms_deg": 0.09959192521788014,
      "angle_sigma_deg": 403.29756412743114,
      "chi2_per_dof": 0.49592757838468854,
      "status": "target_reached",
      "correction": null
    },
    "vs_timing_measured_span": {
      "c_deg": 8.30382658180875,
      "L_mm": -3.876962480080739,
      "rms_deg": 0.04398684899786063,
      "pp_deg": 0.08797369799572126,
      "residual_after_L_rms_deg": 3.1805546814635168e-15,
      "residual_after_L_pp_deg": 0.0
    },
    "vs_timing_full": {
      "c_deg": 310.0571406488503,
      "L_mm": -160.59908662628877,
      "rms_deg": 56.991282901724595,
      "pp_deg": 186.7394078912822,
      "residual_after_L_rms_deg": 18.598514859600083,
      "residual_after_L_pp_deg": 64.77366932829051
    },
    "placement_on_target": {
      "c_deg": 310.05714057270296,
      "L_mm": -160.40908654796604,
      "rms_deg": 56.931042552050364,
      "pp_deg": 186.51169378245555,
      "residual_after_L_rms_deg": 18.598514864233227,
      "residual_after_L_pp_deg": 64.77366934398093
    }
  },
  "photos": [],
  "pictures": {
    "sample_picture": {
      "target": "LAB-A 1-02",
      "c_deg": 310.23238982511447,
      "L_mm": -160.49047342583154,
      "rms_deg": 56.95815277353521,
      "pp_deg": 186.60798959070982,
      "residual_after_L_rms_deg": 18.60251736105277,
      "residual_after_L_pp_deg": 64.78761903403276,
      "photo_l": {
        "written": false,
        "L_mm": null,
        "reason": "opted_out"
      }
    }
  }
}

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

Lab: LAB
Action / 操作 [0]: Results / 结果: LAB
```

### 恢复后的 stderr

```text
(empty)
```
