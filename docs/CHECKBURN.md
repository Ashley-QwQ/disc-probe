# 刻完看不到图

把刻好的盘放进光驱。刻完页打开「看不到图？」会显示这次刻录保存的抽样回读。选「读取光驱里的盘」可再查当前盘的状态和内容。用 DIS 或其他软件刻的盘也能从命令行检查。

```powershell
python -m discprobe --lang zh checkburn --drive E:
python -m discprobe --lang zh checkburn --drive E: --iso iso/picture.iso
python -m discprobe checkburn --drive E: --json
```

- `--iso` 用刻录时相同的抽样方法核对原镜像。程序认出盘上的专属编号且找到对应的 `.burn.jsonl` 时，会复用当时的回读。没有编号的盘可以用 `--burn-log` 指定日志。指定前请确认日志是这张盘的，且最新一条结果就是这次刻录。把追加镜像交给 `--iso` 时，用 `--start-lba` 指定它的起始扇区。
- 只刻了部分容量也可以是正常的短镜像。检查单会结合封盘状态、预计长度和抽样回读来判断。ISO 9660 和 Joliet 根目录可自动检查。UDF 和其他文件系统可在系统里打开盘根目录检查。
- 有些盘用相似的标识，找到同标识的测量后还要核对是不是同一批。盘上身份记录里的 DIS 名义预设可自动识别。知道用了名义预设而盘上没有这项记录时，可以加 `--dis-nominal`。回读正常、盘上也有图案数据时，再看光照和标定。

在网页的「新手引导」里看「光怎么变成图」的示意动画。也可以看[看盘和拍照](../README.md#第-6-步看盘和拍照)的示意图。

# No picture after burning

Insert the recorded disc. On the post-burn page, open “Can’t see the picture?” to review the saved read-back sample. Choose “Check the disc in the drive” to check the state and content of the disc currently inserted. The command line also checks discs made with DIS or other software.

```powershell
python -m discprobe checkburn --drive E:
python -m discprobe checkburn --drive E: --iso iso/picture.iso
python -m discprobe checkburn --drive E: --json
```

- `--iso` uses the same sampled comparison as `burn`. When the disc carries a unique burn ID and the corresponding `.burn.jsonl` entry is available, the check reuses that read-back. For an unmarked disc, pass `--burn-log` after confirming its latest result describes this disc and burn. With an appended image, use `--start-lba` for the session's starting sector.
- A short image can legitimately use a small part of a disc. The checklist looks at closure, expected length and sampled reads together. It reads ISO 9660 and Joliet roots. Check UDF and other filesystem roots in your operating system.
- A media code can be shared by different batches. If a matching calibration record exists, check the batch and the preset used to make the image. The tool recognizes nominal DIS presets named in a disc identity record. Pass `--dis-nominal` if you used one and the disc does not carry that information. If the read-back matches and pattern data is present, check the light and calibration.

See “How light becomes a picture” in the web Start guide or the diagram in [Look at the disc and photograph it](../README.en.md#step-6-look-at-the-disc-and-photograph-it).
