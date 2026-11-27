# 卡 AD · 彩图方向箭头

工作树 `D:/dp-dev/arrow`，分支 `dev/colour-arrow`，基点 `f3d0f2f`。按补充 1 完成交付。

## 按提交交付

- `5dab630` 增加网页彩图填充的默认勾选框和 CLI 的 `--no-arrow`。箭头放在彩图图层正上方，使用普通多边形和 `tex:RND` 材质。两端读取同一份七顶点定义。外沿不足 53.3 mm 时将箭尖移到外沿内侧 0.5 mm，环带放不下时仍可完成彩图填充，并显示提示。
- `8c0cbef` 让网页打开 CLI 的纯多边形作品时沿用箭头的中灰颜色。重开验收发现多图层列表仍调用已移除的 `clearSelection()`，因此点击图层会出错。移除这处旧调用后复验保存重开、去重、移动、隐藏和删除。
- 本报告提交替换第一轮的受阻记录，保留下方社区提示卡报告原文。

`editor_ops.validate()` 仅额外接受精确的大写 `RND`，原错误文字保留。网页导出沿用后端校验，灯下视图已识别 `RND`。`git diff f3d0f2f --stat` 见验收目录中的 `git-diff-stat.log`，`editor_ops.py` 的唯一差异在材质校验。合成、镜像生成、纹理表、拟合色表和 texlib 的差异为 0。

## 老路径逐字节回归

以下 `compose` 分别用基点导出的源码和本分支运行。4-18 使用原作品，另外三个作品来自 `tests/test_editor_ops.py` 的 `document()`、`grey_document('ordered')` 和 `tests/test_design_compose_route.py` 的 `ring_work('92')`。每份标签为 6000 × 6000。下列 SHA-256 在两版完全一致。

| 作品 | 标签 `.npy` SHA-256 | `.textures.json` SHA-256 |
| --- | --- | --- |
| 4-18 `COLOUR-1x21-A` | `1f08f6a7402fab6330a5b21a0df7ee3a2da544fdebb1c191477c535b6da9fe40` | `99cc0a916e5599448c649e2e309117adebb144968828169e526e43c2b3c26850` |
| SVG 与图案 | `5ecb94e2e2d0a82a71cfca85fc8e8bf60bf87b640358c08c2b25d4829567cd2c` | `a328367dd3dcb70c8761e4212fee11b962fac5228d168d48bd582b1b41d41be0` |
| 灰阶影调 | `a6e0b542e3fe059ae8419bfbeedeedbe8506e5c9a178568b0bd1590dd5e46f96` | 同上 |
| 网页圆环填充 | `12448b74f0b1f209ad3a7681b116145bf3d8b260476cf3973b4bd11ea2ad5f9d` | 同上 |

- 4-18 原 `.image.json` 提供几何、材质顺序、20 µm 格、起始和前导 LBA，以及 photo L 和角度修正状态。同一脚本从记录的总扇区数反推 `--r-max 54.0400471937871`，用同一份几何文件副本构建两套 `image` 命令。ISO9660 使用统一的测试时钟（2026-11-12 00:23:03 UTC），其时间戳本来取生成时刻。两份完整 ISO 均通过写入器抽验，长 1,966,944 扇区、4,028,301,312 字节，SHA-256 均为 `67b1548f42713eb64aa741ec78cc873f0a781d15f9c4cbefe90e763e1cdf6811`。
- 从 4-18 文档解出同一张 640 × 640 RGBA PNG，以相同参数运行基点 `colour-design` 和分支 `colour-design --no-arrow`。两份作品 JSON 逐字节一致，SHA-256 为 `11511e6e011bcce99f373a825b95e25e6bc7892eb42f6981ccc63af7d6c25d64`。
- 两版直接运行文档校验。18 份不含 `RND` 的输入结果一致，7 份通过，11 份仍以原消息拒绝，覆盖奇数位、非法十六进制字符、超长、非字符串、小写或混合大小写、前后空格和 `MIX:`。第 19 份精确大写 `RND` 输入由基点拒绝、分支接受。非 `RND` 输入仍走原校验表达式。

## 新作品、ISO 和镜面带

- 用 `colour-design --phone iphone17pro --height 21` 生成默认作品。验收输入沿用 4-18 的彩图，将 27–53.75 mm 外的像素设为透明以适配现有实测几何，要出 ISO 的作品 JSON 由 CLI 直接生成。箭头在 20 µm 网格上覆盖 59,662 格，与独立计算的多边形掩模逐格相同，全部为槽位 60。多边形面积 23.8128 mm²，理论计数 59,532，实测多 130 格（+0.2184%）。掩模外标签与关闭箭头时一致。
- `compose` 的 `.textures.json` 最后一个规格为 `RND`。随后 `image` 成功生成 1,966,944 扇区的 ISO，SHA-256 为 `2b84314360d63c9de285dc83e62872a54c52108fb8048ed01d0951c797400b96`。从螺旋几何定位 8 个扇区内属于箭头的字节，按各 LBA 异或 DVD 扰码表。箭头头部有 2 个扇区完整覆盖，另外 6 个扇区部分覆盖。检查的 9,920 字节全部与 `texture_bytes("RND")` 一致。抽样 LBA 为 1120279、1175733、1258056、1330517、1460824、1477097、1652826、1654069。逐扇区哈希、字节数与半径见 `new/results.json`。

按拟合色表的最低支持偏移 0.1 和偏移比例 0.93，计算 12 点两侧的镜面带全角。B9 比例直接取无箭头的合成标签。

| 机位 | B9（槽位 0）占箭头区域 | 尾部 43.5 mm | 头底 48.59 mm | 尖端 52.8 mm |
| --- | ---: | ---: | ---: | ---: |
| iPhone 17 Pro，CLI 21 cm，镜头离盘 208.7 mm | 59,662 / 59,662（100%） | 25.001° | 24.955° | 24.928° |
| 4-18 原文档机位，镜头离盘 221.740 mm | 59,662 / 59,662（100%） | 26.561° | 26.519° | 26.494° |

4-18 作品存的是机位 ID `21`，现用机位表将它显示为尺高 22.3 cm。对照保留这个作品机位，另测 CLI 输入的 21 cm。宽度为拟合模型的方位宽度。未做实盘观察。

## 网页和测试

- 在临时回环端口用独立 Python 后端进程跑编辑器，光驱提供器返回空列表。用无头 Edge（`--mute-audio`）经过图片文件输入和实际填充按钮，验证默认勾选、取消、重复填充、一次撤销、窄环带提示、保存重开、纯多边形恢复、灯下及刻出视图。在 `F:/dp-archive/tmp/colour-arrow/shots/` 保存 1440 × 1000 的 `paper-checked.png`、`paper-unchecked.png`、`night-checked.png`、`night-unchecked.png`。
- `python -B -X utf8 -m pytest -n 2 tests/test_editor_ops.py tests/test_design_compose_route.py tests/test_lamp_optics.py tests/test_editor_colour.py -q --basetemp=F:/dp-archive/tmp/colour-arrow/acceptance/pytest-final`，**123 passed**。运行 `python -B -X utf8 -m discprobe --lang en colour-design --help` 和对应的 `--lang zh`，核实两份帮助都含 `--no-arrow`。
- 逐个执行 `node tests/<各 test_*.mjs>`，**55 个文件均通过验收**。全量首跑 54 通过、1 失败，失败项是重开后点击图层的检查。修复后为最终版本复跑 `test_editor_texlib_browser.mjs`、`test_editor_desk_browser.mjs`、`test_editor_w245_browser.mjs`、`test_csp_browser.mjs`、`test_ime_activity.mjs`，5 个均通过。首跑和复跑日志均保留。

验收日志、命令生成及反解脚本 `proof.py`、基点和分支的哈希清单均在 `F:/dp-archive/tmp/colour-arrow/acceptance/`。开跑和全量回归前 D 盘分别剩余约 199.7 GiB 和 199.2 GiB。测试生成的 ISO 已删除。未连接光驱或刻盘，未推送或合并。没有需要审查者先决定的实现事项。
