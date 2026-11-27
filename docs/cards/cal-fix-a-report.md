# CF 校准 A1–A3 验收

工作树 `D:/dp-dev/calfix`，分支 `dev/cal-fix-a`，基点 `f7abffc`。Disc Lab 复验只使用虚拟 X:，界面由脚本驱动无头 Edge 157.0.4341.60。

## 提交

- `94042c3` · A1 让窄屏刻录任务使用整行页脚，停止键可直接点到，展开的确认面板贴在页脚上方。A2 用已完成任务的退出码和结果接回校准页，在结果首次前台显示或成功保存时记录 `result-seen`。A3 给未知容量的已刻测量盘提供同批空盘检测和手填两个入口，扇区数经已有的 `calibrate --sectors` 传给 core。测试覆盖窄屏实际命中、接回标记的后端状态、两种取容量的路径和下发参数。

## 修复前后对照

### A1 · 停止刻录

390×844 下的 4 种组合，每组实际用触摸分别点首次进入、刷新后、关闭重开后的停止键，共 12 次。每次核对风险文字、3 秒倒数、滑轨和继续刻录按钮都在视口内。各组在重开后拖动滑块，4 次均停止原来的虚拟任务。1440×1000 的桌面停止、倒数、拖动和取消接回由仓库浏览器测试复验。

| 组合 | 修复前 | 修复后 |
| --- | --- | --- |
| 纸色中文 | [停止键重叠](<D:/dp-dev/tmp/calfix/shots/before-a1-paper-zh.jpg>) | [首次进入](<D:/dp-dev/tmp/calfix/shots/a1-paper-zh-retry/01-active-risk-countdown.jpg>) · [刷新](<D:/dp-dev/tmp/calfix/shots/a1-paper-zh-retry/02-after-reload-risk-countdown.jpg>) · [重开](<D:/dp-dev/tmp/calfix/shots/a1-paper-zh-retry/03-after-close-risk-countdown.jpg>) |
| 纸色英文 | [停止键重叠](<D:/dp-dev/tmp/calfix/shots/before-a1-paper-en.jpg>) | [首次进入](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-3-cf-a1/01-active-risk-countdown.jpg>) · [刷新](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-3-cf-a1/02-after-reload-risk-countdown.jpg>) · [重开](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-3-cf-a1/03-after-close-risk-countdown.jpg>) |
| 夜色中文 | [停止键重叠](<D:/dp-dev/tmp/calfix/shots/before-a1-dark-zh.jpg>) | [首次进入](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-22-cf-a1/01-active-risk-countdown.jpg>) · [刷新](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-22-cf-a1/02-after-reload-risk-countdown.jpg>) · [重开](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-22-cf-a1/03-after-close-risk-countdown.jpg>) |
| 夜色英文 | [停止键重叠](<D:/dp-dev/tmp/calfix/shots/before-a1-dark-en.jpg>) | [首次进入](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-23-cf-a1/01-active-risk-countdown.jpg>) · [刷新](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-23-cf-a1/02-after-reload-risk-countdown.jpg>) · [重开](<D:/dp-dev/tmp/calfix/shots/mx-active-matrix-23-cf-a1/03-after-close-risk-countdown.jpg>) |

### A2 · 关页后接回

同一任务先在运行时重开，随后关页等它以 0 退出。基线回到首页，修复后进入结果页，可以保存。另开新页分别验证了已看未保存、已保存两种状态，均停在首页。任务事件和退出状态沿用原记录，查看确认用新增的小文件及状态字段。刻录取消仍走既有接回流程，由仓库测试及 A1 的停止结果复验。

| 时机 | 修复前 | 修复后 |
| --- | --- | --- |
| 任务仍在运行时重开 | [回到任务](<D:/dp-dev/tmp/calfix/shots/before-a2/14-reopen-running.jpg>) | [回到同一任务](<D:/dp-dev/tmp/calfix/shots/after-a2-final/14-reopen-running.jpg>) |
| 任务在关页期间完成后重开 | [停在首页](<D:/dp-dev/tmp/calfix/shots/before-a2/15-reopen-finished.jpg>) | [回到结果](<D:/dp-dev/tmp/calfix/shots/after-a2-final/15-reopen-finished.jpg>) · [保存成功](<D:/dp-dev/tmp/calfix/shots/after-a2-final/16-saved.jpg>) |
| 看过或保存后再打开 | — | [看过未保存](<D:/dp-dev/tmp/calfix/shots/after-a2-final/15-seen-before-save-reopen.jpg>) · [已保存](<D:/dp-dev/tmp/calfix/shots/after-a2-final/17-saved-reopen.jpg>) |

### A3 · 已刻测量盘的容量

同一批虚拟 DVD-R 的可读长度是 2,252,512 扇区，空白容量是 2,298,496 扇区。推荐路径先检测同批空盘，再检测换回的测量盘。刻好的盘留在空盘步骤、空盘留在测量盘步骤时，两次都提示重试。备用路径输入框起初为空，小数无法提交。两路的任务参数与 core 返回均为 2,298,496，退出码均为 0，两次都保存了预设。

| 路径 | 修复前 | 修复后 |
| --- | --- | --- |
| 读同批空盘 | [只报容量未知](<D:/dp-dev/tmp/calfix/shots/before-a3-zh.jpg>) | [入口](<D:/dp-dev/tmp/calfix/shots/mx-capacity-swap-4-cf-a3-full/10-capacity-paths.jpg>) · [读到容量](<D:/dp-dev/tmp/calfix/shots/mx-capacity-swap-4-cf-a3-full/12-capacity-read.jpg>) · [保存](<D:/dp-dev/tmp/calfix/shots/mx-capacity-swap-4-cf-a3-full/23-saved.jpg>) |
| 手填空盘扇区数 | [勾选入口](<D:/dp-dev/tmp/calfix/shots/before-a3-prepare-zh.jpg>) · [报错](<D:/dp-dev/tmp/calfix/shots/before-a3-zh.jpg>) | [填入扇区数](<D:/dp-dev/tmp/calfix/shots/mx-capacity-manual-4-cf-a3-full/11-manual-entry.jpg>) · [保存](<D:/dp-dev/tmp/calfix/shots/mx-capacity-manual-4-cf-a3-full/23-saved.jpg>) |

## 复验命令与结果

- `python -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/calfix/check-python/pytest`，文件为 `tests/test_{webui,webui_recovery,webui_catalog,burn_cancel,afterburn,recordable_capacity,single_instance}.py`。110 通过，0 失败，99.25 秒。[pytest 日志](<D:/dp-dev/tmp/calfix/pytest.log>)
- 用 `node <文件>` 逐一跑完 `tests/test_*.mjs` 共 56 个文件。首轮 54 通过，`test_csp_browser.mjs` 和 `test_disc_files_browser.mjs` 在页面导航处等待超时。原文件单跑重试 2 通过，合计 56 个文件都取得通过结果。[全量日志](<D:/dp-dev/tmp/calfix/node-results.txt>) · [两项重试](<D:/dp-dev/tmp/calfix/retry-results.txt>)
- 在 D 盘复制 CW 的 `walk.mjs`、`cdp.mjs`、`matrix.mjs`，添加点击命中、视口、任务标识与容量的断言。用 `WALK_STRICT_STOP=1 WALK_TOUCH=1 node matrix.mjs active-matrix 2,3,22,23 cf-a1`，纸色中文首次刷新等待超时，单组用 `WALK_ACTIVE_SECTORS=262144 node walk.mjs active-matrix 2 real a1-paper-zh-retry` 通过。用 `WALK_STRICT_REOPEN=1 node walk.mjs finished-reopen 21 0.04 after-a2-final`，并用相同组合在基线重跑。用 `node matrix.mjs capacity-swap,capacity-manual 4 cf-a3-full` 通过两条路。早期容量轮引用了已经清理的旧虚拟镜像，正式轮各自用新虚拟测量盘复验。[脚本](<D:/dp-dev/tmp/calfix/walk.mjs>) · [A2 运行记录](<D:/dp-dev/tmp/calfix/shots/after-a2-final/run.json>) · [空盘路径记录](<D:/dp-dev/tmp/calfix/shots/mx-capacity-swap-4-cf-a3-full/run.json>) · [手填路径记录](<D:/dp-dev/tmp/calfix/shots/mx-capacity-manual-4-cf-a3-full/run.json>)
- `python -X utf8 D:/dp-dev/tmp/calfix/verify-evidence.py` 校验 62 张 JPEG 的尺寸和可读性，以及运行记录里的关键断言。开工和全量 JavaScript 前均检查 D 盘。开工约 184 GiB，收尾清理后约 167 GiB。

### 六组走查回归

DVD 各组走到保存并返回新作品。CD 各组走到拍照页，再跳过拍照并保存。用 `node matrix.mjs dvd 0,3,28 cf-regression`、`node matrix.mjs cd 5,22,36 cf-regression` 与 `node walk.mjs dvd 28 quick dvd-dark-auto-regression`。

| 场景 | 组合 | 证据 |
| --- | --- | --- |
| DVD · 首次流程、无盘重试 | 纸色，中文，1440×900，动效开 | [返回新作品](<D:/dp-dev/tmp/calfix/shots/mx-dvd-matrix-0-cf-regression/25-return-end.jpg>) |
| DVD · 首次流程、无盘重试 | 纸色，英文，390×844，动效开 | [返回新作品](<D:/dp-dev/tmp/calfix/shots/mx-dvd-matrix-3-cf-regression/25-return-end.jpg>) |
| DVD · 首次流程 | 夜色，中文，1440×900，跟随系统减弱动效 | [返回新作品](<D:/dp-dev/tmp/calfix/shots/dvd-dark-auto-regression/25-return-end.jpg>) |
| CD · 拍照页、跳过并保存 | 纸色，英文，1440×900，动效关 | [保存](<D:/dp-dev/tmp/calfix/shots/mx-cd-matrix-5-cf-regression/27-photo-saved.jpg>) |
| CD · 拍照页、跳过并保存 | 夜色，中文，390×844，动效开 | [保存](<D:/dp-dev/tmp/calfix/shots/mx-cd-matrix-22-cf-regression/27-photo-saved.jpg>) |
| CD · 拍照页、跳过并保存 | 夜色，中文，1440×900，系统减弱且动效关 | [保存](<D:/dp-dev/tmp/calfix/shots/mx-cd-matrix-36-cf-regression/27-photo-saved.jpg>) |

## 待审与未测

- 请 Claude 转达给审查者核对 A3 中英文文案。当前做法是勾选测量盘后才出现容量选项，先列推荐的同批空盘检测，再列手填。输入框旁的 DVD-R 2,297,888、DVD+R 2,295,104 仅作参考。
- 本卡按要求使用根目录的 `CARD_REPORT.md`。如合并时需要保留社区卡旧报告，可从 `git show f7abffc:CARD_REPORT.md` 取回。
- A2 把结果页在前台呈现算作看过，已看未保存的结果随后也不会自动弹出。服务重启后的恢复未测。390×844 的结果来自无头 Edge 的视口和触摸模拟。实体手机、真实光驱和 CD 照片修正未测。
- CW 的 B3 在 A3 正式轮仍偶发首检 409，按原入口重试后通过。夜色自动减动的 DVD 矩阵首轮等待无盘提示超时，保留现场。该组合的正常 DVD 流程单跑通过。[B3 现场和重试](<D:/dp-dev/tmp/calfix/shots/mx-capacity-swap-4-cf-a3-full/run.json>) · [无盘超时](<D:/dp-dev/tmp/calfix/shots/mx-dvd-matrix-28-cf-regression/run.json>)

STATUS: DONE
