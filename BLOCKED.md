# RS 阻塞说明

任务卡要求从检查盘 ISO 的 `.burn.jsonl` 恢复同一次已完成刻录的 `burner`、`path`、`mode` 和盘号。基点 `95d3289` 已触发卡中关于旧日志字段缺失、无法从同一行可靠推导的阻塞条件。

## 卡在哪里

- [`discprobe/burner.py` 的日志写入](discprobe/burner.py#L550)记录 `drive`、`media`、`image` 和时间。[完成记录](discprobe/burner.py#L682)记录写入结果、速度、会话和读回状态。结合这两处可以拿到同次写入的光驱 ID。该行缺刻录程序和明确的模式字段，也没有可以区分写入程序的标记。刻录函数允许注入 recorder，默认平台适配器只是其中一条路径。
- [`discprobe/webui.py` 的事件读取](discprobe/webui.py#L502)才追加 `burner`、`burn_path` 和 `burn_mode`，然后[另存网页作业记录](discprobe/webui.py#L1316)。基点的 [`saved_burns`](discprobe/webui_catalog.py#L28) 分别读取两个来源。独立运行 CLI 的刻录没有网页作业记录。读取旧 JSONL 时按当前系统补写 `IMAPI` 或 `growisofs` 无法证明当时用的程序。
- [`discprobe/photo.py` 的应用门槛](discprobe/photo.py#L178)会拒绝缺记录的照片。[网页的自动盘号](discprobe/web/home/calibrate.js#L285)到进入立即拍照时才生成，旧完成行无法提供当时看见的号码。

## 做完了什么

核对日志的写入、网页的补充和照片的采用门槛。跑了 1 项基点测试并读取 mock 刻录器生成的完成行，复现缺字段。证据、命令和未测项目见 [CARD_REPORT.md](CARD_REPORT.md)。没有访问真实光驱。

## 需要人决定什么

1. 是否允许读取旧网页作业的 `burn.json`，只在 ISO 日志路径和刻录事件时间都吻合时补上该次写入的内容。
2. 只有旧 JSONL 的盘如何处理。可把补拍功能限定在将来明确记录了刻录程序、模式和盘号的写入。基点的旧盘号未保存，若支持旧盘补拍，需要用户核对并填写。
