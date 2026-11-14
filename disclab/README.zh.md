# Disc Lab：虚拟光驱实验盒

[English](README.md)

不用接光驱，也不用准备空盘。Disc Lab 提供一台虚拟光驱、一盒有隐藏真值的虚构光盘、程序画出的手机照片，以及和真值对照的分数。它适合开发者，以及想检查几何测量和照片校准流程的人。disc-probe 只拿到虚拟光驱的回复和图像；实验光驱、照片生成器和评分程序才读取 `answers.json`。

## 编号菜单 TUI

```bash
python -m disclab tui --plain
python -m disclab tui --lab LAB
python -m disclab tui --plain --quick
```

可选已有实验盒，也可输入盘种、数量、种子和读盘配置创建新盒。菜单依次提供：放入虚拟盘、生成测量 ISO 并虚拟刻录、timing、geo、用内置帆船图片生成 ISO、实验盒 A5/B9 双纹理靶及虚拟刻录、照片、照片 L、带已接受 L 的图片刻录、对照真值评分。菜单 11 依次执行完整流程。测量盘、照片靶盘、最终图片盘使用不同虚拟盘，完整流程至少三张；示例图片 ISO 是刻录校准靶之前的预览。不会消耗真实光盘。`--plain` 关闭颜色，可重定向标准输入；输入结束正常退出。进度及设置保存在 `state.json`，下次选择同一目录即可继续。

**目前不能渲染 checkdisc 靶**：实验盒照片渲染器尚不支持其多字节纹理。这里使用实验盒自己的简化双纹理靶。照片 L 被拒绝时保留拒绝结果，只有读取器接受并应用 L 才制作带 L 的图片。评分公式和阈值不变，展示几何、照片 L、图片落点与真值的误差；可用 `score --lab LAB --progress --json` 在无菜单情况下取得同样的流程评分。

`--quick` 使用 65,536 扇区的内圈测量及更少读取。图片通过既有 image 参数限制在实测区间内；全盘评分仍包含外推，不能用来证明全盘精度。此模式适合 geo、图片、评分的短流程，26.2–57.2 mm 的完整照片靶需要完整测量。TUI 保留 ISO，因为后续 timing、info 读取需要原始字节；完整练习每个镜像可能占数 GB。原有 `loop` 的清理行为保持不变。

## 网页练习模式

```bash
python -m disclab practice --media dvd-r --lab LAB-practice --port 8853
```

创建默认读盘配置、三张虚拟盘的小盒，放入第一张，复用 `disclab web` 启动现有网页，并输出中英文操作指导。省略 `--lab` 则自动建立并保留临时目录；指定目录必须为新目录或空目录，避免覆盖结果。默认只监听本机，`--lan` 使用产品已有的带令牌局域网模式。Ctrl+C 停止，退出时打印练习结果目录。全部写入虚拟光驱，不消耗真实光盘。

## JSON 及进度接口

所有子命令支持 `--json`：stdout 只有一个含 `status`、`lab`、`outputs`、`scores`、`errors` 的对象；日志及子进程文本写 stderr。该选项应放在 `dp` 的 `--` 分隔符之前。服务器命令在停止后返回最终 JSON。`state.json` 保留原有键，新增带时间戳的 `steps`，前端无需解析日志。详见双语 [API 文档](API.md) 及 [本机 TUI 实测报告](TUI_REPORT.md)。

```bash
python -m disclab box --lab LAB-json --count 3 --json
python -m disclab dp --lab LAB-json --json -- info --drive X: --out LAB-json/results
```

## 后续工作

- 可擦写光盘及擦除操作。
- 更多故障：超时、整圈混叠、照片姿态与曝光。
- 支持多字节纹理渲染，使 checkdisc 可在练习中拍照。
- 基于同一 JSON API 的网页外壳。

## 安装与兼容性

需要 Python 3.11 或更新版本。这个源码快照要求 **disc-probe 0.1.2.1**，按 `discprobe.version.__version__` 判断。版本字符串必须完全相同，包括预发布后缀；缺少依赖或版本不符时，用一句话说明并退出。

任务卡计划的发布文件叫 `disc-lab-1.0.0.0-alpha.zip`，但当前受保护的 disc-probe 源码版本仍是 0.1.2.1。真正发布该版本前，维护者需要让 `disclab/compat.py` 和实际配套的 disc-probe 版本一致，并重新验证。本任务没有更改 disc-probe 版本。

有两种摆放方式：

1. **安装 wheel。** 在要用的 Python 环境中运行 `python -m pip install disc_probe-0.1.2.1-py3-none-any.whl`。wheel 的依赖声明包括 NumPy、SciPy、Pillow 和 OpenCV；离线安装时，需要事先备好这些依赖。把 Disc Lab 压缩包解到任意目录，在包含 `disclab/` 的目录打开终端。
2. **配合 Windows 完整包。** 解开相同版本的完整包，保留它的 Python 和依赖；把 Disc Lab 解到包含 `discprobe/` 的那一层，让 `disclab/` 和 `discprobe/` 并排。下文的 `python` 要替换为完整包内 Python 的路径。Disc Lab 自身不带 Python 或 disc-probe。

运行 `python -m disclab --help`。下文都从包含 `disclab/` 的目录开始，实验目录可以放在别处。启动钩子按自身文件位置找到包：先找旁边的 `discprobe/`，没有再用已安装的 wheel，并在加载设备钩子前核对版本。网页子进程从实验目录启动时也能找到它。运行中不要移动解包目录；实验记录会保存解析后的完整路径。

本地生成独立压缩包：`python -m disclab.package --output disclab/dist/disc-lab-1.0.0.0-alpha.zip`。内容包括 `disclab/`、两种语言的说明、示例、测试、光谱数据和许可证；不带 disc-probe、Python、实验结果或缓存。文件名不会改变上面的配套版本要求。

## 五分钟示例

PowerShell：

```powershell
& ./disclab/examples/run-example.ps1 -Lab ./LAB-demo
```

Bash：

```bash
bash ./disclab/examples/run-example.sh ./LAB-demo
```

请用一个还不存在的新目录，脚本会拒绝覆盖已有目录。不传目录时，脚本自动创建临时目录并打印位置。PowerShell 用 `-Python` 指定解释器；Bash 用环境变量 `PYTHON` 指定解释器路径。

两个脚本都读取 `examples/dvd-r-3.json`：建一盒 3 张 DVD-R，每张都像真盘一样刻满随机数据、用默认读数做几何测量，另外对第一张执行 `score`，最后打印全部分数和耗时。要跑整盒 12 张，用 `-Config examples/dvd-r-12.json`（Bash 用 `--config`）。实际时间取决于机器。

一定要刻满整盘：只刻内圈的话，几何只测到内圈一小段，整盘的落图误差就是外推出来的，数字会大得离谱，不能说明算法好坏。

手动运行对应的三步是：

```bash
python -m disclab box --lab LAB --media dvd-r --count 3 --seed 1
python -m disclab loop geo --lab LAB
# 在 LAB/scores/geo-wide.json 的第一行找到 geo 目录，用它替换 GEO_DIR：
python -m disclab score --lab LAB --disc "LAB-A 1-01" --geo GEO_DIR
```

快速示例用 256 MiB 的随机镜像，每个梯级 8 对读取，最多 8 个梯级目标。只测到写入的内圈；整盘的落图分数含有外推，可能差很多。这个例子用来走通流程，不是精度基准。不传三个快速参数时，仍用原来的完整镜像大小和测量默认值。完整照片实验请另建目录，别复用这个只测内圈的例子。

`LAB/box.json` 是公开盒标；`answers.json` 是隐藏真值；`state.json` 记录虚拟光驱和虚拟写入。测量结果在 `results/`，照片在 `photos/`，几何分数在 `scores/geo-wide.json`，使用默认范围时是 `geo-default.json`。中间 ISO 都放在 `LAB/iso/`，用完删除，循环步骤失败也会清理。留下的是写入分布图和少量头部数据；删掉 ISO 后不能再完整回读它的字节。换实验时请建新目录。

## 照片流程

另建完整大小的实验盒。这条流程更久，中途需要数 GB 的磁盘空间：

```bash
python -m disclab box --lab LAB-photo --media dvd-r --count 12 --seed 1
python -m disclab loop photo --lab LAB-photo --targets 6 --photos 6 --workers 3
```

它先给第 1 张盘虚拟写入随机镜像、测几何；再给第 2–7 张盘写入实验用的 A5/B9 标靶、生成手机照片、调用 disc-probe 读照片，并把测得的 L 和真值对照。若一组照片通过并应用 L，就分别生成有、无照片修正的图像，比较最终落图，并虚拟写入修正后的图像。汇总与逐照片结果在 `LAB-photo/scores/photo.json`，日志在 `loop-photo.log`。照片或照片组被拒绝时会保留原判定。

对这条流程已经写好的某张目标盘，还可以：

```bash
python -m disclab photos --lab LAB-photo --disc "LAB-A 1-02" -n 3 --out LAB-photo/photos/manual
python -m disclab poses --lab LAB-photo --disc "LAB-A 1-02" --geo GEO_DIR --out LAB-photo/scores/poses.json --workers 2
```

`poses` 改变机位和光学效果，看 L 是否跟着机位变化。`tray --lab LAB --disc "LAB-A 1-01"` 用来选盘。`dp --lab LAB -- info --drive X: --out LAB/results` 会让 disc-probe 查询虚拟光驱。`env --lab LAB --powershell` 打印另一终端所需的环境设置；去掉 `--powershell` 则输出 POSIX shell 的 export 语句。自己启动 disc-probe 前先应用这些设置。实验钩子只列出登记过的虚拟光驱，其他设备名会被拒绝。`X:` 是虚拟名称，不是文件路径。

## 接网页和上传照片

下面是另开开发会话时的用法。本次打包验证没有启动服务器，也没有发送网络请求。

```bash
python -m disclab web --lab LAB-photo --port 8853 --media dvd
```

网页的工作区就是实验目录，打开打印的本地地址即可使用虚拟光驱。默认仅本机模式不提供手机链接。要用手机上传，改用带令牌的局域网模式，并从电脑页取得含会话令牌的地址：

```bash
python -m disclab web --lab LAB-photo --port 8853 --media dvd --lan
python -m disclab upload --url "http://127.0.0.1:8853/home/?token=YOUR_SESSION_TOKEN" --run GEO_RUN_NAME --photos LAB-photo/photos/manual/IMG_00000.jpg
```

把 `GEO_RUN_NAME` 换成网页能看到的已有几何结果目录名，照片也用实际文件名。`upload` 先向电脑接口要手机链接，再用手机上传令牌逐张发送原文件字节，最后用电脑身份列出照片。上传失败会打印服务器回复并以非零码退出。它没有浏览器端的画布转 JPEG 步骤。仅本机模式拿不到所需手机链接。用 Ctrl+C 退出网页启动器。无需修改真实设备后端文件。

## 分数怎么看

误差越小越好，没有合成一个总分。程序成功退出不代表物理精度达标。`score` 打印一条结果；`loop geo` 还会保存每张盘的结果和 geo 退出码。

| 字段 | 含义 |
|---|---|
| `u`、`v`；`true_u`、`true_v` | 测得的螺旋比例 `u=r0/b`、`v=pitch/b`，以及隐藏真值。 |
| `du_bits`、`dv_rel` | `u - true_u`，单位是比特；`v / true_v - 1` 是相对差，不是百分数。 |
| `vs_timing_measured_span` | 在实际测量半径范围内，和计时所能看到的真值对照。 |
| `vs_timing_full` | 对评分默认的 26–57 mm 区间做同样对照；含未测区域的外推。 |
| `placement_on_target` | 图像实际落在目标盘上的位置误差，包含路径偏移。 |
| `c_deg` | 拟合的整体旋转角，单位度；整体旋转不使图案变形。 |
| `L_mm` | 拟合的沿轨偏移，单位 mm，保留正负号。关系是 `误差(r) = c + L/r + 剩余误差`，这里角度用弧度。 |
| `rms_deg`、`pp_deg` | 去掉平均旋转后，角误差的均方根和峰峰值，单位度。 |
| `residual_after_L_rms_deg`、`residual_after_L_pp_deg` | 再去掉拟合 L 后剩余角误差的均方根和峰峰值。 |
| `path_L_mm` | 模型里读完成位置加光头偏移的路径 L，不是照片读数。 |
| `geo_reported` | disc-probe 自报的残差 RMS、角度噪声 sigma、每自由度卡方、完成状态和修正文件名；这些是拟合报告，不是真值误差。 |
| `exit` | 循环保存的 geo 退出码；0 表示命令执行成功。 |

照片结果逐张保留状态、估计 `L_mm`、有正负的 `err_mm` 和机位；每组还保留 `verdict`、实际应用的 L 及其误差。`photos`、`accepted`、`accept_rate`、`statuses` 分别表示总张数、接受数、接受率和各状态数量；`accepted_mae_mm`、`accepted_max_mm` 是被接受照片的平均和最大绝对 L 误差。被接受却绝对误差**大于 0.326 mm**的照片计入 `false_accepts`。

`groups`、`groups_applied` 是组数和实际应用 L 的组数；`group_false_applied` 用同一个严格大于阈值，`group_abs_err_mm` 列出应用组的绝对误差，`reasons` 保留未应用的原因。没有读数时保留 JSON null。`pictures.nophoto` 和 `pictures.photo` 是无、有照片修正的落图误差分解；`photo_l` 记录是否写入 L 以及原因。本次没有改这些公式或阈值。

## 真值模型：实测和假设

第 n 个用户比特的位置是 `alpha(n) = -theta_g(n + w)`。光驱读完成的角度为 `theta_t(n) = theta_g(n + w + d) + asin(h/r) - (e/r) sin(psi + theta_g)`。路径的沿轨常数 `L = d*b + h`，就是照片校准 `tau(r) = c + L/r` 中的 L。实现见 `physics.py`。下表保留原有模型对依据的说明；本次打包没有重做这些真实光盘测量。

| 项 | 取值 | 依据 |
|---|---|---|
| 同一压模的盘 u、v 完全相同 | 默认盘间差为 0 | **实测**：GH70N 上不同 RITEKF1 盘的 geo 拟合 u=180518.44±0.05、v=5.591208±1e-6；**推理**：每圈位数在模压时定死，收缩只缩放毫米。 |
| 批次均值 u、v | 180518.44、5.591208 | **实测**，同上。 |
| 变螺距 | 0.04° RMS 的慢波 | **假设**，量级参照 GH70N 网格盘 0.03° RMS。 |
| GH70N 档计时噪声 | 抖动 13 µs、读两圈、FUA 生效 | **实测对齐**：每次读 std 0.2565°、geo 残差 0.076°、FUA 读 41.4 ms。 |
| 路径 L：GH70N + IMAPI DVD | +0.19 mm：完成点 0.13 + 光头 0.06 | **实测总和**：用户两组照片 +0.08..+0.12 / +0.25..+0.28 mm 和密封测试 0.19 mm；两部分如何拆分**不知道**。 |
| 偏心、翘曲 | 偏心 18 µm σ、碟形 0.12±0.08 mm、马鞍 0.06 mm | **假设**，规格量级。 |
| 低速写入纹理外圈读不出 | ≤4x 时，35 mm 外纹理扇区返回 3/11/00 | **实测现象**：GH70N + RITEKF1 4x；阈值半径是估计。 |
| 照片纹理颜色随 δ 变化 | A3 色卡波动模型，真实 EFMPlus + ECC | **模型**，没有用真实照片标定。 |
| 照片零级反射暗化 | A5 比 B9 暗 15%，按盘变化 | **假设**，从用户照片观感估计。 |
| 照片折射、翘曲、彩虹臂、反光点 | 几何光学 | 物理上应有；量级未对真实照片核对。 |
| 手机色彩处理 | 降饱和 40% | **假设**。 |
| CD、BD | 虚拟驱动和 geo 路径；照片只有 DVD | 未建模 CD 字节布局和 CIRC 交织。 |

## 限制和验证范围

照片生成器只认识 **A5、B9 和随机数据纹理**。多字节纹理（例如 `checkdisc` 标靶）的目标图案会画成空白，不能拿它检验这类标靶。CD、BD 只支持几何测量，不支持照片和字节布局整条闭环。

运行只用随包的 `data/wave_xyz.npz`。要重建它，需另备 A3 源材料，显式运行 `python -m disclab.tables --a3 SOURCE_FOLDER`；A3 源文件不随包提供，正常运行不需要它。

原模型的已有局限也保留了，包括每个 session 保存的写入偏移没有被物理模型的顶层字段读取；见历史测试报告。同时最多运行四个 CPU 重进程：图像生成默认三个工作进程，照片读取默认三个，机位扫描默认两个。各流程依次运行，不要把工作进程数调到超出预算。

本机验证环境为 **Windows、Python 3.13.14**：原有 20 项测试、新增便携性测试、两张盘的小闭环，以及 Windows PowerShell 和 Git Bash 中完整 12 张盘的示例。还从含空格和中文的解包路径，检查了旁放 `discprobe/` 与安装本地配套 wheel 两种方式。网页和上传只做了替身子进程、模拟 HTTP 的单元测试，本任务没有启动真实服务器或做真实上传。没有运行完整照片循环，也没有重建 A3 表。

**本机没有运行 Linux。** Git Bash 仍运行在 Windows 上，不能算 Linux 验证。具体测试数量、耗时和打印分数见 [PACKAGE_REPORT.md](PACKAGE_REPORT.md)。
