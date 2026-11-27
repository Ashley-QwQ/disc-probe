# 核心作品库交付报告

与 `WORKS_SPEC.md` 的差异：无。合同未规定的细节在下面明确列出，供网页直接对接。未修改合同或 `discprobe/web/home/`。

## 数据在哪里

核心现有命令默认把测量结果写进当前工作目录的 `results/`。作品库使用同一数据根，放在它旁边的 `works/`。网页服务若指定 `--out 数据/results`，作品放在 `数据/works/`。环境变量 `DISCPROBE_HOME` 优先于这一推导，作品放在 `$env:DISCPROBE_HOME/works/`；它不会改动现有测量命令的 `--out`。

例如在当前工作树运行时，默认路径为 `D:/disc-probe/.claude/worktrees/works-library/works/`。建议给实际使用设置一个固定位置，让不同启动目录使用同一作品库：

```powershell
$env:DISCPROBE_HOME = 'D:/光盘作品 数据'
python -m discprobe works list --json
```

作品目录如下，名称改变不会改变编号：

```text
works/
  .lock
  w-20261112-120000-abcd/
    work.json
    design.discdesign
    thumb.png
    assets/<SHA-256>
    history.jsonl
  .trash/<作品编号>/...
```

设计文件按输入的 UTF-8 字节保存，包括空白、换行和内嵌图片。原图、工作图片、RGBA 栅格和 SVG 原文按内容 SHA-256 去重，另存到 `assets/`；设计内的引用保持原样。保存时不删除旧素材，以保留原始证据。没有上传缩略图时，使用核心 `editor_ops` 合成器和 `imagedisc.preview` 生成 512 × 512 灰度盘面。

新作品先在临时目录完整写好，再一次重命名发布。每个文件使用同目录临时文件、刷新、`fsync`、替换。已有作品的多文件保存使用 `.pending.json` 写前日志；下次通过库读取时，在返回内容前恢复完成。历史只追加；若进程在追加途中退出，仅裁掉不完整的末行，再重放未完成事件。线程锁和跨进程文件锁覆盖读取、冲突检查及提交。

删除把整个目录移入 `.trash/`，保留原编号。正常访问作品库结束时清理已删除超过 30 天的作品；没有后台服务在浏览器关闭后定时运行。30 天内可以恢复。库内编号、素材路径、符号链接和 Windows 目录联接均检查，编号不能作为任意文件路径使用。

## 命令与例子

下面所有作品命令都支持 `--json`，可写在 `works` 后或具体操作后。列表输出 JSON 数组；详情和修改输出作品对象；导出输出 `{id,path}`。错误输出到标准错误，JSON 模式为 `{error}`，退出码为 1。`--lang zh`、`--lang en` 均可使用，JSON 字段名保持不变。

先新建，再将返回的真实编号放进 `$id`：

```powershell
$id = (python -m discprobe works new '锦鲤 第一版' --media dvd --json | ConvertFrom-Json).id
```

| 命令 | 例子 |
|---|---|
| 列表 | `python -m discprobe works list --status draft --media dvd --sort time --json` |
| 详情，含最近 50 条历史 | `python -m discprobe works show $id --json` |
| 从设计新建 | `python -m discprobe works new '锦鲤 第二版' --from 'D:/中文 设计/锦鲤.discdesign' --json` |
| 保存设计，上传缩略图可省略 | `python -m discprobe works save $id 'D:/中文 设计/锦鲤.discdesign' --thumb 'D:/中文 设计/缩略图.png' --json` |
| 改名 | `python -m discprobe works rename $id '锦鲤 成品' --json` |
| 复制，省略名称则沿用原名 | `python -m discprobe works duplicate $id '锦鲤 副本' --json` |
| 删除 | `python -m discprobe works delete $id --json` |
| 恢复 | `python -m discprobe works restore $id --json` |
| 导出整个作品 | `python -m discprobe works export $id 'D:/作品备份/锦鲤.zip' --json` |
| 导入设计 | `python -m discprobe works import 'D:/中文 设计/锦鲤.discdesign' --json` |
| 导入作品包 | `python -m discprobe works import 'D:/作品备份/锦鲤.zip' --json` |
| 人工确认成品 | `python -m discprobe works mark $id done --note '检查通过' --json` |
| 人工标记失败，原因必填 | `python -m discprobe works mark $id failed --note '图片外圈缺失' --json` |
| 中文帮助 | `python -m discprobe works save --help --lang zh` |
| 英文帮助 | `python -m discprobe works save --help --lang en` |

ZIP 导入保留编号、元数据、设计、素材、缩略图及历史的原始字节，不额外添加导入事件。目标库中已有同一编号（包括回收站）时返回冲突，不覆盖；如需另一个编号，请先复制。ZIP 文件本身的压缩时间戳不参与逐文件字节一致性的定义。

`.discdesign` 导入则创建新编号，名字取文件名，`source_file` 保存原路径作参考。接受网页版本 1、2 的 `disc-probe design` 文档；较新版本拒绝，避免误读。

设计中的几何路径保持原文；元数据 `geo_run` 将本机数据根内的路径统一为相对路径和正斜杠。导入文件若指向另一台电脑或数据根以外的位置，`geo_run` 为 null，不把外部路径当成本机结果。

## HTTP 接口与例子

所有接口沿用服务现有会话认证、Host 与 Origin 检查。需要令牌的会话可发送 `X-Discprobe-Token: <会话令牌>`，也可沿用现有同站会话 cookie。手机拍照令牌不能访问作品库。成功返回 200；错误返回 `{error}`，冲突返回 409。下表中的 `$id` 代表服务器返回的真实编号。

| 方法和路径 | 请求例子及返回 |
|---|---|
| `GET /api/works?sort=time&status=draft&media=dvd` | 无请求体；返回作品数组，每项为 `work.json` 字段加 `thumb_url`。`sort` 可为 `time` 或 `name`，筛选可省略或留空 |
| `POST /api/works` | JSON：`{"name":"锦鲤","media":"dvd"}`；返回作品和 `thumb_url` |
| `POST /api/works`，从已有设计新建 | JSON：`{"name":"锦鲤","media":"dvd","from":"设计/锦鲤.discdesign"}`；路径须在服务工作目录内。也接受 `from` 为设计对象或设计 JSON 字符串；大设计请先新建，再 PUT |
| `GET /api/works/$id` | 返回作品字段、`thumb_url`、`history` 数组（最近 50 条）；更新 `opened_at`，不改变 `updated_at` |
| `GET /api/works/$id/design` | 返回原始设计字节，类型为 `application/json; charset=utf-8` |
| `PUT /api/works/$id/design` | `Content-Type: application/json`，请求体为原始 `.discdesign` JSON；`If-Match: <上次 updated_at>`；返回更新后的作品 |
| `PUT /api/works/$id/thumb` | `Content-Type: image/png`，请求体为 512 × 512 PNG 字节；返回更新后的作品 |
| `GET /api/works/$id/thumb` | 返回 `image/png` 字节 |
| `PATCH /api/works/$id` | JSON：`{"name":"锦鲤 成品","status":"done","note":"人工检查通过"}`；返回更新后的作品 |
| `POST /api/works/$id/duplicate` | JSON：`{"name":"锦鲤 副本"}`，或空请求体／`{}`；返回新编号的作品 |
| `DELETE /api/works/$id` | 无请求体；返回含 `deleted_at` 的作品，作品目录移入回收站 |
| `POST /api/works/$id/restore` | 空请求体或 `{}`；返回恢复后的作品 |
| `GET /api/works/$id/export` | 返回 `application/zip`，下载名为 `<id>.zip` |
| `POST /api/works/import` | 请求体直接放 ZIP 或设计字节，使用 `application/zip`、`application/json` 或 `application/octet-stream`；可加 `X-Filename` 保存设计来源名称；返回作品 |

`PATCH` 还允许 `disc_type`、`batch`、`geo_run`、`photo_l`、`cell_um`，便于其他核心功能关联测量和照片；不允许改编号、时间和 `discs`。`photo_l` 默认 null，本任务没有计算或改动照片 L。

`PUT design` 的 `If-Match` 支持原值和双引号包裹的值。不匹配返回 409，并保持设计、元数据和历史不变。省略头时是无条件保存；网页应始终发送它。`GET` 不使旧的设计保存条件失效。上传缩略图、改名、标记、关联 ISO 或刻录均更新 `updated_at`，网页需使用返回的新值。

设计上限 64 MiB、最多 16 层；缩略图上限 4 MiB，并检查实际 PNG 格式和尺寸。ZIP 请求及解压总量上限 256 MiB，最多 1024 项；导出同样检查此限额，保证成功导出的包可以导入。只允许约定文件和 SHA-256 素材名，拒绝穿越路径、重复文件、链接、错误哈希和缺少的内嵌素材。普通元数据 JSON 上限 64 KiB。

## 网页需要怎样调用

1. 从 `GET /api/version` 读取能力。核心已声明 `works`，`discprobe/web/gui.json` 将其列为可选能力。
2. 往期作品页调用 `GET /api/works`。用返回的 `thumb_url` 加载缩略图，用 `id` 打开详情，不以作品名拼文件路径。
3. 第一次保存：`POST /api/works` 创建，再 `PUT /api/works/<id>/design` 上传 `projectText()` 的原文，带创建响应的 `updated_at` 作为 `If-Match`。记住返回的新 `id` 和 `updated_at`。
4. 继续保存：用上次的 `updated_at` 调用同一 PUT。收到 409 时提示另一个窗口改过，先重新读取，不自动覆盖。
5. 如有网页盘面缩略图，再 PUT PNG。该请求也会更新版本时间，必须用它响应的 `updated_at` 作为下次保存条件。省略上传则核心已经生成灰度预览。
6. 打开作品：读取详情与 `/design` 原文，把后者交给现有 `openProject()`；`history` 和 `discs` 可直接用于详情页。
7. 改名、复制、删除、恢复、导入、导出分别使用上表接口。浏览器关闭不影响已保存的数据。
8. 现有 `/api/run` 的 `image`、`burn`、`calibrate` 作业可在请求顶层或 `args` 中放 `work`；两处同时给值必须一致。`args.disc_code` 可选。

现有网页刻录文件作业仍是 `/api/run` 的 `action: "burn"`，没有另增一条绕过原刻录确认的接口。例如：

```json
{
  "action": "burn",
  "drive": "E:",
  "media": "dvd",
  "work": "w-20261112-120000-abcd",
  "burn_token": "现有接口取得的一次性刻录令牌",
  "args": {"iso":"iso/锦鲤.iso","speed":4,"disc_code":"KOI-A 2-03"}
}
```

## ISO 和刻录关联

实际使用的命令示例（交付验证没有执行真实刻录）：

```powershell
python -m discprobe image --geo 'results/geo-E-20261112-120000' --picture '锦鲤.png' --output 'iso/锦鲤.iso' --work $id --disc-code 'KOI-A 2-03'
python -m discprobe burn --drive E: --iso 'iso/锦鲤.iso' --speed 4 --yes-write --work $id --disc-code 'KOI-A 2-03'
python -m discprobe calibrate --drive E: --iso 'iso/测量.iso' --yes-write --work $id --disc-code 'KOI-A 2-03'
```

`image` 只有写出并通过现有校验后才追加记录，状态变为 `iso_ready`。`burn` 在现有刻录函数返回成功后追加，状态变为 `burned`；回读结论另存为 `verification`，不会把“写完但回读未通过”说成回读通过。`calibrate` 把作品编号转交给自己的刻录子进程，在刻录成功时记录，即使后续测量失败也保留实际刻录记录。

每条 `discs` 记录包括 `type`（`iso` 或 `burn`）、`iso_path`、`iso_sha256`、带时区的 `time`、`drive`、`speed`、`disc_code`、`result`；刻录还保存实际报告速度及回读结论。哈希针对路径所指的源 ISO 文件；刻录过程中按光盘身份补丁生成的数据不冒充源文件字节。对应记录同时追加进 `history`。任务排队期间删除的作品，其已成功作业记录仍追加到回收站中的原作品，恢复后可见。

## 验证与改动边界

验证结果：

- 全量 `python -m pytest -q --tb=short`：562 项通过，182 个子测试通过，1 项跳过，0 失败。日志为 `C:/disc-probe-scratch/works-library/pytest.txt`。跳过项不计为通过。
- 最终作品专项 `python -m pytest tests/test_works.py -q --tb=short`：25 项通过，0 失败。全量回归后本模块的边界修正均在这次复测中覆盖。日志为 `works-pytest-final.txt`。
- 全量 Node：26/26 个测试文件通过，0 失败。日志及逐文件退出码为 `node-final/node-tests.txt`、`node-final/node-summary.json`。握手测试的可选能力预期已随合同新增 `works`，并验证缺少此能力的旧核心仍可启动。
- `python -u -m discprobe selftest`：退出码 0，末行 `all checks passed`；包括每项帮助和每条命令描述的中文检查。日志为 `selftest.txt`。
- `git diff --check`：通过。

专项覆盖全部命令和路由、认证拒绝、中文名称及空格路径、Windows 目录联接、路径穿越、线程和跨进程并发、409、不完整历史及提交中断恢复、回收站及 30 天清理、版本及大小限制、压缩包完整性与解压限额、干净数据根上的逐文件字节回环、核心缩略图、`image --work` 成功／失败分支、刻录成功／失败替身、网页任务参数和数据根传递。

本次未联网，未访问光驱，未执行真实刻录。刻录成功／失败关联使用替身，ISO 关联测试使用极小的模拟输出。没有修改 `scsi.py`、`photo.py`、`pcal` 系列、图像 L 处理或 `discprobe/web/home/`。共享文件仅加入独立模块入口、参数与成功回调。

主要实现为 `discprobe/works.py`、`works_cli.py`、`works_http.py`、`works_link.py`；验证用例为 `tests/test_works.py`。完整回归日志放在 `C:/disc-probe-scratch/works-library/`。
