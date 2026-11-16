# 大厅 base 夜色试烤（卡 T，待审查）

本轮只渲 `F_lobby_a/base` 的 paper、dark 两个主题，Blender 5.2.2 LTS / CPU / 8 线程 / SS=4。原网页资源保持原图，截图的新版本只在浏览器请求中替换 base。其余八个夜色层仍是旧图；没有批量烤图。是否继续由审查看图决定。

固定配方：夜色 amb 三通道 .64、gain 三通道 2.4、add 三通道 0；segment 光池 sigma .42 → .23394（×.557），线稿、原有材质色和纸色参数不变。灯罩自发光、牛皮纸、铜色 LED 未改。两份修改后的 renderer 与依赖已存档到 `tools/night_lobby/`。

## 审查图

- `base_trial_dark.png`：新 base 原始 PNG（2560×1791）。
- `base_old_dark.webp`：提交前旧 base，原字节副本。
- `base_trial_dark.webp`：使用原配方 quality 92 / method 6 编码，仅供试览。
- `lobby_old_dark.png`、`lobby_trial_dark.png`：真实本地虚拟练习后端、无头 Edge，1440×1000；中文、夜色、关闭动作、固定时间。新图仅替换 base 响应，裁切与位置相同，页面错误及 CSP 错误均为 0。

## L*（D65，sRGB 线性化后计算）

| 图 | 光池中心最近可见桌面点 / 邻域中位 L* | 四角 L*（左上 / 右上 / 左下 / 右下） |
| --- | ---: | --- |
| 旧 base WebP | 15.374538 / 15.374538 | 4.628894 / 4.628894 / 5.070039 / 5.070039 |
| 新 base PNG | 11.041125 / 11.041125 | 4.660415 / 4.660415 / 4.660415 / 4.660415 |
| 新 base 试编码 WebP | 11.456290 / 11.456290 | 4.628894 / 4.628894 / 4.628894 / 4.628894 |

光池定义中心投影为 (856.818619, 1117.521146)；表中使用最近可见桌面点 (842, 1074)，距离 45.974793px。若距离非零，表示中心遮挡或不在安全桌面掩码内，不声称测到了被挡住的中心。桌面由原始 ID=1 的 SS 子像素全覆盖掩码确定，向内收 3px，再排除所有可见前景层的 alpha>0 像素及其外扩 3px 区域；邻域为该点周围 5×5 中仍在掩码内的 12 个像素。四角各取 5×5 中位数，包含背景/地面，不称为桌面四角。

光驱顶面最亮 / 最暗 L*：**30.155218 / 25.647402**。这是网页中保留的旧 `newplan_dark.webp`，新旧截图均相同；本轮 base 不包含光驱，因此它不代表新配方下的光驱。ROI 来自该旧层原场景 `room_lobby3_final.blend` 的 `drv_SHELL_top_cover` 朝上面投影（法线 z>.55），收进 3px，只取 alpha=255，且 7×7 邻域各 RGB 通道极差均 ≤6 的 68018 个像素，以排除内部折痕/轮廓的亮线及周边 3px。坐标、RGB、掩码和来源 SHA-256 见 `measurements.json`、`drive-top-mask.png`。

## 纸色核对

使用现有 `tools/night_b_export.py` 原函数（AST 提取，无改写）、原 lobby.json base 裁切、manifest 记录的 (92, 6) 编码；只计算这一张，不触发其它层读取/导出。

| RGB mean | alpha mean | >8 比例 | Night B 绝对门槛 | 结果 |
| ---: | ---: | ---: | --- | --- |
| 0.023598097548 | 0.000000000000 | 0.026368823283% | ≤.3 / ≤.02 / ≤.1% | 通过 |

本张不在历史差值白名单内，未使用历史差值或放宽门槛；未改写仓库已有纸色文件或正式 WebP。完整未舍入值见 `paper-check.json`。

## 复现与证据

主命令：`python -X utf8 -B tools/night_lobby/render_trial.py`，完整 Blender 参数与耗时见 `F_lobby_a-run.json`（本次 1027.416 秒）。核对、截图、测量分别用 `check_trial.py`、`capture_trial.mjs`、`measurement_masks.py`（Blender 后台）、`measure_trial.py`，最后用 `verify_trial.py`。首次准备顺序为 prepare_trial.py → build_scripts.py → inspect_scene.py（Blender 后台）→ render_trial.py；输入原件保持不变。

完整场景、EXR、PNG 纸色核对输入和日志保留在 `F:/dp-archive/tmp/lobbypool/trial/`，仓库审查副本在 `docs/cards/lobby-pool-trial/`。不把本轮称为大厅全部层完成或视觉验收通过。**到这里停止，等待审查。**
