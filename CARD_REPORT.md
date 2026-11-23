# SP 起步预设任务卡报告

基点 `95d3289`，分支 `dev/starter-preset`。A 段按卡要求停止。13 次 RITEKF1 真盘测量构成 156 个有向配对，拟合 `c + L/r` 后 110 个方向仍超出现有网格刻图精度门槛。照片几何形状门槛内有 132 个方向，其中 86 个仍超出网格门槛。现有记录里可核实的跨批和跨同型号机器配对均为 0。 [A 段报告](evidence/starter/REPORT.md) · [阻塞说明](BLOCKED.md)

## 提交

- `f30f0ea`（`Measure RITEKF1 geometry reuse against existing gates`）提交 A 段报告及设备无关的复算脚本，按来源保留摘要 SHA-256，计算修正前后角差和位置误差，检查现有照片、网格及覆盖判据。
- `Record starter preset evidence blocker` 提交停止原因、验收记录和待决事项。

## 验收

- `Get-PSDrive -Name D,F` 开跑前剩余 D 盘 52,707,086,336 字节、F 盘 46,546,345,984 字节。写完 A 段计算后再次检查，D 盘 53,582,508,032 字节、F 盘 46,546,345,984 字节，均超过 5 GB。
- 设置 `TEMP`、`TMP` 为 `D:/dp-dev/tmp/starter`。运行 `python -X utf8 evidence/starter/compare.py --out D:/dp-dev/tmp/starter/pairs.json`，再用同一命令输出到 `pairs-repeat.json`。两次退出码均为 0，输出 SHA-256 同为 `8438293926f535e4d90364d38b052a828de67665aceba13183ac5a5fb6520033`。45 份摘要里入对 13 次实测，另有 3 次模拟和 13 份排除项，真盘重复副本 16 份。
- 冻结照片形状门槛通过 132/156，网格三项均通过 46/156，检查盘范围要求通过 12/156，25–57 mm 出图覆盖通过 0/156。剔除最窄范围测量后网格通过 46/132。注入 1.25 mm 已知偏移的独立算例回收 `1.2500000014 mm`，最大残差 `1.7e-9°`。
- 对提交执行 `git diff --cached --check`，对三份中文 Markdown 执行 UTF-8 字符检查。

## 未测与待决

- B 段未开始。CLI、网页、照片 L 来源绑定和回退功能，默认流程及出图镜像的逐位回归，Disc Lab、截图、pytest、全部 `tests/test_*.mjs` 和 `python -m discprobe selftest` 均未测。没有接光驱或刻盘。
- 跨批或异机偏差需要设备实例、盘批号和足够的实测半径作对照。照片模型中的 L 来自理想角差，真实刻录路径的偏移、摄影信号，以及剩余 S 形弯曲能否被照片稳定拦下均未测。
- 若补证后恢复此卡，需要决定网页默认是否选中和社区数据能否作起点。CD 需单独收集有实例和批号的几何、区分数据与音轨及其读写链路，并验证以帧记录的 L 与同盘多照的来源约束。

STATUS: BLOCKED
