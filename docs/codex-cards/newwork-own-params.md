# Task card: bring your own disc parameters from the new-work page

Worktree: `D:/disc-probe/.claude/worktrees/review-fixes`, branch `web/review-fixes-20261112`.
- Do NOT commit, push, stash, reset or switch branches.
- No drives. A webui serves this worktree on port 8813 for the person: do not stop or restart it, and don't start
  other servers outside tests.
- Edit only `discprobe/web/home/newplan.js`, `newplan.css`, `presetio.js`, `presetio.css`, `discprobe/webui_catalog.py`
  (the preset row's status only) and tests.
- Clean up your temp files.

## The problem (the person's words, paraphrased)

Someone who already has numbers for their discs (a DIS preset, or the radii and sector count) has to leave the
new-work page, go to the lobby, open import/export, come back. There is no way to type the parameters in. Also some
people will only use our editor and take the result to DIS; they must never be forced to calibrate. Next is already
"下一步：放进图片" again; calibration is a link, not a gate. Keep it that way.

## What exists (read first)
- `newplan.js`:
  - the batch select is `fillBatches`, `chosen`, `calibrated`, `needsCalibration`, `calibrationNotice`;
  - the kind choice is the answer-sheet radios `.np-choice`;
  - the `.np-library` link opens the library and comes back.
- `presetio.js`: the import/export desk.
  - `open(from)` is exported; the lever is down for import.
  - The import paper previews and imports a DIS JSON through `/api/presets` (`operation: 'preview'` / `'import'`,
    `text`, `filename`, `media`).
- `webui_catalog.py` lists imported presets as catalogue rows. Each row has `imported`, `image_compatible`,
  `correction_required`, `import_status`, `geo`, and `s='unknown'`.
- `design/export-rules.mjs` `geoChoice` already uses an imported, image-compatible preset as the plan's geometry.

## Do
1. **Imported presets are a state of their own, not "uncalibrated".**
   - Give an imported, image-compatible preset row its own status, e.g. `s='imported'`. Check every place that reads
     `s` (the library page, newplan's `calibrated`, the design header, guidance) so the status means "has geometry
     from DIS, not measured by DP".
   - On the new-work paper it reads: "参数来自 DIS（未经 DP 实测）/ Parameters from DIS (not measured by DP)". The
     calibration notice does not nag.
   - A CD still says its along-track constant is unknown.
   - A preset DP cannot draw with stays archive-only: say that, and don't offer it as usable geometry.
2. **On the new-work paper, under the batch select:** a quiet line "已经有这批盘的参数？ 从 DIS 导入 · 手动填写" (en
   "Already have this batch's numbers? Import from DIS · Type them in"), the same link style as "去盘库看这批盘".
   - **"从 DIS 导入"** opens the presets desk with the lever already down (import), from this page. Add an option to
     `open()`, e.g. `open(from, {state: 1, onImported})`.
     - After a successful import, closing (上一步 / Esc) returns to the new-work page as it was.
     - The imported preset of the current kind is selected in the batch select.
     - If several were imported, select the first of this kind.
   - **"手动填写"** opens a small form on the import paper of the same desk (a third block below the file pick,
     "手动填写参数 / Type the parameters"). The fields are exactly DIS's:
     - name;
     - media (CD / DVD, defaulting to the new-work page's current kind);
     - inner radius (mm), outer radius (mm);
     - sector count;
     - pitch linear / quadratic / cubic (optional, default 0).
     The form builds a single DIS preset JSON (the same shape DIS saves; see `docs/dis-presets/FORMAT.md`) and sends it
     through the existing preview → import path, so the same checks and messages apply. Show the preview row before
     importing. Bad input is refused with the core's reason, next to the field when possible.
3. **Copy** zh first with en, in the page's words. No new colours. Motion off → instant.

## Tests

Extend `tests/test_review_library_newwork.mjs` and `tests/test_presetio_browser.mjs` (mock API):
- the link opens the desk in import state;
- importing returns to new work with the preset selected and the "参数来自 DIS" status;
- manual entry builds the expected JSON and goes through preview and import;
- an archive-only preset is not offered as geometry;
- Next stays "下一步：放进图片" and goes to drawing even when uncalibrated.

Add a pytest for the catalogue status. Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`
(`tests/editor_runner.mjs` is a helper that needs arguments; skip it). All must pass.

Save screenshots at 1440×900 to `.impeccable/own-params/`: the new-work link, the manual form, and the return with the
imported batch selected.

## Done means
Tests pass. Report what changed (file:line), the status value chosen and every place it is read.
