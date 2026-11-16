# 线上报纸 / Online paper

`news.json` 是传真机在线读取的 `dp-fax-news` 第 1 版报纸，格式见 [docs/fax-news.md](../docs/fax-news.md)。这期先沿用包内样张，日期为 2026-11-16；`sample: true` 保留样张标记。

编辑 `news.json` 的日期和内容，皮肤包放 `skins/`，作品图片放 `art/`。引用写相对 `news.json` 的路径（如 `skins/kraft-office.json`），附件只用 JSON、WebP、PNG 或 JPEG，不用 `..`。改完检查格式和附件后提交。**只有进入 `main` 分支才会影响默认在线来源**；本开发分支的提交不会上线，推送和合并由用户决定。

核心先取 GitHub Raw，再试 jsDelivr。jsDelivr 有缓存，`main` 更新后可能暂时仍看到旧内容。程序也会保留最近一次下载，断网时回退缓存或包内示例。

`news.json` is the online v1 `dp-fax-news` paper. This first issue copies the bundled sample with its date set to 2026-11-16; `sample: true` keeps the sample stamp. See the [format and download rules](../docs/fax-news.md).

Edit the date and stories in `news.json`. Keep skin parcels in `skins/` and artwork in `art/`, referenced relative to `news.json`. Use JSON, WebP, PNG or JPEG assets and no parent-directory paths. Validate the paper and its assets before committing. **Changes take effect at the default online sources only after reaching `main`.** This development branch is not published; the user decides whether to push or merge.

The core tries GitHub Raw, then jsDelivr. jsDelivr caches responses and may serve an older issue after `main` changes. When offline, the program falls back to its local cache, then the bundled sample.
