# DIS 用户想要什么、卡在哪里，DP 应该接住什么

数据覆盖更新到多伦多 2026-11-12 晚间（采集窗口 2026-11-13 00:44:53–00:46:21 UTC）。本轮仅通过只读 `gh` 查询 GitHub，没有下载图片或附件、构建、运行 DIS 或做实盘试验；11-11 的人工需求归类和静态源码核对保留为历史基线。

## 11-12 增量：覆盖量与新增需求

当前 DIS **101 个 Discussion＋170 个 Issue＝271 个线程、1,374 条正文／评论／回复**；相对 11-12 原快照（265／1,288）新增 6 个线程、29 条发言，另补齐 57 条旧分页遗漏（D108 54、D107 3），没有旧正文修改。当前 260 条为 Ashley-QwQ 发言，其余涉及 254 个账号（含维护者和贡献者，不等于客户数）。相对 11-11 的 263／1,275，净增覆盖 8 个线程、99 条发言；其中历史补齐不算新需求票数。

另保存 DIS 全部 **53 个 PR、115 条正文／评论／审阅记录**，以及 DP **17 个 Issue＋17 个 PR、162 条记录**。两者没有旧基线，按消息创建／更新时间筛近期活动：DIS PR298 一条新评论；DP #33、PR32、PR34 共 9 条新记录。上述 PR／DP 数量不混入 271／1,374 的旧统计口径。逐文件统计与限制见 [comparison.json](../../goals/dis-community/data-20261113/comparison.json)，问题和 alpha 落点见 [本轮反馈](FEEDBACK_LOG.md)。

下文 13 条摘要及 R01–R13／P01–P11 的账号数、优先分、TSV 仍是 **11-11 人工确认下限**，没有用增量关键词重新累加。新增需求单列，不改旧排序：

| 新类型 | 明确提出的账号数 | 用户要完成什么；证据 | DP 状态 |
|---|---:|---|---|
| R14 原始描线／拟合预测并排检查，解释模型失配 | **1** | gelinkpink 想把可见但不规则的边界变成可信几何，分清描错点与模型无法表示；I324 的 423 点未过校验，I325 的 158 点在三次轨距下平均误差 1.399 mm、最大 4.869 mm，并要求显示未经平滑的原始描线。[I324](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/324)、[I325](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/325) 为同一账号，不算两人 | alpha A2／A6 保留证据、拒绝不可靠修正；A1／A4 解释下一步。完整 φ(r) 人工编辑属 F1，未列入 alpha；变轨距尚不能宣称已解决该实盘案例 |

这也补强既有 P10／R01／R02，未据此重算人数。D270 的“刻前颜色较深更好”只是观察线索，属于原有 R04／P02；D231 从“仍差一到两圈”到“更接近”尚无最终成功；I326 后续已见螺旋，不能继续当纯显色失败。新校准数据 174 → 178 条，I327 保留 `unknown`；新记录不是新的兼容性保证。

## 先看这 13 条

1. 最该先解决的是“怎样走到第一张可辨认的图”：至少 **60 个账号**报告过标定、几何或阶段衔接问题。
2. 有用户用掉 **25 张盘仍失败**；另一人做了约 **40 次、20 小时**，用的是可擦写盘，不能说烧坏了 40 张。
3. **32 个账号**谈到太淡、拍不出来或效果不如预期；线条对齐、字节可读、肉眼可见是三项不同的验收。
4. **24 个账号**遇到预设不适用；品牌、商品名、MID 都不足以单独保证几何相同。
5. **23 个账号**报告写入、导入区或封盘失败；同一个错误码背后可能是容量、写入路径、介质或供电，不能统一叫“没标定”。
6. 最危险的是静默失败：保存了预设却沿用旧系数、选错 CD 扇区模式、格式化备用区改变地址、截图漏掉科学计数法。
7. 教程和下一步指引有 **17 个账号**明确求助或提改进；自动化、少耗盘及工具整合有 **12 个账号**明确提出需求。
8. DP 的计时路线已有第三方成功报告；DVD 可以少走拍照描点，CD 也有“计时后一次精标，共三张”的完整实例。
9. DP 也有自己的失败：CAV 判断、缓存假周期、外圈外推、CD 写入模式、启动及图案写盘问题，不能只当旁观者。
10. 本地 DP 已有 `guide`、`calibrate`、`disexport --install` 和质量拒绝检查，应先把它们放到用户自然经过的入口。
11. 最需要新增的是可靠的盘批次／写入路径记录、按症状排错、可直接分享的报告包，以及素材和参数的可追溯保存。
12. DIS 做得好的地方值得接住：社区会补 MID 和内圈码、提供完整 JSON、回报成功，也会用对照试验推翻早期判断。
13. 这些是 11-11 快照中的人工确认计数，不是故障率。旧导出 D108 的一组回复声明 114 条、只存 60 条；11-12 晚间已补齐旧缺口和新增回复（现为 116 条），以下历史人数仍限于原归类证据，不追溯当成全量重审。

## 范围、计数和排序方法

11-11 人工基线读取了 **99 个 Discussion、164 个 Issue，共 263 个线程、1,275 条正文／评论／回复**。其中 Ashley-QwQ 的 **234 条**全部排除在用户需求和故障计数外，只用于核对我们答过什么、承诺过什么。旧快照有 242 个非 Ashley 账号；这包括维护者和贡献者，不能直接当“242 位客户”。需求和问题计数另排除了能明确识别的维护者 `JiaFeiMiao-K-Cat`、`Catho168`；其解释和提议作为背景保留。

同一登录名在同一主题只算一次；不同主题可以重复。因此各行不能相加。Issue 搬到 Discussion、同帖中英文重复、转引他人发言都不增加人数。没有按点赞数、评论数或关键词命中数当需求票数。功能表计入明确要求的改进、工具、资料或教程；不会把每一个抱怨标定难的人都算作“要求自动标定”。故障表较宽，包含本人报告的问题、困惑及实际结果。

人数是人工确认的下限：完整范围已通读和归类，但短句、只贴图、只贴日志而无明确诉求的内容从严不归入人数。逐条纳入依据在 [evidence.tsv](evidence.tsv)，每个主题的账号集合在 [theme_counts.tsv](theme_counts.tsv)，全部线程目录在 [thread_index.tsv](thread_index.tsv)。`D107.c25.r7` 表示 Discussion 107 的第 25 条评论下第 7 条已导出回复，序号从 1 开始。导出没有评论永久链接／ID，所以引用用**线程 URL + 原发言日期 + 登录名**定位，不编造锚点。日期按 JSON 的 UTC 日期；它是评论日期，不代表实验实际发生时间。

排序用“不同账号数 × 成本等级”。成本 5：整条路走不通、反复耗盘／小时、数据读不回；4：常要重做一轮或换组合；3：效果受限或设置障碍；2：编辑和玩法不便；1：探索性增强。等级是本报告的判断，**不是平均损失、统计风险或每人都付过的代价**。同分优先硬失败；对只提出新玩法的需求保守给低分。原帖里的“几十张”不换算成具体数；同一人跨帖重复报的耗盘不相加。

只看到附件名称、正文和图片链接，未取得附件内容或独立检查照片。表中的“附图”“附日志”表示帖子有这类材料，不表示本次核验了照片质量、完整日志或 SHA。没有把先前研究中的预算估算当社区实测。

## 一、用户提出的功能和资料需求

每项给两条短转述，详列账号见 TSV。频次低而成本高的防睡眠、写入失败分诊，仍应进入 DP 首批工作。

| 优先分 | 主题；不同账号数 | 用户真正想要的东西；例子 |
|---:|---|---|
| 85 | R02 教程、示例、下一步：**17** | 让新手知道该点哪里、正常／失败长什么样，明确“重拍、再粗标还是进精标”。chenxwl 说没有示例、文字难懂；cmdcorp6534 建议把交互式示例放进程序。[I12 · chenxwl · 2026-11-01](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/12)；[I246 · cmdcorp6534 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/246) |
| 60 | R01 少耗盘、自动化和整合：**12** | Shiro7940 六张仍不理想，想一张盘扫描一组候选参数，再做精标；YinWie 希望整合 DP 的测量能力。也包括照片自动识别、边缘检测、几何模拟和扩大测量范围。[I47 · Shiro7940 · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/47)；[I123.c4 · YinWie · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/123) |
| 56 | R03 预设查找、识别、导入和编辑：**14** | 想直接找到自己的盘、看盘面照片、拿到可复制 JSON，并能新增／改名。fkiliver 找不到直接编辑入口；jyxjyx1234 指出截图数值不完整，要求 JSON。[I204 · fkiliver · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/204)；[D172.c3 · jyxjyx1234 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/172) |
| 45 | R04 买什么盘／光驱、看真实效果：**15** | 要“已知能看见”的组合及普通光照效果，不只漂亮展示图。Helimelon 已标定但太淡，想知道换盘还是换光驱；a690089735 要同时收集指定角度和较暗自然光下的结果。[D270 · Helimelon · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/270)；[D261 · a690089735 · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/261) |
| 27 | R05 平台、GUI 和开箱使用：**9** | Linux/macOS 用户需要完整图形流程，CLI 可执行文件不等于好上手；也有人直接要 DP 可用 EXE。Linux Mint 用户抱怨打不开 CLI、兼容层也不稳；macOS 需求强调必须完整复用所有预设参数。[I264 · seagull-joy · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/264)；[I254 · H4CNPE · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/254) |
| 22 | R06 文件／音乐／图案共存：**11** | 礼物盘、旧 CD 机听歌、老游戏混合轨、多处放数据、外圈留余量。EMZ1 手拼内圈音乐外圈图案；EastCation 要保留数据轨、音轨、间隙和索引。[D181 · EMZ1 · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/181)；[I224 · EastCation · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/224) |
| 20 | R09 刻录稳定性、缓冲、防睡眠：**4** | 刻录前能检查，刻坏后能解释，必要时走外部工具。kasumikira 刻到一半电脑睡眠；anyezhixie 希望提供更大的缓冲设置。后者报告调大 ImgBurn 缓冲后成功，但其 AI 根因解释未获独立证实。[I131 · kasumikira · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/131)；[I38.c1 · anyezhixie · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/38) |
| 15 | R11 翻译和错误文字：**5** | 不只翻按钮，还要翻报错、教程和排错操作。Demos25 要语言切换；ollinquetzalcoatl58-glitch 面对中文错误无法继续。[I19 · Demos25 · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/19)；[I149 · ollinquetzalcoatl58-glitch · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/149) |
| 12 | R07 素材、参数历史、输出管理：**3** | 改参数能回退、保存动作明确、大镜像知道存在哪里、素材移动后能重新链接。SODIUMWATER 要可回溯参数历史；E0x72-21 的素材改名或移动后从工程中消失。[I81.c2 · SODIUMWATER · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/81)；[I306 · E0x72-21 · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/306) |
| 12 | R10 可擦写介质／失败后再用：**3** | 正确识别已格式化的 DVD+RW；明确哪些失败盘还能用。Doctor-shengru 要修正空白检测；YukaiP 以为可以忽略数据重刻 CD-R。后一项不能照字面实现，应解释一次写入并提供合法替代路线。[I290 · Doctor-shengru · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/290)；[I251 · YukaiP · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/251) |
| 12 | R08 可信预览和编辑辅助：**6** | 模拟几何差异、显示数据区边界、接近实物的底色、高对比处理、环形文字／长图。zooma-e-migliora 要设计页也显示数据占位；sirius-ookami 发现浅色画布掩盖了实物上明显的白底边界。[I156 · zooma-e-migliora · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/156)；[I105 · sirius-ookami · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/105) |
| 12 | R13 BD、多层、小盘测量：**4** | BD 自动标定、支持非标准容量／多层、miniDVD 流程。LTVA1 问 BD 能否同样省盘；bczhc 的 BD-RE XL 参数被单层上限挡住。[D178 · LTVA1 · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/178)；[I253 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/253) |
| 5 | R12 彩色、视差和全息：**5** | 有人想要更炫的成品，也有人做了插件。Harvie 要 3D 全息；drewmedina55-ux 发了实验性 3D 插件。它们是探索需求，不能挤掉少耗盘、能看懂的基础流程。[I309 · Harvie · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/309)；[D258 · drewmedina55-ux · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/258) |

补两点边界：R06 的 11 人提出的是不同布局需求，不能说“11 人都要完整混合模式 CD”；R13 的小盘部分主要来自实测和流程补齐，并非人人要求支持任意多层盘。维护者提出的盘片新分类方案 D282 很有价值，但没有当成外部用户的一票。

## 二、用户踩过的坑：频次、成本、根因和静默失败

### 总排序

| 顺序 | 问题范围 | 账号数 | 成本等级；优先分 | 本报告判断 |
|---:|---|---:|---|---|
| 1 | P01 标定／几何／阶段成图失败 | 60 | 5；300 | 最大、最伤人的门槛，先处理 |
| 2 | P03 写入中断／封盘失败 | 23 | 5；115 | 一次失败就可能损失一张盘；先分清失败阶段 |
| 3 | P04 预设错配 | 24 | 4；96 | 会把用户带入“照抄仍失败”的反复试错 |
| 4 | P02 可见度、光照、效果预期 | 32 | 3；96 | 容易误认成需要再标定、再烧一张 |
| 5 | P06 参数／素材／状态交接 | 16 | 5；80 | 含已确认的软件缺陷，也有误操作、未定根因 |
| 6 | P08 DP 计时与流程问题 | 17 | 4；68 | DP 自己必须处理，不能宣传为通用免校准 |
| 7 | P05 模式、容量、地址和单位 | 13 | 4；52 | 提前检查最划算 |
| 8 | P10 局部错位和模型不够 | 15 | 3；45 | 全局拟合数字好看不代表局部都正确 |
| 9 | P07 图案数据影响读写 | 8 | 5；40 | 人少但后果大，涉及数据可靠性 |
| 10 | P09 平台、运行／导出及语言障碍 | 11 | 3；33 | 有明确修复实例，也有待排查启动问题 |
| 11 | P11 原理和操作概念误解 | 15 | 2；30 | 多数是前面问题的诱因，不再当独立故障加总 |

下文少量术语：MID／ATIP 是盘报告的身份代码；残差是模型和测量之间的差；抖动是重复测量的波动；CAV 指盘转动角速度基本恒定。它们都只是证据的一部分，单个数字过线不等于成品已验收。

### 1. “只有圈，没有十字”反复出现；粗标成功不等于能刻角色

**反复出现的症状：** 同心圆可见，径向线卷成极细螺旋，或只剩两处鱼钩；用户不知道下一步描哪条线。粗标宽带主要随地址和半径分布，即使角度映射不准也可能很清楚；角色和细十字对累积角度误差敏感。这能解释许多线程，但不能凭“有圈”就断言写入链路、介质和所有参数都正确。

**线程确实解决的：** timetheonce 微调预设尺寸后确认成图；VANsMAN-BBS 的 miniDVD 从更接近的预设开始后确认成功。它说明起点有用，不说明随便换成 DVD-R／DVD+R 预设都通用。[I16.c2 · timetheonce · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/16)；[I14.c5 · VANsMAN-BBS · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/14)

**仍未解决的：** teomantoscu 把边界重复描成 7–8 段、40–80 点，RMS 仍约 0.45–0.54 mm，精标只有两处短钩，不能达到覆盖要求；轨距形状不适合模型只是他的猜测。mmnjrzdgn 只有宽带估计、角度条纹不可靠，仍继续生成下一阶段，以为“粗标图印得好”代表几何已经好。[I249 · teomantoscu · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/249)；[I297 · mmnjrzdgn · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/297)

**成本有实数的：** will86863 说 25 片装已经耗完仍失败，未证实是光驱还是盘；XBBDYF 标题说已花 20 张，最后说没精力继续；VIVAMAO 已用六张仍只有鱼钩。不要把作者建议的“再来一轮”视为低成本。[I91 · will86863 · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/91)；[I65.c8 · XBBDYF · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/65)；[D316 · VIVAMAO · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/316)

### 2. 写盘报错必须按阶段分诊，不能一律归咎用户

**有对照支持的供电问题：** anyezhixie 换新光驱并把旧光驱放到其他电脑对照后认为供电不稳；此前试过两种盘、十几张。但同帖原作者 69wj7c7fzs-dev 换光驱后仍失败。因此结论只适用于前者，不是整帖统一根因。[D104.c2.r2 · anyezhixie · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/104)；[D104.c3 · anyezhixie · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/104)；[D104.c3.r1 · 69wj7c7fzs-dev · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/104)

**写入路径差异：** IceyVanci 的 SN-208FB 用基于 IMAPI2 的程序反复在中途失败，至少三张报废；换 Nero 的链路能得到图案，但仍有固定空白圈。Lakida0 的同型号不同固件也失败。可以把 IMAPI 路径列为嫌疑和绕行方式，不能据此证明 Windows API 或 USB 硬件就是最终根因。[D107.c50 · IceyVanci · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D107.c50.r2 · IceyVanci · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)

**数据能刻、图案不能刻：** xTomeku 的 GSA-T50N 在白底开始处多次报寻迹／聚焦错误，同批盘的普通视频数据却成功并验证；开“读取兼容”仍失败。laiyoi 的 GU90N 多在约 92% 失败，随机数据似乎正常。均未见最终解决。[I317 · xTomeku · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/317)；[D257 · laiyoi · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/257)

**睡眠中断：** kasumikira 刻了大半电脑睡眠，只留下半截，虽然可见部分效果还能接受。这里需要阻止系统自动睡眠，不能靠提醒用户一直盯着。[I131 · kasumikira · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/131)

**别把 0% 当没碰过盘：** pinpinking0930 连续跨版本报告 RAW DAO 在导入区停止。维护者根据日志指出缓冲已有数据、尚未进绘图区，但导入区可能已经写了；后续 ImgBurn 也报写错误，普通音乐能烧，最终根因未定。早期“未实际写入可以继续用”的回答有前提。[I182.c3 · JiaFeiMiao-K-Cat · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/182)；[I196.c1 · JiaFeiMiao-K-Cat · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/196)；[I196.c2 · pinpinking0930 · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/196)

### 3. 预设不通用，不全是用户抄错

**已知真实批次差：** bczhc 同一次购买的五张 Verbatim 43284 中，有一张内圈码不同；交替拿两张做校准，出现一轮向上、一轮向下。最终分别给不同内圈码标定。Joshu-Unit 在同帖报告约 20 小时、40 次尝试，两张可擦写盘变得不可读。它们不是“40 张一次性废盘”。[I67.c6 · bczhc · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/67)；[I67.c8 · bczhc · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/67)；[I67.c3 · Joshu-Unit · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/67)

**同 MID 的反例：** RichardYi-SYSU 的 `RITEK-F16-01` 直接套另一套参数失败；pugod124 和 netham45 的 `CMC MAG. AM3`、不同内圈后缀，互换参数不行。身份信息应该包含盘型、商品、MID、内圈码、容量语义和批次，最后还需本地验证。[I60 · RichardYi-SYSU · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/60)；[I119.c1 · pugod124 · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/119)；[I119.c3 · pugod124 · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/119)

**不要把所有扇区差都叫批次差：** 同一 DVD 的 2,298,496 与 2,297,888 也可能来自软件所报总量与安全可写量的差别，正好差 608。用户在 I87、I183 已解释这个现象。只凭容量差不能推出母盘不同。[I87.c3 · bczhc · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/87)；[I183.c5 · bczhc · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183)

### 4. 可见度差，有时换介质有效，有时只是观察条件，有时仍无解

**预期落差：** nyannurs 在 43411 上标定太难而放弃，换 43438 后只能勉强看见；netham45 说盘用完了、不准备再买这种 CD，DVD 效果更好。有人买了新盘甚至新光驱，仍得不到 README 的效果。[I25.c4 · nyannurs · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/25)；[I25.c9 · nyannurs · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/25)；[I79.c2 · netham45 · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/79)

**确有组合差异：** exotic-namruth 在 GUE0N 上的 HP/CMC DVD 抽查到预期 `A5/92` 数据，扫描也无明显对比；11 月 11 日换 `MCC 02RG20` 的 Verbatim DigitalMovie、同光驱 4× 后，确认肉眼可见。帖子写“100%”，但贴出的扇区抽查不能当全盘逐字节验证。薄光驱功率偏保守、染料具体化学成分都是用户的解释，未测写功率，不能当已证物理根因。[D231.c1.r1 · exotic-namruth · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231)；[D231.c1.r4 · exotic-namruth · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231)

**没有统一配方：** Saxarok317 的 GSA-T50L 对 CD 做了读回、交织检查和角区重建，仍缺可见对比；这一组合未见解决。与此相反，GP60NB50＋Verbatim 43437 已有人三张成功，但成品仍淡。不能给出“所有薄光驱不行”“所有 CMC 不行”“永远最低速最好”的结论。[I295 · Saxarok317 · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/295)；[D303 · suedexlee · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/303)

**静默失败：** “烧录完成”“能读出字节”和“有可见图案”都可能成立其中两项而第三项失败。DP 应在成功页分别显示，不能只放一个绿勾。

### 5. 参数状态会悄悄骗人：有已修复缺陷，也有新问题没定论

**确认解决的保存／同步缺陷：** Sliicy 发现保存预设后旧轨距系数残留；TMarccci 的精标线直、实际角色图不对。维护者提交同步和标定记录持久化修复，用户更新并改工程几何后确认图案清楚。不能把它继续描述成最新版必现问题。[I184.c5 · Sliicy · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/184)；[I184.c6 · JiaFeiMiao-K-Cat · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/184)；[I184.c7 · TMarccci · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/184)

**错误迭代基础：** SODIUMWATER 报已有非零系数的标定盘再次反推会退回旧形状，把系数清零再生成后正常。线程只支持“与原生成系数的处理有关”的判断；当前 DIS `docs/CALIBRATION.md:103` 已写入带系数重复校准检查。[I92 · SODIUMWATER · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/92)；[I92.c5 · SODIUMWATER · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/92)

**人工复制也会静默错：** jyxjyx1234 从截图抄数失败，后来发现末尾还有看不见的科学计数法；krikkirk 把内半径贴错，修正后才知道原因；sanitysama 曾导出时误用较早修正文件。[D172.c3.r3 · jyxjyx1234 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/172)；[I82.c3 · krikkirk · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/82)；[I171.c13 · sanitysama · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171)

**还没定论的不能顺手关闭：** Iron237 用同一套参数做纯图正常，加随盘文件后内／外圈两种布局都扭曲，已用两张 DVD+R 对比。维护者检查生成算法后更怀疑写入链路／策略，线程仍开着。这是**根因未定**，不能说已证实光驱故障。素材移动后静默消失也是另一类结果丢失，未见修复回复。[I289 · Iron237 · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/289)；[I289.c1 · Catho168 · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/289)；[I306 · E0x72-21 · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/306)

### 6. 模式、容量、备用区：看似相同的数据并没有写到同一位置

**CD 的 700 MB／约 807 MiB：** 音轨每扇区 2352 字节，数据容量常按 2048 字节计；把 WAV 当数据文件刻会走错路。I18 的双语答复给了字节数、CUE 选择方法，发帖人随后确认成功；I179 后来仍有人问相同问题。另有真的多出 2–4 扇区的容量问题，不能把它和单位误读混为一谈。[I18.c2 · Catho168 · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/18)；[I18.c3 · Faliureatlife · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/18)；[I179 · knb8s7j6yb-debug · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/179)

**DP 自己的 CD 模式坑：** FanJZSS 的网格 ISO 被 AnyBurn／ImgBurn 识别为 Mode 1，无图；按 Mode 2 Form 1 配套 TOC、用 cdrdao 后确认网格清晰。这是错误编码路径的成功写入，属于**静默失败**。[D107.c57 · FanJZSS · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D107.c57.r2 · FanJZSS · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)

**DVD 总量不等于可写量：** Ashley 的 I183 本身不算用户反馈。domerawind 用较短的正确容量重新导出后确认正常封盘，维护者承认需要区别总量、可写量和模式开销。DP／DIS 都应把“几何分母”与“本次写到哪里”分开，不能简单改扇区数却不重算几何。当前 DIS 的 `WindowsImapiBurner.cs:55` 已明确不再重复扣旧的 608 估计。[I183.c11 · domerawind · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183)；[I183.c13 · JiaFeiMiao-K-Cat · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183)

**BD-RE 备用区改变物理地址：** bczhc 的 43614 反复刻都没有任何明暗，后查出格式化默认启用了缺陷管理及备用区；光盘容量从 12,219,392 变成 11,826,176。只改写入选项不够，按无备用区重新格式化后可见。文档虽提条件，用户说不知道怎样操作。这是**已解决的布局问题**，不是标定精度不足。[D219.c3 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/219)；[D210.c1.r8 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/210)

**多层和 XL 不等于容量乘二／乘三就行：** bczhc 以单层扇区数写 XL，图只占一部分、粗标推到错误外径；Rhiig 同时踩到 8.5 GB、Wine 和工程转 CLI 障碍。当前 DIS 预设文档仍限定单层 BD，不能把插件或手工成功算主程序全面支持。[I253 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/253)；[D285 · Rhiig · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/285)

### 7. 图案数据本身会影响读写；漂亮的盘可能读不回

**复现到具体数据块的读回问题：** bczhc 在 DVD-R、DVD±RW 和多台光驱交叉测试，普通随机数据可读，图案重复数据会在特定区域报 `L-EC uncorrectable error`；对相同位置替换桥接处理后的数据，部分阶段先改善、仍有别处失败，后来报告读通。盘／光驱／块位置的对照比“我觉得是盘坏了”有用得多。[I90.c7 · bczhc · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90)；[I90.c18 · bczhc · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90)；[I90.c22 · bczhc · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90)

**根因层次要分开：** 已有证据支持“特定纹理、编码状态和位置影响某些组合的可靠读写”；EFM+ 状态、低频偏置和长游程是机制分析，不能把未经测量的实际坑岸波形当事实。维护者最初也明确未完成原介质复现，不认为是“缺 ECC”。后续 `0x9B` 和桥接方案有用户实盘反馈，但不等于全型号保证。[I90.c5 · JiaFeiMiao-K-Cat · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90)；[I90.c33 · JiaFeiMiao-K-Cat · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90)；[I90.c34 · bczhc · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90)

**DP 更不能自称已免疫：** LTVA1 在我们的 D108 反复报告图案失败、卡住、外圈扭曲，普通随机数据和某些纹理又成功；加随机起始区改善过一些情况，仍不能解释全部 ISO。11-11 的 D108 导出少了 54 条回复，不能从旧文件追到完整结论；本轮已在新快照补齐，未重新归类旧表中的尝试。POPCORNBOOM 也独立报告长片 `A5` 可能在刻录时失去寻迹。[D108.c18.r46 · LTVA1 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108)；[D108.c18.r56 · LTVA1 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108)；[D207 · POPCORNBOOM · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/207)

### 8. 局部接缝、外圈外推、计时假象：DP 的质量门槛有实际来由

**不是所有弯曲都能多项式修平：** WindowsNoEditor 比较同一读盘光驱、不同写盘光驱和盘型，联想 CD 的约 33.4 mm 接缝在非 LG 写盘上也出现，POSO／Banana 没有，推翻了只怪 LG 写入策略的早期猜测。bczhc 的 Hirucy BD-RE 有不自然弯折，三次式拟合不了，盘质只是猜测。[D107.c32 · WindowsNoEditor · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D266 · bczhc · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/266)

**测到哪里就该承认到哪里：** FanJZSS 初次外圈偏，扩大测量后报告外圈正常；后来为了追最外 LBA 还用了 `--chi2-abort 100`，这是放宽拒绝条件，不能当默认流程的质量保证。[D107.c27 · FanJZSS · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D107.c44 · FanJZSS · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)

**计时不是只要程序跑完就行：** FanJZSS 曾等了一个多小时；Ashley 后续承认把失败读取中的 Windows 15.625 ms 定时器周期误当主轴。ShiroiTree 发现低相干区被丢弃时会误报 CAV；WH14NS40 需重新放盘并用 `--speed keep`；lulifeng 的 SDRW-08D2S-U 在 16 扇区读和 keep 后改善。各组合要记录读速、实测转速、缓存路径、噪声和版本。[D107.c3 · FanJZSS · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D107.c7 · Ashley-QwQ · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D107.c29 · ShiroiTree · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[I171.c8 · sanitysama · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171)；[D302 · lulifeng · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/302)

**CD 还差沿轨常数／路径信息：** FanJZSS 后来撤回“关延迟交织就直”的初步说法，承认复现不出，可能选错 WAV；最终开启交织配约 −105 帧才直。必须保留这个更正，不能把前一条做成教程。[D107.c60.r3 · FanJZSS · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)

### 9. 安装与文档要有“原机验证”的闭环

jurczenko91 的 DIS 1.5.0 在 Windows 11 早期版本启动即崩，维护者调整应用的 CET 配置、给 CI 包，用户在原故障电脑撤掉临时覆盖后确认正常启动。修复是在 main／CI 包，不自动等于原 1.5.0 Release 已替换。DP 的 YukaiP 另报告 BAT 无反应，后来能生成 ISO，但卡在 timing 并重复建议已试过的速度；问题未闭环。[I229.c2 · jurczenko91 · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/229)；[I251.c5 · YukaiP · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/251)；[I251.c7 · YukaiP · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/251)

英文界面缺失 I19 有用户确认 1.3.4 解决；I149 仍出现中文内部错误。按钮翻译、内部异常、教程和平台安装应分别核查。[I19.c3 · dackydeyb · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/19)；[I149 · ollinquetzalcoatl58-glitch · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/149)

### 有明确代价的个案：不能拿成功帖子掩盖成本

| 用户 | 原帖实际代价和结果 | 解读边界 |
|---|---|---|
| will86863 | 一盒 25 张已经耗完，仍失败。[I91 · will86863 · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/91) | 未证实盘质／光驱；不能把软件回复的猜测写成定案 |
| XBBDYF | 已用约 20 张、几小时，最后说没精力继续。[I65.c7 · XBBDYF · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/65)；[I65.c8 · XBBDYF · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/65) | 是停止投入的明确迹象，没看到后来成功 |
| QianLieXian | 先报六张失败，后帖更新说失败案例累计约 20 张，最后成功。[I40 · QianLieXian · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/40)；[I69 · QianLieXian · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/69) | 同一人的演进，不相加成 26 张 |
| Joshu-Unit | 约 40 次、20 小时；用 DVD-RW，两张过程中不可读。[I67.c3 · Joshu-Unit · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/67) | 40 是尝试次数；不可读的两张是否永久报废未证实 |
| JoshAtticus | 11 张不成功后才找到可用参数。[I260 · JoshAtticus · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/260) | 单人个案，不是这种盘的平均预算 |
| Paulus05 | 说耗掉“几十张”，最终发预设。[I277 · Paulus05 · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/277) | 不能推成具体 20、30 或 40 张 |
| LawsonWo | 七张做首次 CD 标定，成图可接受但仍有一处接缝。[D275 · LawsonWo · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/275) | 标定方法成本与额外失败成本没有拆开 |
| SOra-WiND | 同一张 CD-RW 擦写十几次，最后给参数。[D243 · SOra-WiND · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/243) | 省盘数但仍花时间；RW 不是零成本 |
| RainMeoCat | 前四张校准，第五张完成。[D125 · RainMeoCat · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/125) | 与 I77 为同一份搬帖，不重复统计 |
| FanJZSS | 手工十几次才看到径向线；计时路线后成图仍略歪。[D107.c17.r1 · FanJZSS · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) | 后来扩大范围、改参数的反馈也保留，不把第一次改善当最终精度 |

这些个案解释了为什么防止再浪费一张，比增加一种视觉特效更急。缺数字的帖子只记“反复”“一天”“放弃”等原意，不替用户估算金额。

## 三、DIS 维护者和社区做对了什么

| 做法 | 有结果的证据 | DP 可直接学的部分 |
|---|---|---|
| 用最少的新动作让用户往前走 | I14、I16 从接近的预设起步后有人成功；I28 的 DBPolp 看解释后完成标定并发参数。[I28.c6 · DBPolp · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/28) | 回答必须有下一步和成功样子；优先用已有盘、已有记录继续判断 |
| 用白话拆开单位和操作 | I18 不只讲公式，还给“选 CUE、按音频刻”的动作，原作者确认解决。[I18.c3 · Faliureatlife · 2026-11-02](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/18) | 报错直接说明文件应由哪种模式写，不让用户自己换算 MB |
| 让资料有完整模板 | zhiyuan338 写盘型、设备、速度、版本、最终参数和验证边界；rroki-mo、leas1r 随后复用格式。[I165 · zhiyuan338 · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/165)；[I205 · rroki-mo · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/205) | 提供一键生成同样结构的报告，保留完整数字，避免截图抄写 |
| 收录参数后明确回执、保留贡献者 | I35、I36、I41 收到“已在 #45 采纳”；当前 `docs/DISC_PRESETS.md:45` 记录来源和贡献者 | 每条社区记录显示谁提供、在哪个版本纳入、哪些组合未验证 |
| 能拿到复用成功的回报 | Banana CD 参数收到 tuzhiLiu、Nelocompne 的独立成功回报；Acer 参数也有 kasumikira 复用成功。[D169.c1 · tuzhiLiu · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/169)；[D169.c2 · Nelocompne · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/169)；[D216.c1 · kasumikira · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/216) | 独立复用单列，别把同一作者的二次回复算第二个验证者 |
| 允许有用的小工具先独立演进 | EternalEve 的半自动工具下，anyezhixie 从识别失败到“成功了”；D122／I123 的照片识别工具公开小样本和失败边界。[D141.c2.r2 · anyezhixie · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/141)；[I123 · HiroGitea · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/123) | 可以接外部校准路线，清楚写支持范围；不要为统一界面提前承诺稳定 |
| 新版问题回到原机确认 | I184 参数修复、I229 启动修复均有用户后续确认。[I184.c7 · TMarccci · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/184)；[I229.c2 · jurczenko91 · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/229) | 状态分“已定位／已提交／用户原环境验证／已发布” |
| 做对照并更正早期解释 | I67 从“盘用坏了”改为不同内圈批次；D107 接缝从“也许 LG”改为不只 LG；D231 后续补换介质成功 | 数据库记录修改理由和最新结论，旧猜测保留为历史，不并排当事实 |

也有值得改善的回答：早期多次建议“问 AI”“等文档”没有给够操作；I134 首条回“先标定”，用户随即解释根本写不进去，后来才对上容量；I13／I49 早期把封盘错误当不影响成图，不能推广为所有同码错误可忽略。I288 维护者明确认为计时方案兼容性和稳定性还有限，这是 DP 应回应的真实顾虑。[I134.c1 · JiaFeiMiao-K-Cat · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/134)；[I134.c3 · JiaFeiMiao-K-Cat · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/134)；[I288.c1 · Catho168 · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/288)

## 四、DP 应该做什么

以下按“防止高成本失败 → 减少试错 → 扩玩法”排序。源码位置相对只读的 **`D:/disc-probe/.claude/worktrees/webui-backend`**；只核对静态代码与文档，不把函数存在当实盘／整条界面已验收。DIS 核对到 HEAD **619ec75**。先前两份本地研究用于定位代码、理解六类体验问题；社区计数、耗盘和结局均重新回到本次 JSON。

DP 工作树 HEAD 为 `6fba5eefea0e8e592bb901faa9f9bed07df395c4`；不据此假定工作树无未提交改动。已读核心文件的内容哈希见 [source_context.json](source_context.json)，便于以后区分本次状态和后续实现。

### Add：应补的东西；已有但入口不够明显的也标出

| 优先 | 建议及依据 | DP 落点；现状与验收方向 |
|---|---|---|
| 1 | **按症状排错，先保住剩下的盘。** “没图”先区分无任何对比、有圈无臂、细线扭曲、整体太淡、写入失败；先看旧盘／旧日志再建议重刻。[I91 · will86863 · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/91)；[D231 · exotic-namruth · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231) | **已有部分，需显露和补齐。** `discprobe/guide.py` 的下一步、README 打光说明已存在；`imagecheck.py` 只做刻前设计检查，`rings.py`／`ringscan.py` 提供纹理测试路线，成品数据读回仍需独立检查。给 `web/home/burn.js` 的结果页接上分诊；每条建议明确是否耗盘。不能把 rings 检测的用途误说成完整几何校准。 |
| 2 | **预设必须识别到盘批次和写入路径，允许“不知道”。** 保留 MID、内圈码手录／照片、商品、总／可写扇区、光驱固件、工具及模式；候选只当参考。[I67.c6 · bczhc · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/67)；[I119.c3 · pugod124 · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/119) | **关键缺口。** `discprobe/webui_catalog.py:42` 的测量去重键目前主要是介质、MID、光驱；同 MID 同光驱的两批盘可能合并。`calibrate.py` 的 `--mid` 检查也不是批次证明。补独立 batch/path ID；同 MID 不同内圈码不得自动覆盖。PRODUCT 的“认出是哪批盘”仍须兑现。 |
| 3 | **一键问题报告和安全分享表。** 自动带版本、命令、设备、扇区模式、结果范围、停在哪一步、失败码、图案参数、是否已写盘。去掉本机用户名、无关目录及私人照片。[D235.c1.r1 · taniyareece7329-create · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/235)；[I196 · pinpinking0930 · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/196) | **已有日志，缺面向用户的完整交接。** `geo.py` 写 `targets.csv/summary.json`；`webui.py:443` 后任务目录有日志和事件。新增打包／预览导出，区分全盘验证与抽样；不要让新手手动翻终端历史。 |
| 4 | **参数与素材的版本链。** 保存工程／生成镜像时同时保存准确几何、修正来源、原图或可重连素材清单、模式与 hashes；界面显示这次真正用的那套。[I184.c5 · Sliicy · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/184)；[I306 · E0x72-21 · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/306) | **已有部分，需补齐。** `design.py:175` 用相对素材路径、临时文件后替换，整文件夹移动更稳；但 `Project` 主要是图层，未等于打包素材、完整标定快照和历史。`webui.py:483` 保存绘图网格也不能替代可编辑源工程。缺素材时应报失联并允许重连，不能悄悄消失。 |
| 5 | **把可省步骤的路线放到第一屏，同时说耗盘和限制。** 提供“测量 → 校准 → 套回 DIS／独立刻图”的正常出口。[I47 · Shiro7940 · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/47)；[D107.c17.r1 · FanJZSS · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) | **大部分已有，先显露。** `python -m discprobe calibrate`、`guide`、`disexport --install`；`calibrate.py:1` 已串步骤，`disinstall.py:78` 有合并安装、备份／校验。不要让用户继续手填五个数。首次预算沿用 README 的 DVD 至少两张、CD 至少三张，别宣传每种情况只用一张成品。 |
| 6 | **程序内短教程，中英错误同步。** 一张图说明刻的是哪一面、为什么有圈没图、中心孔是哪圈、怎么看成品；完整示例按按钮而非按公式组织。[I246 · cmdcorp6534 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/246)；[I149 · ollinquetzalcoatl58-glitch · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/149) | **已有引导，需可发现、可走通。** `guide.py`、`i18n.py`／`zh.py`、`web/ui.js`；PRODUCT 已定中英文同步。加异常路径的本地化与“复制报告”，避免英文按钮后直接吐中文或 Python 堆栈。 |
| 7 | **可擦写流程和自动睡眠抑制。** 校准练习支持 RW；区分可覆写、不是真空盘、曾写导入区但失败。[I290 · Doctor-shengru · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/290)；[I131 · kasumikira · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/131) | **未找到完整实现。** `burner.py:50` 一律要求新核验的 blank；这是明确保护，但不等于 DVD+RW 覆写流程。应另做明确的覆写入口和资料处理提示，不放宽一次写入介质保护。在 `burner.py`／`tools/burn_imapi.ps1` 的已读写入链路未找到阻止系统睡眠的实现；需按平台加入、结束后释放。 |
| 8 | **编辑器的数据区占位、失真模拟、质量档说明。** 显示孔、可写区、留给数据的位置；说明 5 µm／抖动的时间和清晰度权衡，提供环形排字辅助。[I156 · zooma-e-migliora · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/156)；[D108.c17.r2 · LTVA1 · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108) | **已有部分。** `design.py` 有位置、旋转、阈值、裁剪；`imagedisc.py:34` 和 CLI `--cell-um` 已有 20/10/5 µm 档。`simulate.py` 和 `web/home/sim/` 是模拟入口，不能拿预览承诺自然光可见。环形文字和长图缠绕仍可先导入外部生成的图。 |
| 9 | **文件／音乐／图案和多层作为独立后续路线。** 先做可读数据区与安全占位，再考虑 CD 播放器只播音乐。[D181 · EMZ1 · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/181)；[I224 · EastCation · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/224) | **主要仍缺。** `iso9660.py` 有文件系统能力不等于完整混合轨、MDF/MDS/NRG 或音乐编辑。PRODUCT 说要导入 DIS 工程，但在本次检查的 `design.py` 格式、CLI 入口和 Web API 未找到完整 `.discproj` 导入转换链；不要宣称已有。`bdexport.py:166` 明确限单层 DIS 预设。 |

### Avoid：DP 也会踩的坑，以及具体防线

| 优先 | 应避免的失败；证据 | 检查、默认值和提示；DP 落点 |
|---|---|---|
| 1 | **把发完数据、封盘完成、验证完成、成图成功写成同一个“成功”。** [I196.c1 · JiaFeiMiao-K-Cat · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/196)；[I90 · bczhc · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/90) | `burner.py:247` 已让结果带 `verified=False`，应让 `web/home/burn.js` 保留这个区别；分别记录写入调用返回、封盘、读回（全盘／抽样）、人工观察。失败后禁止自动重试同张一次性盘。别因进度到 100% 或图看起来完整就宣称数据可靠。 |
| 2 | **为图案用了错误的 CD 扇区模式。** [D107.c57.r2 · FanJZSS · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[I179 · knb8s7j6yb-debug · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/179) | 生成文件和 TOC／CUE绑定，保留模式、数据偏移、交织路径。`cd.py` 的 `write_cdrdao_toc` 已有，应让用户只选配套入口；`burner.py:42` 的 raw 子通道选择目前写着 future，Windows CD DAO 还未实现，不能把这个辅助函数算完整支持。 |
| 3 | **把测量用数据量、几何容量和安全写入量混用；不知备用区状态还照算。** [I183.c11 · domerawind · 2026-11-06](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183)；[D219.c3 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/219) | `guide.py:481` 的容量来源说明、`disexport.py`、`bdexport.py:147` 和 `burner.validate_media` 一起保持三者分开。保留原几何映射，只限制输出末端；避免固定减 608 后又减一次。BD 先识别 spare／格式状态，不能把一张没刻满的盘当预留区并向内平移。`bdexport.py:217` 已有相关拒绝检查，须显露来源。 |
| 4 | **用坏输入给出很漂亮的拟合。** [D107.c29 · ShiroiTree · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[I171.c13 · sanitysama · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171) | `geo.py:477` 独立检查点、`guide.py:255/265` 安装拒绝条件已有；保留原始观测，前后状态变了、样本不足、未测范围、修正文件不属于本次结果时清楚停止／警告。不能自动放宽 `chi2` 让流程通过，也不能建议把观测点拖到预测线上求通过，I86 有人实际这么做过。[I86 · 69wj7c7fzs-dev · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/86) |
| 5 | **把所有同 MID 盘和所有写入路径当同一套。** [I60 · RichardYi-SYSU · 2026-11-03](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/60)；[D107.c60.r3 · FanJZSS · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) | catalog 加批次；CD 的沿轨常数绑定整台读写设备、模式和工具。换盘批次、读写光驱或交织路径必须重新确认。`disexport.py:134` 已区分音轨测量与数据轨沿轨常数，不要给所有盘硬塞 206 或 −105。 |
| 6 | **整片重复纹理能生成，就默认能写、能读。** [I317 · xTomeku · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/317)；[D108.c18.r46 · LTVA1 · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108) | `imagedisc.write_iso` 已有随机起始区 `lead_lba`，CLI 默认亮纹理与 DIS 也不同；仍需记录所用暗／亮纹理、起始区、编码参数。提供可读性检查与外部刻录绕行；兼容处理改变了哪些像素／纹理必须可见。不要称 `0x9B` 或桥接已通杀所有介质。 |
| 7 | **无图就推销换驱动器、换品牌、降最低速。** [D231.c1.r4 · exotic-namruth · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231)；[I144.c1 · Rehtt · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/144) | 先在旧盘检查数据和光照。读速与写速分开；`burner.py:28` 当前默认选最低支持写速，应保留已验证组合的速度记录。Rehtt 报同组合 4×局部扭曲、8×正常，说明“最低速”只能是默认起点，不能是物理保证。 |
| 8 | **刚测通一台就承诺所有人无照片／一小时两张。** [I288.c1 · Catho168 · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/288)；[I251.c7 · YukaiP · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/251) | `PRODUCT.md` 的成功图景需要按介质和硬件注明边界。CAV 不成立、噪声大时给已试速度列表和终止出口，避免绕回旧建议；读计时不能确定 CD 数据路径的沿轨常数，BD CLV 路线也有额外假设。 |
| 9 | **缺素材、空字段、长卷标、异常输入到最后导出才失败。** [I206 · Doctor-shengru · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/206)；[I233 · H4CNPE · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/233)；[I306 · E0x72-21 · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/306) | `design.load`、`iso9660.py`、前端设计保存处做早检查；空字段明确代表 0 还是未填，保存前显示全部参数和有效区。素材移动可以重连，参数错误不覆盖上一次可用文件。 |

### Already better / already planned：已有优势与边界

| 与社区痛点的对应 | 当前能确认的 DP 答案 | 尚不能说的部分 |
|---|---|---|
| 反复拍照描点、耗盘高 | `timing/geo/disexport` 有第三方实用结果：li-yifei 同批 VHR12JP53SV4 8×清晰出图；suedexlee 的 CD 用计时＋DIS 一次精标，总三张。[D107.c12.r1 · li-yifei · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)；[D303 · suedexlee · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/303) | 不是所有用户只需两张；CD 沿轨常数和某些盘的轨距仍可能要图片辅助 |
| 不知道下一条命令和质量是否够 | `guide.py` 提示下一步，`calibrate.py` 串起检查／计时／几何／预设，`geo.py` 有独立检查点和 `guide.install_blocker` | 本次只核对实现；YukaiP 的重复速度建议说明实际体验还未完全闭环。[I251.c7 · YukaiP · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/251) |
| 手填参数、预设安装很难 | `disexport --install`、`disinstall.py` 合并用户预设，校验并备份；社区已有手填失误的明确反例。[I82.c3 · krikkirk · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/82) | 未等于 DIS 全工程无损导入，或社区预设能自动匹配每桶盘 |
| 手机拍完还要传电脑 | PRODUCT 已计划局域网手机入口、随机口令、自动读沿轨常数；已有 Web 局域网口令以及 `tilephoto.py`／`calscan.py` 等图像处理代码 | 后两者分别读色板照片、标定盘扫描，不等于已实现自动读沿轨常数。Web API 也不能证明完整手机采集、上传、自动应用全链已完成；PRODUCT 的规划不是验收 |
| Linux 只有 CLI，GUI 与写盘分裂 | DP 计时有 Windows/Linux 后端；本地 `webui.py` 是浏览器壳，核心任务关页仍继续，`calibrate.py:15` 也说明这个设计；PRODUCT 定无显卡降级 | 写盘平台不齐：`burner.py:82` Windows 当前只接 DVD，`adapter:239` 未接 macOS，BD 不在 `burn:250` 的允许类型中。macOS 社区移植不等于本地主线已完成所有功能 |
| 预览与最终用不同几何，误以为光照效果有保证 | `design.py:150` 共用设计渲染；`simulate.py`／Web 模拟提供观察入口；README 已有打光示意 | 共用渲染可减少状态差，但不能保证预览复现每种染料、光驱和灯光的真实对比 |
| BD 自动标定缺失 | 讨论里 11 月 7 日还说 DP 不支持 BD geo；**本地最新代码已不能这样描述**：`geo.py` 有 BD CAV 路线，`clv.py`、`bdexport.py` 和 `guide.py:298` 有 CLV、质量检查及导出入口。[D107.c47.r1 · bczhc · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) | 没有本次新实盘验证；CLV 的高拟合分数不自动保证最终轨距绝对精度，多层仍受导出限制 |

我们在帖里已答应／解释过的事项也要回查：Ashley 在 D107 说会在高残差时提示二次轨距比较，README 现已有这个说明；对 FanJZSS 解释过 CD 模式并已有 TOC 路径；D108 承认多次颜色模型和解释错误，也明确是早期实验。这些作者发言没有增加任何需求人数，更没有用来替代第三方验证。

## 五、可共享的盘片和兼容记录：先做种子，不能直接自动套用

这张表选的是能区分**成功／失败／仅测量**的代表记录，优先包含高成本反例和可复用资料；不是推荐采购清单。正文附图、外链附件尚未独立读取。可信度“较高”是记录链较完整、或有独立复用，不代表已由我们复现实验。缺光驱、缺 MID 或缺参数就明确留空，不靠品牌补齐。结构化同表见 [media_seeds.tsv](media_seeds.tsv)；全部候选线程见 `thread_index.tsv` 的 `preset_candidate` 列，需再清理才能入库。

| 盘／MID（含必要内圈码） | 光驱 | 结果 | 可信度与缺口 | 来源 |
|---|---|---|---|---|
| HP DVD-R / CMC MAG. AM3；HP CD-R / CMC | GUE0N T.02 | DVD 抽查数据对但无可见图；CD 也不明显 | 较高：有负结果及后续换介质对照；不是全盘验证 | [D231.c1.r1 · exotic-namruth · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231) |
| Verbatim DigitalMovie 8× DVD-R / MCC 02RG20 | 同帖 GUE0N | 4×刻录，换盘后确认肉眼可见 | 较高：同一人前后对照；无原始全盘验收 | [D231.c1.r4 · exotic-namruth · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231) |
| Verbatim 43284 DVD-RW / MCC 01RW4X；cd2260、cc9460、ca7240 内圈 | 该帖多台设备，参数需逐条核对 | 分内圈码给参数，互套会弯；两位用户有失败／重做 | 较高：多码对照、双方复测；不能合并成一条通用预设 | [I67.c8 · bczhc · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/67) |
| Sony DVD+R / SONY-D21-00；DRP5GG0001 | ASUS BW-16D1HT 3.10 USB | 纯图及精标正常；随盘文件内／外布局均扭曲 | 较高的问题记录：两张对照，根因未定 | [I289 · Iron237 · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/289) |
| Verbatim BD-RE 43614 / CMCMAG CN2 | 该条未明确；需补原日志 | 原先完全无图；无备用区重新格式化后解决 | 较高：操作与容量变化有后续成功；具体设备需补 | [D219.c3 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/219) |
| Verbatim BD-RE 25GB VBE130NP20SV1 / CMCMAG-CN2-000 | 该帖未明确 | 照片标定、ImgBurn 无备用区＋FastWrite 成图；仍轻微扭曲 | 中：参数及过程完整，独立复用见 D210；FastWrite 关闭未试 | [D210 · Sheng-Horizon · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/210) |
| Verbatim BD-RE DL 43759 / VERBAT IM1；cc7250-mk-bw2b051 | 该帖未明确 | 第一层可见但比单层淡，第二层放数据为手工实例 | 中：有参数、示例；不是 DP/DIS 正式多层支持 | [D250 · bczhc · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/250) |
| Hirucy BD-RE / MID 未给 | 该帖未明确 | 有局部不自然弯折、第一段缺失，三次式拟合不了 | 中：有失败记录；盘质猜测未证实 | [D266 · bczhc · 2026-11-09](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/266) |
| HP DVD-R CMC MAG. AM3；CD-R 97:15:17 | LG GSA-T50L SC04 USB | 外部工具可完成且 CD 读回重建；图案仍不可见；内置流式失败 | 较高：详细步骤与量化；尚无最终解决 | [I295 · Saxarok317 · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/295) |
| Verbatim DVD-R AZO 43729 / MCC 03RG20 | LG GSA-T50N RF07 USB | 图案 3 次早期聚焦／寻迹错误；同批普通数据可写可验 | 较高：速度及兼容选项对照；根因未定 | [I317 · xTomeku · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/317) |
| Lalasan／Thinkplus DVD-R / RITEKF1；DR5F6O-PW104 | hp SN-208FB HJ10 | 计时参数相近；IMAPI 中途失败，Nero 出图仍有固定空圈；JVC 蓝樱未成功 | 较高：多盘及工具对照；空圈机制未证实 | [D107.c50 · IceyVanci · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| VHR12JP53SV4 / CMC MAG. AM3 DVD-R | GP90NB70 1.00 USB | 原恒定轨距预设 8×清晰；二次离线残差 0.380→0.087°，新修正未刻 | 较高：有完整 targets 和身份澄清；成品照片当条未附 | [D107.c12.r1 · li-yifei · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| RiTEK Excellent X DVD+RW / RITEK-004-48；VW47H-01062 | FanJZSS 的 GP65NB60；复用者另机 | 计时＋修正后成图；Doctor-shengru 复用无需改参数成功 | 较高：有参数及独立复用；不能保证所有同 MID | [D191.c1 · Doctor-shengru · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/191) |
| Verbatim CD-R 43437 / 97:26:66；CWLHT-1579 A034 | GP60NB50 RF02 USB | 4233 kB/s CAV；计时＋DIS 一次精标，总 3 张，直但淡 | 较高：版本、步骤、误差及预设俱全；仍是单份组合报告 | [D303 · suedexlee · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/303) |
| Banana CD-R 80min；GSC-B-001 / Li190219DA+ | 主帖未明确；复用者未明确 | 参数有两人复用成功；一人指出 DIS 流式失败、ImgBurn 可用 | 较高：独立复用；缺设备，需补再入兼容矩阵 | [D169.c2 · Nelocompne · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/169) |
| Acer DVD-R / MCC 03RG20 | PLDS DH16ACSH JL3B SATA | ImgBurn 6×，校准通过，另一用户参数复用；原作者仍嫌对比低 | 较高：设备／参数齐，独立复用；几何成功不代表高对比 | [D216 · Helimelon · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/216) |
| JVC DVD+RW / RITEK-004-48 | LG BH16NS48 | Nero 4×，实盘图案正常；DIS 当时拒绝非空白 RW | 较高：完整模板及 JSON 链接，未测其他批次 | [I205 · rroki-mo · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/205) |
| Verbatim DVD-R 97176 Life Series / MID 未列 | Apple USB SuperDrive | DIS 1.4.1，4×，最终预设重刻图正常 | 中高：原保存 JSON 附件、明确验证边界；缺 MID／内圈 | [I165 · zhiyuan338 · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/165) |
| Mr.DATA DVD-R 8× / CMC MAG. AE1；CMDR47G-CAEMM07-002 | ASUS SDRW-08D2S-U USB | 3×，粗标＋精标后清晰；同容量 43533 预设失败 | 较高：型号、内圈、设备、过程和图链齐 | [I76 · skillhunter184 · 2026-11-04](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/76) |
| RITEK BD-R Pro 25G / RITEK-BR3-000 | LG BH16NS48 | 4×最终预设重刻正常；另一份同包装参数不适用的报告见 D241 | 中高：有 JSON／环境；需按内圈分批 | [I213 · rroki-mo · 2026-11-07](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/213) |
| GIGASTORAGE 银面 CD-R / 97:28:12 | 主帖未明确 | 网格盘确认；未刻最终图片，内圈码未记 | 中：不能因标题 Works Perfecly 就记成品 PASS | [I130 · arkwise · 2026-11-05](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/130) |
| RITEK ARITA CD-R RFD80M-79243 / MID 未列 | 该帖未明确 | 可见度极弱，作者不推荐，参数仅参考 | 中：有明确负面边界，缺设备和独立复用 | [D240 · IceyVanci · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/240) |
| 铼德 F16 DVD+R / RITEK-F16-01 | ASUS SDRW-08D2S-U A801 USB | 16 扇区读＋speed keep 后 geo 22级成功；两张盘测量接近 | 中高：量化测量；未明确完成图片验证，勿泛化成盘型定律 | [D302 · lulifeng · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/302) |
| PHILIPS CD-RW 12× 80min / MID 未列 | ASUS SDRW-08U9M-U | 一张反复擦写完成标定；另盘成品 | 中高：记录 JSON 和图链；省的是盘数，不等于省全部时间 | [D247 · MYLMMMM · 2026-11-08](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/247) |
| Sony DVD+RW / SONY-S11-00 | Pioneer BDR-209D | 4×可成图但几乎看不清 | 中：给参数及效果边界；需独立复用 | [I299 · Paulus05 · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/299) |

**入库时保留的最低字段：** 贡献者 login、帖子及评论日期、原始参数文件／文字来源、盘型／层数、商品号、MID／ATIP、内圈完整刻码、总扇区数与可写量各自来源、设备／固件／接口、读速与写速、刻录工具／模式／交织设置、几何测量范围、修正版本、剩余误差、是否真的刻图、读回是抽样还是全盘、光照条件、复用人数。照片和日志缺失要能表示未知，不默认通过。

**三条必须留在数据库里的负面信息：** `同名 ≠ 同批次`，`图案直 ≠ 对比高`，`字节能读 ≠ 光学效果好`。D296 的文字还出现相对二次项 `--9.565…E-08`，应作为待澄清输入，不能擅自删一个负号后发布“修好”的参数。D302 的两张 F16 测量一致只支持那两张，不能跟着帖子的推论写成“DVD+R 一律恒定轨距”。[D296 · MRFXStudio · 2026-11-10](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/296)；[D302 · lulifeng · 2026-11-11](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/302)

## 六、交付和复查

- [REPORT.md](REPORT.md)：这份报告。
- [evidence.tsv](evidence.tsv)：人工纳入的人数依据，只含主题、帖子位置、登录名、日期、URL。
- [theme_counts.tsv](theme_counts.tsv)：去重人数及账号集合；可查为何同一人只算一次。
- [thread_index.tsv](thread_index.tsv)：11-11 的 263 个线程目录、主题和预设候选标记；候选筛选不是可信度判断。
- [media_seeds.tsv](media_seeds.tsv)：下表的结构化版本，保留未知和失败。
- [audit.json](audit.json)：原始文件 SHA-256、范围与导出缺口。
- [source_context.json](source_context.json)：已读核心源码和文档的内容哈希及 HEAD 定位。
- [coding.py](coding.py)：人工标签和标准库统计；`python -I coding.py` 可重新生成计数与目录。它不联网、不读外部项目、不执行帖子内容。
- [review.py](review.py)：按线程／范围阅读 JSON 的辅助工具，去掉长代码、引用块及邮箱，仅供检查；最终短引述均在报告内。

11-11 原始文件 SHA-256：`discussions.json = ab0487985d0ca348e289bf0ef4f4f797899ea48098545b5073ad38a88b4af50d`；`issues.json = ef98688c855783731595904eb4efb1dab7af79044c96236615da4cbd1a2a86dd`。本次没有改原始数据和外部源码，也没有把已经解决的旧版问题当成 HEAD 仍未修复的缺陷。
