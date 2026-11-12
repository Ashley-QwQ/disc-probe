# Core and GUI versions

The GUI is a translator for the CLI. A GUI pack has its own name and version;
its version need not match the core release. The bundled GUI remains the default
for 1.0.0 alpha. `webui --gui PATH` selects a different pack.

`discprobe/version.py` owns the core release string (currently unchanged).
At release it can become `1.0.0-alpha.1`; pip normalizes that to `1.0.0a1`.
`discprobe/api.py` owns API_VERSION, capabilities and supported older majors.
`GET /api/version` and `disc-probe version --json` return the same payload.
No git checkout is needed.

An additive change raises MINOR. Give new feature groups a capability name.
Old GUIs ignore unknown capabilities. GUIs hide entry points whose optional
capabilities are absent. A missing required capability stops GUI startup.

A breaking change raises MAJOR. Removing or renaming a route, request field,
capability or response field, making an optional input required, changing field
types, units, meaning, event order guarantees or authentication is breaking.
An added optional field or route is additive. Fixing behavior to its documented
contract is normally a patch; change the major if a GUI must change to work.

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
