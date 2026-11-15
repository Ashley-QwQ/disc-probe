# C3：记录的文件哈希不受换行符影响

工作目录：`D:/dp-dev/hasheol`；分支：`dev/hash-eol`；验收比较基点：`ffd369d`。
已先读取 `D:/dp-dev/cards/COMMON.md` 和 `D:/dp-dev/cards/hash-eol.md`。

## 按提交列出的改动

本卡一个提交，标题为 `fix: make focal provenance hashes independent of checkout EOLs`，包含以下内容及本报告：

- 新增 `discprobe/hashing.py`，提供 `file_sha256` 和 `content_sha256`。按大小写不敏感的扩展名白名单判断文本，只把 CRLF 替换为 LF；不解码、不去 BOM、不删空格、不转换单独的 CR。白名单完整列在 `TEXT_SUFFIXES`：`.py .json .md .txt .csv .js .mjs .ts .tsx .jsx .css .html .htm .svg .xml .toml .yaml .yml .ini .cfg .rst .sh .ps1 .bat .cmd`。其他扩展名及无扩展名一律按原字节计算；二进制采用分块读取。
- `tools/focal_geometry.py`、`tools/editor_pose_swatches.py`、`tools/focal_regression.py`、`tools/focal_capture.py`、`tools/focal_verify_rulers.py` 的新文件来源记录统一使用共用函数。解压后的夹具按逻辑扩展名 `.json` 处理，而非按容器 `.gz` 处理。
- `tests/test_editor_pose_swatches.py` 改用共用函数核验来源；几何测试通过生成器导入的同一函数检查。新增 `tests/test_hashing.py`，覆盖白名单、大小写、LF/CRLF/混合换行、二进制和未知扩展名、分块边界、内容变化检测及解压夹具的两种换行。
- 重跑几何、色卡和回归生成器，更新 4 个 JSON 产物；补充 `tools/focal_data/README.md` 的哈希规则说明。
- 新增 `tools/check_focal_hash_fields.py`，与指定 Git 基点逐字段比较 4 个产物，检查类型、键、数组长度及全部叶子值，只允许明确列出的来源哈希字段变化；颜色、坐标、`sets_sha256` 等字段变化会失败。
- 新增 `tools/check_focal_hash_eol.py`，备份并把本 worktree 的 15 个明确列出的文本文件转成 CRLF，运行相关测试及生成器检查，最后在 `finally` 中逐字节恢复，并输出恢复证明。

历史外部配方里的校验值保留原始字节语义；`focal_capture.py` 对这些既有配方输入的比对仍按原字节执行。色卡 `sets_sha256` 是规范 JSON 内容摘要，保持原算法。发行包、光盘数据、PNG 像素等其他精确校验不属于本卡的来源哈希，未更改。

## 产物逐字段比较

命令：

```powershell
python -B -X utf8 tools/check_focal_hash_fields.py --baseline ffd369d --out D:/dp-dev/tmp/hash-eol/hash-fields.json
```

结果：**4 个产物，8 个哈希字段变化，非哈希变化 0**。两份色卡的 5 + 255 组颜色、暗色标志、相机/闪光灯坐标及全部其他字段不变。`focal-geometry.mjs` 没有 Git 内容差异。

下表中的“两个色卡”分别指 `discprobe/web/home/design/pose-swatches.json` 和 `discprobe/web/home/design/pose-swatches-custom.json`；每行各改变两个字段实例。

| 文件 / 字段 | 基点值 | 新值 |
| --- | --- | --- |
| `data/focal/pose_1x.json` / `source.legacy_sha256` | `e2465e5a972340277af58a311f7def41d86b9372b1494d7e623bf581d79689ee` | `c6b73619894cbb74ec5a6c812bef1b63eed294e841692956d58e93af333f85f4` |
| 两个色卡 / `source.palette_sha256` | `a13cf8ca900daae3eacf21605dcc15ca456dbea5867d2a3a4e15e8e7370d8e6b` | `e70dbcbdb72ad1a205ad7e20c7cc7312689d10fd498c90de14d1c47554075615` |
| 两个色卡 / `source.generator_sha256` | `03fc81361832ad23522b7aec4528550ac40f287e7d011ae44ee2426e0d71d269` | `3c21e75d76ac256b64ad3442abfd0f7ccd7382ffdc3277a847961e96297618c2` |
| 两个色卡 / `source.pose_sha256` | `c459a83b69d21b1210a3ed330846d81177e614df9ce8c2d7cddb4332256e6e29` | `f285ec0217a48dfe2065c751665739a6fd970325a4984b97463e3191e63d0083` |
| `tools/focal_data/regression.json` / `fixture_sha256` | `3b588faad2d978ab4664f87fae65065c4f2e111f90ff681b243eca744566035e` | `b6cdc031d5370f8c76017c72c9eb98b5c2033bbd998aa71aa320e137beb200de` |

生成器哈希包含本次代码修改；pose 哈希随其上游 legacy 哈希更新。压缩夹具内部原本就是 CRLF，因此它解压后的 JSON 摘要变化；冻结 `.gz` 本身未改。所有 `geometry_sha256`、`calibration_sha256`、二进制表摘要、delta map 摘要及色卡 `sets_sha256` 均不变。

## 验收命令与数字

解释器：本机 Python 3.13.14，pytest 9.1.1，NumPy 2.5.1。所有 Python 命令使用 `-B -X utf8`；子进程另设 `PYTHONDONTWRITEBYTECODE=1`。`TEMP`、`TMP` 均设为 `D:/dp-dev/tmp/hash-eol`，几何缓存设为该目录下的 `cache`；CRLF 工具为其子进程使用自己的 `--out` 目录。pytest 均用 `-n 2`。

1. 重新生成：

   ```powershell
   python -B -X utf8 tools/focal_geometry.py
   python -B -X utf8 tools/editor_pose_swatches.py
   python -B -X utf8 tools/focal_regression.py --out tools/focal_data
   ```

   三条命令退出码均为 0。几何为 `f=3355.0 px`、桌面高度 `223.039615 mm`、盘面高度 `221.739615 mm`；色卡生成 5 + 255 组；回归保留 69 种原始纹理、18 个尺块，最大绝对 delta 残差仍为 `0.005628707126183352`。

2. 故意转 CRLF 并恢复：

   ```powershell
   python -B -X utf8 tools/check_focal_hash_eol.py --out D:/dp-dev/tmp/hash-eol/crlf-final
   ```

   15/15 个输入及产物文本确认只含 CRLF 换行；相关 Python 测试 **70 passed，12.48 s**；`focal_geometry.py --check` 和 `editor_pose_swatches.py --check` 均通过；**15/15 个文件逐字节恢复成功**。`crlf-final/result.json` 保存文件名单、原始字节 SHA256、三个子命令退出码和 `restored_exactly=true`，同目录保存备份及日志。

   首次运行记录在 `D:/dp-dev/tmp/hash-eol/crlf`：68 passed、1 failed。失败来自新增测试把已经是 CRLF 的解压夹具再次直接替换 LF，构造出了双 CR。已修正为先统一成 LF，再分别构造 LF/CRLF 两个参数用例；首次失败后 15 个文件也已恢复。最终通过记录使用独立目录保留。

3. 恢复后的最终相关 Python 回归：

   ```powershell
   python -B -X utf8 -m pytest -n 2 -q --basetemp D:/dp-dev/tmp/hash-eol/pytest-final tests/test_hashing.py tests/test_editor_pose_swatches.py tests/test_focal_geometry.py tests/test_editor_preview.py tests/test_focal_packaging.py
   ```

   **70 passed，16.55 s，退出码 0**。其中新增哈希测试 41 项、色卡 10 项、焦距几何 13 项、预览 2 项、相关打包 4 项。任务卡指定的三个测试文件合计 25 项全部通过。日志：`D:/dp-dev/tmp/hash-eol/pytest-final.log`。

4. 全部 `tests/test_*.mjs`：

   ```powershell
   $nodeTests = @(rg --files tests -g 'test_*.mjs' -g '!**/*blind*' -g '!**/*blind*/**' | Sort-Object)
   node --test --test-concurrency=2 @nodeTests
   ```

   收集 **36 个文件**，Node 汇总 **40 tests / 40 pass / 0 fail / 0 skipped**，耗时 `55131.1587 ms`，退出码 0。日志：`D:/dp-dev/tmp/hash-eol/node-final.log`。测试自动生成的截图和预览证据已移到 `D:/dp-dev/tmp/hash-eol/test-evidence`，不进入提交。

5. `git diff --check`（排除公共规则指定路径）通过；提交前另检查报告 UTF-8 中文数量及连续问号。报告及代码以 UTF-8 写入，没有把非 ASCII 脚本经 PowerShell 管道发送给原生程序。

## 未测及需人决定的事项

- Linux 实机克隆：未测。已用 LF/CRLF 单元测试、本 worktree 的真实 CRLF 文件及当前混合换行状态验证；不据此声称 Linux 实机验收。
- 一次性外部来源抓取 `focal_capture.py` 和原始 PDF 图像比对 `focal_verify_rulers.py`：未运行。仅统一它们的新记录哈希调用；未重新提取或覆盖冻结证据。PDF 后缀按原字节处理，规则由单元测试覆盖。
- 未运行无关 Python 全套测试；未接光驱、未刻盘、未上传或下载；未推送、未合并、未切换分支；未修改其他 worktree 或公共规则禁止修改的纹理脚本。
- 无需人决定的界面或审美取舍。本卡未改变页面视觉、颜色、布局和文案。
