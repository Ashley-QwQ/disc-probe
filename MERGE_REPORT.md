# AM · BG 合并与 alpha 验收

合并分支为 `dev/alpha-merge`。刻录、擦除和换盘验收使用 Disc Lab 虚拟光驱及独立回环端口。8765 验收前后的监听 PID 均为 31360。提交仅在本地合并分支，`dev/1.0.0` 仍指向 `a7b5fbf`。

## 提交

- `4011a8c` 合并 BG。保留前七张卡的结果和 BG 两个原始提交。BG 验收报告归档到 [burn-gates-report.md](docs/cards/burn-gates-report.md)。
- `4fcd888` 修复验收发现的整合问题。刻后检查延迟加载数值依赖，CLI 可在未安装 NumPy 时创建参数解析器。补齐命令帮助翻译和引用行号。390 像素的手动对齐页把顶部位置和高度计算改为共享同一个变量，英文评分恢复可见。测试夹具对齐几何覆盖、已写末端、异批令牌、异步返回和虚拟光驱的实际行为。
- `1c2335d` 补齐 `geo --resume` 和实时 JSON 事件的中文帮助，并刷新受影响的帮助引用行号。

## 冲突

| 文件 | 处理 |
| --- | --- |
| `discprobe/__main__.py` | `cmd_image` 同时导入 `imagecheck` 和 `burn_gate`，保留半径检查、镜像抽样验证和测量 MID 附档。 |
| `discprobe/api.py`、`discprobe/web/gui.json` | API 保持 1.2。核心和 GUI 清单均有 `geo-coverage`、`photo-manual-alignment`、`checkburn`、`burn-preflight`。 |
| `discprobe/calibrate.py` | 子进程传递盘身份环境、`MEASUREMENT_ENV` 和可用的 `EXPECTED_MID_ENV`，支持显式的 `allow_other_batch`。CLI 同时保留续测与放行参数。 |
| `discprobe/web/home/calibrate.js` | 保留 BG 症状直显、重新检查、`burnGate` 和 `measurementGateText`。批次默认 MID 在 `...args` 前面，调用方可覆盖。续测继续传 `args.resume` 并清空 `avoid_mm`。保留工作返回文案 `returnLabel`、保存失败回到结果、任务时钟和测点事件。 |
| `discprobe/web/home/design.js` | `toBurn()` 先拦截「稍后再定」，再走 BG 的 `checkBurn` 和 `confirmBurn`。移除旧的 `inspectDisc()` 检查链。确认继续绑定作品镜像、盘身份和所同意的 MID。 |
| `tests/test_gui_handshake.mjs`、`tests/test_gui_handshake.py` | 两侧分别验证四项能力及老 core 单独缺每一项时的结果。同时保留原有必需能力、`works` 和版本测试。 |
| `tests/test_photo_wire.mjs` | 同时提供 `jobClock`、`hasCapability` 和 `burnPreflight`。 |
| `tests/test_photo_wire_browser.mjs` | 保留时钟、标定画面计时和手动对齐路由；给刻录步骤加上 BG 所需的 `burnInspection`。 |
| `tests/test_review_library_newwork.mjs` | 等待目标盘库的路由、导航完成和精确批次，再点击返回。返回表单和再次进盘库时均等目标路由就绪。 |

`CARD_REPORT.md` 在合并时取 ours，Git blob 与 `a7b5fbf` 相同。复核了 MS 合并点 `a140709` 和 NS 合并点 `1dff34b`。标定保存后的自动 `photoStamp` 仅在非 `manual-*` 来源显示，下一步仍采用 RWB 的 `returnLabel`。拍照和盘库夹具的两边行为在合并后均有通过记录。

## 测试

- JavaScript 全部 59 个 `tests/test_*.mjs` 文件，按文件执行 `node --test --test-concurrency=1`。37 个非浏览器文件、22 个浏览器文件。首轮 56 通过、3 失败，定向复跑后 59 个文件、83 项均通过。另跑 `tests/test_burn_page.cjs`，通过。旧的 DOM 导出夹具由脚本改用 CDP。Disc Lab 浏览器用例只启用虚拟光驱。当前 worktree 名称未触发预设静态路径保护。 [首轮日志](D:/dp-dev/tmp/alphamerge/logs/js-browser/) · [复验日志](D:/dp-dev/tmp/alphamerge/logs/js-retry/) · [刻录页单测](D:/dp-dev/tmp/alphamerge/logs/js-cjs/test_burn_page.log)
- `pytest -n 3` 覆盖 `tests/` 下的测试。首轮 1,326 通过、14 失败、1 跳过。14 个失败都在 `pytest -n 2` 的 99 项定向复验中通过，另做了 31 项核心复验。按用例合计，1,340 项有通过记录，1 项因缺少 `calib-simple` 研究夹具跳过。原图目录检索的一个用例因路径约束在收集时排除。冻结读取器的已存结果复算仍执行。 [全量日志](D:/dp-dev/tmp/alphamerge/logs/pytest.log) · [99 项复验](D:/dp-dev/tmp/alphamerge/logs/pytest-target.log) · [31 项核心复验](D:/dp-dev/tmp/alphamerge/logs/pytest-final-core.log)
- 另以 `pytest -n 3` 跑根目录收集范围中的 `disclab/tests/` 和 `tools/synth_photo_test.py`，162 通过、0 失败、1 跳过。跳过项需要 `DISCLAB_A3_SOURCE`，工具脚本只通过收集。两批 Python 测试合计 1,502 项有通过记录，2 项跳过。 [Disc Lab 日志](D:/dp-dev/tmp/alphamerge/logs/pytest-disclab.log)
- `python -B -X utf8 -m discprobe selftest` 最终从仓库根目录运行，退出码 0，日志记录 1,464 条通过、0 条失败。初跑的工作目录漏了相对路径夹具，后续检查找出了续测、实时事件、手动对齐和刻后只读检查的中文帮助缺口。修复后完整自检通过。 [自检日志](D:/dp-dev/tmp/alphamerge/logs/selftest-final.log)

Python 首轮失败及处置如下。

| 数量 | 失败项 | 原因和复验 |
| ---: | --- | --- |
| 1 | `test_pending_geo_uses_recorded_end_even_if_drive_reports_full_capacity` | RWA 可把初始 98% 的范围扩到已写末端。保留初始范围断言，并检查扩展范围和所有读取均在已写数据内。 |
| 1 | `test_document_preview_http_cli` | 拒绝跨源请求的用例收到 WinError 10053。代码沿用原样，同一用例复验通过。 |
| 1 | `test_pitch_refit_retains_completion_convention` | NS 的新命令在参数解析时提前导入 NumPy。数值探测移到执行刻后检查时才导入。 |
| 5 | `test_calibrate_exports_whole_capacity` | 旧容量夹具没有 RWA 要核对的实测半径，在夹具补齐覆盖范围。 |
| 1 | `test_finding_2_burn_grant_matches_one_job` | BG 拒绝换盘后的旧令牌时新增 `disc_changed`。断言仍要求 403 和原错误，并验证新增代码。 |
| 4 | `test_single_instance.py` | 外层禁用光驱的环境变量把虚拟盘也屏蔽了。仅在虚拟盘夹具去掉该变量。 |
| 1 | `test_citations_and_bilingual_data` | 各卡合入改变了引用行号。用仓库脚本按原关键词重新定位。 |

JavaScript 首轮中，刻后检查遇到后台读盘占用，未改该路径，串行复跑通过 24 项。导航用例在返回完成前点击盘库，增加路由就绪等待后通过。往期作品用例等待 16 个样本进入列表时超时，未改该路径，串行复跑覆盖四种宽度和两种主题并通过。额外运行拍照浏览器用例的截图断言时，英文窄屏读数超出纸面，修复后八种截图组合和交互断言均通过。 [对齐复验](D:/dp-dev/tmp/alphamerge/logs/js-photo-verified/test_photo_wire_browser.log)

## 逐字节对照

`compare_defaults.py` 从 `a7b5fbf` 提取基线，与合并版使用相同输入、路径和固定时钟运行。虚拟刻录还固定了 Disc Lab 的写入抖动种子。 `photo` 使用合成照片，已知的数值库运行时警告在两边均关闭。 [运行脚本](D:/dp-dev/tmp/alphamerge/compare_defaults.py) · [逐项哈希](D:/dp-dev/tmp/alphamerge/logs/parity/verified.json)

- 中英文 `burn`、`info`、`photo` 的正常运行各两组。退出值、标准输出、标准错误相同，`photo.json` 相同。
- `image` 和 `disexport` 以 CD/DVD 分别运行自动照片修正和无照片，共四组。标准输出、标准错误、四个 ISO、四份 ISO 附档和四份预设的 SHA-256 相同。同一盘种的自动修正与无照片两份 ISO 的哈希不同。比较结束后删除生成的大 ISO。
- 有测量 MID 的短 DVD 对照中，ISO 和命令输出相同，附档唯一新增字段为 `calibration_mid: "RITEKF1"`。双语 `burn --help` 和 `photo --help` 随新增参数变化。双语 `info --help` 和 `image --help` 相同。共 18 组完全相同、5 组有预期字段或帮助变化。

## 截图与转达

`capture.mjs` 通过无头 Edge 和 CDP 生成 48 张主图。新建作品、编辑器、预览、刻录、标定和刻完页各 8 张，覆盖 1440×900、390×844、纸色、夜色、中文和英文。另有 4 张窄屏异批确认细节和 8 张手动对齐截图。新建从实际虚拟盘读取批次，在编辑和预览验证留空拦截。刻录和标定用小镜像进入实际页面和预检，作品异批确认后虚拟写入并进入刻完页，96 个抽样块全部匹配。逐张核过尺寸和页面状态，预览等待盘面绘制后取图。 [截图目录](D:/dp-dev/tmp/alphamerge/shots/) · [主图记录](D:/dp-dev/tmp/alphamerge/shots/capture.json) · [回读记录](D:/dp-dev/tmp/alphamerge/logs/capture-report.json)

请 Claude 转达审查人。390 像素截图中，新建、预览和刻录入口出现横向滚动，文档宽度为 437 像素，主面板仍在视口横向范围内。窄屏的异批确认另外保存了滚动到提示处的细节。视觉取舍留给审查。老 core 缺各项能力的握手已测，缺 `burn-preflight` 的老 core 实际刻录未测。实体光驱、实体写入及原图目录检索未测。合入 `dev/1.0.0` 仍待用户点头。

核对了 `CARD_REPORT.md`、`discprobe/pcal.py` 和 `evidence/atlas/*.py` 与基线一致。D 盘开跑及全量测试前均超过 5 GiB。已清理成功场景的 Lab、浏览器配置、ISO 和基线副本，保留日志、截图、哈希和失败现场。

STATUS: DONE
