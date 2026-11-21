# WR 网页标定重试交付

工作树 `D:/dp-dev/webretry`，分支 `dev/web-retry`，基点 `fa26d74`。

## 提交

- `88bcd63` 提供核心重试分类、速度档位与任务诊断信息。几何续测会复核原来的测点，再优先读失败的测点。网页 API 增加可选的 `measurement-retry` 能力，版本为 1.3。
- `47348e0` 在标定页提供中英双语的建议速度、低速选择、补测与续测。随失败类型显示换 USB 口、供电、保持桌面稳定、检查测量盘和低速重刻的方法。诊断可以复制，也可以下载文本。新增无头 Edge/CDP 命令断言。
- `fb15d27` 修正 CSP 走查的启动竞态。等待大厅完成导航初始化，再从大厅的可见入口进入新作品。原有策略和设计页断言均通过。
- 本报告提交记录验收结果和交接事项。

## 修改前后

在 Disc Lab 虚拟 X: 上取得 8 种核心结果。测量结果回放到真网页，前版固定使用 `fa26d74` 的页面模块。刻录长时间无进度用浏览器夹具保留正在写入的任务。

| 场景 | 前版的出路 | 修改后 |
|---|---|---|
| CAV 有噪声 | 通用重测。Lab 的 DVD 8× 测到 2.554–3.123°，核心建议 3324 kB/s。 | 一键用 3324 kB/s 重测，也可选核心提供的 3324 或 5540 kB/s。 |
| CLV | 显示建议，旧按钮把 kB/s 字符串交给只接受数值的任务接口。 | 用数值提交建议速度；核心判定转速可用后才进入几何。 |
| 转速无法判断 | 通用重测。 | 显示核心给出的建议和排查办法。缺少建议时可按原设定重测。 |
| 介质错误 | 提示换盘，原始信息偏向图案盘。Lab 返回 3/11/00。 | 说明随机测量盘和图案盘分别怎么办，给出 `checkburn` 命令、同盘重试和换盘低速重刻的入口。 |
| 读得慢 | 通用中止说明。Lab 在读到一个区后的限时路径退出。 | 说明读盘超时，保留测量盘、检查连接后重试，可导出诊断。 |
| 几何测点读不稳 | 通用重测，或按已有的空档流程补测。Lab 在 LBA 165152 出错后保留 21 个测点。 | 用原盘、原光驱、原读速继续，优先读失败点；换读速时另测一轮。 |
| 几何覆盖有空档 | RWA 已能补测。Lab 给出 28.63–56.01 mm 的待补范围。 | 保留补测以及范围说明，并提供失败时的诊断信息。 |
| 写入失败 | 换空白盘或擦除后重刻。Lab 在写入约 40% 时注入中断。 | 从替换盘检查回报的档位里选较低写速，然后按原流程确认写入。 |
| 写入长时间无进度 | 有停止刻录控件。 | 明确可以手动停止，待任务结束后换盘选择较低速度。 |

## 验收

- `python -X utf8 -B D:/dp-dev/tmp/webretry/lab_cases.py` 取得 8 组虚拟光驱结果；各场景结束后清理 Lab 目录。慢读用已有的 `timing --max-minutes .001` 触发。基线与修改版用同一套故障输入。
- `node tests/test_web_retry_browser.mjs` 通过。断言 12 条读速重试路径、CD 的数值型 `2822`、2 条 `calibrate --resume` 路径、换盘检查和镜像生成、4× 写速在预检、令牌和任务请求中的一致性，以及复制文本和实际下载的诊断文件逐字一致。
- 无头 Edge/CDP 保存 **72 张截图**，共 36 组前后对照。覆盖纸色和夜色、中文和英文、1440×1000 和 390×844。 [截图目录](<D:/dp-dev/tmp/webretry/shots>)
- `python -X utf8 -B D:/dp-dev/tmp/webretry/run_mjs.py` 运行 `tests/test_*.mjs` 共 60 个脚本。首轮 55 个通过，随后逐项复跑，最终 60 个均通过。照片夹具的模块变量冲突在本分支修复，CSP 夹具见独立提交。文件刻录、往期作品和预设导入的首轮失败在单项复跑通过。 [首轮记录](<D:/dp-dev/tmp/webretry/mjs-suite/summary.json>) · [复跑记录](<D:/dp-dev/tmp/webretry/mjs-suite/rechecks.json>)
- 相关 Python 回归使用 `python -X utf8 -B -m pytest -n 2 -q -p no:cacheprovider --basetemp D:/dp-dev/tmp/webretry/pytest-final tests/test_webui.py tests/test_webui_recovery.py tests/test_webui_catalog.py tests/test_web_security.py tests/test_web_guidance.py tests/test_geo_coverage.py tests/test_geo_integration.py tests/test_geo_unsteady.py tests/test_geo_progress.py tests/test_geo_speed.py tests/test_burn_preflight.py tests/test_burn_cancel.py tests/test_checkburn.py`，161 项及 42 个子测试通过。核心字段调整后，`test_geo_coverage.py`、`test_webui_recovery.py`、`test_webui_catalog.py` 和 `test_web_guidance.py` 的 23 项复验通过。
- 续测回归注入第 7 级的转速异常，确认重开后保留前 6 级并补读第 7 级，源 `summary.json`、`targets.csv`、`events.csv` 字节不变。用同一模拟读盘输入和固定时钟对照 `fa26d74`，默认几何路径的三个输出文件和阶梯日志逐字节一致。 [字节对照](<D:/dp-dev/tmp/webretry/default-bytes.log>)

## 边界与交接

- 真光驱、真实 USB 供电、实体盘的 4× 写入和 Windows CD 外部刻录未测。虚拟短盘的物理外圈仍然缺数据，因此空档截图用于验收续测入口，补测完成由独立虚拟盘用例验证。
- 续测遵守已有的同盘、同光驱、原读速及相位复核。续测条件不足或核心拒绝续测时，可另外检查转速并重新测量。检查测量盘使用核心已有的只读 `checkburn` 终端命令。
- 供 Claude 转达：合入时保留 WR 报告的验收和截图路径。根目录同名报告原先记录社区卡，原内容保存在基点 `fa26d74`。

STATUS: DONE
