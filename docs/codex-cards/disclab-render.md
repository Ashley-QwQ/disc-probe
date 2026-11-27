# Task card: Disc Lab renders any recorded texture, so the check disc can be photographed

Worktree: `D:/disc-probe/.claude/worktrees/disclab-render`, branch `dev/disclab-render-20261113` (from Disc Lab 2ec80ce).
Two other Codex runs work in sibling branches: one on scenarios/faults (owns `box.py`, `drive.py`, `faults.py`, `scenario.py`), one on a TUI/practice/`--json` (owns `tui.py`, `practice.py`, `jsonout.py`, `API.md`). **You own `disclab/photos.py`, `disclab/burnmap.py`, `disclab/tables.py`, `disclab/data/`.** Do not edit the others' files; keep any `__main__.py` change to one small block.

## Hard rules (keep unchanged)
- Do NOT commit, push, stash, reset or switch branches.
- Do not edit anything under `discprobe/`. `docs/goals/` in the main checkout (`D:/disc-probe/docs/goals/...`) is read-only: read the A3 wave model there, never write.
- No real drives, no burns, no network, no servers. Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- At most 4 CPU-heavy processes (the other two Codex runs share this machine: keep your own renders and reads to 2 workers). Do not use any word starting with "blin" in commands or paths (a hook blocks it).
- Photos of today's A5 / B9 / random-data discs must stay pixel-identical for the same seed and pose (add a regression test with stored hashes before you change anything).
- The pcal reader and the majority rule are not yours to change; only the renderer.
- Never touch `evidence/atlas/*.py` anywhere (a texture search is running from it; a change makes its workers exit).

## Why
Disc Lab's renderer only knows A5, B9 and random data (`TEXTURE_BYTES`, `burnmap` stores one byte or `MIXED`). The photo check disc that disc-probe now writes (`checkdisc`, the PCAL-C round-2 target, branch `web/main-path-fixes-20261113`) uses nine multi-byte RITEKF1 textures plus RND; Disc Lab renders it blank, the reader finds nothing, and neither the lab's photo loop nor the practice mode can reach "photograph → L → picture with L". The same real target was read from real phone photos: 6 of 11 accepted (`D:/disc-probe/docs/goals/pcal-2026-11-12/photos/`).

## What to do
1. **Burn map with texture identity.** Record, per map cell, which texture is there, not only one byte: for an ISO written by disc-probe's image/checkdisc path, the sidecar (`.image.json`) gives the texture list and the design; otherwise classify each sampled run of recorded bytes by its repeating period and content (single byte, multi-byte period ≤ 64, random). Keep the old codes for single bytes so existing maps and photos are unchanged.
2. **Spectra for any texture: the A3 v3 colour model, as agreed with the user.** Use the repository's own copy, `docs/texture-cards/scripts/wave_model.py` on `origin/main` (PR #38 made its paths repository-relative; the local `main` branch is behind, so do not rely on the working tree). Export it read-only with `git -C D:/disc-probe archive origin/main docs/texture-cards tools/dsv_block.py | tar -x -C C:/disc-probe-scratch/a3-wave/` (a new folder) and import it from there, with a `discprobe` that has `efmplus` and `dvd`. Interface (`import wave_model as M`):
   - `mass, rec = M.texture_mass(spec)`: hex byte sequence → power of the spectral lines on `M.F`, from real EFMPlus, scrambling and DSV over 8 ECC blocks. Slow (seconds to tens of seconds per spec): cache per spec as npz, key = spec + `M.signature()[0]`.
   - `op, meta = M.build_operator()`: the lamp / observer / aperture operator, once, cached (never write its `save=True` output into any repository).
   - `xyz = M.xyz_from_mass(mass, op)`: shape (1025 deltas, 2 lamps, 3), delta grid `M.DELTA` (0.10-0.95), lamp 0 = LED, 1 = D65; all diffraction orders included.
   Rendering: keep Disc Lab's own optics for the pose, refraction and warp; for each pixel take its along-track delta (Disc Lab's delta_t; it should agree with `discprobe/simulate.py::along_track` for a flat disc - check and report), interpolate the pixel's texture XYZ on `M.DELTA`, weight by that texture's area share in the pixel, sum, convert to linear sRGB, apply one fixed exposure per image, encode. A delta outside 0.10-0.95 is dark (XYZ 0), never extrapolated. Ship precomputed tables for the ten check-disc textures (and A5, B9, RND recomputed the same way only if that leaves today's A5/B9/RND photos identical; otherwise keep today's tables for those three and say so) under `disclab/data/`, so users need no A3 source; computing a new spec needs the exported source and says so plainly when it is missing.
   **Flash position:** Disc Lab used 34 mm; the user has now settled on Apple's drawing, lens to flash (-43.66, 19.79) mm = 47.9 mm. Make the offset a pose parameter with 47.9 mm (Apple drawing, (-43.66, 19.79) mm) as the default — the user confirmed 34 mm was a misheard guess, not a measurement — and report how much L and acceptance change at 34 mm as a sensitivity check.
   **Honesty:** the v3 model is a prediction not yet validated by real photos; state in the README and report that simulated colours must not be used to calibrate a real disc.
3. **Zero order / brightness** for multi-byte textures: use the same model terms as today (`tex_gain`, the A5/B9 darkening rule generalised by mark density, stated as an assumption).
4. **Validation**, run against disc-probe from `D:/disc-probe/.claude/worktrees/main-path` (which has `checkdisc` and the wide geo): in a scratch folder put a `disclab` copy (or your worktree's) beside a junction/copy of that `discprobe`, as `C:/disc-probe-scratch/lab-mp` already does. Then: box of 3 DVD-R → measurement disc → default `geo` → `checkdisc` → burn on 2 discs → render 6 handheld photos each → read with the default reader → score L against the truth. Report acceptance rate, errors, false accepts, and compare with the real PCAL-C photos (6/11 accepted) and with the lab's own simplified target. Do not tune the renderer to make the reader accept; report what it does.
5. Tests: the regression hashes for A5/B9/RND photos; texture classification on synthetic maps; a multi-byte texture table matches a direct wave-model computation for one spec; a tiny end-to-end render of a check-disc region is not blank.

## Acceptance
- `python -m pytest disclab/tests -q` all pass (report counts).
- `disclab/RENDER_REPORT.md` (Chinese, plain words first): what changed, the validation numbers, which parts are modelled vs assumed, and a few contact-sheet images of rendered check-disc photos next to a real PCAL-C photo (thumbnails only, under `disclab/docs-img/` or the scratch folder, small files).
