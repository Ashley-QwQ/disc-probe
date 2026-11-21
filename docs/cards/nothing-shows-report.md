# NS 卡交付报告

交付分支 `dev/nothing-shows`，基点 `a7b5fbf`。验收在 2026-11-20（多伦多时间）完成，早于周六 18:00 的时限。

刻完看不到图时，可以先查光盘上有没有写进东西、是不是把镜像或照片直接当文件放进了盘里。有原镜像或这次刻录的记录时，还能查抽看的几处有没有写对。检查单也会告诉你怎么拿盘、怎么打光，以及什么时候该回头核对当初做图用的设置。这样可以先查出问题可能在哪一步，再决定要不要用另一张盘重来。

## 提交

- `cee1053` 新增只读 `checkburn`、中英文检查单和双语 `--json`。读取盘状态、已刻长度、封盘状态和空白容量参考，检测 ISO 9660／Joliet 根目录中的镜像与图片文件，并抽查盘上是图案、随机数据还是普通文件。`--iso` 复用 `burner.verify_image` 及原回读对象。盘上专属编号能对应日志时复用该次回读，其他情况可明确传入 `--burn-log`。
- `59da9bc` 新增刻完页「看不到图？」。打开先看这次刻录保存的结果，可另点「读取光驱里的盘」。两条路径都使用核心检查单，光照项打开新手引导里的动画。API 版本为 1.2，`checkburn` 是可选能力。
- `aee7477` 新增双语使用说明和离线排错条目，覆盖用户常说的「刻完啥也没有」、英文短问法、Jake 和 Lia 的原话。修正了引用检查发现的 16 处行号偏移。

## 验收

| Disc Lab 场景 | 结果 |
| --- | --- |
| 正常图案盘 | 已刻 4,096 扇区，最后 LBA 4,095，已封盘。识别图案数据，96 个抽样块全部相符。 |
| 写到一半停了 | 已刻 2,048／4,096 扇区，最后 LBA 2,047，未封盘。原 ISO 对照有 48 个抽样块读不回，检查单提示写入问题。 |
| 空白盘及空托盘 | 空盘已刻 0 扇区，占比 0，空白容量与 Lab 真值相同。空托盘显示不可读。 |
| 当文件烧进去 | 用 Disc Lab 写入根目录只含 `图片.iso` 的数据盘，检查单给出「可能」并说明怎样刻录光盘映像。同一个文件旁另有盘面图案时，抽样识别图案并排除该项。 |
| 随机测量盘 | 无刻录日志，24 个位置都符合随机数据，提示这类盘通常没有图。找到同盘标识的测量记录时提示核对批次。 |
| 有记录与无记录 | 无可匹配记录时比对当前盘，有记录时回读对象逐字段相同。测试阻止再次调用比对函数，明确指定日志和用专属编号自动匹配两条路径均通过。带 DIS 名义预设编号的盘可识别预设。 |

- 相关 Python 回归用下列命令，190 项通过。[pytest 日志](D:/dp-dev/tmp/nothingshows/logs/pytest-final.log)

  ```powershell
  python -B -m pytest -n 2 --basetemp D:/dp-dev/tmp/nothingshows/pytest-final -p no:cacheprovider `
    tests/test_checkburn.py tests/test_troubleshoot.py tests/test_burner.py tests/test_recordable_capacity.py `
    tests/test_identity_sessions.py tests/test_r1_disc_identity.py tests/test_afterburn.py tests/test_works.py `
    tests/test_gui_handshake.py tests/test_webui.py tests/test_web_security.py tests/test_webui_catalog.py tests/test_webui_recovery.py
  ```

- `python -B -X utf8 tests/score_troubleshoot.py` 的 45 道报错、46 道症状全部命中第一名。`python -B -X utf8 tools/refresh_troubleshoot_citations.py --check` 通过。
- 用 `python -B -X utf8 D:/dp-dev/tmp/nothingshows/compare_cli.py` 在 Disc Lab 固定时间和路径，对比 `a7b5fbf` 和当前 CLI。中英文 `burn`、`info` 实际运行及两条命令的帮助共八组，标准输出和标准错误逐字节一致。[输出对照](D:/dp-dev/tmp/nothingshows/logs/cli-parity.log)
- `python -B -X utf8 D:/dp-dev/tmp/nothingshows/run_mjs.py` 逐个运行 `tests/test_*.mjs`，56 个文件最终均通过。原本用命令行导出 DOM 的四个 Edge 测试通过 CDP 适配脚本保留原断言。首轮两项因测试脚本的禁驱动开关也屏蔽了 Lab 虚拟驱动而失败。为这两项恢复仅暴露虚拟驱动的 Lab 配置后复验通过，取消刻录 32 项、可擦写盘 18 项。刻完页与新检查单复验通过 24 项。[首轮日志](D:/dp-dev/tmp/nothingshows/logs/mjs-full.log) · [复验日志](D:/dp-dev/tmp/nothingshows/logs/mjs-retry.log)
- 八张截图放在 `D:/dp-dev/tmp/nothingshows/shots/`。纸色和夜色、中英文各有一张入口与一张检查单。入口是 1440×900，检查单是 1440×1240，浏览器测试核对六项都在截图范围内。[夜色中文检查单](D:/dp-dev/tmp/nothingshows/shots/checkburn-list-dark-zh.png) · [纸色英文检查单](D:/dp-dev/tmp/nothingshows/shots/checkburn-list-paper-en.png)

## 限制与合并信息

- UDF 和其他文件系统的根目录需要用系统里的文件窗口查看。图案判断取样有限，图案很窄、盘面纹理特殊或遇到读取错误时可能给「没法自动判断」。无原镜像且无对应回读的盘，可以查有没有数据，完整性仍需参考原镜像或原刻录报告。
- 真光驱、实盘亮度、USB 供电效果和 Linux 真机均未测。CD 数据扇区和音轨用字节夹具验证，主要盘况和刻后流程用 DVD Disc Lab 验证。盘的实际图案和观看角度仍由人确认。
- 给 Claude 的合并信息。并行卡如果也改了 `API_VERSION` 或 GUI 的可选能力列表，合并时请保留 `checkburn` 的可选能力和统一后的 API 版本，并复查排错条目的行号。根报告单独提交，方便整合各卡报告。UDF 是否纳入 alpha 后续支持、截图观感和最终措辞留给审查者决定。

STATUS: DONE
