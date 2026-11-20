# EF · 矮窗口里的盘面适应

分支 `dev/editor-fit-short`，基点 `038ba9c`。

## 提交

- `8174ee5` 让画布和适应后的盘面在同一帧跟随尺寸变化。空间特别小时，工具区的预留边距随画布缩小。默认缩放显示「适应 / Fit」，手动缩放保留现有比例和快捷键。新增 Edge/CDP 回归。
- `c19c8d2` 等灯下预览的离线 worker 渲染完成后再截图。

## 根因和前后对照

- 容器变尺寸时，原来的 `resize()` 每次都给画布重设位图宽高，即使数值相同也会清空像素。它随后把重绘排到下一帧。进场同时改变容器高度时，基线的 441 个采样帧里，四处盘缘采样均透明。修复后只在位图规格变化时重设尺寸，画布、盘面和遮罩同帧更新。修复后的 435 个过渡采样帧全部显示四侧盘缘，盘外接框到画布框的最小边距为 68.04 CSS 像素。
- 四个目标视口在稳态默认适应时，基线的 102 次测量均有四侧盘缘，最小边距为 72.44 CSS 像素。修复后这 102 次测量全部通过，最小边距同为 72.44 CSS 像素。1918×893 英文纸色灯下的同一测试作品从 `7%` 改显示 `Fit`。
- 原百分比是每个刻录格占多少 CSS 像素，按 `Math.round(V.s * S.cell * 100)` 四舍五入。100% 对应每格一个 CSS 像素。用 5 µm 格距的合成 DVD 作品在 1918×893 的灯下视图手动放大，复现 `3%` 时盘高 780 px、画布框高 645 px，盘缘越过框顶 83.14 px、框底 51.86 px。修复后的手动模式仍可越框并渐隐，按 `0` 回到完整盘面。原作 «Nov20's breeze» 和截图前的操作轨迹未测，截图中的具体触发路径仍无法确认。

## 验收

使用无头 Edge 157 和 CDP。用临时本地扩展调用 Edge 原生标签页缩放，核对 90%、100%、110% 及对应的设备像素比。1918×893、1366×768、1440×800、1280×720 各覆盖新建、导入、打开已存作品、三个视图、进场时画布变高和变矮，以及手动放大后再缩小窗口。

- `node --test --test-concurrency=2` 加排除受限路径后取得的 `tests/test_editor*.mjs` 和 `tests/test_design_export.mjs`，10/10。桌面回归 35 项通过，W245 的 18 项验收及 4 组预览哈希通过。4 组 SHA-256 均为 `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`。
- `node --test --test-concurrency=1 tests/test_flow_navigation_browser.mjs`，1/1。导航测试单跑。
- 全部 58 个 `tests/test_*.mjs` 文件最终通过，Node 合计 78 项。上述导航单跑，5 个虚拟或隔离后端场景单跑，其余 52 文件使用 `node --test --test-concurrency=2` 执行。两项 Disc Lab 测试首轮因测试脚本继承 `DISC_PROBE_NO_DRIVES=1` 收到 `unknown drive`。重跑这两项时让各自的 Disc Lab 启动器接管光驱枚举，只提供虚拟设备。停止刻录场景 32 项检查通过，可擦写场景 18 项检查通过。
- `python -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/editorfit/py/pytest tests/test_editor_colour.py tests/test_editor_ops.py tests/test_editor_pose_swatches.py tests/test_editor_preview.py tests/test_editor_texlib.py tests/test_lamp_optics.py tests/test_design_compose_route.py`，149/149。
- `node --test tests/test_editor_fit_browser.mjs` 的截图运行前后各输出 13 张，含 12 张指定组合和 1 张手动 3% 复现。设置 `EDITOR_FIT_OUT=D:/dp-dev/tmp/editorfit`，基线用 `EDITOR_FIT_PHASE=before` 和 `EDITOR_FIT_BASE=038ba9c`，修复用 `EDITOR_FIT_PHASE=after`。已核对 26 张 PNG 可解码且像素尺寸正确。截图在 `D:/dp-dev/tmp/editorfit/shots/{before,after}/`，采样在同一临时根目录的 `fit-before.json` 和 `fit-after.json`。

D 盘开跑前剩 154,033,324,032 字节，全量 JS 前剩 153,661,202,432 字节。使用本地隔离端口，8765 未停或重启。所有场景使用离线设计或虚拟设备，未接触真实光驱。

## 供 Claude 转达

进场和调整窗口时的画布清空已修复。原截图的 3% 可以在手动放大的 5 µm 项目中复现，原作的触发路径仍待确认。

执行中有一条指定文件的 `rg` 查询被 Windows 参数引号拆开，扩大成了未加排除条件的仓库搜索。输出未显示受限路径，无法核实进程是否读取过受限文件。后续递归搜索显式添加了排除条件。

STATUS: DONE
