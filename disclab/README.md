# disclab：disc-probe 的开发者测试台

不刻盘、不接真光驱，把"测几何 → 出 ISO → 拍照 → 修正 L → 再出图"整条路走一遍，并且知道每一步离真值多远。
只给开发者用：`disclab/` 不在 `pyproject`、wheel、sdist、Windows 包的任何清单里，`discprobe/` 一行没改。

## 怎么用

```bash
python -m disclab box  --lab LAB --media dvd-r --count 12 --seed 1     # 一盒 12 张虚构盘，真值写进 LAB/answers.json
python -m disclab tray --lab LAB --drive X: --disc "LAB-A 1-01"         # 放盘
python -m disclab dp   --lab LAB -- info --drive X: --out LAB/results   # 任何 discprobe 命令，对着虚拟光驱
python -m disclab loop geo   --lab LAB                                  # 每张盘：刻随机盘 → geo → 打分
python -m disclab loop photo --lab LAB --targets 6 --photos 6           # 盘1 geo → 盘2..7 标靶 → 照片 → 照片 L → 出图 → 打分
python -m disclab poses --lab LAB --disc ... --geo ... --out f.json     # 同一张盘绕一圈拍，看 L 跟不跟机位
python -m disclab web  --lab LAB --port 8853 [--lan]                    # 网页连虚拟光驱（开发模式；--lan 才有手机链接）
python -m disclab upload --url "http://127.0.0.1:8853/home/?token=..." --run GEO_RUN --photos a.jpg b.jpg   # 按手机页协议上传
python -m disclab env  --lab LAB --powershell                           # 在自己的终端里直接用 python -m discprobe
```

`--drive X:` 是实验盒里登记的虚拟光驱名。实验进程里打不开任何真光驱：`SptiDevice`/`SgDevice` 对非实验盘名直接报错，
`list` 只列实验光驱。CPU 重的部分（`image` 用 `DISCPROBE_WORKERS=3`，照片读取 2–3 个进程）不超过 4 个进程。

## 怎么接上 discprobe

`disclab/boot/sitecustomize.py` 放在子进程 `PYTHONPATH` 最前面，只在设了 `DISCPROBE_DISCLAB=<实验目录>` 时生效。
它在模块加载时打补丁，不改文件：

| 模块 | 替换 | 作用 |
|---|---|---|
| `discprobe.spti` / `sg` / `imapi` | `SptiDevice` 等、`list_optical_drives` | 实验盘名返回 `LabDrive`，其他名字报错 |
| `discprobe.burner` | `adapter()` | 实验光驱返回 `LabRecorder` |

`LabDrive` 继承 `discprobe.sim.SimDrive`（主轴、寻道、缓存、FUA 的模型都是它的），换掉螺旋、计时角、容量、识别信息、数据内容和故障。
每条 CDB 仍过 `scsi.check_allowed()`，白名单没动。网页、`calibrate` 起的子进程都继承这个环境，所以也走虚拟光驱。

## 真值模型

见 `physics.py` 开头。一句话：盘上第 n 个用户比特真实在 `alpha(n) = -theta_g(n + w)`；
光驱报读完的角度是 `theta_t(n) = theta_g(n + w + d) + asin(h/r) - (e/r) sin(psi + theta_g)`。
所以路径的沿轨常数 `L = d·b + h`，正是 pcal 读的 `tau(r) = c + L/r`。

## 哪些有依据，哪些是假设

| 项 | 取值 | 依据 |
|---|---|---|
| 同一压模的盘 u、v 完全相同 | 盘间 0 | **实测**：GH70N 上不同 RITEKF1 盘的 geo 拟合 u=180518.44±0.05、v=5.591208±1e-6；加上推理：每圈的位数在模压时定死，收缩只缩放毫米 |
| 批次均值 u、v | 180518.44、5.591208 | **实测**（同上） |
| 变螺距 | 0.04° rms 的慢波 | **假设**，量级参照 GH70N 网格盘 0.03° rms |
| GH70N 档计时噪声 | 抖动 13 µs、读两圈、FUA 生效 | **实测**对齐：真盘每次读 std 0.2565°、geo 残差 0.076°、FUA 读 41.4 ms |
| 路径 L（GH70N + IMAPI DVD） | +0.19 mm（完成点 0.13 + 光头 0.06） | **实测**总和：用户两组照片 +0.08..+0.12 / +0.25..+0.28 和密封盲测 0.19 mm；两部分怎么分**不知道** |
| 偏心、翘曲 | 偏心 18 µm σ、碟形 0.12±0.08 mm、马鞍 0.06 mm | **假设**（规格量级） |
| 低速刻纹理外圈读不出 | ≤4x 时 35 mm 外纹理扇区 3/11/00 | **实测**现象（GH70N + RITEKF1 4x），阈值半径是估的 |
| 照片：纹理颜色随 δ | A3 色卡波动模型（真 EFMPlus + ECC） | **模型**，未用真照片标定 |
| 照片：零级反射暗化 | A5 比 B9 暗 15%（按盘） | **假设**，从用户照片的观感估 |
| 照片：折射、翘曲、彩虹臂、反光点 | 几何光学 | 物理上应有；量级未对真照片核对 |
| 照片：手机色彩处理 | 降饱和 40% | **假设** |
| CD、BD | 驱动和 geo 能跑；照片只做了 DVD | CD 的字节布局（CIRC 交织）没建模 |
