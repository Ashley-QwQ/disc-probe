# Task card: fix motion-audit items 9–17

Worktree: `D:/disc-probe/.claude/worktrees/review-fixes`, branch `web/review-fixes-20261112` (head 71917e9; items 1–8
are already in, see `docs/codex-cards/motion-fixes-1-8.md` and `tests/test_motion_browser.mjs`).
- Do NOT commit, push, stash, reset or switch branches.
- No drives. Port 8813 serves this folder for the person: do not stop or restart it. For your own checks use a mock
  page or the pretend drive (`D:/disc-probe/.claude/worktrees/web-walkthrough/devserve.py`) on a free port such as
  8877. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863. Never press a burn.
- Edit only what these items need: `newplan.js`, `newplan.css`, `lobby.js`, `lobby.css`, `pastworks.js`,
  `pastworks.css`, `presetio.js`, `presetio.css`, `index.html` (only if an item needs it), and tests.

The audit, with file:line, reproduction and suggested fix for each:
`C:/Users/Administrator/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/local_2cfb5b01-cd5a-41c5-9159-c871a79e44e1/motion-audit-20261113.md`.
Read the ranked table and sections 9–17. Line numbers may have moved since items 1–8 landed.

## Items (the audit's fix is the default; a better one is fine if you say why)
9. Esc during the bagging skips forward into design. Ignore clicks on `#back` for the skip, as `pastworks.js` does.
   A real Back undoes the filing (drop `.filing` so CSS runs back) and cancels the pending `next()`.
10. The push lands off the disc (about 80 px, different size). Aim `pushTransform` at the disc on the lobby drive's
    tray (use lobby.json coordinates if present, else the hot-spot centre plus a fixed offset). Size `LOBBY_PUSH` so
    the lobby disc's diameter × LOBBY_PUSH ≈ the top view's disc diameter × TOP_START. The top view's disc is at
    512, 720 of 2560 × 1440 now (the drive was turned round).
11. First entry stalls up to 600 ms when the page is entered without hovering the drive first. Preload newplan and
    pastworks with `requestIdleCallback` after the lobby is up, and also prepare on focus/hover of `#next`.
12–13. Back from calibration takes about 2.8 s and can't be skipped, and the sheet sits under the envelope's front
    for about 400 ms. Click/Enter finishes everything and reopens at once, like the bagging skip. The sheet goes above
    the envelope front as soon as it clears the opening, or the envelope starts dropping much earlier (about 150 ms).
14. The presets desk has no entry or exit transition: a hard cut. Push the lobby into the letter tray (the same
    `pushLobby` approach, origin on the tray), then the desk scales up and fades in from the tray's place, 560–760 ms;
    reverse on close. When motion is off, cut as now. The desk opened from the new-work page ("从 DIS 导入") may keep a
    simple crossfade.
15. Past-works flight performance: drive the push with WAAPI instead of rAF style writes where possible, set
    `will-change: transform` on `#lobby-art` during it, crossfade at about 4–5× instead of 11.66×, and write layer
    opacity directly instead of custom properties on `.pw` that restyle the whole page. Keep the look the same.
16. A second lever move mid-flight first snaps the running one to its end. Reverse from the current progress, or start
    from the current computed transforms.
17. With motion off, past works waits up to 1.5 s before showing (250 ms with motion on). Use 250 in both cases; the
    list can paint later (`listed.then(render)` exists).

The site rules:
- `document.documentElement.dataset.motion` decides ("off" = instant end states);
- transform and opacity only on moving layers;
- continuity, so the last frame of A matches the first frame of B;
- keep items 1–8 working.

## Tests
Add to `tests/test_motion_browser.mjs` (scrub WAAPI with `pause()` / `currentTime`):
- 9: Esc during the bagging stays in new work;
- 10: the push's end frame puts the lobby disc within ~10 px of the top view's first-frame disc centre, at a similar
  size;
- 11: no wait before the push starts after preload;
- 12–13: click skips the return, and the sheet is never under the envelope front after clearing it;
- 14: the desk opens with an animation from the tray and reverses on close, instant when motion is off;
- 16: a second move starts from the current transform (no snap);
- 17: past works shows within 300 ms with motion off.

Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs` (skip the helper `tests/editor_runner.mjs`).
If your sandbox blocks pytest's temp dirs, say so; the reviewer will run it.

## Done means
Tests pass (or the blocked part is reported). Report per item what changed (file:line).
