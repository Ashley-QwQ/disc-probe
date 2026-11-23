# PT 卡交付报告

工作树 `D:/dp-dev/pageteardown`，分支 `dev/page-teardown`，基点 `4f042ca`。

## 按提交交付

- `eae7280` 释放不活动的页面场景、画布、worker 和图片引用，保留任务、草稿和表单数据。将信封、装盘合成帧、预设桌面和往期作品的图片移到使用时加载。复用 PM 测量脚本，并更新随页面生命周期改变的测试和引用行号。
- `4220366` 把信封动效参数恢复到点击时同步设置，解码还没完成时保留静态表单，仍可用原操作跳过。
- `3a34b04` 重建编辑器时沿用原画布上下文参数、面板和滚动位置，释放灯下控件对旧工作区的引用。动效测试验证未预热大厅与悬停后预热两种路径。
- `6c8da38` 释放光驱图片和图层时保留窄屏布局使用的光驱外框。截图脚本在导航就绪后离开编辑器，并支持补充的软件栅格对照。
- `378b58d` 重建图层缩略图，验证草稿和缩略图的一致性。RJ 测试在导航恢复就绪后再点返回。
- `50fc203` 记录原方案的内存、截图和大厅画质阻塞。
- `705dbc5` 保留当前主题的大厅底图及直接使用的位图。离开大厅时继续使用原图元素，切主题时更换图源。浏览器回归覆盖隐藏大厅及切主题。截图脚本等待虚拟盘检测稳定，并记录几何页的暂停进度。
- `3a76146` 增加同一会话的稳定状态重复截图，用于核对截图时机。
- `e464348` 把原阻塞移到 `BLOCKED-resolved.md`，供本轮记录处理决定。

主会话确认重新解码会降低大厅画质，决定保留当前主题的位图并继续逐像素精确验收。[原阻塞与处理决定](page-teardown-blocked-resolved.md)

## 验收

- 修前和修后使用独立的有界面 Edge、独立 Disc Lab 和用户目录。1366 × 768 两种主题，每组 6 个场景，空闲取样至少 30 秒。内存、图片请求以及逐像素表格见 [内存与截图报告](evidence/page-teardown/REPORT.md)。
- `python -X utf8 -m discprobe selftest` 本轮报告 `all checks passed`。
- `python -X utf8 -m pytest -n 2 -q` 对 `test_gui_handshake.py`、`test_web_security.py`、`test_web_instance_read.py`、`test_web_guidance.py`、`test_webui_recovery.py`、`test_webui_catalog.py`、`test_webui.py`、`test_troubleshoot.py` 验证，81 个测试和 58 个子测试通过。首次运行发现基点的握手断言仍写着 1.6，当前 API 已是 1.7。本卡更新测试期望，API 实现未变。
- `python -X utf8 tools/refresh_troubleshoot_citations.py` 刷新传真连接的两处引用。本轮 `--check` 通过。

- `node --test --test-concurrency=2` 本轮跑了全部 63 个 `tests/test_*.mjs` 文件，共 93 项。91 项通过，包含大厅位图和 RJ 回归。两个初次失败项随后单独用 `node --test` 复跑通过。`test_editor_w245_browser.mjs` 初次失败在缩放动画的定时断言。`test_title_font_alignment.mjs` 初次读取新 Edge 配置的 `DevToolsActivePort` 遇到 `EBUSY`。日志分别为 `resident-mjs.log`、`resident-w245.log` 和 `resident-title.log`。
- 浏览器草稿验证在两种主题、两种宽度下都通过。导入测试图并画矩形，回大厅，再点最近作品。重开前后的项目内容、未保存标记和图层缩略图一致。RJ 测试覆盖刷新、新标签、切走再回标定、盘库活进度和任务完成。
- 24 个内存样本。回大厅相对首次大厅的 Private Bytes 增量，纸色 +188.8 → +136.5 MiB，夜色 +269.8 → +62.4 MiB。回大厅的 JS 堆为纸色 17.67 → 3.64 MiB、夜色 17.72 → 3.65 MiB。首次大厅及标定总占用、Working Set 与 GPU 分项见内存报告。
- 48 对场景截图和 160 张转场截图，存于 `D:/dp-dev/tmp/pageteardown/shots/`。装盘和信封序列未见空白帧。几何页两种主题的桌面右侧工具栏、两种主题的窄屏顶部栏逐像素一致。
- 回大厅的新会话精确对照仍有 1、2、28、25 个静态差异像素。桌面纸色候选与上一轮基点图逐像素相同。稳定盘状态下的同版基点跨会话也出现大面积像素差异，见[新阻塞](page-teardown-blocked.md)。
- `windows.ps1 -Action service` 在测试前后均查到 8765 由 PID 12472 监听，启动时间均为 `2026-11-22T19:46:31.5149967-05:00`。检查只查询系统监听器和进程信息。结束时 D 盘 46.70 GiB 可用，F 盘 43.35 GiB 可用。

## 边界与未测

- 物理光驱、真盘、刻录及 4 GB 核显设备未测。测量用 RTX 2060，GPU 栏为 Windows 进程的内存统计。
- 编辑器保留草稿所需的原始像素、文件、撤销记录和选区。浏览器自行决定磁盘缓存、GPU 进程分配和垃圾回收时机。
- 上轮试跑有一处 Edge 临时配置目录留作失败现场。上轮手工递归清理被自动审批以 `blocked by policy` 拒绝。
- 刻录确认、刻录摘要和终端有各自的浏览器回归覆盖。其 1366 和 390 宽的修前修后逐像素对照未做。

STATUS: BLOCKED
