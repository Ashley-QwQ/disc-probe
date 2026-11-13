# DIS / DP 社区反馈记录：要吸收进 DP 的问题和建议

每次对比 DIS 的 issue 和 discussion 后追加。标定数值进 `data/community-calibrations/dis-github.json`，这里只记问题和想法。

## 2026-11-12 晚间（对比 11-12 快照；抓取时 UTC 已到 11-13）

### 本轮短报

- **变化：**DIS 的 Issue／Discussion 新增 **6 个线程、29 条发言**，涉及 21 个线程；旧正文修改 0 条，I81／I92 由 open 变 closed。另补齐 **57 条历史发言**（D108 54 条、D107 3 条），不算成今天新增。当前这两类共 **271 个线程、1,374 条正文／评论／回复**。PR 首次单独建基线：53 个 PR、115 条正文／评论／审阅记录，近期活动为 PR298 的一条新评论。DP 全量为 17 个 Issue、17 个 PR，共 162 条正文／评论／审阅记录；近期新增 9 条记录，分布于 #33、PR32、PR34。PR／DP 没有旧快照，不声称查明其正文编辑增量。
- **影响 11-15 alpha：**A6 要覆盖模型不足、固定完成偏移、范围外推、容量和超时出口；A2／A1 的照片修正需要保留原始证据、拒绝不可靠结果；A3 仍需真实成品验收；A4 要区分“有圈无臂”“对比弱”“写入失败”；A8 应保留“只模拟／未实盘”的限制。D0 预设互通、A2 照片 L 接入已有合入记录；这不等于下列新案例已解决。PR34 是 A4／A6 的待复审贡献，尚未合并。
- **校准库：**174 → **178 条**。新增 I311-1、PR298-1、PR298-2、I327-1；其中 I327 的成图结果为 `unknown`，三项轨距沿用起始预设。I311 的“完美贴合”来自独立复用者 SweetSourFox，原参数作者为 SodiumSulfate。D323-1、I86-2 原来已经收过，没有重复。D270 没有新数值，D316 只有目测改半径的建议，D322 的值在未下载的附件里。
- **边界：**只通过 `gh` 的 GraphQL 查询读取 GitHub；没有发帖、评论、反应、审阅、合并或推送，没有下载图片／附件，没有运行 DIS 或做实盘试验。原脚本复用、分页补齐和散列见[快照清单](../../goals/dis-community/data-20261113/manifest.json)，完整差分见[增量原文](../../goals/dis-community/new_since_20261112.md)。目录按 UTC 命名；采集窗口为 11-13 00:44:53–00:46:21 UTC，即多伦多 11-12 19:44:53–19:46:21。

### 等我们回复／复审的帖子（这里只给一句要旨，不发布）

| 帖子 | 目前轮到谁；建议要旨 |
|---|---|
| [DP #33](https://github.com/Ashley-QwQ/disc-probe/issues/33#issuecomment-6827622004) | **等我们跟进。**感谢授权三次原始 run 和扫描螺旋作回归；Linux 主线已获本人验证，把固定偏移与窄范围外推分开检查，后续给受限测试版本。 |
| [DP PR34](https://github.com/Ashley-QwQ/disc-probe/pull/34#issuecomment-6829466426) | **等我们复审。**收到 `6b740f6`，按旧结果不回 info、盘型筛选和 incomplete 不算空盘逐项复核，再决定是否合并。 |
| [DIS D108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108#discussioncomment-19561593) | **明确 @Ashley，等我们跟进。**三分钟 info 等待和 47.4° 导出拒绝分开处理；先核对原 run、盘型、容量及映射，不建议调松阈值强行导出。 |
| [DIS D231](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231#discussioncomment-19573372) | **可主动跟进；原提问 @exotic-namruth。**已比先前接近但没有最终成功回报，先核对所用 run、盘批次、覆盖范围与写入路径，再讨论照片修正／精标。 |
| [DIS I324](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/324)、[I325](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/325) | **可主动回复，非对 DP 的直接点名。**保留原描线与分段残差，区分描点、照片校正和模型不足；DP 变轨距方案仍需这类实盘验证，不能保证救好这张盘。 |
| [DIS I242](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/242#issuecomment-6824199314)、[I326 最新更正](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/326#issuecomment-6840182558) | **可主动排错。**先看旧盘的实际编码、容量和角度映射；I326 已看到螺旋，不沿用早期“光驱族不兼容”的判断或直接建议采购。 |
| [DIS D270](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/270#discussioncomment-19569280)、[I311](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/311#issuecomment-6827225180)、[D107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19565119) | **可致谢／补信息，非欠答。**按贡献者记录复用和对比观察，补 MID／设备／写速；不把单人目测或仅附件报告当完整几何验收。 |

I251 已在 07:03 UTC 回复，现等 YukaiP 的三个高速结果；PR32 已合并且已致谢，不再列为欠答。上表只是交给人决定的跟进清单。

### 我们自己的问题

11. **读盘重复性好，成品仍可整体扭转：固定完成偏移与范围是两件事。**（[DP #33](https://github.com/Ashley-QwQ/disc-probe/issues/33)，exotic-namruth）
    - 目标：用 GUE0N／MCC 02RG20 在 Linux 稳定刻人像，让计时得到的几何与扫描中的实际螺旋一致。
    - 新回复同意使用三次原始 run＋扫描螺旋，愿意测版本；本人验证 `c25dfac` 的 Linux SG_IO 已覆盖其补丁，`sg_selftest/list/info/geo` 可运行，不再请求移植该补丁。新 run 仍约 103° 扭转；+16 修正后与扫描仍差 6.6–8.6°，测量只覆盖约 33–46 mm，另报检查点漂移。因此“已能跑 Linux”和“完成偏移已解决”不能混用。
    - **DP 状态：Linux 通路已处理（该机本人回报）；完成偏移、范围／质量出口列入 alpha A6，成品归 A3 验收，当前未证明此案例已修复。**从图案盘重新测几何的要求不在本轮 alpha 承诺内，tracker 将其列为研究线。
12. **空盘容量必须在自然流程里读，旧用户不能被拉回第一步。**（[DP PR34](https://github.com/Ashley-QwQ/disc-probe/pull/34)，domerawind）
    - 目标：刻随机盘前取得同盘型空盘容量，后续导出有可靠来源，同时已有 timing／geo 的用户能继续做图。
    - 16:29 UTC 作者报告已修三项必改及 incomplete 分支，更新说明为六步，称 selftest 通过；当前 head 为 `6b740f6751f730fefe7121630f4416a900b9db5f`。旧审阅仍是 `CHANGES_REQUESTED`，没有后续批准或合并记录。本轮未拉代码／重跑测试。
    - **DP 状态：alpha A4／A6，待复审与合入；不能记成已处理。**[PR32](https://github.com/Ashley-QwQ/disc-probe/pull/32) 已于 13:16 UTC 合并并致谢，属于已处理的引导入口；WT／cmd 真机鼠标仍未验收。
13. **info 等三分钟，disexport 因 47.4° 转换差拒绝。**（[DIS D108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108#discussioncomment-19559976)，LTVA1）
    - 目标：用已经测好的盘导出可用的 DIS 预设，继续刻图；不再在无反馈等待和参数搬运间耗盘。
    - 两条新回复分别给出约三分钟等待、30 rungs／0.49° rms／chi2 4.7 的 run，以及 `--sectors 2295104` 后的拒绝。zip 未下载，不能确认容量差或拟合模型就是根因。补齐的 54 条旧回复只作为历史上下文，不再算 54 个新投诉。
    - **DP 状态：alpha A6（有界超时、容量口径、诊断包、转换误差拒绝）；待复现，未解决。**保留拒绝，不把调阈值当修复。
14. **CD 低速始终 CLV 的来回推荐已有回复，仍等用户结果。**（[DIS I251](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/251#issuecomment-6817119300)，Ashley-QwQ 回复 YukaiP）
    - 目标：少浪费剩余 CD，知道这台 SH-216DB 是否有可用测量路线。
    - **DP 状态：已回复；有限次换速与耗尽出口在 alpha A6。**tracker 记 cd-clv 工作树已改但未提交，不能当 alpha 已包含；CLV 粗几何仍需要锚点，不能承诺测出沿轨 L。

### DIS 用户的问题（DP 应该接住）

15. **描几百点也不能同时贴合内外圈，需要看见模型失配。**（[I324](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/324)、[I325](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/325)，同一作者 gelinkpink，Pioneer DVR-218L／DVD+RW）
    - 目标：把看得见的实际边界变成可用几何，并判断应该重描、重拍，还是模型根本表示不了，避免继续耗盘。
    - I324 试约 200、450 多点，日志中的一次为 423 点，内圈贴合时外圈偏、反过来也一样；自动校验未过。I325 的 158 点在启用三次轨距后仍平均 1.399 mm、最大 4.869 mm，作者认为正确点被标成离群，要求原始描线与预测曲线并排显示。三次模型限制／过度平滑是作者的候选解释，未取得原始标定或照片做独立验证；两帖不能算两位用户。
    - **DP 状态：alpha A2／A6（证据覆盖、保守拒绝、变轨距修正）及 A1／A4（说明重拍或换路线）；完整 φ(r) 人工辅助编辑为 F1，未列入 alpha。**tracker 的变轨距结果是 14 组模拟、最坏 0.195° rms，仍等真盘；这些帖子支持优先级，不证明样条已解决 DIS 的原始描线案例。
16. **计时标定后已经能辨认脸，仍扭一到两圈。**（[D231 新评论及后续](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231#discussioncomment-19573372)，jsammarco，GT51N／Dynex DVD+R）
    - 目标：从“看出人像”走到几何正确的成品，知道下一张该做边界还是精标。
    - 19:48 UTC 问是坏标定还是该继续第 2／3 步；22:45 UTC 说更接近、估计再一次第 3 步就好，并想录流程视频。后一句是预期，未报告最终成功。不能只凭图或“一圈”归为 DP #33 的固定偏移。
    - **DP 状态：alpha A2 的照片 L 已合入 `2b6c0c0`；多照片多数一致规则仍在跟进，A3／A6 需核对盘身份、范围、残差及成品。**D0 预设互通已有 `612f37e` 记录，但不自动消除剩余几何误差。
17. **只有圈、没有径向线：保留编码与沿轨两种检查，不直接归咎光驱。**（[I242](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/242#issuecomment-6824199314)，SoulMinf；[I319](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/319#issuecomment-6824671158)，ati180arm-beep；[I326](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/326)，ghpo）
    - 目标：用手头盘／光驱刻出有方向的图案，判断现有盘还能提供什么排错证据。
    - I242 的 Mirex CD-RW／GSA-H66N 粗标环清楚，边界无分界、精标无十字，外部 ImgBurn 4x 也一样。I319 补照片并有人认为是 1.5.0 共性问题，但还不是已定根因。
    - I326 从两台桌面 GH22NS40／GH22NS30 都“无图”，更正为改实际扇区数后能看见螺旋；扫外径 58.040／58.008／57.800 mm，内侧十毫米圈数 18／16／6，外侧仍有更细圈。早期 HLDS 写策略不兼容的推测不能当结论；其“参数无法表达”的后续推导同样未独立复核。
    - **DP 状态：alpha A4／A6（按症状、CD 模式／交织／沿轨、容量与范围分诊），A2／A3（修正与实刻）；尚未解决这几组组合。**不把旧日志的“同心环清楚＝L 不对”当唯一诊断。
18. **六张仍只有鱼钩，社区建议只给了目测增量。**（[D316](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/316#discussioncomment-19569371)，VIVAMAO；新建议 SODIUMWATER）
    - 目标：从不可辨认的精标线继续前进，避免再靠随机改数烧一张。
    - 新建议为“外半径减小 0.01 到 0.02”，作者明确说肉眼估算；没有新完整标定值或成功回报。
    - **DP 状态：alpha A2／A4／A6 的质量检查与下一步；此盘仍未解决。**数据库只记未收录原因，不将建议变为确定半径。

### 值得吸收的结果和想法

19. **几何与显色分开验收；更深底色是观察线索。**（[D270](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/270)，SweetSourFox、SODIUMWATER）
    - 目标：买到在普通观察条件下更容易看清图案的盘，知道该换盘还是继续标定。
    - SweetSourFox 报 RiTEK Excellent DVD+RW 4X／威宝 66768 对比好。SODIUMWATER 对比自己的纽曼、飞利浦和 MID 为 RITEKF1 的索尼，又转述他人的 thinkplus，推测刻前颜色较深的效果好；没有受控光照或量化对比，不推广为 MID／染料规律。[D267](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/267) 新回复的盘层结构解释也是背景看法。
    - **DP 状态：alpha A4／A8 应清楚说明几何、写入／读回、目视对比是不同验收；A7 特效边界继续保留。**按染料预测对比度的模型未列入计划。
20. **社区参数与复用：完整数字可以收，附件和继承项要留未知。**
    - 目标：找到可追溯的起点，知道参数是否适用于自己的盘，而不是同名即套用。
    - [I311](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/311) 完整数值＋独立“perfectly fitted”；[DIS PR298](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/pull/298) 的 Try2Take 原参数和 ManaOnTap 新的独立配置分开收录；MID 未给就留空。[I327](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/327) 参数完整，但 MID 未确认、轨距继承且未明确验收成图，记 `unknown`。
    - [D323](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/323) 与 [I86](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/86#issuecomment-6822624773) 已收不重复；[D322](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/322)／[I81](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/81) 重标纽曼的值只在 zip；D107 新成功报告的 geo 也只在 zip。[I232](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/232#issuecomment-6839596392) 是复用成功，光驱只猜 MATSHITA，不补确定型号。I81／I92 关闭只记线程状态，不推断所有相关问题已经修复。
    - **DP 状态：本轮数据收录已处理；D0 互通已合入，alpha A6／A8 仍需保留身份、来源和验收限制。**附件中的数值本轮未获取，不推算。[D209](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/209)、[D307](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/307) 的底图索取／分享是素材交流，没有新增程序缺陷；自动抓取底图未列入计划。

状态依据为本轮读取的主 checkout `TODO_ALPHA.md` 和 `CODEX_TRACKER.md`，后者已将发布日期改为 11-15；前者标题与旧排期仍写 11-22，不据此延期。没有重新审查其他工作树或替它们做验收。新快照已补齐全部评论／回复／PR 审阅分页；旧人工需求人数仍保留 11-11 的口径，当前覆盖量与新增 R14 见 [USER_NEEDS.md](USER_NEEDS.md)。

## 2026-11-12（对比 11-11 快照：新增 13 条帖子，修改 2 条）

### 我们自己的问题

1. **DP 用户卡在 `timing`：CD 一直是 CLV。**（DIS I251，YukaiP，11-11 12:52 UTC，还没回复）
   - v0.1.2.1，CD-R，`timing --media cd --speed 1411` 判定"是 CLV 不是 CAV"，然后建议换 2822。他已经试过降速、2x、1x，结论都一样，DP 还在让他换速度。
   - 要改：
     - 记住试过哪些速度，不再建议已经试过的；
     - 连续几次都是 CLV 时，直说"这台光驱读 CD 可能一直是 CLV"，给出下一步（`--force` 的含义和风险，或者换一种测法、换一台光驱）；
     - 查 CLV 下能不能测 CD 几何（BD 已经有 CLV 求解器 `docs/research/BD_CLV_GEOMETRY_SOLVER.md`）。
   - 要回复他。

### DIS 用户的问题（DP 应该接住）

2. **CD-R 边界标定刻完是空的 / 只有乱圈。**
   - 涉及的帖子：I251（YukaiP）、I321（4azulla，Verbatim CD-R 43787）、I318（Siborgiy23，Verbatim CD-R，TS-635c 光驱）、I297。
   - 共同点：粗标成功，边界标定那张刻完看不到图案，换了几张盘还是一样。
   - DP 要做的：
     - CD 走计时路线，绕开边界标定；
     - 刻完以后先读回判断"盘到底有没有写进去"，再让用户去看图案。
3. **"干净预设"仍然带着旧标定参数。**（I318）DIS 的 bug。DP 要做的：预设和标定记录分开存，界面上标明当前用的是哪一份。
4. **只有单片装、不想买 10 片或 50 片装。**（I319，Verbatim AZO DVD-R 43547）
   - 同名产品，10 片装和 50 片装的 MID 不同，DIS 里有两个同名预设，用户分不清。
   - DP 要做的：预设按 MID 查，不按商品名；没有现成的就走计时，一张盘解决。
5. **精标那条曲线小到看不清。**（I71，g3nsvrv，"曲线在 9 条里的第 3 条"）DP 的拍照标定要保证尺子在可读的角度范围里，并在照片上标出该看哪里。
6. **参数差太多，十字线扭到认不出来。**（D316，维护者回复"多做几轮前面的标定"）DP 的计时路线不需要靠多轮人工迭代收敛。

### 值得吸收的想法

7. **用盘面错误扫描找一条墨水线来定角度。**（I320，Sodium2He）
   - 做法：刻好以后，在读取面画一条约 1 mm 宽的径向墨线，用 QPxTool 扫 PI/PIF 错误，墨线挡住的扇区就是这条线所在的角度。他说一次就能定出半径。
   - 对 DP 的意义：我们的计时测不出沿轨常数 L（记忆里写的是"免拍照的上限"）。墨线直接给出"哪个扇区在哪个角度"，可能可以不拍照就拿到 L。
   - DP 版本不一定需要 QPxTool：墨线下的扇区会重试或读失败，我们自己读盘就能定位；GH70N 的 C2 全零，所以要靠读失败或读慢来判断。
   - 他的结果里有一个 +6 扇区的修正，和我们 #33 的读完成偏移（GUE0N +16 扇区）是同一类问题。
   - 下一步：在一张已经刻好、可以牺牲的盘上试画一条线（白板笔，可以擦掉），用 `scan` 看读失败或读慢落在哪些扇区。
8. Discord 邀请链接默认会过期（D238）。以后如果 DP 开社区，记得设成永不过期。

## 2026-11-12 白天

9. **CD 精标只有同心环、十字径向线全没了。**（I242，SoulMinf，DIS 1.5.0，LG GSA-H66N，Mirex CD-RW；同帖还有 Slimtype DS8A5SH + CD-R 80）
   - 粗标的同心带很清楚，边界标定没有半盘分界，精标只剩同心环。导出 WAV/CUE 用 ImgBurn 4x 单独刻，结果一样。
   - 同心环清楚说明半径方向对了，丢的是沿轨方向（角度）。这和我们记下的 CD 沿轨常数、音轨交织延迟（L≈−105 帧）是同一类问题：沿轨位置错了，径向线就被抹成一圈。
   - DP 要做的：CD 走计时 + 沿轨常数这条路时，在引导里明确"同心环清楚但径向线没有 = 沿轨常数不对"，并直接给出下一步。
   - 可以考虑在 I242 回复，先问清他要的是什么（回帖前先看对方目标），要用户点头。
10. **DP 成功报告：Optiarc BD-5750H + Victor DVD-R。**（D107，winxp0621，DP v0.1.2.1）
   - IO-DATA BRP-U6XE 外置光驱（里面是 Optiarc BD RW BD-5750H，固件 1.00），没接外接电源；盘是 Victor DVD-R VHR12JP50SJ1。
   - `timing`：CAV，4655 转/分，抖动 0.30–0.80°，判定可用；DP 给出参数后在 DIS 里刻录正常。
   - 附了 result.zip（geo 结果），数值不在正文里；要收进社区标定库得下载，需用户点头。
   - 可能的小 bug：`info` 报"托盘开着"，但同一次输出后面读出了速度表，随后 `timing` 也正常读盘。要看这台光驱的 TEST UNIT READY 返回了什么，可能是外置盒供电不足时的误报。
