# PT 卡交付报告

工作树 `D:/dp-dev/pageteardown`，分支 `dev/page-teardown`，基点 `4f042ca`。

## 按提交交付

- `eae7280` 释放不活动的页面场景、画布、worker 和图片引用，保留任务、草稿和表单数据。将信封、装盘合成帧、预设桌面和往期作品的图片移到使用时加载。复用 PM 测量脚本，并更新随页面生命周期改变的测试和引用行号。
- `4220366` 把信封动效参数恢复到点击时同步设置，解码还没完成时保留静态表单，仍可用原操作跳过。
- `3a34b04` 重建编辑器时沿用原画布上下文参数、面板和滚动位置，释放灯下控件对旧工作区的引用。动效测试验证未预热大厅与悬停后预热两种路径。
- `6c8da38` 释放光驱图片和图层时保留窄屏布局使用的光驱外框。截图脚本在导航就绪后离开编辑器，并支持补充的软件栅格对照。
- `378b58d` 重建图层缩略图，验证草稿和缩略图的一致性。RJ 测试在导航恢复就绪后再点返回。

## 验收

- 修前和修后使用独立的有界面 Edge、独立 Disc Lab 和用户目录。1366 × 768 两种主题，每组 6 个场景，空闲取样至少 30 秒。内存、图片请求以及逐像素表格见 [内存与截图报告](evidence/page-teardown/REPORT.md)。
- `python -m discprobe selftest` 结束时报告 `all checks passed`。
- `python -X utf8 -m pytest -n 2 -q` 对 `test_gui_handshake.py`、`test_web_security.py`、`test_web_instance_read.py`、`test_web_guidance.py`、`test_webui_recovery.py`、`test_webui_catalog.py`、`test_webui.py`、`test_troubleshoot.py` 验证，81 个测试和 58 个子测试通过。首次运行发现基点的握手断言仍写着 1.6，当前 API 已是 1.7。本卡更新测试期望，API 实现未变。
- `python -X utf8 tools/refresh_troubleshoot_citations.py` 刷新传真连接的两处引用。后续 `--check` 复核。

- `node --test --test-concurrency=2` 运行全部 63 个 `tests/test_*.mjs` 文件。该轮 91 个测试通过，动效测试和 RJ 测试失败。更新动效夹具并等导航恢复就绪后，单独的 `node tests/test_motion_browser.mjs` 和 `node tests/test_running_job_browser.mjs` 均通过。最终再跑编辑器工作台、流程导航、动效和盘库四项，4 项通过。全量命令未再重复运行。
- 浏览器草稿验证在两种主题、两种宽度下都通过。导入测试图并画矩形，回大厅，再点最近作品。重开前后的项目内容、未保存标记和图层缩略图一致。RJ 测试覆盖刷新、新标签、切走再回标定、盘库活进度和任务完成。
- 24 个内存样本。回大厅的 Private Bytes 增量，纸色 +174.0 → +163.5 MiB，夜色 +183.2 → +146.6 MiB。回大厅的 JS 堆由约 17.7 MiB 降到约 3.6 MiB。首次大厅及标定总占用、Working Set 与 GPU 分项见内存报告。
- 48 对场景截图和 160 张转场截图，存于 `D:/dp-dev/tmp/pageteardown/shots/`。逐像素验收仍有差异，见 [阻塞说明](BLOCKED.md)。
- `windows.ps1 -Action service` 在测试前后均查到 8765 由 PID 12472 监听，启动时间均为 `2026-11-22T19:46:31.5149967-05:00`。检查只查询系统监听器和进程信息。结束时 D 盘 42.69 GiB 可用，F 盘 43.35 GiB 可用。

## 边界与未测

- 物理光驱、真盘、刻录及 4 GB 核显设备未测。测量用 RTX 2060，GPU 栏为 Windows 进程的内存统计。
- 编辑器保留草稿所需的原始像素、文件、撤销记录和选区。浏览器自行决定磁盘缓存、GPU 进程分配和垃圾回收时机。
- 试跑有一处 Edge 临时配置目录留作失败现场。手工递归清理被自动审批以 `blocked by policy` 拒绝，未执行。系统进程检查无匹配的 Edge 进程。
- 刻录确认、刻录摘要和终端有各自的浏览器回归覆盖。其 1366 和 390 宽的修前修后逐像素对照未做。

STATUS: BLOCKED
