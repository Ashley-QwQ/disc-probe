# 卡 PL（goal）：预设导入/导出页跟随界面语言，标签不被纸张盖住（11-20 写，赶 alpha）

先读 `D:/dp-dev/cards/COMMON.md`。

- worktree：`D:/dp-dev/presetiolang`，分支 `dev/presetio-lang`
- 基点：`038ba9c`（`dev/rw-c-polish`）
- **周六 11-21 18:00 前交付**
- 只动 `discprobe/web/home/presetio.js`、`presetio.css` 和 `presetio/` 目录。别的分支都没碰这些文件，ND 卡和 EF 卡正在改 `newplan.js`、`design.*`，不要去碰。

## 背景（用户 11-20 截图，界面语言是英文）

预设页（大厅右上角 "Presets"）的文字全是写死的"中文 / English"双语，例如：

- "导入 DIS 预设 / Import DIS presets"
- "选择文件 / Choose file"
- "单个预设的盘种 / Standalone media"
- "手动填写参数 / Type the parameters"
- "导入 / Import"
- "选择文件或预设。/ Choose a file or preset."

`presetio.js` 里一次都没调用 `api.lang()`，别的页面都只显示当前语言。用户说："这里语言没做好。"

另外，截图里右侧推子旁边的"导出数据 Export / 导入数据 Import"两个标签，被中间的纸张盖住了一半，只露出"数据 xport"和"数据 nport"。

## 要做的

1. **跟随界面语言**：参照 `newplan.js` 的写法——一张 `STR = {zh, en}` 表，监听 `dp-lang` 事件后重绘——把这一页所有给人看的文字都改成只显示当前语言。范围包括：
   - 按钮、标签、下拉选项；
   - 提示和报错（`message()`）；
   - 导入结果每一行的说明（`issues_zh` 和英文 `issue`，中文界面显示中文，英文界面显示英文）；
   - 近似误差那一行；
   - `aria-label` 和 `aria-valuetext`；
   - 推子的两个标签。

   中文沿用仓库现有的说法。在页面打开的状态下切换语言，要立即生效，已经填进表单的内容、已经读进来的文件和预览结果都不能丢。
2. **标签不被盖住**：推子的"导出 / 导入"标签在任何视口宽度下都要完整可见，不和纸张重叠。可以挪标签的位置，也可以让纸张避开标签，选看起来干净的那一种，选择理由写进报告。窄屏和手机布局（`compact`）也要检查。
3. 功能不变：导入、导出、写进 DiscImageStudio、手动填写、预览，行为和结果都要和原来一致。相关测试要通过（`tests/` 下与 presetio 有关的 mjs 和 py 测试，再加全部 `tests/test_*.mjs`）。新增一个测试：在中文和英文两种界面下，这一页的可见文字里不能出现另一种语言（专有名词除外，比如 DIS、DiscImageStudio、JSON、CD、DVD、mm）。

## 验收

- 截图放 `D:/dp-dev/tmp/presetiolang/shots/`：导入页和导出页；中文和英文；纸色和夜色；宽度 1890 和 390；另外加一张"导入了一个文件、显示结果行"的截图。
- 在 worktree 根目录写 `CARD_REPORT.md`，末尾写 `STATUS: DONE` 并停。

## 边界

- 不碰真光驱。**8765 端口上是用户正在用的服务，不要停掉或重启**；需要起服务时用 `--new-instance` 另开端口。
- **不要真的写用户的 `%LOCALAPPDATA%\DiscImageStudio\disc-presets.json`**。测试"写进 DiscImageStudio"这条路径时，用临时目录或现有测试里的替身。
- 只在本分支提交，不推送、不合并。
- 不使用任何电脑操作或浏览器工具（无头 Edge 用脚本加 CDP 驱动可以）。需要告诉别的会话的事写进报告，由 Claude 转达。
- 绝对不要打开、列出、读取路径里连着出现 b、l、i、n、d 这五个字母（不分大小写）的文件或文件夹，递归时排除。
