# 切页后的浏览器内存

基点 `4f042ca`，候选 `705dbc5`。本轮候选保留当前主题的大厅位图。测量沿用 PM 卡的脚本、虚拟 DVD 和 1600 × 1600 RGBA 测试图。使用独立有界面的 Edge 158.0.4370.33、独立 Disc Lab 工作区和独立 `LOCALAPPDATA`。该主机的 GPU 为 RTX 2060，ANGLE 使用 Direct3D 11。视口为 1366 × 768、DPR 为 1，两组都用原图。每个场景至少静置 30 秒才取样。几何暂停在进度约 48% 时，取样完成后再恢复。各场景由同一标签页依次打开。

Private Bytes 和 Working Set 来自 Windows 进程计数器。renderer 和 GPU 栏均依次列 Private Bytes / Working Set。内存单位为 MiB。Working Set 逐进程相加，可能重复计算共享页。GPU 栏是 GPU 进程的 Windows 内存。专用显存未测。JS 堆是 CDP `Runtime.getHeapUsage.usedSize`，取样前未强制 GC。DOM 节点来自 CDP `Memory.getDOMCounters`，包含浏览器尚未回收的分离节点。

| Theme | Scene | Rev | PB / WS | renderer | GPU | JS heap | DOM nodes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| light | blank | before | 241.6 / 412.3 | 40.5 / 83.7 | 118.3 / 75.1 | 0.40 | 4 |
| light | blank | after | 236.5 / 410.3 | 36.7 / 81.3 | 117.5 / 75.3 | 0.40 | 4 |
| light | lobby | before | 309.1 / 559.1 | 67.8 / 188.1 | 150.6 / 87.5 | 1.73 | 1162 |
| light | lobby | after | 318.1 / 503.9 | 63.4 / 130.9 | 165.0 / 89.0 | 1.59 | 900 |
| light | library | before | 418.2 / 580.1 | 84.8 / 209.7 | 243.3 / 87.2 | 1.84 | 2419 |
| light | library | after | 422.4 / 526.9 | 78.9 / 148.7 | 254.8 / 94.9 | 2.23 | 3080 |
| light | geometry | before | 540.5 / 559.4 | 96.0 / 199.0 | 362.4 / 97.0 | 3.41 | 3004 |
| light | geometry | after | 452.4 / 648.7 | 86.1 / 258.6 | 284.2 / 126.1 | 3.16 | 1342 |
| light | editor | before | 773.1 / 702.0 | 164.6 / 302.5 | 526.1 / 135.1 | 17.68 | 3536 |
| light | editor | after | 543.4 / 662.2 | 131.3 / 242.6 | 329.9 / 154.7 | 3.60 | 1728 |
| light | return | before | 498.0 / 606.2 | 147.7 / 231.0 | 268.1 / 110.8 | 17.67 | 3553 |
| light | return | after | 454.6 / 581.4 | 121.3 / 208.8 | 251.3 / 107.7 | 3.64 | 1739 |
| light | return − lobby | before | +188.8 / +47.1 | | | | |
| light | return − lobby | after | +136.5 / +77.5 | | | | |
| dark | blank | before | 233.2 / 392.9 | 40.5 / 84.0 | 117.4 / 75.0 | 0.40 | 4 |
| dark | blank | after | 238.5 / 412.8 | 39.2 / 83.8 | 115.0 / 74.8 | 0.40 | 4 |
| dark | lobby | before | 299.6 / 539.8 | 67.9 / 188.7 | 148.8 / 87.9 | 1.73 | 1162 |
| dark | lobby | after | 311.5 / 507.7 | 67.8 / 135.5 | 152.0 / 87.8 | 1.62 | 909 |
| dark | library | before | 408.5 / 563.3 | 85.9 / 211.2 | 240.3 / 89.2 | 1.84 | 2419 |
| dark | library | after | 436.4 / 533.3 | 84.0 / 154.0 | 261.7 / 95.4 | 1.68 | 2157 |
| dark | geometry | before | 531.3 / 635.7 | 97.1 / 273.3 | 351.5 / 97.4 | 3.40 | 2990 |
| dark | geometry | after | 467.0 / 637.4 | 90.1 / 244.3 | 293.8 / 128.6 | 3.60 | 2094 |
| dark | editor | before | 512.6 / 679.3 | 158.2 / 281.3 | 271.6 / 132.1 | 17.67 | 3536 |
| dark | editor | after | 475.9 / 646.6 | 144.1 / 248.8 | 248.6 / 132.5 | 3.60 | 1728 |
| dark | return | before | 569.4 / 644.2 | 153.1 / 236.4 | 333.8 / 141.9 | 17.72 | 3553 |
| dark | return | after | 373.9 / 585.0 | 127.6 / 210.1 | 163.2 / 109.6 | 3.65 | 1739 |
| dark | return − lobby | before | +269.8 / +104.4 | | | | |
| dark | return − lobby | after | +62.4 / +77.3 | | | | |

`light` 为纸色，`dark` 为夜色。`return − lobby` 比较同一实例的回大厅与首次大厅。本轮 24 个样本全部完成，最短静置时间为 30.47 秒。

- 回大厅相对首次大厅的 Private Bytes 增量，纸色从 +188.8 降至 +136.5 MiB，夜色从 +269.8 降至 +62.4 MiB。Working Set 增量分别从 +47.1 变为 +77.5 MiB，从 +104.4 变为 +77.3 MiB。回大厅的绝对 Working Set 纸色从 606.2 降至 581.4 MiB，夜色从 644.2 降至 585.0 MiB。
- 首次大厅总占用（Private Bytes / Working Set）纸色为 309.1 / 559.1 → 318.1 / 503.9 MiB，夜色为 299.6 / 539.8 → 311.5 / 507.7 MiB。标定几何页纸色为 540.5 / 559.4 → 452.4 / 648.7 MiB，夜色为 531.3 / 635.7 → 467.0 / 637.4 MiB。每个组合取一次样，GPU 进程占用有波动。
- 回大厅的 JS 堆纸色从 17.67 降至 3.64 MiB，夜色从 17.72 降至 3.65 MiB。两种主题的回大厅 DOM 节点均从 3,553 降至 1,739。

## 场景和状态归属

| 场景 | 离开时的处理 | 返回时的状态来源 |
| --- | --- | --- |
| 大厅 | 停止问候更新和漂移帧。保留当前主题直接使用的位图图源、热点和过场几何。 | 沿用同一批图元素。最近草稿、光驱和任务状态从现有来源读取。 |
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

- 大厅的 `lobby/base_<主题>.webp` 和桌面直接使用的分层位图加载当前主题。切到其他页面后继续绑定在原来的图元素上。切主题时，图元素用新主题图源取代旧图源。包裹和亮屏等按需图层仍随其显示状态加载和释放。浏览器管理自身的缓存寿命。
- `newplan/envelope_back_{dark,paper}.webp` 与 `newplan/envelope_front_{dark,paper}.webp` 在新作品表单可见且启用动效时预热当前主题。切主题时换成当前主题那组。收表起动前检查解码，等待时沿用表单画面。收表后退出时释放图像引用。标定返回需要重新收放时再准备。
- `caltop/anim/final_{dark,paper}.webp` 只在需要合成帧的 `slide()` 中请求当前主题，并在完成后清掉源。日常装盘 `play()` 使用动画分层，等首次动画的图层可用再盖住现有画面。装盘结束后移去只给动态图层用的图片源，保留当前标定桌面所需图层。
- PM 清单中其余未见的较大资源包括 `presetio/desk` 桌面图、`pastworks/tumble_*`、新作品顶视图与纸面、装盘分层。预设桌面到打开导入导出时才配图，往期作品只在进场时配图，新作品主体在入口悬停或实际打开时准备。`row-*.svg` 是用来构建盘库结构的 SVG，进盘库或使用对应光驱场景时读取。网页图标继续随页面使用。
- 两种主题的修前取样都在第一次大厅累计收到 2 张信封图、12 张预设桌面图、10 张档案飞落图。在标定中又收到 1 张装盘合成帧。修后这四组图片在大厅、标定几何和回大厅样本里的累计请求数均为 0。

## 像素和状态验证

截图放在 `D:/dp-dev/tmp/pageteardown/shots/`。分两种主题及 1366 × 768、390 × 844 两种尺寸。普通截图固定表单测试名和日期，比较每个 RGB 像素。大厅只在虚拟盘检测稳定后截取，截图前后核对标题、检测时间和最近作品。几何在各自虚拟任务的暂停点截取，另比对独立于实时光头位置和百分比的顶部栏。录制期间保留原动画时长及曲线。

- 两种转场各取 10 张连续截图，共 160 张。装盘每组有 4–8 张不同的帧，信封每组 10 张均不同。查看两种宽度和主题的序列，未见空白帧。缩览拼图为 `shots/resident-load-disc-contact.png` 和 `shots/resident-envelope-contact.png`。
- 四个候选组合均在编辑器导入测试图并画矩形，随后回大厅，从最近作品重开。脚本比较离开前后的 `.discdesign` 序列化内容、未保存标记和两张图层缩略图的 PNG。390 宽回大厅的文档滚动宽度在修前、修后均为 488 px。
- 本轮第一组硬件栅格对照的 48 对场景截图见下表，其中 18 对逐像素一致。四组回大厅截图的标题均为「上次检测到的 DVD-R 已写过」，检测时间均为「上次检测：刚刚」，最近作品均为 `PT sample`。可在 `before/visual/` 和 `after/visual/` 下的对应 JSON 中核对。
- 几何页暂停进度（基点 → 候选）为桌面纸色 48.33% → 48.02%，桌面夜色 48.02% → 48.13%，窄屏纸色 48.54% → 49.27%，窄屏夜色 48.65% → 49.17%。全图的光头、进度条和测量内容会随进度变化。窄屏顶部栏 `[0, 0, 390, 72]` 两组均逐像素一致。桌面右侧语言、声音、主题和设置的按钮区 `[1050, 35, 1366, 96]` 两组也均为 0。下表同时保留整个页头的计数，其中桌面页头包含进度条，夜色另外有 27 个像素落在静态标志一带。

| Case | Scene | Changed pixels | Bounds |
| --- | --- | ---: | --- |
| 1366x768-light-normal | lobby | 39243 | (134, 226, 1232, 768) |
| 1366x768-light-normal | library | 192 | (183, 300, 798, 750) |
| 1366x768-light-normal | newplan | 0 |  |
| 1366x768-light-normal | calibration | 36 | (146, 2, 674, 371) |
| 1366x768-light-normal | geometry | 941 | (5, 7, 1066, 760) |
| 1366x768-light-normal | geometry header (0, 0, 1366, 96) | 4 | (786, 7, 1066, 33) |
| 1366x768-light-normal | editor | 1472 | (85, 666, 233, 724) |
| 1366x768-light-normal | preview | 4 | (439, 253, 539, 286) |
| 1366x768-light-normal | return | 69362 | (134, 226, 1232, 768) |
| 1366x768-light-normal | reopen | 25 | (196, 13, 530, 693) |
| 1366x768-light-normal | pastworks | 8166 | (2, 0, 1158, 768) |
| 1366x768-light-normal | presets | 99 | (78, 37, 113, 406) |
| 1366x768-light-normal | faxnews | 0 |  |
| 1366x768-dark-normal | lobby | 76551 | (134, 164, 1232, 768) |
| 1366x768-dark-normal | library | 14 | (456, 619, 673, 749) |
| 1366x768-dark-normal | newplan | 0 |  |
| 1366x768-dark-normal | calibration | 24 | (143, 170, 685, 397) |
| 1366x768-dark-normal | geometry | 13693 | (0, 59, 1268, 758) |
| 1366x768-dark-normal | geometry header (0, 0, 1366, 96) | 31 | (167, 59, 785, 82) |
| 1366x768-dark-normal | editor | 1429 | (100, 672, 233, 724) |
| 1366x768-dark-normal | preview | 4 | (439, 253, 539, 286) |
| 1366x768-dark-normal | return | 76160 | (134, 164, 1232, 768) |
| 1366x768-dark-normal | reopen | 18 | (291, 4, 520, 244) |
| 1366x768-dark-normal | pastworks | 9983 | (125, 0, 713, 562) |
| 1366x768-dark-normal | presets | 143412 | (0, 0, 1366, 768) |
| 1366x768-dark-normal | faxnews | 0 |  |
| 390x844-light-normal | lobby | 2349 | (0, 389, 390, 506) |
| 390x844-light-normal | library | 981 | (27, 80, 390, 243) |
| 390x844-light-normal | newplan | 0 |  |
| 390x844-light-normal | calibration | 0 |  |
| 390x844-light-normal | geometry | 1471 | (60, 118, 370, 831) |
| 390x844-light-normal | geometry header (0, 0, 390, 72) | 0 |  |
| 390x844-light-normal | editor | 0 |  |
| 390x844-light-normal | preview | 0 |  |
| 390x844-light-normal | return | 17231 | (0, 351, 390, 593) |
| 390x844-light-normal | reopen | 2 | (254, 104, 262, 105) |
| 390x844-light-normal | pastworks | 4589 | (21, 12, 297, 501) |
| 390x844-light-normal | presets | 0 |  |
| 390x844-light-normal | faxnews | 0 |  |
| 390x844-dark-normal | lobby | 0 |  |
| 390x844-dark-normal | library | 849 | (117, 80, 390, 232) |
| 390x844-dark-normal | newplan | 0 |  |
| 390x844-dark-normal | calibration | 0 |  |
| 390x844-dark-normal | geometry | 8205 | (60, 142, 370, 831) |
| 390x844-dark-normal | geometry header (0, 0, 390, 72) | 0 |  |
| 390x844-dark-normal | editor | 0 |  |
| 390x844-dark-normal | preview | 0 |  |
| 390x844-dark-normal | return | 25 | (307, 506, 384, 523) |
| 390x844-dark-normal | reopen | 2 | (254, 104, 262, 105) |
| 390x844-dark-normal | pastworks | 0 |  |
| 390x844-dark-normal | presets | 0 |  |
| 390x844-dark-normal | faxnews | 0 |  |

### 同一会话重复截图

用 `--control` 新开 Edge 重跑。每个组合在回大厅且盘状态相同的情况下拍三张，两次补拍分别额外等待 600 和 1,800 毫秒，并逐次核对盘状态。每个会话内部三张完全相同。候选的新会话与第一组候选也四组完全相同。下表按任何 RGB 通道不同即计为一个差异像素。

| 组合 | 同版基点跨会话 | 新会话基点对候选 | 差异范围 `(左, 上, 右, 下)` |
| --- | ---: | ---: | --- |
| 1366 × 768 纸色 | 69,361 | 1 | `(247, 664, 248, 665)` |
| 1366 × 768 夜色 | 76,160 | 2 | `(247, 546, 937, 665)` |
| 390 × 844 纸色 | 17,229 | 28 | `(310, 506, 390, 523)` |
| 390 × 844 夜色 | 0 | 25 | `(307, 506, 384, 523)` |

桌面纸色的两次候选截图也都逐像素匹配上一轮保留的基点图 `pre-residency/shots/before/1366x768-light-normal/return.png`。本轮稳定的同版基点跨会话对照复现了大面积差异。新会话基点和候选的少量静态差异仍可复现，无法归到实时盘状态或同一会话的截图时机。所有差异按实数保留，详见 `resident-control-compare.log` 和[当前阻塞](../../BLOCKED.md)。

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

`--only=1366x768-light-normal` 可单跑一项。`--resume` 可跳过已完整保存的内存样本。给两条截图命令加 `--control`，可将截图存到 `shots-control/`，并在盘状态相同的情况下将回大厅截图再拍两次。对应元数据在各版本的 `visual-control/` 目录。脚本只使用自建 Disc Lab 和私有 Edge 配置，结束时关闭各自进程和删除虚拟盘目录。8765 的检查单独通过 `windows.ps1 -Action service` 的系统监听和进程信息执行。
