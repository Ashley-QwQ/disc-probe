# 第一层审查 R2–R9 核心修复

基点为 `dev/1.0.0` 的 `3bd5c5d`。工作树为 `D:/dp-dev/corefix`，分支为 `dev/core-fixes-r2r6`。验证用基点源码快照放在 `F:/dp-dev-tmp/corefix/base-source/`，没有改动其他工作树。

实现与回归测试提交为 `d9a7858`。本报告单独提交。

## 修改及回归

| 项 | 修改位置和行为 | 回归测试 |
| --- | --- | --- |
| R2 | `discprobe/drive_lock.py`、`calibrate.py`、`burner.py`、`eraser.py` 和 `tools/drive_lock.ps1`。普通 CLI 和网页后台共用同一光驱锁。校准在整个命令内保留锁，测量子进程及 PowerShell 适配器各持有受父任务授权的锁。独立调用 `-Machine` 也须取锁。父进程中断时，已经运行的子进程仍保留互斥。 | `test_r2_machine_powershell_respects_another_process_drive_lock`，`test_r2_cli_refuses_while_calibration_owns_drive[cli]`，`test_r2_cli_refuses_while_calibration_owns_drive[web]` |
| R3 | `discprobe/image_output.py`、`ui.py`、`randomdisc.py`、`labelsession.py`。按解析后的 ISO 路径取独占文件锁，生成、自检和保存自检记录期间都持有。只有创建 `.writing` 的任务清除它。任务被杀时留下原数据与标记，后来者收到错误并可选择别的路径。CLI 刻录在使用 ISO 期间也持有该锁。锁文件保留，以便所有进程锁同一个文件。 | `test_r3_concurrent_iso_does_not_delete_other_output` |
| R4 | `discprobe/burner.py` 的 `_write_preflight()` 检查镜像、自检记录、会话布局、介质、容量、速度、取消和刻录日志。需要擦除时先实际写入 `burn_preflight` 日志项，擦除之后再发刻录速度事件。擦除后确认介质已空白或可覆写，并核对可用扇区数。 | `test_r4_log_failure_precedes_erase` |
| R5 | `discprobe/image_output.py`、`__main__.py`、`webui.py`。DVD 自检失败退出 1，保留输出及 `.iso.verification.json` 的 `failed` 记录。CLI 与网页要求 `passed` 和该 ISO 当前大小与修改时间匹配。常规镜像生成路径保存其既有自检结果，随机镜像和续刻标签另检查长度及生成时选取的扇区。 | `test_r5_failed_dvd_self_check_exits_and_blocks_burn`，`test_r5_missing_record_is_refused_and_passed_record_can_burn` |
| R6 | `discprobe/__main__.py`。拒绝从 `correction_unvalidated` 结果自动或手动使用修正，避免静默改变出图映射。CLI 只有明确给出 `--allow-unvalidated-correction` 才继续，中文提示说明理由，网页不提供此选项。拒绝时保留测量文件。 | `test_r6_unvalidated_geo_requires_explicit_opt_in` |
| R7 | `discprobe/burner.py` 的 `sample_lbas()` 将不足 16 扇区的尾部计作最后一块。 | `test_r7_corrupt_partial_final_block_is_sampled` |
| R8 | `discprobe/timing.py` 的 `TimingProbe.setup()` 使用开放盘已读回确认的记录末端，包含 READ CAPACITY 仅报 1 扇区的情况。确认之后的选点、时序和拟合公式沿用原实现。 | `test_r8_timing_uses_read_back_open_track_end` |
| R9 | `discprobe/__main__.py`、`guide.py`、`photo.py`。用原子目录创建抢占输出，同秒碰撞加 `_1` 等序号。历史目录名仍可识别，同秒目录按序号排序。 | `test_r9_same_second_result_dirs_do_not_overwrite` |

R2 的两进程回归分别以 CLI 或网页校准任务为持有者，另一 CLI 尝试 `timing`、`geo`、`erase`、`info` 和 `burn`。基点允许这些调用越过占用检查。修改后均立即退出 75，并显示持有任务为 `calibrate`。设备调用使用替身，PowerShell 测试采用在访问 IMAPI 前必定失败的选项组合。

`native-smoke.log` 另记录一次强制结束父进程的试验。独立 CLI 在 PowerShell 仍持锁时被拒，PowerShell 退出后立即可取锁。

基点与本分支使用同一份编号回归测试。

```text
python -X utf8 -B -m pytest -n 2 -p no:cacheprovider --basetemp=<F 盘测试目录> -q tests/test_core_fixes_r2r6.py
3bd5c5d  FFFFFFFFFFF  11 failed in 7.21s
本分支   ...........  11 passed in 7.38s
```

基点日志为 `pytest-red.log`，本分支日志为 `pytest-green.log`。R3 基点下第二个写者覆盖了原数据，R4 基点下假擦除调用了一次。R5 基点下失败镜像和缺记录镜像均通过对应旧入口，R6 仍把样条传入写入器。R7 漏读 LBA 32，R8 在已确认 4096 扇区时报告无可读区，R9 两份摘要写进同一路径。

## R1 接入位置

卡 AB 可从 `burn()` 传入 `check_medium_identity(drive)`，由 `_write_preflight()` 在日志通过后、首次擦除或写入前执行。该点已持有光驱和 ISO 锁。AB 同时改动了旧刻录前置区及平台适配器，可把确认身份的第一道检查放在此处，继续在擦除和写入适配器入口保留最终复读。此分支未实现 R1，也未合并卡 AB。

## 不变性

| 对照 | 结果 | 原始记录 |
| --- | --- | --- |
| 真实 geo/timing 记录 | 82/82 完全一致。使用 `t1-joint` 中列出的 82 个目录和同一回放方法，两边的完整回放序列化结果 SHA-256 一致。没有字段需要裁剪。 | `F:/dp-dev-tmp/corefix/{before,after}-replay.json` |
| 历史 ISO | 9/9 通过镜像抽样自检。仅按卡 Z 的规则确认并归零 ISO 9660 时间字段后，SHA-256 全部一致。 | `F:/dp-dev-tmp/corefix/history/images/*/raw.json` |
| 卡 Z 旧作品合成 | 26/26 产出的 `.npy` 标签和 `.textures.json` 逐字节匹配。另有一个旧示例两侧均拒绝，未计入分母。 | `F:/dp-dev-tmp/corefix/history/compose-results.json` |
| SHOW-A 与 PCAL-C | 2/2 配对生成结果逐字节匹配。PCAL-C 也与归档标签一致。SHOW-A 用归档画稿和现存历史生成器在两边运行，配对输出一致，归档成品的哈希另有差异。 | `F:/dp-dev-tmp/corefix/historical-labels/{before,after}/sha256.json` |
| CARDB 1–6 | 6/6 配对生成结果逐字节匹配。以第 2 张的边界像素解算历史布局角度的小数舍入，用各盘归档的 RND 箭头与圆点作为固定输入重新绘制扇区色块。两侧与六张归档标签的差异数均为 0。 | `F:/dp-dev-tmp/corefix/historical-labels/cardb-{before,after}.log` |

ISO 对照包含 `cd-grid-m2f1`、`cd-grid2-m2f1`、`cd-grid3-m2f1`、`cd-qmsht`、`COLOUR-1x21-A`、`pn_dvd_sealed` 及三个从作品合成到镜像的历史用例。采用卡 Z 已成功且有入参记录的配方。该卡记录为覆盖不足、缺少原始输入或自身校验失败的用例未计入一致率。

另以同一随机种子重跑普通随机镜像和开放盘的待续刻标签镜像，时间字段归零后 2/2 一致。见 `{before,after}-random-iso.json`。

## 验收与边界

正式运行日志保存在 `F:/dp-dev-tmp/corefix/`。所有设备测试均为模拟光盘、替身或虚拟光驱。浏览器测试只访问本机回环和文件。未接真实光驱、未做实盘擦写、未联网、未推送或合并。

`node tests/test_*.mjs` 逐文件运行，55/55 通过。浏览器回归确认重刻时的擦除完成事件早于刻录开始事件。首次浏览器运行的回环解析规则误拦截了 `127.0.0.1`，已修正规则。批次选择依名称定位，重刻测试等模拟子进程退出后再重载。详见 `js/mjs-results.json`。

相关 Python 模块以 `python -X utf8 -B -m pytest -n 2 -p no:cacheprovider -p dp_isolate --basetemp=F:/dp-dev-tmp/corefix/pytest-acceptance` 运行，结果为 340 passed、1 skipped、46 subtests passed。`dp_isolate` 给各 pytest worker 单独的应用状态目录，防止不同测试的同名假光驱争锁。归档照片的可选递归复验不在本轮范围内。跳过的是当前工作树缺少 PCAL 原稿的测试，已在上面的 PCAL-C 配对验证中直接核对原稿。详见 `pytest-acceptance.log`。

`python -X utf8 -B -m discprobe selftest` 退出 0，输出 `all checks passed`。首次无路径拦截的运行中，Matplotlib 会自动加载一个文件名命中排除规则的附带样式。正式复验在样式发现阶段过滤该文件，并保留打开文件时的路径拦截。绘图测试本身及其几何校验照常执行。详见 `selftest-final.log` 与 `verify-harness/sitecustomize.py`。

开跑和各批验收前检查 D、F 盘均高于 5 GB。配对 ISO、随机镜像及复验生成的大标签数组在校验后移除，保留日志和校验记录。中文输出、帮助及报告通过 UTF-8 与乱码检查，`git diff --check` 通过。

历史镜像如缺少有效的自检通过记录，必须重新生成后才能按本分支的 CLI 或网页刻录。自检仍采用原有采样方法，记录不等同于整个文件的内容哈希。根目录原有 `CARD_REPORT.md` 保持原样。

## merge with dev bb76605

执行 `git merge --no-ff dev/1.0.0` 时，本地分支已从 `bb76605` 前进到 `76be1bb`，后者明确拒绝擦除一次性盘并改善中英提示。因此合并父提交采用本地现行的 `76be1bb`，不变性对照仍使用指定的 `bb76605`。合并在 `dev/core-fixes-r2r6` 进行。卡 AB 的身份取证与许可模型见 [卡 AB 报告](sec-fixes.md)。

- `burner.burn()` 持有光驱锁和镜像独占锁。命令或许可传入的身份快照保持原样。第一次与新读数比对在 `_write_preflight()` 内，晚于日志可写检查，早于任何擦除或写入。同一快照交给擦除入口。Windows 和 Linux 适配器在启动工具前仍最终复读，授权擦除后的刻录按卡 AB 规则核对稳定字段。
- 网页继续一次性消费绑定动作、光驱、介质和镜像版本的许可。签发与启动共用镜像检查，要求完成镜像及当前版本的通过记录。校准的刻录子进程同时收到卡 AB 的介质快照及卡 R2 的光驱锁授权。独立擦除保留卡 AB 的平台复读和卡 R2 的 PowerShell 子进程锁。
- 使用 `tools/refresh_troubleshoot_citations.py` 更新移动的故障排除引用。一次性盘提示提交改变了条件语句，相应引用关键词随实际条件更新。

合并提交为 `4242dba`，父提交为 `a24b97e` 和 `76be1bb`。验收期间 `dev/1.0.0` 又独立前进到 `c4c7ebe`，加入一次性盘的帮助检索条目。本轮验收的代码固定为 `4242dba`。

### 合并后验收

```text
python -X utf8 -B -m pytest -p dp_isolate -n 2 -p no:cacheprovider -q -rA tests/test_core_fixes_r2r6.py tests/test_r1_disc_identity.py tests/test_secfix.py tests/test_troubleshoot.py
35 passed in 20.40s
python -X utf8 -B tools/refresh_troubleshoot_citations.py --check
exit 0
```

其中 R2–R9 11 项、R1 12 项、卡 AB Web 安全 7 项、故障排除 5 项。专项同时验证日志不可写时不进入新读数比对及平台提交前发现换盘时不调用写入工具。初次相关 pytest 的四项失败来自两份缺自检记录的 Web 夹具、一份缺介质身份的校准替身，以及 Windows 读取实例登记时的临时文件共享冲突。夹具现在提供应有的检查结果，实例测试按原超时窗口重试读取。

相关 pytest 覆盖 28 个模块，使用 `-n 2` 与独立 worker 状态目录。JS 在 F 盘镜像中逐个运行。验收后核对镜像与合并提交的应用源码、工具及 JS 测试文件字节一致。

```text
558 passed, 1 skipped, 54 subtests passed in 237.37s (0:03:57)
55/55 JavaScript files passed
```

pytest 跳过的是当前目录没有 PCAL 原稿的可选检查。PCAL-C 原稿在配对合成中另行核对。依赖封存照片递归查找的可选用例排除在验收范围之外。

`python -X utf8 -B -m discprobe selftest` 退出 0，输出 `all checks passed`。沿用文件打开拦截与 Matplotlib 样式发现过滤。设备测试使用替身或虚拟光驱，网络测试限本机回环与本机私有接口。`F:/dp-dev-tmp/corefix/merge-bb76605/` 保留 `pytest-focused.log`、`pytest-acceptance.log`、`js/mjs-results.json` 和 `selftest.log`。

### 与 bb76605 的不变性对照

| 验证项目 | 本轮结果 |
| --- | --- |
| 真实 geo/timing 回放 | 82/82。52 份 geo 和 30 份 timing 的回放序列长度及 SHA-256 均一致。 |
| 卡 Z 旧作品合成 | 26/26 标签和纹理清单哈希一致。另有一个示例两边均拒绝。 |
| SHOW-A、PCAL-C、CARDB 1–6 | 8/8 配对一致。PCAL-C 和六份 CARDB 也与归档逐字节相同。SHOW-A 的归档旧成品与两次一致的重生成结果仍有不同哈希。 |
| 卡 Z 可重建的历史 ISO | 9/9。四个 CD、两个 DVD、三份合成作品的镜像均通过抽样自检。逐一校验并只归零五处 ISO 9660 时间字段，配对的大小及 SHA-256 均一致。 |
| 普通随机盘及待续刻标签 | 2/2。同种子生成，归零 ISO 9660 时间字段后 SHA-256 一致。 |

合计 34/34 标签对一致。历史镜像的逐对日志、原始和归一化 SHA-256 保存在验收临时目录的 `invariance-history.log` 和 `history/images/<case>/raw.json`。历史生成镜像在校验后清理。验收期间 D、F 盘剩余空间均高于 5 GB。没有遇到需要选择一侧安全行为的冲突，配对结果没有发现 ISO 时间字段以外的差异。根目录 `CARD_REPORT.md` 与 `evidence/atlas` 无改动。
