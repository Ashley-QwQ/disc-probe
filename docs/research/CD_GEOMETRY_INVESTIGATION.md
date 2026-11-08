# The CD along-track constant: what it is, why timing cannot see it, and what can

Status: investigation note, not a proposal for a behaviour change. Everything below is either
derived (marked *derived*) or measured on this machine on 2026-11-08 (marked *measured*, with the
result directory). Nothing here writes to a disc and nothing ejects one.

## 摘要（中文）

CD 的沿轨常数 `C` 是"读出实际结束位置"与"标称结束位置"之间相差的 EFM 帧数，它同时包含刻录端
（POSO/DAO、刻录模式）和读取端（固件完成点）两部分。本笔记证明：把每个 `n` 都加上 `C` 帧对应的
通道位，与把 `r0` 换成 `sqrt(r0^2 + p*L*C/pi)`（`L = 588*b = 0.1633 mm` 是一帧的轨道长度）是
**同一个拟合**（30 级梯子上数值差 8.3e-10 度），所以计时梯子只能测到 `r0 + C`，永远测不到 `C`
本身。25 mm、1.6 µm 轨距下每帧只折合 1.663 nm 半径，206 帧是 0.343 µm，却足以让 DIS 预设的
径向线在 25→58 mm 之间扭转 44 度。ATIP 的 ±0.15 mm 约合 9 万帧，比要测的量粗三个数量级。可行
的路线只剩：已知零点的光驱做差、两种读命令或两台光驱做差，或者对烧出的径向线拍照/扫描——本仓库
的 206 帧正是这样得到的。烧盘实验与"任何数据布局都带不出 C"的论证见
[CD_ALONG_TRACK_CALIBRATION.md](CD_ALONG_TRACK_CALIBRATION.md)。

正文以下为英文，保留推导、命令与实测输出。

## 1. The question

`disexport` carries one number for a CD preset that the ladder never fits:

    python -m discprobe disexport --geo latest --sectors N --r-min a --r-max b \
        --along-track-frames 206 --output dis_preset.json

`--along-track-frames` (disexport.py:120-136) shifts the preset's inner radius by

    u = sqrt(u*u - v*along_track_frames*cd.FRAME_BITS/pi)          (disexport.py:136)

i.e. it subtracts `p*FRAME_BITS*b/pi` from `r0^2` per frame. The known values are +206 frames
(GH70N, IMAPI Mode 2 Form 1, CMC CD-R), +7 for SN-208FB with cdrdao, 0 for BU20N with READ CD,
and about 25 for the DU-8A5LH (README.md:73, :289; docs/KNOWLEDGE.md:705).

The maintainer's description in discussion #143 — "the data's absolute position along the track,
constant along the track" — is exactly right, but it is worth writing down *which* position it is,
because that decides whether any timing experiment can see it.

## 2. What the constant physically is

A CD groove is one spiral of track pitch p. Position along it is naturally measured in channel
bits, n. For a sector at logical address k the ladder assumes the read completes at

    n_end(k) = ((k+1)*98 + 108)*588                                   (cd.read_end_bits)

98 frames per sector, a 108-frame tail for the CIRC/decoder pipeline.

Nobody knows the real completion point. Call it `n_end(k) + C` with C constant along the track
(this is the "unmeasured firmware completion" in cd.py's docstring). `--along-track-frames` lets
the user write a guess for C into the preset: `along_track_frames` is `C/588`.

Two different physical effects produce such a C and timing cannot separate them:

* reader side: where the drive's pipeline really finishes (servo settle, decoder, transfer start);
* burn side: where the burner put sector 0 relative to the groove ("POSO" vs "DAO").

The second one is why the number is drive *and* burn-path dependent, and why the same ATIP can
still give two different geometries (discussion #143, comment 19432908).

A table of measured `C` values is therefore only as useful as its key. A value recorded against a
reader model alone will not transfer: the same reader on a disc burned by a different drive, or in
a different write mode, can sit tens of frames away (the 0, 7, 25 and 206 above are four such
combinations). If the project ever ships such a table, key each row by *(burner, burn mode,
reader)* rather than by the reader alone, and keep the write mode next to the number -- it is the
field most often missing from community reports.

## 3. Why the ladder cannot measure it (the main result)

The ladder's model is

    phi(X) = Theta(n_X; u, v) - Theta(n_ref; u, v) + c,   Theta(n) = 2n/(S+u),  S = sqrt(u^2+vn/pi)

with `u = r0/b`, `v = p/b` (calib.theta). A shift of C frames adds `C_bits = 588*C` to every n:

    Theta(n+C_bits; u, v) - Theta(C_bits; u, v) = Theta(n; u', v),
    u' = sqrt(u^2 + v*C_bits/pi)                                     (identity, *derived*)

because `Theta(n) = integral_0^n dn'/sqrt(u^2 + v n'/pi)` and shifting the integration range is the
same as changing its lower limit. Numerically, over a 30-rung ladder at LBA 5000..150000,
`v = p/b` with p = 1.6 um, and `C_bits = 206*588` (206 frames), the two sides differ by
**8.3e-10 deg** — floating-point noise.

So **a disc whose data sits C frames further along the groove is fitted with an r0 that is exactly
`C * p*588*b/(2*pi*r0)` too large, and with the same v, the same c and the same residuals.** At
r0 = 25 mm, p = 1.6 um that is

    dr0/dC = 1.663 nm per frame      -> 206 frames = 0.343 um

The two fits are not "close": they are the same fit. No number of repeats, no lower jitter, no
extra rungs helps. `--along-track-frames` is not a fitted quantity and must not be treated as one.

Reproduce it on a saved run (`tools/cd_refit_along_offset.py` re-fits with every n shifted):

    36-rung sim disc, p = 1.584 um, r0 = 25.25 mm
    shift (frames)   r0 (mm)        dr0 (um)   pitch (um)   rms (deg)   chi2/dof
      -200           25.250328      +0.326     1.584000     0.269       1.272
         0           25.250002       0.000     1.584000     0.269       1.272
      +200           25.249676      -0.326     1.584000     0.269       1.272

r0 moves by 0.65 um across the whole range and *nothing else changes at all*: the residuals are
identical to three decimals, the chi-square to six. Sign convention: adding +d frames to the
model's n lowers the fitted r0 by d*1.663 nm; conversely a disc that is d frames "late" is fitted
with r0 too large by the same amount, which is what `disexport.py:136` subtracts.

### What the constant actually breaks

The 0.3 um inner radius is not the visible problem. The visible problem is that the preset's angle
origin moves with r0:

    delta_theta(r) = (2*pi*eps/p) * (r0/r - 1),   eps = dr0             (*derived*)

At eps = 0.343 um (206 frames), p = 1.6 um this is 1.35 rad at large r, falling to zero at r0, so a
radial line written from such a preset is **twisted by 44 deg between 25 and 58 mm** while the
picture still sits on the right annulus. That is the symptom reported for CD burns set up without
the constant, and it is why the number matters at all.

## 4. Why DVD has no such parameter

The DVD model terminates a read at the end of its 16-sector ECC block:

    n_end(lba) = (lba//16 + 1) * 16 * SECTOR_BITS                    (geo.py, media dvd)

so any per-sector offset inside the block cancels, and only a whole-block offset survives — the
model already uses the block end, and the drive's completion is that block end too. One block is
38688 bits = 5.16 mm of track; one DVD *sector* of error would be eps = 25 nm, i.e. a 7.2 deg twist
over 24..58 mm, and DVD pictures land inside 0.2 deg (docs/KNOWLEDGE.md:715), so C_dvd < 0.1
sector. CD has no block quantisation (98 frames = 588*98 bits and the ladder sees single sectors)
and, more importantly, no *self-consistent* end point: the CD pipeline's tail is not tied to any
sector boundary, so C is a free parameter of order 10..200 frames rather than < 0.1 sector.

The CD-DA path in this codebase already says this out loud: "Timing cannot see it; check it once
per drive with a burned straight line" (geo.py:465-466, `read_offset_note`).

## 5. Routes that were considered

| route | verdict |
|---|---|
| fit C from the ladder | impossible, section 3 (exact degeneracy, 8e-10 deg) |
| absolute address from the ATIP | impossible, section 5.1 (~10^5 frames of uncertainty) |
| Q-subchannel MM:SS:FF as an anchor | no new information: it is the same sector index the ladder already counts |
| disc capacity / last LBA | bounded by the same few-tenths-mm tolerance as the ATIP, so the same 10^5 |
| burn a grid and scan it | works; this is how 206 was obtained (8 scans of one disc, docs/KNOWLEDGE.md:705) |
| let DIS fine-calibrate the preset | works; kasumikira and pugod124 did it for CD (discussion #107) |
| read length sweep on one LBA | worth trying for a *length-dependent* part of C, see 5.2 |

### 5.1 ATIP arithmetic (*derived*, from the measured ATIP)

Measured on G: (`results/info-G-20261108-012304`): ATIP lead-in start 97:34:23, so LBA -11077,
and the last lead-out at 79:59:73. One ATIP frame is one channel frame = 588 bits = 16 mm of
track. From the lead-in start to LBA 0 is therefore 11077*16 mm = 177.2 m of groove, so

    r(LBA 0) = sqrt(r_li^2 + p*177232/pi) = sqrt(r_li^2 + 90.25) mm

`r_li = 23.00 -> r(LBA0) = 24.86 mm`, `r_li = 22.35 -> 24.27 mm`. The published lead-in-start
radius is only pinned to a few tenths of a mm, so the program start inherits ~0.1..0.6 mm of
uncertainty. Converting with dr0/dC = 1.663 nm: **0.15 mm of ATIP uncertainty is about 85 000 frames of
C**. The ATIP is three orders of magnitude too coarse to anchor a micron-scale measurement. It is
still useful for what it is good at: it says which disc this is (ATIP 97:34:23, CMC CD-R) and it is
what `--along-track-frames` values are attached to in the docs.

### 5.2 The read length sweep (not yet run)

A part of C that is a *per-sector* pipeline effect (not a fixed arc) would show up as a phase
error proportional to the number of sectors read. `cd_readcmd_compare.py` already measures the
phase of a whole transfer against the same transfer on another read path; the same trick with
counts 1, 2, 4, 8 at one LBA would say whether C contains a `k`-dependent term. If it does not, C
is a pure arc offset and only the optical route applies.

## 6. On-disc experiments on this machine (2026-11-08)

The drive is MATSHITA BD-MLT UJ272 1.02 and the tray holds a **3-track audio CD-R** (CD-DA), not
a data disc:

* TOC: tracks at LBA 0, 70227, 138739, control = audio, `data=False`
  (`results/info-G-20261108-012304`, a read-only TOC/ATIP dump);
* READ(10) at 6 addresses returns 5/64/00 ILLEGAL MODE FOR THIS TRACK, READ CD with header
  0xF8 returns 2352 B with no sync pattern — pure audio samples.

So the data-track route cannot be exercised here at all. What *can* be measured is the CD-DA path,
which the repo supports through `geo --media cd` (`cd_audio=is_cd`, geo.py:113).

**Result: the CD-DA ladder does not run on this drive.** `geo --drive G: --media cd --speed 1411`
settles at T = 48.1127 ms and then dies on the reference (LBA 79220):

    Spindle settled: T = 48.1127 ms (1247.1 rpm), jitter 14.7 us
    LBA 79220: spindle unsteady or reads failing; settling and retrying
    Spindle settled: T = 48.1054 ms (1247.3 rpm), jitter 599.7 us
    stopped: could not measure LBA 79220 near the reference

A direct probe of the same path -- setting `cd_audio=True` by hand, since `timing` does not -- shows
why:

    Zone 0.05 (LBA 7901, r = 26.3 mm): T = 48.1128 ms, 1247.1 rpm, jitter 42.99 us = 0.322 deg
    Zone 0.50 (LBA 79017, r = 35.6 mm): T = 48.1171 ms, 1247.0 rpm, jitter 1319.73 us = 9.874 deg

Two facts follow. First the spindle runs at a **constant 1247 rpm at both radii** — CAV, 2.86x at
26.3 mm and 3.88x at 35.6 mm — and the 1411 kB/s (8x) request did not change that; this drive does
not honour SET CD SPEED for audio (a 353 kB/s run did not finish settling inside its 2 min budget,
so no period was recorded). Second, the jitter grows from 0.32 deg to 9.9 deg between 26.3 mm and
35.6 mm; the default CD range's midpoint (LBA 79220, r = 35.6 mm) lands exactly there, which is
why the run dies at the reference rather than later.

What that 9.9 deg is has not been established. Candidates are the spindle re-regulating after the
cache-evicting far seek (297 ms mid-stroke, measured in the same run) and a defect on this audio
CD-R at r ~ 36 mm. Either way the CD-DA ladder cannot run on this drive/disc pair even at 3x, and
that is a hardware fact to know before spending a night on a CD-R.

## 7. Small, independent code findings

1. `cmd_timing` never passes `cd_audio`, so `timing --media cd` cannot run on a CD-DA disc even
   though `TimingProbe` supports it (`timing.py:88`, `geo.py:113`). The failure message then
   claims the disc is not Mode 1, which points the user at the wrong thing. A tested prototype of
   the missing wiring exists; the change itself is one line in `cmd_timing`.
2. The audio path's `--read-offset-bytes` and the data path's `--along-track-frames` are the same
   physical quantity in different units: one EFM frame is 24 bytes of the audio stream
   (57624 bits / 2352 bytes), so -603 B is exactly -25.1 frames, matching the "about 25 frames"
   recorded for the DU-8A5LH. Neither should be described as measurable by timing.
3. `disexport --along-track-frames` is refused for audio tracks and for non-CD media
   (disexport.py:127-129), which is right, but the help text could say where the number comes
   from (a burned straight line or DIS fine calibration) since it cannot come from `geo`.

## 8. Reproduction

    python tools/cd_along_track_observability.py                 # identity + dr0/dC, no hardware
    python -m discprobe geo --sim cav-audio --media cd --out results/simA
    python tools/cd_refit_along_offset.py results/simA/geo-SIM-*/summary.json --frames -200 200 9
    python -m discprobe geo --drive G: --media cd --speed 1411   # the CD-DA failure in section 6

## 9. Open questions

* Does a CD-R on a drive that honours SET CD SPEED for audio (or a data CD-R) give a ladder good
  enough to test the degeneracy against real residuals? The sim says the residual cannot move at
  all, so the test is really a check on the model, not on the constant.
* `cd_readcmd_compare.py` can measure the *difference* between READ(12)+FUA and READ CD on a data
  disc. That difference is the only timing-accessible handle on C, and it is a relative one. If a
  disc exists where the two paths disagree by 0.5 frames, that bounds the model error for that
  drive without solving the absolute question.
* Whether DIS's fine calibration can recover the 44 deg twist from a picture alone, or needs a
  known reference mark (the two success reports used a known image).

## 10. Follow-up: the burned-disc experiment (2026-11-08)

This note ended at "timing cannot see the constant, and the only absolute route is optical". The
follow-up report, `docs/research/CD_ALONG_TRACK_CALIBRATION.md`, carries the experiment that was
run next, on the assumption that a disc could be made to *carry* the constant:

1. A grid image (`iso/cd-grid.iso`, 348 634 sectors, sha256 `4004...bcf2`) with 5 mm Cartesian
   lines, 5 mm rings and spokes every 30 degrees was built and burned once, Disc-at-once, closed.
2. The data path then worked end to end -- `timing --media cd` with READ(12)+FUA, then two ladders
   at the drive's two speeds (1241.1 and 2482.2 rpm), 24 rungs each, spans 26.398-53.676 mm:
   `r0_eff` 24.837629 +- 0.0064 mm and 24.837638 +- 0.0038 mm, pitch 1.500257 um both times, i.e.
   `5.7 +- 4.7` frames apart -- and the difference is consistent with zero.
3. The burn left no visible spokes. The burn notes attribute that to a sector-layout mismatch (a
   Mode 2 Form 1 image written as Mode 1 at 24x); the alternative, that 24x gives too little dye
   contrast, is not excluded. Section 5a of the follow-up says what the next disc changes:
   `--cd-sector mode1` and an 8x burn.
4. Section 8 of the follow-up answers the question this note left open: **no data layout can carry
   the constant**, because every quantity a read command returns is a function of the same spiral
   coordinate that the constant shifts. Bounding (two speeds), differencing (two commands, two
   drives) and calibration against a drive whose convention is zero all work; solving does not.

The code findings in section 7 are not changed by this note: on `main`, `timing` still does not
pass `cd_audio`, and the `--along-track-frames` help text still does not say where the number comes
from. Both are one-line follow-ups, recorded here so they are not lost.
