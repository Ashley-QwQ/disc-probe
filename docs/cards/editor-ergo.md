# 卡 U 第二轮交付报告

分支：`web/editor-ergo-20261117`。本节是当前结果；下面保留第一轮记录，第一轮的图层尺寸待定与两项失败不代表当前状态。

## 按提交说明

1. `f65e761`：第一轮颜色页、影调、说明折叠和控件调整，详见历史记录。
2. `16567f1`：按第二轮明确指令执行 `git merge dev/1.0.0`，合入 `c76a92f`。合并只带入审查方修正的 `tests/test_preset_geometry.mjs` 两行变更，无冲突；未自行修改这条断言。
3. 本报告与第二轮实现同次提交，标题 `Keep colour fill visible and expand accessible layer actions`：
   - 当前材质的小色块、名字和右侧填充按钮放入同一 sticky 行，`top: 0`，使用不透明 `var(--paper)` 底色；机位摘要、填到及图案填充分段按钮照常滚走。面板仍只有一层滚动，填充按钮仍只有一个，行为不变。
   - 图层行保留缩略图、名称、44×44 px 隐藏/显示按钮和三点“更多”按钮；更多的 aria-label 为“图层操作” / “Layer actions”。下方展开锁定、上移、下移、删除四个 44×44 px 按钮，同一时间只展开一行。
   - 再点更多或按 Esc 收起；Esc 把焦点交回原行的更多按钮，优先关闭操作区，不顺带取消选区或退出编辑器。展开状态只存于会话 UI 状态，不进作品文件或撤销栈。
   - 锁定时名称旁显示不可点击的小锁（“已锁定” / “Locked”），收起后也可见。保留原来的锁定保护、图层顺序、删除、快捷键及撤销/重做。
   - 图层按钮使用原生 Enter / 空格激活；避免编辑器的空格临时手形快捷键抢走这些按钮的空格事件，画布上的临时手形行为照旧。

本轮实现只修改 `design.js`、`design.css`、`design/editor-controls.mjs` 及本报告。未改画布布局、顶栏、下一步、画布下视图切换、作品格式或材质数据；未推送，未将工作分支合回其他分支。

## 第二轮验收

所有本轮脚本、日志、截图、浏览器配置和测试产物位于 `F:/dp-archive/tmp/editorergo/` 下。以下路径相对此目录。

### 导航单独验收

```text
node --test --test-concurrency=1 tests/test_flow_navigation_browser.mjs
```

- 刚合并、尚未修改第二轮界面时：**1 通过、0 失败，34.66 秒**，日志 `round2/flow-merged.log`。
- 第二轮界面完成后再单独验收：**1 通过、0 失败，40.75 秒**，日志 `round2/flow-final.log`。
- 覆盖动态载入设计页、重试恢复、浏览器前进/后退、图片及表单保留、刷新、资料库深链接、纸色和夜色，以及 CSP。两次均无断言失败；本轮未复现第一轮的连接被拒绝，不能据此追认第一轮通过，也未把旧失败归因为设计页动态模块错误。

### 新增浏览器验收与截图

```text
node F:/dp-archive/tmp/editorergo/round2/cap_after.mjs
```

**22 项检查通过、0 个运行时异常**，无头 Edge **157.0.4341.60**，DPR 1。原本地色条夹具增加第二图层，以验证同一时间只展开一行；不访问后端或光驱。

- 1440×1000 和 1024×768，纸色/夜色共四组；每组各拍颜色页顶部、色板中段 sticky 行、更多展开、锁定后收起四张，共 **16 张**。
- 位置：`after/round2/shots/{1440-light,1440-dark,1024-light,1024-dark}/`。
- 重点截图：`02-palette-middle-sticky.png`、`03-layer-more-expanded.png`；完整测量和检查名见 `after/round2/acceptance.json`。
- 滚动至 `scrollTop=650` 后测量 sticky 行停在滚动区顶部，当前材质和唯一填充按钮同排可见，背景色与面板一致且不透明；机位摘要和填到已滚出视野。
- 用原生键盘事件验证 Enter / 空格打开更多、Esc 收起并恢复焦点；验证展开不新增撤销记录、仅一行展开、锁定禁用受保护操作、隐藏/显示撤销重做、排序/删除/Alt+方向键撤销，以及 sticky 填充按钮的材质和目标不变。
- 新增文案仅“图层操作” / “Layer actions”与“已锁定” / “Locked”；更多用三个 SVG 圆点，无新增动画或弹窗。

| 图层按钮（实际点击元素） | 1440×1000 纸色/夜色 | 1024×768 纸色/夜色 |
| --- | --- | --- |
| 隐藏/显示、更多（收起时） | 各 44×44 px | 各 44×44 px |
| 锁定、上移、下移、删除（展开时） | 各 44×44 px | 各 44×44 px |
| 图层行实际可用宽度 | 262 px | 222 px |

所有测得的按钮均在图层行边界内，无点击区域重叠。第一轮的 24×32 px 不达标项已解决，不再需要选择布局。

### 最终回归

```text
python -B -X utf8 F:/dp-archive/tmp/editorergo/round2/run_node_checks.py
```

最终全量 JS 清单共 **51 个 test_*.mjs 文件、62 项测试**，排除受限路径。49 个文件以并发 2 运行；另外两个会向相对 cwd 写截图的原夹具以 F 盘为 cwd 单独运行。原始整批结果 **59 通过、3 失败**，完整命令及退出码在 `round2/node-results.json`，不得记为整批全过。

失败项的单独重验使用 `node --test --test-concurrency=1 <单个测试文件>`：

| 测试 | 整批结果 | 单独重验 / 对照 |
| --- | --- | --- |
| test_flow_navigation_browser.mjs | 本地服务连接被拒绝，80.19 秒后在新作品页刷新恢复处超时 | **通过**，35.39 秒；加上先前两次单独通过，本轮共三次单独通过 |
| test_review_library_newwork.mjs | library can return another chosen batch 断言失败 | **通过**，12.59 秒 |
| test_presetio_browser.mjs | iframe 结果仍是 PENDING | 单独重验仍失败；换回合并点 16567f1 的三个 UI 文件进行对照，也在同一 PENDING 断言失败 |

单独重验见 `round2/recheck-results.json` 和 `round2/test_*-recheck.log`。导航整批失败时，字体、未改的 flow-navigation.js 和本轮 design.js 等同时出现 `ERR_CONNECTION_REFUSED`；这是资源请求无法建立连接，并非 JavaScript 语法解析错误。多次完整单独通过及编辑器夹具成功载入，未发现本轮引入的动态模块载入缺陷；并发时本地服务连接中断的根因仍未确定，未改卡外服务或前端。

预设页对照过程只临时使用三个已授权 UI 文件的合并点内容，完成后按原始字节恢复，并校验 SHA-256，见 `round2/presetio-base-comparison.json`。合并点对照退出码 1，证据 `round2/presetio-at-merge-point.log`；说明此 PENDING 失败不由第二轮改动引入。未修改 presetio 页面、夹具或断言，也未延长它的 6000 ms 虚拟时间预算来制造通过。

在最后的图层删除展开状态清理完成后，另跑卡内原命令：

```text
node --test tests/test_editor.mjs tests/test_editor_materials.mjs tests/test_editor_rig.mjs tests/test_editor_lamp.mjs tests/test_design_export.mjs tests/test_editor_w245_browser.mjs
```

**6/6 通过、0 失败，16.60 秒**，日志 `round2/editor-final.log`；W245 的 **18 项**行为检查通过、0 个运行时异常，四组 20/10 µm 纸色/夜色预览哈希保持第一轮记录中的值。preset_geometry.mjs 在本轮全量 JS 中通过。

Python：

```text
python -B -X utf8 -m pytest -p redirect_evidence -n 2 -o cache_dir=F:/dp-archive/tmp/editorergo/round2/pytest-cache --basetemp=F:/dp-archive/tmp/editorergo/round2/pytest-run <test_editor_*.py 与 test_design_compose_route.py 的显式清单>
```

**94 passed，32.22 秒**，日志 `round2/pytest.log`。为遵守临时文件只用 F 盘，外置 `round2/redirect_evidence.py` 仅将两个原测试硬编码的 evidence JSON 写入位置重定向到 `round2/python-evidence/`；不改变断言、被测计算或核心输出，仓库测试文件未改。

`impeccable detect --json` 对三个改动 UI 文件的输出为 `[]`；`git diff --check` 通过。含中文的改动 JS 和报告均经 UTF-8 非 ASCII 及连续问号检查；截图尺寸也检查为 1440×1000 / 1024×768。

开跑前 D / F 可用约 40.65 / 20.24 GB，最后一次全部 JS 回归前 D / F 约 39.63 / 19.35 GB；均未触及 D 盘 5 GB 停止线。成功测试的临时大文件和浏览器配置在结束时清理，只保留日志、截图、JSON 证据及必要失败现场。未接光驱、刻盘、联网下载或上传；搜索排除受限路径，未打开、读取或列出其中的文件/目录。

## 当前限制

实体触屏、Firefox、Safari、真实光驱/刻录及真实照片：**未测**。第一轮 1024×768 的短窗口工具栏滚动方式继续沿用，本轮不改变画布布局。整批 JS 的三项失败、其中两项单独通过及预设夹具合并点对照仍失败，均如实保留；没有把整批结果写成全过。卡内界面要求已完成，没有需要审查人另选方案的布局遗留项。

---

# 第一轮记录（f65e761，历史结果）

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
