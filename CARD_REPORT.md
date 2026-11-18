# 卡 AA · 单实例、光驱互斥和退出

分支 `core/single-instance-20261118`，基点 `e0ddb3c`。所有设备验收均在 Disc Lab 或假设备上进行。回归开始前 D 盘剩余约 204 GiB，临时数据和证据放在 `F:/dp-archive/tmp/singleinst/`。

## 提交

- `f21439a` 接入单实例发现、光驱锁、控制台标题、网页退出和回归用例。随包 BAT 将参数交给 `tools/launch_web.py`。它与 `python -m discprobe webui` 共用 [启动逻辑](discprobe/web_instance.py#L112)。
- 本提交记录验收结果和证据位置。
- 基点的社区提示卡报告可用 `git show e0ddb3c:CARD_REPORT.md` 查阅。

## 服务行为

- `web-instance.json` 写在新闻缓存同级的用户状态根目录，包含端口、令牌、PID、启动时间、模式和绑定地址。启动锁协调同时拉起的进程，临时文件和 `os.replace` 发布登记。带令牌的 `GET /api/ping` 校验 PID 与启动时间。登记残缺、令牌或身份不匹配、进程已死或端口被占时会重新启动服务，端口冲突时改用系统分配的端口。
- 第二次启动打开已有大厅并退出 0。请求模式不同时，提示已有模式和本次请求的模式。`--new-instance` 启动独立服务，普通服务继续持有原登记。Disc Lab 自带的网页启动器显式使用这一模式。
- 大厅右上角显示退出电源按钮。服务有任务或正在读盘时禁用，悬停文字为“先等任务结束”。确认后调用带令牌的 `POST /api/quit`，页面收到成功响应后显示退出提示。服务端在同一把任务状态锁内确认空闲并停止接收新任务，正常退出清除自己的登记。

## 光驱入口清单

Windows 用 `msvcrt.locking`，POSIX 用 `fcntl.flock`。光驱锁文件第一个字节用于互斥，其后记录 PID 和动作。锁立即返回持有者信息，同一线程内的嵌套调用保留外层动作。Windows 盘符别名归一，Linux 合并设备路径、符号链接和可匹配的 `srN`、`sgN`。Disc Lab 在同一实验室内按虚拟盘符取得同一把 core 锁。参考 [核心锁](discprobe/drive_lock.py#L25)、[设备键](discprobe/drive_lock.py#L74) 和 [Disc Lab 设备接入](disclab/hooks.py#L23)。

| 实际光驱操作 | 拿锁的入口和覆盖范围 |
| --- | --- |
| 刻录、续写、开放会话、刻前擦除 | [burner.burn](discprobe/burner.py#L397) 覆盖介质检查、刻录、写入状态检查和刻后验证。 |
| 擦除、擦除前后状态检查 | [eraser.erase](discprobe/eraser.py#L109)，可独立调用的检查在 [eraser.inspect](discprobe/eraser.py#L18)。 |
| 刻后抽样比对、盘面写入状态 | [burner.verify_image](discprobe/burner.py#L349)、[recorded.burn_state](discprobe/recorded.py#L115)。嵌在刻录里时保留“刻录”动作。 |
| `info` 完整 MMC 信息与盘面身份 | [cmd_info](discprobe/__main__.py#L511) 将锁交给 [InfoDevice 工作线程](discprobe/info.py#L49)，实际设备关闭后释放。 |
| `disc` 快速检查、`swap` 等待换盘、`whois` 读盘面身份 | [cmd_disc](discprobe/__main__.py#L586)、[cmd_swap](discprobe/__main__.py#L618)、[cmd_whois](discprobe/__main__.py#L561)。 |
| `timing`、`geo`，含 BD / CD CLV 和角度测量分支 | [cmd_timing](discprobe/__main__.py#L647)、[cmd_geo](discprobe/__main__.py#L848)。 |
| `calibrate` 自动校准 | [calibrate.run](discprobe/calibrate.py#L96) 的 `disc`、`burn`、`timing`、`geo` 子命令各在 core 端取得锁，忙时终止该阶段并传回错误。 |
| `label --drive` 读取当前会话的下一可写 LBA | [labelsession.run](discprobe/labelsession.py#L107) 持锁完成会话读，再离线生成镜像。 |
| 网页驱动读盘、写速探测与光驱任务 | [read_disc](discprobe/webui.py#L645)、[burn_speeds](discprobe/webui.py#L658)、[start](discprobe/webui.py#L694)。请求复用 core 的忙态检查，实际动作在 [读取适配器](discprobe/burner.py#L334) 或 CLI 子进程内拿锁。请求后才出现的冲突通过子进程事件回传。 |
| 独立 Windows IMAPI 读取、刻录、擦除脚本 | [burn_imapi.ps1](tools/burn_imapi.ps1#L54) 和 [erase_imapi.ps1](tools/erase_imapi.ps1#L4) 用与 core 互通的 [字节锁](tools/drive_lock.ps1#L2)。由 core 启动的 IMAPI 子进程使用外层已持有的锁。 |
| 直接打开光驱的研究工具 | [bd_holdout.py](tools/bd_holdout.py#L57)、[cd_readcmd_compare.py](tools/cd_readcmd_compare.py#L82)、[geo_probe_points.py](tools/geo_probe_points.py#L52)。 |

`list` 和驱动器列表枚举设备名。`checkdisc` 根据已有测量生成检查用 ISO。`whois --image`、`info --image`、`geo --refit`、`label --start-lba` 和基于已有 `--geo` 的预设导出也只处理文件。这些入口不抢光驱。`--sim` 的进程内软件模型也不需要设备锁。

## 验收

- 相关 Python 使用 `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp <F 盘测试目录> ...`。首轮 490 项得到 474 通过、1 跳过、14 失败和 1 项夹具错误。修正 Disc Lab 独立实例和独立实验室隔离、校准子进程拒绝传递及既有前端测试的抓取边界后，用相同 `-n 2` 定向复验，33 项通过，再单独复验 1 项通过。合计覆盖 489 项通过、1 项跳过。在这组记录中，本卡新增的 11 个用例均通过。完整命令和各轮结果见 [首轮](F:/dp-archive/tmp/singleinst/python/pytest.log)、[定向复验](F:/dp-archive/tmp/singleinst/python-target/pytest.log)、[页面复验](F:/dp-archive/tmp/singleinst/python-web/pytest.log)。
- 共 55 个 `tests/test_*.mjs` 脚本。普通批次 54 个中 53 个首轮通过，`test_presetio_browser.mjs` 首轮等待结果超时，单独复验通过。导航 `node tests/test_flow_navigation_browser.mjs` 单独通过。合计 55/55。见 [普通批次](F:/dp-archive/tmp/singleinst/javascript/results.json)、[复验](F:/dp-archive/tmp/singleinst/javascript-target/test_presetio_browser.mjs.log)、[导航](F:/dp-archive/tmp/singleinst/navigation/test_flow_navigation_browser.mjs.log)。
- [新增用例](tests/test_single_instance.py) 用真实服务进程验证普通和同时启动、浏览器调用桩、LAN 与本机模式冲突、强杀恢复、半写登记、PID 与启动时间不符、错误令牌及端口冲突。设备用例验证双进程拒绝与崩溃释放、另一盘符可用、另一实验室的同盘符可用、嵌套重入、Windows PowerShell 与 core 相互排斥、写入期间拒绝退出以及退出后登记清除。
- 双窗口 Disc Lab 验收命令为 `python -B -X utf8 F:/dp-archive/tmp/singleinst/capture_lab.py edge-final-proof`。第一服务在 X: 选中并完成 8× 虚拟刻录。第二服务在刻录期间读 X:，大厅显示刻录子进程 PID 和中英提示。刻录完在同一页重读成功，接口返回 HTTP 200、`blank=false`、1024 扇区。两服务经网页确认退出，退出码均为 0，普通实例登记已清理。见 [实测日志](F:/dp-archive/tmp/singleinst/edge-final-proof/capture.log) 和 [控制台标题读取](F:/dp-archive/tmp/singleinst/edge-final-proof/console-title.txt)。

| 无头 Edge 画面（1440 × 900） | 纸色 | 夜色 |
| --- | --- | --- |
| 大厅空闲 | [PNG](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/idle-paper.png) | [PNG](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/idle-dark.png) |
| 刻录期间，退出按钮禁用 | [PNG](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/busy-paper.png) | [PNG](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/busy-dark.png) |
| 点退出并确认后 | [PNG](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/exited-paper.png) | [PNG](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/exited-dark.png) |
| 第二窗口读盘 | [刻录期间拒绝](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/read-refused-paper.png) · [刻后成功](F:/dp-archive/tmp/singleinst/edge-final-proof/screenshots/read-success-paper.png) | — |

## 未测和验收边界

- 真光驱、POSIX 实机文件锁、实际点击 Windows 控制台的关闭按钮、在另一台设备上走 LAN、最终发布 ZIP 中的 BAT 双击均未测。Windows 标题用 `GetConsoleTitleW` 核对，强杀与网页正常退出分别实测。复用时的系统默认浏览器调用用桩核对。
- 数值和镜像写入算法的改动范围为入口加锁。相关回归已跑，跨全部媒体、设备和镜像尺寸的独立逐位比对未测。禁用按钮的悬停文案通过页面属性核对。
- 校准阶段之间会释放设备，物理操作期间持锁。`--new-instance` 不登记，因此只启动过强开实例时，下一次普通启动可以再创建一台服务。这两处属于本卡保留的行为边界。
