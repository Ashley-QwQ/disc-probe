# 卡 K：网页导航和 Disc Lab 报错

工作目录：`D:/dp-dev/flownav`；分支：`dev/flow-nav`。依据 `COMMON.md`、`flow-nav.md`、两份 ISSUES、`STYLE.md`、`DESIGN.md` 完成允许范围内的修改。

## 按提交列出的工作

### `fb19045` — Fix web navigation recovery and Disc Lab error flow

- **N02**：握手失败保留核心/GUI 不兼容原因和缺失能力说明，增加重试按钮、本机服务与含口令网址的确认提示。连接错误自动等待 1、2、4 秒重试，之后保留手动重试。每次重新核对版本及必需能力，成功后恢复原页面并继续初始化；不兼容时不会绕过握手。事件监听器在现有 CSP 下工作。
- **N03**：新增 `navigation.mjs` 与 `flow-navigation.js`，主要视图使用 `#/lobby`、`#/library`、`#/newplan`、`#/design`、`#/preview` 等 URL。History API 处理浏览器后退/前进；原有左上返回及页面清理逻辑继续使用。内存保留当前对象，IndexedDB 保存表单、批次输入、原始图片所在的可移植工程文本和可保存的预览状态，刷新时恢复。保留 URL 原查询参数。快速连续返回在上一条历史尚未落定时不会叠加操作。
- **N09**：工作页期间收到状态事件时标记盘库需要更新；退出标定、预设导入完成、回到大厅或盘库时同步。同步仍按批次 ID 保留选择，不要求用户刷新。
- **N10**：确认产品 `openPreview` 没有提供 `showInFolder` 后，移除预览页这项不可达接口和控件，更新对应测试。旧 PRO、随盘文件位于禁止修改的设计页，且部分数据路径仍被使用，保留，见下文。
- **W14 / 错误**：`disclab dp --json` 保存失败子命令输出尾部，结构化错误选取最后一条诊断而不是仅提供退出码。网页从错误及任务日志识别磁盘不足，给出清理不再需要的镜像或换 `--lab` 目录再试的提示；其他错误展示最后诊断和下一步。错误条持续显示，任务结束后仍能查看最近日志。新增 `.mjs` 文件加入独立 Lab 包的打包后缀列表。
- **W14 / 分支**：当前检查盘/拍照步骤中增加“跳过检查盘、继续生成成品（L 未知）”；CLI 同样支持 `step skip-check`。必须先有有效几何，决定随新几何失效；成品生成明确使用 `--no-photo-l`。读取 DP 网页已有的直接成品刻录记录时，不再卡在检查盘步骤。没有把跳过当成测得了 L。
- **W14 / 场景调查**：当前源码及本机服务未复现旧记录的空白。两套主题中大厅 5 层图片均加载成功且尺寸非零，刻录机页图片也加载成功；见截图和限制说明。没有凭猜测改场景布局或颜色。
- 新增握手恢复、必需能力重试门槛、错误文案、浏览器历史/刷新、盘库更新、跳过检查盘及虚拟端到端测试。

### 随后的报告提交 — docs: record flow-nav card verification

提交本报告。截图、测试日志、临时实验盒和打包检查产物在 `D:/dp-dev/tmp/flownav/`，未提交到仓库；现有测试写到 worktree 的 `.impeccable/` 截图已移至该目录的 `test-artifacts/`。

## 删除清单与保留项

实际删除，仅在 `discprobe/web/home/preview.js`：

1. 顶部接口注释中的 `showInFolder?(path)`。
2. 中文“在文件夹里显示”、英文“Show in folder”字串。
3. `data-a="folder"` 条件按钮。
4. 调用 `ctx.showInFolder` 的事件分支。

对应测试 `tests/test_web_guidance.py` 从检查条件按钮改为确认接口已不存在；没有整文件删除测试。

核实后保留：

- `design.js:1323` 附近的旧右栏在 `editor` 存在时直接返回，旧 PRO 开关没有当前产品入口。但是 `S.pro` 仍用于工程读写、预览和缩略图路径；`tests/test_pastworks_browser.mjs:43` 仍验证 PRO 工程缩略图。不能连这些路径一起作为无引用代码删除。
- `design.js:221` 的 `FILES_READY=false` 关闭随盘文件入口；`S.files` 仍属于现有工程读写字段，`fileBits()` 也仍有门槛代码。
- 任务卡明确禁止修改 `design.js`、`design/`，因此上述块及其测试未删。没有修改这些路径或 `burn.js` 的任何部分；也没有修改 `evidence/atlas/*.py`。

## 验收命令与结果

环境：Windows、Python 3.13.14、Node 26.7.0、本机 Edge headless。所有测试临时目录放 D 盘，Python 使用 `-B`，pytest 使用 `-n 2`，`DISCPROBE_WORKERS=2`。没有连接真实光驱、真实刻盘或联网上传。

| 命令 / 检查 | 数字和结果 |
|---|---|
| `rg --files tests -g 'test_*.mjs' -g '!**/*blind*/**' -g '!**/*blind*'`，逐个执行 `node <file>` | 42 个文件均执行。首轮 38 通过、4 失败；修复并定向复验后 **42/42 通过**。原始 `mjs-results.json` 保留首轮结果，接受结果在 `mjs-accepted.json`。 |
| `node tests/test_flow_navigation_browser.mjs` | 最终通过，日志 `test_flow_navigation_browser.settled.log`。验证重试恢复、表单名和批次、设计图片、设计/预览后退前进及刷新、盘库深链接、工作页变更后的盘库同步、两种主题、真实 run/watch 错误 UI；CSP 和运行时错误数组均为空。刷新测试明确等待新的文档，避免对即将卸载的旧文档操作。 |
| `node tests/test_review_library_newwork.mjs` | 最终通过，日志 `test_review_library_newwork.final.log`；确认原有选盘、导入返回和动画流程。 |
| `node tests/test_motion_browser.mjs` | 最终通过，日志 `test_motion_browser.final.log`；24 组既有动效/中断检查。 |
| `node tests/test_csp_browser.mjs` | 最终通过，日志 `test_csp_browser.final.log`；8 个静态 HTML 路由及带口令手机页、Lab，0 项 CSP 违规，含桌面和手机视口。 |
| `node tests/test_gui_handshake.mjs`；`node tests/test_disclab_errors.mjs` | 最终分别 7、2 项通过；日志为各自 `.final.log`。 |
| `python -B -m pytest -n 2 disclab/tests tests/test_gui_handshake.py tests/test_web_guidance.py --basetemp=D:/dp-dev/tmp/flownav/pytest-final -q` | 首轮 **171 passed、1 failed、1 skipped、8 subtests passed**。失败是新增测试把 `t` 传给本就自行写时间戳的 `Lab.step`，已改为测试夹具直接追加带时间戳记录。原始日志 `pytest-final.log` 保留。 |
| `python -B -m pytest -n 2 disclab/tests/test_desk.py -k 'skip_check_requires or direct_final_branch' --basetemp=D:/dp-dev/tmp/flownav/pytest-skip -q` | **2 passed**；包括修正的测试及随后新增的真实核心虚拟分支测试：生成小测量镜像、测几何、跳过检查盘、生成成品、虚拟刻录；核对 sidecar `photo_l.written` 为 false。 |
| `python -B -m pytest -n 2 disclab/tests/test_desk.py tests/test_gui_handshake.py tests/test_web_guidance.py --basetemp=D:/dp-dev/tmp/flownav/pytest-verified -q` | 最终 **29 passed、8 subtests passed**，日志 `pytest-verified.log`。全部 Disc Lab 测试已在全量及定向复验中覆盖，没有重复循环跑整个套件。首轮的 1 项跳过仍保留为跳过。 |
| `python -B -m disclab.package --output D:/dp-dev/tmp/flownav/disclab.zip`，随后 `zipfile` 检查 | 生成包共 **93 个条目**；错误模块、场景 JSON、纸色和夜色底图 **4/4 项存在**。只做了包内容检查，未从此 ZIP 解压启动。 |
| impeccable `detect --json`，及 `git diff --check` | 检测器返回 2 条 warning、1 条 advisory，都是原有纸色/发光/条纹样式；按卡保持视觉不变。差异空白检查通过。 |
| 中文编码检查 | 含中文的 13 个修改/新增代码测试文件非 ASCII 数均大于 0；连续 4 个问号的段数均为 0。本报告另作同样检查。 |

## 截图

全部在 `D:/dp-dev/tmp/flownav/shots/`，共 10 张，1440×1000：

- `retry-light.png`、`retry-dark.png`：握手受控断网后的重试页。
- `back-light.png`、`back-dark.png`、`forward-light.png`、`forward-dark.png`：浏览器后退到大厅、前进恢复表单。
- `lab-desk-paper.png`、`lab-desk-dark.png`：两套主题的大厅场景。
- `lab-error-paper.png`、`lab-error-dark.png`：刻录机页磁盘空间不足错误条，含可见的跳过分支。

Lab 错误截图使用受控任务响应注入，通过产品的 run/watch 流程显示；没有把 D 盘实际写满。Python 测试另外验证了子命令诊断经过结构化响应传递。

## 没做到、拿不准和需人决定的地方

- **旧版空白场景根因未确认**：问题记录说原始截图只在聊天中，本任务没有那次现场的控制台或资源请求。当前本机 HTTP 服务的大厅与刻录机页均可显示，不能据此宣称修复了旧版本的空白原因。若原现场重现，需要该现场缺失资源/控制台信息再定位。
- **设计页遗留清理留给负责人**：由设计页负责卡决定保留工程兼容字段后怎样删除旧 PRO 和随盘文件控件。本卡未越过禁止修改边界。
- 刷新恢复依赖浏览器允许 IndexedDB 和异步快照已写入；它不是正式“保存作品”的替代。运行中的生成任务刷新后不会自动重放生成；缺少作品/ISO 上下文的预览或刻录深链接会回到可操作的设计台，不会自动生成或刻录。真实长任务跨刷新及刻后恢复未测，且未修改卡 J 的流程。
- 未测真实光驱、真实磁盘满、非 Edge 浏览器和此新 ZIP 的解压启动。没有改变审美方案，无其他需要本卡先停下等待决定的问题。

提交边界：只在 `dev/flow-nav` 提交，未推送、未合并、未切换分支、未修改其他 worktree。
