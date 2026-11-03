# 实测证据

以下全部是 2026-11-03 在 HL-DT-ST GH70N（固件 NYA2）上、使用 Ritek F1 DVD-R（MID `RITEKF1`）得到的原始结果。JSON 里的本地绝对路径已换成文件名（`scrub_paths.py`）。图可以用 `python evidence/make_figures.py` 重新生成。

| 文件 | 内容 |
|---|---|
| `drive/info_blank_ritekf1.json` | 空白盘的 `info` 输出：INQUIRY、各项功能、DVD 物理格式、MID、读写速度表 |
| `drive/timing_4x_random_rings_summary.json` | 读速固定 4x、只读随机数据环的计时测试：转速、抖动、相位精度 |
| `geo/random_disc_*` | 随机数据盘上的全盘梯子测量：26 级，25.8–54.5 mm，残差 rms 0.15°，测量范围内 1σ 为 0.12° |
| `geo/rings_disc_*` | 纹理环盘上 3 个随机数据环的梯子测量：21 级，33.6–45.8 mm |
| `gridscan/grid1_*` | 按计时几何刻的网格盘，6 张扫描，逐半径的转角 φ(r) |
| `gridscan/grid2_*` | 加角度修正、另一张新盘，4 张扫描 |
| `angle_correction.json` | 由 grid1 拟合出的修正曲线 φ(r)（四次多项式） |
| `dis_preset_ritekf1.json` | 把计时结果加角度修正，拟合成 DiscImageStudio 的 DVD 预设（三次轨距），附转换残差：在 25.8–54.4 mm 内，与实测角度映射的最大差 0.011°、RMS 0.0036°。用精确弧长公式独立复核，最大差 0.011° |
| `ringscan/` | 纹理环盘扫描后各纹理的亮度等级（`--refs A5,B9`） |
| `figures/bending_before_after.png` | grid1 与 grid2 的 φ(r)：0.31° → 0.14° 峰峰值 |
| `figures/ladder_residuals.png` | 两次梯子测量每一级的残差 |
| `figures/preset_comparison.png` | DiscImageStudio 社区预设 `ritek-dvd-r-e-series`（独立的拍照标定）与我们结果的角度差：不加修正 0.294°，加修正 0.083° 峰峰值 |
| `figures/grid1_scan_*` | grid1 扫描的高通处理图，以及字母 F 的局部放大 |
| `figures/rings_scan_unrolled.png` | 纹理环盘扫描按（半径，角度）展开 |
