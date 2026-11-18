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
