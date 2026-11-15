# 新闻传真机的数据格式（原型）

大厅左翼上的传真机（`discprobe/web/home/faxnews.js`）点一下就去取当天的“报纸”。这一页说明它取什么、怎么取，以及报纸 JSON 的格式。

## 只下载

- 每次拨号只发一个 GET：取“数据源地址”那一个 JSON 文件。不加查询参数，不带 cookie，不带 Referer（`credentials: "omit"`、`referrerPolicy: "no-referrer"`、`cache: "no-store"`）。
- 点报纸上的“订购”，再发一个 GET，取那件皮肤的包裹文件。
- 报纸里的图片按普通图片加载，同样不带 Referer。
- 没有上传，没有统计，不在后台自己拨号。第一次打开传真机时，页面会先给一张说明，讲清楚这三点。

数据源地址默认是程序自带的示例 `faxnews/news.json`（相对 `discprobe/web/home/`）。说明卡上可以改成自己的地址，只接受 `http://`、`https://` 或相对路径，存在本浏览器的 `localStorage`（`dp-fax-source`）。报纸里的相对地址（图片、皮肤包裹）按报纸自己的地址解析。

## 报纸 `dp-fax-news` 第 1 版

文字字段可以是一个字符串，也可以是 `{"zh": "…", "en": "…"}`，缺一种语言时用另一种。单段文字最长 600 个字符，每个列表最多读 40 项，整个文件最大 512 KB。

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

| 情况 | 显示屏 | 打出来的回执 |
|---|---|---|
| 没联网、拒绝连接、10 秒没回应 | 线路不通 | “没接通”，可以重拨、看上次的报纸、换数据源地址 |
| 服务器回 404 等错误 | 号码不存在 HTTP 404 | “号码不存在” |
| 不是 JSON、格式或字段不对、超过 512 KB | 收到的不是报纸 | “收到的不是报纸”，列出前几处问题 |

最近一次成功收到的报纸存在 `localStorage`（`dp-fax-last`），出错时可以拿出来看，报头盖“旧报”。

## 美术

- 大厅：`art/desk/review-20261111/round5` 的场景加上新闻传真机（`art/desk/fax-news/fax_news.blend`，0.9 倍）和包裹盒，用 round5 的渲染器原样烘图（描边、材质、灯光都不改），文件盒沿左翼往外挪了 250 mm。
- 传真机页：`faxnews/render_faxnews.py --mode fax` 正俯视渲染，`faxnews/export_art.py` 导出到 `faxnews/`（桌面整图、听筒和听筒阴影两层、`fax.json` 里的显示屏、按键和出纸口坐标）。
