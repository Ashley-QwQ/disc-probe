# Focal geometry 盘点与实施计划

基线：`dev/focal-geometry`，2026-11-15。先提交此盘点，再改实现。检索范围为
`discprobe/`（含网页）、`tools/`、`presets/`、`data/`、相关测试，以及卡片指定的外部脚本。
递归检索排除公共卡禁止的路径；外部资料只读，不修改其他 worktree，不修改 `evidence/atlas/*.py`。

## 公式与边界

集中定义暂定的 **4K 16:9 标准防抖视频焦距 3355 px**，不是照片/native 像素焦距。
旧纸的精确焦距由 `make_rulers.py` 和 `pose_1x.json` 恢复：
`f_photo_native = bbox_x * 206.5 / 120`；
`f_video_old = f_photo_native * 3840 / (8064 * 0.819)`（约 3126，而非用四舍五入值代替原图）。
纸上视频线固定，所以 `H_table_new / f_video_new = 207.8 / f_video_old`；
`H_disc_new = H_table_new - 1.2 - 0.1`。δ 用相机和闪光灯到盘面点的单位向量之和投影到轨道切线，
不再乘经验系数。不能通过调整焦距或模型来强行消除非线性残差。

照片纸的旧网格使用盘面高度 206.5，视频纸使用桌面高度 207.8；两张原纸的线均冻结，
规范高度以任务指定的视频取景为准，报告照片网格这一历史差异。

## 修改清单（行号为修改前）

| 文件、行 | 当前值或用途 | 计划修改与原因 |
|---|---|---|
| `tools/editor_pose_swatches.py:10–16,37–54` | 外部 pose 依赖；206.5；.93；3126；21 cm | 改读仓库内集中几何模块和本地 pose；规范高度由公式求；scale=1；显示实际高度。旧 id `21` 保留用于已有工程键兼容 |
| 同文件 `72–73,89–95` | 色板乘 .93；记录旧焦距、外部来源 | 去掉新色板缩放调用，记录新几何哈希和本地生成器；重建两套 5+255 色板；check 核对全部元数据 |
| `discprobe/web/home/design/pose-swatches.json:9,12,308,400…` | .93、3126、206.5，各手机高度颜色 | 全量再生成，不改材质表/周期/波模型 |
| `discprobe/web/home/design/pose-swatches-custom.json:9,12,299,388…` | 同上，51×5 自定义间距 | 同上；仍为未验证手机的预测 |
| `discprobe/web/home/design/lamp-pose.mjs:3–19` | 206.5；21 cm 特殊插值；固定刻度 | 使用生成的几何常量；实际桌面厘米与盘面毫米直接换算，刻度与色板一致 |
| `discprobe/web/home/design/lamp-controls.mjs:52,106,132` | 写死设计刻度21；四舍五入识别刻度 | 改用新设计刻度，检查拖动、键盘、吸附和提交仍映射至稳定的 rig id |
| `discprobe/web/home/design/editor-ui.mjs:173` | `height:String(cm)` | 按色板 ruler_cm 查稳定 id，避免新高度失配 |
| `discprobe/web/home/design/editor-rig.mjs:15,33,68–70` | 文案21 cm；scale 从色板注入 scene | 仅更新准确高度和校准说明，布局不变；新 scene 不写过渡缩放，旧 scene 可读取 |
| `discprobe/web/home/design/editor-materials.mjs:14` | 读 scene.deltaScale | 保留显式旧工程兼容 |
| `discprobe/web/home/design/lamp-optics.mjs:81–89` | 缺省scale=1 | 缺省已正确，保留显式旧工程兼容 |
| `discprobe/web/home/design/lamp-pose.mjs:36` | 转发非1 scale | 保留旧工程兼容 |
| `discprobe/web/home/preview.js:30,36` | 读取/转发旧工程scale | 保留旧工程兼容；默认已为1 |
| `discprobe/editor_preview.py:35–38,96` | scale缺省1、范围校验、调用swatches | 保留旧工程兼容并明确注释；不新增 .93 默认 |
| `discprobe/simulate_a3.py:81–84,117,150–178` | API默认1，但文档推荐.93 | 改文档为旧工程兼容；底层旧参数保留供回放和本次回归 |
| `tests/test_editor_pose_swatches.py:33–46`、`tests/test_editor_rig.mjs:15–48` | 断言旧标高、.93、3126 | 更新新几何、生成哈希；保留旧工程读取测试，添加新默认不含缩放检查 |
| `tests/test_editor_lamp.mjs:87–103` | 21cm换算/吸附 | 更新为新高度，保留高度往返及旧工程尺度验证 |
| `tests/test_lamp_optics.py:66,87,122` | 显式206.5测试姿态 | 保留：这是覆盖多姿态的测试输入，不是规范高度；运行其 Python/JS 等价性回归 |
| `tools/colour_map.py:30–38` | 任意相机位置的共轴δ图 | 不改：与规范手机焦距无关 |
| `discprobe/pcal.py:365,699–709`、`photo.py:401–407`、`tilephoto.py:188–214,329–351` | 通用照片 EXIF/回退焦距、圆盘位姿 | 不套用手机视频焦距，保留通用照片输入语义 |
| `tools/flash_lut.py:39,67`、`flash_lut_tiles.py:79`、`synth_photo_test.py:27,86`、`photo_l_majority_check.py:157–160` | EXIF或合成照片焦距 | 不改：独立的照片标定/测试，不是主摄视频规范 |
| `presets/`、`data/` | 检索未找到该手机焦距、旧高度或delta_scale依赖 | 新增本地几何数据、δ图及来源；不改原刻录几何预设 |

## 外部来源（只读）与迁入部分

| 外部文件、行 | 当前值或用途 | 处理 |
|---|---|---|
| `D:/disc-probe/docs/goals/showcase/pose/search_low.py:5–13,25–49` | 24/36×8064 native焦距、镜头表和投影 | 只迁入本任务需要的主摄规范几何及单位换算，不运行原 sweep、不改其他镜头 |
| 同目录 `pose_1x.json:5–24,62–97` | camera=(0,28.45,206.5)，flash_y=76.385787…，native framing | 留存相关字段与原文件sha256；新规范使用精确纸上垂足（不移动线） |
| 同目录 `build_deliverables.py:8–9,51–60`、`deliver_1x.py:21–37` | 4096²、160 mm宽、中心像素、r24–58外NaN；输出delta_map_1x | 迁入自足分块生成器，沿用栅格与掩膜，保存 float32 δ 和哈希 |
| 同目录 `delta_map_1x.npy` | 原δ图 | 只读对照验证；新图在本仓库data生成，绝不覆盖原图 |
| `D:/disc-probe/docs/goals/showcase/template/make_rulers.py:20–47,129–159,235–263` | 207.8标线；GX/GY/GXV/GYV；三页PDF/PNG | 迁入tools；冻结两种放盘页，只有高度尺的标线/对应说明改为新值；输出到 D:/dp-dev/tmp/focal，含新旧并排图 |
| 同目录 `build_1x_labels.py:8–14,35–43,49–62` | 旧δ图上采样；--delta-scale/offset | 不移植依赖外部art的刻录工具；仅迁入可复现δ图生成。原已刻标签固定，回归不重新选纹理 |
| `D:/disc-probe/docs/goals/iso-cleanup/recipes/IMG2654-1x21-H.json:7,80–99` | .93、offset=0；原标签sha；记录已刻SHOW-E | 用作已刻盘回归来源，核验标签/纹理哈希，提取各标签空间样本，记录预览证据，报告每块Δδ/色相而非伪造重新实拍 |
| `C:/disc-probe-scratch/lambda-review/REPORT.md`、`focal_chain.py:11–37`、`refit_focal.py:23–24,61–74` | 旧3126与焦距敏感性研究 | 仅作为卡片背景；不使用镜面点定焦、不改研究文件 |

`0.93` 的其余命中：`geo.py:65,77` 的相干度、各 selftest 的读数、网页渲染器tray_mul、
材质JSON中的周期/颜色/波表数值，均非焦距过渡系数，保持不变。
通用 `simulate.py`、`editor_ops.py` 默认33cm与旧通用swatches展示不改为手机规范高度，避免影响未选手机的工程。

## 验证与交付

1. 新增几何公式、δ图坐标/掩膜、来源哈希、生成一致性、旧工程兼容和网页刻度测试。
2. 对固定已刻 SHOW-E 原标签逐材质报告 Δδ（均值/最大/分位）与色相残差；若差异明显，保留数值并停止调参，明确未达成保色验收。
3. 原纸与新纸放盘页像素比较应为0差异；高度页仅标线及高度说明改变。渲染PDF核对Letter实际尺寸与中文。
4. pytest使用 `-n 2` 和D盘临时目录，最后跑一次全部允许路径的 `tests/test_*.mjs` 及相关Python测试。
5. `CARD_REPORT.md` 按提交写修改、命令、结果、未测、待定焦距及重跑清单，然后本分支提交，不推送。
