# 传真纸张位置交付报告

工作树为 `D:/dp-dev/faxslip`，分支为 `dev/fax-slip`，对比基点为 `b163957`。基点的社区卡报告可通过 `git show b163957:CARD_REPORT.md` 查阅。

## 提交

- `f75431c` 用传真烤图的机身框和出纸口坐标定位纸张。桌面上回执、报纸和说明纸靠在机器右侧，手机上三张纸都在出纸口正前方。报纸和回执从同一纸口分步送出，再移到阅读位置。两行固定控件之间留出了滚动区域，窄纸上的报头和样张戳各有空间。
- 本报告提交记录截图、验证命令和测试结果。

## 验收

`TEMP` 和 `TMP` 设置为完整路径 `D:/dp-dev/tmp/faxslip/runtime/windows-long-temporary-directory`。开工和整轮 mjs 验收前，D 盘分别剩约 115 和 114 GiB。

| 命令或检查 | 结果 |
| --- | --- |
| `node tests/test_faxnews_data.mjs` | 通过。覆盖样张、包裹、错误和版面数据。 |
| `node tests/test_faxnews_browser.mjs` | 3 个模拟场景通过。覆盖说明、报纸、回执、改地址、重拨和跳过动效。 |
| `node D:/dp-dev/tmp/faxslip/fax-layout-check.mjs before` 及 `after` | 用无头 Edge 和 CDP 检验 1920×866、1440×900、1280×720、390×844，纸色和夜色，中英文。16 种组合各拍说明纸、404 回执和报纸，共 48 张修改前截图、48 张对应的修改后截图。另拍 16 张动效帧和 4 张手机说明纸滚到底的截图。 |
| CDP 几何和交互检查 | 48 个静止纸面都在内容区内，光驱状态至少留出 28.09 px。夹具显示右下角的原按钮后，中心点均可命中。4 个尺寸各测报纸、回执出纸，最大出纸口偏差 0.46 px。说明纸滚到底可操作地址输入框和按钮。 |
| `python -X utf8 -B -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/faxslip/runtime/windows-long-temporary-directory/pytest-base tests/test_news.py tests/test_community_feed.py "tests/test_night_pool.py::test_line_pool_direction_and_silhouette[faxnews-fax]"` | 57 项通过。 |
| `node --check discprobe/web/home/faxnews.js`、`git diff --check b163957 f75431c`、Impeccable 扫描两份源码 | 通过，扫描返回空列表。 |
| `python -X utf8 -B D:/dp-dev/tmp/faxslip/run-mjs.py` | 按文件逐个运行 `tests/` 下 60 个 `test_*.mjs`，首轮 56 个通过。 |
| `python -X utf8 -B D:/dp-dev/tmp/faxslip/run-mjs-rerun.py test_burn_cancel_browser test_disc_files_browser test_rw_discs_browser test_web_retry_browser` | 四个定向复跑均通过，合计 60/60。刻录取消和可擦写场景用各自的 Disc Lab 虚拟光驱复跑。随盘文件导出和重试页导航单独复跑。 |

- [修改前截图](D:/dp-dev/tmp/faxslip/shots/before/)
- [修改后截图](D:/dp-dev/tmp/faxslip/shots/after/)
- [修改后几何记录](D:/dp-dev/tmp/faxslip/logs/geometry-after.json)
- [整轮 mjs 结果](D:/dp-dev/tmp/faxslip/logs/mjs-results.json)
- [定向复跑结果](D:/dp-dev/tmp/faxslip/logs/mjs-rerun-results.json)

## 取舍及未测

桌面上为报纸保留较大的阅读区，让短回执靠近出纸口。手机在上方保留整台传真机，长篇说明和报纸在纸内滚动。说明纸截图另附地址部分。验收使用本地模拟数据和 Edge 模拟手机视口。实体手机、其他浏览器、外部数据源和实体光驱未测。无需在交付前作其他决定。

STATUS: DONE
