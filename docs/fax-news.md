# 新闻传真机的数据格式（原型）

大厅左翼上的传真机（`discprobe/web/home/faxnews.js`）点一下就去取当天的“报纸”。这一页说明它取什么、怎么取，以及报纸 JSON 的格式。

## 数据从哪里来

线上报纸是本仓库的 [`news/news.json`](../news/news.json)，图片和皮肤包也放在 `news/` 下，维护方法见 [news/README.md](../news/README.md)。提交到 `main` 才会更新线上内容，jsDelivr 可能还保留缓存。

由 Python 核心下载，网页只向本机的 `GET /api/news` 要报纸，附件走 `GET /api/news/asset?path=...&source=...`。浏览器的 CSP 保持 `connect-src 'self'`；旧的 `DISCPROBE_FAX_ORIGINS` 仍可由兼容解析器读取，但不再扩展 CSP，也不再需要配置。

默认依次尝试：

1. `https://raw.githubusercontent.com/Ashley-QwQ/disc-probe/main/news/news.json`
2. `https://cdn.jsdelivr.net/gh/Ashley-QwQ/disc-probe@main/news/news.json`

`python -m discprobe news` 查看摘要，`python -m discprobe news --json` 输出一个对象：`paper`、`from`（`network` / `cache` / `bundled`）、`source`（重定向后的报纸地址；自带样张为 `bundled:faxnews/news.json`）、`fetched_at`（UTC 下载时间，样张为 null）、`errors`（按尝试顺序的地址和失败原因）。`--source URL` 可重复，优先于空格分隔的环境变量 `DISCPROBE_NEWS_SOURCES`，未设置时才用默认列表。

说明卡的“数据源地址”留空时会显示“默认（GitHub 仓库）”，由核心依次尝试上述镜像。填入自己的 HTTPS 地址后，页面显示该地址，并通过 `/api/news?source=...` 交给核心下载。点“用默认”清空填写的地址。

`python -m discprobe news --asset skins/kraft-office.json > skin.json` 把附件字节写到标准输出；也可配合 `--source`。附件相对本次报纸的最终地址解析，只允许同一目录前缀内的 JSON、WebP、PNG、JPEG（含 .jpg），最多 4 MiB。拒绝绝对地址、`..`、编码后的路径跳转和越界重定向。皮肤包和作品图片都通过核心下载；外部发布页链接仍由人点击打开。

## 只下载

- 每个地址只发一个普通 GET，不加查询串，不带 cookie、Referer、本机路径或设备信息；User-Agent 只有 `disc-probe/<版本>`。不使用系统代理或浏览器凭据。
- 每个报纸地址最多等 8 秒、读 1 MiB；重定向仍只到 HTTPS，DNS 的全部地址须是公网地址，连接固定到检查过的 IP。内网、回环、链路本地等目标被拒绝。仅 Python 测试参数可放行 `http://127.0.0.1`，CLI、环境变量和网页都不能开启。
- 第一个合法报纸为准。所有地址失败就用上次缓存，再没有就用包内样张；页面会写明“上次的报纸”或“自带的样张”。缓存放在现有用户数据目录（`sectors.state_path()` 所在目录）的 `news/` 下，保存报纸、来源、UTC 下载时间和附件。
- 点“订购”再下载那件皮肤包；作品图片也只下载。不上传、不统计、不在后台自己拨号。第一次打开的告知页照旧。

The Python core fetches the repository paper, trying GitHub Raw and then jsDelivr. The browser talks only to the local `/api/news` and `/api/news/asset` routes. Requests download only, with no cookies, referrer or machine details. Each source has an eight-second, 1 MiB budget; assets have a 4 MiB limit and stay under the paper directory. Only public HTTPS destinations are allowed. Failed sources fall back to the last cached paper, then the bundled sample, with provenance shown on the page. `--source` (repeatable) overrides `DISCPROBE_NEWS_SOURCES` and the defaults. No `DISCPROBE_FAX_ORIGINS` setup is needed.

## 报纸 `dp-fax-news` 第 1 版

文字字段可以是一个字符串，也可以是 `{"zh": "…", "en": "…"}`，缺一种语言时用另一种。单段文字最长 600 个字符，每个列表最多读 40 项，整个文件最大 1 MiB。

| 字段 | 必填 | 内容 |
|---|---|---|
| `format` | 是 | 固定为 `"dp-fax-news"` |
| `version` | 是 | 固定为 `1` |
| `date` | 是 | 这一期的日期，`YYYY-MM-DD` |
| `sample` | 否 | `true` 时报头盖“样张”章 |
| `release` | 否 | 最新版本：`version`（如 `1.0.0.0-alpha`）、`date`、`headline`（文字）、`summary`（文字，可省）、`url`（下载页，可省） |
| `changelog` | 否 | 更新日志，每条 `version`、`date`、`title`、`story`（都必填），按新闻稿排 |
| `skins` | 否 | 页面皮肤广告，每条 `id`（小写字母、数字、连字符）、`name`、`pitch`（广告词）、`swatches`（2–6 个 `#rrggbb`）、`package`（包裹地址）、`price`（可省）、`size_kb`（可省） |
| `backgrounds` | 否 | 盘面背景预设，每条 `name`、`note`（可省）、`pattern`：`pattern`（`diamond` / `dots` / `stripes`）、`coordinates`（`cartesian` / `polar`）、`pitch_mm`（0.5–20）、`size_mm`（不超过 `pitch_mm` 的一半）、`angle_deg`（可省）。预览用 `design/pattern.mjs` 画 |
| `artworks` | 否 | 盘面作品，每条 `title`、`image`（图片地址）、`by`、`disc`、`caption`（后三项可省） |
| `jokes` | 否 | 笑话，每条一段文字 |
| `coming` | 否 | 以后要做的功能，每条 `title`、`note`（可省） |

至少要有一项内容，否则算“不是报纸”。

### 一期怎么排

- 本机版本取页面左上角收起的字标后面那个版本号（来自核心 `/api/state` 的 `version`）。`release.version` 比本机新，就上头条；不比本机新时，最新一条更新日志上头条，并注明“本机已是最新”。版本比较按数字逐段比，预发布版排在正式版前面（`1.0.0.0-alpha` < `1.0.0.0`）。
- 更新日志按版本从新到旧，最多排 3 条。
- 皮肤广告最多 2 个。
- 背景预设、作品、笑话各登一个，按日期轮换：同一天总是同一个，换一天换下一个，不用随机数，也不存任何东西。

## 皮肤包裹 `dp-skin` 第 1 版

```json
{"format": "dp-skin", "version": 1, "id": "kraft-office", "name": {"zh": "牛皮纸办公室", "en": "Kraft Office"},
 "tokens": {"paper": {"bg": "#e6dcc8", "accent": "#9a5a2c"}, "dark": {"bg": "#2a241c", "accent": "#e0a868"}}}
```

`id` 必须和广告里的 `id` 一致。`tokens` 下的 `paper`、`dark` 各是一组颜色变量（名字是小写字母、数字、连字符，值是 `#rrggbb`）。原型只把收到的包裹记在 `localStorage`（`dp-fax-parcels`），大厅桌上出现一个包裹盒；真正换上皮肤以后再做。为了让配送过程看得见，原型在下载之外至少等 3.5 秒。

## 出错时

远端的网络、HTTP、超大文件和格式错误都会逐个记录在核心结果的 `errors` 中，并尝试下一个源。全部失败仍返回可读报纸（缓存 → 样张），页面显示一行小字。附件下载失败时使用同源附件缓存；没有缓存时只显示附件未送达。

本机服务本身不可达或返回损坏响应时，原来的“没接通”“号码不存在”“收到的不是报纸”回执继续使用，可重拨、查看浏览器上次的报纸（`dp-fax-last`）或换地址。

## 美术

- 大厅：`art/desk/review-20261111/round5` 的场景加上新闻传真机（`art/desk/fax-news/fax_news.blend`，0.9 倍）和包裹盒，用 round5 的渲染器原样烘图（描边、材质、灯光都不改），文件盒沿左翼往外挪了 250 mm。
- 传真机页：`faxnews/render_faxnews.py --mode fax` 正俯视渲染，`faxnews/export_art.py` 导出到 `faxnews/`（桌面整图、听筒和听筒阴影两层、`fax.json` 里的显示屏、按键和出纸口坐标）。
