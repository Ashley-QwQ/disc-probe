# TB 浏览器测试统一验收

工作树 `D:/dp-dev/testbrowser`，分支 `dev/test-browser`，基点 `67729c9`。测试和工具的浏览器进程均使用本机 chrome-headless-shell。涉及光驱的浏览器测试使用独立的 Disc Lab，测试服务使用临时端口。全程未连接 8765。

## 提交

- `56b4d2b` 统一浏览器选择、启动参数、DevTools 配置路径和进程树清理。Windows 默认选 shell，Edge 或完整版 Chrome 只用各自的固定配置目录。Python 工具也通过 Node 调用同一启动器。旧变量保留，实际采用旧变量时提示改用 `DP_TEST_BROWSER`。
- `008d583` 等待刷新后的文档及任务标题出现再核对现场任务恢复，保留原有断言。移除刻后测试中迁移后用不到的文件检查导入。

## 修改范围

- 26 个直接启动浏览器的测试。下列名称均在 `tests/` 下。
  - `test_afterburn_browser.mjs`、`test_brand_browser.mjs`、`test_burn_cancel_browser.mjs`、`test_csp_browser.mjs`、`test_curve_edit_browser.mjs`、`test_disc_files_browser.mjs`
  - `test_editor_desk_browser.mjs`、`test_editor_fit_browser.mjs`、`test_editor_texlib_browser.mjs`、`test_faxnews_browser.mjs`、`test_flow_navigation_browser.mjs`、`test_gui_handshake_browser.mjs`
  - `test_ime_activity.mjs`、`test_kit_browser.mjs`、`test_motion_browser.mjs`、`test_newplan_disc_browser.mjs`、`test_pastworks_browser.mjs`、`test_photo_wire_browser.mjs`
  - `test_presetio_browser.mjs`、`test_reshoot_browser.mjs`、`test_review_library_newwork.mjs`、`test_running_job_browser.mjs`、`test_rw_discs_browser.mjs`、`test_shelf_nav_browser.mjs`、`test_title_font_alignment.mjs`、`test_web_retry_browser.mjs`
- `tests/test_editor_w245_browser.mjs` 经 `tools/editor_w245_check.mjs` 间接进入同一启动器。用同一 shell 重跑 `731b199` 的浅色预览取得参考哈希。当前浅色、夜色各两档都与该参考逐像素一致，原 Edge 参考哈希保留。
- 传真脚本用原有 JSON 构建文件夹具响应。动效、往期作品正式页和新作品审查通过一份回环夹具提供静态资源，继续使用原页面与断言。两个 Disc Lab Python 夹具在自己的虚拟盘进程中解除全局禁用光驱的环境变量。
- 迁移 `tools/audit_colour_web.mjs`、`tools/editor_shots.mjs`、`tools/editor_w245_check.mjs`、`tools/export_brand_icons.py`、`tools/verify_news_browser.py`，以及 `tools/night_lobby/capture_final.mjs`、`tools/night_lobby/capture_trial.mjs` 和 `evidence/page-teardown/measure.mjs`。
- 新增 `tests/browser.mjs`、`tests/browser_fixtures.mjs`、`tools/browser.py` 和 `tests/README.md`，原 `tests/edge_cleanup.mjs` 的清理逻辑并入启动器。

## 验收

- `git grep -n -i "msedge" -- tests tools` 应用路径排除规则后仅有一行。

  ```text
  tests/browser.mjs:10:const edgeExe = 'msedge.exe';
  ```

- 默认浏览器环境下，将 63 个 `tests/test_*.mjs` 逐个用 `node --test --test-concurrency=1 <file>` 运行。合计 63/63 个文件、93 个 Node 测试通过，0 跳过。首轮的夹具及等待问题均已定向复验。重拍用例首轮达到外部 260 秒上限，延长后在 637.8 秒内完成两个 Disc Lab 场景。 首轮和定向复跑的逐文件记录在 `D:/dp-dev/tmp/testbrowser/node-all/`、`node-remaining/`、`node-recheck/`、`node-running-job/` 和 `node-reshoot-long/`。
- `python -X utf8 -u -B -m discprobe selftest` 退出 0，1490 条检查，末行 `all checks passed`，耗时 460.3 秒。首轮达到外部记录程序的 260 秒上限，延长上限后完成。日志在 `D:/dp-dev/tmp/testbrowser/selftest-final/selftest.log`。
- `python -X utf8 -B -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/testbrowser/python/pytest-work tests/test_brand_assets.py tests/test_news.py tests/test_burn_cancel.py tests/test_rw_discs.py tests/test_discfiles.py` 通过 108 项。日志在 `D:/dp-dev/tmp/testbrowser/python/pytest.log`。
- `node D:/dp-dev/tmp/testbrowser/launcher_proof.mjs` 将 `DP_HEADLESS_SHELL` 指向不存在的路径，两次选择均得到 `%LOCALAPPDATA%/disc-probe-test-browser/edge-profile`。随后用 shell 在 D 盘的隔离目录执行同一固定配置调用流程，两次启动后标记文件仍在，并行启动因占用配置而拒绝。该核查也确认了旧变量提示和统一变量的优先级。

| 工具命令 | 结果 |
| --- | --- |
| `node tools/editor_shots.mjs <plan.json> <out>` | 退出 0，隔离的 `about:blank` 页面完成求值并保存 1 张 PNG。 |
| `node tools/editor_w245_check.mjs after`，`W245_SKIP_PERF=1` | 退出 0，18 项可用性检查，4 个静止预览哈希与参考相同。 |
| `python tools/export_brand_icons.py --temp-dir <out>` | 在 D 盘临时副本中退出 0，导出核心图标 21 个及 Lab 副本 7 个。 |
| `python tools/verify_news_browser.py --out <out>` | 退出 0。网络样张与自带样张各测纸色、夜色，4 张 1440×1000 截图。网络样张读取独立回环镜像。 |
| `node tools/audit_colour_web.mjs <out>` | 启动了 shell，通过握手并导入测试图。后续等待 `[data-ed-choice=fillKind][data-value=colour]` 超时，退出 1。基点的编辑器控件只把 `material`、`pattern` 和 `effect` 列为该控件的选项。整段颜色审计未通过。 |

工具日志和截图在 `D:/dp-dev/tmp/testbrowser/tools/` 和 `audit-recheck/`。

## 安全日志和磁盘

第一轮 shell 命令前记录 `2026-11-23T19:15:06.7395196-05:00`。逐文件及各工具结束后查询安全日志，最后一次总查覆盖至 `2026-11-23T19:53:29.2451227-05:00`。汇总新增 4625 **0 条**、4740 **0 条**。查询及输出如下。

```powershell
$start = [DateTimeOffset]::Parse('2026-11-23T19:15:06.7395196-05:00').LocalDateTime
Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625,4740;StartTime=$start}
```

```text
NoMatchingEventsFound,Microsoft.PowerShell.Commands.GetWinEventCommand
No events were found that match the specified selection criteria.
4625=0, 4740=0
```

D、F 起始可用空间分别为 46.43 GiB 和 43.35 GiB，测试期间均高于 5 GB。中止的临时镜像、Lab 目录和浏览器配置已清理，检查盘证据保留哈希。

## 未测项和交接

- 本次执行只授权启动 chrome-headless-shell。完成条件 3 的两项真实 Edge 测试及两轮 4625 验收未测。需由审查者决定是否接受 shell 的固定配置复用证据，或将真实 Edge 验收交给明确授权的独立环境。
- `test_editor_fit_browser.mjs` 的默认测试用 CSS 视口和设备像素比覆盖各缩放比例，完成 301 次测量。使用 `EDITOR_FIT_NATIVE_ZOOM=1` 的原生标签页扩展路径和 Edge 内存证据工具未测。Linux 浏览器启动及两份夜间大厅历史截图工具未测。
- 请 Claude 更新 `D:/dp-dev/cards/COMMON.md`。将旧浏览器变量列表换为 `DP_TEST_BROWSER`，保留 shell 路径及固定配置目录要求。

STATUS: BLOCKED
