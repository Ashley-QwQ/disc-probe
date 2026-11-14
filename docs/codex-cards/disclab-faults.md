# Task card: Disc Lab scenarios, fault injection and fault scoring

Worktree: `D:/disc-probe/.claude/worktrees/disclab-faults`, branch `dev/disclab-faults-20261113` (from Disc Lab 2ec80ce).
Another Codex works in parallel on a TUI, a practice command and `--json` output in a sibling branch; it owns new files `disclab/tui.py`, `disclab/practice.py`, `disclab/jsonout.py`. **Do not create those files.** You both add subcommands to `disclab/__main__.py`: keep your edits there small and self-contained (one block registering your subcommands) so the merge is easy.

## Hard rules (keep unchanged)
- Do NOT commit, push, stash, reset or switch branches.
- Do not edit anything under `discprobe/` (Disc Lab tests disc-probe; it must not change it). The SCSI allowlist (`discprobe/scsi.py` `check_allowed`) stays the only gate every virtual command goes through.
- No real drives, no burns, no network. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- At most 4 CPU-heavy processes. Do not use any word starting with "blin" in commands or paths (a hook blocks it).
- Existing behaviour, truth model, scores and all 30 tests stay as they are. Default boxes (no scenario) must produce byte-identical `answers.json` to today for the same seed.

## Why
The user wants Disc Lab to check disc-probe's accuracy and robustness: set every part of the virtual drive and disc, inject faults on purpose, and see whether disc-probe recognises each one and reports it correctly, with a truth record and a score per fault. Command line first; everything also reachable as structured data for a future web shell.

## What to do
1. **Scenario file** `scenario.json` (document its schema in `disclab/SCENARIO.md`, Chinese and English), used by `disclab box --scenario FILE` (CLI flags still work and override nothing silently: refuse conflicting values with one sentence):
   - discs: media (dvd-r, dvd+r, cd-r, bd-r), count, seed, batch/stampers, MID string, capacity, parameter overrides (u, v, bit length, start radius, eccentricity, warp), defect arcs, **initial state** per disc: `blank`, `burned` (with which ISO or random), `open` (burned, session not closed), `partial` (burn stopped at a fraction).
   - drive/burner: profile (existing `gh70n`, `slim-clv`, `nofua`, `noisy`) plus overrides (vendor/product/firmware strings, CAV/CLV, jitter, outlier rate, write speeds, completion offset, head offset), and burn-failure behaviour (`none`, `stop_at` fraction, `fail_close`).
   - faults: a list, each `{kind, params, id}`.
   Truth for all of it goes to `answers.json` (never visible to disc-probe), as today.
2. **Four faults**, each implemented in the virtual drive / recorder:
   - `read_error`: an LBA range (or radius band) answers READ with a medium error (sense 3/11/00);
   - `spindle_unsteady`: rotation period drifts or jumps (amplitude, rate, at which time or LBA);
   - `capacity_misreport`: READ CAPACITY / READ DISC INFORMATION / track info report a wrong sector count (offset or fixed value);
   - `burn_interrupt`: the recorder stops writing at a fraction and reports failure (or, a variant, reports success but the disc only holds that fraction).
3. **Fault scoring** `disclab faults --lab LAB [--fault ID]`: for each fault, run the disc-probe commands that should notice it (`info`, `timing`, `geo`, `burn` as appropriate, through the existing `dp` path), and classify each run as
   - `detected`: disc-probe stopped or warned and its reason names the problem (match on its failure.json / summary / stderr, with the expected wording or code listed per fault),
   - `silent_wrong`: it finished and its result is wrong against the truth (e.g. geo with a wrong capacity, a burn marked complete that is not),
   - `unaffected`: the fault did not matter for that command and the result is right,
   - `crash`: a Python traceback or an unexplained non-zero exit.
   Write `LAB/scores/faults.json` (machine-readable: fault, command, expected, observed, class, evidence paths) and print a table. Exit code 0 even when disc-probe misbehaves (the score is the product); non-zero only if Disc Lab itself failed.
4. Ship example scenarios in `disclab/examples/scenarios/`: one per fault, plus `all-faults.json`. Run them all on this machine and include the table in your report — whatever disc-probe does, report it honestly; a `silent_wrong` is a finding about disc-probe, not something to hide or "fix" by changing disc-probe.
5. Tests: scenario parsing and refusal of conflicts; default-box byte identity; each fault's virtual-drive behaviour; the classifier on synthetic outcomes; one end-to-end small scenario.

## Acceptance
- `python -m pytest disclab/tests -q` all pass (report counts).
- The faults table for the example scenarios, in `disclab/FAULTS_REPORT.md` (Chinese, plain words first): per fault what disc-probe did, and what is not modelled yet.
