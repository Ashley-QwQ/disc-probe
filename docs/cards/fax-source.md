# 卡 S：传真新闻来源验收报告

分支：`dev/fax-source-20261116`；worktree：`D:/dp-dev/faxsource`。日期：2026-11-16。

## 按提交说明

1. `1ad528bdce5fa5cf3f05758b8171d23a5bee34c4` — `feat(news): fetch repository papers and assets through the core`
   - 新增线上 `news/news.json`，日期 2026-11-16，保留包内示例的 `sample: true`，随附 2 件皮肤包、3 张作品图；5 件附件均与包内原件字节一致。`news/art/` 被现有忽略规则覆盖，因此已按明确文件名强制加入这 3 张要求提交的图片。
   - 新增共享核心 `discprobe.news`：镜像顺序、重复 `--source` / 环境变量覆盖、HTTPS、DNS 全地址检查与固定 IP 连接、重定向复查、8 秒总预算（包含慢速响应头）、1 MiB 报纸限制、等价 v1 格式校验、缓存 → 包内样张回退，输出来源和逐地址错误。
   - 新增 `python -m discprobe news`，默认跟随既有 `--lang` 规则输出中英摘要；`--json` 输出约定对象；`--asset` 输出附件原始字节，失败退出码为 1。
   - 附件由同一核心下载，限制相对路径、同一目录前缀和重定向目标、类型及 4 MiB 大小，并缓存。缓存复用既有 `sectors.state_path()` 的用户目录，位于其旁的 `news/`。
   - 新增线程请求中的 `/api/news`、`/api/news/asset`。浏览器默认只访问本机接口，自定义源也交给后端；作品图片、皮肤均经本机附件接口。缓存或样张时显示小字，语言重绘保留提示。
   - CSP 保持 `connect-src 'self'`，旧 `DISCPROBE_FAX_ORIGINS` 兼容解析器保留，文档注明不再需要，也不再扩展 CSP。补充中英 README、线上维护说明及格式文档。
   - 新增 Python 安全/回退/接口测试，更新传真数据与浏览器回归，新增可复用截图脚本 `tools/verify_news_browser.py`。未改 CSS、动画、原有纸张布局或配色。
2. 本报告提交 — `docs: record fax news source card acceptance`
   - 添加本 `CARD_REPORT.md`，记录命令、结果、真实网络原始输出、截图与未测范围。

## 验收命令与结果

临时文件、测试用户目录、浏览器配置和截图均放在 `F:/dp-archive/tmp/faxsource/`。为现有测试中写死的 `.impeccable` 输出临时建立了指向 F 盘的 junction，跑完已核对目标并移除，未提交该链接。开跑前 D 盘可用 42,655,432,704 字节，F 盘可用 32,548,446,208 字节；全量 Node 前再次检查 D 盘仍超过 42 GB，未触及 5 GB 停止线。

| 验收 | 命令 | 最终结果 |
|---|---|---|
| 相关 Python | `python -X utf8 -m pytest -n 2 tests/test_news.py tests/test_web_security.py tests/test_webui.py --basetemp=F:/dp-archive/tmp/faxsource/pytest-acceptance -q` | **82 passed, 42 subtests passed，11.98 秒** |
| 全部 Node | `python -X utf8 F:/dp-archive/tmp/faxsource/run_node.py`，用排除受限路径的 `rg --files tests -g test_*.mjs` 枚举，再依次执行 `node <文件>` | **51/51 个文件通过，0 失败**；逐项退出码、耗时见 `node-summary.json`，原始日志在 `node-logs/` |
| 传真浏览器补充 | `node tests/test_faxnews_browser.mjs`（`TEMP`、`TMP`、`FAX_SHOTS_DIR` 均指向 F 盘） | **3/3 通过**：1440×900 纸色、夜色和 390×844 纸色；额外验证自定义源交给 `/api/news?source=...`、附件走本机 API、无法从浏览器开启 HTTP 测试例外、缓存/样张提示及重绘 |
| 真实 HTTP 截图 | `python -X utf8 tools/verify_news_browser.py --out F:/dp-archive/tmp/faxsource/shots` | **4/4 PASS**，每张 PNG 均核对为 1440×1000 |
| 真网络 | `python -X utf8 -m discprobe news --json`（测试用户目录隔离到 F 盘，无 source 覆盖） | 退出码 0；GitHub Raw、jsDelivr 各一次普通 GET，均 HTTP 404，`from=bundled`；原始输出附后 |
| 文件检查 | `git diff --check`、附件字节比对、中文 UTF-8 与问号长串检查 | 通过；附件 **5/5** 一致，中文计数均 > 0，无文字损坏 |

Python 测试全程不访问外网：使用 loopback 镜像和仅 Python 可传的 `_test_http=True`，或固定 DNS/连接替身。覆盖首源失败次源成功、全失败退缓存、无缓存退样张、坏 JSON/格式、长度与条目上限、超大报纸/附件、非法及编码路径、非公网目标、混合 DNS 答案、固定 IP 连接、重定向及 HTTPS 降级、慢速响应头总超时、附件缓存、CLI 中英与二进制输出、并发时 `/api/version` 仍响应。HTTP 例外没有 CLI 开关、环境变量或请求参数入口。HTTPS 降级单测只替换 TLS 传输，生产代码没有证书绕过。

真实 HTTP 截图使用仓库现有传真模块、样式和美术，挂载无光驱后端；镜像由本机服务器提供 `news/`。成功场景经 `/api/news` → 核心 → 本地镜像获取 2026-11-16 报纸；样张场景使用不存在的镜像路径和空缓存，显示 2026-11-14 包内样张的小字。作品图也实际通过附件接口加载。镜像收到的请求只有 `Host` 与 `User-Agent: disc-probe/0.1.2.1`，没有 cookie、Referer、查询串或请求体；记录见 `shots/mirror-requests.json`、`shots/core-results.json`。

| 截图 | 尺寸 | SHA-256 |
|---|---|---|
| `F:/dp-archive/tmp/faxsource/shots/network-paper.png` | 1440×1000 | `dd9f6ba29804104882e2ae58d3cdc8887a8767cec47017a7eb672c120118c126` |
| `F:/dp-archive/tmp/faxsource/shots/network-dark.png` | 1440×1000 | `c6a0bb5c10f6ac736d56c0fb3426c6a4f25bf5cba0d37cc06fbea66acd74cd24` |
| `F:/dp-archive/tmp/faxsource/shots/bundled-paper.png` | 1440×1000 | `0a3527cfc236e9e34a26e1dbec998ea73a2510ed16f9eef5b2100c1f90e05ebf` |
| `F:/dp-archive/tmp/faxsource/shots/bundled-dark.png` | 1440×1000 | `9899bc7abf83c1e026a196908bf434e27d7206fc3455b69439ae2ed8a075f5e2` |

已目视检查成功纸色和样张夜色截图，样张小字可读；其余两张由浏览器 DOM 断言和尺寸检查验收。没有作新的审美取舍。

## 未测、限制与需人决定事项

- 未跑整个 Python 测试套件，仅跑与本卡相关的 Python 测试；全部 `tests/test_*.mjs` 已跑一次，随后因增加自定义源断言只补跑传真浏览器测试。
- 当前 `main` 上还没有 `news/`，因此真实远端“合法报纸下载成功”未测；成功下载和附件流程已用本地镜像验收。真实远端只有两个 404 的证据，不宣称线上已发布。
- 截图在隔离传真挂载页取最终状态；完整拨号动画、Enter 跳过、首次告知、回大厅和皮肤配送由现有传真浏览器回归覆盖。未连接真实光驱、未刻盘，未上传。
- 附件接口只接受相对路径；旧自定义报纸中的绝对附件 URL 应改为相对路径。旧浏览器里保存的相对数据源地址可点“用默认”重置。缓存写入遇到只读目录或磁盘满会继续显示已下载报纸；此特定磁盘故障未做手工复现。
- `news.json` 仍是样张内容，`sample: true` 有意保留。是否换成正式报纸、何时推到 `main` 由用户决定；本分支未推送、未合并、未切换分支、未改其他 worktree，未改 `evidence/atlas/*.py`，未打开、列出或读取用户排除的路径，递归搜索均作排除。
- 日志、截图和复现辅助脚本留在 F 盘；成功测试的配置、镜像/夹具及测试用户目录已清理。没有需要阻止本地提交的待定事项。

## 真网络命令原始输出

命令：`python -X utf8 -m discprobe news --json`。`LOCALAPPDATA=F:/dp-archive/tmp/faxsource/live-user`，`DISCPROBE_NO_TUTORIAL=1`，未设置来源覆盖。输出另存 `F:/dp-archive/tmp/faxsource/live-news.json`（UTF-8）。

```json
{"paper": {"format": "dp-fax-news", "version": 1, "date": "2026-11-14", "sample": true, "release": {"version": "1.0.0.0-alpha", "date": "2026-11-15", "headline": {"zh": "DP 1.0.0.0-alpha 周日见报", "en": "DP 1.0.0.0-alpha goes to press on Sunday"}, "url": "https://github.com/Ashley-QwQ/disc-probe/releases", "summary": {"zh": "第一个公开测试版：量盘、作画、刻录一条路走通，手机可以直接把照片传给电脑。", "en": "The first public test build: measure, draw and burn in one path, and phones send their photos straight to the computer."}}, "changelog": [{"title": {"zh": "主路径打通：图画进实测的环带里", "en": "Main path open: the picture goes into the measured ring"}, "story": {"zh": "本报讯　新作品现在把图片排进 geo 实测出的那一圈里，geo 从 1% 到 98% 都报进度。另附一张检查盘和它的照片，刻完拿来对照。", "en": "Our correspondent reports: new work now lays the picture into the ring that geo measured, and geo reports progress from 1 % to 98 %. A check disc and its photos come with it, to compare after burning."}, "version": "0.1.2.1", "date": "2026-11-13"}, {"title": {"zh": "往期作品搬进文件盒", "en": "Past works move into the file box"}, "story": {"zh": "本报讯　大厅的文件盒能点了。点进去是一张报告单：每件作品刻在哪张盘、用了什么参数、读回来怎样，一页看完。", "en": "The lobby's file box opens now: a report sheet with every work, the disc it went on, its settings and how it read back, on one page."}, "version": "0.1.2.0", "date": "2026-11-12"}, {"title": {"zh": "桌上来了信件托盘和地毯", "en": "A letter tray and a rug arrive on the desk"}, "story": {"zh": "本报讯　导入导出改成一只两层的信件托盘，旁边立一张桌签；桌下铺了一条长地毯，每天换一句问候。", "en": "Import and export became a two-tier letter tray with a tent card; a long rug now runs under the desk with a new greeting every day."}, "version": "0.1.1.9", "date": "2026-11-11"}], "skins": [{"name": {"zh": "牛皮纸办公室", "en": "Kraft Office"}, "pitch": {"zh": "全新上市！把整张桌子换成牛皮纸色，铜色按钮更亮一点。耐看、耐脏、不伤眼。", "en": "New! The whole desk in kraft brown, the copper buttons a shade brighter. Easy on the eyes, hides the coffee rings."}, "price": {"zh": "免费 · 包邮", "en": "Free · free delivery"}, "id": "kraft-office", "package": "skins/kraft-office.json", "swatches": ["#d0c0a2", "#a8693c", "#2b2924"], "size_kb": 1}, {"name": {"zh": "夜班蓝图", "en": "Night Blueprint"}, "pitch": {"zh": "熬夜刻盘的你值得拥有！深蓝底、白线条，像一张工程图。附赠：不晃眼的琥珀色。", "en": "For the late-night burner! Deep blue, white lines, like an engineering drawing. Bonus: an amber that won't glare."}, "price": {"zh": "免费 · 包邮", "en": "Free · free delivery"}, "id": "night-blueprint", "package": "skins/night-blueprint.json", "swatches": ["#1d2b3a", "#e8eef2", "#d9a75c"], "size_kb": 1}], "backgrounds": [{"name": {"zh": "菱格", "en": "Diamonds"}, "note": {"zh": "斜 30°，两种材质交替", "en": "Turned 30°, two materials in turn"}, "pattern": {"pattern": "diamond", "coordinates": "cartesian", "pitch_mm": 6, "size_mm": 1.4, "angle_deg": 30}}, {"name": {"zh": "圆点", "en": "Dots"}, "note": {"zh": "极坐标排布，越往外越疏", "en": "Laid out in polar rings"}, "pattern": {"pattern": "dots", "coordinates": "polar", "pitch_mm": 5, "size_mm": 1.8, "angle_deg": 0}}, {"name": {"zh": "条纹", "en": "Stripes"}, "note": {"zh": "最省事的背景，刻错也看得出来", "en": "The simplest background; a wrong preset shows at once"}, "pattern": {"pattern": "stripes", "coordinates": "cartesian", "pitch_mm": 4, "size_mm": 1.2, "angle_deg": -20}}], "artworks": [{"title": {"zh": "玫瑰", "en": "Roses"}, "by": "DP", "disc": "RITEKF1 DVD-R", "image": "art/roses.webp", "caption": {"zh": "一张 DVD-R 上刻图又存了 1.38 GB 数据，读回来没有错。颜色随角度变。", "en": "A picture plus 1.38 GB of data on one DVD-R, read back without an error. The colour changes with the angle."}}, {"title": {"zh": "清明上河图", "en": "Along the River"}, "by": "DP", "disc": "DVD-R", "image": "art/qingming.webp", "caption": {"zh": "整卷排成内外两圈。", "en": "The whole scroll in two rings."}}, {"title": {"zh": "读者来稿：Memorex CD-R", "en": "From a reader: Memorex CD-R"}, "by": "pugod124", "disc": "Memorex CD-R", "image": "art/pugod124.webp", "caption": {"zh": "先用 geo，再在 DiscImageStudio 里精修。经作者同意刊登。", "en": "geo first, then fine calibration in DiscImageStudio. Printed with the author's permission."}}], "jokes": [{"zh": "问：光盘为什么从不迷路？答：它一直沿着轨道走。", "en": "Why does a disc never get lost? It always stays on track."}, {"zh": "刻录机对空白盘说：别紧张，我只是想在你身上留下一点数据。", "en": "The burner to the blank disc: relax, I just want to leave a little data on you."}, {"zh": "我的光驱很有礼貌：每次弹出来都先打个招呼——咔哒。", "en": "My drive is very polite: every time it pops out, it says click first."}, {"zh": "CD 问 DVD：你怎么装下那么多东西？DVD：轨距收紧一点就好。", "en": "CD asked DVD how it holds so much. DVD: just tighten your track pitch."}, {"zh": "这台传真机只收不发。它说：我是个好听众。", "en": "This fax only receives. It says it is a good listener."}, {"zh": "刻坏的盘也有用：可以当杯垫，还能顺便看彩虹。", "en": "A failed burn still has uses: a coaster with a rainbow."}], "coming": [{"title": {"zh": "手机直传", "en": "Straight from the phone"}, "note": {"zh": "拍完照片直接传进电脑，不用数据线。", "en": "Photos go from the phone to the computer, no cable."}}, {"title": {"zh": "皮肤试穿", "en": "Try on a skin"}, "note": {"zh": "包裹拆开就能换上，不喜欢再换回来。", "en": "Open the parcel and wear it; switch back if you don't like it."}}, {"title": {"zh": "实时 3D 的大厅", "en": "A lobby in real-time 3D"}, "note": {"zh": "还是这张桌子，只是能转一转。", "en": "The same desk, only you can turn it."}}]}, "source": "bundled:faxnews/news.json", "fetched_at": null, "errors": [{"source": "https://raw.githubusercontent.com/Ashley-QwQ/disc-probe/main/news/news.json", "error": "HTTP 404"}, {"source": "https://cdn.jsdelivr.net/gh/Ashley-QwQ/disc-probe@main/news/news.json", "error": "HTTP 404"}], "from": "bundled"}
```
