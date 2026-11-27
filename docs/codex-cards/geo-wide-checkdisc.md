# Task card: geo measures (nearly) the whole disc, and a core command writes the photo check disc

Worktree: `D:/disc-probe/.claude/worktrees/main-path`, branch `web/main-path-fixes-20261113`.
Another agent edits `discprobe/web/home/*.js` and `tests/*.mjs` in this worktree at the same time: **do not touch any file under `discprobe/web/`** and no `.mjs` test.

## Hard rules (keep unchanged)
- Do NOT commit, push, stash, reset or switch branches.
- No drives, no burns, no network, no servers. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- Do not edit `discprobe/scsi.py`, `discprobe/pcal.py`, `discprobe/photo.py`, `discprobe/coverage.py`, `discprobe/imagedisc.py`, `discprobe/calib.py`.
- `docs/goals/calib-simple/` is read-only: read files there, never write, move or regenerate anything in it.
- At most 4 CPU-heavy processes at once. Do not use any word starting with "blin" in commands or paths (a hook blocks it).
- Existing behaviour that must stay byte-identical: CD-DA (audio) geo ranges, BD geo, `image` output for a given geo and design, `rings`, `random`.

## Why
The 1.0.0.0-alpha main path is: measure the batch (geo) → design → burn a **check disc** → phone photos → along-track L → burn the picture with L applied.
Two gaps, found by a walkthrough on a real RITEKF1 measurement:
1. `geo` only samples LBA 3 %–85 % of the recorded area (`Ladder.run`, `self.ranges = [(int(last * 0.03), int(last * 0.85))]`, unchanged since the first commit, no recorded reason). On RITEKF1 that measured 25.72–54.05 mm, and the `image` coverage gate (rightly) refuses any picture outside the measured intervals. The timing check already reads at 3 %, 25 % and 97 % of the disc routinely (`for f in (0.03, 0.25, 0.97)`).
2. The phone photo reader (`pcal.design_burn()`) reads a specific target disc. No core command writes it. The only target ever burned and read from real photos (PCAL-C 4-02, 6 of 11 user photos read ok) was built by research scripts: `docs/goals/calib-simple/artifacts.py` (target_B) and `round2.py` (`artifacts()` adds RND bands; `iso()` writes the ISO). Its design array is `docs/goals/calib-simple/target_round2.npy`, sha256 `052d1835137d0b9173251d14ea44212b85acef2e8eb7c3970957114991565be7`; textures and constants are in `layout_round2.json`; `RANDOM = [(24.6, 26.0), (57.85, 58.198)]`.

## What to do

### A. geo: measure from 1 % to 98 % on data discs
- In `Ladder.run`, the default (no `--ranges`, not audio) becomes `[(int(last * 0.01), int(last * 0.98))]` for DVD and CD data discs. Leave the CD-DA branch (`CD_AUDIO_RANGE`) and Blu-ray behaviour exactly as they are (check how BD reaches this line; if BD shares it, keep 0.03/0.85 for BD).
- `_random_parts`, `safe_ranges` (random label) and the completion logic must still apply on top.
- Update any test or selftest whose expectation depends on 0.85 only where it measures the default range; explain each change in the report. On the simulated drive, show the new measured intervals for a DVD and a CD data run, and that the fit quality (chi2/dof, angle sigma) did not get worse; show the run time change.

### B. `checkdisc`: the PCAL-C target as a core command (DVD only for now)
- New module `discprobe/checkdisc.py` and subcommand `python -m discprobe checkdisc --geo <geo run or summary.json> [--output iso/check-<stamp>.iso] [--sectors N]`, DVD only (refuse CD/BD with a plain sentence).
- Rebuild the round-2 label array **exactly**: features from a small packaged asset (e.g. `discprobe/data/check_target_features.png`, 1-bit, made once from `docs/goals/calib-simple/features.npy`, which is the boolean feature map), then the same rules as `artifacts.py` + `round2.py` (equal-area cell hash with seed 20261111 over the 8 bright textures, polarity B so features are label 0, bright rim 57.1–57.7 mm, label 9 = RND outside 24.6–58 mm and in the two RANDOM bands). A test must assert the rebuilt array's sha256 equals `052d1835…65be7` (skip with a clear reason only if the calib-simple file is absent, e.g. in an installed copy; the hash constant itself must be checked whenever the asset is present). Keep the asset small (report its size).
- Textures: exactly `layout_round2.json`'s list, copied into the module as a constant with a comment that they were chosen for RITEKF1 DVD-R and are unverified on other batches.
- Geometry: u, v and bit from the geo fit **without** photo L (this disc is what measures L). Total sectors: `--sectors`, else the geo run's `setup.last_lba + 1`; refuse if unknown.
- Coverage: before writing, check the radii the reader depends on — the dark features 26.2–57.0 mm — with `coverage.range_warning(fit, [26.2, 57.0])`; if it warns, refuse with a plain sentence (re-measure this batch with the new geo; no new burn). The bright rim and the RND bands may lie outside the measured interval.
- Write with `imagedisc.write_iso(..., textures=..., lead_lba=0, meta=dict(check_disc=True, design='pcal round2', geometry_from=..., experimental=True))`, then `imagedisc.verify_iso(..., samples=300)` like `round2.iso()`; exit non-zero on a verify failure. The sidecar must record `check_disc: true` and the geo path.
- Print the usual "Burn it" steps (`guide.burn_steps`) and a line: after burning, photograph it from the page (or `photo --run <geo run> --disc-id <code>`).
- Register it in the `webui.py` `ACTIONS` set and `OPTIONS` (`geo`, `output`, `sectors`, plus `work`/`disc_code` like `image` if that is how the work link is done), not a drive action.
- Tests: label-array hash, refusal on CD/BD, refusal when the fit's measured interval does not cover 26.2–57.0 mm, a small end-to-end write on a synthetic fit with a small `--sectors` if feasible (or the existing write_iso test pattern), and the webui option whitelist.

## Acceptance
- `python -m pytest -q` all pass (report counts; the previous full run on this branch was 738 passed, 1 skipped).
- `python -B -m discprobe selftest` no new failures.
- A report at `docs/goals/checkdisc/REPORT.md` (Chinese, plain words first): what changed, the sim-drive numbers before/after for geo, asset size, the hash match, what is NOT verified (real geo run to 98 %, real burn and photos of the check disc made by the new command).
