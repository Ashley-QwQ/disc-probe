# Task card: the photo pipeline in the core (upload, phone page, QR, the pcal reader as a command)

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches. Do NOT
touch any drive, do NOT start long-running servers (short test servers inside pytest are fine), do NOT edit
`discprobe/scsi.py`. Another Codex job is editing `discprobe/web/home/calibrate.js`, `discprobe/web/home/index.html` and
`discprobe/web/home/photocal*` right now: do NOT touch those.
Files you MAY edit/create: `discprobe/webui.py` (new routes only, minimal), `discprobe/__main__.py` (register the new
command only), new `discprobe/pcal.py`, new `discprobe/photo.py` (the command), new `discprobe/web/phone/` (the phone
page), new `discprobe/qr.py` if you write a QR encoder, and new tests under `tests/`.

## Read first, all of it (the reader is research code with hard-won rules)

- `D:/disc-probe/docs/goals/photo-calibration/design.md` (what the target is, what the reader may and may not do)
- `D:/disc-probe/docs/goals/photo-calibration/6pro_fine_calibration_report.md` (the audit: coverage gates, why L belongs
  to "path + this geo run", the 0.2 mm centre-offset trap)
- `D:/disc-probe/docs/goals/photo-calibration/pcal.py` and `pcal_frozen_d6375fae.py` (the version that passed the sealed
  blind test, sha d6375faed8fe489e), `inject_test.py`, `inject_votes.py`, `make_target.py`
- `D:/disc-probe/docs/goals/photo-calibration/sealed/` (the blind test: 12 phone photos, read -2.098 mm vs +2.291 injected
  ... read its notes for what passed and what was rejected)
Those files are outside the repo: read them, copy what you need INTO the repo. Keep the frozen reader's logic and its
refusal rules unchanged (it says "unsure" rather than guess; coverage counts only trusted votes; photos whose geometry is
rejected are not used in the joint verdict). If you must change anything, say exactly what and why in your report.

## Build (to the contract in `docs/codex-cards/photo-contract.md`, exactly)

1. `discprobe/pcal.py`: the frozen reader as a library (functions, no CLI side effects), plus the `photo` command in
   `discprobe/photo.py` (`python -m discprobe photo --run <dir> --media cd|dvd --photos a.jpg b.jpg ... [--rings-mm ...]`)
   that reads the run's geo result if the reader needs it, prints progress/log events the way other commands do
   (`ui.event`), writes its result JSON into the run folder, and exits 0 with verdict ok/unsure/rejected (non-zero only on
   a crash). Register it in `__main__.py` and in the web job runner so `/api/run` can start action "photo".
2. Upload + listing + serving routes, the phone link (LAN IP discovery like the existing LAN mode code; token per run),
   the phone page under `discprobe/web/phone/` (small, plain HTML/CSS/JS, the site's paper look: `--paper` `#ebe7e0`,
   ink `#1d1b18`, copper `#a8693c` only for the shutter ring; zh first with en; it says photos stay on the home network).
3. QR: an SVG generator without new packages (a small QR encoder module, byte mode, ECC level M is enough for a URL;
   test it by decoding with a reference implementation if one is installed, else test against known vectors).
4. Tests: upload/list/serve round trip with a temp results folder, token auth (wrong token refused, other run refused),
   size limit (reuse the server's existing body limit), the photo command on the sealed blind-test photos if they are
   readable from the test (skip with a clear reason otherwise) checking it reproduces the recorded verdict and value
   within the recorded tolerance, and an "unsure" case on a non-disc image. `python -m pytest -q tests` must pass.

## Done means

All tests pass. Report: files, the routes, how the phone token works, how pcal was carried over (unchanged or what
changed), the blind-test reproduction result, and anything in the contract you could not meet.
