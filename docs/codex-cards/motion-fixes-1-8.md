# Task card: fix motion-audit items 1–8

Worktree: `D:/disc-probe/.claude/worktrees/review-fixes`, branch `web/review-fixes-20261112` (head f5fe211).
- Do NOT commit, push, stash, reset or switch branches.
- No drives. Port 8813 serves this folder for the person: do not stop or restart it. For your own checks use the
  pretend drive (`D:/disc-probe/.claude/worktrees/web-walkthrough/devserve.py` + `walk-scenario.json`; see that
  worktree's `.claude/launch.json` `walk-blank`) on a free port such as 8876. Never use ports 8772, 8795, 8798, 8812,
  8813, 8841, 8863. Never press a burn.
- Edit only what these items need: `newplan.js`, `newplan.css`, `calibrate.js` (the pan / card hand-off only),
  `lobby.css` (item 4 only), `kit/shared.js`, `kit/kit.css`, `kit/flipnum.js`, `photocal.css`, `burn.js`,
  `index.html` (`setTray` only), `design.js` (only the hand-off that item 5 needs), and tests.

The audit with every detail (file:line, reproduction, screenshots, suggested fix):
`C:/Users/Administrator/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/local_2cfb5b01-cd5a-41c5-9159-c871a79e44e1/motion-audit-20261113.md`.
Read the ranked table and sections 1–8. Its screenshots are referenced by name; the files are in the auditing
session's scratchpad. You don't need them.

## Items (the audit's fix is the default; a better one is fine if you say why)
1. **P0.** Back/Esc during the new-work → calibration pan leaves the calibration card and step ruler over the
   lobby. The pan owns Back while it runs. Back mid-pan reverses the running pan from where it is (store its
   animations), and `calibrateFirst()` stops its later steps if the mode changed.
2. **P1.** Esc during the lobby → new-work push jumps, re-measures the origin, and double-Esc stacks two reversals.
   Store the push state (animations and an origin measured once, before the lobby transforms), reverse the running
   push from its current time, and ignore a second Esc while leaving.
3. **P1.** Forced motion "on" is overruled by the system's reduced-motion in the kit (rolling numbers, ring, slider)
   and on the photo page. `motionOff` reads only `data-motion`. Gate the `@media (prefers-reduced-motion)` blocks with
   `:root:not([data-motion])`, so standalone previews without the attribute still fall back. Drop flipnum's system
   listener.
4. **P1.** Dark theme: entering past works fogs the lobby light grey. The push shade must be dark in both themes
   (not `var(--ink)`).
5. **P1.** New work → design: after bagging there is a hard cut to an empty dark page. Keep the new-work page under
   the design page until the design page has faded in (or crossfade them over the same 420 ms). Then hide it. No
   empty frame. Keep the bag dropping out as it does.
6. **P1.** Back while the calibration card comes out of the envelope stacks two envelopes. `cardIn` finishes or
   cancels the running `cardOut` and removes its parts first; better, it reverses it from where it is.
7. **P1.** Push / pull-back use one easing over the whole keyframe list, which squeezes the opacity stop (the fade-in
   is done at 87 ms instead of about 340 ms; the pull-back fades only in the last 90 ms). Put the easing on each
   keyframe (linear overall), or split transform and opacity into two animations with their own timing.
8. **P1.** On the burn page with the real backend the pictured tray never opens: `burn.js` calls
   `api.setTray(true, false)` without `known`, and `index.html` returns early for non-mock backends. This is a picture
   only and must not touch the drive: pass the flag, or add an explicit `visual` parameter to `setTray`.

The site rules still hold:
- the motion setting is `document.documentElement.dataset.motion` ("off" → instant end states);
- transform and opacity only on moving layers;
- the person cares about continuity: the last frame of A matches the first frame of B.

## Tests
- Add browser tests (mock or pretend drive, scrubbing WAAPI with `pause()` / `currentTime`, no wall-clock sleeps
  where avoidable) for:
  - 1: Back mid-pan ends in new work with no `#cal` / `cal-staged` left over;
  - 2: Esc mid-push reverses from the current frame, and double Esc makes one reversal;
  - 3: forced "on" with system reduce still rolls the numbers;
  - 4: shade colour in dark;
  - 5: no frame where neither page is visible;
  - 6: one envelope only;
  - 7: opacity at 50 % of the push is between 0.3 and 0.9;
  - 8: tray picture opens on a non-mock backend without any drive call.
- Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs` (skip the helper `tests/editor_runner.mjs`).
  All must pass.

## Done means
Tests pass. Report per item what changed (file:line) and anything you couldn't do inside the boundary.
