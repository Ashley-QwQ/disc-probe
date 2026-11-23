# VT 变轨距判定验收

基点为 `4f042ca`。本轮判定保留为实验候选。主噪声组达到 2%，独立噪声组达到 6%，真变轨距完整修正也有回归。

## 读数与模拟对照

| 输入 | 基点 | 候选 |
| --- | --- | --- |
| SysWOW v0.1.2.1，22 级原始读数重放 | 第 10 级触发 | 22 级均未触发，恒定拟合 χ²/dof 12.602，RMS 0.681° |
| SysWOW alpha 第一次，重放到原触发候选 LBA 1735440 | 第 7 级触发 | 未触发，χ²/dof 7.904，RMS 0.583° |
| SysWOW alpha 第一次，按已经变轨距的日志顺序重放全 65 级 | 第 9 个已接纳级触发 | 第 42 个已接纳级触发 |
| SysWOW alpha 第二次，日志反解触发前接纳的 10 级 | 这 10 级未触发 | 这 10 级未触发，χ²/dof 6.233，RMS 0.715° |
| SysWOW alpha 第二次，按日志顺序反解并重放前 22 个已接纳级 | 第 11 个已接纳级触发 | 第 12 个已接纳级触发 |
| 恒定轨距，混合噪声，种子 0–199 | 126/200（63%） | 4/200（2%） |
| 恒定轨距，独立同分布噪声组，种子 200–399 | 139/200（69.5%） | 12/200（6%） |
| PR #29 恒定轨距 seed 4 | 第 7 级触发。64 级后在第 11 个密集测点触发 90° 整圈保护 | 16 个有效级完成，0 个密集测点，提示单次读数离散度中位数 3.29° |

两份有 `events.csv` 的 SysWOW 数据，以原估计器 `interp` 从逐次读数重建。最大重建相位差均为 `0.000°`。第一次 alpha 的全长重放含旧判定换成 64 级后才读取的地址。原触发处以 `prediction_checks` 找到被退回的第 7 级，再用原始事件恢复该级噪声。

第二次 alpha 仅有 `events.jsonl` 和 `output.log`。从日志的整圈数和 `geo_point` 的拟合残差反解级相位，反解重现记录半径的最大差约 `8.42×10⁻¹¹ mm`。原触发候选 LBA 137120 只有地址，缺相位和原始读数。候选退出旧流程时该级被退回，随后接纳的第 11、12 级属于旧模式选择的地址。这份资料能核对已接纳级，原触发候选未测。命令行那次未测。

负例每级仍用 24 对读数。模拟转一圈 26 ms，逐块换用常态 40–85 µs 抖动，6% 的块换为 195–300 µs，并对块均值叠加独立零均值偏移，常态 σ 为 0.48°，突发块为 1.0°。该偏移模拟在同一块内消不掉的读延迟。主组候选在结束或首个触发前共接纳 4,201 级，单次读数离散度的 P5、中位数、P95 为 0.628°、1.031°、3.024°，199 级在 3–5°。该组两版本各有 9 次在 3–5 级触发原有 χ² 整圈保护。

## 正例与修正质量

种子 0–199 按顺序轮换 `i218`、`mild`、`step` 的 20/100 µs 六种条件。介质模型沿用 `9bca225` 的模拟器和现有变轨距测试。每个完成场景在测量范围内取 6,000 个地址扣除全局旋转偏置后与真值比较。表中每列误差均为对各成功场景的 RMS 再作均方根聚合。

| 场景 | 检出 基点 → 候选 | 完整修正 基点 → 候选 | 真值 RMS 基点 → 候选 | 独立检查 RMS 基点 → 候选 |
| --- | ---: | ---: | ---: | ---: |
| i218，20 µs | 34 → 34 | 34 → 34 | 0.0445° → 0.0443° | 0.0897° → 0.0895° |
| i218，100 µs | 34 → 34 | 33 → 29 | 0.1729° → 0.1789° | 0.4272° → 0.4377° |
| mild，20 µs | 33 → 33 | 33 → 33 | 0.0309° → 0.0309° | 0.0861° → 0.0861° |
| mild，100 µs | 33 → 33 | 33 → 33 | 0.1402° → 0.1390° | 0.4418° → 0.4327° |
| step，20 µs | 33 → 33 | 33 → 33 | 0.0360° → 0.0361° | 0.0917° → 0.0924° |
| step，100 µs | 33 → 33 | 33 → 33 | 0.1550° → 0.1624° | 0.4476° → 0.4491° |
| 合计 | 200 → 200 | 199 → 195 | 0.1136° → 0.1150° | 0.3160° → 0.3137° |

只比较两个版本都成功的 194 个相同种子，真值 RMS 为 0.1111° → 0.1145°。旧版在 seed 199 中止修正。候选在 seed 121、157、175、181、193 中止修正，均为 i218、100 µs，均触发密集探针整圈保护。将同方向相邻残差的幅度和标准误门槛提高，能在两个负例组同时降到 2% 以内。该组阈值扫描的最佳正例检出为 196/200。

## 判定、预算与兼容性

- 初筛沿用 χ²/dof 和总残差门槛，至少 7 级并覆盖 5 mm。空间判定在相邻半径比较同向残差，使用 `std_deg / sqrt(used)`、各级误差估计和典型级的实测误差。局部相邻差估计单块统计看不见的块间噪声，截断后的空间相关性给跨级同向证据加权。对两端各有至少 4° 且第三点也有超噪声偏差的陡变保留近处整圈检查。
- 插点使用同一地址 `first/again` 的差值估算重复均值的噪声。相邻均值差和局部弯折均须超过噪声门槛。总预算 384 个不同地址，给独立检查预留 64 个，补测至多 5 轮。进入补测后最多 75 分钟开始新读命令，正在执行的命令正常返回。达到限额保留可用测点和已有拟合，并报告限额原因。终端和网页使用同一进度回调，补测只累加完成的块。
- 候选的模拟补测最多保留 282 个重复或独立检查地址。最长模拟设备时间为 1,918.04 秒，测试用的 2,700 秒限额也未触发。GH70N 的 R001–R005 每份各有 22 个重放级，均走常规拟合。其读块中位数 5.70–6.09 秒，按运行计算的 P95 为 6.89–7.58 秒。把模拟最多 282 个地址全部按双读和 7.58 秒估算，约需 71.3 分钟。GH70N 真变轨距实盘耗时未测。
- 常规模拟 12 个种子各比较 3 个文件，共 36 个 SHA-256 完全一致。时钟固定，保留测量事件时间。GH70N R001–R005 以原始事件执行统一的 `--reapply` 重拟合逻辑，将完成偏移设为 16 扇区，各 3 个文件，共 15 个 SHA-256 完全一致。

## 复跑命令

在工作树根目录运行。脚本使用 `D:/dp-dev/tmp/varpitch`，启动时检查 D、F 余量。`--baseline` 从 Git 读取基点的 `geo.py` 和 `varpitch.py`，由同一套模拟器和证据脚本运行。一次最多并行两条独立计算命令。

```powershell
$p = 'D:/dp-dev/tmp/varpitch'
$env:TEMP = $env:TMP = $env:TMPDIR = $p
$env:OPENBLAS_NUM_THREADS = $env:OMP_NUM_THREADS = $env:MKL_NUM_THREADS = '1'
$v = 'evidence/varpitch-trigger/verify.py'
python -B -X utf8 $v replay --real --baseline > "$p/replay-base.jsonl"
python -B -X utf8 $v replay --real > "$p/replay-new.jsonl"
python -B -X utf8 $v negative --detect-only --baseline > "$p/negative-mixed-base.jsonl"
python -B -X utf8 $v negative --detect-only > "$p/negative-mixed-new.jsonl"
python -B -X utf8 $v negative --detect-only --start 200 --end 400 --baseline > "$p/negative-holdout-base.jsonl"
python -B -X utf8 $v negative --detect-only --start 200 --end 400 > "$p/negative-holdout-new.jsonl"
python -B -X utf8 $v positive --baseline > "$p/positive-strat-base.jsonl"
python -B -X utf8 $v positive > "$p/positive-strat-new.jsonl"
python -B -X utf8 $v parity --baseline --end 12 > "$p/parity-base.jsonl"
python -B -X utf8 $v parity --end 12 > "$p/parity-new.jsonl"
python -B -X utf8 $v parity --real --baseline > "$p/parity-real-base.jsonl"
python -B -X utf8 $v parity --real > "$p/parity-real-new.jsonl"
python -B -X utf8 $v seed4 --baseline > "$p/seed4-base.jsonl"
python -B -X utf8 $v seed4 > "$p/seed4-new.jsonl"
python -B -X utf8 $v summarize > "$p/summary.json"
```

探索冻结进入弯曲前的选点路径，在同一批实际前缀上比较门槛，并为陡变规则保留一个更宽松的检出口径。上表的完整修正数字来自端到端命令。

```powershell
$g = 'evidence/varpitch-trigger/thresholds.py'
python -B -X utf8 $g negative 0 200 > "$p/prefix-neg.jsonl"
python -B -X utf8 $g negative 200 400 > "$p/prefix-holdout.jsonl"
python -B -X utf8 $g positive 0 200 > "$p/prefix-pos.jsonl"
python -B -X utf8 $g sweep > "$p/thresholds.json"
```

现有全流程测试中的 step、100 µs、seed 7，独立检查 RMS 从 0.44007° 增至 0.50012°。该测试要求小于 0.5°。单独复跑两版六种条件的命令为 `python -B -X utf8 $v positive --all-profiles --start 7 --end 8 --baseline` 和 `python -B -X utf8 $v positive --all-profiles --start 7 --end 8`。

相关回归入口为 `python -B -X utf8 evidence/varpitch-trigger/checks.py selftest`、`python -B -X utf8 evidence/varpitch-trigger/checks.py python` 和 `python -B -X utf8 evidence/varpitch-trigger/checks.py js`。Python 测试入口以 `pytest -n 2` 运行。

候选自检耗时 361.95 秒，step 测试的同一断言失败。基点自检通过，耗时 646.75 秒。相关 pytest 共 198 项，196 通过。另一个失败 `test_cd_clv_cli_validates_anchor_before_opening` 可在导出的基点源树用 `python -B -X utf8 -m pytest -n 2 -q tests/test_cd_clv.py::test_cd_clv_cli_validates_anchor_before_opening` 单独复现。CLI 在拒绝参数时创建了 fixture 指定的 `discprobe-home`，测试要求 `tmp_path` 为空。新增的单调进度、点数限额、重试中时间限额与 seed 4 测试全部通过。

JavaScript 首轮 62/63 通过。`test_reshoot_browser.mjs` 在整盘夹具准备阶段触及外层 240 秒时限。单独运行原测试约 714 秒通过，完成 2 个 Disc Lab 场景、8 张截图和 1 张对准箭头预览，最终 63/63 通过。重跑的整盘文件已由夹具清理，哈希和日志留在 `D:/dp-dev/tmp/varpitch/reshoot-retry/` 及 `reshoot-retry.log`。

```powershell
$run = Join-Path $p 'reshoot-retry'
New-Item -ItemType Directory -Path $run -Force | Out-Null
$env:TEMP = $env:TMP = $env:TMPDIR = $run
$env:RESHOOT_TEST_ROOT = Join-Path $run 'scene'
$env:DISCPROBE_HOME = Join-Path $run 'home'
$env:LOCALAPPDATA = Join-Path $run 'localappdata'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:NODE_OPTIONS = '--require=D:/dp-dev/varpitch/evidence/pr29-eval/offline-tests.cjs'
node tests/test_reshoot_browser.mjs *> "$p/reshoot-retry.log"
```
