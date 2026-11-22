# CN 彩色刻图新手走查

分支 `dev/colour-novice`，基点 `6dec7ab`。使用无头 Edge/CDP、独立回环服务和离线 RITEKF1 DVD-R 批次夹具。图片用仓库双语彩图指南里的 `example.png`，拍摄设置用 iPhone 17 Pro 和 22.3 cm。从大厅经新作品、批次选择和导入进入设计，检查 12 点箭头、灯下预测、左右对照，然后到生成 ISO 前的预览页。

## 改前走查

按对新手完成彩色图的影响排序。改前走查是按新用户路径操作和核对界面，未招募真人测试。

| 严重程度 | 改前卡点 | 改后 |
| --- | --- | --- |
| 高 | 桌面导入图片后自动显示「影调」，「颜色」和「彩色图」并列。选好机位后，第二排又出现「彩色图」，难以判断哪个入口负责整张图片。 | DVD 右栏默认打开「彩色图」。窄屏把「彩色图」放到面板按钮行的「影调」之前。单材质、图案填充、特效放在默认收起的「高级 · 手动配色」。 |
| 高 | 「填充」能改画布和添加箭头，但不会打开机位预测，要再找到「灯下」。右下角的「下一步：预览」同时可点，容易跳过彩图设置。 | 「生成颜色预览」用原有填充操作生成颜色，随即打开「灯下」，390 px 上同时收回侧栏。右下角仍可进入 ISO 预览。 |
| 高 | 初始示意和说明没有一次讲清为什么要固定机位、如何用闪光灯及对准纸。「怎么看、怎么拍」要等手机和高度都选好才出现。 | 首次打开彩图显示一张示意图、四段短说明和两个文档入口。「开始设置」收起说明并记住选择，标题可重新展开。 |
| 中 | 页面先问型号，把距离藏在「其他手机」里。高度说明混进焦距复测、色板逐块比对和旧尺信息。 | 先量 1× 镜头中心到闪光灯中心的直线距离。可直接输入，也可按型号查表。高度从桌面量到镜头，注明对准纸的 22.3 cm 参考高度。 |
| 中 | 「模型预测」和「混色还没实刻验证」没有交代实盘通常更暗、更淡，也没有在彩图面板显眼处说明已验证的盘和光驱。 | 「灯下」和 ISO 预览页说明这是选定机位下的模型预测，实盘会更暗、更淡。生成按钮旁注明实拍覆盖 RITEKF1 DVD-R 和 GH70N。 |
| 低 | 选机位前，禁用的「填充」改写成「先选手机和拍摄高度」，读不到将要做的动作。机位选齐后，编号和顺序仍需自己推断。 | 三步标题持续显示，禁用时保留操作名，并在按钮旁说明下一项要补什么。 |
| 低 | 390 px 英文示意图的两条机位标签被裁掉。 | 缩短为 Lower 和 Higher，沿用原示意图。 |

改前两组 390 px 英文走查均出现灯下长时间显示加载中，一次重试后还出现 `Failed to fetch`。两组都能进 ISO 预览页。加入较长的预测说明后，窄屏 CDP 记录到几十个成功的重复请求。底栏的状态文案改变行高后，适应画布的更新又使同一机位的预测过期。把持续显示的预测说明和短状态拆开，为加载、结果与对照保留同样的状态高度，并约束窄屏提示与按钮的宽度。

## 本地提交

- `9a6f138` 交付彩图三步、首次说明、手动配色折叠和预测提示。ISO 预览页借用同一句提示，位置在刻录清单上方。同步已有浏览器测试的操作入口和提示断言。
- 本报告提交记录截图、回归和交接事项。

## 验收记录

| 命令或场景 | 结果 |
| --- | --- |
| `node D:/dp-dev/tmp/colournovice/walk.mjs before` 与 `node D:/dp-dev/tmp/colournovice/walk.mjs after <宽度-语言-主题>` | 改前、改后各 8 组，覆盖中英文、纸色与夜色、1440 × 1000 和 390 × 844 交叉组合。改后 8/8 走到出图的 ISO 预览页，灯下和 ISO 预览各收到一次 HTTP 200，共 16 次。两次改前补拍用 `CN_BASELINE_REF=6dec7ab` 加载原始界面文件。 |
| `python -X utf8 D:/dp-dev/tmp/colournovice/verify_artifacts.py` | 改前 99 张、改后 130 张 PNG，尺寸和 PNG 校验全部通过。改后每组核对了带 12 点箭头的设计视图、灯下预测和左右对照。另验证手填 31.6 mm 后按原有 32 mm 档处理、查表显示 47.9 mm 后保留预置机位、关闭首次说明后在切页中保留、三种手动模式均可见。 |
| `python -X utf8 D:/dp-dev/tmp/colournovice/regress.py editor-mjs` | 9/9 文件通过。W245 的 18 项通过，纸色与夜色各在 20 µm 和 10 µm 的预览 RGBA SHA-256 共四个值均为 `f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36`，与冻结基线一致。 |
| `python -X utf8 D:/dp-dev/tmp/colournovice/regress.py all-mjs` | 逐文件顺序运行，60/60 通过，文件耗时合计 472.18 秒。W245 再次通过 18 项，四个预览哈希一致。 |
| `python -B -X utf8 -m pytest -n 2 --basetemp D:/dp-dev/tmp/colournovice/pytest-work -o cache_dir=D:/dp-dev/tmp/colournovice/pytest-cache tests/test_editor_ops.py tests/test_editor_preview.py tests/test_editor_texlib.py tests/test_editor_pose_swatches.py tests/test_editor_colour.py tests/test_design_compose_route.py tests/test_lamp_optics.py` | 首轮 149 通过，70.70 秒。全部 MJS 后复验 149 通过，58.78 秒，JUnit 结果见 `pytest-final.xml`。 |

截图在 `D:/dp-dev/tmp/colournovice/shots/before/` 和 `D:/dp-dev/tmp/colournovice/shots/after/`。每步可见文案及请求计数在同一临时根目录的 `before-evidence.json` 和 `after-evidence.json`。每个 MJS 文件的 `test.log` 及汇总 `results.json` 在 `editor-mjs/` 和 `all-mjs/`。开始走查和运行全部 MJS 前，D 盘分别剩余约 124.6 GB 和 123.0 GB。全量回归逐场景清理临时盘，任务临时目录中剩余的 ISO 和 IMG 数为 0。

## 未测及交接

- 走查止于 ISO 预览，整盘 ISO 生成、实盘刻录和实拍均未测。夹具用离线 DVD-R 和本地批次目录。用于报告的验证范围来自已有实拍记录。
- 外部文档链接的目标文件已在本地核对。发布域访问未测。
- 请 Claude 转达给 CD 和 ET 的文档维护会话。双语彩图指南目前写「颜色 → 彩色图」和「填充」，应更新成「彩色图 → 确认距离 → 拍摄高度 → 生成颜色预览」。手动配色现在从「高级」进入。「怎么看、怎么拍」仍可从机位步骤下方和 ISO 预览页打开。
- 请 Claude 转达给预览页维护会话。390 px 的 ISO 预览页在改前、改后均出现底部横向滚动和较长的下一步按钮文字换行。此处涉及预览页整体布局，留给那边决定。

STATUS: DONE
