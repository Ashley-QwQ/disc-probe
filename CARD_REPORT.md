# CARD_REPORT：focal geometry

分支 `dev/focal-geometry`，worktree `D:/dp-dev/focal`。本轮完成几何实现、离线生成和回归验收；
焦距仍是卡片授权的暂定值，等待用户两高度测量。历史 alpha 旧预览未定位，详见“未完成与待决定”。
未推送、未合并、未切换分支；未连接光驱、未刻录、未上传、未下载依赖。

## 按提交列出的工作

- `1b79147` — `docs: inventory focal geometry and migration plan`：先提交 `FOCAL_PLAN.md`，列明旧值、基线行号、修改与保留范围、外部来源和验收方案。
- `7fe0e17` — `fix: move provisional focal calibration into physical pose geometry`：集中焦距与高度公式；迁入必要几何、δ图、摆放纸生成和来源提取/回归工具；生成4096²δ图、5套手机色板及255套自定义色板；更新网页刻度及机位映射；保留旧工程显式缩放读取；新增/更新相关测试和固定标签证据。
- 本报告提交 — 记录命令、结果、18块对照尺的数字、输出位置、证据缺口与复测后的重跑步骤。

## 几何改动与单位

唯一待定的校准输入：`discprobe/focal.py:VIDEO_FOCAL_PX = 3355.0`，指3840像素宽、16:9、标准防抖视频。
照片/native焦距均由它换算，未把3355直接用于照片解算器。

保持原视频九宫格在纸上的位置：

```text
f_photo_old_native = 3124.067773216577 × 206.5 / 120
f_video_old = f_photo_old_native × 3840 / (8064 × 0.819)
            = 3125.7631023568388 px
H_table_new = 207.8 × 3355 / 3125.7631023568388
            = 223.0396153420365 mm
H_disc_new  = H_table_new − 1.2 − 0.1
            = 221.7396153420365 mm
δ(P) = |(unit(camera−P) + unit(flash−P)) · unit(track tangent)|
```

高度尺印223.0mm；网页显示22.3cm。模型使用未舍入高度。网页低于30cm的刻度仍采用通过设计点的线性换算，
印刷标线舍入误差小于0.05mm。修复了非整数厘米设计标线处的键盘舍入/吸附问题。

镜头垂足仍为 `(0,28.45)`，闪光垂足仍为原纸的 `(0,76.3857872575386)`。
旧产品色板把后者舍入成76.35mm，本轮回到纸上精确点，未移动纸线。
新色板和标准rig场景不再写入0.93；Python/网页光学API默认1的行为保留，显式旧参数用于兼容回放。
旧标准rig键 `21` 保留以读取旧工程，加载后采用新几何和scale=1；无rig的任意旧机位仍保留其显式旧缩放。

`data/focal/delta_map_1x.npy` 为4096×4096 float32、160mm见方、像素中心取样、r24–58mm外NaN，
与原图坐标口径一致。文件67,108,992字节。生成器按128行分块，不改颜色波模型、材质周期或刻录几何。
原图5个代表行与恢复的旧几何核对通过；新图全部行与当前几何的再生成核对通过。

## 固定已刻盘回归

选用 SHOW-E 4-14 / `IMG2654-1x21-H`。只读配方记录确认scale=0.93、offset=0及已刻盘身份；
原始 `img2654I.npy` 和纹理列表均与配方哈希一致。
原标签SHA256：`7138557faf09cc5afa58a2d9c53ae4cabe69e2f7515b426a96817930be99370a`。

固定69种原纹理、不重新选纹理，保留51,813个原细胞中心样本（主网格0.4mm，极小纹理另取原细胞），
全部样本的最大绝对Δδ为 **0.0056287071**。完整69项数字在 `data/focal/regression.json`，
包括逐材质样本数、旧/新均值、平均残差、95分位和最大残差。
按原周期折算的一阶波长变化最大约11.0463nm；这不是相机色相或肉眼色差测量。

原盘18块对照尺按保存边界各取17×17个位置，直接算同位置的旧几何×0.93与新几何×1。
表中 `new/old` 是原盘的两列纹理名称；两列都按同一对物理机位比较，没有按列另调scale/offset。

| 站点 | 色块 | 原盘列名 | 平均Δδ（新−旧） | 最大\|Δδ\| | 平均相对旧δ |
|---|---|---|---:|---:|---:|
| S1 | red | new | 0.0011145 | 0.0012437 | 0.446% |
| S1 | red | old | 0.0013095 | 0.0014407 | 0.471% |
| S1 | green | new | 0.0010136 | 0.0011243 | 0.405% |
| S1 | green | old | 0.0012176 | 0.0013306 | 0.437% |
| S1 | blue | new | 0.0009659 | 0.0010599 | 0.385% |
| S1 | blue | old | 0.0011851 | 0.0012866 | 0.424% |
| S2 | red | new | 0.0035151 | 0.0036615 | 1.122% |
| S2 | red | old | 0.0037241 | 0.0038521 | 1.097% |
| S2 | green | new | 0.0036294 | 0.0037786 | 1.163% |
| S2 | green | old | 0.0038423 | 0.0039724 | 1.136% |
| S2 | blue | new | 0.0037452 | 0.0038974 | 1.204% |
| S2 | blue | old | 0.0039626 | 0.0040949 | 1.176% |
| S3 | red | new | 0.0050906 | 0.0051697 | 1.223% |
| S3 | red | old | 0.0050326 | 0.0051195 | 1.190% |
| S3 | green | new | 0.0052274 | 0.0053083 | 1.260% |
| S3 | green | old | 0.0051672 | 0.0052563 | 1.225% |
| S3 | blue | new | 0.0053667 | 0.0054492 | 1.297% |
| S3 | blue | old | 0.0053045 | 0.0053957 | 1.262% |

18块平均变化约0.385%–1.297%；残差小但非零，且随位置变化。
高度变化改变单位光线的归一化分母，不能严格等价于整个δ场乘一个常数。
因此没有继续拟合焦距、周期、色表或加offset去强行一致，也不宣称“逐像素无色差”。
原参数重建预览与新预览已并排目视检查，主体颜色接近；彩虹/镜面部分没有使用纹理缩放，仍随真实机位改变。
没有用镜面反射点定焦。

## 摆放纸与输出

输出均在 `D:/dp-dev/tmp/focal/`：

- `dp_rulers_1x_new_letter.pdf`：新版三页PDF；`dp_rulers_1x_old_letter.pdf`：旧高度的本地重建对照。
- `ruler_height_new.png`、`ruler_placement_new.png`、`ruler_placement_video_new.png`：新版PNG。
- `rulers_comparison.png`：原外部PDF与新版PDF的三页并排渲染；`pdf_new_page1.png`至`page3.png`为逐页渲染。
- `rulers_verification.json`：PDF页尺寸与逐页像素差；`regression.json`：回归副本。
- `show_e_old_reconstructed.png`、`show_e_new.png`、`show_e_comparison.png`：固定标签的600²抽样预览与并排图。

PDF三页均为US Letter（612×792pt）。本机无pdftoppm，使用已安装PyMuPDF以110dpi渲染并目视核对。
每页1,131,350像素：高度尺页差3367像素，照片放盘页0，视频放盘页0。
只有高度页的标线、对应数字和高度说明发生变化；两种放盘页连旧“约21cm”的说明也保持原样，未擅自重排。
所有中文正常；新写入中文文件已检查非ASCII字符大于0，无长串问号。

原照片页按盘面高度206.5mm计算网格，视频页按桌面207.8mm计算网格。
本轮以视频取景为准；两种原网格都冻结后，照片线与新尺并用仍有约0.6%的历史高度基准差，
没有通过移动照片线掩盖这一差异。

## 命令与结果

生成命令（在本worktree根目录，Python均使用 `-B -X utf8`）：

```powershell
python -B -X utf8 tools/focal_capture.py
python -B -X utf8 tools/focal_geometry.py
python -B -X utf8 tools/editor_pose_swatches.py
python -B -X utf8 tools/focal_regression.py --out data/focal
python -B -X utf8 tools/focal_regression.py --previews
python -B -X utf8 tools/make_rulers.py
python -B -X utf8 tools/make_rulers.py --legacy
python -B -X utf8 tools/focal_verify_rulers.py
python -B -X utf8 tools/focal_geometry.py --check
python -B -X utf8 tools/editor_pose_swatches.py --check
```

来源提取69/69纹理有样本、18块尺；旧坐标核对通过。δ图全量核对通过；5+255色板及全部元数据核对matches。
7个记录的外部来源文件在结束前重新计算SHA256，7/7未变。

初步测试：相关预览12项通过；新几何6项通过；网页/Python光学一致性9项通过。
最后的相关Python测试命令：

```powershell
$env:TEMP='D:/dp-dev/tmp/focal'
$env:TMP=$env:TEMP
$env:MPLCONFIGDIR='D:/dp-dev/tmp/focal/mpl'
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -n 2 tests/test_focal_geometry.py tests/test_editor_pose_swatches.py tests/test_editor_preview.py tests/test_simulate_a3.py tests/test_simulate_colour.py tests/test_lamp_optics.py --basetemp D:/dp-dev/tmp/focal/pytest-final --junitxml D:/dp-dev/tmp/focal/pytest-final.xml -q
```

结果：**38 passed、119 subtests passed，165.87秒**；JUnit共157个通过条目，0失败、0错误、0跳过。
该命令后增加了来源哈希断言，定向重跑 `test_focal_geometry.py` 与 `test_editor_pose_swatches.py`：16项通过。
网页光学一致性涵盖新机位，以及旧206.5mm、显式0.93的兼容姿态。

全部允许路径的 `tests/test_*.mjs` 用Node逐个串行运行：

```powershell
python -B -X utf8 D:/dp-dev/tmp/focal/run_mjs.py
```

结果 **35/35脚本返回0**，无失败。逐脚本结果在 `D:/dp-dev/tmp/focal/mjs-results.json`，各自 `.log` 同目录。
包括浏览器DOM、工程导入导出和设计页机位测试，均使用模拟后端，不接触光驱。
其后修正设计标高键盘舍入并新增用例，定向重跑 `node tests/test_editor_lamp.mjs`、
`node tests/test_editor_rig.mjs` 均通过。浏览器测试生成的截图移至上述临时目录的 `mjs-impeccable/`、`mjs-editor/`。
未循环重跑整个Python套件。`git diff --check` 通过。

## 未完成与待决定

1. **实机两高度焦距复测、重新拍摄SHOW-E颜色：未测。** 3355只是卡片指定的暂定值，不能把本轮离线回归当成实机保色验证。
2. **历史alpha旧预览证据未定位。** 已找到0.93的已刻配方、原标签及其哈希，但未找到这一盘历史保存的alpha预览；本次对照是按旧参数重建。严格的“曾在alpha出过预览”的历史证据项未完全满足，未伪造该结论。
3. 两种摆放纸的历史高度基准差已保留。是否另开任务统一照片纸说明/网格，需用户决定；本卡要求纸线不动。
4. 回归是固定标签有限采样和解析几何，未证明所有连续位置无色差，也未做新盘/跨手机验证。69材质的51,813个原细胞样本和18个色块的解析样本均已明示。
5. 新规范先用于标准机位；未选手机的旧33cm通用预览默认值未改变。30–70cm仍是模型预测，未重新逐块实拍验证。

## 将来改焦距时重跑什么

只改 `discprobe/focal.py` 的 `VIDEO_FOCAL_PX`，不手改网页生成常量或色板JSON。
依次重跑：`tools/focal_geometry.py`（pose/δ图/网页标高）→ `tools/editor_pose_swatches.py`（两套色板）
→ `tools/focal_regression.py --out data/focal` 与 `--previews`（数字和对照）
→ `tools/make_rulers.py`（新PDF/PNG）→ `tools/focal_verify_rulers.py`（相对原纸逐页核对）
→ 两个 `--check` → 本报告列出的相关Python与网页测试。
检查新δ残差并更新报告；差别变大就停下说明，不调色模型硬凑。
原纸线、旧来源快照、原已刻标签/纹理都不应重做或覆盖；无需重跑一次性 `focal_capture.py`，除非有新的合法回归来源。

## C2 修正：δ 图不进 git（2026-11-15）

### 历史重写与提交

重写前的三个提交号已另存到 `D:/dp-dev/tmp/focal/fix/old-history.json`：

| 原提交 | 重写后 | 提交信息（保持原文） |
|---|---|---|
| `1b79147caef25916186fd1782fb76af6e2058735` | `76edc8b84de3e2f1a2e7e02886e1549cb9aaef13` | `docs: inventory focal geometry and migration plan` |
| `7fe0e17069e0711361720ea752f5d7a7eed9a19a` | `d9289eb8d0d904de5e0eb43d0ac429a6919db7f3` | `fix: move provisional focal calibration into physical pose geometry` |
| `bede7edd38ce502d93157c096d3a75e36b9fe541` | 本报告提交 | `docs: report focal geometry validation and remaining measurement limits` |

按卡执行 `git reset --soft dev/1.0.0` 后，重新暂存并按原三个提交的顺序、信息提交；未用交互式 rebase。
实际重写时 `dev/1.0.0` 已为 `b380563844b098f1eb761d2d421e1a9675191942`，
原焦距分支父提交则为 `56f2cf709fa0420c25e46a6734438333c793b901`。
保留新基点的曲线编辑功能及测试，14 个相关文件相对新基点的 `git diff --quiet` 返回0，
没有将这些其他卡的成果撤回。公共规则中旧基点说明已过时，本次未修改公共卡或其他分支。

第二个提交包含原几何实现与本次修正，但从一开始就不含 `data/focal/delta_map_1x.npy`。
`git log HEAD --format=%H -- ':(glob)**/delta_map_1x.npy'` 输出为空；
最终三个提交还逐个检查该路径不存在。旧提交号仅作溯源记录；未清理共享对象库或其他分支。

### 生成、元数据与离线证据

- `tools/focal_geometry.py` 默认把大图生成到 `D:/dp-dev/tmp/focal/cache/delta_map_1x.npy`，
  可用 `DISC_PROBE_FOCAL_CACHE_DIR` 覆盖目录。临时生成成功后才替换缓存文件。
- `data/focal/pose_1x.json` 保留生成参数、相机/闪光坐标、采样口径、环域、dtype、字节序、NPY版本与SHA256。
  覆盖缓存目录不改变版本化元数据。`--check` 在缓存目录生成新的临时图并比对哈希和元数据，
  不依赖已有缓存，不覆盖已有缓存，检查后删除临时图。
- 新图SHA256仍为 `39090725d7b689bbf16d3fc692c82a0c17879508a71f37f4891adc65e7fa9be5`，
  与修正前一致；本次没有改焦距、机位、色板内容或几何公式。两套色板仅更新pose元数据哈希。
- `.gitignore` 忽略同名大图；wheel/sdist与Windows打包入口也显式排除它，
  防止遗留文件被打包。Windows的ref、worktree和准备好的snapshot三种源码入口均覆盖。
- 测试现场计算6组共10行，与独立单位光线模型比较；另用64²临时图验证环境变量覆盖、
  无缓存检查和错误哈希拒绝。测试不依赖67MB大文件。
- `show_e_samples.json` 仅供离线回归，移为 `tools/focal_data/show_e_samples.json.gz`，
  从775,104字节无损压缩到140,436字节。解压后原工作副本SHA256仍为
  `3b588faad2d978ab4664f87fae65065c4f2e111f90ff681b243eca744566035e`；
  与原Git blob仅有CRLF/LF差别，样本内容相同，回归的fixture哈希继续指解压字节。
- `regression.json`（33,611字节）与`show_e_preview.npz`（19,374字节）也仅供离线工具使用，
  移到 `tools/focal_data/`。前者保留已审查的69材质/18色块数值，并由测试核对再计算结果；
  后者保留原标签抽样供预览。原回归JSON内容和预览二进制均核对未变。
  `focal_capture.py` 与 `focal_regression.py` 已同步路径和压缩读写；本次没有重跑外部来源提取。

以后重跑回归的版本化产物命令改为：

```powershell
python -B -X utf8 tools/focal_regression.py --out tools/focal_data
```

### 实际打包清单

对实现提交 `d9289eb` 离线构建并检查实际压缩包，均未包含大图：

| 压缩包 | 清单条目数 | 字节数 | δ大图条目 |
|---|---:|---:|---:|
| `disc_probe-0.1.2.1-py3-none-any.whl` | 729 | 15,030,002 | 0 |
| `disc_probe-0.1.2.1.tar.gz` | 632 | 14,568,846 | 0 |
| `disc-probe-focal-fix-core.zip` | 673 | 14,789,041 | 0 |

命令：`python -B -X utf8 D:/dp-dev/tmp/focal/fix/verify_archives.py`。
文件、逐包清单、SHA256与汇总位于 `D:/dp-dev/tmp/focal/fix/packages/`。
Windows full zip未构建、其自带Python未运行selftest；它共用的源码筛选入口已通过测试，
包括模拟遗留大图仍被git跟踪时的排除。未下载依赖或上传产物。

### 最终验收

```powershell
$env:TEMP='D:/dp-dev/tmp/focal/fix'
$env:TMP=$env:TEMP
$env:MPLCONFIGDIR='D:/dp-dev/tmp/focal/mpl'
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -X utf8 -m pytest -n 2 tests/test_focal_geometry.py tests/test_focal_packaging.py tests/test_editor_pose_swatches.py tests/test_editor_preview.py tests/test_simulate_a3.py tests/test_simulate_colour.py tests/test_lamp_optics.py tests/test_release_packaging.py --basetemp D:/dp-dev/tmp/focal/fix/pytest-final --junitxml D:/dp-dev/tmp/focal/fix/pytest-final.xml -q
python -B -X utf8 D:/dp-dev/tmp/focal/fix/run_mjs.py
python -B -X utf8 tools/focal_geometry.py --check
python -B -X utf8 tools/editor_pose_swatches.py --check
python -B -X utf8 D:/dp-dev/tmp/focal/fix/check_evidence.py
git diff --check
```

相关Python最终结果：**110 passed、119 subtests passed，224.91秒**，无失败或跳过。
JUnit保存在 `D:/dp-dev/tmp/focal/fix/pytest-final.xml`。此前定向测试23项、打包筛选测试4项也通过；
最终一轮已包含这些用例，未重复跑整个Python套件。

全部允许路径的网页脚本 **36/36返回0**，累计100.72秒；比原报告多出的1项是新基点的曲线编辑浏览器测试。
日志与清单在 `D:/dp-dev/tmp/focal/fix/mjs/`；浏览器生成的截图已移到
`D:/dp-dev/tmp/focal/fix/mjs-artifacts/`。几何检查通过，两套色板均matches。
中文文件非ASCII字符数大于0、连续问号检查为0，`git diff --check`通过。

本修正没有新增需要人决定的问题。实机两高度焦距复测、重新拍摄SHOW-E、历史alpha预览定位仍未完成，
边界与原报告相同；不能将本次缓存、打包或离线回归验收当作这些实机验证。
未推送、未合并、未切换分支，未修改其他worktree或`evidence/atlas/*.py`。
