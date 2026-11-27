# Task card: one release, three packages, four-part version

Worktree: `D:/disc-probe/.claude/worktrees/release-packs`, branch `core/release-three-packs-20261113` (from release/1.0.0-alpha daa13a2).
Plan agreed with the user: GitHub release tag `v1.0.0.0-alpha` (pre-release) carrying three packages built in one run of `tools/release.py`, sharing one `manifest.json` and one `SHA256SUMS.txt`.

## Hard rules (keep unchanged)
- Do NOT commit, push, tag, publish, stash, reset or switch branches. No network, no downloads.
- No drives, no burns. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- Do not edit `discprobe/` except `discprobe/version.py` handling if strictly needed for the version format (prefer handling it in the tools). `tools/build_winpack.py` keeps building only the Windows full and core zips.
- All existing release gates stay: clean tree, snapshot from the commit, wheel proof, full pytest, Node, selftest, Windows trim checks. Nothing becomes an asset before every gate passes.
- At most 4 CPU-heavy processes. Do not use any word starting with "blin" in commands or paths (a hook blocks it).

## What to do
1. **Four-part version.** `release.py --version` must accept `1.0.0.0-alpha` (and keep accepting the old forms). Public version string `1.0.0.0-alpha` (asset names, `version.py` in the snapshot, GUI handshake). The wheel/sdist version is the PEP 440 form `1.0.0.0a0`; check what the build backend (`_build_backend`) derives and make it right. Check `discprobe.api` version parsing (`_VERSION` regex) and the GUI handshake still accept it; add tests.
2. **Disc Lab asset** `disc-lab-<version>.zip`: from the same frozen commit, export the `disclab/` directory (it will be merged in before the release; until then, make the step skip with a clear message when `disclab/` is absent, and add a test using a tiny fake `disclab/`). Gate: unpack it next to the built wheel's install (or the core snapshot) and run `python -m pytest disclab/tests -q`; failure blocks the asset.
3. **Disc Neo asset** `disc-neo-<version>-preview.zip`: `--neo DIR` (or `DISC_NEO_DIR`) points at a staged folder prepared by another session (`C:/disc-probe-scratch/disc-neo/`, top folder `disc-neo/` with README.md, README.zh.md, SCHEMA.md, PROVENANCE.json, LICENSE, atlas/dvd/..., texture-cards/...). The tool only zips it: refuse when README.md, README.zh.md, SCHEMA.md, PROVENANCE.json or LICENSE is missing; record every file's size and sha256 in the manifest under a `disc_neo` section; never modify the staged folder. Without `--neo`, build the other assets and say Neo was skipped (the manifest records `skipped`).
4. **Manifest and sums** cover all assets of all three packages; the manifest says which package each asset belongs to.
5. **Release notes skeleton**: write `tools/release_notes_template.md` (Chinese and English sections) with one section per package: what it is, who it is for, which file to download, install, status (alpha / developer tool / preview data, "predicted, not photographed"), known limits, checksums. Placeholders in brackets for numbers decided at release time. Do not invent results.
6. Tests for the version forms, the Neo refusal/skip paths and the Disc Lab skip path. Do not run the full multi-hour release; a dry check of argument handling and the new steps on small fakes is enough, plus `python -m pytest -q` for the repository.

## Acceptance
- `python -m pytest -q` all pass; report counts.
- A report at `docs/release-three-packages/REPORT.md` (Chinese): what changed, the asset names a real run will produce, what was not run (the full release build).
