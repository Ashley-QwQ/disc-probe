# HS-2 问题检索第二轮交付报告

本轮在 `dev/help-search-20261118` 上把第一轮 `ac60b61` rebase 到本地 `dev/1.0.0` 的 `3bd5c5d`。全量回归期间 `dev/1.0.0` 前进到 `07db2e6`，随后再次 rebase，两次均无冲突。基点包含卡 AA 的合并 `746ec65`。提交仅在本分支。

## 按提交交付

- `5eccaa2` 更新双语条目和回归断言。条目库从 108 条增至 122 条，核对并更新 69 处漂移的引用行号。按卡 AA 的代码改写 Windows 和 Linux 启动器、本机服务状态和停止、实例复用、自动端口和光驱锁。补上照片整体被拒、实物色差、螺旋与整体错位、刻录中断、关浏览器、彩色斜线与放射色带、启动闪退等条目。关浏览器与实际写入中断有各自的条目。
- 本报告提交记录留出题结果、回归和未测范围。第一轮报告保留在线性历史中的 `776fd1a`。

## 验收

| 检查 | 命令与结果 |
| --- | --- |
| 原有题库 | `python -B -X utf8 tests/score_troubleshoot.py`。报错 45/45、口语 38/38，合计 83/83（100%），全部首位命中。 |
| 留出题 | `python -B -X utf8 D:/dp-dev/tmp/helpsearch/r2/score_heldout.py`。前 3 27/35（77.14%），首位 27/35（含正确返回“没找到”）。 |
| 出处及入口 | `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/helpsearch/r2/targeted-pytest tests/test_troubleshoot.py`。5 通过，核对 389 处出处的文件、行号、原文短语及各条目的手册锚点，另验证 JSON、CLI 文本与 HTTP 的社区提示。 |
| 双语 CLI 冒烟 | `python -B -X utf8 D:/dp-dev/tmp/helpsearch/r2/smoke.py`。13 条正向查询首位命中，并验证中文、英文的无结果提示各一次。 |
| 全量 Python | 在 `3bd5c5d` 上的本分支运行 `python -B -X utf8 D:/dp-dev/tmp/helpsearch/r2/run_suite.py python`，底层为 `pytest -n 2`。`6 failed, 1202 passed, 2 skipped in 431.69s (0:07:11)`。 |
| 全量 JavaScript | 在 `3bd5c5d` 上的本分支运行 `python -B -X utf8 D:/dp-dev/tmp/helpsearch/r2/run_suite.py js`，运行 55 个允许路径内的 `test_*.mjs`。65 通过、1 失败、0 跳过，合计 66 项。 |
| 最新基点上的定向复验 | `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/helpsearch/r2/final-provenance tests/test_troubleshoot.py tests/test_night_pool.py`，21 通过。`python -B -X utf8 D:/dp-dev/tmp/helpsearch/r2/run_suite.py js-final-delta test_pastworks_browser.mjs test_pastworks.mjs test_pastworks_works.mjs test_flow_navigation_browser.mjs test_csp_browser.mjs test_review_library_newwork.mjs`，首跑 5 通过、1 失败，失败项单独复跑通过。 |

Python 全量的 6 个失败在未加检索改动的 `07db2e6` 快照上全部复现，JUnit 的用例名和失败消息相同。4 个是 LAN 启动 mock 未被调用，1 个是无效 GUI 参数测试收到 0 退出码，1 个是本机端口 8765 已被占用。详见 `python-base.log`、`python-junit.xml`、`python-base-junit.xml`。JavaScript 全量首跑唯一失败是 `test_csp_browser.mjs` 的回环连接被拒，当前分支单独复跑和 `3bd5c5d` 快照对照均通过。纳入 `07db2e6` 后，往期作品相关的定向复验首跑发现 `test_review_library_newwork.mjs` 的选盘批断言超时，单独复跑和 `07db2e6` 快照对照均通过。详见 `js-retry-csp.log`、`js-base-csp.log`、`js-final-delta.log`、`js-final-retry.log`、`js-final-base.log`。回归未发现本轮新增的可复现失败。

网页引导页测试通过实际页面提交一个无匹配查询，并检查“没找到确定的答案”和社区提问需要的五项资料。两种 CLI 语言也确认列出光驱型号、盘的品牌、刻录速度、读速、完整日志。全量回归启动时 D 盘至少剩余 202.82 GiB。浏览器和服务测试用本机回环与模拟夹具。实盘、真实光驱、Linux 实机行为未测。

可复核记录在 `D:/dp-dev/tmp/helpsearch/r2/`。原题及留出题原始结果为 `score-original.json`、`heldout-score.json`，预期 ID 为 `heldout-expected.json`，出处变更为 `source-line-audit.json`，CLI 实际输出为 `cli-smoke.json`，全量回归为 `python.log`、`js.log`。

## 35 道留出题逐题结果

先查仓库、逐句登记预期 ID，再运行计分。标签判断和条目编写时看过题目，表中保留首次得分。第二次 rebase 前后核对了条目和检索器，内容一致。原题文件的 SHA-256 为 `22c297b14123a196c8b768ad4ac5e6824cff59223405571681fa4ec50f162c7d`。计分前核对了哈希，并检查 35 句在 Unicode 归一化、去首尾空白和忽略大小写后均未与任何症状原文重合。`none` 只有在返回空结果和无匹配提示时才得分。

| # | 原题 | 预期 ID | 实际返回，按排名 | 判定 |
| ---: | --- | --- | --- | --- |
| 1 | 刻完的盘电脑读不出来 | `unreadable-after-burn` | `unreadable-after-burn` | 命中 |
| 2 | 网页一直转圈打不开 | `web-offline` | `web-offline` | 命中 |
| 3 | 拍了好多张都说不行 | `photo-no-adoption` | `photo-no-adoption` | 命中 |
| 4 | 颜色和预览差很多 | `colour-wrong` | `colour-wrong` | 命中 |
| 5 | my picture came out as a spiral | `picture-twisted-lines` | `picture-twisted-lines` | 命中 |
| 6 | 双击开始没反应黑窗口一闪就没了 | `web-startup-error` | `web-startup-error` | 命中 |
| 7 | linux 提示 permission denied /dev/sr0 | `linux-permission` | `linux-permission` | 命中 |
| 8 | 刻到一半我拔了线 | `burn-interrupted` | 没找到 | 未命中 |
| 9 | 图案歪了，和中心对不上 | `picture-placement` | `picture-placement` | 命中 |
| 10 | 图片刻出来整体转了一个角度 | `picture-placement` | 没找到 | 未命中 |
| 11 | 测量盘要刻几张？ | `measuring-disc-count` | `measuring-disc-count` | 命中 |
| 12 | can I reuse the measuring disc for the next picture | `measuring-disc-count` | `measuring-disc-count` | 命中 |
| 13 | 网页上显示光驱正在被另一个窗口使用 | `web-drive-busy` | `web-drive-busy` | 命中 |
| 14 | 提示光驱里的盘和确认时的不是同一张 | `none` | 没找到 | 命中 |
| 15 | 擦盘按钮是灰的点不了 | `burn-erase-media` | `burn-erase-media` | 命中 |
| 16 | 刻录速度选几倍比较好 | `burn-write-speed` | 没找到 | 未命中 |
| 17 | 外圈的图案看不见 | `picture-outer-cropped` | 没找到 | 未命中 |
| 18 | 颜色太暗了几乎看不出来 | `no-picture-visible` | `no-picture-visible` | 命中 |
| 19 | 手机扫码打不开上传页面 | `web-phone-lan` | `web-phone-lan` | 命中 |
| 20 | phone says it cannot reach the computer | `web-phone-lan` | `web-phone-lan`、`web-offline`、`photo-pending` | 命中 |
| 21 | timing 跑了很久没反应 | `timing-timeout` | `timing-timeout`、`web-double-click` | 命中 |
| 22 | geo 说外推超出范围 | `geo-partial-span` | `geo-partial-span`、`web-port-invalid` | 命中 |
| 23 | DIS 里导入预设之后图还是歪的 | `picture-twisted-lines` | `picture-twisted-lines` | 命中 |
| 24 | CD 刻出来全是噪点没有图案 | `cd-burn-layout` | `cd-burn-layout` | 命中 |
| 25 | 蓝光盘能用吗 | `bd-picture-calibrate` | 没找到 | 未命中 |
| 26 | my drive is not in the list | `drive-missing` | `drive-missing` | 命中 |
| 27 | burn failed halfway, is the disc dead? | `burn-interrupted` | `burn-interrupted` | 命中 |
| 28 | 导出 ISO 太大刻不进去 | `iso-capacity` | `disc-close-fails` | 未命中 |
| 29 | 网页里的退出按钮点了没反应 | `web-stop-busy` | `web-stop-busy` | 命中 |
| 30 | 预测图上有一块斜线区域是什么 | `colour-hatched-preview` | 没找到 | 未命中 |
| 31 | 彩色图里有一条一条放射状的条纹 | `colour-radial-bands` | 没找到 | 未命中 |
| 32 | which phone height should I pick | `colour-pose` | `colour-pose` | 命中 |
| 33 | 曲线编辑保存不了，说独立检查不够 | `curve-validation` | `curve-validation` | 命中 |
| 34 | 传真机一直在拨号 | `fax-connection` | `fax-connection` | 命中 |
| 35 | I accidentally closed the browser while burning | `burn-browser-closed` | `burn-browser-closed` | 命中 |

## 未覆盖和审查事项

- 第 14 题要求的“盘和确认时的不是同一张”在 `07db2e6` 的写入前检查里找不到对应错误。当前写入检查只有令牌、空白盘与可擦写状态等条件，见 `discprobe/webui.py:722–734`。该题标为 `none`，未写对应解法。
- 第 8、10、16、17、25、28、30、31 题没有命中预期条目，逐题实际返回见上表。彩色斜线、放射细纹和写入中断均已有出处和正向冒烟证据，留出题反映这些问法仍有召回缺口。
- 卡 AB 和 R1–R6 仍以复核时的本地 `dev/1.0.0` 为准。后续提示如合入，需跟随代码另行更新。本轮条目措辞随代码提交审查。
- 准备本地基点快照时，首次调用 Windows 上的 tar 把盘符 `D:` 当成远程归档名，报主机名解析失败，随后改用 Python 从本地 Git 归档解包。

STATUS: DONE
