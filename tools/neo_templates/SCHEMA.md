# Disc Neo {{VERSION}}: field reference

This page defines every file, column and number in the pack. The overview is in [README.md](README.md)
(中文：[README.zh.md](README.zh.md)；本页末尾有中文速查). The units are µm for periods, T for DVD channel bits
(1 T = 0.13333 µm along the track), and nm for wavelengths.

## 1. Stable IDs

Every search target has a permanent ID. An ID is fixed by what the target *asks for*: media, kind, period bin or exact
period, line shares or ratio, the bound on pattern length, and the harmonic-order guard. Search results, random seeds,
machines and effort never change it. IDs are never reused. A target whose definition changes gets a new ID, and the
old one is archived.

```
DVD-S-B0042-K96-A123abc               single period, period bin 42
DVD-S-X-T32-K96-A123abc               single, exact rational period 32 T (extended long-period range)
DVD-L-B0042-L050-K96-A123abc          brightness ladder: 50 % of the best single in bin 42
DVD-D-d25-LOW-K96-A123abc             dark texture for viewing factor 0.25, risk class "low"
DVD-2-R5_4-S70_30-B0042-K96-A123abc   two lines, period ratio 5:4, shares 70/30, bin 42
DVD-3-H5_6_7-white-B0003-K96-A123abc  three lines, harmonic tuple 5:6:7, white mix, bin 3
DVD-O2-B0042-GNONE-K96-A123abc        second-order target, no visible lower order guarded
DVD-OBS-1-T32_3-A1b2c3                an observation from the earlier palette, not a search target
```

- `S/L/D/2/3/O2/O3` is the kind. `B0042` is the period bin on the target's own logarithmic grid (`grid_anchor`,
  `grid_step`). `K96` means patterns of 1..96 bytes are allowed.
- `A` + 6 hex digits is the start of the SHA-256 of the target's intrinsic definition. It keeps rounded periods from
  colliding. The full hash is stored as `id_definition_hash`.
- **rev** starts at 0. It goes up by one each time a different pattern becomes the target's whole-block winner. When
  that happens `verified` resets to `none`. Only a real photo card number may replace `none`, and in this release
  every value is `none`.
- A printed chip should show **id + rev + spec + period in µm**.

## 2. Metrics

**purity** (per line). Encode the pattern with the real DVD EFMPlus encoder, including scrambling and DSV control,
over complete ECC blocks in several contexts. Strip the sync codes, remove the mean, and project the channel signal
onto the exact target frequency. Purity is that line's share of the total AC power (0..1). Multi-line targets have
one purity per line. `purity_basis` names the method. `whole-block exact-frequency AC projection` is the whole-block
CPU measurement. Anything with `proxy` in it is a GPU approximation on random fill, and the CSV winners never use that.

**min_purity_over_share** (multi-line). The minimum over lines of purity divided by the target share. This is the
ranking objective for mixes. 1.0 would mean every line gets exactly its share of all the power.

**F512_percent / F1488_percent.** The percentage of 512-bit (1488-bit) windows whose mean level, with marks and lands
as ±1, exceeds 0.125 (0.10) in magnitude. It measures long-range DC drift.

**lean.** The mean absolute per-frame level after removing sync.

**risk.** A model label from F512 and lean: `HIGH` if F512 > 4 % or lean > 0.15. Otherwise `as 92` if F512 ≥ 1.5 %,
otherwise `low F512, frames lean` if lean ≥ 0.04, otherwise `low (A5-like)`. These are thresholds from the v3 model.
They are **not** a read test on a real drive. `risk_basis` says so.

**leakage / visible_power** (JSON only). The share of FFT power, per viewing factor δ, inside the visible band
380–780 nm (`visible_power`) and the part of it outside the target lines (`leakage`).

**δ windows** (`delta_*` columns). For period P in µm, wavelength λ (nm) reaches the viewer at viewing factor
δ = λ / (1000 · P). Here δ = sin θ_in + sin θ_out, measured along the track: it is a difference of direction
components, not an angle. The windows used are blue 440–490 nm, green 510–590 nm and red 610–690 nm.
`delta_red_edge_700nm` = 0.7 / P marks where the first order leaves the red end of the visible range.

**visible_fraction_design_poses.** The fraction of sampled viewing geometries in the design poses where the target's
representative period sends 400–700 nm to the camera. There are four of these, weighted equally: a close 2× phone
shot, a 600 mm shot, a 1× shot, and the card-4 geometry. 0 means the target is invisible in those poses (long
periods, infrared, …). It is still searched and recorded. This value is used to plan the search only. It is not a
probability that a person will see the colour.

**usefulness.** The planning score that sets search density: visibility in the design poses × prior purity × kind
priority.

## 3. Search state

**status.** `todo`: not searched yet. `searched`: at least one restart finished, but the restarts don't agree yet.
`converged`: the stopping rule is met, meaning five independent restarts agree within 0.005 purity and none is worse
than a known incumbent by more than that. `exhausted`: a complete enumeration certificate covers the target's whole
domain. No target in this release is `exhausted`. Only patterns of 1–2 bytes were enumerated completely.

A target can be `todo` and still have a whole-block winner. Finer child targets start with the measured patterns
of their parent bin, and of earlier palettes that fall inside them, before they are searched themselves. So
`status` says how far the search for that target has got. Whether a pattern is known shows in `best_purity` /
`measurement`.

**density_tier / grid_step / campaign_pass.** Each target first gets a coarse pass (`campaign_pass` 0). That means
about 2.5 % period steps for singles, ladders and second order, and about 5 % for mixes. Where the coarse result is
useful and still improving, finer children (`campaign_pass` ≥ 1; steps of 0.25 %, 0.5 % or 1 % for singles) are
authorised. `density_tier` is `coarse` or `dense`. These step sizes allocate computer time. They are not a measure of
what the eye can resolve.

**ring.** Priority group for scheduling: 0 means the material is used soon by the editor's material panel or
templates (and so are dark textures with a recipe). 1 means singles and second-order targets with usefulness ≥ 0.2
and a period ≤ 2.2 µm, plus the other dark textures. 2 means ladders and equal-share two-line mixes with usefulness
≥ 0.12. 3 is everything else: reserves, long and invisible periods, unequal mixes, third order.

**measurement.** `whole` means the result is a whole-block CPU measurement.

### Progress figures in the README

- *GPU restarts complete*: the target's runs include at least 5 complete independent restarts. Since 11-14 some coarse
  targets ran these restarts on CPU helper workers (the same search code and seeds on a CPU); they count here too,
  and they are not refined this run.
- *refined*: in addition, its authorised budget round finished and every restart's finalists were re-measured on
  whole blocks by the CPU refinement. This is `round_refined` in `evidence/atlas/campaign.py`.
- *with a whole-block result*: at least one whole-block measured candidate exists, which can come from an earlier
  round or from an import.

`PROVENANCE.json → progress` has these counts for the coarse pass, the dense pass and each kind.

## 4. Files

### `atlas/dvd/singles.csv`

One row per active single-period target that has a whole-block winner, sorted by period.

| Column | Meaning |
|---|---|
| `id`, `rev` | Stable ID and revision (section 1) |
| `spec` | The repeated byte pattern, hex, as written to the disc image |
| `k` | Pattern length in bytes |
| `period_um` | Measured line period of the winner, µm along the track |
| `purity`, `purity_basis`, `measurement` | Section 2 |
| `F512_percent`, `risk` | Section 2 |
| `status`, `verified` | Section 3; `verified` is `none` everywhere in this release |
| `ring`, `density_tier` | Section 3 |
| `visible_fraction_design_poses` | Section 2 |
| `delta_blue_lo` … `delta_red_hi` | δ range where the first order is blue / green / red |
| `delta_red_edge_700nm` | δ where the first order passes 700 nm |

### `atlas/dvd/multi_line.csv`

Two- and three-period targets with a whole-block winner. List-valued cells are separated by `;` and given in the same
line order: `periods_um`, `shares` (target power shares), and `purity` (measured purity per line). The other columns
are `min_purity_over_share`, `purity_basis`, `measurement`, `F512_percent`, `risk`, `status`, `verified`, `ring` and
`density_tier`. `kind` is `two_line` or `three_line`.

`singles.csv` and `multi_line.csv` also have `candidates_total` and `candidates_whole_block`. These are the number
of ranked candidates for that target in `candidates.csv`, all of them and the whole-block measured ones.

### `atlas/dvd/candidates.csv` and `candidates.json`

All distinct patterns found for each active target, ranked. `candidates.csv` has one row per target × candidate.
`candidates.json` has the same data grouped by target (`targets → id → {kind, status, shares, candidates[]}`), plus
`F1488_percent`, `lean` and `peak_DSV` for whole-block candidates.

Where they come from: the target's merged GPU `top` list (top 4), each independent restart's own `top` (top 4 each,
five restarts), each restart's `refined_top`, and the target's `refined_top` / `refined_candidates`, which hold all
whole-block measurements so far, including earlier rounds and imports. Duplicates are merged by `spec`. A spec
measured on whole blocks is shown with that measurement, and `sources` lists every list it appeared in.

Ranking: all `whole-block` candidates come first, ordered by the atlas's own `rank()`. That compares the target
objective, then lower leakage, then shorter pattern, then spec, and it is the rule that picks the published winner, so
rank 1 is the winner (`is_current_winner` = 1). `gpu-proxy` candidates follow, ordered by the same `rank()` on their
GPU metrics, then by `proxy_score`. Their `purity` is an approximation on random fill, and they have no F512.
`gpu-proxy` names the fast approximate search, wherever it ran: for targets searched by the CPU helpers the same
approximation ran on a CPU.

| Column | Meaning |
|---|---|
| `target_id`, `kind`, `target_status` | Target |
| `rank` | 1 = best |
| `basis` | `whole-block` (CPU measurement over complete ECC blocks) or `gpu-proxy` (GPU approximation) |
| `is_current_winner` | 1 for the published winner of this target |
| `spec`, `k` | Byte pattern (hex) and its length |
| `main_period_um` | Period of the line with the largest target share; for singles, the period |
| `periods_um`, `purity` | All lines and their purities, `;`-separated |
| `objective` | The target's ranking objective. For singles this is purity, for mixes min purity/share, for ladders −\|purity − goal\|. Empty where it can't be computed from proxy metrics |
| `purity_basis`, `risk`, `risk_basis` | As in section 2. For `gpu-proxy` rows the risk comes from the GPU risk code |
| `F512_percent` | Whole-block candidates only |
| `leakage_max`, `proxy_score` | Largest leakage over δ; the GPU search score where recorded |
| `sources` | Which lists the pattern appeared in, e.g. `refined_top;run2.top` |

**What this version keeps and what the next will.** This version keeps "the top 4 of each list plus every whole-block
measurement found". After this run ends, the uniform dense pass will switch to a tolerance rule. A cell will keep
every pattern in the same period bin whose purity is at least 80 % of the winner's and whose risk is no worse, with at
least 8 and at most 16 per cell.

### `atlas/dvd/coverage.csv`

One row per active target, measured or not.

| Column | Meaning |
|---|---|
| `id`, `kind` | Target |
| `period_lo_um`, `period_hi_um` | Base-period interval the target covers: its grid bin, or the union of its density domains. Empty for dark textures, which have no fixed period |
| `grid_step`, `density_tier`, `campaign_pass`, `ring`, `usefulness`, `visible_fraction_design_poses` | Section 2 and 3 |
| `status`, `converged` | `converged` is 1 for `converged` / `exhausted` |
| `cpu_refined_round` | 1 if the authorised round is refined (see progress figures) |
| `best_purity`, `best_purity_max` | Purities of the current winner (per line), and their maximum; empty if none yet |
| `measurement`, `rev`, `verified` | Of the current winner |

### `atlas/dvd/atlas_dvd.json`

The same file the search coordinator publishes every day. `schema_version` 1, `id_scheme_version` 1. Main keys:

| Key | Content |
|---|---|
| `media`, `T_um`, `STANDARD_VERIFIED` | `dvd`, 0.13333, and the codec's standard-verification flag |
| `targets` | Every target definition: ID, kind, grid, shares, status, rev, verified, density and planning fields |
| `atlas_target_winners` | Current whole-block winner per active single, mix and order target: the source of the CSVs |
| `ladder`, `dark`, `order2`, `order3` | Winners for brightness ladders, dark textures, second and third order (with order purity and lower-order guards) |
| `singles`, `two_line`, `three_line`, `best` | Compatibility view for older disc-probe tools: one pick per 0.5 % bin, lowest risk first. It mixes in imported observations |
| `observations` | Every whole-block candidate from every target and restart, plus imported rows. This is the history |
| `imported_observations` | The {{IMPORTED}} observations from earlier palettes, unchanged |
| `order_observations` | All candidates for order targets |
| `coverage` | Legacy 0.25 % log-bin coverage of single periods (measured or not) |
| `extended_singles`, `extension_summary` | Long-period singles above purity 0.05 and what is known about the longest usable period |
| `conflicts` | Specs that were observed at more than one period |
| `target_status_counts`, `archived_target_count`, `policy` | Summary counts and the ranking policy in words |

Each candidate row carries `spec`, `k`, `periods_T`, `periods_um`, `purity`, `purity_basis`, `F512_percent`, `lean`,
`risk`, `risk_basis`, `measurement`, the full `metrics` object (including F1488, DSV, leakage and the encoding
contexts), and `id` / `rev` / `verified`.

### `PROVENANCE.json`

`epoch`, `snapshot_utc`, `merge_code` (the atlas commit whose `merge()` built this export), `code_versions` (how many
targets and how many restarts carry each atlas code hash: a long search runs several code versions, and every result keeps
the hash of the code that produced it), `encoder_hash` (hash of the EFMPlus encoder sources), `plan_hash`, campaign dates,
and `control_source_note` (when the coordinator's control file was copied, if not at the snapshot time). `cpu_helper` counts the targets the CPU helpers searched (`also_in_gpu_journals`: also searched by a GPU worker;
the merge keeps the more complete copy of each restart). `machines` holds events and targets per source journal: one GPU journal per
search machine, one CPU-refinement journal per refine host, one per CPU helper (`cpu-helper:<name>`), one per extra GPU process started later (`gpu-extra:<name>`, e.g. a second
GPU worker on glassbox). `sources` holds size, source modification time and
SHA-256 for every copied input. `progress` holds the figures in section 3, `counts` the record counts, and
`texture_cards` the git commit the cards were taken from. `package_files` holds size and SHA-256 for every other
file in this pack.

## 中文速查

- **编号**：`DVD-<类型>-…-K96-A<定义哈希前 6 位>`；类型 S 单周期、L 亮度阶梯、D 暗色、2 双线、3 三线、O2/O3 高阶。
  编号只由"目标要什么"决定，不随搜索结果变，永不复用。找到更好的纹理时 `rev` 加一、`verified` 回到 `none`。
  色块上印 **编号 + rev + spec + 周期（µm）**。
- **纯度 purity**：真实 EFMPlus 编码、完整 ECC 块、去同步码去直流后，正好落在目标频率上的交流能量占比（0–1）。
  `purity_basis` 写着 `whole-block` 的才是整块 CPU 实测；带 `proxy` 的是 GPU 近似，CSV 里不用。
- **F512_percent**：512 位滑动窗口里平均电平绝对值超过 0.125 的比例（%），衡量长程直流漂移。
- **risk**：按 F512 和 lean 的模型阈值分档（HIGH / as 92 / low F512, frames lean / low (A5-like)），不是真机读盘测试。
- **δ 窗口**：δ = sin θ入 + sin θ出（沿轨道），λ(nm) = 1000 · P(µm) · δ；蓝 440–490、绿 510–590、红 610–690 nm。
- **状态**：todo 未搜；searched 已搜未收敛；converged 五次独立重启相差 < 0.005；exhausted 完整穷举证书（本版没有）。
  加密子目标在自己被搜之前会先继承父区间和旧色板里落在区间内的实测纹理，所以 todo 也可能已经有结果；有没有纹理
  看 `best_purity` / `measurement`。
- **候选（candidates.csv / .json）**：每个目标列出搜索找到的全部不同字节段，按 spec 去重。整块实测（`whole-block`）的
  排前面，排序规则就是选冠军的 `rank()`，所以第 1 名就是公布的冠军；只有 GPU 近似值（`gpu-proxy`）的排后面，纯度是估计。
  这一版每格是"各列表的前 4 名 + 能找到的全部整块测量"；下一版改成按容差收录：同一周期格、纯度 ≥ 冠军 80%、风险不更差，
  每格最少 8 名、最多 16 名。
- **设计机位可见比例**：在四个设计机位里，代表周期把 400–700 nm 送进相机的几何占比；0 表示在这些机位看不见
  （长周期、红外），但照样搜、照样记。只用来分配算力。
