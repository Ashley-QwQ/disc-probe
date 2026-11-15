# F1 曲线辅助编辑交付报告

分支：`dev/f1-curve-edit`；worktree：`D:/dp-dev/f1`。按 COMMON 和 f1 卡执行。未推送、未合并、未切换分支，未连接光驱、刻盘或上传。没有修改 `evidence/atlas/*.py`。

## 做了什么（按提交）

1. `3f9977b` — `docs: plan F1 curve editing contract and validation`
   - 先提交 `F1_PLAN.md`，梳理 geo spline、gridscan 多项式、pcal / photo 的 L-only 边界、网页参考环与测量结果页，以及 A2/A6 当前源码交付和未验收部分。
   - 冻结坐标、符号、有效范围、来源哈希、格式版本、独立验证规则和实现范围。
2. `79178b6` — `feat: add independently validated assisted curve editing`
   - `discprobe/curve_edit.py`：实际自动结果初始化；完整 JSON 值无损往返；控制点平滑偏移重拟合；在原多项式或原 spline 空间叠加；独立检查、失败拒绝、陈旧来源拒绝、并发锁、原始自动结果备份、历史与单文件原子替换。
   - `curve-edit --run ... [--edit ... | --edit-json ...] [--save]`：JSON 返回、明确失败退出码、保存时重新验证。CLI 是引擎；网页通过已有作业后端运行同一命令。修正操作不枚举光驱；关闭网页不终止子进程。
   - 结果页新增“辅助修正”，复用 kit DOM helper、既有 placed 按钮、主题和详情控件；显示自动 / 候选曲线、数值偏移、独立验收和拒绝原因。改动或重读即清除通过状态；保存仅在验证通过后可用；保存时核心仍复验。
   - 修正作业期间阻止“下一步”，保存修正后使旧缓存预设失效，继续保存测量时重新导出。新一次测量清空前次编辑状态。
   - `docs/CURVE_EDIT.md`：CLI、格式、显式照片留出协议、保存与恢复说明。计划追加实现补充，明确轻量网页请求、跨 JSON 运行时数值哈希和事务边界。
   - 新增 30 项 Python 案例和真实 CLI / HTTP / Chromium 集成测试；更新原照片流程测试的模块依赖和缓存预设回归。
3. 本报告提交 — `docs: record F1 acceptance results and limitations`
   - 记录最终命令、通过数字、证据位置及未测范围。

## 验收命令与数字

所有测试临时目录通过 `TEMP` / `TMP` 指向 `D:/dp-dev/tmp/f1`；pytest 使用两个 worker，没有运行完整 Python 套件。

```powershell
$env:TEMP='D:\dp-dev\tmp\f1'
$env:TMP=$env:TEMP
python -B -m pytest -n 2 tests/test_curve_edit.py tests/test_webui.py tests/test_webui_recovery.py tests/test_geo_varpitch.py tests/test_geo_integration.py tests/test_dis_pitch.py -q --basetemp D:/dp-dev/tmp/f1/pytest-final
```

结果：**81 passed, 42 subtests passed，28.67 秒**。日志：`D:/dp-dev/tmp/f1/python-final.log`。

```powershell
$env:F1_TEST_SHOTS='D:\dp-dev\tmp\f1\shots'
$f1NodeTests = @(rg --files tests -g 'test_*.mjs' -g '!**/*[bB][lL][iI][nN][dD]*/**' -g '!**/*[bB][lL][iI][nN][dD]*')
node --test --test-concurrency=2 $f1NodeTests
```

结果：全部 **36 个 test_*.mjs 文件，40 tests / 40 pass / 0 fail / 0 skipped，71.21 秒**。日志：`D:/dp-dev/tmp/f1/node-final.log`。新增浏览器测试使用发货的编辑组件、真实本地 HTTP 后端与真实 CLI 子进程，后端设备列表固定为空，验收自动初值、修改、拒绝不回写、通过后保存、390/1000 px 布局及可聚焦数值控件。全部可见输入/按钮/summary 高度至少 44 px，未见横向溢出。

```powershell
python -B -X utf8 D:/dp-dev/tmp/f1/verify_acceptance.py
git diff --check
```

另存具体数值的合成验收：`D:/dp-dev/tmp/f1/acceptance/RESULT.json`。两个模型各用 15 个独立检查点；真值相对自动结果增加 `+1.25°`：

| 自动表示 | 找回偏移 | 验证 RMS | 故意设为 −5° 后 RMS | 拒绝后原文件字节 |
| --- | --- | --- | --- | --- |
| 多项式 | +1.25° | 1.282e-16° | 6.25° | 不变 |
| 三次 B-spline | +1.25° | 2.979e-16° | 6.25° | 不变 |

固定验收门为 RMS ≤0.5°、最大绝对误差 ≤1°；不会随噪声或人工编辑放宽。测试另覆盖三次非恒定偏移、低阶 spline、完整元数据往返、错坐标/版本/范围、NaN/Inf、留出缺失/重复/重叠/分布不足、来源改变、重复保存后仍锚定原始独立读数、CLI 与网页拒绝契约、现有 loader 及 `disexport.target_angle` 消费。

末轮 `git diff --check` 通过。中文文件检查：`F1_PLAN.md` 1335、使用文档 1285、编辑器 JS 433 个非 ASCII 字符，均无 `??` 连续问号；测试文件中中文也通过检查。报告本身在提交前同样检查。

## 截图与证据

三张要求的截图均放在指定目录，另附窄屏失败态：

- [自动初值](../tmp/f1/shots/automatic.png)
- [修改中](../tmp/f1/shots/editing.png)
- [验证失败](../tmp/f1/shots/validation-failed.png)
- [窄屏验证失败](../tmp/f1/shots/validation-failed-mobile.png)

这些是复用既有结果页样式的组件集成 fixture 截图，运行真实编辑组件与 CLI 后端，页面明确写“合成数据验收 · 无光驱、无实盘”；不是从插盘到标定结束的实盘截图。已实际查看四张图，确认自动/修改中/失败态及禁用保存可读。

`D:/dp-dev/tmp/f1/ARTIFACTS.json` 保存最终日志、合成数值结果、四张截图的字节数和 SHA-256。验收脚本、模型目录、原自动结果备份及历史记录保留在同目录。现有 Node 回归默认生成的额外截图已移到 `D:/dp-dev/tmp/f1/regression-shots/`，没有把临时文件提交到工作树。

界面机械检查：`impeccable.cmd detect --json` 对改动页面运行一次，结果在 `D:/dp-dev/tmp/f1/ui-detector.json`。49 个提示均落在 `index.html` 的既有视觉样式（3 warning、46 advisory），该文件本次仅增加样式表引用；没有借此更换原配色、字体或版式。新编辑器 JS/CSS 未报告提示。

## 没做到、拿不准及需要人决定的事

- **仅合成验证，没有实盘。** 未接光驱、未刻盘、未测真实变轨距盘、真实读取耗时、实体成品或新照片的准确率。原有实盘和 A2 reader 放行结论没有因此升级。
- 自动曲线的范围、符号及原始模型保持一致；本版控制点只拟合最高三次的平滑增量（低阶 spline 会降阶），不是任意局部高频描线。是否下一版扩展为局部控制基函数，留给审查者决定；本次没有把拖参考环说成曲线编辑。
- 当前 pcal / photo 的沿轨 L 不产生可独立验收的完整 φ，不会伪造初值。已有照片多项式可提供显式 `curve-evidence.json`；该协议和来源转换只用合成照片点测过，真实照片适配未测。协议中的来源、输入哈希与划分是调用者声明，核心不重新读取原图证明其真实性。
- 独立检查未参与自动/偏移拟合，且与所有记录的拟合 ID 分离；反复看同一验证集调参后，不能再宣称新封存留出通过。固定阈值和对检查点间的未知高频误差不作额外保证，真实硬件适用性仍需审查和新数据。
- 锁和替换前哈希检查保护本功能的并发/陈旧写入；不是跨多个文件的事务，也不与正在写同目录的 geo 作业共用锁。磁盘故障、进程强杀、保存恰遇外部写入的极窄竞态未注入测试。可能留下备份/历史或残锁，恢复步骤已写文档。
- 没做整套标定主线的真实浏览器/硬件验收，也没做人工读屏器、完整英文视觉或低配机器性能验收，均为**未测**。现有页面文字/风格未作审美重设计，没有待决定的新配色或版式。
- 开发过程中首轮核心测试有 1 项断言大小写错误，浏览器发现 JSON 数值哈希问题，首轮全部 Node 有 1 项旧测试缺少新增模块替身；均修复后执行上面的最终回归。最终没有失败被改记为通过或跳过。
