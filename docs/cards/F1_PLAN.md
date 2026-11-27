# F1 曲线辅助编辑计划

## 当前表示与交付边界

- `geo.Ladder.dense_correction` 以重复读取拟合 B-spline：`spline={t,c,k}`、`radius_valid_mm`、`geo_fit`、`validation`，写 `correction.json`；`probes.json` 分开保存拟合点与新半径上的 `independent_checks`。图像角度为基准轨道角减 φ，φ 单位度，数据面看逆时针为正。
- `gridscan.fit_correction` 从照片网格的 `phi.csv` 拟合 `poly_in_x`，系数按降幂，`x=(r_mm-40)/15`；照片旋转先归零，可以叠加刻网格时的 base correction。`imagedisc.load_correction` 对两种曲线都在有效半径边界夹取，`image` 和 `disexport` 使用它。
- 冻结 `pcal` 自动读照片的模型是 `tau=c+L/r+phi(r)`，实际公开 `photo` 工作流只给经组间检查的 L、参考环、来源和拒绝原因；它没有可独立验证的通用 φ(r) 输出。L 不能转换成虚构的自动曲线。
- 网页 `calibrate.js` 的实际测量结果页有状态、几何图与照片入口；`photocal.js` 能改参考环，不能编辑 φ。A2 已有照片质量/组一致性拒绝及 L 应用来源门；A6 已有自动变轨距修正、独立计时检查和覆盖门。TODO/REPORT S6/S7/S9 所述实盘、照片 reader 完整验收不能从源码推定通过。

## 格式 v1

`kind=curve-edit`, `version=1`, `coordinates={radius:mm, angle:deg, positive:ccw-data-side, meaning:picture-phi}`, `radius_valid_mm`、`source_sha256`、`evidence_sha256`、`automatic`（原始 correction JSON 的完整深拷贝，不丢弃任何字段），`controls=[{radius_mm,delta_deg}]`。控制点是同一 φ 坐标上的增量，初值全为零，自动曲线取实际文件。版本、坐标、范围、来源冻结；自动表示与编辑表示零修改往返按 JSON 值完全相等。

重拟合选择低阶平滑偏移：控制点最小二乘拟合最高三次多项式（原 spline 次数较低时相应降阶），再精确叠加到原多项式或原 B-spline 空间。不重新采样替代原曲线，不改变结点、半径范围、geo_fit、L 或照片参考环。此版本不提供任意局部高频描线；可表示的偏移阶数在响应中公开。

## 独立验证与保存

- 首先支持实际 geo 目录：从 `correction.json` + `probes.json` 自动初始化。独立检查的目标 φ 等于自动 φ 减 `error_deg`；检查点 LBA 必须不在拟合点/参考/原几何拟合数据中。记录输入文件哈希；每次重算/保存重新读取，拒绝陈旧编辑。
- 核心内存 API 另接受明确分离的 `fit_ids` 与独立 `checks`（id、radius_mm、phi_deg）；可接后续照片留出，但没有这些证据的历史照片多项式只支持无损转换，不准保存人工曲线。照片 reader 和 L 保持不变。
- 至少 4 个有限且不重复的独立点，分布覆盖有效范围的内、中、外段；拒绝空洞/thin intervals、范围外、重复训练点、NaN、无效模型。阈值先定为 RMS ≤0.5°、最大绝对误差 ≤1°，不随编辑或噪声放宽；保留每点残差。
- 验证失败返回原因且不写任何文件；通过后以原文件哈希并发保护、原子替换保存 correction，并保留原自动结果及编辑/验证记录。不改 summary 的既有可用性结论；图像/导出原覆盖门仍生效。

## CLI 与网页

`curve-edit --run <geo-dir> [--edit <json-file>] [--save]`：无 edit 返回实际自动曲线和编辑格式；有 edit 重拟合并验证；save 只允许验证通过。JSON 响应便于 agent，任务独立于浏览器。网页增加严格参数白名单的同名 CLI 作业：编辑文档以 JSON 参数交给同一核心，不另写浏览器拟合算法。

实际标定结果页增加“辅助修正”展开入口；显示半径/φ 坐标、自动/候选曲线、数值控制点、独立验证结果；改动即清除之前通过状态，保存时服务端再验证。沿用 kit 按钮/表单、现有主题与布局；自动结果缺失则明确说明。截图用明确标示的合成 geo 数据，存 D:/dp-dev/tmp/f1/shots/。

## 验收

无损往返（多项式与 spline、额外元数据）；已知平滑偏移找回、独立留出通过；坏改动/证据缺失/数据重叠/范围外/NaN/陈旧来源拒绝且文件字节不变；CLI/网页同一路径、保存后实际 loader 和导出消费。pytest `-n 2`，只跑相关 Python 测试，末轮全部 `tests/test_*.mjs`。报告列命令、数量、截图、仅合成与未实盘边界。先提交本计划，再实现和报告；不推送、不合并。

## 实现时补充

- 照片/其他来源可显式提供 `curve-evidence.json`；格式和“来源为调用者声明，非自动核验原图”的边界见 `docs/CURVE_EDIT.md`。当前 L-only reader 不产生它。
- 浏览器回传 JSON 会把 `26.0` 变成 `26`，哈希规范化整数值浮点；网页发送不含完整自动模型的轻量文档，由核心在哈希检查后补上磁盘原值，避免 Windows argv 长度限制。
- 修正作业期间阻止结果页下一步；保存后废弃缓存预设，要求重新导出。锁、哈希和单文件原子替换不能构成跨文件事务，强杀残锁恢复办法见使用文档。
