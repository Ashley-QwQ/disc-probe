# 卡 T 最终批量：统一大厅中性光池

本轮七个 job 已完成 CPU 渲染、九层纸色核对；实际写入 **5/9**，保留旧图 **4/9**（faxnews, filebox, lamp, newplan）。[完整数字与四张截图](docs/cards/lobby-pool-final/NOTE.md)。没有把未过门槛的图写进网页。

## 按提交列出的工作

- `8f879f8`：第一版 base 试烤；`3677c75`：第二版 sigma=.42 / amb=.64 / gain=5.8 / add=0，经用户确认采用。两版审查记录保留。
- 本轮 `art: apply neutral lobby pool with frozen paper checks`：按七个 manifest job 分层渲染，统一物件与桌面配方；牛皮纸、灯罩、LED、屏幕 glow 和线稿未改。增加大厅冻结历史门槛与按层选择，默认原子写入及其它组门槛保持不变；使用正式 exporter 写入通过子集，更新 manifest 和导出报告，未通过项附本轮失败数据并保留原来源。新增四张真实点击导航截图、桌面暖色和文件袋色相比对、测试及保护检查证据。

始终在 `web/lobby-pool-20261116`，父提交 `3677c753bb32cecf6d643bfa6bce761847570238`；未推送、未合并、未切分支、未改其它 worktree 或 evidence/atlas/*.py、未操作真实光驱或上传。所有路径操作和递归枚举排除用户禁止的名称。lobby.json 及 116 张纸色原图哈希不变，非大厅 manifest/导出报告条目不变。

## 渲染和输入

CPU、`-t 8`、SS=4、16 samples，paper/dark。四个场景均为原 sigma=.42 的 segment；机位、几何及材质本色保持原输入。room_fax_parcel / room_round5 从指定 x79 stage 只读 tar 拷入，远端字节数和 SHA-256 与副本一致；room_lobby3_final 本机与远端哈希也一致。源脚本为已提交 tools/night_lobby，两份 renderer 与 stage 哈希一致，未更改 x79 或 D 盘原件。

| Job | 本轮渲染层 | 复用层 | 耗时秒 |
| --- | --- | --- | ---: |
| F_lobby_a | faxnews,filebox | base | 438.527 |
| F_lobby_b | base,parcel | 无 | 1100.133 |
| F_lobby_c | fax,lamp,newplan,screen | 无 | 925.015 |
| F_lobby_d | screen | 无 | 208.151 |
| L_round5 | fax | 无 | 200.904 |
| L_lobby3 | lamp,newplan | 无 | 480.628 |
| G_lamp | lamp | 无 | 202.594 |

F_lobby_a 的 base 来自已批准 trial2 双主题原始 PNG，按原字节复用；其余层全部本轮 CPU 重渲。逐 job 完整命令、scene/script SHA-256、manifest 原 args 和差异见 *-run.json。G_lamp 的 OPTIX 参数明确改为 CPU；没有使用 glassbox。开始 D/F 可用 41417998336 / 23823048704 字节；测试前和收尾均 >5GB，渲染与临时数据在 F 盘。

## 门槛、光驱和牛皮纸

逐层纸色原始统计、冻结记录和差值见 NOTE 表及 paper-*.json。Night B 绝对门槛仍为 .3 / .02 / .1%；历史差值仍为 .05 / .01 / .1 个百分点，直接读固定 Git blob，不从可变 manifest 取历史值。先做绝对检查，再做批准的历史比较；过不了的层保留旧图，数字原样报告。

newplan 候选顶面最亮/最暗 35.286589/29.878216，桌面 16.116785；最暗差 13.761431≥6，所以未加主角档。实际网页光驱最暗差 9.570915，来源是否保留旧图在 NOTE 中明确。

桌面暖色 0/553037（0.000000000%），只查桌面 ID，不把牛皮纸、灯罩或 LED 计为失败。文件盒中性候选的牛皮纸区域色相差 **11.456445529°>3°**，未通过；本轮保留旧文件盒，因此实际网页新旧色相差 0.000000000°。这个 0° 不是新候选达标的结论。逐像素中位/p95/最大及超过 3° 比例均完整保留在 NOTE，没有通过改材质或旧暖光例外凑指标。

## 验收命令与测试

- `python -X utf8 -B tools/night_lobby/final_lobby.py prepare`，随后 render/all：输入拷贝、哈希及 CPU 批量。
- Blender 后台 `extract_final_masks.py`；`measure_final.py drive-prewrite / prewrite-surfaces / surfaces / drive-written`：光驱亮度、桌面暖色及 kraft 对比。
- `python -X utf8 -B tools/night_lobby/export_final.py export`：内部使用 `tools/night_b_export.py --only lobby --paper-gate night-b-recorded --lobby-layers <通过层> --write`；没有改 gate 值。
- `node tools/night_lobby/capture_final.mjs`：四张 1440×1000 夜色图，真实从大厅点击光驱、传真机、文件盒；错误和 CSP 均 []，最终截图已逐张查看。
- `final_tests.py python` / `final_tests.py javascript`：相关 pytest `-n 2` 和全部允许路径内 test_*.mjs `--test-concurrency=2`，TEMP/basetemp 在 F 盘。首次新增测试暴露了既有总开关不接受大厅，修复实现后复跑相关 Python；首次日志亦保留。

```text
ℹ tests 62
ℹ suites 0
ℹ pass 62
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 192598.6055

................                                                         [100%]
============================= 16 passed in 3.49s ==============================
```

JavaScript 失败项：

```text
无
```

没有修改无关 UI 或降低测试断言；未重复全量 JS。`verify_final.py` 检查 121 个受保护文件变化 0、非大厅元数据不变、七个 job 均 CPU/8 线程、输入和源脚本不变、base 复用原字节、实际图片与门槛决策一致、四图尺寸与错误数组。`git diff --check`、UTF-8 中文检查和 gzip 原始证据字节核对在提交前完成。通过测试的临时数据清理，保留日志、截图和现存失败现场，见 cleanup.json。

## 未完成与限制

保留层 faxnews, filebox, lamp, newplan 未完成新配方落地，原因及未舍入数字在 NOTE。没有自行放宽纸色或把更接近原图当作历史一致；原图仍显示在最终截图中。区域色相均值与逐像素色相误差分开报告，未做去饱和、向青色偏移或材质调色。跨机重现和未列出的页面未测；不会宣称大厅九层全通过，除非九层实际均已写入。
