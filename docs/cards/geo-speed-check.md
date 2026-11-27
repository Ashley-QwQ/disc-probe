# geo 读速检查交付报告

工作树 `D:/dp-dev/geospeed`，分支 `dev/geo-speed-check`，基点 `e0ddb3c`。

## 提交

- `89916ca` 为 DVD、CD 和 BD 的 geo 结果增加 `read_speed` 和 `speed_check`。角度阶梯记录参考周期，CLV 记录各测区的周期和 LBA。按驱动器、固件、介质和请求速度查询登记表，在测量开始和结束时提示，并在 `guide` 的 geo 结果下显示同一条提示。补充中文提示、中英文 README、登记格式和回归测试。
- 本报告另行提交。所有提交只在本分支。

## 验收

- 运行前 D 盘余 219,403,960,320 字节，最终验收前余 219,401,265,152 字节。`TEMP`、`TMP` 均指向 `F:/dp-dev-tmp/geospeed`，测试的 HTTP 服务只走本机回环。
- 相关 Python 测试共 174 项通过，用时 92.77 秒。覆盖包内登记表、工作区覆盖及回退、缺失和损坏的新段、三个状态的终端与 guide 提示，以及 DVD、CD、BD 模拟路径和 BD 的 CLV 至角度阶梯切换。

```powershell
python -m pytest -n 2 -p no:cacheprovider --basetemp "$env:TEMP/pytest-accepted" tests/test_geo_speed.py tests/test_geo_integration.py tests/test_geo_progress.py tests/test_geo_unsteady.py tests/test_geo_varpitch.py tests/test_read_completion.py tests/test_cd_clv.py tests/test_bd_clv_solver.py tests/test_fail_exits.py tests/test_web_guidance.py
```

- `python -X utf8 -B "$env:TEMP/check-wheel.py"` 离线构建 wheel，并在源树外读取 `discprobe/_presets/drives.json`。针对 GH70N（NYA2）DVD，5540、11080、3324 kB/s 分别得到 `validated`、`known_bias`、`unvalidated`。
- 登记证据为 4x 的 grid3 径向峰峰值 0.106°，以及 8x 相比 4x 在 54 mm 处增加约 0.3° 的相位滞后。8x 提示建议回到 `--speed 5540`。
- `python -X utf8 -B "$env:TEMP/run-node-offline.py"` 调用仓库的 `tests/run_webguide_checks.py`，覆盖全部 55 个 `test_*.mjs`。首轮 52 个通过，3 个浏览器测试因离线配置误阻断回环而失败。修正回环规则后，用同一命令附加 `test_afterburn_browser.mjs test_brand_browser.mjs test_burn_cancel_browser.mjs`，复测 3 个全部通过。两轮结果合计 55 个文件通过，日志在临时目录的 `node` 和 `node-recheck` 下。

## 模拟输出

`python -m discprobe geo --sim cav --seed 7 --out "$env:TEMP/sim-final" --lang en` 完成 22 级，状态 `target_reached`。新增字段实录如下。模拟器未发出速度设置命令，`set_cd_speed` 的原值为 `null`。

```json
{
  "read_speed": {
    "media": "dvd",
    "requested_kBps": 5540,
    "requested_multiple": 4.0,
    "period_ms": 6.598510337558251,
    "drive": "SIM-cav",
    "firmware": null
  },
  "speed_check": {
    "status": "unvalidated",
    "note": "This read speed has not been grid-validated. At a single read speed, the fit can absorb read delays that vary with radius, leaving no trace in the residuals. Before using this geometry to burn a picture, burn and check a grid disc."
  }
}
```

## 改前改后逐字节比较

改前和改后在同一工作树用同一条命令运行；只在验收进程内将 `geo` 的耗时计时器换成固定步长时钟，避免 `elapsed_s` 随机器负载变化。模拟光驱照常使用自己的时钟。比较脚本为 `F:/dp-dev-tmp/geospeed/check-parity.py`，两次原始结果在同目录下的 `baseline-fixed` 和 `after-fixed`。

```powershell
python -c 'import sys; from itertools import count; from types import SimpleNamespace; from discprobe import geo; from discprobe.__main__ import main; ticks=count(); geo.time=SimpleNamespace(monotonic=lambda: next(ticks)/1000); main(sys.argv[1:])' geo --sim cav --seed 7 --out "$env:TEMP/parity-run" --lang en
```

| 比较项 | 字节数 | 两次相同的 SHA-256 |
| --- | ---: | --- |
| `targets.csv`（22 个目标） | 2151 | `ed0ae8cf13ec32773a24a2becec784d197c409e0edea5126e292215cb40fea71` |
| `fit`（JSON，2 空格缩进） | 5051 | `08f8bf443057f49413b4d6883298d604f6dd57c500e39e3d4e10c1e815081cfa` |
| `summary.json`（去掉两项新增字段，以同样格式重新序列化） | 7416 | `b12d7730615e13b7ac6a57c6b7e637bfc0e7ca6a9b6400998f10eda10905bb10` |

## 未测及审阅事项

- 本轮未接光驱、未刻盘、未访问外网。实盘证据来自已有 grid3 扫描和 11 月 18 日双速复测。CD、BD 和其他光驱的提示已测数据路径，未测其网格验证结果。
- `guide` 对已有提示字段采用运行时语言，对旧结果继续显示原有几何信息。已知偏差的来源是卡片指定的 `D:/dp-dev/t1joint/evidence/t1-joint/level4/RESULT.md`，安装包携带证据文字和路径。
- 新段损坏时查询下一个登记表，找不到匹配则提示未经验证。旧 DVD 完成偏移段仍按原规则解析，整份登记表 JSON 损坏时沿用原有完成偏移读取错误。
- `python -m discprobe selftest` 的失败项为全局中文帮助的 3 项检查。`python -X utf8 -B "$env:TEMP/check-baseline-help.py"` 对比基点与本分支，两者均有 19 个选项帮助条目及 `colour-design`、`textures` 两个命令描述缺少中文。`geo` 新提示的中英文输出通过专门的测试。完整日志为临时目录下的 `selftest-final.log`。
- 没有待决定的发布或界面取舍。
