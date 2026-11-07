# The Blu-ray geometry solver

What `geo --media bd` measures, how the fit turns completion periods into the three numbers
DiscImageStudio needs, and how well the answer holds up when the same disc is measured again.

This note is the model behind `discprobe/clv.py`; `BD_CLV_FEASIBILITY.md` records the study that
led to it (why the angular ladder cannot see a CLV disc, what the standards say, what the drive
reports). Measured numbers below come from the BD-RE in this drive: 12 088 320 sectors, a single
layer, read at a constant linear speed.

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

## 6. Measured, on the BD-RE in this drive

Nine or 25 zones per run, as noted; `a` in ms^2/LBA, `b` in ms^2.

| run | zones kept | R^2 | a (ms^2/LBA) | b (ms^2) | b/a | r0 (mm) | sigma(r0) | v (m/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.6x (`--speed 7193`) | 7/9 | 0.9999943 | 1.441296e-4 | 383.6087 | 2.66155e6 | 24.6427 | 41.6 um | 7.9054 |
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

## 8. Where the error is

| source | size | how it shows up |
| --- | --- | --- |
| fit tolerance | 12-15 um | `sigma_r0` in the summary, from (6) |
| run-to-run scatter | 28 um over four runs | larger than the fit tolerance, so the drive is not perfectly repeatable at this speed |
| zone count | 40 um with 5-6 zones vs 14 um with 23 | more zones buy the tolerance; `--bd-zones 25` is the setting used here |
| the pitch anchor | `dp/p` maps to `dr0/r0 = dp/(2p)` | 10% wrong pitch is 1.2 mm at the inner radius, which is why the outer-edge check in section 7 is worth doing |
| extrapolation | 6.2 mm from the innermost zone to LBA 0 | `r0_extrapolated_mm` says how far the answer is extrapolated; it comes from the curvature, not from a zone measured there |

6. **DiscImageStudio's own inversion.** A Blu-ray preset carries inner radius, outer radius and a
   sector count; DIS solves one constant pitch from them by bisecting the exact spiral arc length
   (`BluRayTrackGeometry`, `Primitive`). Re-running that bisection on our three numbers
   (24.6575 mm, 58.0180 mm, 12 088 320 sectors) returns `0.320000 um` -- the pitch we anchored on --
   and the exact-arc-length correction to the area identity is 1e-6 relative, under a nanometre on
   the pitch. The preset is self-consistent in the engine that will read it, not only in this fit.

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

```
python -m discprobe geo --drive G: --media bd --bd-zones 25
python -m discprobe disexport --geo results/geo-G-... --sectors 12088320 --install
```

The first command prints the fit, the tolerance, the outermost sector, how far `r0` was extrapolated,
and the command that turns the run into a preset; the second writes (or installs) the record and
reports the inner radius, the outer radius and the pitch it will be read back with.
