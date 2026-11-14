# Disc Lab JSON API / 结构化接口

Every subcommand of `python -m disclab` accepts `--json`. Put it before the `dp --` separator; flags after that separator belong to disc-probe. A global `--json` before the command also works. UTF-8 stdout contains exactly one JSON object, including argument, compatibility and execution failures. Help with `--json` returns `outputs.help`. Human messages, prompts, child output and server addresses go to stderr. Without `--json`, existing human output stays available.

`python -m disclab` 的所有子命令都支持 `--json`，也可放在子命令之前。`dp` 的该选项必须放在 `--` 分隔符之前；分隔符之后的参数交给 disc-probe。stdout 为 UTF-8，只有一个 JSON 对象，参数错误、版本不兼容和执行失败也使用此格式。`--json --help` 返回 `outputs.help`。日志、提示、子进程输出和服务器地址写到 stderr；不加该选项仍为原有的人类可读输出。

```json
{"status":"ok","lab":null,"outputs":{},"scores":{},"errors":[]}
```

| Field / 字段 | Contract / 约定 |
| --- | --- |
| `status` | `ok` or `error`: command execution, never an accuracy grade. / 命令执行结果，不代表精度合格。 |
| `lab` | Resolved lab path; null when absent or arguments could not be parsed. Generated practice/TUI labs are included. / 实验盒绝对路径；无实验盒或参数解析失败时为 null；包含自动创建的目录。 |
| `outputs` | Command-specific object below. Paths refer to local files, not download URLs. / 各命令的结构化结果；路径为本机文件。 |
| `scores` | Existing `LAB/scores/*.json`, keyed by filename stem; empty without saved scores. Equations and thresholds are unchanged. / 已保存评分文件，键为不含扩展名的文件名；公式、阈值不变。 |
| `errors` | List of `{type, message}` objects; empty on success. Numeric child failures also return `outputs.exit_code`. / 错误列表；成功时为空；子进程退出码在可用时一并返回。 |

Exit code is zero for success, nonzero for failure (argument errors: 2). Missing estimates and non-finite response numbers are JSON null. A zero exit does not imply that photo L was accepted. Preserve the reader's `verdict`, reasons, null estimates and `photo_l.written`.

成功退出码为 0，失败为非零（参数错误为 2）。缺失估计及非有限数在响应中为 null。命令成功不等于照片 L 被接受；前端必须保留 `verdict`、拒绝原因、null 估计以及 `photo_l.written`。

The TUI's corrected-picture action also requires the generated image sidecar to report `photo_l.written: true` before virtual burning. A numeric estimate alone cannot pass the image generator's provenance and application checks.

TUI 的带 L 图片动作在虚拟刻录前还会检查生成的图片旁车文件，要求 `photo_l.written: true`。只有数值估计不足以通过图片生成器的来源及应用检查。

## Command outputs / 各命令输出

| Command / 命令 | `outputs` / 字段及含义 |
| --- | --- |
| `box` | `box`: public label / 公开标签；`paths`: box, answers and state files / 标签、真值、状态文件。 |
| `tray` | `drives`: each drive's reader, tray disc and open flag / 各虚拟光驱的读盘配置、盘号、托盘开关。 |
| `env` | `environment`: shell-independent environment mapping / 无需解析 shell 文本的环境变量字典。 |
| `dp` | `argv`, `exit_code`, `paths`: forwarded command, child exit and named artifacts, including image sidecars and result summaries / 转发参数、子进程退出码、输出路径（含图片旁车文件和结果摘要）。 All disc-probe capabilities remain reachable through this command. / 可通过此入口调用 disc-probe 的全部命令。 |
| `loop geo` / `loop photo` | `rows`, `paths`: existing per-disc results and saved score path / 各盘原有结果及评分文件路径。 |
| `photos` | `paths`: generated JPEGs; poses/truth remain in answers.json / JPEG 路径；拍摄姿态真值仍写入 answers.json。 Optional `--width` and `--height` reduce render size; defaults remain 4032×3024. / 可选尺寸参数可减小渲染量，默认尺寸不变。 |
| `poses` | `result`, `paths`: truth L, sweep rows, summary, output file / L 真值、姿态扫描、摘要、输出文件。 |
| `score` | `result`, `paths`: unchanged geo scorer output, also saved to `scores/score.json` / 原有几何评分，并保存到文件。 Requires `--disc` and `--geo`. / 需要盘号及几何目录。 |
| `score --progress` | `result`, `paths`: geo measured/truth/errors, photo L estimates/truth/errors and picture placement; saved as `scores/tui.json` / 汇总几何、照片 L 及图片落点误差，包含测量值和真值。 Uses recorded progress; no GUI required. / 从进度记录读取，无需 TUI。 |
| `web` | `url`, `exit_code`, `paths`: server address, exit and results folder, returned when stopped / 停止后返回地址、退出码、结果目录。 |
| `upload` | `replies`, `run`, `paths`, `exit_code`: per-file HTTP replies and final computer listing / 逐文件 HTTP 回复及电脑端列表。 Optional `--lab` records progress; otherwise `lab` is null. / 可选实验盒参数用于记录进度。 |
| `tui` | `paths`: selected lab state file; menus and prompts use stderr in JSON mode / 当前实验盒状态路径；JSON 模式下菜单、提示走 stderr。 EOF exits cleanly. / 输入结束可正常退出。 |
| `practice` | `url`, `guide`, `paths`, `exit_code`: bilingual guide, retained lab and server exit / 双语指导、保留的实验盒目录及服务退出码。 New/empty folder only; default creates a retained temporary folder with three virtual discs. / 只接受新目录或空目录；默认自动创建并保留三盘实验盒。 |

`web` and `practice` run until Ctrl+C. They emit their JSON response after shutdown; read the local URL from stderr or the `web` progress record while running. The default binds only locally; `--lan` uses the existing product's token-guarded LAN mode. Do not infer readiness solely from a `started` progress record: it records the launch attempt, not an HTTP health check.

`web`、`practice` 持续运行到 Ctrl+C，停止后才写最终 JSON。运行期间可从 stderr 或 `web` 进度记录取得本机地址。默认只监听本机；`--lan` 沿用产品的带令牌局域网模式。`started` 仅表示尝试启动，实际可用性应检查本机 HTTP 响应。

## Progress / 进度

`LAB/state.json` keeps all previous keys, including `drives`, `burns` and `events`, and adds `steps`, a mapping from step name to an append-only list. Each entry has `t` (Unix seconds), `status`, and `paths`; operation-specific fields include `disc`, `drive`, `argv`, `iso`, `outputs` and `errors`. Paths can later be removed by existing loop cleanup; a progress record is history, not a file-existence guarantee. Existing labs gain records as commands run; old runs are not invented retrospectively.

状态文件保留原有键（包括光驱、刻录、事件及扩展键），新增 `steps` 字典，按步骤名保存追加式记录列表。每条包含 Unix 秒时间戳 `t`、状态 `status`、路径 `paths`，以及适用时的盘号、光驱、参数、ISO、结果、错误。既有循环会清理部分 ISO，因此历史记录中的路径不保证仍存在。旧实验盒仅从新执行的命令开始积累进度，不补造历史。

Names include `box`, `tray`, `burn`, each forwarded command (`random`, `timing`, `geo`, `image`, `photo`, …), `pictures`, `photo_L`, `photos`, `scores`, `web`, `practice`, `tui_config`, `sample_picture`, `picture_L` and command dispatch records. `box`/`tray`/`burn` records are also written by the virtual device/event layer, including web-initiated virtual burns. `photo_L` means a reader result exists; inspect its verdict to learn whether L was applied. Web operations otherwise retain the product's existing result files; this API does not instrument or modify disc-probe internals.

步骤名包括建盒、托盘、刻录、转发命令、图片、照片、L、评分、服务生命周期及 TUI 配置。虚拟设备事件层也会记录建盒、托盘和刻录，包括网页触发的虚拟刻录。`photo_L` 表示产生读取结果，是否应用必须查看其 verdict。网页其余操作沿用产品结果文件；此接口不修改 disc-probe 内部实现。

```bash
python -m disclab box --lab LAB --count 3 --json
python -m disclab tray --lab LAB --disc "LAB-A 1-01" --json
python -m disclab dp --lab LAB --json -- timing --drive X: --out LAB/results
python -m disclab score --lab LAB --progress --json
python -m disclab practice --lab LAB-practice --port 8853 --json
```

The TUI imports only standard-library modules and lab helpers. It uses the same parser/dispatcher, virtual recorder, renderer and scorers as the CLI. All durable selection, configuration, progress and score information lives under the lab; a future web shell can translate this API directly.

TUI 自身仅导入标准库及实验盒辅助模块，通过同一命令解析器和分发器调用虚拟刻录、渲染和评分能力。持久状态均保存于实验盒，可供后续网页外壳直接使用。
