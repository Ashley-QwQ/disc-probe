# Issue #49｜`info` 显示 DVD+R DL 的 MID 和 L0

工作树 `D:/dp-dev/issue49`，分支 `dev/info-dl-issue49`，基点 `c4c7ebe`。实现及夹具提交 `e6fd786`。现场来源为 GH40N / NX05 用户报告及其终端输出。 [Issue #49](https://github.com/Ashley-QwQ/disc-probe/issues/49)

实现与相关验收已完成。卡片的完整 `selftest` 条件仍受 `COMMON.md` 文件路径限制阻塞。

## 改动位置与标准依据

- `discprobe/info.py` 的 `collect` 和 `summarize`。当前 profile 为 `0x002B` 时，优先用校验通过的 `0x11`，再从已读的 `0x00` 取 MID。`info.json` 的 `dvd_plus_mid.source` 标明所用格式，终端在回退时说明 `0x11` 是拒读还是未能解析。此回退限于 DVD+R DL，以满足单层输出兼容要求。保留原始结构响应及其诊断字段。
- `discprobe/mmc.py` 的 `parse_dvd_plus_r_dl_mid`。MMC-6 §6.22.3.2.1 表 398 与 §6.22.3.2.18 表 424 定义四字节响应头。ECMA-364 §14.4.2.1 及 §18.8.1 表 13 定义 DVD+R DL 载荷类别和层结构，以及字节 19–26（厂商）、27–29（介质类型）、30（产品修订与叠层类型）。文本字段要求非空且可打印，只允许尾随 NUL 填充。终端按光盘 ID 的习惯以两位十六进制显示完整字节，例如 `66`。JSON 分别保留低六位修订号 `product_revision` 和完整的 `product_revision_byte`。单层 +R 的 ECMA-349 §14.4.2.1 和控制数据区表格也列出对应位置，单层继续沿用原读法。 [ECMA-364](https://ecma-international.org/wp-content/uploads/ECMA-364_3rd_edition_december_2007.pdf) · [ECMA-349](https://ecma-international.org/wp-content/uploads/ECMA-349_4th_edition_june_2008.pdf) · [MMC-6（T10/1836-D Revision 2g）](https://www.t10.org/drafts.htm)
- `discprobe/mmc.py` 的 `parse_dvd_layer0_end` 和 `parse_dvd_layer_capacity`。先按 MMC-6 表 398 从 `0x00` 的载荷字节 5–7 和 13–15 取起始 PSN、含末端的 L0 PSN。对缺少有效末端的 DVD±R DL，才查询 `0x20`。按 §6.22.3.2.20 表 426，`0x20` 载荷字节 4–7 是以扇区为单位的容量，字节 0 的最高位是 Init Status。表 404 给出起始 PSN `0x030000`。`dvd_layer0` 保存整数起止 PSN、扇区数和来源。`0x20` 的初始状态另留在命令记录中。 [MMC-6（T10/1836-D Revision 2g）](https://www.t10.org/drafts.htm)
- `discprobe/zh.py` 增加 MID 回退和 L0 的中文。帮助索引没有关于 MID 缺失、双层边界或 L0 的条目。`python tools/refresh_troubleshoot_citations.py` 移动了两处因词条插入而偏移的引用。`--check` 通过。

## 验收

- `tests/test_info_dl.py` 以 MMC 响应字节驱动 `info`，覆盖 CLI 与写出的 JSON、`0x11` 优先、`0x11` 拒读或字段不全时回退、截断/非 ASCII/类别不符时隐藏 MID、`0x00` 和 `0x20` 分别得到 2,086,912 扇区、两条路径均无有效边界时隐藏 L0，以及中文输出。
- 基点与改后使用同一套输出采集。既有 `info` 相关夹具的输出对 **35/35** 一致，额外单层覆盖 **15/15** 一致，合计 **50/50**。比较 JSON 及终端 UTF-8 字节，四次 CLI 测量比较实际写出的 `info.json`，其余经生产 JSON 写入函数序列化。测试固定输出目录时间戳，采集后按原字节比较。覆盖 CD、DVD±R、DVD±RW、DVD-ROM、BD，以及单层 DVD+R/+RW 的 `0x11` 成功与拒绝。逐对哈希见 `F:/dp-dev-tmp/issue49/byte-parity.tsv`。
- GH40N 字节夹具复现 issue 终端输出的 **17/17** 行，内容与顺序均一致。与同一夹具下的 `c4c7ebe` 比较，只增加下面两行，原版已有的容量提示仍在。两个输出见 `F:/dp-dev-tmp/issue49/gh40n-base.stdout` 和 `gh40n-updated.stdout`。

```text
DVD+R MID: RITEK/S04/66 (from physical format info 0x00; ADIP 0x11 refused)
L0: 2086912 sectors (PSN 0x030000..0x22D7FF)
```

- 相关 Python 测试使用 `python -m pytest -n 2 --dist loadfile`，**64 通过**。前后输出采集的 pytest 各通过 **46 项**，另有 **1 项**既有测试回放，其两条输出来自快读和全读。首次基点采集有两个 worker 争用同一虚拟 `X:`，按测试文件分配后通过。日志见 `F:/dp-dev-tmp/issue49/pytest-final.log`、`baseline-pytest.log`、`after-pytest.log` 及 `*-pytest-extra.log`。
- `tests/` 下的 **55 个 `test_*.mjs`** 均运行。首次 **54/55**，`test_flow_navigation_browser.mjs` 等待盘库导航超时。用 `c4c7ebe` 的对应模块和索引单独复跑通过，使用当前分支单独复跑也通过。合计 **55/55** 文件至少通过一次。三次结果分别保存在 `F:/dp-dev-tmp/issue49/js/summary.log`、`js-base-retest/summary.log`、`js-worktree-retest/summary.log`。
- 带路径防护运行 `python -m discprobe selftest`，退出码 **1**，汇总 **2 项失败**。防护在内存中提供两条内置的临时文件名夹具，并阻止真实受限路径的打开。`test_frozen_photo_and_video_placement_geometry` 还需要读取一份现有受限证据，访问已拦截。另一项 `test_identity_sessions` 在隔离目录下找不到按工作树相对路径加载的样本，从工作树复跑 `tests/test_identity_sessions.py` 后 **6/6** 通过。单独运行解析器、无盘 `info` 与中文自检，**76/76** 通过。日志见 `F:/dp-dev-tmp/issue49/selftest.log`、`pytest-identity-followup.log` 和 `selftest-info-only.log`。

## 待核对

- GH40N 夹具按标准和 issue 终端输出构造。未测真实光驱或盘片，未取得报告者的 `info.json`，所以实际由哪条结构携带 MID 和 L0 仍待原始响应核对。
- `0x00` 若因 book type bitsetting 显示为 DVD-ROM，MID 回退仍要求该响应自身明确采用 DVD+R DL 布局。对 `0x20`，空白 DVD+R DL 可返回默认容量，DVD-R DL 返回固定中间区的边界。记录来源便于区分这些情况。

## 请维护者转发的建议文字

**中文**　谢谢你贴出 GH40N 的终端输出。方便的话，能否再附上同一台光驱读取这张 RITEK-S04-66 DVD+R DL 时保存的 `info.json`？请保留 `dvd_physical` 和 `dvd_plus_adip_11` 的原始十六进制数据、状态和 sense。如果文件中还有层容量响应，也请一并保留。我们想对照光驱实际返回的字节，确认 MID 和 ImgBurn 报告的 2,086,912 扇区 L0 边界。

**English**　Thanks for posting the GH40N terminal output. Could you also attach the `info.json` saved by `discprobe info` for the same RITEK-S04-66 DVD+R DL disc in that drive? Please keep the raw hex, status, and sense for `dvd_physical` and `dvd_plus_adip_11`, plus any layer-capacity response present in the dump. We'd like to check the MID and the 2,086,912-sector L0 boundary from ImgBurn against the bytes the drive actually returned.
