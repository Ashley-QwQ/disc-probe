# DIS preset interchange report

Task: `docs/codex-cards/dis-presets.md`, worktree `dis-presets`, 2026-11-12.

## Delivered

- `python -m discprobe presets import <file>`: whole schema 2/3/4 catalogs, single
  unambiguous presets, or existing DP preset wrappers; preview, selection, dry run,
  machine JSON and zh/en human messages. Each entry includes original fields, media,
  sector count, radii, pitch, MID availability, nominal/unverified status and mapping limits.
- Save selected entries in existing `{preset, fit, source}` form under `presets/`.
  Provenance names DIS, input file, preset id and schema. Exclusive hashed filenames
  prevent path-like ids and silently overwritten duplicates. Invalid and disabled rows
  cannot be accidentally imported by default. All-invalid CLI imports return failure.
- `python -m discprobe presets export <dp preset>`: original DIS fields to stdout or
  exclusive `--output`; `--install`, `--dis-presets` and explicit `--replace` share the
  old installer’s backups, merge, enable and atomic write behavior. Geo summaries use
  the existing CD/DVD `disexport` and BD `bdexport` builders, including supported
  corrections and quality gates. Simulated geo runs cannot be installed.
- A library entry opens `presetio.js`/`presetio.css`: pick/drop → inspect → tick → import;
  saved DP preset → install or download. It hides its entry on old/offline servers.
  CLI and routes use the same Python functions. Existing page integration is three lines;
  the new server adapter is one route block plus GET/POST hooks.
- FORMAT.md records the existing DP pipeline, every catalog field and limit, source
  file/line citations, version/ref comparison, project/calibration geometry, and model
  differences. Fifty mock files and their provenance/expectations are in
  `tests/data/dis-presets/README.md`.

## What round-trips exactly

All accepted DIS **preset fields** survive DIS → DP wrapper → DIS unchanged in value,
key presence and JSON type: id, Chinese/emoji names, descriptions, resource keys,
contributors, capacity, radii, zero/absent/nonzero pitch terms, usable capacity, compatibility
density, BD polarity and unknown extensions. Fixtures exercise **57 valid preset entries**
across 40 accepted files, including each entry of a whole catalog and both duplicate-id
candidates imported separately. Unknown fields can be downloaded unchanged; they are not
installed into a DIS reader that rejects them.

This is field-level preservation, not original JSON bytes. Formatting, comments, BOM,
escape spelling and top-level catalog metadata are not reproduced by single-preset export.
Disabled state is reported during import, not encoded into the standalone preset; an
explicit installation follows the existing enable rule. A duplicate destination is reported
and left unchanged; it is not a successful overwrite round trip.

DP's pre-existing DVD/CD preset wrappers also export their already-fitted fields directly.
Existing BD wrappers with `layerCount` use `bdexport.catalog_entry` to obtain the shared
flat catalog shape; that legacy conversion is distinct from preservation of imported DIS
entries. A source geo run with correction is checked against a direct call to the old
builder, so the new interface does not silently lose the correction.

## What is approximated

`angle-audit.json` is reproducible with `python -m tools.analyze_dis_presets`.
The audit checks 20,001 positions from sector 0 to full geometry capacity, uses the
existing `dis_angle_map` 40,001-radius grid, reports unwrapped degrees, and removes
one mean angular offset (global orientation is free). A synthetic constant-pitch DP
geometry derived from each media’s source nominal preset is exported and imported back.

| Medium | DP → DIS max error | DIS → returned DP max error | Original DP → returned DP max error |
|---|---:|---:|---:|
| CD | 0.000531314° | 0.000432009° | 0.000184183° |
| DVD | 0.001215067° | 0.001328799° | 0.000714951° |
| BD | 0.002572105° | 0.002572102° | 0.0000000178215° |

Every leg is below the explicit **0.003°** test tolerance. The BD value exposes the
existing fixed-grid interpolation floor; the continuous area conversion is much closer,
as the final column shows. These numbers are scoped to those reproducible constant-pitch
cases, not a universal bound for arbitrary presets or physical burns. Tests additionally
measure each imported fixture against its area-equivalent DP baseline.

For variable pitch the baseline can be unusable:

| Medium | Worst fixture’s baseline angle error | Radius error | Fixture |
|---|---:|---:|---|
| CD | 5.049112449° | 0.0000622894 mm | `18-community-3.json`, D275-1 |
| DVD | 729.166457775° | 0.004019891 mm | `27-pitch-linear.json`, synthetic +0.001 coefficient |
| BD | 337.364108227° | 0.000804299 mm | `37-bd-pitch.json`, synthetic +0.0002 coefficient |

These presets are **retained for exact DIS export and refused for DP image use**.
The large unwrapped errors are deliberately not hidden by taking modulo 360 or declaring
a fit calibrated. DP's angle-only correction cannot fix the sector-radius change.
Constant CD/DVD values are usable explicitly as `image --geo <saved preset> --media ...`;
their status stays nominal/unverified, and CD's L remains unknown.

DIS’s exact DVD/BD and variable-CD arc-length model differs from DP’s thin-track model.
FORMAT.md identifies the integrands, sector constants and angle sign conventions. This was
a source inspection and Python numerical comparison, not execution of C# generation or a
claim of bit-for-bit image parity. CD frame/interleave layout, absolute rotation, MID,
  recording path and physical spare-area relocation are not established by geometry alone.

## What is refused, and why

- Two fixtures are refused as documents: truncated JSON and an unsupported future schema.
  Eight more contain refused rows: four incomplete real community records with no sector
  count, string/negative radii, a pitch polynomial that becomes nonpositive, and unaligned
  BD capacity. Every refusal exposes its reason.
- Other checked refusals include booleans as sector counts, integer overflow, invalid usable
  alignment, reserved ids, blank optional text and an interior-zero pitch polynomial.
  A cubic is checked at endpoints and stationary points, not only on a sampling grid.
- An ambiguous standalone DVD/BD object requires a media choice; a whole catalog supplies
  it directly. Future-schema meanings, noncanonical property casing, `.discproj`, calibration
  sessions and legacy nested `parameters` documents are not guessed into presets.
- Unknown per-preset fields are archived but block image geometry and strict DIS install.
  The generic archive retains possible future geometry without claiming to understand it.
- Nonzero pitch terms block DP image sampling. BD maps analytically to r0/pitch, but DP’s
  `image` command has no BD writer. BD polarity is retained and does not become angle sign.
- Existing output files, source/output aliases and unapproved differing DIS ids are refused.
  `--replace` is explicit; existing installed presets are backed up before mutation.
- Stopped, incomplete, noisy and simulated geo installations retain the old quality rules;
  unrepresentable BD angle corrections are refused. Export of a previously built preset
  cannot independently reconstruct the measurement history it no longer contains.
- HTTP paths outside the workspace, symlink escapes, non-JSON requests and invalid body
  sizes are refused. The page does not turn uploaded filenames into server-side read paths.

## Verification

Final result: **312 passed, 1 skipped, 46 subtests passed** for Python;
**all 18 Node test files passed**. `git diff --check` is clean. The sole Python skip is the
pre-existing sealed-photo reproduction whose original JPGs are absent.
The final command results are recorded in `test-results.txt`. Temporary-file environment
variables were directed inside this worktree because this sandbox cannot write the default
Windows pytest temporary directory. No product behavior or validator was relaxed for that.

```powershell
$env:TEMP = Join-Path (Get-Location) '.test-temp'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
python -m pytest -q tests
Get-ChildItem tests -File | Where-Object { $_.Extension -in '.mjs','.cjs' } | ForEach-Object { node $_.FullName }
python -m tools.analyze_dis_presets
git diff --check
```

New coverage includes all mocks and exact original-field preservation, full-area per-media
geometry tolerance, corrected geo builder reuse, simulated/stopped gates, dry-run/JSON,
duplicates, temp DIS installs and original-byte backups for all three media, replace rules,
i18n, HTTP/core parity, file-path boundaries, page selection logic and 404 hiding.
An ASCII-only stdout regression confirms `--json` preserves Chinese and emoji through
legacy Windows pipes using JSON escapes. Catalogue tests cover imported BD grouping and
older optional/non-object provenance without breaking existing preset discovery.
File-only Edge tests exercise real DOM behavior at desktop and actual 390px layout, safe
literal rendering of HTML-like names, rejected/empty selections, current-file media changes,
import/export requests, backup feedback and close/reopen. No product server is involved.

The skill finish reviewer’s final disposition was **ship**, scoped to three corrected
findings: accessible ink/paper action contrast, dropped-file retention on media changes,
and the browser fixture’s Archivo URL. The detector returned `[]`. Refreshed mock-sheet
captures are `.impeccable/review/presetio-desktop.png` and `presetio-mobile.png`.
The sheet inherits the existing tokens; DESIGN.md was not changed. Full live-library
composition and a real DIS UI install were not exercised.

## Unresolved questions / later work

No blocking format question remains for the implemented shared-catalog path. These require
user evidence or further product work:

1. Which burner, recording mode and registration L should an imported CD preset target?
   The catalog cannot answer. A measured registration must come from that actual path.
2. Should DP eventually render variable-pitch radius/angle directly, and add a BD image
   writer? Current imports expose the limitation and preserve the source; this card does
   not expand the sampler or implement either writer.
3. Should legacy nested BD catalogs, noncanonical key casing, or project/calibration
   geometry receive explicit import adapters? They need separate provenance/selection
   rules; no candidate or saved target was silently promoted to a calibrated preset here.
4. The original sealed-photo JPGs are absent in this checkout. That existing optional
   reproduction test remains skipped; saved-vote reproduction does not substitute for it.
5. Generated test folders `.test-temp/`, `.test-tmp-angle/`, `.test-tmp-presets/` and
   `.test-tmp-presets2/` remain, along with the `.test-*.log` captures. Automatic approval
   review rejected both bounded and literal-path cleanup commands as “blocked by policy”.
   Cleanup was left undone; no source directory was removed. These are test artifacts,
   not files required by the implementation.

## Boundary audit

No commits, pushes, stashes, resets or branch switches. No drive access. No server was
started/stopped outside isolated tests; port 8772 was never contacted. `scsi.py`, `pcal.py`,
`geo.py` and `photo.py` are unchanged. The DIS study checkout was read-only using `git show`,
`log` and `diff` with per-command safe-directory configuration. The real DIS preset file
and its backup remain at the recorded identical SHA-256; all install writes used temp files.

## Pitch correction follow-up (2026-11-12)

This section supersedes the earlier card's archive-only variable-pitch behavior above. CD/DVD imports now use the DIS arc-length model and the existing DP polynomial correction format. Degrees 0 through 16 are tried in order; the first with maximum unwrapped angle residual <= 0.01 degrees is selected. The full-area check uses 20,001 positions including sector zero and capacity. Radius residual must also be <= 0.005 mm. The fit range is the full DP radius interval; the correction is held constant outside it. Angles are anchored at sector zero; no mean rotation or modulo is removed for this conversion. The polynomial uses signed data-side angles: phi = -DIS accumulated magnitude + DP magnitude, because `_sample` starts at negative DP angle and adds phi. BD retains its previous comparison and has no DP image writer.

Accepted means usable as DP image geometry, not physically calibrated. Converted status is “从 DIS 导入，换算成 DP 修正（未经 DP 实测）”; nominal status stays nominal and CD L remains unknown. Accepted corrections are sibling JSON files linked from their DP wrappers. CLI image resolves that link; the page explicitly selects compatible imported geometry and uses the same image command. The original DIS object is untouched and export ignores the DP-side correction.

Community source SHA-256: `bdafb77ec530f48c8d8aa35e097ffe689dc593b1a1cb6d3340ccd5e868f5c8e5`. Of 174 records, 132 have complete geometry fields. This read-only snapshot has 130 records carrying pitch fields and 119 with nonzero pitch, rather than the card's 134/123. **99 nonzero-pitch presets are now usable**; 119 records total are usable. The denominator 123 cannot be reproduced from this source; no missing parameters, density aliases or unknown extensions were silently converted.

### Fixtures (every file and entry)

| Input / id | DP image | Max angle ° | Max radius mm | Degree | Reason if refused |
|---|---|---:|---:|---:|---|
| 01-builtin-cd-0.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 02-builtin-cd-1.json ritek-medical-aqua | accepted | 5.00257995851e-09 | 2.13162820728e-14 | none |  |
| 03-builtin-cd-2.json verbatim-azo-43438 | accepted | 4.16881663209e-09 | 2.13162820728e-14 | none |  |
| 04-builtin-cd-3.json cd-74 | accepted | 3.33505330567e-09 | 2.13162820728e-14 | none |  |
| 05-builtin-dvd-0.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 06-builtin-dvd-1.json verbatim-dvd-r-azo-43533 | accepted | 0.00364496080419 | 4.18776975053e-05 | 7 |  |
| 07-builtin-dvd-2.json verbatim-dvd-r-azo-43523 | accepted | 0.00364496080419 | 4.18776975053e-05 | 7 |  |
| 08-builtin-dvd-3.json verbatim-dvd-plus-r-azo-43498 | accepted | 0.00467287155922 | 3.20742488285e-05 | 6 |  |
| 09-builtin-dvd-4.json philips-dvd-plus-r | accepted | 0.00284369462353 | 0.000150065366292 | 8 |  |
| 10-builtin-dvd-5.json ritek-dvd-plus-r-e-series | accepted | 0.00373838682371 | 1.18108704115e-05 | 7 |  |
| 11-builtin-bd-0.json bd-r-sl-25gb | refused | 0.00257209643891 | 3.7594531932e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 12-builtin-bd-1.json bd-r-ritek-10x | refused | 0.00259179984803 | 3.76943631863e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 13-builtin-bd-2.json bd-r-ritek-12x | refused | 0.00259446016414 | 3.76935460622e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 14-builtin-bd-3.json bd-r-verbatim-64099 | refused | 0.00257832840038 | 3.76241615641e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 15-community-0.json D169-1 | accepted | 5.00257995851e-09 | 1.42108547152e-14 | none |  |
| 16-community-1.json D169-2 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| 17-community-2.json D169-3 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| 18-community-3.json D275-1 | accepted | 0.00279374144038 | 6.22892813027e-05 | 5 |  |
| 19-community-4.json D172-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| 20-community-5.json D172-3 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| 21-chinese-name.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 22-emoji-name.json ../CON:盘💿 | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 23-mid-present.json dvd-5-120mm | refused | 7.25540846649e-05 | 3.41913164448e-11 | none | Unknown fields retained; geometry use and DIS installation refused: mid |
| 24-mid-absent.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 25-pitch-absent.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 26-pitch-zero.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 27-pitch-linear.json dvd-5-120mm | accepted | 0.00598587532227 | 0.00401988966581 | 9 |  |
| 28-pitch-cubic.json dvd-5-120mm | accepted | 0.00743182983166 | 0.00117744914743 | 9 |  |
| 29-dvd-odd-sectors.json dvd-5-120mm | accepted | 7.25507496116e-05 | 3.41984218721e-11 | none |  |
| 30-cd-rw.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 31-dvd-plus-rw.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 32-dvd-minus-rw.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 33-unknown-field.json dvd-5-120mm | refused | 7.25540846649e-05 | 3.41913164448e-11 | none | Unknown fields retained; geometry use and DIS installation refused: futureGeometry |
| 34-resource-null.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 35-cd-legacy-speed.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 36-dvd-legacy-bit.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 37-bd-pitch.json bd-r-sl-25gb | refused | 337.364108227 | 0.000804299086056 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 38-single-preset.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 39-dp-wrapper.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 40-schema-2.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 41-schema-3.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 42-duplicate-ids.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 42-duplicate-ids.json dvd-5-120mm | accepted | 7.25207341318e-05 | 3.41700001627e-11 | none |  |
| 43-disabled.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 44-whole-catalog.json cd-80 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| 44-whole-catalog.json ritek-medical-aqua | accepted | 5.00257995851e-09 | 2.13162820728e-14 | none |  |
| 44-whole-catalog.json verbatim-azo-43438 | accepted | 4.16881663209e-09 | 2.13162820728e-14 | none |  |
| 44-whole-catalog.json cd-74 | accepted | 3.33505330567e-09 | 2.13162820728e-14 | none |  |
| 44-whole-catalog.json dvd-5-120mm | accepted | 7.25540846649e-05 | 3.41913164448e-11 | none |  |
| 44-whole-catalog.json verbatim-dvd-r-azo-43533 | accepted | 0.00364496080419 | 4.18776975053e-05 | 7 |  |
| 44-whole-catalog.json verbatim-dvd-r-azo-43523 | accepted | 0.00364496080419 | 4.18776975053e-05 | 7 |  |
| 44-whole-catalog.json verbatim-dvd-plus-r-azo-43498 | accepted | 0.00467287155922 | 3.20742488285e-05 | 6 |  |
| 44-whole-catalog.json philips-dvd-plus-r | accepted | 0.00284369462353 | 0.000150065366292 | 8 |  |
| 44-whole-catalog.json ritek-dvd-plus-r-e-series | accepted | 0.00373838682371 | 1.18108704115e-05 | 7 |  |
| 44-whole-catalog.json ritek-dvd-r-e-series | accepted | 0.00582960592666 | 2.95756738211e-06 | 5 |  |
| 44-whole-catalog.json dvd-5-80mm | accepted | 4.99957841053e-05 | 1.1912248965e-11 | none |  |
| 44-whole-catalog.json bd-r-sl-25gb | refused | 0.00257209643891 | 3.7594531932e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 44-whole-catalog.json bd-r-ritek-10x | refused | 0.00259179984803 | 3.76943631863e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 44-whole-catalog.json bd-r-ritek-12x | refused | 0.00259446016414 | 3.76935460622e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 44-whole-catalog.json bd-r-verbatim-64099 | refused | 0.00257832840038 | 3.76241615641e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 44-whole-catalog.json bd-r-verbatim-64293 | refused | 0.00257832840038 | 3.76241615641e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| 45-bad-json.json | refused | N/A | N/A | none | invalid JSON: Expecting property name enclosed in double quotes: line 1 column 21 (char 20) |
| 46-wrong-type.json dvd-5-120mm | refused | N/A | N/A | none | radii must satisfy 0 < innerRadiusMm < outerRadiusMm |
| 47-negative-radius.json dvd-5-120mm | refused | N/A | N/A | none | radii must satisfy 0 < innerRadiusMm < outerRadiusMm |
| 48-bad-pitch.json dvd-5-120mm | refused | N/A | N/A | none | pitch must be finite and positive throughout 0 <= x <= 1 |
| 49-bd-odd.json bd-r-sl-25gb | refused | N/A | N/A | none | invalid/incomplete document |
| 50-future-schema.json | refused | N/A | N/A | none | unsupported schemaVersion; expected 2, 3 or 4 |
| 51-unwrapped-over360.json synthetic-unwrapped-over360 | refused | 1116.32439168 | 26.7996450335 | 16 | DP approximation exceeds 0.01 deg angle or 0.005 mm radius; archive only. |

### Community (all 174 records, including incomplete refusals)

| Input / id | DP image | Max angle ° | Max radius mm | Degree | Reason if refused |
|---|---|---:|---:|---:|---|
| D169-1 | accepted | 5.00257995851e-09 | 1.42108547152e-14 | none |  |
| D169-2 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| D169-3 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| D275-1 | accepted | 0.00279374144038 | 6.22892813027e-05 | 5 |  |
| D172-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D172-3 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D209-1 | accepted | 0.00447250945343 | 4.33871900754e-05 | 7 |  |
| D271-1 | accepted | 0.00275716750673 | 1.69920896909e-05 | 7 |  |
| D216-1 | accepted | 0.00404849762036 | 3.25064387852e-06 | 6 |  |
| D216-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D127-1 | accepted | 0.00256778498454 | 2.1544865163e-06 | 6 |  |
| D127-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D269-1 | accepted | 0.00380243321532 | 1.85174897638e-08 | 0 |  |
| D268-1 | accepted | 0.00314649415755 | 0.000101347728986 | 7 |  |
| D266-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D265-1 | accepted | 0.00476422625006 | 8.11224443495e-05 | 5 |  |
| D262-1 | accepted | 0.00249232687803 | 7.89556339598e-05 | 7 |  |
| D252-1 | accepted | 0.00904694973172 | 4.77293973233e-06 | 5 |  |
| D250-1 | refused | 2.9359556501 | 6.96156079272e-06 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| D243-1 | accepted | 0.0051435768333 | 4.37860969242e-05 | 6 |  |
| D244-1 | accepted | 0.00528050889891 | 4.11025763469e-06 | 5 |  |
| D241-1 | refused | 0.617619413194 | 1.56276284002e-06 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| D240-1 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| D210-1 | refused | 0.174044400358 | 9.39846653836e-07 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| D210-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D109-1 | accepted | 0.00822616142088 | 7.05162431558e-06 | 6 |  |
| D109-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D109-3 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D109-4 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D198-1 | accepted | 0.00833007547933 | 6.47487640038e-06 | 5 |  |
| D225-1 | accepted | 0.00254135103417 | 7.40217706863e-06 | 7 |  |
| D191-1 | accepted | 0.00269971531261 | 7.73281982163e-05 | 7 |  |
| D191-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D220-1 | accepted | 0.00551919962706 | 3.5656851253e-05 | 6 |  |
| D217-1 | accepted | 0.00483803534613 | 3.20595783663e-05 | 6 |  |
| D214-1 | accepted | 0.00058187941742 | 3.34792460421e-09 | 0 |  |
| D214-2 | accepted | 0.00056291330122 | 3.27511529008e-09 | 0 |  |
| D214-3 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D208-1 | accepted | 7.29309456884e-05 | 3.45181661032e-11 | none |  |
| D208-2 | accepted | 7.29309456884e-05 | 3.45181661032e-11 | none |  |
| D201-1 | accepted | 0.00773887072269 | 0.000127297127861 | 7 |  |
| D115-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D199-1 | accepted | 0.00270795247225 | 4.03166431084e-05 | 7 |  |
| D163-1 | accepted | 7.21005174153e-05 | 3.38218342222e-11 | none |  |
| D176-1 | accepted | 0.00371574933441 | 0.000106764500018 | 7 |  |
| D176-2 | accepted | 0.00972062133051 | 9.334009561e-05 | 6 |  |
| D133-1 | accepted | 0.00296418883808 | 4.69002852554e-06 | 6 |  |
| I35-1 | accepted | 0.00364496080419 | 4.18776975053e-05 | 7 |  |
| I36-1 | refused | 0.00259446016414 | 3.76935460622e-09 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| I41-1 | accepted | 0.00284369462353 | 0.000150065366292 | 8 |  |
| I41-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I50-1 | accepted | 0.00373838682371 | 1.18108704115e-05 | 7 |  |
| I99-1 | accepted | 0.00373838682371 | 1.18108704115e-05 | 7 |  |
| I53-1 | accepted | 0.00582960592666 | 2.95756738211e-06 | 5 |  |
| I58-1 | accepted | 0.00517477987356 | 4.26966073519e-06 | 6 |  |
| I58-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I60-1 | accepted | 0.0081153157486 | 3.6866076556e-06 | 5 |  |
| I60-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I61-1 | accepted | 0.00855648733502 | 7.07442529091e-06 | 6 |  |
| I61-2 | accepted | 0.00854929133109 | 7.07403410516e-06 | 6 |  |
| I61-3 | accepted | 0.00352829173417 | 1.21452074957e-05 | 7 |  |
| I64-1 | accepted | 0.00253906618001 | 7.71046420027e-05 | 7 |  |
| I65-1 | accepted | 7.29209405285e-05 | 3.46744855051e-11 | none |  |
| I65-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I69-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I73-1 | accepted | 0.00270720475576 | 4.03160680236e-05 | 7 |  |
| I74-1 | accepted | 0.00821405369208 | 3.28800196527e-05 | 6 |  |
| I74-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I75-1 | accepted | 0.00520320834684 | 1.08268590111e-05 | 6 |  |
| I76-1 | accepted | 7.24073423194e-05 | 3.40349970429e-11 | none |  |
| I77-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I77-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I79-1 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| I82-1 | accepted | 0.00833977864116 | 3.97147623445e-05 | 6 |  |
| I82-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I83-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I86-1 | accepted | 3.33505330567e-09 | 2.13162820728e-14 | none |  |
| I87-1 | accepted | 0.0005706823201 | 3.93814048039e-09 | 0 |  |
| I87-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I87-3 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I94-1 | accepted | 0.00296418883808 | 4.69002852554e-06 | 6 |  |
| I132-1 | accepted | 0.00296418883808 | 4.69002852554e-06 | 6 |  |
| I119-1 | accepted | 0.00432201013208 | 4.17341698338e-05 | 7 |  |
| I119-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I124-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I129-1 | accepted | 0.00271355267835 | 3.58186848075e-05 | 7 |  |
| I146-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I140-1 | accepted | 0.00866705465142 | 2.30441818019e-05 | 5 |  |
| I144-1 | accepted | 0.00371138991249 | 5.65143835018e-06 | 6 |  |
| I144-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I145-1 | accepted | 0.000176131069275 | 1.73869096898e-09 | 0 |  |
| I151-1 | accepted | 0.00487091535528 | 4.83024168219e-06 | 6 |  |
| I165-1 | accepted | 0.00941233344946 | 3.98721093902e-05 | 6 |  |
| I185-1 | accepted | 0.00519870523617 | 0.00050090334836 | 9 |  |
| I185-2 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| I189-1 | accepted | 3.33505330567e-09 | 2.13162820728e-14 | none |  |
| I200-1 | refused | 1.19795326233 | 2.6979662664e-06 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| I200-2 | accepted | 0.00242882924447 | 4.56135840139e-05 | 7 |  |
| I202-1 | accepted | 0.00807062088027 | 5.17300052891e-05 | 6 |  |
| I205-1 | accepted | 0.00320310290381 | 8.18589056522e-05 | 7 |  |
| I212-1 | accepted | 0.00248687623755 | 3.47165278214e-06 | 5 |  |
| I213-1 | refused | 1.01057735002 | 4.68035996448e-06 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| I223-1 | accepted | 0.00240987907271 | 1.24687971592e-05 | 6 |  |
| I228-1 | accepted | 0.00528050889891 | 4.11025763469e-06 | 5 |  |
| I248-1 | accepted | 0.00589349510327 | 1.56732090062e-06 | 4 |  |
| I248-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I255-1 | accepted | 0.00595585893459 | 7.75358459251e-05 | 5 |  |
| I272-1 | accepted | 0.00358446106898 | 4.07748632796e-05 | 7 |  |
| I277-1 | accepted | 0.00467444589801 | 3.2073742247e-05 | 6 |  |
| I278-1 | accepted | 0.00737629244698 | 1.75365091977e-05 | 6 |  |
| I281-1 | accepted | 0.00645589617395 | 8.56493073087e-06 | 6 |  |
| I281-2 | refused | 1.15374742155 | 4.59330870228e-06 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| I281-3 | accepted | 0.00272638347218 | 3.84508217905e-05 | 7 |  |
| I281-4 | refused | 3.93068643914 | 1.53330096353e-05 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| I283-1 | refused | 1.14109357764 | 3.44170933886e-06 | none | BD geometry maps to r0/pitch; DP image command has no BD writer. |
| I289-1 | accepted | 0.00275717605832 | 1.6992089158e-05 | 7 |  |
| I171-1 | refused | 0.00258439621474 | 4.19647030654e-05 | 7 | Unknown fields retained; geometry use and DIS installation refused: interleave |
| I171-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I171-3 | accepted | 0.00333963410738 | 3.15812276241e-05 | 5 |  |
| I171-4 | accepted | 0.00472221675509 | 3.99934099065e-05 | 5 |  |
| I184-1 | accepted | 0.00258439621474 | 4.19647030654e-05 | 7 |  |
| I184-2 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I116-1 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| I232-1 | accepted | 5.00257995851e-09 | 1.42108547152e-14 | none |  |
| I232-2 | refused | N/A | N/A | none | sectors must be a positive integer <= 9223372036854775807 |
| I260-1 | accepted | 0.0052862735829 | 5.77060003408e-05 | 7 |  |
| I249-1 | accepted | 7.25874351979e-05 | 3.42126327268e-11 | none |  |
| I242-1 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| I292-1 | accepted | 3.33505330567e-09 | 2.13162820728e-14 | none |  |
| I25-1 | accepted | 4.16881663209e-09 | 2.13162820728e-14 | none |  |
| I52-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D107-1 | accepted | 0.000237141014144 | 1.08372688601e-09 | 0 |  |
| D107-2 | accepted | 0.000383781119072 | 1.74926384489e-09 | 0 |  |
| D107-3 | accepted | 4.40425607978e-05 | 7.58646478971e-11 | 0 |  |
| D107-4 | accepted | 0.000190109854752 | 2.19507967358e-09 | 0 |  |
| D107-5 | accepted | 0.000207158662539 | 2.23555929324e-09 | 0 |  |
| D107-6 | accepted | 0.00752427568451 | 8.42745604004e-05 | 6 |  |
| D107-7 | accepted | 0.00804858357521 | 7.74979434581e-05 | 6 |  |
| D107-8 | accepted | 0.00270022425368 | 7.7346667176e-05 | 7 |  |
| D107-9 | accepted | 5.00257995851e-09 | 1.42108547152e-14 | none |  |
| D107-10 | accepted | 9.5510552763e-05 | 1.3125145415e-10 | 0 |  |
| D107-11 | accepted | 0.00540751508793 | 7.86609735641e-05 | 6 |  |
| D107-12 | accepted | 0.00292331997051 | 9.45784146467e-05 | 7 |  |
| D107-13 | accepted | 0.00540894618085 | 7.86805436448e-05 | 6 |  |
| D107-14 | accepted | 0.00720647142264 | 9.26485191073e-05 | 6 |  |
| D107-15 | accepted | 0.000175893801097 | 1.73712777496e-09 | 0 |  |
| D107-16 | accepted | 0.00433976750527 | 2.21518519083e-08 | 0 |  |
| D107-17 | accepted | 0.00435119058032 | 2.21950564594e-08 | 0 |  |
| D107-18 | accepted | 0.00435448352871 | 2.22131681937e-08 | 0 |  |
| D107-19 | accepted | 0.00229751626279 | 1.9392757622e-08 | 0 |  |
| D107-20 | accepted | 0.00357165158519 | 8.27239882994e-06 | 6 |  |
| D107-21 | accepted | 7.21071875219e-05 | 3.38218342222e-11 | none |  |
| D107-22 | accepted | 7.21005174153e-05 | 3.38218342222e-11 | none |  |
| D107-23 | accepted | 0.00178978173006 | 1.01039532296e-08 | 0 |  |
| D107-24 | accepted | 0.00090631713936 | 4.47754189281e-09 | 0 |  |
| D107-25 | accepted | 0.00086273344512 | 4.29839985827e-09 | 0 |  |
| D107-26 | accepted | 0.00521044728826 | 0.000297359114121 | 8 |  |
| D107-27 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D107-28 | accepted | 0.000147028427443 | 1.56653356953e-09 | 0 |  |
| D107-29 | refused | 0.00257908053725 | 3.76261155566e-09 | none | Unknown fields retained; geometry use and DIS installation refused: channelBitLengthNm; BD geometry maps to r0/pitch; DP image command has no BD writer. |
| D107-30 | accepted | 7.26474661574e-05 | 3.43192141372e-11 | none |  |
| D107-31 | accepted | 3.33505330567e-09 | 1.42108547152e-14 | none |  |
| D174-1 | accepted | 0.00356736838366 | 8.74993609372e-05 | 7 |  |
| D181-1 | accepted | 0.00694879333018 | 5.33354751582e-05 | 6 |  |
| I67-1 | accepted | 0.00654325574105 | 5.2624973776e-05 | 7 |  |
| I67-2 | accepted | 0.00481706501894 | 4.35897462481e-05 | 7 |  |
| I67-3 | accepted | 0.00741678736031 | 2.72291817751e-05 | 5 |  |
| I78-1 | accepted | 0.00347144581217 | 3.92096883175e-05 | 5 |  |
| I78-2 | accepted | 4.16881663209e-09 | 1.42108547152e-14 | none |  |
| I88-1 | refused | N/A | N/A | none | radii must satisfy 0 < innerRadiusMm < outerRadiusMm |
| I218-1 | refused | 7.26708115306e-05 | 3.42907924278e-11 | none | Unknown fields retained; geometry use and DIS installation refused: pitch_um, r0_mm, u, v |
| I320-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| D323-1 | refused | N/A | N/A | none | totalSectors must be a positive integer <= 4294967295 |
| I86-2 | refused | 0.00582539229707 | 8.41474881526e-05 | 6 | Unknown fields retained; geometry use and DIS installation refused: linearDensity |


## Pitch follow-up verification

The new tests cover full-area corrected CD/DVD geometry, polynomial sign and range,
the lowest passing degree, DIS's independent constant-arc primitive, exact original-field
export, CLI JSON and Chinese residual listings, radius-only refusal, an unwrapped error
above 360 degrees, automatic correction loading at the actual image writer boundary,
and the page's actual geometry selector. The focused suite passed all **7 tests**;
its result is in `pitch-focused-tests.txt`.

Two Windows timing failures found during full-suite runs were repaired without weakening
assertions: the preset HTTP route now consumes its bounded request body before sending
a 415 response (avoiding a reset caused by unread socket bytes), and the existing burner
test registers `backend.close` before its temporary-directory cleanup, joining its mock
job before deleting the event log. The isolated HTTP test passed three consecutive runs
(`pitch-http-tests.txt`). The earlier failure captures are retained as
`pitch-python-pre-http-fix.txt` and `pitch-python-pre-cleanup-fix.txt`.

This remains a numerical conversion of the documented DIS model, with drive-free tests;
neither C# generator execution nor physical-burn parity is claimed. BD remains archive-only,
CD L remains unknown, and nominal presets remain nominal. Missing community parameters
and unknown extensions remain explicit refusals. The actual community snapshot supports
99 usable nonzero-pitch records (16 CD and 83 DVD), with the card's denominator discrepancy
and input hash recorded above.

No commits, pushes, stashes, resets or branch switches were made. No real drives or port
8772 were contacted. The DIS study source was only read, the real DiscImageStudio app-data
directory was not written, and `scsi.py`, `pcal.py`, `geo.py`, and `photo.py` are unchanged.

Final full-suite result: **320 passed, 1 skipped, 46 subtests passed** in 225.44 seconds
(`python -m pytest -q tests`, `pitch-python-tests.txt`). The skip is the pre-existing
sealed-photo reproduction whose original JPGs are absent. **All 19 Node test files passed**
(`node` for every `tests/*.mjs` and `tests/*.cjs`, `pitch-node-tests.txt`). `git diff --check`
is clean. Test TEMP/TMP were directed inside this worktree; no validator or assertion was
relaxed.

Cleanup remains incomplete: automatic approval review rejected the workspace-bounded
PowerShell removal command as **“blocked by policy”** before it ran. The targets had been
resolved and checked as immediate children of this worktree. Per the card, the remaining
owned test folders are listed here:

- `D:/disc-probe/.claude/worktrees/dis-presets/.pitch-test-temp/`
- `D:/disc-probe/.claude/worktrees/dis-presets/tmpseny_d8_/`

No product work remains for this card; these are temporary test artifacts. The source's
119-versus-123 nonzero-pitch count discrepancy remains explicit rather than inferred away.

