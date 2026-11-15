# Offline focal regression evidence

These files support tools/tests; the application does not load them.

- `show_e_samples.json.gz`: frozen SHOW-E cells, losslessly compressed with gzip
  (`mtime=0`). SHA256 of the decompressed original JSON:
  `3b588faad2d978ab4664f87fae65065c4f2e111f90ff681b243eca744566035e`.
  `tools/focal_capture.py` can refresh this fixture from the original read-only
  sources, but is not part of normal focal recalibration.
- `show_e_preview.npz`: the unchanged compressed 600-square label sample.
- `regression.json`: generated numerical evidence, retained for review. Rebuild
  with `python -B -X utf8 tools/focal_regression.py --out tools/focal_data`.
  `fixture_sha256` refers to the decompressed JSON after CRLF-to-LF normalization:
  `b6cdc031d5370f8c76017c72c9eb98b5c2033bbd998aa71aa320e137beb200de`.
  The frozen compressed file and the original-byte hash above are unchanged.

Focal generators use `discprobe.hashing`: the explicit, case-insensitive
`TEXT_SUFFIXES` allowlist normalizes CRLF to LF before SHA256. Other bytes are
unchanged, including lone CR, whitespace and BOMs. Binary/unknown extensions
(including `.npz`, `.npy`, `.bin`, `.gz` and `.pdf`) use exact original bytes.
The decompressed fixture uses its logical `.json` extension. Existing hashes
inside frozen historical fixtures/recipes retain their original meaning;
`focal_capture.py` checks those recipe inputs byte for byte before recording new
portable provenance. Palette `sets_sha256` hashes canonical JSON content rather
than a file and is unchanged.

The 4096-square delta map is not a fixture or a runtime dependency. Generate it
with `python -B -X utf8 tools/focal_geometry.py`; it goes to
`D:/dp-dev/tmp/focal/cache/delta_map_1x.npy`. Set
`DISC_PROBE_FOCAL_CACHE_DIR` to override the cache directory. Only the parameters
and expected map SHA256 in `data/focal/pose_1x.json` belong in git.

`tools/focal_geometry.py --check` regenerates a temporary map in that cache
directory and checks its SHA256 and metadata without requiring a saved map.
It removes the temporary map and leaves existing cached files untouched.
