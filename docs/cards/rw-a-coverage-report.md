# RWA 真盘走查验收

分支 `dev/rw-a-coverage`，基点 `73f7073`。对应走查第 13、14、18、24、11、9 条。

## 提交

- `5544129` 在几何精度目标之后检查默认图片与预设所需的半径。按缺口补读，沿用原拟合及整圈判定。增加只读续测、逐级事件和 `geo --json`，统一两条预设保存路径的范围门槛。
- `b6e952c` 在结果页呈现缺口和“补测空档”按钮，用结构化事件驱动实时图，切换阶段时更新主按钮预估。在编辑器里显示全部已测环带，用斜线标出间隙。API 1.2 增加可选能力 `geo-coverage`。
- `2fc8d2e` 保留显式选择局部范围的命令行用法。默认测量留有空档时，终端给出缺口和续测命令，省去“good”判词。
- `e10c206` 增加补读次数和时间上限、事件去重、失败结果恢复以及主按钮阶段预估回归。
- `60ba293` 更新 GUI 握手测试，验证旧内核缺少 `geo-coverage` 时仍可启动。
- `b728b59` 让盘库浏览器测试等导入面板关闭并返回新作品表单，再检查空批次字段。保留原断言，不改产品导航。

## 几何与网页

- 真盘回放复制 `D:/dp-dev/integ/results/geo-H-20261119-231212` 的五个文件到 `D:/dp-dev/tmp/rwa/replay-real/`。在副本上运行 `coverage.assess_range(fit, DVD_PRESET_MM)`，确认预设范围内缺 36.883–40.429 mm 和 47.131–49.566 mm。默认图片还需要向内覆盖约 0.140 mm。编辑器取得三段 24.630–36.883、40.429–47.131、49.566–57.263 mm。
- 对同一副本执行 `disexport --geo <副本> --sectors 2297888 --output <临时文件>`，再执行 `calibrate --geo <副本> --sectors 2297888 --preset <临时文件>`。两条命令均返回 1、报告同样的两个预设缺口，均未写出预设。
- `python -B -X utf8 D:/dp-dev/tmp/rwa/lab_compare.py before` 与 `after` 使用 Disc Lab GH70N 读取模型与种子 178。覆盖完整场景均读 22 级，`targets.csv` 与 `events.csv` 逐字节相同。`summary.json` 除墙钟耗时外逐字段相同。两侧 `targets.csv` 的 SHA-256 均为 `5ad4ed9f96eeee181aec8b28d45ad1268143298f3a8cc7b775a78d331255b798`。
- 同种子的空档场景复现了 36.883–40.429 和 47.131–49.566 mm。22 级变成 25 级，默认图片和预设所需范围补齐。`u` 从 180517.84068936 到 180517.84081529，差 0.000126，原 1σ 为 0.011027。`v` 从 5.591208422761 到 5.591208419505，差 3.26×10⁻⁹，原 1σ 为 4.24×10⁻⁷。
- `python -B -m discprobe geo --sim cav --json --out <临时目录>` 返回 22 条 `geo_point`，级号 1–22，以及 `progress`。点包含 `rung`、`lba`、`radius_mm`、`residual_deg`、`sigma_deg`。阶段切换的 MJS 测试从旧阶段的 `about 1 s` 回放到几何阶段，验证主按钮采用新的 300 秒初始预估。
- `node D:/dp-dev/tmp/rwa/screens.mjs` 使用无头 Edge 与 CDP，走隔离的 `webui --new-instance --port 18765 --local-only`。先载入模拟旧版留下的 22 级结果，点“补测空档”。Disc Lab 作业仅执行 `check → geo → preset`，发出第 23、24、25 级，保存预设并回到“可用”。脚本在收到真实测点事件后逐条放行，以便截图。页面记录的未捕获异常为 0，测试服务和 Lab 已清理。[截图目录](D:/dp-dev/tmp/rwa/shots) · [事件记录](D:/dp-dev/tmp/rwa/screens-result.json)

## 镜像与颜色方案比较

按 `I:/dp-archive/tmp/regress/RESULT.md` 的方法，用同一配方、输入和硬盘上的完整镜像算 SHA-256。回归脚本把两侧的 ISO9660 时间冻结在同一秒，除此之外沿用生产写入器。历史 SHOW 和 CARDB 配方在两侧均拒绝原来的几何覆盖。追加的受控用例沿用相同图案、纹理和 `u/v`，只在临时副本中给定覆盖充足的范围，以比较完整镜像字节。[回归脚本](D:/dp-dev/tmp/rwa/regress.py) · [时间戳包装](D:/dp-dev/tmp/rwa/fixed_launch.py)

| 用例 | 字节数 | 改前与改后共同的 SHA-256 |
| --- | ---: | --- |
| SHOW `IMG2654-1x21-A`，受控覆盖 | 4,393,271,296 | `f211280a763a5a8163e5a61357fbc89de54b00e144ede58dd7a10a6ebc2d88a1` |
| `CARDB-1x21-1`，受控覆盖 | 4,393,271,296 | `e764c09f3f608a837b45e26a8dc9aa5b9ca8e0ba805dc3c8733a83fbd45e7037` |
| PCAL-B `pn_dvd_sealed`，历史配方 | 4,700,372,992 | `48c2c3479cc54d8e3ffd86286a622cc6fa1f069a58bc1d74f45c0baae287e232` |
| MIX-A，历史混采写入器 | 3,839,852,544 | `110fef4ec7184efebe8f71da52f7955cae6f8f583dd35b167fbc5ef8a55da388` |

MIX-A 用 `python -B -X utf8 D:/dp-dev/tmp/rwa/regress.py before --mix-only` 和 `after --mix-only`，沿用历史布局、混采规则和图案数组。两侧还用同一归档插画执行 `colour-design --phone iphone17pro --height 20.78`。方案 JSON 和预测 PNG 分别一致，SHA-256 为 `18f3c3077dba93abbe917aad8ec248ba2f3b3d9e2905fda2829f2b96150fea6c` 和 `f679ec5614cfb1665f5eef60267de459f57f54b775a7633bbe63e2728ac1aeb4`。[改前命令与哈希](D:/dp-dev/tmp/rwa/image-fixed-before/before.jsonl) · [改后命令与哈希](D:/dp-dev/tmp/rwa/image-fixed-after/after.jsonl) · [MIX-A 改前](D:/dp-dev/tmp/rwa/mix-only-before/mix.sha256) · [MIX-A 改后](D:/dp-dev/tmp/rwa/mix-only-after/mix.sha256)

## 自动测试

- 相关 Python 测试用 `python -X utf8 -m pytest -n 2 -q --basetemp D:/dp-dev/tmp/rwa/pytest-final`。选取 `test_geo_coverage.py`、`test_geo_progress.py`、`test_geo_varpitch.py`、`test_geo_speed.py`、`test_geo_unsteady.py`、`test_geo_integration.py`、`test_catalogue_measured.py`、`test_fail_exits.py`、`test_along_track_preset.py`、`test_webui.py`、`test_webui_catalog.py`。第一轮通过 188 项及 42 个子测试，有 7 项失败。修复导入和局部命令的兼容问题后，相关子集复验 43 项全部通过，包含首次失败的 7 项。补上限和实时事件的最终子集 10 项全部通过。[首轮日志](D:/dp-dev/tmp/rwa/pytest-final.log) · [复验日志](D:/dp-dev/tmp/rwa/pytest-recheck.log) · [最终事件和补测测试](D:/dp-dev/tmp/rwa/pytest-events-final.log)
- `node --test --test-concurrency=1` 运行全部 56 个 `tests/test_*.mjs`。首轮 69 项中 63 通过、5 失败、1 超时取消。更新 `geo-coverage` 的握手测试预期后，7 个握手子测试全部通过。`test_motion_browser.mjs` 原样单独重跑通过。传真浏览器用例用原断言由 CDP 等待完成，三个视口通过。往期作品浏览器用例在临时副本只给 `Browser.close` 加等待上限后通过。照片浏览器用例在临时副本延长测试总时限后通过，实际用时约 51 秒。盘库测试基点整例在更早的批次返回断言处失败。分支失败点是关导入面板后立刻检查字段，复验确认回调要等关闭动画。改为等页面返回再检查，整例通过。合计 69 项经首轮或定向复验通过，未重跑整套。[全量日志](D:/dp-dev/tmp/rwa/node-final.log) · [盘库复验](D:/dp-dev/tmp/rwa/review-final.log) · [传真 CDP 启动脚本](D:/dp-dev/tmp/rwa/fax_cdp.mjs) · [临时复验脚本](D:/dp-dev/tmp/rwa/cdp_rechecks.py)

## 供 Claude 转达

- RWB 在接回标定结果时保留 `result.ok`，以及 `geo.measurement.missing_mm` 和 `can_resume`。补读也走 `calibrate` 任务的 `attach` 和结果页。参数 `resume` 指向原几何结果，新结果另存。
- RWC 可以沿用 `geo_point` 驱动的测点和 `step` 事件里的预估初始化。RWA 修改了几何主按钮上的时间来源，步骤尺的配色、纸面布置和光头动画仍由各卡处理。

## 需审查的取舍

- 每次最多尝试 12 个补测级，补测阶段的计时上限为 120 秒。读命令之间检查时限，底层已发出的读命令仍按光驱超时返回。两项上限都用 Disc Lab 自动测试覆盖。
- 缺失身份记录的保留块只有在整块确认是随机数据后才可补读。有效、损坏或不可验证的记录继续保留其保护范围。可续测的是恒轨距角度阶梯。已有变轨距修正的结果出现缺口时，页面提供同盘检查转速并重测。真盘上只做了副本回放，未用真光驱验证续测用时。
- “补测空档 / Measure missing radii”和结果印章措辞请随网页合并一起审查。建议审查历史无盘身份记录时的判据。此类记录靠同容量、已知驱动和 MID 信息、相同转速及三处保存相位来核对，缺少可唯一识别这张盘的标识。

## 执行记录

- 第一次镜像回归对历史 `D:/disc-probe/results/geo-H-20261112-002303/summary.json` 使用了原路径。旧版 `image` 拒绝覆盖后，在同目录写入了 `diagnostics.zip`。后续所有会写诊断的命令改用临时副本。11-19 的真盘原目录仅用于读出和复制。用户的 8765 服务未停止或重启。
- 临时整盘镜像和 Disc Lab 目录已清理。D 盘从开跑时的 187.34 GiB 到收尾时的 186.22 GiB，检查时均高于 5 GiB。

STATUS: DONE
