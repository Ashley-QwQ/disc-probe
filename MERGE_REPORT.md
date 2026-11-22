# AM2 · alpha 集成与验收

集成分支为 `dev/alpha-merge-2`，基点 `e752ef5`。SN 包含 LM，五次合并带入六张卡。`dev/1.0.0` 仍在 `e752ef5`。SR 未合入，所有提交留在本地集成分支。

## 提交

| 提交 | 内容 |
| --- | --- |
| `589e0a8` | 合入 SN 和其祖先 LM。归档[盘库导航](docs/cards/shelf-nav-report.md)和[盘库管理](docs/cards/library-manage-report.md)。 |
| `6de68f4` | 合入 CN。归档[彩色刻图新手走查](docs/cards/colour-novice-report.md)。 |
| `bae6441` | 合入 TE，统一 API 版本与能力。TE 的分支提交不含卡片报告，归档该卡工作目录交付的[模板导出报告](docs/cards/template-export-report.md)。 |
| `e12cb7f` | 合入 WC。归档[为什么要标定](docs/cards/why-calibrate-report.md)。 |
| `ab7f37a` | 合入 FS。归档[传真回执](docs/cards/fax-slip-report.md)。 |
| `9740392` | 增加三项新能力各自缺席时的握手断言，刷新排错引用。 |
| `a1fb7ec` | 重建 Probe 和 Lab 的标题字体子集及生成样式，补齐 WC 新增的「漩」字。两份子集相同，各 777,448 字节，覆盖 3,808 个码位。Adobe 官方发布包及提取的 Heavy OTF 均与品牌卡的 SHA-256 相符。 [生成记录](D:/dp-dev/tmp/alphamerge2/logs/title-font-subset.json) |

## 冲突与重叠

| 位置 | 处理 |
| --- | --- |
| `discprobe/data/troubleshoot.json` | SN 与基点在三个条目的 `sources` 行重叠，关键词相同，先保留基点行号，再合入 WC 的排错内容。最终用 `python tools/refresh_troubleshoot_citations.py` 更新 29 处，随后的 `--check` 退出码 0。 [刷新日志](D:/dp-dev/tmp/alphamerge2/logs/citations-refresh.log) |
| `discprobe/api.py`、`discprobe/web/gui.json`、`docs/API_VERSIONING.md` | API 取 1.5。核心能力和 GUI 可选能力同时登记 `library-management`、`library-batch-details`、`grid-templates`。版本文档将 TE 的独立 1.4 条目标为随本分支 1.5 发布。 |
| `design.js`、`design.css`、`design/editor-*.mjs` | 自动合并后检查入口与实际页面。CN 的 DVD 彩色图默认入口、首次说明和手动配色折叠仍在右侧；TE 的三档下载与返导在图层栏，老 core 可继续使用原模板入口；SN 的批次选择继续给编辑器传递所选批次。 |
| 新手引导、刻完页 | WC 的中英文说明同时接入引导和刻后检查单。浏览器用例走过两处页面，刻完页截图另核对两条相应语言的说明链接均返回 HTTP 200。 |
| 根目录 `CARD_REPORT.md` | 每个合并点使用 `e752ef5` 的 blob `aceed48298149378bf1960b7093057dfa6b4a947`，六份交付报告另归档。 |

## 测试

- `python -m pytest -n 3` 首轮收集 1,371 项，1,369 通过、1 失败、1 跳过，耗时 8 分 25 秒。唯一失败为 `test_title_font_covers_all_interface_chinese_and_level_one` 缺「漩」。重建后用 `pytest -n 2` 复验品牌、握手、排错引用、网页引导及 Disc Lab 打包，33 项通过。第一轮的失败项目已转为通过，主测试范围合计 1,370 项有通过记录。手动照片对齐有一条 NumPy 空切片警告，该用例通过。 [全量日志](D:/dp-dev/tmp/alphamerge2/logs/pytest.log) · [33 项复验](D:/dp-dev/tmp/alphamerge2/logs/pytest-target.log)
- Disc Lab 的 `disclab/tests` 与 `tools/synth_photo_test.py` 使用 `pytest -n 3`，162 通过、1 跳过。直接模型校对用例需要 `DISCLAB_A3_SOURCE`。工具脚本参与收集。 [Disc Lab 日志](D:/dp-dev/tmp/alphamerge2/logs/pytest-disclab.log)
- 全部 `tests/test_*.mjs` 用 `node --test --test-concurrency=1` 逐文件执行。首轮 60 通过、1 失败，往期作品用例等待 16 件夹具进入列表时超时。串行复验覆盖两套主题、四种宽度、滚动和焦点，原断言通过。字体重建后品牌浏览器和标题度量两项复验也通过。共 61 个文件、90 项通过。三种独立缺失能力场景通过 Python、JavaScript 和 Edge 的握手检查。 [首轮日志](D:/dp-dev/tmp/alphamerge2/logs/js-all/) · [复验日志](D:/dp-dev/tmp/alphamerge2/logs/js-retry/)
- `python -B -X utf8 -m discprobe selftest` 首轮仅报标题子集缺字。重建后从仓库根目录完整复跑，1,474 条 `ok`、0 条失败，退出码 0。 [首轮](D:/dp-dev/tmp/alphamerge2/logs/selftest.log) · [终轮](D:/dp-dev/tmp/alphamerge2/logs/selftest-final.log)
- 模板测试实际生成三种分辨率和 DPI，20 µm 档的标记返导位置误差 0 像素。W245 浏览器测试通过 18 条交互和合成检查，四组静止画布的哈希相同。 [模板用例](tests/test_template_grid.py) · [W245 日志](D:/dp-dev/tmp/alphamerge2/logs/js-all/test_editor_w245_browser.log)
- 原图命令复算未测。两处默认候选目录内经排除项过滤后未找到允许读取的原图。补查跳过原因时，把输入指向隔离空目录，pytest 报 1 跳过。该次补查由 pytest 按测试名自动生成的空临时目录命中了禁入词，并随测试清理。这是执行偏差，已撤掉补跑路径。原图未读取，已存投票复算通过。主全量的另一个跳过项是 `calib-simple` 夹具。 [跳过记录](D:/dp-dev/tmp/alphamerge2/logs/pytest-source-photo.log)

## 默认输出与作品库

`python -B -X utf8 D:/dp-dev/tmp/alphamerge2/compare_defaults.py all` 与 `core-artifacts` 以 `e752ef5` 为基线，使用同一输入、输出路径、固定时钟和虚拟盘种子。29 组对照退出码均为 0，标准输出和标准错误逐字节一致。10 组是五条命令的中英文帮助。成功场景同时比较了中英文刻录日志、读盘 JSON、合成照片 JSON、CD/DVD 的整盘 ISO 和附档、预设 JSON，以及含已知测量 MID 的短 DVD。两种照片修正设置各自与基线一致，同一盘种的自动修正和无照片 ISO 哈希不同。整盘 ISO 只保留哈希。 [回归脚本](D:/dp-dev/tmp/alphamerge2/compare_defaults.py) · [逐项哈希](D:/dp-dev/tmp/alphamerge2/logs/parity/comparisons.jsonl)

作品库 `D:/dp-dev/integ/works` 验收前后均为 7 件作品、66 个条目，逐项核对文件时间、大小和 SHA-256 一致。测试和截图使用 D 盘上的独立状态目录，`TEMP` 和 `TMP` 指向长路径。开跑前和全量测试前的可用空间均高于 5 GiB。成功场景的临时镜像、浏览器配置、字体源包和基线副本已清理。 [验收前快照](D:/dp-dev/tmp/alphamerge2/logs/works-before.json) · [验收后快照](D:/dp-dev/tmp/alphamerge2/logs/works-after.json)

## 截图与审查

64 张截图，每个界面 8 张。范围为大厅、盘库批次列表、盘库批次详情、新建页、编辑器彩色面板、模板导出、刻完页和传真回执。每页覆盖 1440 × 900、390 × 844、纸色与夜色、中文与英文。无头 Edge 通过 CDP 走实际页面，刻完页使用隔离工作区的保存记录，传真回执使用本地 404 夹具。模板截图打开 5 µm 档，显示 24,000 × 24,000 和单层 2.15 GiB 提示。64 张均核过尺寸、SHA-256 和画面内容对应的 DOM 状态。 [截图目录](D:/dp-dev/tmp/alphamerge2/shots/) · [逐张记录](D:/dp-dev/tmp/alphamerge2/shots/capture.json) · [截图核验](D:/dp-dev/tmp/alphamerge2/logs/capture-check.json)

请 Claude 转达审查人。390 像素的大厅、新建页和传真回执各四个组合，文档宽度为 437 像素。批次详情在窄屏展开后滚动到详情处取图。视觉取舍留给审查。实体光驱、实体写入、原照片复算及传真外网源未测。集成分支是否合入 `dev/1.0.0` 待用户决定。

`git diff --check` 通过。核对 `discprobe/pcal.py`、`evidence/atlas/*.py` 和根目录 `CARD_REPORT.md` 的基点差异为空。本机服务使用独立回环端口。 [验收数字汇总](D:/dp-dev/tmp/alphamerge2/logs/verification-summary.json)

STATUS: DONE
