# 卡 R：夜色光池中性化、收窄

状态：**阻塞，未完成实现或烤图**。2026-11-16 按任务卡“找不到就停下写进报告，不要自己重建场景”的要求，在源文件检查阶段停止。

## 提交

本提交 `docs: record night-pool missing source blockers` 只增加本报告，记录预检结果与恢复条件。没有修改渲染脚本、网页图片、位置 JSON、manifest 或导出报告。

工作分支：`web/night-pool-20261116`。开始时 HEAD：`3c3f66aa25111287fbec9293f155a1db60594428`。没有切换分支、推送、合并或修改其他 worktree。

## 预检与证据

已先读取 `D:/dp-dev/cards/COMMON.md`，再读取 `D:/dp-dev/cards/night-pool.md`，并检查 manifest、两个渲染脚本和标定页实现。标定页仅作为只读参考。

开跑前磁盘剩余空间：D 盘 42,916,589,568 字节，F 盘 34,245,582,848 字节，均高于 5 GB。停止时再次检查：D 盘 42,841,161,728 字节，F 盘 33,387,642,880 字节。本任务未创建渲染或大型测试夹具。

`F:/dp-archive/tools/blender-5.2.2-windows-x64/blender.exe --version` 成功，报告 `Blender 5.2.2 LTS`，构建哈希 `d13f752e3b9c`。未启动渲染，未验证 GPU / OptiX 设备。

场景检查：

| 输入 | 结果 |
| --- | --- |
| `F:/dp-archive/tmp/webpolish/night/disc_explode_render.blend` | `Test-Path` 为 True；未打开场景 |
| `D:/disc-probe/art/desk/**/fax_news.blend` | 找到 1 个：`fax-news/fax_news.blend`；未打开场景 |
| `D:/disc-probe/art/desk/**/lobby_tray.blend` | 找到 0 个 |
| `D:/disc-probe/art/desk/**/penrose.json` | 找到 0 个 |
| `D:/disc-probe/art/desk/**/tray.blend` | 找到 9 个，包括脚本注释所指的 `skills/desk-prop-tray/final_bundle/tray.blend`；未将其认定为 manifest 中 `lobby_tray.blend` 的等价输入 |

源文件搜索命令如下，包含隐藏文件和被忽略文件；遍历排除了用户指定的禁用名称及其子树。没有搜索其他工作树或禁用路径。

```powershell
rg --files --hidden --no-ignore `
  -g '!**/*[bB][lL][iI][nN][dD]*' `
  -g '!**/*[bB][lL][iI][nN][dD]*/**' `
  -g '!**/.git/**' `
  -g 'lobby_tray.blend' -g 'tray.blend' `
  -g 'fax_news.blend' -g 'penrose.json' `
  'D:\disc-probe\art\desk'
```

共返回 10 条安全路径。实际搜索输出保存在 `F:/dp-archive/tmp/nightpool/source-search.log`。

## 未完成与未测

- 未修改 `STYLE["dark"]`、按物体分组的光照、夜色 sigma 或线条透明度；未修改 `sheet_light` 和纸色参数。
- 16 个目标 job 均未渲染；纸色重新渲染核对未测，不能声明 `unchanged`。
- 未运行 `night_b_export.py` 的核对或 `--write`；未更新 manifest 和导出报告中的机器、设备、光池数据。
- 夜色图的 L*、OKLCH 暖色比例未测；没有产出新的网页验收截图或平移过程截图。
- Node 测试（包括全部 `tests/test_*.mjs`）和相关 `pytest -n 2` 未测：在源文件缺失的停工条件触发后没有启动测试。
- 未修改任何既有纸色图片、`caltop/`、`index.html`、CSS 或 `evidence/atlas/*.py`。没有接光驱、刻盘、下载或上传。

## 恢复工作需要的输入

需要提供原始 `lobby_tray.blend` 与 `props/penrose.json` 的可读、安全路径；如拟采用 `final_bundle/tray.blend`，需要确认它就是原先烤图所用的托盘来源，并仍须补齐原始 Penrose 数据。源文件齐全后，应从修改脚本、首个 job 双主题烤图和纸色核对开始；本报告不代表视觉验收通过。
