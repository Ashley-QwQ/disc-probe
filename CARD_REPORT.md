# LG 卡交付报告

分支 `dev/learn-grating`，基点 `39a1dac`。三段各自提交。验收只使用离线软件和虚拟设备。

## 段 1 · 网页彩色求解器

提交 `Audit the web colour solver from pixels to disc image`。详见[核查报告](docs/goals/colour-solver-audit.md)和其中的复现命令。只修正一处重复且过时的导出说明，网页和 CLI 的默认标签、刻图算法及材质配方均沿用现有实现。

- 无头 Edge/CDP 从同一 PNG 走实际图片导入、彩色填充、合成与镜像生成。使用隔离回环端口和模拟几何，无任何刻录或设备打开。首轮 HTTP 夹具合成挂住，改由主线程预加载 SciPy 后通过。旧夹具的 `image` 结束提示读取了 Windows 的逻辑驱动器类型以输出驱动器盘符，复现脚本使用模拟几何命名来跳过这条提示。
- 同一份作品的标签完全一致。独立导入对齐摆放后，3,600 万格的实写纹理一致。4,700,372,992 字节的两个 ISO 归零日期字段后 SHA-256 一致。ISO 已清理，`run3/parity.json` 保留原始及归一化哈希。
- `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/learngrating/pytest-colour -q tests/test_editor_colour.py tests/test_editor_preview.py tests/test_editor_pose_swatches.py tests/test_design_compose_route.py tests/test_gui_handshake.py`，42 项和 12 个子测试通过。
- `node --test --test-concurrency=1 tests/test_design_export.mjs tests/test_editor_rig.mjs`，2 项通过。
- 模型数据、旧实拍的对应色片、角色表数值对照和测试日志保存在 `D:/dp-dev/tmp/learngrating/`。物理板位误差、新刻盘的颜色与抖动外观未测。

## 段 2 · 光栅角色卡

提交 `Add a core grating card command and reproduce the recorded cards`。角色卡按补充采用 SHOWCASE-BLINK 4-20 和 FLIP-A 4-21。旧效果盘的 O/X、两点成环和反向流光是此前的实体实验，FLIP-A 中的 O/X 是对照项。SHOW-D 是另一张角色展示盘。以盘登记 `D:/disc-probe/docs/goals/discs/register.md`、`F:/dp-dev-tmp/showcase-blink/DESIGN.md`、`D:/disc-probe-scratch/flip-pairs/REPORT.md` 和 `F:/dp-dev-tmp/video/IMG_8338/REPORT.md` 为源。

- Core 的 `gratingcard` 从两至三张图及其角度算共同面积配方，生成 ISO、标签、材质顺序、数据面预览和双语可选的观看说明。沿用原始 δ 分阶表、倾转、Bayer 与通道门槛。默认包收录两盘 132 个已用纹理中同时满足索引和通道检查的 124 个，NPZ 约 1.16 MB。原表、索引、检查和清单的哈希记录在 `discprobe/grating_card/provenance.json`。其余 8 个是 FLIP-A 对照项，随原材料仍能复刻。Wheel 核对包含四个数据文件。网页彩色仍用原来的 58 个材质。
- 新卡加 12 点随机纹理方向箭头，生成的图案数据域不含 `92`。箭头单独做原门槛的四地址、两种块布局、四初态共 32 组检查。F512%、八扇区最差平均帧偏、帧末最大 |DSV| 分别为 0.00777%、0.00389、20。实体通道效果未测。历史复刻保持原样，缺少箭头的存档 ISO 只用于软件核对。
- `--replay` 让 4-20 从定稿 `design_accent.npz` 的 0.06 mm 面积权重重建，FLIP-A 从 `flip-a.work.json` 的已选材料图层重建。两张各 36,000,000 个标签逐字节相同，112 项、38 项材料顺序也分别相同。各 4,020,994,048 字节的 ISO 原哈希有异，仅归零 ISO 9660 时间字段后逐字节相同。4-20 归一化 SHA-256 为 `2254ab65c27a0d5b40305aaaf3f8478becbac2849f6be793e57cacb2be9f3ebb`，FLIP-A 为 `6d8ae35516817ce1089c781689ba66ac69f951422fc85f822ecea66d2dfcf1d4`。两个重建 ISO 已清理，只留校验结果。重建从原成像输入开始。新图片入口是通用联合求解，原专案的遮罩、色适应白点、局部红色点缀和围巾流光需要原设计权重才能重现。
- 用 `tools/verify_grating_replays.py` 对照整盘和标签，结果在 `character-compare.log`、`flip-compare.log`。用 `python -B -X utf8 tools/check_grating_cli_defaults.py D:/dp-dev/tmp/learngrating/default-parity 68ea72d` 比较加命令前后。固定时钟并使用 Disc Lab，`burn`、`info`、`image` 的中英文执行与帮助共 12 组标准输出／标准错误逐字节相同，默认 `image` 整个测试镜像逐字节一致。
- `pytest -n 2`，光栅、刻后检查、彩色合成与刻录相关共 62 项、4 个子测试通过。新增随包数据的三角度用例后，`tests/test_gratingcard.py` 8 项通过。新命令 16,777,216 字节样盘在 Disc Lab 抽样读回 96 处，全相符。去时间的默认样盘哈希为 `d708214a92b668fee4c88f60f163fdbfcca93304cadd953a3021f46a0456bdb6`。
- [中文说明](docs/grating-card.zh.md)和 [English guide](docs/grating-card.md)记录各区域、预期角度、4-20 实拍和 FLIP-A 的模型图。没有为本卡新增实体刻录。新通用入口的实拍换画保真度未测，FLIP-A 的两个目标角仍只有模型支持。

## 段 3 · 光盘怎么变成图

待完成。

## 需要用户决定

- 彩色网页暂沿用随包 58 种材质。若考虑替换，先单独比较新候选的色域、运行耗时、读回和实拍。角色卡使用数及查表行数的含义见段 1。

## 给 Claude 转达

- 段 1 没有编辑 README 彩色章节或编辑器工具栏。触及的颜色说明在 `editor-rig.mjs` 和 `editor-controls.mjs`，并行编辑器卡若改了后者的布局，请同时保留这里的一段默认导出说明。

<details>
<summary>Earlier report already present at the branch point</summary>

# 社区提示卡交付报告

工作树：`D:/dp-dev/community`，分支：`dev/community-presets`。仅在本分支提交，没有推送、合并或切换分支。

## 按提交交付

- `39c41a0`：更新 DIS 研究数据，收录社区文字参数与内置预设，归并复用报告，保留不完整证据。
- `138b32d`：定义 `dp-community` v1，增加严格校验器、可重复生成工具、线上及包内数据，补充 `news/README.md` 维护步骤。
- `93fb5ef`：核心下载/缓存/回退、CLI 筛选和主动导入，补齐中文帮助与 guide 提示。
- `e65a1b5`：保留重复出处的原始数值字典，核对同日帖子时间，修正最早出处，追加 I171 的新复用报告。
- `a211d86`：CLI JSON 只输出筛选结果，导入被拒时明确报错，增加 Windows 源码打包阶段和 wheel 回退文件校验。
- 本网页提交：本地社区 API、传真机浏览和次要导入按钮、新作品提示、相关浏览器测试，以及本报告。

## 数据及出处

本轮主刷新窗口为 `2026-11-13T00:46:21Z` 到 `2026-11-17T01:38:57Z`（多伦多仍是 11 月 16 日）。只通过 `gh` 只读访问 DIS GitHub：62 个更新过的 issue/PR、35 个 discussion、14 个 release、26 个 commit；另检查 PR review/comment，得到 2 条 review 文字。discussion 的 comments/replies 做了分页，包括超过 100 条评论的帖子。最后对同日重复帖补查创建时间，未将补查误记为整库重新刷新。

原始抓取与检查脚本在 `F:/dp-dev-tmp/community/`：`issues.json`、`discussions.json`、`releases.json`、`commits.json`、`pr-reviews.json`、`fetch.json`、`earliest-audit.json`。没有下载附件图片、ZIP 或外部购买链接内容。图片中的数值未猜测。

相对卡开始时的文件，新增 **27 个 canonical id**（社区 17、内置独立数值组 10），修改 **30 个既有 entry**。原有 24 条空参数复用报告归到原数值记录，12 条不完整/指代不清记录移入 `skipped`，另有 6 个既有重复数值 id 归并。原始报告及重复来源的数值字典均保留。因此 `entries` 从 178 变为 **163**，不是简单追加后的条数；`skipped` 从 17 变为 **34**。具体对应关系在最后一条 `updates` 的 `merged`、`consolidated_reuse`、`moved_to_skipped`。

新增 id：

```text
D328-1 D337-1 D340-1 D344-1 D352-1 D360-1 D362-1 D363-1 D365-1
I308-1 I329-1 I332-1 I335-1 I339-1 I341-1 PR298-3 PR368-1
DIS160-bd-r-ritek-10x DIS160-bd-r-sl-25gb DIS160-bd-r-verbatim-64099
DIS160-cd-74 DIS160-cd-80 DIS160-dvd-5-120mm DIS160-dvd-5-80mm
DIS160-ritek-medical-aqua DIS160-verbatim-dvd-plus-r-azo-43498
DISmain-verbatim-dvd-plus-rw-94520-95043
```

修改 id（含仅补充来源/复用报告的记录）：

```text
D107-22 D109-1 D127-1 D169-1 D191-1 D208-1 D210-1 D214-1 D216-1 D275-1
I119-1 I132-1 I144-1 I171-1 I228-1 I248-1 I25-1 I311-1 I327-1 I35-1
I36-1 I41-1 I50-1 I53-1 I58-1 I60-1 I65-1 I74-1 I79-1 I87-1
```

新的结果说明包括：I327 在另一台光驱上“almost worked”，标为 `partly`，不把评论者的 MID 当作原作者确认的 MID；D275 商务版复用报告仍保留原来的部分有效结论；I171 增加另一位用户的首次尝试报告。D352 同组数值在新批次有效、旧批次失败，两个结果都写明。I329/D349 保留圈码和多批次不可通用的提醒。

内置来源完整记录 **v1.6.0 的 17 条**和 **main 的 6 处变更**，后者为 1 条新预设、5 条 MID/圈码描述更新。使用只读本地克隆；`gh` 核实远端 main 同为 `28310c8700646808bffa434feb2db68ab2c26a50`，v1.6.0 为卡指定的 `4915b7d`。同值预设不另造独立数值组，但在 `source` / `additional_sources` 中保留标签/提交、内置 id、描述、贡献者用户名及 GPL-3.0-or-later。标准预设、DIS 声称实测/验证、社区实际结果分开陈述，未标成 DP 实测。

同日重复帖额外核对：I132 早于 I94、D133；I311 早于 D313；I335 早于 D336。保留最早出处，时间证据写入 `updates.earliest_source_timestamps`。

## 下发与程序行为

`news/community.json` 与 `discprobe/web/home/faxnews/community.json` 一致，**169,234 字节**，163 条，数据日期 `2026-11-17`。SHA-256：

```text
f89392ba00699001e983bc9d4c5dcb7dddc14026b6f8f81b1ff341b6b6c291ff
```

生成：`python -X utf8 tools/build_community_feed.py`；检查：同命令加 `--check`。维护顺序已写入 `news/README.md`：改研究数据 → 生成两份 → 提交 → 用户决定进 main → 用户下次取传真时更新。`.gitattributes` 保持两份生成文件的字节，避免 Windows 换行转换破坏重复生成检查。

`community.get_community()` 复用传真机的 DNS 检查、固定解析地址、HTTPS/重定向检查、公网限制、超时和 1 MiB 上限。顺序为 GitHub Raw → jsDelivr → 独立社区缓存 → 包内。坏 JSON、坏字段、长度、重复 id、日期、链接、非有限数等都当作来源失败。返回 `from`、数据日期、总条数、实际来源和错误记录。网页选盘时只读缓存/包内；传真机取报纸时才刷新社区数据。

CLI：`python -m discprobe community`，支持卡要求的全部筛选参数和 JSON。类型是硬筛选；MID、扇区数、品牌/型号文字作为候选匹配，按 MID 完全一致、扇区数一致、文字匹配排序，也考虑同值记录的其他盘片出处。失败 entry 默认不列，显式 `--include-failed` 才列。

仅 `--import ID` 或网页明确点击导入才写预设库。继续走 `presets.import_file` 的校验及换算，保留 id、原帖、作者、日期、结果、可信度、来源版本和“不是 DP 测的，这批盘还没确认，只当起点”。导入后的 `fit.calibrated` 仍为 false，外来实测范围只记在来源中，未冒充本机测量。既有几何兼容门槛继续生效。

## 网页位置和需要人工审查的选择

传真机第一栏顶部增加“社区提示”，沿用现有报纸文字、分隔线、按钮和主题；显示日期/总数/联网、上次的或程序自带，按 CD/DVD/BD 浏览。记录折叠展开后可看数值、结果及各原帖，导入是次要按钮。失败复用报告可能属于一个非失败的主记录，展开后仍按原出处写清，不掩盖失败。

新作品页只在原来的光盘帮助文字下面添加一段提示。识别盘与记录同 MID 或同扇区数才显示；默认排除失败 entry，最多列三条原帖链接，其余提示去传真机。没有改变已有选择、光盘识别、标定文案和进入设计页的流程，也没有自动导入。

请审查者决定是否保留目前的**传真机第一栏顶部、折叠记录、选盘帮助行及三条链接上限**。目前是依现有样式实现的可审查位置，没有替用户作新的视觉方向决定。1440px 两种主题和 390px 传真布局已做浏览器检查；新作品页的实际截图位于下述目录。未做人工外观批准。

## 验收

所有测试均在本地/模拟环境进行，没有连接真实光驱或刻盘。运行前设置 `TEMP`、`TMP=F:/dp-dev-tmp/community`，pytest 使用 `-n 2`。开跑和全量 Node 前 D 盘约 40.7 GB、F 盘约 20–22 GB，均高于 5 GB。

| 命令/检查 | 结果 |
| --- | --- |
| `python -X utf8 -m pytest -n 2 tests/test_community.py tests/test_community_feed.py tests/test_community_http.py tests/test_news.py tests/test_presets.py tests/test_dis_pitch.py tests/test_gui_handshake.py -q --basetemp=F:/dp-dev-tmp/community/pytest-acceptance` | 159 passed，8 subtests passed |
| 最后修订出处后，重新跑 community、feed、HTTP 三个模块 | 29 passed |
| 增加 Windows 打包阶段测试后，跑 feed 与 gui_handshake | 27 passed，8 subtests passed；包含新增 Windows 源码复制校验、wheel 内文件字节一致检查 |
| `tests/` 下全部 `test_*.mjs`，逐个 `node` 执行 | 52 个文件全部通过，详见 `F:/dp-dev-tmp/community/node-results.json` 和 `node-*.log` |
| 最后增加展开数值不溢出检查后，重跑 `node tests/test_faxnews_browser.mjs` | 3 个视口/主题场景全部通过 |
| `python -X utf8 -m discprobe selftest` | exit 0，`all checks passed`；日志 `F:/dp-dev-tmp/community/selftest.log` |
| `python -X utf8 tools/build_community_feed.py --check` | 163 entries，两份文件一致，可重复生成 |
| 数据 id、数值、GitHub HTTPS 链接及字段检查 | 通过；不完整记录留在 skipped |
| `git diff --check`、中文 UTF-8 检查 | 通过；应含中文的改动文件均有非 ASCII 字符，无连续三个问号的损坏迹象 |

初次测试暴露的测试问题已修正：超大字节串不再用作 pytest 用例名称（会超过 Windows 环境变量长度）；新作品页异步返回使用等待条件；浏览器 mock 明确允许新增的只读社区请求；失败记录断言只检查主记录结果，避免误把保留的失败复用证据当作筛选失效。没有放松生产数据校验。

截图：`F:/dp-dev-tmp/community/fax-shots/`、`disc-shots/`、`review-shots/`、`own-shots/`。测试产生的工作树外观证据、作品夹和 editor 证据已可逆地移到 F 盘的 `generated-*` 目录，工作树没有留下这些测试产物。自动审核拒绝了合并执行的递归清理命令，未返回更具体原因；因此未删除成功测试的临时目录，仍保留在 F 盘，日志、截图和失败现场也全部保留。

## 未测及边界

没有重新构建完整 Windows 内置 Python 发布 ZIP；测试实际执行了 `build_winpack.copy_source(worktree=True)` 并核实社区模块、网页模块和回退数据会进入 Windows 源码打包阶段，wheel 则实际构建并检查内容。没有发布线上数据、推送或合并，远端 main 目前不会因本分支发生变化。

附件图片/视频/ZIP 没有读取，图中才有的完整值、仅称成功而未贴最终数值的报告没有补成预设。相同 MID、容量或型号只表示可以参考，不构成这批盘几何匹配或 DP 实测。界面位置/外观请人工复核，其余没有需要用户先回答才能运行的事项。

</details>
