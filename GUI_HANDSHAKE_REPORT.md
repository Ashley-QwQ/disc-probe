# GUI 与核心握手

本分支基于 `a08b1cf`，只处理核心与 GUI 的接口、GUI 加载和源码安装。核心版本仍为 `0.1.2.1`，没有提前升到 alpha；没有联网、访问光驱、修改 `discprobe/scsi.py` 或推送。

## 改了什么

- `discprobe/version.py` 保存核心版本；网页不再运行 Git 查版本。发布时只需在这里改为 `1.0.0-alpha.1`，pip 元数据会规范成 `1.0.0a1`。
- `discprobe/api.py` 保存 API `1.0`、能力名单、旧主版本支持名单。`GET /api/version` 与 `disc-probe version --json` 返回相同内容。API 1 没有更早的公开主版本，因此旧版本名单为 `[]`；没有虚报适配器。
- 内置 `discprobe/web/gui.json` 保存 GUI 名称、独立版本、API 范围 `>=1.0 <2`、必需和可选能力。GUI 版本不必跟核心版本同步。
- 首页在启动工作流前读取清单和核心版本。不兼容时只显示一张中英文提示纸：核心太旧或缺必需能力就更新核心，核心超出上界就更新 GUI。连接失败也只显示可操作的提示。握手通过才运行原有大厅和页面逻辑。
- `templates` 为默认 GUI 的可选能力。缺少它时，“下载模板”按钮隐藏；后续动态挂载的按钮也受相同规则限制。其他 14 项为必需能力。文件方式打开的开发预览不要求启动核心。
- `python -m discprobe webui --gui "GUI 文件夹"` 选择其他 GUI；不指定时使用内置包。核心在监听前检查清单、版本范围和必需能力，缺清单或不兼容时给出清楚的中英文错误。外部包入口约定为 `home/index.html`，资源相对包目录寻址。

## 能力名单

这些分组来自当前 HTTP 路由及首页各模块实际使用的操作，没有新增不存在的业务接口。

| 名称 | 当前涵盖的接口或操作 |
| --- | --- |
| `state` | `/api/state`，工作流、介质和平台状态 |
| `drives-info` | 光驱列表、`/api/disc`、`info`、`swap` |
| `jobs-events` | `/api/run`、任务快照、回答、取消、SSE 事件 |
| `timing` | `timing` 测量 |
| `geo` | `geo` 几何测量 |
| `image-design` | `random`、`image`、`/api/design`、ISO 信息 |
| `editor` | `/api/compose`、编辑预览、材质色样 |
| `burn` | 刻录、速度检查、写入口令、外部刻录命令 |
| `photo-calibration` | `calibrate`、`photo`、照片上传、列表和读取 |
| `phone-link` | 手机链接、二维码、设备列表、断开设备、手机上传页 |
| `presets` | `disexport`、`cdprobe` 及当前预设文件使用；没有把大厅尚未接线的导入导出按钮宣称为新接口 |
| `catalogue` | `/api/catalogue` 读取和保存 |
| `results-history` | 状态、目录和任务结果中的测量结果与批次历史 |
| `greetings` | `/api/greetings` |
| `templates` | `/api/template` 模板 ZIP，可选 |
| `presets-io` | `/api/presets` DIS 预设导入导出（合进 alpha 时由整合方补上），可选；缺少时大厅传真机和“预设导入导出”入口隐藏 |

## 版本规则

完整规则见 `docs/API_VERSIONING.md`。增加兼容功能升 MINOR，并用能力名声明；删除、重命名接口或字段，改变类型、单位、含义、必填条件、事件顺序保证或认证方式，升 MAJOR。旧 GUI 忽略不认识的能力；缺可选能力隐藏入口，缺必需能力停止启动。

建议从新主版本首次稳定发布起，至少保留前一主版本适配器六个月，并公布退役日期。只有实际可工作的适配器才能写入支持名单。测试矩阵为“当前核心 + 当前 GUI”和“当前核心 + 上一次已发布 GUI”。这是第一次引入清单，第二行目前不适用；下一次发布应保存本次 GUI 包作为固定测试输入。

## pip 离线证明

`pyproject.toml` 声明发行名 `disc-probe`、Python 模块 `discprobe`、命令 `disc-probe`，入口与 `python -m discprobe` 相同。NumPy、Pillow、SciPy、OpenCV 均为默认依赖；照片读取器 `pcal.py` 直接导入后两者，当前不适合把它们声明为不安装也可完整使用照片功能的可选项。

构建后端 `_build_backend.py` 只用标准库，实现 wheel、源码归档和包元数据，不需要 Git 或下载构建依赖。系统 Python 没有安装 setuptools；本次没有向系统 Python 安装任何包。wheel 包含全部 GUI、字体、LUT、色板、预设、社区数据和辅助脚本；安装后辅助脚本从包内定位。

验证环境为 `C:/disc-probe-scratch/gui-handshake/venv`，没有启用系统 site-packages。四个依赖 wheel 从本机已有 pip 缓存取出，没有网络下载；版本为 NumPy 2.5.1、Pillow 12.3.0、SciPy 1.18.1、OpenCV 5.0.0.93。

关键命令：

```powershell
python -B -m venv C:/disc-probe-scratch/gui-handshake/venv
C:/disc-probe-scratch/gui-handshake/venv/Scripts/python.exe -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir C:/disc-probe-scratch/gui-handshake/wheelhouse .
C:/disc-probe-scratch/gui-handshake/venv/Scripts/python.exe -m pip install --no-index --find-links C:/disc-probe-scratch/gui-handshake/wheelhouse disc-probe
C:/disc-probe-scratch/gui-handshake/venv/Scripts/disc-probe.exe --help
C:/disc-probe-scratch/gui-handshake/venv/Scripts/disc-probe.exe version --json
C:/disc-probe-scratch/gui-handshake/venv/Scripts/disc-probe.exe webui --port 0
```

运行目录为仓库外的 `installed-work`。`--help`、`version --json` 均退出 0；安装来源确认为该虚拟环境的 `site-packages`。临时服务的 `/api/version`、`/home/`、`/gui.json`、握手模块和字体均返回 200。CLI 和 HTTP 的版本 JSON 完全一致，随后已关闭服务。`pip check` 无依赖错误。

构建日志、安装日志和 `pip-proof.json` 保存在 `C:/disc-probe-scratch/gui-handshake/`。`offline_verify.py` 可重跑安装后检查。wheel 包含 271 个 GUI 文件，并逐文件比对了工作树与 wheel 中的字节。

最终 wheel 为 `disc_probe-0.1.2.1-py3-none-any.whl`，8,870,756 字节，SHA-256：

```text
b4f92340b4f50cd870b9a7e9909badc4c228a568f89e1999ee5f0c5630a6b0cd
```

还把源码归档 `source/disc_probe-0.1.2.1.tar.gz` 交给 pip 的隔离构建环境，使用 `--no-index --no-deps` 成功构建 wheel。447 个条目均与工作树构建的 wheel 字节相同；记录见 `sdist-build.txt`、`sdist-equivalence.txt`。alpha 版本写法的独立检查见 `alpha-version-normalization.txt`。

## 回归与 Windows 包

- 全量 pytest：440 passed、1 skipped、182 subtests passed，耗时 641.86 秒。随后为兼容旧的零参数 selftest 加载器补上 smoke 检查，并把旧的 Git 版本断言更新为“不运行 Git、使用包版本”；最终定向复测为 9 passed、8 subtests passed。未修改任何已知失败断言。
- Node：22/22 个 JS、MJS、CJS 入口退出 0，其中原有 20 个入口全部通过。新增浏览器检查使用本地合成响应，覆盖中英文、明暗主题、390/1440 宽度、不兼容时不启动工作流，以及动态生成的可选入口隐藏。
- selftest：退出 1，仍为原来的 14 项失败；与基线逐条文本完全一致，新增和消失的失败均为 0。新握手 smoke 检查通过。记录见 `selftest-final.txt`、`selftest-comparison.json`；首次发现的测试加载器接入问题也保留在原始 `selftest.txt`，没有改写旧日志。

Windows 构建器仍通过原有复制流程收入 GUI、清单和握手脚本，并增加源码包元数据、版本规则和社区数据。第一次检查用的旧缓存缺 OpenCV；没有下载补齐，而是从刚验证过的虚拟环境复制四个依赖到独立 `winpack-cache`，并复用本机已有的 Python 3.13.14 嵌入包。

实际检查命令：

```powershell
python -B tools/build_winpack.py --ref a08b1cf --label gui-handshake-check --worktree --cache C:/disc-probe-scratch/gui-handshake/winpack-cache --out C:/disc-probe-scratch/gui-handshake/winpack --no-trim
```

装配后的完整目录中，271 个 GUI 文件与工作树逐字节相同；用包内 Python 启动服务，`/api/version`、`/home/`、`/gui.json` 均返回 200，随后关闭。证据为 `winpack-proof.json` 与可重跑的 `winpack_verify.py`。

完整构建在原有 selftest 门槛处退出 1，未生成正式 ZIP，也没有完成裁剪验证。包内没有仓库的 pytest 测试文件，因此出现的是已知 14 项中的 5 项：两项旧 CD 音轨导出断言，以及三项中文帮助检查。逐项与 `C:/disc-probe-scratch/release-alpha/docs-selftest.txt` 对照，没有新增失败。没有跳过门槛或把失败改成通过。原始记录为 `winpack-build-complete-cache.txt`、`winpack/audit/*/untrimmed/selftest.log`；这里证明了 GUI 装配和包内服务能运行，不宣称完整 ZIP 构建通过。

## 需要本人决定

- 是否正式使用 PyPI 发行名 `disc-probe`、命令 `disc-probe`、模块名 `discprobe`；本次未联网核对名称是否可用，也未发布。以后 `pipx install disc-probe` 需要先发布该名称。GUI 包名称目前为 `disc-probe default`，其他皮肤可独立命名和发布。
- 是否采纳“稳定版发布后至少六个月”的前一主版本支持窗口，以及到期后的延长规则。
