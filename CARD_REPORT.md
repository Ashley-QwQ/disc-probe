# 卡 R：夜色光池中性化、收窄

执行已结束，**图片更新未通过验收**。16 个目标 job 已逐个尝试；14 个完成双主题烤图，2 个缺少额外原始输入。完成烤图的 job 均未通过纸色逐像素核对，导出 0 个 job、0 张图片。没有放宽门槛或写入失败候选。

## 提交与实际改动

- `3cdf1fe`：记录首次源文件预检阻塞；该次关于托盘与 Penrose 输入的阻塞已由用户后续确认解除。
- `a989a6a`：两个 renderer 的夜色桌面改为 amb .64、gain 2.4、add 0；top 光驱 / fax 传真机用 amb 1、gain 4.9、add .006；夜色 sigma 乘 .557；线条按光池在 .88 / .35 之间变化，透明边缘剪影下限 .6。纸色 STYLE、纸色模式特例及 sheet_light 配方保持不变。加入按主题输出的 sigma 记录。
- `3183a15`：严格纸色核对使用 manifest 已记录的编码配方，避免根据文件大小穷举猜测；新增有损编码配方重现测试。没有放宽逐像素一致的门槛。
- 本次证据提交 `docs: record night-pool render attempts and validation`：更新本报告、manifest 和导出报告的对应 `night_pool_attempt`。失败候选的机器标为 `local RTX 2060, OptiX`；原有顶层 machine、encoding、paper_check 保留既有图片的来源，避免把未发布候选冒充现有图片。

导出工具增加 `--jobs`、`--require-paper-unchanged`、`--check-report`。严格模式比较解码后的全部 RGBA 像素，包括透明区域；整个所选 job 检查完才允许写图片。新增 4 项测试覆盖物体分光、行方向和剪影、第二张图片只差一个通道一步时整组不写入，以及已记录有损编码的精确重现。

分支始终为 `web/night-pool-20261116`，没有推送、合并或修改其他 worktree。未接光驱、刻盘、下载或上传。递归查找排除了用户指定的禁用名称及其子树。

## 输入与渲染命令

Blender 5.2.2 LTS，构建 `d13f752e3b9c`。能力探针及 `nvidia-smi` 均识别 NVIDIA GeForce RTX 2060（6144 MiB），探针列出 OPTIX 设备。所有渲染命令均指定 `--device OPTIX --variants paper,dark`，其余参数照 manifest；CPU 线程限制 `-t 2`。完整逐 job 命令见 `F:/dp-archive/tmp/nightpool/<JOB>-run.json`，日志为 `<JOB>.log`。

托盘由用户确认的 `D:/disc-probe/art/desk/skills/desk-prop-tray/final_bundle/tray.blend` 复制到 F 盘 `lobby_tray.blend`；Penrose 从仓库 `caltop/props/penrose.json` 复制到 F 盘 `props/penrose.json`。传真场景和 `parts.json` 复制到 F 盘 `fax/`，并将 renderer 临时副本放在该场景旁，以满足原脚本的同目录保护。未保存源场景。3 组输入/副本 SHA-256 均相同，见 `validation/validation_report.json` 的 `source_copies`。

续作开始时 D 盘剩余 42,773,655,552 字节、F 盘 33,305,194,496 字节；全量测试开始前检查均高于 5 GB。输出、渲染日志、验收截图保存在 `F:/dp-archive/tmp/nightpool/`。没有往仓库复制输入素材。

先完成并查看 `F_np_env/envelope_back_dark.png`，然后继续其余 job；另查看了预设桌面候选及网页平移帧。

## 每个 job 的结果

| Job | 双主题渲染 | 核对图片数 | 各图片不同像素数 | 状态 |
| --- | --- | ---: | --- | --- |
| `F_np_top` | 失败 | 0 | 未测 | blocked_missing_input |
| `F_np_paper` | 成功 | 2 | 134713, 108739 | blocked_paper_mismatch |
| `F_np_env` | 成功 | 2 | 279412, 144468 | blocked_paper_mismatch |
| `F_np_desk` | 成功 | 12 | 142220, 1738515, 16, 35510, 931818, 28620, 843811, 4350, 73967, 67763, 1641460, 77922 | blocked_paper_mismatch |
| `F_pw_env` | 成功 | 2 | 62079, 153286 | blocked_paper_mismatch |
| `F_fax_top` | 失败 | 0 | 未测 | blocked_missing_input |
| `F_tumble0` | 成功 | 1 | 41363 | blocked_paper_mismatch |
| `F_tumble1` | 成功 | 1 | 40242 | blocked_paper_mismatch |
| `F_tumble2` | 成功 | 1 | 36414 | blocked_paper_mismatch |
| `F_tumble3` | 成功 | 1 | 37037 | blocked_paper_mismatch |
| `F_tumble4` | 成功 | 1 | 37237 | blocked_paper_mismatch |
| `F_tumble5` | 成功 | 1 | 31267 | blocked_paper_mismatch |
| `F_tumble6` | 成功 | 1 | 34792 | blocked_paper_mismatch |
| `F_tumble7` | 成功 | 1 | 37498 | blocked_paper_mismatch |
| `F_tumble8` | 成功 | 1 | 38181 | blocked_paper_mismatch |
| `F_tumble9` | 成功 | 1 | 31411 | blocked_paper_mismatch |

`F_np_top` 在读 `mark_split.json` 时失败；renderer 所需的 `mark_soft_D/P_paper/dark.png` 同样未在已检查的安全来源中找到。没有重建标记输入。`F_fax_top` 缺少 `extra_palette.json`；没有猜测或重建该配色。日志另有 `File written by newer Blender binary (503.31), expect loss of data!` 警告，场景与指定 Blender 的兼容性尚未验证，原场景没有保存。两个 job 的纸色与主角亮暗指标均为未测。

其它 job 没有因这两个阻塞而停止。纸色检查使用：

```text
python -X utf8 -B tools/night_b_export.py F:/dp-archive/tmp/nightpool --only <group> --jobs <JOB> --require-paper-unchanged --check-report F:/dp-archive/tmp/nightpool/<JOB>-paper-check.json
```

纸色核对失败返回 2，没有调用这些 job 的 `--write`。逐图片记录如下；“mean 0.00”只是显示时四舍五入，不能当作 unchanged。

| 候选对应的网页图 | 原编码方式 | 不同像素数 | 纸色差异诊断 |
| --- | --- | ---: | --- |
| `newplan/paper_dark.webp` | `(90, 4)` | 134713 | mean 0.08, alpha mean 0.00, px >8: 0.000% |
| `newplan/paper_shadow_dark.webp` | `(91, 6)` | 108739 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `newplan/envelope_back_dark.webp` | `(90, 4)` | 279412 | mean 0.07, alpha mean 0.00, px >8: 0.001% |
| `newplan/envelope_front_dark.webp` | `(90, 6)` | 144468 | mean 0.04, alpha mean 0.00, px >8: 0.015% |
| `presetio/desk/desk_bag_dark.webp` | `(88, 6)` | 142220 | mean 0.26, alpha mean 0.00, px >8: 0.083% |
| `presetio/desk/desk_bag_shadow_dark.webp` | `(93, 4)` | 1738515 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_base_dark.webp` | `(90, 4)` | 16 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_doc_envelope_dark.webp` | `(90, 4)` | 35510 | mean 0.04, alpha mean 0.00, px >8: 0.007% |
| `presetio/desk/desk_doc_envelope_shadow_dark.webp` | `(92, 4)` | 931818 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_doc_paper_dark.webp` | `(90, 4)` | 28620 | mean 0.03, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_doc_paper_shadow_dark.webp` | `(86, 4)` | 843811 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_knob_dark.webp` | `(91, 6)` | 4350 | mean 1.48, alpha mean 0.00, px >8: 1.342% |
| `presetio/desk/desk_knob_shadow_dark.webp` | `(85, 6)` | 73967 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_sheets_dark.webp` | `(91, 4)` | 67763 | mean 0.13, alpha mean 0.00, px >8: 0.002% |
| `presetio/desk/desk_sheets_shadow_dark.webp` | `(84, 4)` | 1641460 | mean 0.00, alpha mean 0.00, px >8: 0.000% |
| `presetio/desk/desk_upper_dark.webp` | `(91, 6)` | 77922 | mean 0.11, alpha mean 0.00, px >8: 0.009% |
| `pastworks/envelope_back_dark.webp` | `(90, 6)` | 62079 | mean 0.02, alpha mean 0.00, px >8: 0.002% |
| `pastworks/envelope_front_dark.webp` | `(89, 6)` | 153286 | mean 0.12, alpha mean 0.00, px >8: 0.065% |
| `pastworks/tumble_0_dark.webp` | `(89, 4)` | 41363 | mean 1.40, alpha mean 0.11, px >8: 3.857% |
| `pastworks/tumble_1_dark.webp` | `(89, 4)` | 40242 | mean 1.44, alpha mean 0.11, px >8: 4.408% |
| `pastworks/tumble_2_dark.webp` | `(89, 4)` | 36414 | mean 1.91, alpha mean 0.09, px >8: 5.680% |
| `pastworks/tumble_3_dark.webp` | `(89, 4)` | 37037 | mean 1.62, alpha mean 0.10, px >8: 4.736% |
| `pastworks/tumble_4_dark.webp` | `(89, 4)` | 37237 | mean 2.01, alpha mean 0.10, px >8: 6.448% |
| `pastworks/tumble_5_dark.webp` | `(89, 4)` | 31267 | mean 3.33, alpha mean 0.08, px >8: 10.490% |
| `pastworks/tumble_6_dark.webp` | `(89, 4)` | 34792 | mean 1.71, alpha mean 0.10, px >8: 4.785% |
| `pastworks/tumble_7_dark.webp` | `(89, 4)` | 37498 | mean 1.73, alpha mean 0.10, px >8: 5.998% |
| `pastworks/tumble_8_dark.webp` | `(89, 4)` | 38181 | mean 1.72, alpha mean 0.10, px >8: 5.281% |
| `pastworks/tumble_9_dark.webp` | `(89, 4)` | 31411 | mean 2.99, alpha mean 0.08, px >8: 8.380% |

## 亮度和色相：仅候选 PNG，未发布

以下逐图片数据来自未通过纸色门槛的候选，不代表网页已经更新。透明的信封、纸、阴影和道具分层没有桌面或主角，该指标记为“不适用”，不从透明黑色推算桌面亮度。边缘为最左 / 最下 5 像素条带中不透明像素的 L* 中位数；条带没有不透明像素时也记不适用。

| 候选图 | 光池中心桌面 L* | 左 / 下边缘 L* | 主角最亮 / 最暗 L* |
| --- | ---: | --- | --- |
| `F_np_paper/paper_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_paper/paper_shadow_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_env/envelope_back_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_env/envelope_front_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_bag_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_bag_shadow_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_base_dark.png` | 19.74 | 6.21 / 8.16 | 不适用 |
| `F_np_desk/desk_doc_envelope_dark.png` | 不适用 | 不适用 / 24.86 | 不适用 |
| `F_np_desk/desk_doc_envelope_shadow_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_doc_paper_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_doc_paper_shadow_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_knob_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_knob_shadow_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_sheets_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_sheets_shadow_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_np_desk/desk_upper_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_pw_env/envelope_back_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_pw_env/envelope_front_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble0/tumble_0_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble1/tumble_1_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble2/tumble_2_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble3/tumble_3_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble4/tumble_4_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble5/tumble_5_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble6/tumble_6_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble7/tumble_7_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble8/tumble_8_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |
| `F_tumble9/tumble_9_dark.png` | 不适用 | 不适用 / 不适用 | 不适用 |

预设桌面中心在 (1483,493)，RGB=(35,50,56)，L*=19.74；左边缘范围 5.78–6.25、下边缘范围 5.78–10.50。**中心高于约 16、下边缘中位数 8.16 高于 ≤7，亮度目标未通过。** 配方严格照卡片，未自行调整视觉参数。桌面无道具矩形 ROI `[1000,10,1800,650]` 内，OKLCH 色相 30–90°且彩度 >.02 的像素为 0 / 512000；这只是该 ROI 的证据，不是全桌面掩码测量。主角 35 / 14 目标因两个主角 job 缺输入未测。

## 网页截图

`shots/` 下已拍摄 5 张 1440×1000、夜色主题截图：`newplan-dark.png`、`design-to-presetio-dark.png`、`pastworks-dark.png`、`faxnews-dark.png`、`newplan-to-caltop-halfway-dark.png`。使用 `tests/webguide_http_fixture.py` 的本地练习服务和无头 Edge，走大厅光驱、设计页预设按钮、往期作品和传真入口；将实际 760ms 平移动画暂停在 380ms 取中间帧。`shots/capture.json` 记录每张的模式、主题、尺寸和页面错误数组（均为空）。

**截图呈现的是保留原图片后的工作树，不能证明新作品页与标定页已经接色。** 所有候选均被导出门槛阻止，接色验收未完成。截图中未注入失败候选。

## 测试与保护检查

- `node --test --test-concurrency=2 <tests/ 中排除禁用路径后的全部 test_*.mjs>`：首轮 62 项，59 通过、3 失败；详见 `node-all.log` 和 `node-all-result.json`。
- `test_review_library_newwork.mjs` 首轮因 ResizeObserver 通知错误失败，单独重跑 1/1 通过，见 `node-review-rerun.log`。
- `test_csp_browser.mjs` 首轮缺少它硬编码的输出目录；在临时目录准备 F 盘输出链接后重跑，进入 newplan 超时，仍失败，见 `node-csp-rerun.log`。
- `test_kit_browser.mjs` 的 `Preview must copy the :root token block` 断言失败，未修改无关 HTML/CSS 去迁就测试。该测试与相关页面文件不属于本次修改。没有把这两项失败算成通过。
- `python -X utf8 -B -m pytest -n 2 tests/test_night_pool.py tests/test_presets.py tests/test_works.py --basetemp F:/dp-archive/tmp/nightpool/pytest-related -q -p no:cacheprovider`：106 通过，见 `pytest-related.log`；之后编码配方改动对应的最终单测为 `pytest -n 2 tests/test_night_pool.py --basetemp F:/dp-archive/tmp/nightpool/pytest-unit-final -q -p no:cacheprovider`，工具返回 4/4 通过、耗时 2.95 秒（含新增第 4 项）。
- 哈希对比：195 个受保护文件中 116 张纸色图片，变化 0；同时覆盖已提交 caltop、CSS、HTML。原始构造/相机代码段以及纸色 STYLE 的 AST 与 `3c3f66a` 比较均相同。
- 版式、裁切、位置 JSON、既有图片均未修改。sigma 的实际候选记录保存在渲染元数据和 manifest 的 attempt 中；没有把未发布的 sigma 填进网页位置 JSON。
- `git diff --check` 退出 0；中文编码检查：本报告 2167 个非 ASCII 字符，连续问号替代计数 0（追加本行与清理说明前的计数）。两个 JSON 均能解析；原有非 attempt 字段与提交前完全一致。
- 已清理 11 处通过测试的临时目录、浏览器配置或任务输出链接；日志、截图和失败测试现场保留在 F 盘，清单见 `cleanup.json`。结束前 D / F 盘分别剩余 42,655,571,968 / 30,345,232,384 字节。

## 尚需解决

需要补齐原始标记输入和传真 `extra_palette.json`。其余 14 个 job 需要找出纸色重现差异的原因，直到真正逐像素 unchanged；当前证据不能确定是 GPU/CPU、编码器、原始素材版本还是其它环境差异，不能靠忽略微小差异放行。预设桌面的亮度目标也未达成，需要审查人决定如何处理指定配方与实测值的差距。当前未完成图片发布和接色验收。
