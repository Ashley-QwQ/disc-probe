# Task card: the burn grid's 10 and 5 µm also apply ALONG the track (DVD and BD)

Worktree: `D:/disc-probe/.claude/worktrees/along-grid`, branch `core/along-track-grid-20261113` (from e7f51a6).
- Do NOT commit, push, stash, reset or switch branches.
- No drives, no burns, no servers outside tests. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863.
- Do NOT edit `discprobe/scsi.py`.
- Edit only `discprobe/calib.py`, `discprobe/imagedisc.py`, `discprobe/editor_ops.py` (only if the compose → image
  path needs the cell size passed on), `discprobe/__main__.py` (help text), `discprobe/web/home/design.js` (the grid
  help words only), docs and tests.

## Why
The writer samples the design once per 16-byte group (`calib.GROUP_BYTES = 16`): on a DVD that is 256 channel bits,
about 34 µm of track. The page offers 20, 10 and 5 µm cells, so at 10 and 5 µm the drawing is finer only ACROSS the
track (tracks are 0.74 µm apart) and still 34 µm steps ALONG it. A community burn (LTVA1, GU70N, Ritek DVD+R) with a
one-off patch, `CELL_MM = 0.005` and `GROUP_BYTES = 1`, showed 10 µm checkerboards cleanly and 5 µm lines resolved
under a microscope. So per-byte steps can be written. The person chose: make the along-track step follow the grid.

## Do
1. **DVD.** With a 10 or 5 µm design, sample per byte (`GROUP_BYTES` = 1, about 2.13 µm of track). A 20 µm design
   keeps 16-byte groups (unchanged output: a 20 µm ISO must stay byte-identical to today's). Derive the step from the
   design's cell size (`imagedisc.cell_mm` / `check_cells`), not from a global. `calib.GROUP_BITS` becomes a function
   of the group size (keep the 16-byte constants for existing callers: `randomlabel.py` measurement images stay at
   16).
2. **BD.** Same idea with its own group slicing (`GROUP_BITS_BD`). Per-byte BD is about 1.2 µm at 74.5 nm/bit, so a
   2-byte step is enough for 5 µm. Choose the BD step so one step stays below half the cell, and say what you chose.
3. **CD.** Unchanged. Its unit is a 12-symbol half-frame (`cdimage.py`), about 80 µm along the track, set by the
   CIRC interleave. Do not change it.
4. **Textures stay phased by column** (`_COL`), so a repeating sequence runs on across byte steps; single-byte
   textures have no phase. Keep the fast path for single-byte textures (expand per group) and make the per-byte path
   memory-safe for a full disc at 5 µm: work in sector chunks, no full-disc int64 label arrays.
5. **Words.**
   - The page's grid help (`design.js` grid / cellCost / precCost strings, zh + en) says plainly:
     - "10 / 5 µm：DVD 和 BD 沿轨、半径两个方向都更细；CD 沿轨最细约 80 µm，只有半径方向更细";
     - "彩色材质需要成片的区域，单个 5 µm 小格看不出颜色".
   - The CLI `--cell-um` help says the same.
6. **Cost.** Measure the `image` time and peak memory for a full DVD at 20 / 10 / 5 µm, before and after, on this
   machine (busy, shared; say so). Put the numbers in the report and keep the page's time estimates (`design/export-
   rules.mjs` cost table) honest: update them if they change a lot. That file may be edited for those numbers only.

## Tests
- A synthetic 5 µm design with stripes alternating every 10 µm ALONG the track gives alternating textures in the
  recorded bytes at the expected byte positions (compute the expected positions from `BYTE_BITS` and theta). The same
  design at 20 µm sampling would blur them.
- A 20 µm design's output is byte-identical to before (hash a few sectors of a small synthetic case before and after).
- CD unchanged (existing CD tests).
- BD step as chosen.
- `randomlabel` unchanged.
- Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs` (skip `tests/editor_runner.mjs`). If your
  sandbox blocks pytest's temp dirs, say so; the reviewer runs it.

## Done means
Tests pass (or blocked parts reported), and you report:
- the numbers (time and memory at 20/10/5 µm);
- the BD step;
- every caller of `GROUP_BYTES` / `GROUP_BITS` and what it now uses;
- anything that should be verified on a real burn.
