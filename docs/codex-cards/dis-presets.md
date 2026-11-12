# Task card: one-click DiscImageStudio preset import and DP preset export

Worktree: `D:/disc-probe/.claude/worktrees/dis-presets`, branch `core/dis-presets-20261112` (from 476e1ff).
- Do NOT commit, push, stash, reset or switch branches.
- No drives. Do not start or stop servers outside tests (a user's server runs on port 8772: never touch it).
- Do NOT edit `discprobe/scsi.py`, `pcal.py`, `geo.py`, `photo.py`.
- Never write to the real `%LOCALAPPDATA%/DiscImageStudio/`: tests and examples use temp folders. The real file may
  be READ (read only) for the analysis.
- `D:/dis-study/DiscImageStudio` is read only: no checkout and no branch switch there. Read other refs with
  `git -C D:/dis-study/DiscImageStudio show <ref>:<path>` and `git log`/`git diff <a> <b> -- <path>`.

Another job is editing the web page in another worktree (`webui.py`, `photo.py`, `calibrate.js`, `photocal.js`,
`web/phone/`). To keep the merge small:
- web code goes in NEW files (`discprobe/web/home/presetio.js` + `presetio.css`);
- only a few lines in an existing page to open it (the library / presets place, see below);
- server routes in `webui.py` are new routes in one block, not edits spread through the file.

## Why (the person's words)

For the 1.0.0 alpha (2026-11-22): cut the cost of moving from DiscImageStudio (DIS) to disc-probe (DP).
- Import: one click to bring DIS presets into DP.
- Export: one click to write a DP preset back into DIS's format.
- Core-full-featured: the CLI must do everything the page does.
- Reuse the existing `disexport` / `disexport --install` code rather than duplicating it.

## 1. Analyse how DIS stores presets (write `docs/dis-presets/FORMAT.md`)

Sources:
- `src/DiscImageStudio.Core/Presets/built-in-disc-presets.json` (schemaVersion 4: `cdPresets`, `dvdPresets`,
  `bluRayPresets`, ... look at all of them) and the C# that loads, validates, migrates and saves presets
  (search `Presets/`, `schemaVersion`, `disc-presets.json`);
- the user file: `%LOCALAPPDATA%/DiscImageStudio/disc-presets.json` (read only), and a backup copy at
  `D:/disc-probe/docs/goals/perf/dis-appdata-backup/disc-presets.json`;
- project files and calibration records: do they carry geometry or a preset copy?
- version differences: tag v1.5.0 (29b8cc1) vs main 619ec75, plus anything relevant in local `pr-*` branches (variable
  pitch, Blu-ray, new fields);
- real-world examples: `D:/disc-probe/data/community-calibrations/dis-github.json` (174 entries of preset fields as
  people post them).

Write down:
- every field, its unit, which media use it, required/optional, defaults, and validation limits;
- how DIS turns a preset into a sector→(radius, angle) map. For each media, read the code and cite file:line.
- Compare with `discprobe/disexport.py` `dis_angle_map` and `discprobe/bdexport.py` and confirm they agree; if they
  don't, say where.

## 2. The test set: 50 mock DIS preset files (`tests/data/dis-presets/`)

Cover the real variety:
- DVD±R, DVD-RW, CD-R, CD-RW, BD;
- custom names, Chinese names, emoji or odd characters, duplicate ids;
- MIDs present or absent;
- pitch terms present or absent or zero;
- odd sector counts;
- old schema (v1.5.0) and new schema fields, resource keys, unknown future fields;
- broken files: bad JSON, wrong types, out-of-range values;
- a file holding one preset vs a whole `disc-presets.json`.

Base them on the real built-in and community examples (cite which). Add a `README.md` listing each file and what it
tests.

## 3. Build it

Find how DP keeps presets today first:
- `presets/*.json` in the workspace, written by `disexport` as `{preset, fit, source}`;
- `webui_catalog.py` reads `presets/`, `dis/`, `dis_preset*.json`, `disc-presets.json`;
- what the design/image pipeline consumes, and whether a DIS-style preset (ri, ro, pitch terms) can drive DP's image
  output directly or needs converting into DP's own geometry.

Write the answer at the top of FORMAT.md, then design to it.

**Import** (`python -m discprobe presets import <file>`; page: drop or pick a file):
- Parse a DIS file (whole `disc-presets.json` or one preset) and list every preset with media, name, id, sectors,
  radii, pitch terms and MID.
- Map each one to DP's geometry and say exactly what does not map, per preset. For example:
  - a CD has no along-track constant in DIS, so "L unknown"; never invent 0;
  - a missing MID;
  - a pitch model or field DP can't represent;
  - a preset that is not a measurement (DIS built-in nominal values) is marked as nominal, not calibrated.
- Save the chosen ones as DP presets in the same place and shape DP already uses, with a `source` that says "imported
  from DIS" plus the file, the preset id and the schema.
- `--dry-run` lists without writing. `--json` gives machine output. Duplicates: never overwrite silently.
- Words in zh and en via `i18n` like the rest of the CLI.

**Export** (`python -m discprobe presets export <dp preset> [--install] [--dis-presets <file>]`; page: one button):
- Write a DP preset (from geo, with corrections where they can be represented) into DIS's format.
- Reuse `disexport`'s preset building and its `--install` file handling (backup, replace rules, `--dis-presets`).
  Refactor into shared functions if needed, but keep `disexport`'s behaviour and tests unchanged.
- A preset that came from DIS goes back out unchanged (exact round trip of the DIS fields).

**The page:**
- A small sheet in the site's look: read `discprobe/web/home/index.html` tokens, the "glass" comment and `DESIGN.md`.
  Paper and ink, copper accent, words zh first with en, no new colours.
- **Import:** drop or pick a file → the list, with a per-preset line of what maps and what doesn't → tick → "导入 /
  Import".
- **Export:** choose a DP preset → "写进 DiscImageStudio / Write to DiscImageStudio" (`--install`) or "存成文件 / Save as
  file".
- Open it from where the library lists presets (one entry). The server routes call the same functions as the CLI. No
  dead ends: an old server that answers 404 hides the entry.

## 4. Tests and the report

Tests:
- every mock parses or is refused with a clear reason;
- import → export round-trips the DIS fields exactly;
- DP→DIS→DP stays within tolerance: report the max angle error in degrees per media over the data area, using
  `dis_angle_map`;
- refused cases;
- the CLI: `--dry-run`, `--json`, duplicates, `--install` into a temp `disc-presets.json` with a backup;
- the page logic as a node test.

Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`. All must pass.

Write `docs/dis-presets/REPORT.md`:
- what round-trips exactly;
- what is approximated (with the max error in degrees);
- what is refused and why;
- what you could not decide (questions for the person).

## Done means

Tests pass, and FORMAT.md and REPORT.md are written. Report the commands and anything left for later.
