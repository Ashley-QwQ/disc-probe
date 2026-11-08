# The Blu-ray geometry solver

What `geo --media bd` measures, how the fit turns completion periods into the three numbers
DiscImageStudio needs, and how well the answer holds up when the same disc is measured again.

This note is the model behind `discprobe/clv.py`; `BD_CLV_FEASIBILITY.md` records the study that
led to it (why the angular ladder cannot see a CLV disc, what the standards say, what the drive
reports). Measured numbers below come from the BD-RE in this drive: 12 088 320 sectors, a single
layer, read at a constant linear speed.

**Nothing in this path looks at the disc.** There is no photograph, no scan and no external optical
reference anywhere in it: the measurement is the drive's own completion timing against the disc's
own sector addresses, and the one number imported from outside is the track pitch the Blu-ray
standard fixes at 0.320 um. A photographic route was explored first and is now frozen
(`BD_SPOKE_SHEAR_REPORT.md`, `tools/experimental/bd_gen2.py`): it needs a camera, a centre someone
picked and a scale someone measured, which is not a step a command-line tool may ask of the user
that runs it. The same three numbers come out of one unattended command in about two minutes
(section 10).

## 1. What the drive gives, and what it does not

At a constant linear speed the disc turns faster at the centre than at the edge, and a read that
starts and ends at one sector takes one revolution to complete. The completion period is therefore a
direct measurement of the radius:

    T(lba) = 2 pi r(lba) / v                                        (1)

and the angle the spindle covered during that read is one turn wherever you are -- which is why the
angular ladder of `geo` (the DVD and CD path, phase against sector index) has nothing to fit here:
its model is `theta(n) - theta(n_ref) + c`, and on a CLV disc `theta` advances at a constant rate per
sector, so the phase is a straight line in LBA with no curvature to measure.

## 2. The identity

The spiral of a disc of pitch `p` and a sector length `L` (mm of track per sector) satisfies the
area identity

    pi (r^2 - r0^2) = p L lba      =>     r(lba)^2 = r0^2 + p L lba / pi   (2)

Put (2) into (1) and square it:

    T^2(lba) = (2 pi r0 / v)^2 + (4 pi p L / v^2) lba
             = b + a lba                                            (3)

So a plot of `T^2` against LBA is a straight line, and its two coefficients are

    a = 4 pi p L / v^2        b = (2 pi r0 / v)^2 .                (4)

For a Blu-ray, `L = 962136/32` channel bits per sector times 74.5 nm per bit, i.e.
2.239973 mm per sector, and `p = 0.320 um` nominal.

## 3. What cancels, and the three ways to close the set

(3) has two measured numbers and three unknowns (`r0`, `p`, `v`), so one of them has to be anchored.
Two of the three matter, and the ratio is the interesting one:

    b / a = pi r0^2 / (p L)                                          (5)

**the linear speed is gone from (5)**. Whatever the drive does with its servo, the data alone fixes
`r0^2 / p`: a run at 1.6x and a run at 2.1x of the same disc have to give the same `b/a`, and they
do (section 6). With `b/a` in hand, one anchor finishes the job:

| anchor | what is measured | how |
| --- | --- | --- |
| pitch (default) | `r0`, `v` | `p = 0.320 um` from the standard; `r0 = sqrt(p L (b/a) / pi)`, `v = sqrt(4 pi p L / a)` |
| speed (`--linear-mm-s`) | `p`, `r0` | `v` known from a throughput measurement or from 1x; `p = a v^2 / (4 pi L)` |
| none | `r0` and `p` pinned to 1x | `v = 4.917 m/s`, reported as pinned rather than measured |

The third case is for a disc where neither the standard pitch nor a trusted speed is available: it
still reports `b/a`, which is what a comparison between two drives should use.

## 4. The estimator

`t` is fitted, not `t^2`. The drive's timing noise lives in the period it timed -- one revolution --
and squaring weights the outer zones by `2 t`, so a least-squares fit in `T^2` lets the far zones
drag the intercept with noise that should have been flat. `clv._period_fit` runs Gauss-Newton on

    t_i = sqrt(a lba_i + b) + noise

with the Jacobian columns `[lba/(2s), 1/(2s)]`, a halving step when `a` or `b` would go negative, and
`cov = s2 inv(J^T J)`, `s2 = sum(residual^2) / (n - 2)`. Outliers are removed first with a MAD rule,
in `T^2` space, where a gross misread is obvious.

The two anchors are not independent parameters, so the variance of `r0` needs the cross term:

    Var(r0) = r0^2 [ cov_aa/(4a^2) + cov_bb/(4b^2) - cov_ab/(2ab) ]   (6)

Dropping `cov_ab` understates the tolerance by about a third on this data (29.5 um claimed against
41.4 um of true scatter in a 300-run simulation). With it, the claimed 1 sigma tracks the scatter
(37.6 against 41.4 um, and the `selftest` keeps a 0.6-1.5 ratio check over 120 repetitions).
`sigma_pitch_um` and `sigma_v_m_s` follow the same way: `sigma_v/v = sigma_a/(2a)`,
`sigma_p/sigma_v = 2 sigma_v/v`.

## 5. What is thrown out, and why

- **Zones whose period is not the spindle's.** After a speed change the platter is still settling;
  zone 0.05 came back with coherence 0.48 on the first run and dragged the fit to 17.6 mm. Anything
  below `COHERENCE_FLOOR = 0.90` is dropped, and the run lists which fractions it dropped.
- **A period offset the data cannot see.** `--fit-offset` adds a free delay to every period. An offset
  and the starting radius are nearly one parameter over a 6 mm segment, so a 2.3 sigma offset moved
  the inner radius by 0.41 mm (`bdreal6`: 25.01 mm against 24.66 mm). The fit is kept but only applied
  when `|offset| >= 3 sigma`; both values are written, and the command says which one it used.
- **A disc that steps.** A drive reading in zones gives a `T^2` line with a break in it. Every single
  break is tried, and one is reported only when the residual has an amplitude worth speaking of
  (>= 5 us), the improvement is at least 50%, and F >= 20; the first gate matters because on a clean
  line every break "explains" some of a vanishing residual. `results` and `disexport --install` refuse
  a run with a break rather than fit a spiral through it.

## 6. Measured, on the discs in this drive

Nine or 25 zones per run, as noted; `a` in ms^2/LBA, `b` in ms^2.

| run | zones kept | R^2 | a (ms^2/LBA) | b (ms^2) | b/a | r0 (mm) | sigma(r0) | v (m/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.6x (`--speed 7193`) | 7/9 | 0.9999943 | 1.441296e-4 | 383.6087 | 2.66155e6 | 24.6427 | 41.6 um | 7.9054 |
| 1x requested (`--speed 4495`, 7.91 m/s) | 7/9 | 0.9999929 | 1.440016e-4 | 383.9123 | 2.66603e6 | 24.6635 | 50.4 um | 7.9089 |
| 1.6x, 25 zones | 22/25 | 0.9999968 | 1.437774e-4 | 383.1293 | 2.66474e6 | 24.6575 | 14.5 um | 7.9151 |
| 2.1x, 9 zones | 6/9 | 0.9999871 | 8.3666e-5 | 223.3088 | 2.66905e6 | 24.6774 | 74.0 um | 10.3759 |
| 2.1x, 25 zones #1 | 23/25 | 0.9999973 | 8.344018e-5 | 222.4349 | 2.66580e6 | 24.6624 | 14.0 um | 10.3900 |
| 2.1x, 25 zones #2 | 23/25 | 0.9999969 | 8.339346e-5 | 222.8052 | 2.67174e6 | 24.6898 | 15.1 um | 10.3929 |
| 2.1x, 25 zones #3 | 23/25 | 0.9999974 | 8.343306e-5 | 222.4712 | 2.66646e6 | 24.6655 | 13.7 um | 10.3904 |
| 2.1x, 25 zones #4 | 23/25 | 0.9999970 | 8.339505e-5 | 222.8281 | 2.67196e6 | 24.6909 | 15.0 um | 10.3928 |

The four 25-zone runs at 2.1x give `r0 = 24.677 mm` (24.6624 / 24.6898 / 24.6655 / 24.6909,
spread 28.5 um, each fit's own tolerance 13.7-15.1 um). The 25-zone run at 1.6x gives 24.6575 +- 14.5 um,
19.7 um lower; the anchor-free `b/a` differs by 0.13% between the two speeds (2.66474e6 against a mean
2.66824e6 at 2.1x), which is the same 20 um of radius arrived at with no anchor at all. A constant
period offset would show up as a speed-dependent radius: `eps*v/2pi` differs by 0.39 mm/ms between the
two speeds, so 20 um bounds any constant epsilon at about 50 us.

Why 24.66 and not 24.0: the disc holds 12 088 320 sectors, 131 072 fewer than a full layer, and a
formatted BD-RE keeps exactly that much (4 096 clusters, 256 MiB) as its inner spare area ISA0 with
no outer spare area. So its last sector still reaches the physical edge (58.0214 mm) while LBA 0
starts 0.66 mm out. Walking the same spiral back over those 131 072 sectors,
`sqrt(24.6655^2 - p*S*131072/pi) = 24.0516 mm`, lands on the start of the data zone the standard puts
at 24.00 +- 0.05 mm -- an independent check of the whole chain, and the number a preset for an
unspared BD-R needs (`disexport ... --pullback-isa0`).

### A pressed BD-ROM, which has no spare area

The same command on a pressed single-layer BD-ROM (`MATSHITA BD-MLT UJ272`, 12 218 368 sectors)
returned

    r0 24.0490 mm, pitch 0.3200 um, linear speed 10.390 m/s  (R^2 0.999996 over 23 zones)
    1 sigma: r0 16.0 um, pitch (anchor), speed 0.002 m/s
    the outermost sector lands at 58.018 mm

with 23 of 25 zones kept (the two innermost dropped, coherence 0.43 and 0.88). That is 0.049 mm out
from the standard's data-zone start and no ISA0 subtraction anywhere: a pressed disc begins its
logical address space where the standard says the data zone begins, while the formatted BD-RE above
begins it 0.66 mm further out because it reserved that region. Two discs, two starting radii, one
instrument, and the 0.61 mm between them is the 131 072 sectors of ISA0 to within the fit's
tolerance -- which is the check the `--pullback-isa0` correction rests on.

The rotation verdict is worth reading again here: `info` reports this disc's nominal rate rising
2.42x from the inner to the outer edge, which looks like CAV, and `GET PERFORMANCE` calls it CLV.
The two-zone test settled it by measurement (the period grew 1.280x against a radius ratio of 1.279),
so the run went on to a full 23-zone line. The drive's answer is a hint; the spindle is the evidence.

A request for 1x (`--speed 4495`) lands at 7.91 m/s as well: the drive floors at one speed for both
requests, so two speeds is all this drive offers and the two-speed check below cannot grow a
third arm. That run kept 7 of 9 zones and its innermost kept zone was at 36.97 mm, 12.31 mm
inside r0 -- visible in `r0_extrapolated_mm` and reported as such.

That 1.6x run also caught a case the coherence gate cannot see: one zone (fraction 0.84) reported
85.71 ms where the trend says 42.9 ms -- exactly two turns -- with coherence 0.9993. The gate tests
whether the period repeats, not whether it is the spindle's, so a harmonic lock passes it. The MAD
clip in the fit dropped that zone and its neighbour, and the run now names the sectors it dropped, so
the number of zones used is not the only record of what was thrown away.

## 7. Cross-checks

1. **Two speeds, one disc.** The speed differs by 24%, the period squares by 73%, and `b/a` -- which
   has no `v` in it (5) -- agrees to 0.15%. If the fit were picking up a fixed cable or firmware
   latency it would move with `v` and this number would not hold.
2. **The whole layer closes.** With the measured `r0 = 24.677 mm`, the standard 0.320 um pitch and
   this disc's 12 088 320 sectors, the outermost sector lands at 58.024 mm. DiscImageStudio's own
   `bd-r-sl-25gb` preset says 58.0232 mm for a full layer, 3 um away.
3. **The other direction.** Take the built-in preset's outer edge (58.0232 mm), the same sector count
   and the same pitch, and the inner radius has to be 24.6698 mm; the timing says 24.677 mm, 7 um or
   0.5 sigma apart. Those two numbers are independent: one is a standard geometry, the other a
   measurement of when reads finish.
4. **Against the thirteen runs already in the tree** (three zones each, 39 zones): outer-zone speeds
   of 10.33-10.36 m/s against 10.39 m/s here, 0.3% apart, on the same drive at the same nominal speed.
5. **All the runs together.** `tools/bd_pool.py` fits several runs of one disc for a single shared
   `k = b/a = pL/(pi r0^2)`, letting each run keep its own intercept (its own speed). Nine runs from
   this disc, 142 zones, give `r0 = 24.662 mm` with a formal 0.9 um -- but one at a time they range
   from 24.6475 to 24.7395 mm, a 92 um spread. That gap is the honest uncertainty: the pooled
   covariance assumes every zone is independent, while each run carries its own offset, and 92 um
   over 1.6x and 2.1x is what a per-run offset of a few tens of microseconds looks like. The pooled
   number is a consistency check on the model, not a claim to 1 um.

6. **DiscImageStudio's own inversion.** A Blu-ray preset carries inner radius, outer radius and a
   sector count; DIS solves one constant pitch from them by bisecting the exact spiral arc length
   (`BluRayTrackGeometry`, `Primitive`). Re-running that bisection on our three numbers
   (24.6575 mm, 58.0180 mm, 12 088 320 sectors) returns `0.320000 um` -- the pitch we anchored on --
   and the exact-arc-length correction to the area identity is 1e-6 relative, under a nanometre on
   the pitch. The preset is self-consistent in the engine that will read it, not only in this fit.

## 8. Where the error is

| source | size | how it shows up |
| --- | --- | --- |
| fit tolerance | 12-15 um | `sigma_r0` in the summary, from (6) |
| run-to-run scatter | 28 um over four runs | larger than the fit tolerance, so the drive is not perfectly repeatable at this speed |
| zone count | 40 um with 5-6 zones vs 14 um with 23 | more zones buy the tolerance; `--bd-zones 25` is the setting used here |
| the pitch anchor | `dp/p` maps to `dr0/r0 = dp/(2p)` | 10% wrong pitch is 1.2 mm at the inner radius, which is why the outer-edge check in section 7 is worth doing |
| weighting | none | weighting zones by their in-zone jitter or by coherence^4 makes agreement worse, not better: across the five 25-zone runs the spread of `r0` goes from 25 um with equal weights to 217 um weighted by 1/jitter^2. Jitter measures media noise inside a zone, not the error of that zone's mean period, so the fit keeps equal weights and a hard coherence gate. |
| extrapolation | 6.2 mm from the innermost zone to LBA 0 | `r0_extrapolated_mm` says how far the answer is extrapolated; it comes from the curvature, not from a zone measured there |

## 9. Limits

- Single layer only. A layer change is a jump in the LBA-to-radius map and no run here crosses
  one, so a disc whose sector count exceeds one layer's 12,219,392 is refused before the ladder
  starts rather than fitted as if the map were continuous.
- Z-CLV discs are detected and refused (section 5), not fitted.
- The pitch is an anchor by default. If a disc's pitch is in doubt, measure the speed separately and
  pass `--linear-mm-s`, then the pitch is the measurement and its tolerance follows `sigma_p`.
- The angular route (`section 12a` of `BD_CLV_FEASIBILITY.md`) covers a disc the drive holds at a
  constant angular velocity; it measures `u = r0/b` and `v = p/b` and exports the same three-number
  preset.

Two things about the hand-over, from `BluRayPresetStore.Import` in the DiscImageStudio source:

- An imported *document* (the file `disexport` writes without `--install`) is turned into a catalog
  entry whose display name is the **file name**; whatever name the document carries is not used.
  The default file is therefore named after the preset (`BD-RE (drive-timing calibration).json`),
  and the command says so when it writes one.
- `--install` does not go through Import: it writes the catalog entry itself, so the ID and the
  display name in the file are the ones DiscImageStudio shows.

## 10. Reproduction

A blank Blu-ray has nothing to time -- an unwritten BD-R reports zero readable capacity and the
measurement refuses it before spinning up. Fill one first:

```
python -m discprobe random --media bd --output iso/bd-random.iso
```

That is a whole 25 GB layer (12,219,392 sectors); burn it with any image burner, then:

```
python -m discprobe geo --drive G: --media bd --bd-zones 25
python -m discprobe disexport --geo results/geo-G-... --sectors 12219392 --install
```

The first prints the fit, the tolerance, the outermost sector, how far `r0` was extrapolated, and
the command that turns the run it just wrote into a preset with that disc's own sector count filled
in, so the second line above need not be retyped from this document:

    For a DiscImageStudio preset: python -m discprobe disexport --geo results\geo-G-20261108-210111 --sectors 12218368 --install

The second writes (or installs) the record and reports the inner radius, the outer radius and the
pitch DiscImageStudio will read it back with.

How much of the disc has to be written for this to work? A partially written disc still measures,
because the fit only needs zones that carry data: refitting the 21:12 run with its zones cut off at
30%, 50%, 70% and 90% of the layer gives `r0` = 24.144, 24.056, 24.079, 24.043 mm and 1σ = 31.8,
22.2, 17.7, 16.5 µm against 24.0501 ± 16.5 µm for the whole disc. Half a disc is within 25 µm of the
full-disc answer and 95% of the tolerance; a third of a disc is not (95 µm out).

Neither one asks a question. The first spins the disc up, decides between CLV and CAV on measured
zones rather than on what the drive claims, settles the spindle, times 25 zones, fits and writes
`summary.json`; the 25-zone runs in section 6 took 1:45 to 2:07 of wall clock on the UJ272, five
minutes inside the six this is budgeted at even when a run loses most of its zones. The second is a
closed-form conversion of that file and writes nothing else. Both exit non-zero, with the reason,
rather than writing a preset they do not trust: a break in the line, a dual-layer disc, a pitch
anchor no radius can satisfy.

## 11. The last few ppm: one disc that times itself and shows its own twist

The timing sees only the product of the inner radius squared and the pitch (`c = pi r0^2 / (p S)`),
and the two are exactly degenerate there. Three ppm of pitch is 0.04 µm on the inner radius, while
the fit reports that radius with 1 sigma = 16 µm: the last few ppm cannot be timed out of a disc
at all. They are also not a property of the individual burn -- the groove pitch is cut by the
stamper the disc was pressed from, so it is constant within a batch and one reading pins it for
every disc of that brand and grade.

That reading costs no second burn. `geo` times rotations out of the sector addresses and never
looks at the 2048 bytes a sector carries, so a disc burnt with a picture can be timed exactly like
a disc burnt with random data:

```
python -m discprobe calibdisc --output iso/bd-calib.iso --preview iso/bd-calib.png
```

lays out a full layer with the nominal `r0 = 24.04 mm` and `p = 0.3200 µm`, showing three rings
(26, 40 and 55 mm) for the radius scale, one line from 12 o'clock to the rim and a short tick at
3 o'clock so the disc cannot be read upside down. Burn it, put it back in the drive, run
`geo --drive G: --media bd --bd-zones 25` on the same disc, then look at where the far end of the
line points: 1 o'clock is 30 degrees, 4 o'clock about 120.

The angle is not proportional to the pitch in the simple way one expects, because on a disc whose
pitch is off, the same sector number lands at a different radius as well. Laying the picture out on
the nominal spiral gives `theta(r) = 2 pi (r - r0) / p`; a disc whose pitch is `p (1 + eps)` puts
the sector meant for `r` at `sqrt(r0^2 + (1 + eps)(r^2 - r0^2))`, and expanding leaves a quadratic
remainder,

    dtheta = pi * eps * (r - r0)^2 / (p * r)

so the dial is a weaker lever than "one turn per turn": read at the rim of this disc, 126 degrees
means `eps` = 11.3 ppm, not 3.3, and 11.3 ppm over the 106,158 turns of a full layer is 1.2 turns
of spiral. `disexport --twist-deg 126` applies exactly that and moves the inner radius by +0.14 µm
and the outer by +0.27 µm -- below the precision a preset is written with, and precisely what makes
the picture close at 58 mm. A second burn of the same disc is the test: the angle disappearing is
the loop closing, the same angle the other way is a sign error, and an angle that does not move at
all was never the pitch (a stamper whose own spiral wanders, which no preset can take out).

**A sector is not always 38 688 bits.** The writer steps along the spiral a channel bit at a time to
decide which design pixel a sector carries, and that step was written for DVDs: 38 688 bits of
133.3 nm track, 5.157 mm per sector. A Blu-ray sector is 2.2399 mm -- 30 066.75 bits at 74.5 nm --
so the same 12.2 million sectors were taken 6.5 mm further out than the drive puts them, and the
design was read at radii that ran away from the real ones. Circles are invariant under an angular
smear, and a 28.7 % error in the radial walk is thousands of turns of angular drift: a disc burnt
before this was fixed shows its rings (26, 40 and 55 mm would come out at 25.6, 37.0 and 49.8 mm)
but neither the line nor the tick. `calib.SECTOR_BITS_BD` and `sector_bits(media)` are what the
picture path now asks for the media it is drawing on.

**What the picture may be made of.** The drive scrambles the 2048 payload bytes (ISO/IEC 30190:
`seed = (lba + 0x100000) >> 5`, 32 sectors to a seed) before its ECC and its 1-7PP modulator, so a
host that wants a chosen byte on the disc has to write `P = Q xor S`; that is what
`discprobe/bd.py` computes, and what a picture compensated with the DVD table (a 15-bit register,
sixteen preset seeds) turns into flat noise on a Blu-ray -- legal, readable, invisible. The texture
`Q` itself is what the modulator sees, so it decides the servo's fate as well as the contrast:
`00` and `FF` give seven gaps with no transition and a digital sum of -8 or +8 per byte, a long run
for clock recovery to coast through, and a picture burnt that way can come back as an L-EC error --
at which point the timing fails and there is no fit at all. `A5` and `B9`, the defaults, keep six
and four of the seven gaps changing with sums of 0 and +2: grey rather than black and white, dense
enough for the servo, different enough in duty cycle to be seen. `calibdisc` refuses a texture pair
that would not, and every sector it writes is an ECC-valid payload, which is why the same disc can
be timed in 25 zones at a coherence of 0.98 to 0.99 and still show a picture.
