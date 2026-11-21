# Disc Neo 新手导引交付报告

分支 `dev/neo-onboarding`，基点 `39a1dac`。本分支提交，未推送、合并或切换分支。

## 提交

- `72a4b27` 增加中英文导引、四个入口、可收起的查表说明、列名提示和离线查询示例。首屏嵌入 Disc Neo 的纸色／夜色字标与图标，复用 DP 的控件尺寸和主题底色。查表页保留原周期图、候选与搜索，修正目标编号大小写导致的精确搜索落空，压暗夜色表格底图以提高文字对比度。
- `72a4b27` 将实拍依据写入首屏和中英文 README。每次构建把图谱候选和已核对的实拍规格清单相交，生成 `colour-evidence.csv`。输出附一张色卡照片及一组眨眼角色卡实拍帧，另链接到仓库的 SHOW-D 照片。生成完整包与 `--docs-only` 共用文档生成与链接预检。数据导出代码和 core 无改动。
- 本报告提交记录验收和跨会话交接。

## 显色依据

- **色卡取色。** `D:/disc-probe/docs/goals/colour-fit-cardb/REPORT.md` 和 `observations.py` 记录了六张 CARDB-A（4-07 至 4-12）的手持闪光视频和取色筛选。读取 `F:/dp-dev-tmp/colour-fit/observations.npz`，用该目录对应源码旁的 `selection.json` 将 `spec` 索引还原成字节规格。实拍记录有 11,127 个合格色块×秒观测，来自 1,171 个物理色块，归并为 630 种重复字节段。`observations.npz` SHA-256 为 `99696217ae8d46c0650e0eaeb8ca12a59470b698f1a51c0363f8ed4a80d6d192`。
- **展示盘。** `D:/disc-probe/docs/goals/discs/register.md` 登记了 SHOW-A 到 E、盘和刻录条件。使用各自 ISO 的归档配方 A、B、C、E、H，核对标签图 `.npy` 和 `.textures.txt` 的全部 10 个 SHA-256，再从实际使用的标签取出纯十六进制规格。排除 `RND` 等非重复字节标记后，各盘分别有 72、71、73、69、68 种，共 76 种，和色卡取色清单有 9 种重合。SHOW-E 登记的 `s=0.93` 是六盘拟合的机位比例。用料出现在实拍展示盘上，与逐纹理色差量测是两种依据。
- **眨眼角色卡。** 刻录及回读见登记 4-20，实拍见 `F:/dp-dev-tmp/video/IMG_8338/REPORT.md`。包内的 `character-disc-photo.png` 复制自该记录的 `best/sheet.png`。逐规格统计受源目录路径限制，表内数量仅包含已逐项核对的色卡与 SHOW-A 到 E。色卡图片复制自卡 W2 的 `background/figs/geometry_preview.jpg`，照片上的轮廓标注是原分析的一部分。
- **Neo、纹理库、拟合表的关系。** 归档 texlib 把同日 Neo 的冠军规格和版本保留下来，并生成 LED 模型色表。拟合报告 `D:/disc-probe/docs/goals/colour-table-fitted/REPORT.md` 锁定 `F:/dp-archive/texlib/20261118-0933`，在同一组规格和角度上重算衍射 XYZ。该归档有 4,350 个去重冠军规格，拟合 NPZ 有 4,506 个规格，其中色卡取色规格匹配 336 个，展示盘匹配 11 个。拟合参数来自实拍，表内新算的各角度 XYZ 仍是估计。Neo 阅读器的波长色条和 A3 色卡使用图谱模型。`F:/dp-archive/texlib/20261119-1020/MANIFEST.json` 也记录了该日纹理库使用的 Neo 导出路径与哈希。
- **本次临时包。** 11-16 验收快照有 7,648 个搜索目标、115,744 条候选记录。将占满同一最短字节段的完全重复规格归一化，不旋转、不翻转。由独立 CSV 对照算得 93,936 种不同候选规格，266 种匹配色卡取色记录，40 种匹配 SHOW-A 到 E 用料，重合 9 种，93,639 种在以上两份记录里未匹配。计数涵盖冠军和次名。正式快照构建会重新计算匹配数。CD 和蓝光在 Neo 包里暂无数据。

## 临时重建与走查

- `python -B -X utf8 D:/dp-dev/tmp/neoonboard/logs/verification/prepare.py` 调用 `build_neo.py --docs-only --snapshot D:/dp-dev/tmp/neoonboard --out D:/dp-dev/tmp/neoonboard/pack --work D:/dp-dev/tmp/neoonboard/work --reader-ref 56f2cf7`，随后调用 `--check-only`。使用 11-16 冻结模式 A 已有包的副本，结果均通过。六份 `atlas/dvd/` 数据文件的 SHA-256 前后相同，正式 Neo 目录未用于验收。
- `node D:/dp-dev/tmp/neoonboard/logs/verification/screens.mjs` 用无头 Edge 和 CDP 打开本地文件。1440 × 900、390 × 844，各两套主题、两种语言，共 8 张首屏截图。390 宽时引导末尾位于中文 723 px、英文 819 px，无页面横向溢出。验证了查表入口、收起帮助、目标编号搜索、列名提示、目标深链接及查询示例锚点。浏览器异常 0，页面 HTTP 请求 0。另存一张候选表截图。[截图目录](D:/dp-dev/tmp/neoonboard/shots) · [CDP 记录](D:/dp-dev/tmp/neoonboard/logs/screens.json)
- `python -B -X utf8 D:/dp-dev/tmp/neoonboard/logs/verification/verify_pack.py` 核对 14 个 HTML 链接含 5 个 DP 目的地，两个 README 使用相同目标。故意移走 `docs/colour.md` 和移除章节分别得到明确错误，现有输出时间戳保持一致。中文 README 含 2,505 个汉字，HTML 含 1,411 个汉字，均无连续四个问号。
- `python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/neoonboard/pytest --junitxml D:/dp-dev/tmp/neoonboard/logs/pytest.xml tests/test_release_packaging.py tests/test_brand_assets.py`，72 项通过。
- `python -B -X utf8 D:/dp-dev/tmp/neoonboard/logs/verification/run_js.py` 依次执行符合路径约束的全部 `tests/test_*.mjs`，59 项全部通过。清理了临时图谱副本、浏览器配置和测试夹具。[JavaScript 日志索引](D:/dp-dev/tmp/neoonboard/logs/js/results.json)
- 开跑前 D 盘余 145,754,931,200 字节，全量 JS 回归前余 144,505,978,880 字节。只用脚本、离线资料、无头 Edge 和测试用隔离端口，未请求 8765 上的服务。实物光驱、刻录、擦除、实机触屏未测。

## 请 Claude 转达

- **CD / core-release**：验收复制了 `dev/colour-docs` 的 `docs/colour.md#in-the-web-app` 与 `docs/colour.zh.md#在网页里做`。正式构建前把文档接入发布源码，并确保链接指向的 GitHub `main` 上有对应页面。发布链接在线可达性未测。
- **LG / core-release**：LG 教程目前还没有可引用的正式文件。Neo 按 `docs/how-discs-make-pictures.md` 和 `docs/how-discs-make-pictures.zh.md` 预留中英文入口，临时验收用两个仅存在于 D 盘临时目录的占位页面。请 LG 确认文件名，路径不同就同步更新 `DP_DOCS`。当前分支直接构建会精确报告缺少的文件，正式包需等教程接入后重建。
- **core-release**：由发布会话使用 11-21 冻结快照正式重建。正式快照的包内计数和发布产物未测。若能提供一份合规路径下、可溯源的角色卡逐规格清单，可以扩展匹配证据的范围。

STATUS: DONE
