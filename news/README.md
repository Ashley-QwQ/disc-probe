# 线上报纸 / Online paper

`news.json` 是传真机在线读取的 `dp-fax-news` 第 1 版报纸，格式见 [docs/fax-news.md](../docs/fax-news.md)。2026-11-22 期随 1.0.0.0-alpha 发布，包内样张仍用于离线回退。

编辑 `news.json` 的日期和内容，皮肤包放 `skins/`，作品图片放 `art/`。引用写相对 `news.json` 的路径（如 `skins/kraft-office.json`），附件只用 JSON、WebP、PNG 或 JPEG，不用 `..`。改完检查格式和附件后提交。**只有进入 `main` 分支才会影响默认在线来源**；本开发分支的提交不会上线，推送和合并由用户决定。

核心先取 GitHub Raw，再试 jsDelivr。jsDelivr 有缓存，`main` 更新后可能暂时仍看到旧内容。程序也会保留最近一次下载，断网时回退缓存或包内示例。

`news.json` is the online v1 `dp-fax-news` paper. The 2026-11-22 issue accompanies 1.0.0.0-alpha. The bundled sample is still available as an offline fallback. See the [format and download rules](../docs/fax-news.md).

Edit the date and stories in `news.json`. Keep skin parcels in `skins/` and artwork in `art/`, referenced relative to `news.json`. Use JSON, WebP, PNG or JPEG assets and no parent-directory paths. Validate the paper and its assets before committing. **Changes take effect at the default online sources only after reaching `main`.** This development branch is not published; the user decides whether to push or merge.

The core tries GitHub Raw, then jsDelivr. jsDelivr caches responses and may serve an older issue after `main` changes. When offline, the program falls back to its local cache, then the bundled sample.
# 社区提示数据

`community.json` 是 `dp-community` 第 1 版，下发内容包括数据日期、条数、出处、许可，
以及每条的盘类型、MID、品牌/型号/圈码/扇区数、光驱、速度、原始数值、结果、可信度、
公开 GitHub 用户名、日期和原帖链接。`source.kind` 区分社区帖和 DIS 内置；内置来源带
`version`（标签或提交）与 `builtin_id`。同值的其他出处和复用结果在 `also` 中，保留各自的盘和结果。
`measured_span_mm` 只记录原文明确给出的实测范围；内外半径不是实测范围。
`unknown` 不表示成功，`confidence` 只描述证据/抄录把握，不表示适用于用户这批盘。

维护步骤：

1. 只读检查 DIS 的新帖、评论、PR 与内置预设，更新 `data/community-calibrations/dis-github.json`，
   在 `updates` 记录时间、增改 id、重复来源和没有完整数值的帖子；不从图片猜值。
2. 运行 `python -X utf8 tools/build_community_feed.py`，同时生成此处和
   `discprobe/web/home/faxnews/community.json` 的包内回退副本。
3. 运行 `python -X utf8 tools/build_community_feed.py --check`，提交研究数据与两份生成文件。
4. 进 main 后，用户下次用传真机取报纸，也会取社区数据。联网依次尝试 GitHub Raw、jsDelivr，
   失败则用上次缓存，再失败则用程序自带数据。wheel 与 Windows 包均包含包内副本。

格式严格限制为 1 MiB；所有出处链接只能是 HTTPS 的 `github.com` 地址，所有数值必须有限。
类型、长度、条数、重复 id、来源版本和实测范围由 `discprobe/community_feed.py` 校验。
未测过这批盘时默认只显示提示；`failed` 默认隐藏，可显式查看。
导入必须由用户主动选择，保留来源信息，并仍需确认这批盘；不会自动选择或安装 DIS 参数。

