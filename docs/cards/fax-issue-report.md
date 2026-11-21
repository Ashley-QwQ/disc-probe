# FX · 2026-11-22 传真报纸与来源显示

交付在本地分支 `dev/fax-issue`，基点 `39a1dac`。旧工作树 `D:/dp-dev/faxissue` 用于核对 11 月 17 日那期。

## 提交

- `f51b13a` 将 `news/news.json` 换成 11 月 22 日发布期。双语头条宣布 1.0.0.0-alpha 发布，摘要写明 RITEKF1 DVD-R 和 GH70N 的彩色验证范围、灯下预览和模拟擦除限制。三条新闻覆盖刻录前检查与报错、刻后检查单、几何补测、照片手动对齐、预设页语言、四角和投影、盘况提示及稍后选批次。保留社区数据的原日期与出处，更新当日笑话及纹理计划的说明。下载地址沿用上期及仓库 README 的 Releases 链接。
- `3499b5c` 给传真设置和默认来源的失败回执加双语标签。来源框默认显示「默认（GitHub 仓库）」。输入自定义 HTTPS 地址后，重新打开说明卡仍显示保存的地址，保留大小写和百分号编码。点「用默认」再拨号会恢复默认请求。只改了网页显示和表单，核心镜像顺序、缓存、附件和包内样张均沿用原行为。
- 本报告提交记录验收、截图及发布时要转达的事项。

## 验收

| 命令 | 结果 |
| --- | --- |
| `python -B -X utf8 -m pytest -n 2 -q -p no:cacheprovider --basetemp D:/dp-dev/tmp/faxissue/release-20261122/pytest-work/cases tests/test_news.py` | 37 项通过，pytest 用时 7.25 秒。[日志](D:/dp-dev/tmp/faxissue/release-20261122/logs/python.log) |
| `python -B -X utf8 D:/dp-dev/tmp/faxissue/release-20261122/verify_suite.py targeted tests/test_faxnews_data.mjs tests/test_faxnews_browser.mjs` | 2 个文件通过。无头 Edge 经 CDP 跑了 1440×900 纸色、1440×900 夜色、390×844 纸色三种场景，覆盖默认来源中英文、非法地址、自定义地址、重置及失败回执。[日志](D:/dp-dev/tmp/faxissue/release-20261122/logs/targeted/) |
| `python -B -X utf8 -m discprobe news --source http://127.0.0.1:62953/news/news.json --json` | 从本地文件的回环镜像拿到正式报纸，`from=network`，0 个下载错误。输出经 Python v1 校验，核对了 3 张作品图及 2 件皮肤包。命令由截图脚本运行，仅在临时子进程内为此地址启用既有的 Python 回环测试选项。[JSON](D:/dp-dev/tmp/faxissue/release-20261122/cli-news.json) |
| `python -B -X utf8 D:/dp-dev/tmp/faxissue/release-20261122/capture_issue.py` | 4/4 通过。使用隔离挂载页、实际传真模块和本机 API，等待拨号、打印和落纸，再核对日期、头条、发布链接、三条双语更新、社区栏目、图片加载和版面宽度。每张 PNG 为 1440×1440。[验收记录及哈希](D:/dp-dev/tmp/faxissue/release-20261122/capture-results.json) |
| `python -B -X utf8 D:/dp-dev/tmp/faxissue/release-20261122/verify_suite.py all`，随后同脚本 `retry tests/test_csp_browser.mjs` | 逐个以 `node --test --test-concurrency=1` 跑全部 59 个 `tests/test_*.mjs`。首轮 58 个文件通过，82 项通过、1 项超时。CSP 用例首轮及第一次复跑在切换主题后等待新建页时超时，页面无 JS 抛错。临时诊断运行和恢复原文件后的复跑通过。合计 59/59 个文件、83 项均有通过记录。 [首轮](D:/dp-dev/tmp/faxissue/release-20261122/logs/all/summary.json) · [原样复跑](D:/dp-dev/tmp/faxissue/release-20261122/logs/retry/test_csp_browser.log) |

`git diff --check` 和 UTF-8 检查通过。D 盘开跑时余 145,951,240,192 字节，全量回归前余 145,754,451,968 字节。JavaScript 全量回归使用排除了受限路径的临时源码副本，结束后已清理副本、成功场景的临时目录和浏览器配置。Disc Lab 场景用虚拟光驱，各场景结束后清理对应临时盘。日志、截图和失败记录保留在 D 盘。

四张截图都落在 [shots](D:/dp-dev/tmp/faxissue/shots/)。

| | 中文 | English |
| --- | --- | --- |
| 纸色 | [纸色中文](D:/dp-dev/tmp/faxissue/shots/release-2026-11-22-paper-zh.png) | [纸色英文](D:/dp-dev/tmp/faxissue/shots/release-2026-11-22-paper-en.png) |
| 夜色 | [夜色中文](D:/dp-dev/tmp/faxissue/shots/release-2026-11-22-dark-zh.png) | [夜色英文](D:/dp-dev/tmp/faxissue/shots/release-2026-11-22-dark-en.png) |

截图显示报纸首屏。现有版式把社区记录放在三条更新上方，更新日志需要滚动查看，其语言、顺序和内容已在页面上断言。截图模拟从旧版本接收报纸，所以展示新版本头条和下载按钮。用 `node --input-type=module` 对正式报纸同时校验了旧版本及当前 alpha 的排版，后者按既有规则把第一条更新抬到头条。

## 未测及转达

- 请 Claude 转达发布会话。11 月 22 日这期已备好，等用户点头随 alpha 进 main。真实远端拉取未测。发布后需用 `python -m discprobe news --json` 确认是 11 月 22 日、`from=network`。备用站 jsDelivr 可能先返回缓存。
- 发布方案与 `news/README.md` 未确认行星仪刊登，先保留已有作品轮换。按 11 月 22 日取报时显示读者投稿的 Memorex CD-R。是否加行星仪留给发布审查。
- 本卡未接真实光驱，实体刻录及擦除未测。测试服务使用隔离回环端口。未推送、未合并，未修改其他工作树。

STATUS: DONE
