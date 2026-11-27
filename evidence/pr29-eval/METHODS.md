# 复现与口径

所有命令从 `D:/dp-dev/pr29m` 运行，不连接设备、不下载、不上传；Python 3.13.14，BLAS/OMP 线程数为 1，评估最多两个 worker。

```powershell
$env:TEMP='F:\dp-dev-tmp\pr29eval'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -X utf8 evidence/pr29-eval/evaluate.py --mode phase --seeds 200 --workers 2
python -B -X utf8 evidence/pr29-eval/evaluate.py --mode end-to-end --end-seeds 30 --workers 2
python -B -X utf8 evidence/pr29-eval/evaluate.py --mode replay
python -B -X utf8 evidence/pr29-eval/run_checks.py --only selftest
python -B -X utf8 evidence/pr29-eval/run_checks.py --only python
python -B -X utf8 evidence/pr29-eval/run_checks.py --only js
python -B -X utf8 evidence/pr29-eval/run_checks.py --only js --js-test test_csp_browser.mjs
python -B -X utf8 evidence/pr29-eval/build_report.py
python -B -X utf8 evidence/pr29-eval/audit.py
```

也可用 `python evidence/pr29-eval/evaluate.py --seeds N` 一次生成三个部分；端到端数量默认 30，通过 `--end-seeds` 调整。

## 每级实验

- 种子均为 1–200；各条件、同一 seed 的目标固定为容量 8%–85% 上均布的 14 个 LBA（向下按模拟器读块对齐），参考固定在 5%。不运行梯子的选点、拟合、重试或 state check；TimingProbe 的暂停 RNG 保持其默认 seed 1，SimDrive RNG 使用实验 seed。
- DVD 为 CAV 6.6 ms、reps=16、FUA；CD-DA 对照为 CAV 48.35 ms、reps=32、far 缓存策略。均使用 `jitter_us=60`、`outlier_rate=0.01`、`reread_delay_ms=35`，没有用 CD-DA 对照代替任务要求的 DVD 当前噪声。
- `SimDrive._read` 原噪声为 `t_end_pass + 250 us + N(0, jitter_us)`，1% 额外加 `U(300,3000 us)`，最后用 `max(done,t_end_pass)` 截断；寻道时间还含随机量，但合法介质读取结束锁定于转盘几何相位，缓存命中有另一个小延迟分布。
- 新增尾巴在 `LateDrive._read` 包装中实现，原库文件不变；每个介质读取（含参考、目标以及 far 读取）独立以 0/3/10/20% 的概率额外延迟，条件角度分布为 `80% U(10,20°)+20% U(4,60°)`，用局部角速度换成秒，并让后续读取沿更新后的模拟时钟继续。它是依据任务卡范围构造的敏感性模型，不是从 BU20N 事件拟合出的分布；非零尾巴条件的随机流独立于 SimDrive，seed 为 seed+1000003。
- 生产式 ±2% 周期搜索在固定远距离读数上发现少数别名，原始结果全部保留在 `wide_period_diagnostic/`；主表用模拟器在参考读数中点的真周期作 ±0.01% 的窄先验，仍调用未修改的 `estimate_period` 和 `phase_offsets`，不代表真实设备已知这个先验。该函数对任何先验都另外搜索 1/2、1/3 周期，所以窄先验本身不能杜绝别名；主表最终沿用 geo 的相干度至少 0.93、周期相对先验差不超过 0.2% 的共同门限，拒绝样本不进入统计但原始误差仍在 CSV，全部 200 个 seed 均保留有效样本，不按两种剪切器各自的 std 或结果误差筛选。
- 宽先验复现：`python -B -X utf8 evidence/pr29-eval/evaluate.py --mode phase --seeds 200 --period-window .02 --output F:/dp-dev-tmp/pr29eval/wide-reproduction`。宽表来自第一轮完整运行，保存的 metadata 是当时脚本的 SHA256；后续改动只增加先验控制、重放分类、报告与验收，不改变端到端实验。
- 同一级的两种估计器接收完全相同的 offsets；误差为 wrap 到 [-180,180) 的测量相位减模拟真值，DVD 还用 `theta(n,truth_u,truth_v)` 交叉验证，`truth_u=r0/b`、`truth_v=pitch/b`。偏差为共同有效每级有符号误差均值，RMS 为平方均值开根号，P95 为绝对误差的线性分位数；每 seed 的至多 14 个共同有效级 RMS 较低计为“新更好”，1e-12 内为相同，`phase_seeds.csv` 保留每 seed 实际有效级数。
- 第一轮窄先验运行保留所有误差，之后用 `python -B -X utf8 evidence/pr29-eval/evaluate.py --mode summarize` 应用共同周期门限重汇总，没有重新抽样；最终脚本在 `phase_job` 中直接作同样分类，可从头重跑得到同一统计。

## 端到端实验

- 种子 1–30；原噪声和 10% 新增尾巴；每种估计器每 seed 跑普通、整块、纹理环盘三个场景，共 360 次。只在 worker 内临时替换 `analysis.robust_median_mean` 函数对象，磁盘文件不变，两种估计器在不同任务中新建同 seed 模拟器；因为自适应选点，两者的后续读数不保证一样，此处正是端到端路径效应。
- `max_targets=14`，reps=16，35 ms 重读；普通盘与整块 `state_check=False`，纹理环盘保持默认 True；不关闭自动修正、不改阈值或固定种子。
- 普通盘在 0–98% 容量上 400 个点比较真值；整块检查比较同估计器、同 seed 普通盘的拟合（严格沿用 selftest 实现，其显示文案写 85%，代码实际复用 98% 的数组）；纹理环盘在实际目标 n 的最小至最大处取 300 点比较真值。
- 原始 CSV 同时保留 `truth_span_deg`，整块读取的真值误差并非 0；`span_deg` 则是 selftest 的检查指标。异常和停止独立记录，分位数与 >1.5° 比例只用成功完成的分母；由于 selftest 判断 `<1.5`，恰等于阈值也应失败，本次没有恰等于 1.5° 的结果。
- `seed=7`、原噪声、纹理环盘复现旧 1.381667664°、新 1.566315898°；可直接在 `end_to_end.csv` 中核对。

## 真实结果重放与边界

- 只遍历任务卡明确的四个根目录；任何含禁用连续字母序列的路径在 stat、进入或输出之前过滤，不跟随子目录符号链接；archive 的 untracked 树中只将 results* 下 geo-* 的事件与摘要作为重放输入。
- 输入必须有 events.csv 和 summary.json，缺 targets.csv 的结果单列失败；读取前后对三种输入文件逐个 SHA256 核对，原文件不写入。输入绝对路径和每个 hash 在 manifest；Rxxx 文本是未改动重放工具的标准输出。
- 重建是否通过按工具显示的三位小数 `0.000°` 判断，不代表数学上严格零；非零结果排除。非 geo 的 timing 摘要只有 events/summary，没有 fit，单列“非 geo”。完整三文件内容相同的目录只作一条独立来源，复制件在表中注明；`-Z-`、名字含 sim 或 summary 明确 simulated 的记录独立标为模拟，即使内容与真实目录相同。
- 光驱型号仅取 summary.identity.drive，未记录则 UNKNOWN；不根据盘符推断型号。全部指定目录未找到可用 BU20N 音轨记录，这两次 PR 背景结果未复核。
- 当前找到的真实记录均是数据轨；工具原生输出 `r0(mm)` 与 `pitch(um)`，没有 audio 轨的 ri/ro。表保留 r0 为条件内半径，并按 setup.last_lba+1（优先 fit.sectors）计算 `ro*=sqrt(r0² + pitch_mm * bits_per_sector * sectors * assumed_bit_mm/pi)`；使用摘要假定位长，外推至可读容量而非独立实测盘缘，不能解释为纳米级真值精度。
- χ²/dof 与 RMS 直接保留工具打印结果（χ² 两位、RMS 三位），半径计算依赖其九位小数 r0/pitch；因此工具舍入后显示相同的结果计为相同，不额外声称精度。完整 raw 输出还包括 recorded 和 line 对照，结论仅比较 interp/median。

## 验收与文件

- `run_checks.py` 串行执行各测试命令，每个 JS 文件一次，Python 只选择四个 geo 文件并使用 `-n 2`；selftest 自身的 `_tests_folder` 会调用它内置的无参数测试，这是本分支既有行为，未绕过或删减。
- 环境临时目录和可配置浏览器输出都放 F 盘；selftest 内部少数既有测试显式指定 `TemporaryDirectory(dir=ROOT)`，会在本 worktree 根目录短暂产生小夹具并自行清理，此限制不能在不改测试或其行为的情况下用 TEMP 环境变量覆盖，报告如实列出。
- `offline-tests.cjs` 仅通过测试子进程的 NODE_OPTIONS 载入，阻止 Node 外部 fetch，并给 Chromium 增加关闭后台网络和外部 DNS 解析的参数；本地 HTTP/CDP 与被测试自身拦截的 photo.test 夹具仍可用。没有修改浏览器测试源码或断言。
- JS 首轮 50/51 通过，CSP 的浏览器断言完成后，输出至写死的 `D:/dp-dev/tmp/webguide/csp-headers.json` 因父目录不存在而 ENOENT；评估侧随后只重定向 CSP/flow 两个硬编码输出目的地至 `F:/dp-dev-tmp/pr29eval/checks/fixed-output/`，只重跑 CSP，首次错误日志保留。首轮 flow 的既有截图输出在 `D:/dp-dev/tmp/flownav/shots/`，未修改或清理可能共用的历史截图；这与 selftest 的显式 ROOT 小夹具都是首次验收中发现的 D 盘临时输出例外。
- 三个既有 JS 测试还向当前 worktree 的 `.impeccable/` 写截图；本次新生成的该目录已在核对绝对源/目标路径后移至 `F:/dp-dev-tmp/pr29eval/checks/screenshots-from-worktree/`，没有纳入提交，评估侧也为未来复跑加入这一输出路径映射。
- selftest 和 pytest 每命令最多 600 秒，单个 JS 最多 180 秒，超时杀死该命令子树并记 TIMEOUT，不影响其它会话；日志在 `checks/`。不因预期的纹理环盘失败改变阈值或重跑整个套件。
- `audit.py` 用独立的均值/分位数公式检查 CSV 聚合、种子覆盖、输入 hash、源文件 hash、中文编码和受保护目录的 git diff，并另用最终脚本重跑 2 个 seed/224 行逐列比对，随后清理该小样本临时 CSV；报告中的未测项目不补成 PASS。
