# MS · 拍照沿轨常数手动对齐

分支 `dev/photo-manual-slider`，基点 `a7b5fbf`。2026-11-20（多伦多）完成最小版本，早于周六 18:00 交付时限。

## 提交

- `8f67069` 在拍照页加入手动对齐，按冻结读取器留下的单应矩阵投影标靶圆环和 PN 条纹边界。拖动 L 或整体转角时实时重画，原有缩放、平移和专注视图可用于检查。保存由 core 换算并应用到 ISO 和预设。预设和 ISO 记录区分 `manual-slider`、`manual-cli` 和已有自动来源。
- `6b4f500` 补充人工值超出几何可用范围时的双语提示，更新旧 core 和拍照流程测试。
- `dadd0c6` 盘库回归测试等浏览器的异步返回完成后再点下一步，避免两次导航交叠。

## 使用和范围

- 选照片，点「手动对齐」。DVD 范围为 ±10 mm，方向键每次 0.025 mm，约为 1/200 个 DVD 扇区。CD 范围为 ±300 帧，方向键每次 ¼ 帧（约 0.041 mm）。转角范围为 0–360°，方向键每次 0.05°。按住 Shift 时步长乘 10。
- 停下后显示「边界吻合区块」。这项读数用冻结投票函数在当前 `c + L/r` 处评估信号。吻合区块少于 4 个、达不到两个角区和两个半径带，或圆环配准未锁定时，提示「可能没对准」。仍可保存。
- 保存写入该几何测量目录内的 `photo-manual.json`。同一测量的自动读数仍留在 `photo.json`。新的出图和预设优先采用已保存的有效人工值。已出图的 ISO 重开时核对它自己带的来源记录。
- 最小版覆盖拍照页现有的 PN 标靶。没有可用盘缘单应时，页面请用户等待读取或换一张拍全盘的照片。已有单应、圆环未锁定时，可以叠图并看到警告。

CLI 用法如下。最后一行的容量换成这张空白盘的实际容量。

```powershell
python -m discprobe photo --run results/<测量目录> --media dvd --manual-l -2.291
python -m discprobe calibrate --geo results/<测量目录> --media dvd --sectors 2295104 --preset presets/manual.json
```

## 密封标靶实拍

用 2026-11-10 密封标靶两张原图重新跑冻结读取器，两张都因角度覆盖不足拒答，但保有已锁定的圆环单应。已知答案为 −2.291 mm。验收脚本从读取器的起始位置调节滑块，并在同一转角将 L 增加 2 mm 测偏离分数。

| 原图 | 滑块 L（mm） | 转角 | 与已知值之差（mm） | 对齐 | L 偏离 +2 mm |
| --- | ---: | ---: | ---: | ---: | ---: |
| IMG_7500 | −2.200 | 268.10° | +0.091 | 6 / 66 | 0 / 66，提示可能没对准 |
| IMG_7508 | −2.150 | 203.40° | +0.141 | 6 / 54 | 0 / 54，提示可能没对准 |

这两张有足够条纹的 DVD 照片上，脚本调节误差约 0.09–0.14 mm。起点来自冻结读取器，分数在邻近位置有平台。人工目测重复性、CD 实拍精度及换盘后的精度未测。需要比这两张实测误差更小的偏差，或者照片只有单一半径带、反光严重、圆环未锁定、多张照片调出的值明显不一致时，建议用 DIS 精校准。

PCAL-C 5-02 已有刻录登记。检查了登记关联的对照目录和本地校准照片目录，未找到可核实归属 5-02 的原片，实拍未测。

## 验收和证据

- `node --test tests/test_photo_wire_browser.mjs`，设置 `PHOTO_ALIGN_FIXTURE` 和 `PHOTO_ALIGN_SHOTS` 后，无头 Edge 通过 CDP 实测两条滑块、鼠标拖动、方向键与 Shift、低分仍可保存、预设显示人工来源。读照片、打分、保存及预设导出使用独立回环 core。另发 `POST /api/catalogue` 核对实际目录保存，返回 `manual-slider` 和 −2.200 mm。日志见 `D:/dp-dev/tmp/manualslider/alignment-browser-final-proof.log` 和 `catalogue-proof.log`。
- 截图共 8 张，位于 `D:/dp-dev/tmp/manualslider/shots`，文件名为 `manual-{1440|390}-{light|dark}-{zh|en}.png`。1440×900 与 390×844 均检查两条滑块和读数可同时看到、没有横向溢出。8 张尺寸和哈希均已核对。
- `python -X utf8 D:/dp-dev/tmp/manualslider/compat.py`。与 `a7b5fbf` 比较，CD/DVD × 自动采用/无照片共 4 组的 ISO、预设、`photo_l` 和 ISO 旁记录合计 16 项 SHA-256 全部逐位相同。每种盘的自动采用与无照片 ISO 彼此不同，测试确实覆盖了写入变化。详见 `compat-final.log`。
- `python -X utf8 D:/dp-dev/tmp/manualslider/cli_check.py`。走真实 DVD CLI 保存 −2.291 mm，随后独立导出预设和 4096 扇区的 ISO 追加段，抽样扇区验证通过。两处记录均为 `manual-cli`。ISO 为 8,388,608 字节，验收后仅留 SHA-256 和日志，见 `cli-check-final.log`。Python 测试也覆盖 CD 帧换算、预设和旧 ISO 重开。
- `python -m pytest -n 2 --basetemp D:/dp-dev/tmp/manualslider/pytest-final -p no:cacheprovider tests/test_photo.py tests/test_photo_l_image.py tests/test_along_track_preset.py tests/test_gui_handshake.py tests/test_webui.py tests/test_web_security.py tests/test_webui_catalog.py tests/test_web_guidance.py tests/test_read_completion.py tests/test_presets.py tests/test_dis_pitch.py -k "not photos_through_command"`，301 项通过。旧的全原图测试会建立一个命名触及路径限制的 pytest 目录，已排除。真实冻结读取另用本卡的两张密封原图跑过，保留全组存档复算测试。新 API 在空白图片上的测试触发冻结读取器已有的空切片警告。
- `node --import file:///D:/dp-dev/tmp/manualslider/edge-adapter.mjs --test --test-concurrency=1 <tests/ 下全部 test_*.mjs>` 跑 56 个文件，收集到 69 项。首轮 65 项通过，4 项失败。修复后单独重跑失败所在的四个文件，10/10 通过。见 `node-suite.log` 和 `node-followup-final.log`。适配脚本把原用 Edge 命令行导出 DOM 的四个测试改用 CDP 取 DOM 和截图，无需改其断言。
- `git diff a7b5fbf --quiet -- discprobe/pcal.py` 通过。冻结读取器 Git blob 为 `92641a3de641449f51192249264d087f4e282e61`，与基点一致。实拍和浏览器验收均使用独立回环服务或脚本夹具。未对 8765 服务执行请求、停止或重启。

## 由 Claude 转达

- 与 RWA/RWB/RWC 汇合时，优先核对 `calibrate.js` 的 `paintPhoto`、`photoNavigation`、`realSave` 插接点。API 1.2 加了可选能力 `photo-manual-alignment`，旧 core 仍能打开原来的拍照流程。
- 由审查者决定是否补 5-02 原片，以及是否在更多光照、盘种和拍摄角度上标定提示阈值。这轮阈值只作辅助，观感打磨留到后续。

STATUS: DONE
