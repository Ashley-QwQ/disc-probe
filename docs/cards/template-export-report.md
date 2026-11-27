# TE 设计模板导出

## 提交

- `d275eb1`（`dev/template-export`）加入 5、10、20 µm 透明模板、独立引导 PNG、按格距返导与原像素合成。编辑器和 CLI 使用同一生成器。文件名含格距、批次、扇区数、相机坐标、盘片旋转角及机位指纹，包内说明记录完整的相机和光源坐标。

## 输出及往返

两张 PNG 均为同坐标的 120 × 120 mm RGBA 图片。选择独立 PNG 是为了让 Photoshop、Krita、Procreate 用户可以分别打开作画底稿和参考图，并在导出时直接隐藏参考图层。引导图画出可刻环带、内外圆、中心孔、0.5 mm 安全边距和 12 点箭头轮廓。DVD 使用当前机位预测的一阶可见弧段。箭头在数据面 12 点，沿半径 43.5–52.8 mm。

| 格距 | 底稿和引导图尺寸 | 每像素 | DPI | 本次底稿 / 引导 PNG 字节 | 标记返导误差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 µm | 24,000 × 24,000 | 5 µm | 5,080 | 10,057,075 / 12,934,737 | 0 px |
| 10 µm | 12,000 × 12,000 | 10 µm | 2,540 | 2,515,118 / 3,807,166 | 0 px |
| 20 µm | 6,000 × 6,000 | 20 µm | 1,270 | 628,913 / 1,148,434 | 0 px |

5 µm 的一层 RGBA 展开为 2,304,000,000 字节，约 2.15 GiB。网页在下载前显示这个数字。核心按 96 行一条生成 PNG，浏览器收取 ZIP 和返导用的 1,200 × 1,200 工作预览。带原 DPI 或模板文件名前缀的 PNG 走普通图片导入。软件去掉或改写 DPI 后，可选「导入模板作品」。两种导入方式都按 120 mm 居中，匹配作品格距。原画随 `.discdesign` 保存，核心合成读取原像素。

## 验收

- 在 RITEKF1 离线几何夹具上逐档运行 `python -m discprobe template --geo <geo.json> --grid <5|10|20> --pose 0,75,350,-40,95,350 --rotate 30 --out <目录>`。读取两个 PNG 的尺寸及 pHYs，确认三张底稿整图透明。依次在 5 µm 的 (17285, 7157)、10 µm 的 (8642, 3578)、20 µm 的 (4321, 1789) 写入一个不透明像素，核心合成各命中同一个像素。以 `6dec7ab` 比对旧模板默认导出的 6 个文件，逐字节相同。普通图层的 6,000 × 6,000 合成数组也逐字节相同，SHA-256 为 `13a8d91d22bdcbe3beb8d7329ab8b1a69ab2ebee9b76d004228ecbcb3cd4daa6`。[CLI 记录](D:/dp-dev/tmp/template-export/logs/cli-acceptance.json)
- 用 Node 脚本和 CDP 驱动无头 Edge。20 和 5 µm 的网页 ZIP 分别为 708,053 和 4,694,096 字节，两个包的每个成员都与 CLI 文件逐字节相同。等待 5 µm ZIP 时页面仍刷新了两帧。三档都在编辑器返导，10 µm 走无 DPI 的显式入口。20 µm 保存、重开作品后走真实 `/api/compose`，6,000 × 6,000 输出只有 (4321, 1789) 一个非背景像素。[CDP 记录](D:/dp-dev/tmp/template-export/logs/browser-template.json) · [字节、坐标和截图核验](D:/dp-dev/tmp/template-export/logs/verified-artifacts.json) · [验收脚本记录](D:/dp-dev/tmp/template-export/logs/browser_grid_acceptance.mjs.txt)
- 纸色和夜色各有中、英文截图，均为 1440 × 1000，显示 5 µm 选项及内存提示。[纸色中文](D:/dp-dev/tmp/template-export/shots/template-paper-zh.png) · [夜色中文](D:/dp-dev/tmp/template-export/shots/template-night-zh.png) · [纸色英文](D:/dp-dev/tmp/template-export/shots/template-paper-en.png) · [夜色英文](D:/dp-dev/tmp/template-export/shots/template-night-en.png)
- 逐文件执行 `node --test tests/<文件>.mjs`，60 个文件全部通过。首轮的两项 Disc Lab 测试被 `DISC_PROBE_NO_DRIVES=1` 屏蔽了虚拟光驱，在仅暴露 Disc Lab 虚拟光驱的配置下单独重跑，两项通过。最终另跑 `node --test tests/test_editor_w245_browser.mjs`，18 项检查通过，纸色和夜色各两档的预览 SHA-256 都是 `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`。[逐文件记录](D:/dp-dev/tmp/template-export/logs/node/results.json) · [重跑记录](D:/dp-dev/tmp/template-export/logs/node/retry-results.json) · [W245](D:/dp-dev/tmp/template-export/logs/node/final-test_editor_w245_browser.log)
- `python -m pytest -n 2 tests/test_template.py tests/test_template_grid.py tests/test_design_compose_route.py tests/test_editor_ops.py tests/test_editor_colour.py tests/test_editor_preview.py tests/test_editor_pose_swatches.py tests/test_editor_texlib.py tests/test_lamp_optics.py tests/test_gui_handshake.py` 通过 175 项。最终针对文件名、模板和合成重跑 `python -m pytest -n 2 tests/test_template_grid.py tests/test_template.py tests/test_design_compose_route.py`，通过 22 项。测试期间使用 D 盘长路径的 TEMP，临时镜像、原始夹具和 Edge 配置已清理。[回归](D:/dp-dev/tmp/template-export/logs/pytest-final.log) · [最终聚焦回归](D:/dp-dev/tmp/template-export/logs/pytest-grid-final.log)

## 未测、限制与转达

- Photoshop、Krita、Procreate 未实机测试，各软件和设备能打开的最大画布尺寸也未测。单张返导 PNG 上限为 256 MiB，多个图层还受作品总大小上限约束。
- DVD 弧段是模型预测，未用实盘照片验证。CD、BD 提供几何引导。可刻环带以批次几何和扇区数为准。
- 编辑器中的剪切或删除像素选区会将该图层转为工作预览分辨率。仅移动、旋转、缩放或改影调仍以原图合成。DVD 拟合色彩使用预览分辨率做颜色编码，透明覆盖仍按原图取样。
- 请 Claude 转达集成人员，核心 API 从 1.3 增至 1.4，新增可选能力 `grid-templates`。旧 `POST /api/template` 请求沿用原包格式。若其他卡也修改 API 次版本，请在集成时统一版本及可选能力列表。功能提交为 `d275eb1`，本报告留在当前工作树根目录。

STATUS: DONE
