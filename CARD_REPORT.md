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

## 第二轮 · 统一启动、状态和停止

- `8495054` 按指令将 `dev/1.0.0@93e6a71` 合入当前卡分支，带入无头 Edge 的 `--mute-audio`。
- `4980264` 把启动、复用、查询和停止收进 core 的 `discprobe webui`，同步中英 README、CLI 帮助、Windows 包的 BAT 模板以及回归用例。保留标明弃用的 `tools/launch_web.py` 转调壳。本提交补记验收结果。

### 行为与代码

- [启动和发现](discprobe/web_instance.py#L143) 共用带令牌的健康检查。启动及复用时都打印实际 URL，有 `--open` 才调用默认浏览器。首选 8765，已占用时绑定空闲端口并登记；同一个首选端口再次启动时沿用登记里的实际端口。模式、盘种、端口、工作目录、输出目录、GUI、纹理配置及无光驱设置不一致时，在 stderr 列出冲突并提示先 `webui stop`，stdout 仍打印已有实例的 URL。
- [状态](discprobe/web_instance.py#L228) 的 JSON 包含 `running`、`pid`、`port`、`token`、`started`、`mode`、`bind`、`url`、`tasks` 和 `drives`。每台盘报告是否持锁、PID 和动作，包含同一实验室或设备命名空间下的独立进程。状态依据实时文件锁，崩溃后遗留的持有者记录不会显示为活锁。旧版登记没有配置快照时只能核对已有的模式。
- [命令行停止](discprobe/web_instance.py#L264) 和大厅退出进入同一个 [服务端判定](discprobe/webui.py#L1139)。普通停止遇到忙态返回 1 并列出任务。`--force` 可取消非写入任务，保护刻录、擦除和校准的写入阶段，也拒绝有外部写入或活动锁无法判定动作的快照。CLI 等到实例登记清理才报告成功。
- [开始 Start.bat 模板](tools/build_winpack.py#L33) 只有一行，切到包目录、使用包内 Python 和 UTF-8，然后执行 `-m discprobe webui --open`，透传原参数。BAT 文件按原方式写成 ASCII 和 CRLF。`--no-drives` 及 `DISC_PROBE_NO_DRIVES=1` 都由 core 的启动入口处理。

### 第二轮验收

- `python -B -X utf8 F:/dp-archive/tmp/singleinst/round2/run_regression.py python` 底层使用 `pytest -n 2`，得到 **496 通过、1 跳过**。另以 `pytest -n 2 tests/test_design_compose_route.py` 验证合成入口，**3 通过**。跳过项缺既有的 `calib-simple` 参考夹具。新增生命周期路径验证了实际 BAT 与 CLI 两种启动顺序、同一 PID 和 URL、无 `--open` 时只打印、默认端口被占时登记实际端口、模式及盘种冲突、完整状态 JSON、只读强停和写入拒绝。见 [回归日志](F:/dp-archive/tmp/singleinst/round2/python/pytest.log) 和 [合成回归](F:/dp-archive/tmp/singleinst/round2/pytest-compose.xml)。
- `tests/test_*.mjs` 共 **55/55 通过**。普通批次 54 个中 53 个首轮通过，预设导入导出的无头用例首轮结果停在 `PENDING`，单独复验通过。导航按要求单独跑，首轮等待盘库切换超时，单独复验通过。见 [普通批次](F:/dp-archive/tmp/singleinst/round2/javascript/results.json)、[预设复验](F:/dp-archive/tmp/singleinst/round2/javascript-target/test_presetio_browser.mjs.log)、[导航复验](F:/dp-archive/tmp/singleinst/round2/navigation-target/test_flow_navigation_browser.mjs.log)。
- 用合入后的 `8495054` 作基点，在两份隔离目录运行相同模拟输入。`compare_outputs.py` 和 `compare_geo.py` 逐字节比对 **5 份样本**，DVD/CD ISO 各 8,388,608 字节，`info` JSON 6,894 字节，`timing` CSV 22,287 字节，`geo` CSV 2,140 字节，全部一致。未固定时钟的首轮 ISO 差异在日期字段，重验给两端同一创建时钟，不修改生成后的文件或生产代码。见 [镜像与计时哈希](F:/dp-archive/tmp/singleinst/round2/byte-compare.log)、[几何 CSV 哈希](F:/dp-archive/tmp/singleinst/round2/geo-byte-compare.log)。
- 无头 Edge 实测新增 `--mute-audio`。两服务使用 X: 完成 8× 虚拟刻录、刻中拦截、刻后同一页面重读，以及两次网页正常退出。截图脚本在第一服务的刻后自动读盘结束后再触发第二服务重读。两进程退出码均为 0，登记清除。见 [实测日志](F:/dp-archive/tmp/singleinst/round2/edge-final/capture.log)、[截图目录](F:/dp-archive/tmp/singleinst/round2/edge-final/screenshots)。

### 第二轮边界

- 本轮运行了生成模板的实际 BAT，测试中的 `python` 目录指向本机 Python。正式 full-win64 ZIP 和包内嵌入式 Python 未验收。设备验证只使用 Disc Lab 或测试桩。逐位数据对应上述样本。
- 除指定的上游合入，提交留在本工作分支，未推送、未合回 `dev/1.0.0`。

## 第三轮 · 完整包的跨平台启动

- `198c33b` 按「补充 2 修订」改名 Windows BAT，加入 Linux 启动器和双语首读说明，同步打包、文档和网页提示。本提交记录验收，并将中英 README 的手动安装要求同步为 Python 3.11。
- [build_winpack](tools/build_winpack.py#L33) 生成 `开始 Start (Windows).bat`。CMD 只执行一行包内 Python 命令。开头另有一行兼容 sh 的提示，Linux 上用 sh 误跑会提示执行 `bash start-linux.sh` 并退出 1。构建目录会带上 `start-linux.sh` 和 `先看我 Read me first.txt`。
- [start-linux.sh](start-linux.sh) 在 Git Bash、MSYS 和 Cygwin 上提示使用 Windows BAT。它切到包目录，确认 `linux/python/bin/python3` 可执行，然后直接 `exec ./linux/python/bin/python3 -X utf8 -B -m discprobe webui --open "$@"`。Git 确认权限为 `100755`，源码和打包副本为 LF。首读说明也给出 `bash start-linux.sh`。启动不会创建环境或安装依赖。
- core 负责 Linux [无图形桌面的启动](discprobe/web_instance.py#L103) 和 [/dev/srN 的权限提示](discprobe/webui.py#L1780)。无 DISPLAY 和 WAYLAND_DISPLAY 时终端地址仍可用。光驱提示检查读写权限元数据，提示加入 `cdrom` 组后重新登录。

### 第三轮验收

- 本机 Windows 用 [实际生成的 BAT 测试](tests/test_single_instance.py) 在含中文和空格的目录验证 BAT 先启动及 CLI 先启动。两种顺序都复用同一实例，并通过 Disc Lab 读到了虚拟 X: 的盘片后正常停止。浏览器调用使用测试桩。
- 本机 Linux 分支验收使用 [Git Bash 模拟布局](tests/test_start_linux.py)。用 `uname` 桩走 Linux、MINGW、MSYS 和 Cygwin 分支。测试包里的 `linux/python/bin/python3` 是转调本机 Python 的脚本，核对了切换目录、包含空格的参数、完整 exec 参数、缺解释器提示和 sh 误跑 BAT。另用实际 Windows Git Bash 直接运行 Linux 脚本，退出 1 并提示 Windows BAT。使用 `python -B -X utf8 F:/dp-archive/tmp/singleinst/round3/check_pack_layout.py` 核对打包目录中的 Linux 脚本和首读文件与源码逐字节相同，以及 Windows 模板只留一条可执行命令。
- `python -B -X utf8 F:/dp-archive/tmp/singleinst/round3/run_regression.py python` 以 `pytest -n 2` 验证相关用例，**507 通过、1 跳过**。跳过项缺既有的 `calib-simple` 参考夹具。首轮启动器测试有两项因 Git Bash 的模拟 PATH 使用了带冒号的盘符路径而落进 Windows 分支，修正测试夹具后均通过。见 [首轮用例](F:/dp-archive/tmp/singleinst/round3/pytest-focus.xml) 和 [最终 Python 回归](F:/dp-archive/tmp/singleinst/round3/python/pytest.log)。
- 同一脚本的 `javascript` 批次 **54/54 通过**。导航单独验收，前两次分别遇到本机环回连接被拒和 Edge 的 `ERR_NO_BUFFER_SPACE`。等待本机连接回收后以 `navigation-cooldown` 第三次单独通过，合计 **55/55**。见 [普通批次](F:/dp-archive/tmp/singleinst/round3/javascript/results.json)、[首次导航](F:/dp-archive/tmp/singleinst/round3/navigation/test_flow_navigation_browser.mjs.log)、[第二次导航](F:/dp-archive/tmp/singleinst/round3/navigation-target/test_flow_navigation_browser.mjs.log) 和 [通过的导航复验](F:/dp-archive/tmp/singleinst/round3/navigation-cooldown/test_flow_navigation_browser.mjs.log)。
- 对 `0d8c9f2` 做等输入逐字节复验。固定两边 ISO 创建时间后，DVD/CD ISO 各 8,388,608 字节、`info` JSON 6,894 字节、`timing` CSV 22,287 字节和 `geo` CSV 2,140 字节全部一致。见 [镜像与计时哈希](F:/dp-archive/tmp/singleinst/round3/byte-compare.log) 和 [几何哈希](F:/dp-archive/tmp/singleinst/round3/geo-byte-compare.log)。

### 第三轮边界

- 真光驱和实际 Linux 包内解释器未测，预装及 Linux 实包验收由 core-release 负责。Windows 用本机 Python 驱动生成的 BAT，正式完整 ZIP 未构建。本轮验收仅在本机，提交不包含 wheel，未推送、未合并。
- 中文手册的 DVD 读完成章节在基点已有 17 行连续问号，逐行核对与基点相同。本轮改动的中英文字通过 UTF-8 检查。
