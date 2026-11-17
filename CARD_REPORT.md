# 卡 W：编辑器接入只读纹理库

2026-11-17；worktree `D:/dp-dev/editortex`；分支 `web/editor-texlib-20261117`；起点 `7cf2c82`。

## 本次提交

提交主题：`Support optional texture libraries in core and editor`。实现、测试与本报告一并提交，没有推送、合并、切换分支或修改其他 worktree，没有接光驱、刻盘、上传或下载。

- 新增 `discprobe/texlib.py`：只读目录、查询、引用解析和指标读取。`DISCPROBE_TEXLIB` 或 CLI 的 `--texlib DIR` 指向含 `colour_table.npz`、`textures.jsonl` 的目录；未配置、不可用、损坏或不匹配时回退包内表。读取实际 Unicode dtype，不写死 U190。
- `simulate_a3.tables()` 换来源时清缓存；键包含解析后的路径、大小、mtime、模型 signature 和目录签名。PNG/色板缓存也包含来源。一次绘制复用同一表，避免逐材质重复访问文件。
- `/api/editor-swatches` 提供当前机位及盘面右侧 40 mm 的颜色/筛选指标；新 `/api/editor-lamp-tables` 一次返回相配的 metadata 与 XYZ，浏览器 worker 使用同一色表。静态服务没有 API 时继续用包内数据；来源变化后重建 worker。
- 网页默认“拿在手里看”，可切换“固定机位拍照”。手持阈值常量 15，可见门槛 0.04；拍照只检查可见性。主区按实际显示色的 sRGB/D65 CIELAB ΔE76 < 2 合并，代表先取稳定度好者，再取纯度高者。
- “全部材质”保留两个收录档次中的每一条记录，包括同 spec 的不同目标；按颜色、目标 ID、spec 搜索，筛掉的仍能选择/填充。格子 title 提示变色或消失，详情显示“实刻过 / 模型预测”和人话稳定度。网页不展示内部质量档名或稳定度字段名。
- 不改旧色板的 255 个 ID、含义和导入 RGB；不改布局/CSS、木纹桌面、画布外透明度或格子选中样式。空作品只预留底色/深色，实际填充的新增材质随可撤销操作加入；已有作品的材质表不删减，第 257 种明确报错，不截断。
- DVD/CD 环形靶支持十六进制字节序列，保留原参考纹理约束。CD 按物理 frame/slot 定相，独立反解检查；没有把 DVD 序列相位套到 CD。

未修改 faxnews、newplan、presetio、news、community 模块或 `evidence/atlas/*.py`。全量 JavaScript 验收按公共卡要求包含它们的现有测试，未修补其代码。递归检索预先排除受限路径。`F:/dp-archive/texlib/` 全程只读。

## 材质身份和 CLI 入口

查明作品 v2 保存完整 `materials: [{id,spec,rgb,...}]`，填充和图案按 ID 引用；compose 生成的 `.textures.json` 保存槽位顺序对应的 spec。旧身份保持。新身份为 **`tex:<spec_canonical>`**，作品同时保存完整 spec；目标 ID/rev 只用于查询。不同目标的相同冠军字节共用作品身份，但在“全部材质”中各自可查。更换冠军不改已保存作品的字节纹理，测试覆盖改 rev 后重开。

| 现有入口 | 本轮处理 |
|---|---|
| `simulate --dark/--light` | 接受目录目标 ID、旧编辑器 ID、`tex:<spec>` 或原始 spec；扩展纹理走 A3 表，支持单图和 `--sheet`。无库且使用旧字节参数时保留旧渲染路径。 |
| `simulate --work` | 用作品内固定 spec 和所选色表，不重新绑定目标冠军。 |
| `image --dark/--light/--textures` | 生成前解析引用，交给既有编码器。 |
| `tiles --palette` | 同上，保留靶布局。 |
| `rings --textures/--filler` | 解析引用，DVD/CD 增加序列编码与验证。 |
| `compose` | 从作品完整材质表生成标签与 spec 顺序；它原本没有独立选择材质的参数。 |
| `template` | 没有任意材质参数；原模板导入身份保留，未重排模板色。 |

`simulate/image/tiles/rings/compose/webui` 支持 `--texlib DIR`，也可统一设环境变量。固定校准命令中写死的参考纹理未替换为冠军。没有色表/周期的未知 spec 不能凭空获得光学预测；编码可以使用任意合法字节序列。

```powershell
$env:DISCPROBE_TEXLIB = 'F:/dp-archive/texlib/latest'
python -m discprobe textures find --grade best_so_far --kind ladder --delta 0.35 --max-de05 15 --min-y 0.04 --top 10 --json
python -m discprobe textures find --near '#50a070' --top 5 --json
python -m discprobe textures show DVD-S-B0000-K96-A8e5716 --json
python -m discprobe webui --texlib F:/dp-archive/texlib/latest
```

新查询当前输出 JSON，支持显式 `--json`；不应用网页的手持/近色合并规则。核心可以查询 approx，网页只收 converged 和 best_so_far。近色查询按指定 δ 最近的颜色采样点比较；指标按下述保守规则读取。

## 真库统计

源解析到 `F:/dp-archive/texlib/20261116-0441`，3973 条记录、3832 种 canonical spec。脚本/数据在 `F:/dp-archive/tmp/editortex/measure.py`、`measure.mjs`、`real-palette.json`、`statistics.json`。

使用现有 `iphone17pro@30`：camera `[0,28.45,298.7]`、flash `[0,76.3857872575386,298.7]` mm；盘面 `[40,0]` mm；**δ=0.33968092402234995**。“30 cm”是现有标尺机位名，未把镜头高度强改为 300 mm。

目录指标只有 18 个采样点。非网格 δ 的 Y 线性插值；稳定度保守取两侧较大值，任一侧未知则保持未知；fades 任一侧为真即按会消失处理。null 不当作 0，不在范围外外推。这里是实际网页策略的统计，未在任意 δ 精确重算窗口稳定度。色块及合并均用 `simulate_a3.swatches()` 的同机位显示色。

色相分段为红 <20° 或 ≥340°、橙 <45°、黄 <75°、绿 <165°、青 <200°、蓝 <265°、其余紫；HSV 饱和度 <0.12 归近白。以下各项为 **合并前 / 合并后**；前者按目录记录计，仍含同 spec 的目标别名。

| 阈值 | 总数 | 红 | 橙 | 黄 | 绿 | 青 | 蓝 | 紫 | 近白 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 0 / 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| 12 | 6 / 5 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 6/5 | 0/0 | 0/0 |
| **15** | **21 / 12** | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 21/12 | 0/0 | 0/0 |
| 20 | 46 / 26 | 0/0 | 0/0 | 0/0 | 0/0 | 1/1 | 44/24 | 0/0 | 1/1 |
| 25 | 89 / 51 | 0/0 | 0/0 | 0/0 | 0/0 | 4/3 | 81/44 | 0/0 | 4/4 |

拍照模式 **3864 / 1659**；全部材质始终 3973 条。先取默认 15：8 没有选项，12 仅 5 格，15 有 12 格且比 20/25 保守；这是待审查方决定的使用策略，不是实拍保证。

阈值 8/12/15/20 没有 HSV 饱和度 ≥0.35 的蓝绿代表；25 只有一个偏蓝代表，RGB `[98,111,153]`、稳定指标 22.9、纯度 0.009972，视觉仍偏灰。按饱和度 ≥0.5，五档均没有。没有绿格，不能宣传成“鲜艳且稳定的蓝绿”。

读取前后下列 SHA-256 一致：

| 文件 | SHA-256 |
|---|---|
| colour_table.npz | `3bb71d2ec71480d3962f6520c9293a7830707828a9b88c02b811401956a509c6` |
| textures.jsonl | `eee3886c0984d42b30290455c118dc51ee31017ca7498062b2f6dd100eb5e479` |
| README.md | `bc9f98e51ce38f52873a4ea22179721031c1c9db15b54dc9dfcf65aad91f2287` |
| MANIFEST.json | `1a22e390844662b500e72c0763f270e92a5318d7c1eb4ee844204b5f698f4dec` |

## 验收命令和结果

所有日志在 `F:/dp-archive/tmp/editortex/`。测试设置 `TEMP/TMP` 到该目录、Python 用 `-B -X utf8`；默认回归清除 `DISCPROBE_TEXLIB`。启动前 D 盘约剩 46.38 GB，全量前约 46.37 GB，未触及 5 GB 停止线。pytest 固定 `-n 2`。

1. `python -B -X utf8 -m pytest -n 2 tests/test_editor_ops.py tests/test_editor_preview.py tests/test_editor_pose_swatches.py tests/test_lamp_optics.py tests/test_design_compose_route.py tests/test_editor_texlib.py --basetemp=F:/dp-archive/tmp/editortex/pytest-final -q -p no:cacheprovider`：**109 passed**，`python-final.log`。
2. 后续环形靶/CLI/光学复核，同样参数运行 `test_editor_texlib.py test_editor_preview.py test_lamp_optics.py`：**20 passed**，`python-sequences.log`。只生成 64 扇区小文件，独立反解成功，没有真实刻盘。
3. 最后针对拼图路径和坏表回退运行 `test_editor_texlib.py test_editor_preview.py`：**13 passed**（新库测试 11 项），`python-last.log`。这些轮次有重叠，不能相加冒充独立项数。
4. `node --test --test-concurrency=2 <tests/ 下所有非受限 test_*.mjs，导航另跑>`：**64 passed / 1 failed**，`node-final.log`。卡中指定的编辑器、材质、rig、lamp、design export、W245 均通过；W245 四个主题/格距哈希均仍是 `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`，18 个浏览器检查通过。
5. `node --test --test-concurrency=1 tests/test_flow_navigation_browser.mjs`：**1 passed**，`navigation.log`。
6. 唯一失败是 `test_presetio_browser.mjs:312`，期望 `PASS`，收到 `PENDING`。单独串行复核一次仍失败，`presetio-isolated.log`。不改卡 W 排除的模块；**未证明是基线已有故障，不宣称全套通过**。
7. 最后 `node --test tests/test_editor.mjs tests/test_editor_materials.mjs tests/test_editor_rig.mjs tests/test_editor_lamp.mjs tests/test_editor_texlib.mjs tests/test_design_export.mjs`：**6 passed**，`editor-last.log`。
8. 普通新增测试只读临时目录中的 4 行 JSONL / 小 NPZ（含 U192），不读真库。覆盖坏库回退、换表缓存、旧 ID、冠军变更后的固定身份、未知稳定度、筛选、CLI、动态 worker 表、软筛选仍可填充保存和 256 拒绝。
9. 显式 `EDITOR_TEXLIB_ROOT=F:/dp-archive/texlib/20261116-0441`、`EDITOR_TEXLIB_OUT=F:/dp-archive/tmp/editortex/after` 运行 `node --test tests/test_editor_texlib_browser.mjs`：**1 passed**。3973 条、默认主区 12 格、活动材质有效、筛掉材质仍可用且 spec 固定、256 拒绝、浏览器异常 0。日志 `real-browser.log`，这是单独真库验收，不是默认夹具。
10. `git diff --check` 通过；中文改动做 UTF-8 字符数及连续问号检查。impeccable detector 对改动 UI 返回 `[]`。独立界面复核 `ship`；活动材质回退修正后的有限范围复核也为 `ship`。

无头 Edge 的纸色/夜色截图均为 1440×1000，在 `after/`：两套主题各有 `held`、`camera`、`all-warning`、`detail-tested`、`detail-predicted`，共 **10 张**。已逐张核对主题、内容、尺寸，无空白/未加载区域。测试生成到 worktree 的 `evidence/editor` 和 `.impeccable` 已移至 `F:/dp-archive/tmp/editortex/regression-evidence/`，不混入提交。新增浏览器夹具自动删除自己的 Edge profile。

测试结束清理存在限制：自动审批策略拒绝删除 `pytest-*`、API 夹具目录，以及改用明确路径删除大 `.npy/.raw` 文件的请求，返回原因仅为 `blocked by policy`。没有换工具绕过。其余成功测试夹具因此仍留在指定 F 盘临时目录，未达到“只留日志/截图/失败现场”的完整清理要求；结束前 F 盘约剩 8.8 GB，D 盘约剩 46.3 GB。

## 待决定与边界

- 默认 **不随包带快照**。优点：包小，数据独立更新，旧版默认行为明确；代价：未配置的机器只有 255 种，跨机器做相同光学预览需要相应色表。随包快照则离线即有扩展色板、预览更容易复现，但约增加 15 MB NPZ + 7 MB JSONL，需要维护版本/来源/更新节奏及外部库优先级。随包方案未实现，留给审查方决定。
- 阈值 15、可见门槛 0.04、合并距离 2 及非网格的保守取值均待审查。颜色是 LED 模型预测，不保证真实颜色、绝对亮度、手持实拍稳定或可读性。
- 作品不嵌入光学表。未来表不再含已存 spec 时，预览沿用既有按周期近似；无周期的未知 spec 可能无法预览，但作品编码仍使用保存的字节。
- 旧作品满 256 槽时保留原表，新增会提示上限；网页尚无专用材质槽清理工具。没有通过自动删槽绕开限制。
- 浏览器更换机位/刷新/重开时取当前来源，没有新增每小时轮询。静态页面没有后端时只用包内表。
- 独立文档核对无需新增设计系统文件，PRODUCT/DESIGN/STYLE 保持原样。既有文档在圆角、字标及夜色迁移说明上有漂移，未借本卡修补。
- 新库作品完整导出链路、实际刻盘/实拍、安装包构建：**未测**。指定旧导出规则测试已通过。全量 JavaScript 的 presetio 失败仍未解决。
