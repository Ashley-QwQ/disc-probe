# 卡 AD · 彩图方向箭头

工作树 `D:/dp-dev/arrow`，分支 `dev/colour-arrow`，基点 `f3d0f2f`。按补充 1 完成交付。

## 按提交交付

- `5dab630` 增加网页彩图填充的默认勾选框和 CLI 的 `--no-arrow`。箭头放在彩图图层正上方，使用普通多边形和 `tex:RND` 材质。两端读取同一份七顶点定义。外沿不足 53.3 mm 时将箭尖移到外沿内侧 0.5 mm，环带放不下时仍可完成彩图填充，并显示提示。
- `8c0cbef` 让网页打开 CLI 的纯多边形作品时沿用箭头的中灰颜色。重开验收发现多图层列表仍调用已移除的 `clearSelection()`，因此点击图层会出错。移除这处旧调用后复验保存重开、去重、移动、隐藏和删除。
- 本报告提交替换第一轮的受阻记录，保留下方社区提示卡报告原文。

`editor_ops.validate()` 仅额外接受精确的大写 `RND`，原错误文字保留。网页导出沿用后端校验，灯下视图已识别 `RND`。`git diff f3d0f2f --stat` 见验收目录中的 `git-diff-stat.log`，`editor_ops.py` 的唯一差异在材质校验。合成、镜像生成、纹理表、拟合色表和 texlib 的差异为 0。

## 老路径逐字节回归

以下 `compose` 分别用基点导出的源码和本分支运行。4-18 使用原作品，另外三个作品来自 `tests/test_editor_ops.py` 的 `document()`、`grey_document('ordered')` 和 `tests/test_design_compose_route.py` 的 `ring_work('92')`。每份标签为 6000 × 6000。下列 SHA-256 在两版完全一致。

| 作品 | 标签 `.npy` SHA-256 | `.textures.json` SHA-256 |
| --- | --- | --- |
| 4-18 `COLOUR-1x21-A` | `1f08f6a7402fab6330a5b21a0df7ee3a2da544fdebb1c191477c535b6da9fe40` | `99cc0a916e5599448c649e2e309117adebb144968828169e526e43c2b3c26850` |
| SVG 与图案 | `5ecb94e2e2d0a82a71cfca85fc8e8bf60bf87b640358c08c2b25d4829567cd2c` | `a328367dd3dcb70c8761e4212fee11b962fac5228d168d48bd582b1b41d41be0` |
| 灰阶影调 | `a6e0b542e3fe059ae8419bfbeedeedbe8506e5c9a178568b0bd1590dd5e46f96` | 同上 |
| 网页圆环填充 | `12448b74f0b1f209ad3a7681b116145bf3d8b260476cf3973b4bd11ea2ad5f9d` | 同上 |

- 4-18 原 `.image.json` 提供几何、材质顺序、20 µm 格、起始和前导 LBA，以及 photo L 和角度修正状态。同一脚本从记录的总扇区数反推 `--r-max 54.0400471937871`，用同一份几何文件副本构建两套 `image` 命令。ISO9660 使用统一的测试时钟（2026-11-12 00:23:03 UTC），其时间戳本来取生成时刻。两份完整 ISO 均通过写入器抽验，长 1,966,944 扇区、4,028,301,312 字节，SHA-256 均为 `67b1548f42713eb64aa741ec78cc873f0a781d15f9c4cbefe90e763e1cdf6811`。
- 从 4-18 文档解出同一张 640 × 640 RGBA PNG，以相同参数运行基点 `colour-design` 和分支 `colour-design --no-arrow`。两份作品 JSON 逐字节一致，SHA-256 为 `11511e6e011bcce99f373a825b95e25e6bc7892eb42f6981ccc63af7d6c25d64`。
- 两版直接运行文档校验。18 份不含 `RND` 的输入结果一致，7 份通过，11 份仍以原消息拒绝，覆盖奇数位、非法十六进制字符、超长、非字符串、小写或混合大小写、前后空格和 `MIX:`。第 19 份精确大写 `RND` 输入由基点拒绝、分支接受。非 `RND` 输入仍走原校验表达式。

## 新作品、ISO 和镜面带

- 用 `colour-design --phone iphone17pro --height 21` 生成默认作品。验收输入沿用 4-18 的彩图，将 27–53.75 mm 外的像素设为透明以适配现有实测几何，要出 ISO 的作品 JSON 由 CLI 直接生成。箭头在 20 µm 网格上覆盖 59,662 格，与独立计算的多边形掩模逐格相同，全部为槽位 60。多边形面积 23.8128 mm²，理论计数 59,532，实测多 130 格（+0.2184%）。掩模外标签与关闭箭头时一致。
- `compose` 的 `.textures.json` 最后一个规格为 `RND`。随后 `image` 成功生成 1,966,944 扇区的 ISO，SHA-256 为 `2b84314360d63c9de285dc83e62872a54c52108fb8048ed01d0951c797400b96`。从螺旋几何定位 8 个扇区内属于箭头的字节，按各 LBA 异或 DVD 扰码表。箭头头部有 2 个扇区完整覆盖，另外 6 个扇区部分覆盖。检查的 9,920 字节全部与 `texture_bytes("RND")` 一致。抽样 LBA 为 1120279、1175733、1258056、1330517、1460824、1477097、1652826、1654069。逐扇区哈希、字节数与半径见 `new/results.json`。

按拟合色表的最低支持偏移 0.1 和偏移比例 0.93，计算 12 点两侧的镜面带全角。B9 比例直接取无箭头的合成标签。

| 机位 | B9（槽位 0）占箭头区域 | 尾部 43.5 mm | 头底 48.59 mm | 尖端 52.8 mm |
| --- | ---: | ---: | ---: | ---: |
| iPhone 17 Pro，CLI 21 cm，镜头离盘 208.7 mm | 59,662 / 59,662（100%） | 25.001° | 24.955° | 24.928° |
| 4-18 原文档机位，镜头离盘 221.740 mm | 59,662 / 59,662（100%） | 26.561° | 26.519° | 26.494° |

4-18 作品存的是机位 ID `21`，现用机位表将它显示为尺高 22.3 cm。对照保留这个作品机位，另测 CLI 输入的 21 cm。宽度为拟合模型的方位宽度。未做实盘观察。

## 网页和测试

- 在临时回环端口用独立 Python 后端进程跑编辑器，光驱提供器返回空列表。用无头 Edge（`--mute-audio`）经过图片文件输入和实际填充按钮，验证默认勾选、取消、重复填充、一次撤销、窄环带提示、保存重开、纯多边形恢复、灯下及刻出视图。在 `F:/dp-archive/tmp/colour-arrow/shots/` 保存 1440 × 1000 的 `paper-checked.png`、`paper-unchecked.png`、`night-checked.png`、`night-unchecked.png`。
- `python -B -X utf8 -m pytest -n 2 tests/test_editor_ops.py tests/test_design_compose_route.py tests/test_lamp_optics.py tests/test_editor_colour.py -q --basetemp=F:/dp-archive/tmp/colour-arrow/acceptance/pytest-final`，**123 passed**。运行 `python -B -X utf8 -m discprobe --lang en colour-design --help` 和对应的 `--lang zh`，核实两份帮助都含 `--no-arrow`。
- 逐个执行 `node tests/<各 test_*.mjs>`，**55 个文件均通过验收**。全量首跑 54 通过、1 失败，失败项是重开后点击图层的检查。修复后为最终版本复跑 `test_editor_texlib_browser.mjs`、`test_editor_desk_browser.mjs`、`test_editor_w245_browser.mjs`、`test_csp_browser.mjs`、`test_ime_activity.mjs`，5 个均通过。首跑和复跑日志均保留。

验收日志、命令生成及反解脚本 `proof.py`、基点和分支的哈希清单均在 `F:/dp-archive/tmp/colour-arrow/acceptance/`。开跑和全量回归前 D 盘分别剩余约 199.7 GiB 和 199.2 GiB。测试生成的 ISO 已删除。未连接光驱或刻盘，未推送或合并。没有需要审查者先决定的实现事项。

---

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
