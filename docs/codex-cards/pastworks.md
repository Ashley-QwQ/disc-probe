# Task card: the past-works page ("往期作品"), and falling into it from the lobby's file box

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches; no
long-running servers, no drives. Another Codex job is editing `index.html`, `calibrate.js`, `calstage.js`, `burn.js`,
`preview.js`, `photocal.js`, `webui.py`, `webui_catalog.py`, `photo.py`, `kit/`: do NOT touch those.
You MAY create `discprobe/web/home/pastworks.js`, `pastworks.css`, `pastworks-preview.html`, files under
`discprobe/web/home/pastworks/` (except the `tumble_*.webp` pictures, which are made for you), tests
`tests/test_pastworks*.mjs`; and you MAY edit `discprobe/web/home/lobby.js` / `lobby.css` (the entry only) and
`discprobe/web/home/design.js` (only to export what you need, e.g. a plan's disc thumbnail).

## The page (the person's own description)

A sheet of paper like a report form that runs on as long as it needs (it scrolls). On it, in rows and columns, archive
envelopes seen straight from above, each with its work's disc lying flat on it. The first cell is "新作品" (new work: an
empty envelope with a blank disc, dashed). Order: newest first by default; also by name (Chinese by pinyin:
`Intl.Collator("zh-u-co-pinyin")`, then others). Clicking an envelope moves the camera to it: the envelope with its disc
slides to the left half, larger; the right half is for details, left plain for now (one line: the name and date).
Behind the paper: many envelopes at different 3D angles, in three depth groups that move at different speeds while the
page scrolls (far slow and small and faint, mid, near fast and large and slightly soft), to feel like depth.

## Getting there: falling down the rabbit hole through the lobby's file box

The lobby has the past-works file box ("往期作品", standing envelopes; see `lobby.js` targets and `lobby/lobby.json`).
Clicking it (or its label, or its keyboard path):
1. push in on the box, as the lobby pushes in on the drive for "new work" (`newplan.js` pushLobby): ~0.4 s, the box's
   opening fills the window, the rest darkens;
2. fall ~1 s: the background envelopes stream upward past the camera, accelerating; near ones big and fast, far small
   and slow, some turning slowly. This IS the page's background scrolled very fast: same layers, same depth groups;
3. brake ~0.5 s like a falling sheet, and the report paper comes up from below and settles; "新作品" first.
The fall ends exactly in the page's resting background (no seam). Back (button / Esc) plays it in reverse (rising out,
the camera pulling back out of the box to the lobby). From the second time on the whole thing is shorter (~0.6 s);
a click or Enter skips; motion off (`document.documentElement.dataset.motion === "off"`) = straight cut.
Clicking "新作品" on the paper starts a new work the way the lobby does (`api.newWork` or the lobby's own handler).
Clicking a work opens it in the design page the way the lobby's "上次" link does (`design.start(api, { plan })`).

## Assets

- Envelope seen from above (the cells): `discprobe/web/home/newplan/envelope_back_<theme>.webp` +
  `envelope_front_<theme>.webp` (draw back, then the disc, then front only if the disc is inside; here the disc lies ON
  the envelope, so back + front, then the disc on top). Their geometry: `newplan/newplan.json` → `envelope`.
- The disc on each envelope: that work's own disc as the design page draws it (look for an existing thumbnail or the
  projection code in `design.js`; export a small `planThumbnail(plan, px)` if needed). Only the disc has colour.
- The tumbling envelopes: `discprobe/web/home/pastworks/tumble_<0..9>_<paper|dark>.webp` (640 x 640, the bag centred,
  transparent, different 3D angles; they will be there when you finish; until then use any placeholder and keep the
  names). Use each several times at different sizes / rotations (2D rotation is fine on top of their 3D angle).
- The paper: the calibration card's paper (`newplan/paper_<theme>.webp` as `border-image: ... 120 fill / 46px / 23px
  stretch`, see `index.html` `.cal-staged .cal`).

## Rules

- The site's look (read `discprobe/web/home/index.html` tokens and the glass comment): ink and copper only, only the
  disc has colour; buttons on the glass with `var(--glass-desk)` shadows; the paper lies on the "desk" (short shadow).
- Performance: background layers are a few absolutely positioned images per depth group, moved with `transform` only;
  cell discs are small images (cache them); no layout per scroll frame.
- Words zh first with en. No dead ends: no plans -> the paper shows only "新作品" and one quiet line.
- `pastworks-preview.html`: standalone, mounts the page with fake plans (both themes, the fall can be replayed).
- Tests (`tests/test_pastworks*.mjs`, plain node): sorting (time, pinyin, mixed scripts), the depth-group parallax maths,
  the fall's speed curve (monotone position, ends at rest), the "second time shorter" rule, back/Esc order. Run all
  `node tests/*.mjs` / `*.cjs` and `python -m pytest -q tests`.

## Done means

Tests pass; report what is real, what is a placeholder, how the lobby entry works, and anything left for later (the
details panel).
