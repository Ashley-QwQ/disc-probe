# 打包输入按可信 SHA-256 锁定

工作树 `D:/dp-dev/linuxpack`，分支 `dev/linux-pack`。本卡跟进第二层审查第 5 项。

## 提交与合并

- `ec2b7f0` 按指令将 `dev/1.0.0@07db2e6` 合入当前分支，其中包含卡 AA `746ec65`。Windows BAT、Linux 脚本、首读文本和弃用转发壳采用上游的启动逻辑。完整包继续同时带两个平台的 Python 和 headless OpenCV。
- `7b11db4` 增加输入锁定、离线预装、发布输入清单和负向测试。
- `9a96319` 将 Windows embed 的文件名及 URL 对齐到 PSF 发布表的 64 位入口。摘要始终与本地原始 ZIP 相同。
- `b3ab474` 隔离包验收的服务进程和状态目录，清理测试进程时使用本次启动的解释器进程。
- `c85f1f0` 更新四个 LAN 模式用例的桩，使其验证卡 AA 合入后的单实例入口和服务配置。
- 本报告提交记录构建、两端复验与体积拆分。

合并后的五个相关 pytest 文件覆盖 103 个用例和 8 个子测试。首轮 101 个用例通过，另有两个用例受已有 8765 监听及实例复用影响。让无效 GUI 用例显式开独立实例，并让端口用例接受已被占用的 8765 后，两项定向复验通过。三个相关 Node 脚本均通过。本机已有的 WebUI 未停止。

## 锁定和来源核对

[pack_inputs.lock.json](../../tools/pack_inputs.lock.json) 包含原始 CPython 归档和 wheel 的名称、版本、平台、解释器与 ABI 标签、官方文件 URL、官方校验来源及 SHA-256。构建先复制到每次新建的临时目录，再校验副本。wheel 还核对文件名、METADATA、WHEEL 标签以及当前 Python 3.13 下的依赖闭包。SciPy 要求 NumPy `>=2.0.0,<2.8`，OpenCV 要求 NumPy `>=2`。两者均由 NumPy 2.5.1 满足。Pillow 的可选 extras 未启用。

Windows 和 Linux 分别从核对过的 wheel 安装，使用 `pip install --require-hashes --no-deps --no-index --find-links … -r …`。临时安装目录会在构建结束后清理。发布 `manifest.json` 和 ZIP 内的 `release-build.json` 都记录锁文件摘要和逐项 `verified: true`。

每行的锁定值、官方值和本机原始文件实算值相同。

| 原始输入 | 平台和解释器标签 | 锁定 = 官方 = 实算 SHA-256 | 校验来源 |
| --- | --- | --- | --- |
| CPython 3.13.14 embed ZIP | Windows AMD64，cp313 | `90b4e5b9898b72d744650524bff92377c367f44bd5fbd09e3148656c080ad907` | [PSF 64 位嵌入包发布表](https://www.python.org/downloads/release/python-31314/) |
| CPython 3.13.14 install_only | Linux x86_64 GNU，cp313 | `31ebbb024fecb446d7f25a5b59ca1d4955597ca3f5b4b76f55b30a8987eb61c9` | [Astral 20260610 SHA256SUMS](https://github.com/astral-sh/python-build-standalone/releases/download/20260610/SHA256SUMS) |
| NumPy 2.5.1 | win_amd64，cp313 | `6c3fe51bc6a16453d452997053454f309e8e0ed7b42d6b361ce4ac8c32913d74` | [PyPI JSON](https://pypi.org/pypi/numpy/2.5.1/json) |
| NumPy 2.5.1 | manylinux x86_64，cp313 | `9726558e8db4a5bf7929a70ae50f63abda4daf0efe810e3bfbab95976f75fc1a` | [PyPI JSON](https://pypi.org/pypi/numpy/2.5.1/json) |
| Pillow 12.3.0 | win_amd64，cp313 | `1cca606cd25738df4ed873d5ad46bbdb3d83b5cbca291f6b4ff13a4df6b0bbe8` | [PyPI JSON](https://pypi.org/pypi/pillow/12.3.0/json) |
| Pillow 12.3.0 | manylinux x86_64，cp313 | `0847a763afefb695bc912d7c131e7e0632d4edc1d8698f58ddabec8e46b8b6d3` | [PyPI JSON](https://pypi.org/pypi/pillow/12.3.0/json) |
| SciPy 1.18.1 | win_amd64，cp313 | `559ed65f60c1af5a03f3912605a1b5114f522c7c32fb23c3376ae8f03219fe28` | [PyPI JSON](https://pypi.org/pypi/scipy/1.18.1/json) |
| SciPy 1.18.1 | manylinux x86_64，cp313 | `fdaf5ea890a6183d0565f51a61799d67081bd5b1cf03c5f4b3fd3732108625c9` | [PyPI JSON](https://pypi.org/pypi/scipy/1.18.1/json) |
| opencv-python-headless 5.0.0.93 | win_amd64，cp37-abi3 | `829717b6a95554f273e49e357cee3b3a2a26b6f4842fbc1bed2b45bdd8f87e0e` | [PyPI JSON](https://pypi.org/pypi/opencv-python-headless/5.0.0.93/json) |
| opencv-python-headless 5.0.0.93 | manylinux x86_64，cp37-abi3 | `ed709fdf9aa0bd1f2ed8549e71d19449b03a675bb581eb292285f6861953be37` | [PyPI JSON](https://pypi.org/pypi/opencv-python-headless/5.0.0.93/json) |

指定的 `C:/disc-probe-scratch/gui-handshake/winpack-cache` 不存在。Windows 原始 ZIP 从 `D:/disc-probe-dist/cache` 只读取得，校验后复制到 `F:/dp-dev-tmp/linuxpack/pinned-cache`。Python.org 仅用于读取发布表。Windows wheel 通过 `pip download` 从 PyPI 取得。Linux 原始归档及 wheel 沿用 F 盘前一轮缓存，重新核对官方摘要。构建无需连接下载站，发现输入缺失或不符会立即退出。

## 负向与正向验收

负向自动化覆盖 Windows NumPy 单字节改动、Windows 和 Linux CPython 归档各改单字节、Pillow 版本不符、Linux NumPy 平台标签不符，以及缺失 Linux SciPy。六个用例均要求命令非零退出、指出受影响的输入、输出目录无 ZIP 且无残留临时目录。release 编排的输入校验失败用例也验证不会生成发布 ZIP。

首轮完整 pytest 在四个旧 LAN 测试失败。它们在实例复用逻辑引入后仍替换旧的服务构造调用，并触及正在运行的本机实例。改用单实例入口的测试桩后，四项定向验收通过，再跑完整彩排。

```powershell
$env:TEMP = 'F:/dp-dev-tmp/linuxpack'
$env:TMP = $env:TEMP
python -X utf8 -B tools/release.py --version 1.0.0.0-alpha --out F:/dp-dev-tmp/linuxpack/rehearsal-pinned --cache F:/dp-dev-tmp/linuxpack/pinned-cache
```

- 构建快照 `c85f1f0`。[status.json](../../evidence/pack-inputs-pinned/release-status.json) 为 `PASS`，68/68 条命令退出码 0。pytest 为 `1210 passed, 2 skipped, 196 subtests passed`，55/55 个 MJS 和 1/1 个 CJS 脚本通过。Disc Lab 为 `153 passed, 2 skipped`，Disc Neo 未启用。
- 完整 ZIP SHA-256 为 `c552518c7d323585ba66ac742cfb359b03ee554946e2ecfe951663fe5d58b7fb`。发布目录 `F:/dp-dev-tmp/linuxpack/rehearsal-pinned/assets`，摘要文件的 7 项均已复算。包内和发布清单的十条输入记录一致，见 [inputs.json](../../evidence/pack-inputs-pinned/inputs.json)。
- 完整 ZIP 在本机 Windows 解压至含中文和空格的目录，BAT 帮助和包内 `python/python.exe -m discprobe selftest` 均通过。[Windows 日志](../../evidence/pack-inputs-pinned/windows.log)

| 主机 | 系统 | 解压工具 | 整包验收 | 日志 |
| --- | --- | --- | --- | --- |
| x79 | Ubuntu 24.04.4 LTS | BusyBox unzip | PASS | [运行](../../evidence/pack-inputs-pinned/x79/verify.log) · [清理](../../evidence/pack-inputs-pinned/x79/cleanup.log) |
| agentbox | Ubuntu 26.04 LTS | 系统 unzip | PASS | [运行](../../evidence/pack-inputs-pinned/agentbox/verify.log) · [清理](../../evidence/pack-inputs-pinned/agentbox/cleanup.log) |

两台主机都校对整个 ZIP 的 SHA-256，并核对启动脚本解压权限为 0755。实际执行 `bash start-linux.sh --local-only --no-drives --port 0`。以包内 Python 运行 `selftest`、`webui status --json`、`webui stop` 均通过。大厅与版本接口返回 200。停止后状态为未运行，监听端口关闭。上传和解压目录已清理。

## 同源对照

用 `8ef9ad0` 的旧打包器和新打包器分别构建卡 AA 合入后的同一份 `discprobe/` 源码，版本文件均写成 `1.0.0.0-alpha`。旧基线只用于对照，沿用当时的 Windows 已安装缓存及 Linux 构建方式。新版的输入验证和安装均使用原始文件。

两份 ZIP 中 `discprobe/` 的 **603 个文件全部逐字节一致**。两个平台中各自的已安装包名和版本完全一致。[逐项对照](../../evidence/pack-inputs-pinned/comparison.json)

- Windows 的 site-packages 有 1291 个文件原始字节相同。差异类型为 .whl 1 项、RECORD 2 项、direct_url.json 1 项。
- Linux 的 site-packages 有 1648 个文件原始字节相同。差异类型为 RECORD 4 项、direct_url.json 4 项。

Windows 新出现的同名 .whl 是官方 SciPy wheel 的 RECORD 中列出的 0 字节占位文件。两平台其余变化均为安装记录。未发现非空运行时文件变化。

## ZIP 体积

单位是十进制 MB。各部件使用 ZIP 条目的压缩字节数，目录表和 ZIP 头单列。Linux Python 包含其发行包自带的标准库、共享库和工具。Windows Python 项口径相同。共用文件含源码、资源、启动器和发行元数据。

| 部件 | 350.7 MB 原包 | 同源旧打包器 | 同源锁定版 |
| --- | ---: | ---: | ---: |
| Windows Python | 10.051 | 10.051 | 10.051 |
| Windows NumPy | 10.471 | 10.471 | 10.471 |
| Windows Pillow | 7.081 | 7.081 | 7.081 |
| Windows SciPy | 31.676 | 31.676 | 31.676 |
| Windows OpenCV headless | 43.820 | 43.820 | 43.820 |
| Linux Python | 116.555 | 116.555 | 116.555 |
| Linux NumPy | 14.724 | 14.724 | 14.723 |
| Linux Pillow | 6.917 | 6.917 | 6.917 |
| Linux SciPy | 30.395 | 30.395 | 30.394 |
| Linux OpenCV headless | 61.127 | 61.127 | 61.126 |
| 共用源码和资源 | 16.697 | 16.718 | 16.720 |
| ZIP 目录表与文件头 | 1.169 | 1.171 | 1.169 |
| 合计 | **350.684** | **350.707** | **350.706** |

在 350.7 MB 原包中，仅 Linux 的 `libpython3.13.so.1.0` 和 `python3.13` 就占 105.181 MB 压缩空间。两端 OpenCV headless 合计 104.947 MB。本轮沿用已验过的裁剪范围及原有 Windows OpenCV 类型标注。真实光驱、读盘和刻录未测。

## 续轮：使用官方 stripped Linux Python，并合入卡 AB

- `45c6e5e` 将 Linux 便携运行时锁定为 Astral 20260610 的 CPython 3.13.14 `x86_64-unknown-linux-gnu`、`install_only_stripped` 归档。版本、目标和依赖 wheel 沿用上一轮。构建沿用原有裁剪规则，校验后才解包。
- `9ab455b` 用 `git merge --no-ff dev/1.0.0` 合入 `c4c7ebe`。包含卡 AB、作品列表修复、离线排错搜索与 `webui --gui` 校验。三个冲突均为测试文件。GUI 校验和端口回退用例采用上游实现，LAN 模式用例沿用原有隔离桩。wheel 内容测试新增对 `discprobe/data/troubleshoot.json` 的逐字节检查。
- `efb011a` 修正合并后失效的排错出处及安装文档锚点，使出处刷新工具能处理重复引用。校准容量用例用模拟介质通过现行身份验证，并校验写入子进程收到的介质身份。

### 归档与负向验收

归档 `cpython-3.13.14+20260610-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz` 大小为 34,931,836 字节。官方 `SHA256SUMS` 对应行、GitHub 发布 API 资产摘要、本机实算和锁定值均为 `d607e18e83227a0527cf3f54a48be973a75358a6885e4be67d4b0359b6f1c880`。`SHA256SUMS` 文件本身与发布 API 记录同为 `698c0a756445f998fe752d220391ef87f8e207aea16dfa329a4bf6f65acd899e`。[官方发布资产](https://github.com/astral-sh/python-build-standalone/releases/expanded_assets/20260610) · [官方 SHA256SUMS](https://github.com/astral-sh/python-build-standalone/releases/download/20260610/SHA256SUMS)

两个官方运行时归档中检查的 4,514 个路径相同。核对 `python3.13` 与 `libpython3.13.so.1.0` 的 ELF 节表时，移除项为调试节和关联的重定位节。[归档对照日志](../../evidence/pack-inputs-pinned/stripped/elf-sections.log)

`tests/test_pack_inputs.py` 八项负向全部通过，包括 stripped 归档字节改动、将锁定资产名改回未剥离版本以及缺少 stripped 归档。失败命令均报告受影响文件，退出码非零且未生成 ZIP。合并相关定向测试为 146 通过、1 跳过、8 个子测试通过。两项合并问题修复后，排错、校准、介质身份及打包定向复验为 104 通过。刷新工具的 `--check` 通过，排错测试覆盖 389 处引用。

### 发布彩排与三机验收

首轮彩排在 Windows pytest 阶段发现两个失败，分别为校准容量的模拟盘缺少身份，以及排错语料引用了上游版文档位置。修复后从 `efb011a` 重跑。

```powershell
$env:TEMP = 'F:/dp-dev-tmp/linuxpack'
$env:TMP = $env:TEMP
python -X utf8 -B tools/release.py --version 1.0.0.0-alpha --out F:/dp-dev-tmp/linuxpack/rehearsal-stripped-final --cache F:/dp-dev-tmp/linuxpack/pinned-cache
```

最终彩排 68/68 项通过。pytest 为 `1235 passed, 2 skipped, 196 subtests passed`，55/55 个 MJS 和 1/1 个 CJS 通过，Disc Lab 为 `153 passed, 2 skipped`。Disc Neo 本轮跳过。发布目录中 7 项 SHA-256 全部重算一致。[彩排状态](../../evidence/pack-inputs-pinned/stripped/release-status.json)

完整包的 Windows 和 Linux 共用同一份 `discprobe/data/troubleshoot.json`，它与发行 wheel 中的副本及仓库原文件逐字节一致，SHA-256 为 `99c9bc161b3a757763dd72f5fd4102aed66c8a580d6ff8babf9501900f7bae1d`。安装后的 wheel、本机 Windows 解压件及两台 Ubuntu 主机均以各自的解释器查询 *This disc cannot be erased: only rewritable discs*，首位命中 `burn-erase-media`。[已安装 wheel 验证](../../evidence/pack-inputs-pinned/stripped/installed-wheel-help.log)

| 主机 | 系统与解压方式 | 实测结果 | 日志 |
| --- | --- | --- | --- |
| x79 | Ubuntu 24.04.4 LTS，BusyBox unzip | Bash 启动、包内自检、WebUI status/stop 通过 | [运行](../../evidence/pack-inputs-pinned/stripped/x79/verify.log) · [清理](../../evidence/pack-inputs-pinned/stripped/x79/cleanup.log) |
| agentbox | Ubuntu 26.04 LTS，系统 unzip | Bash 启动、包内自检、WebUI status/stop 通过 | [运行](../../evidence/pack-inputs-pinned/stripped/agentbox/verify.log) · [清理](../../evidence/pack-inputs-pinned/stripped/agentbox/cleanup.log) |
| 本机 | Windows，解压路径含 `中文 空格` | BAT 帮助及 `python/python.exe -m discprobe selftest` 通过 | [运行](../../evidence/pack-inputs-pinned/stripped/windows.log) |

两台 Ubuntu 主机均核对 ZIP SHA-256，解压后保留启动脚本的 0755 权限。通过 `bash start-linux.sh --local-only --no-drives --port 0` 启动，大厅和版本接口均返回 200，停止后状态显示服务未运行，监听端口关闭。远端上传件和解压目录均已清理，日志保留。真实光驱、读盘及刻录未测。

### 完整 ZIP 体积

完整 ZIP 为 **267.953 MB**（267,953,316 字节），比上一轮减少 **82.753 MB**（23.6%）。SHA-256 为 `4a3b5741d6235eb29d6efe0ed5da7f0f2330b39946e05a9828d49c32003d2f21`。产物位于 `F:/dp-dev-tmp/linuxpack/rehearsal-stripped-final/assets`。[精确压缩字节数和 SHA-256](../../evidence/pack-inputs-pinned/stripped/comparison.json)

单位为十进制 MB。各部件按 ZIP 条目的压缩字节计，ZIP 文件头和目录表单列。两列使用各轮实际发布彩排 ZIP。共用源码和资源包含本轮合并的新增文件。

| 部件 | 上轮锁定版 | 本轮 stripped 版 |
| --- | ---: | ---: |
| Windows Python | 10.051 | 10.051 |
| Windows NumPy | 10.471 | 10.471 |
| Windows Pillow | 7.081 | 7.081 |
| Windows SciPy | 31.676 | 31.676 |
| Windows OpenCV headless | 43.820 | 43.820 |
| Linux Python | 116.555 | 33.743 |
| Linux NumPy | 14.723 | 14.723 |
| Linux Pillow | 6.917 | 6.917 |
| Linux SciPy | 30.394 | 30.394 |
| Linux OpenCV headless | 61.126 | 61.126 |
| 共用源码和资源 | 16.720 | 16.779 |
| ZIP 目录表与文件头 | 1.169 | 1.170 |
| 合计 | **350.706** | **267.953** |

ZIP 中的 `python3.13` 和 `libpython3.13.so.1.0` 两项合计由 105.181 MB 降至 22.551 MB，归档内保留的 Linux Python 运行时文件路径与上轮相同。

## 11-19 补充：Windows、Linux 和双平台包

- `adf274b` 用 `git merge --no-ff dev/1.0.0` 合入 `c2f2033`，包含 R2–R9、issue #49 的说明和排错出处刷新。排错语料冲突先取 dev 的版本，再用 `python tools/refresh_troubleshoot_citations.py` 和本分支现有安装说明校正引用。合并的定向测试为 80 通过、1 跳过。
- `6a35a3e` 从同一份打包暂存树生成三个 ZIP。Windows 和 Linux 各安装一次已校验的依赖，各变体只取所需运行时和启动器。单平台首读文件只给出本平台的启动命令，并列出另外两种包。
- `0314cd5` 让合入前已有的光盘镜像用例适配 R2–R9。模拟写入器生成可登记的测试镜像，刻录日志用例使用带自检记录的测试镜像，随机镜像用例校验陈旧边车清理。
- `dd30917` 给 pytest 用例独立用户状态目录，隔离两个 worker 上使用同一虚拟 `X:` 的用例。
- `0d3fa1e` 从 Linux 单平台包排除 Linux 标准库随附的两个仅供 Windows 使用的批处理辅助文件 `ctypes/macholib/fetch_macholib.bat` 和 `idlelib/idle.bat`。完整包保留两个文件，Linux 单平台包的其余运行时文件仍复用原暂存树。
- `76f6a30` 让浏览器测试等盘库可操作后确认实际选中项，再点击下一步。无界面业务代码改动，定向复跑三次均通过。
- 沿用 CPython 3.13.14（Windows embed、Linux 官方 stripped 归档）和上一轮的八个 wheel。本轮复算十个缓存原件的 SHA-256，均匹配原锁定文件。没有新增下载，也没有改变已有的裁剪规则。

### 下载选择与大小

单位为十进制 MB。完整 ZIP 仍可在两个平台上运行。源码树文档显示约数，包内中英文 README、INSTALL-linux.md 和单独发布的安装指南写入本次实际包名和大小（MB 保留三位小数）。三份包内 `release-build.json`、发布 `manifest.json` 及 `SHA256SUMS.txt` 注释记录精确字节数，发布说明模板为三个大小分别留槽。

| ZIP | 大小（MB） | 字节 | 选择 |
| --- | ---: | ---: | --- |
| disc-probe-1.0.0.0-alpha-win64.zip | 120.494 | 120,493,842 | 只用 Windows |
| disc-probe-1.0.0.0-alpha-linux-x86_64.zip | 164.687 | 164,687,278 | 只用 Linux |
| disc-probe-1.0.0.0-alpha-full.zip | 268.079 | 268,078,728 | 两个平台都用，或不确定 |

产物位于 `F:/dp-dev-tmp/linuxpack/rehearsal-platforms/assets`。[字节数及 SHA-256](../../evidence/pack-inputs-pinned/platform-variants/comparison.json)

### 校验、同源对照和平台验收

输入负向测试八项全部通过，覆盖原始文件单字节改动、版本或平台标签错误、文件缺失以及将 stripped 资产名退回旧变体。每项均报告受影响输入、以非零退出，并清掉模拟的旧 ZIP 和摘要文件。发行编排也验证缺任一单平台包时不生成通过验收的 assets 目录。最新打包及引用定向检查为 83 项通过。

首轮彩排在 pytest 停止，共有八个旧镜像用例失败，无便携 ZIP 产出。更新测试夹具后，R2–R9 相关定向复验为 123 项通过。第二轮两个模拟驱动用例争用同一把虚拟盘锁。隔离用户状态后定向复验 142 项通过。含标准库批处理排除的最终定向复验 77 项通过。

前两轮原始日志分别保存在 `F:/dp-dev-tmp/linuxpack/rehearsal-platforms-first-failure/logs/pytest.log` 和 `F:/dp-dev-tmp/linuxpack/rehearsal-platforms-second-failure/logs/pytest.log`。确认 BAT 清单后主动重启了一次预检，其临时目录清理被自动审查拦截，现场留在 `F:/dp-dev-tmp/linuxpack/rehearsal-platforms-restarted-preflight`。后续一轮 pytest 通过，盘库选择浏览器用例偶发失败，原始日志见 `F:/dp-dev-tmp/linuxpack/rehearsal-platforms-browser-failure/logs/test_review_library_newwork.mjs.log`。

```powershell
$env:TEMP = 'F:/dp-dev-tmp/linuxpack'
$env:TMP = $env:TEMP
python -X utf8 -B tools/release.py --version 1.0.0.0-alpha --out F:/dp-dev-tmp/linuxpack/rehearsal-platforms --cache F:/dp-dev-tmp/linuxpack/pinned-cache
```

构建快照为 `76f6a30`。彩排 68/68 项通过，pytest 为 `1272 passed, 2 skipped, 196 subtests passed`，55 个 MJS 和 1 个 CJS 全部通过，Disc Lab 为 `153 passed, 2 skipped`。Disc Neo 本轮跳过。发布目录中的 9 项 SHA-256 均已复算一致。[彩排状态](../../evidence/pack-inputs-pinned/platform-variants/release-status.json)

用上一轮 `f4e7f43` 的旧打包器从同一份冻结源码重建对照 full。三个交付 ZIP、旧打包器对照 ZIP 和冻结源码的 **607 个 `discprobe/` 文件逐字节一致**。发行 wheel 中的排错语料也与三个 ZIP 相同。新 full 与各自单平台包中的 Windows 1,327 个运行时文件和 Linux 2,542 个共有运行时文件均逐字节一致。各平台依赖版本与对照包一致。旧包到新包的运行时变化仅涉及 2 项安装记录（RECORD）。两个 NumPy RECORD 仅有未随包分发的 f2py.exe 和 numpy-config.exe 记录的哈希不同。[同源对照记录](../../evidence/pack-inputs-pinned/platform-variants/comparison.json) · [旧打包器日志](../../evidence/pack-inputs-pinned/platform-variants/legacy-build.log) · [已安装 wheel 查询日志](../../evidence/pack-inputs-pinned/platform-variants/installed-wheel-help.log)

| 包 | 本机 Windows | x79（Ubuntu 24.04） | agentbox（Ubuntu 26.04） |
| --- | --- | --- | --- |
| win64 | [通过](../../evidence/pack-inputs-pinned/platform-variants/win64/windows/verify-summary.log) | — | — |
| linux-x86_64 | — | [通过](../../evidence/pack-inputs-pinned/platform-variants/linux-x86_64/x79/verify-summary.log) | [通过](../../evidence/pack-inputs-pinned/platform-variants/linux-x86_64/agentbox/verify-summary.log) |
| full | [通过](../../evidence/pack-inputs-pinned/platform-variants/full/windows/verify-summary.log) | [通过](../../evidence/pack-inputs-pinned/platform-variants/full/x79/verify-summary.log) | [通过](../../evidence/pack-inputs-pinned/platform-variants/full/agentbox/verify-summary.log) |

Windows 在 `中文 空格` 路径解压。两个 ZIP 的 BAT 帮助、包内 Python 和 headless OpenCV 校验、排错查询和 selftest 均通过。两台 Ubuntu 对两个 Linux 可用的 ZIP 分别复算发布摘要、解压并核对 0755 权限，以 `bash start-linux.sh --local-only --no-drives --port 0` 启动。包内 selftest 通过，大厅和版本接口返回 200。`webui status` 命中本次服务，`webui stop` 后状态显示服务已关闭，监听端口已释放。两台机器均清理了上传件和解压目录。完整原始日志位于 `F:/dp-dev-tmp/linuxpack/platform-verification`。实际光驱读盘和刻录未测。
