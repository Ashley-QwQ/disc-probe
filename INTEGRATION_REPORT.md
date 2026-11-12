# 1.0.0 alpha ????

???`31990f2`??? `release/1.0.0-alpha`???????????????????????????????????????? `INTEGRATION_TASK.md`?

## ?????

pytest?302 passed?1 skipped?46 subtests passed?Node?16 ????????? 0?selftest??? 1??? 14 ??????????????

```text
FAIL  and names the read offset, no along-track constant
FAIL  disexport --along-track-frames is refused on an audio fit
FAIL  test_along_track_preset passes (9 checks) -- test_different_directory_with_identical_summary_is_not_same_run: TypeError: test_different_directory_with_identical_summary_is_not_same_run() missing 1 required positional argument: 'tmp_path'; test_explicit_cli_photo_path: TypeError: test_explicit_cli_photo_path() missing 3 required positional arguments: 'tmp_path', 'selected_drive', and 'expected'; test_legacy_disexport_cli_discovers_same_run_photo: TypeError: test_legacy_disexport_cli_discovers_same_run_photo() missing 1 required positional argument: 'tmp_path'
FAIL  test_burn_progress passes (3 checks) -- test_preparation_precedes_generator: TypeError: test_preparation_precedes_generator() missing 1 required positional argument: 'command'
FAIL  test_geo_progress passes (4 checks) -- test_calibrate_simulator_events: TypeError: test_calibrate_simulator_events() missing 1 required positional argument: 'tmp_path'; test_rate_and_emitted_progress_are_bounded: TypeError: test_rate_and_emitted_progress_are_bounded() missing 2 required positional arguments: 'monkeypatch' and 'tmp_path'; test_simulated_geo_progress: TypeError: test_simulated_geo_progress() missing 4 required positional arguments: 'monkeypatch', 'state_check', 'max_targets', and 'sectors'
FAIL  test_geo_unsteady passes (9 checks) -- test_avoid_bands_use_geo_radius_model: TypeError: test_avoid_bands_use_geo_radius_model() missing 3 required positional arguments: 'media', 'audio', and 'last'; test_calibrate_children_and_stop_reason: TypeError: test_calibrate_children_and_stop_reason() missing 4 required positional arguments: 'monkeypatch', 'tmp_path', 'capsys', and 'speed'; test_invalid_avoid_band: TypeError: test_invalid_avoid_band() missing 1 required positional argument: 'band'
FAIL  test_photo passes (15 checks) -- test_accepted_result_mapping_and_original_diagnostics: TypeError: test_accepted_result_mapping_and_original_diagnostics() missing 2 required positional arguments: 'tmp_path' and 'media'; test_duplicate_image_cannot_be_two_independent_photos: TypeError: test_duplicate_image_cannot_be_two_independent_photos() missing 1 required positional argument: 'tmp_path'; test_phone_devices_count_and_rotation_revoke_every_old_link: TypeError: test_phone_devices_count_and_rotation_revoke_every_old_link() missing 1 required positional argument: 'tmp_path'
FAIL  test_recordable_capacity passes (10 checks) -- test_calibrate_exports_whole_capacity: TypeError: test_calibrate_exports_whole_capacity() missing 7 required positional arguments: 'monkeypatch', 'tmp_path', 'capacity', 'explicit', 'catalogue', 'burn', and 'expected'; test_catalogue_is_exact_mid_and_explicit_capacity_only: TypeError: test_catalogue_is_exact_mid_and_explicit_capacity_only() missing 1 required positional argument: 'tmp_path'; test_measurements_without_preset_do_not_require_blank_capacity: TypeError: test_measurements_without_preset_do_not_require_blank_capacity() missing 2 required positional arguments: 'monkeypatch' and 'tmp_path'
FAIL  test_webui passes (6 checks) -- test_job_whose_folder_is_gone_does_not_break_events: TypeError: test_job_whose_folder_is_gone_does_not_break_events() missing 1 required positional argument: 'tmp_path'
FAIL  test_webui_catalog passes (8 checks) -- test_history_saved_runs_and_explicit_burn_links: TypeError: test_history_saved_runs_and_explicit_burn_links() missing 1 required positional argument: 'tmp_path'; test_history_unidentified_runs_stay_separate: TypeError: test_history_unidentified_runs_stay_separate() missing 1 required positional argument: 'tmp_path'; test_measurement_preserves_stop_reason: TypeError: test_measurement_preserves_stop_reason() missing 1 required positional argument: 'tmp_path'
FAIL  test_webui_recovery passes (2 checks) -- test_export_radius_order: TypeError: test_export_radius_order() missing 1 required positional argument: 'tmp_path'; test_recovery_arguments: TypeError: test_recovery_arguments() missing 1 required positional argument: 'tmp_path'
FAIL  every option's help has Chinese (add it to zh.py): ['selected drive identity; required for measuring, checked when saving photo L', 'burn this measurement image first (needs --yes-write and a blank in the drive)']
FAIL  every command's description has Chinese
FAIL  Chinese: -h ['  photo       read the along-track residual from target photos (no drive access)']
```

?????`C:/disc-probe-scratch/release-alpha/baseline-*.txt`?

## ????????

?? `3030687fbee1cb8a61c3314b65252599c524fc73`????? `a51aecd`?

???????????

- `__main__.py`??????????????????????????????????? label ? whois?????? CLI ?????
- `randomdisc.py`??? pending ????????????????????????????????ISO/???????????????????????????????????????????????????
- `timing.py`????????????????????????????????????????????? `reserved.py` ???????????????????????????far?evict?warmup?cache?phase ??????????????????????????
- `geo.py`?????????????????????? completion ???????????????????summary ???? args?????????????
- `burner.py`??????????? keep-open/append/NWA ???????????????????????????????? LBA ????????????????????????????? append ??????????????
- `sim.py`??? CLV ?????????????????????????????????????
- `zh.py`???????????????????
- `tools/burn_imapi.ps1`?C# ?????????????????????????????????????????NWA ??????????????????????????????

????????????????????????? opt-in??? keep-open ????????? id???????????????????? id???? whois ??? LBA 32 ???????????????????????????????????????????????????????

?????60 passed?10 failed????? `_label_parts` ????????????????????????????????????????????????????? tests/data????????????? SHA-256 ? `9b3d84e57046b4759d7be0e4299b16eeb210e96023249d59f46f73dcc8e5942c`?

身份步骤最终结果：pytest **331 passed、1 skipped、46 subtests passed**；Node **16/16 入口退出 0**；selftest **14 项旧失败，逐条文本相同，新增/消失均为 0**。原始日志及审计为 `C:/disc-probe-scratch/release-alpha/identity-*.txt`、`identity-audit.json`。补充的跨功能定向回归为 **61 passed**。后续提交 `2192838` 增加五项跨功能用例；`c716414` 移除测试分支专用临时路径，正式回归遵循 TEMP/TMP。初轮定向运行曾沿用源测试的临时路径，之后已统一纠正。

## 第二步：slim 与照片读取器

选择保留 SciPy，不替换冻结读取器的 gaussian_filter / uniform_filter1d，也不声称 NumPy/OpenCV 近似等价。`pcal.py` 内容不改；slim 对其他模块的数值实现改动保留。

冲突：`zh.py` 两组独立词条均保留；`tools/build_winpack.py` 保留已有 presets 源文件和 slim 的 selftest 数据，同时保留 SciPy，并补齐 pcal 原本就需要的 OpenCV。离线缓存必须提供全部四项依赖；缺少时继续明确失败，不下载、不安装。

原无 SciPy 审计仍为默认；alpha 打包显式选择照片依赖配置，实际导入 pcal/SciPy/OpenCV，记录实际依赖存在性，并继续运行原测试门槛。没有放宽测试失败判定。原瘦包体积数据标为历史结果，当前 alpha 未重新打包。

照片验证：在 slim 合并前后，分别对每张原始照片执行 `python -m discprobe photo --run <C盘独立结果目录> --media dvd --photos <原图>`。11 张全部退出 0；输入 SHA-256、原始 status、原始 L_mm 及组合 verdict **精确相同，无容差比较**。读取器 SHA-256 为 `b90e15db056a6886d6b3f390f8ae6826263ab68ad9394f108d61ad6c7e76ceff`，与集成起点相同。首次在冲突期间中断的照片调用不计入结果，随后整批重新运行了有效基线。

| 照片 | 合并前后原始 status | 合并前后 L（mm） |
|---|---|---|
| IMG_7909.jpeg | ok | 0.21143897358570804 |
| IMG_7910.jpeg | too_few_votes | null |
| IMG_7911.jpeg | ok | 0.12622871365030955 |
| IMG_7912.jpeg | ok | 0.31751139586744653 |
| IMG_7913.jpeg | too_few_votes | null |
| IMG_7914.jpeg | ok | 0.27003670555769416 |
| IMG_7915.jpeg | too_few_votes | null |
| IMG_7916.jpeg | too_few_votes | null |
| IMG_7917.jpeg | ok | -0.01745507735976541 |
| IMG_7918.jpeg | poor_angle_coverage | 0.2031662885577814 |
| IMG_7919.jpeg | ok | 0.07183176123271034 |

每次单张输入的组合 verdict 均为 unsure；表中的 L 是原始读取诊断值，不等于已经接受并可导出的校准。poor_angle_coverage 一项仍拒绝采用其 L。保留原来的数值警告，不改变读取门槛。

环境版本：numpy 2.5.1, scipy 1.18.1, pillow 12.3.0, opencv-python 5.0.0.93。逐张 CLI 原始日志与 photo.json 在 `C:/disc-probe-scratch/release-alpha/before-photos/` 和 `after-photos/`；总核对为 `photo-comparison.json`。新的照片依赖审计入口已实际导入 pcal，并确认两个滤波函数都来自 scipy.ndimage；未执行打包或安装。

slim 合并提交：`e76786a`，来源 `a38f502698f77d5207eaa258371a860fc1947c1b`。完整回归：pytest **336 passed、1 skipped、46 subtests passed**；Node **16/16 退出 0**；selftest **14 项旧断言失败，无新增失败断言**。日志为 `slim-*.txt`，原始逐条文本差异在 `slim-audit.json`。

中文自测的失败文本发生变化：slim 补齐了“先刻录测量镜像”的翻译，原先排在第三项的“DVD 默认 8x”缺项进入前两项输出。已核对 `calibrate.py` 与基线完全相同，后者也是既有缺项，不是新回归。另作独立提交补齐这条翻译，定向解析中文 CLI 并断言 burn-speed 帮助含中文及 8x，通过。自测断言和失败判断未改，后续各步骤仍运行完整 selftest。

## 第三步之一：模板导出

来源 `752aab0958344b08f5833e590ac617b39fa3107d`。三个冲突：

- `simulate.py`：使用模板分支的共享纹理色表及线性响应函数；把已有 random_mask、白纸背景和可选外缘半径一起接入共享响应。默认渲染运算顺序保留，避免把标签预览恢复成黑色背景或丢掉随机数据上下文。
- `webui.py`：模板 ZIP 路由先返回二进制结果，再走原有手机断开/目录/任务分派；不把两个独立 if 生硬拼接，避免成功断开手机后又落入未知路由。
- `zh.py`：新增模板词条加入现有字典，保留身份、标签、slim 和速度文案。

模板合并提交 `2633c67`。回归：pytest **357 passed、1 skipped、174 subtests passed**；Node **17/17 入口退出 0**；selftest **14 项旧断言失败**。日志为 `template-*.txt`，原始失败文本差异在 `template-audit.json`。另对基线全部 CLI 中文缺项作集合比较（不只看自测截出的前两项）：未翻译选项由 20 条降至 14 条，新增选项/命令缺项均为 0；详见 `template-zh-audit.json`。

随后独立修复首段长度发现的元数据边界：有效哈希的 JSON 数组/字符串曾触发 AttributeError，定向用例先复现 1 failed，再增加对象类型检查，使其按既有 ValueError 路径拒绝；相关会话测试 **6 passed**。未改变正常布局、位置协议或校验规则，并增加三个集成错误的中文提示。日志为 `metadata-before.txt` / `metadata-after.txt`。后续各合并的完整回归继续覆盖此用例。

## 第三步之二：编辑器

来源 `8e80e38a7e59d9dffdc1825441eb9ee0602b8644`。五个冲突文件：

- `__main__.py`：template 与 compose 分别建解析器，并把 compose 放入制作镜像命令组；保留已有 label、whois、身份和 completion 参数。
- `simulate.py`：共享缓存色表、线性光响应和最终色调编码；普通纹理/模板、标签 random_mask/白纸/外缘、编辑器材料标签与 fine/draft 开关接入同一最终渲染流程。保留编辑器按设计尺寸采样的能力。文档多字节材料沿用原编辑器公开说明的周期近似，不把它升级成实测光谱结论。
- `web/home/design.js`：模板下载和图层上下移动/删除各自保留明确的提前返回分支，不让图层操作吞掉模板按钮。
- `webui.py`：image 参数增加 textures，disexport 的 photo/reading_drive/completion 保留；模板 ZIP 与 compose 方法并存。响应函数第四位置参数保留给编辑器 headers，模板附件 filename 改为显式关键字，防止把缓存头字典写成附件名。原照片/手机路由和写入确认逻辑保留。
- `zh.py`：增加编辑器、compose、作品模拟的词条，保留前面所有中文和错误提示。

编辑器合并提交 `371707e`。完整 pytest：**432 passed、1 skipped、174 subtests passed**。首轮 Node 为 **19/20 入口退出 0**；`test_pastworks_browser.mjs` 的桌面、窄屏和真实 lobby 功能断言均已通过，但 finally 同步删除 Edge 配置目录时报 Windows EPERM。原始日志 `editor-test_pastworks_browser.txt` 保留。

独立修复该退出竞态：等待测试自己启动的浏览器关闭；超时终止后也等待关闭并检查退出状态；删除目录前保留绝对路径边界断言，改用异步、有限次重试清理，使事件循环能完成退出通知。没有吞掉清理错误、跳过断言或终止其他浏览器。定向重跑完整浏览器入口退出 0（`editor-pastworks-fixed.txt`），随后重跑全部 Node 入口。

编辑器步骤最终回归：pytest **432 passed、1 skipped、174 subtests passed**；修复 `8915e70` 后全部 Node **20/20 退出 0**；selftest **14 项旧断言失败，无新增失败断言**。完整回归仍覆盖首段元数据类型修复 `0c432e6`。日志分别为 `editor-*.txt`、`editor-node-fixed-*.txt`，原始失败文本差异和全部中文缺项比较为 `editor-audit.json` / `editor-zh-audit.json`；中文新增缺项为 0。原始失败日志没有覆写。

## 第四步：本地 origin/main

来源 `c25dfaccee4658c4158ed0d9e9d59e241f486af1`（已合并 PR #32 的引导控制台）。未 fetch。

- `__main__.py` 冲突：Start here 同时列 menu、guide、webui；保留 whois、label、compose、template 及各自参数，接入 main 的控制台入口。
- `guide.py` 两处冲突：保留网页所需的 result_verdict / guide_state JSON 契约，并接入控制台所需的 Task / Plan / workflow 对象契约；不把一个返回类型替换成另一个。workflow 增加可注入 drives 参数以保留合并后的驱动列表读取语义，命令建议继续使用当前 after_timing 的速度历史与 CLV 处理。核心依赖状态仍与 slim 的 numpy/Pillow 检查一致，说明明确区分照片额外依赖并补中文。

自动合并后的打包器仍保留 SciPy、OpenCV、presets、照片审计入口。Linux SG_IO 提交 `86720d1` 在此合并前就已经是当前分支祖先；本次不需要修改 discprobe/scsi.py，也未运行真实 Linux 设备测试。

main 合并提交 `fa9c92f`。首轮完整 pytest 为 **1 failed、432 passed、1 skipped、174 subtests passed**，唯一失败是 `test_fresh_blank_inspection_opens_the_gate_briefly` 清理临时目录时，后台 watcher 仍持有 events.jsonl（Windows WinError 32），不是写入门槛断言失败。定向单跑和修复前 40 次重跑均通过，完整批次堆栈才暴露生命周期竞态。

独立修复 `5c25739`：测试登记 backend.close 清理，并在删除临时目录前等待假任务 finished；不改变 120 秒门槛、确认码、介质或空白盘校验。修复后连续 40 次通过，完整 burner 文件 **26 passed、4 subtests passed**。

首轮 Node 的历史作品用例另报 Edge 写入 DevToolsActivePort 时的 EBUSY。独立修复 `48da762`：在原 10 秒上限内等待可读且包含有效端口/endpoint 的完整文件，只重试指定临时文件错误，其他错误仍立即失败。全部 Node 重跑 **20/20 退出 0**。

修复后的全量 pytest 再次执行，结果：**433 passed, 1 skipped, 174 subtests passed in 541.47s (0:09:01)**。本次 main selftest **14 项旧断言失败，新增断言失败为 0**，新增控制台检查通过。原始日志为 `main-*.txt`，全量复核为 `main-recheck-pytest.txt`，修复后的 Node 为 `main-node-fixed-*.txt`；失败原始日志均保留，未覆写或排除用例。

## 第五步：研究文档与社区校准数据

来源 `822905187737caa99f2b028e008d92fac0c38a2e`。无冲突。提交前核对来源增量恰为六个文件：五个 docs/research/dis 文档和 data/community-calibrations/dis-github.json，没有带入生产代码、其他数据或排除分支。研究链接及社区记录是本地快照，本次未联网复核新鲜度。

研究文档步骤完整回归见下表；与所有前面步骤一样，未省略 pytest、Node 或 selftest。最终六个来源父提交逐一匹配指定顺序，未合并 geo-varpitch、pcal-v2、pcal-lottery 或 atlas-core。

## 合并顺序与最终检查汇总

| 次序 | 来源提交 | 集成分支合并提交 | pytest | Node 入口 | selftest |
|---|---|---|---|---|---|
| 1 core/disc-id-20261112 | `3030687fbee1cb8a61c3314b65252599c524fc73` | `a51aecd2ae4374599222799ee34d3aa86ca36c77` | 331 passed, 1 skipped, 46 subtests passed in 286.27s (0:04:46) | 16/16 退出 0 | 14 项旧断言，0 新增 |
| 2 core/slim-pack-20261111 | `a38f502698f77d5207eaa258371a860fc1947c1b` | `e76786a71a5b4f06697ff26eda54d9996f5f4983` | 336 passed, 1 skipped, 46 subtests passed in 214.13s (0:03:34) | 16/16 退出 0 | 14 项旧断言，0 新增 |
| 3 core/template-export-20261111 | `752aab0958344b08f5833e590ac617b39fa3107d` | `2633c67dd1cfc85ad2913bb1f70c034ef4c7a9e3` | 357 passed, 1 skipped, 174 subtests passed in 502.43s (0:08:22) | 17/17 退出 0 | 14 项旧断言，0 新增 |
| 4 web/editor-20261111 | `8e80e38a7e59d9dffdc1825441eb9ee0602b8644` | `371707e2351f0c6bd83b1b89d1fe2b85c500bc33` | 432 passed, 1 skipped, 174 subtests passed in 525.52s (0:08:45) | 20/20 退出 0 | 14 项旧断言，0 新增 |
| 5 origin/main | `c25dfaccee4658c4158ed0d9e9d59e241f486af1` | `fa9c92f0b5eadb3539a589fc114f0dd7e773ba91` | 433 passed, 1 skipped, 174 subtests passed in 541.47s (0:09:01) | 20/20 退出 0 | 14 项旧断言，0 新增 |
| 6 docs/dis-research-20261112 | `822905187737caa99f2b028e008d92fac0c38a2e` | `bb8c83fc4bf1104a9fb7ee014ea2342bbe09ba41` | 433 passed, 1 skipped, 174 subtests passed in 542.00s (0:09:02) | 20/20 退出 0 | 14 项旧断言，0 新增 |

表格采用修复后的完整结果；初轮失败、具体原因、独立修复提交与定向验证保留在各节及原始日志中。selftest 退出码仍为 1；没有将原有失败标成通过，没有增加跳过项。中文自测只显示前两项缺词，故另比较了完整缺项集合，确保没有新帮助词条缺失。

实际命令：各步骤在本工作树运行 `python -m pytest -q --basetemp=C:/disc-probe-scratch/release-alpha/<步骤>-pytest-temp`；逐个运行 tests/ 下所有 test_ 开头的 JS/MJS/CJS Node 入口；运行 `python -m discprobe selftest`。日志统一在 `C:/disc-probe-scratch/release-alpha/`。HTTP/浏览器用例仅使用本地文件或回环测试服务。

执行说明：第一次基线 selftest 和初轮定向测试沿用了原来的临时目录设置；随后正式逐步回归统一设置 TEMP/TMP 到指定 C 盘目录。最初因合并中临时冲突而中断的照片调用已整批重跑，不计入有效照片结果。所有有效照片输入都来自原始 11 张文件，未修改原图、参考哈希或验收断言。

## Alpha 尚存限制与风险

- 14 项既有 selftest 断言仍失败：包含旧的 CD 音轨导出断言、零参数测试加载器无法提供 pytest fixture、尚未补齐的中文。完整原始清单在报告开头。它们需要独立维护；当前报告不宣称 selftest 全通过。
- 本次没有访问光驱。开放首段、实际 NWA、身份补丁、追加封盘及回读仅有离线、假设备和编译后的假 COM 验证，真实介质行为与标签可见性为 NOT_RUN。抽样回读也不等于全盘校验。
- 四份身份留在首段；追加后发现旧槽依赖可读取、校验正确的首段布局标记。标记与首份同时受损时，不能承诺发现全部旧槽。复制镜像会复制身份记录，它不是防复制凭证。标签盘内布局仍继承原分支的几何来源路径字段；身份记录本身的 basename 隐私边界不等于整盘标签元数据已净化。
- 冻结照片读取器保留 SciPy；11 张实拍输入的原始 status/L 精确相同，只证明这组输入。单张组合 verdict 均为 unsure，不能当作已接受的 L 校准。
- 未重建 Windows 包，未验证离线缓存是否齐备。alpha 现在要求保留 SciPy/OpenCV，不能沿用原瘦包的体积、SciPy 不存在或依赖闭包结论；打包器测试门槛没有放宽。
- 原 EQUIVALENCE.md 的优化最优性、协方差等未证明范围没有在本次解除；额外 slim acceptance 工具本次 NOT_RUN。编辑器多字节材料仍包含周期近似，所有颜色仍是模型预测。
- Linux SG_IO 已在历史中，本次 Windows 环境未运行真实 Linux 设备测试。新标签/身份完整流程仍以 CLI 的独立 opt-in 为准，未另外制作整套控制台或网页专用流程。
- 社区研究是本地资料快照，未联网刷新链接或记录。没有推送、打标签、发布或改写历史。

最终检查确认 discprobe/scsi.py 与起点逐字不变；discprobe/pcal.py 同样不变，照片读取相关直接依赖在照片对照之后也没有变化。编辑器测试产生的两个小 JSON 已移存 C 盘 `editor-evidence/`，对应 SHA-256 在 `editor-evidence-manifest.json`；不混入提交。

## 最终合并日志

命令：`git log --first-parent --merges --oneline 476e1ff..HEAD`。包含任务开始前已合并的三个来源：

```text
bb8c83f integration: merge the research documents and community calibrations
fa9c92f integration: merge the guided console while preserving the web workflow
371707e integration: merge the editor with template downloads and shared rendering
2633c67 integration: merge template export with shared label preview rendering
e76786a integration: merge slim numerics while retaining photo dependencies
a51aecd integration: merge disc identity with label sessions
31990f2 Merge branch 'core/random-label-20261112' into release/1.0.0-alpha
c345332 Merge branch 'core/cd-clv-20261112' into release/1.0.0-alpha
0f7104b Merge branch 'core/completion-offset-20261112' into release/1.0.0-alpha
```

## 追加集成：变轨距与手机校准（2026-11-12）

本轮起点为 `a08b1cf`；只在 `release/1.0.0-alpha` 提交，不联网、不安装、不访问光驱、不推送、不改写历史。用户本轮明确授权合并变轨距分支，取代原任务中暂不合并该分支的限制。来源已核实为 `9bca22535d5bf936903dc77e0b063019ffdfc3ec` 和 `ac8a951620232a3424dbe16eb0de88e5383bacab`，按此顺序处理。

本轮重跑合并前 selftest，退出 1，仍为 **14 项旧失败**；完整清单保存在 `C:/disc-probe-scratch/release-alpha/task2-baseline-selftest.txt` 和 `task2-baseline-audit.json`。与上一轮最终结果的断言身份一致；本轮比较以这份新采集的原始输出为准。

### 变轨距的八个冲突决定

- `discprobe/__main__.py`：保留身份元数据构造，再独立检查实际绘图区间；完成偏移的注册表解析、显式覆盖、重应用入口均保留。geo 把 `auto_correct` 开关传给同一个 Ladder；image 先读取设计范围，再按该范围选择 latest；disexport 使用范围门槛。保留 menu、guide、webui、标签、身份、编辑器和模板入口。
- `discprobe/disexport.py`：继续通过 `read_completion.load_fit` 读取或重拟合完成偏移，不能恢复为直接读取原 JSON；随后对这份 fit 检查范围并寻找同次自动修正。照片 L 的来源、读取光驱检查和导出元数据保留。
- `discprobe/geo.py`：构造参数同时保留 `completion_sectors` 和 `auto_correct`。新预测、桥接、两次重复探测、独立检查共用已有 `_n_end` 和 `_allowed`；保留按读取长度限制采样位置的逻辑，以及 `safe_ranges(..., completion_sectors)` 对标签、布局标记和身份槽的统一避让。完成偏移参与新点的半径计算和反向地址选择。
- `discprobe/guide.py`：先拒绝将实验性 CD CLV 当作可安装角度标定，再做实际使用范围检查。保留 CLV 速度历史、已试速度耗尽处理、`--cd-clv` 说明及控制台 Task/Plan/workflow 契约；增加自动修正、部分测量和外推说明。
- `discprobe/sim.py`：`phi_profile` 与 `cav_above_kbs`、`layout_sectors`、`identity_sectors` 同时保留。读开始和读完成都使用相同的变轨距真值；速度策略和元数据模拟继续有效。
- `discprobe/web/home/guidance.mjs`：统一选取当前 geo 或 timing 的 measurement；保留 CLV 速度历史建议，然后处理部分覆盖和自动修正。保留原恢复命令并增加带修正的 image 命令。
- `discprobe/webui_catalog.py`：同一个返回对象提供 completion_status、coverage、correction、correction_validation 及原 speed_advice、rotation、jitter，不以新字段替换旧字段。
- `discprobe/zh.py`：两侧独立词条均保留；旧身份、标签、速度、控制台、编辑器、模板翻译与新变轨距/范围提示共存。

合并提交为 `e1981a9`。冲突处理脚本首次把标记行匹配得过宽，误删了七个文件的后部内容；这是本轮执行错误，不能作为可用状态。独立提交 `ddbef85` 从原两父提交的 Git 三方合并树恢复完整文件，并改为逐标记行匹配后重新解决冲突。未 reset、amend 或重写该合并提交。恢复后 Python 编译和 Node 语法检查通过；完整回归针对恢复后的树运行。逐块冲突和最终选择保存在 `task2-geo-conflicts.json`，错误脚本的原始记录另存 `task2-resolution-script-error.json`，没有覆写。

首轮完整回归为 pytest **6 failed、433 passed、1 skipped、174 subtests passed**（678.03 秒），Node **20/20 退出 0**，selftest **15 项失败**。六个 pytest 失败及新增的一项 selftest 失败均为离线完成偏移重拟合调用 `Ladder.result()` 时，新增 coverage 代码访问不存在的 ranges。独立修复 `1e6d508` 只在实际探测提供范围后生成 coverage；离线调用不伪造覆盖，也不会覆盖原 fit 已保存的 coverage。原 10 项完成偏移测试和 6 项变轨距测试通过。

新增跨功能用例又复现一项范围错误：在 54.214–57.266 mm 的标签空洞内请求 55.760–55.762 mm，原 0.002 mm 舍入容差竟把整个请求吞掉并返回 covered。独立修复 `49f49fe` 要求至少有一个接近或相交的实测区间；未改变误差门槛、参考真值或原测试断言。新增 `tests/test_geo_integration.py` 同时使用真实格式的四份身份记录和标签标记，覆盖 16 与 65536 扇区完成坐标偏移，检查梯级、两次重复探测、独立新半径检查点的地址及完成位置均避开保留区；覆盖记录保留身份和标签空洞，最终相位真值 rms 仍须小于 0.5°。独立定向结果 **1 passed**（7.88 秒）。

该组合测试的最终模拟将读开始和完成两个边沿的螺旋坐标一起平移，读完成真值为 theta(end + offset)，独立于 Ladder 的坐标函数。最初把 65536 扇区全部作为额外读取延迟时，会制造每次读取上千圈、累计数小时漂移，转速无法稳定；该诊断日志保留。随后零漂移的大延迟试验也未作为验收结果，已终止本轮自行启动的该测试进程。最终测试验证坐标和保留区契约，不声称复现极端真实固件延迟。原分支的标准/高噪声模拟仍使用原有漂移、真值、随机种子和验收规则，未改变。

### 与来源报告的变轨距模拟表对照

在本工作树执行原 `tools/geo_varpitch_check.py` 的标准、`--noise`、`--coverage` 与 `--saved-only` 模式。外层小包装仅把 OUT 改到 `C:/disc-probe-scratch/release-alpha/task2-varpitch-evidence/`，不改模拟或验收。标准 10 例及高噪声 4 例的梯级数、重复位置数、rms/最大误差和模拟光驱时间，按来源报告显示精度逐项相同；全部整圈错误为 0，rms 均小于 0.5°。四种恒定轨距回归的选点完全相同，Δu=Δv=0，无自动修正。程序时间受当前机器负载影响，不能作为真实读盘耗时。22 份保存记录的原始文件只读，重拟合均无 u/v/c/χ² 差异。

参数细节以工具和原始 CSV 为准：该工具没有覆盖 Ladder 的 reps 默认值，DVD/BD 为每点 24 对，CD 为每点 32 对；本轮 targets.csv 的 used 列也分别为 24/32。来源报告“统一每点 24 对”的文字描述不够准确，本轮没有为匹配这句话而改变工具参数。

标准噪声（20 μs）；所有数值列均为“来源报告 → 本轮”。

| 介质 / 曲线 | 梯级 / 重复位置 | 整圈错误 | 最终 rms / 最大（°） | 程序秒 | 模拟光驱秒 |
|---|---|---|---|---|---|
| dvd / constant | 22/0 → 22/0 | 0 → 0 | 0.0196/0.0735 → 0.0196/0.0735 | 1.88 → 3.12 | 153.5 → 153.5 |
| dvd / i218 | 64/232 → 64/232 | 0 → 0 | 0.0424/0.1426 → 0.0424/0.1426 | 7.30 → 9.38 | 2204.9 → 2204.9 |
| dvd / mild | 64/97 → 64/97 | 0 → 0 | 0.0349/0.0917 → 0.0349/0.0917 | 2.56 → 3.13 | 1039.4 → 1039.4 |
| dvd / step | 64/112 → 64/112 | 0 → 0 | 0.0373/0.1555 → 0.0373/0.1555 | 3.11 → 3.74 | 1140.0 → 1140.0 |
| cd / constant | 36/0 → 36/0 | 0 → 0 | 0.0128/0.0311 → 0.0128/0.0311 | 0.64 → 0.79 | 242.6 → 242.6 |
| cd / i218 | 64/175 → 64/175 | 0 → 0 | 0.0365/0.1229 → 0.0365/0.1229 | 6.22 → 8.03 | 2080.1 → 2080.1 |
| cd / mild | 64/92 → 64/92 | 0 → 0 | 0.0159/0.0438 → 0.0159/0.0438 | 3.51 → 4.23 | 1220.4 → 1220.4 |
| cd / step | 64/108 → 64/108 | 0 → 0 | 0.0244/0.1152 → 0.0244/0.1152 | 3.62 → 4.45 | 1350.6 → 1350.6 |
| bd / constant | 22/0 → 22/0 | 0 → 0 | 0.0212/0.0456 → 0.0212/0.0456 | 0.40 → 0.50 | 147.0 → 147.0 |
| cd-audio / constant | 36/0 → 36/0 | 0 → 0 | 0.0240/0.0858 → 0.0240/0.0858 | 0.87 → 1.13 | 424.3 → 424.3 |

高噪声（100 μs，DVD）；所有数值列均为“来源报告 → 本轮”。

| 介质 / 曲线 | 梯级 / 重复位置 | 整圈错误 | 最终 rms / 最大（°） | 程序秒 | 模拟光驱秒 |
|---|---|---|---|---|---|
| dvd / constant | 22/0 → 22/0 | 0 → 0 | 0.1951/0.4346 → 0.1951/0.4346 | 1.78 → 2.12 | 152.1 → 152.1 |
| dvd / i218 | 64/263 → 64/263 | 0 → 0 | 0.1623/0.4327 → 0.1623/0.4327 | 6.60 → 8.34 | 2467.7 → 2467.7 |
| dvd / mild | 64/97 → 64/97 | 0 → 0 | 0.0880/0.2938 → 0.0880/0.2938 | 2.67 → 3.19 | 1044.9 → 1044.9 |
| dvd / step | 64/118 → 64/118 | 0 → 0 | 0.1178/0.3199 → 0.1178/0.3199 | 2.98 → 3.66 | 1183.6 → 1183.6 |

变轨距步骤修复后的完整结果：pytest **440 passed、1 skipped、174 subtests passed**（562.31 秒）；Node **20/20 入口退出 0**；selftest **14 项旧失败、退出 1**（435.42 秒），完整失败文本和顺序与本轮基线逐条相同，新增/消失均为 0，`task2-geo-fixed-audit.json` 中 identical=true。原始日志为 `task2-geo-first-*` 和 `task2-geo-fixed-*`，初轮失败日志未覆写。中文完整缺项集合也已审计，新增选项和命令缺项均为 0。完成这一整套检查后才开始下一项网页合并。

### 手机校准分支

`476e1ff..ac8a951` 只有 `ac8a951` 这一个新增提交，来源增量共 15 个文件；整体合入，没有只摘手机页面。合并提交为 `4f3995f`，其前一提交 `71833d2` 记录了第一步的完整验证。

唯一冲突是 `discprobe/webui.py` 的 OPTIONS：保留 calibrate 的 `completion_sectors`，同时为 photo 增加 `burner`、`burn_path`、`burn_mode`。它们使用 photo 原有参数校验入口，不能把整个 calibrate 或 photo 对象替换成另一侧版本。冲突原始文件保存在 C 盘 `task2-webui-conflict.py`。

自动合并后逐项复核：CLI 默认 LAN 开、`--local-only` 关闭 LAN、`--lan` 保留为兼容空操作；LAN 地址候选和默认路由优先；手机端 JPEG 转码、相册/相机入口、逐张状态和重拍原因；电脑端对同次全部照片去抖、串行合读；刻录来源由实际 burn_result 事件提供。`guidance.mjs` 新增手机状态词表，同时保留变轨距/部分覆盖建议、CLV 速度历史和修正图像命令；webui 的模板 ZIP、compose、完成偏移、照片 L 及原会话/手机令牌校验继续保留。`docs/codex-cards/phone-1.0.md` 和新增/更新测试一并合入。

合并后完整中文帮助审计复现两项新缺词，分别为默认 LAN 的兼容参数说明和 local-only 说明。独立提交 `4f4864a` 补齐两条翻译；原有 selftest 判定未改。修复后完整缺项审计新增选项/命令均为 0，日志为 `task2-web-first-zh-output.txt`，前后 JSON 为 `task2-web-first-zh-audit.json` / `task2-web-fixed-zh-audit.json`。

网页步骤完整 pytest 为 **449 passed、1 skipped、174 subtests passed**（681.65 秒），完整 selftest 为 **14 项旧断言失败、退出 1**（543.66 秒）。首轮 Node **19/21 退出 0**，两个问题均保留原日志并独立处理：

- `test_kit_browser.mjs` 在未修改的 UI kit 输入上发生 Edge spawnSync ETIMEDOUT，原参数重跑也超时。诊断捕获到完整 `PASS: UI kit DOM, cancellation, focus and bilingual preview`，但进程未正常及时退出；不是放宽 UI 断言来修复。独立提交 `6f92c6c` 改为 CDP 读取同一夹具的原 DOM 结果，保留两个窗口尺寸、全部原断言和 30 秒执行预算；明确将测试页置前，恢复虚拟时钟、跳到空白页停止预览，再 Browser.close 并核对自身子进程退出，最后在已验证路径内异步重试清理。中间诊断曾暴露焦点及退出等待问题，日志也保留在 `task2-web-kit-*.txt`；最终两个尺寸均通过。
- `test_photo_wire_browser.mjs` 新增 24999 ms 边界检查出现 1 ms 竞态：页面的 phoneShown 与测试捕获的定时器创建时刻是两次 Date.now。独立提交 `6558e14` 在创建页面前固定夹具时钟，再显式推进到原 24999/25001 ms，原 25 秒阈值和断言均未改；并让浏览器配置目录使用 TEMP/TMP 的 C 盘位置，保留清理路径边界检查。定向完整照片流程通过（17.98 秒），覆盖 375×812、812×375、820×1180、1180×820 四种尺寸。截图在 `C:/disc-probe-scratch/release-alpha/task2-phone-shots/`，已抽查手机横竖屏。

上述两项只改 JS 测试驱动，`git diff 4f4864a..HEAD -- discprobe` 为空；完成 pytest/selftest 后生产代码未再改变。最终全套 Node 另用 `task2-web-node-final-*` 保留独立日志，不覆写首轮失败。

### 本轮补充的 alpha 风险

- 变轨距仍没有真实光盘新读数。模拟通过不能证明任意隐藏尖峰、未读空洞或实测边缘外的误差小于 0.5°；参数协方差也不包含这些模型偏差。身份槽和标签保留区仍是覆盖空洞，不能用最内/最外两点把它们填平。
- 自动加密可能显著增加真机时间：DVD I218 的模拟光驱时间仍为 2204.9 秒，约 36.7 分钟，程序执行几秒不等于真机几秒。Primeon / AD-7701H 的真实噪声、长时状态、实际耗时和再刻图效果均为 NOT_RUN。
- 样条修正不一定可由 DIS 的三次轨距预设表达；保留转换误差检查和越界限制。普通导出的 force 也不会把外推或缺覆盖变成已验证结果。
- 变轨距使 geo/varpitch 再次依赖 SciPy，不再只有照片读取需要它。现有 alpha 打包器已保留 SciPy/OpenCV，本轮未重建 Windows 包或验证新的离线依赖闭包，不能继续使用历史瘦包“生产无 SciPy”的结论。
- LAN 默认开启是本次来源分支的明确行为，`--local-only` 可关闭；手机逐次令牌和主会话令牌仍分开。真实 LAN 可达性、防火墙、iOS/Android 相机及 HEIC 转码没有实机验证。浏览器和后端测试不能替代这些实测。
- 自动合读由电脑校准页的轮询和去抖队列触发；电脑校准页应保持打开。仅上传照片而关闭该页面，不代表后台有独立的自动读取服务。
- 原有 14 项 selftest 失败仍需独立维护；本轮没有修改旧自测的通过标准、隐藏断言或新增跳过项。原合并提交 `e1981a9` 不能单独使用，必须包含完整恢复及后续两个几何修复提交。

### 本轮最终检查汇总

| 次序 / 来源 | 合并及独立修复 | pytest | Node 入口 | selftest |
|---|---|---|---|---|
| 1 geo-varpitch `9bca225` | `e1981a9`；`ddbef85`、`1e6d508`、`49f49fe` | 440 passed, 1 skipped, 174 subtests passed in 562.31s (0:09:22) | 20/20 退出 0 | 14 项旧断言，0 新增；退出 1 |
| 2 walkthrough `ac8a951` | `4f3995f`；`4f4864a`、`6558e14`、`6f92c6c` | 449 passed, 1 skipped, 174 subtests passed in 681.65s (0:11:21) | 21/21 退出 0 | 14 项旧断言，0 新增；退出 1 |

表中采用各项最终有效结果。两个阶段均实际运行全套 pytest、全部 JS/MJS/CJS Node 测试入口和 selftest，没有增加跳过项。网页的两项 JS 测试驱动修复只改测试夹具，生产代码与完成 Python 检查时相同；随后重跑全部 Node 入口，结果见 `task2-web-node-final-*`。Python 日志与逐项审计分别为 `task2-geo-fixed-*` 和 `task2-web-fixed-*`。

网页步骤的 selftest 原始失败文本并非逐字相同：来源分支增加测试后，既有零参数加载器仍无法提供 pytest fixture，旧失败包装器的检查数量或 fixture 提示发生变化。完整 before/after 和未改变的 14 个顶层断言身份保存在 `task2-web-fixed-audit.json`；全部新增用例在 pytest 中通过。完整中文缺项集合另有审计，新增为 0。

最终确认：`scsi.py`、`pcal.py`、`timing.py`、`reserved.py`、`read_completion.py` 与本轮起点的 Git 内容一致。两个来源分支头仍为指定提交；没有改写任何既有提交，没有推送、打标签或发布。关键文件的原始 SHA-256、LF 归一化 SHA-256 和两个合并的完整父提交记录见 C 盘 `task2-manifest.json`。

测试生成的两个编辑器 JSON 已移存 C 盘 `task2-editor-evidence/`，原路径、目标和 SHA-256 见 `task2-editor-evidence-manifest.json`；没有混入提交。原先未跟踪的三个任务/会话文件保持不动。

本轮结束时的完整合并日志（`git log --first-parent --merges --oneline 476e1ff..HEAD`）：

```text
4f3995f integration: merge phone calibration with completion-aware web commands
e1981a9 integration: merge variable pitch with completion offsets and reserved ranges
bb8c83f integration: merge the research documents and community calibrations
fa9c92f integration: merge the guided console while preserving the web workflow
371707e integration: merge the editor with template downloads and shared rendering
2633c67 integration: merge template export with shared label preview rendering
e76786a integration: merge slim numerics while retaining photo dependencies
a51aecd integration: merge disc identity with label sessions
31990f2 Merge branch 'core/random-label-20261112' into release/1.0.0-alpha
c345332 Merge branch 'core/cd-clv-20261112' into release/1.0.0-alpha
0f7104b Merge branch 'core/completion-offset-20261112' into release/1.0.0-alpha
```
