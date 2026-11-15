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
  `fixture_sha256` refers to the decompressed JSON, preserving the original hash.

The 4096-square delta map is not a fixture or a runtime dependency. Generate it
with `python -B -X utf8 tools/focal_geometry.py`; it goes to
`D:/dp-dev/tmp/focal/cache/delta_map_1x.npy`. Set
`DISC_PROBE_FOCAL_CACHE_DIR` to override the cache directory. Only the parameters
and expected map SHA256 in `data/focal/pose_1x.json` belong in git.

`tools/focal_geometry.py --check` regenerates a temporary map in that cache
directory and checks its SHA256 and metadata without requiring a saved map.
It removes the temporary map and leaves existing cached files untouched.
