# Five GH70N ladders of two RITEKF1 DVD-R discs, 2026-11-07

HL-DT-ST GH70N (NYA2), SATA, Windows, `geo` with `--speed 5540` (the default), read with READ(12) FUA. Each folder holds what `geo` wrote: `events.csv` (every read), `targets.csv` (the rungs) and `summary.json`.

| folder | disc | ranges | single-shot scatter (median) | rms | note |
|---|---|---|---|---|---|
| `geo-H-20261107-183256` | B: a second disc from the same pack, random data throughout | default 3–85 % | 0.34° | 0.116° | clean |
| `geo-H-20261107-191044` | A: the one-disc trial disc (texture rings and random rings out to 50 mm, a grid appended outside) | `--ranges` over the 13 random stretches | 0.32° | 0.103° | clean |
| `geo-H-20261107-201833` | A | found by the content check (the same 12 random rings) | 1.14° | 0.501° | noisy |
| `geo-H-20261107-204800` | A | as above | 0.96° | 0.401° | noisy |
| `geo-H-20261107-210507` | A | `--ranges` as in 191044 | 1.05° | 0.421° | noisy |

The three noisy runs came after disc A had been taken out to be scanned and put back, after other runs at other speeds, and on a drive that had worked for some hours. With the same `--speed 5540`, the settled spindle period was 21.18 ms (2832 rpm) in the clean runs and 20.74 ms (2893 rpm) in two of the noisy ones. The cause of the extra scatter is not known.

Peak-to-peak angle difference from 191044 over 24.5–58 mm, constant-pitch fits: 183256 0.124°, 201833 0.64°, 204800 0.77°, 210507 0.50°. `tools/geo_reanalyse.py` (PR #29) reads these folders as they are.
