# GC 任务卡报告

分支 `dev/geo-checkpoint`，基点 `4f042ca`。验证使用 Windows 上的模拟光驱和 Disc Lab。实盘记录用于离线重放。
基点的社区提示卡报告仍可通过 `git show 4f042ca:CARD_REPORT.md` 查阅。

## 提交

- `b8a0180` 在 DVD 和 CD 的角度阶梯里，每接受一级就把 `events.csv` 和 `targets.csv` 写到同目录临时文件，刷盘后原子替换，再更新 `partial.json`。标记记录级数、更新时间、准确的目标值和原始读数的有效字节数。完成时先提交数据，再发布 `summary.json` 并清理标记。标定的 geo 子进程走同一条路径。
- `b8a0180` 让 `geo --resume` 校验盘、光驱和已保存的相位后继续原阶梯，写到新目录并保留原始读数。部分结果可用 `--reapply` 离线重拟合。盘库把中断列为 `incomplete`，`guide` 显示级数并给出续测命令。
- `aace15e` 更新受改动影响的 165 个故障排查源代码及手册行号。内容和检索规则沿用原样。
- `69bda7d` 保留缺少测量依赖时的安装指引。用模拟缺少 NumPy 的中断目录验证了 `guide`。
- `70a9f90` 修正复拍回归脚本在页面导航和重载时的竞态。轮询允许 DOM 尚未创建，仍要求导航就绪、所选记录恢复后才继续。

## 验收

- `python -X utf8 -m pytest -n 2 -q -rP --basetemp D:/dp-dev/tmp/geocheckpoint/pytest-checkpoint tests/test_geo_checkpoint.py` 通过 4 项。测试把子进程停在指定检查点完成后的第一个位置，再调用 Windows `TerminateProcess`。DVD 第 1 级留下 858 条完整读数，续测到 22 级。DVD 第 8 级留下 1,194 条，续测到 22 级。CD-DA 第 8 级留下 2,501 条，续测到 36 级。第 8 级的两份记录都用原始读数离线重拟合。另测 `calibrate` 的 geo 子进程第 3 级被终止，父进程报告中断并保留三组读数。[专项日志](D:/dp-dev/tmp/geocheckpoint/pytest-checkpoint.log)
- 相关 pytest 使用 `python -X utf8 -m pytest -n 2 -q -rA --basetemp D:/dp-dev/tmp/geocheckpoint/pytest-final`，范围为 `tests/test_geo_*.py`、`test_read_completion.py`、`test_library_manage.py`、`test_webui.py`、`test_webui_catalog.py`、`test_webui_recovery.py`。通过 145 项和 42 个子用例。新增 CD-DA 分支纳入上述专项。另跑 `tests/test_troubleshoot.py`，通过 5 项。[回归日志](D:/dp-dev/tmp/geocheckpoint/pytest-final.log)
- `python -X utf8 -m discprobe selftest` 退出码 0，日志含 1,490 条通过记录，末尾为 `all checks passed`。[自检日志](D:/dp-dev/tmp/geocheckpoint/selftest-final.log)
- `python -X utf8 D:/dp-dev/tmp/geocheckpoint/run_mjs.py` 逐一用 `node` 执行 `tests/test_*.mjs`，最终 63/63 通过。单项重跑修正了 Disc Lab 的虚拟驱动枚举环境。复拍首轮超时，延长测试时限后发现导航竞态，再修复测试等待条件并验证两个场景全部通过。复拍整盘已清理，保留 SHA-256、300 个抽查样本的验证记录、8 张截图和对准箭头预览。[汇总](D:/dp-dev/tmp/geocheckpoint/mjs-final-status.json) [复拍日志](D:/dp-dev/tmp/geocheckpoint/mjs-reshoot-final-logs/test_reshoot_browser.log)
- 普通完成路径用基点和本分支分别运行 `geo --sim cav --seed 7 --out D:/dp-dev/tmp/geocheckpoint/byte-sim`。测试驱动仅把每次运行的 `fit.elapsed_s` 输入固定为 4 秒。两次命令参数相同，CSV 与 JSON 共 3 个文件直接按二进制比较，全部相等。[计时夹具](D:/dp-dev/tmp/geocheckpoint/byte_proof.py)
- 真实记录取自 SysWOW 首轮的 `geo-D-20261123-100710`。基点和本分支各运行一次 `python -X utf8 -m discprobe geo --reapply RUN --completion-sectors 16 --out NEW`，均从原始读数重拟合，得到 `u=179979.43732607`、`v=5.5373905639`。三个输出文件逐位相等，六组对照的字节数和 SHA-256 见日志。[二进制对照日志](D:/dp-dev/tmp/geocheckpoint/byte-compare.log)

## 边界和待审查事项

- 最后一条已提交的检查点是恢复边界。进行中的一级、阶梯结束后的加密探测以及末次复核，可能需要重读。离线拟合需要至少三级。Blu-ray 默认的 CLV 按区测量沿用现有流程。真实断电、Linux 强杀和实物续测未测。
- SysWOW 的网页 `events.jsonl` 有 7,206,090 字节和 36,581 条完整记录。其中 36,442 条进度事件占 7,182,182 字节（99.67%）。活跃任务按字节偏移消费该文件，旧接口也支持完整事件历史。活跃时截断或轮换需要同时处理读偏移、游标和上一段文件。若要控制体积，待审查的是完成后压缩归档，或把网页的进度采样从每秒约 4 次降到 1 次。进度采样会影响拾取头动画的更新频率。
- 网页端可使用现有的 `calibration_issue.stopped` 和 `can_resume`。待审查的是网页导览是否要把普通「开始测量」操作改为直接续测，并展示保存时间。任务卡内只交付核心识别。

STATUS: DONE
