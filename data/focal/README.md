# 主摄 1× 几何数据

唯一待定焦距常量为 `discprobe/focal.py:VIDEO_FOCAL_PX`，单位是 3840 px 宽视频的像素。
当前暂取 3355；不是照片或原生感光面像素。等待用户用尺子在两高度复测后定稿。

日常再生成，不需要任何仓库外的 showcase 文件：

```powershell
python -B -X utf8 tools/focal_geometry.py
python -B -X utf8 tools/editor_pose_swatches.py
python -B -X utf8 tools/focal_regression.py --out tools/focal_data
python -B -X utf8 tools/focal_regression.py --previews --out D:/dp-dev/tmp/focal
python -B -X utf8 tools/make_rulers.py --out D:/dp-dev/tmp/focal
```

`legacy.json` 冻结旧机位的必要字段及来源哈希。`pose_1x.json` 是新机位与δ图清单。
`delta_map_1x.npy` 为 float32 4096×4096、160 mm 见方、像素中心取样、x向右/y向上；
r24–58 mm 以外为 NaN。保留原图的栅格口径；它不是 6000×6000 的刻录标签图。
大图按需生成到仓库外的 `D:/dp-dev/tmp/focal/cache/`，不进 git 或发行包。
可用环境变量 `DISC_PROBE_FOCAL_CACHE_DIR` 覆盖目录；元数据始终记录默认值，
避免本机缓存路径影响版本化哈希。`tools/focal_geometry.py --check` 不依赖已存大图，
会重新生成临时文件，比对元数据中的 SHA256 后删除临时文件。

`tools/focal_data/show_e_samples.json.gz` 无损压缩保存哈希匹配的 SHOW-E 原标签细胞位置，全部69种纹理都有样本；
主要按0.4mm网格抽样，极小纹理另保留原细胞中心。
18块原盘对照尺的边界也已保存。同目录的 `regression.json` 报告每种纹理和每块尺的 Δδ，未重新挑纹理。
同目录的 `show_e_preview.npz` 是原标签的600×600中心抽样，仅用于并排预览，不能当作原刻录文件。
这些文件仅供离线工具和测试使用；样本解压后的字节和原 SHA256 保持不变。

`tools/focal_capture.py` 是一次性来源提取工具，重新提取才需要外部原始文件；
它核验原标签与纹理哈希、检查旧δ图的坐标口径，不会写入外部目录。
已刻配方已找到；这张盘的历史 alpha 旧预览尚未定位，本次旧预览为按旧参数重建。

保留旧工程中的显式 `delta_scale`/`deltaScale` 读取。已有标准 rig 的稳定 id `21` 沿用，
加载后跟随新标高和 scale=1；没有 rig 的任意旧机位仍按其显式旧参数回放。
新用户看到的是22.3cm，内部 id 不显示为旧21cm。

照片放盘页原先按盘面高度算线，视频页按桌面高度算线。两页均保持原样；
本轮规范高度以视频九宫格为准。照片页与新尺并用仍有约0.6%的历史基准差，未重新实拍。
