# Separating the CD along-track constant on one disc: what a burned layout can and cannot do

Status: design, protocol, measurement and analysis, 2026-11-08. Companion to
[CD_GEOMETRY_INVESTIGATION.md](CD_GEOMETRY_INVESTIGATION.md), which shows that the timing ladder
measures `r0 + C` and never `C` alone. This note asks the next question: with one writable CD-R and
a deliberately designed burn, can the two be separated after all?

Short answer: **only the time-like part of `C` can be separated on one disc, and only if the drive
offers more than one spindle speed for CD.** The absolute number needs an optical ruler, which is a
photograph of the burned lines, not a read command. Both statements are derived below; the measured
part is marked *measured* with its result directory, and anything still pending says so.

## 1. What "C" is made of, and which experiments separate which part

Write the read completion position as `n_end(k) + C`, with `n_end` the nominal end of sector `k`
(`discprobe/cd.py:151-158`, CD_GEOMETRY_INVESTIGATION.md §2). `C` has at least two physical sources:

    C = W  +  R
    W   what the burner's write pipeline adds or drops, fixed when the disc is burned
    R   what the reader's pipeline (FIFO, servo, completion interrupt) adds at read time

Both are measured in EFM frames (588 channel bits, 24 bytes of audio, 163.3 µm of track).

A reader-side term that comes from *time* rather than from *track length* scales with the linear
speed at which the disc is being read: a fixed latency `tau` costs `tau*v/b` frames at speed `v`.
So `R = R0 + tau*v/b`, and because a constant frame count shifts `r0` by `k` per frame with

    k = p*588*b/pi        [mm^2 per frame]

the ladder sees

    r0_eff(v)^2 = r0^2 + k*(W + R0) + k*tau*v/b            (1)

Equation (1) is what the experiments can reach:

| experiment | separates | leaves degenerate |
|---|---|---|
| one disc, one drive, one speed | nothing | `r0`, `W+R0` |
| one disc, one drive, two or more speeds | `k*tau/b` (the slope) | `r0`, `W+R0` (the intercept) |
| same disc in a second drive, same speed | differences in `R0` between drives | `r0`, absolute value |
| same drive, two burn modes | differences in `W` | `r0`, absolute value |
| photograph of burned radial lines | *everything*, to about one frame | — |

The repository's existing recipe is the last row (README.md:73, docs/KNOWLEDGE.md:705), and it is
how the 206-frame number was obtained. The middle rows are cheaper, and this note runs two of them
(one disc at two speeds, §3a) before sketching the optical one (§5); §5a reports why this
particular burn could not supply it.

Why layout cannot help on its own: every read command addresses data by LBA, and an LBA maps to an
arc length through the same spiral that defines `C` (`LBA -> n = LBA*98 frames -> r`, geometry.py).
A pattern inside the data area is a *label on the track*, so reading it back tells the ladder where
it already thinks it is. The
pattern becomes a ruler only if something outside the track reads it: light, or a second clock.
That is the whole content of §4 of CD_GEOMETRY_INVESTIGATION.md, and the reason the disc below is
a grid rather than a clever data pattern.

## 2. The disc that was burned

`iso/cd-grid.iso`, burned once, Disc-at-once, one session, closed:

    size         714,002,432 bytes = 348,634 sectors (681 MiB of 702.8 MiB free)
    sha256       40048498c67ae4f5edc0e3e889fc3ac72d020d8da3b6b14b4a37ffcea14fbcf2
    built with   python -m discprobe image --media cd --geo results/nominal-cd/summary.json \
                     --r-max 56.5 --line-mm 0.45 --output iso/cd-grid.iso

`cmd_image` verifies sampled sectors against the design after writing. The layout is a 0.45 mm
Cartesian grid on a 5 mm pitch (plus circles every 5 mm), 12 radial spokes (one every 30 degrees,
`discprobe/imagedisc.py:38-56`), and a 10 mm letter F that makes a mirrored burn obvious; preview
in `iso/cd-grid.preview.png`. Two properties matter:

* it is a data disc, so `geo --media cd` and `timing --media cd` run on it as on any pressed data
  CD, and the data path (READ(12), 16-sector block reads) is exercised for the first time on this
  machine;
* if the optical route is ever taken, the spokes are there by construction in the data domain,
  which is exactly what a photograph can compare against -- though this burn did not make them
  visible (§5a).

The geometry used to lay the grid out is nominal (24.92 mm, 1.4865 µm) and is not a measurement;
`results/nominal-cd/summary.json` says so in its own `note` field.

## 3. Measurement protocol

Run in this order; each step is read-only except the burn.

1. `python -m discprobe info --drive G:` — check `last LBA` is 348,633, `Disc status: complete`,
   one session, and that the profile is still CD-R. Save the result directory.
2. `python -m discprobe timing --drive G: --media cd --speed 2822` — confirms the data path and
   reports the spindle the drive actually chose. `cd_audio` is not needed for a data disc; the
   audio-CD case is a separate finding (CD_GEOMETRY_INVESTIGATION.md §7) and this protocol does not
   use it.
3. `python -m discprobe geo --drive G: --media cd --speed 2822 --max-targets 30 --reps 24` —
   the ladder. Record `fit.u`, `fit.v`, `fit.chi2_per_dof`, `fit.residual_rms_deg`, `fit.period_ms`,
   `fit.reference_lba`.
4. Repeat step 3 at every CD read speed the drive honours (try 1411, 2822, 4234, and `--speed 353`).
   Each run is a separate result directory; `period_ms` says what the drive did, not what was asked.
5. If any two runs have different `period_ms`, `tools/cd_along_track_speeds.py` fits equation (1)
   across them.

One caution that the protocol depends on: `geo`'s `_rotation_check` requires a constant spindle
speed, i.e. CAV, so within one run the linear speed varies as `omega*r` across the ladder. A
time-like term is therefore a *radial gradient* in `C`, not a constant offset. Equation (1) uses `v`
at the reference radius as a first approximation; the tool reports the gradient check as well, and
the honest statement is that a single CAV run cannot tell a small `tau` from a small pitch error
without the multi-speed comparison.

## 3a. What was measured (2026-11-08, results/geo-G-20261108-033459 and -033747)

The disc above was burned once, Disc-at-once, closed, at 24x CAV (`Disc status: complete, sessions 1`,
`last LBA 348633`). On it the CD data path works: `timing --media cd` reads with READ(12) and the FUA
strategy, the spindle holds 1241.1 rpm at `--speed 1411` and 2482.2 rpm at `--speed 2822`/`4234`
(the drive honours two speeds and no more), and the ladder completed with 24 rungs both times:

| run | spindle | v at reference | r0_eff | pitch | chi2/dof | residual rms | span |
|---|---|---|---|---|---|---|---|
| `-033459` | 2482.2 rpm | 10 994.6 mm/s | 24.837629 mm +- 6.4 nm | 1.500257 um | 2.66 | 0.310 deg | 26.398-53.676 mm |
| `-033747` | 1241.1 rpm | 5 497.3 mm/s | 24.837638 mm +- 3.8 nm | 1.500257 um | 0.50 | 0.132 deg | 26.398-53.676 mm |

`tools/cd_along_track_speeds.py` on the pair: slope of `r0_eff^2` against `v` is 1.2 sigma from zero,
`tau = -0.3 +- 0.2 us`, and the two inner radii differ by 9 nm, i.e. `5.7 +- 4.7` frames out of the 206
the community measures. Residuals against radius are flat at both speeds (slope `0.0000 +- 0.0044`
and `0.0000 +- 0.0070` deg/mm).

The null has a reason, and it is worth stating before anyone repeats the experiment: **the ladder
requires a constant spindle speed** (`geo.py` refuses a run whose period drifts), so the drive turns
at constant angular velocity and the linear speed varies along the track. A fixed read latency `tau`
then delays the completion by a constant *angle* `omega*tau`, not by a constant number of frames, and
the fit absorbs a constant angle into `c`. In CAV the ladder is therefore blind to latency by
construction, and `C` as measured there is a *bit-position* convention of the firmware (where it
considers the sector to end), not a time delay. That is consistent with the community numbers: the
spread (0, 7, 25, 206 frames) tracks the read command and the firmware, not the speed at which the
disc is read.

So the answer to "does a second speed separate `C`?" is no, and not because the drive is unusual: on
a CAV ladder the time-like part never reaches `r0`. Only the optical route below can produce an
absolute number.

## 4. How to read the result

`tools/cd_along_track_speeds.py` reports, for each run, `rpm`, `v` at the reference, `r0_eff`,
`pitch`, `rms`, and then the fit of equation (1):

* slope consistent with zero (|B| < 3 sigma): `C` has no measurable time-like part on this drive at
  this precision. Combined with CD_GEOMETRY_INVESTIGATION.md §3, that is a *positive* result: the
  constant is a pure track-length offset, timing can never see it, and `--along-track-frames` is a
  number that must come from optics or from DIS calibration. It also means the ladder's `r0` is
  exact up to a burn-and-read constant that does not depend on how fast the disc is read.
* slope non-zero: `tau = B*b/k` seconds, and `C(v) = W + R0 + tau*v/b` is predictive: a user who
  measures `r0_eff` at one speed can compute the constant at another. That would be the first
  measurable handle on the constant without a camera.

Either outcome bounds what the project can promise. Neither produces an absolute `C`.

## 5. The optical route, sketched

The repository already contains the calibrated version of this experiment: eight 600 dpi scans of
burned straight lines gave 205.4, 205.6, 206.9 and 206.0 frames, i.e. `C ~ 206` frames with about
one frame of scatter (docs/KNOWLEDGE.md:705, README.md:73). The recipe:

1. burn the grid above (done);
2. scan the disc flat, with the spokes crossing the field of view (the successful runs used 600 dpi
   and grazing light; on this burn nothing came out, see §5a);
3. for each spoke, measure its angle against the model's radial direction as a function of radius,
   giving `delta_theta(r) = c + a/r` with `a = 2*pi*eps*r0/p` (CD_GEOMETRY_INVESTIGATION.md §3);
4. `eps = a*p/(2*pi*r0)`, `C = -eps/k` — one frame is 1.663 nm of radial shift at 25 mm, which is
   what a good 600 dpi scan of a 0.45 mm line can resolve.

This needs optics, not another disc, and it is the only route in the discussion that produces an
absolute number. §5a is what happened when it was tried on this disc.

## 5a. The optical step on this disc: nothing to photograph

*Measured, 2026-11-08.* The burned grid has no visible spokes. A 260 dpi phone photograph and
flatbed scans both give a flat response across the disc (3.0, 3.0, 3.0, 2.9, 2.8 at the five radii
tested), so there is no pattern to fit, rotated or otherwise.

The cause is not established. The burn notes put forward a sector-layout mismatch: `image` built
this ISO with its default `--cd-sector mode2form1`, while the disc was burned as a Mode 1 data
track, and at 24x the resulting pit field carries no visible 0.45 mm geometry. The alternative is
that 24x simply wrote the dye with too little contrast for a 3% scan. The next disc separates the
two explanations: rebuild with `--cd-sector mode1` and burn at 8x, the speed the earlier scans
used, then scan it the same way.

Until that disc exists, the optical route has no measurement here. §3a already settles the
narrower question the available disc can reach: the constant has no measurable time-like part.

## 6. Safety notes

The drive is a slim tray drive that cannot be closed unattended, so nothing in this note ejects or
opens the tray; the burn was done by hand with the drive's own software. The CD-R is writable once:
the image was built, checksummed and verified before the burn, and the burn is a single
Disc-at-once session with the disc closed. Nothing here writes to the disc again.

## 7. Reproduction

    python -m discprobe random --media cd --sectors 340000 --seed 20261108   # filler image
    python -m discprobe image  --media cd --geo results/nominal-cd/summary.json \
        --r-max 56.5 --line-mm 0.45 --output iso/cd-grid.iso
    sha256sum iso/cd-grid.iso        # 40048498c67ae4f5edc0e3e889fc3ac72d020d8da3b6b14b4a37ffcea14fbcf2
    python -m discprobe info --drive G:
    python -m discprobe geo  --drive G: --media cd --speed 2822 --max-targets 30 --reps 24
    python tools/cd_along_track_speeds.py results/geo-G-*/summary.json

## 8. Why no data format can carry this constant

The obvious next idea is to put the reference *into the data*: burn a pattern whose position the
drive can report, and read the constant out of it. That cannot work, and it is worth saying why,
because the idea comes back every time someone meets the identity.

`C` is the difference between two origins: where the spiral physically starts, and where the
firmware starts counting the sector stream. Every quantity a read command returns is a function of
the second one:

| what a read returns | its argument | separates n from n+C? |
|---|---|---|
| the 2048 bytes of a sector | its LBA | no, the LBA *is* n/57624 |
| the header MSF and the Q channel | the address the burner wrote, taken from the ATIP | no |
| P channel track, INDEX 0/1 boundaries | the same spiral | no, they are rings |
| sync patterns, CIRC, C2 flags | inside the 98 frames of a sector | no |
| the completion instant (what the ladder uses) | the integral of n plus a constant | no |

A pattern only changes *which* `f(n)` the disc holds. The shift being looked for belongs to the
disc's own coordinate system, not to the model that reads it, so no `f(n)` can expose it.

The one thing on a CD that does *not* come from the spiral is the factory pregroove: its ATIP is
pressed into the substrate, one frame being 16 mm of arc, and the burner only follows it. That is a
real ruler, and it measures arc length from the pregroove's start -- whose radius the standard
leaves at 22.05-22.35 mm (ECMA-394). `0.15 mm` of uncertainty is about **90 000 frames**, three
orders of magnitude coarser than the 206 frames being measured.

So the compact statement is: the constant can be *bounded* and *differenced* without optics, and
each of those is useful, but it cannot be *solved*:

* two spindle speeds on one drive: `5.7 +- 4.7` frames (section 3a) -- says the constant has no
  time-like part, which is a real result;
* two read commands on one drive: a difference of a few frames (`tools/cd_readcmd_compare.py`);
* two drives on one disc: a difference of tens of frames (BU20N against DU-8A5LH, ~25 frames);
* a drive whose own convention is known to be zero: turns any of the differences into an absolute
  value. That is calibration against a reference, not self-measurement, but it is the only
  non-optical route that produces a number.

Everything else needs optics: the burned grid and a scanner or camera (section 5), which is how the
206 frames in `docs/KNOWLEDGE.md` were obtained in the first place. `--along-track-frames` is
therefore a number to *enter*, not a number `geo` can *produce*; the help text does not yet say so,
and that is a one-line follow-up rather than part of this note.
