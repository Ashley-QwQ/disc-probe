# 卡 E 完成报告

分支：`dev/web-guidance`；worktree：`D:/dp-dev/webguide`。只在本分支提交，未推送、未合并、未切换分支。未接触实体光驱、未刻盘、未上传。未修改 `evidence/atlas/*.py`；所有递归遍历均在进入子目录前排除 COMMON.md 禁止的名称。

## 按提交列出的工作

1. `05256497700c` — `fix(web): guard IME Enter, enforce CSP and suspend hidden work`
   - 共享 `kit/shared.js:isActionEnter()` 同时检查 `isComposing` 与 `keyCode === 229`。14 个入口接入：标定名称、设计图层改名、选区改名、传真来源、新作品名、批次候选、终端命令、作品库改名、选区列表、图层列表、画布绘制、新作品返回动画、新作品归档动画、作品库进入动画。
   - 保留原有 keys.js、design.js 工具快捷键和 faxnews.js 全局组成态判断。按钮长按、keyup 释放、合成按钮事件、Ctrl/Cmd+Enter、滑块按键抑制和帮助文字都有局部 `ime-enter-exempt` 注释。静态检查覆盖两棵前端树的 Enter/NumpadEnter 字面量、switch/别名/数组入口及 keyCode 13，不能无说明增加裸入口。
   - 两个 HTTP 服务器为 HTML 实际响应计算脚本 SHA-256 CSP；手机配置替换后再计算。无脚本 `unsafe-inline`、无 `unsafe-eval`。嵌入项目图片、缩略图及模拟库中的 `fetch(data:)` 改成本地 Blob 解码，不放宽连接策略。
   - 暂停/恢复明细见下表。冲突对话框使用 `closedby="any"`，特性不支持时保留旧点背景关闭逻辑。DP 首页和 Disc Lab 的主题切换同步 color-scheme meta；现有 CSS 的 color-scheme 声明不动。
   - 增加真实 KeyboardEvent、活动状态/并发轮询、worker 停止及异步解码竞态、HTTP 策略和 Edge 页面测试；给原有文件页面测试提供可选 CSP 夹具。原预设下载测试直接检查捕获的 Blob，避免测试自身额外要求 `connect-src blob:`。
2. 本报告提交 — `docs: record web guidance card verification`：保存实现、验收、策略原文及边界。

## 来源和 CSP 取舍

已从安装在 `D:/dp-dev/tmp/mwg` 的 modern-web-guidance 1.0.0 读取 `ime-safe-enter-submit`、`efficient-background-processing`、`dialog`、`dark-mode-toggle`。`restrict-outbound-connections` 的 retrieve 被实验功能开关拦截，未读取其原始文件、未更改开关、未采用 connection-allowlists API。本卡明确要求的标准 CSP 已独立完成。

资源盘点：页面有头部主题脚本及内联模块；样式包含内联 style、JS 动态样式表、style 属性和运行时 CSS 变量。字体是同源 Archivo/Mona Sans/Smiley Sans 等本地文件；图片为同源 WebP/PNG/SVG、项目 data 图片与 Blob 预览。渲染、处理 worker 及其 JSON/bin 数据均为同源模块。仅 `dev-photo.html` 把安装的标定代码拼成 Blob 模块，故该开发预览单独允许脚本 `blob:`。

传真盘点：`faxnews-data.mjs:DEFAULT_SOURCE` 为 `./faxnews/news.json`；默认皮肤、作品图片都是包内相对路径。`faxnews.js` 下载用户指定的报纸及其引用的皮肤；webui 后端没有固定外部新闻代理。报纸里的 GitHub releases 链接是导航，不是 fetch 来源。

默认 `connect-src 'self'`。需要远程传真时，启动进程前用 `DISCPROBE_FAX_ORIGINS` 明确列出以空格分隔的 http(s) origin；不接受路径、凭据、通配符、查询或片段。这些 origin 仅加入 DP 的 connect-src/img-src；Disc Lab 保持 self。例：`https://news.example https://skins.example:8443`，此处只是配置示例，测试没有请求这些地址。远程报纸自身还须满足 CORS。界面仍可填地址；未列入白名单的远程地址会被 CSP 拒绝。

必须放宽的项目：

- `style-src 'self' 'unsafe-inline'`：两套界面依赖动态 style 和大量属性样式。以后可先集中样式创建与 nonce 传播，收紧 style-src-elem，再逐步把属性样式迁成类；本卡不改视觉结构。
- `img-src ... data: blob:`：保存项目、图片选择及缩略图预览需要。
- 开发页 `dev-photo.html` 的 `script-src blob:`：现有隔离预览模块需要；生产首页、手机页和 Disc Lab 不允许该来源。
- 外部传真 origin 必须显式配置；仓库没有可据以默认授权的固定外部源。

未发现生产页面被嵌入的需要，采用 `frame-ancestors 'none'`。测试用 iframe 夹具只加同等资源策略的 meta CSP；meta 无法实施 frame-ancestors，完整响应头另由真实 HTTP 页面测试验证，不能把夹具当成该指令的运行证明。

## 看不见时的处理

| 位置 | 本轮处理 |
| --- | --- |
| 设计画布 / 灯下视图 | visibilitychange 与 IntersectionObserver 共同门控绘制；隐藏或出视口即 terminate lamp worker，丢弃排队任务和跨暂停的旧解码结果；回来按当前设计和机位重建。保留最后画面。 |
| 设计“往返播放” | 清除定时器，保留方向及往返次数，回来继续；离开设计页正常结束播放。 |
| 预览画布 | 同样观察可见性；灯下 worker 暂停，旧 SimView 引擎 stop，回来按现有参数创建。 |
| 大厅 | 视差 rAF 停止/恢复；离屏时暂停大厅运行中的动画；原有页隐藏/闲置暂停机制保留，补上清理正在运行的 ramp 定时器。 |
| 大厅地毯问候 | 原有回来刷新保留；日界线是一次低频更新，不是持续轮询，保留。 |
| Disc Lab | 实际没有持续 canvas 绘制；大厅和工作进度动画按可见性暂停。状态与 job 轮询清除定时器，回来继续，阻止慢请求因反复切换可见性而重叠。隐藏取消尚未完成的长按确认，回来不会无人值守地确认。 |
| 手机页 | 修复隐藏分支最终仍 poll 的路径；隐藏清除照片轮询和上传进度显示定时器，回来恢复。正在上传的请求不由显示定时器中断。 |
| 传真、引导、刻录滑块 | 传真已有 visibilitychange 跳过动画并静音、引导已有隐藏停止/回来 tick、滑块已有隐藏取消；保留。 |

没有改 CSS 颜色、布局、文字或动画参数；没有因指南建议而新增 content-visibility 布局隔离。

## 验收命令和结果

- `python -X utf8 tests/run_webguide_checks.py`：最终整轮 **37/37 文件通过**，涵盖全部 `tests/test_*.mjs`；文件夹具启用 `tests/csp-fixtures.cjs`。每项日志和 `node-results.json` 在 `D:/dp-dev/tmp/webguide/`。
- `python -m pytest -n 2 tests/test_web_security.py tests/test_webui.py tests/test_webui_recovery.py tests/test_webui_catalog.py tests/test_web_guidance.py disclab/tests/test_desk.py --basetemp D:/dp-dev/tmp/webguide/pytest-verified -q`：**73 passed，42 subtests passed**。最后调整 Lab meta 后单独再跑 `tests/test_web_security.py`：**10 passed**。
- `python -m pytest -n 2 tests/test_gui_handshake.py --basetemp D:/dp-dev/tmp/webguide/pytest-handshake -q`：**8 passed，8 subtests passed**。上述两个不同的相关 Python 测试集合合计 **81 passed，50 subtests passed**；10 项头部复验不重复计数。
- 新 IME 测试：**14 个实际处理函数 × 3 类合成 KeyboardEvent = 42 组**；第二类先派发 compositionend，再派发 `isComposing=false,keyCode=229` 的 Safari 顺序事件。额外静态检查覆盖 **14 处**保留的 Enter 字面量（含 helper、例外和帮助/事件生成）。
- 活动状态测试：前台/视口条件合取、不支持 IntersectionObserver 的回退、监听器释放、Lab job/status 慢请求不重叠、worker terminate/重启与跨暂停的异步解码丢弃。手机 VM 测试验证隐藏后两个时钟都为 0、回来仅恢复一个 poll。
- Edge **157.0.4341.60**：真实 HTTP 下 8 个静态 HTML 页面、带真实临时令牌的手机页面、Disc Lab 均无非预期 CSP 违规；验证桌面主题/设计/真实灯下 worker 出帧、滚出视口停止/恢复、390×844 手机视口，以及原生/强制回退的对话框取消。另注入未授权内联脚本，确认其被阻止；该预期违规单独断言后清空，不计入“无非预期违规”。Python 响应测试还覆盖 Lab `/index.html` 别名，原始 `/phone/index.html` 模板维持 403。
- `python -X utf8 D:/dp-dev/tmp/webguide/scan_after.py`：为遵守禁止路径规则，先把 **91 个**允许访问的 HTML/JS/MJS/CSS 文件原字节复制到安全镜像，保存逐文件 SHA-256 清单，再从 `D:/dp-dev/tmp/mwg` 对两棵镜像分别运行 `npx.cmd --no-install modern-web-guidance legacy-scan <路径>`。结果保存在要求的 `D:/dp-dev/tmp/webguide/scan-after.txt`：**DP 0 条、Disc Lab 0 条**（各 33 个 qualified guides）。没有剩余条目需要判为误报。扫描只覆盖工具声明的约 20% 指南，不是完整符合性证明。
- `git diff --check`：通过。UTF-8 检查 **34 个**变更代码/测试文件，原有非 ASCII 保留，无 U+FFFD、无四连问号；源码里的 `nullish coalescing` 是合法运算符，逐文件计数保存在 `encoding-check.json`。本报告另做中文字符及问号校验。

中间轮次有夹具问题，均保留了原有验收断言并修正夹具：脚本字符串里的 `<head>` 不能当文档头插入；预设下载检查不能自行 fetch Blob；未保存设计的离开确认需要由测试响应。一轮现有 `test_review_library_newwork.mjs` 还记录了 ResizeObserver 通知时序错误，单项复验通过；最终完整 37 项文件整轮也通过，原失败日志保留在 `test_review_library_newwork.previous.log`。没有消音该错误或放宽测试，不能据此排除以后偶发复现。

测试临时目录、浏览器 profile、日志、策略抓取、扫描镜像均在 D 盘。生成的截图移到 `D:/dp-dev/tmp/webguide/browser-screenshots-final/`，不提交到源码。报告中的策略取自最终 Edge HTTP 夹具抓取的 `csp-headers.json`；测试服务器已经关闭。

## 未测与需要人决定的问题

- 真实 iPhone Safari、中文/日文/韩文系统输入法人工操作：**未测**。这里验证的是 Safari 顺序和 keyCode 229 的合成事件，不等于真机验收。
- 实体光驱、真实刻录、外网传真服务及其 CORS：**未测**。所有设备路径使用已有 mock 或 Disc Lab 虚拟实验盒。
- 未做人工审美或逐像素截图比对；现有几何、版式和动画浏览器断言通过，CSS 数值未改。
- 需要发布方决定正式传真服务及其图片/皮肤 origin，部署时配置白名单；是否以后迁移动态样式以移除样式 unsafe-inline，留给后续独立任务。

## CSP 最终原文

以下为本轮默认白名单为空时实际响应头。手机脚本哈希随替换后的配置变化；列出的只是已经关闭的临时测试响应样例。自定义传真白名单只在前述两条来源指令追加 origin。

### `/home/`、`/home/index.html`

```text
default-src 'self'; script-src 'self' 'sha256-Cl4T78CkHaFLqwd5vu2q6ZyNqBezZd7mstcg3G1tqG8=' 'sha256-u4/UPKUgIxGcH0ow0G7dHXdifjTlVLjGxpt1zMrSCAk='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/phone/<临时令牌>`

```text
default-src 'self'; script-src 'self' 'sha256-W89SZ5F7xJK86lGY1AEly9w3NrYk0qqiegMiRKHD6mQ=' 'sha256-kG/MgLxGDPYUqyhwaPBmlz/YitjlfswbiMGLeT2HXDs='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `Disc Lab /`

```text
default-src 'self'; script-src 'self' 'sha256-/s0hDl+q7YoYlnCg8a+gDOFEqCu47+MAkfd9aRItZFA='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/home/dev-burn.html`

```text
default-src 'self'; script-src 'self' 'sha256-akVPY9jlZbyCWrjd+U1Kzls3eWwoUCu5d/MrNIEvvRA='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/home/dev-photo.html`

```text
default-src 'self'; script-src 'self' blob: 'sha256-z1Fr3eyLhkCV+DP5qeEXemMe8gqReh0phHHjoqTfJBc='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/home/dev-preview.html`

```text
default-src 'self'; script-src 'self' 'sha256-p6dJby0IfehLPaujYsz8sk5llNQCbFPd4yhs4/Ov1kY='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/home/kit/kit-preview.html`

```text
default-src 'self'; script-src 'self' 'sha256-N4xP/1lUWqmx2rxXme90YfbmiQ/tzp3dFdl2EO7px+Y='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/home/pastworks-preview.html`

```text
default-src 'self'; script-src 'self' 'sha256-FE8lYk1TPOwRKB+Z9hi4V8oqcE2h3CTuVYJej1S8YiQ='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/home/photocal-preview.html`

```text
default-src 'self'; script-src 'self' 'sha256-lxcHesY/NC0ysoFjUVjxGa4s90XMpQv/KED5SJqCtWw='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

### `/samples.html`

```text
default-src 'self'; script-src 'self' 'sha256-VEsZ0IRDaUtnhviuHu7fYzAqGx7dBX8wZ5nLkzlFHfw='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```
