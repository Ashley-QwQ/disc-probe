# 1.0.0-alpha 打包演练报告

本次 **不能放行 A9**。Windows 便携包已完成解包、自检、真实照片读取和启动入口检查；当前修正后的 wheel 被一个产品 selftest 用例阻塞，Linux 离线依赖尚不齐，桌面视觉走查也未完成。所有状态和哈希记录在 `C:/disc-probe-scratch/release-pack/verify.json`。

工作分支为 `core/release-pack-20261112`，起点 `3938acf`。完整构建第 05 轮来自 `7c6be6884409393b754f7fb3466b36f65b4245b6`；最新候选及发布工具来自 `bbaee380a5e28ea04a9899718399708c446020f6`。两批结果分开保存，不能混成“同一冻结提交全部通过”。没有修改 `discprobe/` 产品代码；工作树版本仍为 `0.1.2.1`，只有构建副本写入 `1.0.0-alpha`。pip 元数据及文件名按 PEP 440 使用 `1.0.0a0`。

## 发布命令

在 Windows Python 3.13 上执行，输出目录必须不存在或为空：

```powershell
python -B tools/release.py --version 1.0.0-alpha --out C:/disc-probe-scratch/release-pack/release-day-20261120 --cache C:/disc-probe-scratch/gui-handshake/winpack-cache
```

也可用 `DISC_PROBE_WINPACK_CACHE` 指定缓存。缓存需要 `python-3.13.14-embed-amd64.zip` 和四个依赖的 `site-packages/`；本次没有下载依赖。实际环境为 Python 3.13.14、Node 26.7.0、pytest 9.1.1，NumPy 2.5.1、Pillow 12.3.0、SciPy 1.18.1、OpenCV 5.0.0.93。

命令先检查 Git 干净状态，再从提交导出副本、设置副本版本、构建私有候选并离线安装 wheel，验证 CLI、HTTP、设计保存重开和 selftest。候选源码包重建的 wheel 还要逐条目比较。随后运行完整 pytest、26 个 Node 入口、源码 selftest，以及 Windows 裁剪前后的包内 selftest。所有门槛通过后，才写最终 `assets/`、`manifest.json` 和 `SHA256SUMS.txt`；已验证候选 wheel 的原始字节直接复制到资产目录。日志和私有构建目录保留。

manifest 包含完整提交、公开及规范版本、GUI 版本、Python/Node 和依赖版本、文件尺寸及 SHA-256、检查日志哈希、嵌入 Python 哈希和资源设置。默认图像 worker 与数学线程数均为 1；selftest 内置的双 worker 一致性用例顺序执行。`source_archive_sha256` 指原始 Git 导出输入，发行文件的哈希见 `assets` 清单。

已实测最新命令拒绝未跟踪改动，且不创建输出目录；最新 wheel 门槛退出 1 后，第 06 轮没有生成最终 `assets/`。这两个门槛没有绕过。原渲染回归需要本机已有的 `v0.1.2.1` 历史对象，命令不会联网获取它。

## 实际资产和哈希

第 05 轮完整资产位于 `C:/disc-probe-scratch/release-pack/rehearsal-05/assets/`。其构建门槛全部通过，校验和已逐一复核。后续独立 wheel 自检发现缺项，因此这组文件仅保留为演练证据，**不能直接作为最终发行集合**；其中旧 wheel／sdist 应由下面的修正候选替代。core ZIP 仅完成构建，未单独运行。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `disc-probe-1.0.0-alpha-core.zip` | 9,261,298 | `cea3ca4a1390187c63199ab3cc653416cbc6f8104ad650ab8efb4f9a070b6c75` |
| `disc-probe-1.0.0-alpha-full-win64.zip` | 112,867,006 | `1786555c77d6b6923dfbb08fe8c0075aa89b40bf551716d261ded233aeb0a320` |
| `disc_probe-1.0.0a0-py3-none-any.whl` | 9,162,229 | `ded1deef98a1bc3ee940abd6403794b460e2d200ac6ee5a63b3bdd43f3f19748` |
| `disc_probe-1.0.0a0.tar.gz` | 9,060,978 | `1ddfd68006a261d60dae7a3873d934c27b6154ff0577bae40ea303b5b0604576` |
| `INSTALL-linux.md` | 2,406 | `4f23b32350de88150c66ee8d896162fc9e91620f9744295e7c4f5bd478107c31` |
| `manifest.json` | 14,501 | `8aeed2225aab19ca0df92c3b827be209be5337bb49df3c23e755d1378f3a135a` |
| `SHA256SUMS.txt` | 565 | `ab38c3ab93a49adacaf2f1c26b5cb6073d58299c2b2c741047345a6096258c26` |

第 06 轮修正源码候选位于 `C:/disc-probe-scratch/release-pack/rehearsal-06/candidate-assets/`，状态为 BLOCKED，没有正式 manifest 或放行校验和。候选 wheel 的 568 个条目与从 sdist 离线重建的 wheel 逐字节一致，比较不要求 ZIP 时间戳相同。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `disc_probe-1.0.0a0-py3-none-any.whl` | 9,346,715 | `245aef238c467f1880bb06c0d47f9d56f9e7042dba9c9c806369aed839f28b80` |
| `disc_probe-1.0.0a0.tar.gz` | 9,062,105 | `80e7c6175c607ad71df21e7414d54f60bd25d5e79df6a7309d47409964ecc9bd` |

## 验证结果

**Windows 便携包，第 05 轮提交。** ZIP 解压到 `C:/disc-probe-scratch/release-pack/中文 空格/disc-probe-1.0.0-alpha-full-win64/`。由其中嵌入 Python 启动本地服务，`/api/version`、`/home/`、`/home/design/editor-ui.mjs`、`/api/state` 均返回 200；CLI 与 HTTP 版本一致。空设备提供器下保存并重开 6000×6000 设计成功。包内直接 selftest 输出 `all checks passed`。298 个 GUI 文件与构建副本逐字节相同，字体、模板代码与色板、模拟 LUT、纹理数据、工具及记录 CSV 均在包内。

真实输入为 `D:/disc-probe/photos/grid_darkfield_IMG_6903.jpeg`，SHA-256 `cf757cf9c0ec1e91d9e217c60210f000064877a585c355505703a2f16d332080`。读取耗时 28.831 秒；pcal、OpenCV、SciPy、NumPy、Pillow 的实际加载位置均记录在包路径内。读取器返回 **`unstable_L`**：依赖及读取流程执行成功，但照片校准未通过，没有据此写入任何修正预设。

启动器使用 `.bat` 的 Windows `ShellExecuteW open` 入口（与资源管理器双击相同的激活入口），带 `--local-only --no-drives`。确认启动包内 Python、打开 web 服务并返回大厅 200，未停在菜单提示符。默认启动器代码直接调用 `launch_web.py` 并请求系统浏览器打开大厅。桌面原生接口重试／重置后仍报 native pipe unavailable，浏览器接口报 access host unavailable，因此没有取得真实浏览器视觉证据或完成鼠标双击走查；此项为 NOT_RUN。自检服务和启动器自有进程均已停止。

**Windows 安装版，第 06 轮提交。** 全新 `rehearsal-06/wheel-venv/` 不启用系统 site-packages；依赖从离线缓存复制，wheel 用 `pip install --no-index --no-deps` 安装，`pip check` 通过。`disc-probe --help`、`version --json`、四个 HTTP 路由及无设备设计保存重开通过，实际模块位于该 venv。selftest 退出 1，仅一个用例失败，见下面阻塞。

第 05 轮源码门槛为 **546 passed、1 skipped、182 subtests passed**（1423.11 秒），Node **26/26**，源码及 Windows 裁剪前后 selftest 均通过。最新第 06 轮在候选 wheel 验证处正确停止，未运行该轮后续 pytest／Node／便携 ZIP 构建。当前包装改动的定向检查为 12 passed、8 subtests passed。早期一次浏览器退出清理失败、一次 Edge 30 秒超时以及中止批次的日志均保留；第 05 轮完整 Node 重跑已通过。

**Linux x79，第 06 轮 wheel。** Linux x86_64、glibc 2.39、Python 3.12.3。文件在 `~/dp-release-check/a9-1794534619286801700`，进程 nice 19，CPU affinity 14、15；临时文件和 pip 缓存也放在该目录下。初期根分区满，后恢复约 38 GiB 可用空间。系统没有 ensurepip，已用 `venv --without-pip` 创建全新隔离环境，旧 `~/dp-venv` 的 pip 仅通过 `--python` 向新环境安装；没有复用旧环境的 NumPy 等包。

已复制候选 wheel 和 NumPy 2.2.6 的 Linux CPython 3.12 wheel，并在远端核对哈希。现有 NumPy wheel 为 16,527,618 字节，SHA-256 `fd83c01228a688733f1ded5201c678f0c53ecc1006ffbc404db9f7a899ac6249`。离线解析接受候选和 NumPy，随后因找不到 `Pillow>=10` 停止；当前 wheelhouse 也没有匹配的 SciPy、OpenCV wheel。因此 Linux CLI、版本、HTTP 和 selftest 均为 **NOT_RUN**。`agentbox` 两次 SSH 连接超时。没有访问光驱或修改搜索 worker。

## 尚未解决的阻塞

1. **产品 selftest：`discprobe/selftest.py:757–780`。** `_incomplete_folder` 把三个文件复制到没有 `__init__.py` 的临时目录，期望子进程返回 1 和“incomplete”。在正常安装的 venv 中，Python 实际导入已安装的完整常规包，`--help` 返回 0，故该断言失败。已单独复现并记录实际导入路径、stdout、stderr 和退出码，见 `installed-selftest-blocker.json`。其余安装版自检项均通过。需要产品方修正该用例对安装环境的假设；本任务未修改产品、未删除该用例，也未改用隔离参数使它跳过。
2. **Linux 离线依赖。** 需要适用于 Linux x86_64／CPython 3.12 的 Pillow、SciPy、OpenCV wheel；在已检查的缓存未找到。提供齐全依赖后，才能继续实际安装和运行验收。
3. **真实桌面走查。** 恢复桌面／浏览器观察接口，或由人双击完整包启动器确认大厅、无设备提示及设计入口。HTTP 和 ShellExecute 检查不能代替视觉验收。

产品边界也须保留：Windows 内置 CD DAO 尚未实现，后端会拒绝；内置 `burn` 接受 DVD／CD，BD 镜像走外部刻录步骤。本次没有测量或刻录光盘。Linux 需要系统 Python、匹配的依赖 wheel，以及按介质使用的 `growisofs`、`dvd+rw-mediainfo`、`cdrdao` 和 `wodim`；`INSTALL-linux.md` 说明了 `/dev/sr*` 与 `cdrom` 组权限。

## 发布日的具体步骤

1. 产品方先解决安装版 selftest 阻塞；准备齐全 Linux 离线依赖，恢复桌面走查条件。整合方给出约 2026-11-20 的准确冻结提交，须包含本分支全部包装修复及产品修复。确认本地历史对象、Python 3.13、Node、pytest 和缓存齐备。
2. 在该冻结提交上执行 `git status --porcelain`（必须无输出）和 `git rev-parse HEAD`，记录准确 SHA。使用上面的唯一发布命令，选择新的空输出目录。任何非零退出都停止，查看 `status.json` 和日志；不要从中间目录取文件冒充完成资产。
3. 成功后复核 `manifest.json` 的提交、公开版本、依赖及文件尺寸，逐行重新计算 `SHA256SUMS.txt`。核对 `wheel-proof/proof.json` 为 PASS，且其 wheel 哈希与最终资产相同。工作树 `discprobe/version.py` 应仍未被改写。
4. 从新 ZIP 解压到新的中文空格路径，再运行包内验证器，使用保存的真实照片。例如：

```powershell
$assetsDir = 'C:/disc-probe-scratch/release-pack/release-day-20261120/assets'
$extractDir = 'C:/disc-probe-scratch/release-pack/发布日 中文路径'
Expand-Archive -LiteralPath "$assetsDir/disc-probe-1.0.0-alpha-full-win64.zip" -DestinationPath $extractDir
$packDir = "$extractDir/disc-probe-1.0.0-alpha-full-win64"
& "$packDir/python/python.exe" -X utf8 -B "$packDir/tools/verify_package.py" --artifact "$assetsDir/disc-probe-1.0.0-alpha-full-win64.zip" --expected-root $packDir --out C:/disc-probe-scratch/release-pack/day-windows --photo D:/disc-probe/photos/grid_darkfield_IMG_6903.jpeg
```

5. 对齐 Linux 依赖架构、ABI 和版本并记录其哈希，运行 SSH 验证器。它只在 `~/dp-release-check/` 建新环境，使用最多两个 CPU，不会使用搜索 worker 环境：

```powershell
python -B tools/verify_linux.py --host x79 --wheel C:/disc-probe-scratch/release-pack/release-day-20261120/assets/disc_probe-1.0.0a0-py3-none-any.whl --wheelhouse C:/disc-probe-scratch/release-pack/linux-wheelhouse --out C:/disc-probe-scratch/release-pack/day-linux
```

6. 完成真实桌面启动与无设备走查，将各平台 proof、完整提交、实际依赖和最终包哈希写入新的 `verify.json`。所有要求的状态均通过后，才可讨论 A9 放行。本命令不创建标签、不推送、不发布；这些动作也没有在本次演练中执行。

原始证据目录：`rehearsal-05/logs/`、`rehearsal-05/winpack/audit/`、`windows-pack-proof/`、`launcher-proof/`、`rehearsal-06/logs/`、`rehearsal-06/wheel-proof/`、`linux-final-candidate/`。`package-data-proof.json` 保存包数据逐文件检查，`candidate-review.json` 保存当前候选的尺寸和哈希。
