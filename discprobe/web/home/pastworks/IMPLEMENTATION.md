# 往期作品 / Past works

## 实现范围

这是现有桌面世界的延伸；`PRODUCT.md`、`DESIGN.md`、`index.html` 的全局变量及玻璃说明保持原样。`pastworks.js` / `.css` 提供可滚动的报告纸、4 / 3 / 2 列档案网格和作品聚焦视图。每格按信封背面、正面、盘面的顺序叠图，盘在信封上；第一格始终是虚线空盘“新作品”。作品格先放大移到左侧，再由“打开作品”进入设计页；窄屏改为上图下文。详情目前只有名称和日期。

沿用纸色 / 墨色、墨与铜、Archivo、4 px 控件圆角和固定角落导航。报告纸采用现有 `paper_<theme>.webp` 的 `120 fill / 46px / 23px stretch` 边框及短阴影；打开按钮用 `--glass-edge` / `--glass-desk`，页头用 `--glass-desk-drop`。只有盘面承载作品的颜色。

墨色报告纸与聚焦区局部使用白墨 `--ink: #fff`、`--ink-2: var(--ink)`，以字重和字号保留层级。提供的纸面内容区域最亮像素为 RGB (119, 119, 108)，白字对比度约 4.526:1；这是本页对真实纸纹的可读性适配，未修改图片或全局主题变量。

## 入口与退出

`lobby.js` 在原生 `#lobby-open` 按钮的捕获阶段接管点击，阻止旧文件选择器的冒泡监听器；物体热点、印刷标签和键盘都汇入同一按钮。悬停 / 聚焦预加载模块。首次推入文件盒 400 ms、下落 1000 ms、刹停 500 ms；以后合计 600 ms。文件盒开口取热点上部的近似框，并非新增的美术定位数据。

下落、刹停和静态滚动共用一个相机坐标与远 / 中 / 近三组信封，速度为 .16 / .43 / .86；重复图层首尾衔接，逐帧只更新 transform。返回 / Esc 先取消作品聚焦，再沿原路径倒放回大厅并恢复入口焦点；入场中可直接反向，退出中再次返回会结束退出。点击或 Enter 跳过过场。页面动效关闭、API 减弱动效或系统减弱动效均直接切换。

## 真实数据、演示与降级

- 正式入口读取 `design.recentPlans()` 的本页会话作品，以 `design.start(api, { plan, fly: false })` 打开；新作品走 `api.newWork`，缺失时点击大厅原入口。这里没有新增磁盘扫描、跨会话档案或持久化接口。
- `design.planThumbnail(plan, px)` 重用设计页的图层栅格化、色调处理、媒体有效半径及 PRO 外观叠层；辅助函数接收显式 plan / layers，避免切换当前编辑作品。256 px 小图按作品对象和渲染输入缓存；滚动不重新投影。
- 两主题共 20 张 `tumble_*.webp` 是已提供的真实美术资源，本任务未改动。单张加载失败才退回现有正面信封图；盘面生成失败显示“缩略图不可用”，不替造作品图。
- `pastworks-preview.html` 使用明确标注的假作品、假日期和示例盘面，展示两主题、空档案与重播；其打开 / 新建回调只展示演示结果。正式入口不注入这些数据。
- 当前会话计划没有日期，显示“日期未知”，最近优先保留 `recentPlans()` 的原有稳定顺序。有有效时间字段时按时间倒序；名称排序以中文开头者在前，使用 `Intl.Collator("zh-u-co-pinyin")`，相同值保持原序。没有作品时仍保留新作品入口和一句说明。

## 验证与留待后续

已保存的验证记录：`review/node-tests.txt`（16 个 Node 测试文件，包括真实图片、1440 / 390 px、主题、排序、缓存 / PRO、动效、返回焦点及大厅旧选择器抑制）与 `review/pytest.txt`（234 passed、1 skipped、46 subtests passed）。这两份完整运行记录早于局部白墨修正；修正后已再次通过两种宽度和真实大厅入口的浏览器测试。截图 `review/pastworks-1440-paper.png`、`review/pastworks-390-dark.png` 已在图片解码后刷新。独立对比度复核确认上述最亮像素及 4.526:1 比值、两张截图有效，修正无可见回归，结论为可交付；该结论仅覆盖本次对比度修正，不代表整页无条件审定。

按任务卡留待后续的是完整详情内容；持久化档案与真实日期来源属于现有数据层的限制。未将既有系统漂移写成新规则：`DESIGN.md` 的绿色 good / 独立 warn 与当前 `index.html` 的墨色 / 铜色状态变量不同，且未完整记录现有玻璃阴影层次；既有 LobbyHand 和机械扫描的配色 / Archivo 警告不在本次系统修订范围。未改写设计文档或 `.impeccable` 元数据。

## English

This extends the existing visual world without changing its global tokens or design records. A scrolling report sheet holds top-down envelopes with each work's disc above the back and front images. The first cell creates a new work. Selecting a work enlarges it beside its name and date; “Open work” enters the editor. The layout uses four, three or two columns, with a vertical focus view on small screens.

Dark archive paper and its focus view use local white primary and secondary ink for readability: approximately 4.526:1 against the supplied texture's lightest content pixel, RGB (119, 119, 108). Size and weight carry hierarchy. This adaptation leaves the art and global theme unchanged.

The lobby's existing file-box button is intercepted in capture phase, including its label and keyboard routes, suppressing the old picker. Entry takes 400 / 1000 / 500 ms initially and 600 ms on repeat visits. The push uses an estimated opening within the existing hotspot. One camera drives the fall and the three repeating depth groups, so arrival shares the resting background. Back / Esc unfocuses first, then reverses the flight and restores lobby focus. Click / Enter skips; reduced motion cuts directly.

Production reads session-only `design.recentPlans()`, opens through `design.start(api, { plan, fly: false })`, and creates through `api.newWork` or the original lobby action. Cached thumbnails reuse editor rasterisation, tone, media ranges and PRO overlays without selecting an editor plan. The 20 supplied tumble images are real and unchanged; failed images fall back to the existing envelope front, while failed thumbnails are explicitly unavailable. The standalone preview alone supplies sample plans, dates, art and demonstration callbacks.

Session plans currently carry no dates: the UI says “Date unknown” and retains their stable recent order. Valid timestamps sort newest first; name sorting uses Chinese pinyin with stable ties. Fuller details remain deferred as requested; persistence and a real date source are existing data limitations. Saved full-suite logs predate the local white-ink correction; targeted browser checks passed again afterward and screenshots were refreshed after decoding. Independent re-review confirmed the pixel scan, contrast ratio and valid captures, found no visible regression, and returned “ship” for the contrast correction alone. This does not imply whole-surface approval. Existing design-record drift and inherited detector warnings are recorded rather than promoted into rules or repaired here.
