# 卡 AB 验收报告

工作树为 `D:/dp-dev/secfix`，分支为 `web/sec-fixes-20261118`，基点为合入卡 AA 第二轮的 `ce30590`。

## 代码提交

`698dfdb` · Bind local file exports and disc writes to one-time permits

| 审查条目 | 改动与代码位置 | 专门验收 |
| --- | --- | --- |
| #1 随盘目录授权 | [作品导入和 ISO 导出](discprobe/web/home/design.js)、[随盘文件面板](discprobe/web/home/design/disc-files.mjs)、[清单摘要](discprobe/discfiles_api.py)和 [Web 后端](discprobe/webui.py)。导入和保存作品只携带文件数量、大小和放置位置。使用者在本机重新输入目录路径、检查并确认清单后，后端签发有效期 15 分钟的单次授权。授权绑定目录和文件树清单摘要。导出前重新检查文件树和布局指纹，图像子进程沿用原有的布局指纹校验。 | `finding_1_directory_requires_one_export_confirmation` 用浏览器打开带目录绑定的合成作品，扫描直接导出镜像的 ISO 9660 目录树和整个文件，均无夹具。重新选目录、查看清单、确认后导出，Joliet 树和镜像数据均查到夹具，再次导出要求重新确认。`test_finding_1_backend_requires_the_reviewed_directory_for_one_export` 验证无授权、替换目录、修改清单及重复提交都被后端拒绝。 |
| #2 刻录与擦除许可 | [签发、核验和启动](discprobe/webui.py)，并接入[设计页](discprobe/web/home/design.js)、[校准页](discprobe/web/home/calibrate.js)和[刻后检查页](discprobe/web/home/afterburn.js)现有确认。凭据经本机回环 POST 签发，30 秒内提交且一次消费。签发和启动时核对光驱的介质报告，核对介质类型、配置、批号、空白与可擦写状态等字段。镜像身份采用规范化路径、文件大小和纳秒修改时间。普通刻录、独立擦除、先擦后刻、带镜像校准及擦除后校准的许可分别绑定。 | `test_finding_2_burn_grant_matches_one_job` 用虚拟光驱核对串用动作、换光驱、换镜像、原路径镜像变化、介质报告变化及重放的 HTTP 403 和错误文字。对应动作的正确许可均可启动。模拟流程验证了刻录取消、擦除后重刻和刻后检查。 |
| #6 作品内容渲染 | [导入、图层列表及旧版影调面板](discprobe/web/home/design.js)、[选区列表](discprobe/web/home/design/editor-controls.mjs)。图层 ID 限定为 ASCII 字母、数字、下划线和连字符，长度 1–64。导入时为不合规或重复 ID 分配新值，并重映射图层填充引用。检查并修复的模板插值包括图层行的 `data-id`、`id`、`aria-controls`，选区行的 `data-mask-id`、`data-delete-mask`，旧版影调数值框及自动色阶文案，以及旧版随盘文件计数。图层名经过转义，文件名单使用 `textContent`。 | `finding_6_layer_id_and_text` 在静音 Edge 中导入含标记字符的 ID 和图层名。重新生成的 ID 符合白名单，填充引用与 DOM 属性一致，原名称完整显示为文本，监视标记节点的 `window` 钩子调用数为 0。 |
| #3/#4 局域网 | [HTTP 监听与请求校验](discprobe/webui.py)。Host 必须带实际端口，只接受回环地址、`localhost` 和该连接实际到达的本机私有 IPv4。头部阶段最多 24 条连接，局域网来源最多 16 条，给本机桌面预留 8 条。3 秒请求头总期限覆盖分段到达的请求，正常认证完成后释放这部分容量。 | `test_finding_3_only_listener_hosts_before_authorization` 在两种监听模式下检查伪造 Host。`test_finding_4_partial_headers_expire_and_leave_room_for_a_normal_request` 同时打开 6 条未完成头部的本地连接，正常请求在期限内返回 200，随后慢连接到期。`test_finding_4_remote_slots_cannot_take_the_loopback_reserve` 验证限额和本机保留。`test_finding_3_4_phone_page_and_upload_on_the_lan_listener` 用实际局域网地址打开手机页，上传合成 PNG，并在桌面列表读到该照片。 |

## 回归验收

- `python -B -X utf8 -m pytest -n 2` 运行 `test_secfix.py`、`test_webui.py`、`test_burner.py`、`test_photo.py`、`test_single_instance.py`、`test_webui_catalog.py`、`test_works.py`、`test_design_compose_route.py`、`test_editor_ops.py` 和 `test_discfiles.py`，结果为 **256 通过、1 跳过，另有 46 个子测试通过**。后续相关改动单独复验了 Web 后端、刻录、目录和照片路由，结果为 **124 通过、1 跳过，另有 46 个子测试通过**。最终 `python -B -X utf8 -m pytest -n 2 tests/test_secfix.py -q` 为 **7 通过**。[Python 回归日志](<F:/dp-archive/tmp/secfix/pytest-final.log>) · [后端复验](<F:/dp-archive/tmp/secfix/pytest-recheck.log>) · [安全专项](<F:/dp-archive/tmp/secfix/security-final.log>)
- `node --test --test-concurrency=1` 运行除导航之外的全部 54 个 `tests/test_*.mjs` 文件，**67 通过**。`node --test tests/test_flow_navigation_browser.mjs` 单独运行，**1 通过**。在最终代码上复验随盘文件、刻后检查和刻录取消浏览器测试，共 **5 通过**。[Node 全量](<F:/dp-archive/tmp/secfix/node-final.log>) · [导航](<F:/dp-archive/tmp/secfix/navigation-final.log>) · [浏览器复验](<F:/dp-archive/tmp/secfix/node-recheck.log>)
- 用 `python -B -X utf8 -m discprobe compose <作品> --out <标签.npy>` 重跑 `F:/dp-archive/tmp/regress/RESULT.md` 的三份作品。先核对输入 SHA-256，再比较标签 `.npy` 和纹理清单 `.textures.json`。三份作品的两种输出都与归档一致。[命令、输入和完整结果](<F:/dp-archive/tmp/secfix/compose-sha256.json>)

| 历史作品 | 标签 `.npy` SHA-256 |
| --- | --- |
| `fixture-full-disc` | `5ecb94e2e2d0a82a71cfca85fc8e8bf60bf87b640358c08c2b25d4829567cd2c` |
| `work-a37427bb99f56e55` | `12448b74f0b1f209ad3a7681b116145bf3d8b260476cf3973b4bd11ea2ad5f9d` |
| `design-8eb60f75` | `40b9c1eef5d4f3a2ceae2ed7f6a2097ab91f81367b8af47f0783b6f8ce2b6414` |

## 验证边界

- `test_default_port_falls_back_and_reuse_keeps_the_registered_port` 的夹具需要自行占用 8765。本机已有进程独占此端口，按原夹具执行时得到 `WinError 10013`，因此后续相关回归排除了该用例。使用临时端口的 `test_force_kill_recovery_and_occupied_port` 已通过。照片回归中依赖封存原始 JPG 的可选用例跳过，局域网上传专项使用合成 PNG。
- 介质检查的精度取决于光驱报告。若两张盘的可读字段完全相同且光驱未提供独立介质 ID，软件无法区分。实机刻录、擦除及实体手机未测。
- D 盘开跑和全量回归前均通过 5 GB 空间检查。日志及证据归到 `F:/dp-archive/tmp/secfix/`。
