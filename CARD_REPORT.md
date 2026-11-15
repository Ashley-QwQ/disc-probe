# 卡 J：刻后结果与重开恢复

分支：`dev/flow-after-burn`。工作区：`D:/dp-dev/afterburn`。

## 按提交列出的改动

本卡采用一个提交：`feat: persist post-burn review and restore report navigation`。

- **核心记录**：作品的每次刻录有独立的 `burn_id`，保留原始刻录报告、关盘证据、ISO 路径和 SHA-256、关联测量、job ID、用户观察及历史事件。用户观察不改变光驱报告；只确认最新一次“看到了，位置对”才把作品标为完成。旧库缺少编号时生成稳定编号，缺少预览时明确说明没有保存。
- **保存预览**：生成 ISO 时把库中设计和 512 像素缩略图存成内容寻址资源；刻录关联同 SHA-256 的 ISO 快照，之后编辑作品不会换掉旧刻录的预览。设计、预览和观察随作品 ZIP 导出、导入。恢复时先显示保存的缩略图，完整设计仍可通过“打开作品”进入现有编辑器。
- **没有作品关联的刻录**：CLI 或网页任务未传作品 ID 时，优先找 ISO 对应作品；找不到就自动保存刻录记录。没有提供原设计稿的记录明确标记不可恢复设计预览，不用空白设计冒充原图。失败或中断的刻录也保存本次实际产生的报告；写入前失败不会借用同 ISO 上次的日志。
- **W12**：成品刻录完成后的右下按钮进入“结果怎么样？”。四种选择写入核心。位置对：存为完成，并派发 `dp-after-burn-confirmed` 扩展事件；没有制作礼花动画。看不见：光照文字、现有带图说明入口、四项刻录报告。歪了或扭了：先核对盘批次、刻录机和读取光驱，再看这次测量的覆盖与检查；DVD 可生成检查盘、进入现有确认刻录页、拍照后返回；CD 接现有照片读取沿轨常数路线；之后打开作品重新生成，重新测量放在最后。断开或缺块：报告、保留/重读日志建议和换速度准备入口，注明慢不一定更好。
- **N04**：大厅沿用“上次”按钮展示最近刻录报告和预览；作品详情增加同一入口。恢复只查看，不会自动发起刻录。恢复预览的右下和左上都返回刻录报告。
- **CLI / HTTP**：新增 `works after-burn ID [--choice correct|invisible|distorted|gaps] [--burn BURN_ID] [--json]`。HTTP 提供相同观察读写、指定刻录的设计/缩略图和关联测量读取；沿用现有鉴权、作品锁和原子更新。
- **范围**：未修改 `design.js` 或其设计页模块，未修改 `evidence/atlas/*.py`。配色只引用现有变量，夜色纸面复用现有灯下纸色变量；固定左上返回、右下完成。测试产生的库和截图已移到 D 盘临时目录，未纳入提交。

CLI 示例（把 `ID` 换成作品编号）：

```text
python -m discprobe works after-burn ID --json
python -m discprobe works after-burn ID --choice distorted --json
```

## 验收命令和结果

临时目录及浏览器配置目录均放在 `D:/dp-dev/tmp/afterburn/`；运行前设定 `TEMP`、`TMP` 指向该目录。Python 测试使用 `-n 2`。

| 命令 / 检查 | 结果 |
| --- | --- |
| `python -m pytest -n 2 tests/test_afterburn.py tests/test_works.py tests/test_burner.py tests/test_webui.py tests/test_burn_progress.py tests/test_web_guidance.py disclab/tests/test_disclab.py -k "not truth" --basetemp D:/dp-dev/tmp/afterburn/pytest-confirm -q` | 132 passed，46 subtests passed |
| HTTP 空选择校验、Disc Lab 测试隔离调整后：`python -m pytest -n 2 tests/test_afterburn.py disclab/tests/test_disclab.py -k "not truth" --basetemp D:/dp-dev/tmp/afterburn/pytest-last -q` | 31 passed |
| 增补本次失败日志隔离测试后：`python -m pytest -n 2 tests/test_afterburn.py --basetemp D:/dp-dev/tmp/afterburn/pytest-failure -q` | 10 passed |
| 逐个 `node tests/test_*.mjs`，所有匹配文件（41 个） | 41 / 41 退出码 0；未重复跑整个 Python 套件 |
| 最终相关复验：`node tests/test_afterburn_browser.mjs` | 15 个 Disc Lab / 浏览器检查通过 |
| `node tests/test_burn_page.cjs` | recorded-event checks passed |
| 对实际 Disc Lab 刻录记录用独立 CLI 进程依次选择四种结果 | 4 / 4 保存成功，原报告中的 96 块回读结果保持不变 |
| `git diff --check` | 通过 |

全部 `.mjs` 的逐项输出在 `D:/dp-dev/tmp/afterburn/mjs-logs/`，汇总为 `results.json`。浏览器最后一轮结果是 `D:/dp-dev/tmp/afterburn/browser-results.json`；独立 CLI 结果是 `D:/dp-dev/tmp/afterburn/cli-check.json`。

### Disc Lab 与截图的证据范围

- 使用隔离的 Disc Lab DVD-R 虚拟光驱和 4096 扇区小镜像，经过实际核心刻录任务和确认滑块。报告为请求/实际速度 8×、关盘 complete、抽样 96 块一致、0 不同、0 读不出、0 未检查。这是抽样，不是整盘验证。
- 四个分岔在实际网页逐一选择并保存；点击打开光照图示、关联测量和保存预览；清掉整页模块状态后重新导航 `/home/`，从真实大厅入口找回；再从作品详情入口找回同一观察。另验收英文和 390×844 窄屏纸面边界。
- 浏览器测试通过组件适配器把预先准备的小 ISO 放进现有刻录组件，后续核心、HTTP、持久化和真实恢复入口不做假响应。**小 ISO 是 random 测试内容；截图里的设计和覆盖记录是导航夹具，不证明该小 ISO 刻出了图案，也不是一次真实几何测量或照片修正验证。**
- 全程未访问实物光驱、未刻实体盘、未上传数据。

截图在 `D:/dp-dev/tmp/afterburn/shots/`：

- `correct-paper.png`、`correct-dark.png`
- `invisible-paper.png`、`invisible-dark.png`
- `distorted-paper.png`、`distorted-dark.png`
- `gaps-paper.png`、`gaps-dark.png`
- `reopened-entry.png`：重开大厅后的入口
- `mobile-night.png`：窄屏英文恢复页

已查看纸色、夜色、重开入口和窄屏截图；右栏长内容滚动，固定角落按钮可用。

## 未测、限制及需要人决定的问题

- DVD 的完整“大检查盘生成 → 确认刻录 → 拍摄多张照片 → 修正沿轨偏移 → 重新生成成品”实跑：**未测**。本卡接入现有核心生成、刻录和照片流程，验收覆盖到分岔入口及关联测量，不把它写成完成照片标定。
- CD 完整虚拟刻录、照片读取或导出 DIS 预设闭环：**未测**；CD 的分支接入现有照片路线和指导文字，没有声称补齐 Windows 原有 CD 刻录器能力。
- 本卡恢复的是设计快照及其 512 像素预览，不恢复旧标签的灯下模拟机位、播放状态、缩放或平移。没有原设计的 CLI 刻录、历史旧库没有保存的预览会明确显示缺失。
- 作品设计快照取自 ISO 关联入库时的已保存设计；“生成中另一个标签改写同一作品”的并发设计版本追踪没有新增保证。
- 正在运行的刻录在重开网页后自动接管进度：**未测且未新增**；本卡解决已完成刻录的持久报告、预览和刻后观察恢复。
- 机械 UI 检测器只对现有 `index.html` 给出纸色底、既有光晕及条纹建议。纸色是明确风格要求，其余属于本卡外既有视觉，未调整。
- 无阻断提交、需要用户先批准的问题。若后续要求完整灯下机位恢复或对大检查盘/CD 路线追加实跑，可作为进一步验收；本报告保留上述未测边界。
