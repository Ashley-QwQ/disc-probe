# Task card: write the photo-read along-track constant into the preset

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches; no
servers, no drives, do NOT edit `discprobe/scsi.py`. Another Codex job is creating `discprobe/web/home/kit/` and
`tests/test_kit_*.mjs`: do not touch those. You MAY edit: `discprobe/disexport.py`, `discprobe/photo.py`,
`discprobe/calibrate.py`, `discprobe/webui.py`, `discprobe/webui_catalog.py`, `discprobe/web/home/calibrate.js` (the
photo step's save and the result stamp only), `discprobe/web/home/guidance.mjs` (words), and tests.

## Background (read before coding)

- `discprobe/disexport.py` already takes an along-track shift for CD (`--along-track-frames`, look how it is applied).
- The photo command (`discprobe/photo.py`, reader `discprobe/pcal.py`) returns `L_frames` (CD) in its result and writes
  `<run>/photo.json`. The page keeps it in `flow.photoResult` and shows it, but "the save path cannot write it into a
  preset yet" (see `calibrate.js`, search photoResult / realSave, and the save route in `webui.py`).
- Facts that must hold (from measurements on real discs; do not "simplify" them away):
  1. L belongs to the path: burner + burn mode + reading drive, and to THIS geometry run. It does not depend on the disc
     batch. It must never be applied to a preset made from another geo run or another drive.
  2. Each drive's mechanical offset is mixed into L, so a stored L is registered to the whole machine (drive model and
     the specific drive identity the page knows) plus the burn path, never to "this model in general".
  3. No usable L -> the program says it does not know. Never default to 0.
  4. On the DIS audio path with delayed interleave on, L is about -105 frames (verified on a real burn); our IMAPI
     Mode 2 Form 1 data path is about +206 (unverified guess). These are context, not defaults.
  5. pcal's verdicts: only "ok" may be written. "unsure"/"rejected" never reach a preset.

## Do

1. Saving a calibration whose photo step returned verdict ok and an `L_frames`: the preset written for DIS carries it
   (through the same mechanism `--along-track-frames` uses), and the preset's own metadata records where it came from:
   the geo run id, the photo run's `photo.json` path, the drive identity, the burn path/mode, the verdict, the photo ids.
2. If the photo result belongs to a different geo run or drive than the one being saved, refuse to write it (a clear
   reason) and save the preset without L, saying so on the page ("沿轨常数没写进去：照片对应的是另一次测量。").
3. CLI parity: whatever the page can do, `calibrate`/`disexport` can do (e.g. `disexport --photo <run>/photo.json` reads
   L and its provenance with the same checks). Document in the parser help.
4. The page: the result stamp after saving says which L was written (frames, and "来自照片，盘批次无关，换光驱要重拍")
   or that none was, and why. Words in zh and en.
5. Tests: unit tests for the provenance check (same run ok; other run refused; other drive refused; unsure/rejected
   refused; missing L -> no field, no 0), the preset round trip (write then read back the shift), the CLI path, and a
   node test for the stamp words. Run `python -m pytest -q tests` and all `node tests/*.mjs`, `node tests/*.cjs`.

## Done means

All tests pass. Report the preset field(s) used, the provenance record, the refusal cases, and anything about DIS's
preset format you were unsure of.
