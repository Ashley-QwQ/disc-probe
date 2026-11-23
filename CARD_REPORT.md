# RS 任务卡报告

工作树 `D:/dp-dev/reshoot`，分支 `dev/reshoot-burn-record`，基点 `95d3289`。

## 按提交交付

- `Report reshoot burn record blocker` 记录基点的取证结果和需要决定的兼容范围，见 [BLOCKED.md](BLOCKED.md)。本卡没有产品代码变更。

## 核验

测试前将 `TEMP`、`TMP` 和 `DISCPROBE_TEST_TMP` 指向 `D:/dp-dev/tmp/reshoot`。启动前 D 盘可用 49.09 GiB，F 盘可用 43.35 GiB。

| 命令 | 结果 |
| --- | --- |
| `git rev-parse --short HEAD` | 开工时为 `95d3289` |
| `python -m discprobe photo --help` | 现有手工输入参数包括 `--burner`、`--burn-path`、`--burn-mode`、`--disc-id` |
| `python -X utf8 -m pytest -n 2 -q --basetemp=D:/dp-dev/tmp/reshoot/pytest-log-proof tests/test_burner.py::BurnerTests::test_durable_speed_log_and_events` | 1 passed，1.20 秒 |
| `python -X utf8 D:/dp-dev/tmp/reshoot/burn_log_proof.py` | 使用同一测试夹具和 mock 刻录器，生成 3 行 JSONL。唯一的完成行有 `drive=H:`，缺 `burner`、`burn_path`、`burn_mode`、`disc_id`。证据在 `D:/dp-dev/tmp/reshoot/burn-log-proof.log` |

`drive` 能提供该次写入的光驱 ID。基点的 `burn_result` 省略了刻录程序和明确的模式记录。网页读取事件时追加这些字段，随后另存到 `.webui-jobs/<job>/burn.json`。旧 CLI 记录没有这份网页补充；网页上用于检查盘的自动盘号是在打开拍照页时生成的。现有门槛要求照片带有刻录器、程序、模式和盘号，因此单靠旧的 ISO 日志无法可靠恢复完整来源。

## 未测及待决定

- Disc Lab 两个端到端场景、立即拍照路径的逐位对比、网页截图、全量 `test_*.mjs`、其余相关 Python 测试和 `python -m discprobe selftest` 均未测。触发阻塞条件时停止功能实施。
- 需要决定旧版网页记录是否可以按 ISO 日志路径和事件时间关联同一次写入，以及如何处理只有 ISO 日志的旧盘。盘号历史缺失时需要人确认手上盘号。详见 [BLOCKED.md](BLOCKED.md)。

STATUS: BLOCKED
