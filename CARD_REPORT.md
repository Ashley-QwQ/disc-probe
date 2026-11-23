# P29 合并卡报告

本卡在 `D:/dp-dev/pr29merge` 的 `dev/pr29-merge` 执行，基点为 `95d3289`。

## 提交

| 提交 | 内容 |
| --- | --- |
| `dd10bcf` | 合入 WindowsNoEditor 的 `81b00b7`，保留原作者和原提交。Git 自动合并了 `geo.py`、`selftest.py` 和标定说明，无需手工解决冲突。 |
| `ef4dbc7` | 从评估分支 `dev/pr29-geo-clip` 的 `059cf07` 导入 `evidence/pr29-eval/`，共 122 个文件，目录树内容一致。 |
| `afeb5d7` | 普通 DVD、整块 ECC、纹理环 DVD 和四组 CD 数据盘的跨度检查改用 8 µs 抖动、额外长延迟概率为 0 的模拟读数。DVD 加入各级相位偏差检查和变异测试。 |
| `3687285` | 更新中英文手册和 README 致谢。手册保留原有行号供离线故障排查索引引用。PR 未引入主 CLI 新选项。 |
| `ab55d8a` | 提交重放表、seed 4 诊断、逐字节回归与复跑脚本。 |
| `414a3a1` | 将 web 重试用例的夹具根目录指向已创建的本卡临时目录。 |

## 验收

- `python -B -X utf8 -m discprobe selftest` 返回 0，打印 `all checks passed`，共 1,482 条 `ok`。合并后第一次运行耗时 283.652 s，唯一失败是手册插入段落后引用行号移动。调整手册后，与其他检查重叠的一轮耗时 582.757 s，全部通过。
- **耗时门限通过。** 用同一解释器、相同 BLAS 和镜像工作进程设置同时启动两份 `python -B -X utf8 -m discprobe selftest`，各用本卡独立临时目录。基点 `95d3289` 从 Git 导出，耗时 371.506 s，合并版耗时 371.645 s，均返回 0。增加 0.139 s（0.0374%）。原始配对数据在 `D:/dp-dev/tmp/pr29merge/paired-selftest.json`。不同时间启动的计时波动较大，最初基点为 280.450 s，后续两轮串行合并版和基点分别为 784.189 s 与 584.674 s。验收采用同时启动的配对数据。
- `python -B -X utf8 evidence/pr29-merge/verify.py seeds` 用两个进程扫 seed 0–199。200/200 通过，共 3,200 项检查、1,400 次几何模拟。改过的跨度检查及各自最大值如下。

| 检查 | 阈值 | 最大观测值 |
| --- | ---: | ---: |
| 普通 DVD 对真值，0–98% | < 0.75° | 0.436° |
| 整块 ECC 对同种子普通 DVD，0–98% | < 0.10° | 0.000° |
| 纹理环 DVD 对真值，实际测量跨度 | < 0.75° | 0.444° |
| CD 数据盘对真值，u/v 各 ±1% 的四组组合，0–98% | < 0.75° | 0.086° |

- DVD 的级点平均有符号相位误差上限为 0.25°。普通、整块、纹理环三种场景在种子扫描中的最大绝对偏差分别为 0.178°、0.178°、0.082°。变异测试 `test_ladder_geometry_rejects_a_biased_estimator` 给生产估计器的返回相位加 0.5°，seed 7 的三项偏差检查报错（+0.560°、+0.560°、+0.497°），干净对照 0 项失败。另保留 PR 的 CD 音轨晚到读数检查。
- seed 4 复现为普通和整块 DVD 的模拟噪声误触发可变轨距判断。样条向内圈外推后，LBA 174800 的预测与实测相差 93.693°，越过 90° 整圈保护门限。该次实测相位对真值只差 +0.754°。64 个接纳级点的整圈数正确。去掉额外长延迟或关闭自动修正的诊断对照均完成。命令、对照数据及结论见[回归报告](evidence/pr29-merge/REPORT.md)。
- `python -B -X utf8 evidence/pr29-merge/parity.py` 验证同种子 `timing` 的事件 CSV 和摘要 JSON，以及默认 DVD 网格镜像的 4,455,694,336 字节，均与 `95d3289` 的长度和 SHA-256 一致。两份 ISO 核对后已删除。 [回归报告与哈希](evidence/pr29-merge/REPORT.md)
- `python -B -X utf8 evidence/pr29-merge/verify.py replay` 重放 38 个候选，输入哈希和 646 项字段比对全部与评估一致。22 条去重且可重建的实测中，median 的 RMS 有 16 条较低、3 条较高、3 条相等。 [逐条重放表](evidence/pr29-merge/REPORT.md)
- `python -B -X utf8 evidence/pr29-merge/checks.py python` 调用 `pytest -n 2` 跑 12 个相关文件，194 通过，耗时 111.81 s。日志为 `D:/dp-dev/tmp/pr29merge/checks-python-0r3v1u16/pytest-geo.log`。
- `python -B -X utf8 evidence/pr29-merge/checks.py js` 串行跑完全部 61 个 `tests/test_*.mjs`。首轮 60 个返回 0，`test_web_retry_browser.mjs` 因夹具父目录未创建而在断言前退出。修正复跑脚本后用同一命令加 `--js-test test_web_retry_browser.mjs` 单独复跑并通过，覆盖 12 次读取重试、2 次继续测量以及写速重试门禁。测试使用仓库自带的本机无头夹具。首轮日志和复跑结果均在 `D:/dp-dev/tmp/pr29merge/`。
- D、F 盘在开跑前分别有 49.087 GiB、43.350 GiB 可用，测试前按卡检查 5 GiB 门限。`git diff` 核对 `evidence/atlas/*.py` 和 `discprobe/pcal.py` 的变动为 0。

## 未测和待决定事项

未接光驱或刻录实盘。现有归档中未找到 BU20N 音轨结果，PR 提到的两次实测改善及实盘上类似 seed 4 的触发频率均未复核。逐字节镜像对照覆盖默认 DVD 网格。当前合并无待决定事项。

STATUS: DONE
