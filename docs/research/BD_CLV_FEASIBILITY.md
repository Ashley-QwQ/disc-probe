# BD is CLV: what the phase ladder can and cannot measure

Status: research note, 2026-11-08. Nothing here is merged; the measurements come from one
drive and one disc, and the community reports are quoted second-hand (see §9).

`geo` measures a spiral by timing reads. It works on DVD and on CD because the spindle holds
a constant rotation: the angle between two positions is then a function of how far along the
spiral they are, and two numbers -- where the spiral starts and how fast it widens -- explain
every measurement. On BD the same command stops after a few seconds with
`the drive is running at a constant linear speed`. This note works out why, what the timing
data can still say, and what it would take to turn that into a preset.

## 1. What the ladder measures

`discprobe.geo` reads a reference sector, then a ladder of sectors across the disc, and at
each one measures the time of one rotation `T`. From `T` and the reference it builds a phase

    phi(n) = theta(n; u, v) - theta(n_ref; u, v) + c

where `n` is the position along the spiral in channel bits, `u = r0 / b` the start radius in
bits, `v = pitch / b` the pitch in bits per bit, `b` the channel bit length, and

    theta(n; u, v) = 2n / (sqrt(u^2 + v n / pi) + u)

is the angle swept from the start of the spiral. Only `phi mod 360` is measured; the ladder is
dense enough that the turns can be counted, and the curvature of `phi` against `n` gives
`(u, v)`.

The whole construction assumes the spindle holds the *angle* rate. Under CAV, `T` is the
rotation period and everything above is one rotation's worth of angle. Under CLV the drive
holds the *linear* rate instead: the time from `n_ref` to `n` is `(n - n_ref) b / v_lin`, and
the fraction of a rotation it represents is that distance over the circumference

    phi_CLV(n) = 2 pi (n - n_ref) b / r_ref

which is **linear in n**. It has no curvature, so the fit has nothing to read `(u, v)` from,
and the size of the phase is a distance rather than an angle: a factor `b` (74.5 nm) away from
what `theta` would predict. No value of `(r0, pitch)` can absorb that factor.

`geo` already notices: `discprobe/geo.py:70-77` has `looks_clv(ratio, expected)`, called from
the rotation check in `geo.py:190-209`, and a BD run stops once the measured ratio between an
inner and an outer zone matches the CLV prediction. That check is right, and this note does not
ask for it to be relaxed. The question is what to do instead of stopping.

## 2. The data

`tests/data/bd_discussion_samples/local_uj272_bd_zones.csv` holds 39 zones from 13 `timing`
runs on one MATSHITA BD-MLT UJ272 (firmware 1.02) with a BD-RE (last LBA 12 088 319), read
with READ(12) in 32-sector blocks. Each row is one zone of one run: radius from the nominal
geometry, period, rpm, and the linear speed that follows.

```
run                          req    zone   radius  period     rpm     v m/s    T/r
timing-G-20261106-212541    26974    0.05  26.258   15.888  3776.4 10383.979  0.6051
timing-G-20261106-212541    26974    0.50  41.363   25.106  2389.9 10351.814  0.6070
timing-G-20261106-212541    26974    0.95  52.272   31.693  1893.2 10363.160  0.6063
```

(the CSV stores mm/s, as the summaries do; the tool divides by 1000.)

Across the radius the linear speed does not move while the rpm follows `1/r` exactly: the
ratio `v(inner)/v(outer)` is 0.987-1.007, against an `r(inner)/r(outer)` of 0.47-0.54.
Over the 13 runs, 9 hold the linear speed to within 0.96 % of their own median. That is CLV.

Two details matter for anyone writing a check like this:

- **Three runs locked onto the second harmonic.** `timing-G-20261106-211921`, `-211950` and
  `-203622` report an inner zone at exactly twice the outer rate (15 835 vs 7 898 m/s;
  40 755 vs 10 317). The periods at those inner zones are half a rotation, so a reader that
  compares only "is the rate constant" sees a 2x jump and may label the run `mixed`, which is
  what the stored summaries do. Those zones are not a different spin law; they are a misread.
- **One run was interrupted** (2026-11-07 20:28:36, `--speed 7193`, stopped by hand); its
  zones are consistent with CLV as well but its line is not a clean fit.

At 2.1x the drive settles on 10.35 m/s; at 1.6x (request 7193) on 7.86 m/s. `--cav` has no
effect. That matches what the drive reports elsewhere: Page 2A says `rotation CAV` for the
write speeds and `4033 CAV / 1411 CLV` for the CD ones, but for BD there is no rotation bit
to set.

## 3. Why the ladder cannot be rescued

A ladder only sees `phi mod 360`, so consecutive rungs have to be closer than one rotation or
the turns cannot be counted. Under CLV one rotation is `2 pi r_ref / b` bits -- at 24 mm that
is 2.02e6 bits, or **67 sectors**. Thirty rungs thirty sectors apart therefore cover 870
sectors: 870/67.3 = 12.9 turns, and at 0.32 um per turn that is **4.1 um of radius**.

Over 4 um, the model's own curve bends away from a straight line by 0.0104 degrees
(`tools/bd_clv_model_analysis.py degenerate`). Changing the pitch by 10 % changes that bend
by 4e-5 degrees; changing `r0` by 5 % changes it by 5e-4 degrees. The timing noise on this
drive is 0.3 degrees. The information is four orders of magnitude below the noise, and no
amount of averaging helps: it is a systematic absence of curvature, not a random error.

Relaxing the "denser than a turn" rule does not help either, because the turn count is exactly
what is unknown -- the argument is circular. Under CAV a ladder may jump many turns because
the model predicts how many; under CLV the model has been replaced by a straight line, which
predicts nothing.

So: **a BD phase ladder is not a weak measurement of the geometry, it is a measurement of the
wrong quantity.** Stopping, as `geo` now does, is the correct behaviour for `--media bd` with
the CAV model.

## 4. What CLV data does contain

Under CLV `T = 2 pi r / v_lin`, so `T^2 = (2 pi / v)^2 r^2`; with `r^2 = r0^2 + pitch *
sector_mm * LBA / pi`,

    T^2(LBA) = (2 pi r0 / v)^2 + (4 pi pitch sector_mm / v^2) LBA

a straight line in LBA. Seven of the clean runs fit it with `R^2 >= 0.9999`:

```
run                       slope (ms^2/LBA)     R^2   v (p=0.32)  v measured    r0      pitch if r0=24
timing-G-20261106-211843      8.427288e-05  0.99998      10.338      10.364   23.781 mm   0.3259 um
timing-G-20261106-212541      8.398604e-05  0.99999      10.356      10.363   23.958 mm   0.3211 um
timing-G-20261106-212835      8.404702e-05  0.99999      10.352      10.361   23.933 mm   0.3218 um
timing-G-20261106-213105      8.399744e-05  1.00000      10.355      10.362   23.964 mm   0.3210 um
timing-G-20261107-202836      8.407453e-05  1.00000      10.351      10.302   24.380 mm   0.3101 um
timing-G-20261107-202908      8.441189e-05  0.99998      10.330      10.283   24.233 mm   0.3139 um
timing-G-20261107-203351      8.430521e-05  1.00000      10.337      10.294   24.281 mm   0.3126 um
```

The slope gives `pitch / v^2` and the intercept `r0 / v`: two equations, three unknowns. Give
the fit one anchor and it returns the other two.

- **Anchor on the standard start radius**, `r0 = 24.0 mm`: the pitch comes out 0.310-0.322 um
  and the linear speed 10.33-10.36 m/s, which is 2.1x. That is a real measurement of the pitch,
  something the phase ladder cannot do on BD at all.
- **Anchor on a linear speed measured from sustained throughput** (`bytes/s * bytes per user
  sector / 2048 * b`): `r0` comes out at 23.9-24.4 mm and the pitch again near 0.32 um.

Both anchors agree with the standard, which is a useful cross-check of the arithmetic and of
the drive's reported radii. The measurement is not circular -- the slope and the intercept come
from timing alone -- but it is only as good as the anchor: `pitch` scales as `r0^2` and as
`v^-2`, so a 1 % error in `r0` is 2 % in the pitch, and a 1 % error in `v` is also 2 %.

This is the same shape as the method the maintainers of `US6914862B2` and `WO2004102560A1`
describe for drives that cannot hold CAV: measure periods at known positions, fit the line,
read the pitch off the slope.

## 5. Can the drive be made to hold CAV instead?

Partly, and the interesting part is that `info` already answers the question.

**The drive picks the rate but not the law.** On this BD-RE, `--speed 7193` reads at 1.6x and
`--speed 8990`, `11162`, `17980` and `26974` all settle on 2.1x: the request selects between
the two rates the drive offers, and `--cav` changes nothing at either. So the reports of "the
speed setting has no effect" are half right -- the setting does pick a rate, and neither rate
is CAV. `SET CD SPEED` (0xBB) is specified for CD and DVD media; for BD the drive is doing
what it likes with it.

**`GET PERFORMANCE` (0xA4, Type 00h) says which law is in force, in one command.**
`discprobe/mmc.py:62` already implements it and `discprobe/info.py:55` already stores the
answer as `perf_read_nominal`. From the dumps in `results/`:

| disc | last LBA | start kB/s | end kB/s | end/start | law |
| --- | --- | --- | --- | --- | --- |
| DVD-R (4.7 GB) | 2 295 103 | 4585 | 11 080 | 2.4166 | CAV |
| CD-R (audio) | 158 035 | 1899 | 3162 | 1.6651 | CAV |
| BD-RE (25 GB) | 12 088 319 | 7193 | 7193 | 1.0000 | CLV |

The DVD ratio is `58.0/24.0 = 2.4167` to four digits: the drive reports the end of the
performance range at the end of the data area, so the ratio *is* the ratio of the two radii.
The CD ratio 1.6651 puts the outer radius of that burn at 41.6 mm. The BD-RE ratio is exactly
1.0 -- the two radii would give 2.42 if the drive held CAV.

That means the pre-flight does not need new code: `info` already collects it, and `geo
--media bd` could refuse before the first rung by comparing `perf_read_nominal` start and end,
with the numbers in the message. For recordable media the law depends on the recorded speed
and the drive's policy rather than the medium -- a BD-RE written at 2x is read at 2x CLV,
while a BD-ROM is read CAV at 12x -- but the command reports whichever it is.

What is *not* available is a way to force CAV: Pioneer's command reference for BDR-203 says
"The drive can not specify the reading speed by any Packet command ... determined by the
drive", `SET STREAMING` (0xB6) governs the write side, and its read fields are a request for a
minimum rate rather than a rotation law.

## 6. Do the disc structures hold the geometry?

No. For BD there is no ATIP; the equivalents are:

- **Disc Information** (`READ DISC STRUCTURE` 0xAD, format 00h): channel bit length, disc
  type, recording speed, first and last addressable address. It locates the *data*, and says
  the bit length is 74.5 nm, but not the radius.
- **PIC**: the permanent information area carries the disc manufacturer's write strategy and
  IDs, not geometry.
- **BCA** (format 03h, 66 bytes): a serial number and a manufacturer code.

The TOC-style map the drive returns for BD is compiled by the drive from DI, not measured. So
`info` can report `last_lba` and the nominal length, but not a radius.

One more thing this rules out, which is worth saying because CD has the same problem: any
"absolute position along the track" has to come from a physical reference, and BD has none that
is finer than a millimetre.

## 7. What the standard fixes, and what is left to measure

For BD the geometry is not really a free parameter:

| quantity | value |
| --- | --- |
| track pitch | 0.32 um |
| data area | 24.0 - 58.0 mm |
| lead-in start | 22.0 mm |
| BCA | 21.0 - 22.2 mm |
| channel bit length | 74.50 nm |
| 1x linear speed | 4.917 m/s |
| channel bit rate | 66.000 Mb/s |
| user data rate | 35.965 Mb/s |

Against that, what a preset actually needs is: the start radius the disc really uses, the pitch
(0.32 um, to confirm rather than to discover), and how much of the spiral is written. The
first and third are what `T^2` and the throughput measurement above give; the second comes
along with them.

## 8. What this would look like in `disc-probe`

Three separable pieces, smallest first:

1. **Say which law the drive is using before the ladder starts.** No new command is needed:
   `info` already stores `perf_read_nominal`, so `geo --media bd` can refuse before the first
   rung when its start and end are equal, and put both numbers in `summary.json`
   (`rotation_check.start_kBps` / `.end_kBps`). That replaces a few seconds of ladder with a
   decision made from data already on disk. It also explains the second-harmonic zones, whose
   inner rate is 2x the outer: the existing `looks_clv` already refuses to call that CLV
   (`CLV_RATIO_SLACK`), but nothing says *why* the run looked like that.
2. **A CLV preset, timing only.** The `T^2` fit needs periods at three or more zones and one
   anchor. With `--r0 24.0` (the standard) it can write a BD preset with `pitch` measured,
   `inner radius` from the standard, and the last LBA from `info`. That preset is as good as
   the standard's start radius, which is presumably what a BD preset needs anyway -- BD has no
   fine calibration step the way CD does.
3. **A throughput anchor**, so the fit does not need `--r0` at all: read a long run of sectors
   with timestamps, divide bytes by time, and set `v`. This is the only piece that needs a
   new measurement path in `timing.py` rather than arithmetic on what it already records.

Nothing here asks `geo` to change its model, and nothing here touches the CD or DVD paths.

## 9. What is not known

- The community reports are second-hand. The discussion at
  `JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107` renders BD reports as a table, but the
  comment bodies could not be fetched (the API truncates them, `?page=2` does not work, and the
  archive has no copy). `tests/data/bd_discussion_samples/discussion107_bd_reports.json`
  records both reports as quoted, with a `honesty_note` saying so.
- The 9705 rpm figure in the second report (ASUS BW-16D1H-U, OEM Pioneer BDR-209) is given as
  "the inner and middle zones" in one place and "inside" in another, and the repo's
  `KNOWLEDGE.md` reads it as 58 mm at 12x. All three cannot be right. It is left unverified.
- No source gives the ZCLV partition map for BD-R at 6x or 8x. If a drive does run ZCLV, the
  `T^2` line breaks into segments and the slope changes between them; the fit would show it as
  a poor `R^2`. None of the runs here show that, because this drive only has 1.6x and 2.1x
  CLV for the media at hand.
- The pitch spread here (0.310-0.322 um, 4 %) is dominated by the 3-zone fits; more zones per
  run would tighten it. It is not yet clear whether the remaining spread is the anchor, the
  disc, or the period measurement.

## 10. Reproducing

```
python -m discprobe timing --drive G: --media bd --speed 8990 --period-reads --max-minutes 10
python tools/bd_clv_model_analysis.py tests/data/bd_discussion_samples/local_uj272_bd_zones.csv
```

The first writes `results/timing-*/summary.json`; the CSV is assembled from those with
`setup.family == "bd"`. `--media bd` sets 32-sector blocks and READ(12), which is what the
stored runs used.

## 11. The solver, as implemented

`discprobe/clv.py` carries the fit; `geo --media bd` is the command that runs it. Nothing here
is a new drive command: the period is what `timing` already measures per zone, and
`fit_from_summary` can re-fit any finished `timing` run without a drive at all.

**Before measuring.** `ClvLadder.precheck()` sends `GET PERFORMANCE` type 00h and passes the
descriptor to `classify_rotation`. A ratio of 1.0000 is CLV, a ratio near 58.0/24.0 = 2.4167 is
CAV, and anything in between is reported as `unknown` and not fitted -- that is a range that
spans a ZCLV speed change, and one straight line cannot describe it. This is the routing the
command uses: a CAV answer means the angle ladder in `geo` applies (that is how this drive reads
every DVD), a CLV answer means the period fit below, and `_geo_clv` is only reached through
`--media bd` or that check.

**The fit.** Nine zones at 5-95 % of the recorded area by default. `fit_t2` is a weighted
least-squares line through `(LBA, T^2)` with iterative MAD rejection (at most three rounds,
never below three points), then one anchor:

| anchor | what it measures | what it assumes |
|---|---|---|
| `--pitch-um` (default 0.32) | r0 and the linear speed | the factory track pitch |
| `--linear-mm-s` | r0 and the pitch | the drive's linear speed |
| neither | only `r0/v` and `p/v^2` | both, pinned to 1x |

The three cases are named in `summary.json` as `anchor`, and the ratios `r0_over_v_mm_s` and
`pitch_over_v2_um_s2` are always written, so two runs can be compared without agreeing on an
anchor first.

**What it writes.** `zones.csv` (fraction, LBA, period, rpm, coherence, jitter, nominal radius)
and `summary.json` with `fit`, `setup`, `cache`, `settle`, `period`, `rotation_check` and
`identity`. The `fit` block is tagged `"model": "clv"` and carries `"media": "bd"`, which is how
`results`, `guide` and the `disexport` blocker tell a period fit from an angle fit; the geometry
keys differ on purpose, because `u` and `v` do not exist here.

**What the regression set says.** `tests/test_bd_clv_solver.py` and the selftest both fit the 39
stored zones. Seven of the eleven runs are a straight line in `T^2` (R^2 >= 0.999) with
r0 = 23.778-24.377 mm and v = 10.33-10.36 m/s; the four runs whose inner zone turned at twice the
outer rate are rejected by their own speed spread before the fit sees them. On the simulated
drive (`geo --sim clv --media bd --linear-mm-s 39336`) the fit returns 24.0191 mm and 0.3185 um
against a truth of 24.02 mm and 0.3185 um.

**What the line says about itself.** Three figures guard the answer, and the command prints all
three when they matter:

- `r_first_mm` and `r0_extrapolated_mm`: the radius of the innermost zone, and how far inside it
  r0 sits. On the real disc that is 2.3 mm -- r0 is the fit's curvature, not a radius the head ever
  visited, and the printed tolerance is the fit's, not the model's.
- `derived.outer_radius_mm`: where the spiral would end at the disc's own last sector. It is a
  second extrapolation, but in the other direction, and it checks the whole model at once: a full
  25 GB layer has to land near 58.0 mm.
- The tolerance itself: `sigma_r0_mm` comes from the fit in *period* space (the drive's error is on
  the turn it timed, and squaring it over-weights the outer zones). A 200-trial simulation whose
  truth was known scattered 42 um where the covariance claimed 38, so the 1 sigma figure is mildly
  optimistic; the selftest compares the claim against the simulation and fails outside 0.6-1.5x.
- `break_fit`: a one-break two-line fit through (LBA, T^2). A drive reading in zones holds one
  angular speed per zone, so the periods step rather than rise, and one line through them leaves a
  staircase. The detector only reports a break when the line's own residual is large enough to
  explain (rms >= 0.005 ms) *and* two lines remove at least half of it *and* F >= 20; a clean line
  fails the first test on floating-point dust alone, which is why that test exists. A break here
  means the fit describes a staircase with a spiral, so `guide.install_blocker` refuses to turn one
  into a preset.

**What is still missing.** Full ZCLV segmentation -- a fit per zone, with each zone's own angular
speed -- is not implemented, because no disc here does it. What is implemented is the refusal:
the two-zone rotation test says `unknown` when the ratio is neither 1 nor the radius ratio, and the
break detector catches a run whose periods step instead of rising.

## 12. Measured on a real BD-RE

Everything above was offline or simulated. On 2026-11-08 a BD-RE went into the MATSHITA
BD-MLT UJ272 (firmware 1.02; `last LBA 12 088 319`, `complete, sessions 1, erasable True`) and
the solver was run against it. Three runs, ~4 minutes each, all read-only.

**The drive claims one thing and does another.** `info` reports `GET PERFORMANCE` type 00h at
11 447 -> 26 974 kB/s, a ratio of 2.356 against a radius ratio of 2.417: that reads as CAV, and
a precheck that trusted it would refuse the disc. The periods say otherwise:

| fraction | LBA | period ms | rpm | coherence | nominal r mm |
|---|---|---|---|---|---|
| 0.05 | 604,384 | 5.485 | 10939 | 0.480 | 26.72 |
| 0.15 | 1,813,216 | 19.536 | 3071 | 0.815 | 31.46 |
| 0.25 | 3,022,048 | 21.805 | 2752 | 0.877 | 35.57 |
| 0.35 | 4,230,880 | 24.018 | 2498 | 0.910 | 39.26 |
| 0.50 | 6,044,128 | 27.004 | 2222 | 0.932 | 44.22 |
| 0.65 | 7,857,376 | 29.679 | 2022 | 0.957 | 48.67 |
| 0.75 | 9,066,208 | 31.333 | 1915 | 0.976 | 51.42 |
| 0.85 | 10,275,040 | 32.929 | 1822 | 0.983 | 54.04 |
| 0.95 | 11,483,872 | 34.394 | 1744 | 0.991 | 56.53 |

Between 0.35 and 0.95 the period tracks the radius to 0.5%: 24.018/39.26 = 0.6118 and
34.394/56.53 = 0.6084 ms/mm, so 2*pi*r/T = 10.27 -> 10.33 m/s. That is CLV at 2.11x, and it
matches the 13 stored runs (10.33-10.36 m/s) to 0.3%.

Two things had to change to survive real hardware:

1. **The type 00h ratio is not decisive.** After the speed request the same disc reports
   8991 -> 8991 (flat), i.e. CLV; before it, 11 447 -> 26 974 (CAV). The nominal figure follows
   the current speed setting, not the strategy, so the run now measures two zones (halfway out
   and the edge) and lets the period ratio decide: 1.277 against a radius ratio of 1.279 says
   CLV. A disc that really is CAV is still refused -- after two zones, before the other seven.
2. **The first zones after spin-up are not the spindle.** 0.05 came back at coherence 0.480 and
   10 939 rpm (the drive still coasting down from its 6x spin-up), and 0.15 at 0.815. Fitting
   all nine points put r0 7 mm low (17.6 mm, R^2 0.966). Zones below coherence 0.90 are now
   dropped and named in `summary.json` as `zones_unstable`:

```
r0 24.6774 mm, pitch 0.3200 um (anchor), linear speed 10.376 m/s
(R^2 0.999987 over 6 zones; 1 sigma: r0 74 um, speed 0.009 m/s)
```

Three runs gave r0 = 24.716, 24.717 and 24.677 mm -- a 40 um spread against a formal sigma of
72-74 um, and v = 10.379, 10.379, 10.376 m/s. The 24.68-24.72 mm sits slightly above the
23.78-24.38 mm of the stored runs; both groups anchor the pitch at 0.32 um, so the difference is
either the disc or the intercept's long extrapolation from LBA 4.2 M out to 0, not a fitting
artifact that shows up within a run.

`summary.json` now carries both answers, `rotation_check` (what the drive claims) and
`rotation_measured` (what two zones said), so a disagreement is visible instead of silent.

**Refitted in period space.** The numbers above came from the first version, which fitted `T^2`.
Fitting the period itself (the drive's error is on the turn it timed, and squaring it over-weights
the long outer turns) moves the answer slightly and tightens it:

| run | zones | r0 mm | v m/s | R^2 | 1 sigma r0 |
|---|---|---|---|---|---|
| 25 requested at 2.11x (`bdreal6`) | 24 | 24.6735 | 10.391 | 0.999998 | 12 um |
| 9 at 1.6x (`bdreal5`) | 9 | 24.5807 | 7.900 | 0.999996 | 26 um |
| 9 at 2.11x (`bdreal2`) | 9 | 24.4835 | 10.354 | 0.999971 | 87 um |

The three early attempts (`bdreal`, `bdreal3`, `bdreal4`) had been read as CLV runs with r0 of
7.0-12.8 mm; the break detector in the new fit names them for what they are -- a fit whose periods
step twice instead of rising -- rather than reporting a wrong radius with a small-looking sigma.
The 24-zone run is the one worth quoting: 24.6735 +/- 0.012 mm at 2.11x.

## 13. Writing the preset DiscImageStudio actually wants

A Blu-ray preset in DiscImageStudio is not the angular `u`/`v` pair a DVD or CD preset is. It is
three numbers:

```
totalSectors, layerCount = 1, innerRadiusMm, outerRadiusMm, startAngleDegrees = 0
```

and, with no pitch coefficients, the engine solves one constant pitch from them
(`BluRayTrackGeometry`: it bisects a growth rate so the spiral between the two radii carries
`totalSectors / 32 * 962136` channel bits of 74.50 nm). That is exactly the family a BD-R or BD-RE
lives in, and it is exactly what a `--media bd` run measures:

- `r0_mm` is the radius of sector 0,
- `pitch_um` is the track pitch (anchored on the standard, or measured against `--linear-mm-s`),
- `totalSectors` comes from the disc's own last LBA (`info` prints it).

The third radius is not fitted, it follows: `r_out = sqrt(r0^2 + p L N / pi)`, the same area
identity the whole tool is built on. `discprobe/bdexport.py` does that conversion and nothing else.

**The one trap: `pitchLinear` is not a pitch.** `BluRayDiscParameters` describes the pitch shape as
`p(x) = p0 (1 + c1 x + c2 x^2 + c3 x^3)`, and `DvdTrackGeometry.ValidatePitchCoefficients` says so
in its own words: "Pitch coefficients must be finite and 1 + c1*x + c2*x^2 + c3*x^3 must stay
positive". Writing `pitchLinear = 0.32` for a 0.32 um pitch would be read as "a pitch 1.32 times p0
at the outer edge", a 32% flare. A constant-pitch disc therefore leaves all three at 0 and lets the
engine solve p; that is what `bdexport.parameters()` returns, and a test pins it.

**The catalog is a different file.** Blu-ray presets live in
`%LOCALAPPDATA%\DiscImageStudio\blu-ray-presets.json` (`BluRayPresetStore`), schema 1, with records
`{id, displayName, parameters, invertMapping}` -- no `description`, which that store does not keep.
The `disc-presets.json` file this tool's CD and DVD export writes is a different document with a
different schema; the Blu-ray export never touches it.

**What a measurement gave.** The BD-RE in this drive, 12 088 320 sectors:

| run | zones | R^2 | r0 (mm) | v (m/s) | preset inner / outer (mm) |
| --- | --- | --- | --- | --- | --- |
| 1.6x, 9 zones | 7 | 0.999994 | 24.6427 | 7.9054 | 24.6427 / 58.0117 |
| 2.1x, 9 zones | 6 | 0.99994 | 24.6745 | 10.3747 | 24.6745 / 58.0190 |
| 2.1x, 25 zones, `--fit-offset` | 23 | 0.999998 | 25.0148 | 10.342 | 25.0148 / 58.1707 |

The offset run is the outlier and it is instructive: fitting a free per-period delay moved the radius
by 0.41 mm, because an offset and a starting radius are nearly the same parameter over the measured
span. The residuals say the offset is not real -- over 23 zones they run +0.017 to -0.002 ms with no
slope in LBA (1.7e-10 ms/LBA), so `offset = -246 +- 104 us` is a 2.4 sigma wobble of a parameter that
should be zero -- and the two speeds agree to 21 um (24.640 vs 24.661 mm) where a real 0.5 ms delay
would have separated them by 0.2 mm. So the radius is 24.66 mm, `--fit-offset` is a diagnostic
rather than the default, and the command says out loud when an exported preset came from a run that
fitted one.

Why 24.66 and not the standard 24.0: this disc holds 12 088 320 sectors, 131 072 fewer than a full
layer's 12 219 392. In the same physical data area a shorter spiral starts further out. The check is
that the outermost sector then lands at 58.020 mm, against 58.0232 mm for DiscImageStudio's built-in
`bd-r-sl-25gb` preset -- 3 um apart, which no fitting artifact produces by accident.

```
python -m discprobe geo --drive G: --media bd --bd-zones 9
python -m discprobe disexport --geo results/geo-G-.../summary.json --sectors 12088320 --install
```
