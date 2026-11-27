# LM · 盘库和往期作品

分支 `dev/library-manage`，基点 `738889d`。所有写入、恢复和光驱验收在 D 盘独立工作区和 Disc Lab 内完成。

## 提交

- `e3f244d` 增加 `library list/show/delete/trash/restore` 和 API 1.4 的 `library-management` 能力。批次回收覆盖关联几何、可追溯的转速记录和专用预设。预览列出文件、共享预设及依赖作品，确认时可选择保留或一起移走作品。恢复检查路径冲突，可继续完成被打断的移动。
- 同提交为往期作品的鼠标和 Delete 键入口加入文件说明和确认，沿用撤销。CLI 用 `works list --trash` 找回收编号。两个删除命令都支持 `--json` 和显式 `--permanent`。
- 同提交保存标定验收记录。盘库用实测区间识别旧记录的空档，保留较早通过的结果并标出后一次拒绝。网页保存和 core 校准保存检查拒绝状态。续测会重新检查临时排除的区域，在每个重新开放的内部空档内补读，并沿用 RWA 的同盘、光驱和转速检查。
- 同提交增加盘库和光驱页的主标定入口。光驱按型号或驱动器编号匹配，分别显示通过和未完成的批次，移除空白 Burns/Reads 栏。光驱影子朝左下。编辑器保留三段可测环和边界刻度，在空间允许时显示数字。回收批次后，保留的作品可在编辑器重新选批次。
- `36c24ba` 让校准重试浏览器用例等待目标页面和 DOM 就绪，覆盖切页时短暂没有根元素的情况。

## 2,251,920 扇区的来源

旧盘库把测量摘要的 `setup.last_lba + 1` 当作容量。此次 Disc Lab 用 `last_lba = 2,251,919` 复现了显示值。网页的测量镜像策略是容量乘 0.98 后向下对齐到 16 扇区。以 2,297,888 为输入，恰好得到 2,251,920。这里只复算了代码路径，原 11-19 运行的输入未测。

盘库现在把空白盘容量从已写区长度分开。旧 RITEKF1 行无明确容量时使用任务卡给出的 2,295,104。新记录保留读到的空白容量或者显式指定的容量及其来源。未填的同桶余量显示「未记录」。历史计数仍按同批次归集，覆盖或验收失败归入待处理。

## 验收

- `python -m discprobe --lang zh library delete --help` 验证中文参数帮助。临时工作区通过 JSON CLI 测了回收、恢复、永久删除、共享预设、恢复冲突和中断恢复。测试也用走查中的 36.88–40.43、47.13–49.57 mm 验证旧数据。
- Disc Lab 使用固定种子 178 和独立虚拟光驱 X:。正常标定导出通过，指定三段的 `geo --ranges` 保留两个空档，`calibrate --avoid-mm … --preset …` 拒绝并留下验收记录。对同一虚拟盘运行 `calibrate --resume … --preset …` 后，在两个旧空档内得到 38.78、49.01 mm 测点，覆盖 24.49–56.01 mm，预设写出。 [续测日志](D:/dp-dev/tmp/libmanage/logs/lab-resume.log)
- 无头 Edge 加 CDP 对照 `738889d`。盘库、光驱、作品详情、编辑器各有 8 组前后图，另有 2 张删除确认，共 66 张。覆盖中英文、纸色和夜色、1440×900 和 390×844。验证删批次并保留作品、一起移走、取消、撤销，以及作品删除和恢复。网页版拒绝重新导出被拒记录。8 组改后标尺文字边界都无重叠。 [截图](D:/dp-dev/tmp/libmanage/shots/) · [截图记录](D:/dp-dev/tmp/libmanage/shots/capture.json)
- 相关 Python 测试用 `python -B -X utf8 -m pytest -n 2`。主回归 345 项通过，后续分别复验盘库及作品 75 项、几何及容量 53 项、最终提交的盘库、RWA 和引用 20 项，均通过。 [主回归](D:/dp-dev/tmp/libmanage/logs/pytest-related.log) · [最终复验](D:/dp-dev/tmp/libmanage/logs/pytest-commit.log)
- 全部 `tests/test_*.mjs` 用 `node --test --test-concurrency=1` 逐文件运行，60 个文件都通过。两项首轮失败均定向复验通过。随旧作品选批次时保留独立的局部几何。回连后，校准页负责自己的盘片检查，避免历史任务触发的后台读取抢占擦除预检。导航复验通过，重试页修复测试的切页等待后也通过。 [首轮](D:/dp-dev/tmp/libmanage/logs/js-browser-run.log) · [局部几何复验](D:/dp-dev/tmp/libmanage/logs/js-retest/test_disc_files_browser.log) · [可擦写盘复验](D:/dp-dev/tmp/libmanage/logs/js-final-target/test_rw_discs_browser.log) · [重试页复验](D:/dp-dev/tmp/libmanage/logs/js-retry-ready/test_web_retry_browser.log)
- 用 MERGE_REPORT 方法对照 `a7b5fbf`，固定时间、输入路径和虚拟盘写入参数。23 组里 18 组逐字节一致，覆盖双语正常 `burn`、`info`、`photo` 及 CD/DVD 默认 `image`、`disexport`。5 组符合原报告的预期差异，包括双语 `burn --help`、`photo --help` 和已知 MID 的 `image` 附档新增 `calibration_mid`。该镜像本身、命令输出和退出码一致。 [哈希和逐项对照](D:/dp-dev/tmp/libmanage/logs/parity/comparisons.jsonl)
- 开工与回归前 D 盘都超过 5 GiB。Python 用长 TEMP 路径。虚拟盘目录及整盘镜像按场景清理。

## 请 Claude 转达

- 请审查人确定 11-19 这批 RITEKF1 的容量口径。卡上给出 2,295,104，按镜像长度反推旧输入为 2,297,888，仓库另有基于预刻地址换算的 2,298,496 示例。本卡把卡上数值用于旧行的 MID 参考，保留明确容量记录优先的行为。实体盘、原始记录及正式数据迁移未测。
- 390 像素对照里，盘库文档宽 488，光驱和作品页文档宽 437，前后相同。编辑器文档宽 390。视觉取舍留给审查。旧的无关联转速记录只在能追溯到批次时纳入回收，共用预设文件会留在原处。
- 后续处理真实的 RITEKF1 记录由集成审查决定。当前提交只在本地工作分支。

STATUS: DONE
