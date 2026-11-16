# 卡 T：大厅 base 夜色试烤，等待审查

## 按提交列出的工作

本轮一个提交 `art: add neutral lobby base trial for review`（父提交 `3437398ea6dab7035bd3aacaf1f7e1773872e2f6`），仅在 `web/lobby-pool-20261116`：

- `tools/night_lobby/` 存档 x79 版本的两份 renderer 及依赖，并加入只试 base 的准备、渲染、核对、截图、测量、保护检查与报告脚本。
- 夜色使用固定 .64 / 2.4 / 0 配方，sigma ×.557（segment 亦适用）；纸色与柔和线设置保持原样，CPU 路径显式指定。只执行传真场景的 base 双主题 job；round5 修改后留档，未运行。G_lamp、parcel 和其它层未渲。
- [trial 图和 NOTE](docs/cards/lobby-pool-trial/NOTE.md) 已提交审查副本；F 盘保留原始场景、EXR、日志和完整证据。

正式的九张大厅夜色图、所有纸色图、lobby.json、manifest、既有导出报告和 UI/CSS 均未改。没有推送、合并或切换分支；没有操作其他 worktree、光驱、刻盘、上传或 atlas 脚本。路径操作及递归枚举按用户要求排除指定连续字母组合。

## 输入与只读检查

采用 `F:/dp-archive/tmp/lobbypool/x79stage/stage/` 的脚本。round5、palette、glow 与 `D:/disc-probe/art/desk/night-b/` 同名副本 SHA-256 相同；D 盘没有同名 fax 脚本。原件未改。逐文件字节数与 SHA-256 见 trial/preflight.json。

仅从 x79 只读拷入 `room_fax.blend`，用 Python 二进制管道连接 `ssh x79 "tar cf - -C /home/knappy/nightb/stage room_fax.blend"` 和 `tar xf -`。远端/本地均 18389936 字节，SHA-256 `913c2af0b7ba10affc64a315c46f4c9d4ea72896185e410ad2d6ddf2fbb801ac` 一致。其余远端场景不需要本轮渲染，未拷入。光驱旧图 ROI 另只读使用卡片列出的本机 `room_lobby3_final.blend`。

开始时 D/F 盘剩余 42537455616 / 28906631168 字节；测试前及收尾见 tests.json、verification.json，均高于 5 GB。渲染、浏览器配置与测试 TEMP/TMP 均设在 F 盘；测试内硬编码到工作树 `.impeccable/` 的截图在结束后迁到 F 盘，未提交。

## 验收命令与结果

1. `python -X utf8 -B tools/night_lobby/render_trial.py`：exit=0，1027.416 秒，Blender 5.2.2 LTS、`-t 8 --device CPU --layers base --ss 4 --no-mist --force --variants paper,dark`。未运行其它层。
2. `python -X utf8 -B tools/night_lobby/check_trial.py`：原导出函数、原裁切、(92,6) 编码；RGB mean=0.023598097548，alpha mean=0.000000000000，>8=0.026368823283%；Night B 绝对门槛通过。本层不适用历史差值白名单。没有写入正式图片。
3. `node tools/night_lobby/capture_trial.mjs`：本地虚拟练习后端，无头 Edge；新旧截图均 1440×1000、夜色、中文，错误与 CSP 记录均为 []；世界变换和各层位移完全相同，第二张仅替换 base HTTP 响应。初次相同 URL 导航没有刷新图片，被提交前像素差检查拦下；工具已改为强制重载并断言替换请求实际发生，重新截图后有 809797 个像素不同。初次无效截图及捕获记录以 initial/no-reload 名称保留在 F 盘，不作为本轮审查图。
4. Blender 后台运行 `measurement_masks.py` 后，`python -X utf8 -B tools/night_lobby/measure_trial.py`：L* 数值、坐标、RGB 与掩码已记录在 NOTE 和 measurements.json。光驱值属于未改的旧层。
5. `python -X utf8 -B tools/night_lobby/run_checks.py`：一次全部允许路径内的 `tests/test_*.mjs`（`node --test --test-concurrency=2`），再跑相关 `pytest -n 2 -p no:cacheprovider tests/test_night_pool.py`，TEMP 与 basetemp 在 F 盘。

JavaScript 全量结果：

```text
ℹ tests 62
ℹ suites 0
ℹ pass 58
ℹ fail 4
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 233355.3497
```

首次失败项（F 盘原始 javascript-tests.log，仓库为保留原字节的 javascript-tests.log.gz；其他日志与完整场景清单也按原字节 gzip 存档）：

```text
✖ tests\test_csp_browser.mjs (4185.0284ms)
✖ tests\test_flow_navigation_browser.mjs (65229.3785ms)
✖ tests\test_review_library_newwork.mjs (7649.2281ms)
✖ tests\test_rw_discs_browser.mjs (101518.9394ms)
```

Python 结果：

```text

............                                                             [100%]
============================= 12 passed in 3.02s ==============================
```

只对 JavaScript 失败项的后续单并发复核（命令见 javascript-retest.json；不重复全套）：

```text
✖ tests\test_csp_browser.mjs (18974.1989ms)
✖ tests\test_flow_navigation_browser.mjs (64624.7989ms)
✖ tests\test_rw_discs_browser.mjs (99989.3212ms)
ℹ tests 4
ℹ pass 1
ℹ fail 3
ℹ skipped 0
```

6. `python -X utf8 -B tools/night_lobby/verify_trial.py`：128 个受保护文件（其中 116 张纸色）哈希变化 0；输入原件和场景副本未改；两 renderer 的纸色样式、非灯光夜色材质与轮廓/合成/阴影设置 AST 一致；stage 与存档脚本相同。`git diff --check`、Python AST 解析、中文 UTF-8 检查均在提交前完成。拓扑与跨机渲染未测，本轮不作几何或全层一致性结论。

## 未完成、疑问与审查决定

仅完成 base 试烤。光驱、传真机、文件盒、显示器、灯等八层都保留旧图，网页对比因此是“新 base + 旧前景”；光驱顶面亮度没有体现新配方。光池定义中心被前景遮挡，NOTE 明确给出最近可见桌面点及距离；四角数值包含画面背景/地面，不夸称桌面数值。

本轮不调整固定配方来追求目标亮度，不自行判断视觉好坏；不展开无关 UI 测试故障修复，也不修改断言。首次盘库批次断言失败在单并发复核时通过；复核仍失败的 CSP 用例等待 design 超时，导航用例等待握手失败状态超时（空页面及本地连接拒绝），RW 用例等待重载恢复超时（空页面）。这些被测 UI 未在本轮修改，根因未确定；不把失败自动归为既有问题或资源竞争。需要审查决定是否接受这一张 base 试烤及是否开始后续分层渲染；本轮提交后停止等待。
