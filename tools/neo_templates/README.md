# Disc Neo {{VERSION}} (preview): DVD texture atlas

[中文说明](README.zh.md) · [Field reference](SCHEMA.md) · [Provenance](PROVENANCE.json) · Licence: GPL-3.0-or-later

Look up the colours that different data textures on a DVD show at different angles.

## What would you like to do?

- **I just want to burn a colour disc.** You can skip this atlas. In the Disc Probe web app, calibrate your batch, start a new work, import a picture, turn on colour, generate the image, burn and photograph the disc. [Follow the web walkthrough]({{COLOUR_EN}}).
- **I want to understand how it works.** See how the tracks on a disc turn light into a picture. [Read How discs make pictures]({{THEORY_EN}}).
- **I want to pick textures or experiment.** Choose a cell on the period map, or search by ID, spec or period. [Open the offline reader](index.html#atlas).
- **I'm an agent or writing code.** Use the [field reference](SCHEMA.md) and [query examples](#query-examples) to read the CSV and JSON files.

Burn a short byte pattern over and over as ordinary data on a DVD±R and the marks along the track form a grating. In
the right light the data area then shows a colour that depends on the pattern's period. This pack is a lookup table
of such patterns ("textures"). For each period range it gives the best pattern found so far, how cleanly that pattern
concentrates at the wanted period, and how far the search there has got.

In the reader, **δ** describes the angles of the light and camera. The **period** is the repeat spacing along a
track and sets the main colour at a given δ. **Purity** measures how much signal power is at the target period.
Higher purity usually gives a cleaner colour.

What you get:

- **{{SINGLES}} single-period textures** with stable IDs, measured over complete DVD ECC blocks
  (`atlas/dvd/singles.csv`). For each one you get its period, purity, low-frequency risk and the viewing-factor
  windows where it shows blue, green or red.
- **{{TWO_LINE}} two-period and {{THREE_LINE}} three-period mixes** (`atlas/dvd/multi_line.csv`) for colours a
  single period cannot make: whites, greys, magentas.
- **The runner-ups, not just the winners** (`atlas/dvd/candidates.csv`, `candidates.json`): {{CAND_ROWS}}
  ranked candidates across {{CAND_TARGETS}} targets. {{CAND_WHOLE}} of them are measured on whole blocks and
  {{CAND_PROXY}} are GPU estimates only. See [Why runner-ups are kept](#why-runner-ups-are-kept).
- **A coverage map of all {{COVERAGE_ROWS}} search targets** (`atlas/dvd/coverage.csv`): searched or not, search
  density, converged or not, best purity so far.
- **The full export** (`atlas/dvd/atlas_dvd.json`). It adds brightness ladders ({{LADDER}}), dark textures ({{DARK}}),
  second- and third-order targets ({{ORDER2}} / {{ORDER3}}), every whole-block candidate ({{OBSERVATIONS}} rows) and
  all {{IMPORTED}} earlier palette observations.
- **The A3 v3 texture colour cards** (`texture-cards/`): 637 textures drawn as predicted colour across the viewing
  range, under white LED and D65 light, with their data and generator scripts.

## Preview status and physical evidence

Disc Probe fitted its colour table to samples from six photographed test discs. That fitted table generates
colour estimates for the web app. Neo's own wavelength strip and A3 cards use the atlas models.

- **{{CARD_SPECS}} Neo candidate textures** match sampled colour records from the six test discs. [Photo of a test disc](colour-card-photo.jpg).
- **{{SHOW_SPECS}} Neo candidate textures** match byte patterns used on photographed SHOW-A–E showcase discs. The fox character disc was also burned and photographed. [Photo of SHOW-D]({{SHOWCASE_PHOTO}}) · [Character disc photos](character-disc-photo.png).
- **{{MODEL_SPECS}} other Neo candidate textures** have no match in these two sources. Their atlas colour indications come from models.

These are distinct byte patterns within each group, including runner-ups. The two physical evidence groups can overlap.
The disc and drive for this evidence are RITEKF1 DVD-R and GH70N. Photos are tied to the recorded setups.
[Download the matching pattern list](colour-evidence.csv).

| | |
|---|---|
| Media | **DVD only.** There is no CD or Blu-ray data yet. |
| Snapshot | {{SNAPSHOT_HUMAN}}, from search run `{{EPOCH}}`. The run is planned to finish on {{END_DATE}} (hard stop {{HARD_DATE}}). |
| Coarse pass | {{COARSE_GPU}} of {{COARSE_JOBS}} coarse targets ({{COARSE_GPU_PCT}} %) have finished all GPU restarts; {{COARSE_REF}} ({{COARSE_REF_PCT}} %) have also finished whole-block CPU refinement.{{HELPER_NOTE_EN}} |
| Dense pass | {{DENSE_GPU}} of {{DENSE_JOBS}} finer targets ({{DENSE_GPU_PCT}} %) have finished GPU search; {{DENSE_REF}} ({{DENSE_REF_PCT}} %) are refined. |
| Results | {{WHOLE_TARGETS}} of {{ALL_JOBS}} targets ({{WHOLE_PCT}} %) have at least one whole-block measured pattern. {{CONVERGED}} targets meet the stopping rule (converged). |

- **Best found is not proven best.** The search is a randomised search with restarts plus a complete enumeration of
  patterns up to 2 bytes only. "Converged" means five independent restarts agreed within 0.005 purity. That is an
  empirical stopping rule, not a proof of optimality.
- **Invisible textures are included.** Long periods and other settings that send their first order outside visible
  light in the design viewing poses (for example into the infrared) are recorded too, because someone may want them
  later, say to use a disc as a reflective infrared mask. So far they are searched on a coarse grid only. A uniform
  dense pass over the whole period range is planned after this run ends.
- Later releases of this pack will carry newer snapshots. IDs stay the same; a better pattern for the same target
  raises its `rev`.

## Why runner-ups are kept

Every cell of the atlas (one search target: a period range, a mix, a brightness level) lists all the distinct byte
patterns the search found for it, in rank order, and not only the best one. Patterns that land on the same colour
but are written differently are useful in their own right:

- **Hiding data inside a coloured area.** If 16 different patterns give the same colour, each one can stand for 4
  bits, so a coloured area can carry data and still look uniform.
- **A spare when the winner burns badly.** If the best pattern turns out hard to burn or read on your drive, the
  next one is ready.
- **Grey levels.** Patterns with the same colour but less purity look the same hue at lower brightness. That gives
  shades.
- **Breaking up visible texture.** Taking turns between several equivalent patterns along the track can stop a
  regular pattern from showing through.
- **Mixing colours.** Some runner-ups carry a second spectral line. They are a starting point for mixed colours.

**What this version stores per cell:** the top 4 of the merged GPU search, the top 4 of each of the five independent
restarts, and every whole-block measurement found so far. Those are mainly each restart's finalists re-measured on whole
blocks by the CPU refinement, plus measurements from earlier rounds and imported palettes. They are de-duplicated by
byte pattern. Whole-block measured patterns come first, in the same order the winner is
chosen by, so rank 1 is always the published winner. Patterns with only a GPU estimate follow. Their purity is an
approximation and the `basis` column says so.

**Next version:** after this run ends, a uniform dense pass over the whole period range will replace this with a
tolerance rule. A cell will keep every pattern whose purity is at least 80 % of the winner's, in the same period bin,
with a risk no worse than the winner's. That means at least 8 and at most 16 patterns per cell.

## Colour is a job for the model, not for eyeballing a table

The colour you see depends on the light, the camera or eye position, and for photos also on the phone model and
where its flash sits beside the lens. The same texture can look blue in one photo and green in another. So this pack
deliberately ships no "pick a colour" list for casual use. It ships the raw material:

- the measured data here (periods, purities, viewing-factor windows),
- the ISO solver in [disc-probe](https://github.com/Ashley-QwQ/disc-probe), which turns a design into a burnable
  disc image,
- the colour model (`texture-cards/scripts/`, and the simulator in disc-probe).

The intended workflow is to pair them with an AI coding agent: describe your phone, light and shooting position, and
let the agent pick textures from this data and simulate them for that setup.

<a id="query-examples"></a>

## How to look things up

**By period.** A grating of period P (µm) sends wavelength λ = 1000 · P · δ nm toward you, where δ = sin θ_in +
sin θ_out along the track is the viewing factor set by your light and camera positions. `singles.csv` lists for each
texture the δ ranges in which it shows blue (440–490 nm), green (510–590 nm) and red (610–690 nm).

```python
import csv
rows = list(csv.DictReader(open('atlas/dvd/singles.csv', encoding='utf-8')))
# Best measured textures with a period between 0.95 and 1.05 µm, lowest readability risk first
near = [r for r in rows if 0.95 <= float(r['period_um']) <= 1.05]
near.sort(key=lambda r: (not r['risk'].startswith('low'), -float(r['purity'])))
for r in near[:5]:
    print(r['id'], r['rev'], r['spec'], r['period_um'], r['purity'], r['risk'], r['delta_green_lo'], r['delta_green_hi'])
```

**By printed chip.** A chip printed from this atlas shows **id + rev + spec + period**, for example
`DVD-S-B0042-K96-A123abc rev 2 A37062 0.853 µm`. Look up the `id` in any of the CSV files or in `targets` /
`atlas_target_winners` in the JSON. If the `rev` on your chip is lower than the current one, a better pattern has
been found since, and the old one is kept in the history (`observations` in the JSON).

**By eye.** Open `texture-cards/texture_cards_v3_led.pdf`: every row is one texture, and moving along a row is like
tilting the disc.

## Files

| Path | What it is |
|---|---|
| `index.html` | Bilingual guide and offline reader with a period map, ranked candidates, search and a δ slider |
| `colour-evidence.csv` | Candidate byte patterns that match sampled card colours or were used on photographed SHOW-A–E discs |
| `atlas/dvd/singles.csv` | One row per single-period target with a measured winner: id, rev, spec, period, purity, F512, risk, status, δ windows |
| `atlas/dvd/multi_line.csv` | Two- and three-period targets: id, kind, spec, periods, shares, purity per line, status |
| `atlas/dvd/candidates.csv` | Every ranked candidate of every target: rank, whole-block or GPU estimate, spec, main period, purity, risk |
| `atlas/dvd/candidates.json` | The same, grouped by target, with more metrics per candidate |
| `atlas/dvd/coverage.csv` | Every active target: period range, search density, status, converged, best purity |
| `atlas/dvd/atlas_dvd.json` | Full export in the same format the search publishes each day (fields in [SCHEMA.md](SCHEMA.md)) |
| `texture-cards/` | A3 v3 colour cards: two PDFs (LED, D65), input data, generator scripts, checks. Its own README explains them; the scripts need a clone of disc-probe |
| `SCHEMA.md` | Field reference: ID rules, every column, metric definitions |
| `PROVENANCE.json` | Snapshot time, code and encoder hashes, per-machine record counts, SHA-256 of every source and every file here |
| `LICENSE` | GPL-3.0-or-later, with a note on how it applies to data |

## What the numbers mean, briefly

- **purity**: the share of the pattern's signal power (DC removed) that sits exactly at the wanted period,
  measured over complete DVD ECC blocks after the real EFMPlus encoder, scrambling and DSV control. 1.0 would be a
  perfect single line. Higher purity means a cleaner, more saturated colour.
- **F512_percent / risk**: how often the data drifts towards long runs of one polarity. That is a known cause of read
  errors. `risk` is a label from model thresholds, not a read test on a real drive.
- **status**: `todo` (not searched yet), `searched`, `converged` (stopping rule met). See SCHEMA.md for the rest.

## Licence

GPL-3.0-or-later, the same as disc-probe. You may use, study, share and change this data. If you pass it on, or
something built from it, keep it under the same licence. See `LICENSE`.

## Citing

Please cite the pack version, the snapshot time and the SHA-256 of `atlas/dvd/atlas_dvd.json` from `PROVENANCE.json`,
for example: *Disc Neo {{VERSION}}, DVD texture atlas, snapshot {{SNAPSHOT_DATE}} (run {{EPOCH}}), disc-probe
project.*
