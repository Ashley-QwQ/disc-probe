# 蓝光光盘几何测量：模型、算法、实现与实测结果

写给接手这套东西的另一个 AI（或另一个工程师）。读完应该能：读懂 `discprobe/clv.py` 的每一行在算什么、
判断一次运行的结果可不可信、把结果导出成 DiscImageStudio 能直接用的蓝光预设、并且在需要时改这里面的任何一环。

代码位置：`discprobe/clv.py`（解算）、`discprobe/geo.py`（角度梯子 + 蓝光分支）、
`discprobe/__main__.py`（`cmd_geo` / `_geo_clv` / `_disexport_bd`）、`discprobe/bdexport.py`（预设）、
`discprobe/sim.py`（仿真驱动器）、`discprobe/timing.py`（周期测量）。测试在
`tests/test_bd_clv_solver.py`、`tests/test_bd_preset.py`、`discprobe/selftest.py::_bd_clv` / `_bd_export`。

---

## 0. 一句话结论

一支普通 BD-RE 光驱，用 `geo --media bd` 读 25 个区域各几十圈，能在 **6 分钟内**得到
`r0 = 24.677 ± 0.015 mm`（扇区 0 的半径）、`pitch = 0.3200 µm`（锚定标准值后自洽）、外径 `58.02 mm`，
再由 `disexport` 写进 DiscImageStudio 的蓝光预设，那里三个数就够复现整条螺旋。

---

## 1. 为什么"读数"能测几何

盘上是一条从内到外、间距 `p` 的螺旋。第 `n` 个扇区所在半径满足面积关系

```
π (r² − r0²) = p · S · n          ⟹     r(n)² = r0² + (p S / π) n
```

其中 `S` 是一个扇区占的弧长。蓝光：1 个 recording unit = 32 扇区，含 962 136 个通道位，
每个通道位 74.50 nm，所以

```
S = 962136 / 32 × 74.5 nm = 30 066.75 × 74.5 nm = 2.239 470 mm
```

**CAV 盘**（恒定角速度，压盘 BD-ROM 常见）：转速固定，一圈的时间与半径无关，读完时刻只告诉你
"转了几圈"，所以 `geo` 用的是角度梯子 `θ(n) = 2n / (√(u² + v n/π) + u)`，`u = r0/b`、`v = p/b`。

**CLV 盘**（恒定线速度，BD-RE 与未封盘 BD-R 常见）：线速度 `v` 固定，读完一个扇区的时间就是它走完
那段弧的时间。于是

```
T(n) = 2π r(n) / v
T(n)² = b + a·n ,     b = (2π r0 / v)² ,     a = 4π p S / v²
```

这就是整套东西的核心：**T² 对 LBA 是一条直线**，斜率给 `a`、截距给 `b`。

注意量纲：`T` 用 ms、`v` 用 mm/ms（数值上等于 m/s）、`S` 用 mm，则 `a` 是 ms²/LBA、`b` 是 ms²。
写代码时最容易错的就是这里——把 `v` 再除以 1000 会得到 0.78 mm 的半径（我犯过）。

---

## 2. 三个未知数、两个方程：必须锚一个

一次回归只给 `a`、`b` 两个数，而盘有 `(r0, p, v)` 三个未知量。但它们的组合

```
b/a = π r0² / (p S)
```

**不含 v**。所以：

| 锚定什么 | 能解出什么 | 用什么 |
|---|---|---|
| `p`（默认 0.32 µm） | `r0`、`v` | 标准值精度 0.3%，最稳 |
| `v`（`--linear-mm-s`） | `r0`、`p` | 由持续吞吐量反推速度，精度 ~1e-5 |
| 都不锚 | 把 `(p, r0)` 钉在 1×（4.917 m/s） | 只用于仿真自检，`anchor` 字段会写明 |

实测里 `p` 始终是锚：`p` 的标准值是 0.320 ± 0.001 µm，而自测速度的误差会以 1e-5 量级进 `p`；
反过来说，锚 `p` 之后算出的 `v = 10.390 m/s` 与"2.1× 名义 10.33 m/s"吻合到 0.6%，是个旁证。

---

## 3. 周期是怎么测出来的

`timing.py` 里的探针做这些事，每一步都影响结果能不能用：

1. **命令**：`READ(12)` 带 FUA 位，32 扇区一次读（一个 recording unit）。
2. **清缓存**：先读一个远处的 LBA，再读目标，确保测的是盘不是 RAM。蓝光上远读要 ~300 ms。
3. **计时**：记录 SCSI 请求的完成时刻，同一点重复 `reps` 次，取中位数，同时算 `coherence`
   （重复性）与 `jitter`（离散度）。
4. **恒速检查**：`SET CD SPEED` 请求某个速率；同一张盘换速率，`T` 会等比变，`T²` 直线的**形状**不变。

`coherence` 不是万能门：它只证明"周期在重复"，不证明"重复的是主轴"。实测抓到过一个区域
报 `T = 85.71 ms`（应为 42.9 ms，正好两圈）而 `coherence = 0.9993`——二次谐波锁相也能通过这道门。
处理方法见第 4 节的 MAD 剔除。

---

## 4. 估计量与误差：五个必须做对的地方

### 4.1 在周期空间拟合，不在 T² 空间

误差落在"它计时的那一圈"上（相对误差），平方之后外圈被放大，而 OLS 是等权的。所以在
`t = √(a·x + b)` 上做 Gauss-Newton（`clv.py::_period_fit`）：

```
雅可比列   [ x/(2s), 1/(2s) ],  s = √(a x + b)
每一步折半，保持 a, b > 0；收敛 atol = 1e-14
协方差    cov = s² · (JᵀJ)⁻¹,  s² = Σ(t−model)²/(n−2)
```

### 4.2 方差要带协方差交叉项

```
∂r0/∂a = −r0/(2a) ,   ∂r0/∂b = +r0/(2b)
Var(r0) = r0² [ cov_aa/(4a²) + cov_bb/(4b²) − cov_ab/(2ab) ]
```

只取对角项会**低报 1/3**：九区域、20 µs 噪声的仿真里，对角项给 29.5 µm，真实散度 41.4 µm，带交叉项给 37.6 µm。
校准检查写在 `selftest` 里：120 次固定种子仿真，`claimed/scatter` 必须落在 0.6–1.5。

### 4.3 周期偏置：3σ 规则

如果存在一个与周期无关的固定延迟 `ε`（FIFO、servo），它会把 `r0` 移动 `ε·v/2π`：

```
t = √(a x + b) + ε
```

`--fit-offset` 会同时拟合 `ε`。但 9 个区域时它几乎不可辨，`bdreal6` 那次给出 `ε = −194.5 ± 85.1 µs`
（2.3σ），扣掉它会把内径报到 25.01 mm（真值 24.66），误差 0.35 mm。**所以只有 |ε| ≥ 3σ 才真的扣**，
否则保留拟合值到 `offset_fitted_ms` 但不使用。25 个区域那次 `ε = −246 ± 104 µs` 同样被留用外。

独立证据：同一张盘 1.6× 跑出 24.6399 mm、2.1× 跑出 24.6611 mm，只差 21 µm；若真有 0.5 ms 偏置，
两速之间应差 `ε(v₁−v₂)/2π ≈ 0.2 mm`。所以 `ε ≈ 0`，offset 拟合在这类盘上是诊断项、不是必需项。

### 4.4 剔除：coherence 门限 + MAD + 断点

- `coherence < 0.90` 直接不用（`COHERENCE_FLOOR`）。上电过渡态（盘还在从高速降速）通常落在这里。
- 剩下的人在 `T²` 空间做 4σ 的 MAD 迭代剔除，最多 3 轮，至少留 3 点（`fit_t2`）。
- **断点检测**（`_break_fit`）：对每个可能的断点位置拟两条直线，要求残差本身有量级（`rms ≥ 5 µs`）、
  残差改善 ≥ 50%、F 统计 ≥ 20。三道门缺一不可——完美直线上任何断点都能"解释"掉一大截残差。
  这是 Z-CLV（分区恒速）盘的识别器：它的 `T²` 是两段直线，一条直线拟合出来的 `r0` 没有物理意义
  （早期三次失败运行曾给出 7–12 mm 的半径）。

### 4.5 外推距离

`r0` 是从直线的**曲率**外推出来的，通常落在所有测量区域之内（更小的半径处）。`ClvFit.r0_extrapolated_mm`
= 最内测量区半径 − `r0`。超过 0.5 mm 时 CLI 会提醒"这个数是曲率给的，不是在那里量到的"。
`--bd-zones 25` 时它通常是 6 mm 左右（区域从 29 mm 开始）。

---

## 5. 程序结构与数据流

```
 geo --media bd
   ├─ _geo_clv(args)                       __main__.py
   │    ├─ ClvLadder(...)                  clv.py      打开驱动器、设速率
   │    ├─ tp.setup() / cache_test()       timing.py   先量转速与缓存策略
   │    ├─ precheck_by_measuring()         量两个区域（0.5、0.95）判 CAV/CLV
   │    │     └─ 若 CAV：raise ConstantAngularVelocity → 交棒角度梯子（第 8 节）
   │    ├─ period_test(zones)              timing.py   每个区域 reps 次读，取中位数
   │    ├─ fit_t2(samples, ...)            clv.py      coherence 门限 → MAD → 周期空间 GP
   │    │     ├─ _offset_fit()（可选）     3σ 规则
   │    │     └─ _break_fit()              断点
   │    └─ write_outputs()                 clv.py      zones.csv + summary.json
   └─ disexport --geo <run> --sectors N
        └─ _disexport_bd → bdexport.export() → 预设（打印 / --output / --install）
```

### 5.1 `clv.py` 的主要符号

| 名字 | 作用 |
|---|---|
| `Sample(lba, period_ms, coherence, fraction)` | 一个区域的测量 |
| `fit_t2(samples, sector_mm, pitch_um=None, v_m_s=None, drop_outliers=True, clip=4.0, fit_offset=False)` | 主拟合，返回 `ClvFit` |
| `_period_fit(x, t, a0, b0)` | 周期空间 Gauss-Newton，返回 `(a, b, cov)` |
| `_offset_fit(x, t, a0, b0)` | 拟合 `ε`，返回 `(ε, σ_ε)` |
| `_break_fit(x, y)` | 断点检测 |
| `classify_rotation(perf, ...)` / `classify_from_zones(zones)` | 由 GET PERFORMANCE 或实测周期判 CAV/CLV |
| `ClvFit` | `r0_mm, pitch_um, v_m_s, slope_ms2_per_lba, intercept_ms2, r2, n, anchor, sigma_*, dropped, zones_dropped_lbas, break_fit, offset_ms, offset_fitted_ms, r_first_mm, r0_extrapolated_mm` |
| `ClvLadder` | 驱动器 + 九个默认区域 + 预检 + 拟合 |
| `write_outputs` | `zones.csv`（每区域）与 `summary.json`（`fit` + `derived` + `rotation_measured` + `zones_unstable`） |

### 5.2 `summary.json` 里重要的键

```jsonc
{
  "fit": {
    "model": "clv", "media": "bd",
    "r0_mm": 24.6655, "pitch_um": 0.32, "v_m_s": 10.39,
    "slope_ms2_per_lba": 8.34331e-5, "intercept_ms2": 222.5,
    "r2": 0.9999974, "zones_used": 23, "anchor": "pitch 0.32 um",
    "sigma_r0_mm": 1.37e-5, "sigma_pitch_um": null, "sigma_v_m_s": 0.0004,
    "r_first_mm": 29.14, "r0_extrapolated_mm": 4.47,
    "offset_ms": 0.0, "offset_fitted_ms": -0.0001945, "sigma_offset_ms": 8.51e-5
  },
  "rotation_measured": {"mode": "CLV", "period_ratio": 1.276, "radius_ratio": 1.279},
  "derived": {"outer_radius_mm": 58.0214, "last_lba": 12088319, "full_layer": false},
  "zones_unstable": [0.05]
}
```

`zones.csv` 每行一个区域：`fraction, lba, period_ms, rpm, coherence, jitter_us, nominal_radius_mm`。

---

## 6. 预设导出：三个数进 DiscImageStudio

### 6.1 那边要什么

```csharp
record BluRayDiscParameters(uint TotalSectors = 12_219_392, int LayerCount = 1,
    double InnerRadiusMm = 24.0, double OuterRadiusMm = 58.0, double StartAngleDegrees = 0,
    double PitchLinear = 0, double PitchQuadratic = 0, double PitchCubic = 0,
    uint? UsableSectors = null);
```

`Validate()`：层数必须 1、扇区数是 32 的倍数且 ≤ 12 219 392、`0 < inner < outer ≤ 60`、`StartAngleDegrees == 0`。

**三个 pitch 系数不是微米**：`DvdTrackGeometry` 里写的是

```
dr/dθ = b (1 + c1 x + c2 x² + c3 x³),   x = (r − ri)/(ro − ri)
```

即相对形状修正。常数轨距 = 三个系数全 0，DiscImageStudio 自己用二分法从三个数解出一个恒定
`EffectiveTrackPitchMicrometers = 2π·growth`。把 0.32 填进 `pitchLinear` 会被读成"外缘轨距是 p0 的 1.32 倍"。
DiscImageStudio 自带的五个蓝光预设系数也全是 0。

### 6.2 我们算什么

```
innerRadiusMm = r0_mm
outerRadiusMm = √(r0² + p·S·N/π)      （N = 总扇区数，S = 2.239470 mm）
usableSectors = N − 1024              （默认留 2 MiB 给 lead-out）
```

`bdexport.check()` 照抄那边的校验条件与文案，写之前先过一遍。

### 6.3 写到哪里（这个坑踩过）

DiscImageStudio 1.5.0 读的是 **`%LOCALAPPDATA%\DiscImageStudio\disc-presets.json` 的 `bluRayPresets` 数组**
（schema 4，条目是扁平字段 `id / displayName / description / totalSectors / innerRadiusMm / outerRadiusMm /
invertMapping / usableSectors`）。它源码里另有一个 `BluRayPresetStore`（写独立的 `blu-ray-presets.json`），
但**整个应用没有任何地方引用它**——我们一开始就往那个文件写，DIS 界面里什么都没有。

`--install` 现在写对的那个文件：保留文件里其他内容、同值幂等、`--replace` 才覆盖、时间戳 `.bak`、`os.replace` 原子写。

### 6.4 验证过的事

- 操作者的 DIS 1.5.0 里出现了 `BD-RE (drive-timing calibration)`：内 24.665461、外 58.021352、扇区 12 088 320。
- 用三个数复跑 DIS 自己的二分（精确弧长积分）：得到 **0.320000 µm**，即我们锚的轨距在它的模型里自洽。
- DIS 的**刻录**只支持 virgin 单层 SRM BD-R（`WindowsImapiBurner` 硬拒 BD-RE 与已格式化 BD-R），
  所以那张 BD-RE 只能读不能刻；普通烧录器会把 virgin BD-R 格式化成 12 088 320 扇区 / 内径 ~24.66 mm，
  即"正好是我们预设描述的那种盘"。

---

## 7. 实测结果（同一张 BD-RE，只读，`G:`）

| 运行 | 区域数 | r0 (mm) | σ_r0 (µm) | v (m/s) | R² | a (×1e-5 ms²/LBA) | b (ms²) |
|---|---|---|---|---|---|---|---|
| 051012 | 23 | 24.6624 | 14.0 | 10.390 | 0.9999973 | 8.34402 | 222.4 |
| 051355 | 23 | 24.6898 | 15.1 | 10.393 | 0.9999969 | 8.33935 | 222.8 |
| 052047 | 23 | 24.6655 | 13.7 | 10.390 | 0.9999974 | 8.34331 | 222.5 |
| 053859 | 23 | 24.6909 | 15.0 | 10.393 | 0.9999970 | 8.33950 | 222.8 |
| 053317 | 6 | 24.6623 | 42.7 | 10.377 | 0.9999966 | 8.36456 | 223.0 |
| 053416 | 6 | 24.7342 | 37.8 | 10.384 | 0.9999974 | 8.35409 | 224.0 |
| 053509 | 5 | 24.7131 | 58.7 | 10.380 | 0.9999959 | 8.36065 | 223.8 |
| 054613 (1.6×) | 22 | 24.6575 | 14.5 | 7.915 | 0.9999968 | 14.37775 | 383.1 |
| 055112 (1.6×) | 11 | 24.6438 | 27.6 | 7.907 | 0.9999940 | 14.40770 | 383.5 |

四次 25 区域运行：**均值 24.6772 mm，极差 28.5 µm**，与单次形式误差 14–15 µm 同量级。
两个速度档的 `b/a` 一致到 **0.13%（≈20 µm 半径）**，而两档的周期平方差 73%——这是模型正确的最直接证据。

### 为什么是 24.66 而不是标准的 24.0

这张盘只有 12 088 320 扇区（满层 12 219 392 少 1.07%）：格式化时分配了内圈备用区，逻辑 LBA 0 被推后。
同样数据区里扇区数少了，起点必然更靠外。四条独立校验都指向同一组数：

1. 以 `r0 = 24.677`、`p = 0.32` 外推最外扇区 → **58.024 mm**；DiscImageStudio 自带 BD-25 是 58.0232 mm，差 3 µm。
2. 反过来用 58.0232 与同一扇区数 → 内径必须 24.6698 mm；实测 24.677 mm，差 7 µm（0.5σ）。
3. 锚 `p = 0.32 µm` 反出的速度 10.390 m/s 与"2.1× 名义 10.33 m/s"差 0.6%。
4. DiscImageStudio 用三个数做它自己的二分 → 0.320000 µm。

### 负结果：加权最小二乘更差

按区内 jitter 的 `1/σ²` 或 `coherence⁴` 加权，五个 25 区域运行的 r0 一致性从等权的 25 µm 恶化到 **217 µm**。
原因：jitter 反映区内介质噪声，不是"该区域平均周期"的误差。所以维持等权 + 硬性 coherence 门限。

### 池化（九次运行 142 个区域）

公用一个 `k = B/A` 的 Gauss-Newton 给 `r0 = 24.6620 mm`，形式误差 0.9 µm，但单次之间散 92 µm。
池化是自洽性检查，**不是 1 µm 精度的声明**——每次运行有自己的系统项。

---

## 8. 恒定角速度的蓝光：自动换仪器

压盘 BD-ROM 常被驱动以 CAV 读，这时 `T` 与半径无关，`T²` 拟合没有信息。`geo --media bd` 先量两个区域
（0.5 与 0.95）判旋转：

```
|T比/r比 − 1| < 0.10  → CLV
|T比 − 1| < 0.05      → CAV   → 抛 ConstantAngularVelocity，交棒角度梯子
否则                  → unknown（继续按 CLV 做，结果里会写）
```

交棒时把 `--sectors` 设成 32（一个 recording unit），改跑 `geo` 的角度梯子：`_n_end` 用
`((LBA/32)+1)·32·(962136/32)`，拟合 `u = r0/b`、`v = p/b`，`dis_equivalent` 里带
`inner_radius_mm` 与 `pitch_um_estimate`，`disexport` 直接拿这两个数出预设。
仿真自检：24.02 mm / 0.3185 µm 回收 24.02000 / 0.318500，chi²/dof 1.10。

---

## 9. 限制与没做的事

- **单层**：扇区数 > 12 219 392 直接拒绝（双层 LBA 在层间跳变，一条螺旋的假设不成立）。
- **Z-CLV 拒绝**：断点检测命中时不给预设，只说明"这是分区读法的样子"。
- **`p` 是锚**：同一次运行里 `v` 与 `p` 不可分；要自测 `p` 得用 `--linear-mm-s` 给一个独立的 `v`。
- **两个速率档**：这支 UJ272 只给 7.91 / 10.39 m/s（请求 1× 也被封顶到 7.91），没法加第三条腿互检。
- **没有 DIS 1.5.0 的真机导入回归**：只在操作者机器上看过一次，没有自动化。
- 只测过一张 BD-RE；BD-R（未封盘）与压盘 BD-ROM 只有仿真覆盖。

---

## 10. 复现

```bash
# 测量（默认九个区域；25 个更稳）
python -m discprobe geo --drive G: --media bd --bd-zones 25
# 换一个速度档（有些盘只给两档）
python -m discprobe geo --drive G: --media bd --speed 7193 --bd-zones 25
# 只要诊断，不写预设
python -m discprobe geo --drive G: --media bd --bd-zones 25 --fit-offset

# 看结果列表
python -m discprobe results

# 出预设（打印）/ 写文件 / 直接装进 DiscImageStudio
python -m discprobe disexport --geo results/geo-G-20261108-052047 --sectors 12088320
python -m discprobe disexport --geo results/geo-G-20261108-052047 --sectors 12088320 --output bd.json
python -m discprobe disexport --geo results/geo-G-20261108-052047 --sectors 12088320 --install

# 仿真：CLV 与 CAV 两条路径
python -m discprobe geo --sim clv --media bd --linear-mm-s 39336
python -m discprobe geo --sim cav --media bd

# 自检
python -m discprobe selftest
python tests/test_bd_clv_solver.py
python tests/test_bd_preset.py
```

---

## 11. 接手时最该先看的六个坑

1. **单位**：`v` 用 mm/ms 时数值就是 m/s；`T` 用 ms；`S` 用 mm。任何"再乘/除 1000"都先怀疑。
2. **`_build_parser()` 返回三元组** `(parser, sub, {"cd": ..., "bd": ...})`，改它会同时影响 `completion.py` 与 `ui_selftest`。
3. **`--media bd` 的默认值**在 `_build_parser` 的 `bd_defaults` 里（r0 24.0、pitch 0.32、bit 74.5、speed 8990、reps 24、
   host_delay 35）；`_main` 只覆盖用户显式给了的选项。
4. **CAV 交棒**：`cmd_geo` 的入口判断在 `bd_angular` 标志上，别在 `_geo_clv` 里重复处理。
5. **预设要写 `disc-presets.json`**，不是 `blu-ray-presets.json`；pitch 系数留空。
6. **Windows 上 numpy < 2 会把 Python int 当 int32**：`read_end_bits(352000)` 在 32 位下溢出成负数，
   已在 `cd.py` 用 `np.int64` 修掉（PR #12）；新写的位运算请显式给 dtype。

---

## 12. 相关文档

- `docs/research/BD_CLV_FEASIBILITY.md`：CLV 可行性、真实数据、§12 真机结果、§13 预设导出。
- `docs/research/BD_CLV_GEOMETRY_SOLVER.md`：模型推导、误差预算、交叉校验（本文件是它的"接手版"）。
- `docs/MANUAL.md` / `docs/MANUAL.en.md`：`--media bd`、`--bd-zones`、`--fit-offset`、`disexport` 的用户说明。
- `SUMMARY_PHASE2.md` / `OVERNIGHT_BD_SUMMARY.md`：阶段性结果与命令记录。
