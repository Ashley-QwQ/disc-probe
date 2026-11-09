# Blu-ray geometry from one BD-RE, and the preset DiscImageStudio needs

> **Read this with the correction in mind.** This note was written from the first BD-RE, before the
> spare area was understood. The 24.677 mm inner radius below is what the timing gave; the disc is a
> formatted BD-RE, and pulling back its 4096-cluster ISA0 spare area (131,072 sectors) puts sector 0
> at **24.0485 mm**, 0.5 um from a pressed BD-ROM of the same size. Section 6 of
> [`BD_CLV_GEOMETRY_SOLVER.md`](BD_CLV_GEOMETRY_SOLVER.md) has the corrected reading and the current
> test counts; the explanation of *why* the radius sits outward is the part this note got wrong.

Phase-2 deliverable. The disc in `G:` is a single-layer BD-RE holding 12 088 320 sectors, read by a
MATSHITA BD-MLT UJ272 at a constant linear speed. This note records what that one disc yields: the
model, the numbers, how they were checked, and what is still missing. Everything here was measured
read-only; the drive was never ejected and nothing was written.

## What was measured

`geo --media bd` times one revolution at a series of sector addresses and fits

    T^2(lba) = (2 pi r0 / v)^2 + (4 pi p L / v^2) lba        (L = 2.239973 mm per sector)

which gives two numbers (slope `a`, intercept `b`). With the standard pitch `p = 0.320 um` as the
anchor, `r0` and `v` follow; the ratio `b/a = pi r0^2/(p L)` has no `v` in it at all.

| quantity | measured | standard says | comment |
| --- | --- | --- | --- |
| inner radius of sector 0 | **24.677 mm**, four 25-zone runs spanning 28.5 um (24.6624 / 24.6898 / 24.6655 / 24.6909) | 24.0 mm for a full layer | this disc is 1.07% short of a full layer, so its sector 0 sits further out; see below |
| outer radius at the last sector | **58.024 mm** | 58.0232 mm (DIS `bd-r-sl-25gb`) | 3 um apart |
| track pitch | 0.3200 um (anchor) | 0.320 um | anchored, not measured in this run; the outer-edge check covers it |
| linear speed at 2.1x | 10.390 +- 0.002 m/s | 10.33 m/s for 2.1x (4.917 m/s at 1x) | 0.6% high, within the 2.1x binning of the drive |
| total sectors | 12 088 320 | 12 219 392 for a full single layer | 131 072 fewer, 1.07% |

Why 24.677 and not 24.0, as this note first read it: the spiral of this disc is shorter than a full
layer's in the same physical data area, so it starts further out. (The shorter spiral is a formatted
disc's inner spare area, not a smaller physical extent -- see the note at the top.) The consistency check is that the outermost sector then lands at
58.024 mm against the 58.0232 mm of DiscImageStudio's built-in BD-25 preset -- 3 um apart -- and read
the other way, a 58.0232 mm outer edge with this sector count implies an inner radius of 24.6698 mm,
7 um (0.5 sigma) from what the timing measured.

## How the numbers were checked

1. **Repeatability.** Four 25-zone runs at 2.1x: 24.6624 / 24.6898 / 24.6655 / 24.6909 mm. Spread
   28.5 um, against a fit tolerance of 13.7-15.1 um per run. A fifth 25-zone run at 1.6x gives
   24.6575 +- 0.0145 mm, 19.7 um lower -- which also bounds any constant period offset at ~50 us.
2. **Two speeds, no anchor.** At 1.6x the slope and intercept both grow by (2.1/1.6)^2, and `b/a`
   -- the speed-free combination -- agrees with the 2.1x runs to 0.15%, i.e. 20 um of radius. A
   tenth run asked for 1x and the drive floored it at the same 7.91 m/s (24.6635 +- 50 um), so this
   drive offers two speeds and the two-speed check cannot grow a third arm.
3. **Capacity.** The measured inner radius matches what the sector count and the 0.320 um pitch
   imply for a 58.0232 mm edge (section above), without any parameter tuned to make it so.
4. **Against the tree.** The thirteen BD runs already in this repo (39 zones, three per run) give
   outer-zone speeds of 10.33-10.36 m/s; this disc reads at 10.39 m/s, 0.3% apart.

5. **All the runs, one shape.** `tools/bd_pool.py` fits nine runs of this disc for a single shared
   `k = pL/(pi r0^2)` and gets `r0 = 24.662 mm` (formal 0.9 um), while the runs fitted one at a time
   stretch from 24.6475 to 24.7395 mm. The 92 um spread is the honest error bar: the pooled
   covariance does not know that each run carries its own offset.

## What the model cannot do

- **A period offset is not identifiable.** An offset and the starting radius trade off over a few
  millimetres of span: a fitted offset of -246 +- 104 us moved the inner radius by 0.41 mm. The fit
  now applies an offset only at 3 sigma and reports both numbers.
- **Zonal reading is refused, not fitted.** A Z-CLV disc gives a `T^2` line with a step; the break
  detector reports it and `disexport --install` refuses the preset.
- **Two layers are not handled.** A layer change is a jump in the map and no run crosses one.
- **The pitch is an anchor.** Pass `--linear-mm-s` with an independently measured speed to make the
  pitch the measurement instead (`p = a v^2/(4 pi L)`); then the tolerance follows `sigma_p`.

## What DiscImageStudio receives

`disexport --geo <run> --sectors 12088320` writes a `blu-ray-presets.json` record:

```
parameters: totalSectors 12088320, layerCount 1, innerRadiusMm 24.6655, outerRadiusMm 58.0214,
            startAngleDegrees 0
```

and no pitch coefficients: they are relative shape factors in DiscImageStudio, so a constant 0.320 um
pitch is expressed by leaving them at zero and letting the engine solve the pitch from the three
numbers. `--install` adds the record to `%LOCALAPPDATA%\DiscImageStudio\blu-ray-presets.json`, a
file of its own, separate from the CD and DVD `disc-presets.json`.

## Verification state

| thing | state |
| --- | --- |
| model, estimator, tests | `selftest` 1038 ok; `tests/test_bd_clv_solver.py` 15/15; `tests/test_bd_preset.py` 17/17 |
| real disc, real drive | six runs at 2.1x (two of them 9 zones), two at 1.6x -- one of them a 1x request that the drive floored -- all read-only |
| import into DiscImageStudio | **not tested** -- this machine has no DiscImageStudio 1.5.0; the record is written against `BluRayPresetStore.Import`/`Validate` in the DIS source |
| dual-layer discs | refused before measuring (sector count above 12,219,392); the LBA-to-radius map jumps at the layer break |
| DIS's own pitch inversion | re-ran the bisection from `BluRayTrackGeometry` on our three numbers: `0.320000 um` back, so the record is self-consistent in DIS's model |
| pushed / PR | in review as a pull request against `main` |

## The commands, as actually run

```
python -m discprobe geo --drive G: --media bd --bd-zones 25        # writes results/geo-G-<stamp>/
python -m discprobe disexport --geo results/geo-G-<stamp> --sectors 12088320 --install
```

`geo` writes a result directory (`--out` names it), not a single JSON file: the fit goes into
`summary.json`, the zones it used into `zones.csv`, and the drive's own answers into the same
summary. `disexport` takes either that directory or the `summary.json` inside it.

## Where the work lives

Branch `feat/bd-clv-geometry-solver`: `discprobe/clv.py` (the fit),
`discprobe/bdexport.py` (the preset), `geo --media bd`, `disexport --media bd`,
`tests/test_bd_clv_solver.py`, `tests/test_bd_preset.py`, and the two research notes
`docs/research/BD_CLV_FEASIBILITY.md` (study) and `docs/research/BD_CLV_GEOMETRY_SOLVER.md` (model).
The CD side of the earlier phase is a separate branch, `feat/cd-along-track-calibration`.
