# Task card: the presets page as a desk with a lever (import / export animation)

Worktree: `D:/disc-probe/.claude/worktrees/dis-presets`, branch `core/dis-presets-20261112`.
- Do NOT commit, push, stash, reset or switch branches.
- No drives. No servers outside tests; never touch port 8772.
- Edit ONLY `discprobe/web/home/presetio.js`, `discprobe/web/home/presetio.css`, `tests/test_presetio*.mjs`.
- Read but never change the pictures in `discprobe/web/home/presetio/desk/`. Clean up your own temp files.

## The picture (made for you, read `presetio/desk/desk.json` first)

One desk scene, 2560 x 1440 scene px, rendered in layers that line up pixel for pixel (same canvas), each in
`paper` and `dark` (the page's `document.documentElement.dataset.theme`; follow changes with a MutationObserver as the
current code does):

| file `desk_<name>_<theme>.webp` | what | moves |
|---|---|---|
| `base` (opaque) | desk, the letter tray's lower pan and feet, Penrose block, notebook and pen, the lever plate with its slot and two LED windows; all their shadows | never |
| `bag` + `bag_shadow` | the archive bag in the tray's lower tier, peeking out of the mouth at the bottom | export |
| `upper` | the tray's upper pan and posts (drawn ABOVE the bag) | never |
| `sheets` + `sheets_shadow` | the sheets in the upper tier | import |
| `knob` + `knob_shadow` | the lever's knob, drawn in the middle position | the lever |
| `doc_paper` + `doc_paper_shadow` | a big sheet in the middle column (the import form's paper), at rest | import |
| `doc_envelope` + `doc_envelope_shadow` | a big closed archive bag, top at the frame's top, running off the bottom (the export form) | export |

Draw order: base → bag_shadow, bag → upper → sheets_shadow, sheets → (desk writing, below) → knob_shadow, knob → LEDs
→ doc_*_shadow, doc_*. A layer always moves together with its shadow.

`desk.json`:
- `knob.centre_px` and `knob.travel_px` (up = export, down = import);
- `leds.export` and `leds.import` (centre, radius);
- `slot_px`, `lever_plate_rect_px`, `tray_rect_px`, `bag_rect_px`, `sheets_rect_px`;
- `doc_paper_rect_px`, `doc_envelope_rect_px`;
- `doc_paper_text_rect_px` and `doc_envelope_text_rect_px`, where the form's content goes on each document.

## The stage

- The sheet (`.presetio`) is full-screen.
- Inside it, a stage box of 2560 x 1440 scene px is scaled with `transform: scale(k)`, k = max(vw/2560, vh/1440)
  (cover), and centred. Every layer and every piece of HTML is positioned in scene px inside it.
- Recompute k on resize.
- On a narrow or portrait window (width < 820 px or aspect < 1.2), use the compact layout described below instead.

## Writing on the desk (left of the lever plate, as on the person's sketch)

Ink text printed on the desk itself, NOT glass: no shadow, colour `--ink-2`, the site font, about 34 scene px for zh
with en smaller under it. Each label is right-aligned, ending about 70 scene px left of the plate, with a thin ink
leader line (1.5 scene px) running to its LED's bezel.
- "导出数据 / Export" at the export LED's height.
- "导入数据 / Import" at the import LED's height.
- A short tick (no words) at the knob's middle height.

The writing lies under the documents: when a document flies in it covers part of the writing, which is fine (the person
asked for exactly that).

## The lever

- The knob is a `role="slider"` (aria-valuemin -1, max 1, valuetext "导出 / Export", "空 / Idle", "导入 / Import"),
  focusable.
- Drag it with pointer events (vertical only, clamped to ±travel; set capture). On release it snaps to the nearest of
  up / middle / down; past 40 % of travel counts. The snap takes 220 ms with an ease-out.
- Keyboard: ArrowUp moves one step up (down → middle → up), ArrowDown one step down. Clicking a desk label moves the
  lever there too.
- LEDs: the active one lights green: a small bright core (#7dff6a-ish) and a soft glow (box-shadow), fading in over
  150 ms when the knob arrives. The person asked for green explicitly; it is the only new colour.

## Choreography (motion on; `document.documentElement.dataset.motion === "off"` → instant, same end states)

- **Idle → export** (lever up):
  1. The knob travels.
  2. The bag + its shadow slide straight down out of the frame: 520 ms, accelerating
     (cubic-bezier(.55,0,.8,.2)). It passes under the upper pan.
  3. 140 ms after the bag starts, the big envelope + shadow fly up from below the frame to rest: 760 ms, decelerating
     (cubic-bezier(.16,1,.3,1)). While moving, its shadow sits farther from it (offset (-18, +24) scene px and a little
     larger), settling to 0 on landing, as if it lands on the desk.
  4. The export content fades in on the envelope (180 ms) after landing.
- **Idle → import** (lever down):
  1. The tray's sheets + shadow fly up out of the frame (520 ms, accelerating).
  2. 140 ms later the big paper + shadow fly down from above the frame to rest (760 ms, decelerating, same shadow
     landing).
  3. The import content fades in.
- **Back to idle:** the exact reverse. The document leaves the way it came (envelope down, paper up), then the bag
  slides back up into the tray / the sheets drop back in.
- **Export ↔ import:** the reverse to idle, then the other way in, chained.
- **A new move while one is playing:** finish the playing one at once (`Animation.finish()`), then start.
- **Reduced motion or off:** jump to the end state.
- Default on open: idle. The first view shows the desk, the tray, the writing and the lever; nothing covers the writing.

## The form, split across the two documents (keep ALL existing logic and requests as they are)

- **Import paper** (`doc_paper_text_rect_px`):
  - heading "导入 DIS 预设 / Import DIS presets";
  - the file pick + drop zone, the standalone media select, the preview rows, the import button.
- **Export envelope** (`doc_envelope_text_rect_px`, below its buttons):
  - heading "导出到 DIS / Export to DIS";
  - the DP preset select, "写进 DiscImageStudio" and "存成文件".
- The status line shows on whichever document is out.
- Content uses scene px sizes (body ~30, headings ~46, mono rows ~24) so it scales with the stage.
- Each text rect scrolls inside itself when the preview list is long. Ink on the kraft envelope uses the paper ink
  colours.
- Keep the current control styling (ink button for choosing a file, line selects) at scene size.
- **Close:** keep the glass close button fixed top right. Escape closes as now.
- **Title:** a small glass label top left, "预设 · DiscImageStudio / Presets".
- **Compact layout** (narrow or portrait): no stage. Show a plain paper card (the current CSS for `.presetio-paper` is
  fine) with two tabs "导入 / Import" and "导出 / Export" in place of the lever. Same content, same logic. No dead ends.

## Tests

Extend `tests/test_presetio_browser.mjs` (mock API, file URLs, as now):
- stage scale at 1440x900 and 1920x1080;
- the lever by keyboard and by pointer (drag up past 40 % → export; small drag → back to middle);
- LEDs on/off by state;
- with motion off, the end positions of the bag/sheets/docs per state;
- import and export flows still work from their documents;
- the compact layout at 390 px with tabs.

Save review screenshots to `.impeccable/review/desk-<state>-<theme>-<w>.png` for idle, export and import, both themes,
at 1440x900. Keep `tests/test_presetio.mjs` passing. Run `python -m pytest -q tests` and every `node tests/*.mjs` /
`*.cjs`. All must pass.

## Done means

Tests pass and the screenshots are saved. Report what you built and anything that needed a judgement call.
