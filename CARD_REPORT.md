# 卡 T 第二版：恢复大厅光池宽度并按目标提亮

## 按提交列出的工作

- 第一版 `8f879f8`：仅 base 试烤，sigma=.42×.557、gain=2.4；图和记录仍保存在 [第一版 NOTE](docs/cards/lobby-pool-trial/NOTE.md)，本轮未改其任何文件。
- 本轮提交 `art: brighten lobby base with original pool width`：按最新审查恢复 sigma=.42，amb=.64、add=0，gain 三通道相等并经两个低 SS 候选确定为 5.8。只执行 base；两份 renderer 一起存档，round5 未运行。加入 trial2 驱动与交付脚本，并让已有核对/截图/测试工具可通过 LOBBY_TRIAL 指定本轮目录。[第二版 NOTE 与图](docs/cards/lobby-pool-trial2/NOTE.md)。

分支始终为 `web/lobby-pool-20261116`；本轮父提交 `8f879f8904fbb900039ad828afa6259042c219b9`。未推送、未合并、未切分支、未动其他 worktree、光驱或 atlas 脚本。路径操作及递归枚举均排除用户指定的连续字母组合。所有正式网页资源、纸色图、lobby.json、manifest、原导出报告、CSS 和前景夜色层均未改。

## 渲染和数字验收

1. `python -X utf8 -B tools/night_lobby/trial2.py prepare`：复用第一版已验明的 room_fax.blend 副本，字节数与 SHA-256 再次相同；不重新访问远端。只读复用原场景清单、ID 桌面覆盖和光驱投影数据，逐文件哈希见 reused-geometry.json。x79 源脚本、原场景和第一版审查副本保持不变。开始 D/F 剩余 42438123520 / 26094096384 字节，测试前和收尾均高于 5 GB；全部临时数据在 F 盘。
2. 两个有效 SS=1 CPU 候选：gain=4 → L*=13.809171125；gain=5.5 → L*=15.759468498；四角最高均 4.660415488。线性亮度拟合到 L*=16.1 后取 gain=5.8，详见 selection.json。首次 gain=4 启动因新 stage 缺 palette 依赖而退出、未出图；已修复准备脚本并重跑，失败日志保留，不算一个有效候选。
3. 正式命令 `python -X utf8 -B tools/night_lobby/trial2.py render --gain 5.8 --ss 4 --label F_lobby_a --variants paper,dark`：CPU、8 线程、16 samples，只渲 base 双主题，exit=0，967.094 秒。没有批量渲其它层。
4. 同一安全桌面测点 (842,1074)，PNG **L*=16.116784936**，试编码 WebP **L*=16.076486219**；均在 15.5–17。PNG 四角最大 **4.660415488**，WebP 四角最大 **4.628894368**，均 ≤7。没有挪测点、改掩码或调整阈值。光池中心遮挡及光驱仍是旧前景的限制见 NOTE。
5. `LOBBY_TRIAL=F:/dp-archive/tmp/lobbypool/trial2` 下运行 `check_trial.py`：本轮重新渲纸色，原 exporter 函数、原裁切、(92,6) 编码；RGB mean=0.023598097548、alpha mean=0.000000000000、>8=0.026368823283%，Night B 绝对门槛通过（≤.3 / ≤.02 / ≤.1%）。未使用历史白名单或写入仓库纸色。
6. 同环境运行 `node tools/night_lobby/capture_trial.mjs`：本地虚拟练习后端、无头 Edge，1440×1000 中文夜色；相同固定时间、机位、布局和动作设置；强制重载并记录 base 响应替换，页面错误及 CSP 均 []。新旧截图差异 806206 像素，其余层位置一致；最终截图已查看。
7. `verify_trial.py`：128 个受保护文件，含 116 张纸色，哈希变化 0；第一版整个 docs 副本不变；两份 renderer 的纸色样式、非灯光夜色样式、线稿/阴影相关函数 AST 与原输入相同。stage 与存档 renderer 相同；SS=4 输出及试编码各自满足亮度范围。`git diff --check`、Python 语法和中文 UTF-8 检查在提交前执行。

## 测试

`LOBBY_TRIAL=F:/dp-archive/tmp/lobbypool/trial2` 下运行 `python -X utf8 -B tools/night_lobby/run_checks.py`：一次允许路径内全部 `tests/test_*.mjs`，`node --test --test-concurrency=2`；相关 Python 为 `pytest -n 2 -p no:cacheprovider tests/test_night_pool.py`。完整命令和耗时见 tests.json，原始日志以 .log.gz 存档。

```text
ℹ tests 62
ℹ suites 0
ℹ pass 61
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 235653.0368

............                                                             [100%]
============================= 12 passed in 2.63s ==============================
```

JavaScript 失败项：

```text
✖ tests\test_flow_navigation_browser.mjs (78994.3464ms)
```

唯一失败为导航浏览器测试：本地 handshake.mjs、api.js 等资源出现 ERR_CONNECTION_REFUSED，重载后空页面，在 design 状态等待超时。未修改测试断言或相关 UI 来消除失败，未重复跑全量。根因未在本轮判定，详细诊断与可用截图保留；测试自身 finally 清理的失败夹具未复原。通过测试的临时数据已清理，截图移入 F 盘，见 cleanup.json。

## 停止点与未测

只完成第二版 base。光驱、传真、文件盒、显示器、灯等八个前景层仍是旧图；光驱顶面数值不代表 gain=5.8 的新光驱。未测其它层、跨机和全场景一致性；没有把光池中心遮挡处当作实测桌面。本轮不再做视觉取舍或后续批量，提交后停止等待用户审查。
