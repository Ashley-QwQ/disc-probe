# DVD texture colour cards (v3, simulation)

[中文说明](README.zh.md)

A3 sheets that show the predicted colour of 637 DVD textures across the viewing range. A texture here is a short byte
sequence repeated along the track (written in hex in the `spec` column, e.g. `A37062`). Repeating it makes a periodic
pattern of marks along the track, and that pattern diffracts light like a grating.

**These colours are predictions from a model. Nothing on these sheets has been checked against a burned disc yet, and
only sheet 1 has had a full-size visual check by hand.**

| File | What it is |
|---|---|
| [`texture_cards_v3_led.pdf`](texture_cards_v3_led.pdf) | All four sheets, white-LED light (main version) |
| [`texture_cards_v3_d65.pdf`](texture_cards_v3_d65.pdf) | The same under D65 daylight |
| `data/palette_merged.json` | Input: the 637 textures (id, spec, periods, measured block purity), grouped by sheet |
| `data/<sheet>_<led\|d65>_manifest.json` | One record per row (id, spec, periods in µm, spatial frequency, position on the page) and the sheet's fixed exposure |
| `scripts/` | The generator (see below) |
| `checks/` | Reproduction checks, physics self-checks, model and source hashes |
| `research/` | Reference inputs from the earlier colour model, used by `verify_v3.py` |

| Sheet | Content | Rows |
|---|---|---:|
| 1 | Single-period textures | 260 |
| 2a, 2b | Two periods mixed | 183 + 166 |
| 3 | Three periods mixed | 28 |

## How to read a sheet

- Each row is one texture. The x-axis is δ from 0.10 to 0.95, a viewing-geometry factor: δ = sin θ_in + sin θ_out,
  measured along the track. A pattern with period P (µm) sends wavelength λ = 1000 · P · δ nm toward the eye, so moving
  along a row is like tilting the disc. δ is a difference of direction components, not an angle.
- `P` is the period in µm. `1/P` is lines per mm.
- Black stretches are where the first order is outside 380–780 nm; the labels give the UV/IR end in nm. The thin
  upper strip in each row shows all orders.

## How the colours are made

1. Encode the texture with the real EFMPlus coder (with DVD scrambling and DSV control) and take the power spectrum of
   the channel bits over whole ECC blocks.
2. Turn channel bits into marks with an assumed mark width W = 0.35 µm, edge blur σ = 0.03 µm and no length change
   (ΔL = 0).
3. Integrate over the lamp spectrum, the CIE 1931 2° observer and a finite lamp and eye: a 5 cm lamp at 1 m and a
   4 mm pupil at 30 cm, in a symmetric geometry along the track.
4. Convert XYZ to sRGB with one fixed exposure per sheet and lamp. Rows are not brightened one by one, so brightness can
   be compared within a sheet.

The LED spectrum is a nominal analytic white LED (Gaussians at 450 and 560 nm), not a measured lamp. The CIE tables are
5 nm transcriptions that have not been checked against the official 1 nm files.

## Running the scripts

Run them from a clone of this repository; every path is relative to it. They import `discprobe.efmplus`,
`discprobe.dvd` and `tools/dsv_block.py` from the repository, read the inputs in `data/`, and write everything they
produce to `build/` next to this README. `research/` holds the reference inputs from our earlier colour model
(`spectra.npz` and the two source files whose functions `verify_v3.py` reuses).

Python 3.13, NumPy and Pillow; no GPU or network. The page fonts are the repository's `discprobe/web/fonts`
(MonaSans, Archivo) plus Windows system fonts (Microsoft YaHei for Chinese, Consolas); if one is missing the scripts
fall back to Arial, so on other systems the layout will differ. Run in `docs/texture-cards/`:

```
python scripts/render_all.py --estimate          # time estimate only
python scripts/render_all.py --layout-check      # layout only, no colours
python scripts/verify_v3.py                      # reproduction checks, needed before a full render
python scripts/render_all.py --sheets 1          # sheet 1, both lamps
python scripts/render_all.py --sheets all --lamps LED
```

A full run of all 637 rows took about 20–30 minutes with two processes. `checks/` holds the results from our own run.

## Limits

- Simulation only, no burn or photo has checked these colours.
- DVD only. Blu-ray uses 17PP coding and a 74.5 nm channel bit, so these sheets don't carry over, though the same
  pipeline would.
- The sheets compare visible windows and hues for a given δ. They don't predict absolute brightness in a photo,
  second-order efficiency, printing colour, or whether a drive can read the disc.

## Licence

GPL-3.0-or-later, like the rest of this repository.
