# Disc 家族标识

默认使用夜色 `ink`；浅色环境可以选 `paper`。源 SVG 从本机原稿逐字节入库，不依赖外部字体。

`disc-{probe,lab,neo}-{icon,icon-small,mark,wordmark}-{paper,ink}.svg` 共 24 个：

| 部分 | 用途 |
| --- | --- |
| `probe` / `lab` / `neo` | Disc Probe / Disc Lab / Disc Neo，各用自己的标识 |
| `icon` | 带底色的应用图标，32 px 及以上 |
| `icon-small` | 简化的小图标，**32 px 以下必须用它** |
| `mark` | 无底色的双字母标记，紧凑页头或图示 |
| `wordmark` | 展开的产品全名字标，宽页头或文档 |
| `paper` / `ink` | 纸色 / 夜色版本；夜色是默认 |

每个产品的导出文件放在同名子目录 `probe/`、`lab/`、`neo/`：

| 文件 | 用途 |
| --- | --- |
| `favicon.ico` | 网页标签，含 16 / 32 / 48 px |
| `apple-touch-icon.png` | Apple 主屏幕图标，180 px |
| `disc-产品-64.png`、`-128.png`、`-256.png`、`-512.png` | 启动器、应用列表、文档插图 |
| `disc-产品.ico` | Windows 启动器 / 快捷方式，含 16 / 24 / 32 / 48 / 64 / 128 / 256 px |

重导出：`python tools/export_brand_icons.py`。使用已安装的 Edge 渲染 SVG、Pillow 编码 PNG，再组装多尺寸 ICO；同一版本的 Edge / Pillow 和同样输入可得到相同字节。无网络请求；临时目录默认为 `D:/dp-dev/tmp/brand/export/`，可用 `--temp-dir` 指定，`--edge` 指定浏览器。

Disc Lab 的独立网页目录保留 `lab/` 导出物的相同副本，由导出脚本同步。Disc Neo 的图标已备齐；本仓库没有 Disc Neo 网页，未来网页应引用 `neo/`。

源稿生成器：`python discprobe/web/brand/build_marks.py`（需要 fontTools，读取同包 `fonts/Archivo-VF.ttf`）。它也会在旁边生成仅供本地检查的 `sheet.html`；导出图标不需要重建 SVG。
