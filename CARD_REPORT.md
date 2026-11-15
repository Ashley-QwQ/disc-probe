# D2：F1 曲线辅助编辑界面打磨报告

分支：`dev/f1-polish`；worktree：`D:/dp-dev/f1polish`；基点：`b380563`。已先读 COMMON、D2 卡和 F1 交付报告。仅改 `curve-edit.js`、`curve-edit.css`、对应浏览器测试及本报告。没有推送、合并、切换分支或修改其他 worktree；没有接光驱、刻盘、上传或下载，没有修改 `evidence/atlas/*.py`。

## 做了什么（按提交）

1. 本提交 `fix: polish assisted curve editor presentation`
   - y 轴使用 1、2、5 × 10ⁿ 的步长，显示 3–5 个刻度，覆盖曲线并包含零；零处使用 rule 细参考线。x 轴在范围不超过 40 mm 时每 5 mm 一格，更宽时每 10 mm 一格。数字小数位随步长变化。
   - 图右上角改为线样与文字图例；自动曲线为墨色实线，候选为上层、稍粗的铜色虚线，重合时两者仍可辨。轴标题为“φ 偏转 / °”“半径 / mm”，使用页面正文字体和 muted 色。
   - 控制点表格随内容宽度排列，输入约 7em、右对齐、等宽数字，单位 ° 放在输入后；半径也右对齐。偏移不为零的行显示 1px 铜色左线，恢复零后取消。
   - 修改中显示非零偏移点数；验证通过显示 RMS、最大误差及可以保存；超限失败显示 RMS、最大误差和各自上限，并使用已有 warn 色。所有误差及上限直接取后端 validation，仅作最多三位小数的显示格式化；没有重算指标或改变阈值。缺少数值的证据错误继续显示原有原因。
   - 重拟合、保存复用 kit-ring-button，主操作用现有墨/纸色突出；重读复用 kit-text-button。禁用保存下方显示“先通过验证才能保存”。沿用结果页平面控件，不带入 kit 的场景大阴影。没有改变事件动作、请求参数、导出 API、CLI、拟合、验证和保存门槛。
   - 增加数值刻度不变量与真实 Edge/HTTP/CLI 验收：16 个状态/主题/宽度组合，检查图例、零线、RMS 文案、点数、回零标记、5/10 mm 刻度、无数值拒绝原因、控件高度、图表文字边界、表格宽度及拒绝不回写、通过后保存、编辑后撤销通过状态。

## 验收命令与数字

临时目录均在 D 盘；没有运行完整 Python 套件。

```powershell
$env:TEMP='D:/dp-dev/tmp/f1polish'
$env:TMP=$env:TEMP
python -B -m pytest -n 2 tests/test_curve_edit.py tests/test_webui.py tests/test_webui_recovery.py -q --basetemp D:/dp-dev/tmp/f1polish/pytest-final
```

结果：**67 passed，42 subtests passed，14.60 秒**。日志：`D:/dp-dev/tmp/f1polish/python-final.log`。

```powershell
$env:F1_TEST_SHOTS='D:/dp-dev/tmp/f1polish/shots'
node --test tests/test_curve_edit_browser.mjs
```

定向最终结果：**2 tests / 2 pass / 0 fail / 0 skipped，21.11 秒**。日志：`D:/dp-dev/tmp/f1polish/browser-final.log`。同一曲线用例在全体最终回归中也再次通过。

```powershell
$f1Tests=@(rg --files tests -g 'test_*.mjs' -g '!**/*[bB][lL][iI][nN][dD]*' -g '!**/*[bB][lL][iI][nN][dD]*/**')
node --test --test-concurrency=1 $f1Tests
```

最终结果：**36 个文件，41 tests / 41 pass / 0 fail / 0 skipped，88.52 秒**。日志：`D:/dp-dev/tmp/f1polish/node-final.log`。

首轮全体 Node（并发 2）为 39 pass / 2 fail：新增线宽断言把带 px 的字符串用 Number 转换，已改为 parseFloat；另一个既有预设导入导出浏览器用例返回 PENDING。未改该用例或产品实现，最终串行全体回归通过。首轮日志保留在 `D:/dp-dev/tmp/f1polish/node-first.log`，没有把首轮失败记成通过。

```powershell
python -B -X utf8 D:/dp-dev/tmp/f1polish/make_review.py
python -B -X utf8 D:/dp-dev/tmp/f1polish/verify_artifacts.py
git diff --check
```

16 张要求截图逐一检查实际像素宽度为 1000 或 390，高度至少 1250；页面与表格均无横向溢出，可见输入/按钮/summary 高度均 ≥44px，SVG 文字在 viewBox 内。已查看 16 态联系表、390 失败态、390 夜色通过态及并排对比图。`git diff --check` 通过；JS、测试及报告检查非 ASCII 字符数 >0、连续双问号数为 0。

机械检查运行一次：`impeccable.cmd detect --json discprobe/web/home/curve-edit.js discprobe/web/home/curve-edit.css`，结果 **0 条提示（[]）**；原始结果：`D:/dp-dev/tmp/f1polish/ui-detector.json`。

## 截图路径

以下均由 Edge 无头截图，使用发货编辑组件、真实本地 HTTP 后端和 CLI，合成 spline 数据、15 个独立检查点、5 个控制点，设备列表固定为空。截图页面明确标注“合成数据验收 · 无光驱、无实盘”。

| 状态 | 纸色 1000 | 纸色 390 | 夜色 1000 | 夜色 390 |
| --- | --- | --- | --- | --- |
| 自动 | `D:/dp-dev/tmp/f1polish/shots/automatic-paper-1000.png` | `D:/dp-dev/tmp/f1polish/shots/automatic-paper-390.png` | `D:/dp-dev/tmp/f1polish/shots/automatic-dark-1000.png` | `D:/dp-dev/tmp/f1polish/shots/automatic-dark-390.png` |
| 修改中 | `D:/dp-dev/tmp/f1polish/shots/editing-paper-1000.png` | `D:/dp-dev/tmp/f1polish/shots/editing-paper-390.png` | `D:/dp-dev/tmp/f1polish/shots/editing-dark-1000.png` | `D:/dp-dev/tmp/f1polish/shots/editing-dark-390.png` |
| 验证通过 | `D:/dp-dev/tmp/f1polish/shots/validation-passed-paper-1000.png` | `D:/dp-dev/tmp/f1polish/shots/validation-passed-paper-390.png` | `D:/dp-dev/tmp/f1polish/shots/validation-passed-dark-1000.png` | `D:/dp-dev/tmp/f1polish/shots/validation-passed-dark-390.png` |
| 验证失败 | `D:/dp-dev/tmp/f1polish/shots/validation-failed-paper-1000.png` | `D:/dp-dev/tmp/f1polish/shots/validation-failed-paper-390.png` | `D:/dp-dev/tmp/f1polish/shots/validation-failed-dark-1000.png` | `D:/dp-dev/tmp/f1polish/shots/validation-failed-dark-390.png` |

- 改前/改后并排：`D:/dp-dev/tmp/f1polish/shots/validation-failed-paper-1000-comparison.png`。
- 改前原图副本：`D:/dp-dev/tmp/f1polish/shots/validation-failed-paper-1000-before.png`，来自卡指定的 `D:/dp-dev/tmp/f1/shots/validation-failed.png`，没有重新运行旧实现；左右均为同一 F1 合成 fixture、纸色、1000 宽失败态。
- 16 态联系表：`D:/dp-dev/tmp/f1polish/shots/review-contact-sheet.png`。
- 图像及日志的字节数、SHA-256：`D:/dp-dev/tmp/f1polish/ARTIFACTS.json`。
- 其他既有 Node 回归生成的图片移至 `D:/dp-dev/tmp/f1polish/regression-shots/`，没有提交到仓库。

## 没做到、拿不准及需要人决定的事

- **实盘、光驱、完整真实标定主线均未测。** 本次只证明组件的显示与合成 CLI 集成，没有升级 F1 原有硬件/准确率结论。完整英文视觉、读屏器、浏览器缩放和其他浏览器均未测。
- kit 没有单独命名的“primary”变体或通用数字输入组件。本次复用 kit 的按钮基样式与次要文字按钮，并在曲线区用已有墨/纸变量表达主按钮；数字输入保留原有边框/焦点方式，换用页面字体。是否要把该主按钮变体提炼到 kit，留给后续审查，本卡没有扩展共享组件。
- “改了 N 个点”按相对自动曲线的非零偏移计数；清空而尚未填有效数字的点也算一个待处理点，既有有效数字检查仍会拒绝提交。恢复为零后行标记消失，仍需重新验证才能保存。
- 指标显示最多三位小数并去掉尾零；极小误差会显示 0°，完整原始值仍在“验证详情 / CLI”。当前失败样本 RMS 和最大值都为 6.25°，因此如实显示 6.25°，没有照抄卡中文字示例里的 6.3°。
- 保留原图表约 0.1° 的范围余量，再向整洁刻度扩展；为包含零，单侧曲线可能留白较多。没有新增配色、修改其他页面的审美或替审查者决定进一步压缩图表。
