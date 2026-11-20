# CW 角落配重验收

分支 `dev/corner-weight`，基点 `038ba9c`。

## 提交

- `faea062` 将共用页脚样式放进 `discprobe/web/home/footer.css`。“下一步”、标定的辅助按钮和共用确认滑块使用面板的投影变量 `--glass-far`，缺省取 `--glass-desk`。按下时投影沿原方向收短，禁用时用浅底、细描边和同高度投影。窄屏将禁用理由放进按钮上方的留白。
- 同一提交把光驱状态做成 `--row` 高的物件，使用现有光驱图标和状态色，带中英文状态文字及盘名。光驱条显示当前光驱，悬停提示和可访问名称保留所有光驱的详情。长盘名在窄屏可省略。按钮、回车和滑块沿用原有处理逻辑。
- 同一提交在 `DESIGN.md` 的固定位置规则后加了角落配重规则，并更新原有的写入后光驱刷新测试，以验证页脚上的当前光驱和多光驱摘要。

## 两版供选

- **A，默认。** 使用细描边。在已经有面板和主按钮投影的桌面上，它给左下角一个清楚的轮廓，低亮度和较小的字保持次要层级。省略参数或用 `?corner-weight=a`。
- **B。** 用浅底和与主按钮同层的投影，适合希望光驱条也浮在桌面上时。用 `?corner-weight=b`。已有查询参数时用 `&corner-weight=b`，放在路由井号前。
- **请 Claude 转达。** A 只是本分支的初始默认。请用户看 [页脚对照图](D:/dp-dev/tmp/cornerweight/logs/footer-contact.png)，确定最终采用 A 还是 B。

## 验收

- [截图目录](D:/dp-dev/tmp/cornerweight/shots) 有 **264 张 PNG**。修改前、A、B 各 88 张，覆盖 11 个状态、纸色和夜色、中英界面以及 `1908×868` 和 `390×844`。状态包括大厅、新作品、编辑器空白和有图、预览、标定、刻录确认锁定和解除、刻后页、预设、往期作品。
- 用 `node D:/dp-dev/tmp/cornerweight/capture.mjs before` 和 `node D:/dp-dev/tmp/cornerweight/capture.mjs a b` 驱动无头 Edge CDP。用文件夹具、合成 API 响应和本地样图，390 px 启用触摸模拟。A/B 的 176 个截图状态通过页脚几何及投影检查，检查了窗口边距、52 px 行高、光驱和操作区间距、禁用理由位置及启用和禁用时的投影一致性。另用合成光驱分别验证空白、已刻、无盘及托盘打开，每版 4 种状态。
- CDP 按压验证覆盖纸色和夜色按钮以及纸色和夜色刻录滑块。滑块在两主题中的投影偏移从 `(-105.6, 57.6) px` 收到 `(-26.4, 14.4) px`。截图测量和按压记录在 [日志目录](D:/dp-dev/tmp/cornerweight/logs)。
- 分组运行全部 **57 个** `tests/test_*.mjs`。主批次 `node --test --test-concurrency=2 --test-reporter=spec <53 个文件>` **73 通过**。导航用 `node --test --test-concurrency=1 tests/test_flow_navigation_browser.mjs` 单跑，**1 通过**。刻后、停止刻录、可擦写盘三个 Disc Lab 浏览器文件分别用 `--test-concurrency=1` 单跑，均通过，内含 15、32、18 项检查。
- `python -X utf8 -m pytest -n 2` 对 `test_webui.py`、`test_webui_catalog.py`、`test_webui_recovery.py`、`test_web_security.py`、`test_gui_handshake.py`、`test_web_guidance.py`、`test_burn_cancel.py`、`test_afterburn.py`，**95 通过**。
- D 盘开跑前有超过 140 GiB 可用。每个 Disc Lab 浏览器场景结束后清理了各自的虚拟盘目录。临时目录已清理，留存截图、日志和测量记录。8765 监听进程保持运行。

## 范围和验收记录

- 页面原有可见性适用。新作品与刻录页的光驱状态由主体场景展示，预设覆盖层盖住页脚，往期作品隐藏“下一步”。编辑器双栏投影和其他卡的文件留给各自的卡。实机、真光驱和物理刻盘未测。
- 两个 Disc Lab 测试首跑时，测试脚本的离线开关也隐藏了虚拟光驱。重跑改用 Disc Lab 自带的光驱隔离，两个文件均通过。主批次完整结果记录在控制台，后一次误触发的批次已终止，原日志被部分覆盖，数字见 `logs/mjs-summary.txt`。
- 一次 `rg` 调用把路径排除参数放在 `--` 之后，扫描 `discprobe/web` 时未应用排除规则。命令输出仅出现允许路径里的匹配，扫描中具体读过哪些文件无法核实。随后递归查找都在搜索前应用了排除规则。

STATUS: DONE
