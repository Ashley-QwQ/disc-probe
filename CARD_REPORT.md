# RS 任务卡报告

工作树 `D:/dp-dev/reshoot`，分支 `dev/reshoot-burn-record`，基点 `95d3289`。主会话对旧刻录的兼容决定见 [BLOCKED-resolved.md](BLOCKED-resolved.md)。

## 提交

- `39a05f6` 给完成的 CLI 和网页刻录追加刻录器、适配器、模式和盘号。新检查盘的记录还绑定镜像规格的 SHA-256。旧网页记录只在原 ISO 日志路径和事件时间完全相同时补齐，并在 provenance 标记来源。照片的应用门槛沿用基点。
- `c42c014` 读取损坏日志时逐行解码，前面的完整记录仍可恢复。
- `756dc03` 加回检查盘补拍入口，按时间选记录，填写或修正盘号，随网页导航快照保存选择。新手引导和四份中英文教程都解释了隔天补拍的入口。
- `5491198` 增加 Disc Lab 和无头浏览器验收，修正测试载入共享文案、Windows 测试浏览器清理和受行号变动影响的故障排查引用。
- `b7e2621` 在 Disc Lab fixture 中增加可复现的补拍角度。上传的 JPEG 均由当次虚拟盘渲染，并交给正式照片任务重新读取及比较。
- 报告提交归档初次阻塞与主会话的决定，记录以下证据。

## Disc Lab 和截图

用仓库自带的无头测试运行 `node tests/test_reshoot_browser.mjs`，退出码 0。两条路径都在虚拟刻录结束后关掉网页、重启 webui，再从盘库进入补拍。页面确认后重新加载，第二条路径还在确认后再重启一次服务。两个出图任务都输出 `Photo L used`，均无 `Photo L not applied`。图盘 provenance 包含所选刻录的事件时间、`X:`、`Disc Lab`、`2048-byte data sectors; physical interleave unknown` 和盘号。

| 场景 | 实际出图结果 | 图盘 ISO SHA-256 |
| --- | --- | --- |
| 一次刻录 | 空列表先显示「去刻检查盘」。刻完重启后自动选中唯一记录。两张模拟照片采用 L = −0.098159 mm，盘号 `C1123-1352`。 | `76501b674bca865f8af2ecfcf311c02a3703f8dd370c7dbe70847993c36ae489` |
| 同一 ISO 两次刻录 | 列表按时间倒序。选第二次后改为 `marked-second`，重启和刷新后保留。两张模拟照片采用 L = −0.073668 mm。原号 `C1123-1359` 和改号标记都写进 provenance。 | `be26a74ffc3719adbfbe5fd83f39387985492cc3a55e73a58cf1a9291341102a` |

完整 provenance 在 `D:/dp-dev/tmp/reshoot/reshoot-evidence.json`。两条场景日志分别为 `reshoot-1.log` 和 `reshoot-2.log`。

测试 ISO 加了 12 点数据面对准箭头，箭头单独预览在 `D:/dp-dev/tmp/reshoot/shots/check-disc-arrow.png`。完整检查盘为 4,700,372,992 字节，两次场景的 SHA-256 都是 `c2adefa161da542eafe777c878250fbccdae210c5809216b074e13cf039234e7`，刻录前后相同。每个场景结束后清理了各自的 Lab 目录，保留日志、哈希和截图。

`D:/dp-dev/tmp/reshoot/shots/` 有纸色和夜色、中英文、1440×900 和 390×844 共 8 张网页截图。无头测试检查选择控件没有超出视口。文件尺寸已用 Pillow 核验。

## 立即拍照的逐位对比

用 `node D:/dp-dev/tmp/reshoot/reshoot_parity.mjs` 从 Git 读取 `95d3289` 和本分支的立即拍照入口与刻录参数函数。固定同一分钟，两个版本给出逐字节相同的光驱、程序、模式和盘号入参。开刻和完刻跨分钟时，按本卡续办决定用开刻时间生成盘号。

用 `python -X utf8 -B D:/dp-dev/tmp/reshoot/reshoot_parity.py` 在同一路径、同一 geo、同一组固定模拟读取值和同一 ISO9660 时钟下比较。照片命令结果和标准输出、`photo.json`、图盘的 `photo_l`、规格 JSON、4096 扇区图盘逐位一致。模拟刻录的旧日志字段、结果和标准输出也一致，源 ISO 字节相同。对比只略去这次明确新增的日志字段。

| 数据 | 两个版本一致的 SHA-256 |
| --- | --- |
| `photo.json` | `bf45be195ca25190d58eb0015333b48cd0e000a0493fce70509dfb92561e89cd` |
| 图盘规格 JSON | `6e0042ac43b9e86aeaf094705f55c5812312955cdfcbececbaf45f7bc4c031e3` |
| 图盘 ISO | `edeb766624ac3f8b3903b2dff12b4b1dc04b6067771c015def2470e949482ef6` |

## 验收命令和结果

测试的 `TEMP`、`TMP` 指向 `D:/dp-dev/tmp/reshoot/` 或其子目录。续办前可用空间为 D 盘 49.05 GiB、F 盘 43.35 GiB，Node 全量开始前为 D 盘约 44 GiB、F 盘 43.35 GiB。清理后为 D 盘 44.22 GiB、F 盘 43.35 GiB。

- `python -X utf8 -m pytest -n 2 -q -k 'not sealed' --basetemp=D:/dp-dev/tmp/reshoot/pytest-acceptance tests/test_reshoot_burn.py tests/test_burner.py tests/test_burn_cancel.py tests/test_burn_preflight.py tests/test_burn_progress.py tests/test_checkburn.py tests/test_checkdisc.py tests/test_afterburn.py tests/test_photo.py tests/test_photo_l_image.py tests/test_catalogue_measured.py tests/test_gui_handshake.py`。232 通过，19 子测试通过，1 跳过。跳过项是仓库外的研究对照设计缺失。
- 后续用 `pytest -n 2` 定向复验刻录和补拍测试，32 通过、4 子测试通过。增加截断 JSONL 检查后复验 `tests/test_reshoot_burn.py`，4 通过。引用行号修正后复验 `tests/test_troubleshoot.py`，5 通过。
- 用 `python -X utf8 D:/dp-dev/tmp/reshoot/run_node_suite.py` 逐个 `node tests/test_*.mjs`。首轮 58 个通过，修正测试文案依赖、Windows 浏览器配置目录清理和 Disc Lab 摄影夹具后定向复验，合计 62/62 通过。汇总在 `D:/dp-dev/tmp/reshoot/node-results-final.json`。日志在 `D:/dp-dev/tmp/reshoot/node-logs/`，复验日志在同一临时根目录。
- `python -X utf8 -m discprobe selftest`。退出码 0，`all checks passed`，1478 条 `ok`。首轮发现代码移动造成故障排查引用行号过期，已按原关键词重新对齐。
- `python -X utf8 -m discprobe --lang zh photo --help` 和 `--lang en photo --help`。两种帮助均列出 `--list-burns`、`--burn-record` 和 `--burn-log`。CLI 测试覆盖了盘号改写和读完照片后的出图提示。

## 未测和边界

- 真实光驱、实体刻盘、真实手机取景和局域网实机重连未测。服务重启验收用同一本机地址，选择跟随现有网页导航快照。两组实验照片来自真实 Disc Lab 虚拟写入后的模拟渲染。
- 只有旧 ISO 日志且缺严格匹配网页作业的刻录继续按决定拒绝。盘号缺失或需改时，仍由拿盘的人确认并输入。
- 首轮排查有一次递归 `rg` 漏加排除 glob，返回结果未出现受限路径。首轮 pytest 疏漏运行了可选的原始照片用例，它会递归寻找源照片，结果为跳过。后续递归命令加了排除 glob，后续 pytest 排除了该用例。

没有额外待决定事项。

STATUS: DONE
