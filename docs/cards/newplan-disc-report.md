# ND 验收报告

分支 `dev/newplan-disc`，基点 `038ba9c`。所有提交留在本地分支。

## 提交

- `abd0cd1` 使用读盘接口的空白、封盘、可擦写和托盘状态写提示。只有已确认空白且盘型受支持时，光驱里的盘才参与推荐。修正只读 `disc` 命令解析托盘状态的逻辑，保留随错误说明返回的 SCSI 状态码。
- `9081eb1` 增加「稍后再定」。编辑器使用该介质的标称范围，保存留空状态，并在生成刻录文件前引导用户去盘库选批次。新增六个 Disc Lab 场景和一条保存、重开、选批次的流程回归。
- `45ecdc8` 保留旧作品和导航快照的批次语义。随盘文件测试显式选中一个小镜像夹具批次。纹理库浏览器测试按相对资源路径判断分区，使它可以从名为 `newplandisc` 的 worktree 运行。
- `1229253` 按完整光驱盘型匹配转盘，避免把 DVD-RAM 当成 DVD-R。新建页回归等待浏览器历史返回完成后再进盘库。

## 修复前后

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 空白 DVD-R，MID 为 RITEKF1 | 主要显示识别到的类型，MID 取决于选中的批次 | 明示是空白盘并显示 RITEKF1。自动转到 DVD-R，推荐 RITEKF1 批次 |
| 已封盘，报 DVD-ROM | 只念出 ROM，转盘可能回到 DVD-R | 提示已封盘、可先设计、刻前换空白盘。验收中保留历史 DVD+R 及其批次 |
| 已写入、未封盘 | 可按已写入的盘推荐批次 | 明示已经刻过、尚未封盘。沿用历史设置 |
| 有数据的 RW | 可把当前盘当推荐批次 | 提示刻前须擦除。沿用历史设置 |
| 空托盘、开托盘 | 只读接口可能把两者都报成未知，表单也可能遮掉托盘提示 | 分别显示「光驱里没有盘」和「光驱托盘开着」。沿用历史设置 |
| 空白状态未知 | 可按当前盘型推荐 | 明示无法确定是否空白，沿用历史设置 |
| 批次留空 | 清空入口不明显，预览可能沿用最新几何 | 「稍后再定」清空建议，仍能进入编辑器。编辑器提示按标称范围画，预览下一步前往盘库 |

## 作品文件和刻录入口

留空的 `.discdesign` 继续使用版本 2 和原 `media` 字段。新增可选布尔字段 `batch_deferred: true`，此时 `batch`、`disc` 和 `geo` 都为 `null`。往期作品保存同一份 JSON。选中批次后按已有批次字段保存，序列化时省略 `batch_deferred`。没有这个字段的旧作品走原有批次语义，包括旧版里意义不唯一的 `batch: null`。

预览页将下一步改成「选批次」。`design.js` 的 `makeBurnFile()` 和 `makeCheckFile()` 会在发任务前检查留空标记，`toBurn()` 在打开刻录页之前再检查一次。RW 的擦除流程沿用既有核心功能，新建作品页只提示用户。

## 验收

- `node tests/test_newplan_disc_browser.mjs` 通过六种 Disc Lab 盘况和一条留空流程。流程覆盖写入往期作品、从服务器取回文件重开、读取 v1 文件、选批次返回编辑器。留空时生成镜像被拒绝，服务器任务数为 0。ROM 场景在 Disc Lab 中把已封盘 DVD-R 的当前 MMC profile 设为 `0x10`，浏览器仍经真实只读接口取数据。
- `python -B -X utf8 D:/dp-dev/tmp/newplandisc/run_regressions.py` 全量首轮为 55/58。复跑 `node tests/test_disc_files_browser.mjs`、`node tests/test_editor_texlib_browser.mjs`、`node tests/test_rw_discs_browser.mjs` 均通过，58 个脚本各有通过记录。前两项修正了测试夹具，RW 首轮是 Edge 重载时动态模块加载失败，原命令重跑通过 18 项检查。最后又单独通过了新建页的两个浏览器脚本。日志在 [测试目录](D:/dp-dev/tmp/newplandisc/)。
- `python -B -X utf8 -m pytest -n 2 --basetemp D:/dp-dev/tmp/newplandisc/pytest-scratch tests/test_webui.py tests/test_webui_catalog.py tests/test_works.py tests/test_rw_discs.py tests/test_design_compose_route.py` 通过 117 项。第二次耗时 29.55 秒。 [pytest 日志](D:/dp-dev/tmp/newplandisc/pytest.log)
- [截图目录](D:/dp-dev/tmp/newplandisc/shots/) 有 9 张 PNG。六种盘况各一张 1440 × 900，覆盖纸色、夜色及中英文。另有一张 ROM 的 390 × 844 截图，及两张编辑器和预览流程截图。用 Pillow 核对尺寸，窄屏测试同时检查盘况提示位于下一步按钮上方。
- `git diff 038ba9c..HEAD --check` 通过。开跑和全量回归前 D 盘均余 154 GB 以上。Disc Lab 每个成功场景结束即删除临时目录。8765 端口验收前后的监听 PID 均为 `31360`。

## 未测和转达

- 实体光驱、实盘换盘和实体刻录未测。盘况和流程以 Disc Lab 为验收依据。
- 请 Claude 转达给 burn-gates 会话。合入时保留 `preview.js` 的选批次入口，以及 `design.js` 的 `toBurn()` 入口检查。涉及同一文件的其他检查可以各自继续负责光驱和盘况，`burn.js` 此卡无改动。
- 无待决的实现问题。

## 补充第 5 项 · 批次下拉

- `c7d6c96` 批次框一获得焦点就展开列表，框尾箭头也能开合。列表列出当前介质（DVD、CD 或 BD）的全部可用批次，已标定的在前并显示日期，同组沿用盘库顺序。输入仍可按名称和 MID 筛选。选择同介质的另一子类型时转盘会同步。「稍后再定」位于列表末尾，可以点击，也可以用方向键和回车选中。
- `bac1f84` 更新 IME 回归夹具，让它继续验证组合输入时按回车不会误选批次。
- `node tests/test_newplan_disc_browser.mjs` 通过六种 Disc Lab 盘况和留空流程，每种都检查点进空框后列出的批次和日期。390 像素时从列表选「稍后再定」，仍可保存并重开设计，生成刻录文件前被拦，服务器任务数为 0。`node tests/test_review_library_newwork.mjs` 通过，覆盖已标定批次排序、名称和 MID 筛选、键盘选项和转盘同步。 [Disc Lab 日志](D:/dp-dev/tmp/newplandisc/regressions-supplement/test_newplan_disc_browser/node.log)
- 按原验收跑了全部 58 个 JavaScript 脚本，首轮通过 56 个。`node tests/test_ime_activity.mjs` 更新夹具后复跑通过 14 个回车处理器，每个检查 3 种键盘事件。`node tests/test_pastworks_browser.mjs` 首轮所有界面断言通过，Edge 关闭未返回回执，原命令复跑退出码为 0。58 个脚本各有通过记录。 [全量日志](D:/dp-dev/tmp/newplandisc/node-supplement.log) · [IME 复跑](D:/dp-dev/tmp/newplandisc/ime-supplement.log) · [往期作品复跑](D:/dp-dev/tmp/newplandisc/regressions-supplement/test_pastworks_browser/retry.log)
- 原验收命令中的 5 个 Python 测试文件用 `pytest -n 2` 重跑，117 项通过，耗时 28.92 秒。 [pytest 日志](D:/dp-dev/tmp/newplandisc/pytest-supplement.log)
- 更新原 9 张截图并补拍 3 张展开列表的截图，覆盖纸色中文 1440、夜色英文 1440 和夜色英文 390。已核对 12 张 PNG 的尺寸。8765 端口验收前后均由 PID `31360` 监听。 [截图目录](D:/dp-dev/tmp/newplandisc/shots/)

STATUS: DONE
