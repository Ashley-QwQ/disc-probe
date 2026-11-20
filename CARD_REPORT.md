# EF 编辑器修复验收

分支 `dev/editor-fix-a`，基点 `ed7136e`。A1–A4 均已在 Disc Lab 复验。浏览器用脚本经 CDP 驱动无头 Edge，光驱和刻后流程均用 Disc Lab 的虚拟设备。

## 提交

- `a04c774`：窄屏默认显示画布，用现有按钮切换「图层」「影调」侧栏，预览在画布下方显示检查清单。可用的 DIS 转换走名义几何，预览单独说明实测状态。镜像按作品和保存的设计版本找回，后端用当前文件的 `.verification.json` 判断是否可继续。Web 镜像参数支持 `RND`，无效纹理报出从 1 开始的项号。新增窄屏实坐标、名义几何、任务恢复及纹理验证测试。
- `dbec384`：更新 GUI 握手测试，覆盖 API 1.1 的可选镜像恢复能力。
- `644812e`：更新中英两种 DIS 名义几何提示的断言。
- `d7d9a73`：镜像任务提交后，重新进入预览按服务器保存的设计版本校验；本页尚在准备并未启动任务时保留原有准备状态。

## Disc Lab 复验

运行 `node D:/dp-dev/tmp/edfix/final-walk.mjs <scenario> <variant> <tag> <port>`，另用 `extra.mjs` 跑无重叠的 DIS 用例、`close-live.mjs` 跑关页后从往期作品接回进行中的任务。截图和每轮 `run.json` 都在 [shots](<D:/dp-dev/tmp/edfix/shots>)，前后对照汇集在 [before](<D:/dp-dev/tmp/edfix/shots/before>) 和 [after](<D:/dp-dev/tmp/edfix/shots/after>)。

| 项目 | 结果与证据 |
| --- | --- |
| A1 · 390×844 | 纸色中文关动效、纸色英文开动效、夜色英文关动效、夜色中文跟随系统减动共 4 组。导入、示例和每个「下一步」均经实坐标命中，走到预览、镜像生成和刻录确认。[纸色中文改前](<D:/dp-dev/tmp/edfix/shots/before/A1-paper-off-390-zh.jpg>) · [改后](<D:/dp-dev/tmp/edfix/shots/after/A1-paper-off-390-zh-entry.jpg>) · [夜色英文改前](<D:/dp-dev/tmp/edfix/shots/before/A1-night-off-390-en.jpg>) · [改后](<D:/dp-dev/tmp/edfix/shots/after/A1-night-off-390-en-entry.jpg>) · [坐标及 10 组结果](<D:/dp-dev/tmp/edfix/matrix-summary.json>) |
| A2 · DIS 与实测 | 原拒绝发生在 `coverage.range_warning` 的无实测区间分支。只导入兼容的 DIS 预设，中文预览明确提示在第一张盘上检查位置，后台任务退出 0，生成 4,700,372,992 字节。另测英文的 16–22 mm 名义范围，预览解释与可刻区无重叠，「下一步」进入标定，没有启动镜像任务。无几何的中文用例也进入标定。用同一虚拟 DVD-R 实测数据的主路径正常生成。[改前](<D:/dp-dev/tmp/edfix/shots/before/A2-dis-zh.jpg>) · [改后](<D:/dp-dev/tmp/edfix/shots/after/A2-dis-zh.jpg>) · [无重叠](<D:/dp-dev/tmp/edfix/shots/after/A2-dis-range-en.jpg>) · [无几何](<D:/dp-dev/tmp/edfix/shots/after/A2-no-geometry-zh.jpg>) |
| A3 · 关闭及刷新 | 中文生成中关页，后台完成后从往期作品打开，预览显示「下一步：刻录」。英文刷新接回进度，再跳到刻录确认。另用英文在生成中关页，从往期作品接回进度，再继续到刻录确认。三轮各只有 1 个 `image` 任务，各自退出 0。后端测试覆盖了自检缺失、文件被替换及设计已改的情形。恢复沿用后端 Job、取消接口与作品记录，成功镜像可以再次打开。[关页改前](<D:/dp-dev/tmp/edfix/shots/before/A3-close-zh.jpg>) · [改后](<D:/dp-dev/tmp/edfix/shots/after/A3-close-zh.jpg>) · [刷新改前](<D:/dp-dev/tmp/edfix/shots/before/A3-refresh-en.jpg>) · [改后](<D:/dp-dev/tmp/edfix/shots/after/A3-refresh-en.jpg>) · [往期作品接回进度](<D:/dp-dev/tmp/edfix/shots/after/A3-library-progress-en.jpg>) |
| A4 · 方向箭头 | 保留彩色图的默认箭头。Web 生成 4,626,808,832 字节，自检通过。用几何和光盘扰码解出最终 ISO，核对了 2,470 个箭头扇区中 1,806,560 个随机纹理字节及 288,319 个相邻非随机纹理组。实读落在半径 43.503–52.776 mm，数据面 12 点两侧约 4.09° 内。参数测试核对了第二项不合法时的中英错误。[改前](<D:/dp-dev/tmp/edfix/shots/before/A4-arrow-zh.jpg>) · [改后](<D:/dp-dev/tmp/edfix/shots/after/A4-arrow-zh.jpg>) · [最终数据面预览](<D:/dp-dev/tmp/edfix/shots/after/A4-arrow-data-side.png>) · [读回数字](<D:/dp-dev/tmp/edfix/shots/arrow-paper-off-1440-zh-verified/arrow-byte-check.json>) |

EW 桌面主路径另外跑通 6 组。纸色中文关动效、夜色英文开动效、纸色英文开动效、夜色中文关动效、纸色中文跟随系统减动、夜色英文跟随系统减动。六组都从大厅走到导入、机位和灯下预览、生成、虚拟刻录、刻后记录和往期作品重开。矩阵用相同的虚拟实测夹具缩窄到 26–38.5 mm，每组生成 1,583,316,992 字节。A2、A3 关页后打开和 A4 另有整盘尺寸复验。

## 自动测试及逐位回归

- `python -X utf8 -m pytest -n 2 --basetemp D:/dp-dev/tmp/edfix/pytest-final -q tests/test_webui_recovery.py tests/test_webui.py tests/test_presets.py tests/test_webui_catalog.py tests/test_design_compose_route.py tests/test_gui_handshake.py tests/test_works.py`：166 项、50 个子测试通过。[日志](<D:/dp-dev/tmp/edfix/pytest-final.log>)
- 按卡片排除指定路径后，将 `tests/` 下所有 56 个 `test_*.mjs` 交给 `node --test --test-concurrency=2`。首轮 69 项中 63 项通过。更新能力列表、文案和窄屏按钮选择器的断言后，对这 3 项单跑通过。其余 3 项为 Edge 配置目录清理权限和两处计时失败，串行复跑 3/3 通过。[全量日志](<D:/dp-dev/tmp/edfix/node-final.log>) · [串行日志](<D:/dp-dev/tmp/edfix/node-retry.log>) · [最新导航复跑](<D:/dp-dev/tmp/edfix/flow-navigation-final.log>)
- 以保留的四张盘的历史 `.npy` 设计为输入，用 `EF_LABELS_ONLY=1` 和 `python -X utf8 D:/dp-dev/tmp/edfix/compare.py <case> <source> <before|after>`，分别载入 `ed7136e` 和本分支代码，重算整个写入范围的取样标签。MIX-A 沿用原配方的分组和逐字节细采样区域。取样标签没有 ISO 写入时间字段，直接比较 SHA-256。四对全部一致。本轮逐位回归证据是标签数组。[前后哈希与输入记录](<D:/dp-dev/tmp/edfix/regression-labels>) · [回归脚本](<D:/dp-dev/tmp/edfix/compare.py>)

| 历史设计 | 每次计算的标签数 | 前后相同的 SHA-256 |
| --- | ---: | --- |
| SHOW-E | 274,579,456 | `a17b8581fc571e9fc32c4b104687539d179303aa5fe3b52ee4d2022b39d59acd` |
| CARDB-1 | 274,579,456 | `6ea5ece0b23abff1830f059c56748f504b018252eaa0919722d72c97630cde71` |
| PCAL-C | 293,773,312 | `460d5e3fdb2860a5b115475a4904533d9d7ec9790b9f510cb9b2cfe3a9074ebf` |
| MIX-A | 699,874,944 | `08719615838d76bdf573b835fe26e1921e0f0b6dffc61addde5667e4d505333a` |

## 给 Claude 转达及待审

- 请审查窄窗的「图层」「影调」按钮位置和 DIS 文案「位置准不准，要看第一张盘」。A3 重开预览后显示原任务的进度或原文件，用户仍从右下角进入刻录确认。
- 新增任务查询路由采用 API 1.1 的可选能力。作品记录只增加来源设计字段，原任务事件和既有记录格式仍可读。
- 实体光驱兼容性、实体手机与刻盘外观未测。首轮并发镜像跑法有超时，矩阵改用缩短的虚拟实测范围，总结中的整盘结果来自独立用例。已从 EF 临时目录清理约 50.2 GB 的镜像、浏览器配置和测试夹具，保留日志、截图及校验记录。未推送或合并。

STATUS: DONE
