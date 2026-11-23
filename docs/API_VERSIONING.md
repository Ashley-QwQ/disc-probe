# Core and GUI versions

The GUI is a translator for the CLI. A GUI pack has its own name and version;
its version need not match the core release. The bundled GUI remains the default
for 1.0.0 alpha. `webui --gui PATH` selects a different pack.

`discprobe/version.py` owns the core release string (currently unchanged).
At release `tools/release.py --version` writes the four-part public version into the frozen copy,
e.g. `1.0.0.0-alpha`; pip normalizes that to `1.0.0.0a0`. API_VERSION below is a separate number.
`discprobe/api.py` owns API_VERSION, capabilities and supported older majors.
`GET /api/version` and `disc-probe version --json` return the same payload.
No git checkout is needed.

API 1.2 adds the optional `geo-coverage` capability. The `geo_point` job event carries
`rung` (one-based), `lba`, `radius_mm`, `residual_deg`, and `sigma_deg`. A calibration
job accepts `args.resume` with a local geometry result path to read missing radii.
Geometry job measurements can include `missing_mm` and `can_resume`. Catalogue
rows can include `measured_intervals_mm`. Older readers can still use `measured_mm`.

An additive change raises MINOR. Give new feature groups a capability name.
Old GUIs ignore unknown capabilities. GUIs hide entry points whose optional
capabilities are absent. A missing required capability stops GUI startup.

A breaking change raises MAJOR. Removing or renaming a route, request field,
capability or response field, making an optional input required, changing field
types, units, meaning, event order guarantees or authentication is breaking.
An added optional field or route is additive. Fixing behavior to its documented
contract is normally a patch; change the major if a GUI must change to work.

API 1.2 adds `burn-preflight`. `POST /api/burn-check` accepts a burn or
calibrate-with-ISO request and reports the current disc, available speeds and a
bilingual `gate` when something needs attention. It performs read-only checks.
To accept an `other_batch` warning, echo the actual MID as `args.confirmed_mid`
in both `/api/burn-token` and `/api/run`. The token binds the resulting request
to the checked disc and ISO. Refusals can carry the same object as `burn_gate`
in error responses and job events.

API 1.3 adds optional `measurement-retry` metadata. Timing and geometry
measurements can include `retry_kind` and `failed_rung` (one-based). Timing's
`speed_advice` and geometry's optional `retry_speed_advice` can list
`lower_speeds` in kB/s. `can_resume` still means the core can attempt
a continuation on the original disc, drive and read settings. A completed
measurement job snapshot may include `diagnostics.argv` and a workspace-relative
`diagnostics.log_path`. These describe the job that ran.

API 1.4 adds optional `library-management`. `POST /api/library` takes
`{operation:"preview", id}` to return the batch's files, shared files,
dependent works and a revision. Delete uses `{operation:"delete", id, revision,
with_works}` and returns a `trash_id`. Restore uses `{operation:"restore",
id:trash_id}`. The web route uses the reversible operation. Measured catalogue
rows can also include `drive_id`, `capacity_sectors`, `capacity_source` and
`calibration_issue`. The old `sectors` field on measured rows still describes
the recorded area. An incomplete result uses `s:"incomplete"`.

API 1.5 adds optional `library-batch-details`. Usable CD geometry catalogue
rows report `along_track.known` from photo evidence accepted for that run.
Measured rows may include `media_kind` from a saved disc report.
`/api/presets` with `operation:"export"` accepts optional `name` and `sectors`
when exporting a geometry summary directly to a DIS preset.

API 1.5 also adds optional `grid-templates`. `POST /api/template` accepts a `grid`
of 5, 10 or 20 µm for a disc-centred, 120 mm RGBA canvas and a separate guide
PNG, returned in one ZIP. The legacy request still produces the original
template bundle. `POST /api/template-preview` accepts a full-size PNG as
`image/png` and returns a small preview plus its artwork bounds in millimetres
in `X-Discprobe-Artwork-Bounds` (JSON array or null). This is a read-only
operation. For native-pixel composition an image layer can include an optional
`gridPng` PNG data URL alongside its existing preview raster.

API 1.6 adds optional `colour-input-icc`. `POST /api/colour-input` accepts a
PNG, JPEG, WebP or BMP body up to 24 MiB and 36 million pixels. It returns
204 for an untagged image, or 200 with an sRGB PNG and an ASCII JSON
`X-Discprobe-ICC` header containing `{"profile":"…"}` or `{"fallback":true}`.
`POST /api/template-preview?icc=1` opts into the same conversion and header
for a native-grid template preview. Requests without that option keep the
previous response. These operations are read-only.

API 1.6 also adds optional `photo-burn-recovery`. `GET /api/photo-burns?run=ID`
lists eligible completed DVD check-disc burns for a geo run, newest first.
Each row contains `id`, `time` (Unix seconds), `burner`, `path`, `mode`,
`disc_id` (string or null), `log_path` and `source`. The reply also lists
`unavailable` reason codes. A photo job can supply `args.burn_record` with
the selected ID instead of the three explicit burn fields. If supplied,
`args.disc_id` takes precedence over the saved number. Photo uploads,
listings, phone links and device lists accept an optional `burn_record`
query parameter for photos taken under the selected burn.

API 1.6 also adds optional `starter-preset`. The DVD-only `/api/run` action `starter`
lists sources for the blank in the specified drive. Supply `args.source` to
select one explicitly and receive the workspace-relative starter path. A DVD
`info` result can include `starter_candidates` for the blank it read. A starter
check-disc burn emits `starter_burn` with its disc number. Analyzed
starter photos return `starter.written` and `starter.reason`. A confirmed
starter appears in the DVD catalogue with `starter`, `starter_source`, and
`checked_mm`. The normal `geo` and `photo` job formats remain valid.

Proposed policy: retain working adapters for the previous MAJOR for at least
six months after the new major's first stable release. Publish its retirement
date with that release. List only majors with actual working adapters in
`supported_older_api_majors`. It is empty for API 1.0 because no prior public
major exists. Listing a major alone does not make an incompatible API compatible:
future adapters must expose that major's complete contract and version endpoint.

Test every supported core release with its current GUI and the previous released
GUI. Archive released GUI packs as immutable fixtures. For API 1.0's first release,
there is no previously released manifest-bearing GUI; this row is not applicable
until the next release. Also test rejected majors, missing required capabilities
and hidden optional entry points. A future major must test its old-major adapter
against the archived previous GUI before claiming support.

## Pack contract

A GUI folder contains `gui.json` and `home/index.html`. Static paths are relative
to that folder, including `fonts/` and `phone/index.html` if used. The manifest has
`name`, `gui_version`, `required_api`, `required_capabilities` and
`optional_capabilities`. Capability lists contain unique lowercase names and do
not overlap. API versions are MAJOR.MINOR. The range grammar is space-separated
AND comparisons: `>=`, `>`, `<=`, `<`, `=` followed by a major or major.minor;
an omitted minor means zero. Example: `>=1.0 <2`. OR, wildcards and prerelease
API versions are not supported.

The core validates the manifest before listening. Each served GUI must fetch
`/gui.json` and `/api/version` before starting its workflow, and show one translated
update sheet on incompatibility. A core below the range or missing a required
capability needs updating; a core above the range needs a newer GUI. Optional
entries carry `data-capability`, so hiding also applies to dynamically mounted UI.
File-based developer previews may run without a core. External GUI packs are
local code chosen by the person; manifest validation is a compatibility check.

## Source installation

`pipx install disc-probe` will be the public installation once that name is
published. A checkout supports `python -m pip install .`; the command is
`disc-probe`, with the same arguments as `python -m discprobe`.
NumPy and Pillow support timing/drawing; SciPy and OpenCV are needed by the photo
reader, which imports them directly. All four are included in the default pip
dependencies so the bundled GUI's photo capability is available.

The PEP 517 backend uses only the standard library (no build downloads). It builds
wheels and source archives with the GUI, fonts, presets, LUTs and helper scripts.
Offline installation also needs locally available dependency wheels.
