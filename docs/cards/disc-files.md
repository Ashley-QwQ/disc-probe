# 卡 L：DVD 随盘文件交付报告

日期：2026-11-15。工作区：`D:/dp-dev/discfiles`，分支：`dev/disc-files`。

## 提交与实现

- `882d9eb` — `feat: add DVD files alongside disc artwork`
  - 新增 `discprobe/discfiles.py`：扫描本机目录，生成唯一的扇区布局，给出元数据、逐文件起止 LBA、图案区及半径。区间均为左闭右开，文件按 2048 字节取整。
  - 写入 ISO 9660 主目录树及 Joliet 中文目录树、两套大小端路径表；保留目录结构及文件/目录的修改时间。拒绝超过 4 GiB−1 的单文件。
  - 图案编码器只处理布局允许的扇区，文件与元数据不会进入图案编码。镜像旁的 `.image.json` 保存布局、布局摘要和文件 SHA-256。
  - 保留 `DISCPROBE.ID` 的 LBA 21 主副本及三个既有分散副本，并保护所在 DVD ECC 块。测试验证内外圈均可读到四份一致副本。
  - 新增 `files-layout` JSON 命令；`image` 新增 `--files`、`--files-at`、`--files-margin`、`--writable-sectors`。
  - 新增 `/api/files-layout` 和独立前端模块 `design/disc-files.mjs`、`disc-files.css`。设计页通过粘贴本机目录路径选择文件，显示元数据/文件占用环与剩余图案范围；预览页使用同一布局的环。
  - 导出前重新检查文件，随后将核心生成的布局 SHA-256 传给 CLI。文件树、容量或几何变化时，CLI 拒绝旧布局；复制时再次检查文件尺寸和修改时间。
  - 新增不导入写入器的只读解析器 `discprobe/iso_read.py`，以及可重复执行的 Windows 挂载、独立解析、Disc Lab 全盘读回脚本 `tools/verify_discfiles.py`。
- `d4af281` — `fix: merge contiguous file guide intervals`
  - 将相邻占用扇区合并成引导环。无身份记录时，内圈为一个占用环，外圈为元数据与文件两个环，避免按每个小文件重复绘制。
- `042d585` — `test: read back empty and capacity-boundary DVD images`
  - 增加内外圈空目录、恰好装满的实际 ISO 写入及独立解析/哈希验收，随后增加一字节确认明确拒绝。
- 本报告随报告提交保存。

已先读 `D:/dp-dev/cards/COMMON.md`、`disc-files.md`，以及调查报告第 6 节第 1 条、第 2 节 D12 布局说明；只读参考了 `DataRegionPlanner.cs`。没有复制 DIS 代码，没有编译或运行 DIS。没有改动 `evidence/atlas/*.py`，没有切换分支、推送、合并或改其他 worktree。

## 布局规则与使用

- 无身份记录时：LBA 16/17/18 分别是主卷描述符、Joliet 描述符和终止符；路径表与目录接在后面。0–15 为系统区，保护但不计入 `metadata_sectors`。
- 内圈：元数据后紧接文件，图案在剩余外圈。外圈：元数据留在开头，文件位于实际写入范围末端，图案在中间。
- 外圈默认余量为可写扇区的 `0.05`，实际镜像末端再向下对齐到 16 扇区；内圈默认 `0`。保留 5% 是参考调查中的边缘保留思路所选的保守策略，未经本任务实盘测定。它缩短实际输出镜像，避免把图案写进本应留空的盘边。外圈可设 `--files-margin 0`。
- 半径由同一布局中的 LBA 转换；有几何时使用出图同款模型及照片 L 修正，没有几何时只显示明确标注的“标称半径”引导，出图前按实测更新。
- `/api/files-layout` 和携带文件目录的 `/api/run` 均要求客户端及 Host 为本机 localhost。手机、局域网界面显示不可用原因，服务端也拒绝这些请求。

示例（容量数字应替换为空白盘 info 或该批盘几何中的实际可写扇区数）：

```powershell
python -B -m discprobe files-layout --files 'D:/作品/随盘文件' --files-at outer --writable-sectors 2295104 --geo 'results/geo-run/summary.json'
python -B -m discprobe image --geo 'results/geo-run/summary.json' --picture 'picture.png' --files 'D:/作品/随盘文件' --files-at inner --writable-sectors 2295104 --output 'iso/with-files.iso'
```

布局命令的 stdout 是 JSON；选择几何时的说明文字走 stderr。仅有 `--geo` 时，布局命令需要该几何有 `capacity_sectors` 或 `total_sectors`，否则明确要求填写 `--writable-sectors`。

## 自动验收

所有测试的 TEMP/TMP 均指向 `D:/dp-dev/tmp/discfiles/temp`；pytest 始终使用 `-n 2`，没有跑整个 Python 测试套件。

| 验收 | 命令/范围 | 结果 |
| --- | --- | --- |
| 相关 Python 回归 | 下列完整命令 | 141 passed，42 subtests passed；44.88 秒 |
| 最后补充的容量边界测试 | `python -B -m pytest -n 2 tests/test_discfiles.py --basetemp D:/dp-dev/tmp/discfiles/pytest-boundary-final -q` | 9 passed；6.07 秒 |
| 全部 JavaScript 测试 | 排除 COMMON 禁读路径后，`rg --files tests -g 'test_*.mjs'`，逐个 `node --test` | 42 个文件全部成功；47 个 Node 测试，0 失败，0 跳过 |
| 合并引导环后的前端复验 | `node --test tests/test_disc_files_browser.mjs`、`node --test tests/test_disc_files.mjs` | 浏览器测试 1/1；纯函数测试 1/1（7 项断言） |
| 界面机械检查 | `impeccable.cmd detect --json`，目标为 design.js、preview.js、新增 mjs/css | 返回 `[]` |
| 空白/差异检查 | `git diff --check`、暂存区同项检查 | 通过 |
| 中文编码 | `python -B -X utf8 D:/dp-dev/tmp/discfiles/summarize.py` | 含中文的代码/测试及本报告均有非 ASCII 字符，无连续 3 个以上问号 |

相关 Python 回归完整命令：

```powershell
python -B -m pytest -n 2 tests/test_discfiles.py tests/test_webui.py tests/test_discid.py tests/test_discid_copies.py tests/test_photo_l_image.py tests/test_cell_size.py tests/test_design_compose_route.py --basetemp D:/dp-dev/tmp/discfiles/pytest-locked-final -q
```

测试覆盖内圈/外圈、空目录、12 层深目录、中文名、跨扇区目录记录、空文件、未整扇区文件、容量刚好装满及超一字节、单文件 4 GiB−1 边界和超过 4 GiB 的拒绝、源文件变化、过期布局、禁止输出进源目录、身份副本及文件/图案互不覆盖。4 GiB 级尺寸通过 stat 替身验证边界，没有为此生成 4 GiB 文件；真实装满及超容测试使用缩小的 1000 扇区容量。

逐文件 JavaScript 日志及汇总位于 `D:/dp-dev/tmp/discfiles/test_*.mjs.log`、`mjs-summary.json`。其他既有 UI 测试产生的截图已移到同目录的 `js-screenshots/`，没有混入提交。

## Windows 挂载、独立解析与虚拟刻录

最终生产代码验收命令：

```powershell
python -B -X utf8 tools/verify_discfiles.py --root D:/dp-dev/tmp/discfiles/acceptance-release --mount --lab
```

输入为脚本生成的中文测试目录：133 个文件、71,309 字节、14 个子目录，包含空目录、空文件和 12 层深目录。详细清单及 SHA-256 在 `acceptance-release/source-manifest.json`；各项结果及布局在 `acceptance-release/verification.json`。

| 放置 | Windows Mount-DiskImage | 独立解析器 | Disc Lab 虚拟刻录后全盘读回 |
| --- | --- | --- | --- |
| 内圈 | 133/133 文件、71,309 字节，SHA-256 全部一致；147/147 文件及子目录修改时间一致 | Joliet 原路径及中文名全部一致；ISO 9660 主树也读到 133 个文件，内容哈希全部一致 | 32,768/32,768 扇区逐字节一致，共 67,108,864 字节 |
| 外圈 | 133/133 文件、71,309 字节，SHA-256 全部一致；147/147 文件及子目录修改时间一致 | Joliet 原路径及中文名全部一致；ISO 9660 主树也读到 133 个文件，内容哈希全部一致 | 31,120/31,120 扇区逐字节一致，共 63,733,760 字节 |

全盘读回同时包含文件区、元数据区和图案区，没有只抽查文件区。源 ISO 与虚拟光驱读回的全盘 SHA-256：

```text
inner  1a2b4095fc682c443b2dcfaf277241e840cac1997a78803c23abd003f095f130
outer  6aabab3084fd007b628729d9daa2537ac33c2860a6ea8549b5cd31978a8bbefe
```

脚本在 `finally` 中使用 `Dismount-DiskImage` 卸载，结束后又通过 `Get-DiskImage` 确认两份最终镜像的 `Attached=False`。虚拟刻录日志分别为 `inner/virtual-burn.log`、`outer/virtual-burn.log`。没有枚举、打开或刻录实体光驱。

## 界面截图与并行分支接口

截图来自真实设计页及真实本地布局接口，使用隔离的无设备后端；不是静态模拟页面。为看清占用环，截图目录使用两个合成文件，其中一个为 256 MiB；这些截图的“标称半径”状态与上述挂载验收的 133 文件输入不同。

- `D:/dp-dev/tmp/discfiles/shots/inner-paper.png`
- `D:/dp-dev/tmp/discfiles/shots/inner-dark.png`
- `D:/dp-dev/tmp/discfiles/shots/outer-paper.png`
- `D:/dp-dev/tmp/discfiles/shots/outer-dark.png`

浏览器检查了四种状态、输入/按钮尺寸、错误路径、清除、键盘焦点、窄屏列内适配及 403 拒绝；颜色全部沿用已有变量。新增 CSS 只作用于 `.disc-files-step`，没有改其他编辑器样式。

给卡 I / K 的合并接口：

- `design.js` 导入 `disc-files.mjs`；`buildLeft()` 尾部调用 `mountFilesStep()`，不依赖旧 `FILES_READY`、旧容量比例估算或浏览器目录上传。
- `S.files` 保存 `{folder, where, margin, writable, layout}`。`filePictureRange()`、`occupiedRings()` 只消费核心返回结果。
- `makeBurnFile()` 导出前 `refreshFiles()`，使用 `fileArguments()` 传递核心参数及布局摘要。
- 预览上下文的 `project.fileRegions()` 返回同一布局的占用环；`preview.js` 只新增引导绘制。
- 卡 K 可以继续删除旧的关闭态文件面板、常量及上传事件；需要保留上述新模块接口。没有把旧按字节比例估算重新开放。

## 限制、未测及下一步

- **实盘未测。** 需要支持普通数据 DVD-R / DVD+R 单层刻录及读回的光驱（例如项目已有的 GH70N）和两种同批次空白单层盘。建议先小文件混合盘，再验证接近容量上限、外圈余量 0/5% 的盘；用另一台光驱或电脑复核中文目录、全文件哈希和图案实物效果。
- Windows 挂载及虚拟读回证明本机文件系统可读、数据一致；不证明盘边可靠性、实体光驱兼容性或图案观感。完整 4.7 GB 镜像的挂载/虚拟刻录、真实近满盘刻录和其他操作系统读取均未测。
- Joliet 使用 UCS-2：单组件最多 64 个 BMP 字符；非 BMP 字符（例如部分 emoji）及过长文件名明确拒绝，没有静默改名。修改时间按 ISO 目录记录的 UTC 整秒保存；创建时间、访问时间和亚秒精度未保存。符号链接、目录联接及网络目录不支持。
- 开启身份记录时，固定的分散 ECC 保留块可能在文件之间留下空隙；每个文件始终单一连续区段。若目录元数据碰到固定副本，或找不到足够连续的文件空间，会拒绝，不能以覆盖身份或文件来强行放满。
- CD、BD、UDF、文件碎片化及可引导 ISO 未实现，符合本卡范围。接 CD 时应先接入 CD 逻辑扇区、Mode 1 / Mode 2 与 DAO 写入/读回路径，复用目录清单及区间保护测试，不能直接套用 DVD 字节处理；接 BD 时应使用 BD 写入单位、真实容量和独立几何，补 UDF 以支持大文件，重新验收文件系统元数据与图案的簇级隔离。
- 无阻塞性待决定事项。5% 默认值是可配置的首版策略，是否调整应以后续实盘证据为准。
