# 卡 AC · 往期作品固定纸面

工作树 `D:/dp-dev/pwsheet`，分支 `web/pastworks-sheet-20261119`，基点 `3bd5c5d`。

## 提交

- `c6eaf23` `Keep the past works sheet fixed while its contents scroll`。列表纸面固定在顶栏和底栏内侧，各留 16 px。标题、筛选和作品格在纸内滚动，滚动条在右边距，只有还有内容的一侧显示约 24 px 淡出。键盘焦点移到可见区之外的作品时，作品滚进纸内并避开淡出带。
- `Record card AC validation`。提交本报告。

文件盒进出场继续移动整张纸。列表停稳后，滚轮和触屏越过边界时纸面也保持原位。作品展开的位置取自所选格的当前矩形。窄屏的外层滚动条只在往期作品模式隐藏，夜色的列表标题使用现有纸上墨色 `--lit-ink`。

## 验收

无头 Edge 使用 `--mute-audio`，从正式首页的本地 `?mock` 文件盒进入，夹具为 16 件作品和一个新作品入口。四个尺寸、两套主题共 8 组通过。每组检查三个滚动位置，确认纸的矩形相同，上下淡出分别为仅下沿、两沿、仅上沿，焦点移到原先不可见的作品时可读。

| 视口 | 纸的边框盒（px） | 纸内最大滚动量（px） |
| --- | ---: | ---: |
| 1873×901 | 1180 × 653 | 1374 |
| 1440×1000 | 1180 × 771.84 | 1258 |
| 1024×768 | 958.47 × 566.47 | 1187 |
| 390×844 | 350 × 668 | 1957 |

列表态验证返回、可见字标、工具栏和光驱信息的矩形，以及底栏预留区。右下「打开作品」在详情态出现，将其实际矩形与列表纸面的位置比对。390×844 另用浏览器输入检查滚轮、滚轮越界、触屏拖动和筛到无溢出时清除淡出。

| 命令 | 结果 |
| --- | --- |
| `node tests/test_pastworks.mjs` | 通过 |
| `node tests/test_pastworks_works.mjs` | 通过 |
| `node tests/test_pastworks_browser.mjs` | 原有浏览器检查和新增矩阵通过，写出 10 张 PNG |
| `node tests/test_flow_navigation_browser.mjs`（单独运行） | 通过。首次本地连接中断，单跑重试通过 |
| `node --test --test-concurrency=1 --test-timeout=180000 <tests/ 内筛选后的 test_*.mjs>` | 单轮覆盖 55 个文件，66 项通过，0 失败，0 跳过 |
| `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp F:/dp-archive/tmp/pwsheet/pytest-ac tests/test_works.py tests/test_web_security.py` | 35 项通过 |
| `impeccable.cmd detect --json discprobe/web/home/pastworks.css discprobe/web/home/pastworks.js` | 1 条原有侧边描边提示，位于 `.pw-note.pw-warn` |
| `git diff --check` | 通过 |

单轮 JavaScript 回归覆盖最后两处截图修正之前的版本。处理窄屏外层滚动条和夜色标题颜色后，复跑了表中的四个单文件 JavaScript 命令。D 盘开跑前剩余 202.96 GiB，全量 JavaScript 回归前剩余 202.82 GiB。

截图位于 `F:/dp-archive/tmp/pwsheet/after/`。纸色和夜色各 5 张，分别为 1873×901 的顶部、中段和底部，以及 1024×768、390×844 的顶部。已核对全部 PNG 的像素尺寸。日志为同一临时目录下的 `js-suite.log`、`pastworks-browser.log`、`flow-nav.log` 和 `pytest-ac.log`。

## 未测与待决定

- 触屏用 Edge 输入模拟验收。实体触屏、实体触控板及 Edge 以外的浏览器未测。
- 无需额外决策。测试使用本地夹具，未接光驱、未刻盘、未上传。分支未推送、未合并。
