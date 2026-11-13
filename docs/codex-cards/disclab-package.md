# Task card: make Disc Lab a package people can download and use on its own

Worktree: `D:/disc-probe/.claude/worktrees/disclab`, branch `dev/disclab-20261113` (commit 1f8b956).
It ships in the 1.0.0.0-alpha release as its own asset `disc-lab-1.0.0.0-alpha.zip`, next to disc-probe (which it imports).

## Hard rules (keep unchanged)
- Do NOT commit, push, stash, reset or switch branches.
- Do not edit anything under `discprobe/`. Only `disclab/`, a new top-level `disclab/README*.md` / `examples` inside `disclab/`, and this card's report.
- No drives, no burns, no network, no servers except the existing disclab tests' own. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- At most 4 CPU-heavy processes. Do not use any word starting with "blin" in commands or paths (a hook blocks it).
- Keep every existing disclab behaviour and its 20 tests passing; keep the truth model and scores unchanged.

## What to do
1. Remove machine-specific paths:
   - `disclab/loop.py`: `SCRATCH_ISO = Path("C:/disc-probe-scratch/disclab/iso")` → ISOs go under the lab directory (e.g. `LAB/iso/`), or a `--work DIR` option; keep deleting big ISOs after use.
   - `disclab/tables.py`: the A3 path `D:/disc-probe/docs/goals/...` is only for rebuilding `data/wave_xyz.npz`; make it an explicit argument of that rebuild step, never needed at run time.
   - Grep for any other absolute path, user name or machine name and remove it.
2. Make it work from an unpacked zip: `python -m disclab ...` from the folder that holds `disclab/`, with disc-probe either installed (`pip install disc_probe-*.whl`) or as the `discprobe/` of the Windows full package. `sitecustomize` boot must find the right `discprobe` in both cases; refuse with a plain sentence when disc-probe is missing or its version differs (`discprobe.version.__version__`; accept the same major.minor.patch.build, ignore pre-release tags only if they match exactly — keep it simple: require equality and say so).
3. Documentation, two languages: `disclab/README.md` (English) and `disclab/README.zh.md` (Chinese, plain words first):
   - what it is (a virtual drive, a box of made-up discs with hidden truth, rendered phone photos, scoring against the truth) and who it is for;
   - install (two ways above), a five-minute example (`box` → `loop geo` → score), the photo loop, the web hookup, `upload`;
   - how scoring works, what each number means;
   - the truth model table: measured / assumed (keep the current table, translated);
   - limits: the photo renderer knows only A5, B9 and random data textures (multi-byte textures such as the `checkdisc` target render blank), CD and BD only measure geometry, Windows and Linux tested as far as actually tested (say exactly which).
4. `disclab/examples/`: a 12-disc DVD-R box config, `run-example.ps1` and `run-example.sh` that run the five-minute example end to end into a fresh lab folder and print the scores.
5. Tests: keep the 20; add one that runs the five-minute example on a tiny box (2 discs, few reads) and checks the score file exists and is sane, and one that checks no absolute machine paths remain in `disclab/` (excluding tests' own temp paths).

## Acceptance
- `python -m pytest disclab/tests -q` all pass; report counts.
- The example scripts run on this machine (Windows PowerShell) into a fresh folder; report wall time and the printed scores.
- A short report at `disclab/PACKAGE_REPORT.md` (Chinese): what changed, what is verified, what is not (Linux not run here unless you actually ran it).
