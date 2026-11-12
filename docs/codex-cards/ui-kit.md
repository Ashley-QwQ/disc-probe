# Task card: a small UI kit for the disc-probe page (vanilla JS), after two component libraries

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches; no
servers, no drives. Two other Codex jobs are editing `discprobe/webui.py`, `discprobe/web/home/calibrate.js`,
`index.html`, `photocal*` right now: do NOT edit ANY existing file. Create only a new folder `discprobe/web/home/kit/`
(modules, one `kit.css`, a `kit-preview.html`) and new tests `tests/test_kit_*.mjs`. The wiring into the pages is done
by someone else later.

## References (downloaded, read them; they are React/Tailwind/Motion, ours is plain ES modules + CSS)

- `D:/ref-ui/obsidianui` (MIT, see its LICENSE): `src/components/block/flip-text.tsx`, `text-stream.jsx/.css`,
  `status-bars.tsx/.css`, `active-sessions.tsx/.css`, `src/components/ui/progress.tsx`, their docs in
  `src/content/*.mdx` and `public/markdown/docs/*.md`. You may port logic from these; put a credit line
  ("after ObsidianUI <component>, MIT") at the top of each file that does.
- `D:/ref-ui/rewampui` (NO license: read for behaviour and feel only, do NOT copy code or CSS; write your own):
  `src/components/ui/SlideToConfirmButtonShowcase.jsx`, `NeumorphicDownloadButtonShowcase.jsx`,
  `ShimmerButtonShowcase.jsx`, `GlossButtonShowcase.jsx`, `ChromeBorderButtonShowcase.jsx`, and look through the rest of
  `src/components/ui/` for small progress bars / loaders worth having; list what you looked at in your report.

## Build (each a tiny ES module exporting a function that creates/updates DOM; no frameworks, no packages)

1. `flipnum.js` — numbers that roll when they change (after ObsidianUI flip-text / text-stream): `flipNumber(el)` returns
   `{ set(text) }`; only the changed characters roll (digits up when increasing, down when decreasing), the rest stay;
   tabular figures; works for "62%", "约 4 分钟", "01 / 08". Motion off (`document.documentElement.dataset.motion === "off"`)
   = plain text swap.
2. `statusbars.js` — a row of thin bars, one per event (after ObsidianUI status-bars): `statusBars(el, items)` with items
   `{ state: "ok"|"needs"|"unknown", label, when }`; ok = ink, needs = copper, unknown = ink at 25 %; hover/focus shows the
   label and date in a small tooltip; keyboard reachable; an accessible summary ("12 次，2 次要看").
3. `devices.js` — connected devices list (after ObsidianUI active-sessions): `deviceList(el, devices, { onDisconnect })`,
   device `{ id, name, kind: "phone"|"computer", since, sent, thisDevice }`; each row: icon (line drawing, ours), name,
   "已连上 3 分钟 · 发来 2 张", a quiet "断开" text button (not on this device). Empty state: one line.
4. `slideconfirm.js` — slide to confirm, for irreversible actions like burning (behaviour after Rewamp's, code ours):
   `slideConfirm(el, { label, done })`; drag the knob to the end (or keyboard: focus + hold Right/End for 1 s, Enter
   does nothing by itself), springs back if released early; on confirm calls `done()` and shows a tick; disabled state.
5. `ringbutton.js` — a button that carries its own progress (behaviour after Rewamp's neumorphic download, code ours):
   `ringButton(btn)` returns `{ progress(p | null), done(), reset() }`; a small ring at the button's leading edge fills
   0..1 (null = indeterminate slow turn); the label stays readable.
6. `shimmer.js` (optional, only if it stays quiet): a "working…" text with a slow sheen, for checking states.

## Look (the site's rules, strict)

- Paper and line drawing; only the disc has colour. Colours only through the page's CSS variables: `--ink`, `--ink-2`,
  `--ink-3`, `--rule`, `--rule-strong`, `--copper`, `--paper`, `--paper-2`, `--mono`, `--font`. Copper only for what needs
  the person. No gradients, no glow, no neumorphic soft shadows, no rainbow: take the motion and the interaction, not the
  styling. Buttons on the page cast the page's glass shadow: `box-shadow: var(--glass-desk, none)`.
- Line widths: outline 1.5 px ink; structure 1 px ink 70 %; detail 0.75 px ink 40 %. Radii 4 px (controls), 8 px (cards).
- All words zh first with en (`lang` option, default "zh").
- `kit-preview.html`: one page showing every component in both themes side by side (define the CSS variables by copying
  the `:root` / `:root[data-theme="dark"]` token blocks of `discprobe/web/home/index.html`), with buttons that drive them
  (step a number, add a status, add/remove a device, run a fake progress). Relative URLs, works from
  `python -m http.server` in `discprobe/web/home`.

## Tests

`tests/test_kit_*.mjs` with plain `node:assert` on the pure parts (which characters roll and which way; status summary
text; time words; slide threshold and keyboard reducer; progress clamping). Run all `node tests/*.mjs` and
`node tests/test_burn_page.cjs`.

## Done means

Files exist, tests pass; report per component what it is after, what was ported (MIT) vs. written new, and anything
from Rewamp you found worth adding later.
