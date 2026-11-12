# Task card: put the UI kit into the pages

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, stash, reset or switch branches; no
long-running servers, no drives, do NOT edit `discprobe/scsi.py`. Nobody else is editing now; still, touch only what this
card needs. The kit: `discprobe/web/home/kit/` (read `kit/README.md` and `kit-preview.html` first).

## Where each piece goes

1. Rolling numbers (`flipnum.js`). Add to the kit a `flipWatch(el)` helper that rolls whenever code elsewhere sets the
   element's text (so callers keep assigning `textContent`; use a MutationObserver and guard against feedback loops).
   Use it for: the calibration stage's big percent and its time line (`calstage.js`, `.cs-big b` / `span`), the footer job
   bar's time (`#job-time`), the library's counter (`#idx` / `#total` in `index.html`), and the disc check's 5 s countdown.
2. Status bars (`statusbars.js`) on the library's batch details (the right-hand information of a disc batch in
   `index.html`): one bar per calibration and per burn of that batch, newest on the right, ink = good, copper = needs the
   person (a stopped/failed run, a read-back with bad blocks), faint = unknown. Data: what the server already knows about
   runs (`discprobe/webui_catalog.py`, results folders); add a small `history` list to the catalogue entry if it is not
   there (each item `{kind: "calibrate"|"burn", state, when, label}`), computed from saved results only, never invented.
   Hidden when a batch has no history.
3. Connected devices (`devices.js`) on the photo calibration page (`photocal.js`, the paper's phone block): the phones
   that used this run's token (`discprobe/photo.py` / `webui.py`: record per token use the device's user-agent summary,
   first/last seen, photos sent; add `GET /api/phone-devices?run=...` and `POST /api/phone-devices/<id>/disconnect` which
   revokes that device's access, i.e. issues a new token for the run and invalidates the old one). Poll with the photo
   list. "This computer" is not listed as disconnectable.
4. Slide to confirm (`slideconfirm.js`) for the two irreversible burns, in place of "hold for 1 s": the calibration
   page's measurement-disc burn (`calibrate.js` holdButton use for the burn step) and the burn page's burn button
   (`burn.js`). Keep the existing consent checks before it (the burn page's tick box stays); keyboard: as the kit does.
   The Next button area shows the slider in place of the button while that step is current; everything else keeps the
   normal Next button.
5. Progress button (`ringbutton.js`) for "make the measurement image" (calibration `random` job) and the preview page's
   "下一步：生成并去刻录" (`preview.js`): the ring fills with the job's progress (indeterminate when none).

## Rules

- The site's look: ink/copper, glass shadows, no new colours; motion off = no rolling, no ring turning.
- No dead ends: if a route answers 404 (old server), the piece hides; nothing pretends.
- Words zh first with en.
- Tests: extend the existing node tests where they cover those pages (`tests/test_burn_page.cjs`,
  `tests/test_photo_wire*.mjs`, `tests/test_geo_progress.mjs`) and add pytest for `history` and the device routes.
  Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`; all must pass.

## Done means

Tests pass; report each placement, what data the status bars use, how disconnect revokes access, and anything left out.
