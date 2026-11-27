# DIS 社区增量报告：2026-11-12 晚间

对比主 checkout 的 11-12 快照，只通过只读 `gh` 查询 GitHub。采集时间是多伦多 11-12 19:44:53–19:46:21（UTC 11-13 00:44:53–00:46:21），所以新目录名为 `data-20261113`。

| 范围 | 当前覆盖 | 本轮变化 |
|---|---|---|
| DIS Issue／Discussion | 170＋101＝271 个线程，1,374 条发言 | 新增 6 个线程、29 条发言，涉及 21 个线程；旧正文修改 0 条；I81／I92 关闭 |
| 历史分页缺口 | 本轮已补齐 | D108 补 54 条、D107 补 3 条，共 57 条，单列而不当作新投诉 |
| DIS PR | 53 个 PR，115 条正文／评论／审阅记录 | 首次建完整基线；按创建时间筛出 PR298 的 1 条新评论 |
| DP Issue／PR | 17＋17＝34 个线程，162 条记录 | 首次建完整基线；#33、PR32、PR34 共 9 条新记录，旧正文编辑无法比较 |
| 社区校准库 | 174 → 178 条 | 新收 I311-1、PR298-1、PR298-2、I327-1；D323-1、I86-2 已有不重复 |

新增 6 个 DIS 线程为 D322、D323、I324、I325、I326、I327。主要变化是：几百描点仍拟合不过；计时后人像仍差一到两圈；完成偏移测试获得原作者授权；空盘容量引导 PR 已更新待复审。I326 最新已看见螺旋，不能继续当作“完全无显色”或已证实某光驱族不兼容。D270 的“刻前颜色深更好”保留为个人观察。

I311 的参数作者是 SodiumSulfate，SweetSourFox 新增“完美贴合”的独立复用回报。原作者光驱、MID 和实际写速未提供，保持未知。PR298 的原配置和新评论是不同盘号、不同设备、不同参数，分开收录。I327 的 MID 未确认，三项轨距沿用起始预设，没有明确的最终成图验收，结果记 `unknown`。D316 的减外径 0.01–0.02 是目测建议；D322 的数字只在未下载的 zip，均未编造参数。

11 月 15 日 alpha 受影响的项是 **A6**（模型不足、完成偏移、覆盖范围、容量、超时与诊断），**A1／A2**（保留照片证据、拒绝不可靠修正），**A3**（真实成品），**A4**（按症状说明下一步）及 **A8**（说明验收边界）。D0 预设互通和 A2 照片 L 接入有合入记录；多图多数一致规则、这些用户的实际组合仍待验证。变轨距目前只有模拟证据，完整 φ(r) 人工编辑为 F1，不承诺 alpha 已解决 I324／I325。PR34 属 A4／A6 待复审项。

待人决定的跟进及一句要旨如下，没有发布任何回复：

- [DP #33](https://github.com/Ashley-QwQ/disc-probe/issues/33#issuecomment-6827622004)：感谢授权三次 run＋扫描作回归，Linux 已获本人验证；固定偏移与窄范围误差分开检查，再给受限测试版本。
- [DP PR34](https://github.com/Ashley-QwQ/disc-probe/pull/34#issuecomment-6829466426)：复核 `6b740f6` 的旧结果续走、盘型筛选、incomplete 排除；作者报告通过不代替我们的复审。
- [DIS D108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108#discussioncomment-19561593)：回应三分钟等待和 47.4° 导出拒绝，先核对原 run、容量与映射，保留质量拒绝。
- [DIS D231](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/231#discussioncomment-19573372)：可主动跟进；已接近但未最终成功，先核对盘批次、run 和覆盖范围，再讨论精标／照片修正。
- [DIS I324](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/324)／[I325](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/325)：可主动回复；保留原始描线、区分模型不足与描点错误，不保证 DP 已能修好这张盘。
- [DIS I242](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/242#issuecomment-6824199314)／[I326](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/326#issuecomment-6840182558)：可主动排错；先核对旧盘编码、容量和角度映射，不直接建议买光驱。
- D270、I311、D107 可致谢或补 MID／设备信息，属于可选跟进。I251 已回复，等用户高速结果；PR32 已合并且致谢，无需再催。

详细问题、用户目标和 DP 状态见 [FEEDBACK_LOG.md](docs/research/dis/FEEDBACK_LOG.md) 最新一节；[USER_NEEDS.md](docs/research/dis/USER_NEEDS.md) 已更新覆盖量并新增 R14“原始描线与拟合并排检查”，同一作者两帖只计一人，旧人工人数未重算。原文差分见 [new_since_20261112.md](docs/goals/dis-community/new_since_20261112.md)，完整原始数据、分页核对、脚本来源及散列见 [manifest.json](docs/goals/dis-community/data-20261113/manifest.json) 和 [comparison.json](docs/goals/dis-community/data-20261113/comparison.json)。旧快照没有采集时刻和稳定评论 ID，历史／近期分界使用原文件 UTC 修改时间；采集并非原子快照。

仅改文档与数据；未下载附件、运行帖子中的命令、构建、刻盘、发帖、评论、反应、审阅、合并或推送。提交号由交付回复列出。
