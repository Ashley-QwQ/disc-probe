# 卡 R：最终历史基线核对与亮纸修正

本轮按最新更正执行：**15/16 个 job、20 张夜色导出已保留；预设桌面 1 个 job 仍保留原图。** 本轮相对 `25930fb` 新增 11 张实际变化的 WebP。纸色图片始终不写入。`F_np_paper` 和 `F_np_desk` 已使用 CPU、8 线程重渲双主题；其余 14 个不含可见 sheet_light 物体的 job 复用上一轮 CPU 原始渲染，重新运行当前导出工具核对，不重复烤图。

## 提交与范围

- `a989a6a`：中性桌面/主角分光、夜色 sigma ×.557、线条 .88 / .35 / 剪影下限 .6。
- `3183a15`：重现已记录编码配方。
- `0e47522`：CPU 与 Night B 绝对门槛；`25930fb`：上一轮通过项、失败项和亮纸对比度回退的记录。
- `a73c213`：新增 `--paper-gate night-b-recorded`；固定读取 `3c3f66a` 的 Git 对象；sheet_light 填色及线条使用原 sigma，桌面和其它物体保持 .557 倍。新增边界、缺失基线、白名单隔离、不可变 Git 基线测试，单测 12/12 通过。
- 本次提交 `art: apply recorded Night B checks and restore sheet pool width`：更新通过门槛的夜色图片、分物体类型 sigma、manifest、导出报告和本报告。

始终在 `web/night-pool-20261116`，未推送、未合并、未修改其他 worktree。未接光驱、刻盘、下载或上传；未改 `evidence/atlas/*.py`、已提交 caltop、index.html 或 CSS。递归操作排除用户指定的禁用名称与子树。

## 门槛与输入证据

历史基线：`3c3f66a:tools/night_b_manifest.json`，blob SHA-1 `74f5b32826511e6390e381d3e94acf45dbe976c1`。工具直接 `git show` 读取，绝不从当前可变 manifest 取比较基线。

- 仅 `pastworks/tumble_0_dark.webp` … `tumble_9_dark.webp` 和 `presetio/desk/desk_knob_dark.webp` 用历史差值：RGB mean 相差 ≤.05，alpha mean 相差 ≤.01，>8 相差 ≤.1 **个百分点**。缺失或格式错误的历史值拒绝写入。
- 其它所有图片仍用绝对门槛：RGB mean ≤.3，alpha mean ≤.02，>8 ≤.1%。统计沿用原工具可见像素定义；判断使用未舍入值。一个 job 的所有层都通过后才写入，不进行部分写入。
- `sheet_light` 原有 amb/gain/add 完全不动，其物体在夜色下使用原始 sigma；纸色参数不动。物体 ID 还让纸的线条透明度跟随这个原始光池，其它对象线条跟随收窄的光池。元数据明确区分默认/桌面与 sheet sigma；纸张整层记录其实际 sheet sigma。

输入仍为用户提供的 x79 stage、指定 D 盘只读托盘与传真场景，以及 F 盘光驱场景副本。脚本和输入只放 `F:/dp-archive/tmp/nightpool/recorded/stage/`，未复制进仓库。新渲染命令为 Blender 5.2.2 LTS、`-t 8 --device CPU --variants paper,dark`，其它参数照 manifest；逐 job 命令和日志见 `recorded/<JOB>-run.json`、`<JOB>.log`。复用记录含 `reused_from`，不冒充本轮重渲。

本轮开始 D / F 盘分别剩余 42,635,513,856 / 29,241,143,296 字节，均高于 5 GB。全部渲染、临时文件和日志在 F 盘。先重渲并查看 `F_np_paper/paper_dark.png`，再核对、写入，并继续桌面重渲及其余核对。

## Job 结果

| Job | 渲染来源 | 图片数 | 结果 | 未通过的图片 |
| --- | --- | ---: | --- | --- |
| `F_np_top` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_np_paper` | 重渲 | 2 | 已写入 | 无 |
| `F_np_env` | 复用 CPU 渲染 | 2 | 已写入 | 无 |
| `F_np_desk` | 重渲 | 12 | 未写入 | desk_knob_dark.webp |
| `F_pw_env` | 复用 CPU 渲染 | 2 | 已写入 | 无 |
| `F_fax_top` | 复用 CPU 渲染 | 3 | 已写入 | 无 |
| `F_tumble0` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble1` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble2` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble3` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble4` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble5` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble6` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble7` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble8` | 复用 CPU 渲染 | 1 | 已写入 | 无 |
| `F_tumble9` | 复用 CPU 渲染 | 1 | 已写入 | 无 |

命令（核对通过后才再加 `--write`）：

```text
python -X utf8 -B tools/night_b_export.py F:/dp-archive/tmp/nightpool/recorded --only <group> --jobs <JOB> --paper-gate night-b-recorded --check-report F:/dp-archive/tmp/nightpool/recorded/<JOB>-paper-check.json
```

### 历史差值图片

最后一项差值单位为百分点；门槛是 .1，不向上放宽或先粗略舍入。

| 图片 | 3c3f66a 记录 | 差值 RGB / alpha / >8 | 结果 |
| --- | --- | --- | --- |
| `presetio/desk/desk_knob_dark.webp` | mean 1.49, alpha mean 0.00, px >8: 1.474% | 0.003802714 / 0.000081923 / 0.109863586 | 超限 |
| `pastworks/tumble_0_dark.webp` | mean 1.40, alpha mean 0.11, px >8: 3.859% | 0.002787726 / 0.002607422 / 0.017206227 | 通过 |
| `pastworks/tumble_1_dark.webp` | mean 1.43, alpha mean 0.11, px >8: 4.403% | 0.007801425 / 0.001484375 / 0.003318436 | 通过 |
| `pastworks/tumble_2_dark.webp` | mean 1.91, alpha mean 0.09, px >8: 5.685% | 0.003332904 / 0.001540527 / 0.000281367 | 通过 |
| `pastworks/tumble_3_dark.webp` | mean 1.62, alpha mean 0.10, px >8: 4.729% | 0.003789667 / 0.000581055 / 0.022469709 | 通过 |
| `pastworks/tumble_4_dark.webp` | mean 2.01, alpha mean 0.10, px >8: 6.410% | 0.001860868 / 0.004995117 / 0.012037619 | 通过 |
| `pastworks/tumble_5_dark.webp` | mean 3.33, alpha mean 0.08, px >8: 10.492% | 0.000751731 / 0.002609863 / 0.000216101 | 通过 |
| `pastworks/tumble_6_dark.webp` | mean 1.70, alpha mean 0.10, px >8: 4.776% | 0.003810177 / 0.001267090 / 0.000420246 | 通过 |
| `pastworks/tumble_7_dark.webp` | mean 1.73, alpha mean 0.10, px >8: 6.052% | 0.002776931 / 0.004138184 / 0.041434239 | 通过 |
| `pastworks/tumble_8_dark.webp` | mean 1.72, alpha mean 0.10, px >8: 5.313% | 0.001215548 / 0.001943359 / 0.036710545 | 通过 |
| `pastworks/tumble_9_dark.webp` | mean 2.99, alpha mean 0.08, px >8: 8.369% | 0.001353769 / 0.002458496 / 0.023202934 | 通过 |

### 全部纸色核对

| 对应夜色图 | RGB mean | alpha mean | >8 比例 | 实际门槛 | 结果 |
| --- | ---: | ---: | ---: | --- | --- |
| `newplan/top_dark.webp` | 0.000706199 | 0.000000000 | 0.000352648% | night-b | 通过 |
| `newplan/paper_dark.webp` | 0.086849700 | 0.000027311 | 0.000000000% | night-b | 通过 |
| `newplan/paper_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `newplan/envelope_back_dark.webp` | 0.082867290 | 0.000004010 | 0.001248330% | night-b | 通过 |
| `newplan/envelope_front_dark.webp` | 0.044468302 | 0.000013282 | 0.015640509% | night-b | 通过 |
| `presetio/desk/desk_bag_dark.webp` | 0.257081071 | 0.000003255 | 0.087357698% | night-b | 通过 |
| `presetio/desk/desk_bag_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `presetio/desk/desk_base_dark.webp` | 0.020940032 | 0.000000000 | 0.003824870% | night-b | 通过 |
| `presetio/desk/desk_doc_envelope_dark.webp` | 0.060746636 | 0.000001085 | 0.009340801% | night-b | 通过 |
| `presetio/desk/desk_doc_envelope_shadow_dark.webp` | 0.000003391 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `presetio/desk/desk_doc_paper_dark.webp` | 0.039737751 | 0.000010851 | 0.000209097% | night-b | 通过 |
| `presetio/desk/desk_doc_paper_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `presetio/desk/desk_knob_dark.webp` | 1.493802714 | 0.000081923 | 1.364136414% | night-b-recorded | 超限 |
| `presetio/desk/desk_knob_shadow_dark.webp` | 0.000000000 | 0.000040148 | 0.000000000% | night-b | 通过 |
| `presetio/desk/desk_sheets_dark.webp` | 0.128970037 | 0.000000000 | 0.002103500% | night-b | 通过 |
| `presetio/desk/desk_sheets_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `presetio/desk/desk_upper_dark.webp` | 0.108992689 | 0.000001085 | 0.008684816% | night-b | 通过 |
| `pastworks/envelope_back_dark.webp` | 0.036730435 | 0.000005678 | 0.001639070% | night-b | 通过 |
| `pastworks/envelope_front_dark.webp` | 0.120485416 | 0.000004867 | 0.065212434% | night-b | 通过 |
| `faxnews/top_dark.webp` | 0.001466019 | 0.000000000 | 0.000135634% | night-b | 通过 |
| `faxnews/handset_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `faxnews/handset_shadow_dark.webp` | 0.000000000 | 0.000000000 | 0.000000000% | night-b | 通过 |
| `pastworks/tumble_0_dark.webp` | 1.402787726 | 0.112607422 | 3.876206227% | night-b-recorded | 通过 |
| `pastworks/tumble_1_dark.webp` | 1.437801425 | 0.108515625 | 4.399681564% | night-b-recorded | 通过 |
| `pastworks/tumble_2_dark.webp` | 1.913332904 | 0.088459473 | 5.685281367% | night-b-recorded | 通过 |
| `pastworks/tumble_3_dark.webp` | 1.616210333 | 0.100581055 | 4.706530291% | night-b-recorded | 通过 |
| `pastworks/tumble_4_dark.webp` | 2.008139132 | 0.104995117 | 6.422037619% | night-b-recorded | 通过 |
| `pastworks/tumble_5_dark.webp` | 3.329248269 | 0.077390137 | 10.491783899% | night-b-recorded | 通过 |
| `pastworks/tumble_6_dark.webp` | 1.703810177 | 0.101267090 | 4.776420246% | night-b-recorded | 通过 |
| `pastworks/tumble_7_dark.webp` | 1.727223069 | 0.095861816 | 6.010565761% | night-b-recorded | 通过 |
| `pastworks/tumble_8_dark.webp` | 1.721215548 | 0.101943359 | 5.276289455% | night-b-recorded | 通过 |
| `pastworks/tumble_9_dark.webp` | 2.991353769 | 0.077541504 | 8.392202934% | night-b-recorded | 通过 |

`night_pool_recorded` 是本轮记录；旧 `night_pool_attempt` / `night_pool_cpu` 保留历史含义。未写入图片保留原来源，另附本轮失败数字。原始 renderer sigma 记录中的默认光池用于桌面/其它物体，`sheet_pool_sigma_px_by_theme` 是纸实际使用的宽光池；纸张位置元数据以此作为有效 sigma。

## 实际图片 L* 与暖色

测量仓库实际解码后的 WebP。桌面用物体 ID 掩码，排除道具和线条周围 3px；边缘为左/下各 5px 条带内桌面像素中位数。主角为 body/tray 表面的最大/最小 L*，排除盘、LED、洞腔和线条；透明信封、亮纸、阴影等无桌面/主角的层记为不适用，不把透明黑当作桌面。

| 已写入图片 | 中心桌面 L* | 左 / 下边缘 L* | 主角最亮 / 最暗 L* |
| --- | --- | --- | --- |
| `newplan/top_dark.webp` | 遮挡；近点 11.37 | 7.65 / 5.58 | 37.03 / 13.52 |
| `newplan/paper_dark.webp` | 不适用 | 不适用 | 不适用 |
| `newplan/paper_shadow_dark.webp` | 不适用 | 不适用 | 不适用 |
| `newplan/envelope_back_dark.webp` | 不适用 | 不适用 | 不适用 |
| `newplan/envelope_front_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/envelope_back_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/envelope_front_dark.webp` | 不适用 | 不适用 | 不适用 |
| `faxnews/top_dark.webp` | 19.78 | 6.18 / 7.17 | 32.92 / 9.89 |
| `faxnews/handset_dark.webp` | 不适用 | 不适用 | 17.81 / 3.35 |
| `faxnews/handset_shadow_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_0_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_1_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_2_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_3_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_4_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_5_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_6_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_7_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_8_dark.webp` | 不适用 | 不适用 | 不适用 |
| `pastworks/tumble_9_dark.webp` | 不适用 | 不适用 | 不适用 |

中心被遮挡时明确标出最近可见点，不能声称测到了遮挡处的桌面。坐标、距离、RGB 和边缘范围见 `recorded/validation_report.json`。亮度与卡片约 16 / ≤7 / 35、14 的差距照实保留，未自行调整固定配方。

| 桌面图 | OKLCH 暖色像素 / 桌面掩码像素 | 比例 |
| --- | ---: | ---: |
| `newplan/top_dark.webp` | 0 / 3117837 | 0.0000000% |
| `faxnews/top_dark.webp` | 0 / 3356845 | 0.0000000% |

暖色定义为色相 30–90°且彩度 >.02。

## 截图与测试

最终五张 1440×1000 夜色截图放在 `F:/dp-archive/tmp/nightpool/shots/`，后缀为 `-recorded-dark.png`：新作品页、设计页→预设页、往期作品页、传真新闻页、新作品页→标定页平移中间帧。使用本地练习服务和无头 Edge；平移动画停在实际 760ms 动画的 380ms。状态与页面错误见 `shots/capture-recorded.json`。

全量 `node --test --test-concurrency=2 <排除禁用路径后的全部 tests/test_*.mjs>`：

```text
ℹ tests 62
ℹ suites 0
ℹ pass 61
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 198374.9353
```

相关 Python，`pytest -n 2 tests/test_night_pool.py tests/test_presets.py tests/test_works.py`（TEMP、basetemp 均在 F 盘，禁用缓存写入）：

```text
bringing up nodes...
bringing up nodes...

........................................................................ [ 62%]
...........................................                              [100%]
115 passed in 25.36s
```

移动预设页对比度已通过原 `test_presetio_browser.mjs` 的 ≥4.5 断言。另在真实练习页面的 390×900 夜色布局中，用同样的原生纸图取样和计算方式量得：正文 10.281308769，标签和副标题最低 4.894513001，导入/导出两栏均通过。数据包含纸图 SHA-256，见 `recorded/contrast.json`，不依赖修改 CSS 或测试断言。

全量 JavaScript 61/62；唯一未解决的是 `test_kit_browser.mjs` 的 `Preview must copy the :root token block` 断言，此前各轮也记录了同一失败。相关 HTML/CSS 未修改，没有跳过或修改断言。新作品、传真、往期作品、预设页相关浏览器测试均通过；相关 Python 115/115 通过。

## 仍未完成与最终保护检查

预设旋钮重渲后的实际值为 RGB mean 1.493802714、alpha mean 0.000081923、>8 为 1.364136414%；`3c3f66a` 记录为 1.49 / 0.00 / 1.474%。对应差值为 0.003802714 / 0.000081923 / **0.109863586 个百分点**。第三项仍大于用户给定的 0.1，因此预设桌面整组 12 张未写入，不能把接近门槛当作通过。其余 31 张图片各自通过所适用的门槛；其中预设桌面其它 11 层随该 job 一起保留原图。

完整卡 R 的视觉验收仍未全部完成。已写入图片的 L* 差距按表保留：传真桌面中心 19.78（目标约 16），下边缘中位数 7.17（目标 ≤7）；新作品页左边缘中位数 7.65。没有自行调整用户指定配方。新作品页和传真桌面掩码内暖色像素均为 0；预设桌面仍是旧图，不宣称它完成了中性化。

五张最终截图均已查看，尺寸为 1440×1000、夜色，页面错误数组均为空，包括真实的平移中间帧；平移两边的纹理和明度差异仍留待审查，不宣称无缝接色。预设页截图显示保留旧桌面后的真实工作树。

`recorded/verification.json` 已通过：固定历史 blob、仅 11 张使用历史门槛、32 张核对记录、14 个复用 job 的原始文件哈希相同、新 stage 脚本与仓库脚本匹配、输入原件和副本不变、195 个受保护文件（116 张纸色）哈希变化 0、非目标 manifest/导出报告条目不变、既有位置字段不变。纸张有效 sigma 在两主题均为 1181.538px；纸色原参数未改。

清理了 14 处通过测试的临时目录、虚拟光盘实验目录、浏览器配置或输出链接，保留渲染、输入、日志、截图和失败测试现场，见 `recorded/cleanup.json`。清理时 D / F 盘分别剩余 42,623,733,760 / 29,064,507,392 字节。`git diff --check` 与 UTF-8 中文检查在提交前通过；没有推送或合并。
