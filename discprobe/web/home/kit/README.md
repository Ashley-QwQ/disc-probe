# 小组件 / Small UI kit

组件、演示与页面接入。加载 `kit.css`，再按需导入 ES 模块；不用框架、包或 CDN。
Components, preview and page integration. Load `kit.css`, then import the modules you need.

## 用法 / API

所有可生成文字的组件默认 `lang: 'zh'`，可选 `'en'`；`flipNumber` 的内容由调用者提供。
All generated copy defaults to Chinese; pass `{ lang: 'en' }` for English. Number text belongs to the caller.

```js
import { flipNumber, flipWatch, flipValue } from './kit/flipnum.js';
import { statusBars } from './kit/statusbars.js';
import { deviceList } from './kit/devices.js';
import { slideConfirm } from './kit/slideconfirm.js';
import { ringButton } from './kit/ringbutton.js';

const number = flipNumber(numberEl);
number.set('62%');
number.set('约 4 分钟');
number.set('01 / 08');
// Observe ordinary textContent assignments; read without the animation's old glyphs.
const watched = flipWatch(timeEl);
timeEl.textContent = '5 秒';
flipValue(timeEl);
// Before removing a number host: number.destroy().

const history = statusBars(historyEl, [
  { state: 'ok', label: '测量完成', when: '2026-11-11' },
  { state: 'needs', label: '检查盘面', when: new Date() },
  { state: 'unknown', label: '没有回读数据', when: null },
]);
history.update(nextItems, { lang: 'en' });

const devices = deviceList(devicesEl, connectedDevices, {
  lang: 'zh',
  // Receives (id, device); may return a promise. Reject to retain the row and allow retry.
  onDisconnect: (id, device) => disconnectDevice(id),
});
devices.update(nextDevices);

const confirmation = slideConfirm(confirmEl, { label: '滑动确认刻录', done: onConfirm });
confirmation.setDisabled(true);
confirmation.setDisabled(false);
confirmation.reset();
// Before removing the host: confirmation.destroy().

const progress = ringButton(existingButton, { lang: 'zh' });
progress.progress(0.62);
progress.progress(null); // Unknown progress, slow turn; no invented percentage.
progress.done();
progress.reset();
```

- `statusBars` and `deviceList` can be called again on the same host to update it. Their returned `update` methods preserve options unless overridden. Lists contain one status per supplied event; missing or invalid status values remain unknown.
- Device `since` and event `when` accept a `Date`, ISO string or epoch milliseconds. Date-only event strings retain their calendar day across time zones. Device time text is refreshed when `update` is called; there is no hidden polling timer. Optional `now` (epoch milliseconds) supports a caller's shared clock. Devices have `{ id, name, kind: 'phone' | 'computer', since, sent, thisDevice }`. The current device is listed first and has no disconnect button. Without a callback, other disconnect buttons are disabled. Successful callbacks remove their row; rejected callbacks keep it with a retry message.
- Mount `slideConfirm` on a container, not a button. Drag the knob all the way to the end **and release**. Keyboard users focus the knob and hold Right or End continuously for 1 second. Enter and Space never confirm. Early release, Escape, pointer cancellation, lost capture, blur, hiding the document, resize, and disabling cancel an incomplete gesture. `done` means the deliberate confirmation occurred, not that the irreversible operation succeeded. It fires once until `reset`. Initial `disabled: true`, the host's `disabled` attribute, and `aria-disabled="true"` are supported.
- `ringButton` preserves the supplied button's label nodes, listeners and disabled state. Use `progress` for fractions, `done` for completion and `reset` to return to the idle badge and original `aria-busy` / `aria-describedby` state. Localized progress is explicitly included in the button's accessible description, preserving pre-existing descriptions; completion also has a status announcement. `null` means indeterminate; numeric values clamp to 0…1, NaN/invalid values to 0. Label updates after mounting should target `.kit-ring-label`.
- `data-motion="off"` on the document root makes numbers plain text swaps, stops indeterminate rotation and removes spring transitions. The system's reduced-motion preference also stops these animations. No progress or confirmation is fabricated when motion is off.

## 页面接入 / Page integration

- 数字：标定大百分比和时间、底栏时间（含读盘的 5 秒倒计时）、盘库页码。Numbers: calibration percent/time, footer time including the 5-second disc check, library counters. `flipWatch` disconnects observation during internal rendering and ignores animation cleanup; `destroy()` stops text and motion observation.
- 记录条：盘批次详情；只用保存的真实 geo 结果及有明确几何或批次关联的刻录结果。无记录时隐藏。History: saved non-simulated geometry runs and explicitly linked burn results, oldest to newest. Unlinked old burns are omitted; no event is invented.
- 手机：照片列表轮询时一起读取 `/api/phone-devices`；404 只隐藏设备列表。断开会轮换该次测量的共享口令，所有旧链接失效，重新获取链接与二维码。Devices poll with photos; disconnect rotates the shared run token, revokes all old links and refreshes the QR. “This computer” cannot be disconnected.
- 确认：测量盘与成品刻录都用滑动条，保留原有勾选和检查。键盘聚焦滑块，按住 → / End 1 秒。Burn sliders retain consent and checks. `nextconfirm.js` swaps the shared Next button only for the irreversible step.
- 进度：测量镜像与预览页生成文件的 Next 按钮；没有进度时只转圈，关闭动效时停止。Image generation rings use job fractions; unknown progress is indeterminate. `ringButton.destroy()` restores label nodes and accessibility state before another page takes Next.

刻录数据：引擎的 `iso/*.iso.burn.jsonl` 经 `.image.json` 的 `geometry_from` 关联；网页任务另存 `.webui-jobs/*/burn.json`，保留引擎结果、时间与写入前已知的批次。两处同一日志与时间的记录只显示一次。失败、取消、坏回读为铜色；已完成且样本全可读为墨色；未验证或无法判断为淡色。这不证明实物图案正确。
Burn sources: engine JSONL plus image-sidecar geometry links, and durable web-job burn records with the batch known before writing. Duplicate log/time pairs count once. Failed/cancelled/bad read-back needs attention; a completed clean sample is OK; missing verification stays unknown. This does not certify the physical artwork.

页面接入验证（2026-11-11）：`python -m pytest -q tests`：234 通过、1 跳过、46 subtests 通过；全部 16 个 `tests/*.mjs` / `*.cjs` 通过。受限 Windows 会话用 `PYTEST_ADDOPTS=--basetemp=.test-tmp/pytest-kit-wire-verified` 把临时文件放在工作树。浏览器测试使用本地文件或拦截的测试响应，没有启动长期服务器或接触光驱；检查了桌面、760 px、390 px、纸色/墨色、减弱动效、断开与口令轮换后的链接、旧服务器 404，以及刻录滑块和生成进度。未实测触屏、读屏器或实际刻录。
Page integration validation: 234 pytest tests passed, 1 skipped, 46 subtests passed; all 16 Node test files passed. Browser checks cover actual page DOM and kit behavior using local/intercepted fixtures. Physical touch, screen readers and real burning were not exercised.

## 来源与授权 / Provenance

| Component | Reference | Adapted / written here |
| --- | --- | --- |
| `flipnum.js` | ObsidianUI `flip-text` and `text-stream`, MIT | Adapted the per-character window and vertical movement ideas. Numeric-run comparison, changed-character reconciliation, node reuse, accessibility and reduced-motion text swapping are new vanilla JS. No React, GSAP, Motion or NumberFlow code/dependencies were brought in. |
| `statusbars.js` | ObsidianUI `status-bars`, MIT | Adapted event strip, date-tooltip and keyboard navigation patterns. Event states, Chinese/English summary, date formatting and DOM implementation are new. No uptime assumptions, inferred successful events or daily padding. |
| `devices.js` | ObsidianUI `active-sessions`, MIT | Adapted current-device-first sorting, protected current device, async pending/error handling and focus recovery. The connection-duration/photo wording, SVG drawings and DOM implementation are new. |
| `slideconfirm.js` | Rewamp `SlideToConfirmButtonShowcase.jsx`, behaviour only | All code and CSS written here. The downloaded reference actually starts its truck animation on click; this kit implements the task card's stricter drag/hold gesture instead. |
| `ringbutton.js` | Rewamp `NeumorphicDownloadButtonShowcase.jsx`, behaviour only; ObsidianUI `progress.tsx` inspected | All code and CSS written here. Small monochrome SVG ring, independent readable label, indeterminate state and explicit completion/reset. No borrowed gradients, colour interpolation or soft-shadow treatment. |
| `kit.css`, `shared.js`, preview | Existing disc-probe page and the references above | Original component styles and icons. Preview copies both complete token blocks from `../index.html`; unused disc-gradient tokens remain in those exact copies, but no kit component uses a gradient. Dark tokens are additionally scoped to the comparison sheet. |

Credit lines are at the top of the adapted MIT component files and stylesheet. The complete ObsidianUI copyright/permission notice is in `LICENSE.obsidianui.txt`. No Rewamp source or CSS was copied; the checkout has no license grant.

Read locally: ObsidianUI's `LICENSE`, all five requested component sources and three accompanying stylesheets, plus the `flip-text`, `text-stream`, `status-bars`, and `active-sessions` documentation in both `src/content/*.mdx` and `public/markdown/docs/*.md`.

Read in Rewamp's `src/components/ui/`: `SlideToConfirmButtonShowcase.jsx`, `NeumorphicDownloadButtonShowcase.jsx`, `ShimmerButtonShowcase.jsx`, `GlossButtonShowcase.jsx`, `ChromeBorderButtonShowcase.jsx`, `Skeleton.jsx`, and `CanvasShimmerSkeleton.jsx`. Listed the directory's 136 files and searched its JSX/TSX for loader/loading/progress/spinner candidates; this search is not a claim that every component source was read.

Later candidates: an original, static placeholder matching a device row's footprint, informed by `CanvasShimmerSkeleton` and `Skeleton`; a delayed busy indicator for slow disconnects. No additional standalone small progress/loader component was found in the directory scan. The optional `shimmer.js` is omitted: the inspected sheen treatments rely on gradients or decorative reflections, while the required ring already communicates checking work quietly. Gloss and chrome styling are not carried forward.

## 预览与检查 / Preview and validation

`kit-preview.html` shows all five required components in paper and ink themes, side by side on desktop and stacked on narrow screens. Its controls change numbers, append each status type, add/remove devices, exercise confirmation/reset/disabled states, and run determinate or indeterminate sample progress. Language and motion switches apply to both sheets.

Relative URLs support `kit/kit-preview.html` when the home folder is served by `python -m http.server`. No server or drive operation was started for this task; the preview was exercised through local file URLs.

```powershell
Get-ChildItem tests -Filter '*.mjs' | ForEach-Object { node $_.FullName }
node tests/test_burn_page.cjs
```

`test_kit_pure.mjs` uses `node:assert` for numeric carry/direction/unchanged suffixes, summaries/dates, bilingual time words, slide thresholds, the keyboard reducer and progress bounds. `test_kit_browser.mjs` uses headless Edge and file URLs at 1280 px and 390 px iframe widths; pointer events/capture and the animation clock are synthetic. It checks actual DOM updates, focus recovery, disconnect errors, cancellation, one-shot callbacks, disabled semantics, labels, both themes, language/motion controls and horizontal overflow. It skips explicitly when no browser is installed (`KIT_TEST_BROWSER` can select Chromium). Physical touch and screen-reader use are not reproduced by these tests.

The mechanical style detector ran once. Its cream-palette, glass-shadow and spring-easing findings correspond to the task's explicit design requirements. Its Archivo finding conflicts with the existing `DESIGN.md` body-font token. Existing design files and tokens were preserved.

Kit-only validation before page integration: the kit pure/browser tests and `test_burn_page.cjs` pass. An earlier full run of all 12 `.mjs` files and the burn-page test passed. After concurrent edits outside this kit, the final full run has 10 of 12 `.mjs` files passing: `test_photo_wire.mjs:113` expects `L = 2.5 frames` but receives the unverified-saved-preset message; `test_photo_wire_browser.mjs:106` expects phase `saved` but receives `photo`. Both failures reproduced in a focused rerun. These tests exercise the protected photo/calibration integration and do not import the new kit; no protected implementation or test was changed to resolve them. Whole-repository green status is therefore not claimed.

The skill's separate finish reviewer inspected the modules, tests, provenance and final desktop/390 CSS px captures after the correction batch and returned **ship within the kit's scope**, with no unresolved kit blockers. It did not certify physical touch, screen-reader behavior or the photo-wire suite. The page integration and current tests are documented above and below.
