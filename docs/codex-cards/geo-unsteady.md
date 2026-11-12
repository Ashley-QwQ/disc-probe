# Task card: stop geometry early when the drive's speed is not steady; re-measure at a fixed speed, around the bad band

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches.
Do NOT start servers, do NOT touch any drive (no real `timing`/`geo`/`burn`/`info` runs; use `--sim` and unit tests only),
do NOT edit `discprobe/scsi.py`. Another Codex job is creating `discprobe/web/home/calchart.js` and
`tests/test_calchart.mjs` right now: do not touch those two files.

Files you MAY edit: `discprobe/geo.py` (only the rotation check and what it needs), `discprobe/calibrate.py`,
`discprobe/web/home/guidance.mjs` (only `stopReason` and what it needs), `discprobe/web/home/calibrate.js` (only the
arguments `realCalibrate` passes to the `calibrate` job, around the line `realJob("calibrate", ...)`), and tests under
`tests/` (new files, or additions to `tests/test_web_guidance.mjs` and existing geo/calibrate pytest files).

## What went wrong (real runs, data in `results-real/`)

Two geometry runs on a real GH70N (`results-real/geo-H-20261111-200909`, `results-real/geo-H-20261111-201252`, with
their `timing-H-...-200908` / `-201251`) stopped half way with "a whole-turn count is probably wrong"; chi2/dof 32 and 51.
Cause: the spindle was not steady. geo's own `rotation_check` (see `summary.json`) measured 63.5 ms a turn at the inner
place and 21.18 ms at the outer: ratio 0.333. Constant angular speed gives 1; constant linear speed gives about the
radius ratio (`expected_clv`, ~2.1). 0.333 is neither: the drive changed speed while measuring (probably retrying a hard
band: the read-back after burning failed near 43.2 mm). `rotation_check` in `geo.py` (around line 215-235) only stops
when the ratio looks CLV, so this run went on through the whole ladder and failed late.
The second run also sent no SET CD SPEED (`set_cd_speed` null in its summary): the page passed no `--speed`.

## Do

1. `geo.py` rotation check: also stop at once when the ratio is neither CAV (|ratio - 1| > a named constant, start with
   0.05) nor CLV. Raise with a plain reason that starts with the fixed words `the drive's speed is not steady` and gives
   both periods and radii, e.g. "the drive's speed is not steady (63.50 ms a turn at 26 mm, 21.18 ms at 56 mm): it
   probably slowed down on a hard-to-read part of the disc". Keep the existing CLV message unchanged.
   Check how this error reaches `calibrate.py` (its `Stopped` reason / the event the web page gets) and make sure the
   page receives this sentence as the stop reason.
2. `calibrate.py`: a default read speed. When `--speed` is not given, use the same value the earlier run 200909 used
   (look in its `summary.json`: it sent SET CD SPEED 4x, status 0) in the format `timing`/`geo` take for `--speed`;
   log which speed is used. Add `--avoid-mm A-B` (repeatable): radius bands (mm) that `geo` must not place rungs in;
   pass them to geo (geo already takes LBA `ranges`; convert with geo's own radius/LBA model, or add an exclusion
   parameter). Document both in the parser help.
3. `guidance.mjs` `stopReason`: a case for `the drive's speed is not steady` with zh and en text that says what
   happened and what to do: "光驱转速不稳，多半是这张盘某一段难读，光驱在那里反复降速。页面会用固定的读速、避开那一段再测；
   还不行就换一个刻录速度另刻一张测量盘。" / an English equivalent. Add the zh/en pair to `tests/test_web_guidance.mjs`.
4. `calibrate.js` `realCalibrate`: always pass a fixed read speed (the same default as in 2, so the page and the CLI
   agree), and when `flow.burnCheck?.verification?.failures` has entries with `radius_mm`, pass `avoid_mm` bands of
   radius ± 2 mm (merge overlaps) the way the page passes other args (look at how `args`/`extra` become CLI options in
   `discprobe/webui.py`; if the server does not forward unknown args, add `speed`/`avoid_mm` there minimally and say so).
5. Tests: unit-test the rotation check with fake periods (CAV ok, CLV ok/stop as before, 0.333 stops with the new
   reason), the default speed, and the avoid-band conversion; a `--sim cav` calibrate run still succeeds.
   Run: `python -m pytest -q tests` (all must pass) and `node tests/test_web_guidance.mjs`, `node tests/test_geo_progress.mjs`,
   `node tests/test_burn_page.cjs`.

## Not now (report only, do not implement)

Whether `timing` should also check speed consistency: two timing runs measured 10.15 ms and 21.17 ms a turn on the same
disc and both were judged fine. Look at the code and write 3-5 lines on what such a check would compare.

## Done means

All tests pass; report the diff summary per file, the exact new reason sentence, the default speed chosen and why,
and the timing note.
