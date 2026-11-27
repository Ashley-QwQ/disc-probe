# A6：失败后先保住现有盘

本次以 `3938acf2c2eda9cd576c1536c60b39d51428a2cf` 为基线，在 `core/fail-exits-20261112` 工作树内修改。先读了 A6 与 `docs/goals/d107-failures/REPORT.md`。只使用假设备、模拟驱动器和已有数据；没有联网、访问真实光驱或刻录，没有修改照片模块、照片 L 处理或网页文件。所有新日志放在 `C:/disc-probe-scratch/fail-exits/`。

| 失败原因 | DP 现在的处理和最省盘的下一步 | 证据 |
| --- | --- | --- |
| `info` 长时间没有输出 | 开始时立即输出。打开设备限 5 秒；每条查询向系统传入 3 秒超时，另有最多 4 秒的墙钟等待；整次查询共享 25 秒预算，关闭最多等待 1 秒。超时后跳过后续查询，保留部分结果和诊断包，退出 1。先关闭其他光驱程序、重新放入同一张盘再查。 | `test_info_every_step_has_native_timeout_and_next_action`；`test_info_ignored_driver_timeout_never_reuses_handle`；`test_info_cli_failure_keeps_partial_report_and_bundle` |
| INQUIRY、容量、轨道信息、配置、MODE SENSE、TOC/ATIP、盘结构或性能查询卡住 | 全部 `info` 查询有相同的超时和具体步骤名；计时探针的配置、读取、FUA、逐出及零长度缓存探测统一传入 5 秒超时。SG_IO 和 SPTI 错误包含命令名、超时值及下一步。没有改 CDB 字节、数据传输内容或解析算法。 | `test_probe_timeout_preserves_cdb_payload_and_names_step`；`test_spti_timeout_header_and_error_without_opening_device`；`test_sg_timeout_header_and_error_without_opening_device`；`test_preflight_timeout_saves_a_run` |
| Windows 非管理员 IMAPI 查询 | 打开、执行、关闭全部在同一个工作线程，保持 COM 的线程要求；查询超时后排队清理，不在尚未返回的调用下面关闭缓冲区。人工选择光驱在 I/O 预算之外。 | `test_info_open_execute_close_stay_on_one_worker`；选驱动器先于工作线程的假设备测试 |
| 计时不进入 CAV | 保留原有分类和停止角度测量的行为；自动保存诊断。失败速度历史也记录“主轴未稳定”，耗尽后不循环推荐旧速度。先用同一张盘试未试速度，再换已有光驱；不以重刻修理读取状态。 | `test_spindle_failure_history_never_loops_failed_speeds`；既有 `test_clv_at_every_speed_stops_suggesting` |
| 缓存、主机定时器假周期 | 已识别的 Windows 15.625 ms 及分频周期改为停止，明确说不能据此认定 CLV。已判 CAV 时，FUA 读取与周期不成整圈也停止。先在同一张盘对照 FUA／逐出缓存。CLV 不同半径的周期不做这种整圈比较。 | `test_cached_host_tick_stops_separately_from_clv`；`test_nonintegral_fua_period_stops`；selftest 的 timer tick 检查；既有 CD CLV 求解测试 |
| 首个拟合前失败 | 现在也保存 summary、已有命令事件、参数、版本和失败原因，并输出诊断包位置；不会再只说“没有写结果”。 | `test_geo_failure_before_first_fit_still_saves_diagnostics`；`test_cache_probe_timeout_is_a_saved_failure` |
| 测量范围窄、内部有空洞、作品超出实测跨度 | 用作品实际使用的半径检查覆盖。`image` 和 `tiles` 在写 ISO 前停止；预设导出保留原有覆盖门槛。保存诊断后优先缩小作品，或重读同一张盘的缺失区域，不调松 chi²。 | `test_saved_incomplete_range_refuses_export_without_writing` 三组保存数据；`test_image_reports_actual_drawing_extrapolation` |
| 候选耗尽 | 保留 `candidates_exhausted` 等部分完成状态，自动保存诊断，不包装成完整测量。完整范围的使用仍拒绝；明确限定在实测区间内的局部使用继续沿用基线规则。优先缩图或重读已有盘。 | `test_partial_run_has_task_scoped_trust`；保存数据的候选耗尽用例；六类诊断出口测试 |
| 抖动、局部异常、整圈计数不安全或模型不适合 | 原 chi²、25 度预测安全界限、桥接和独立修正检查保留；停止出口补保存诊断。没有为得到通过结果而放宽门槛。 | 既有 geo 变轨距、整圈解包和非稳定测试；首拟合前失败用例 |
| CLV CD | 研究用的锚定半径／轨距仍可保存，附诊断和限制说明；不能据此导出可刻图的扇区角度映射。修复非模拟入口引用已删除检查函数的问题，统一走平台适配器；拟合前超时也保存诊断。先换能 CAV 的已有光驱，再走 DiscImageStudio 标定。 | `test_cd_clv_cli_and_export_boundary`；`test_native_clv_entry_uses_platform_adapter_and_saves_stop` 的 Windows／Linux 假后端；六类诊断出口测试 |
| 容量口径混用 | `info.json` 和终端分别列几何总量、当前空盘可写容量、可读已写长度与随机镜像长度的含义。随机镜像另存 `.capacity.json`；图像与预设元数据也说明本次数字的用途。2297888 与 2295104 不再暗示为不一致错误。 | `test_three_capacity_meanings_from_saved_blank`；既有可写容量测试 |
| Windows CD 被错误地当数据 DVD／错误模式写入 | 集成适配器在查工具、启动进程、写入前拒绝 CD DAO；中英文都说明外部路径。Windows 外部脚本只配 DP 的 `--cd-sector mode2form1` 镜像，不能送入 Mode 1 镜像。DAO 使用 DiscImageStudio 或 Linux cdrdao。 | `test_windows_cd_refuses_before_tool_or_process_access`；`test_burn_cli_refusal_saves_bundle_without_writing` |
| 集成刻录失败或回读不可用 | CLI 失败保存参数、版本、错误和已有刻录日志的诊断包。写入完成、抽样回读、图像目视继续分开。回读失败时先重读同一张盘，不直接要求再烧；只有日志证实数据未写全／不可读时才考虑换盘。 | 新刻录拒绝用例；既有 burner 假适配器与回读测试 |

容量例子来自已保存的 RITEKF1 空盘查询：几何总量 2298496 扇区，这张空盘可写 2297888 扇区；默认 DVD 随机镜像写 2295104 扇区。不能把任意两项相减当成所有 DVD 固定的边界开销。`random --sectors` 控制镜像文件长度；`timing/geo --sectors` 控制每次读取多少扇区；`disexport --sectors` 控制与 DiscImageStudio 一致的映射总量；`label --sectors` 是绝对映射终点，默认采用随机镜像长度。真正写入时仍必须检查当前空盘的可写空间。未知值保持未知。标签命令的中英文帮助另见 `label-help-en.txt`、`label-help-zh.txt`。

分享已有结果只需：

```text
python -m discprobe diagnose RUN
```

也接受该运行的 `summary.json`。程序在运行目录写 `diagnostics.zip`，打印实际文件清单。包内有 summary、settings、versions、失败原因及可用日志；没有原始日志时如实注明。只收固定文件名，不递归找文件、不跟随文件符号链接、不包含照片和环境变量。JSON、CSV、日志中的外部 Windows／Unix／UNC 路径会脱敏，运行内路径用 `<RUN>` 表示；原始结果文件保持原样。大于 8 MiB 的单文件不收，并在说明中列出，避免把整个大目录误打包。生成包后仍应查看内容再分享。

实际演示使用保存的 `geo-H-20261107-183256` 的副本，命令退出 0，产物和打印清单分别是 `C:/disc-probe-scratch/fail-exits/saved-geo/diagnostics.zip` 与 `diagnose-example.txt`。原始证据目录没有写入。

## 验证结果

日志路径均相对于 `C:/disc-probe-scratch/fail-exits/`。

| 检查 | 结果 | 日志／机器记录 |
| --- | --- | --- |
| 全量 pytest | 588 passed，1 skipped，182 subtests passed；退出 0 | `pytest-final.txt` |
| 定向组合回归 | 109 passed，4 subtests passed；退出 0 | `focused-final.txt` |
| 最终失败出口、隐私与选驱动器检查 | 48 passed；原生退出 0 | `exits-verified.txt`、`verified-results.json` |
| 补充跨平台 CLV 出口及相关回归 | 67 passed；原生退出 0，含最终 50 项失败出口测试 | `platform-fixed.txt` |
| 提示、空托盘、断开／中断的状态检查 | 0 失败；原生退出 0 | `ui-verified.txt` |
| Node 全部 26 个入口 | 首轮 26/26；最终逐入口复核 26/26，无剩余失败 | `node-results.json`、`node-latest-results.json` |
| 完整 selftest | all checks passed；原生退出 0 | `selftest-verified.txt`、`verified-results.json` |

Node 复核曾有 4 个 Edge 浏览器启动／退出超时。只关闭了本任务临时配置目录对应的遗留浏览器进程，未改网页、断言或超时值；随后全部复测通过。失败原日志保留在 `node-final-*`、`node-retry-*`；最终一个预设浏览器检查的独立通过记录为 `node-presetio-verified.txt`。

本次也修复了首拟合前 Ctrl+C 保存诊断时的空结果访问；空白 CD 提示保持命令行位置，断开设备的检查要求保存具体 READ 错误，而非只保存笼统的 interrupted。早期失败与中断日志没有删除，也没有算作验收通过。最终原生退出码通过 `verify_final.py` 的 `subprocess.returncode` 记录，原始 stderr 仍完整保留，避免 PowerShell 将数值库警告包装为命令失败。修改源码的 SHA-256 在 `source-hashes.json`。

## 仍未保护或未验证的部分

- 没有真盘、真实 Windows 驱动栈或 Linux 内核测试。本次 SG_IO 是伪 libc 调用，SPTI 是伪 DeviceIoControl 调用；证明超时字段、错误出口和字节保持，不证明所有 USB 桥／固件会遵守超时。计时探针依赖系统原生超时；`info` 另外提供墙钟退出，但不能取消一个内核中尚未返回的调用。
- 假周期识别是保守的已知模式检查，不能证明发现所有缓存伪周期，也可能拒绝接近主机节拍的真实周期。测点之间的未知模型偏差没有被协方差消除，局部通过不等于全盘准确。
- Windows 集成 CD DAO 仍未实现；外部工具的实际扇区模式、刻录和 CD 沿轨标定仍需真实介质验收。明确说明外部路径不等于本轮实刻验证。
- 没有复现 #107／#108 的所有实际写入错误，也没有把未知原因归为供电或硬件故障。源 ISO、写入完成、96 块抽样回读与目视图案仍是不同证据。
- 既有 `disexport --force` 仅供明确要求的离线检查，仍可能写出不可用于刻录的预设；本次没有新增绕过门槛的参数，也没有放宽既有门槛。磁盘不可写或空间耗尽时，诊断文件本身仍可能保存失败。
- 本轮观察到的浏览器夹具启动／退出偶发超时没有在本任务根治；复测通过不能替代这方面的后续稳定性检查。
