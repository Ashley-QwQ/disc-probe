# Task: build and verify the 1.0.0-alpha packages for Windows and Linux (alpha A9), as a rehearsal

Worktree `D:/disc-probe/.claude/worktrees/release-pack`, branch `core/release-pack-20261112`, base `3938acf` (the 1.0.0 alpha integration branch; selftest is all-pass there). Commit here only, house style (`area: plain sentence`, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`). Never push, never create a tag or a GitHub release. The real build happens from the frozen commit around 2026-11-20; this job makes that a one-command step with no surprises. Read `D:/disc-probe/docs/goals/alpha-value/TODO_ALPHA.md` A9 and `GUI_HANDSHAKE_REPORT.md` in the base first.

## Do

1. **One release command**, e.g. `python tools/release.py --version 1.0.0-alpha --out DIR`, that:
   - sets the version in its single place (`discprobe/version.py`) **only inside the build copy**, not in the tree;
   - runs pytest, Node and selftest and keeps their logs;
   - builds every asset;
   - writes `SHA256SUMS.txt` and a manifest: commit, versions, dependency versions, file sizes.
   
   It refuses to build from a dirty tree, or with any failing check.
2. **Windows:**
   - the full win64 ZIP (`tools/build_winpack.py`: embedded Python with NumPy, Pillow, SciPy, OpenCV, the web GUI, fonts, templates, photo assets);
   - the core/source package (the pip wheel and sdist from the handshake work).
   
   The full pack's launcher must open the web lobby, not leave the person at a CLI prompt. Check a double-click start, and the "no drive" path.
3. **Linux:** a source tar.gz plus the wheel, and a short `INSTALL-linux.md`:
   - Python version;
   - `pipx install` / venv steps;
   - which external burning tools are needed for which media (`growisofs`, `dvd+rw-mediainfo`, `cdrdao`/`wodim`);
   - permissions for `/dev/sr*` (the `cdrom` group).
   
   Do not call it self-contained.
4. **Verify from the packages, not the tree:**
   - Windows: unpack into a path with Chinese characters and spaces under `C:/disc-probe-scratch/release-pack/`. Start the web server from the pack, fetch `/api/version`, the lobby and one design-page asset, run `selftest` from the pack, and run the photo reader on one saved real photo, to prove OpenCV and SciPy import inside the pack.
   - Linux: on `ssh x79` (Linux, Python 3.12, no system pip; a venv at `~/dp-venv` exists, but make a fresh venv for this) or `ssh agentbox`, install the wheel offline (copy the dependency wheels over; no internet assumed). Run `disc-probe --help`, `version --json`, start the web server bound to localhost briefly, fetch `/api/version` and the lobby, and run selftest. No drive access on those machines.
   - Record each platform, commit, dependency set and hash in `C:/disc-probe-scratch/release-pack/verify.json`.
5. **Fix packaging blockers you find**, in packaging code only: missing package data, launcher, path handling, version plumbing. Anything that needs a product change, list instead.

## Deliver

`RELEASE_PACK_REPORT.md` in plain Chinese:
- the command;
- the assets with sizes and SHA-256;
- what was verified where;
- blockers left;
- the exact steps for release day.

## Limits

No network except ssh to x79/agentbox and copying files to them. Do not publish anything. No drive access. Those machines run atlas search workers (`evidence.atlas.budget_worker` / `refine_dispatch`): do not kill or slow them; use at most 2 cores there and put files under `~/dp-release-check/`. Do not change product code beyond packaging. At most 2 heavy local processes.

## Rule

No file path or command you run may contain the five letters b,l,i,n,d written together. When searching, exclude them:
- grep: `--exclude-dir='*<that word>*' --exclude='*<that word>*'`
- find: `-iname '*<that word>*' -prune -o`
