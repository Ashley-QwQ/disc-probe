# Task card: fix four disc-probe faults found by Disc Lab, and prove each fix with the same fault

Worktree: `D:/disc-probe/.claude/worktrees/fault-fixes`, branch `core/fault-fixes-20261114` (from `web/main-path-fixes-20261113` fc197be, the alpha main path).
The user has agreed these are fixed before the 1.0.0.0-alpha (Sunday 23:59).

## Hard rules (keep unchanged)
- Do NOT commit, push, stash, reset or switch branches.
- Do not edit `discprobe/scsi.py` or its command allowlist; `discprobe/pcal.py`; `discprobe/photo.py`; `evidence/atlas/*.py` (a search is running from those). Do not touch `docs/goals/calib-simple/`, `docs/goals/rgbcard/`, `art/photomask/`.
- No real drives, no real burns, no network. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- **Disk: every temporary file, lab, ISO, cache and output on D:.** Set `TMP`/`TEMP` to `D:/disc-probe-scratch-tmp/fault-fixes/tmp` and pytest `--basetemp=D:/disc-probe-scratch-tmp/fault-fixes/pytest`. C: was full twice tonight. Use small ISOs (a few thousand sectors).
- At most 4 CPU-heavy processes. Do not use any word starting with "blin" in commands or paths (a hook blocks it).
- Good discs and good burns must behave exactly as before (same outputs, same exit codes); only the faulty cases change. Do not relax any existing gate.

## The four problems (from Disc Lab's fault scoring, `D:/disc-probe/.claude/worktrees/disclab-faults/disclab/FAULTS_REPORT.md`)
1. **Burn read-back failures still report "completed".** With read-back, 96 of 96 sampled blocks unreadable (read_error) or 58 unreadable (burn_interrupt) → `burn_result` still `completed`, exit 0. Required: any unreadable or differing sampled block makes the burn result say so explicitly (e.g. `result: "completed_with_readback_errors"` or `"failed_verification"` — choose, document, keep the event schema backward compatible for the web: keep `result` values the web understands or update the web too), and a non-zero exit code. Update the web burn page (`discprobe/web/home/burn.js`, `design.js` realBurn, `calibrate.js` burnCheck) so it shows that the burn did not check out and does not offer "Photograph the disc" / the next step as if all were well. Keep `verified` semantics.
2. **Burn stopped part-way but the recorder reported success.** With `--no-verify`, a 1638-of-4096-sector, unclosed disc is reported `completed`, no warning. Required: after any burn (verify or not), read the disc's state back (READ DISC INFORMATION / track information through the existing allowed commands): disc or session closed when it should be, recorded length ≥ the ISO's sectors. A mismatch fails the burn with a plain reason ("the drive said it finished, but the disc holds only N of M sectors / is not closed"), non-zero exit, web shows it.
3. **The drive's reported capacity is believed blindly.** `info` reports the drive's READ CAPACITY / DISC INFORMATION as is; `timing` saves a wrong readable length. Required: cross-check READ CAPACITY, track information (track size / last recorded address), DISC INFORMATION (free blocks, disc status) and, where cheap, one read at the reported end; when they disagree, say so in `info` (a warning line and a field in info.json), and in `timing` / `geo` refuse to use an unverified length silently (warn and use the conservative, confirmed value, or stop with the reason). Do not add drive commands outside the existing allowlist.
4. **`geo` gives the wrong reason.** With a misreported capacity it stops with "no random data found in the recorded area". Required: when the capacity checks of (3) disagree, `geo` names that as the reason (and the next step), not "no random data".

## Proving each fix with Disc Lab
Disc Lab's fault scorer lives on branch `dev/disclab-faults-20261113` (worktree `D:/disc-probe/.claude/worktrees/disclab-faults`, read-only for you). To run it against THIS worktree's `discprobe`: make a folder on D: (e.g. `D:/disc-probe-scratch-tmp/fault-fixes/lab-root/`) holding a copy of that worktree's `disclab/` and a junction `discprobe` → this worktree's `discprobe/` (`cmd /c mklink /J`), run `python -m disclab ...` from that folder (see `disclab/SCENARIO.md` and the example scenarios in `disclab/examples/scenarios/`). First run the four example scenarios against the UNCHANGED code (baseline, should reproduce the report's table), then after the fixes. The report's before/after table must come from these runs; a fault still `silent_wrong` or `crash` after your change is reported as such, not hidden.

## Tests
Unit tests for each fix on the existing fakes (`tests/test_fail_exits.py`, burner tests, info tests), including that good burns/discs are unchanged; then `python -m pytest -q` for the whole repository and the web tests touched (`node tests/test_burn_page.cjs` and any other burn/calibrate test).

## Acceptance
- Full pytest passes (report counts); touched Node tests pass.
- `docs/goals/fault-fixes/REPORT.md` (Chinese, plain words first): per problem what changed, the Disc Lab before/after table, what is still not covered.
