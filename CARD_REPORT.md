# 卡 Y · DVD 彩色图

分支 `web/colour-print-20261118`，基点 `b3cc9e5`。只在本分支提交，未推送、未合并。ISO 的刻录和读回均在 Disc Lab 虚拟光驱 `X:` 中进行。

## 提交

- `06a1318` 实现 `colour` 填充和 `colour-design`。合成器从作品的 `scene.rig` 取得机位，在每行逐格计算 δ，先插值 LED XYZ，再与原图的 CIELAB 比较。支持最近色和 Bayer 8×8 有序混色。沿用原有透明度、层内顺序、选区覆盖和可刻环带。CLI 可选材质集、色表、拟合方式和预测 PNG。小图测试使用真实 `compose`、`image` 和 ISO 校验器。
- `1b446df` 接入网页「彩色图」填充，自动加入 40 种候选材质。选机位后可填充，灯下和刻出来由 core 返回 PNG。灯下的「对照」左边显示原图，右边显示预测。DVD 有可见彩色图时默认按作品材质生成烧录文件，也可切回黑白。旧作品的手动彩色烧录仍沿用原有开关。浏览器检查覆盖导入、手机与高度、填充、预测、对照及重新打开作品。
- 本提交记录验收结果和待审查项。

## 颜色来源

- 色表采用 `F:/dp-archive/texlib/latest/colour_table.npz` 的未拟合 LED 模型，SHA-256 `cf72ba75c1776b8ee3de3120d199647049585cee39c7e461d1cfe8d2d161b0d7`。
- 材质来自 `D:/disc-probe-scratch/gamut/greedy_set.json`，SHA-256 `206dd1d897eb6f158b18f6a64c6249d6cdeb729bd3400174a799b74f2cf1c84c`。两个来源均只读。作品保存 `tex:<spec_canonical>` 与字节纹理，色表签名用于记录。换表后合成会使用当前配置的表。CLI 的 `--texlib`、`--materials` 和网页服务的 `DISCPROBE_TEXLIB`、`DISCPROBE_COLOUR_MATERIALS` 可更换来源。
- `--fit disc` 按外缘铺图，再裁到可刻环带。`--fit ring` 把全图放进盘心上方的环带，避免图案被盘心裁断。网页沿用原有导入位置和图层变换。

## 整盘验证

测试图是 640 × 640 的平涂插画，包含红、黄、绿、蓝和肤色。iPhone 17 Pro，拍摄高度 22.3 cm，20 µm 刻录格，40 种候选材质。起跑时 D 盘空余 204.57 GiB、F 盘 41.24 GiB。回归前复查 D 盘仍有约 204.5 GiB。

```powershell
python -B -X utf8 -m discprobe colour-design illustration.png --phone iphone17pro --height 22.3 --texlib F:/dp-archive/texlib/latest -o illustration.json --preview prediction.png
python -B -X utf8 -m discprobe compose illustration.json --texlib F:/dp-archive/texlib/latest --out illustration.npy
python -B -X utf8 -m disclab box --lab geometry-lab --media dvd-r --count 1 --seed 17
python -B -X utf8 -m disclab loop geo --lab geometry-lab
python -B -X utf8 -m discprobe compose illustration-measured.json --texlib F:/dp-archive/texlib/latest --out illustration-measured.npy
$textures = (Get-Content illustration-measured.textures.json -Raw | ConvertFrom-Json).textures
python -B -X utf8 -m discprobe image --geo geometry-lab/results/geo-X-20261118-150058/summary.json --design-npy illustration-measured.npy --textures $textures --no-photo-l --r-max 58.1 --output illustration.iso
python -B -X utf8 -m disclab dp --lab virtual-lab -- burn --drive X: --iso illustration.iso --speed 8 --yes-write
```

命令的输入输出用 F 盘临时目录。`virtual-lab` 用相同种子和 DVD-R 型号另建。第一次给 `image` 的几何只有模型参数，缺失覆盖资料，正确被拒绝。随后在 Disc Lab 内运行正式几何流程，实测模拟覆盖为 25.754–57.470 mm，采用与网页相同的约 0.05 mm 内缩，形成 `illustration-measured.json` 的 25.805–57.419 mm 可刻环带。ISO 容量为完整 DVD 大小。

| 步骤 | 用时 | 结果 |
| --- | ---: | --- |
| `colour-design` + 预测 PNG | 90.85 s | 作品含一张图片和 40 种候选材质，生成 600 × 600 模型预测图 |
| `compose`，默认 24–58 mm | 72.20 s | 6000 × 6000 uint8 标签，42 项材质表，低于 120 s 目标 |
| Disc Lab `loop geo` | 36.80 s | 得到虚拟盘几何和带实测范围的 `summary.json` |
| `compose`，按虚拟测量裁切 | 72.23 s | 同为完整 20 µm 网格 |
| `image`，2 个 worker | 92.18 s | 2,295,104 扇区，4,700,372,992 字节，核心扇区抽查通过 |
| Disc Lab `burn`，8× | 20.31 s | 写入阶段 13.8 s。96 组读回通过，0 组不同、不可读或未测 |
| Disc Lab 全量 `READ(10)` | 19.11 s | 每次读 128 扇区，覆盖全部 2,295,104 扇区，SHA-256 与源文件相同 |

ISO SHA-256 为 `3ea451fd6068be48a94358c01480fe6a741f2d01367e400f7175a092a49b356e`。全量校验完成后已删除 ISO 和标签数组。日志在 `F:/dp-archive/tmp/colourprint/`，含 `colour-design.log`、`compose-measured.log`、`image-measured.log`、`virtual-burn.log`、`full-readback.log`，同目录保留 `prediction.png` 和 `illustration.preview.png`。

## 回归和截图

- `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp F:/dp-archive/tmp/colourprint/pytest-relevant` 跑 `tests/test_editor_*.py`、`tests/test_design_compose_route.py`、`tests/test_lamp_optics.py`、`tests/test_simulate_a3.py`，123 项通过。最后一次针对合成和预览的改动再跑相关三文件，11 项通过。非彩色作品的 36,000,000 个共享网格标签，Python 与 JS 差异为 0。旧的 core CLI 与 HTTP PNG 字节相同。
- `node --test --test-concurrency=1` 所有符合卡片路径范围的 `tests/test_*.mjs`，47 个文件，首轮 56 项通过、2 项失败。定向重跑两项均通过。一个失败来自导出测试仍断言旧的固定黑白默认，已补断言覆盖彩色图和旧作品。另一个是桌面截图夹具的纯色画布能被排队重绘覆盖，基点可复现，已修正夹具的取样准备，颜色断言保持原值。含受限组件的社区、IME、CSP 和新建作品审查测试未跑。
- `tests/test_editor_w245_browser.mjs` 的 18 项通过。与基点同一 Edge/CDP 环境比较，纸色和夜色 20/10 µm 四个画布哈希均为 `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`，相同。
- `tests/test_editor_texlib_browser.mjs` 的小夹具和实际纹理库都通过。实际库从普通导入按钮载入图片，选机位后填入 40 种材质，灯下状态从计算中进入就绪，600 × 600 预测帧首轮约 41.36 s。对照、刻出来和重新打开 CLI 作品均通过，浏览器异常 0。证据见 `browser-final.log`、`node-patch.log`。
- 纸色、夜色各三张 1440 × 1000 的 Edge 截图在 `F:/dp-archive/tmp/colourprint/after/`。文件为 `paper-colour.png`、`paper-prediction.png`、`paper-comparison.png`、`night-colour.png`、`night-prediction.png`、`night-comparison.png`。
- 现有 Python 测试曾把两份临时对比 JSON 写入 worktree 的固定证据目录，已移到 F 盘，未纳入提交。一次检查测试引用的 `rg -l` 漏排了社区测试文件，命令只返回文件名，该测试未运行或修改。

## 待审查

- 色表尚未按色卡校正。预测图的饱和度、底光和在不同位置的条纹变化，均等待实盘照片验证。全盘字节读回只验证虚拟刻录数据。物理刻录、混色观感与颜色误差未测。
- 网页使用 200–800 px 的 core 预览，彩色图在「刻出来」中显示缩放后的材质分布。彩色图的放大逐格检查和 10/5 µm 整盘耗时未测。
- 叠加手动彩色填充时，默认彩色烧录选项会一并使用这些填充的作品材质。请审查首版是否采用这一行为、左原图右预测的对照，以及待拟合色表与新材质集是否进入冻结版。

## 第二轮 · 拟合材质和相对映射

- `aa64f05` 添加 `discprobe/colour_print/table.npz`、`materials.json` 和生成脚本 `tools/build_colour_print_table.py`。只取 `material_sets.json` 的 `scenarios["0.000"].materials`，原序保留 `spec`、`id`、`rev`、`texlib_rev`。`0.049` 未入包。58 × 341 × 3 个 XYZ 元素与拟合源表选中行逐元素相同，dtype 仍为 `float32`，`specs` 缩到实际最长的 `U68`。A5/B9 峰值 Y 写成一个标量，未附加这两条曲线。wheel 中两份文件逐字节核对通过，大小分别为 222,342 和 7,953 字节。
- `7e55b61` 让 `colour-design`、`compose` 和网页彩色图默认使用随包数据。无 `DISCPROBE_TEXLIB` 的 CLI、网页填充、预测与重新打开作品均通过。`--table NPZ` 和 `--materials JSON` 可覆盖，网页也支持 `DISCPROBE_COLOUR_TABLE`、`DISCPROBE_COLOUR_MATERIALS`。第一轮已保存的未拟合分配仍可用原纹理库重放，重新填充可采用新表。拟合预览只渲染已分配纹理的衍射光，保留模型估计提示和六张色卡盘的校准说明。
- 候选 XYZ 在实际 δ 先插值再转 Lab，每格由候选求 `Lmin`、`Lmax` 和 `Cmax`。原图 `L*` 的 0–100 线性映到 `[Lmin,Lmax]`，`a*`、`b*` 同乘 `min(1,Cmax/134)`。134 是 sRGB 角点在 D65 Lab 中的最大色度向上取整后的常量。映射保留目标色相，候选用 ΔE76 排序，Bayer 8×8 及前两名距离比例照旧。超出色表角度范围时，模型响应为零。

```powershell
python -B -X utf8 tools/build_colour_print_table.py --table F:/dp-dev-tmp/colour-table-fitted/colour_table_fitted.npz --material-sets D:/disc-probe/docs/goals/colour-table-fitted/material_sets.json
python -B -X utf8 -m discprobe colour-design illustration.png --phone iphone17pro --height 22.3 -o full-work.json
python -B -X utf8 -m discprobe compose full-work.json --out full-labels.npy
```

拟合源表 SHA-256 `2f71fd2daad780ce4f715ae4d2c0074da1b4d2cbf6c47924019f3d9f15b258de`。材质集源 JSON SHA-256 `a9aa62e7b4f7bbcec71b8c768adbfa4e2bd30c508452f4b1fb2b60575233260b`。随包 NPZ SHA-256 `756f7440306509e2f68156e00f2e4ceb9eb46f5eb0623754de663e0568fc4763`。

### 可认度和色块

用第一轮同一张 640 × 640 插画，重新生成的原图 SHA-256 为 `a95b712049044e71cb39ed2267fe63f91eb90f226c6812977bd8a06116f2b2e6`。同一 80.4 mm 居中图层、20 µm 合成格和 600 × 600 预测像素。对原图和预测图的 sRGB 像素取 Rec.709 加权灰度，在图片与可刻环带交集中算 Pearson 相关系数。「有角度数据」一列只计入拟合表有角度数据的共同像素。色块误差是区域内预测线性 RGB 的均值转 Lab 后，与原色块之间的最短色相角差，单位为度。色块边缘剔除两像素。

| 组别 | 灰度 r | 有角度数据的灰度 r | 天空 | 黄 | 绿 | 深蓝 | 红 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 第一轮未拟合表、绝对匹配，22.3 cm | 0.363 | 0.535 | 23.22 | 15.73 | 9.77 | 46.55 | 16.75 |
| 拟合表、绝对匹配，22.3 cm | 0.425 | 0.546 | 14.21 | 19.90 | 0.07 | 3.93 | 22.74 |
| 拟合表、相对匹配，22.3 cm | 0.401 | 0.506 | 16.71 | 19.04 | 1.90 | 2.39 | 22.58 |
| 拟合表、相对匹配，30 cm | 0.465 | 0.610 | 14.40 | 16.51 | 6.74 | 4.45 | 2.76 |

居中构图的肤色落在不可刻盘心。用同一张图右移 23 mm 做补充对照，在 1200 × 1200 标签网格和 600 × 600 预览取到 2,369 个肤色采样像素。肤色色相误差依次为第一轮 34.66°、拟合绝对匹配 7.19°、拟合相对匹配 6.99°。其余指标和每块采样数见 `readability.json`。

新版能分出蓝色天空、黄色太阳和绿色山体，仍看得到放射色带。整图灰度相关从 0.363 到 0.401，改善主要来自本轮拟合表及对应的纯衍射预览。单独比较拟合表两种映射，22.3 cm 相对匹配的灰度相关低于绝对匹配，深蓝误差较小，天空误差较大。22.3 cm 和 30 cm 分别有 88.85% 和 84.85% 的受测图像像素落在拟合色表的 δ 范围。

### δ 与灯下渲染器核对

合成与灯下均使用到相机和灯的单位方向之和在轨道切线上的投影绝对值。合成行向下，光学坐标向上，进入计算前翻转 y。拟合源表的来源记录明确 `delta_scale_applied=false`，两条拟合路径均在纹理查表前应用一次 0.93。

将同一次 `colour` 合成得到的标签交给 `lamp-worker` 实际调用的 `LampFrame`，与 core 的纯衍射 PNG 对比。22.3 cm、600 × 600 个同位置的查表 δ 最大差 `1.14×10^-14`。

| 使用同一份标签 | RGB 全图平均绝对差 | 环带平均绝对差 | 最大通道差 |
| --- | ---: | ---: | ---: |
| 6000 × 6000 实际标签，core 面积覆盖、JS 单点取样 | 6.33754 / 255 | 10.41902 / 255 | 255 |
| 600 × 600 合成标签，两者匹配到同一取样点 | 0.000232 / 255 | 0.000382 / 255 | 1 |

全分辨率差异主要是取样口径。core 对每 10 × 10 个刻录格做面积覆盖，单点 JS 取一个格。取样一致时 1,080,000 个 RGB 通道里有 251 个相差 1。没有发现需更换几何公式的差异。并排原图、`full-grid-*`、`matched-sampling-*` 和 `delta-and-render-parity.json` 一并保留。

### 回归、ISO 和截图

- 全量 Node 用 `node --test --test-concurrency=1` 跑 54 个 `test_*.mjs` 文件，65 项通过。`node --test tests/test_flow_navigation_browser.mjs` 单独跑，1 项通过。社区、faxnews、presetio、新建作品审查、IME 和 CSP 本轮均通过，相关测试文件未改。W245 的 18 项通过，四个旧画布哈希与第一轮相同。Python 相关测试 `-n 2` 共 125 项通过，最后定向重跑包含新增拟合 δ 检查的 17 项，也全通过。旧 Python 测试写到 worktree 的两份临时对比 JSON 已移到 F 盘。
- 20 µm、整盘默认环带的 `compose` 耗时 **92.95 s**。使用第一轮 Disc Lab 量测范围裁切后 `compose` 耗时 80.68 s。沿用虚拟几何向 `image` 传 60 项材质顺序表，2 worker 生成 4,700,372,992 字节 ISO 耗时 134.87 s，核心扇区抽查通过。另一只同种子的 Disc Lab 虚拟 DVD-R 用 8× 刻录，含抽查的总耗时 22.55 s，96 组通过。再用 128 扇区一组的 `READ(10)` 全读 2,295,104 扇区，17.22 s，读回与 ISO SHA-256 均为 `5355ccf13e75f3b2ff4183f1c572e63d8da7a2f5843ecdcfea87bb2124eff189`。ISO 已清理。
- 截图和原始数据均在 `F:/dp-archive/tmp/colourprint/round2/`。`before-after.png` 是四组预测与原图并排，`skin-block-control.png` 是肤色补充对照。`after/` 是 22.3 cm 的纸色、夜色截图，`after-30cm/` 用同一张插画重新按 30 cm 选材并截图。两组均为 Edge 1440 × 1000，无纹理库环境，成功生成 600 × 600 预测、切换对照和重新打开 CLI 作品，浏览器异常 0。首张灯下图分别耗时 55.98 s 和 54.01 s。
- 以上为模型、界面及虚拟刻录验证。第二轮新材质的实盘照片、物理读盘和实际混色仍未测。

## 第三轮 · 保持色块可辨并减少放射细纹

代码提交 `95cb523`。拟合图先把原图整理成至多 256 个代表色，能装下的平涂色保留原值。`L*` 仍压进该 δ 的可达范围。范围越窄，匹配越侧重色相、色度，并适当保留饱和区域的色度。Cornsweet 类增益按两种尺度的局部亮度差计算，宽、窄高斯标准差分别为 0.42 和 0.14 mm，最多调整源 `L*` ±8，透明像素不参与局部亮度平均。以颜色、边缘等级和 δ 预计算匹配，拟合的旧作品重新合成时也使用这套算法。CAM16 和盘面平均色作为适应白点均留在 alpha 范围之外。

### 放射细纹的成因与改动

把第二轮固定的单个源色在 δ=0.13–0.46 以 0.0001 间隔扫描。天空和深蓝的第一名分别换了 36 和 46 次，其中 35 和 43 次是同一对材质前后换序。未排序的前两名集合分别换了 66 和 65 次。旧算法会在前后换序时翻转 Bayer 阈值对应的材质。用第二轮 `nearest` 关闭抖动，窄放射纹仍可见，说明 δ 变化时的光谱响应及候选排名是主要来源。对照图见 `diagnostic-ordered.png` 和 `diagnostic-nearest.png`。

第三轮先在 δ 上以 σ=0.0125 平滑匹配误差，再对主材质路径的每次切换加 1200 的平方色差代价。`ordered` 用 σ=0.010 平滑候选占比，每个位置取至多四种材质，按稳定的槽位顺序套用原 8×8 Bayer。主导材质能过渡得更平滑，格级混色切换会增多。`nearest` 使用同一平滑后的单材质路径。

### 同一插画的可认度与材质切换

与第二轮沿用同一张图、80.4 mm 居中图层、20 µm 标签和 600 × 600 光学图。灰度相关以图像和可刻环带相交的 116,360 个像素计算，依据相同的 Rec.709 灰度和 Pearson 口径。色相误差是色块平均线性 RGB 转 Lab 后的最短角差。数值不含预览斜线。

| 高度 | 第二轮灰度 r | 第三轮灰度 r | 有 δ 数据区域的灰度 r，第二轮 → 第三轮 |
| --- | ---: | ---: | ---: |
| 22.3 cm | 0.401 | 0.398 | 0.506 → 0.499 |
| 30 cm | 0.465 | 0.452 | 0.610 → 0.610 |

| 色块 | 22.3 cm 色相误差 °，二 → 三 | 30 cm 色相误差 °，二 → 三 | 22.3 cm 主导材质切换，二 → 三 | 22.3 cm 全标签切换，二 → 三 |
| --- | ---: | ---: | ---: | ---: |
| 天空 | 16.71 → 4.88 | 14.40 → 16.30 | 3,011 → 548 | 49,223 → 66,165 |
| 太阳 | 19.04 → 20.11 | 16.51 → 18.68 | 155 → 111 | 3,417 → 6,632 |
| 沙 | 11.60 → 9.90 | 22.15 → 19.58 | 18 → 0 | 10,478 → 10,808 |
| 山 | 1.90 → 4.98 | 6.74 → 11.05 | 926 → 596 | 30,270 → 44,395 |
| 海 | 2.39 → 5.40 | 4.45 → 8.85 | 2,331 → 615 | 30,552 → 45,019 |
| 红衣 | 22.58 → 14.29 | 2.76 → 17.19 | 22 → 18 | 387 → 676 |
| 合计 | | | **6,463 → 1,888** | **124,327 → 173,695** |

肤色在居中构图落在盘心，无法按该机位统计。沿用第二轮右移 23 mm 的补充构图，肤色误差 6.99° → 13.82°。切换统计只计色块内且两端都有 δ 数据的连续环向取样对，在 24.5–57.5 mm 间每 0.5 mm 取一条圆弧，按 0.05° 取样，排除落在同一记录格的点对，共 263,000 对。「主导」是应用 Bayer 前占比最大的材质，「全标签」是实际取到的 20 µm 标签。天空沿方位角使用 0.75° 高斯高通后的灰度 RMS 从 9.43 降至 2.59，海从 7.01 降至 1.61。放射细纹减少，阴影和更宽的色带仍可见。

天空和山的平均色相分离由 77.17° 变为 92.08°，原图为 91.97°。天空和太阳的色度差由 38.44 变为 43.81，原图为 41.79。各色块并非一律改善，表中列出下降与升高。分步关掉平滑来隔离 Cornsweet 效果，对原图灰度差至少 20 且两侧有 δ 数据的相邻像素，预测的顺向反差平均增加 3.71 个灰度值（跨水平边）和 5.26 个灰度值（跨竖直边）。最终版的这两个反差仍分别比仅色度优先高 2.34 和 2.59。原始统计在 `measurements.json` 和 `adjacent-colour.json`。

### 预览、耗时与回归

- 彩色图的中英说明新增机位灵敏度和正对闪光灯的缺图区提示。拟合的灯下 PNG 以斜线标出当前机位环带内的超表角度，包括常见的上下正中缺口。合成跳过这些位置的彩色填充，保留下层已有标签。斜线只在显示端添加，不进入烧录图和指标。
- 20 µm、默认整盘环带、116 mm 图层分步执行，色度优先和颜色查表 3.96 s，加入 Cornsweet 3.39 s，再加平滑和切换代价 3.44 s。每步为一次本机实测。正常 `python -B -X utf8 -m discprobe compose full-work.json --out full-labels.npy` 端到端 4.60 s。`colour-design --preview` 含生成作品、合成和 600 px 细采样 PNG 共 17.61 s。另用 2048² 随机 RGB 试了多色输入，整段含生成图和合成耗时 9.39 s。所有测得步骤均低于 120 s。日志在 `cli-compose.log`、`cli-preview.log`、`rich-compose.log`，分步统计在 `whole-disc.json`。
- Python 相关回归 `-n 2` 129 项通过。Node 全量除导航外 54 个 `test_*.mjs` 文件、65 项通过。`test_flow_navigation_browser.mjs` 单独跑，1 项通过。W245 的 18 项通过，四个旧画布哈希与第二轮相同。旧回归生成的两份临时对比 JSON 已移到 F 盘。
- `F:/dp-archive/tmp/colourprint/round3/before-after.png` 保留前两轮内容并追加本轮一列。`skin-block-control.png` 另呈现右移的肤色对照。`after/` 和 `after-30cm/` 分别保存 22.3 cm、30 cm 的纸色和夜色截图，Edge 1440 × 1000。两个机位均用相同无纹理库配置打开，浏览器异常 0。首张灯下帧分别为 9.26 s 与 8.39 s。
- 实盘混色、格级换材增多后的实盘光学和读盘表现仍未测。第三轮验收使用模型、标签、小 ISO 回归与网页截图。
- 最终检查发现 worktree 中有另一试验写入的未跟踪 `works/` 记录，原样保留，本轮提交不包含它。
