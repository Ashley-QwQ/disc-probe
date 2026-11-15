# 卡 A：品牌收尾

工作目录：`D:/dp-dev/brand`；分支：`dev/brand-1201`；基点：`56f2cf7`。

## 按提交列出改动

本报告与全部实现放在同一次提交：`feat(brand): bundle family icons and Chinese title font`。

- `discprobe/web/brand/` 入库 24 个 SVG、生成器及用途说明。24 个 SVG 与 `D:/disc-probe/art/brand/` 原稿逐字节一致；生成器只调整搬迁后的 Archivo 路径及命令示例。临时目录重建的 24 个 SVG 也与原稿一致。`.gitattributes` 固定 SVG、STYLE 和 Adobe 许可文件为原字节，避免 Windows 换行转换；SVG 原稿 CRLF 保留，空白检查将行尾 CR 正确识别为 CRLF。
- `tools/export_brand_icons.py` 使用已安装 Edge 渲染、Pillow 编码，导出三产品各 7 个文件：favicon（16/32/48）、Apple 图标（180）、PNG（64/128/256/512）、Windows ICO（16/24/32/48/64/128/256）。16/24 使用 icon-small，32 及以上使用 icon；默认 ink。Lab 独立静态目录同步 7 个副本。
- 所有现有 HTML 页面接入对应产品的 favicon / Apple 图标；Probe、手机及预览页用 probe，Lab 用 lab。手机端只新增四个确切的匿名静态资源路径，未放开目录或桌面 API。
- 原字节复制 `D:/disc-probe/STYLE.md`；DESIGN 只增加开头的优先级说明，其余内容不变。
- 新增标题子集构建脚本、woff2、Adobe OFL 许可、字体说明及标题专用 CSS。保留原有颜色、布局和动画声明，正文原字体栈不变，标题拉丁字母与数字仍优先 Archivo。Lab 独立目录带相同的字体/CSS/许可副本。
- Windows 文件清单和 sdist 加入 STYLE / DESIGN；现有目录收集机制带入品牌资源和字体。release manifest 新增逐文件 `brand_assets` 大小与 SHA256；Lab 独立打包清单补上 `.ico` / `.png`。打包及相关可移植性测试的递归遍历排除 COMMON 指定禁入路径。
- 新增字符覆盖、图标尺寸、手机静态资源访问、真实 wheel/sdist/ZIP 内容和 Edge 实际字形测试。

## 字体来源与体积

唯一下载来源：[Adobe 官方 source-han-sans 2.005R 发布文件](https://github.com/adobe-fonts/source-han-sans/releases/download/2.005R/19_SourceHanSansCN.zip)，下载留在 `D:/dp-dev/tmp/brand/19_SourceHanSansCN.zip`，只提取 `SubsetOTF/CN/SourceHanSansCN-Heavy.otf` 和 `LICENSE.txt`。

- ZIP SHA256：`3a769d1b082ebd813cdb4c06ea57d29b340bce548edcc8e61976b78ca28e6236`。
- 输入 OTF SHA256：`88c749b0a54a0800124ded6544e399302ed224aa49992ea364b88769f825c54c`，脚本锁定此输入。
- 扫描范围为 `discprobe/web`、`disclab/web` 内所有 `.html` / `.js` / `.mjs`，目录递归提前排除禁入路径。收集汉字、显式中文标点，加 Python `gb2312` 编码表生成的一级汉字 3755 个；不纳入拉丁字母和数字。
- 最终 **3807 个 Unicode 字符 = 3759 个汉字 + 48 个标点**；当前页面/JS 所需字符集合为 834 个，缺字 **0**。
- `SourceHanSansSC-Heavy-subset.woff2` 每份 **776236 字节（约 758.0 KiB）**；SHA256：`1c4b6be716109ba35a710774e1727e52fd00527e9384a330c87e2328b96ee9a8`。
- 原字体字重 900。OFL 保留字体名 `Source`，因此修改后的内部家族名为 `Disc Title SC`、PostScript 名为 `DiscTitleSC-Heavy`；输出文件名按卡片要求保留，来源与许可未改。
- 全部 Windows SOURCE 变更按 ZIP_DEFLATED 逐项比较新旧压缩贡献（含文件名及 ZIP 头），估计 **full-win64 ZIP 增加 961015 字节，约 0.92 MiB**。这是同一运行时条件下的增量估算，未实际重建完整 Windows 包；Lab 副本在独立 Lab ZIP 中，不计入 full-win64。

## 验收命令与数字

所有临时、下载与验收输出均在 D 盘；测试环境设置 `TEMP=TMP=D:/dp-dev/tmp/brand`、`PYTHONDONTWRITEBYTECODE=1`，pytest 使用 `-n 2`。

1. `python -X utf8 -B -m pytest -n 2 tests/test_brand_assets.py tests/test_release_packaging.py tests/test_webui.py tests/test_webui_catalog.py tests/test_webui_recovery.py disclab/tests/test_interface.py disclab/tests/test_package.py --basetemp D:/dp-dev/tmp/brand/pytest-final -q`
   - **145 passed，42 subtests passed，0 failed**，40.94 秒。
   - 包含真实小型 wheel、sdist、品牌 ZIP 和完整独立 Lab ZIP 的文件字节检查；验证手机匿名加载四个新资源成功、受保护路径仍返回 403。
   - 首轮 133 passed / 1 failed：Lab 可移植性检查发现新字体 README 的本机路径，改成通用路径后最终通过。
2. `python -X utf8 -B D:/dp-dev/tmp/brand/run_nodes.py`
   - 顺序运行 `tests/test_*.mjs` 全部 **36 个文件，36 PASS，0 FAIL**，包括新增 Edge 字形测试及现有网页测试。
   - 每项命令为 `node tests/<文件名>.mjs`；逐项日志及汇总在 `D:/dp-dev/tmp/brand/node-results/`、`summary.json`。现有测试写出的辅助 PNG 已收集到 `D:/dp-dev/tmp/brand/legacy-test-shots/`。
3. `$env:BRAND_SCREENSHOTS='D:/dp-dev/tmp/brand/shots'; node tests/test_brand_browser.mjs`
   - **PASS**，3 个视口均验证中文标题实际字形来自内嵌 `Disc Title SC`，拉丁字形来自 Archivo，正文字体栈不含新标题字体；favicon / Apple 图标 HTTP 200。
   - 使用本机 HTTP 静态测试服务与合成 API 数据，home 为 `?mock`，phone 配置为测试数据；无光驱访问。证据在 `D:/dp-dev/tmp/brand/shots/font-evidence.json`，使用 CDP `CSS.getPlatformFontsForNode`，并非仅检查 CSS 字符串。
   - 已查看三张截图：
     - `D:/dp-dev/tmp/brand/shots/home-paper.png`（1360×1000）
     - `D:/dp-dev/tmp/brand/shots/home-ink.png`（1360×1000）
     - `D:/dp-dev/tmp/brand/shots/phone.png`（390×844）
4. `python -X utf8 -B D:/dp-dev/tmp/brand/audit.py`
   - 24/24 SVG 原稿字节一致；迁移后的生成器重建 24/24 一致；STYLE 原字节一致；DESIGN 新增行之外的内容一致（与 Git blob 比较时归一化 CRLF）。
   - 重跑 `tools/export_brand_icons.py` 与 `tools/subset_title_font.py`，28 份图标和 2 份字体，共 **30 个文件 SHA256 全部不变**。
   - 结果、每个 SVG 和导出物的哈希、ZIP 增量明细在 `D:/dp-dev/tmp/brand/audit.json`。
5. `git diff --check`：**通过**。提交前检查中文文件：非 ASCII 字符数大于 0、无连续问号乱码；提交暂存区再核对 24 SVG 和 STYLE 原字节。

构建环境：Python 3.13.14、Node 26.7.0、Edge 157.0.4341.60、fontTools 4.66.0、Pillow 12.3.0、Brotli 1.2.0；图标的确定性针对同一 Edge / Pillow 版本，字体针对同一 fontTools / Brotli 版本。

## 未测、边界及需要人决定的事项

- 仓库内没有 Disc Neo 网页：已交付 neo SVG、PNG、favicon、Apple 及 Windows ICO，未来 Neo 网页应接入 `neo/`；没有修改外部 Neo 目录或其他 worktree。
- 完整 `tools/release.py` 发布演练、full-win64 整包重建、Windows 快捷方式关联以及真实手机 / Apple 加到主屏幕行为：**未测**。本次没有推送、合并、刻盘或上传。
- 保留首页地毯原有 LobbyHand 手写问候，它原先不属于 Archivo 标题；字体比较样稿 `samples.html` 保留可选字体的原行为，只接入图标。
- 未做审美调整。impeccable 上下文/机械检测启动器未运行，避免其可能自动下载卡片未授权来源；本次使用现有设计资料、源文件差异和 Edge 截图/实际字形证据验收。
- 需要人决定的问题：**无阻塞项**。字体子集未来改界面文字时由覆盖测试检查，缺字需重跑子集脚本。


## 卡 A2：标题中英混排对齐（2026-11-15 追加）

### 按提交列出的改动

本节与 A2 实现一起提交：`fix(brand): stabilize mixed title font metrics`，接在品牌卡提交 `9bb5f00` 后。

- 新增 `tools/align_title_fonts.py`，读取实际字体的 `head` / `hhea` / `OS/2`，用 fontTools 实例化 Archivo 可变字体，再生成 Probe / Lab 相同的 `titles.css`。可用 `--check` 验证可重跑结果；`--report` 输出输入字体 SHA256、原始度量、校准语料和所有比例。不下载、不复制 Windows 字体。
- 运行时仅改两份标题 CSS：新增 `Archivo Title` 别名，避免覆盖正文的 Archivo；标题仍使用原有选择器和 `--font` / `font-family` 声明。标题的字号、字重、字宽、字距、line-height，以及页面的正文声明、颜色、布局文件均未改。字体二进制、图标、STYLE / DESIGN 均未改。
- 正式中文与拉丁字形按 x-height / em 比例协调，并统一有效升部、降部和行间距。Windows 回退分别使用 `local("Arial Black")` 和 `local("Microsoft YaHei UI Bold")`；Unicode 范围来自实际 cmap，拉丁回退不会抢占汉字。
- 拉丁回退按现有标题字宽 100 / 105 / 108 / 110 / 112 / 115 / 118 / 120 / 122 / 125% 分别校准，并补字体最窄端 62%。每档按 Archivo 800 的固定语料总 advance / Arial Black 同语料总 advance 计算，不从截图反推百分比。中文字宽校准检查全部 3759 个已覆盖汉字均为一 em。
- 新增三态比较夹具、改前 CSS 声明快照及 Edge 无头测试；另加“改前回退”控制组。测试确认字体文件实际被屏蔽、实际平台字形、标题盒子、基线与字宽；现有品牌 Python 测试增加生成可复现及标题范围检查。字体说明补充重建方式和局限。

### 指南、度量和选择依据

已在 `D:/dp-dev/tmp/mwg` 执行并读取：

```text
npx --no-install modern-web-guidance retrieve visually-stable-mixed-fonts
npx --no-install modern-web-guidance retrieve visually-stable-font-fallbacks
```

采用第二篇的手工 `@font-face` 描述符策略，同时处理不依赖 `font-size-adjust` 的场景。没有再叠加 `font-size-adjust: from-font` 或固定 aspect 值：这会抵消按 advance 计算的 `size-adjust`，参见 [CSS Fonts 5 工作草案的交互说明](https://drafts.csswg.org/css-fonts-5/#font-size-adjust-prop)。当前浏览器验收为 Edge 157.0.4341.60。

| 字体 | UPM | hhea 升部 / 降部 / gap | OS/2 typo 升部 / 降部 / gap | sxHeight / capHeight |
| --- | ---: | --- | --- | --- |
| Archivo | 1000 | 878 / -210 / 0 | 878 / -210 / 0 | 526 / 686 |
| Disc Title SC Heavy | 1000 | 1160 / -288 / 0 | 880 / -120 / 0 | 543 / 733 |
| Arial Black | 2048 | 2254 / -634 / 0 | 1466 / -434 / 291 | 1062 / 1466 |
| Microsoft YaHei UI Bold（TTC index 1） | 2048 | 2080 / -521 / 0 | 1663 / -519 / 9 | 1106 / 1549 |

Archivo 的 `USE_TYPO_METRICS` 已置位，typo 与 hhea 一致。因此共同目标为升部 **0.878 em**、降部 **0.210 em**、gap **0**。思源的缩放为 `(526/1000)/(543/1000) = 96.869245%`；思源与雅黑回退均保留接近原有的汉字大小。由于 CSS 的 size-adjust 也缩放 override，三个 override 均为 `目标 em / 缩放倍率 × 100%`。

| face / 参考字宽 | size-adjust | ascent-override | descent-override | line-gap-override |
| --- | ---: | ---: | ---: | ---: |
| Archivo Title | 100.000000% | 87.800000% | 21.000000% | 0% |
| Disc Title SC / SC Fallback | 96.869245% | 90.637643% | 21.678707% | 0% |
| Latin Fallback，118% | 108.065237% | 81.247219% | 19.432706% | 0% |

固定 ASCII 校准语料为 `DISC-PROBE Disc Probe Disc Lab Disc Neo DVD-R CD-R BD 0123456789 16x`。118% 时 Archivo 总 advance 是 **44.674 em**，Arial Black 为 **41.33984375 em**。脚本按字体实际 hmtx 计算；真实浏览器的 kerning / shaping 残差另行测量。所有字体的输入哈希、11 档字宽比例在 `D:/dp-dev/tmp/brand/mixed/font-metrics.json`。

第一轮检查发现仅用 118% 比例会使 100% 字宽的样例偏差变大，已一次补齐各档参数。审美取舍没有扩大到字体替换或页面重排。

### 三态盒子与基线实测（px）

以下数值来自最终 `measurements.json`，不是 CSS 推算。夹具使用同一组 6 个标题、800 字重，每档固定同一视口和原有角色参数。盒子为 `width:max-content` 标题的 DOMRect；每格为 **宽 × 高；中英基线差**，保留两位小数。基线差是同一行汉字 run 与拉丁 run 的零尺寸 inline-block baseline 标记 y 坐标之差；纯中文 / 纯拉丁没有中英对，记 `—`。

改前状态加载 `9bb5f00` 的标题声明，已逐条核对与快照一致。三态分别为：屏蔽 `.woff2/.ttf/.otf` 的新回退、修改后的正式字体、改前正式字体。额外控制组 `before-fallback` 也保存在 JSON 和 PNG。

**桌面：48px / 118% / line-height:normal，1340×900**

| 标题 | 只有新回退 | 新正式字体 | 改前正式字体 |
| --- | --- | --- | --- |
| 新作品 | 139.48 × 52.00；— | 139.48 × 52.00；— | 144.00 × 70.00；— |
| 光盘刻录 | 185.97 × 52.00；— | 185.97 × 52.00；— | 192.00 × 70.00；— |
| 刻录 DVD-R 16x | 408.27 × 52.00；0.00 | 407.59 × 52.00；0.00 | 410.61 × 70.00；0.00 |
| Disc Probe 盘库 | 416.59 × 52.00；0.00 | 409.67 × 52.00；0.00 | 412.69 × 70.00；0.00 |
| BD 校准 2026 | 346.67 × 52.00；0.00 | 345.42 × 52.00；0.00 | 348.44 × 70.00；0.00 |
| DISC-PROBE 1201 | 509.23 × 52.00；— | 518.19 × 52.00；— | 518.19 × 52.00；— |

**手机视口：26px / 118% / line-height:34px，390×800**

| 标题 | 只有新回退 | 新正式字体 | 改前正式字体 |
| --- | --- | --- | --- |
| 新作品 | 75.55 × 34.00；— | 75.55 × 34.00；— | 78.00 × 34.00；— |
| 光盘刻录 | 100.73 × 34.00；— | 100.73 × 34.00；— | 104.00 × 34.00；— |
| 刻录 DVD-R 16x | 221.12 × 34.00；0.00 | 220.80 × 34.00；0.00 | 222.42 × 34.00；0.00 |
| Disc Probe 盘库 | 225.62 × 34.00；0.00 | 221.92 × 34.00；0.00 | 223.55 × 34.00；0.00 |
| BD 校准 2026 | 187.77 × 34.00；0.00 | 187.12 × 34.00；0.00 | 188.75 × 34.00；0.00 |
| DISC-PROBE 1201 | 275.78 × 34.00；— | 280.69 × 34.00；— | 280.69 × 34.00；— |

**字标宽度：34px / 125% / line-height:1，1000×800**

| 标题 | 只有新回退 | 新正式字体 | 改前正式字体 |
| --- | --- | --- | --- |
| 新作品 | 98.80 × 34.00；— | 98.80 × 34.00；— | 102.00 × 34.00；— |
| 光盘刻录 | 131.73 × 34.00；— | 131.73 × 34.00；— | 136.00 × 34.00；— |
| 刻录 DVD-R 16x | 302.50 × 34.00；0.00 | 301.98 × 34.00；0.00 | 304.11 × 34.00；0.00 |
| Disc Probe 盘库 | 308.77 × 34.00；0.00 | 303.52 × 34.00；0.00 | 305.64 × 34.00；0.00 |
| BD 校准 2026 | 256.28 × 34.00；0.00 | 256.22 × 34.00；0.00 | 258.34 × 34.00；0.00 |
| DISC-PROBE 1201 | 382.20 × 34.00；— | 387.38 × 34.00；— | 387.38 × 34.00；— |

**正常字宽：32px / 100% / line-height:1.08，1000×800**

| 标题 | 只有新回退 | 新正式字体 | 改前正式字体 |
| --- | --- | --- | --- |
| 新作品 | 92.98 × 34.55；— | 92.98 × 34.55；— | 96.00 × 34.55；— |
| 光盘刻录 | 123.97 × 34.55；— | 123.97 × 34.55；— | 128.00 × 34.55；— |
| 刻录 DVD-R 16x | 239.72 × 34.55；0.00 | 239.41 × 34.55；0.00 | 241.42 × 34.55；0.00 |
| Disc Probe 盘库 | 244.41 × 34.55；0.00 | 241.00 × 34.55；0.00 | 243.02 × 34.55；0.00 |
| BD 校准 2026 | 205.00 × 34.55；0.00 | 202.11 × 34.55；0.00 | 204.12 × 34.55；0.00 |
| DISC-PROBE 1201 | 287.06 × 34.55；— | 296.16 × 34.55；— | 296.16 × 34.55；— |

**解读与加载前后的位移：**

- 48px / normal 下，含汉字的改前正式盒高为 70px，改前回退为 61px，换字体高度差 9px；新正式和新回退均为 52px，高度差 **0px**。基线距标题盒顶由原来回退 49px / 正式 56px，变成两者均 42px，加载基线位移从 **7px 降至 0px**。
- 同一行中英的 alphabetic baseline 在改前、改后本来都为 **0px 差**，不能把原有基线对齐宣称为新修复。改善的是字体行框度量及字体交换时整行基线的位置；不是测量字形墨迹的视觉中心。
- 四档角色的 **24 组**新回退 ↔ 正式比较，高度差均为 **0px**，基线距盒顶的差均为 **0px**。纯中文宽差均为 **0px**。
- `desktop` 6 个样例的最大字体交换宽度残差：**16.44% → 1.73%**。
- `phone` 6 个样例的最大字体交换宽度残差：**16.44% → 1.75%**。
- `wide` 6 个样例的最大字体交换宽度残差：**20.82% → 1.73%**。
- `normal-width` 6 个样例的最大字体交换宽度残差：**4.01% → 3.07%**。

截图均在 `D:/dp-dev/tmp/brand/mixed/`：每档 `{desktop,phone,wide,normal-width}-{fallback,formal,before,before-fallback}.png`，共 **16 张**；已查看桌面三态及手机正式 / 回退截图。现有品牌浏览器测试另保存三个真实页面截图到 `mixed/pages/`（home-paper、home-ink、phone）。每个 run 实际使用的平台字体、屏蔽请求记录及原始 DOMRect 均在 `measurements.json`。

### 验收命令与结果

全部临时目录、Edge profile、截图和日志均在 D 盘，`TEMP=TMP=D:/dp-dev/tmp/brand`、`PYTHONDONTWRITEBYTECODE=1`；没有运行整套 Python 测试。

1. `python -X utf8 -B tools/align_title_fonts.py --check --report D:/dp-dev/tmp/brand/mixed/font-metrics.json`
   - **通过**；两份生成 CSS 与脚本输出一致，生成过程不写字体二进制。输入哈希、表值及全部百分比已留档。
2. `python -X utf8 -B -m pytest -n 2 tests/test_brand_assets.py tests/test_release_packaging.py tests/test_webui.py tests/test_webui_catalog.py tests/test_webui_recovery.py disclab/tests/test_interface.py disclab/tests/test_package.py --basetemp D:/dp-dev/tmp/brand/pytest-mixed -q`
   - 首轮 **144 passed、42 subtests passed、2 failed**，55.77 秒。两处是新增 CSS 规则测试取错块 / 后续空白比较，以及 Lab 字体说明误带本机路径；已修正。
   - 单独重验 `tests/test_brand_assets.py::test_title_metric_css_rebuild_and_title_only_scope`：最终 **1 passed**，5.49 秒（`pytest-mixed-metric`）。
   - 单独重验 `disclab/tests/test_package.py::test_no_absolute_machine_paths`：**1 passed**（`pytest-mixed-fixes` 的两项运行中该项通过）。
   - 合计本次所选 **146 个测试、42 subtests 最终均有通过结果**；没有为得到一次整批全绿重复运行这 146 项。
3. `python -X utf8 -B D:/dp-dev/tmp/brand/run_mixed_nodes.py`
   - 逐个运行 `tests/test_*.mjs` 全部 **37 个文件**，工作目录设为 D 盘临时目录，使现有测试的相对截图路径也留在临时目录。
   - 首轮 **36 PASS、1 FAIL**。唯一失败是未修改的 `test_presetio_browser.mjs`：第三个案例在 Edge 的 6000ms virtual-time budget 后仍为 `PENDING`，没有返回断言结果；尚不能据此判断根因。
   - 单独用原命令复跑 `node D:/dp-dev/brand/tests/test_presetio_browser.mjs`：**10/10 场景通过，exit 0**；没有修改该测试或放宽等待。37 个文件最终均有通过结果，保留首轮失败记录。日志在 `D:/dp-dev/tmp/brand/mixed-node-results/`，复跑为 `test_presetio_browser.retry.log`。

4. `node tests/test_title_font_alignment.mjs`
   - 最终全 Node 轮内 **PASS**：**4 角色 × 4 状态 × 6 标题 = 96 个盒子**、16 张截图；24 组加载前后比较通过，字宽残差阈值 4%、纯中文绝对宽差阈值 0.1px、行高和基线位置差阈值 1px。实测行高 / 基线差均为 0px。
   - CDP `Network.setBlockedURLs` + cache disabled 确认屏蔽真实字体请求；`CSS.getPlatformFontsForNode` 确认新回退是 Arial-Black / MicrosoftYaHeiUI-Bold，正式字体是 Archivo / Disc Title SC。不是仅检查 computed font-family。
5. `impeccable.cmd context --target discprobe/web/fonts/titles.css` 与最终 `impeccable.cmd detect --json --scope type discprobe/web/fonts/titles.css disclab/web/fonts/titles.css`
   - 使用已安装本机引擎，禁用下载回退；context 成功读取现有上下文，最终检测输出 **`[]`，0 项**。
6. 改前夹具与 Git `9bb5f00:discprobe/web/fonts/titles.css` 去注释 / 空白后声明一致；`git diff --check` **通过**。中文报告及新增测试已作非 ASCII / 连续问号检查。

### 未测、局限和需要人决定的事项

- 单一 size-adjust 不能逐字匹配另一字体的形状和 kerning。全部实测样例残差小于 4%，不代表任意字符串、任意字重或任意连续可变字宽都小于 4%。100% 档的纯拉丁样例残差仍为约 3.07%；未掩盖或声称完全相同。
- 本次校准的是本机 Windows 的 Arial Black / Microsoft YaHei UI Bold。其他平台或缺少 local 字体时继续使用既有平台回退栈，**没有声称那些回退已经校准**。字号协调依据 x-height 元数据；中文没有拉丁 x 字形，未把此比值当作中文墨迹高度的完整视觉模型。
- 手机测试是 Edge 桌面中的 390px 视口，使用 Windows 字体；真实 Android / iOS、macOS、Linux、旧浏览器、真实网络延迟下的 CLS：**未测**。本轮是字体前后两个确定状态及度量比较，不是线上 CLS 采样。
- 浏览器测量页使用合成标题；现有真实首页 / 手机字体测试仍通过。完整应用的每个标题与多行长文本换行组合未穷举，完整 Windows 发布包未重建。
- 需要人决定的问题：**无阻塞项**。未做额外配色、版式或措辞调整；没有推送、合并、切分支、访问其他 worktree、接光驱、刻盘、上传或下载资源。
