# DVD 起步预设

放入新批次的空白 DVD，运行 `python -m discprobe starter --drive H:`，再用 `--source ID` 显式选择一个来源。本机同一台光驱、同 MID 的标定排在前面。其他机器同型号的记录和社区记录标为未验证。网页默认走测量盘流程。

1. 用 `checkdisc --geo <starter.json> --output iso/check.iso` 生成检查盘镜像。
2. 用 `burn --drive H: --media dvd --iso iso/check.iso --yes-write` 刻录。抽样回读通过后，把输出的检查盘编号写在盘上。
3. 转动同一张盘，从不同角度拍照。用 `photo --media dvd --run <起步记录目录> --disc-id <盘号> --photos one.jpg two.jpg three.jpg` 读取。
4. 照片通过后用 `image --geo <starter.json>` 出图，作品放在 26.2–57.0 mm 内。照片不过时，换同批空白盘走原来的测量盘流程。
