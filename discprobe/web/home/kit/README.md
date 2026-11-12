# 小组件 / Small UI kit

仅包含组件和演示，尚未接入页面。加载 `kit.css`，再按需导入 ES 模块；不用框架、包或 CDN。
Components and preview only; page wiring is left to the integration job. Load `kit.css`, then import the modules you need.

## 用法 / API

所有可生成文字的组件默认 `lang: 'zh'`，可选 `'en'`；`flipNumber` 的内容由调用者提供。
All generated copy defaults to Chinese; pass `{ lang: 'en' }` for English. Number text belongs to the caller.

```js
import { flipNumber } from './kit/flipnum.js';
import { statusBars } from './kit/statusbars.js';
import { deviceList } from './kit/devices.js';
import { slideConfirm } from './kit/slideconfirm.js';
import { ringButton } from './kit/ringbutton.js';

const number = flipNumber(numberEl);
number.set('62%');
number.set('约 4 分钟');
number.set('01 / 08');
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

Final validation: the kit pure/browser tests and `test_burn_page.cjs` pass. An earlier full run of all 12 `.mjs` files and the burn-page test passed. After concurrent edits outside this kit, the final full run has 10 of 12 `.mjs` files passing: `test_photo_wire.mjs:113` expects `L = 2.5 frames` but receives the unverified-saved-preset message; `test_photo_wire_browser.mjs:106` expects phase `saved` but receives `photo`. Both failures reproduced in a focused rerun. These tests exercise the protected photo/calibration integration and do not import the new kit; no protected implementation or test was changed to resolve them. Whole-repository green status is therefore not claimed.

The skill's separate finish reviewer inspected the modules, tests, provenance and final desktop/390 CSS px captures after the correction batch and returned **ship within the kit's scope**, with no unresolved kit blockers. It did not certify physical touch, screen-reader behavior or the unrelated photo-wire suite.
