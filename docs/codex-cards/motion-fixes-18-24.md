# Task card: fix motion-audit items 18–24 (P3)

Worktree: `D:/disc-probe/.claude/worktrees/review-fixes`, branch `web/review-fixes-20261112` (head e7f51a6; items 1–17 are
in, with tests in `tests/test_motion_browser.mjs`).
- Do NOT commit, push, stash, reset or switch branches.
- No drives; don't touch port 8813. Use mock pages or the pretend drive on a free port such as 8878. Never press a
  burn.
- Edit only what these items need: `newplan.js`, `calibrate.js`, `loaddisc.js`, `index.html`, `design.js`,
  `design.css` and tests.

The audit (section "18–24"):
`C:/Users/Administrator/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/local_2cfb5b01-cd5a-41c5-9159-c871a79e44e1/motion-audit-20261113.md`.

18. The Next button's words change before the new page arrives (80 ms into the push, 379 ms into the pan). Set the
    words when the page arrives, or crossfade the label with the move.
19. `.flyer` and `.gallery` animate left/top (layout every frame). Move them with transform (translate) instead; the
    positions are already percentages.
20. The kind dial: the old label vanishes and only the new one turns in; the outer keys swap instantly. Turn a copy of
    the old label out the other way while the new one turns in, and give the outer keys a ~120 ms crossfade.
21. Design → preview: `hideDesign()` runs before `await import("./preview.js")`, which leaves an empty gap the first
    time. Import (or preload on hover/focus of Next) before hiding.
22. Back from calibration: the disc-load animation should play in reverse (the person asked for this earlier:
    "从标定返回计划页能不能倒过来播放下动画"). During `panBack`, play `loadDisc` backwards (the audit suggests
    `frame(anchor, T.end - ms)` over its 1080 ms) before or while the pan returns. Keep items 1, 6, 12 and 13 working
    (Back mid-pan, envelope handling, click-to-skip the return).
23. A resize mid-flight uses targets computed at the start. Recompute the end target on resize for the push and the
    past-works flight, or finish the flight at once on resize. Pick the simpler one and say which.
24. `design.css` `.dirty` dot fades in over 200 ms even with motion off. Respect `data-motion="off"`.

Rules: `data-motion` decides; transform and opacity only; continuity; items 1–17 keep working.

## Tests
- Add to `tests/test_motion_browser.mjs` where testable: 18 label timing, 19 no left/top animation, 20 two labels
  during the turn, 21 no empty frame, 22 the load plays reversed on Back and the skip still works, 24 the dot is
  instant with motion off.
- Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs` (skip `tests/editor_runner.mjs`). If pytest's
  temp dirs are blocked in your sandbox, say so; the reviewer runs it.

## Done means
Tests pass (or the blocked part is reported). Report per item what changed (file:line).
