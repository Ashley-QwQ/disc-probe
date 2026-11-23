# SP DVD 起步预设任务卡报告

分支 `dev/starter-preset`，基点 `95d3289`。按主会话决定，A 段改用同盘复测作为相对基线，只比较照片形状门槛内的方向。同盒异盘的修正后角差 RMS 和最大位置误差中位数为 0.077°／0.151 mm，同盘复测为 0.105°／0.205 mm。跨批与跨机器仍无可核实真盘对照。 [A 段报告与分位数](evidence/starter/REPORT.md#相对判据) · [原阻塞及解除决定](BLOCKED-resolved.md)

## 提交

- `f30f0ea` 提交 A 段原始几何比对脚本和报告。13 次 RITEKF1 真盘测量组成 156 个有向配对。两个全量 JSON 结果的 SHA-256 均为 `8438293926f535e4d90364d38b052a828de67665aceba13183ac5a5fb6520033`。
- `e99336b` 记录按原判据停止的原因。
- `66862a1` 增加相对误差表，保留原阻塞文件并注明解除决定。
- `f10a5a3` 增加显式选择的 DVD 起步预设、API 1.6 网页入口、检查盘刻录记录、照片和出图校验、来源标注以及失败回退。起步预设确认后才出现在盘库可用项中。真实 `geo` 摘要和冻结照片路径继续使用原契约。
- `3a048b7` 更新帮助索引中随 B 段代码和手册改动移位的引用。
- `3afa0f5` 用原有的检测光盘任务附带候选。无匹配时不启动额外任务。补上 Windows 无头网页回归测试的正常关闭顺序，避免浏览器子进程占用测试目录。
- `0910c39` 将 A 段脚本二次路径检查收紧为指定的完整五字母串。重跑仍得到逐字节相同的全量 JSON。
- `Record starter preset acceptance results` 记录回归、Disc Lab 场景和截图的验收结果。

## 验收

- `python -X utf8 evidence/starter/compare.py --out D:/dp-dev/tmp/starter/pairs.json` 复现 A 段。分位数按 `relation` 分组，对 `photo_within_shape_limits` 为真的方向计算。25–57 mm 模型误差表同时列中位数、90 分位和最大值。
- `python -m discprobe starter --help` 显示中英文命令和参数。Python 相关测试用 `pytest -n 2 --basetemp D:/dp-dev/tmp/starter/pytest-final`，251 通过，1 跳过，另按路径限制排除了封存照片用例。范围包括起步预设、检查盘、照片与 L、刻录和预检、GUI 握手、盘库、网页、刻录复核及相关 core 回归。
- 最后一次核心调整后，用 `pytest -n 2 --basetemp D:/dp-dev/tmp/starter/pytest-finish tests/test_starter.py tests/test_gui_handshake.py` 复验，13 项通过。
- 最后调整网页检测后，用 `pytest -n 2 --basetemp D:/dp-dev/tmp/starter/pytest-info-final tests/test_webui.py tests/test_starter.py tests/test_troubleshoot.py` 复验，45 项通过。
- 用 Node 跑了 `tests/` 下全部 61 个 `test_*.mjs`，全部已通过。首轮 58 个退出 0。传真和预设浏览器测试首轮停在 `PENDING`，两个文件原样单独重跑均退出 0。网页回退测试验证了无匹配时的旧任务顺序，修复后原断言全通过，随后用正常关闭顺序复验并退出 0。
- `python -X utf8 -m discprobe selftest` 退出 0，输出 1,478 行通过项和 `all checks passed`。首轮发现帮助索引的引用行号漂移，修正后单独的 `tests/test_troubleshoot.py` 也为 5 项通过。
- `NEWPLAN_STARTER_ONLY=1` 运行 `node tests/test_newplan_disc_browser.mjs`，使用真实本地 API 和 Disc Lab 光驱。默认“使用测量盘”，明确选择后按钮变为“刻检查盘”。纸色和夜色、中文和英文、1440 和 390 像素，共 8 张，位于 `D:/dp-dev/tmp/starter/shots/`。移动宽度另检查了选择框的位置。
- Disc Lab 用 40 级的已有 RITEKF1 几何（25.734–57.828 mm），给同 MID 的另一虚拟批次 `LAB-A 2-01` 跳过测量盘。检查盘生成校验 300 个扇区，刻后回读 96/96。6 张照片有 3 张通过现有判据，采用 `+0.197689 mm`。出图 292,064 扇区，镜像 SHA-256 `34d35b9c40a0dc089f0a9068f47b866506a2167889d2fcfe05822fb178ff52a5`。场景目录随即清除。
- Disc Lab 的失败场景在同 MID 的另一个虚拟批次刻检查盘，三张测试图片均返回 `no_rim`。`image` 退出 1 并指向测量盘，未生成图片镜像。随后生成了 16,384 扇区的随机数据测量镜像，场景目录随即清除。Lab 命令和结果在 `D:/dp-dev/tmp/starter/` 的 `*-lab.log`。
- `95d3289` 与当前代码读取 `manual-align/run-cd` 里的真盘摘要和原照片记录，输出按字节相同，均为 `verdict_not_ok`。已有测试的合格 DVD 照片夹具输出也逐字节相同，序列化结果为 1,791 字节、L 为 `20.0 mm`、SHA-256 为 `3a77458755c357f459ee88da9234bf1e2934a187981b78c0444783c4d65114ee`。
- `base_regression.py workflow` 将原版和本分支在同一工作区参数下产生的 `calibrate --drive H: --media dvd --sectors 2295104` argv 序列化为 JSON，字节相同。网页回退浏览器测试也验证了替换空白盘时的查询序列。
- `base_regression.py image` 用现有作品 `w-20261123-020928-d4db` 和真实 `geo-H-20261107-183256` 复跑 `compose` 和 `image`。将作品限制在实测范围内，两版使用相同标签数组、纹理和固定 ISO 卷时间。`95d3289` 和本分支均生成 4,565,172,224 字节，并同为 SHA-256 `7ddddd58d806d3069e92cd1f7b34ba057c6ce08d02fa1fffc1f7b1d1ce994d7f`。镜像已删除，校验记录在 `base-image.log`。
- `Get-PSDrive -Name D,F` 在开跑、相关测试开始前和运行中均确认 D、F 盘高于 5 GB。进程临时目录、报告和截图使用 `D:/dp-dev/tmp/starter/`。检查盘方向箭头位于数据面 12 点，验证了 `pass-target-preview.png` 的对应区域。

## 工程取舍与未测

- 网页默认不选起步预设。仅同一台记录过 `drive_identity` 的本机光驱、同 MID 的标定列为本机来源。同型号的其他记录和同型号、同 MID 社区项只有显式选择入口，标为未验证。没有保存设备身份且无法用现有照片证明来源的旧测量，不会被归为同一台光驱。
- 起步预设保留来源、来源 SHA-256、实测范围和旧 L（未知则为空）。单独的检查盘记录绑定本机光驱、实际刻录路径和这张盘的编号。照片按现有 `pcal.GATE` 和多姿态一致规则处理。确认后的出图半径限于检查盘验证的 26.2–57.0 mm。未通过时转回测量盘。没有实刻，也未验证跨机器或跨批真盘效果。
- 是否以后预选本机匹配、是否扩展社区数据资格留给审查。CD 未实现，需要另验证不同读写链路和它们以帧为单位的 L、同盘多照的来源约束及可用实测范围。

STATUS: DONE
