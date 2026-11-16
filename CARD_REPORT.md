# 卡 R：CPU 夜色光池更新

本轮已逐个执行 16 个 job，全部完成双主题渲染，按用户更正使用 CPU、8 线程和 Night B 数值门槛。**最终保留 4 个 job、8 张夜色导出；12 个 job 保留原图。** 8 张导出中，7 张 WebP 字节发生变化，1 张听筒阴影与原文件相同。其中 11 个 job 纸色超限；`F_np_paper` 纸色通过，但移动端预设页文字对比度为 4.1875，低于 4.5，已整组回退。超限 job 没有部分写入；所有仓库纸色图片永不写入。

## 按提交列出改动

- `3cdf1fe`：首次缺输入报告，相关输入后来已由用户补齐。
- `a989a6a`：中性桌面/主角分光、夜色 sigma ×.557、随光池变化的线条透明度；纸色 STYLE 和 sheet_light 配方不变。
- `3183a15`：按 manifest 记录重现编码配方，保留原有精确检查选项。
- `3f7cff2`：此前 OptiX、精确门槛试渲记录，作为历史证据保留在 F 盘根目录。
- `0e47522`：CPU 设备记录、`--paper-gate night-b`、未舍入统计、整组拒写检查，以及物体 ID 验收数据；新增门槛边界和纸色永不写入测试。单测 8/8 通过。
- 本次提交 `art: publish CPU-verified neutral night pools`：通过门槛的夜色图片、按主题区分的实际 sigma、manifest、导出报告及本报告。

分支始终为 `web/night-pool-20261116`；未推送、未合并，未修改其他 worktree。没有修改 `evidence/atlas/*.py`、已提交 caltop、index.html 或 CSS；没有接光驱、刻盘、下载或上传。递归操作均排除用户指定的禁用名称和子树。

## 本轮规则和来源

用户本轮明确覆盖卡片中的 OptiX 和精确核对要求：CPU，`-t 8`；纸色解码后 RGB mean ≤0.3、alpha mean ≤0.02、差超过 8 的像素 ≤0.1%。统计沿用原导出工具：RGB mean 和 >8 比例只统计任一侧 alpha >8 的可见像素，alpha mean 统计整张图；>8 检查 RGBA 任一通道。使用未舍入值判断，三个条件必须同时满足，且一个 job 的所有图片必须通过。

核对 `x79stage/run_jobs.sh` 和 `jobs_*.txt` 后，将 x79 的 stage 输入以及两个 renderer 的当前副本放到 `F:/dp-archive/tmp/nightpool/cpu8/stage/`，从那里运行。托盘、传真场景使用用户指定的 D 盘只读来源；光驱场景从卡片指定的 F 盘副本复制。原始 mark、extra_palette、parts、Penrose 数据都在 stage 中；没有往仓库复制这些输入。输入和副本的 SHA-256、结束时源文件未变的证据见 `cpu8/source_copies.json`、`cpu8/validation_report.json`。本机 CPU 为 i5-12400F；Blender 5.2.2 LTS，构建 `d13f752e3b9c`。

本轮开始 D / F 盘分别剩余 42,655,338,496 / 30,458,638,336 字节，均高于 5 GB；全量测试前再次检查。临时文件、渲染和日志保存在 `F:/dp-archive/tmp/nightpool/cpu8/`，验收截图在 `F:/dp-archive/tmp/nightpool/shots/`。

先只渲 `F_np_top`，查看 `cpu8/F_np_top/top_dark.png`，纸色检查通过后写入，再批量执行其余 15 个 job。所有命令均为 `--device CPU --variants paper,dark`、`-t 8`；其它模式参数沿用 manifest。完整命令、退出码和耗时见 `cpu8/<JOB>-run.json`，逐 job 日志为 `<JOB>.log`。

## 写入与阻塞

| Job | 渲染退出码 | 核对图片数 | 结果 | 未通过的图片 |
| --- | ---: | ---: | --- | --- |
| `F_np_top` | 0 | 1 | 已写入 | 无 |
| `F_np_paper` | 0 | 2 | 对比度回退 | 纸色通过；亮纸对比度 4.1875 < 4.5 |
| `F_np_env` | 0 | 2 | 已写入 | 无 |
| `F_np_desk` | 0 | 12 | 未写入 | desk_knob_dark.webp |
| `F_pw_env` | 0 | 2 | 已写入 | 无 |
| `F_fax_top` | 0 | 3 | 已写入 | 无 |
| `F_tumble0` | 0 | 1 | 未写入 | tumble_0_dark.webp |
| `F_tumble1` | 0 | 1 | 未写入 | tumble_1_dark.webp |
| `F_tumble2` | 0 | 1 | 未写入 | tumble_2_dark.webp |
| `F_tumble3` | 0 | 1 | 未写入 | tumble_3_dark.webp |
| `F_tumble4` | 0 | 1 | 未写入 | tumble_4_dark.webp |
| `F_tumble5` | 0 | 1 | 未写入 | tumble_5_dark.webp |
| `F_tumble6` | 0 | 1 | 未写入 | tumble_6_dark.webp |
| `F_tumble7` | 0 | 1 | 未写入 | tumble_7_dark.webp |
| `F_tumble8` | 0 | 1 | 未写入 | tumble_8_dark.webp |
| `F_tumble9` | 0 | 1 | 未写入 | tumble_9_dark.webp |

核对命令：

```text
python -X utf8 -B tools/night_b_export.py F:/dp-archive/tmp/nightpool/cpu8 --only <group> --jobs <JOB> --paper-gate night-b --check-report F:/dp-archive/tmp/nightpool/cpu8/<JOB>-paper-check.json
```

通过后才运行同一命令加 `--write`。门槛失败退出 2，不写该 job 的任何图片。`F_np_paper` 在写入后验收中发现移动端文字对比度回归，已从 `3f7cff2` 恢复该 job 两张夜色图片，原样保留认可的亮纸；没有改 sheet_light 配方或 CSS。回退后的预设页、新作品页浏览器测试单独重跑，结果见 `node-after-rollback.log`。以下为本轮逐图纸色数字，>8 栏单位是百分比，门槛为 0.1%，不是 10%。

| 对应夜色图 | 纸色 RGB mean | alpha mean | >8 像素比例 | 结果 |
| --- | ---: | ---: | ---: | --- |
| `newplan/top_dark.webp` | 0.000706199 | 0.000000000 | 0.000352648% | 通过 |
| `newplan/paper_dark.webp` | 0.086849700 | 0.000027311 | 0.000000000% | 通过 |
| `newplan/paper_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | 通过 |
| `newplan/envelope_back_dark.webp` | 0.082867290 | 0.000004010 | 0.001248330% | 通过 |
| `newplan/envelope_front_dark.webp` | 0.044468302 | 0.000013282 | 0.015640509% | 通过 |
| `presetio/desk/desk_bag_dark.webp` | 0.257081071 | 0.000003255 | 0.087357698% | 通过 |
| `presetio/desk/desk_bag_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | 通过 |
| `presetio/desk/desk_base_dark.webp` | 0.020940032 | 0.000000000 | 0.003824870% | 通过 |
| `presetio/desk/desk_doc_envelope_dark.webp` | 0.060746636 | 0.000001085 | 0.009340801% | 通过 |
| `presetio/desk/desk_doc_envelope_shadow_dark.webp` | 0.000003391 | 0.000000000 | 0.000000000% | 通过 |
| `presetio/desk/desk_doc_paper_dark.webp` | 0.039737751 | 0.000010851 | 0.000209097% | 通过 |
| `presetio/desk/desk_doc_paper_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | 通过 |
| `presetio/desk/desk_knob_dark.webp` | 1.493802714 | 0.000081923 | 1.364136414% | 超限 |
| `presetio/desk/desk_knob_shadow_dark.webp` | 0.000000000 | 0.000040148 | 0.000000000% | 通过 |
| `presetio/desk/desk_sheets_dark.webp` | 0.128970037 | 0.000000000 | 0.002103500% | 通过 |
| `presetio/desk/desk_sheets_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | 通过 |
| `presetio/desk/desk_upper_dark.webp` | 0.108992689 | 0.000001085 | 0.008684816% | 通过 |
| `pastworks/envelope_back_dark.webp` | 0.036730435 | 0.000005678 | 0.001639070% | 通过 |
| `pastworks/envelope_front_dark.webp` | 0.120485416 | 0.000004867 | 0.065212434% | 通过 |
| `faxnews/top_dark.webp` | 0.001466019 | 0.000000000 | 0.000135634% | 通过 |
| `faxnews/handset_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | 通过 |
| `faxnews/handset_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | 通过 |
| `pastworks/tumble_0_dark.webp` | 1.402787726 | 0.112607422 | 3.876206227% | 超限 |
| `pastworks/tumble_1_dark.webp` | 1.437801425 | 0.108515625 | 4.399681564% | 超限 |
| `pastworks/tumble_2_dark.webp` | 1.913332904 | 0.088459473 | 5.685281367% | 超限 |
| `pastworks/tumble_3_dark.webp` | 1.616210333 | 0.100581055 | 4.706530291% | 超限 |
| `pastworks/tumble_4_dark.webp` | 2.008139132 | 0.104995117 | 6.422037619% | 超限 |
| `pastworks/tumble_5_dark.webp` | 3.329248269 | 0.077390137 | 10.491783899% | 超限 |
| `pastworks/tumble_6_dark.webp` | 1.703810177 | 0.101267090 | 4.776420246% | 超限 |
| `pastworks/tumble_7_dark.webp` | 1.727223069 | 0.095861816 | 6.010565761% | 超限 |
| `pastworks/tumble_8_dark.webp` | 1.721215548 | 0.101943359 | 5.276289455% | 超限 |
| `pastworks/tumble_9_dark.webp` | 2.991353769 | 0.077541504 | 8.392202934% | 超限 |

manifest 的 `night_pool_cpu` 是本轮记录，`night_pool_attempt` 是旧 OptiX/精确门槛历史记录。已写入图片的机器和核对数据更新为本机 CPU；未写入图片保留原有来源，另附本轮失败数字。

## 写入后的 L* 与色相

测量对象为仓库实际解码后的 WebP。桌面用物体 ID 掩码，排除道具和线条周围 3 像素；左/下边缘为各 5 像素条带中桌面像素的中位数。主角亮/暗为 body/tray 材质表面的最大/最小 L*，排除盘面、LED、洞腔及线条附近像素；听筒单层采用不透明内部区域。透明信封、纸和阴影没有桌面或主角，不把透明黑色算作桌面。

| 已写入图片 | 光池中心桌面 L* | 左 / 下边缘 L* | 主角最亮 / 最暗 L* |
| --- | --- | --- | --- |
| `newplan/top_dark.webp` | 遮挡；最近可见点 11.37 | 7.65 / 5.58 | 37.03 / 13.52 |
| `newplan/envelope_back_dark.webp` | 不适用 | 不适用 | 不适用 |
| `newplan/envelope_front_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/envelope_back_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/envelope_front_dark.webp` | 不适用 | 不适用 | 不适用 |
| `faxnews/top_dark.webp` | 19.78 | 6.18 / 7.17 | 32.92 / 9.89 |
| `faxnews/handset_dark.webp` | 不适用 | 不适用 | 17.81 / 3.35 |
| `faxnews/handset_shadow_dark.webp` | 不适用 | 不适用 | 不适用 |

光池中心被主角遮挡时不声称测到了该点桌面，表中明确标为遮挡并给最近可见点；坐标、距离、RGB、边缘最小/最大值保存在 `cpu8/validation_report.json`。配方按卡片固定，亮度与约 16 / ≤7 / 35、14 的差距保留供审查，没有自行改色或调 sigma。

桌面中 OKLCH 色相 30–90°且彩度 >.02 的像素统计：

| 桌面所在图 | 暖色像素 / 掩码像素 | 比例 |
| --- | ---: | ---: |
| `newplan/top_dark.webp` | 0 / 3117837 | 0.0000000% |
| `faxnews/top_dark.webp` | 0 / 3356845 | 0.0000000% |

## 截图、测试和保护检查

最终截图文件为 `shots/newplan-cpu-dark.png`、`design-to-presetio-cpu-dark.png`、`pastworks-cpu-dark.png`、`faxnews-cpu-dark.png`、`newplan-to-caltop-halfway-cpu-dark.png`，均 1440×1000、夜色主题。使用本地练习服务和无头 Edge，走实际页面入口；平移帧将实际 760ms 动画暂停在 380ms。`shots/capture-cpu.json` 记录页面状态和错误。截图反映已写入与保留原图混合后的真实工作树，不替换失败候选。

全量 `node --test --test-concurrency=2 <排除禁用路径后的 tests/test_*.mjs>` 的数字：

```text
ℹ tests 62
ℹ suites 0
ℹ pass 60
ℹ fail 2
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 190140.0434
```

详见 `cpu8/node-all.log`、`node-all-result.json`。相关 Python：`python -X utf8 -B -m pytest -n 2 tests/test_night_pool.py tests/test_presets.py tests/test_works.py --basetemp F:/dp-archive/tmp/nightpool/cpu8/pytest-related -q -p no:cacheprovider`：

```text
bringing up nodes...
bringing up nodes...

........................................................................ [ 64%]
.......................................                                  [100%]
111 passed in 25.68s
```

保护检查：195 个受保护文件（其中 116 张纸色图片）哈希变化 0。所有输入副本与来源一致，源文件未变。位置 JSON 只新增 `pool_sigma_px_by_theme`，既有 box、centre_px、裁切、布局以及代表纸色的旧 sigma 标量均保持原值；其它 job 的 sigma 在 manifest 的本轮记录中。`newplan/newplan.json`、传真/预设 JSON 去掉这个新增字段后，与 `3f7cff2` 的对象相同。

## 未完成与审查事项

超限 job 均保留原图，上表是实际未通过的数值，不推断为已重现。预设旋钮层 RGB mean 为 1.493802714、alpha mean 为 0.000081923、>8 为 1.364136414%；整组 12 张未写入。十张翻滚信封也各自超限，没有另找角度或改变门槛。亮纸的纸色检查通过，但其夜色光池收窄触发移动端文字对比度回归，因此恢复认可的旧图；该模式的收窄方案尚未完成。

亮度目标仍有差距：传真桌面中心 L*=19.78，高于约 16，下边缘中位数 7.17 高于 ≤7；新作品页左边缘中位数 7.65 高于 ≤7。主角表面实测见表；中心被遮挡的桌面不能直接测量。保持卡片固定配方，未自行调色或调整 sigma，不能宣称全卡视觉验收通过。最终平移帧已查看，两侧仍有背景纹理及明度差异，接色是否可接受留给审查。

测试结果解释：全量 JavaScript 为 60/62，通过后续回退，`node --test --test-concurrency=1 tests/test_presetio_browser.mjs tests/test_review_library_newwork.mjs` 再跑 2/2 通过，见 `cpu8/node-after-rollback.log`。剩余 `test_kit_browser.mjs` 的 `Preview must copy the :root token block` 断言仍失败；此前 OptiX 轮也记录了相同断言，相关 HTML/CSS 未修改，没有跳过该测试或调整断言。相关 Python 111/111 通过。

最终五张截图均已查看，包含本地示例报纸及真实平移中间帧，页面错误数组均为空。截图展示保留未过关旧图后的实际工作树，不是全范围完成的效果图。传真场景验证记录 50 个部件、非有限部件 0、零面积面 0，geometry_unchanged 和 copy_hash_unchanged 均为 true。

`cpu8/verification.json` 验证：16 个 CPU/8 线程运行记录、stage 脚本与仓库脚本哈希相同、输入原件及副本未变、195 个受保护文件未变、非目标 manifest / 导出报告条目未变、位置数据未变、5 张截图尺寸和错误状态合格。`git diff --check` 已通过，中文编码检查未发现连续问号替代字符。

已清理 15 处任务临时目录或输出链接，包括通过测试的虚拟光盘实验目录、浏览器配置和 pytest 临时数据；保留日志、截图、渲染结果、stage 输入以及失败测试现场，清单见 `cpu8/cleanup.json`。清理时 D / F 盘分别剩余 42,636,378,112 / 29,241,155,584 字节。
