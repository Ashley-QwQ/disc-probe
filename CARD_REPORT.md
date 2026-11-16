# 卡 P：刻录停止与未完成测量盘

分支：`dev/burn-cancel`。按 2026-11-15 更新后的任务卡实现滑块，不使用确认框。

## 本次提交

单次提交：`fix: guard burn cancellation and reject incomplete measurement discs`，包含本报告、实现和测试。

- 标定页任务条使用文字“停止刻录 / Stop burn”。停止操作原位展开现有 `slideConfirm` 组件，锁定 3 秒，显示 3、2、1；解锁后拖到底并松开，或聚焦后长按空格／回车 1 秒，才调用取消。Esc、点滑块外、继续刻录均只收起；重新展开重新计时。
- 风险提示和解锁提示使用 aria-live。风险文字闪烁；系统 `prefers-reduced-motion` 或应用关闭动态效果时保留红色、停止闪烁。开始和停止刻录共用滑块的拖动与长按处理；输入法合成回车不触发操作。
- 刻录页移除原先的内联二次确认区，使用同一个锁定滑块。写完后的回读仍一键停止。检查了 `design.js`：实际写盘的取消句柄由刻录页滑块调用；两处预览渲染的 `/cancel` 及换盘任务是非写盘操作，保持直接取消。补了刻录请求尚未返回任务编号时的停止请求排队，以及 SSE／快照中的用户取消识别。
- `Backend.cancel()` 保存一次 `cancelled/by=user` 事件，含任务阶段及最近一次真实进度；标记落盘到任务目录的 `user-cancel.json`，并进入 SSE、任务快照和刻录记录。使用独立文件，避免与核心进程并发追加同一 JSONL。页面刷新后可以恢复本次被用户停止的标定结果；SSE 重连重放标记。
- 未完成刻录保留在准备测量盘步骤，不打勾。结果区区分用户停止与刻录失败，用户停止给出约百分比及不能再刻、不能测的原因，失败保留实际原因。主按钮为“换一张空白盘重新刻”，重新检查必须确认是空白盘。修正模拟流程把所有 stopped 都直接送去测转速的跳步。
- 核心标定检查和网页检查拦截已封口、已写入但极短的盘；576 扇区显示“约 1 MB，多半是刻录中途停了，不能用来测”，并给出换空白盘的动作。核心有英文诊断、`zh.py` 中文翻译和新增拒绝事件；网页有中英文文案。既有 CLI 字段和格式保留，仅新增诊断字段／事件。

## 验收与数字

所有测试不访问真实光驱；临时目录和浏览器配置均在 D 盘。

1. 最后一轮相关 Python 测试：

   ```powershell
   $env:TEMP='D:\dp-dev\tmp\burncancel'; $env:TMP=$env:TEMP
   python -X utf8 -B -m pytest -n 2 tests/test_burn_cancel.py tests/test_burn_progress.py tests/test_burner.py tests/test_webui.py tests/test_webui_recovery.py tests/test_webui_catalog.py tests/test_recordable_capacity.py tests/test_geo_unsteady.py tests/test_web_guidance.py disclab/tests/test_burn_time.py --basetemp D:/dp-dev/tmp/burncancel/pytest-final -q
   ```

   结果：**152 passed，46 subtests passed，13.10 秒**。新测试覆盖用户标记落盘、快照、重连、重复请求、已结束任务不误标记、只读阶段、短盘判定边界、核心未启动 timing、中文翻译及盘信息新增字段。

2. 按公共卡要求遍历 `tests/` 根目录所有 `test_*.mjs`，每个文件单独用 node 运行：

   ```powershell
   python -X utf8 -B D:/dp-dev/tmp/burncancel/run_mjs.py
   ```

   共 **49 个文件**；该遍历中 **47 个退出 0，2 个失败**。失败是 `test_photo_wire.mjs` 和 `test_photo_wire_browser.mjs` 手工拼接的页面夹具漏掉本次新增的模块依赖。补齐真实模块导入及 job-cancel 节点，并把失败刻录的旧“禁用下一步”断言改为检查新版安全重刻按钮；对已刻完但回读检查失败的情况仍保留原来的禁用断言。随后分别执行：

   ```powershell
   node tests/test_photo_wire.mjs
   node tests/test_photo_wire_browser.mjs
   ```

   两项均退出 **0**；浏览器项 **1 passed，0 failed**。最终 49 个文件均已有通过结果，未重复全遍历。首遍逐文件日志和原始汇总保留在 `D:/dp-dev/tmp/burncancel/mjs-final/`，其中仍如实保留这两项首遍失败。

   这些既有测试额外生成的截图和作品夹具已从工作区移到本卡临时目录的 `suite-generated-impeccable/`、`suite-generated-works/`，保留内容，不纳入提交。

3. 新浏览器集成验收：

   ```powershell
   node tests/test_burn_cancel_browser.mjs
   ```

   最新结果：**24 项检查通过，退出 0**。使用真正的 `python -m disclab practice --media dvd-r --burn-time 0.3 --lab <独立目录> --port <空闲端口>`，再通过真实 HTTP 启动并取消标定刻录。覆盖锁定内拖动和长按无效、三种收起方式、重新计时、解锁后的部分拖动不取消／完整拖动才取消、双主题闪烁和减弱动态效果、用户标记、取消文案与按钮、步骤不打勾、真实页面刷新恢复、快照重放，以及 576 扇区盘不启动转速测量。另用刻录组件适配器验证开始滑块空格长按、停止滑块复用和回读一键停止。

   最新完整证据：`D:/dp-dev/tmp/burncancel/browser-K3fiT8/`，含 `checks.json`、`cancelled-job.json`、`short-disc-job.json`、`practice.log`。最后一次执行也验证了 Windows 稀疏镜像：`fsutil sparse queryflag` 报 sparse，`queryrange` 没有已分配范围。

4. `git diff --check` 通过。新增／修改含中文文件已检查非 ASCII 字符数大于 0，且没有连续问号损坏。修改通过 apply_patch 或 UTF-8 文件写入，没有把中文脚本从 PowerShell 管道送进原生程序。

## 截图

目录：`D:/dp-dev/tmp/burncancel/shots/`。已逐类查看画面，无新增配色或版式调整超出任务要求。

- `stop-button.png`：刻录中的文字停止按钮。
- `slider-locked-paper.png`、`slider-locked-dark.png`：纸色／夜色锁定倒计时。
- `slider-ready-paper.png`、`slider-ready-dark.png`：纸色／夜色解锁状态。
- `cancelled-result.png`：用户取消、实际进度百分比及安全重刻按钮。
- `short-576-disc.png`：576 扇区盘的原因和换盘出口。

## 取舍、局限与未测

- 首页现有危险状态使用铜色；另一套网页 tokens 虽有红色 `--error`，首页没有可直接复用的双主题亮红变量。因此新增局部 `burn-stop-tokens.css`：纸色 `--burn-danger: #c52020`，夜色 `#ff6b6b`，仅供本次停止风险文字使用。其余主题和组件颜色保持原样。
- 极短盘的保守阈值：已知预期容量时不超过其 1%；容量未知时不超过 4096 扇区。同时必须明确已封口、非空白、长度为正整数。未知状态、未封口和正常容量的盘不据此判作废。这是测量入口的明显短盘防护，不是整盘完整性验证，也不能证明中断原因。
- Disc Lab 的用户取消路径目前不保留部分刻录后的介质状态。取消操作、用户来源和页面恢复使用真实虚拟刻录；576 扇区场景是在同一独立 Lab 中明确注入已封口短盘状态，然后使用真实盘信息和标定核心检查。测试里的大镜像是零数据稀疏计时夹具，不是合格的随机数据测量镜像。
- 开发验收曾因普通文件扩展耗尽 D 盘空间；已将本卡临时目录中的计时夹具转为稀疏文件，保留日志和截图，并修复夹具以后用 Windows EOF API 扩展稀疏文件，避免 CRT truncate 分配零数据。
- 真光驱／真盘、IMAPI 两分钟收尾时长、实际刻后盘状态、服务进程重启后重新发现旧任务、屏幕阅读器实际播报、手机窄屏观感：**未测**。页面刷新、SSE 重连及 aria-live 属性已自动验证。没有接光驱、刻真盘、下载或上传，也没有修改纹理图谱脚本。
- 需要人决定的阻塞问题：无。亮红色数值和短盘阈值已列明，供审查；不以虚拟测试替代真盘结论。
