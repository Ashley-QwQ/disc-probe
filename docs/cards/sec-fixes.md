# 卡 AB 验收报告

工作树为 `D:/dp-dev/secfix`，分支为 `web/sec-fixes-20261118`，基点为合入卡 AA 第二轮的 `ce30590`。

## 第二轮 · R1

- 合并提交 `23df931` 将 `dev/1.0.0` 的 `3bd5c5d` 合入本分支。仅 `CARD_REPORT.md` 发生冲突，保留卡 AB 报告。`cmd_geo` 自动合并，保留光驱锁装饰器、`speed_check` 以及装饰器的关键字参数透传。
- 实现提交 `f9be4d7` 接入 core 盘身份核对，补齐 R1 回归并隔离端口测试。
- 网页签发时读取介质身份，将它随动作、光驱和镜像身份一起存入一次性许可。启动任务时比较新读数，并将**签发时**的快照交给 core。CLI 刻录、擦除和带镜像校准在命令开始阶段采集快照，`--erase` 沿用该快照。网页带镜像校准会把原快照继续传给实际刻录子进程。[Web 签发](./discprobe/webui.py#L790) · [Web 传递快照](./discprobe/webui.py#L916) · [校准子进程](./discprobe/calibrate.py#L187)
- R4 集中的写前检查在合并基点尚未落入本分支。R1 的单一核对调用位于 `discprobe/burner.py:541` 和 `discprobe/eraser.py:132`，位于各自的入口光驱锁内。平台适配器在准备参数和临时流后、启动写入或擦除工具前执行回调。Windows 擦除沿用 `erase_imapi.ps1`，由持锁的 Python 在创建 PowerShell 子进程前读盘核对。先擦后刻会在擦除前核对完整身份，刻录前再核对稳定字段，允许授权擦除引起的空白状态和可读长度变化。身份不符抛出 `DiscChanged`，中英提示为“光驱里的盘和确认时的不是同一张 / The disc in the drive is not the one that was confirmed.”。[共用读取与比对模块](./discprobe/disc_identity.py) · [刻录接入点](./discprobe/burner.py#L541) · [擦除接入点](./discprobe/eraser.py#L132)

### 比对字段与 GH70N 证据

| 字段 | 用法及现有依据 |
| --- | --- |
| 介质家族和当前 profile | 从 MMC `GET CONFIGURATION` 获取。GH70N NYA2 的空白 DVD-R 存档报告为 DVD、`0x0011`。 |
| MID 或 ATIP | DVD 取格式 0Eh 的 MID 或格式 11h 的 ADIP 厂商、型号及版本。CD 取 ATIP 导入区起始时码。存档里的 GH70N 通过格式 0Eh 读到 `RITEKF1`。该 DVD-R 样本没有有效 ATIP 或 ADIP 响应。 |
| 可选独立盘 ID | 取 `READ DISC INFORMATION` 中由 DID_V 标为有效的四字节标识。GH70N 存档的标志字节为 `0x20`，DID_V 未置位。 |
| 容量、可读长度和状态 | 分别比较报告容量、已报告扇区数、空白、关闭和可擦写。该 GH70N 空白盘报告 2,297,888 个可写扇区，状态为空白、不可擦写，关闭状态为空。格式 0Eh 另可推得整盘几何容量为 2,298,496 扇区。对已记录的顺序式盘，整盘容量缺失时可把已报告的可读范围作为大小证据，镜像是否装得下仍由原有可写容量检查判断。 |
| 最近读取时间 | 软件在生成快照时写入纳秒时间戳，随签发快照传入 core。第二次读盘会产生新时间戳，比较以介质字段为准。 |

擦除许可要求当前 profile、可读的空白状态、可擦写标志、大小证据，以及 MID、ATIP 或有效的独立盘 ID。证据不足时拒绝签发。若光驱未提供独立盘 ID，两张盘的可读身份字段又完全相同，软件仍无法区分。Python 最后一次核对到平台工具实际接管光驱之间仍有物理换盘窗口。GH70N 段落只依据现存的空白 DVD-R 回包。CD-RW、DVD±RW 实盘、实体换盘与 Windows 实际擦除未测。[GH70N 原始 info 存档](./evidence/drive/info_blank_ritekf1.json)

### 第二轮验收

- `test_r1_core_checks_web_grant_after_taking_write_lock` 的四个用例均通过。擦除和刻录各验证换盘拒绝、同盘成功。两次网页读数均为 A，换盘只发生在 core 接手前。替身保持相同 profile、MID、容量和状态，仅改变有效盘 ID。拒绝用例确认锁内读到 B，且写入或擦除工具启动次数为零。另五个用例覆盖缺标识、缺大小证据、Windows 启动擦除助手前拒绝、CLI `--erase` 继承命令发起时的身份，以及 GH70N 存档解析。[专项测试](./tests/test_r1_disc_identity.py)
- `test_busy_port_falls_back_and_reuse_keeps_the_registered_port` 已通过。测试在 `tmp_path` 的临时状态目录运行，由测试套接字用端口 0 取得端口并占用，然后以该端口启动并复用服务。断言覆盖回退到另一端口、同配置复用和正常停止。[端口测试](./tests/test_single_instance.py#L314)
- `python -B -X utf8 -m pytest -n 2` 运行 R1、Web 后端、刻录和擦除、启动、刻后检查、失败退出、标签会话、盘身份标记、作品、目录、照片、合成与随盘文件相关的 17 个模块。首次为 **408 通过、1 跳过、1 失败，46 个子测试通过**。失败项 `test_cancel_owns_descendants` 的 Windows 输出日志曾遇到文件共享冲突。临时目录移到 F 盘且加上作业结束等待后，复验 Web 后端、刻录、目录、R1、启动共 **99 通过，46 个子测试通过**，包含此前的清理失败项。原始封存照片仍缺失，跳过 1 项。手机打开页面和上传合成 PNG 的本机局域网测试通过。[Python 相关回归](<F:/dp-archive/tmp/secfix/round2/pytest-final.log>) · [隔离复验](<F:/dp-archive/tmp/secfix/round2/pytest-recheck.log>)
- `node --test --test-concurrency=1` 运行导航之外全部 54 个 `tests/test_*.mjs` 文件，**67 通过**。独立运行 `node --test tests/test_flow_navigation_browser.mjs`，**1 通过**。Disc Lab 浏览器回归覆盖先擦后刻、取消和刻后检查。[Node 全量](<F:/dp-archive/tmp/secfix/round2/node-final.log>) · [导航](<F:/dp-archive/tmp/secfix/round2/navigation-final.log>)
- 用 `python -B -X utf8 -m discprobe compose <作品> --out <标签.npy>` 重新合成下表三份历史作品，输入 SHA-256 均与归档一致，输出的标签和纹理清单各 **3/3** 与归档逐字节一致。[第二轮合成命令和完整哈希](<F:/dp-archive/tmp/secfix/round2/compose-sha256.json>)

## 第一轮代码提交

`698dfdb` · Bind local file exports and disc writes to one-time permits

| 审查条目 | 改动与代码位置 | 专门验收 |
| --- | --- | --- |
| #1 随盘目录授权 | [作品导入和 ISO 导出](discprobe/web/home/design.js)、[随盘文件面板](discprobe/web/home/design/disc-files.mjs)、[清单摘要](discprobe/discfiles_api.py)和 [Web 后端](discprobe/webui.py)。导入和保存作品只携带文件数量、大小和放置位置。使用者在本机重新输入目录路径、检查并确认清单后，后端签发有效期 15 分钟的单次授权。授权绑定目录和文件树清单摘要。导出前重新检查文件树和布局指纹，图像子进程沿用原有的布局指纹校验。 | `finding_1_directory_requires_one_export_confirmation` 用浏览器打开带目录绑定的合成作品，扫描直接导出镜像的 ISO 9660 目录树和整个文件，均无夹具。重新选目录、查看清单、确认后导出，Joliet 树和镜像数据均查到夹具，再次导出要求重新确认。`test_finding_1_backend_requires_the_reviewed_directory_for_one_export` 验证无授权、替换目录、修改清单及重复提交都被后端拒绝。 |
| #2 刻录与擦除许可 | [签发、核验和启动](discprobe/webui.py)，并接入[设计页](discprobe/web/home/design.js)、[校准页](discprobe/web/home/calibrate.js)和[刻后检查页](discprobe/web/home/afterburn.js)现有确认。凭据经本机回环 POST 签发，30 秒内提交且一次消费。签发和启动时核对光驱的介质报告，核对介质类型、配置、批号、空白与可擦写状态等字段。镜像身份采用规范化路径、文件大小和纳秒修改时间。普通刻录、独立擦除、先擦后刻、带镜像校准及擦除后校准的许可分别绑定。 | `test_finding_2_burn_grant_matches_one_job` 用虚拟光驱核对串用动作、换光驱、换镜像、原路径镜像变化、介质报告变化及重放的 HTTP 403 和错误文字。对应动作的正确许可均可启动。模拟流程验证了刻录取消、擦除后重刻和刻后检查。 |
| #6 作品内容渲染 | [导入、图层列表及旧版影调面板](discprobe/web/home/design.js)、[选区列表](discprobe/web/home/design/editor-controls.mjs)。图层 ID 限定为 ASCII 字母、数字、下划线和连字符，长度 1–64。导入时为不合规或重复 ID 分配新值，并重映射图层填充引用。检查并修复的模板插值包括图层行的 `data-id`、`id`、`aria-controls`，选区行的 `data-mask-id`、`data-delete-mask`，旧版影调数值框及自动色阶文案，以及旧版随盘文件计数。图层名经过转义，文件名单使用 `textContent`。 | `finding_6_layer_id_and_text` 在静音 Edge 中导入含标记字符的 ID 和图层名。重新生成的 ID 符合白名单，填充引用与 DOM 属性一致，原名称完整显示为文本，监视标记节点的 `window` 钩子调用数为 0。 |
| #3/#4 局域网 | [HTTP 监听与请求校验](discprobe/webui.py)。Host 必须带实际端口，只接受回环地址、`localhost` 和该连接实际到达的本机私有 IPv4。头部阶段最多 24 条连接，局域网来源最多 16 条，给本机桌面预留 8 条。3 秒请求头总期限覆盖分段到达的请求，正常认证完成后释放这部分容量。 | `test_finding_3_only_listener_hosts_before_authorization` 在两种监听模式下检查伪造 Host。`test_finding_4_partial_headers_expire_and_leave_room_for_a_normal_request` 同时打开 6 条未完成头部的本地连接，正常请求在期限内返回 200，随后慢连接到期。`test_finding_4_remote_slots_cannot_take_the_loopback_reserve` 验证限额和本机保留。`test_finding_3_4_phone_page_and_upload_on_the_lan_listener` 用实际局域网地址打开手机页，上传合成 PNG，并在桌面列表读到该照片。 |

## 第一轮回归验收

- `python -B -X utf8 -m pytest -n 2` 运行 `test_secfix.py`、`test_webui.py`、`test_burner.py`、`test_photo.py`、`test_single_instance.py`、`test_webui_catalog.py`、`test_works.py`、`test_design_compose_route.py`、`test_editor_ops.py` 和 `test_discfiles.py`，结果为 **256 通过、1 跳过，另有 46 个子测试通过**。后续相关改动单独复验了 Web 后端、刻录、目录和照片路由，结果为 **124 通过、1 跳过，另有 46 个子测试通过**。最终 `python -B -X utf8 -m pytest -n 2 tests/test_secfix.py -q` 为 **7 通过**。[Python 回归日志](<F:/dp-archive/tmp/secfix/pytest-final.log>) · [后端复验](<F:/dp-archive/tmp/secfix/pytest-recheck.log>) · [安全专项](<F:/dp-archive/tmp/secfix/security-final.log>)
- `node --test --test-concurrency=1` 运行除导航之外的全部 54 个 `tests/test_*.mjs` 文件，**67 通过**。`node --test tests/test_flow_navigation_browser.mjs` 单独运行，**1 通过**。在最终代码上复验随盘文件、刻后检查和刻录取消浏览器测试，共 **5 通过**。[Node 全量](<F:/dp-archive/tmp/secfix/node-final.log>) · [导航](<F:/dp-archive/tmp/secfix/navigation-final.log>) · [浏览器复验](<F:/dp-archive/tmp/secfix/node-recheck.log>)
- 用 `python -B -X utf8 -m discprobe compose <作品> --out <标签.npy>` 重跑 `F:/dp-archive/tmp/regress/RESULT.md` 的三份作品。先核对输入 SHA-256，再比较标签 `.npy` 和纹理清单 `.textures.json`。三份作品的两种输出都与归档一致。[命令、输入和完整结果](<F:/dp-archive/tmp/secfix/compose-sha256.json>)

| 历史作品 | 标签 `.npy` SHA-256 |
| --- | --- |
| `fixture-full-disc` | `5ecb94e2e2d0a82a71cfca85fc8e8bf60bf87b640358c08c2b25d4829567cd2c` |
| `work-a37427bb99f56e55` | `12448b74f0b1f209ad3a7681b116145bf3d8b260476cf3973b4bd11ea2ad5f9d` |
| `design-8eb60f75` | `40b9c1eef5d4f3a2ceae2ed7f6a2097ab91f81367b8af47f0783b6f8ce2b6414` |

## 第一轮验证边界

- 第一轮原启动测试因 8765 被已有进程独占而未验收，第二轮已改用动态端口并通过，见上文。照片回归中依赖封存原始 JPG 的可选用例跳过，局域网上传专项使用合成 PNG。
- 介质检查的精度取决于光驱报告。若两张盘的可读字段完全相同且光驱未提供独立介质 ID，软件无法区分。实机刻录、擦除及实体手机未测。
- D 盘开跑和全量回归前均通过 5 GB 空间检查。日志及证据归到 `F:/dp-archive/tmp/secfix/`。
