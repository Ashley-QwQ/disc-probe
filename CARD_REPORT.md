# HS 卡交付报告

工作树 `D:/dp-dev/helpsearch`，分支 `dev/help-search-20261118`，基点 `8fa1c4b`。提交均在本分支。

## 按提交交付

- `8ad9734` 增加 108 条中英双语排错条目、离线检索器、CLI、网页 API 和新手引导搜索框。最终条目库为 141,880 字节。
- `e119897` 增加 83 道题、计分脚本、来源与入口一致性测试，以及浏览器搜索交互回归。
- `8bc2159` 将笼统的拍照失败描述指向照片采用说明，提醒先看逐张拒绝原因。
- 本报告提交记录验收、十次实际 CLI 输出和待审事项。

CLI 接受问题、报错原文或 `-` 读标准输入。已安装的入口是 `disc-probe troubleshoot`，源码入口是 `python -m discprobe troubleshoot`。通过现有 `--lang zh|en` 选择语言。加 `--json` 后，与 `POST /api/troubleshoot` 返回同一 JSON 结构。网页请求发送 `{"query":"…","lang":"zh"}`，复用现有权限检查和 65,536 字节 JSON 请求上限。

日志匹配先归一化数字、LBA、盘符和常见路径。具备明确错误签名时优先展示这些条目。口语按汉字二元组和英文单词检索，最多展示三项。可信度表示与条目匹配的程度。低可信度时提示社区提问所需的五项信息。

## 验收

```text
python -B -X utf8 tests/score_troubleshoot.py
python -B -X utf8 -m pytest -n 2 -p no:cacheprovider --basetemp D:/dp-dev/tmp/helpsearch/feature-final2 tests/test_troubleshoot.py
```

| 题型 | 前三命中 | 首位命中 |
| --- | ---: | ---: |
| 报错原文和拟真日志（只计错误签名匹配） | 45/45 | 45/45 |
| 中英文口语 | 38/38 | 38/38 |
| 合计 | 83/83（100%） | 83/83（100%） |

首次查找含载入和索引构建为 37.667 ms。题库其余查询中位数 0.326 ms，最大 0.866 ms。追加 Azul-la 原文的 54,538 字节日志耗时 11.122 ms。十次独立 CLI 启动到退出的中位数为 490.940 ms，最大 635.415 ms，包含 Windows 进程启动、Python 导入和终端输出。

来源测试逐条校验仓库相对路径、行号和关键短语，另检查双语症状数量和手册锚点。入口测试比较 CLI 参数、UTF-8 标准输入、JSON 以及同一查询的 HTTP 响应，同时检查请求字段和会话校验。

| 回归范围 | 命令与结果 |
| --- | --- |
| 相关 Python | `python -B -X utf8 D:/dp-dev/tmp/helpsearch/suite.py targeted`，160 通过。最终新增测试另验 5 通过。 |
| 全量 Python | `python -B -X utf8 D:/dp-dev/tmp/helpsearch/suite.py python`，`pytest -n 2` 收集 1180 项，1178 通过、2 跳过、0 失败，约 9 分 11 秒。 |
| 全量 JavaScript | `python -B -X utf8 D:/dp-dev/tmp/helpsearch/suite.py js`，运行允许路径内全部 55 个 `test_*.mjs`，覆盖 66 项，最终均取得通过。首轮 57 通过、9 失败；修正离线测试配置后定向复跑恢复 8 项，最后一项 `test_afterburn_browser.mjs` 在单独复跑时通过，基点对照也通过。 |
| 引导页 | Edge 用本机回环服务验证提交日志、显示中文结果及无匹配提示。截图为 `navigation-shots/troubleshoot-zh.png`。 |

日志在 `D:/dp-dev/tmp/helpsearch/`。相关和全量记录分别是 `targeted.log`、`python.log`、`js.log`，JavaScript 复跑记录是 `js-retry.log`、`js-afterburn-final.log`，基点对照是 `js-base-afterburn.log`。原始计分与性能记录是 `score.json`，十次原始 CLI 输出是 `examples.json`。Python 和浏览器测试只调用本机虚拟夹具和回环服务。开跑前以及全量回归前均确认 D 盘剩余大于 5 GB。Linux 实机与光驱未测。

## 审查事项

- 任务卡里的 DVD 固定读速例子使用 `--speed 4x`。手册和参数解析将 `--speed 4` 解释为 4 kB/s。先用原盘换读速或光驱重测，再根据回读是否仍不稳决定要不要以另一种受支持的刻录速度重做测量盘。
- 端口和重复启动依据当前仓库实现。使用固定端口的 `webui` 实例需要可用端口。Windows 全量包启动脚本会为每次启动分配可用端口，并打印当前地址。
- 记录、标靶和颜色建议来自仓库证据。实盘操作和建议效果未测。命中率只针对本次题库，条目与题库在同一轮迭代。
- 条目措辞及是否进入 alpha 由维护者审查。

## 十次实际 CLI 查询

以下五次中文、五次英文查询的标准输出由测试脚本读取。第 1 次通过标准输入传入三行日志，其余通过参数传入。

### 1. zh · 标准输入

```text
Zone 0.95 (LBA 2062016): no period found
Rotation: unknown (zones [0.95] have no clear period; the speed may be changing, try a fixed --speed)
Rotation is unknown, not CAV, so the phase test would not give disc angles; skipping it. Try another --speed, or pass --force to run it anyway.
```

```text
1. 报错所在测区可能变速了或读得不稳定。外圈经常是出现变速的位置，计时无法确定清晰的转动周期。 [timing-no-period, 可信度 100%]
   - 先用固定低读速重测同一张盘。DVD 可试 4x，并看 timing 报告的实际转速。
   - 先别加 --force，它只继续诊断采样。换读速或光驱后仍读不稳，且需要重刻测量盘时，试另一个受支持的刻录速度。
     python -m discprobe timing --drive <drive> --speed 4x
   手册在 docs/MANUAL.md#timing-做三个实验。
```

### 2. zh · 参数

```text
刻完读不出来
```

```text
1. 当前盘上的部分扇区可能不可读，刻有图案的盘也可能很难读。 [unreadable-after-burn, 可信度 100%]
   - 检查刻录报告和保存的读错记录。关闭其他光驱软件，重装盘，先换读速或光驱重读。
   - 测量优先用已有的普通数据盘；没有可用盘时才重做测量盘。
     python -m discprobe info --drive <drive>
     python -m discprobe timing --drive <drive>
   手册在 docs/MANUAL.md#手动使用。
```

### 3. zh · 参数

```text
颜色不对
```

```text
1. 结构色随灯光和观察角度变化。纹理预览的颜色用于区分材料，灯下效果是预测。 [colour-wrong, 可信度 100%]
   - 按拍摄设置对准角度。拍实验花盘时关掉房间灯，只用手机闪光灯并稍稍侧持手机。
   手册在 docs/MANUAL.md#刻图纹理与颜色。
```

### 4. zh · 参数

```text
拍照一直不通过
```

```text
1. 当前照片没有得到可用于出图的已采用读数。 [photo-no-adoption, 可信度 100%]
   - 查看每张照片下的重拍提示。用同一张盘拍不同角度，等至少两张读数一致。
   手册在 README.md#第-6-步看盘和拍照。
```

### 5. zh · 参数

```text
linux 说没权限
```

```text
1. 运行用户需要有光驱设备的读写权限。 [linux-permission, 可信度 100%]
   - 通常将用户加入 cdrom 组后重新登录，再检查 /dev/sr* 权限。网页服务继续用普通用户运行。
     sudo usermod -aG cdrom "$USER"
   手册在 INSTALL-linux.md#linux-安装1000-alpha。
```

### 6. en · 参数

```text
Rotation is CLV, not CAV, so the phase test would not give disc angles; skipping it. Try another --speed, or pass --force to run it anyway.
```

```text
1. This read speed did not give the constant angular velocity needed to measure sector angles. [timing-clv, Confidence 100%]
   - Try an untried read speed. A higher one may give CAV on CD. Try another drive when the listed speeds are exhausted.
   - Blu-ray has a separate CLV geometry route.
     python -m discprobe timing --drive <drive>
   The manual is docs/MANUAL.en.md#the-three-experiments-in-timing.
```

### 7. en · 参数

```text
A preset needs --sectors: the capacity of your disc (`info` prints it)
```

```text
1. DIS uses the sector count to define the capacity and outer radius. [dis-sector-count, Confidence 100%]
   - Run info on a blank from the same batch and use its available sector count in --sectors and DiscImageStudio.
     python -m discprobe info --drive <drive>
     python -m discprobe disexport --geo <run> --sectors <count>
   The manual is docs/MANUAL.en.md#using-it-by-hand.
```

### 8. en · 参数

```text
error: [WinError 10048] Only one usage of each socket address (protocol/network address/port) is normally permitted
```

```text
1. Another process may already be bound to the requested HTTP port. [web-port, Confidence 100%]
   - Use the existing local page if it is already serving the session you want. For a separate instance, use --port with an available port and open the printed address.
     python -m discprobe webui --local-only --port <free-port>
   The manual is README.en.md#web-page.
```

### 9. en · 参数

```text
colour picture needs a phone and shooting height in scene.rig
```

```text
1. Colour mapping depends on the phone and shooting height. [colour-pose, Confidence 100%]
   - Set the phone and shooting height in the design, or read the pose options in colour-design help.
     python -m discprobe colour-design -h
   The manual is docs/MANUAL.en.md#burning-pictures-textures-and-colour.
```

### 10. en · 参数

```text
What is the Wi-Fi router password?
```

```text
No definite answer found. When asking the community, include your drive model, disc brand, write speed, read speed and complete log.
```
