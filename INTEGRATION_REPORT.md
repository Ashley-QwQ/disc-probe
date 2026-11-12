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
