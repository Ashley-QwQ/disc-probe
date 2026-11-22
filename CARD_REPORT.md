# PP 拍照校准页交付

分支 `dev/photo-polish`，卡片基点 `3eb2421`。

## 提交

- `aa4474b` 修复拍法区域、手机设备列表、跳过按钮和手动调整的语言，并在 `tests/test_photo_wire_browser.mjs` 添加回归断言。
- 本报告单独提交。

## 修复

- 拍法原本在扫码区下方单列堆叠，1920×895 英文夜色下，说明文字被裁到滚动区下方。宽屏将扫码区和拍法并排，窄屏先显示文字。CD 显示标靶拍法，包括关顶灯、侧面打光、拍到整盘、相邻照片转 60–120°。DVD 保留原有拍法和侧视图。ET 补充 C 的对准纸用于拍摄已刻彩色作品，因此这一步沿用标靶拍法。
- 拍照页只把已连接的手机交给设备列表。有手机时保留断开操作和原有连接信息，没手机时隐藏列表。手动调整、电脑地址和手机连接帮助按当前语言显示。
- 跳过按钮继承的 `--glass-desk` 在夜色下向左偏移 105.6 px、向下偏移 57.6 px，模糊半径 24 px。单独关闭该按钮的投影，右栏截图有 38,274 像素变化，覆盖标靶盘号附近的黑块消失。按钮使用纸面配色和描边，悬停时在纸面上轻微加深，去掉与按钮文字重复的原生提示。`calibrate.js` 和冻结的 `pcal.py` 与基点一致。

## 验收

- `node D:/dp-dev/tmp/photopolish/capture-live.mjs before` 和 `node D:/dp-dev/tmp/photopolish/capture-live.mjs after` 通过无头 Edge 和 CDP 从实际应用的 CD 批次拍照入口、DVD 测量结果拍照入口进入。每轮覆盖 CD／DVD × 纸色／夜色 × 中文／英文 × 1920×895／390×844，共 32 张主图。另有 20 张右栏悬停截图和 1 张关闭投影的定位截图。回环服务使用模拟批次、手机链接和空照片列表。 [截图](D:/dp-dev/tmp/photopolish/shots/)
- `python -X utf8 -B D:/dp-dev/tmp/photopolish/verify-shots.py` 验证 53 张 PNG 的尺寸和完整性。跳过按钮在纸色默认和悬停的对比度分别为 13.94:1 和 11.98:1，在夜色分别为 12.71:1 和 10.92:1，均达到 4.5:1。 [截图测量](D:/dp-dev/tmp/photopolish/logs/screenshot-check.json)
- `node D:/dp-dev/tmp/photopolish/touch-proof.mjs after` 用 CDP 发送触屏滑动，验证 390 宽时 CD 和 DVD 两个入口都能把完整二维码滚进视口。 [触屏日志](D:/dp-dev/tmp/photopolish/logs/touch-proof.log)
- `node --test --test-concurrency=1 tests/test_photo_wire.mjs tests/test_photo_wire_browser.mjs tests/test_photocal.mjs tests/test_phone_page.mjs`，4 个文件通过。覆盖两类拍法、两种主题和宽度下的按钮对比度及提示、本机行过滤、手机断开、无手机及旧服务状态、手动调整语言和跳过动作。 [定向 JavaScript 日志](D:/dp-dev/tmp/photopolish/logs/photo-js.log)
- `python -X utf8 -B D:/dp-dev/tmp/photopolish/run-js.py` 逐个跑 `tests/test_*.mjs`，首轮 59／61。测试脚本的无光驱设置挡住了两项 Disc Lab 虚拟光驱测试。用 `python -X utf8 -B D:/dp-dev/tmp/photopolish/run-js.py test_burn_cancel_browser.mjs test_rw_discs_browser.mjs` 让这两项各自使用隔离的虚拟光驱，复跑 2／2 通过，合计 **61／61**。 [全量日志](D:/dp-dev/tmp/photopolish/logs/all-js/summary.txt) · [复跑日志](D:/dp-dev/tmp/photopolish/logs/retry-js/summary.txt)
- `python -X utf8 -B -m pytest -n 2 -q -p no:cacheprovider --basetemp D:/dp-dev/tmp/photopolish/pytest-work tests/test_photo.py tests/test_photo_l_image.py tests/test_along_track_preset.py tests/test_along_track_grid.py -k 'not sealed_blind_photos_through_command'`，154 项通过，20.17 秒。冻版读取器在合成手动对齐夹具上有一条 `Mean of empty slice` 警告。 [Python 日志](D:/dp-dev/tmp/photopolish/logs/photo-python.log)
- `TEMP` 和 `TMP` 使用 D 盘完整路径。起跑和全量 JavaScript 测试前分别有约 105 GiB 和 101 GiB 可用。临时浏览器配置、虚拟盘和 pytest 夹具已清理。

## 未测及取舍

- 未测真机拍摄、局域网实机连接或实体光盘。按路径限制跳过一项会递归查找原始归档照片的可选测试，保留同批照片的已存读数复验。
- 390 宽的左栏先显示拍法，扫码区可向下滚动到达。宽屏的拍法在首屏可读。无需要审查人额外决定的事项。

STATUS: DONE
