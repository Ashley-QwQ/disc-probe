# PL 预设导入／导出

分支 `dev/presetio-lang`，基点 `038ba9c`。

## 实现提交

- `5a13d46`。预设页读取站点当前语言并监听 `dp-lang`。按钮、表单、下拉选项、状态、错误、结果行、近似误差和无障碍文本都按当前语言更新。切换时保留文件、表单值、选择和预览，文件名及预设名按原样显示。中文结果优先用 `issues_zh`，对 v1 未翻译的动态校验消息补充中文。未识别的错误使用中文通用提示，英语界面保留原始错误说明。
- 同一提交把两条标签移到推子右侧，对齐原有指示灯高度。右侧空位避开纸张、信封和它们的动画区域，也避开推子下方的笔记本。宽高比小于 1.5、超过 2.4、宽度小于 820 px，或上方工具栏占用标签空间时，使用紧凑页签。紧凑标题随纸张排版，避免压住返回键。夜色灯下纸张沿用浅纸配深墨的配色，主按钮和文件按钮用浅色字。
- 产品改动限 `presetio.js` 与 `presetio.css`。两个测试文件同步更新双语旧断言，并增加单语、实时切换保留状态、标签几何和夜色对比度检查。

## 验收

- `python -X utf8 D:/dp-dev/tmp/presetiolang/run_tests.py all` 逐个执行 `tests/test_*.mjs`，首轮 53／57 通过。修正新作品走查的中文状态断言后，使用同一脚本的 `retry` 复跑通过。首轮无光驱环境变量也屏蔽了两个 Disc Lab 虚拟驱动测试，仅在这两个隔离夹具中去掉该变量后分别通过 32 和 18 个检查。材质库测试的静态文件保护规则把 worktree 名 `presetiolang` 误当成预设静态路径，通过 D 盘临时目录联接从另一个路径启动原测试后通过。最终 57／57 脚本通过。最后一轮预设页浏览器测试 10／10 场景通过。[测试日志](D:/dp-dev/tmp/presetiolang/logs/)
- `python -X utf8 D:/dp-dev/tmp/presetiolang/run_tests.py python` 执行 `pytest -n 2 -p no:cacheprovider --basetemp … tests/test_presets.py`，78 项通过。[pytest 日志](D:/dp-dev/tmp/presetiolang/logs/pytest-presets.log)
- `node D:/dp-dev/tmp/presetiolang/capture.mjs` 在无头 Edge 中通过 CDP 驱动独立服务，完成 28 次实际页面几何检查，其中桌面 12 次、紧凑 16 次。两条标签或页签都完整可见，能接收点击。共 17 张 PNG，覆盖 1890×1063、390×844 的导入与导出 × 中英 × 纸色与夜色，并附一张实际 CD 文件的预览结果行。另用界面语言按钮切换已打开的预览，验证保留文件并翻译结果行。[截图目录](D:/dp-dev/tmp/presetiolang/shots/) · [几何记录](D:/dp-dev/tmp/presetiolang/shots/geometry.json) · [导入结果](D:/dp-dev/tmp/presetiolang/shots/import-result-zh-paper-1890.png)
- 独立服务通过 `--local-only --no-drives --new-instance --port 0` 启动，实际导入一条 CD 预设，并在临时 `%LOCALAPPDATA%` 验证写出的 DiscImageStudio JSON。8765 验收前后均由 PID 31360 监听。真实用户预设文件、真实光驱、刻录、擦除及实机触屏未测。Disc Lab 的运行目录已清理。

## 给 Claude 转达

- 可转交产品提交 `5a13d46` 和截图目录。请以截图核对推子右侧标签与紧凑模式的观感。材质库浏览器测试从目录名包含 `presetio` 的 worktree 运行时会误拒自身静态文件，本卡用临时目录联接完成验收。

STATUS: DONE
