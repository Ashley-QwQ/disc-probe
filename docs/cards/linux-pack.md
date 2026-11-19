# Linux 与 Windows 完整包

工作树 `D:/dp-dev/linuxpack`，分支 `dev/linux-pack`，基点 `699ff86`（接卡时 `dev/1.0.0` 的 HEAD）。

## 提交

- `234e10d` 将两个平台的便携 Python 放入 `full.zip`，锁定依赖与下载摘要，切换至 headless OpenCV，更新入口、安装说明和发布清单。
- `f984535` 将发布测试的照片搜索限制在快照内的允许路径，并在传输前检查完整 ZIP 的路径及入口类型。
- `10735fb` 给 Linux 验证器单独设立不含空格的临时目录，保留带空格的解压路径。
- `024bc28` 用 LF 写发布摘要文件，并增加换行检查。
- 本报告提交记录完整 ZIP 的验收、OpenCV 对照和两台 Linux 的日志。

临时 `start-linux.sh` 先进入脚本所在目录，再用包内 Python 启动 `tools/launch_web.py`。合并时以 web-polish 的为准。同包包含 `开始 Start (Windows).bat` 和 `先看我 Read me first.txt`。

## 产物与下载校验

`disc-probe-1.0.0.0-alpha-full.zip` 为 **350.7 MB**（350,683,995 字节，334.4 MiB），比卡上约 280 MB 的估算多 70.7 MB。压缩数据中 Windows 运行时占 103.1 MB，Linux 运行时占 229.7 MB，共用文件占 16.7 MB。本次保留指定的 `install_only` 版 Python 共享库和标准库。

SHA-256 为 `d970b4a4b86cc5871a529119ab58a5f0c675035fb09a39bd439f6255873c20ca`。成品位于 `F:/dp-dev-tmp/linuxpack/rehearsal/assets/`。

Windows 和 Linux 均带 CPython 3.13.14、NumPy 2.5.1、Pillow 12.3.0、SciPy 1.18.1 和 opencv-python-headless 5.0.0.93。Linux wheel 的平台标签要求 glibc 2.28 或更新，实际运行覆盖下列两版 Ubuntu。版本和依赖列在发布资产的 `manifest.json`、`SHA256SUMS.txt`，以及完整 ZIP 内的 `release-build.json`。Linux 裁剪记录在 `linuxpack-keep-list.json`。Python 的两个短命令名指向同一份解释器，ZIP 采用普通文件入口，开包时无需重建符号链接。

以下下载的 SHA-256 均与对应官方发布的摘要一致。Astral 摘要来自发行资产元数据，wheel 摘要来自 PyPI 对应版本的 JSON。[Astral CPython 发布](https://github.com/astral-sh/python-build-standalone/releases/tag/20260610) · [NumPy](https://pypi.org/project/numpy/2.5.1/) · [Pillow](https://pypi.org/project/Pillow/12.3.0/) · [SciPy](https://pypi.org/project/scipy/1.18.1/) · [OpenCV GUI](https://pypi.org/project/opencv-python/5.0.0.93/) · [OpenCV headless](https://pypi.org/project/opencv-python-headless/5.0.0.93/)

| 下载文件 | SHA-256 |
| --- | --- |
| `cpython-3.13.14+20260610-x86_64-unknown-linux-gnu-install_only.tar.gz` | `31ebbb024fecb446d7f25a5b59ca1d4955597ca3f5b4b76f55b30a8987eb61c9` |
| `numpy-2.5.1-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `9726558e8db4a5bf7929a70ae50f63abda4daf0efe810e3bfbab95976f75fc1a` |
| `pillow-12.3.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `0847a763afefb695bc912d7c131e7e0632d4edc1d8698f58ddabec8e46b8b6d3` |
| `scipy-1.18.1-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `fdaf5ea890a6183d0565f51a61799d67081bd5b1cf03c5f4b3fd3732108625c9` |
| `opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl` | `ed709fdf9aa0bd1f2ed8549e71d19449b03a675bb581eb292285f6861953be37` |
| `opencv_python_headless-5.0.0.93-cp37-abi3-win_amd64.whl` | `829717b6a95554f273e49e357cee3b3a2a26b6f4842fbc1bed2b45bdd8f87e0e` |
| `opencv_python-5.0.0.93-cp37-abi3-win_amd64.whl`（对照组） | `f90ba04b8f73bc5c3814037699739f0156f597338a98f05956c684e7c3ca10d2` |

卡上给的 `C:/disc-probe-scratch/gui-handshake/winpack-cache` 在本机不存在，实际只读使用 `D:/disc-probe-dist/cache` 的 Windows embed 和原 NumPy、Pillow、SciPy 三项依赖。Windows embed 来自该现有缓存，实算 SHA-256 为 `90b4e5b9898b72d744650524bff92377c367f44bd5fbd09e3148656c080ad907`。本轮下载缓存及彩排产物位于 `F:/dp-dev-tmp/linuxpack/`。

## OpenCV 对照

Windows 分别从隔离目录导入同号的 GUI 和 headless wheel，其余依赖相同。**23/23 个有输出的配对用例逐字节一致**，共 61 个输出文件，其中 23 个 JSON、11 个 CSV、11 个 NPY、16 个 JPEG 或 PNG。原始字节相同，无需剥离时间戳。合成 beacon 工具的 stdout 也逐字节相同。输入和输出 SHA-256、分类结果及失败原因见 [regression.json](../../evidence/linux-pack/regression.json)。原始执行日志在 `F:/dp-dev-tmp/linuxpack/regression/`。

- `photo` / `pcal` 用 10 张原片 `IMG_7910` 至 `IMG_7919`，连同读数、透视展开 NPY 和叠图一起比较。5 张得到单张暂定值，另外 5 张各保留原有拒判。配对执行的 `gridscan` 用同一实扫结果引用的三张网格原图，`ringscan` 用灰阶盘原始扫描。
- Beacon 比较 `tools/beacon_overlay.py` 在 colour4 原片 `IMG_7099` 上生成的 JSON 和 JPEG。两边都读取 9/27 块。另比较了桌面标志轮廓、已有 focal 标尺记录的 18 块预测结果，以及 Disc Lab 渲染和姿态夹具。
- 两张色块原片按已有结果的单应矩阵重读像素和编号，完整姿态重拟合未完成。`tilescan` 另在灰阶盘实扫上做了零编号的冒烟检查。原色块平板扫描及匹配 `scan`、`calscan` 的实扫未找到。两次不匹配实扫在换包前后均拒绝，无输出，未计入 23 个一致用例。仓库自检中的 `scan` 和 `calscan` 合成夹具各有一份完整输出对照，两者均逐字节相同。
- `rg` 核对的产品直接调用位于 `pcal.py`、Disc Lab 的 `photos.py` 与 `poses.py`、以及 `penrose_shape.py`。封存研究脚本 `photo_l_majority_check.py` 及 `evidence/` 下 mix1、dense-bridged 的旧脚本整套重放未测。

## 完整彩排与整包验收

```powershell
$env:TEMP = 'F:/dp-dev-tmp/linuxpack'
$env:TMP = $env:TEMP
$env:DISC_PROBE_WINPACK_CACHE = 'D:/disc-probe-dist/cache'
python -X utf8 -B tools/release.py --version 1.0.0.0-alpha --out F:/dp-dev-tmp/linuxpack/rehearsal --cache F:/dp-dev-tmp/linuxpack/cache
```

- [status.json](../../evidence/linux-pack/release-status.json) 为 `PASS`，67/67 条命令退出码为 0。主 pytest 使用 `-n 2`，1174 通过、2 跳过、182 个子测试通过。55/55 个 `test_*.mjs` 与 1/1 个 `test_*.cjs` 均通过。源码、安装后的 wheel、Windows 裁剪前和裁剪后完整包的自检均通过。Disc Lab 153 通过、2 跳过，Disc Neo 未启用。
- 彩排构建快照为 `f984535`。后续修正验证器的临时目录，并将彩排的 `SHA256SUMS.txt` 转为 LF。完整 ZIP、manifest 和其他发布资产字节未变，`sha256sum -c SHA256SUMS.txt` 7/7 通过。换行修正另跑 `tests/test_release_packaging.py`，61 通过。
- Windows 在带中文和空格的路径解压完整 ZIP，运行 `开始 Start (Windows).bat --help` 后检查包内 Python、依赖版本以及 OpenCV 的 GUI 配置。见 [Windows 启动](../../evidence/linux-pack/windows-launch-help.log) 和 [Windows 运行时](../../evidence/linux-pack/windows-runtime.json)。

Linux 对同一个完整 ZIP 执行 `python -X utf8 -B tools/verify_linux.py --host <x79|agentbox> --zip <full.zip> --out <F 盘日志目录>`。

| 主机 | 系统 | 解压工具 | 解压后启动器及 Python 命令权限 | 结果 | 日志 |
| --- | --- | --- | --- | --- | --- |
| x79 | Ubuntu 24.04.4 LTS | BusyBox `unzip` | 0755 | PASS | [运行](../../evidence/linux-pack/x79/verify.log) · [清理](../../evidence/linux-pack/x79/cleanup.log) |
| agentbox | Ubuntu 26.04 LTS | 系统 `unzip` | 0755 | PASS | [运行](../../evidence/linux-pack/agentbox/verify.log) · [清理](../../evidence/linux-pack/agentbox/cleanup.log) |

两台主机接收整个 ZIP，校对 SHA-256，从另一个目录运行 `bash start-linux.sh --help`，再用包内 Python 导入依赖并运行 `-m discprobe selftest`。用包内 Python 启动 `webui --local-only --port 0`，大厅和 `/api/version` 均返回 200。该版本的 `webui status` 和 `webui stop` 均返回参数错误。用 SIGINT 停止前台服务时，进程以 0 退出，监听端口已关闭。两台主机均已删除上传包和解压目录，保留日志。

首轮两台均未通过 Bash 补全自检。自检脚本未给临时文件路径加引号，`TMPDIR` 含空格时会触发失败。验证器改用单独的临时目录后，对同一 SHA-256 的 ZIP 复验。解压路径仍带空格。首轮日志见 [x79](../../evidence/linux-pack/x79/initial-verify.log) 和 [agentbox](../../evidence/linux-pack/agentbox/initial-verify.log)。

Linux 两台验收机无光驱。真实读盘、刻录和网页发起刻录均未测。本轮没有推送、合并、切换分支、连接光驱或刻盘。

本地临时构建目录 `F:/dp-dev-tmp/linuxpack/runtime-smoke` 的递归删除被工具的自动审查拦截，目录仍在 F 盘。此目录是单独的 Linux 运行时构建检查。
