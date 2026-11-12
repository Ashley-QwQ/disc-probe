# Task card: make variable-pitch DIS presets usable for DP images (angle correction)

Worktree: `D:/disc-probe/.claude/worktrees/dis-presets`, branch `core/dis-presets-20261112`. This continues
your previous card (`docs/codex-cards/dis-presets.md`); read `docs/dis-presets/REPORT.md` and `FORMAT.md` first.
The same boundaries apply:
- no commits, pushes, stashes, resets or branch switches;
- no drives; never touch port 8772;
- read-only for `D:/dis-study` and the real `%LOCALAPPDATA%/DiscImageStudio`;
- do not edit `scsi.py`, `pcal.py`, `geo.py`, `photo.py`.
Clean up your own temp folders at the end. If the sandbox refuses, list them.

## Why

Of the 134 community calibration records that carry pitch fields, 123 have nonzero pitch terms. Today an imported DIS
preset with nonzero pitch is archived but refused for DP image use. That leaves most real DIS users unable to move
over, which defeats the point.

Your own numbers say the difference between DIS's variable pitch and DP's thin-track base model is almost all angle:
- for `18-community-3.json`, the radius differs by 0.00006 mm while the unwrapped angle differs by 5°;
- the synthetic DVD/BD fixtures are extreme cases.

DP already has an angle correction phi(r): `imagedisc.load_correction`, a polynomial in degrees, held constant outside
its range, relative to a base u/v, applied in `_sample`. So a variable-pitch preset can be represented as DP base
geometry plus a phi(r) correction, with the radius residual reported.

## Do

1. **Convert on import** (CD and DVD; BD stays as it is, because DP has no BD image writer):
   - for each preset with nonzero pitch, choose the DP base (u, v) as you do now;
   - compute DIS's own sector → (r, theta) map per FORMAT.md, over the full data area;
   - fit phi(r) = theta_DIS − theta_DP(u, v) as a correction in the existing correction file format. Use a
     polynomial degree that fits within tolerance; prefer the lowest that does. Record the fit range;
   - the correction file is saved next to the imported DP preset and linked from it, so that choosing that preset
     anywhere (CLI `image`, the web page's preset choice for burning/preview) uses the correction automatically, the
     same way a geo-run correction is used. Find how the page picks geometry for image generation and make sure it
     follows the link. Add a test that proves it.
2. **Accept or refuse with numbers.** After correction, over 20,001 positions from sector 0 to capacity:
   - the max angle error must be ≤ 0.01°;
   - the max radius error (DIS r minus DP r at the same sector, which the angle correction cannot change) must be
     ≤ 0.005 mm.

   Both numbers go in the preset's `source` and in the import listing ("近似：角度 ≤ x°，半径 ≤ y mm"). Above either
   limit: archive only, as now, with both numbers and the reason. Never take angles modulo 360 to hide an error.
3. **Status words stay honest:**
   - a converted preset is "从 DIS 导入，换算成 DP 修正（未经 DP 实测）";
   - a CD still has L unknown;
   - DIS nominal presets stay nominal.
4. **Export back to DIS:**
   - an imported preset still exports its original DIS fields unchanged (exact round trip);
   - the correction is DP-side only and never written into DIS.
5. **Report** in `docs/dis-presets/REPORT.md` (a new section):
   - for every fixture and for all 174 community records that have complete parameters: accepted/refused, the max angle
     and radius errors after correction, and the polynomial degree;
   - summary counts: how many of the 123 nonzero-pitch community presets are now usable.
   - Also update `angle-audit.json` via `tools/analyze_dis_presets.py`.

## Tests

- conversion within tolerance for real community examples;
- refusal above tolerance with both numbers;
- the correction is used automatically by `image` and by the page's geometry choice;
- export round trip unchanged;
- no modulo hiding (a fixture whose true error is above 360° must be refused);
- CLI `--json` carries the numbers.

Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`. All must pass.

## Done means

Tests pass, and the REPORT section is written with the counts. Report what changed and anything left.
