# 切页后的浏览器内存

基点 `4f042ca`。候选分支 `dev/page-teardown`。测量沿用 PM 卡的脚本、虚拟 DVD 和 1600 × 1600 RGBA 测试图。使用独立有界面的 Edge 158.0.4370.33、独立 Disc Lab 工作区和独立 `LOCALAPPDATA`。该主机的 GPU 为 RTX 2060，ANGLE 使用 Direct3D 11。视口为 1366 × 768、DPR 为 1，两组都用原图。每个场景至少静置 30 秒才取样。几何暂停在进度约 48% 时，取样完成后再恢复。各场景由同一标签页依次打开。

Private Bytes 和 Working Set 来自 Windows 进程计数器。renderer 和 GPU 栏均依次列 Private Bytes / Working Set。内存单位为 MiB。Working Set 逐进程相加，可能重复计算共享页。GPU 栏是 GPU 进程的 Windows 内存。专用显存未测。JS 堆是 CDP `Runtime.getHeapUsage.usedSize`，取样前未强制 GC。DOM 节点来自 CDP `Memory.getDOMCounters`，包含浏览器尚未回收的分离节点。

| Theme | Scene | Rev | PB / WS | renderer | GPU | JS heap | DOM nodes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| light | blank | before | 237.5 / 414.7 | 37.3 / 80.6 | 116.0 / 74.9 | 0.40 | 4 |
| light | blank | after | 241.9 / 415.7 | 40.9 / 84.9 | 117.1 / 74.9 | 0.40 | 4 |
| light | lobby | before | 324.1 / 563.9 | 64.5 / 186.3 | 167.6 / 87.4 | 1.73 | 1162 |
| light | lobby | after | 310.2 / 508.0 | 66.2 / 135.1 | 152.8 / 87.7 | 1.59 | 900 |
| light | library | before | 420.4 / 585.2 | 82.8 / 208.7 | 246.6 / 87.0 | 1.84 | 2419 |
| light | library | after | 435.2 / 532.4 | 82.3 / 155.9 | 262.5 / 91.6 | 2.23 | 3121 |
| light | geometry | before | 461.5 / 694.3 | 92.3 / 297.1 | 285.7 / 127.1 | 3.22 | 2825 |
| light | geometry | after | 464.3 / 664.9 | 89.2 / 273.4 | 292.5 / 126.5 | 3.24 | 1417 |
| light | editor | before | 518.9 / 653.3 | 151.0 / 276.4 | 283.6 / 101.1 | 17.68 | 3536 |
| light | editor | after | 489.0 / 654.0 | 143.0 / 255.9 | 263.3 / 132.3 | 3.60 | 1768 |
| light | return | before | 498.2 / 615.8 | 146.4 / 229.3 | 267.8 / 110.6 | 17.72 | 3555 |
| light | return | after | 473.8 / 582.2 | 125.7 / 208.2 | 265.5 / 108.0 | 3.65 | 1747 |
| light | return − lobby | before | +174.0 / +51.9 | | | | |
| light | return − lobby | after | +163.5 / +74.1 | | | | |
| dark | blank | before | 242.9 / 418.3 | 38.0 / 81.7 | 120.5 / 75.5 | 0.40 | 4 |
| dark | blank | after | 236.1 / 410.4 | 37.8 / 81.2 | 115.7 / 74.7 | 0.40 | 4 |
| dark | lobby | before | 307.5 / 566.9 | 66.2 / 187.7 | 150.0 / 88.8 | 1.73 | 1164 |
| dark | lobby | after | 308.9 / 504.2 | 64.3 / 131.5 | 153.8 / 88.0 | 1.61 | 904 |
| dark | library | before | 420.6 / 591.6 | 83.8 / 212.3 | 245.9 / 88.8 | 1.84 | 2419 |
| dark | library | after | 434.9 / 529.1 | 80.3 / 151.1 | 264.8 / 94.0 | 1.69 | 2197 |
| dark | geometry | before | 532.2 / 601.4 | 93.2 / 213.4 | 355.8 / 116.8 | 3.38 | 2994 |
| dark | geometry | after | 421.1 / 651.4 | 84.5 / 260.0 | 254.4 / 126.8 | 3.23 | 1412 |
| dark | editor | before | 729.2 / 674.6 | 130.1 / 265.8 | 515.8 / 136.7 | 3.75 | 3536 |
| dark | editor | after | 679.0 / 634.0 | 128.2 / 235.1 | 468.4 / 133.5 | 3.60 | 1768 |
| dark | return | before | 490.6 / 615.8 | 147.8 / 232.4 | 259.8 / 111.4 | 17.68 | 3553 |
| dark | return | after | 455.5 / 580.5 | 123.1 / 204.9 | 249.8 / 108.1 | 3.64 | 1745 |
| dark | return − lobby | before | +183.2 / +48.9 | | | | |
| dark | return − lobby | after | +146.6 / +76.3 | | | | |

`light` 为纸色，`dark` 为夜色。`return − lobby` 比较同一实例的回大厅与首次大厅。

- 回大厅的 Private Bytes 增量，纸色从 +174.0 降到 +163.5 MiB，夜色从 +183.2 降到 +146.6 MiB。Working Set 增量分别从 +51.9 增到 +74.1 MiB，从 +48.9 增到 +76.3 MiB。首次大厅的 Working Set 下降较多，回大厅的绝对 Working Set 两种主题分别下降 33.6 和 35.3 MiB。
- 首次大厅总占用，纸色 324.1 / 563.9 → 310.2 / 508.0 MiB，夜色 307.5 / 566.9 → 308.9 / 504.2 MiB。几何约半程，纸色 461.5 / 694.3 → 464.3 / 664.9 MiB，夜色 532.2 / 601.4 → 421.1 / 651.4 MiB。每个组合只有一次最终样本，GPU 进程占用有波动。
- 回大厅的 JS 堆，纸色 17.72 → 3.65 MiB，夜色 17.68 → 3.64 MiB。DOM 节点分别从 3,555 降至 1,747，从 3,553 降至 1,745。

## 场景和状态归属

| 场景 | 离开时的处理 | 返回时的状态来源 |
| --- | --- | --- |
| 大厅 | 清图片源，停止问候更新和漂移帧。保留热点与过场几何。 | 当前主题的原图，最近草稿、光驱与任务状态。 |
| 盘库 | 回大厅或俯视标定台接管画面时，清架子 SVG、光驱图层与待执行的预载。保留参与窄屏滚动范围计算的光驱外框。 | 现有批次、选中位置和 SVG 装配逻辑。刻录和标定的降级画面还可使用光驱。 |
| 标定 | 移除俯视台、装盘层和标定内容。清零两套画布，销毁数字翻页和绘图帧。 | 活动作业、几何测点、结果和返回回调由原流程保存。 |
| 编辑器 | 退出淡出后移除工作区，取消观察和渲染，关闭灯下、彩色和精确格子 worker，释放工作画布、渲染图层副本和序列化缓存。 | 原草稿、源文件、像素、选区和撤销记录留在现有设计对象。导航 IndexedDB 存同一项目格式的 Blob，兼容旧字符串。 |
| 新作品 | 收表或离开后卸载表单，清信封图、拉拽帧和提示计时器。 | 保留表单文字、文件和原流程数据。标定及盘库返回继续使用同一份表单。 |
| 预览 | 退出后停止模拟和灯下渲染，销毁环控件、观察器和画布。 | 预览上下文和正在生成的文件留给原有作业。 |
| 往期作品 | 清背景图源、作品卡、缩略图引用、通知计时器和相机动画帧。 | 作品库及未保存作品重新生成列表，排序和筛选原有行为继续使用。 |
| 传真和预设 | 传真退出时释放原图和纸张内容。导入导出退出时清桌面图源，保留表单数据。 | 传真本地设置、预设输入及导入状态。 |
| 刻录和结果 | 切页时释放剖视图及图片。结果页关闭时清内容并注销预览 URL。 | 进度和日志由当前任务继续持有，结果页按记录重新读取。 |
| 终端 | 作为大厅上的浮窗保留已有命令和可回看的输出。 | 已打开的终端会话继续持有命令、历史和进度。 |

## 大图请求时机

- `newplan/envelope_back_{dark,paper}.webp` 与 `newplan/envelope_front_{dark,paper}.webp` 在新作品表单可见且启用动效时预热当前主题。切主题时换成当前主题那组。收表起动前检查解码，等待时沿用表单画面。收表后退出时释放图像引用。标定返回需要重新收放时再准备。
- `caltop/anim/final_{dark,paper}.webp` 只在需要合成帧的 `slide()` 中请求当前主题，并在完成后清掉源。日常装盘 `play()` 使用动画分层，等首次动画的图层可用再盖住现有画面。装盘结束后移去只给动态图层用的图片源，保留当前标定桌面所需图层。
- PM 清单中其余未见的较大资源包括 `presetio/desk` 桌面图、`pastworks/tumble_*`、新作品顶视图与纸面、装盘分层。预设桌面到打开导入导出时才配图，往期作品只在进场时配图，新作品主体在入口悬停或实际打开时准备。`row-*.svg` 是用来构建盘库结构的 SVG，进盘库或使用对应光驱场景时读取。网页图标继续随页面使用。
- 两种主题的修前取样都在第一次大厅累计收到 2 张信封图、12 张预设桌面图、10 张档案飞落图。在标定中又收到 1 张装盘合成帧。修后这四组图片在大厅、标定几何和回大厅样本里的累计请求数均为 0。

## 像素和状态验证

截图放在 `D:/dp-dev/tmp/pageteardown/shots/`。分两种主题及 1366 × 768、390 × 844 两种尺寸。普通截图固定表单测试名和日期，比较每个 RGB 像素。录制期间保留原动画时长及曲线。几何截取真实虚拟任务，当前测点、相位和剩余时间随采样进度变化。

- 两种转场各取 10 张连续截图，共 160 张。装盘序列有 5–7 张不同的帧，信封各组 10 张均不同。抽看桌面两主题的序列，未见空白帧。缩览拼图为 `shots/transition-contact.png`。
- 四个候选组合均在编辑器导入测试图并画矩形，随后回大厅，从最近作品重开。脚本比较离开前后的 `.discdesign` 序列化内容、未保存标记和两张图层缩略图的 PNG。390 宽回大厅的文档滚动宽度在修前、修后均为 488 px。
- 硬件栅格的 48 对截图中，20 对逐像素相同。1366 宽纸色回大厅在额外等待后仍有 75,194 像素不同。将候选代码导出到隔离目录，只在离开大厅时保留 `img.src` 的对照中，同一画面的差异为 0。关闭 GPU 和 LCD 文本栅格后的候选对照为 7 像素。基点同一纸色场景重复截图的回大厅差异为 2 像素。大厅图片释放与常规 Edge 的逐像素条件仍未同时通过。

| Case | Scene | Changed pixels | Bounds |
| --- | --- | ---: | --- |
| 1366x768-light-normal | lobby | 0 |  |
| 1366x768-light-normal | library | 120 | (4, 173, 798, 595) |
| 1366x768-light-normal | newplan | 0 |  |
| 1366x768-light-normal | calibration | 17 | (25, 24, 592, 334) |
| 1366x768-light-normal | geometry | 17219 | (0, 58, 1268, 759) |
| 1366x768-light-normal | editor | 12 | (310, 13, 530, 233) |
| 1366x768-light-normal | preview | 0 |  |
| 1366x768-light-normal | return | 75194 | (44, 117, 1260, 768) |
| 1366x768-light-normal | reopen | 23 | (310, 13, 530, 484) |
| 1366x768-light-normal | pastworks | 6617 | (2, 0, 1158, 768) |
| 1366x768-light-normal | presets | 0 |  |
| 1366x768-light-normal | faxnews | 0 |  |
| 1366x768-dark-normal | lobby | 2 | (279, 643, 280, 645) |
| 1366x768-dark-normal | library | 129 | (169, 302, 761, 603) |
| 1366x768-dark-normal | newplan | 0 |  |
| 1366x768-dark-normal | calibration | 18 | (143, 159, 592, 380) |
| 1366x768-dark-normal | geometry | 24454 | (0, 75, 1268, 760) |
| 1366x768-dark-normal | editor | 0 |  |
| 1366x768-dark-normal | preview | 4 | (439, 253, 539, 286) |
| 1366x768-dark-normal | return | 76845 | (59, 164, 1244, 768) |
| 1366x768-dark-normal | reopen | 18 | (291, 4, 520, 244) |
| 1366x768-dark-normal | pastworks | 67 | (25, 0, 375, 545) |
| 1366x768-dark-normal | presets | 143403 | (0, 0, 1366, 768) |
| 1366x768-dark-normal | faxnews | 0 |  |
| 390x844-light-normal | lobby | 117 | (87, 389, 385, 504) |
| 390x844-light-normal | library | 6 | (27, 155, 118, 240) |
| 390x844-light-normal | newplan | 0 |  |
| 390x844-light-normal | calibration | 0 |  |
| 390x844-light-normal | geometry | 348 | (119, 128, 271, 801) |
| 390x844-light-normal | editor | 0 |  |
| 390x844-light-normal | preview | 0 |  |
| 390x844-light-normal | return | 17962 | (0, 351, 390, 809) |
| 390x844-light-normal | reopen | 2 | (254, 104, 262, 105) |
| 390x844-light-normal | pastworks | 3020 | (27, 12, 297, 548) |
| 390x844-light-normal | presets | 0 |  |
| 390x844-light-normal | faxnews | 0 |  |
| 390x844-dark-normal | lobby | 63 | (87, 393, 384, 504) |
| 390x844-dark-normal | library | 5 | (117, 206, 179, 243) |
| 390x844-dark-normal | newplan | 0 |  |
| 390x844-dark-normal | calibration | 0 |  |
| 390x844-dark-normal | geometry | 2604 | (71, 193, 370, 831) |
| 390x844-dark-normal | editor | 0 |  |
| 390x844-dark-normal | preview | 0 |  |
| 390x844-dark-normal | return | 30508 | (0, 94, 390, 798) |
| 390x844-dark-normal | reopen | 2 | (254, 104, 262, 105) |
| 390x844-dark-normal | pastworks | 12 | (180, 18, 292, 85) |
| 390x844-dark-normal | presets | 0 |  |
| 390x844-dark-normal | faxnews | 0 |  |

## 重跑

在本工作树执行，先用 `git archive 4f042ca` 导出 `discprobe`、`disclab`、`tests`、`presets`、`tools`、`pyproject.toml` 到隔离目录 `D:/dp-dev/tmp/pageteardown/base`。`--source` 指向目录；当前版本默认从本工作树启动。脚本使用本机 Edge、Python 和 Node 26。日志、原始数据和截图均在卡的 D 盘临时目录。

```powershell
$env:TEMP = $env:TMP = 'D:/dp-dev/tmp/pageteardown'
node evidence/page-teardown/measure.mjs --run=before --source=D:/dp-dev/tmp/pageteardown/base
node evidence/page-teardown/measure.mjs --run=after
node evidence/page-teardown/measure.mjs --run=before --visual --source=D:/dp-dev/tmp/pageteardown/base
node evidence/page-teardown/measure.mjs --run=after --visual
python -X utf8 evidence/page-teardown/compare.py
```

`--only=1366x768-light-normal` 可单跑一项。`--resume` 可跳过已完整保存的内存样本。脚本只使用自建 Disc Lab 和私有 Edge 配置，结束时关闭各自进程和删除虚拟盘目录。8765 的检查单独通过 `windows.ps1 -Action service` 的系统监听和进程信息执行。
