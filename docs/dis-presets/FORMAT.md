# DIS presets and DP geometry

## DP storage and generation (design decision)

DP already saves `presets/*.json` as `{preset, fit, source}` through `disexport.export`.
`webui_catalog.catalogue` reads that location, `dis/`, `dis_preset*.json` and `disc-presets.json`.
The image pipeline does **not** consume the DIS object: `__main__._geo_fit` loads `fit`,
and `imagedisc._sample` uses `u`, `v`, `bit_nm_assumed` and an optional angle-only polynomial
correction. A variable-pitch DIS preset changes both radius and angle at a sector and cannot
be represented exactly by that sampler. Import therefore keeps the original DIS dictionary
as `preset` and derives an explicitly uncalibrated area-equivalent fit. CD/DVD nonzero pitch
is converted to a sibling angle correction when full-area residuals pass 0.01° angle and
0.005 mm radius. Unknown fields and BD remain archive-only. Usable presets can be passed
to `image --geo presets/<file>.json --media cd|dvd`; the correction link loads automatically.
CD registration L remains unknown; the imported preset does not invent a measured zero.

Import saves provenance (`origin: imported from DIS`, input filename, id, schema, media,
status and mapping issues) in `source`. It never overwrites a preset. Export of a saved
preset preserves its original fields, including absent fields and unknown future fields.
Export of a geo run calls the existing `disexport.export` or `bdexport.export`; install
shares `disinstall`'s merge, backup, enable, replace and atomic writer.

## Sources and version comparison

Inspected read-only on 2026-11-12:

- DIS checkout HEAD `619ec7505ac8955f35fe2f353ebda74b6ea90dda` in
  `D:/dis-study/DiscImageStudio`. All DIS references below are relative to that repository's
  `src/` directory and use this revision unless a ref is named.
- v1.5.0 `29b8cc1`: `git show` and `git diff 29b8cc1 619ec75` show **no differences** in
  `DiscImageStudio.Core/DiscPresetJsonStore.cs`, its built-in JSON, `DvdTrackGeometry.cs`,
  `DiscImageStudio.Cd/CdDiscParameters.cs` or `DiscImageStudio.BluRay/BluRayDiscParameters.cs`.
  Thus “old release” does not mean schema 2: v1.5.0 already uses schema 4, BD, cubic pitch,
  resource keys, contributor and usable-sector fields. Schemas 2 and 3 are its supported
  legacy shapes, not an invented v1.5.0-only schema.
- Local refs inspected: `pr-188`, `pr-221`, `pr-222`, `pr-227`, `pr-236`, `pr-284`,
  `pr-287`, `pr-291`, `pr-298`. Against `619ec75`, preset-store/geometry format changes
  are absent except older `pr-188` lacking some later usable-sector handling. `pr-222`
  adds built-in `ritek-dvd-plus-rw-4x` (measured cubic DVD+RW, MID in description);
  `pr-298` adds a measured Verbatim CD-R Extra Protection entry with pitch coefficients.
  The other inspected refs add no fields to the shared preset schema. In particular,
  dual-layer work in `pr-236` does not add a layer-count field to that catalog definition.
  Variable pitch was already introduced before v1.5.0 (`b714ca4` in file history).
- The real `%LOCALAPPDATA%/DiscImageStudio/disc-presets.json` and the specified backup
  were read only. Both have schema 4 and one initial `user-custom-*` entry per medium,
  with zero pitch terms and empty disabled lists. Both SHA-256 values were
  `70e203df96006023dbbb5531567ee23b96eb2e0ff44c92af7065850925fd74a0`.
  These are nominal initial values, not measurements.
- Built-in JSON contains 4 CD, 8 DVD and 5 BD entries. It mixes nominal standards and
  claimed measured examples; being built-in alone does not prove calibration.
- `D:/disc-probe/data/community-calibrations/dis-github.json`: 174 entries, collected
  2026-11-10 (125 DVD, 34 CD, 15 BD). Posted `parameters` include incomplete records,
  DP `u/v`, pitch/r0 estimates, linear density, interleave and polarity in addition to
  catalog fields. They are starting points, with individual source URLs, not a validated
  DIS catalog. Fixture provenance is listed in `tests/data/dis-presets/README.md`.

## Catalog and field inventory

Definitions: `DiscImageStudio.Core/DiscPresetJsonStore.cs:7` (CD), `:30` (DVD), `:52`
(BD), `:72` (document). JSON options at `:103` accept comments, trailing commas and
case-insensitive property names; unknown members are **disallowed** by DIS. DP reads
comments/BOM/trailing commas, writes canonical plain UTF-8 JSON, and expects the published
camelCase field names. It archives unknown per-preset fields with a warning and refuses to
install them into strict DIS. It does not infer future-schema meanings.

| Top-level field | Required/default | Meaning and validation |
|---|---|---|
| `schemaVersion` | Required integer | 2, 3 or 4. 2 predates BD; 3 omitted compatibility density fields; writes migrate to 4. |
| `cdPresets`, `dvdPresets` | Required arrays | CD/DVD entries. Duplicate ids within each family are invalid in DIS. |
| `bluRayPresets` | Required non-null array in schema 4; absent allowed in 2/3 | Single-layer BD entries. |
| `disabledCdPresetIds`, `disabledDvdPresetIds`, `disabledBluRayPresetIds` | Optional/null → empty | Unique, nonblank, case-sensitive ids excluded from the merged built-in/user lists. |
| `fallbackLanguage` | Optional/null | Nonblank localization language identifier when present; not geometry. |

`DiscPresetJsonStore.cs:275` validates the document and arrays; `:299` checks ids;
`:455` merges by ordinal id, allows user overrides of built-ins, and omits disabled entries.
`Save` at `:230` migrates schema, validates, writes a temporary file and replaces the target.
`DiscImageStudio.App/ViewModels/DiscParametersState.cs:430` loads and merges built-in and
user catalogs; `:443` falls back to built-ins if user loading fails. Invalid installation
can therefore hide the entire user's list, which is why import warnings and refusals matter.

| Preset field | Media | Unit | Required/default | Limits/meaning |
|---|---|---|---|---|
| `id` | All | text | Required | Nonblank, unique within family, case-sensitive; `__manual__` reserved. No filesystem meaning. |
| `displayName`, `description` | All | text | Required | Nonblank. Names may contain Chinese, emoji and punctuation. Not reliable evidence of MID or calibration. |
| `sectors` | CD | 1/75 s sectors | Required | Positive signed 64-bit integer. No multiple requirement. Generation byte-count arithmetic can additionally overflow on unrealistic capacities. |
| `totalSectors` | DVD | sectors | Required | Positive unsigned 32-bit integer. The catalog allows odd geometry capacity; only usable capacity is aligned. |
| `totalSectors` | BD | sectors | Required | Positive multiple of 32, at most 12,219,392. |
| `innerRadiusMm`, `outerRadiusMm` | All | mm | Required | Finite; `0 < inner < outer`. Only BD has the catalog maximum `outer <= 60`. |
| `linearVelocityMmPerSecond` | CD | mm/s | Optional, 1200 | Finite positive. Compatibility field: current app generation uses 1200 regardless of stored value. Retain unchanged. |
| `channelBitLengthNm` | DVD | nm/channel bit | Optional, 133.3 | Finite positive. Compatibility field: current app generation uses 133.3 regardless of stored value. Retain unchanged. |
| `pitchLinear`, `pitchQuadratic`, `pitchCubic` | All | dimensionless | Optional, each 0 | Finite coefficients; `1+c1*x+c2*x²+c3*x³` must remain strictly positive for all `x∈[0,1]`. No arbitrary coefficient cap. |
| `usableSectors` | All | sectors | Optional/null → full geometry | Positive, at most geometry total; multiple of 1 for CD, 16 for DVD, 32 for BD. Changes output length, not full geometry normalization. |
| `invertMapping` | BD | boolean | Optional, false | Luminance/run-length polarity, **not** track-angle reversal. |
| `displayNameResourceKey`, `descriptionResourceKey` | All | text | Optional/null | Nonblank when supplied. Localization metadata, preserved even without a matching DP resource. |
| `contributor` | All | text | Optional/null | Nonblank when supplied; attribution, not MID or measurement certification. |

Validation references: `DiscPresetJsonStore.cs:325` (CD), `:359` (DVD), `:390` (BD),
`:424` (usable sectors), `:498` (reserved id), `:507` (pitch), `:516` (text), `:532`
(radii). Cubic validation checks endpoints and all real stationary points, rather than
sampling a few radii: `DvdTrackGeometry.cs:212` and `:677`.
CD-R/CD-RW, DVD−R/+R/−RW/+RW do not have separate type fields in this catalog; their names
and geometry vary. The importer does not manufacture a subtype or a MID from those names.

There is **no** MID, drive identity, CD along-track L, pitch unit in micrometres, start
rotation or layer count in a shared catalog entry. BD's fixed bit length is 74.5 nm; it has
no catalog `channelBitLengthNm`. `mid`, `MID`, `interleave`, `r0_mm`, `pitch_um`, `u/v`,
`linearDensity`, etc. are community/export extensions, not newly discovered DIS fields.
They survive archive export but do not become verified geometry.

## Sector → radius and angle

Let `N` be the full geometry sectors, `ri/ro` its radii, `S` the track length per sector,
`x=(r-ri)/(ro-ri)`, `q(x)=1+c1*x+c2*x²+c3*x³`, and `p(r)=p0*q(x)`.
Track angle magnitude satisfies `dθ/dr=2π/p(r)`. DIS uses a clockwise sampling convention
with per-media image-coordinate transformations; compare accumulated magnitude and remove
one free global rotation when comparing DP, not a modulo-360 residual.

- **CD:** `S=1200/75=16 mm`; 98 frames × 588 bits = 57,624 channel bits/sector.
  With zero pitch coefficients, `r(s)=sqrt(ri²+(ro²-ri²)*s/N)` and
  `θ(r)=start+2*N*S*(r-ri)/(ro²-ri²)`.
  `DiscImageStudio.Cd/CdDiscParameters.cs:57` defines total time, `:106` arc length,
  `:111` radius, `:120` theta and `:127` polar coordinates. Nonzero coefficients use
  `DvdTrackGeometry` with total length `16*N` (`:24`). App calibration fixes standard
  speed at `DiscImageStudio.App/ViewModels/CalibrationViewModel.cs:400`.
- **DVD:** `S=38,688*133.3e-6 mm`. `DiscImageStudio.Dvd/DvdStreamingGenerator.cs:31`
  fixes standard bit length; `:38` and `:102` create the common track geometry.
  `DiscImageStudio.Core/Calibration/CalibrationTarget.cs:30` and `:43` spell out sector
  bits and length. The engine solves `p0` so exact spiral length reaches `ro` at `N`:
  `ds/dr=sqrt(1+(2π*r/p(r))²)`. `DvdTrackGeometry.cs:43` handles constant pitch with
  bisection and exact arc primitive; `:69` handles variable pitch; `:220` inverts arc
  length to radius, `:332` evaluates angle, and `:534` integrates angle and exact length.
  `:718` gives `primitive(r,b)=(r*sqrt(r²+b²)+b²*asinh(r/b))/2`, `b=p0/(2π)`.
- **BD:** `S=(2760+496*1932+1104)/32 * 74.5e-6 = 2.239972875 mm`.
  `DiscImageStudio.BluRay/BluRayDiscParameters.cs:23` defines the recording-unit constants
  including run-in and run-out. `BluRayTrackGeometry.cs:31` defines full track length;
  `:37` delegates variable pitch to common `DvdTrackGeometry`; `:44` solves constant
  exact arc growth; `:133` maps progress, and `:161` maps a sector. Its final angle is
  `angleOffset - accumulatedAngle` (`:143`, `:157`). A BD catalog is single-layer;
  `BluRayDiscParameters.cs:35` rejects other layer counts. Spare-area relocation is not
  encoded by the catalog and cannot be inferred from the name or capacity.

### Agreement with DP, and the precise differences

`discprobe/disexport.py:32` uses the same normalized cubic **pitch**, with total length
`N*sector_bits*bit_nm*1e-6`, but uses the thin-track approximation `ds/dr=2π*r/p(r)` and
a 40,001-point trapezoid grid. It is mathematically the same **constant CD** area model
apart from interpolation; it approximates exact DVD/BD and variable-CD arc length.
These models are not byte-exact C# parity. For ordinary physical disc pitches the omitted
radial component is tiny; pathological accepted catalog geometries need not have that
property. The numerical audit reports the actual DP-grid discrepancies instead of claiming
the header comment's “under 0.001 degree” as a universal interpolation bound.

The generic `dis_angle_map` honors whatever `bit_nm` its caller supplies. DIS's current app
ignores its stored compatibility CD speed/DVD bit length and uses standard values, so new
import mapping uses 1200/133.3 rather than blindly replaying those stored fields. The old
exporter still allows nonstandard DVD geo bit assumptions: that creates a density mismatch
with current DIS even though the field is retained. CD export already refuses a bit
assumption different from `cd.BIT_NM` (`disexport.py:143`).

`discprobe/bdexport.py:37` defines the same BD recording-unit constants and fixed bit
length. `outer_radius_mm` at `:117` uses the area identity
`ro²=ri²+pitch_mm*N*S/π`, whereas DIS solves exact spiral arc length. BD export is thus
an analytic area conversion, with the small radial-component distinction above. Existing
`bdexport` optionally derives/pulls back inner spare area, applies a pitch/twist correction,
aligns capacity to 32 and reserves a default usable margin; those are export policy, not
extra DIS schema fields. New geo exports call it rather than reimplementing those policies.

DP's `θ(n)=2n/(sqrt(u²+v*n/π)+u)`, `r=b*sqrt(u²+v*n/π)` has the same constant-pitch
area family (`imagedisc.py:232`). Set `u=ri/b`,
`v=π*(ro²-ri²)/(N*sector_bits*b²)`. For a varying DIS pitch this is only an area-equivalent
baseline. The importer reports maximum **unwrapped angle** and radius residual over
20,001 full-data-area sector positions. For CD/DVD, `dispitch.sector_map` integrates the exact
DIS arc-length and angle integrands (constant CD keeps its area formula). `dispitch.convert`
fits the signed data-side difference in the existing `poly_in_x`, `radius_valid_mm` format,
trying degrees 0–16 and taking the lowest that passes. The maximum radius residual is
checked independently; angle correction cannot change it. Sector-zero anchored unwrapped
errors, degree, full fit range and baseline error are recorded in `source.comparison`.
No modulo or free mean rotation is removed for this conversion. BD retains the previous
thin-track grid comparison and image refusal. See `angle-audit.json` and REPORT.md.

The DP wrapper's top-level `correction` names a sibling file containing `geo_fit` u/v.
Image loading validates that base and resolves the link relative to the wrapper, so moving
both files together works. Imported geometry remains `calibrated: false`. The page lists
compatible imports as explicitly selectable geometry while keeping status `unknown`;
preview describes them as imported and unmeasured. Image generation caps capacity at the
imported full data area. Export returns the original `preset` without the DP correction.

## Other persisted geometry

`DiscImageStudio.Core/ProjectJsonStore.cs:10` defines `ProjectGeometry`: ri, ro, sectors,
three pitch terms and optional usable sectors. `:56` defines `.discproj` with family,
that geometry copy, layer/image transforms, outputs, calibration-session path and BD
polarity. It does not merely retain a preset id; editing the catalog later does not replace
the project geometry. Project schema 2 includes BD; a removed `imageProcessing` key has
explicit compatibility handling (`:84`). From v1.5.0 to main only output options changed
in this file; the preset/geometry records did not acquire new fields.

`DiscImageStudio.Core/Calibration/CalibrationSessionJson.cs:6` stores a target, observations,
options, photos and optional confirmed fit. `CalibrationTarget.cs:21` embeds generation
parameters (family, radii, sectors, linear density, pitch, BD polarity, drawing limits,
timestamp, compatibility and usable sectors); `:190` has calibration schema 16.
`CalibrationSessionJson.cs:52` ties confirmed fit to a target while freezing original
generation geometry. These are not preset files: the importer refuses such documents
rather than treating observations or an unconfirmed candidate as a chosen calibration.

`DiscImageStudio.App/Services/BluRayPresetStore.cs:10` is a separate schema-1 nested
`parameters`/`luminanceMapping` format, with imports at `:42`. The active shared catalog
loader above uses `disc-presets.json`; searches found no construction of this separate
store in the active app. Legacy nested BD exports are therefore distinguished from flat
shared catalog entries; the new importer refuses them with a specific reason. Existing
DP BD preset wrappers are converted by the existing `bdexport.catalog_entry` helper.

## Interchange behavior and CLI

```powershell
python -m discprobe presets import disc-presets.json --dry-run --json
python -m discprobe presets import disc-presets.json --select 0 2 --directory presets
python -m discprobe presets import single-bd.json --media bd --dry-run
python -m discprobe presets export presets/<dp-file>.json --output exported.json
python -m discprobe presets export presets/<dp-file>.json --install --dis-presets temp/disc-presets.json
python -m discprobe presets export results/<geo>/summary.json --sectors 2295104 --correction correction.json --output exported.json
```

Indexes are zero-based and shared by preview, CLI selection and the page. Default import
selects valid, enabled entries; disabled ones require explicit selection. Invalid rows show
their reason and cannot be selected. A malformed document is refused before any write.
Duplicate ids are retained in preview; exclusive, opaque per-media/id filenames ensure
the first selected entry is kept and later conflicts are reported, never silently replaced.
Export output also uses exclusive creation. `--replace` applies only to deliberate DIS
installation and shares existing backup/merge rules. No new replacement flag bypasses
import protection. Machine `--json` values stay English/schema-stable with either language.
Human prose passes through the existing i18n catalog. Missing or future fields remain visible.

A standalone flat BD entry can omit `invertMapping`, making it indistinguishable from a
DVD entry that omits compatibility density. Use its whole catalog or choose `--media bd`
(the sheet has the same media selector). The importer refuses ambiguous standalone objects.
It expects canonical camelCase; DIS's case-insensitive aliases are a documented input limit.

The new `/api/presets` routes call these same functions. HTTP source paths stay inside the
workspace; uploaded text does not become a server-side input path. The sheet probes the route
and hides its single library entry on 404/offline servers. No server was started outside tests.
