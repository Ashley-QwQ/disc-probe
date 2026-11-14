# Disc Lab

[中文说明](README.zh.md)

Disc Lab gives disc-probe a virtual optical drive, a box of made-up discs with hidden truth, rendered phone photos, and scores against that truth. It is for developers and people testing geometry and photo calibration. No physical drive or recordable disc is needed. Disc-probe sees virtual SCSI replies and images; only the lab drive, renderer and scorer read `answers.json`.

## Install and open

Use Python 3.11 or newer. This snapshot requires **disc-probe 0.1.2.1**, the value of `discprobe.version.__version__`. Version strings must be exactly equal, including pre-release tags. A missing package or a different version stops with a plain sentence. The planned release asset name is `disc-lab-1.0.0.0-alpha.zip`; this source snapshot still uses 0.1.2.1. The release maintainer must align `disclab/compat.py` with the actual matching disc-probe release and repeat verification before publishing that release.

Two layouts work:

1. Install the matching wheel into the Python environment you will use: `python -m pip install disc_probe-0.1.2.1-py3-none-any.whl`. It supplies NumPy, SciPy, Pillow and OpenCV dependencies through its package requirements. For offline use, provide those dependencies locally. Unpack the Disc Lab zip anywhere and open a terminal in the folder containing `disclab/`.
2. Unpack the matching Windows full package, with its Python runtime and dependencies. Unpack the Disc Lab zip into the folder containing `discprobe/`, so `disclab/` and `discprobe/` are siblings. Use that package's Python executable for every command (replace `python` below with its path). Disc Lab does not bundle disc-probe or another Python runtime.

Run `python -m disclab --help`. All examples below start from the folder containing `disclab/`; lab folders may be elsewhere. The boot hook locates its own package, finds a sibling discprobe first or the installed wheel otherwise, and checks the version before loading device hooks. It also works when the child process starts inside the lab folder, as the web launcher does. Keep the unpacked package at its location while running; saved lab records contain resolved paths.

To assemble the standalone archive locally: `python -m disclab.package --output disclab/dist/disc-lab-1.0.0.0-alpha.zip`. It contains the `disclab/` folder, both READMEs, examples, tests, spectrum data and license. It excludes disc-probe, Python, experiment output and caches. The filename does not override the required disc-probe version above.

## Five-minute example

PowerShell:

```powershell
& ./disclab/examples/run-example.ps1 -Lab ./LAB-demo
```

Bash:

```bash
bash ./disclab/examples/run-example.sh ./LAB-demo
```

Use a fresh folder. Existing folders are refused. Omit the folder argument to create a new temporary lab whose location is printed. In PowerShell, `-Python` selects an interpreter; in Bash, set `PYTHON` to its executable path. Both scripts read `examples/dvd-r-3.json`: a 3-disc DVD-R box, each disc burned full of random data and measured with the default reads like a real disc; the first run is scored explicitly, and all scores and the wall time are printed. For the whole 12-disc box use `-Config examples/dvd-r-12.json` (Bash: `--config`). Runtime depends on the machine.

Burn the whole disc: with only an inner band written, geometry is measured on that band alone and the whole-disc placement is an extrapolation, with numbers far too large to say anything about the algorithms.

The equivalent steps are:

```bash
python -m disclab box --lab LAB --media dvd-r --count 3 --seed 1
python -m disclab loop geo --lab LAB
# Replace GEO_DIR with the first row's geo folder in LAB/scores/geo-wide.json:
python -m disclab score --lab LAB --disc "LAB-A 1-01" --geo GEO_DIR
```

The quick example uses a 256 MiB random image, 8 read pairs per rung and at most 8 ladder targets. It measures only the recorded inner part of the disc; full-disc placement scores therefore include extrapolation and can be much worse. It is a working example, not a precision benchmark. Omitting the three quick options preserves the existing full-image and measurement defaults. Do not reuse the quick-example lab for the full photo loop: its geometry covers a smaller span.

`LAB/box.json` is the public box label, `answers.json` holds truth, and `state.json` records virtual drives and virtual writes. Results go to `results/`, rendered photos to `photos/`, and scores to `scores/geo-wide.json` (or `geo-default.json`). Intermediate ISOs live under `LAB/iso/` and are deleted after use, including failed loop steps. Burn maps and small retained headers remain; the full ISO's byte contents cannot be read again after deletion. Create a new lab for a different experiment.

## Numbered TUI

```bash
python -m disclab tui --plain
python -m disclab tui --lab LAB
python -m disclab tui --plain --quick
```

Choose an existing box or create one by media, disc count, seed and reader profile. Numbered actions cover tray insertion, measurement ISO and virtual burn, timing, geo, a bundled sailboat picture ISO, the lab's simplified A5/B9 target and virtual burn, rendered photos, photo L, a picture with accepted L, and scores against truth. Action 11 walks those steps in order. Measurement, photo target and corrected picture use separate virtual discs; create at least three for the whole path. The sample ISO is a preview before the calibration target is burned. No physical discs are used up. `--plain` disables colour and works with redirected stdin; EOF exits. Resume by selecting the same lab: progress and settings are in `state.json`.

The **checkdisc target cannot be rendered yet**: its multi-byte textures are not supported by the lab renderer. The photo path uses the lab's own simplified two-texture target. A refused photo L remains refused; a corrected picture is offered only when the reader applies L. Scores preserve the original formulas and compare geo, photo L and picture placement with truth. `score --lab LAB --progress --json` retrieves the same saved-flow scores without menus.

Quick mode uses a 65,536-sector inner-band measurement and fewer reads. Artwork is restricted to a measured island using the existing image options, while full-disc scores still include extrapolation. It is for the short geo/picture/score practice path; the full 26.2–57.2 mm photo target needs a full measurement. TUI ISOs are retained because subsequent timing and info reads need their bytes; full practice can retain several GB per image. Existing `loop` cleanup is unchanged.

## Practice in the existing web page

```bash
python -m disclab practice --media dvd-r --lab LAB-practice --port 8853
```

This makes a three-disc practice box with the default reader, inserts its first disc, starts the existing `disclab web` launcher and prints a short Chinese/English guide. Omit `--lab` for a new retained temporary folder. A supplied folder must be new or empty, so existing results are preserved. The default is local-only; `--lan` enables the existing token-guarded LAN mode. Stop with Ctrl+C; the results path is printed on exit. All writes use the virtual drive; no physical discs are used up.

## Structured commands

Every subcommand accepts `--json`, returning one object with `status`, `lab`, `outputs`, `scores` and `errors`. Logs and subprocess text go to stderr. Put the option before `dp`'s `--` separator. Server commands return their final JSON after stopping. `state.json` gains timestamped `steps` while preserving its existing keys. See the bilingual [API contract](API.md) and [scripted TUI report](TUI_REPORT.md).

```bash
python -m disclab box --lab LAB-json --count 3 --json
python -m disclab dp --lab LAB-json --json -- info --drive X: --out LAB-json/results
```

## Next steps

- Rewritable discs and erase operations.
- More faults: timeouts, whole-turn aliasing, photo pose and exposure.
- Multi-byte texture rendering, so checkdisc can be photographed in practice.
- A web shell over the same JSON API.

## Photo loop (existing commands)

Use a separate, full-size lab. This path can take much longer and temporarily needs several GB of free space:

```bash
python -m disclab box --lab LAB-photo --media dvd-r --count 12 --seed 1
python -m disclab loop photo --lab LAB-photo --targets 6 --photos 6 --workers 3
```

It writes a random image on disc 1 in the virtual recorder, measures geo, writes the lab's A5/B9 target on discs 2–7, renders phone photos, runs disc-probe's photo reader, and compares the reported L against truth. If a photo group applies L, it generates picture images with and without L, scores both on the picture disc, and virtually records the corrected picture. Summary and per-photo results are in `LAB-photo/scores/photo.json`; logs are in `loop-photo.log`. Refused photos and groups remain refused.

For one target already made by that loop:

```bash
python -m disclab photos --lab LAB-photo --disc "LAB-A 1-02" -n 3 --out LAB-photo/photos/manual
python -m disclab poses --lab LAB-photo --disc "LAB-A 1-02" --geo GEO_DIR --out LAB-photo/scores/poses.json --workers 2
```

`poses` holds a disc fixed and varies camera pose and optical effects to see whether the estimated L follows the pose. `tray --lab LAB --disc "LAB-A 1-01"` selects a virtual disc. `dp --lab LAB -- info --drive X: --out LAB/results` runs disc-probe against it. `env --lab LAB --powershell` prints the environment for a separate PowerShell session (omit `--powershell` for POSIX export statements). Apply those settings before starting disc-probe yourself. Lab hooks list only registered virtual drives and reject other drive names. `X:` is a virtual name, not a filesystem path.

## Web hookup and upload

These are commands for a separate development session; packaging verification does not start a server or send network requests.

```bash
python -m disclab web --lab LAB-photo --port 8853 --media dvd
```

The child workspace is the lab directory. Open the printed local URL; the page uses virtual drives. This default local-only mode disables phone links. To use phone uploads, run the token-guarded LAN mode instead and use the computer page URL containing its session token:

```bash
python -m disclab web --lab LAB-photo --port 8853 --media dvd --lan
python -m disclab upload --url "http://127.0.0.1:8853/home/?token=YOUR_SESSION_TOKEN" --run GEO_RUN_NAME --photos LAB-photo/photos/manual/IMG_00000.jpg
```

Replace `GEO_RUN_NAME` with an existing geo folder name visible to the page, and use actual photo filenames. `upload` asks the computer API for a phone link, sends each supplied image as raw bytes using that phone capability, then lists photos using computer authentication. It reports server failures and exits nonzero if an upload fails. It does not perform the browser's canvas/JPEG conversion. Local-only mode cannot supply the required phone capability. Stop the launcher with Ctrl+C. No real-drive backend files are changed.

## What the scores mean

Lower errors are better; there is no overall pass/fail grade. A successful command exit does not establish physical accuracy. `score` prints one result; `loop geo` also saves a list with each geo exit code.

| Field | Meaning |
|---|---|
| `u`, `v`; `true_u`, `true_v` | Measured spiral ratios `u=r0/b`, `v=pitch/b`, and the disc's hidden values. |
| `du_bits`, `dv_rel` | `u - true_u` in bit units; `v / true_v - 1` as a fraction, not percent. |
| `vs_timing_measured_span` | Error against what read timing can observe, restricted to geo's measured radial span. |
| `vs_timing_full` | The same timing comparison over the scorer's default 26–57 mm span, including extrapolation. |
| `placement_on_target` | Actual image placement error on the target disc, using its truth; includes the path offset. |
| `c_deg` | Fitted constant rotation in degrees; a free rotation does not bend an image. |
| `L_mm` | Fitted along-track term in mm in `error(r) = c + L/r + residual`, with the angle in radians. Its sign is retained. |
| `rms_deg`, `pp_deg` | RMS and peak-to-peak angular error after removing the mean rotation. |
| `residual_after_L_rms_deg`, `residual_after_L_pp_deg` | Angular error left after removing both rotation and the fitted L term. |
| `path_L_mm` | Reader completion distance plus head offset; the model's nominal path L, not a photo estimate. |
| `geo_reported` | Disc-probe's own residual RMS, angle sigma, chi-squared per degree of freedom, completion status and correction filename. These describe its fit, not truth error. |
| `exit` | Geo subprocess exit code saved by the loop. Zero means the command succeeded. |

Photo scores keep per-photo status, estimated `L_mm`, signed `err_mm`, pose, group `verdict`, applied L and its error. `photos`, `accepted`, `accept_rate` and `statuses` count all/accepted photos and outcomes; `accepted_mae_mm` and `accepted_max_mm` summarize absolute L error among accepted photos. `false_accepts` counts accepted photos with absolute error **greater than 0.326 mm**. `groups` and `groups_applied` count target groups and those applying L; `group_false_applied` uses the same strict threshold, `group_abs_err_mm` lists applied absolute errors, and `reasons` preserves reasons for no application. Missing estimates remain JSON null. `pictures.nophoto` and `pictures.photo` contain placement decomposition with and without photo L; `photo_l` records whether and why L was written. None of these thresholds or equations has been changed for packaging.

## Truth model: measured and assumed

A user bit n is at `alpha(n) = -theta_g(n + w)`. The read-completion angle is `theta_t(n) = theta_g(n + w + d) + asin(h/r) - (e/r) sin(psi + theta_g)`. The along-track path constant is `L = d*b + h`, the L in photo calibration's `tau(r) = c + L/r`. See `physics.py` for implementation. The following table preserves the original model's evidence claims; packaging has not independently repeated those physical measurements.

| Item | Value | Basis |
|---|---|---|
| u/v identical within one stamper | Zero disc-to-disc spread by default | **Measured:** separate GH70N/RITEKF1 discs fit u=180518.44±0.05, v=5.591208±1e-6. **Inference:** moulding fixes bits per turn; shrinkage scales mm. |
| Batch mean u/v | 180518.44, 5.591208 | **Measured**, as above. |
| Variable pitch | Slow wave, 0.04° RMS | **Assumed**, scaled from GH70N grid-disc residual of 0.03° RMS. |
| GH70N timing noise | 13 µs jitter, two turns per read, FUA effective | **Aligned to measurements:** read std 0.2565°, geo residual 0.076°, FUA read 41.4 ms. |
| Path L, GH70N + IMAPI DVD | +0.19 mm: completion 0.13 + head 0.06 | **Measured sum:** user photo groups +0.08..+0.12 / +0.25..+0.28 mm and a sealed test at 0.19 mm. The split is **unknown**. |
| Eccentricity and warp | 18 µm eccentricity sigma; dish 0.12±0.08 mm; saddle 0.06 mm | **Assumed**, specification-scale values. |
| Outer texture fails at low write speed | At ≤4x, texture sectors beyond 35 mm give 3/11/00 | **Measured phenomenon**, GH70N + RITEKF1 at 4x; radius threshold is estimated. |
| Photo texture colour versus delta | A3 colour-card wave model, real EFMPlus + ECC | **Model**, not calibrated to real photos. |
| Photo zero-order reflection darkening | A5 15% darker than B9, per disc | **Assumed**, estimated from user photos. |
| Refraction, warp, rainbow arms, specular spots | Geometric optics | Physically expected; magnitudes not checked against real photos. |
| Phone colour processing | 40% desaturation | **Assumed**. |
| CD, BD | Virtual drive and geo paths; photos are DVD only | CD byte layout / CIRC interleaving is not modelled. |

## Limits and verification

The renderer records single-byte, repeating multi-byte (up to 64 bytes), and random-data texture identities. It ships spectra for the ten PCAL-C round-2 `checkdisc` recipes in `data/textures_v3.npz`. Their XYZ curves come from the repository A3 v3 scalar wave model, using real EFMPlus, scrambling, ECC and DSV across eight blocks, including all spectral orders. **This is a prediction not yet validated by real photos. Simulated colours must not be used to calibrate a real disc.** A5/B9/RND keep the original `data/wave_xyz.npz` and legacy rendering path to preserve existing pixels; six stored pre-change hashes test that contract. The original table is not regenerated.

New texture maps retain recipe identities after the ISO is removed. Rendering uses the existing pose/refraction/warp optics and four equal-area recording-layer subpixel samples, sums texture XYZ, converts to linear sRGB, then applies one image exposure. New-model texture light is zero outside delta 0.10–0.95. The polar map and four samples limit small-feature accuracy. The legacy path, including its original interpolation and exposure, is retained for A5/B9/RND-only maps. CD and BD still support geometry measurement only.

Flash offset is a pose parameter, default **`(-43.66, 19.79)` mm**, approximately 47.9 mm lens to flash, from the Apple drawing confirmed by the user. The old 34 mm guess was not a measurement. Use `--flash-mm 34 0` to reproduce old flash poses, or `--illuminant D65` for the other supplied lamp spectrum. The six legacy hashes use the original explicit `(34, 0)` pose; changing the default does change a default flash photo. Room-lamp poses do not depend on this offset. Sensitivity results are in the render report.

Computing an unshipped recipe needs an external, repository-relative A3 export with its sibling `discprobe` source. Set `DISCLAB_A3_SOURCE` to its `docs/texture-cards/scripts` directory, and `DISCLAB_WAVE_CACHE` to a scratch cache outside both repositories (otherwise Windows uses its temporary folder, other systems their user cache). A missing source produces a plain error, never a substitute spectrum. To rebuild the ten new tables, run `python -m disclab.tables --a3 SOURCE_FOLDER --cache SCRATCH_CACHE`; `--spec HEX --output SCRATCH_TABLE.npz` builds a custom table. Mass/XYZ cache keys include the spec and full model signature. The A3 export is only read; the adapter skips its import-time directory creation in memory and never uses operator `save=True`. It also completes the AST loader with the unchanged `_hash` helper required by RND.

Zero-order reflection uses the existing empirical A5 coefficient 1 and B9/RND coefficient 0.4 times each disc's `zero_order_dark`. For new recipes the coefficient is `0.4 * mark_density / B9_density`, an **assumption**. DSV makes both A5 and B9 mark densities almost 50%; density does not explain their legacy brightness difference. `tex_gain`, desaturation, lamp spectrum and exposure also remain modelling choices. Validation results and comparison thumbnails are in [RENDER_REPORT.md](RENDER_REPORT.md).

Existing optical-model limitations remain; see the render report. Keep at most four CPU-heavy processes active. When sharing the machine, set `DISCPROBE_WORKERS=2`, use `--workers 2` for photo workflows, and render/read sequentially. Historical packaging runs used three image/photo-reader workers; this renderer validation uses at most two.

Verified here on **Windows, Python 3.13.14**: the original 20 tests, the added portable-package tests, the tiny two-disc end-to-end example, and the full 12-disc example scripts in Windows PowerShell and Git Bash. The sibling layout and a locally installed matching wheel are checked from extracted paths with spaces and Chinese characters. Web launch/upload unit tests mock subprocesses and HTTP; no live web server or live upload was run for this packaging task. The original packaging run did not run the full photo loop or A3 rebuild; the later renderer validation is recorded separately in RENDER_REPORT.md. **Linux was not run here**; the shell script was exercised with Git Bash on Windows, which is not a Linux test. Exact counts, timings and scores are in [PACKAGE_REPORT.md](PACKAGE_REPORT.md).

## Scenario and fault assays

Use `python -m disclab box --lab LAB --scenario FILE` to configure discs, initial recorded states, the drive, and deliberate faults. Run `python -m disclab faults --lab LAB [--fault ID]` for per-command classifications and `LAB/scores/faults.json`. See [the bilingual schema](SCENARIO.md), [example scenarios](examples/scenarios/), and [the measured fault report](FAULTS_REPORT.md).
