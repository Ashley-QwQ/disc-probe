# FR 全量回归修复

分支 `dev/fullrun-fix`，起点 `c281f45`，包含原失败报告的 `fa26d74`。

## 提交和根因

- `4649876` 补齐学习页品牌资源。LG 的 `686cce0` 随 `45aea73` 合入，生成的五个页面都缺 favicon、Apple touch icon 和离线标题样式，资产检查访问缺失的 `icon` 键时报错。修改生成模板并重生成五页，检查失败时会显示页面路径。两份光栅卡手册改链到归档的 LG 报告，修复 `fa26d74` 恢复根报告后失效的章节链接。
- `80ea2ee` 将光栅卡数值求解推迟到执行命令。LG 的 `e0509d4` 随 `45aea73` 合入，注册 `gratingcard` 时提前导入 NumPy，导致屏蔽 NumPy 的解析阶段回归断言失败。用轻量模块注册原选项，执行时交给原求解器。复核了该命令的帮助与解析默认值，也验证了屏蔽 NumPy 时能建解析器、解析该命令的参数。
- `703013a` 修复 Windows 下的三个 burner 夹具。旧日志中的 `TEMP` 使用 8.3 短路径。CD TOC 保留了别名，测试预期规范路径。`web_no_verify_flag` 把别名根目录直接传给命令构造器，解析后的 ISO 无法匹配根目录。`web_token_blank_whitelist_and_job` 则在 argv 断言中预期别名。用 `c281f45` 的夹具和 D 盘目录联接复现三项，统一在夹具创建时解析根目录，并复用已有的临时用户状态隔离。复现用例只用模拟刻录器和运行器。 [修复前复现](../tmp/fullrun-fix/logs/burner-path-before.log)
- `703013a` 同时修复品牌和 CSP 浏览器测试的退出顺序。原日志中页面断言均先通过，之后才在删除配置目录时分别收到 `EBUSY` 和 `EPERM`。两份旧脚本单独复跑各通过 1 项，现场可确认为清理阶段的偶发失败。现在优先通过 CDP 关闭 Edge，等待自身进程退出，再以重试清理专用配置目录。CSP 也等待自身 Python 夹具退出后再删目录。是否有别的 Edge 进程加重了竞争未测。 [旧品牌测试复跑](../tmp/fullrun-fix/original-test_brand_browser.log) · [旧 CSP 测试复跑](../tmp/fullrun-fix/original-test_csp_browser.log)

## 验收

- `python -B -X utf8 tools/render_learning_guide.py --check` 检查 5 页、5 份配图。重生成的页面和改动的中文文档通过 UTF-8 字符核对。
- 定向 `pytest -q -n 2` 跑 `test_brand_assets.py`、`test_read_completion.py`、`test_burner.py`，使用 D 盘目录联接作为 burner 夹具的临时根。45 项通过、4 项子测试通过。对应三项在旧夹具中均复现。 [定向日志](../tmp/fullrun-fix/logs/targeted.log)
- `python -B -X utf8 D:/dp-dev/tmp/fullrun-fix/run_suite.py pytest` 以 `pytest -n 3` 覆盖 `tests/`、`disclab/tests/` 和 `tools/synth_photo_test.py` 的收集范围。1,510 项通过、0 项失败、2 项跳过，用时 575.89 秒。两个跳过项需要缺失的 `calib-simple` 参考和 `DISCLAB_A3_SOURCE` 夹具。原片递归检索用例按路径约束在收集时排除，已存测量结果复算仍执行。日志有一条既有的 `pcal.py` 空切片警告。 [全量日志及命令](../tmp/fullrun-fix/logs/pytest.log)
- 按文件单独执行 `node --test --test-concurrency=1`。37 个非浏览器文件、22 个浏览器文件共 59 个文件全部通过，83 项通过。四个旧式 DOM 导出脚本沿用 AM 的 CDP 预加载适配。品牌日志确认 3 个视图的字体和图标，CSP 日志确认 13 个静态路由、令牌手机页和 Lab 页的策略。 [非浏览器汇总](../tmp/fullrun-fix/logs/js-unit/summary.json) · [浏览器汇总](../tmp/fullrun-fix/logs/js-browser/summary.json) · [品牌日志](../tmp/fullrun-fix/logs/js-browser/test_brand_browser.log) · [CSP 日志](../tmp/fullrun-fix/logs/js-browser/test_csp_browser.log)
- `python -B -X utf8 D:/dp-dev/tmp/fullrun-fix/compare_defaults.py all` 沿用 AM 固定时钟和输入，复跑 `a7b5fbf` 的 23 组对照。18 组逐字节相同。CD/DVD 两种照片修正条件下的四个整盘 ISO、四份预设和四份附档哈希相同。5 组差异符合 AM 已记录的变化，分别是 `burn` 和 `photo` 的中英文帮助，以及带测量 MID 的 DVD 附档新增 `calibration_mid`。后者的 ISO 和命令输出也完全相同。实跑命令的退出码均为 0。 [逐项哈希](../tmp/fullrun-fix/logs/parity/comparisons.jsonl)

## Claude 转达

三个旧 burner 失败来自 Windows 临时路径别名，修复落在测试夹具。两个浏览器失败发生在成功断言后的配置清理。LG 合并带入的两个回归已在本分支修复。原片检索、实体光驱和实体刻录未测。验收使用独立回环服务和虚拟光驱，8765 保持原状。

全量测试前 D 盘余 131.71 GiB。成功测试的 Lab、浏览器配置和对照 ISO 已清理，整盘对照保留逐项哈希。冻结的 `discprobe/pcal.py` 和纹理图谱脚本与起点一致。提交均保留在本地分支。

STATUS: DONE
