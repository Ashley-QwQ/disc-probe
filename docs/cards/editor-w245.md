# 卡 I：设计页编辑器 W2 / W4 / W5

分支：`dev/editor-w245`。实际基点：`731b199258e68cf1a0809d0ea7a5e467c22dd90b`（任务卡头指定的基点）。

## 提交内容

本卡一个提交，主题为 `feat(editor): complete W2 W4 W5 selection and interaction fixes`，包含以下改动、测试和本报告：

- W5：撤销、重做移到画布左侧竖排工具栏最上方，下接分隔线；移除图层标题旁的按钮。提示含 Ctrl+Z、Ctrl+Shift+Z、Ctrl+Y；Mac 平台用 ⌘。按钮随历史状态禁用。历史上限仍为 80，原有快捷键保留。
- W5：导入名取文件名去扩展名，重名追加 ` 2`、` 3`；无文件名为“图片 N”，剪贴板图片按无文件名处理。保留原文件本来就是哈希串的名称，不擅自猜测。旧工程中的名称照原样打开。图层改名继续使用共用 `isActionEnter`，实测中文组合输入和 keyCode 229 不提前提交。
- W2：当前选区条第一行提供“拷贝到新图层”“剪切到新图层”“删掉选区里的内容”“只留选区里的内容”和取消。支持 Ctrl+J、Ctrl+Shift+J。新层紧邻原层上方并选中，保留变换、影调和图层材质分配；柔化覆盖率重采样到源图工作副本像素的 alpha，不缩成选区网格分辨率。新旧两层不共享可写画布。
- W2：选择工具或 V 工具在选区内拖动内容，超过 3 px 才进行剪切分层，整次拖动只记一步。取消、Escape、切换工具可以撤回未完成的拖动；历史栈已满时也保留原先 80 个条目。锁定图层不可修改，仍遵守最多 16 层。
- W2：魔棒按下后用临时蒙版实时预览，左右拖动调容差，同步数值，松开才提交一条历史；点一下沿用原先容差，取消不留下选区操作。工具提示补充用途和下一步。
- W4：导航期间对最后完整画布做 CSS 平移/缩放，跳过重采样、重合成和新的精确窗口请求；约 150 ms 无输入后清除变换，按原有路径重画。移动/缩放/旋转图层期间复用已合成的位图并叠加移动中的灰度源图，停手后再合成。未改 `exact-view.mjs`、`exact-worker.mjs` 和合成算法。
- 工程格式仍为既有 version 2，未加必需字段；旧版迁移规则未改。加入纯像素测试、可见页面的本机 Edge/CDP 验收脚本，以及对应浏览器测试入口。

## 两个疑点

1. **有选区按 Delete 删除整层：属实，已修。** 基点的真实 canvas 键盘事件使层数减少；修改后同一事件只修改选区 alpha，层数不变，撤销恢复原像素和选区。没有选区时仍删除图层。
2. **旧选区条走不到：属实，已删除旧分支。** W 工具被映射到当前 `colour` 工具，当前选区在 `S.selections / activeMask`；旧 `S.tool === "wand"`、`L.sel / seeds` 无可达建立入口。浏览器确认旧 `.fbar[data-mode="sel"]` 不显示。已删除旧魔棒、模糊、旧选区条及相应事件路径；图层数字属性条保留。

## 验收

临时文件、浏览器 profile、日志、原始测量和截图均在 `D:/dp-dev/tmp/editor/`。无光驱、无刻盘、无上传、无下载；浏览器夹具只使用回环 HTTP 和合成图片，不启动真实设备后端。不推送、不合并、不切换分支，不改其他 worktree 或纹理图谱 Python 文件。

最终命令与结果：

- 全部 `tests/test_*.mjs`：PowerShell 用 `rg --files tests -g 'test_*.mjs'`（附带任务要求的禁读路径排除规则）收集，再执行 `node --test --test-concurrency=1 $tests`。**47 项通过，0 失败，0 跳过**；日志 `mjs-final.log`。最初并发 2 的一轮为 45 通过、1 失败，失败是无关的 `test_presetio_browser.mjs` 停在 PENDING；单独重跑其 10 个场景通过，最终串行全量通过。没有修改该测试或其产品代码。
- `python -B -m pytest -n 2 tests/test_editor_ops.py tests/test_editor_preview.py tests/test_design_compose_route.py tests/test_editor_pose_swatches.py --basetemp D:/dp-dev/tmp/editor/pytest-final`：**94 通过，31.84 s**；日志 `python-final.log`。
- `node tools/editor_w245_check.mjs after`：**18 组浏览器验收通过，0 个 Runtime 异常**；包括真实 CDP 鼠标拖动、选区快捷键、剪切工程往返、柔化 alpha、取消恢复、80 步上限、锁定保护、复制材质、绘制工具不抢占为移动、实际 20/10 µm 精确窗口入口，以及独立 exact-worker 窗口与合成器逐标签一致。结果 `after.json`。原始结果、截图、相关源文件的 SHA-256 清单另存于 `evidence-manifest.json`。
- `node tests/test_selection_edit.mjs`：源像素分辨率、柔化、alpha 分配、旋转、边界、中文命名、重名和带点层名通过。
- `git diff --check`、三个修改模块的 `node --check` 通过。impeccable 检测输出 `[]`（`impeccable.json`）。中文文件 UTF-8 检查非 ASCII 字符大于零，未发现连续三个问号的乱码。

## W4 改前与改后

方法：`node tools/editor_w245_check.mjs before` / `after`。Edge 157.0.4341.60 无头，CDP `Performance.enable/getMetrics`，记录 rAF 相邻时间和主线程 TaskDuration / ScriptDuration。1440×1000，DPR 1；1024×1024 合成灰度图片放成 120×120 mm，铺满盘面；20/10 µm 各测平移和缩放，每段 48 帧。平移用 CDP 鼠标按下/松开及每帧 PointerEvent 驱动实际平移处理器，往返 72 px；缩放用每帧 Ctrl+wheel，放大 24 帧再缩回 24 帧。基点源文件通过 `git show 731b199:<明确文件路径>` 在同一只读夹具提供，没有切换或改写分支。

| 格子 | 操作 | 改前中位数 ms | 改前 P95 ms | 改前最长 ms | 改后中位数 ms | 改后 P95 ms | 改后最长 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| 20 µm | 拖动平移 | 8.3 | 13.7 | 16.6 | 8.3 | 8.4 | 8.5 |
| 20 µm | 缩放 | 725.1 | 991.6 | 1041.6 | 8.3 | 8.5 | 8.8 |
| 10 µm | 拖动平移 | 8.4 | 16.5 | 16.7 | 8.3 | 8.5 | 8.5 |
| 10 µm | 缩放 | 691.7 | 916.7 | 941.7 | 8.3 | 8.5 | 8.5 |

四组改后采样均达到中位数 ≤ 16 ms、P95 ≤ 33 ms。

原始 48 帧数组、浏览器版本和 Performance 计数保存在 `before.json` / `after.json`；简表在 `before-summary.json` / `after-summary.json`。这些数字是这台机器在该合成输入上的一次配对采样，不代表所有图片或硬件。初版夹具误继承首页待握手隐藏状态，已丢弃该轮数字和空白截图，修为可见夹具后重新测量。

像素验收：使用基点 `731b199` 的 `preview()` 对同一输入建立 420×420 RGBA SHA-256；当前纸色/夜色、20/10 µm 四组均完全相同，并冻结进测试。纸色 `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`，夜色 `00f4a7292cab532e5d70928e6d080259a2f233291b437145088a71095816e9f1`。基点记录在 `reference/before.json`。平移往返停手后的整个 canvas 另做逐通道对比，允许不超过 1/255 的浮点坐标栅格化误差；过程中断言没有调用 preview 重采样。

## 截图

均在 `D:/dp-dev/tmp/editor/shots/`，纸色与夜色的可见页面已检查：

- `undo-paper.png`、`undo-dark.png`：撤销/重做位置、分隔线与禁用状态。
- `layer-names.png`：文件名、重复名、匿名图片名。
- `selection-actions.png`：选区条第一行及柔化设置。
- `wand-tolerance.png`：魔棒按住向右拖动期间，容差 18 → 53。
- `move-before.png`、`move-after.png`：选区内容移动前后。

## 限制、未测和需要人决定的问题

- 停手后的屏幕分辨率合成仍在主线程，会发生一次重画等待；本卡消除连续交互期间反复合成，未把该合成搬进 Worker。精确视图仍按原算法计算，复杂图像/误差扩散的完整 10 µm 大窗口耗时未专项量测。实际网格入口验收使用小窗口和 threshold，不能据此宣称完整精确视图性能提升。
- 选区仍沿用既有 0.2 mm 网格；柔化以 mm 设置并在源像素 alpha 中保留，不能恢复该网格未表达的精细边界。导入仍沿用工作副本最大边 4096 px 的现有限制。
- Windows Edge 已测；实体 Mac、实体触控板、双指触屏与其他浏览器未测。Mac 的 ⌘ 提示按平台条件实现，没有实体 Mac 验证。
- 审美、原照片的真实文件名、真实盘面结果未做推断。现有颜色、主题与页面其他区域未重设计。暂无必须由人决定才能使用本卡功能的问题。
