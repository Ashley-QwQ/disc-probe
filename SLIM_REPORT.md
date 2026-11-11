# Windows 完整包瘦身报告

代码和本地验证包已经生成，全部未提交。**严格形式等价验收没有通过**：主要数值和输出比较通过，但一项额外保守的全容量映射门槛未过；照片目标的一阶最优性、姿态协方差、FFT 编译实现的无条件误差证明也仍有缺口。不能把这些检查写成“所有功能在所有输入上已形式证明等价”。`tests/slim_acceptance.py` 对此明确返回 1，详细理由在 `EQUIVALENCE.md` 和 `tests/slim_artifacts/acceptance.json`。

没有联网下载、系统安装、提交、发布或改动 release。没有使用光驱。重计算和压缩使用低优先级，限制 BLAS 为一个线程，重任务没有超过两个并行进程。没有改写 `D:/disc-probe/results` 或 `D:/disc-probe/evidence`。所有遍历工具都按要求排除受限名字。

## 改了什么

| 文件与位置 | 内容 |
|---|---|
| `discprobe/numerics.py:20` | 增加本项目实际使用的高斯滤波、矩形最大值、实数卷积和滑动均值；限制支持的参数域 |
| `discprobe/numerics.py:113` | 增加梯度、正规方程、独立导数、局部修正量、协方差和局部秩诊断；不把停止标志当作证明 |
| `discprobe/numerics.py:165` | 用 NumPy SVD 信赖域法解无约束线性损失最小二乘；lm 调用保留相同目标、换用此算法 |
| `discprobe/numerics.py:278` | 保留照片使用的非自适应 Nelder–Mead 规则 |
| `discprobe/numerics.py:338` | F survival 改用带尾界的 Decimal 不完全 beta 级数 |
| `discprobe/disexport.py:22`、`discprobe/beaconread.py:29`、`discprobe/tilephoto.py:22` | 替换数值导入；生成扇区数据的模块未改 |
| `discprobe/tilephoto.py:308` | 照片结果增加停止状态、局部下降探测及同分姿态提示；明示一阶条件和协方差未证明 |
| `tools/geo_polyfit.py:48`、`:407` | 替换最小二乘及 F 检验；残差、权重、缩放和模型不变 |
| `tools/bd_spoke_shear.py:160` | 总是执行原完整包的两个均值滤波，取消原先缺依赖时使用另一算法的分支 |
| `tools/synth_photo_test.py:23` | 合成照片也改用新滤波 |
| `discprobe/guide.py:52`、`:427`，两个 README 和两个 MANUAL | 安装提示仅保留 numpy、pillow |
| `discprobe/ui_selftest.py`、`discprobe/__main__.py:2194` | 去掉因缺 scipy 而跳过 geo 检查的逻辑；缺依赖检查仍然实际运行 |
| `discprobe/zh.py:10` | 补齐这个分支已有命令缺少的十条中文帮助，原自测会因此失败；没有降低检查条件 |
| `tools/build_winpack.py:27`、`:89`、`:135`、`:187` | 仅用本地缓存，按 Git 文件清单打包未提交源码，选择 numpy/Pillow，执行前后检查，应用保守保留清单，检查失败不生成新 ZIP |
| `tools/build_winpack.py:28` | 加入随包 selftest 已经要求的一个小型 BD CSV 夹具，否则原打包清单会让完整包自测失败 |
| `tools/winpack_policy.json` | 明列可删文件和保留理由；未知文件默认保留 |
| `discprobe/NOTICE_NUMERICS.txt` | 保留改编数值算法的 BSD 版权声明 |
| `tests/slim_*.py`、`tests/scipy_oracle_checks.py`、`tests/test_numerics.py` | 对照、记录复跑、轨迹、尺寸、哈希和严格验收工具；旧 scipy 后端只在测试侧 |

`discprobe/scsi.py` 及 allowlist 没有修改，Git diff 为空、Git 规范化 blob 哈希一致。工作树原有的 CRLF 与 Git 对象中的 LF 分开记录，未把换行口径差异说成源文件变化。证据见 `provenance.json`。

## 实测尺寸

旧尺寸来自本地实际的 `disc-probe-0.1.2.1-full-win64.zip`；新尺寸来自最终 ZIP 的目录项，解压大小为文件长度之和，不是磁盘簇占用。下表 MB 均为 1,000,000 字节。各部分压缩大小不含 ZIP 文件头，文件头单独列出。

<!-- GENERATED_SIZES -->

| 部分 | 旧压缩 MB | 新压缩 MB | 旧解压 MB | 新解压 MB |
|---|---|---|---|---|
| scipy、其 DLL 和元数据 | 31.676 | 0.000 | 90.459 | 0.000 |
| 嵌入 Python（含剩余原生库） | 11.067 | 10.051 | 21.478 | 19.545 |
| Pillow 和元数据 | 7.081 | 7.081 | 14.751 | 14.751 |
| NumPy OpenBLAS | 6.690 | 6.690 | 20.981 | 20.981 |
| NumPy 和元数据 | 3.781 | 3.781 | 12.185 | 12.185 |
| disc-probe、网页、源码与清单 | 0.590 | 5.974 | 1.615 | 10.471 |
| ZIP 文件头 | 0.375 | 0.186 | 0 | 0 |
| 完整包合计 | 61.260863 | 33.763979 | 161.468356 | 77.932559 |

完整包压缩体积减少 27.497 MB（44.88%）；解压文件减少 83.536 MB（51.74%）。换成 MiB，压缩为 58.42 → 32.20，解压为 153.99 → 74.32。

core 为 6.023506 MB ZIP、10.449896 MB 文件，依赖目录为零。旧发布 core ZIP 为 0.607472 MB；两者源码基线不同，不能把网页资源增长算作依赖裁剪失败。

<!-- END_SIZES -->

当前工作树基于含网页前端的 `feat/webui-backend`。网页字体、两种主题的图片是已跟踪的功能资源，导致源码部分比旧发布包大；没有为了缩小数字删除网页功能。core 仍没有 Python、site-packages 或其他依赖。最初怀疑有忽略的本地图片混入，经逐项复核，主要增长实际来自上述网页资源；这里按最终 ZIP 的实测数报告。

## 删除和保留的理由

每个实际删除文件的名字、解压字节、压缩字节和理由均在 `tests/slim_artifacts/removals.json`，共 847 项，没有未分类项。

<!-- GENERATED_REMOVALS -->

| 删除项 | 文件数 | 解压 MB | 压缩 MB | 理由 |
|---|---|---|---|---|
| scipy + scipy.libs + dist-info | 843 | 90.458518 | 31.675894 | 生产数值导入全部替换；不复制整个缓存 |
| python/Lib/site-packages/bin/f2py.exe | 1 | 0.108373 | 0.052606 | 仅用于 Fortran 编译或 NumPy 构建配置；程序不调用 |
| python/Lib/site-packages/bin/numpy-config.exe | 1 | 0.108373 | 0.052613 | 仅用于 Fortran 编译或 NumPy 构建配置；程序不调用 |
| python/_sqlite3.pyd | 1 | 0.131296 | 0.061118 | 应用和工具不使用数据库；未加载 |
| python/sqlite3.dll | 1 | 1.584864 | 0.849367 | 应用和工具不使用数据库；未加载 |

<!-- END_REMOVALS -->

这不是把未加载的东西全删掉。保留清单在完整包根目录 `winpack-keep-list.json`：

* 标准库 ZIP 的 541 个条目全保留。动态字符编码、子进程、多进程和分析工具的使用范围不能仅凭一条测试轨迹缩成可靠的静态闭包。
* Python 顶层 34 个条目保留。SSL、libssl、libcrypto、压缩、XML、ctypes、socket、Decimal 等没有凭“没加载”删除。哈希确实使用加密库；HTTPS 虽未见于应用主流程，仍保留相关库。
* Pillow 目录的 106 个条目全保留，包括 AVIF、WebP、颜色管理、TrueType 字体和其他插件。用户可以选择不同格式的图片，工具也确实使用字体；网页图片和字体还需要保留原有静态资源。
* NumPy、OpenBLAS、Pillow 的 403 个共同文件与旧包逐字节相同。没有裁其运行 API 或 DLL。

SQLite 的删除只针对 disc-probe 功能闭包：生产代码和随包工具没有数据库功能或导入，轨迹也未加载它。这个包不是任意用途 Python 开发环境；未承诺手动 import sqlite3 或运行 f2py 仍可用。缓存本身没有被改动。

## 检查结果与边界

<!-- GENERATED_TESTS -->

| 检查 | 结果 |
|---|---|
| 无 scipy 的未裁剪包 selftest | all checks passed |
| 无 scipy 的未裁剪包 pytest | 108 passed，17 subtests passed |
| 裁剪包 selftest | all checks passed；失败时构建不会生成 ZIP |
| 裁剪包 pytest | 108 passed，17 subtests passed |
| 参考 scipy 存在时的函数级检查 | 9 passed（独立规格检查 5、参考对照 4） |
| 参考 scipy 缺席时的对照检查 | 实际 find_spec 为 None，4 skipped |
| 最终完整包解压导入检查 | scipy 缺席，numpy、Pillow、Decimal 数值函数可用 |
| 最终 ZIP 哈希和源码清单 | 两包均核对；运行文件与中文空格路径自测通过的副本逐字节相同 |
| 额外全容量映射门槛 | FAIL：一组 0.000190106 度 > 附加的 0.00005 度；按来源所报 sigma 的比较通过 |
| 严格形式等价门槛 | FAIL，保留上述附加失败和形式证明缺口 |

退出时的模块与 DLL 轨迹（含测试侧模块，DLL 包括 Windows 系统库）：

| 阶段 | 进程轨迹数 | 模块名并集数 | DLL 路径并集数 |
|---|---|---|---|
| untrimmed | 42 | 626 | 83 |
| trimmed | 42 | 626 | 83 |

本次成功构建轨迹目录：`D:/disc-probe-dist/slim-20261111/audit/1794432811583376800`。`sys.modules` 和 EnumProcessModulesEx 的退出快照都保留。退出快照不证明所有曾短暂加载的 DLL。

<!-- END_TESTS -->

32 组梯级数据全部参与了旧、新路径重算，4 个仅有摘要的 geo 输入仍记缺失。已接受的 91 对单次/联合多项式解，最大观测差约为 6.43e-6 sigma，最大参数差约为 7.49e-7 sigma；独立数值一阶检查通过。本来就失败的运行没有改为成功。32 次完整 CLI 的 stdout 一致，其中 3 次两边都失败；三种联合模式的数值输出与结论一致。预设有两组末位显示差异，原样列在 EQUIVALENCE.md；来源半径不确定度及完整映射差解释了其大小，但不称为末位相同。

40 份照片摘要都缺所指向的原照片。不能用 overlay 或保存的颜色结果代替原始输入。补充的合成照片两条路径都是 129/129 个 ID，CSV 逐字节相同；合成 beacon 都是 27 个结果，全部相同。合成照片使用 800 像素拟合宽度，不能代替默认 1200 像素及所有实拍条件的验证。

一次中文空格路径检查最初因隔离子进程使用系统 GBK、测试按 UTF-8 解码而失败。加入显式 `-X utf8` 后，中文空格路径的解压自测通过。最终重打包只同步这一构建参数、core 的未提交工作树标记和源码哈希清单；工具拒绝任何运行代码变化。最终 ZIP 再次解压，逐文件确认与已自测运行文件一致，并重新验证 import scipy 失败。`extracted-first.json` 保留首次失败，`repack.json` 和 `final-artifacts.json` 记录最后这一小步，没有用最终哈希冒充先前完全相同的 ZIP。

## 本地产物与复跑

完整包：`D:/disc-probe-dist/slim-20261111/disc-probe-slim-20261111-full-win64.zip`。core：同目录 `disc-probe-slim-20261111-core.zip`。各有 SHA-256。构建、解压和测试轨迹仍在这个 scratch 目录；原 release 和缓存未动。

<!-- GENERATED_HASHES -->

| 最终文件 | SHA-256 |
|---|---|
| full-win64 | 669c8cb6edd6a929067e62877cb9a9a020c6442f651ee9c15f87a5570a89e2a4 |
| core | 91f4d60eb55ae82c25251184050172e68f671f1d09f942eed4a3715fd3904eb1 |

<!-- END_HASHES -->

从工作树根目录运行，命令均显式隔离路径；不要安装任何东西：

```powershell
python -I -X utf8 -B tests/slim_inventory.py
python -I -X utf8 -B tests/slim_equivalence.py --section all
python -I -X utf8 -B tests/slim_photo_equivalence.py
python -I -X utf8 -B tests/slim_cli_equivalence.py
python -I -X utf8 -B tests/slim_prepare_deps.py D:/disc-probe-dist/slim-20261111/test-deps
python -I -X utf8 -B tools/build_winpack.py --ref HEAD --label slim-20261111 --out D:/disc-probe-dist/slim-20261111 --cache D:/disc-probe-dist/cache --worktree --audit-tests --test-deps D:/disc-probe-dist/slim-20261111/test-deps
```

数值对照需要本机原有的 scipy，缺失就跳过，不能当作等价通过。完整包的两个构建检查均在没有 scipy 的解释器里执行。`slim_acceptance.py` 是严格任务验收，目前应该返回 1；不要为了得到零退出码改掉缺口。

## 干净 Windows 上仍需检查

还没有干净虚拟机或第二台 Windows 的结果。需要在没有系统 Python、NumPy、scipy 和额外 VC 运行库的机器上解压，双击启动，检查终端、网页及本地字体；也要在默认系统区域设置和含中文/空格路径下测试正常启动流程。当前中文路径检查用了显式 UTF-8 隔离解释器，不能据此声称所有系统编码组合都已测试。

还需要真实原照片，覆盖默认 1200 像素配准、不同镜像/倾斜/曝光、相近候选、多种 Pillow 格式及 EXIF。需要给照片目标建立可审查的测量模型和不确定度定义，才能谈参数协方差与一阶条件；局部秩检查不能排除全部远处极小值。FFT 的无条件编译实现误差证明也没有完成。按本任务规则没有做任何光驱或刻录检查，这些记录不证明硬件行为。
