# Disc Lab 场景 / Scenarios (version 1)

场景文件设置虚拟光盘、光驱和故障。只读本地 JSON 和本地 ISO；不访问真实光驱，不使用网络。真值保存在 `LAB/answers.json`，disc-probe 通过原来的 `dp` 子进程和虚拟设备取得回复，不会收到真值参数。

A scenario configures virtual discs, the drive/recorder, and injected faults. Input is local JSON and local ISO files. Private truth stays in `LAB/answers.json`; disc-probe runs through the existing `dp` path and receives device replies, not truth parameters.

```powershell
python -m disclab box --lab results/my-lab --scenario disclab/examples/scenarios/capacity_misreport.json
python -m disclab faults --lab results/my-lab
python -m disclab faults --lab results/my-lab --fault capacity-offset
```

已有 `box` 选项继续有效：文件没有写的字段可由 CLI 补充；两边都明确指定时，值必须相同，否则用一句话拒绝，创建前不写实验目录。未使用 `--scenario` 时走原来的随机生成器，不添加新真值字段。同 seed、同参数的 `answers.json` 字节保持不变。

Existing box flags fill fields omitted from the file. Two explicit values must agree; a conflict is refused in one sentence before lab creation. Without `--scenario`, the original generator and answer bytes are preserved.

## 文件结构 / File structure

所有对象拒绝未知键。所有数值必须有限；整数不接受布尔值。除表中说明外，各字段可省略。`version` 当前只能为 `1`。`discs` 是一盒同种介质；不同介质分开建盒。

Unknown keys are rejected at every level. Numbers must be finite; booleans are not integers. Fields are optional unless stated otherwise. The only supported version is `1`. A box has one media type.

```json
{
  "version": 1,
  "discs": {
    "media": "dvd-r", "count": 2, "seed": 17, "batch": 1, "stampers": 1,
    "mid": "CUSTOM", "capacity": 8192,
    "uv_noise": [0, 0],
    "parameters": {"b_nm": 133.3, "start_radius_mm": 24, "v": 5.591208,
                   "ecc_um": 12, "ecc_deg": 45, "dish_mm": 0.1,
                   "saddle_mm": 0.05, "saddle_deg": 90},
    "defect_arcs": [{"r_mm": [25, 26], "deg": [350, 370]}],
    "initial_state": ["blank", {"state": "partial", "random": true,
                                    "sectors": 4096, "seed": 23, "fraction": 0.4}],
    "overrides": [{}, {"parameters": {"ecc_um": 30}}]
  },
  "drive": {
    "profile": "gh70n",
    "overrides": {"vendor": "DISCLAB", "product": "CUSTOM", "firmware": "LAB2",
                  "mode": "cav", "jitter_us": 13, "outlier_rate": 0.01,
                  "write_speeds_x": {"dvd": [4, 8]},
                  "completion_mm": {"dvd": 0.13}, "head_mm": 0.06},
    "burn_failure": {"kind": "none"}
  },
  "drives": ["X:"],
  "faults": [{"id": "scratch", "kind": "read_error", "params": {"lba": [100, 200]}}]
}
```

| 字段 / Field | 含义、默认 / Meaning and default |
| --- | --- |
| `discs.media` | `dvd-r` (默认 / default), `dvd+r`, `cd-r`, `bd-r` |
| `count`, `seed`, `batch`, `stampers` | 默认 / defaults: 12, 1, 1, 1；seed 非负，其余正整数 / nonnegative seed, other values positive integers |
| `mid` | ASCII；默认介质 MID。DVD-R ≤12 字符；DVD+R 为 `maker/type/revision` (≤8/≤3/0..255)；CD 为 `ATIP mm:ss:ff`；BD ≤64 字符 / default media MID; format restrictions as shown |
| `capacity` | 物理总扇区数，2048 字节用户扇区；默认介质容量，至少32；不是伪报容量 / true physical sectors, default media capacity, minimum 32; distinct from a false report |
| `parameters.u`, `v`, `b_nm` | 槽形参数、位长 nm；正数 / groove ratios and bit length in nm; positive |
| `parameters.start_radius_mm` | 由 `u = radius / (b_nm × 10^-6)` 转换；若同时写 u 必须给 b_nm 且数值一致 / derives u; specifying u too requires explicit b_nm and agreement |
| `ecc_um`, `ecc_deg` | 偏心距离 µm 和方向度 / eccentricity and direction |
| `dish_mm`, `saddle_mm`, `saddle_deg` | 翘曲：碟形高度、鞍形振幅和方向；沿用现有照片模型，不让翘曲凭空造成读错误 / warp components used by existing photo model; no invented read failure from warp |
| `uv_noise` | 原有每片 u 绝对量、v 相对量的随机散布 / original per-disc absolute u and relative v spread |
| `defect_arcs` | 半径范围 mm 和连续角区间 deg，可跨360；例如350..370。显式场景默认无随机缺陷 / radial and unwrapped angular intervals; scenario default has no random flaws |
| `overrides` | 与 count 等长的对象列表；每片可覆盖 `parameters`, `capacity`, `defect_arcs`, `initial_state`；MID 使用整盒字段 / one object per disc; per-disc overrides for listed fields; MID is box-wide |
| `initial_state` | 单项应用全盒，或 count 等长列表；下表说明 / one value for all discs or count entries; see below |
| `drive.profile` | `gh70n` (默认 / default), `slim-clv`, `nofua`, `noisy` |
| `drive.overrides` | vendor/product/firmware 最长8/16/4个 ASCII；mode 为 CAV/CLV（不区分大小写）；jitter_us≥0、outlier_rate 0..1、head_mm -20..20 / field widths and bounds shown |
| `completion_mm` | 家族到读完成偏移 mm 的对象：`dvd`, `cd:mode1`, `cd:mode2form1`, `bd`；部分覆盖 / partial map of completion offsets |
| `write_speeds_x` | `dvd`, `cd`, `bd` 到非空正数列表；不能超出虚拟 MMC 16位速度字段 / nonempty positive speed lists within virtual MMC representation |
| `drive.burn_failure` | `{"kind":"none"}`、`{"kind":"stop_at","fraction":0.4,"report_success":false}`、`{"kind":"fail_close"}`；stop_at 留下前缀，fail_close 留下全部数据但会话开放并报失败 / prefix interruption or full-data close failure |
| `drives` | 不重复的虚拟盘符；默认 `["X:"]`，全部使用同一配置 / unique virtual drive names, sharing the configured reader |

CD 真容量受 MSF 表示范围限制；所有介质真容量也受现有 DVD 结构回复的字段范围限制（最多16580607）。这些限制不改变默认介质的容量。随机几何仍由 seed 决定，显式 parameters 再覆盖每片真值。stamper 表保留原始母盘样本；每片 discs 项才是覆盖后的最终真值。

True CD capacity is limited by MSF; all true capacities also fit the existing DVD structure representation (maximum 16580607). Default media capacities are unchanged. Explicit parameters override the seeded per-disc values. Stamper records retain the generated base samples; final per-disc truth is authoritative.

## 初始状态 / Initial state

| `state` | 内容 / Content |
| --- | --- |
| `blank` | 无数据；可简写成 `"blank"`，不能附带 ISO 设置 / no data, no image settings |
| `burned` | 全部图像写入并封盘 / image recorded and closed |
| `open` | 全部图像写入但会话开放 / image recorded, session open |
| `partial` | 只写 `floor(image_sectors × fraction)` 扇区，会话开放；fraction 默认0.5、范围[0,1) / recorded prefix, open; default fraction 0.5 |

后三项可写 `iso`（相对 scenario.json 的本地路径，复制进 LAB/iso），或者 `random:true, sectors:4096, seed:1`。随机 ISO 由原来的 `dp random` 生成；sectors 默认 min(4096, capacity)，至少32，不得超过容量；不可同时指定两种来源。真值记下来源、完整 ISO 的 SHA256、实际写入长度，虚拟 READ 在前缀后返回 5/21/00，不会把未写区域伪装成有效数据。

Recorded states take either a local `iso` path, relative to the scenario file and copied into LAB/iso, or `random:true` with optional sectors/seed. Random data uses `dp random`. Truth records the source, full-image SHA256, and written prefix. Reads past that prefix return 5/21/00.

## 故障 / Faults

每项必须给 `id`, `kind`；`params` 为对象。id 为1..64个字母、数字、下划线或短横线，不能重复。所有 params 可选 `disc`，值是盒内标签（如 `LAB-A 1-01`）；省略时影响所有光盘。所有故障真值都写入 answers，原有 SCSI allowlist 仍是每个虚拟命令的第一道检查。

Each fault requires a unique id (1..64 ASCII letters/digits/underscore/hyphen) and kind. Params optionally selects one disc label; omission affects all discs. All virtual SCSI commands still enter the original allowlist first.

| kind | params 和实际行为 / Parameters and behaviour |
| --- | --- |
| `read_error` | `lba:[start,end]`（半开）或 `r_mm:[lo,hi]` 二选一。READ(10)/(12) 请求覆盖范围与故障相交便返回 medium error `3/11/00`，保留重试耗时 / intersecting reads return medium error, including narrow bands |
| `spindle_unsteady` | `amplitude` 默认0.15、(0,0.8]；`rate_hz` 默认1、>0；`time_s` 默认0（每次打开设备的虚拟时钟）；`lba` 默认0；`mode` 为 `drift`（默认）或 `jump`。达到时间和LBA条件后保持激活；转速乘 `1 + amplitude × sin(2π rate_hz elapsed)`，jump 使用 `1 + amplitude`。每次读更新转速，保持相位连续；CLV 重锁也保留扰动 / read-sampled angular-speed perturbation with continuous phase, latched activation |
| `capacity_misreport` | `offset`（有符号整数）或 `sectors`（正整数）二选一；修改 READ CAPACITY 的已写长度、DISC INFORMATION 的总容量、TRACK INFORMATION 的长度/剩余量；数值夹到1..2^32-1，CD leadout再夹到MSF范围。实际可读边界不变，其他结构回复保持真容量 / false metadata only; actual readable boundary unchanged |
| `burn_interrupt` | `fraction` 默认0.5、[0,1)；`report_success` 默认 false。记录前缀且会话开放，再报写入失败；true 时假报成功。故障优先于 drive.burn_failure；多项烧录故障按列表最后一项生效 / prefix is persisted; optional false success; last matching burn fault overrides drive failure |

同 kind 多项：读错取并集，转速因子相乘，容量按列表顺序计算，刻录故障最后一项生效。场景建好后直接 `tray` + `dp` 会同时启用所有故障。

Repeated kinds combine as union (read), multiplication (spindle), ordered capacity transforms, and last matching burn rule. Direct tray/dp use enables every fault together.

## 评分 / Scoring

`faults` 在 `LAB/scores/fault-runs/<unique-run>/<id>/<command>/` 建独立实验副本，每次只启用被评分的一个故障；原始 answers/state 不改。光驱覆盖仍生效，因此这种配置也可能影响结果。读实验保留原先已写数据；原盘空白时准备最多4096扇区的已写样本。刻录实验用同真值的新空白样本，防止“原盘已封盘”遮住刻录故障。每个副本的 `fixture.json` 明确记录准备方式和来源真值哈希。

Each score uses a separate assay copy with one fault active; the source answers/state remain unchanged. Reader overrides remain active. Read assays retain recorded source data, or prepare up to 4096 sectors for a blank source. Burn assays use a fresh virtual blank with the same physical truth. Fixtures record preparation and source hashes. Thus `all-faults.json` produces isolated per-fault scores, not a causal attribution of a simultaneous multi-fault run.

运行矩阵：read_error → info/timing/geo/burn；spindle_unsteady、capacity_misreport → info/timing/geo；burn_interrupt → burn 和带 `--no-verify` 的 burn。小实验使用 timing reps12、period_reads24，geo reps12、max_targets6；单子进程最多120秒，超时记 crash。

The matrix and bounded measurement settings are as listed above. A process timeout is scored as crash. Commands run sequentially through `dp`; no server or hardware is used.

| class | 判据 / Rule |
| --- | --- |
| `detected` | failure.reason、summary.stopped、结构化警告或 stderr/明确 stdout 警告匹配下列故障用语；仅在普通结果中出现故障词不算 / relevant explicit stop or warning |
| `silent_wrong` | 退出0，但已评估的结果与真值不符 / successful process with a wrong result |
| `unaffected` | 退出0，输出可评估且与真值相符；只限本命令与采样范围 / assessable correct result for this command and sample |
| `crash` | traceback、超时、无匹配理由的非零退出，或缺少可评分结果 / traceback, timeout, unexplained exit, or missing assessable output |

期望用语 / Expected warning vocabulary (exact regex lists are also saved in each score):

- read_error: `3/11/00`, `medium error`, `unreadable`, `cannot read this disc`.
- spindle_unsteady: `spindle did not reach a steady speed`, `spindle speed never settled`, `no clear/stable period`, `speed may be changing`, rotation mixed/unknown, `cache/false period`, `reference has no clear period`.
- capacity_misreport: capacity mismatch/inconsistent/wrong, `5/21/00`, `out of range`.
- burn_interrupt: `write interrupted`, `session close failed`, `5/21/00`, read-back failed, a nonzero unreadable count.

数值判据：info 的 DISC INFORMATION 总容量对照真实物理容量，info/measurement 的已读扇区数和 track size 对照真实已写长度；非 CD 总容量按原始回复的扇区数解释，避免把通用 MSF 解析当作 DVD 真值。timing 相位与同一读块的真值比较，最大误差5度；geo 在实际报告的测量半径内取65点，对照读完成几何真值，去掉常数旋转后 RMS≤5度。geo 不把小样本外推成整盘正确。burn 对照实际长度、封盘状态和 burn_result；有回读警告即 detected，即使它仍把 write 标记 completed。

Oracles compare DISC INFORMATION total sectors to physical capacity, and readable sector counts and track size to written truth, timing phases to block-end truth (5-degree maximum error), and geo's timing curve on 65 points within its measured span (5-degree RMS after removing a constant rotation). Burn compares actual prefix and closure to the claimed completion. Read-back warnings count as detection even when the write result still says completed.

`scores/faults.json` 含 version、source_fault_ids、isolation、rows。每行含 fault、command/argv、expected、observed、class、fixture、evidence_paths；逐行另存 score.json，stdout/stderr 和原始结果保留。产品发现不影响 faults 的退出码（仍为0）；只有 Disc Lab 本身无法准备/读写/评分才非零。`--fault` 不存在会非零。

The JSON report is the structured interface for a future shell. Findings do not change the CLI's zero exit status; preparation/I/O/scorer failures do. See [FAULTS_REPORT.md](FAULTS_REPORT.md) for observed results and modelling limits.
