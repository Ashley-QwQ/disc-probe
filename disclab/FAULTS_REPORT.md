# 场景与故障实测报告

这次实验发现了两类漏报：disc-probe 接受了假的容量；刻录只写入一部分却报告成功时，关闭回读校验会让它把残缺盘当成完成。有回读校验时，它能列出读失败的块，但刻录结果仍写成 `completed`。这些发现保留在评分中，没有修改 disc-probe 来改变结果。

本机为 Windows、Python 3.13.14、disc-probe 0.1.2.1，工作基线为 `2ec80ce`，日期为 2026-11-13。先检查了上一次留下的修改和实验结果，再接着完成；原来的 `results/fault-examples/` 保留。下面以缩小后的五份样例为准，原始输出在 [本次实验目录](../results/fault-examples-small-20261113/)，[manifest.json](../results/fault-examples-small-20261113/manifest.json) 记录场景哈希、退出码、耗时和源数据未变检查。

## 条件与判据

每份样例一张 DVD-R，物理容量 8192 扇区，初始写入 4096 扇区（8 MiB）。读错覆盖 `[0,4096)`；转速按振幅 0.3、频率 2 Hz 扰动；容量增加 1024 扇区；刻录中断比例为 0.4，并故意报告成功。刻录实验也只用 4096 扇区。没有生成整盘 ISO。

`faults` 逐条、逐命令建立独立副本；读实验保留初始数据，刻录实验准备同一物理真值的空白盘。每个副本只激活当前故障，保留光驱设置。`all-faults.json` 的表是四个独立故障实验的合集；它不代表同时开启四种故障后的因果归属。直接用该场景的 `tray` 和 `dp` 则会同时启用四项故障。

所有被测命令经现有 `dp` 子进程运行。每行的 `expected.reason_patterns` 保存允许的诊断用语，`observed` 保存实际退出码、诊断、真值比较和超时/traceback 状态，`evidence_paths` 指向原始输出和独立真值。匹配相关警告/停止才算 `detected`；退出 0 且结果错误算 `silent_wrong`；结果可评分且正确才算 `unaffected`；traceback、超时、没有匹配故障理由的非零退出，或缺失可评分结果算 `crash`。这里的 `crash` 也包含错误归因的停止，不能直接理解成 Python 崩溃。

info 比较真实已写长度、轨道长度和 DISC INFORMATION 物理容量；后者按介质的原始回复格式解释。timing 相位最大误差容限为 5 度；geo 在实际测量半径内取 65 点，比较包含完成偏移、头偏移、偏心和变螺距的计时真值，去掉常数旋转后的 RMS 容限为 5 度。小范围符合不代表整盘符合。burn 比较写入长度、封盘状态和完成声明；相关回读警告优先计为检测。

## 逐命令结果

下表“单项”和“合集”分别指对应的单故障样例和 `all-faults.json`。两次分类一致，合计 24 行：12 行 `detected`、6 行 `silent_wrong`、4 行 `unaffected`、2 行 `crash`。

| 故障 | 命令 | 单项 | 合集 | 被测退出码 | 实际表现 |
| --- | --- | --- | --- | --- | --- |
| read_error | info | unaffected | unaffected | 0 | 容量、轨道元数据正确；这不保证数据区可读 |
| read_error | timing | detected | detected | 1 | 明确报告 medium errors `3/11/00` 后停止 |
| read_error | geo | detected | detected | 1 | 明确报告 medium errors `3/11/00` 后停止 |
| read_error | burn | detected | detected | 0 | 回读 96 块全部不可读，打印警告；结果仍为 completed |
| spindle_unsteady | info | unaffected | unaffected | 0 | 元数据正确；info 不测转速稳定性 |
| spindle_unsteady | timing | detected | detected | 0 | 报 rotation mixed，停止相位流程 |
| spindle_unsteady | geo | detected | detected | 1 | 报 spindle speed never settled 后停止 |
| capacity_misreport | info | silent_wrong | silent_wrong | 0 | 实写 4096，却报可读 5120；物理容量 8192，却报 9216 |
| capacity_misreport | timing | silent_wrong | silent_wrong | 0 | 保存可读 5120；只警告 rotation unknown，没有指出容量问题 |
| capacity_misreport | geo | crash | crash | 1 | 报 no random data found in the recorded area，没有指出容量问题 |
| burn_interrupt | burn | detected | detected | 0 | 只写 1638，未封盘；96 块回读中 38 块正常、58 块不可读，结果仍为 completed |
| burn_interrupt | burn --no-verify | silent_wrong | silent_wrong | 0 | 同样只写 1638、未封盘，却无相关警告并报告 completed |

容量实验中的 timing 确实停止了后续相位测量；`silent_wrong` 指它成功退出并保存了错误可读长度，同时没有给出容量故障的相关诊断，不是说它完成了正确的相位拟合。两条 `crash` 都没有 traceback，也没有超时，是未识别容量问题的非零停止。之前较大样本的 geo 分类与本次不同，不能把之前的分类移用到这次 4096 扇区实验。

| 场景 | 评分行数 | box / faults 退出码 | 首次小样本运行耗时（秒） | 评分 JSON |
| --- | --- | --- | --- | --- |
| read_error | 4 | 0 / 0 | 10.358 | [faults.json](../results/fault-examples-small-20261113/read_error/scores/faults.json) |
| spindle_unsteady | 3 | 0 / 0 | 7.039 | [faults.json](../results/fault-examples-small-20261113/spindle_unsteady/scores/faults.json) |
| capacity_misreport | 3 | 0 / 0 | 6.459 | [faults.json](../results/fault-examples-small-20261113/capacity_misreport/scores/faults.json) |
| burn_interrupt | 2 | 0 / 0 | 9.665 | [faults.json](../results/fault-examples-small-20261113/burn_interrupt/scores/faults.json) |
| all-faults | 12 | 0 / 0 | 22.467 | [faults.json](../results/fault-examples-small-20261113/all-faults/scores/faults.json) |

实验输出保留在本地仓库的 results 中，不随独立 Disc Lab 包分发。每次重跑会使用新的证据目录，并更新该 lab 的 `scores/faults.json`。

## 验证与边界

验收命令为 `python -m pytest disclab/tests -q`：97 项通过，包括原有 30 项未改测试和 67 项场景/故障测试。覆盖冲突提前拒绝、严格类型检查、原始默认答案字节哈希、四种初始状态及实际读边界、四种故障、CAV/CLV 扰动、正常报失败/假报成功、封盘失败、零比例中断、分类器、超时证据保存，以及真实子进程的小场景闭环。两组默认箱字节哈希与改动前一致；原有 box、physics、score、原有测试和整个 discprobe 目录无修改。

本次所有临时目录、pytest 基目录、实验目录、ISO、日志和缓存均放在 D 盘；每次运行显式设置 TMP/TEMP，pytest 也显式指定 D 盘基目录。渲染波形缓存沿用用户指定的 D 盘位置，本任务没有重建波形缓存；原有照片测试读取随包的波形表。新测试和故障样例均使用小图像；原有便携性测试仍使用 65536 扇区的几何拟合样本，保留其数值验收行为，没有使用整盘图像。流程顺序运行，工作进程设置保持 3，数值库线程数为 1。未访问网络、未启动服务器、未接触真实光驱；网页/上传的原有测试使用替身。

尚未建模或验证的部分：

- 读错是确定性 LBA/半径区间，没有概率性恢复、ECC 分级或真实固件重试曲线。缺陷弧沿用离散抽样，窄角缺陷可能漏采；显式 read_error 区间会检查整个命令跨度。
- 转速扰动在每次读取时更新，读内按当前角速度积分，保持更新时的相位连续；没有连续机电动力学、温度或伺服闭环。时间从每次打开设备起算，达到时间与起始 LBA 条件后保持激活。
- 容量故障只改 READ CAPACITY、DISC INFORMATION 和 TRACK INFORMATION。其他结构/TOC 仍可保留真实值；未覆盖所有 MMC 格式、固件或多层盘情形。
- 中断保留虚拟已写前缀和开放会话，不模拟断电后的物理损坏、掉电恢复或异步硬件写入。正常报失败与 fail_close 有单元验证，样例表使用假报成功这一变体。
- 初始已写状态建立 ISO 与会话记录，未自动建立照片用极坐标图；本任务没有验证这些初始状态的完整照片流程。BD 可作为虚拟读盘，disc-probe 自身仍会拒绝 BD 刻录命令。
- 分类按列出的诊断用语和声明的数值容限作出；换版本、换文案或不相关的光驱设置可能影响结果。这里没有证明某条警告只可能由被注入故障造成，也没有进行 Linux、真实光驱或全盘精度验证。

格式、字段范围和复现命令见 [SCENARIO.md](SCENARIO.md)。产品的漏报、错误结果和无关停止都保留；`faults` 自身成功完成时退出 0，准备或读写实验失败才非零。
