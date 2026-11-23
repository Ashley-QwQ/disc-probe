# RJ · 网页识别正在测量的批次

基点 `24fc50e`，分支 `dev/running-job`。

## 提交

- `a4705e2` 登记 timing 和 geo 实际分配的目录。占用记录放在工作区的内部目录里，和测量文件分开。文件锁跟随进程寿命，标定的父进程持有子步骤的目录直到写完最终标定记录。盘库扫描和删除共用工作区锁。网页和 CLI 会拒绝删除被占用的批次，网页也会拒绝改名。任务退出后，盘库重新按写盘结果判定状态。
- 同一提交增加 API 1.7 的可选能力。盘库显示「测量中」以及可得到的阶段、测点和百分比。标定页按游标分批接收事件，大厅订阅状态和结束通知。进度条复用节点，离开标定视图后停止绘制该场景，地面日志隐藏时停表。补上回归测试和双语文案，刷新排错引用行号。
- 本报告单独提交。

## 重开和回程

| 走法 | `24fc50e` | 本分支 |
| --- | --- | --- |
| 刷新标定页 | 从 `/api/state` 找到服务仍在跑的标定，接回进度 | 接回同一任务，分批重放进度 |
| 关标签，再打开启动器使用的服务地址 | 当前代码会自动接回。基点实测能回到几何页，但盘库把同一批次列成 `incomplete` | 自动接回，盘库显示测量中 |
| 主动回大厅，再进标定 | 当前基点的主按钮和底部任务名都能回去，11-19 走查单第 3 条在本基点未复现 | 保留这两个入口，随服务状态更新 |

选择沿用自动接回的启动行为。主动回大厅时沿用既有主按钮「回到校准」和底部任务名。启动器复用服务的路径按源码及实例测试核对。浏览器复现使用同一地址新建标签，未双击 BAT。

## 验收

- `node tests/test_running_job_browser.mjs` 用 Disc Lab 录完的全容量虚拟 DVD。在几何约 48% 时暂停虚拟读取，先刷新，再关闭标签并新建标签。验证两个大厅入口、盘库状态、改名及删除禁用、HTTP 409 的 `measurement_running`，恢复读取后验证实际可用结果和按钮重新启用。在基点的隔离源码上，同一测试在盘库状态处失败，实际 `incomplete`，预期 `measuring`。见 [基点日志](D:/dp-dev/tmp/runjob/baseline-reopen.log)。
- `python -X utf8 -m pytest -n 2 -q --basetemp D:/dp-dev/tmp/runjob/pytest-verify tests/test_library_manage.py tests/test_webui_catalog.py tests/test_webui.py tests/test_webui_recovery.py tests/test_web_security.py tests/test_web_instance_read.py tests/test_web_guidance.py tests/test_geo_progress.py tests/test_geo_coverage.py tests/test_geo_integration.py tests/test_troubleshoot.py` 通过 94 项及 42 项子测试。占用期间从另一个进程执行 `library delete` 返回退出码 1，无占用批次照常移入回收站，遗留进度恢复为原来的 `incomplete`。后续相关两文件复验通过 13 项。见 [pytest 日志](D:/dp-dev/tmp/runjob/pytest-verify.log)。
- `python -X utf8 -m discprobe selftest` 退出码 0，日志 1,488 行 `ok`，0 行 `FAIL`。见 [自检日志](D:/dp-dev/tmp/runjob/selftest-final.log)。
- 逐个执行 `node tests/test_*.mjs`，63 个文件通过。补拍测试首次触及运行器的 300 秒超时。用原夹具的镜像和相同 SHA-256，按该测试支持的 `RESHOOT_PREPARED_LAB` 路径建新 Lab 重跑，两个场景均通过。见 [JavaScript 结果](D:/dp-dev/tmp/runjob/mjs-logs/verified-results.json) 和 [补拍重跑日志](D:/dp-dev/tmp/runjob/mjs-logs/test_reshoot_browser-retry.log)。
- `python -X utf8 tools/refresh_troubleshoot_citations.py --check` 和 `git diff --check` 均通过。
- 无任务对照。两个版本浏览器的初始任务和盘库 JSON、大厅「下一步」、空盘库条目及标定「检测光盘」一致。相同已测加中断夹具的 `library list`、`show`、`delete --keep-works` 和删除后 `list` 逐字段一致，删除比较排除随机回收站 ID。见 [网页状态](D:/dp-dev/tmp/runjob/idle-after.json) 和 [CLI 对照](D:/dp-dev/tmp/runjob/idle-library-comparison.json)。
- 截图覆盖纸色和夜色、中英文、1440 和 390 宽的盘库状态和大厅入口，共 16 张。另有 4 张窄屏滚到禁用按钮的截图。20 张均已核对尺寸和主题语言。见 [截图目录](D:/dp-dev/tmp/runjob/shots)。

## 内存

基点和修复版各跑两次完整 DVD 标定，分别将取样标签停在标定页和大厅。录制会话使用 Disc Lab 的全容量 DVD，扇区数据在虚拟读盘时按扇区生成。测试给几何读加 9 ms 的间隔，再用本次几何实际发出的进度记录扩增 4,800 条更新，保留真实测点和结果。进度每累计 240 条暂停取样，每组取等效 0–20 分钟和结束时共 22 点。四场的几何取样分别约 36–39 秒，发出 4,920–4,926 条进度。指标用 CDP `Runtime.getHeapUsage`、`HeapProfiler.collectGarbage`、`Memory.getDOMCounters` 和页面元素统计。

| 页面 | 版本 | GC 后 JS 堆 MiB，0 / 10 / 20 分 | 前半 / 后半增量 MiB | 原始 JS 堆峰值 MiB | CDP 节点峰值 |
| --- | --- | --- | --- | --- | --- |
| 标定 | 基点 | 2.30 / 3.45 / 4.70 | 1.15 / 1.26 | 9.10 | 5,698 |
| 标定 | 修复 | 2.26 / 2.39 / 2.57 | 0.13 / 0.18 | 3.37 | 2,752 |
| 大厅 | 基点 | 2.25 / 3.06 / 3.85 | 0.81 / 0.79 | 11.58 | 5,808 |
| 大厅 | 修复 | 2.26 / 2.33 / 2.35 | 0.073 / 0.014 | 3.02 | 2,603 |

基点每 250 ms 拉取完整历史，把新的序列化事件长期存在去重集合里。两个页面共用这条路径。进度重画也会反复替换节点，标定场景退出后仍在做部分绘制。游标每批最多返回 256 条，页面只记当前位置。地面日志原有七行上限继续生效，步骤尺保留已有节点，隐藏时停止不必要的绘制。

大厅后半段增量是前半段的 18.6%。标定页是 140.1%，未过相对 20% 的门槛，后半段绝对增量比基点少约 85%。大部分余量出现在等效第 10–12 分钟。补采时这段图上由 2 个点增加到 6 个，实时图和读数判定仍需要增加元素。第 12–20 分钟由 6 个点增加到 21 个，堆只多约 0.021 MiB。保留正常测点和判定显示，未为相对比例压掉真实数据。补采支持增长集中于图表展开这段，未对余量逐对象归因。

两页取样均为 3 个 canvas 和 98 个图片元素。第 2 分钟加载尺寸非零的图片去重后是 64 张，按宽 × 高 × 4 估算全部解码需要约 385 MiB，最大单图 `caltop/anim/final_paper.webp` 约 18.4 MiB。这个估算是像素尺寸的和，Edge 实际解码缓存、GPU 内存和系统占用未测。可由审查者决定是否另测 4 GB 设备上的场景素材常驻成本。

[基点 CSV](D:/dp-dev/tmp/runjob/memory/before.csv) · [修复 CSV](D:/dp-dev/tmp/runjob/memory/after.csv) · [折线图](D:/dp-dev/tmp/runjob/memory/heap.png) · [标定图表补采](D:/dp-dev/tmp/runjob/memory/after-calibration-chart.csv)

## 范围

未测社区用户的 4 GB 笔记本、真实标签崩溃、物理光驱和实际刻录。重开验证覆盖服务仍在运行的场景。服务外启动的 CLI 测量也能阻止删除在写的批次，其进度仍在运行命令的终端显示。

STATUS: DONE
