# Task card: the photo calibration page (from the designer's mockups), as a self-contained module

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches.
Do NOT start long-running servers, do NOT touch any drive. Two other Codex jobs are editing in this worktree right now:
do NOT edit any existing file at all. Create only these new files:
`discprobe/web/home/photocal.js`, `discprobe/web/home/photocal.css`, `discprobe/web/home/photocal-preview.html`,
`tests/test_photocal.mjs`. (Someone else wires the module into the calibration flow later.)

## The mockups (the designer's drawings; replicate their values, not their code)

Unzipped, one folder each (read the `*.dc.html`: inline styles and the `<helmet><style>` carry the values):
- aligning, paper theme: `C:/Users/ADMINI~1/AppData/Local/Temp/claude/0fa2f3b7e932577a/3cb97cf6-4528-48e8-a950-a898c53a3f9c/scratchpad/mockups/align_paper/Main.dc.html`
- aligning, ink theme: `.../scratchpad/mockups/align_ink/Ink.dc.html`
- no photo yet: `.../scratchpad/mockups/no_photo/Empty.dc.html`
- focus mode: `.../scratchpad/mockups/focus/Focus.dc.html`
Screenshots of each: `.../scratchpad/mockups/{align_paper,align_ink,no_photo,focus}.png`, all four on one sheet:
`.../scratchpad/mockups/sheet.png`. The designer's written notes: `D:/disc-probe/docs/goals/art-brief/review/评审意见.txt`,
section "新页面：照片标定页" (read all of it). The mobile page is out of scope.

## Corrections to the mockups (these win over the drawings)

1. The calibration disc pattern is NOT spirals. It is unequally spaced concentric rings plus a pseudo-random barcode of
   spokes. So the alignment overlay is: the disc outline, and a set of concentric ring guides (radii in mm given as data,
   default `[30, 38, 47, 55]`), each ring with 4 small square handles (at 45°, 135°, 225°, 315°); dragging a handle
   changes that ring's radius only. Keep everything else of the designer's overlay: copper thin line with a dark outline
   so it shows on any photo; the dragged handle filled copper with a ring; the small mono label "r 47.0 mm · 偏 0.9 mm"
   next to it; disc outline and printable area as thin white dashed lines; a small radius scale (24, 40, 58 mm).
2. The disc's rim is found automatically by the program (no step for the person to align the rim).
3. Phone upload, auto-align and the photo reader are NOT available from this page yet. Rule of the whole site: no dead
   ends, no fake buttons. So: the QR block is shown only when the host passes a `phoneUrl`; otherwise that place says in
   one plain line that phone upload is not connected yet and points to "add from this computer". The "自动对齐" button is
   shown only when the host passes an `autoAlign` callback. "从电脑添加照片" and drag-and-drop onto the viewport work for
   real (local files, object URLs; nothing is uploaded).
4. Service address in the mockup (192.168.1.23:8472) is a placeholder; never hard-code it.

## The module

```js
export function photoPage(host, opts)   // mounts into `host` (an element); returns { destroy(), state() }
// opts: { lang: "zh"|"en", photos: [], ringsMm: [30,38,47,55], measuredMm: [24,52], phoneUrl: null,
//         autoAlign: null | async (photo, rings) => ({ rings, offsetMm }), onUse: (photo, rings) => void,
//         onSkip: () => void, onBack: () => void }
```
States: "no photo yet" (the mockup Empty: the QR or the honest line, the "how to shoot" side drawing, the drop zone,
the paper with "why", "after shooting", "not shooting is possible" + "跳过，就用现在的结果"), and "aligning" (Main/Ink:
viewport with the photo filling it, the overlay, the floating toolbar below the disc — select/pan, zoom − %, +, 整张盘,
曲线 show/hide, 增强条纹 (CSS contrast filter) — the photo strip on the paper with labels, the alignment summary).
Focus mode: button "专注" and key F; hides everything but the viewport; Esc first leaves focus (only), shows the three
small things of the mockup (shortcut strip, minimap with zoom %, alignment readout); while dragging a handle a 4×
magnifier with cross-hairs appears offset up-right of the handle (draw it from the photo, it must not cover the hand).
Pan with drag (space or the hand tool), zoom with the wheel around the pointer, 整张盘 resets.
All words in both languages (zh first), from the mockups.

## Look (the site's rules; check against the screenshots)

- Use the page's CSS variables only (`--paper`, `--paper-2`, `--ink`, `--ink-2`, `--ink-3`, `--rule`, `--rule-strong`,
  `--copper`, `--mono`, `--font`, `--edge`, `--row`, `--foot`); both themes through them. Only the disc/photo has colour;
  copper only for what needs the person (the dragged handle, the curve, "先加一张照片"-type reasons). No green, no red.
- Line widths: outlines 1.5 px ink; structure 1 px ink 70 %; detail and hatching 0.75 px ink 40 %.
- The paper on the right is the same paper as the calibration card: in CSS
  `border-image: url(newplan/paper_paper.webp) 120 fill / 46px / 23px stretch;` (dark theme `newplan/paper_dark.webp`),
  plus `box-shadow: var(--paper-desk)` if defined. Buttons and floating tools lie on "glass": `box-shadow: var(--glass-desk)`
  for buttons, `filter: var(--glass-desk-drop)` for floating text; fall back to nothing when the variables are missing.
- QR on the ink theme stays dark-on-light (scanners). Generate QR codes yourself only if you can do it without packages;
  otherwise accept `phoneQrSvg` as an option and draw nothing when absent.
- `photocal-preview.html`: a standalone page in the same folder that loads `photocal.css`, defines the CSS variables
  (copy the `:root` and `:root[data-theme="dark"]` token blocks from `discprobe/web/home/index.html`), a theme toggle,
  a language toggle, and mounts the module in "no photo yet"; picking or dropping a photo goes to "aligning". It must
  work served by `python -m http.server` from `discprobe/web/home` (relative URLs only).

## Tests

`tests/test_photocal.mjs` (plain `node:assert`, no packages; import only pure helpers you export from photocal.js, e.g.
ring/handle geometry, px↔mm with zoom/pan, magnifier placement that never covers the pointer, the "Esc leaves focus
first" key handling as a pure reducer). Also run `node tests/test_web_guidance.mjs` and `node tests/test_geo_progress.mjs`.

## Done means

The four files exist; tests pass; report what is real and what waits for the host (phoneUrl, autoAlign), and list any
mockup detail you left out and why.
