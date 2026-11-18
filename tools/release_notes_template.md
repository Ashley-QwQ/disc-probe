# disc-probe [VERSION] / 三个软件包 · Three packages

Tag: `v[VERSION]` · GitHub pre-release · Commit: `[COMMIT]` · Date: `[DATE]`

## 中文

这是同一个预发布版本下的三个独立软件包。公开版本为 `[VERSION]`（例如 `1.0.0.0-alpha`）；Python wheel / sdist 使用 `[PEP440_VERSION]`（例如 `1.0.0.0a0`）。以下可选包是否提供，以本次附件和 `manifest.json` 中的状态为准。

### Disc Probe — alpha

- **是什么 / 给谁用：** 光盘几何测量与图案制作工具，面向需要核心程序、命令行或图形界面的用户。
- **下载：** Windows 和 Linux x86_64 免安装版共用 `disc-probe-[VERSION]-full.zip`。已有 Python 的用户可选 `disc-probe-[VERSION]-core.zip` 或 `disc_probe-[PEP440_VERSION]-py3-none-any.whl`。源码为 `disc_probe-[PEP440_VERSION].tar.gz`。
- **启动：** 解压完整包到可写目录，Windows 双击 `开始 Start (Windows).bat`，Linux 运行 `bash start-linux.sh`。core 版按包内说明准备 Python 和依赖。wheel 使用 `python -m pip install ./disc_probe-[PEP440_VERSION]-py3-none-any.whl`，然后运行 `disc-probe --help`。离线安装 wheel 需自行预备依赖。
- **Linux 实盘测试：** 完整包已提供一键启动。Linux 下读取、刻录实盘和从网页发起刻录都未实测。欢迎有光驱的 Linux 用户试用读盘、刻录并反馈。所需设备权限和刻录工具见 `INSTALL-linux.md`。
- **状态 / 已知限制：** alpha；兼容性与光驱、介质相关。本次适用平台与已知问题为 `[SUPPORTED_PLATFORMS_AND_KNOWN_LIMITS]`。软件包检查不代表真实光驱、刻录或测量精度已经验证。
- **校验：** 在统一 `SHA256SUMS.txt` 中查找所选附件；大小 `[PROBE_BYTES]`，SHA-256 `[PROBE_SHA256]`。

### Disc Lab — 开发者工具

- **是什么 / 给谁用：** 与同一提交核心快照配套的 `disclab/` 目录，面向开发、实验和测试用户。
- **下载：** `disc-lab-[VERSION].zip`。若冻结提交尚无 `disclab/`，本包跳过，附件中不提供该文件；本次状态 `[LAB_STATUS]`。
- **安装：** 先安装本版本 Disc Probe wheel，或准备同版本 core；将 ZIP 中的 `disclab/` 解压到核心可导入的工作目录，按包内说明准备开发依赖。在该目录执行 `python -m pytest disclab/tests -q` 进行检查。
- **状态 / 已知限制：** 开发者工具，接口和用法可能变化。与发布核心配套的自动测试结果 `[LAB_TEST_COUNTS]`；用途、依赖和限制以包内文档及 `[LAB_KNOWN_LIMITS]` 为准。
- **校验：** 使用统一 `SHA256SUMS.txt`；大小 `[LAB_BYTES]`，SHA-256 `[LAB_SHA256]`。

### Disc Neo — 预览数据

- **是什么 / 给谁用：** 独立的 atlas、纹理卡与来源说明，面向数据检查、可视化和实验用户。本包数据为模型预测，非实拍（**predicted, not photographed**）。
- **下载：** `disc-neo-[VERSION]-preview.zip`。仅在发布时提供合格暂存目录才生成；本次状态 `[NEO_STATUS]`，文件数 `[NEO_FILE_COUNT]`。
- **安装：** 解压得到 `disc-neo/`，双击里面的 `index.html` 就能离线浏览，不用联网，也不用装任何东西。字段说明和来源见 `README.zh.md`、`SCHEMA.md`、`PROVENANCE.json`，许可见 `LICENSE`。
- **状态 / 已知限制：** preview data；不代表实测颜色、光盘照片或刻录效果验证。模型、覆盖范围与使用限制见来源说明及 `[NEO_KNOWN_LIMITS]`。
- **校验：** ZIP 使用统一 `SHA256SUMS.txt`，逐文件大小与 SHA-256 见 `manifest.json` 的 `disc_neo.files`；大小 `[NEO_BYTES]`，ZIP SHA-256 `[NEO_SHA256]`。

### 许可

三个包都按 GNU GPL-3.0-or-later 授权：代码（disc-probe、Disc Lab）和数据（Disc Neo 的纹理图谱与色卡）用同一份许可，全文见各包里的 `LICENSE`。

### 检查与校验说明

本次发布检查结果：`[RELEASE_GATE_RESULTS_AND_COUNTS]`。完整检查日志位置：`[CHECK_LOG_LOCATION]`。未执行或不覆盖的检查：`[NOT_RUN_AND_SCOPE_LIMITS]`。请在填写时使用真实检查记录，保留未执行项。

所有软件包共用一份 `manifest.json` 和一份 `SHA256SUMS.txt`。manifest 记录冻结提交、公开版本、PEP 440 版本、各附件所属软件包以及跳过原因。`SHA256SUMS.txt` 包含所有附件和 manifest 的摘要；不包含自身摘要。

PowerShell：`Get-FileHash ./[DOWNLOADED_ASSET] -Algorithm SHA256`，与 `SHA256SUMS.txt` 对照。Linux：在附件目录执行 `sha256sum -c SHA256SUMS.txt`（全部附件均在本地时）。校验通过表示文件与清单一致。

## English

One GitHub pre-release contains three separate packages. The public version is `[VERSION]` (for example, `1.0.0.0-alpha`); Python wheel / sdist metadata uses `[PEP440_VERSION]` (for example, `1.0.0.0a0`). Optional package availability follows the attached files and the statuses in `manifest.json`.

### Disc Probe — alpha

- **What / audience:** Optical-disc geometry measurement and image-design software for users of the core, CLI or GUI.
- **Download:** `disc-probe-[VERSION]-full.zip` includes portable Python for Windows and Linux x86_64. For an existing Python setup, use `disc-probe-[VERSION]-core.zip` or `disc_probe-[PEP440_VERSION]-py3-none-any.whl`. The source archive is `disc_probe-[PEP440_VERSION].tar.gz`.
- **Start:** Extract the full package to a writable directory. On Windows, double-click `开始 Start (Windows).bat`. On Linux, run `bash start-linux.sh`. For core, prepare Python and dependencies using the included instructions. For the wheel, run `python -m pip install ./disc_probe-[PEP440_VERSION]-py3-none-any.whl`, then `disc-probe --help`. Offline wheel installation requires locally prepared dependencies.
- **Linux hardware testing:** The full package includes a launcher. Reading and burning real discs on Linux, including starting a burn from the web UI, await hardware testing. Linux users with an optical drive are invited to try reading and burning and share their results. See `INSTALL-linux.md` for drive permissions and burning tools.
- **Status / limits:** Alpha. Compatibility depends on drives and media. Supported platforms and known issues: `[SUPPORTED_PLATFORMS_AND_KNOWN_LIMITS]`. Package checks do not establish real-drive, burn or measurement accuracy results.
- **Checksums:** Find the chosen asset in the shared `SHA256SUMS.txt`. Size `[PROBE_BYTES]`; SHA-256 `[PROBE_SHA256]`.

### Disc Lab — developer tool

- **What / audience:** The `disclab/` directory paired with the same frozen core commit, for developers, experiments and tests.
- **Download:** `disc-lab-[VERSION].zip`. Skipped if `disclab/` is absent from the frozen commit. This release: `[LAB_STATUS]`.
- **Install:** Install this release's Disc Probe wheel or prepare its core package. Extract `disclab/` into a working directory where that core can be imported; prepare development dependencies as documented in the package. Run `python -m pytest disclab/tests -q` there.
- **Status / limits:** Developer tool; interfaces and usage may change. Tests against the matching core: `[LAB_TEST_COUNTS]`. See package documentation and `[LAB_KNOWN_LIMITS]` for scope and requirements.
- **Checksums:** Shared `SHA256SUMS.txt`. Size `[LAB_BYTES]`; SHA-256 `[LAB_SHA256]`.

### Disc Neo — preview data

- **What / audience:** A separate atlas, texture cards and provenance bundle for data inspection, visualization and experiments. **Predicted, not photographed.**
- **Download:** `disc-neo-[VERSION]-preview.zip`, present only when a valid staged folder is supplied. This release: `[NEO_STATUS]`; files `[NEO_FILE_COUNT]`.
- **Install:** Extract `disc-neo/` and double-click `index.html` inside to browse it offline; nothing to install and no network needed. Fields and provenance are in `README.md`, `SCHEMA.md` and `PROVENANCE.json`; the licence is in `LICENSE`.
- **Status / limits:** Preview data. It does not establish measured colours, disc photographs or verified burn outcomes. Model, coverage and usage limits: provenance documentation and `[NEO_KNOWN_LIMITS]`.
- **Checksums:** Shared `SHA256SUMS.txt` for the ZIP; `manifest.json` → `disc_neo.files` for every file's size and SHA-256. ZIP size `[NEO_BYTES]`; ZIP SHA-256 `[NEO_SHA256]`.

### License

All three packages are licensed under GNU GPL-3.0-or-later: the code (disc-probe, Disc Lab) and the data (Disc Neo's texture atlas and colour cards) alike. The full text is in each package's `LICENSE`.

### Checks and verification

Release gate results: `[RELEASE_GATE_RESULTS_AND_COUNTS]`. Complete logs: `[CHECK_LOG_LOCATION]`. Checks not run or outside scope: `[NOT_RUN_AND_SCOPE_LIMITS]`. Fill these fields from actual records and retain all not-run items.

All packages share one `manifest.json` and one `SHA256SUMS.txt`. The manifest records the frozen commit, public and PEP 440 versions, each asset's package, and skip reasons. The sums cover all attached assets and the manifest, excluding the sums file itself.

PowerShell: `Get-FileHash ./[DOWNLOADED_ASSET] -Algorithm SHA256`, then compare with `SHA256SUMS.txt`. Linux: run `sha256sum -c SHA256SUMS.txt` in the asset directory when every listed file is present. Matching checksums establish consistency with the inventory.
