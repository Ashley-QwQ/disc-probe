# 卡 CD · 彩色 DVD 使用说明

工作树 `D:/dp-dev/colourdocs`，分支 `dev/colour-docs`，基点 `2e6939c`。仅提交本分支。改动限于 README 的彩图部分、两个指南、配图与本报告。

## 按提交交付

- `db228f6` 更新中英文 README，新增 [中文版](docs/colour.zh.md) 和 [英文版](docs/colour.md)，附同一张 640 × 640 示例图和中英文各 7 张纸色截图。两版命令与参数一一对应。
- 本报告提交记录本地验收与待转达事项。

## 验收

- 以当前工作树的 CLI `--help` 和实现核对 `info`、`random`、`timing`、`geo`、`colour-design`、`compose`、`image`、`textures` 和 `burn`。手机距离依苹果尺寸图详图 D 计算。17 Pro 是 47.9 mm，17 Pro Max 是 53.6 mm，17 是 19.0 mm。后两项只用作自定义机位尺寸。
- Disc Lab 用 `python -m disclab box --lab <临时目录> --media dvd-r --count 2 --seed 17` 建箱。两次 `swap --drive X:` 分别放入测量盘、成品盘。用 `python -m disclab dp --lab <临时目录> -- <盘命令>` 包住指南中的 `info`、`burn`、`timing` 和 `geo`。出图命令在同一个临时目录直接运行。日志含完整实参。
- `info` 检出空盘，下一可写地址为 0，可写 2,298,496 扇区。测量镜像为 2,295,104 扇区，默认 8× 写入，96 块一致。`timing` 得出 CAV，`geo --ranges 0-2295088` 得到约 24.064–58.198 mm 覆盖，残差 RMS 0.069°。Lab 没有这个虚拟设备的真盘网格验证记录，所以仍提示核对读速。该提示只在虚拟链路里略过。第一次提前删除了虚拟测量盘引用的 ISO，`timing` 因此停止。复跑时保留测量 ISO 到 `geo` 完成。
- `colour-design` 生成 600 × 600 预测图，选用默认的 58 项候选并加入 12 点箭头。`compose` 输出 61 项材质索引，最后一项为 `RND`。20 µm 正常出图，`colour.iso.verification.json` 为 `passed`，ISO 长 2,295,104 扇区（4,700,372,992 字节）。成品盘以默认 8× 写入，96 块一致、0 块不同、0 块不可读、0 块未检查。此处是抽样回读。
- CLI 步骤耗时依次为 `random` 10.53 秒、测量盘 `burn` 29.66 秒、`timing` 2.19 秒、`geo` 4.06 秒、`colour-design --preview` 20.39 秒、成品盘 `burn` 57.13 秒。生成整盘镜像用两个 worker，抽样峰值为进程树 RSS，包含子进程，不能直接和设计页的旧基准对比。

| 网格 | 合成（秒） | 出 ISO（秒） | 峰值 RSS（GB） | ISO SHA-256 |
| --- | ---: | ---: | ---: | --- |
| 20 µm | 6.42 | 351.90 | 1.29 | `1a2254007e6c8902d70b33ceacfaacdd2c1f09468830c2eea5a923f74492b792` |
| 10 µm | 50.90 | 1012.43 | 1.21 | `22afac184eea4cf2a5b502f5c728c3be7e5e8a005d9b9877ed3406b3c28898c8` |
| 5 µm | 86.18 | 478.84 | 4.67 | `137843c2881b4cc1afcc9d077b583bbf61bfe6baf30dfd165101ec84ad547d9f` |

10 和 5 µm 用同一个作品改顶层 `cell` 后重新生成，镜像均为 4,700,372,992 字节，ISO 抽样核对均通过。虚拟刻录使用 20 µm。上述时间受本机同时运行的任务影响。

- 用 `node capture.mjs` 启动无头 Edge，经 CDP 驱动自开的 `webui --new-instance --local-only --port 0`。用同批虚拟测量记录验证大厅、批次、导图、58 项彩色填充、方向箭头、模型对照和实验纹理默认勾选。网页生成并以 8× 刻入虚拟光驱 X:，回读 96 块一致，结果页可查看。网页 ISO SHA-256 为 `e860ab7e72f8ff953171c58b5ff4a32457499d1ff8e0b306ef982c0f971e2679`。控制台异常 0。第一轮取图脚本因 270 秒等待上限退出，第二轮完成。首五步另在批次已选、预览已加载后取图。
- `python -m pytest -n 2 -p no:cacheprovider --basetemp <D盘临时目录>` 加 10 个相关测试文件，涵盖彩图、编辑器、纹理库、灯下预览、合成和刻录。193 项通过，689.71 秒。见 `python-regression.log`。
- `node --test --test-concurrency=1` 跑 59 个 `tests/test_*.mjs`，79 项中 75 通过、4 失败。只复跑失败文件，刻后流程（首次为 Windows 清理 EPERM）、中止刻录和曲线编辑通过。往期作品浏览器测试仍在等待 16 个作品格时超时（`test_pastworks_browser.mjs:209`），其代码和测试与基点一致。见 `node-regression.log`、`node-retry-regression.log`。
- `python -X utf8 check_docs.py` 检查指南与 README 更改中的 48 个链接引用，包括 3 个返回 200 的苹果 PDF。中英文 10 条命令逐字相同，14 张截图和示例 PNG 均可解码。中文文件非 ASCII 字符数大于零，无连续问号。`git diff --check` 通过。
- 开始时 D 盘剩约 152.5 GB，全量 Node 回归前约 141 GB。临时文件放在 `D:/dp-dev/tmp/colour-docs/`。完整镜像只保留 SHA-256；清理了本卡的 Lab 目录。8765 的监听 PID 核对为 31360。

## 请 Claude 转达

- **CLI 帮助**：`image --help` 列出 `--writable-sectors`，但 `cmd_image` 只在带 `--files` 时读取它。纯彩图指南改用 `--r-max` 和扇区数核对容量。
- **预览文案与显示**：实验纹理已经选中时，“刻之前”仍列出“刻成深浅两种纹理”。英文设计页在 1440 px 下截断 `Colour picture` 按钮文字，预览里的色彩图注与底部视图切换控件也有重叠。网页的相机和灯高度还显示长小数。请决定是否在发布前另开修复。
- **拍摄纸**：`tools/make_rulers.py --out rulers` 已运行，生成的 PDF 照片放盘页仍印旧的约 21 cm，高度尺为 22.3 cm。指南指出应按高度尺。请决定新版放盘页何时更新。
- **README 的历史分辨率说明**：5 µm 显微照片下面仍写着正式版没有这么细的选项。当前 CLI 和设计页支持 5 µm。该段在本卡的彩色章节之外，请发布审查时一并核对。

## 未测

未接触真光驱。当前网页导出路径、`vivid`、新手机与其他盘种（含 RW）的实刻显色未测。示例的实拍对照沿用库内早期试验盘照片。放盘尺已生成，未打印或实拍核对。

STATUS: DONE
