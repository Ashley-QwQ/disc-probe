# VT 变轨距判定验收

基点为 `4f042ca`。第二轮按主会话批准的退路保留首轮生产候选，保留补测限额和单调进度。

## 第二轮决定与验收

### 确认读数试验

模拟器使用与首轮相同的噪声组和正例种子。对至少 7 级、跨 5 mm、读数离散度中位数 ≥0.55°、通过基点 χ² 与残差门槛的可疑拟合，优先取高标准化残差且径向相隔至少 0.02 mm 的至多 8 个已读地址。从中选信号最强的 5 个，权重消除常量、半径和半径倒数三个恒定轨距拟合方向，误差估计按平方和加入 0.30° 的块间项。在初次信号至少 2.5 个标准误时独立重读，比较同一方向的加权相位差。最多尝试两次，每次最多测 5 个地址，两次之间至少接纳 3 个新级。每个地址沿用已有的一次稳速重试。重读相位偏移超过 25° 时拒绝确认。较严格版本同时保留原候选已经判为真弯且恒定拟合将触发 χ² 停止保护的场景。

| 版本 | 主组误触发 | 独立组误触发 | 真变轨距检出 | 7 个高噪声 I218 重点种子的完整修正 |
| --- | ---: | ---: | ---: | ---: |
| 确认门槛 2.8 个标准误 | 6/200 | 5/200 | 194/200 | 5/7 |
| 确认门槛 3.2 个标准误，保留会触发 χ² 停止保护的原候选 | 3/200 | 0/200 | 198/200 | 4/7 |

3.2 版本漏检 step 的 seed 77、119。高噪声 I218 seed 157、175、181 仍在密集探测触发整圈保护。记录中的三次完整修正失败已经超过主路线允许的一次。两套确认规则进入完整 200 个正例的修正统计前均未达到检出要求，因此该轮确认试验只对重点 7 个种子运行完整修正，共同样本全组 RMS 未测。

```powershell
$p = 'D:/dp-dev/tmp/varpitch'
$env:TEMP = $env:TMP = $env:TMPDIR = $p
$v = 'evidence/varpitch-trigger/confirm_trial.py'
python -B -X utf8 $v negative --detect-only --end 400 > "$p/confirm-negative.jsonl"
python -B -X utf8 $v positive --detect-only > "$p/confirm-positive.jsonl"
python -B -X utf8 $v positive --seeds 7 121 157 175 181 193 199 > "$p/confirm-i218.jsonl"
python -B -X utf8 $v negative --detect-only --end 400 --repeat-sigmas 3.2 --keep-strong > "$p/confirm-b-negative.jsonl"
python -B -X utf8 $v positive --detect-only --repeat-sigmas 3.2 --keep-strong > "$p/confirm-b-positive.jsonl"
python -B -X utf8 $v positive --seeds 7 121 157 175 181 193 199 --repeat-sigmas 3.2 --keep-strong > "$p/confirm-b-i218.jsonl"
```

### 退路验收

生产代码沿用首轮候选。复用同一生产源码产生的 200 种子对照日志。主组 4/200（2%，门槛 3%），独立组 12/200（6%，门槛 6%），检出 200/200，完整修正 195/200。194 个共同成功样本的真值 RMS 从 0.1111° 升到 0.1145°，属于本轮退路接受的差异。

`test_variable_pitch_end_to_end` 对每种盘面和抖动条件跑种子 0、7、19，以独立检查 RMS 的中位数对照原 0.5° 门槛。每个种子的完整修正、与模拟真值的误差、整圈计数、检查点数和修正文件装载仍须单独通过。原卡失败的 step、100 µs 三个样本分别为 0.26316°、0.50012°、0.43679°，中位数为 0.43679°。变异测试把重复样本生成的角度曲线压成常量，三次 RMS 为 1.10761°、1.18260°、1.05811°，同一中位数断言拒绝该估计器。相关测试入口是 `python -B -X utf8 evidence/varpitch-trigger/checks.py python`。

SysWOW 第二次网页任务的原始读数无法取得。原触发级无法重放，按主会话决定从阻塞项移除。下文只记录日志能核对的已接纳级。CD CLV 临时目录断言为基点已知失败。

### 浏览器验收安排

本卡的 `tests/test_*.mjs` 与浏览器验收均未跑。Edge 每次以新配置目录启动时会尝试空密码登录，连续失败会锁定 Windows 账户。浏览器迁移合并后由主会话补跑。卡内运行器只保留 `selftest` 和 `python` 两个入口。它在执行标准自检命令时列出并跳过会启动 MJS 的内嵌检查，也在相关 pytest 中取消选择两个会启动 MJS 的测试。启动防护拦截浏览器、MJS 子进程和对 8765 的连接或绑定。防护用合成审计事件验证，通过该测试时未启动程序或打开套接字。

最终 `selftest` 通过，耗时 283.12 秒。它明确跳过 8 个 MJS 依赖检查和 `test_frozen_photo_and_video_placement_geometry`，后者依赖排除路径。日志位于 `D:/dp-dev/tmp/varpitch/selftest-round2-no-browser.log`。第一次有防护的尝试拦下一个间接 MJS 调用和一次排除路径访问，这两项在最终运行前列入显式跳过列表。

最终相关 `pytest -n 2` 196 通过、1 失败，耗时 69.94 秒，另取消选择 2 项 MJS 依赖检查。唯一失败为已在 `4f042ca` 复现的 `test_cd_clv_cli_validates_anchor_before_opening`。日志位于 `D:/dp-dev/tmp/varpitch/checks-python-361gvobn/pytest-geo.log`。重跑逐字节核对后，12 个模拟和 5 份 GH70N 重放的 51 个输出散列与基点一致。`python tools/refresh_troubleshoot_citations.py` 刷新后，`--check` 退出码 0。本轮续跑起点后 Windows Security 的新增 4625、4740 事件各为 0。

## 首轮数据与复跑命令

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

当前相关回归入口为 `python -B -X utf8 evidence/varpitch-trigger/checks.py selftest` 和 `python -B -X utf8 evidence/varpitch-trigger/checks.py python`。Python 测试入口以 `pytest -n 2` 运行。

候选自检耗时 361.95 秒，step 测试的同一断言失败。基点自检通过，耗时 646.75 秒。相关 pytest 共 198 项，196 通过。另一个失败 `test_cd_clv_cli_validates_anchor_before_opening` 可在导出的基点源树用 `python -B -X utf8 -m pytest -n 2 -q tests/test_cd_clv.py::test_cd_clv_cli_validates_anchor_before_opening` 单独复现。CLI 在拒绝参数时创建了 fixture 指定的 `discprobe-home`，测试要求 `tmp_path` 为空。新增的单调进度、点数限额、重试中时间限额与 seed 4 测试全部通过。

首轮历史记录为 JavaScript 首跑 62/63，其中 `test_reshoot_browser.mjs` 在整盘夹具准备阶段触及外层 240 秒时限。首轮单项重跑约 714 秒通过。历史日志位于 `D:/dp-dev/tmp/varpitch/reshoot-retry.log`。第二轮浏览器验收按上述新规则延期。
