# CD／DVD 预读回归

## 检测与绕开

同址重复读取仍按旧规则选策略。CD、DVD 数据盘走 `plain` 时，再从同一参考扇区出发，分别检查多个前向距离。每个距离用四组参考点和测点读数，组内停顿为 0、¼、½ 和 ¾ 圈。圈时用同址 plain 重读的中位数估计。至少三组须两次读成功，且测点读数低于 `min(½ 圈, max(3 ms, ⅓ 圈))`。快读的相对完成角还须散开超过 60°，以区分预读和正常的近距离快读。`cache.read_ahead_sectors` 是最远命中距离给出的下界。

若同址 FUA 已表现为读盘，再用 FUA 读同一个命中测点。四组都需读成功，且相对完成角与第一组相差均在 45° 以内，才采用 FUA。这样两个初始测点、后续跳阶和整圈约束可以沿用原有参数。无法绕开的光驱继续使用原策略。如果实际测点出现持续的预读快读，测量会停下并建议用另一台光驱测同一张盘。CD 音轨沿用 READ CD 的远读做法。

诊断样本独立于原有缓存统计和 `events.csv`。模拟使用独立的诊断快照，原测量的虚拟时钟、随机数流、缓存和读盘计数按原顺序推进。只有检测到命中时，摘要才会增加字段，`timing` 才会打印预读提示。真实硬件的额外读盘发生在原同址缓存测试之后、转速稳定和测角之前。

## 运行命令

在仓库根目录用 PowerShell 执行。脚本检查 D 盘空间并把所有临时输出放在 `D:/dp-dev/tmp/readahead/`。每个模式会打印本次 JSON 和日志目录。

```powershell
$env:TEMP='D:/dp-dev/tmp/readahead'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
python -B -X utf8 evidence/readahead/verify.py simulate
python -B -X utf8 evidence/readahead/verify.py parity
python -B -X utf8 evidence/readahead/verify.py replay
python -B -X utf8 evidence/readahead/verify.py syswow
python -B -X utf8 evidence/readahead/verify.py selftest
python -B -X utf8 evidence/readahead/verify.py js
```

脚本用 `git show` 从 `f99ac21` 载入修改前的 Python 模块，其他模块和测试夹具来自同一 worktree。复现时仅将新增的模拟光驱送进旧版 CLI，再运行未改的旧版测量。两版本的模拟比较固定 CLI 墙钟和输出路径，测量事件仍由模拟光驱的独立虚拟时钟生成。

## 模拟复现和修后几何

`simulate` 使用 seed 7。DVD 首级距参考点 96 扇区，覆盖该测点需要比默认 24 更大的窗口，所以 DVD 以 112 扇区运行。两种盘在基点都选 `plain`，均以状态 1 停在首级并打印 `could not measure LBA ... near the reference`。修后两种 `timing` 均判定 CAV，`geo` 均到达 `target_reached`。

| 介质 | 模拟预读窗 | 参考 LBA → 首级 LBA | `timing` 与 `geo` 报告的下界 | 修后策略 |
| --- | ---: | --- | ---: | --- |
| CD | 24 | 178124 → 178132 | 24 | `fua` |
| DVD | 112 | 1136064 → 1136160 | 96 | `fua` |

对照使用同一模拟光驱、同一盘、同一种子、窗口 0。修后与对照的测点 CSV 逐字节相同，`u`、`v`、起始半径、轨距、残差 RMS 和角度不确定度的差均为 0。每种盘的测点读取 LBA 序列也相同。

| 介质 | 修后与对照起始半径 mm | 修后与对照轨距 µm | 修后与对照残差 RMS ° | 修后与对照角度不确定度 ° |
| --- | ---: | ---: | ---: | ---: |
| CD | 25.24999661 | 1.584000354 | 0.227706 | 0.146730 |
| DVD | 23.87626318 | 0.733349494 | 0.979693 | 0.731319 |

脚本也用忽略 FUA 的模拟复核失败路径。两种盘均在同一首级报告光驱反复从预读缓存返回该扇区，并建议将同一张盘放到另一台光驱测量。两种语言的提示均已核对。

## SysWOW 离线数据

`syswow` 读取原 timing 的 `summary.json` 和 geo 的 `events.csv`。同址 plain 中位数 30.1252 ms，对应新检查 10.0417 ms 的快读门限。同址 FUA 中位数 29.5900 ms，原记录 `fua_reads_media=true`。从参考点 178122 到测点 178130 的 64 个相邻事件对，有 49 对低于门限，超过需要的 48 对。参考点耗时中位数为 47.2122 ms，测点为 2.8041 ms。读完参考点到发出测点请求的时间为 1.4092–36.9815 ms，快读相对完成角满足新判据。旧数据确认了至少 8 个后续扇区处的预读。同址 FUA 结果支持绕开路线，仍需要对该光驱做邻址 FUA 控制和完整实测。旧记录只有这一个相邻距离，无法用它估出 16–24 扇区的整个窗口。

## PR #29 数据重放

`replay` 使用 PR #29 合并卡的 `compare_replay()`，按原清单逐个核验输入 `summary.json`、`events.csv` 及已有的 `targets.csv` 的 SHA-256。38 组输入全部匹配，其中有 11 组内容重复。基点和修后共比对 40 个生成文件，SHA-256 全部相同，包括 `replay.csv`、`replay_manifest.json`、`replay-comparison.json`、`replay-table.md` 和 36 份重放文本。原合并卡的 17 个字段 × 38 组输入均无差异。重放从保存的事件重建几何和比较估计器，两个版本均使用原 PR #29 估计器。

## 无预读故障的逐字节对照

`parity` 比较 16 组现有模拟，涵盖两种介质、四种模拟光驱和两个命令。另有 4 组 `plain` 零窗口对照，确保实际走了邻址检查却未命中时，原读盘事件和输出也逐字节相同。共 20 组匹配。脚本比较退出码、终端日志及每个生成文件的 SHA-256，包括适用的 `events.csv`、`summary.json`、`targets.csv`、`partial.json`、`failure.json` 和 `diagnostics.zip`。CD `cav-audio` 的 `timing` 沿用数据盘限制，CD `cav-nofua` 的 `geo` 沿用基点在第二级前停止的行为。

对照固定运行日期、结果路径、测量墙钟和进度检查点时间。首次对照有 19 组通过，CD `cav-nofua` 的 `partial.json` 和包含它的 ZIP 因检查点时间不同而失配。补齐固定时钟后，用 `python -B -X utf8 evidence/readahead/verify.py parity --parity-case cd cav-nofua geo` 复核该组，全部字节匹配。其 `events.csv`、`targets.csv` 和终端日志在两次对照中均匹配。

## 相关 Python 测试

在卡片临时目录环境下运行以下命令，135 项通过，耗时 451.30 秒。

```powershell
$env:DISCPROBE_HOME="$env:TEMP/pytest-final-home"
$env:LOCALAPPDATA="$env:TEMP/pytest-final-state"
$env:DISCPROBE_WORKERS='2'
$env:OPENBLAS_NUM_THREADS='1'
python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp="$env:TEMP/pytest-final" -q `
  tests/test_geo_coverage.py tests/test_geo_integration.py tests/test_geo_progress.py `
  tests/test_geo_selftest.py tests/test_geo_speed.py tests/test_geo_unsteady.py `
  tests/test_geo_varpitch.py tests/test_geo_checkpoint.py tests/test_read_completion.py `
  tests/test_cd_clv.py tests/test_bd_clv_solver.py tests/test_troubleshoot.py
python -B -X utf8 tools/refresh_troubleshoot_citations.py --check
```
