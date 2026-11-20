# RWC 真盘走查观感修整

基点 `73f7073`，分支 `dev/rw-c-polish`。

## 实现提交 `deea824`

- 第 2 条。编辑器左栏为滚动条留出稳定槽位，控件和内容边缘另留 6 px。窄屏滚动在靠近段落时对齐，坐标工具栏在栏内换行。[design.css](D:/dp-dev/rwc/discprobe/web/home/design.css)
- 第 6、15 条。宽屏说明纸与光驱垂直居中，纸右边沿对齐页头外边距，纸顶距步骤条至少 52 px。标题留在可滚动正文上方。灰块是页头工具和步骤条投到纸上的模糊阴影。在基点上临时关掉这两处投影，灰块消失。[有投影](D:/dp-dev/tmp/rwc/shots/before-1920-dark-en-on-rotation.png) · [临时关掉投影](D:/dp-dev/tmp/rwc/shots/before-1920-dark-en-on-rotation-header-without-shadow.png) · [改动后](D:/dp-dev/tmp/rwc/shots/after-1920-dark-en-on-rotation.png)
- 第 7、8、10 条。翻牌字沿用所在位置的文字基线、字体和前景色，保留英文空格。任务条、大号进度下方和主按钮显示同一个 `分:秒` 倒数。每次减 1 秒，估值变化时用 850–1150 ms 的间隔渐调速度。换步骤时取该步骤的新估值。关动效也继续走秒。[翻牌组件](D:/dp-dev/rwc/discprobe/web/home/kit/kit.css) · [倒数](D:/dp-dev/rwc/discprobe/web/home/kit/countdown.mjs)
- 第 12 条。红点、标签、光头和彩虹圈边缘共享一段约 400 ms 的缓动。关闭动效或系统要求减弱动效时，直接显示新位置。[calstage.js](D:/dp-dev/rwc/discprobe/web/home/calstage.js)
- 第 17 条。详情告诉用户用右下角按钮继续，有测量图时用一句话说明图意。手动改读速、限定测量区域及比较结果的命令放进「详情 → 进阶」。[390 像素结果页](D:/dp-dev/tmp/rwc/shots/after-390-dark-en-off-result-scrolled.png) · [进阶展开](D:/dp-dev/tmp/rwc/shots/after-390-dark-en-off-result-advanced.png)

## 验收记录

- `python -X utf8 D:/dp-dev/tmp/rwc/baseline_gui.py` 和 `node D:/dp-dev/tmp/rwc/evidence.mjs fast` 通过。脚本用 `webui --local-only --no-drives --new-instance --port 0` 启动两套独立界面。校准回放使用虚构盘和事件，编辑器用示例图。8765 在验收前后均由 PID 29628 监听。实物光驱、实盘测量、刻录和擦除未测。
- 共 6 组成对场景、12 份布局记录和 105 个截图及测量文件。1920×925 用夜色英文开动效、纸色中文关动效。1440×900 用纸色英文开动效、夜色中文关动效。390×844 用夜色英文关动效、纸色中文开动效。三种宽度均核对了坐标工具栏、编辑器左栏、转速、几何、结果滚动和进阶。[截图目录](D:/dp-dev/tmp/rwc/shots) · [DOM 与帧时间原始记录](D:/dp-dev/tmp/rwc/shots/measurements-fast.json)
- 编辑器控件与滚动槽之间实测 6 px，390 像素坐标工具栏内容宽度由 526–542 px 收到可用的 294 px。两个桌面宽度的纸卡与页头外边距对齐，结果纸滚到末尾时标题纵坐标不变。390 像素校准页的横向滚动宽度由 437 px 降到 390 px。
- `python -X utf8 D:/dp-dev/tmp/rwc/run_tests.py python` 通过，按 `pytest -n 2` 运行 6 个相关 Python 测试文件，61 个测试及 8 个子测试通过。[Python 日志](D:/dp-dev/tmp/rwc/tests/pytest-rwc.log)

- `python -X utf8 D:/dp-dev/tmp/rwc/run_tests.py` 及续跑命令 `python -X utf8 D:/dp-dev/tmp/rwc/run_tests.py --resume-after test_disc_files_browser` 覆盖 `tests/test_*.mjs` 全部 56 个脚本。前 13 个脚本有 12 个直接通过，清理时遇到 Windows 文件锁后，从下一脚本继续。余下 43 个脚本有 39 个直接通过。`afterburn`、`flow_navigation`、`ime_activity`、`pastworks` 和 `photo_wire` 的浏览器用例单独复跑通过，共 56 个通过。异常分别出现在 Edge 关闭、临时目录解锁、启动或页面等待。`flow_navigation` 的最后一次复跑延长了临时目录删除重试，测试断言沿用仓库脚本。[JavaScript 日志](D:/dp-dev/tmp/rwc/tests)

### CDP 帧时间

下表以浏览器收到新半径为零点。前 400 ms 内超过 50 ms 的 `DrawFrame` 间隔列于表中，捕获时段的全部长帧、rAF 采样和录帧时戳见测量 JSON 中的 `longCdpFrames`、`longRafFrames` 和 `film`。JPG 依播放顺序编号，起点和结束状态另存 PNG。1920 像素开动效的录帧可以看到 43.3 mm 的过渡位置，以及倒数从 `4:52` 翻到 `4:51`。[光头缓动帧](D:/dp-dev/tmp/rwc/shots/after-1920-dark-en-on-head-03.jpg) · [倒数翻牌帧](D:/dp-dev/tmp/rwc/shots/after-1920-dark-en-on-head-05.jpg)

| 录制条件 | 录帧数 | 观测到的标签位置数 | 前 400 ms 的长帧间隔（ms） |
| --- | ---: | ---: | --- |
| 1920 夜色英文开动效，改前 | 4 | 2 | 87.9、73.3、68.6、76.7 |
| 1920 夜色英文开动效，改后 | 13 | 7 | 57.4、60.6、59.5、67.0、60.3、65.5、73.3 |
| 390 夜色英文关动效，改前 | 6 | 2 | 无 |
| 390 夜色英文关动效，改后 | 2 | 2 | 260.5 |

关动效的 390 像素改后样本还有 766.3 ms 的后续 `DrawFrame` 间隔，两次间隔跨过静态画面。该组 86 次 rAF 采样里没有超过 50 ms 的间隔。显式开动效并发送系统减弱动效信号后，也核对了光头到达新半径。[1920 改前 CDP](D:/dp-dev/tmp/rwc/shots/before-1920-dark-en-on-head-cdp.json) · [1920 改后 CDP](D:/dp-dev/tmp/rwc/shots/after-1920-dark-en-on-head-cdp.json) · [390 改前 CDP](D:/dp-dev/tmp/rwc/shots/before-390-dark-en-off-head-cdp.json) · [390 改后 CDP](D:/dp-dev/tmp/rwc/shots/after-390-dark-en-off-head-cdp.json)

## 交接与审美取舍

- 请 Claude 转达 RWA。基点没有可用的逐级结构化结果。第 12 条暂保留随光头移动的连续彩虹带，纸上说明已把它与读过的位置区分开。RWA 的逐级事件汇合后，再从事件里的已读半径绘制离散圆环。结果页正文现在在 `.cal-body` 里，RWA 的结果内容应进入这个滚动区。
- 请 Claude 转达 RWB。校准页的倒数在当前步骤内更新共享任务条，主按钮的倒数只在校准页接管。合并导航改动时请保留 `step` 切换时清空该步骤显示的处理。
- 宽屏选了垂直居中。短步骤的纸与光驱重心对齐，长结果页保留顶部空隙并独立滚动。请审定是否接受垂直居中及夜色下沿用灯照纸色。
- 倒数选了 `4:52` 这种裸分秒，沿用原有文字层级。步骤条下的小字仍表示各步骤的计划时长。大幅修正估值时也只走单秒，若估值用完但后台仍在运行，显示 `0:00` 直到步骤状态变化。请审定这个取舍。

STATUS: DONE
