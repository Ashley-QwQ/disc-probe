# 卡 Q：可擦写盘

分支：`dev/rw-discs`；本次开始时 HEAD 为 `5b28fa0`（已含卡 P）。只在此 worktree 修改、提交；未推送、合并或切换分支。

## 提交内容

本卡以一笔提交 `feat: support explicit rewritable disc erase and reburn` 交付实现、测试和本报告。

- MMC 当前 profile 的 CD-RW、DVD-RW 顺序／受限覆写、DVD+RW（含 DL）、BD-RE，以及 READ DISC INFORMATION 的 erasable 位，共同生成 `rewritable`。`rewritable_sources` 分别保留当前 profile、profile 判断和 erasable 原值；读不到的位保留 null，不把光驱支持列表当成当前盘。`disc`、网页盘信息、`info.json` 和 info 新增输出均包含这些信息。
- 新增 `python -m discprobe erase --drive H: [--full]`，默认快速擦除。独立擦除适配器在破坏性操作前重新只读识别；一次写入盘拒绝。新增 `erase_started`、`erase_progress`、`erase_result` 事件和中文提示。失败／取消报告状态未知、重新检测并擦除的下一步，不自动重试或继续刻录。
- `burn --erase` 和 `calibrate --erase` 是已有内容可擦写盘的显式入口。无 `--erase` 不擦、不覆写。擦之前先检查介质家族、容量和速度；擦之后重新检查空白／覆写就绪状态。`--erase` 不可与 `--append` 合用。保留原有只读 SCSI 白名单和一次写入盘空白确认门槛；网页缓存本身不会授权一次写入盘刻录。
- 网页标定页、刻录页提供擦除后重刻；先说明“盘上的内容会被清掉”，再复用开始刻录的滑块确认。共享 Next 滑块增加可选 label，实际可见标签和读屏标签都说明擦除。刻录页重试会清除旧同意，需重新勾选并滑动。删掉标定样稿原来无人赋值的 `item.rw` 分支，没有保留两套擦除入口。
- 半盘停止后刷新恢复的验收复现了另一页预热时抢 Next 的问题：新作品页为图片栅格化会短暂取消 hidden，原 isOn 只判断 hidden，state 尚未建立也能拦截标定页按钮。现要求实际处于 newplan 模式且有 state；浏览器验收显式模拟预热可见状态，验证标定页仍能进入擦除确认。没有改动导航模块或放宽既有导航断言。
- 卡 P 的 3 秒锁定、闪烁、减弱动态效果、用户取消标记保持。按可擦写字段更换停止风险、失败／取消的恢复动作、短盘提示。可擦写盘不再被说成永久不能重刻。保留具体写入失败原因；刷新和重连能恢复盘类型、镜像路径及恢复动作。
- 擦除有独立进度状态，完成之后才进入写入；不会把擦除完成当成测量盘完成。未知 ETA 显示未知，不把工具没有报告的百分比伪造成估计进度。
- Disc Lab 加入 DVD-RW、CD-RW、DVD+RW、BD-RE；MMC profile／erasable 位与模拟介质一致。取消刻录会保存部分写入状态；擦完回到空白，能再次刻录。`practice --media dvd-rw`／`cd-rw` 可选，`--burn-time` 同时缩放擦除：快速约 60 秒，完全擦除按整盘 1× 数据时间估算；quick 模式约 1 秒。
- 随机访问的 DVD-RW 受限覆写、DVD+RW、BD-RE 采用格式化逻辑地址空间作为可覆写容量，并明确来源；顺序 DVD-R/RW 不据 READ CAPACITY 的短刻录长度推断整盘容量。

## 平台处理和用法

以下为用法说明，未在真光驱执行：

```text
python -m discprobe erase --drive H:
python -m discprobe erase --drive H: --full
python -m discprobe burn --drive H: --iso image.iso --yes-write --erase
```

Windows 使用新的 `tools/erase_imapi.ps1`，创建 `IMAPI2.MsftDiscFormat2Erase`，配置 Recorder／ClientName／FullErase，订阅擦除进度并调用 EraseMedia。COM 边界可注入假对象测试，未执行真实 COM 擦除。此同步接口没有本实现可调用的取消方法：收到取消后保持进程，让光驱结束当前擦除，然后报告需重新检测，禁止接着刻录；不承诺立即停止擦除。

Linux：CD-RW 使用 wodim（不存在时 cdrecord）的 `blank=fast`，完全擦除为 `blank=all`；DVD-RW 使用 `dvd+rw-format -blank`／`-blank=full`。DVD+RW、BD-RE 本来可覆写，本入口选择显式重新格式化 `-force`／`-force=full`，成功后标作 overwrite-ready；不会默默擦掉旧内容。快速擦除／快速格式化不是安全销毁数据，也不保证每个旧数据字节已经物理清零。工具取消发 SIGINT，失败后不写盘。

实现依据：[Microsoft EraseMedia](https://learn.microsoft.com/en-us/windows/win32/api/imapi2/nf-imapi2-idiscformat2erase-erasemedia)、[Microsoft IDiscFormat2Erase](https://learn.microsoft.com/en-us/windows/win32/api/imapi2/nn-imapi2-idiscformat2erase)、[dvd+rw-format 手册](https://manpages.ubuntu.com/manpages/jammy/man1/dvd%2Brw-format.1.html)。只查阅文档，没有下载或安装工具、上传项目内容。

## 验收命令与结果

所有硬件操作均由假适配器或 Disc Lab 提供，临时目录和浏览器配置在 `D:/dp-dev/tmp/rwdiscs/`。

### Python

相关批跑命令（TEMP／TMP／DISCPROBE_HOME 均指向本卡 D 盘临时目录）：

```text
python -X utf8 -B -m pytest -n 2 tests/test_rw_discs.py tests/test_burner.py tests/test_burn_cancel.py tests/test_burn_progress.py tests/test_webui.py tests/test_webui_recovery.py tests/test_webui_catalog.py tests/test_recordable_capacity.py tests/test_web_guidance.py disclab/tests/test_burn_time.py disclab/tests/test_disclab.py --basetemp D:/dp-dev/tmp/rwdiscs/pytest-complete -q
```

该轮 **184 passed、46 subtests passed、1 failed，32.78 秒**。唯一失败是既有 `test_design_upload_size_sets_the_cell` 的 144 MB NPY 文件因 D 盘空间不足写不下，不是可擦写功能断言失败。此前按失败项单独复验该项和另三项：**4 passed、3 subtests passed，9.17 秒**；但之后空间再次不足，不能声称最近整批全绿。

新增格式化容量检查后：

```text
python -X utf8 -B -m pytest -n 2 tests/test_recordable_capacity.py tests/test_rw_discs.py --basetemp D:/dp-dev/tmp/rwdiscs/pytest-capacity-final -q
```

**59 passed，19.02 秒**，其中本卡测试 **40 项**。最后连同 burner 复验得到 **85 passed、4 subtests passed**；另带上的上述 144 MB 既有测试仍因磁盘不足失败，原测试断言保持。

覆盖 profile／erasable 映射、非可擦写拒绝、无 --erase 不擦、擦前速度／家族门槛、格式化容量边界、取消保留部分写入、擦除取消不继续写、四类 Lab 盘刻／擦／再刻、擦除时长缩放、中英文短盘提示、HTTP token 门槛。DVD-RW、CD-RW 还通过真正独立 CLI 子进程验证“无 --erase 拒绝 → --erase 重刻 → 独立 erase 后为空白”。Linux 工具派发用假 Popen 验证；Windows 假 COM 编译测试覆盖快速／完全、五类 profile 和一次写入拒绝、事件订阅清理，无真实设备调用。

### 网页与 Disc Lab

```text
python -X utf8 -B D:/dp-dev/tmp/rwdiscs/final_checks.py
```

逐一运行 `tests/` 根目录 **51 个 test_*.mjs**，首遍 **48 个退出 0、3 个失败**，完整逐文件日志保留在 `mjs-final/`。不是反复重跑全部网页测试。

- `test_disc_files_browser.mjs` 首次因 256 MB 全零容量夹具耗尽空间失败。改成真正稀疏文件，文件长度／内容和测试断言不变；修正模块导入后，单独复验 **1 passed、0 failed**。稀疏创建使用 Windows EOF API，不用会分配零数据的 CRT truncate。
- `test_review_library_newwork.mjs` 首次在换盘库的同步时序断言失败，单独复验退出 **0**。
- `test_flow_navigation_browser.mjs` 在共用状态目录时出现不同导航时序失败；基点网页脚本拦截复验退出 **0**，当前脚本使用独立 `DISCPROBE_HOME=.../nav-current-home` 复验也退出 **0**。不能据此认定此前时序失败全是本卡或全是基点问题。后续半盘验收定位的新作品预热事件归属问题已按上文修复。原失败日志仍保留。
- 一次写入盘的 `test_burn_cancel_browser.mjs` 在首遍真实 practice 运行中退出 **0**，旧风险文案、滑块锁定和换空白盘恢复断言通过，截图在 `once/shots/`。
- 新增 `node tests/test_rw_discs_browser.mjs`：真实 `disclab practice --media dvd-rw --burn-time 0.3`、HTTP、SSE 和交付网页，验证停止、刷新恢复、擦除滑块、擦完空白、重刻完成及事件先后顺序；另以只记调用的适配器检查刻录页的风险、重试、重新同意、显式 erase 选项。最后一次结果和证据目录见本报告末尾的最终记录。

核心图案夹具是 1 GB 全零稀疏计时镜像，不是合格的随机数据测量镜像；因此只验写入／擦除状态转换和抽样回读，不把后续几何结果当作有效标定。重刻完成之后仅取消后续只读测量，不取消已完成写入。

### 截图与其他检查

`D:/dp-dev/tmp/rwdiscs/shots/` 保存八张图：`rw-stop-{paper,dark}.png`、`rw-cancelled-{paper,dark}.png`、`rw-erase-slider-{paper,dark}.png`、`rw-erase-progress-{paper,dark}.png`。已检查两主题的实际文案和操作状态；没有更改配色、CSS、纸色／夜色色值或卡 P 的亮红变量。

Impeccable mechanical detector 对 burn-stop、burn、calibrate、design、api、nextconfirm 六个网页目标返回 `[]`，原始记录 `ui-detector.json`；后加的 newplan 一行事件归属修复不在该扫描中。`git diff --check` 通过。中文文件通过 UTF-8 字符检查，未以 PowerShell 非 ASCII 管道生成脚本。

为缓解共享 D 盘不足，只清理本卡已结束浏览器的临时配置和可重新生成的 pytest ISO／head 二进制夹具；保留 JSON、测试日志和截图。网页旧测试生成的 `.impeccable/` 和 `works/` 移到本卡临时目录的 `suite-generated-*`，不纳入提交。不清理其他任务目录。

## 未测、限制和需要决定的问题

- **真光驱擦除、刻录、真盘取消状态、Windows/Linux 实际擦盘时长和介质兼容性：未测。没有在真光驱执行擦盘、刻盘或接盘操作。** 本卡验收完全在虚拟设备和假 COM 边界内。
- Windows 原有集成 CD DAO 刻录限制、核心不支持 BD 刻录的限制仍在；CD-RW 和 BD-RE 的 Lab 可刻／可擦不等于新增了 Windows CD DAO 或真实 BD 刻录支持。
- Lab 新介质沿用同家族的名义几何和写入模型；本卡新增的是可擦写状态转换，没有用真盘校准相变层的材质或光学表现。
- DVD+RW、BD-RE 的驱动／工具是否接受完全格式化，以及格式化后 blank／overwrite-ready 报告差异需真盘验证。不支持时明确失败，不强行重试。实际 Linux 进度取决于工具输出，无百分比时仅发等待状态。
- 屏幕阅读器实际播报、手机窄屏、完整安装包运行：未测。共享滑块的 aria、键盘同意、双主题和现有桌面浏览器测试有自动验证。
- 当前共享 D 盘不足以稳定重跑既有 144 MB 上传测试；报告保留失败和先前独立通过记录，不改断言来换 PASS。需恢复足够空间后再跑上述整批命令，才能得到同一轮全绿。
- 无需人决定的实现阻塞。硬件验收和磁盘空间属于上述保留项；没有修改 `evidence/atlas/*.py`。

## 最终记录

- 最终 `node tests/test_rw_discs_browser.mjs`：**18 项检查通过，退出 0**；证据 `D:/dp-dev/tmp/rwdiscs/browser-m67NXk/`（`checks.json`、`cancelled-job.json`、`rewrite-job.json`、`practice.log`）。用户停止事件为 `by=user`、`phase=burn`、`fraction=0.5043103448275862`，即约 **50.4%**。事件顺序为 erase_result completed（blank=true），随后 burn_result completed。包含预热状态下 Next 的事件归属回归验证；无浏览器错误。
- 八张双主题截图已用该最终流程覆盖更新；最后检查了擦除确认和夜色擦除进度，实际滑块明确写“滑动确认擦除后重刻”，进度标题、任务名、剩余时间和禁用主按钮均为擦除状态。
- 新增中英文文案单测 **2 passed**，原停止／短盘单测 **3 passed**，kit pure helpers 通过；中文 CLI `erase -h --lang zh` 正确显示快速／完全擦除帮助。
- 最后编码检查覆盖 **19 个含中文改动文件**，非 ASCII 字符均保留，连续四个问号的损坏串为 **0**；记录 `encoding-check.json`。`git diff --check` 通过。
- 中间半盘验收曾因 D 盘满而让事件日志写入失败，也曾撞到上述新作品预热抢按钮；均保留各次临时目录记录。最终流程开启浏览器禁用组件更新选项，减少与测试无关的缓存写入，没有减少应用断言。
