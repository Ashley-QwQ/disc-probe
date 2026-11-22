# WC 卡交付报告

工作树 `D:/dp-dev/whycal`，分支 `dev/why-calibrate`，基点 `6dec7ab`。提交留在本地分支。

## 按提交

- `21c7976` 写了[中文](docs/why-calibrate.zh.md)和[英文](docs/why-calibrate.md)入门说明。从螺旋上落点的误差讲到为什么会只剩环，再走一遍测量、设计、刻录和看盘。DVD 和数据 CD 的步骤、用盘和估时各有出处。沿用了 README 的 DVD 网格扫描图。
- 同一提交给新手引导、刻完页「看不到图？」、彩色指南、成像教程和刻后检查单加了对应语言的链接。离线版由现有生成器产出，教程和网格图可在本机打开。仓库 Markdown 的出处链接可点，离线版按原生成器的规则保留未随包文档的出处名称。`burn-no-picture` 的依据增加了本文，手册字段继续指向可直接照做的检查单。
- `30d0b7c` 把用于拍照测量的标靶和刻录后抽样回读的意思写进中英正文，并同步离线页。
- 本报告单独提交。中英文正文和帖子按 humanizer 的 File mode 做了末遍修订。

## 验收

开跑前 D 盘可用约 122.8 GB，全量 Node 测试前约 122.6 GB。测试临时目录使用 D 盘完整路径，浏览器为脚本驱动的无头 Edge，服务和 CDP 走临时回环端口。Disc Lab 目录和测试镜像已清理。

| 命令或检查 | 结果 |
| --- | --- |
| `python -B -X utf8 tools/render_learning_guide.py` 及 `--check` | 7 页、6 张配图通过生成一致性检查。 |
| `python -B -X utf8 D:/dp-dev/tmp/whycal/verify_docs.py` | 核对 40 个新正文引用、6 个 Markdown 入口和 42 个离线 HTML 引用。中文文件可按 UTF-8 读取，无问号串或替换字符。 |
| `python -B -X utf8 tools/refresh_troubleshoot_citations.py` 及 `--check` | 通过。与基点逐项比较，排错数据只有 `burn-no-picture` 新增一条出处。这条出处也会随 `troubleshoot --json` 返回。 |
| `python -B -X utf8 tests/score_troubleshoot.py` | 45 条报错、46 条症状全部命中第一名。 |
| `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/whycal/temporary-files-for-wc-card-verification/pytest-acceptance -q tests/test_troubleshoot.py tests/test_web_guidance.py tests/test_afterburn.py tests/test_checkburn.py tests/test_web_security.py` | 39 项通过。 |
| `python -B -X utf8 D:/dp-dev/tmp/whycal/verify_entries.py start-guide` 和 `afterburn-checklist` | 两个入口各核对中英文。链接可见并指向对应离线页，文章和网格扫描图均为 HTTP 200，流程表各有四步。 |
| `python -B -X utf8 tools/check_grating_cli_defaults.py D:/dp-dev/tmp/whycal/temporary-files-for-wc-card-verification/default-parity 6dec7ab` | 冻结时钟，用 Disc Lab 比较中英文 `image`、`burn`、`info` 执行与帮助的 12 组标准输出和标准错误，全部逐字节相同。`image` 测试 ISO 的 SHA-256 均为 `82f466cba46a94a8ae616c353d539c73f16c4b959dba0c75e764f6b2d0629692`。 |
| `git diff --check` | 通过。 |

`python -B -X utf8 tests/run_webguide_checks.py` 扫完 `tests/` 下符合路径限制的全部 60 个 `test_*.mjs`，首轮 58 个通过，包括 `test_start_guide.mjs` 和 `test_flow_navigation_browser.mjs`。

- `test_afterburn_browser.mjs` 首轮重新打开大厅时没能加载 `design.js`。在工作树里设 `BROWSER_WAIT_MS=90000` 后原样复验，24 项检查通过。另跑的入口截图脚本首轮完成 DOM 检查后遇到 Edge 临时目录锁，等 Edge 退出再清理后复验通过。
- `test_review_library_newwork.mjs` 在工作树首轮和重跑都卡在「关闭预设导入后批次字段应保持空白」。用 `D:/dp-dev/tmp/whycal/review_at_base.py` 和同一脚本加 `current`，在同一个隔离目录分别跑基点和本分支的网页文件，两次完整通过。这次未定位工作树与隔离跑法结果不同的原因。算上定向复验，60 个 Node 文件各有一次通过记录。

原始结果和复验日志在 `D:/dp-dev/tmp/whycal/logs/`，全量结果见 `node-results.json`。

## 截图与帖子

- 新手引导入口 `D:/dp-dev/tmp/whycal/screenshots/start-guide.png`，1440 × 1000。
- 刻完页检查单入口 `D:/dp-dev/tmp/whycal/screenshots/afterburn-checklist.png`，1440 × 1120。
- Discord 草稿 `D:/dp-dev/tmp/whycal/discord-post.md`。按 UTF-16 代码单元计，中文 549、英文 1610，两条均低于 2000。草稿未发送。

## 未测与交接

DVD 和 CD 实盘刻录、手机拍摄及完整发布包未测。正文里的盘数和时间引自现有 README 和网页引导，网格图是既有扫描。没有找到可直接配成同图前后对照的名义预设失败照。本卡未使用 8765 端口。

请 Claude 转达两条草稿的位置，发帖由发布侧安排。发布时随网页带上两份生成的 `why-calibrate` HTML 和 `learn/media/grid_lines_zoom.jpg`。改正文后跑 `tools/render_learning_guide.py` 同步离线页。合入时若根目录的报告冲突，基点的社区提示卡报告仍可从 `6dec7ab:CARD_REPORT.md` 取回。

STATUS: DONE
