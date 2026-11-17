# 卡 U 交付报告

分支：`web/editor-ergo-20261117`。起点：`006ec00`（与卡 U 一致；COMMON 中较早的基点未采用）。
本报告与实现同次提交：`Improve editor colour workflow and fold persistent guidance`。未推送、未合并。

## 本次提交

- 仅修改 `design.js`、`design.css`、`design/editor-controls.mjs`、`design/editor-ui.mjs`、`design/editor-rig.mjs`，以及本报告。
- 右栏增加“影调 / 颜色”分段按钮。默认影调；用 WeakMap 按作品保存本次会话的标签选择，不改变作品文件或撤销记录。
- 机位完整后显示手机与高度摘要，“更改”可展开原来的两组控件。其他手机的距离输入和异步色板仍可用。
- 当前材质、填到、图案填充及唯一的“填充”按钮移到颜色页顶部。保留单材质、图案、特效及原来的选项；禁用没有有效像素的选区，并显示原因。
- 色板移除内部滚动限制，自动排列，保留弧形图；title 和 aria-label 使用现有材质名字加颜色名，选中描边改为墨色 2 px。右栏只有面板滚动。
- 原来的机位、模型和默认黑白刻说明放进“说明”；搜索框仍在色板上方，隐藏材质数量提示仍在下方。
- 刻录格子保留一条短说明，其余原文放进“说明”；DVD±R 等限制说明移到随盘文件的折叠中。随盘文件的原有教法在空时显示，有文件时收起，清除后恢复。
- 影调抖动原文收进“说明”。切换格子后同步刷新影调说明的 µm 数值。
- 右栏 range 使用墨色进度与滑块、rule-strong 轨道；select 保持原生下拉，只改边框、颜色、箭头和方角。沿用原有焦点环，未新增动画。
- 左侧工具栏和刻录格子按钮达到 44 px。短窗口工具栏可滚动，末尾手形按钮可到达；短窗口的自定义悬浮提示会受滚动容器裁切，原生 title 提示及 aria-label 保留。
- **图层行五个小按钮暂未扩大**，原因与两种可选做法见下节。画布、顶栏、下一步及画布下的视图切换未改。

## 点击区域与需要决定的布局

数据来自 `after/acceptance.json`，用 `getBoundingClientRect()` 测量；纸色、夜色相同。

| 控件 | 1440×1000 | 1024×768 |
| --- | --- | --- |
| 图层：隐藏、锁定、上移、下移、删除（各） | **24×32 px，未达标** | **24×32 px，未达标** |
| 20 / 10 / 5 µm（各） | 86.66–86.67×44 px | 73.33–73.34×44 px |
| 左侧工具栏 11 个按钮（含撤销、重做） | 44×44 px | 44×44 px |
| 色板 | 5 列，约 52.40×48 px | 4 列，54.5×48 px |

图层行宽为 272 / 232 px。五个 44 px 按钮加 32 px 缩略图、现有间距、边框及 padding，即使不给名称留空间也需约 280 px。用伪元素扩大会让相邻点击区域重叠，所以保留原布局，按卡要求交审查决定：

1. 每个图层固定两行：上行缩略图和名称，下行五个 44 px 按钮紧邻排列（220 px）；每行高度约 90–98 px。操作直接可见，但图层列表明显变高。
2. 保留紧凑图层行，用一个 44 px 的“图层操作”入口展开下方五个 44 px 按钮；只让正在操作的图层变高。列表较紧凑，但多一次展开操作，需要决定是否接受。

10 / 5 µm 有现成短说明，分别取现有 cellCost 的首句，不需要新增事实。1024 px 时 10 µm 的时间和内存句会换成两行，未缩小字号。

## 验收

本轮脚本、浏览器配置、截图和日志存放在 `F:/dp-archive/tmp/editorergo/`。运行时设置 TEMP、TMP；Python 使用 `-B`。两个原 Python 测试仍硬编码向工作区 `evidence/editor/` 写 compose-parity.json 和 round4/render-parity.json；结束检查发现后，已将这两个本轮新建 JSON 移到 F 盘 `python-evidence/`，未修改测试、未纳入提交。开跑前 D 盘可用 40,683,593,728 字节，全部 JS 回归前仍约 40.66 GB，超过 5 GB 门槛。成功的 pytest 临时产物及 W245 浏览器配置已清理，保留日志、截图和失败日志。

### 卡内 JavaScript

```text
node --test tests/test_editor.mjs tests/test_editor_materials.mjs tests/test_editor_rig.mjs tests/test_editor_lamp.mjs tests/test_design_export.mjs tests/test_editor_w245_browser.mjs
```

6 个测试文件全过、0 失败。W245 浏览器夹具 18 项行为检查全过、0 个运行时异常。20 / 10 µm、纸色 / 夜色的四组预览 SHA-256 均保持：

`f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`

日志和 JSON 保存在 `tests/browser-test-*/after.json`；最终全部 JS 回归也包含以上六个文件并全部通过。

### Python

```text
python -B -X utf8 -m pytest -n 2 -o cache_dir=F:/dp-archive/tmp/editorergo/pytest-cache --basetemp=F:/dp-archive/tmp/editorergo/pytest-run <tests/test_editor_*.py 和 tests/test_design_compose_route.py 的显式文件列表>
```

**94 passed，41.35 秒**。文件列表由排除受限路径的 `rg --files` 生成。日志：`pytest.log`。未跑整个 Python 测试套件。

### 最后一次全部 JS 回归

```text
python -B -X utf8 F:/dp-archive/tmp/editorergo/run_node_checks.py
```

脚本对 `tests/` 下全部 `test_*.mjs` 用排除规则生成清单，使用 `node --test --test-concurrency=2`。共 **51 个文件、62 项测试：60 通过、2 失败**。其中两个原测试把截图写到相对 cwd 的 `.impeccable`，单独以 F 盘临时目录为 cwd 执行，源码未变，均通过。

- `test_preset_geometry.mjs`：匹配 preview.js 中已过时的英文导入说明失败。把 `006ec00` 的原测试及所需源码直接导出到 `base-check/`，同一断言仍失败（exit 1），证实基点已有。preview.js、此测试均未修改。证据：`base-check/preset-geometry.log`。
- `test_flow_navigation_browser.mjs`：本地夹具服务出现 `ERR_CONNECTION_REFUSED`，首次在动态载入 design.js 时失败。单独重验仍失败，92.38 秒后在 `?nav-library` 入口超时，多项首页资源连接被拒绝。原因未确定，不能声称只是偶发，也未证明基点同样失败；未改相关页面、服务或断言。证据：`node-all.log`、`flow-recheck.log`。

完整命令、每批文件数和退出码见 `node-results.json`；另有 `test_review_library_newwork.log`、`test_presetio_browser.log`。

### 新布局、截图及静态检查

```text
node F:/dp-archive/tmp/editorergo/cap_after.mjs
impeccable.cmd detect --json <五个改动的 UI 文件>
git diff --check -- <五个改动的 UI 文件>
```

- 从卡给定的 `cap_before.mjs` 派生本地色条夹具；无后端、无光驱。实际浏览器 **Edge 157.0.4341.60**，无头模式，DPR 1。
- **21 项检查通过、0 个运行时异常**：默认标签、同作品标签记忆、机位折叠/展开、自定义手机、唯一填充按钮、空及零面积选区禁用、图案填充与撤销、range 进度、文件教法收起/恢复、英文控件、单层滚动、色板最小尺寸、窄窗口末尾工具可达。
- 1440×1000 纸色、夜色各一套：`after/shots/light/`、`after/shots/dark/`，含 01–05、选中色块、展开“更改”、10 µm。保留了滚动过程的 04 三张。
- 与原夹具文件名对应的 01–05 副本放在 `after/` 根目录；原 02 是完成机位和工具操作后的夜色状态，对应 `shots/dark/05-colour-tool.png`。
- 1024×768：`after/shots/09-narrow-top.png`（顶部控件）、`09-narrow-colour.png`（滚到色板，4 列）；另有 `10-english-narrow.png`。
- 机器检查输出 `impeccable-detect.json` 为 `[]`；diff 空白检查通过。含中文的四个 JS 文件及本报告，UTF-8 非 ASCII 数量均大于 0，未发现问号连续替代中文；CSS 为原有英文注释。
- 未修改仓库中的任何测试断言。临时截图检查初稿误用材质 ID 核对可读名称，已改成核对现有材质名字；检查也发现切换格子后影调说明未更新，已在 UI 中修正。

## 新增或缩短的中英文案

| 中文 | English |
| --- | --- |
| 影调 / 颜色（沿用） | Tone / Colour |
| 编辑 | Edit |
| 更改 | Change |
| 填到 | Fill to |
| 填充 | Fill |
| 说明 | About |
| 还没有选区，先在画布上建立选区。 | No selection yet. Create one on the canvas first. |
| 先选一张图片，再调整影调。 | Select a picture to adjust its tone. |
| 颜色是模型预测，还没逐块对照 | Colours are model predictions, not yet checked swatch by swatch |
| 默认，约 2 分钟生成 | Default, about 2 min to make |
| 生成约 4 分钟，要 2 GB 左右内存。（原句） | Takes about 4 min and 2 GB of memory to make. |
| 生成约 10 分钟，要 5 GB 左右内存。（原句） | Takes about 10 min and 5 GB of memory to make. |

原有 cellCost、机位、模型、黑白刻限制、随盘文件教法和抖动说明未删字，保留在相应折叠或空状态。选区空状态原文不变。

## 边界与未测

- 遵守受限路径排除；未打开、读取或输出其目录/文件。未修改 `evidence/atlas/*.py`、faxnews、新作品/预设导入相关源码或 index.html。
- 没有接光驱、刻盘、联网下载或上传；全部使用本地夹具及现有依赖。
- 真实光驱、真实刻录和真实照片验证：**未测**。Firefox、Safari、实体触屏：**未测**。
- 两处全部 JS 回归失败及图层按钮尺寸未达标如上，不把它们记成通过。需要人决定的是图层操作采用哪一种布局。
