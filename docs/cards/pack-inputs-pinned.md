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
