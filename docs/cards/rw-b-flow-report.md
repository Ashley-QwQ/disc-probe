# RWB 真盘走查修复

`dev/rw-b-flow` 基于 `73f7073`。在本分支提交，未推送或合并。测试服务均用 `--new-instance` 和独立端口。8765 和用户真实数据未改动，未接真光驱，作品走查停在刻录确认页。

## 提交

- `bedf116` 实现先存作品再绕路标定。回程按保存的批次 ID 关联原作品，生成该作品的 ISO 后进入刻录确认页。大厅加入焦点刷新、30 秒前台轮询、重新检测和检测时间。校准任务可从大厅主按钮和任务条返回，读盘步骤可单击停止。调整已刻光盘标签、盘名输入、剩余空白盘登记、DVD 预设提示、档案日期和无预览样式。新增 mjs 和 pytest 回归。
- `0b222fd` 固定异步保存使用的作品对象，补并发检测回归，并让档案测试等待实际缩略图加载。
- `6b6af6d` 保留用户主动新建同 MID 批次的选择。显式 CLI 关联的测量盘继续留在后台诊断记录中，作品状态、刻盘数量、时间线和预览保持按作品刻录记录计算。

- `1ee1a07` 增加校准停留后台和动画回程传递批次的状态测试。
- `d70a58d` 在校准表单归档动效起始时保留返回取消，兼容不报 MID 的已封盘以及独立大厅挂载。

## 行为与数据

- 检测日期和作品显示日期以浏览器本地时区为准。作品 ID、ISO 文件名和后端时间仍用 UTC，旧文件可读。验收记录包括多伦多 11 月 19 日 23 点多对应 UTC 11 月 20 日的日期边界。基线在同一受控时区也使用了本地日期，因此用户当时的 UTC 显示只由原始走查截图记录。
- 作品的批次继续写到现有 `work.json` 的 `batch` 字段。设计稿增加可选批次 ID，旧稿略去该字段时保留已有批次。按检测到的 MID 匹配已经标定的批次，优先使用已知批次 ID。手工明确命名一个新批次时，MID 相同仍保留用户的新批次选择。
- 测量盘默认留在校准任务的日志和结果。历史上自动生成的测量盘作品记录从界面隐藏，原文件保留。普通 CLI 刻录仍可查报告。直接 `burn` 一个 ISO 时没有源设计稿，后台原来生成的是空稿缩略图。曾用 `image --work` 保存相关设计快照的作品仍可显示预览。
- 用户这次保存的 DVD 预设有合法 JSON 和正常的 `source`，省略了 CD 用的 `photo_shift`。之前把省略的照片字段当成预设读不到。DVD 保存成功页只显示相关状态，确实读不到文件时使用“预设文件读不出来，请重新保存预设”。

## 验收

- `python -m pytest -n 2 --basetemp D:/dp-dev/tmp/rwb/pytest-final tests/test_works.py tests/test_webui_catalog.py tests/test_webui.py tests/test_webui_recovery.py` 通过 78 项。见 [Python 日志](../tmp/rwb/logs/pytest-final.txt)。
- 对 `tests/` 下全部 57 个 `test_*.mjs` 执行 `node --test --test-concurrency=1`。全量这轮为 77 项中 73 通过、4 失败。CSP 和 W245 浏览器用例单独重跑通过，分别是页面切换超时和 Edge 调试端口尚未就绪。往期作品和动效用例暴露了独立大厅、无 MID 封盘和在归档动效中按返回的兼容问题，修复后单独重跑通过。最终代码集中复跑这四个文件，4 项全部通过，见 [集中复跑日志](../tmp/rwb/logs/mjs-four-final.txt)。相关纯逻辑回归 13 项通过，容量用例也随最终修补复验通过。见 [全量日志](../tmp/rwb/logs/mjs-final.txt)、[CSP](../tmp/rwb/logs/mjs-csp-retry.txt)、[W245](../tmp/rwb/logs/mjs-editor-w245-retry.txt)、[动效](../tmp/rwb/logs/mjs-motion-retry.txt)、[往期作品](../tmp/rwb/logs/mjs-pastworks-retry.txt)。
- `python -X utf8 D:/dp-dev/tmp/rwb/walk.py after dark zh 390` 从空白虚拟盘实际生成并写入测量镜像，测量、保存并回到原作品。其余七组用同种子的预先写入虚拟随机盘，仍走真实 WebUI 标定、保存和生成作品 ISO。所有组都核对了标定前后的同一个作品 ID、标定批次 ID、`iso_ready` 和 ISO SHA-256。作品没有写入任何虚拟成品盘。测试脚本以 Edge CDP 驱动，并跳过了 Disc Lab 只供照片渲染用的纹理图生成。矩阵使用关闭动效的设置，动效另由仓库浏览器用例覆盖。
- 复现大厅停在校准后台的路径时，基线英文标题是 `Next: new work`，`Rotation` 旁仍是 `Stop burn`。修复后是 `Return to calibration` 和 `Stop`。两处返回入口都操作过，另有一次只读任务的单击停止试验。封盘报告为 DVD-ROM 的画面由 Disc Lab 改写驱动报告后复现，容量用例覆盖 MID 读不到的情况。
- 开跑及全量前 D 盘高于 5 GB。所有走查 Lab 已清理，整盘 ISO 留 SHA-256。源码差异和中文 UTF-8 检查通过。

| 主题 | 语言 | 宽度 | 刻录页截图 | 原作品 ID |
| --- | --- | ---: | --- | --- |
| 纸色 | 中文 | 390 | [after-light-zh-390-21-return.png](../tmp/rwb/shots/after-light-zh-390-21-return.png) | `w-20261120-051710-7390` · [日志](../tmp/rwb/logs/after-light-zh-390.log) |
| 纸色 | 中文 | 1440 | [after-light-zh-1440-21-return.png](../tmp/rwb/shots/after-light-zh-1440-21-return.png) | `w-20261120-050635-bfa5` · [日志](../tmp/rwb/logs/after-light-zh-1440.log) |
| 纸色 | 英文 | 390 | [after-light-en-390-21-return.png](../tmp/rwb/shots/after-light-en-390-21-return.png) | `w-20261120-051447-3721` · [日志](../tmp/rwb/logs/after-light-en-390.log) |
| 纸色 | 英文 | 1440 | [after-light-en-1440-21-return.png](../tmp/rwb/shots/after-light-en-1440-21-return.png) | `w-20261120-051448-6b36` · [日志](../tmp/rwb/logs/after-light-en-1440.log) |
| 夜色 | 中文 | 390 | [after-dark-zh-390-21-return.png](../tmp/rwb/shots/after-dark-zh-390-21-return.png) | `w-20261120-050232-ef3b` · [日志](../tmp/rwb/logs/after-dark-zh-390.log) |
| 夜色 | 中文 | 1440 | [after-dark-zh-1440-21-return.png](../tmp/rwb/shots/after-dark-zh-1440-21-return.png) | `w-20261120-051712-1901` · [日志](../tmp/rwb/logs/after-dark-zh-1440.log) |
| 夜色 | 英文 | 390 | [after-dark-en-390-21-return.png](../tmp/rwb/shots/after-dark-en-390-21-return.png) | `w-20261120-051217-7549` · [日志](../tmp/rwb/logs/after-dark-en-390.log) |
| 夜色 | 英文 | 1440 | [after-dark-en-1440-21-return.png](../tmp/rwb/shots/after-dark-en-1440-21-return.png) | `w-20261120-051930-1a63` · [日志](../tmp/rwb/logs/after-dark-en-1440.log) |

纸色中文 1440 和夜色中文 390 的截图拍于刻录页正在只读检查光驱时。两组的 ISO 和原作品关联均已验证。


### 截图索引

截图在 `D:/dp-dev/tmp/rwb/shots/`，日志在 `D:/dp-dev/tmp/rwb/logs/`。文件前缀中的 `light` 表示纸色。 `reported-before-` 是 11-19 真盘走查截图副本。其余由 Edge CDP 从基线或修复分支截图。

| 条目 | 修复前 | 修复后 |
| --- | --- | --- |
| 21、21b 原作品先存后回 | [before-light-zh-1440-21-return.png](../tmp/rwb/shots/before-light-zh-1440-21-return.png) | [after-dark-zh-1440-21-return.png](../tmp/rwb/shots/after-dark-zh-1440-21-return.png) |
| 1 大厅换盘再检测 | [before-light-zh-390-01-swap.png](../tmp/rwb/shots/before-light-zh-390-01-swap.png) | [after-dark-zh-390-01-swap.png](../tmp/rwb/shots/after-dark-zh-390-01-swap.png) |
| 3 大厅任务回程 | [before-light-en-1440-park-03-lobby-rotation.png](../tmp/rwb/shots/before-light-en-1440-park-03-lobby-rotation.png) | [after-light-en-1440-03-lobby-rotation.png](../tmp/rwb/shots/after-light-en-1440-03-lobby-rotation.png) |
| 4 读盘步骤停止 | [before-light-en-1440-park-03-lobby-rotation.png](../tmp/rwb/shots/before-light-en-1440-park-03-lobby-rotation.png) | [after-light-en-390-stop-04-rotation.png](../tmp/rwb/shots/after-light-en-390-stop-04-rotation.png) |
| 5、5b 测量盘和上次记录 | [before-light-en-1440-01-swap.png](../tmp/rwb/shots/before-light-en-1440-01-swap.png) | [after-dark-zh-390-01-lobby.png](../tmp/rwb/shots/after-dark-zh-390-01-lobby.png) |
| 20 DVD-ROM 标签和盘名输入 | [reported-before-item20-bounced-back-to-calibrate.webp](../tmp/rwb/shots/reported-before-item20-bounced-back-to-calibrate.webp) | [after-dark-zh-390-rom-20-name-scrolled.png](../tmp/rwb/shots/after-dark-zh-390-rom-20-name-scrolled.png) |
| 22 默认名用本地日期 | [reported-before-item21b-22-new-work-lost-design-utc-name.png](../tmp/rwb/shots/reported-before-item21b-22-new-work-lost-design-utc-name.png) | [after-light-en-1440-22-default-name.png](../tmp/rwb/shots/after-light-en-1440-22-default-name.png) |
| 23 档案日期和无预览 | [before-light-en-1440-23-archive.png](../tmp/rwb/shots/before-light-en-1440-23-archive.png) | [after-dark-zh-390-23-archive.png](../tmp/rwb/shots/after-dark-zh-390-23-archive.png) |
| 16 剩余空白盘 | [reported-before-item14-15-16-result-page.webp](../tmp/rwb/shots/reported-before-item14-15-16-result-page.webp) | [after-dark-zh-390-16-result.png](../tmp/rwb/shots/after-dark-zh-390-16-result.png) |
| 19 DVD 保存提示 | [reported-before-item19-preset-saved-dvd-alongtrack.png](../tmp/rwb/shots/reported-before-item19-preset-saved-dvd-alongtrack.png) | [after-dark-zh-390-19-preset.png](../tmp/rwb/shots/after-dark-zh-390-19-preset.png) |

已标定批次识别的补充证据见 [after-dark-zh-390-21-known-batch.png](../tmp/rwb/shots/after-dark-zh-390-21-known-batch.png)。

## 请 Claude 转达

- 请 RWA 保留 `calibrate.js` 的 `giveBack` 回传 `savedBatch`，以及保存成功后的作品批次同步。覆盖判定、预设接受条件和实时测量图由 RWA 统筹。RWB 的测试使用了通过原有覆盖判定的 Disc Lab 样盘。
- 请 RWC 合并 `calibrate.js` 和底栏样式时保留可点击任务名、写入与只读阶段的停止控制，以及窄屏盘名输入可滚到完整显示的行为。大范围版式和动效由 RWC 统筹。
- 测量盘分类采用“保留校准日志，历史自动作品记录在界面隐藏”。请审查是否以后增加独立“测量盘”档案。文案请审查“已刻好的光盘（光驱报告为 DVD-ROM）”和“这桶还剩几张空白盘（选填）”。计数只显示在盘库，留空可照常保存和刻录。

STATUS: DONE
