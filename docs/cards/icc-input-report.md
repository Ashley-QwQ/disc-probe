# ICC 彩色图导入

STATUS: DONE

## 提交

- `82781d9` 为 `colour-design`、网页图片导入和全尺寸模板接入同一套 ICC 读入逻辑。CLI 和网页显示源配置名称，无法使用内嵌配置时提示并按 sRGB 读取。新增可选能力 `colour-input-icc`，API 版本升到 1.6。README、主手册和彩色 DVD 指南均更新了中英文说明。

## 转换与兼容

选纹理前统一到 sRGB。现有色表和选纹理器以 sRGB 像素为输入，内部再完成线性化及颜色计算，沿用这一输入即可兼容存量作品。普通带 ICC 的图片使用 Pillow ImageCms 的相对比色转换。带矩阵和色调曲线 ICC 的 16 位 RGB PNG，以及带色调曲线 ICC 的 16 位灰度 PNG，用现有 OpenCV 保留 `uint16` 采样，完成浮点转换后才量化成 8 位。透明度随像素保留，普通图片导入也应用 EXIF 方向。无 ICC 的输入保留原有解码路径。

超出 sRGB 的颜色会裁切到工作空间。16 位 PNG 的 ICC 查找表转换当前走带提示的 sRGB 回退。按 sRGB 以外的目标色使用盘的全部色域属于后续工作。

## 色差与出图

用 ImageCms 自带的 sRGB，以及按各色域的原色和传递函数生成的 Display P3、Adobe RGB 兼容和 Rec.2020 测试配置，给同一张 16 色块图做五种编码。本机 Pillow 和系统色彩目录未找到来源和许可可确认的 Display P3 或 Adobe RGB 配置文件，未联网下载。16 位 Display P3 样本从线性 sRGB 计算源采样。

每种编码运行 `python -B -X utf8 -m discprobe --lang en colour-design swatches.png --phone iphone17pro --height 22.3 -o swatches.json --preview <profile>.png`。用 scikit-image 计算 CIEDE2000，再对比 480 × 480 的合成标签和 600 × 600 的预测图。scikit-image 只用于验收计算。五个版本两两比较的最大 ΔE00 为 **0.706**，出现在 Display P3 与 Rec.2020 之间。以下数字均相对内嵌 sRGB 参考。

| 输入 | 最大 ΔE00 | 不同标签数 / 230,400 | 预测图 RGB 通道平均绝对差（0–255） |
| --- | ---: | ---: | ---: |
| Display P3 | 0.353 | 716 | 0.216 |
| Adobe RGB 兼容 | 0.415 | 697 | 0.227 |
| Rec.2020 | 0.355 | 412 | 0.197 |
| Display P3，16 位 PNG | 0.000 | 0 | 0.000 |

日志和预测图在 `D:/dp-dev/tmp/icc/colour-acceptance.log` 与 `D:/dp-dev/tmp/icc/colour-evidence/`。额外用两个高字节相同的 16 位像素验证低字节能改变最终 RGB 量化结果，同时验证透明度边界、有损坏 ICC 时的回退，以及模板预览与原格点输入的一致性。

## 旧路径逐字节回归

从干净的 `95d3289` 工作树复制允许读取的源码到 `D:/dp-dev/tmp/icc/baseline`。分别以基点和 `dev/icc-input` 的目录为工作目录，设置对应的 `PYTHONPATH`，记录实际导入的 `discprobe.__file__`。以 `python -B -X utf8 D:/dp-dev/tmp/icc/legacy_regression.py` 运行同一套 CLI 参数，两边均清除色表、材质集及纹理库的环境覆盖。

用正常 `compose --out` 合成三份没有 `colour` 分配的历史作品。每份的 6000 × 6000 标签 `.npy` 和 `.textures.json` 均逐字节相同。对其中两份执行 `image --geo <几何夹具> --design-npy <标签> --textures <同一列表> --r-max 26 --no-photo-l --output <ISO>`。对无 ICC 的 `docs/colour-guide/example.png` 另以同样的几何和半径运行 `image --picture`，以及运行 `colour-design --phone iphone17pro --height 22.3 --fit ring`。后者生成的作品 JSON 与 180 × 180 合成标签也完全相同。

ISO 使用同一几何夹具和固定的 ISO 9660 写入时间。三对镜像每份 215,121,920 字节，均通过写入器的抽样核对。每对 SHA-256 一致，镜像验证后删除。全容量镜像对照未测。

| 镜像输入 | 基点与本分支共同的 SHA-256 |
| --- | --- |
| `browser-work.discdesign` | `4a310c59dc2e03427c847384d466a468e727269e0a734f9ee74082fb582f1c07` |
| `light-en-picture-work.json` | `df53015a6ff6c39292420ca0c3e4d95e891f93fd09fb19d8c315e70bb6627732` |
| `example.png` | `52b89249a38df1e64272854b6a6d64000e59c6817c7d18152a177d6de5fb6bf5` |

完整哈希在 `D:/dp-dev/tmp/icc/legacy/before.json` 和 `after.json`，运行日志为 `regress-baseline.log`、`regress-icc.log`。首次用历史实测几何时覆盖检查拒绝生成，程序在几何目录新建了两个诊断文件。已核对创建时间并将两个文件移回 `D:/dp-dev/tmp/icc/legacy/first-attempt/`。正式对照采用临时目录里的完整覆盖几何夹具。

## 自动测试与交付环境

- Python 使用 `TEMP`、`TMP` 指向任务临时目录，执行 `python -B -X utf8 -m pytest -n 2 -q --basetemp D:/dp-dev/tmp/icc/pytest-verified tests/test_colour_input.py tests/test_editor_colour.py tests/test_editor_ops.py tests/test_template_grid.py tests/test_gui_handshake.py tests/test_design_compose_route.py tests/test_lamp_optics.py tests/test_simulate_colour.py`。该轮 151 项及 135 个子测试通过，新增 CLI 提示测试暴露了缺失的翻译函数导入。补上导入后复跑 `tests/test_colour_input.py tests/test_editor_colour.py`，24 项全过。日志为 `pytest-verified.log` 与 `pytest-final-icc.log`。
- JavaScript 以 `node --test --test-concurrency=2` 运行 `tests/` 下全部 61 个 `test_*.mjs`。首轮 88 项通过，3 项失败。改正 ICC 无头测试对图层名的假设，并只对 Disc Lab 夹具启用虚拟驱动后，用同一命令复跑这 3 个文件，均通过。ICC 用例通过真实本机 HTTP 读入 16 位 Display P3 和损坏 ICC 图片，分别检查中文转换提示、英文回退提示和实际图层像素。日志在 `D:/dp-dev/tmp/icc/mjs.log` 与 `mjs-retry.log`。
- 卡片指定的 `C:/disc-probe-scratch/gui-handshake/winpack-cache` 不存在。使用 `C:/disc-probe-scratch/release-pack/中文 空格/disc-probe-1.0.0-alpha-full-win64/python/python.exe` 加载本卡代码，确认 Pillow 12.3.0 的 ImageCms 加载 LittleCMS 2.19，OpenCV 5.0.0 用 16 位 Display P3 样本输出参考像素 `(211, 69, 48, 255)`。沿用已打包的依赖。
- Linux 便携运行时未实测。离线 Pillow wheel 带 `_imagingcms` 和 `liblcms2`。发布时可在解包目录执行 `./linux/python/bin/python3 -B -X utf8 -c 'from PIL import ImageCms, features; print(features.version_module("littlecms2")); print(ImageCms.createProfile("sRGB"))'`，再用同一个 16 位 Display P3 样本运行 `colour-design`，检查转换提示和像素。

D 盘开工剩余 49.09 GiB。全量 JavaScript 测试前剩余 49.80 GiB，验收结束时约 40 GiB。实体光驱及实盘刻录未测。执行环境拒绝了递归删除临时测试目录的命令，已逐文件清理 Disc Lab 镜像，仍有部分临时目录留在 D 盘。
