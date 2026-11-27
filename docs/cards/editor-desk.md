# 卡 X 第二轮验收报告

工作区 `D:/dp-dev/editordesk`，分支 `web/editor-desk-20261117`。本报告描述第二轮最终状态；第一轮日志和截图继续保留在原目录。

## 按提交列出的改动

- `60c2b92`：第一轮实现初始缩放跟随、A/B 桌面、盘的屏幕投影、全舞台半透明画布和浏览器检查。
- `5983819`：第一轮验收报告。
- 本轮提交 `Select wood desk and fade canvas before header and footer`：桌面默认定为 B；移除第一轮新增的顶栏、底部整宽背景和作品标题背景；给外围画布添加上下 48 px 渐隐；更新浏览器检查、重拍截图并更新本报告。

## 第二轮行为

- **默认 B（木纹）**：`discprobe/web/home/design/editor-desk.mjs` 中 `DESK_VARIANT = 'B'`。**保留 A 分支及两张 A 图片**，仅作历史对照；若需对照，把该常量改为 `'A'` 后刷新即可。B 纸色/夜色 PNG 分别为 15,879 / 15,101 字节，仍低于单张 200 KB。没有重生成纹理。
- 顶栏 DP 字标、图标和作品标题，以及底部“下一步”所在行，恢复透明背景，直接放在桌面上；左右面板的不透明底保持。
- 使用现有 canvas 包装层的两层 CSS linear-gradient mask：中央方框保持 100%，方框外中段约 35%；在靠近顶栏/底部行的 48 px 内由 35% 线性降至 0。上下零点沿用 `--top - 16px`、`100% - --foot` 对齐现有栏位，没有增加动画或计时器。
- **右栏左侧玻璃投影带保持原样**：`.ed-panel-shadow`、玻璃阴影变量与层次均未修改。
- 本轮生产改动仅 `design.css`、`design/editor-desk.mjs`；没有改 design.js 的编辑逻辑、适应跟随、指针事件、撤销、导出或灯下颜色计算，也没有改卡 U 的标签、sticky 填充行和图层更多按钮。

## 验收

运行环境：所有 `TEMP`、`TMP`、浏览器配置与测试缓存均放在 `F:/dp-archive/tmp/editordesk/round2/`。下述日志文件均相对此目录。

1. 全部非导航前端测试：先用 `rg --files tests` 选择 `test_*.mjs`，排除禁读路径与导航测试，再执行 `node --test --test-concurrency=2 $files`。共 **52 个文件、63 项测试，首轮 60 通过 / 3 失败**；日志 `all-node.log`。卡片指定的 editor、materials、rig、lamp、design_export、w245 均通过。
2. 只重跑上述失败文件：`node --test --test-concurrency=1 tests/test_csp_browser.mjs tests/test_pastworks_browser.mjs tests/test_presetio_browser.mjs`。CSP 与预设页通过；往期作品补跑因我指定的截图目录尚未创建而报 ENOENT，建立目录后执行 `node --test --test-concurrency=1 tests/test_pastworks_browser.mjs`，**1 项通过，0 失败**。三项最终均通过，日志 `retry-node.log`、`pastworks-retry.log`。全量首轮分别为本机 `ECONNREFUSED`、浏览器关闭时 unsettled top-level await、预设页返回 PENDING。未修改这三项测试及其业务代码；未定位首轮偶发原因，失败记录保留，不记作首轮全绿。没有重复运行整套前端测试。
3. 导航单独、且无其他测试并行运行：`node --test --test-concurrency=1 tests/test_flow_navigation_browser.mjs`。首轮进入盘库深链接时夹具报 `ERR_CONNECTION_REFUSED` 并超时；相同命令独立重跑 **1 文件 / 1 项通过，0 失败**。失败日志 `navigation.log`；通过日志 `navigation-retry.log`，截图 `navigation-retry/`。未修改导航测试或后端。
4. Python：`python -B -X utf8 -m pytest -n 2 -o cache_dir=F:/dp-archive/tmp/editordesk/round2/pytest-cache --basetemp=F:/dp-archive/tmp/editordesk/round2/pytest tests/test_editor_ops.py tests/test_editor_pose_swatches.py tests/test_editor_preview.py tests/test_design_compose_route.py`，**94 项通过，0 失败，46.99 秒**；日志 `python.log`。
5. 新增/更新画布检查：`node --test tests/test_editor_desk_browser.mjs`，内部 **30 项通过、运行错误 0**，并在全量前端回归中再次通过；日志 `desk.log`，详细结果 `desk-check.json`。保留先小后大适应、用户缩放后 resize 不改缩放、双指与外围输入检查；新增默认 B、透明栏位与真实截图渐隐像素检查。
6. W245 内部 **18 项通过、运行错误 0**；纸色/夜色、20/10 µm 四组 preview RGBA SHA-256 均保持：

   `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`

   结果文件 `w245/browser-test-*/after.json`。本轮没有修改工具或测试中的预览哈希预期。
7. Impeccable detector 返回 `[]`，`git diff --check` 通过；中文报告经 UTF-8、非 ASCII 字符与问号长串检查。

渐隐像素实测：临时用纯黑画布覆盖 RGB 200 的灰色桌面，隐藏界面，仅测合成结果：中央 RGB 0（100%）；外围中段 RGB 130（35%）；上下栏位 RGB 200（0%）；两端渐隐中点 RGB 165（17.5%）。结果记录在 `desk-check.json` 的 `opacity` 字段。渐隐仅作用于屏幕包装层，桌面纹理仍连续显示。

## 截图与清理

- 无头 Edge 157.0.4341.60、DPR 1；截图位于 **`F:/dp-archive/tmp/editordesk/after2/`**。
- 命名：`B-{light|dark}-{1440x1000|1220x750}-{initial|overflow}.png`，共 **8 张**；initial 为刚进入时整盘适应，overflow 为导入测试图后实际平移到超出中央方框。截图直接使用仓库的 B 默认值，不在夹具中替换常量。已检查纸色、夜色与两种尺寸。
- 测试自行生成到仓库 evidence/editor 的 JSON 和 `.impeccable` 截图移至本轮 F 盘 `python-evidence/`、`generated-review/`；浏览器配置与大型测试夹具清理清单为 `cleanup.json`。保留日志、截图及失败记录。
- 开始前 D 盘 38.12 GB / F 盘 14.58 GB；全量测试前已检查 D 盘仍高于 5 GB。

## 边界与未测项

递归搜索持续排除禁读路径；未改 index.html、faxnews、newplan、presetio、evidence/atlas 或其他 worktree。未接光驱、未实际刻录、未下载、未上传、未推送、未合并。真实硬件、其他浏览器、高 DPI 与触屏实机未测。桌面选择已经确定为 B，本轮没有待审查方选择的 A/B 问题。
