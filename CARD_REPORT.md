# 卡 X：编辑器画布验收报告

工作区：`D:/dp-dev/editordesk`；分支：`web/editor-desk-20261117`。

## 提交与完成内容

1. `60c2b92` — `Fix editor fit tracking and add desk view variants`
   - 新增视图跟随适应状态：进入编辑器、打开作品、换盘种、按 0 或调用适应后，每次 ResizeObserver 通知都重新适应中央操作区域。滚轮、触控板平移、双指捏合、手形拖动、键盘 1 / 加减号退出跟随；手动视图 resize 保留缩放。点击缩放数字从手动视图返回适应；跟随时点击仍可切到 100%。移除了进场后用 30 ms 定时器再测尺寸的做法，没有新增动画。
   - 提交 A/B 两版桌面、纸色/夜色共四张 256×256 PNG。桌面按 80 mm 平铺，位置与尺寸由视图盘心、px/mm 计算，缩放、平移时内外连续。
   - 盘的屏幕投影按离桌面 3 mm：偏移 `(-0.5609×3, +0.3085×3) mm`，模糊量 5 mm；纸色 `rgb(29 27 24 / .15)`，夜色 `rgb(10 17 20 / .6)`。外缘选择 **1 px 暗边**。盘孔透出桌面。以上均在 DOM / 屏幕画布层，未修改 preview、灯下颜色计算或导出算法。
   - 屏幕画布覆盖全舞台，中央区域全不透明，区域外通过独立包装层的 CSS mask 保留 35% 不透明度；快速平移/缩放时遮罩位置保持固定。面板、顶栏、底部按钮有现有纸色底，右栏夜色也有底。现有右栏玻璃投影单独放到图像下方，避免面板阴影压暗盘面。新样式限定编辑器，保留 `.ws.pv` 预览页原有布局。
   - 面板优先接收点击；外围空隙可以拖动平移和滚轮缩放，不开始新的选区或绘制。双指接管未完成手势时取消该手势，不提交额外选区。
   - 新增 `tests/test_editor_desk_browser.mjs`，这是卡片要求的浏览器回归文件。生产代码改动限于 design.js、design.css、design/editor-desk.mjs 和四张桌面图片。
2. 本报告提交 — `Document card X validation and review choices`：记录验收、切换方法、证据与限制。

## 桌面来源与切换

默认 **A**。在 `discprobe/web/home/design/editor-desk.mjs` 把唯一常量 `DESK_VARIANT = 'A'` 改为 `'B'`，刷新页面即可。两版都已提交，未替审查方作最终选择。

- A：只读取现有 `presetio/desk/desk_base_paper.webp`、`desk_base_dark.webp`。截取无物体桌面区域 `(1000,64)–(1512,576)`，缩到 256×256，减去 GaussianBlur(24) 的低频光照，微小残差限幅并在边缘平滑归零。底色取无物体、无物体阴影的下缘 `(1000,1320)–(1320,1420)` 中位数。没有带入台灯光池或场景道具。
- B：同 A 底色，固定种子 245，周期细纹叠少量噪声生成；单通道起伏不超过约 2/255。纸色底 RGB `(219,208,191)`，夜色底 `(20,30,34)`。
- 图片实际大小：A 纸色 608 B、A 夜色 897 B、B 纸色 15,879 B、B 夜色 15,101 B，均远小于 200 KB。
- 可复现生成脚本与统计保存在 `F:/dp-archive/tmp/editordesk/make_tiles.py`、`tiles.json`。

## 验收命令与结果

所有命令在本 worktree 运行。环境 `TEMP`、`TMP` 均指向 `F:/dp-archive/tmp/editordesk`，Python 使用 `-B -X utf8`；Python 缓存、浏览器配置、截图目录也定向 F 盘。

1. 最终前端遍历：用 `rg --files tests` 选取全部 `test_*.mjs`，排除禁读路径和导航测试，再运行 `node --test --test-concurrency=2 $files`。
   - **52 个文件、63 项测试通过，0 失败**。覆盖卡片指定的 editor / materials / rig / lamp / design_export / w245 测试。
   - 日志：`F:/dp-archive/tmp/editordesk/all-node.log`。
2. 导航单独运行：`node --test --test-concurrency=1 tests/test_flow_navigation_browser.mjs`。
   - **1 文件、1 项通过，0 失败**；覆盖中英文状态、双主题、历史前进后退、刷新、作品图像保留、CSP 和预览来回导航。
   - 首轮夹具本地连接中断，出现 `ERR_CONNECTION_REFUSED`，因此首轮失败。无其他测试并行的独立重跑通过，未修改导航测试或后端。首轮原因未进一步定位，不将首轮记成通过。
   - 失败日志 `navigation.log`；通过日志 `navigation-retry.log`；通过截图 `navigation-retry/`。
3. Python：`python -B -X utf8 -m pytest -n 2 -o cache_dir=F:/dp-archive/tmp/editordesk/pytest-cache --basetemp=F:/dp-archive/tmp/editordesk/pytest tests/test_editor_ops.py tests/test_editor_pose_swatches.py tests/test_editor_preview.py tests/test_design_compose_route.py`。
   - **94 项通过，0 失败，38.13 秒**。日志 `python.log`。
   - 测试自身写到仓库 evidence/editor 的两个新 JSON 已移到 F 盘 `python-evidence/`；没有把测试临时证据提交到仓库。
4. 最终样式隔离后补跑：`node --test tests/test_editor_desk_browser.mjs` 与 `node --test tests/test_editor_w245_browser.mjs`。
   - 新增浏览器检查 **30 项通过**：容器先小后大等于 fit 计算、手动缩放后 resize 保持、各个退出/恢复入口、实际双指输入、外围拖动无新选区/绘制、面板命中、纹理跟随，以及真实截图像素验证外围 35% / 中央 100% 不透明度。运行错误 0。
   - 日志 `desk-final.log`、`w245-scoped.log`；详细结果 `desk-check.json`、`w245-scoped/browser-test-*/after.json`。
   - W245 内部 **18 项检查通过**，运行错误 0；四个主题/精度组合的 preview RGBA SHA-256 均仍为：

     `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`

   - 首次相关测试发现屏幕绘制变量遗漏，修正后重跑通过；原失败日志 `target-node.log` 保留。
5. 机械检查：Impeccable detector 返回空数组 `[]`；`git diff --check` 通过。报告与包含中文的源文件另做 UTF-8、非 ASCII 字符和问号长串检查。

全量前端回归后仅进一步修正了面板投影层次和编辑器样式隔离，随后补跑上述新增画布、W245 和导航检查；未重复跑整套测试循环。

## 截图

无头 Edge `157.0.4341.60`、DPR 1；目录：`F:/dp-archive/tmp/editordesk/after/`。

文件模式：`{A|B}-{light|dark}-{1440x1000|1220x750}-{initial|overflow}.png`，共 **16 张**。initial 为刚进编辑器、整盘适应；overflow 为导入测试图后实际拖动画布，使图片/盘越出中央方框。截图测试只在本机夹具响应中替换常量以捕获 B，仓库默认仍是 A。

## 边界、清理与待审查事项

- 按约定排除禁读路径；未改 index.html、faxnews、newplan、presetio、evidence/atlas，也未改卡 U 的 editor-ui / editor-controls。纹理源图只读。
- 开始前 D 盘剩余 38.13 GB；全量测试前仍为 38.13 GB，未低于 5 GB。清理后 F 盘剩余 14.72 GB。
- 清理了本任务生成的 8 份浏览器配置和 5 个大型测试夹具，保留日志、JSON、截图及失败记录；清单见 `cleanup.json`。既有前端测试自行生成到 `.impeccable` 的截图已移到 F 盘 `generated-review/`。
- 未接光驱、未实际刻录、未上传、未下载、未推送、未合并。真实光驱/真实刻录验收未测；其他浏览器、高 DPI 与触屏设备实机未测，双指只验证了 Edge/CDP 输入。
- **需要审查方决定：选择 A 还是 B。** 两版颜色一致，A 接近原烤图的细微起伏，B 可见细纹。暗边与 35% 外围处理已按卡片允许的方案实现，最终观感请结合 16 张截图审查。
