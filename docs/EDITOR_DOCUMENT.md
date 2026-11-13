# DP 编辑器作品 v2

保存文件仍是 JSON（`.discdesign` 或 `.json`），`format` 为 `disc-probe design`，`version` 为 2。只生成设计数组，不包含设备命令或扇区写入代码。

## 坐标与图层

整盘 120 × 120 mm，盘心 (0,0)，x 向右、y 向下，从数据面看；正角顺时针。数组从左上逐行排列。每格取中心，坐标和半径按 `floor(x*1e6+.5)/1e6` 量化。这个数只是计算规则，不是实刻精度。

`layers` 从底到顶排列；每层有 `id,name,visible,locked,opacity,x,y,width,height,rot`。位移、宽高用 mm，旋转用度。锁定禁止编辑，不改变输出。`sourceKind` 区分 `bitmap,svg,shape,stroke`；为兼容旧网页，运行时的 `kind` 仍可为 `image`。

位图保存 `raster:{width,height,rgba}`：rgba 是原始 RGBA8 字节的 base64，不依赖 PNG 解码器的颜色管理。SVG 另保存 `svg` 原文；网页栅格化后把同一 RGBA 存在文档旁字段中。**Python 不独立解析 SVG**：没有栅格副本就明确拒绝，不新增包。普通图片保留 `original`，页面另保留 `picture` PNG 以兼容旧读者。合成以 RGBA 副本为准，不会在导出时重新解释原图。

`shape` 保存简单参数：`type:rectangle|ellipse|polygon|line|stroke`，点在本层归一化坐标 [-.5,.5] 中；polygon 用奇偶填充，line/stroke 用线段距离和归一化 `stroke` 宽度。变换时逆矩阵回本地坐标；源图用最近邻采样。原图的工作副本最长边最多 2048 px，保留原文件但不会假称恢复了被缩小的细节。

不透明度用固定 4×4 有序覆盖，把上层材质与下层按面积混合，不对两种材质的 RGB 插值。完全透明不覆盖，完全不透明覆盖。矩形和椭圆边界不含外沿；多边形使用标准射线奇偶规则。

## 选区

`maskGrid:{width,height,left_mm,top_mm,cell_mm}` 默认 600²、原点 (-60,-60)、格宽 0.2 mm。`selections:[{id,name,bits,definition?}]`；bits 是逐行 **每格一字节 0/1** 的 base64，不是压缩位流。`activeMask` 是当前选区 ID。保存的 bits 是事实；definition 只供说明，不会偷偷重新计算颜色选区。

工具：rectangle (`a,b`)，lasso (`points`)，ring (`inner,outer`)，sector (`inner,outer,start,end`)，colour (`seed,tolerance,contiguous`)。颜色容差为 RGBA 四通道最大差，和初始种子比较；相连模式用四邻接。扇形沿顺时针跨 0°，跨度达到 360° 表示整圈；相等角度表示空集。圆环内沿包含，外沿不包含。

替换、加、减、交分别是 B、A∨B、A∧¬B、A∧B。Shift / Alt / Shift+Alt 对应加 / 减 / 交，也有可见下拉菜单。合成时把保存蒙版最近邻采样到刻录格子；**5 µm 刻录格子不会把 0.2 mm 蒙版变成 5 µm 精度。**

## 材质与填充

`materials` 是项目稳定材质表，数组下标就是 uint8 槽号。0 为背景 B9；最多 256 项。每项至少 `id,spec`；还可存 `rgb,period_um,risk,period_conflict,template_name`。材质身份用 ID，不能用 RGB 或当前槽号代替。

打包的 `swatches.json` 与模板任务同名字段一致：`schema_version,source,pose,swatches`，swatches 为名字到记录的对象；记录使用 `kind,spec,periods_um,periods_T,srgb,hex,id,source,risk,period_conflict`。网页加载时把 srgb/periods_um 转成项目内部 rgb/period_um。全部 255 个 single 来自合并色板，预测色沿用现有 `tools/lut_scatter.py` 的一阶色谱，默认机位在 3 点钟方向 r=40 mm 取样。模板已导出的 16 个 single 保留其确切 RGB 和 ID；不把五个灰阶混合配方冒充单材质。

这些颜色是模型占位，尚未经照片验证，不保证盘面各处或 CD/BD 的颜色。只有带 `template_name` 的材质（下载的模板色）按导入图的精确 RGB 自动映射，同色时按项目槽顺序；色板其余条目的导入 RGB 大量重复（145 条是 50,50,50），不再用来匹配。其余像素按图层的影调和抖动变成深（dark 槽）或浅（背景）两种，见下节；图层填充和选区填充仍然覆盖它。

`assignments` 每项有 ID，以及 `layer` 或 `selection` 二选一的目标；填充为以下三选一：

- `material:稳定ID`。
- `pattern:{version:1,pattern:diamond|dots|stripes,coordinates:cartesian|polar,pitch_mm,size_mm,angle_deg,origin_mm,phase_mm,reference_radius_mm,segments?,materials:[ID,ID]}`。复用原型整数量化规则；图案固定在盘坐标，物体变换只改变覆盖区域。
- `effect:{kind:flow|ox|merge|sync,y1,y2,wavelength_um?}`。沿用旧页面已有的目标机位场，核心根据一阶光栅式在本项目材料中选最近周期；光学预测仍待实盘验证。选区效果以整盘为区域，图层效果以图层框为区域。

先按图层顺序合成，层内填充按记录顺序覆盖；然后按记录顺序应用选区填充。隐藏层不输出其层内填充，锁定层仍输出。选区填充独立于图层。最后裁切 `annulus_mm`；默认 DVD/BD 24–58 mm，CD 26–58 mm（保留文件系统）。示意范围不是几何测量。

## 影调与抖动（2026-11-12）

位图图层可带 `tone:{brightness,contrast,highlights,shadows,dither,strength}`：前四个是 -100…100 的整数，`strength` 0…100，`dither` 为 `floyd-steinberg`（默认）、`blue-noise`、`ordered`、`clustered`、`threshold`。没有 `tone` 就用默认（误差扩散、强度 100、其余 0）。核心 `discprobe/editor_tone.py` 与网页 `design/tone.mjs` 是同一规则，全用整数运算，`tests/test_editor_ops.py` 逐格对比：

- 灰度：最近邻取到的源像素 `floor((2126 R + 7152 G + 722 B) / 10000)`。
- 影调表（每个灰度 u）：`v = floor((floor((2u−255)(100+contrast)/100) + 255 + floor(255·brightness/100)) / 2)`，夹到 0…255；再加 `floor(2·shadows·v·(255−v)² / 6502500) + floor(2·highlights·v²·(255−v) / 6502500)`，再夹到 0…255。全零时是恒等。
- 参与抖动的格：落在图片内、alpha>0、没有命中模板色的格。命中模板色的格用那个材质；透明格不参与。
- `threshold`：v < 128 为深。`ordered`（8×8 Bayer）、`clustered`（8×8 网点）、`blue-noise`（页面原有的 32×32 秩表）：按全局格 (i mod N, j mod N) 取秩 r，`200·N²·v < 25500·N² + 255·strength·(2r+1−N²)` 为深。
- `floyd-steinberg`：每个图层一份误差，单位 1/1600 灰度；偶数行从左到右、奇数行从右到左（全局行号）；`v' = v + floor((误差+左邻进位)/1600)`，`v' < 128` 为深，`e = (深 ? v' : v'−255)·strength`，下一格进位 7e，下一行 (x−方向) 3e、x 5e、(x+方向) e；遇到不参与的格，行内进位清零。每行只走第一个到最后一个参与格之间。

抖动在**正在合成的格子**上做：`compose` 和网页导出用作品的刻录格子（20/10/5 µm），画布在放大到 1 格 ≥ 1 像素时由 worker 用同一合成器算出屏幕上的那一片刻录格子（`design/exact-view.mjs`），所以画布、核心 `compose` 和 ISO 是同一批格子。缩小看时画布在 420 格预览网格上抖动，只代表观感。预览页的"设计稿"用 1200 格网格，同样只代表观感。

## 迁移与 CLI

v1 `.discdesign` 图层补齐 ID、可见性、锁定、蒙版和材质表；保留 PNG、原稿、变换和旧 tone/scene 元数据。旧 fx 区域转换为矩形目标和同名效果记录。旧影调参数保存在文件中，但新版材质合成使用上述确定采样和覆盖规则，不能承诺复现旧误差扩散的逐位结果。`edit` 的旧路径型 JSON 继续由原 `design.py` 读取，本次没有替换那个格式。

```powershell
python -m discprobe compose work.discdesign --out design.npy
$textures = (Get-Content design.textures.json -Raw | ConvertFrom-Json).textures
python -m discprobe image --geo latest --design-npy design.npy --textures $textures --output iso/work.iso
```

第一条生成 6000² / 12000² / 24000² 的 uint8 标签图（`cell` 为 .02/.01/.005 mm）及 `.textures.json` 顺序表。第二、三行只是后续调用示例，本任务没有执行写盘。网页 `/api/compose` 调用同一核心，保存工作 JSON 和设计，再交给现有 `image`。输出必须配对应材质表，不能当 bool 使用。CLI 分行处理并写入 mmap，避免整盘坐标阵列。

验收代码：`tests/test_editor_ops.py`、`tests/test_editor.mjs`；共享选区向量和原型图案夹具在 `tests/fixtures/`。完整盘面的两端 hash 记录在 `evidence/editor/compose-parity.json`。这是列出的参数和运行环境的有界一致性证据，不是任意平台所有浮点边界的数学证明。

## 第二轮显示与操作

材质表中的导入 RGB 和烧录槽号保持不变。界面另用 `swatches.json` 的 `preview_lut` 计算并缓存显示色：采用已有 `simulate` 的光谱响应、环境项、增益 4、0.6 饱和度和 sRGB 编码。打包文件中有独立 LUT 的 5 种单字节使用各自的响应；没有独立 LUT 的配方按周期比缩放 A5 响应，属于预测近似。此显示过程不参与标签合成。研究色板变化时，以 `tools/editor-material-ids.json` 保存的第一轮 255 项定义维持项目身份与导入匹配。

选区记录可增加 `named:false` 表示临时蒙版；它仍参与保存、合成和撤销，只是不列入命名选区列表。保存为命名蒙版会复制记录并写 `named:true`。旧记录没有这个字段时仍列出。界面工具键为 V/R/F/C/G/W/Y/N/H；Space 临时手形，松开恢复；画布键盘绘制使用 Enter 起笔/完成。

## 材质分区与灯下视图

以下为第三轮记录；当前灯下显示按后面的“第四轮”执行，已移除 JS 光学预览。

默认“设计”是中性细纹的材质身份图；“灯下”是当前相机/灯位的逐像素预测。显示模式不参与 `compose`，不改变图层、蒙版、材质 ID 或烧录标签。旧界面的 `orig` 显示状态回到默认设计视图。

灯下采用 `simulate.along_track` 的切向 δ：每点 `λ_nm = period_um × δ × 1000`。一阶波长不在 400–700 nm 时只显示低亮中性环境项。在范围内沿用独立谱 LUT，缺少独立谱的配方按周期比缩放 A5 响应，再用既有增益、0.6 饱和度和 sRGB 编码。此处保留多字节谱近似和待照片验证的边界，不声称完全复现真实盘面。δ/径向分量缓存仅由机位和采样大小决定，最多保留 4 组；切换显示和修改填充分别复用几何缓存。当前查看位置 `lookY` 和 `scene` 的灯位与原界面一致，后续角度控件可以继续驱动它们。

## 第四轮：核心模拟视图

文档版本和烧录合成规则不变。“设计”仍是材质身份图。“灯下”通过 `POST /api/editor-preview` 返回核心 `simulate.render` 的 PNG，使用整份文档合成的 uint8 材质标签图。它与 `python -m discprobe simulate --work work.json --output lamp.png --size 942` 使用同一个适配器和核心。机位的单位为 mm，x 向右、y 向上；网页从 `scene`/`lookY` 转换坐标。预览请求不写作品或操作光驱。

请求体为 `{document,pose:{camera:[x,y,z],flash:[x,y,z],rotate:0},size:942,quality:"full"}`。网页尺寸限制 200–2048 px，先请求 200 px `draft`，再请求盘面实际显示像素大小的 `full`。后者沿用发布版约 0.06 mm 细采样、线性光平均、沟槽响应与 `PHOTO_SATURATION`、sRGB 编码。旧的一阶硬裁切不再使用。

PNG 缓存按规范化文档 SHA-256/机位/尺寸/质量区分；合成数组另缓存。HTTP 渲染串行，PNG 有数量/字节上限，常用设计数组有 96 MiB 总量上限。浏览器在机位停顿 220 ms 后重算，舍弃过期响应。预览本身不写回文档。

`/api/editor-swatches` 和 `swatches.json.display_colours` 由同一核心的 `material_swatches` 生成；显示 RGB 与导入匹配 RGB 分开。单字节使用现有谱数据，多字节缺少独立谱时按周期缩放 A5 响应，近似统一在核心。所有显示仍是模型预测，等待照片验证。作品入口本轮输出单张 PNG；原 bool 模拟的 12 格图接口不变。
