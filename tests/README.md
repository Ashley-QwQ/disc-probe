# 浏览器测试

在仓库根目录用 Node.js 22 或以上版本执行 `node --test tests/test_brand_browser.mjs`。Python 浏览器工具也使用 Node 运行同一个启动器。

`DP_TEST_BROWSER` 可指定 Chromium 系浏览器的可执行文件。Windows 默认使用本机的 `chrome-headless-shell`，可用 `DP_HEADLESS_SHELL` 指定另一份 shell。找不到 shell 时，启动器用 Windows Edge，并复用 `%LOCALAPPDATA%/disc-probe-test-browser/edge-profile`。指定完整版 Windows Chrome 也会复用固定配置。全新的 Edge 或 Chrome 配置会触发一次 Windows 登录检查，重复启动可能锁定账户。Linux 从 PATH 查找 Chromium。

各测试原先支持的浏览器环境变量仍可用。使用旧变量时，启动器会提示改用 `DP_TEST_BROWSER`。优先级是 `DP_TEST_BROWSER`、工具的 `--browser` 参数、测试原有的环境变量，再到平台默认值。

编辑器适配测试在 shell 上用 CSS 视口和设备像素比复现页面缩放条件。`EDITOR_FIT_NATIVE_ZOOM=1` 使用固定配置的 Edge，通过扩展接口测试原生标签页缩放。
