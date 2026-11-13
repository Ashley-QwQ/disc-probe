# Along-track burn grid report

Task: [along-track-grid.md](../codex-cards/along-track-grid.md). Base commit:
`e7f51a6b243ba4414cb4b377cf46f4ad2186f59b`, branch
`core/along-track-grid-20261113`.

DVD now selects 16 / 2 / 1-byte sampling (revised from 16 / 1 / 1, see the end) for 20 / 10 / 5 µm designs, from
`imagedisc.cell_mm(design)`. The 20 µm path retains the original sample centres,
chunk boundaries and expansion. BD selects 16 / 4 / 2 bytes respectively. CD's
12-symbol half-frame sampling and CIRC path are unchanged.

## BD choice

The existing BD model divides 30,066.75 channel bits uniformly over a sector's
2,048 user bytes. At 74.5 nm/bit that is 1.0937367554 µm per user-byte slice
(including the model's overhead allocation, rather than assuming 16 bits per
byte). Fine grids use powers of two below half a cell:

| Grid | BD group | Nominal step | Half a cell |
| --- | ---: | ---: | ---: |
| 20 µm | 16 bytes (legacy) | 17.500 µm | 10 µm |
| 10 µm | 4 bytes | 4.375 µm | 5 µm |
| 5 µm | 2 bytes | 2.187 µm | 2.5 µm |

The half-cell constraint applies to the new 10/5 µm BD steps. The 20 µm grid
retains its legacy step, following the card's "same idea" and unchanged-output
rule. An initial 8-byte choice at 20 µm broke the frozen `calibdisc1` baseline;
validation caught it and the 16-byte path was restored without changing the
baseline. DVD's nominal per-byte data step is 16 × 133.3 nm = 2.1328 µm;
sync and parity gaps remain in
`BYTE_BITS` and are not treated as drawable user bytes.

## Memory and texture behaviour

`calib.group_bits(group_bytes, media)` supplies group-dependent centres;
`sector_bits(media, group_bytes=16)` keeps its old default. All existing
16-byte constants remain available. Single-byte textures gather one uint8 byte
per sample and expand only when needed. Sequences, RND and MIX still use
`texture_bytes`, including the original `_COL` phase, without restarting a
sequence at group boundaries.

The chunk sample budget stays at 2048 × 128 points: DVD fine grids use 128
sectors per chunk; BD uses 2048 / 512 / 256 sectors for the three grids.
Coordinates and any int64 labels are chunk-local. There is no full-disc int64
label array. Existing file-backed worker sharing of large designs is retained.
The CLI still loads/copies the uint8 design and makes a preview, so finer grids
retain their existing whole-design memory costs.

`editor_ops.compose_file` already emits a square array whose side encodes its
cell size. No change to the compose route was needed. The image sidecar now
records `group_bytes` alongside `cell_mm`.

## Measurements

Measured on this **busy, shared machine** on 2026-11-13: Windows, Python
3.13.14, NumPy 2.5.1, 12 logical CPUs, 34.16 GB installed RAM, automatic six
writer workers. Other jobs were running; these are single runs, not isolated
performance guarantees. Available RAM varied from about 3.0–5.1 GB before to
11.8–12.1 GB after, so timing differences include changing host contention.

| Grid | Before image time | After image time | Before peak working set | After peak working set |
| --- | ---: | ---: | ---: | ---: |
| 20 µm | 26.6 s | 23.4 s | 0.585 GB | 0.585 GB |
| 10 µm | 26.7 s | 190.1 s | 1.234 GB | 1.276 GB |
| 5 µm | 46.2 s | 208.9 s | 4.656 GB | 4.674 GB |

Each run executes the real `python -B -m discprobe image` CLI, including design
loading, its existing uint8 copy, drawing-span checks, full ISO writing,
sample verification and preview. Each writes **2,295,104 sectors / 4,700,372,992
bytes**. Input generation is outside the timed interval: an identical physical
0.2 mm checkerboard at each grid, in the 25–58 mm annulus, uint8 labels B9/A5,
with a clearly synthetic geometry fixture. No real measurement is claimed.
All six CLI logs report successful sector verification.

Peak memory is the maximum sampled sum of resident working sets of the CLI
process and its descendants, sampled every 100 ms with psutil 7.2.2. GB is
decimal. This can count shared mapped pages in more than one process and can
miss a short transient; it is not a unique physical-page measurement. The raw
JSON also records sampled summed Windows private committed bytes (before:
3.106 / 3.004 / 5.022 GB; after: 3.102 / 3.047 / 5.040 GB). Private commit and
resident working set measure different things; the page's memory estimates
continue to describe working set, as its earlier measurements did.

Raw measurements: [before.json](before.json), [after.json](after.json); per-grid
CLI logs are beside them. Reproduce with
`python -B tests/bench_along_track_grid.py before|after` at the appropriate
source version. The script deletes its large scratch inputs/ISOs after each
run. It needs roughly 6 GB free disk and psutil; it never uses a drive/server.

The page's cost table describes **compose + image**. Retaining its previously
measured compose times (25 / 82 / 277 s on 2026-11-12), the new combined times
are approximately 48 / 272 / 486 s. Updated rounded estimates are **2 / 6 / 10
minutes**, with the existing **1 / 2 / 5 GB** working-set estimates retained.
Composition was not remeasured in this task. Only cost numbers and their
measurement comment changed in `design/export-rules.mjs`.

## Callers of the group constants and offsets

Inventory covers `discprobe`, `tests`, `tools` and the build backend sources,
including indirect callers of `sector_bits` (none in tools/build backend):

| Caller | Sampling now used |
| --- | --- |
| `calib` module's `GROUP_BITS`, `GROUP_BITS_BD` definitions | Original 16-byte arrays, unchanged. |
| `calib.group_bits` / `sector_bits` | Requested divisor of 2048; default 16 returns the original constants. DVD averages `BYTE_BITS`; BD divides its own sector track. |
| `calib._band_sectors` | Still uses `GROUP_BITS` and expands by `GROUP_BYTES=16`; calibration generation is unchanged. |
| `imagedisc.group_bytes` | Uses legacy 16 as the DVD coarse step and BD maximum, then chooses from the design's cell size. |
| `imagedisc._sample` | Calls `sector_bits(media, group_bytes(design, media))`. |
| `imagedisc._sector_q` | Expands by the selected group size, with per-byte direct output for single-byte textures. No constant `GROUP_BITS` use remains. |
| `imagedisc.write_iso` | Scales chunk sectors by selected group size / legacy 16 to cap sample memory. Its workers and verification call the same sampler. |
| `calibdisc.write` (indirect image-writer caller) | Its default 20 µm BD calibration stays at 16 bytes, including the frozen split-disc ISO baseline. |
| `imagedisc.sectors_to_radius` | Uses only the sector-bit count from default `sector_bits`; geometry and 16-sector capacity alignment are unchanged. |
| `randomlabel.Label.patch` | Still imports `GROUP_BITS` / `GROUP_BYTES` and samples/expands at 16 bytes. Frozen output hash matches. |
| `template.geometry` | Uses only `sector_bits(kind)[0]` for non-CD capacity geometry; unchanged. |
| `tests/test_perf2.py` reference sampler and texture checks | Default 16-byte reference, on its coarse 317 × 317 synthetic design; unchanged. |
| `tests/test_along_track_grid.py` | Checks legacy constants, dynamic DVD/BD offsets, chosen steps and bounded chunks. |

## Validation

All 31 `node tests/*.mjs` / `tests/*.cjs` files passed (only
`tests/editor_runner.mjs` excluded as requested). See
[node-results.json](node-results.json) and individual file logs beside it.

The requested full `python -m pytest -q tests` run finished in 500.98 s:
**729 passed, 2 failed, 1 skipped, 182 subtests passed**. See [pytest.log](pytest.log).
The failures were:

- `DiscIdTests.test_baseline_calibdisc1`: caught the initial 20 µm BD 8-byte
  choice described above. The implementation now retains 16 bytes; the frozen
  baseline file was not edited.
- `BackendTests.test_lan_every_request_requires_token`: Windows aborted a local
  test-server connection with `WinError 10053`. The same test passed on its
  isolated rerun, without changing server or test code: **1 passed in 1.90 s**,
  [lan-rerun.log](lan-rerun.log).

The post-correction regression run passed: **88 passed in 194.13 s**. It covers
`test_along_track_grid.py`, `test_cell_size.py`, `test_perf2.py`, `test_discid.py`,
`test_random_label.py` and `test_cd_clv.py`; see [regression.log](regression.log).
This includes the previously failing frozen BD calibration hash.

The final complete rerun passed with the compatibility correction in place:
**731 passed, 1 skipped, 182 subtests passed in 1142.65 s (19:02)**. See
[pytest-final.log](pytest-final.log). This includes the existing CD tests and
both frozen BD calibration baselines. The initial failure count above is
retained for provenance. Both full runs used the same worktree-local temp
configuration (the final basetemp was `tests/.pytest-along-final`); this busy,
shared machine's runtime varied substantially between runs.

Initial focused tests: 21 passed, including the existing cell-size and
performance-identity tests. The old fine-copy test was updated
to retain identity inside uniform groups while allowing newly resolved edges.

The stripe tests independently compute byte positions using `BYTE_BITS` and
`theta`, then check the recorded bytes after scrambling/descrambling. At 5 µm,
10 µm stripes alternate as predicted; the legacy 16-byte reference disagrees
with more than 30% of byte labels. Tests cover single-byte, phased sequence,
RND and MIX textures, plus BD byte positions.

[Frozen baseline hashes](../../tests/data/along-track-grid-baseline.json) were
captured before editing production code: 24 DVD 20 µm cases (four LBA locations,
three texture sets, correction on/off), three sectors each, plus a four-sector
`randomlabel` patch. All match after the change. Full-DVD benchmark sector
hashes independently compare four sectors each at LBAs 32, 500003 and 2145149;
all three DVD 20 µm hashes match before/after. Fine-grid hashes change at the
two non-background sample locations, as expected from finer sampling.

The sandbox denied pytest's default
`C:\Users\Administrator\AppData\Local\Temp\pytest-of-Administrator` directory.
Focused tests passed with an explicit worktree-local `--basetemp`. The full
run used `PYTEST_ADDOPTS=--basetemp=tests/.pytest-along-full` and worktree-local
`TEMP` / `TMP`; the command itself was `python -m pytest -q tests`.

## Physical verification still needed

No hardware was accessed and no burn was performed. A real DVD burn should
check 10 µm checkerboards, 5 µm lines and texture transitions at multiple radii,
including sync/parity boundaries. Confirm the unchanged 20 µm DVD appearance.
BD needs an actual burn to validate the equal-track-slice approximation,
especially transitions across its parity/cluster structure; smaller software
samples do not establish physical BD resolution. Compare broad coloured areas
and phase continuity on both fine grids. A single 5 µm cell cannot establish
visible colour. CD remains limited to about 80 µm along-track sampling.

Changes remain uncommitted. No commit, push, stash, reset or branch switch was
performed; `discprobe/scsi.py` was not edited. No servers were used outside
tests and none of the prohibited ports were used.

Command policy blocked recursive scratch deletion. Generated screenshots and
temporary files are instead preserved by reversible moves under the ignored
`tests/.along-grid-artifacts/` folder, keeping them out of the source diff.

## Revision: DVD 10 µm uses 2-byte steps (2026-11-13, reviewer)

The person chose to cut the 10 µm cost. `imagedisc.group_bytes` now applies the
same rule to DVD as to BD: the largest power-of-two step whose track length
stays below half a cell, with 16 channel bits per DVD byte (2.133 µm). That is
2 bytes (4.27 µm) at 10 µm and 1 byte at 5 µm; 20 µm keeps 16. A pair that
straddles a sync code spans 48 bits, so each byte is still within 3.2 µm of
its sample.

Re-measured full DVD (`after.json`; the per-byte run is kept as
`after-perbyte10.json` and `after-perbyte10-*um.log`):

| Grid | Per-byte 10 µm | 2-byte 10 µm |
| --- | ---: | ---: |
| 20 µm | 23.4 s, 0.585 GB | 23.8 s, 0.581 GB |
| 10 µm | 190.1 s, 1.276 GB | 88.5 s, 1.273 GB |
| 5 µm | 208.9 s, 4.674 GB | 167.0 s, 4.675 GB (same code; host noise) |

20 µm sector hashes still equal the "before" run. The page's 10 µm estimate is
back to 4 minutes; 5 µm stays at 10.

Tests changed with it: the stripe test computes its expectation at the chosen
step; `test_cell_size` now allows under 1 % of uniform fine groups to differ
from the coarse sample, because a 34 µm group centre can clip a feature's
corner that the 4.27 µm samples pass beside (seen: 1 of 410).
