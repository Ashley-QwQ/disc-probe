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
