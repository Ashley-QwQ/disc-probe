# DiscImageStudio 校准全流程与盘面图案

2026-11-11；只读审查 `619ec7505ac8955f35fe2f353ebda74b6ea90dda`，与 `9b74ca3` 比较。没有联网、构建、安装、运行 DIS、访问光驱或刻盘。Python 复现只在本目录运行，单进程、Windows IDLE 优先级。递归检索排除了任务禁止的名称模式。

**结论：DIS 现在用照片逐步反推几何。新设备、新盘、没有可信预设时，完整主线是三张校准盘，随后一张复查盘，再一张成品图片盘，共五张；最低只走三阶段后直接刻成品是四张。** 每张校准盘通常导入一张完整盘面照片，人工对齐盘缘和孔缘，再点宽带或描曲线。它可以解明显扭曲的图案，但依赖同一条线的连续性、足够的半径覆盖和人工核对；并没有自动证明下一张盘与校准盘几何相同。五张是教程路线的计数，**不是成功率统计，也不是保证五张就准**。〔`DIS/docs/CALIBRATION.md:5,13–17,81–111`；`DIS/docs/CALIBRATION_TUTORIAL.md:3–5,127–143`〕

本文 `DIS/` = `D:/dis-study/DiscImageStudio/`；`DP/` = `D:/disc-probe/`。`文件:行` 均指本次本地文件。DP 的计划、原型和实测分开说明，不把计划写成已交付功能。

## 1. 相比昨天，什么变了

昨天的[研究](../dis-v150-study.md)已经确认三阶段、六个粗标点、人工照片矫正、保存预设以及迭代耗盘；这些主结论仍成立。旧报告的“四张用于教程示例，再刻图片通常另加一张”应理解为**三张求解 + 一张复查 + 一张成品**，并非四张都参与首次求解。〔`DP/docs/goals/dis-v150-study.md:7–9,36–65`〕

两提交之间没有改动 `Core/Calibration` 图案与拟合器。有关变化是新增 `OuterRingBleed`：当附带文件放外圈且启用留空时，将有效输出容量上限压到总容量的 95%，按介质写入单位向下对齐；纯图片、内圈文件不套用。校准参数读取明确传 `applyOuterRingBleed: false`，保留原始可写限制。因此不能把成品工程的外圈留空误解为校准模型的外半径改变，也不能自动将其视为校准盘多了验证区。刻录内容标识包含新开关，工程格式也保存它。〔`DIS/src/DiscImageStudio.App/ViewModels/DiscParametersState.cs:304–378`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:386–405,447–450`；`DIS/src/DiscImageStudio.App/ViewModels/BurnViewModel.cs:285–325`；`DIS/src/DiscImageStudio.Core/ProjectJsonStore.cs:38–42`〕

本目录保存了[有关提交差异](relevant-commit-diff.txt)。另有一个**文档内部不一致，不能当成这次新增功能**：教程说记录不保存候选；当前完整说明及实现已经支持保存“人工确认过的拟合结果、误差、所选候选”，恢复预测成功后还恢复下一张靶的设置；未确认的求解不走这条保存路径。原盘生成参数仍冻结。两提交对这段实现没有变化。这也校正了本次中途更新的归因：冲突在教程与完整说明/实现之间，不能直接说旧研究整篇记错。〔`DIS/docs/CALIBRATION_TUTORIAL.md:126`；`DIS/docs/CALIBRATION.md:117–119`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:572–616`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationSessionJson.cs:50–76`〕

## 2. 所有拍照阶段共有的操作

每一张实盘必须配它自己生成时的 `.calibration.json`。图案、容量、编码选项、生成几何都来自这个记录；不能拿已经改好的参数重新解释旧盘，也不能只切换阶段就认为旧盘变成了新图案。〔`DIS/docs/CALIBRATION.md:35–43`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:364–378`〕

1. 拍照或扫描盘的数据面，**完整实体外缘与中心孔都在画面内**，待测图案清楚。DIS 没有要求固定几度俯拍、固定灯距、固定闪光灯或固定曝光，也没有要求每盘拍三张。透视可以靠后续矫正处理；反光遮挡就换光照重拍同一张盘。以“尽量正视、平放、让孔缘和图案可辨”为操作建议是合理的，但这不是源码承诺的姿态容差。〔`DIS/docs/CALIBRATION.md:11–27`〕
2. 在电脑导入照片，选实体直径 12 cm 或 8 cm，对应外半径 60/40 mm；常规孔半径 7.5 mm。不要用约 58 mm 的刻录外缘代替实体边缘。〔`DIS/docs/CALIBRATION.md:13–17`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationPhotoViewModel.cs:259–263`〕
3. 分别拖 **8 个外缘点 + 8 个孔缘点**。导入时的“建议轮廓”只是图像中心附近的椭圆：横纵半轴均取图像对应尺寸的 43%，孔圈是它的 0.125 倍，**不是已经检测到了真实盘缘**。因此把 16 点全都检查、必要时拖动列为典型人工成本。〔`DIS/src/DiscImageStudio.App/ViewModels/CalibrationPhotoViewModel.cs:182–210`；`DIS/src/DiscImageStudio.App/Services/CalibrationPhotoService.cs:55–70`〕
4. 点“计算矫正”，程序联合拟合两条实体圆的单应变换，报告外缘和孔缘像素残差；查看正视图，再点确认。它不单独校正镜头径向畸变，**不会把真实刻录的 S 弯拉直**。改实体规格或边缘点，会使矫正、后续点位和拟合失效，需要重做。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationPhotoRectifier.cs:118–164`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationPhotoViewModel.cs:169–177,217–221`；`DIS/docs/CALIBRATION.md:17–27`〕
5. 后续所有宽带点和曲线点都落在矫正图上。程序一次处理一张工作照片；未找到把多张照片自动合并求同一套几何的主流程。保存记录可内嵌工作图、轮廓点、测量点；重拍和多角度人工比较可行，不能据此称为多照片联合标定。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationSessionJson.cs:82–94`；`DIS/docs/CALIBRATION.md:115–121`〕

## 3. CD：从新光驱、新桶盘到成品

以下是无可信初值时的完整路线，`→` 表示应用结果后生成下一张盘。照片要求与第 2 节相同。

1. **选 CD、盘片预设、读容量。** 用户插入空盘，选择预设，点“从光盘读取”；多设备时选刻录机。程序读取 CD 预刻槽引出区地址对应的总扇区数及可写量，核对设置，不测旋转耗时。内置 80 分钟预设是 `24.5–56.8 mm / 359849 扇区 / 1200 mm/s`，可写量另列 `359847`。容量是地址尺度，不是测得的真实内外半径。此步不刻盘、不拍照。〔`DIS/docs/CALIBRATION.md:35–43`；`DIS/src/DiscImageStudio.Core/Presets/built-in-disc-presets.json:6–13`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationMediaViewModel.cs:25–95`〕
2. **粗标盘 C1：三宽带 + 地址角度条纹。** 用户选粗标，点新建标靶，保存记录，生成 WAV/CUE 或 RAW，或者从校准页流式刻录；选设备和写入设置、勾选确认并确认刻录。程序冻结本盘参数，按全轨地址放宽带，在带的中间 72% 加扫频时标。照片 1 张，矫正 16 点后，从内到外沿同一半径点三带的内外缘，共 6 点。点估算，程序先用宽带位置求内外半径，再自动读取三处条纹的转折位置，交叉检查后给角度修正半径。用户检查后应用；只改半径，保留原轨距系数。条纹失败时可能只有宽带估值。**C1 结果 → C2。**〔`DIS/docs/CALIBRATION.md:35–65`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:347–351`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationRingViewModel.cs:342–416`〕
3. **边界盘 C2：沿半径摆动的半明半暗图。** 用户换新空盘，选择边界标定并新建，使用上一步半径、原轨距系数。输出和刻录路径同 C1。照片 1 张，再做 16 点矫正；沿真正明暗交界描线，不点条带中线。连续一段至少 6 个不同点且覆盖环带径向宽度 55%；或两段各至少 6 点、各跨 10%，总覆盖仍须 55%；只有短片段时至少 4 段、各至少 3 点，建议 5–8 段。程序用片段走向与相位反推两端半径，保留轨距形状。默认搜索初值 ±0.01 mm，自动扩范围关闭；这是为粗标约已达 ±0.005 mm 的初值准备的。用户核对所有可见交界的预测、选候选、勾吻合、应用，保存记录。**C2 结果 → C3。**〔`DIS/docs/CALIBRATION.md:71–87`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationBoundaryFitter.cs:13–18,73–98`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:369–378`〕
4. **精标盘 C3：同心圆 + 十字细臂。** 再换新盘、新建精细标靶、刻录。照片 1 张、再矫正；选择一条清楚细臂，沿中线按内到外连续描点，不沿圆环拐走。只修半径至少 6 点、跨度 18%；要完整精标，勾三次轨距拟合，至少 12 个不同半径、跨度 60%。程序拟合内外半径与三个轨距系数，连同整体转角解释弯曲，给误差、离群点和候选预测。用户核对并勾吻合、应用，把整套参数保存为有辨识度的预设。CD 同样支持三次轨距；没有单独显示 DP 所说的沿轨常数 L。〔`DIS/docs/CALIBRATION.md:89–103`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationCubicFitter.cs:15–20,122–147`〕
5. **复查盘 C4：用精标新参数再刻十字。** 新空盘、新建精标靶、刻录，拍 1 张，看内到外细臂是否更接近径向直线，有没有局部弯曲。只目视验收不必再移动 16 点；若要再求解，则打开 C4 的记录，重复矫正与描线。这一步不承诺数值精度。**C4 不满意 → 再精标 → 再刻新盘验证。**〔`DIS/docs/CALIBRATION.md:105–111`〕
6. **图片盘 C5。** 回到绘图工程，主动选择刚保存的预设，排图片并预览，核对扇区数、可写量和 CD 写入路径/交织选项，再生成或流式刻录到新空盘。程序按整套几何把图像采样到轨道并映射为数据纹理。此步不要求拍照片、不要求描点。所谓“几何正确”仍须以复刻或实盘检查为准，不能把拟合通过当成新盘已经验证。〔`DIS/docs/CALIBRATION.md:101,111`；`DIS/src/DiscImageStudio.Cd/CdTrackGenerator.cs:268–287,329–348`；`DIS/src/DiscImageStudio.App/ViewModels/BurnViewModel.cs:686–700`〕

CD 粗标的限制：70–85 分钟（315000–382500 扇区）、1200 mm/s 的全尺寸 CD，另有角度带宽度/圈数约束；8 cm CD 不应套用这条粗标路线，可以从边界或精标开始，但这要求已有可用初值。**这不是每一种 CD 都能无条件从第 2 步开始。**〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationClockRulerPattern.cs:13–18`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationWideBandPattern.cs:62–82`；`DIS/docs/CALIBRATION.md:67`〕

这里 CD 的 `.raw` 是这条校准生成器的裸音频字节流，不能因为扩展名 RAW 就把它当成 CD-ROM 数据盘校准。WAV 使用小端音频，RAW 使用大端音频；地址图案先作用在 CD-DA 逻辑字节，再交织/转换字节序。若成品改成带文件的数据盘或换外部刻录软件，应重新核对路径可迁移性；本次没有找到程序自动测得两条路径差值的机制。〔`DIS/src/DiscImageStudio.Cd/CdTrackGenerator.cs:206–218,228–241`〕

## 4. DVD：从新光驱、新桶盘到成品

1. **选 DVD、相应盘片预设、读容量。** 插空盘，读设备报告的总扇区数和可写量；可写量按 16 扇区块向下对齐。标准模板 `24–58 mm / 2295104 扇区 / 133.3 nm 位长`；实盘报告多少就用多少。没有 `geo` 式定时测量，不从空盘自动得出真实轨距曲线。此步不刻、不拍。〔`DIS/src/DiscImageStudio.Core/Presets/built-in-disc-presets.json:56–63`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationMediaViewModel.cs:53–83`〕
2. **粗标 D1。** 新建粗标靶，输出纯绘图 ISO 或走校准页流式刻录，保存同名记录。三宽带占绘图地址 3.5–17%、30.5–51%、70.5–95.5%，实际边界向上取整到 DVD 扇区。拍/扫 1 张完整盘面，拖 16 轮廓点、计算并确认矫正、沿同一半径点 6 带边、点估算；程序给宽带半径，再读条纹修正。用户应用结果，只更新半径，保留既有三个系数。**D1 → D2。**〔`DIS/docs/CALIBRATION.md:35–65`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationWideBandPattern.cs:42–59`〕
3. **边界 D2。** 新盘、由粗标参数新建波动边界 ISO、刻录；拍/扫 1 张、矫正 16 点、描清楚交界。数量与覆盖要求和 CD 相同。程序在小范围内区分片段之间相差的半圈数，反推半径，保留系数；用户看叠加线、候选、警告，勾吻合、应用。**D2 → D3。** 教程 DVD 实例有 13 段、154 点，不是固定要求。〔`DIS/docs/CALIBRATION.md:81–87`；`DIS/docs/CALIBRATION_TUTORIAL.md:96–111`〕
4. **精标 D3。** 新盘、新十字 ISO、刻录；拍/扫 1 张、矫正、沿同一细臂中线描点，勾三次轨距、反推、检查、勾吻合、应用。三个系数加两端半径是一整套新解，不能把新系数加到旧系数上。教程实例 33 点；自动扩范围从 ±0.02 mm 开始。保存预设。**D3 → D4。**〔`DIS/docs/CALIBRATION_TUTORIAL.md:113–125`；`DIS/docs/CALIBRATION.md:97–111`〕
5. **复查 D4。** 新盘，用新参数再刻十字，拍 1 张核对；若仍弯，可沿新盘自己的细臂继续精标。教程复查照片只能说明外观改善，不能给毫米精度；其前一张精标盘的局部线条还经过美工刀增强，不能当作未经处理的可见度证据。〔`DIS/docs/CALIBRATION_TUTORIAL.md:127–143`〕
6. **成品 D5。** 回工程选新预设、排图、生成/刻录；程序按几何把图像分配到 DVD 通道位置，将目标亮暗映射成纹理。校准 ISO 是纯绘图；正式成品可以另放文件或开读取兼容，但这不是重新测量几何。保持同批盘、同设备、同写入设置是教程要求，程序没有替你证明批次相同。此步无需照片或手工描线。〔`DIS/docs/CALIBRATION.md:37–45,101`；`DIS/docs/CALIBRATION_TUTORIAL.md:38–44`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:1106–1112`〕

## 5. 盘、照片、人工动作，到底多少

以下把“移动一个点 / 点一个测量点 / 计算 / 确认 / 应用”各算 1 次**测量动作**。一次拖动算一次，不把鼠标按下松开拆开；不统计滚轮、平移、文件选择器内部点击。没有用户遥测，不能声称下表是平均用户的真实点击数。

### 三阶段的可复算人工负担

| 阶段 | 对齐点 | 测量点 | 算矫正 + 确认 | 求解 | 勾轮廓吻合 | 应用 | 本阶段测量动作 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 粗标 | 16 | 6 | 2 | 1 | 0 | 1 | 26 |
| 边界：单段够清楚的最低路线 | 16 | 6 | 2 | 1 | 1 | 1 | 27 |
| 精标：要三次轨距的最低路线 | 16 | 12 | 2 | 1 | 1 | 1 | 33 |
| **三阶段最低配置合计** | **48** | **24** | **6** | **3** | **2** | **3** | **86** |
| 教程实际点数配置：边界 154、精标 33 | 48 | 193（6+154+33） | 6 | 3 | 2 | 3 | **255** |

低配置的边界 6 点必须真的跨够 55%，精标 12 点必须为不同半径且跨够 60%；点多也不能代替有效覆盖。若边界用 13 段，还有至少 12 次“另描一段”。于是教程同等点数的 **255 + 12 = 267 次测量/分段动作**。另外勾三次拟合开关至多加 1 次（若已启用则不加）。CD 没有本次实盘教程计数，267 是把同样操作配置应用到 CD 的估算，不是 CD 实测。〔`DIS/docs/CALIBRATION.md:82–85,97–101`；`DIS/docs/CALIBRATION_TUTORIAL.md:29–33`〕

**行政与刻录动作另计，不能漏掉。** 每盘至少有“新建标靶、启动生成/流式刻录、选/核对设备与速度、勾刻录确认、确认实际写入”；每张求解照片还有“导入文件、保存记录”，阶段切换 2 次，最后保存预设、回工程选择预设。为提供明确口径：假设单驱、默认速度、流式路径、记录保存对话框算一个完成动作，三张求解盘按每盘 7 个动作（新建、进入刻录、勾确认、确认写入、导入照片、选实体规格、保存记录）=21，阶段切换 2，初始选盘型/预设/读容量 3，勾三次拟合 1，保存/选择最终预设 2，共 **29 个流程动作**；再加上述 267 为 **296 个定义内动作**。这不包括选路径对话框内部操作、打开校准页、插取盘、拍照转传、复查盘与成品盘的写入点击，也不把这个数冒充真实 UI 最短路径。〔`DIS/docs/CALIBRATION.md:13–17,35–41`；`DIS/src/DiscImageStudio.App/ViewModels/BurnViewModel.cs:686–700`〕

### 成功和失败的耗材账

| 明确场景（CD、DVD 主线相同） | 全程盘数，含成品 | 拍摄/扫描次数 | 新增人工工作 |
|---|---:|---:|---|
| 三阶段各一次，直接刻成品 | 4 | 3 | 86 次最低测量；教程点数配置 267 次含分段 |
| 三阶段各一次，再独立复查，再成品 | **5** | **4** | 同上；第 4 张照片只目视比较，无须再描线 |
| 一张照片轮廓拟合失败，重拍同一盘后成功 | 5 | 5 | 假设失败前已拖完 16 点并算矫正，额外 17 次测量动作；按教程配置为 284；重拍不费新盘 |
| 粗标已量完 6 点但读角度失败；重拍同盘后成功 | 5 | 5 | 失败的一轮多耗 16+2+6+1=25 次，267+25=292；另有再导入照片等流程动作 |
| 初值仍不够，完整再烧一轮粗标后才进边界 | 6 | 5 | 多一套粗标 26 次测量，加新建、写入、拍照、传图、存记录 |
| 精标复查盘仍弯，拿复查盘继续求解，再烧复查盘 | 6 | 5 | 原复查盘照片增加矫正和描线；最低再 33 次测量，新复查多拍 1 次 |
| 三轮粗标才进入边界（教程另一实例） | 7 | 6 | 比主线多 2 套粗标，至少多 52 次测量；并非程序固定要求 |
| 写盘中断/写入失败，旧盘不可继续用 | 至少 6 | 通常仍可 4 | 重建/复用正确生成文件和记录，换新空盘重刻；坏盘可能根本没有可用照片 |

这些是**一次明确失败发生在什么时刻**的条件计数，而不是一个含糊的“失败平均多一张盘”。点位不对但照片可用时，补点、换候选或重算可完全不增加盘/照片；粗标角度失败仍可保留宽带结果，并不强制马上重刻。失败日志在底部任务栏自动展开。〔`DIS/docs/CALIBRATION.md:41,61–65,84–87,107–109`；`DIS/docs/CALIBRATION_TUTORIAL.md:72–84`〕

## 6. 每种盘面图案与 Python 复现

### 共同尺度、数据与极性

本次复现脚本：[render_patterns.py](render_patterns.py)，运行 `python -I render_patterns.py`。清单、参数、源文件哈希和输出像素哈希见 [render_manifest.json](render_manifest.json)。预览 1600×1600、画布直径 120 mm（75 µm/预览像素）；这是便于看图的分辨率，**不是盘上最小线宽或 DIS 的 8192 输出格距**。默认 CD 用圆整的 80 分钟例 `360000 扇区、24.5–56.8 mm、1200 mm/s`，不冒充内置模板的精确扇区数；DVD 用内置标准值 `2295104、24–58 mm、133.3 nm`；两者三个轨距系数均 0，全绘图区、兼容选项关闭。

目标灰度 `0=黑、255=白`。下表“黑线白底”指**逻辑目标**，不是保证拍出来黑白不反。CD 二值目标映射 `0→0x0D`、`255→0xAA`；经过交织等链路后不是所有盘面通道位都等于这个逻辑字节。DVD 黑白是送往 EFMPlus 的**扰码后字节 Q** `0xA5 / 0x92`，ISO 原始负载 P 需要再按扇区扰码逆变换，并有 ECC、同步等开销；因此不能说“ISO 黑区全部填 A5、白区全部填 92”。极性可能随观察方向/光照改变，DIS 的角度模板可容纳明暗反相。〔`DIS/src/DiscImageStudio.Cd/CdToneMapping.cs:13–30`；`DIS/src/DvdImageSolver/Solver/DvdGrayscalePalette.cs:5–9`；`DIS/src/DvdImageSolver/Solver/DispersionPoolSolver.cs:46–71`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngleSweepTemplates.cs:84–86`〕

以下覆盖 `CalibrationArtwork` **全部 10 种**及历史版本几何差异，另列独立 DVD 灰阶测试盘。当前 UI 新建只选其中三种，其他是旧记录兼容或底层 API 能生成的图案。没有发现当前校准默认图案另加网格、数字、二维码或唯一盘号。旧版 cell/group 的“可选区域、角点、spine 控件”不等于另有一层要刻的格子；实际图案由 `Target.Sample` 决定。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngularPattern.cs:3–6`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:369–374`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:564–616`〕

| 图案/版本与用途 | 几何、内容与极性 | 人/程序读什么；复现忠实度 | 预览 PNG |
|---|---|---|---|
| **AngleSweepBands v13，现粗标** | 三个地址带 `[.035,.170)、[.305,.510)、[.705,.955)`；黑带白间隔，每带两端各 14% 留黑肩，中间 72% 是 50% 占空比地址时标。虚拟半径首尾相对生成半径：第 1/3 带 `−0.65/+0.65 mm`，第 2 带反向。条纹无统一 mm 宽。 | 人点 6 个外带边；程序读条纹径向转折、检查三站一致。复现源 `Sample` 示意与精确地址相位公式；DVD 扇区上取整、CD 字节寻址不同。不是编码后光学模拟。〔`CalibrationWideBandPattern.cs:23–24,42–59`；`CalibrationAngleSweepStation.cs:25–52,66–113`；`CalibrationTarget.cs:588–612`，三者均在 `DIS/src/DiscImageStudio.Core/Calibration/`〕 | ![粗标](previews/DVD_AngleSweepBands.png) [CD](previews/CD_AngleSweepBands.png) |
| **WavyBoundary v16，现边界** | 整环半黑半白；两条对置交界，相差 180°。相位 `φ(r)=90°·sin(6π(r−ri)/(ro−ri))`，全半径三周期，摆幅 ±90°。理想阶跃交界无规定物理线宽；不是细黑螺旋线。 | 人描交界局部方向，程序解半圈归属与两半径；本来就弯，不能拿“直”作验收。解析式复现。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:369–379,574–580`〕 | ![边界](previews/DVD_WavyBoundary.png) [CD](previews/CD_WavyBoundary.png) |
| **ReferenceCross v14 / v6 参考像素，现精标** | 源 2400² 灰度资源直接采样；9 个原始圆半径像素 `[490,570,650,730,810,890,970,1050,1130]`、名义线宽 10 px；四臂十字，黑线白底，裁到环带。DVD 每源像素 `58/1199.5 mm`，线宽 **483.535 µm**；CD `56.8/1200 mm`，**473.333 µm**。本例最内圆被裁掉，完整可见 8 圈。 | 人沿同一细臂中线取点；圈帮定位，不要求交点。直接读取与源码相同的冻结灰度资源并核验 SHA256，CD 最近像素、DVD 双线性；不是凭圈数重画。忠实于输入资源及坐标采样，未执行 C# 编码逐字节对拍；v6 文件导出原图与 v14 输出尺寸不同。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationReferencePattern.cs:12–34,57–96`；`CalibrationTarget.cs:219–226,354,614–616`；`DIS/src/DiscImageStudio.App/Services/CalibrationPatternRenderer.cs:113–129`〕 | ![精标](previews/DVD_ReferenceCross.png) [CD](previews/CD_ReferenceCross.png) |
| SingleRadialLine v14，旧中标 | 仅朝上（照片 Y<0）一根 **6 mm** 宽黑色径向条，白底，裁环带；两条边只作中线视觉提示。 | 人描宽条中线；不是描两边。按判断式重写。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:191,582–585`〕 | ![单线](previews/CD_SingleRadialLine.png) [DVD](previews/DVD_SingleRadialLine.png) |
| HalfDisc v15，旧中标 | `x<0` 黑、另一半白，两条垂直径向交界，50% 占空，无细线宽。 | 描可见的任一交界，片段分别赋半圈整数；按判断式重写。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:359–367,574–576`〕 | ![半盘](previews/DVD_HalfDisc.png) [CD](previews/CD_HalfDisc.png) |
| SweptReference v7，旧组合 | 8 圈；半径归一化位置 `[.05,.13,.27,.395,.58,.68,.86,.95]`，圈宽 `[.65,1,.8,.65,1,.8,.65,1]·span/34 mm`；十字宽 `min(1.5×参考10px宽, .025×span)`。120° 黑扇区，扇区内十字反成白；第 2–3、6–7 圈间扇区角以二次函数扫动。圈周围 ±0.68 圈宽为隔离区，圈本身 ±0.5 宽。 | 量圈及扇区参考/描臂；宽窄、非等间距有助辨认，但不是唯一编号。已复现完整采样逻辑。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngularPattern.cs:13–72`；`CalibrationTarget.cs:246–249`〕 | ![组合](previews/DVD_SweptReference.png) [CD](previews/CD_SweptReference.png) |
| FineCross v7，旧组合细标 | 同上 8 圈、同上十字与宽度，但不绘黑色扇区，全是黑线白底。DVD 零系数例圈宽正好 `[650,1000,800,650,1000,800,650,1000] µm`，十字 **725.302 µm**；CD 对应乘 `32.3/34=0.95`，十字 **710 µm**。 | 读圈/描臂，按原解析式重写。与现精标参考 PNG 不是一张图。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngularPattern.cs:21–34,51–61`〕 | ![旧细标](previews/DVD_FineCross.png) [CD](previews/CD_FineCross.png) |
| ClockRuler v8，旧 CD 粗标 | 连续逻辑字节载波，周期 **2058 字节=14 mm**，表长 `2058×257=528906`；黑比例 `.5+(cosφ−cos3φ/6)/√3`，按冻结 PCG64 抖成 0/255，再映射 0D/AA。六地址圈位于 `[.05,.18,.35,.55,.74,.92]`，黑半宽 `.006` 全轨进度，白肩到 `.0095`。近共振的光学条纹宽度不是固定刻线宽；共振间隔约 **2.22817 mm**。 | 自动找六门圈与载波角阶数，分 45° 窗口交叉验证；相邻区域结果差 >.035 mm 判冲突。PNG 忠实移植 **应用自身的增强示意预览**，灰度不是原始字节；另复现精确 PCG 载波二进制及按地址的取样函数，未生成整条 CD。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationClockRulerPattern.cs:7–33`；`DIS/src/DiscImageStudio.Cd/CdClockRulerSampler.cs:16–59`；`DIS/src/DiscImageStudio.App/Services/CalibrationPatternRenderer.cs:50–101`；`CalibrationClockReader.cs:42–75` 位于 Core/Calibration〕 | ![时钟尺示意](previews/CD_ClockRuler.png) |
| RadialArcDashes v9，旧 CD 粗标 | 3 个朝 +X 的短弧，半径 `ri+span×[.12,.50,.88]`；径向厚 **200 µm**，圆周长 **16 mm**，全张角 `16/r` 弧度。CD 例中心半径 `28.376/40.650/52.924 mm`，张角约 `32.31/22.55/17.32°`。黑弧白底。 | 用户量完整弧跨度、确认弯曲方向/未绕整圈/未反向；程序用跨该厚度的角度变化求半径。按 v9 原规则复现。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationRadialArcPattern.cs:10–41`；`CalibrationRadialArcFitter.cs:20–22,47–70`〕 | ![短弧9](previews/CD_RadialArcDashes_v9.png) |
| RadialArcDashes v10，旧 CD 粗标 | 同样 3 个径向位置，各全张角 **40°**，厚度依次 **320/300/280 µm**。本例弧长约 **19.810/28.379/36.949 mm**。 | 同上；按版本分支重写。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationRadialArcPattern.cs:14–30`〕 | ![短弧10](previews/CD_RadialArcDashes_v10.png) |
| WideAddressBands v11，旧 CD 宽带 | 3 黑带白底，原始地址 `[.050,.078)、[.280,.320)、[.860,.920)`，没有带内扫频条纹；不是与 v12 相同宽度。 | 人量边，求两半径；没有刻过的角度标记无法补读。按地址/恒轨距示意复现。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationWideBandPattern.cs:19–24,55–59`；`DIS/docs/CALIBRATION.md:125`〕 | ![宽带11](previews/CD_WideAddressBands_v11.png) |
| WideAddressBands v12，旧 CD/DVD 宽带 | 地址与当前粗标相同的三带，但全部填黑，无条纹。DVD/CD 尺度见下表。 | 人量宽带内外缘，只读径向地址，不独立读取每圈角度。按源规则重写。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationWideBandPattern.cs:23–24,42–59`；`CalibrationTarget.cs:588–612`〕 | ![宽带12](previews/DVD_WideAddressBands.png) [CD](previews/CD_WideAddressBands.png) |
| DVD `periodic-9b-16-v1`，当前可选读取兼容纹理 | 每个2048字节扇区偏移 `0,16,…,2032`，仅属于绘图且 Q 不是 A5/9B 时改为 9B；二值白扇区改128字节=6.25%，A5 黑不动。不是有毫米半径的附加图案。 | 不读几何，旨在改善纹理区可读性。Q域与字节归属规则均移植；图为字节身份，橙色不是光学颜色。〔`DIS/src/DvdImageSolver/Solver/DvdReadCompatibilityGuard.cs:12–34`〕 | ![兼容纹理字节示意](previews/DVD_read_compatibility.png) |
| DVD `bridge-9b-v1`，旧校准记录兼容纹理 | 每段至少2个连续92的起始处，若归属绘图、前字节非75/9B、前或后64字节窗口有至少58个A5/92，段首改9B；所有决策看原始Q。 | 旧记录未存配方但开了兼容时走此冻结规则；不与新版叠加。Q域移植，非真实盘面光学复现。〔`DIS/src/DvdImageSolver/Solver/DvdReadCompatibilityGuard.cs:37–93`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:287–295`〕 | [同图右列](previews/DVD_read_compatibility.png) |
| **DvdGrayProbe 独立开发测试盘**，非主线校准 | 6000²、20 µm 栅格，半径 24.5–57.3 mm。12 个 30° 面板、24 个 15° 参考色块；Q 码 `[A5,66,64,E4,B9,92]`；4 级渐变、四级源图裁块、多组 25/50/75% 混合、面板数字/十六进制文字、12 点钟方向矩形标记。假彩预览颜色只为区分 Q 码，**不是盘片真实颜色**。 | 看不同候选灰纹与混合的可见效果，不参与两半径拟合。布局、混合 FS 抖动与字形都已移植；原输入是外部指定 6000² 四级图，本次没有它，640² 裁块用四条灰阶竖带代替。因此整体几何可复现，原画内容不能声称忠实；不生成 ISO。〔`DIS/tools/DvdGrayProbe/ProbePattern.cs:11–50,72–121,123–175,178–191`；`Program.cs:110–133` 同目录〕 | ![灰阶测试假彩](previews/DvdGrayProbe.png) [原生 Q 码图](previews/DvdGrayProbe_Q.png) |

“ReferenceCross 的 v6”与“v14”共用原始图；“RadialArc 的 v9/v10”和“宽带 v11/v12”则真正改变几何，所以单列。其余没有证据表明存在额外需要另刻的网格或文字校准靶。BD 字节密度研究工具中的有限编码向量是编码分析，不是这里 CD/DVD 用户流程中的盘面图案；本文不把 BD 整套编码研究扩成另一个课题。〔`DIS/src/DiscImageStudio.Core/Calibration/Patterns/README.md:3–21`；`DIS/tools/BluRayByteProbe/Program.cs:21–44`〕

### 运行参数下可直接量的尺寸

恒轨距时宽带位置近似 `r(q)=sqrt(ri²+q(ro²−ri²))`。CD 零系数就是面积公式，DVD 复现求解精确阿基米德弧长，表中显示到 µm 的 1/1000 mm 仅为计算值的位数，**不表示实盘有该精度**。DVD 已按源逻辑把带边地址向上取整到扇区，以下理想百分比值与其预览差小于所列 0.001 mm 精度。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationGeometry.cs:22–42,74–93`；`ConstantPitchCalibrationGeometry.cs:9–49`；`CalibrationWideBandPattern.cs:42–52`〕

| 本次示例 | 第 1 带内/外 mm | 第 2 带内/外 mm | 第 3 带内/外 mm |
|---|---|---|---|
| CD 24.5–56.8 | 26.309 / 32.352 | 37.432 / 44.040 | 49.513 / 55.750 |
| DVD 24–58 | 25.953 / 32.403 | 37.767 / 44.698 | 50.414 / 56.908 |

参考 PNG 九圈的全部源半径经缩放为：DVD `23.693,27.561,31.430,35.298,39.166,43.035,46.903,50.771,54.639 mm`；CD `23.193,26.980,30.767,34.553,38.340,42.127,45.913,49.700,53.487 mm`。各例第一个圆低于绘图区内缘，裁掉。没有人为再添一条圈或数字标记。〔源圈及映射：`DIS/src/DiscImageStudio.Core/Calibration/CalibrationReferencePattern.cs:23–34`；可见圈筛选：`CalibrationTarget.cs:219–226`〕

粗标时标的源公式是 `rv(q)=sqrt(rv0²+(q−qs)·(rv1²−rv0²)/(qe−qs))`，`phase(q)=2L(q−qs)/(rv0+rv(q))`，每半个周期切换黑白。二维示意采样 `atan2(y,x)−θ生成(r)+phase(q)` 的正负半周，而实际写入按全轨地址切换。因此预览中微密条纹有栅格混叠，不能按 PNG 像素倒推字节边界或真实拍照对比；特别不应用普通绘图导入这张 PNG 代替校准生成器。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngleSweepStation.cs:25–40,66–113`；`CalibrationTarget.cs:598–606`；`DIS/docs/CALIBRATION.md:45`〕

可选读取兼容是**同一目标内部的负载纹理变换**，不能用黑白目标PNG表达它的真实光学亮度。每个Q字映射16通道位，按133.3 nm位长是约2.1328 µm的通道长度；每16负载字节只是地址周期，不应忽略同步/ECC等结构后声称盘上处处等距34.1248 µm。上述例子128黑+128白重复8次，当前配方改64字节，旧配方改8字节；见 [guard_manifest.json](guard_manifest.json)。默认预览关闭这项，因此前面主图没有9B保护纹理。精确指定Q的灰阶探针接口拒绝该选项，以保留实验输入。〔`DIS/docs/DVD_ENGINE.md:21–29`；`DIS/src/DvdImageSolver/Solver/DvdReadCompatibilityGuard.cs:23–31,65–90`〕

### DVD 灰阶探针的细分尺寸

12 面板的候选依次 `66,64,E4,64,E4,66,E4,66,64,66,E4,64`；面板留左右各 4% 空隙。内参考带 `24.5–25.6 mm`、外参考带 `52.2–57.3 mm` 各分 24 色块，每块左右各 2.5% 留白。`26–28.1 mm` 为 640×105 的四级误差扩散渐变；`28.5–30.5 mm` 为 64/E4 混合；源图片局部是各面板坐标中 `u∈[−6.4,6.4)、v∈[31.1,43.9) mm` 的 12.8 mm 方块。候选分别与 A5/B9/92 混合的三带为 `45.8–47.5 / 47.8–49.5 / 49.8–51.5 mm`，每带三列占比 25/50/75%，列两侧 2.5% 留白。〔`DIS/tools/DvdGrayProbe/ProbePattern.cs:13–33,72–118`〕

面板名文字中心半径 45.15 mm、字点 0.13 mm；外码文字中心半径 56.2 mm、字点 0.17 mm；字形 5×7，字符步长 6 点，A5 墨/92 底。顶部方向标记原栅格 30×50 像素=**0.6×1.0 mm**。源码逐半格盖写字形；移植相同步长和字形，浮点迭代边缘可能差一两个原栅格，不称字节完全一致。四级内容是 A5 / 候选 / B9 / 92；这里 B9 在探针名义预览按 170 灰显示，不要与主二值绘图或别的灰度映射混为一谈。〔`DIS/tools/DvdGrayProbe/ProbePattern.cs:46–50,121,150–174,190`〕

## 7. 扭曲、S 弯、重复特征和相位绕回

### 为什么三阶段能接力

按源几何推导：同一地址进度 q 在生成假设上是 `(r生成,θ生成)`，在真实盘上是 `(r实,θ实)`。所以目标图案的角度偏移随半径为 `θ实(q)−θ生成(q)+整体转角`。内外半径或轨距形状略差，累积许多圈后也能大幅弯曲。这是模型推论，不是本次真实光盘实验。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationGeometry.cs:74–93`；`CalibrationTarget.cs:521–535`〕

![相同图案在错误几何下的预览与源图对照](previews/contact.png)

下排前两图是本次模拟：生成 `24/58 mm`，实际 `24.003/57.997 mm`，相同总轨长、恒定轨距。仅两端各差 3 µm，十字仍可明显绕转；这说明不能用半径数字“只差几微米”断定细线一定可见。这里没有模拟衍射、CIRC、镜头、眩光；白黑目标也不能预测照片可见率。图中边界本来的三周期弯曲与几何误差叠加，不能把两者都叫错误。

| 阶段 | 假定前一步已经做到什么 | 大扭曲下怎样保留信息 | 失效或歧义时怎样处理 |
|---|---|---|---|
| 三宽带初估 | 不要求十字已可辨；地址容量/线速度正确，能辨认至少首末带边，实体尺度正确 | 整圈地址带不靠绝对转角，不会因照片转动而认错臂；先用半径平方对地址回归 | 带序倒置、边缘与其余预测差 >0.40 mm 拒绝；仅首末带边可先粗估，但三站角度修正要同方向六点 |
| 三带扫频修正 | 宽带定位能将每带照片半径对应到地址；环带足够宽、转折落在可读范围 | 找“频率反转/条纹最宽处”，不用在海量重复条纹中手数绝对第几根；首/末站预测中站，再多方位比较 | 低对比、边缘裁断、多峰、三站冲突时不给角度修正；保留纯宽带估值，重拍或重粗标 |
| 波动边界 | 默认适合粗标约 ±5 µm；搜索默认 ±10 µm，轨距形状已至少能解释大体走向 | 半明半暗占空比高，扭成密螺旋也比细十字更容易留下可跟随交界；已知三周期源波形增加走向信息 | 同段连续展开、不同段枚举半圈归属；范围/绕圈过多、短段、覆盖不足、多解时自动不通过；补点、缩/扩范围或回粗标 |
| 十字精标 | 能在实盘辨认并连续跟随同一细臂，覆盖足够半径 | 对连续点展开相位，然后拟合累积角度差和三次轨距；并不假设输入十字已经直 | 只靠稀疏点仍可能漏圈或跨臂；接近半圈会警告/拒绝，其他情况需人查看整条预测；不保证全局唯一 |

证据：宽带检查 `DIS/src/DiscImageStudio.Core/Calibration/CalibrationRingFitter.cs:100–134`；扫频 `CalibrationAngleSweepReader.cs:35–115,152–187`；边界默认/假定 `DIS/docs/CALIBRATION.md:84–87`；边界绕圈 `CalibrationBoundaryFitter.cs:154–157,202–233,254–268`；十字 `CalibrationCrossFitter.cs:218–242,353–392`（以上未带目录的 `.cs` 在 `DIS/src/DiscImageStudio.Core/Calibration/`）。

### 源码真的做了哪些识别保护

**扫频不是随便相关最高就接受。** 每个 45° 窗口采 17 根射线，方位每 22.5° 移动，共 16 窗口；每个窗口必须找到三站，至少一站角向增益 >0.15，三站增益总和 >0.15。内外站推中站需差 ≤0.050 mm；可用方位之间任一端半径极差 >0.12 mm 判冲突。单站相关 <0.24、幅度 <0.004、角向增益 <−0.60、最佳峰贴有效范围边缘或相距 >0.27 mm 的次峰仍达主峰 94%，都不取该站。RGB 中选信号能量最大的通道，不是只用一个固定亮度通道。它能拒绝一部分同心纹假峰与重复条纹别名，**不能据此证明任意大误差都能识别正确**。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngleSweepReader.cs:22–24,49–103,157–185`；`CalibrationAngleSweepTemplates.cs:38–40,122–132`〕

**边界允许分段，不允许每个点各自乱绕。** 同一段按半径排序展开连续相位；整段共享一个半圈整数，不逐点随意加减 π 来压低误差。相邻角差超过 `0.95π=171°` 则失败要求补点；局部径向跨度 <0.03 mm 或局部长度尺度 <0.3 mm 也失败。不同绕圈解接近时，按至少 0.02 mm 的噪声下限比较代价；自动结果不通过但可以有候选。默认小搜索范围有物理理由，盲目扩大不一定救得回来。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationBoundaryFitter.cs:154–157,233,254–268,285–324`〕

**精标四臂存在 90° 对称性，但跟踪中不能换臂。** 初始臂编号和整体转角处理常量方向；真正关键是半径间连续转角。相邻点按最短角差展开：`>0.995π=179.1°` 失败，`>0.9π=162°` 警告；明显向内回退失败。**如果两点之间实际多绕一整圈，而两端角差恰好很小，这个检查不能凭两端发现漏圈；如果在圆环交叉处跳到另一臂，也不必触发半圈阈值。** 因此源码始终追加“相邻点间没有遗漏整圈”的前提提示，并要求看完整曲线、转弯加点。低残差不是排除了漏圈的证据。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationCrossFitter.cs:225–231,366–388`；`DIS/docs/CALIBRATION.md:95–101`〕

三次轨距与内外半径还可能互相补偿，代码明确警告“低残差不表示参数唯一”。不够 12 个半径/60% 覆盖时退回只修半径；没有稳定改善或不能稳定区分系数时保留原系数。**用户应补充独立半径位置和复刻验证，而不是把点拖到预测线上追求通过。**〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationCubicFitter.cs:15–20,108–135`〕

## 8. 照片质量、拒绝、警告与不确定性

| 检查 | 实际行为 | 证据 |
|---|---|---|
| 源照片尺寸 | 长边 ≤8192 px 且总像素 ≤33554432，超限按比例缩小；转每通道 8 位 BGRA。矫正图随局部像素密度选尺寸，最大 5792²，实体外缘另留 3 mm 画布边。不是精度证明 | `DIS/docs/CALIBRATION.md:19–23,121` |
| 实体轮廓 | 每圈至少 5 点（UI 通常 8）；非有限、重复/近直线、局部集中、盘片过小、孔/外缘比例异常、投影退化均失败 | `DIS/src/DiscImageStudio.Core/Calibration/CalibrationPhotoRectifier.cs:90–116,142–156` |
| 两轮廓残差 | 容许 RMS `max(2 px, 外缘半尺度×0.006)`；任一圈 RMS 超限，或最大偏差 >3 倍容差，拒绝。返回的是像素残差，无镜头/翘曲模型的完整误差预算 | 同上 `:157–164` |
| 粗标条纹不足 | 显示只有宽带估计/不足证据/三站冲突，不提供角度修正。可重拍原盘或修点，非必然废盘 | `DIS/docs/CALIBRATION.md:59–65`；`CalibrationAngleSweepReader.cs:5–13,98–115` |
| 边界自动检查 | 点数覆盖、短片段、相位空隙不够则拒绝；贴边、RMS>0.15 mm、极端残差或多解可使自动 `Succeeded=false`，候选仍可保留 | `CalibrationBoundaryFitter.cs:254–310` |
| 精标点与模型 | 太窄、向内回退、接近半圈等为失败；覆盖偏窄、离群点、搜索贴边、近似候选、不唯一为警告，偏离点标红 | `CalibrationCrossFitter.cs:61–66,218–242,370–392`；`DIS/docs/CALIBRATION.md:97–100` |
| 人工最终放行 | 必须有矫正、当前求解候选、预测渲染完成、人工勾吻合。**放行条件并不要求自动 Succeeded=true，也不要求残差过阈值**；RMS>0.35 mm 或最大>0.8 mm 是警告，非硬性否决 | `DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:317–349` |
| 不确定性表示 | 给 RMS、最大误差、离群数、候选、搜索贴边与覆盖提示；没有发现给每个半径/轨距系数输出经验证的置信区间或“成品落点误差保证” | 同上 `:587–592,739–751,1184–1188`；`CalibrationCubicFitter.cs:122–147` |

上表简写 Core 文件均在 `DIS/src/DiscImageStudio.Core/Calibration/`。没有找到一套全流程“照片过曝百分比、清晰度、照度、最大倾角”的统一准入标准；这里的光学质量多半通过轮廓与可读图案间接体现。不能把允许输入图像尺寸，或只见一个 45° 清楚区域，就写成照片一定能读准。外缘/孔缘完整仍是前置要求，45° 指图案局部可见。〔`DIS/docs/CALIBRATION.md:13,57,83`〕

## 9. 换盘、换桶、换驱动器：有没有自动核对

**有按盘型和品牌/SKU 保存的几何预设；没有找到“自动认出这桶盘、这个压模、这台光驱，所以这套校准仍然有效”的核验链路。** 内置 AZO 43533/43523 甚至列了相同几何，但这是预设数据，不是对眼前空盘的独立检测。用户层按 ID 新增/覆盖预设；它不是逐片几何数据库。〔`DIS/src/DiscImageStudio.Core/Presets/built-in-disc-presets.json:68–90`；`DIS/docs/DISC_PRESETS.md:20–27`〕

读容量代码将设备报告的总量/可写量填回设置，不读一段测试数据来验证旋转相位或轨距；教程也明确相同容量可能不同内外半径，并要求同批、同设备、同设置。保存的 `CalibrationParameters` 有介质、半径、扇区、密度、系数与输出范围；`CalibrationSession` 的模型没有把刻录机序列号、压模、桶号写成必须匹配的几何条件。即使写盘日志有设备信息，也不等于自动限制预设复用。〔`DIS/src/DiscImageStudio.App/ViewModels/CalibrationMediaViewModel.cs:53–95`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationTarget.cs:21–28`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationSessionJson.cs:6–10`；`DIS/docs/CALIBRATION.md:35`；`DIS/docs/CALIBRATION_TUTORIAL.md:38–44`〕

正式写入前的设备支持、盘型、空白、容量、勾选及二次确认，能阻止一部分写错盘和写不下，**不能证明半径、位长、轨距或写入路径偏移相同**。没有在本次校准生成/应用路径中找到 DP `geo` 式数据区计时、按随机带读回拟合、同盘后续追加成品、或成品前测一段数据交叉验证几何。ISO 读取兼容、数据文件区、ECC 可读性与几何校准是不同事情；不能拿“盘能读、容量相同”替代照片/几何验收。〔`DIS/src/DiscImageStudio.Burning/WindowsImapiBurner.cs:1167–1247`；`DIS/src/DiscImageStudio.App/ViewModels/BurnViewModel.cs:686–700`；`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:948–995,1070–1112`〕

## 10. 与 DP 逐阶段比较：哪些值得借，哪些 DP 更差

| 阶段/问题 | DIS 当前实现 | DP 实测、原型或计划 | 建议与短处 |
|---|---|---|---|
| 初始几何 | 读容量，靠品牌预设与照片逐步修两半径/三次轨距 | DVD `geo` 从可读测量盘计时重建几何；已有 GH70N 一张网格盘 8 扫描约 0.03° RMS 的记录，但不是任意光驱保证。CD 也有计时几何及更高阶修正 | 对计时可靠设备，DP 把多次照片拟合缩成数据测量很有价值；遇计时残差大/非理想转速，不能硬套。DIS 的人工独立几何路线值得保留为备用，而非认为 `geo` 永远够用。〔`DP/docs/goals/photo-calibration/design.md:29–34`〕 |
| CD 的 L | 没有独立 L 状态，用照片整套几何拟合吸收可解释弯曲 | L 为读写路径沿轨常数，`θ误差=c+L/r`，计时不能给；同心环不受 L 影响。换读/写路径要重新确认 | DP 只拟合真正缺少的一个量更省事；务必把光驱与写入路径绑定。不能从 DVD 成功推 CD 免照片。〔同上 `:31–44`〕 |
| 粗图案与识别 | 手点六边，地址宽带稳住尺度，三站扫频提供独立角度修正，首末预测中间站 | photo-reader 用非等间距环定位，再读分带伪随机辐条/相对角度；目标是自动读 L | 借 DIS 的**独立中站留出检查、其他方位各自求解再比较、两侧局部重找带边**；不应只看合并相关峰。纹理宽带/护肩与可见性要单独实测。〔`DIS/src/DiscImageStudio.Core/Calibration/CalibrationAngleSweepReader.cs:60–103,125–149`；`DP/docs/goals/photo-calibration/design.md:102–161`〕 |
| 照片定位 | 完整外缘+孔缘，用户修 16 点，透明可核对 | DP 目标是三张转盘照片、不摆正不描点；旧设计甚至写不需盘缘，后来的冻结读取器真盘却有 no_rim 拒绝 | DP 的用户负担低，但当前自动定位/覆盖是弱项，**“不需盘缘”已不能当成兑现的体验**。可借 DIS 叠加轮廓和 mm/像素残差作为诊断或人工补救，默认仍自动，避免一失败就让新手完全无路可走。〔`DP/docs/goals/photo-calibration/design.md:249–261`；`DP/docs/goals/calib-simple/TASK.md:7–15`〕 |
| 大 S 弯、错臂、多周期 | 宽带→宽边界→细十字，显式处理片段半圈及连续相位，仍须人核对漏圈 | DP L 模型只校正 `c+L/r`；不能自动解释任意 S 形残差。旧 design 错误注入曾出现联合误收，尤其局部盘面和中心偏差 | 借 DIS 的退回上一步与“先确认整条曲线”思想：L 解之外留半径/方位残差图，检验是否像 1/r；不符合应报告模型不适用，不能强给 L。旧注入结果不能直接扣到后来的冻结版头上。〔`DP/docs/goals/photo-calibration/design.md:363–385`〕 |
| 多照片可信度 | 单工作图，靠多方位窗口一致性；人可改光照换照片 | DP 三张转盘联合投票，目标交叉验证；当前新手任务记载冻结真盘 12 张仅 2 张单张通过，整组 L 误差约 0.19 mm，无错误读数 | DP 在“用户随手拍就能独立通过”上仍差；应先把可见度/覆盖做稳，不能把联合通过用来掩盖各张几何拒绝。2/12 是一盘一组证据，不是广泛成功率。〔`DP/docs/goals/calib-simple/TASK.md:9,15`；`DP/docs/goals/calib-disc-v2/REPORT.md:7–13`〕 |
| 纹理/极性 | 主校准大多逻辑黑特征白底，物理反相允许；不做手机光谱校准 | 简单盘正在比较亮特征暗底 vs 暗特征亮底、0.5/1/1.5 mm 线、亮边环、约60°重复；以冻结读取器为裁判 | 可借 DIS **50% 宽边界与粗/细分级**来增加可见性；但重复等间距不能把伪随机识别身份抹掉，需保留非等间距/编码差异以防 alias。DIS 黑白逻辑不能证明 DP 的 B 极性光学上一定赢，仍需真盘。〔`DP/docs/goals/calib-simple/TASK.md:17–31`〕 |
| 红边、颜色附加校准 | 不需要知道手机红外截止才能量几何 | v2 红边在理想已矫正/已知截止的合成测试也有 3/59 错收；不是完整原图自动链路；亮度跨盘要约4倍增益 | **这一点 DP v2 计划比 DIS 更绕、风险更大。** 简单盘已正确把颜色任务拿掉；先读相对角度，不应增加不可辨识的灯源/截止波长变量。〔`DP/docs/goals/calib-disc-v2/REPORT.md:38,53,78–88`；`DP/docs/goals/calib-simple/TASK.md:7–11`〕 |
| 同盘、省盘 | 每次应用→新标靶→新盘；主线不做随机带后追加成品 | one-disc 已有一张试盘：RND 内圈 24.06–49.96 mm 保持开放，计时后 NWA=1613968，追加图片在50.53–56.6 mm。用户目视直，尚未扫描验证 | DP 同盘可去掉跨盘外推，但牺牲大片绘图面积、两次写入/会话间隙且要可靠预期 NWA；不能称整盘图片一遍刻好。DIS 的完整盘校准/整盘成品更容易解释。〔`DP/docs/goals/one-disc/plan.md:33–39`〕 |
| 同桶/同驱可迁移 | 人选择预设、教程要求同批同设备同设置；不自动验证 | one-disc 计划 E1 明确比较同桶多张和重复计时，E2 用扫描独立验收；其计划中的 5 张实验预算不是最终产品每次耗盘数 | 借 DIS 保存**原盘生成配方+原图+点位+确认候选**的整套档案，DP 另补驱动器/路径、MID/ATIP与实际计时质量，区分“同桶先验”与“本盘测量”；不把容器标签当几何证明。〔`DP/docs/goals/one-disc/plan.md:13–30`；`DIS/src/DiscImageStudio.Core/Calibration/CalibrationSessionJson.cs:6–10,50–94`〕 |
| 失败放行 | 自动不通过仍可有人为确认候选；透明但容易主观误放 | DP 希望低证据时明确“不知道”，冻结读取器不可为提高通过率改阈值 | **不要照搬无条件人工越过数值警告的成功标签。** 可允许专家导出/试刻，但状态应保留“自动未通过/手工采用”，并把未描位置/复刻当独立验收。DIS 的警告详细、失败后可补点，值得借 UI；DP 自动拒答也需给可执行的重拍建议。〔`DIS/src/DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:317–349,739–751`；`DP/docs/goals/calib-simple/TASK.md:9,15,22`〕 |

**适合现在简单盘直接采用的五件事：** 保留冻结读取器与独立检验；用亮边环改善盘缘定位但别让定位环冒充 L 信号；在不同半径放足够独立标记，给每个半径/方位的有效票与覆盖；检查至少一个不参与拟合的半径或独立方位；失败明确说“缺盘缘 / 可读弧太短 / 模型不像 1/r / 多个相似解”，先重拍同盘。图案重复可扩大照明适用范围，不能减少独立覆盖要求或靠重复票虚增置信。这个建议来自上述源码与 DP 失败记录的推论，本次没有把它实现到 DP 或修改冻结读取器。

## 11. 复现核验与无法确定的事

已完成：20 张 CD/DVD 目标预览（全部枚举 + 历史几何分支）、DVD 灰阶探针假彩和原生 Q 图、2 张几何错误示意、接触图、1 张当前/旧版读取兼容字节示意，共26张PNG；钟尺完整 528906 字节载波文件 [clock_carrier_gray.bin](previews/clock_carrier_gray.bin) 与地址取样函数。反解 `q(r(q))` 的本次参数误差 <1e−12；冻结参考灰度 SHA256 与源码常量一致；各目标范围、六种探针 Q 码存在性检查，以及读取兼容对白/黑/非绘图字节的保护检查通过。**这些是移植自检，不是执行 C# 后做过的跨语言逐字节等价测试。** 源码/输出哈希及参数均在两个 manifest；预览已人工看图检查。

边界/单线/半盘/短弧/旧组合的几何判定按源逻辑移植；参考十字直接用源资源；扫频是源二维示意与地址公式，不包含每种介质后端的全部离散采样、交织、ECC、边界写入效果；时钟尺 PNG 明确是程序自己的增强示意，不是假装实盘微观重建。灰阶探针以合成四级裁块替代外部原图，标签半栅格盖写有潜在浮点边缘差。没有生成镜像、音轨或让 DIS 执行任何代码。

仍不能从本次源码审查确定：

- 家庭用户成功率、平均耗盘量、典型操作时间、真实手机照片最低对比/分辨率/最大倾角；源码阈值不等于真实分布验证。
- 每桶、每压模、每驱动器几何差异有多大，以及保存的预设换速度/写入链路后还能否用；没有真实跨盘计时/扫描实验。
- 相位展开在任意极大扭曲、稀疏点、强反光下绝不误识别；源代码自身依赖无漏圈假设，允许人工采用警告候选。
- 每个拟合系数的独立统计误差与成品落点误差；残差小和位数多都不能替代校准复刻。
- 灰阶探针所需外部原图的原始内容，以及每种字节纹理在具体染料、光源、相机下真实亮暗/颜色；本次 PNG 不作光学效果承诺。
- 真实发布 EXE 是否与此 HEAD 完全一致、所有按钮是否按源码运行、实际写入失败能否恢复；本次遵守要求没有启动、构建或刻录。
- DP 简单盘研究正在进行的最终 A/B 推荐与新结果；这里只按指定 TASK 和已有报告比较，不读取另一个研究进程的中间产物，也没有把旧版 photo-reader 的已知问题推断为新版未修。

源树始终只读；未访问任务禁止名称的路径。所有新脚本、图像、清单与差异文件均位于本工作目录。
