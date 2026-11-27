# Task card: put the photo page into the calibration flow

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches. Do NOT
start long-running servers or touch drives. Another Codex job is building the core side (`discprobe/webui.py`,
`discprobe/pcal.py`, `discprobe/photo.py`, `discprobe/web/phone/`): do NOT touch those or `discprobe/__main__.py`.
Files you MAY edit: `discprobe/web/home/calibrate.js`, `discprobe/web/home/index.html` (a stylesheet link and small
rules only), `discprobe/web/home/photocal.js` / `photocal.css` (fixes only), `discprobe/web/home/guidance.mjs` (words),
and tests under `tests/`.

## What exists

- `discprobe/web/home/photocal.js`: `photoPage(host, opts)` (read it; the preview `photocal-preview.html` shows its use).
- The contract with the core: `docs/codex-cards/photo-contract.md` (routes and the "photo" job). Build against it even
  though the core is being written at the same time; when a route answers 404, the page behaves as "not available"
  (no phone block, no auto-align) and says so in one line. Never a dead end, never a fake button.
- The calibration page: `calibrate.js` (phases `review`, `photo`, the CD route, the recovery for `narrow_span`), the step
  ruler (`RULER`, its "拍照" segment), the stage (`calstage.js`) and the paper card (`#cal`).

## Do

1. When the calibration reaches the photo step, show the photo page in place of the stage (left) and use the paper card
   (right) for its paper: the step ruler's "拍照" segment becomes current. The photo step is reached
   (a) on the CD route, where it now says "continue in DIS" (keep that text as the fallback when the photo job is not
   available), and (b) from a geometry result whose recovery kind is `narrow_span` (an action "拍一张照，补上外圈" next
   to the existing ones, not replacing them).
2. Wire the options per the contract: phone link, photos list (poll every 2 s while open), autoAlign = start the "photo"
   job through the existing job runner (`realJob`) and map its result; per-photo reasons shown under the thumbnails.
3. Next: "下一步：用这张照片" runs/uses the photo result: verdict ok -> save as the existing save path does (CD: the
   along-track constant goes where the CD preset needs it; if the save code has no place for it yet, keep the value in
   the flow, show it on the result stamp, and list that in your report). verdict unsure/rejected -> say why in the stamp
   style (意思 / 对你的图 / 现在) and offer "再拍一张" and "跳过，就用现在的结果". Skip returns to the review with the
   existing result.
4. Back (the page's Back button / Esc) leaves the photo step to the review; in focus mode Esc only leaves focus.
5. Keep the site's rules: copper only for what needs the person; glass shadows on buttons as elsewhere.
6. Tests: extend or add node tests for the routing of the photo step (which phase shows the page, which button goes
   where, 404 -> "not available" mode). Run all node tests in `tests/` and `python -m pytest -q tests`.

## Done means

Tests pass. Report what is wired, what falls back while the core routes are missing, and anything you could not place.
