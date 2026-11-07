# User manual

Chinese original: [MANUAL.md](MANUAL.md) (in Chinese).

How each command works, its parameters, outputs and self-test results. For an introduction and quick start, see [README](../README.en.md); for experiment records, see [KNOWLEDGE.md](KNOWLEDGE.md) (in Chinese).

## Safety

- Only read commands are sent. A whitelist in `discprobe/scsi.py` rejects any other opcode before it reaches the device, so no write, close-disc or format command can be sent. The self-test checks that WRITE, CLOSE TRACK and FORMAT UNIT are refused.
- The only command that changes drive state is `SET CD SPEED` (to adjust rotation speed), and it is sent only if you pass `--speed` or `--cav`.

## Preparation

1. Open a terminal as **administrator**, otherwise SPTI may not be able to open the device. You can also add `--transport imapi` to the command to use IMAPI2 (`IDiscRecorder2Ex`), which works as a standard user; the default, `auto`, switches to it when SPTI is refused. IMAPI2 also takes exclusive access to the drive and disables media change notification (MCN) during measurement, so polling by Explorer and other programs cannot get in between.
2. Switch the power plan to "High performance" to reduce latency jitter from SATA link power saving (ALPM). This is optional, and its effect needs to be compared in actual measurements. To go further, you can show the hidden "AHCI Link Power Management - HIPM/DIPM" setting and set it to Active in the advanced power options. The command below shows the setting; you can hide it again after measuring:

   ```bash
   powercfg -attributes SUB_DISK 0b2d69d7-a2a1-449c-9680-f91c70521c60 -ATTRIB_HIDE
   ```

3. Close other software that accesses the drive, such as burning software and AutoPlay.
4. The timing test needs a disc **already burned with ordinary data**, preferably a random-data disc made with `python -m discprobe random`. Blank areas have nothing to read; **discs burned with pictures, calibration patterns or uniform textures will not work either**, since drives often report medium errors (3/11/00) on these discs, with retries taking several seconds each time (the exceptions are the random-data rings of a texture ring disc, and an audio-track disc burned by DiscImageStudio on the CD route, described later). Fill the whole disc: measurement positions are chosen as fractions of how much has already been burned, so only a full disc covers the whole radius. DVD-R is best; for CD-R, a data disc is better than an audio track because READ CD has no FUA bit.

## Usage

First enter the repository directory.

List the drives:

```bash
python -m discprobe list
```

Export drive and disc information. This also works on a blank disc and can retrieve its ATIP or MID:

```bash
python -m discprobe info --drive E:
```

Run the timing experiment on a burned disc, about 1 to 3 minutes:

```bash
python -m discprobe timing --drive E:
```

Read one whole aligned DVD ECC block (16 sectors) each time, so each read ends at a consistent position:

```bash
python -m discprobe timing --drive E: --sectors 16
```

Set the read speed (in kB/s; DVD 1x = 1385 kB/s, so 8x = 11080 and 16x = 22160):

```bash
python -m discprobe timing --drive E: --speed 11080
```

Check the whole process on the simulated drive, with no hardware connected:

```bash
python -m discprobe selftest
```

All results go into a timestamped folder under `results\`: `info.json`, or `summary.json` with `events.csv`. `events.csv` records the start and end timestamps of every command for later offline analysis.

## Using it by hand

The hints, progress and animation below only appear when stdout is a terminal. Pipes, redirects and scripts get the same output as before, and result files keep their format. To turn these off in a terminal, set `DISCPROBE_PLAIN=1`.

**Walkthrough.** The first time you run `guide` in a terminal, it asks whether you want a walkthrough. Enter or `y` shows it, `n` skips it, and it only asks once; someone with real measurement results already is not asked. To see it again later, run:

```bash
python -m discprobe tutorial
```

**What to run next.** `guide` reads the `results` folder, lists the steps you have done and prints the next command without touching the drive. Running `python -m discprobe` with no arguments does the same. `guide --media cd` shows the CD steps; without it, the disc type follows your most recent measurement.

```bash
python -m discprobe guide
```

At a terminal, the steps go all the way to the picture image and the burn, with your current step marked. The program does not do the burning and cannot see whether you have burned the disc, so the final step is never ticked. Once the `iso` folder contains a picture image, `guide` also explains how to look at the disc (not straight on) and what to do about different results. This part was put together from the existing documentation and commands and may need adjusting after someone follows it through in practice.

`info`, `timing`, `geo`, `random`, `image` and `disexport` also print the next step when they finish, and `timing`, `geo`, `random` and `image` list your progress before it (simulated drive results do not count as progress). `timing` also gives a verdict: change speed if it is not CAV, try a lower speed if jitter is above about 2°, and above about 5° the drive is probably not suitable (these two limits come from the hands-on reports table and are not strict boundaries). If `geo` stops part way, it gives advice based on why it stopped. When `geo` finishes, it also gives a one-line conclusion and converts the angle uncertainty (1σ within the measured range) to a distance at a radius of 50 mm. It is only classed as good when χ²/dof is no more than 2 and uncertainty is no more than 0.25°; above 0.25° it is usable but noisy, and above 0.6° it is too noisy, with a suggestion to change speed or drive in either case. χ²/dof alone is not enough, because a noisy drive also has large error bars, so its fit can still look good. These two limits come from complete measurements in this repository (clean runs are 0.10 to 0.15°, and the unusable 3226 rpm CD run is 0.77°) and a conversion of the jitter limits in `timing`. They are not strict boundaries, and most external reports do not include this number, so they have not been checked against those reports. χ²/dof above 2 means the deviation is larger than the noise, so it automatically compares constant and quadratic track pitch: if the quadratic model at least halves χ²/dof, it asks you to write a correction file first and includes it in the commands that follow; otherwise it says this is probably read noise and you can carry on. This comparison happens after closing the drive and does not affect the measurement. Like the other hints in this section, the verdict and next step only appear in a terminal; pipes and scripts get just the numbers.

**Drive letter.** `list` lists the drives. At a terminal you can leave out `--drive`: with one drive it is used, and with several you are asked. If the drive letter is wrong, the error lists the available drives.

**Result paths.** For `image`, `tiles`, `beacons` and `disexport`, `--geo` accepts a result folder or `latest` as well as `summary.json`. `latest` selects the most recent complete real measurement, skips simulated drive results and runs that stopped early, and prints which run it chose. Results from runs that stopped early have `stopped` in `summary.json`; results left by older versions do not have this field and can only be judged by fewer than 8 rungs or χ²/dof above 25, so a run that stopped after 8 or more rungs cannot be identified. You can still use a stopped run by specifying its result folder, and the printed explanation marks it as such. `results` lists past measurements, newest first:

```bash
python -m discprobe results geo
```

For a path in a script, use `results geo --latest`, which prints just one line containing the folder path.

**Choosing a past result.** `latest` takes the newest reliable result, skipping those judged too noisy. To choose for yourself, run `python -m discprobe results --pick`, or use `--geo pick` in a command. The first level groups results by disc and drive; within a group, sort by precision or date: `s` changes the sort, `r` reverses it, Enter selects, the left arrow goes back, and `q` quits. Outside a terminal it only prints a list. Results from before 2026-11 did not record the disc type, so they are matched to `info` records with a similar timestamp and the same capacity, and marked with `~`.

**`--sectors` means three things.** In `timing` and `geo` it is the number of sectors per read; `16` reads one whole DVD ECC block (`geo` only accepts 1 or 16, and only 1 on CD). In `random` it is how much to burn, which has to fit. In `disexport` it is the disc's capacity and is required. Enter the same number in DiscImageStudio, otherwise the outer radius changes, and too high a number may also make closing the disc fail. DVD used to default to 2298496 when this was omitted, more than some discs can hold (the disc in [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19440415) has 2295104), so omitting it now gives an error and a suggested value. `info` prints a suggested value at a terminal and says where it came from: for a blank disc it prefers the free space, for CD it uses the lead-out start in the ATIP, and for a burned disc it uses the last LBA plus one (which equals the blank disc's capacity only if the whole disc was filled). Go by the `info` value from a blank disc. If DiscImageStudio's "read-from-disc" gives a different value, still go by `info`: domerawind [reported](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442161) that it gave more than could actually be written (RITEKF1 2298496 versus 2297888, mini DVD-R 714546 versus 713936), and using its value made closing the disc fail. The cause has been identified: the extra 608 sectors on DVD-R are boundary overhead needed to close the disc (TBO 592 plus BSGA 16). See the DIS author's explanation in [#183](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6691519009); this number cannot be applied to every DVD. A preset refitted to 2297888 [closed normally](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6690200194) (one disc).

**Choosing `--speed`.** You can give kB/s or a multiple such as `4x` (with `--media cd`, it is converted using CD's 1x). Lower speed usually means less noise, but not every drive changes speed, so check the rotation speed printed by `timing`.

| | Common values |
|---|---|
| DVD (1x = 1385 kB/s) | `2.4x` = 3324, `4x` = 5540 (the `geo` default), `8x` = 11080 |
| CD (1x = 176.4 kB/s) | `8x` = 1411 (the `--media cd` default), `16x` = 2822, `24x` = 4234 |
| Blu-ray (1x = 4495 kB/s) | `8x` = 35960, `12x` = 53940. Multiples are converted using the actual disc type; all Blu-ray drives reported so far have been CLV, so changing speed may not make them CAV, and `geo` does not support Blu-ray |

**Choosing `--ranges`.** The default, 3% to 85% of the burned area, suits most discs and usually needs no change. It accepts LBA ranges `a-b,c-d`. If `geo` always stops near the same LBA, or the speed jumps near the outer edge, leave out that part; to cover a larger radius, widen the range, provided the drive reads it cleanly (widening it on the GP65NB60 removed the outer error). `info` shows the last LBA.

**CD and DVD.** The steps are the same. Add `--media cd` to each command, which also changes the defaults to CD values. At a terminal, if the disc is a CD but the command has DVD settings, it asks whether to add this first. If the tray is open, there is no disc or the disc cannot be recognised, `timing`, `geo` and `info` say so straight away, including in pipes. `disexport` decides the preset type from the `--geo` result; its `--media` is only a check.

**When something goes wrong part way.** If the tray opens or the disc is removed during measurement, reads return `2/3A` (measured as `2/3A/02` on the GH70N; the first read after opening the tray takes about 4 to 5 seconds, then each read fails in about 5 ms); after a disc change, the standard says it returns `6/28`, which has not been measured yet. On receiving these, `timing` and `geo` stop at once, explain why and exit with code 1, without running through the remaining reads for nothing. "loading" (`2/04`) may be temporary, so it only stops after 100 consecutive occurrences. These checks only apply to failed reads; the timing of successful reads is unchanged. Ctrl+C and a drive disappearing also count as stopping early. What has been measured is kept and marked as stopped early, `guide` does not tick the step, and `--geo latest` does not use it.

If writing an image is interrupted (an error, Ctrl+C or a full disk), the unfinished file is deleted. If parameter checks fail before the file is touched, an old image is unaffected. A `.writing` marker sits beside the file while it is being written: if the process is killed or the window is closed before cleanup can run, the marker stays, so `guide` will not treat the file as finished. The next write to the same file clears it first. The program cannot stop you from burning that incomplete file directly, though.

**Tab completion.** Run the command below once. After that, Tab after `--sp` completes it to `--speed`, Tab after `--media` lists `dvd` and `cd`, and after `--geo` you can choose `latest`.

```bash
python -m discprobe completion install
```

It writes a script to your home directory and adds one line to the shell's startup file (PowerShell's `$PROFILE`, `~/.bashrc` or `~/.zshrc`). **It does not work in the current window yet**: open a new window or run the line it prints. `completion uninstall` removes both, leaving everything else alone. The descriptions follow the current language, or you can add `--lang zh` or `--lang en`. If you do not want it to change the startup file, `completion` with no arguments prints the manual steps.

In PowerShell, Tab on a `discprobe` command line opens a list of options, argument types and descriptions. Tab on other commands is unchanged (an existing custom Tab binding is left alone; Ctrl+Space shows the list). In the repository directory, `python <Tab>` offers `-m discprobe` first. It does not complete filenames where a command or option belongs. bash and zsh only complete text, without descriptions. If PowerShell's execution policy (ExecutionPolicy) does not allow scripts to run, it changes neither the startup file nor the policy. It only tells you what to do and leaves the decision to allow scripts to you.

Pressing Tab does not start Python: all commands and options are already written into the script, and the shell only matches prefixes against the current command's options. Regenerate it after updating disc-probe. It recognises the words `python -m discprobe`, while other `python` commands still complete file paths as usual; however, any existing completion specifically for `python` in bash or zsh is replaced.

**Language.** At a terminal, the default follows the system language: a Chinese system gets Chinese help, hints and measurement output. Traditional Chinese systems currently get Simplified Chinese too. To choose manually, put `--lang zh` or `--lang en` anywhere in the command, or set the environment variable `DISCPROBE_LANG=zh`. Pipes, redirects and `DISCPROBE_PLAIN=1` always use English, leaving scripts unaffected, and ignore `DISCPROBE_LANG`; they only switch to Chinese if you explicitly put `--lang zh` in the command (with UTF-8 output). Result files such as `summary.json` and the output of `selftest` are not translated.

```bash
python -m discprobe --lang zh guide
```

**Progress.** `timing` and `geo` show a progress bar, the current stage, elapsed time and estimated time left; writing an ISO and checking its contents use the same status line, with progress taken from the file's actual size. In a narrow window, key hints, elapsed time and then the progress bar are dropped in that order, without wrapping. The percentage is rounded down and only shows 100% when finished; a digit that has just changed flashes briefly, and at 100% it turns green. Bright green is used if the terminal reports a dark background through `COLORFGBG`; otherwise it uses the terminal theme's own green. Ctrl+C keeps what has been measured, says where it is and exits with code 130.

In terminals that support OSC 9;4, including Windows Terminal, ConEmu, Ghostty, kitty and WezTerm, the tab and taskbar button also show progress, which is cleared at the end. In a wide window, the `timing` and `geo` progress line also has a small graph of the last 12 timed read durations. Taller blocks mean slower reads, and it rescales to those 12 readings each time. It only shows what the jitter looks like and is not a measurement result. These readings are recorded only during the wait after a read. When the window narrows, terminals known to rewrap lines clear the wrapped part; other terminals may leave a short remnant, which does not affect the data.

**Measured lines.** At a terminal, the Zone and Target lines of `timing` are aligned in columns, adding only spaces and trailing 0s removed by rounding, without changing the values. Pipes and scripts get the original bytes.

**After an image is generated.** When `random`, `image`, `tiles`, `beacons`, `rings` or `calib` finishes an image, it prints the full path on its own line and flashes a red warning: burning a DVD+R, DVD-R or CD-R cannot be undone; only RW discs can be erased. The program does not read the drive, so it does not know which kind of disc you have and cannot stop a burn. Picture images made with simulated geometry do not flash, since they already tell you not to burn them. Ctrl+C only skips the flashing, leaving the red text; `--no-animation` shows the red text straight away. On Windows, a muted hint also asks you to check that the burner has the right drive letter, because the burn window may default to another drive.

When `image` uses a picture or the default grid, it draws a disc thumbnail of about 40 × 40 pixels before finishing, in the same orientation as the preview (the data-side view), with areas that cannot be burned shown in grey. With `--picture`, it also points out up to three of these at a time: a nearly all-black or all-white picture, dark content outside the drawable area or in the middle of the disc, a pattern occupying only a very small area, a picture that is not square, a resolution that is too low or too high, or too many grey levels. These are only hints and do not stop generation. The limits are provisional conservative values and have not been calibrated on real discs yet.

**Games.** While measuring, press `g` to open a game below the progress line, `n` for the next game and `q` to close it. Measurement output keeps printing above it and is not covered. These do not appear unless you press `g`. They need animation and a keyboard, so they never appear in pipes, with `DISCPROBE_PLAIN=1` or with `--no-animation`; with `NO_COLOR` they use character art. A game is skipped if it does not fit in the window.

| Game | How to play |
|---|---|
| Snake | Arrow keys or WASD steer; `r` plays again |
| Fill the Disc | Blocks fly in from the right and stack on the left. Up and down move them, right rotates, left drops, a full column clears and scores, and reaching the right edge ends the game. `r` plays again |
| Merge Sectors | Arrow keys slide, equal blocks merge and double, starting at `2K` (`32K` is exactly one DVD ECC block). When there is no room left, `r` plays again. The board is kept for the next wait |
| Sudoku | Arrow keys move, number keys fill, `0` or space clears, and conflicting numbers turn red. After solving it, `r` starts another puzzle. Each puzzle has exactly one solution |

Sudoku's size is chosen the first time it comes up and does not change during that run: with an estimated 30 seconds to 2 minutes left it is 4×4 (2×2 boxes), with more than 2 minutes it is 6×6 (2×3 boxes), and with less than 30 seconds it is not offered. If there is no estimate yet, `timing` assumes 90 seconds and `geo` assumes 300 seconds.

Like the progress line, the games have no background threads: reading keys, moving and drawing all happen in the random wait before a timed read. Only changed cells are drawn, and each game uses its own random numbers. The Merge Sectors save is only written when the progress line closes, never between two reads. On the simulated drive, measuring while playing all four games with the same seed gives the same `summary` and events, entry for entry, as not playing. This has not been compared on a real drive; when measuring an important disc, do not press `g`.

**Local files.** Besides `results` and generated images, the program only writes two small files in `%LOCALAPPDATA%\disc-probe\` (`~/.local/state/disc-probe/` on other systems): `games.json` holds the Merge Sectors board and high scores, and `tutorial_offered` records that the walkthrough has been offered. An unreadable save starts a new game, and a failed save does not affect measurement. Files written for Tab completion are described above. All of these can be deleted directly.

Animation still runs at no more than 8 frames per second, like the previous progress line, but a coloured frame writes more bytes than before. `timing` was compared with the old progress line: the difference with and without it (0.01 to 0.20°) matched the difference between repeat measurements (0.02 to 0.23°). Neither the new animation nor `geo` has been compared on a real drive yet; if this concerns you, add `--no-animation`, or run through a pipe or with `DISCPROBE_PLAIN=1`.

`timing` and `geo` raise the process to high priority while measuring. Before 2026-11-06, this always failed on 64-bit Python, so earlier real measurements on 64-bit Python all ran at normal priority, including the comparison above. Most measurements in the hands-on reports table made with this tool on Windows probably did too; measurements from ports or other probes may differ. The effect of high priority on jitter has not been compared yet.

The progress line has no background thread, to avoid disturbing measurement. ctypes releases the GIL during ioctl. If another thread holds the GIL when a read returns, the completion timestamp can be delayed by up to one 5 ms switching interval, while the jitter being measured is only tens of microseconds. The progress line therefore draws on the main thread during the random wait before each timed read, subtracting the time spent from that wait. This wait is already random. On the simulated drive, the same seed gives identical `summary` and events, entry for entry, with or without this wrapper; this has not been compared on a real drive yet. If this concerns you, run through a pipe or with `DISCPROBE_PLAIN=1`.

**Appearance.** Below the opening screen of `guide` is a greeting. The same time slot within a week always gets the same one; it is just conversation and says nothing about the measurement result. `guide` opens with a disc whose rainbow band turns halfway around and stops. The animation follows the clock and skips frames on a slow terminal instead of taking longer. It falls back in stages according to the terminal's capabilities:

- Windows Terminal, Ghostty, WezTerm, kitty and the Claude desktop app's terminal draw block characters themselves, so in these terminals (requiring UTF-8 and true colour) the disc uses half-block pixels, and only changed cells are sent. The light band moves from white through purple to red, close to diffraction on a real disc. As more steps are completed, the tracks are coloured more deeply from the inside out.
- Other true-colour terminals: the disc uses coloured spaces, with `/` and `\` marking the light band in the middle, and a few `*`, `+` and `.` flashing along its path.
- Below that are 16 colours and plain text. A narrow or short window gets only the title or a single line of text.

The progress line has a small turning disc, and a rainbow highlight sweeps over the current stage text every second or two. The text itself keeps the terminal's default colour, so it is legible on both dark and light themes. The turning is decoration and does not represent the actual rotation speed. In the terminals listed above, the progress bar uses lines, advances in half-cell steps and occasionally shows a highlight passing over the completed part. Other terminals, such as Windows' old console window, default to 7-bit ASCII throughout, so code pages and fonts cannot affect it; if the terminal font supports it, `DISCPROBE_UNICODE=1` switches to finer graphics manually.

| Environment variable | Effect |
|---|---|
| `DISCPROBE_PLAIN=1` | Turns off all hints, progress, animation and Chinese, as in a pipe |
| `DISCPROBE_LANG=zh` or `en` | Chooses the language at a terminal |
| `DISCPROBE_NO_ANIMATION=1` | Same as `--no-animation`: keeps colours and numbers, without animation or games |
| `DISCPROBE_UNICODE=1` | Manually switches to finer graphics in a UTF-8 terminal; not needed for the terminals listed above |
| `DISCPROBE_NO_TUTORIAL=1` | Does not offer the walkthrough; `selftest` uses it too |
| `NO_COLOR=1` | Turns off colour only, keeping animation |
| `CI=1` | No animation |

Nothing is drawn if stdout is not a terminal or `TERM=dumb`.

**Common errors.** If numpy, scipy or Pillow is missing, an install command is printed. A missing `--geo` file or a file that is not a `geo` result, an invalid `--ranges` format or a `--drive` that cannot be opened now gets a one-line explanation, still with exit code 1; parameter errors still use exit code 2.

## What `info` reads

INQUIRY, GET CONFIGURATION (the current profile and feature list), READ DISC INFORMATION, READ TRACK INFORMATION, READ CAPACITY, TOC, ATIP (the CD-R lead-in start time can identify the dye manufacturer, and the maximum lead-out time gives the capacity), DVD physical format information (nominal bit length and track pitch categories, PSN range), DVD-R pre-recorded information (0Eh, including MID), DVD+R ADIP (11h, including MID), GET PERFORMANCE (read and write speed curves against LBA; under pure CAV, the speed ratio between the ends is the outer/inner radius ratio), MODE SENSE 2A (cache size, rotational control mode, write speed list).

The raw hexadecimal data is saved for every command. Items that cannot be parsed or are not supported by the drive are listed separately and do not interrupt the remaining commands.

## The three experiments in `timing`

1. **cache**: Read the same sector 40 times in succession, in three ways: ordinary reads, reads with FUA, and a zero-length READ(12) with FUA followed by an ordinary read (redumper uses this to clear the cache). A median time below 3 ms means the data comes from the cache (over a slow link a cache hit can take longer, so it is also compared with the FUA time). This selects the strategy for subsequent reads in the following order of preference, and records P50/P95/P99 of the read times for each method:
   - `plain`: the drive does not cache repeated reads in the first place;
   - `fua`: FUA works;
   - `flush`: FUA is ignored, but a zero-length FUA read clears the cache;
   - `evict`: none of the above works, so before each measurement, read some data elsewhere to evict the cached data, and discard samples suspected of being cache hits.
2. **period**: Repeatedly read the same sector in each of the inner, middle and outer zones. Use a Rayleigh periodogram of the completion times to estimate the period T of one turn, and report rpm and jitter (in µs and degrees). The same T in all three zones means CAV; T increasing with radius means CLV, in which case the phase method does not hold and a warning is printed.
3. **phase**: Alternate reads of reference sector R and target sector X, and calculate the spindle phase at X's completion time relative to R. Under CAV, this is the angle on the disc between the ends of the two read blocks, plus a fixed decoding delay term, modulo 360°. Random seek times do not affect the result. Slow spindle drift is subtracted by interpolating R's residuals. The output gives each target's mean phase, standard deviation of individual reads, standard error of the mean (sem) and sample count.

## How to read the results

- `cache.strategy`: `fua` or `plain` is best; `evict` also works, but is slower and noisier.
- `period.rotation.mode`: this must be `CAV` for the phase method to be meaningful. If it is CLV, use `--speed` to try another speed setting and measure again. `--cav` sets the Rotational Control bit of SET CD SPEED, but MMC defines this bit as rotational control for writing, so only the period test can tell whether it affects reading.
- `jitter_deg` in each zone: the angle noise of a single measurement, which directly determines precision. To estimate it, after averaging n reads the error is about `jitter_deg / sqrt(n)`.
- `phase.targets[].phase.sem_deg`: the uncertainty of each target's phase. In simulation, the spread of the true errors is about 10 to 20% greater, so this can be treated as a slightly optimistic estimate. These phases are modulo 360°. Unwrapping them and fitting r0/b and p/b still needs the next analysis step (to be written separately).
- `timing` stops early after consecutive read errors and says why; if the period test finds that rotation is not CAV, it skips the phase test (`--force` can force it to continue); by default, the total duration is at most 15 minutes (`--max-minutes`).
- Page 2A's "rotation CLV" in `info` refers to rotational control when **writing**, not the read mode. Use the period test in `timing` to check reading.
- The random pause before each timed read (`--host-delay-ms`, default 25 ms) should be **longer than one turn**. Below 2400 rpm a turn takes more than 25 ms, so increase it, for example to 30 to 40 ms.

## Background and suggested first experiments

The following comes from a research report. I have verified the parts that cite source code.

- **Prior work.** Philips patent US7538787B2 (writing labels on discs) describes the same method as this probe: locate sectors from read completion times; measure the rotation period by repeatedly reading the same ECC block; double the read jump distance at each step of the fit. The method itself therefore has a precedent, but the precision it can achieve on modern SATA drives still needs to be measured.
- **Manufacturer read specifications for candidate models.**
  - HLDS GH24NSD5 reads single-layer DVD±R at 6.6 to 16x CAV, 9360 rpm, with about 6.41 ms per turn;
  - Lite-On iHAS124 F uses CAV at every DVD±R read speed setting.

  The OEM of this rebadged drive has not yet been confirmed, so these specifications cannot be applied directly.
- **The biggest unknown is exactly which position on the disc a completed read corresponds to.** Completion time seen by the host = physical read position + firmware and transfer delay. If that delay changes with the address, it will be wrongly fitted as a "change in track pitch", even if all closed-loop checks pass. An independent comparison with a scanned spoke disc is therefore needed.
- **Suggested first comparison experiments**, all on burned single-layer DVD±R:
  - Run once with the default options and once with `--sectors 16`, and compare whether the two phase curves agree (a constant offset is allowed);
  - run with `--speed 11080` and `--speed 22160` separately;
  - remove the disc, put it back in and run again to check repeatability.

## Simulated drive

`discprobe/sim.py` simulates these behaviours: a CAV spindle (with about 2 ppm/s drift) or CLV (locking to the speed again after each seek), random seek times, a cache with read-ahead (FUA can be made ineffective), decoding delay, 60 µs host jitter and 1% large outliers. The disc geometry deliberately differs from the nominal values. The self-test runs the full procedure in five configurations and compares the results with the simulator's true geometry:

- CAV with working FUA, reading 1 sector and 16 sectors respectively;
- CAV with ineffective FUA, but a zero-length FUA read can clear the cache;
- CAV with neither of the above methods working, so the cached data has to be evicted;
- CLV.

With 40 read pairs per target, the phase error is between 0.8° and 2.2°. Across 8 random seeds, the errors have no bias and their spread is about 1.1 to 1.2 times the reported standard error.

Simulation only proves that the analysis mathematics and procedure are correct. It does not represent the behaviour of real drives. Real jitter, cache behaviour and rotation strategies still need to be measured.

## Ground truth measurement: spoke disc + flatbed scan

This provides an independent comparison for the drive timing method: burn a disc with a spoke pattern, lay it flat on a scanner, and measure how many degrees the pattern has actually rotated at each radius.

### How it works

In model coordinates, the pattern consists of three sets of sinusoidal spokes (k = 3, 21, 63, meaning 3, 21, 63 cycles per turn). DiscImageStudio assigns a brightness to each byte using its own geometry model, so if the model differs from the actual disc, the burned spokes at radius r will all have rotated by an angle δ(r) = actual angle − model angle. In other words, δ(r) is exactly the "bending curve" we want.

The analysis first finds the disc centre in the scan, then divides the image into concentric rings at 0.05 mm intervals, performs Fourier analysis on each ring, and extracts the phases of the three spoke sets:

- k = 3 is used for unwrapping along the radius;
- k = 21 and k = 63 are aligned to k = 3 in turn, with the final precision determined by k = 63;
- at radii of 26, 32, 38, 44, 50, 56 mm, there is a uniform grey marker ring 0.5 mm wide. In the scan, these appear as places where the spoke signal disappears, giving the correspondence "model radius → actual radius".

Several properties make this method less prone to errors:

- **Errors in locating the disc centre and differences in the scanner's x/y scale have little effect.** The angle shifts from these two errors alternate between positive and negative over a turn, and cancel to first order when averaged over the full turn.
- **Unaffected by lighting and diffraction rainbows.** Uneven lighting and the scanner's diffraction rainbow are mainly at frequencies k = 1, 2, while the spokes are at k = 3, 21, 63. Whether spokes are present is judged by the signal-to-noise ratio at that frequency relative to nearby frequencies, rather than relative to the brightness variance over the whole ring.
- **Handles both mirroring and inverted brightness.** Whether the scan is mirrored is detected and corrected automatically; reversing light and dark does not affect the result.

### Steps

1. Generate the pattern. For DVD, set `--radius-mm` to the project's generation outer radius (default 58); for CD, use 57.5 (DiscImageStudio's CD canvas radius is fixed at 57.5 mm):

   ```bash
   python -m discprobe spokes --output spokes.png --radius-mm 58
   ```

   This also generates `spokes.spokes.json`, which the analysis needs.

2. Import `spokes.png` as a layer in DiscImageStudio, centre it and make it fill the canvas exactly. A small scaling error does not affect the angle measurement, but makes the marker rings' "model radii" inaccurate. Leave dithering enabled as it is by default. Then generate or burn with the parameter set you want to calibrate (for example, a preset).

3. Scan: put the disc data side down on the scanner glass, use 600 dpi in greyscale or colour, and save as PNG or TIFF (not JPEG). The disc can be placed anywhere and at any angle. Do not scan it together with a calibration board laid over it, as that would interfere with finding the disc edge.

4. Analyse:

   ```bash
   python -m discprobe scan scan.png --spec spokes.spokes.json
   ```

### Output

- `phase.csv`: one row per radius. `delta_rel_deg` is the bending angle relative to the innermost valid ring; `snr_k*` gives the signal-to-noise ratios of the three spoke sets; `good` marks whether a ring contributed to the result.
- `summary.json`: disc centre position, scanner y/x scale ratio, whether the scan is mirrored, noise per ring, actual radius of each marker ring, and so on.
- `detect.png`: a downsized scan with the detected outer-edge circle and centre hole overlaid. Look at this first to check that the disc was located correctly.
- `unrolled.png`: the disc surface unrolled into a rectangle in (radius, angle), with the innermost ring at the top. If the parameters are inaccurate, the spokes will look bent.
- `unrolled_corrected.png`: the result after shifting each row in the opposite direction by the measured δ(r). Straight vertical spokes mean the measurement is correct.

### Self-test results

The synthetic test simulates a scan with a bending curve from −3° to 220°, radial scaling of 0.2%, a scanner y/x scale difference of 0.3%, a disc centre offset from the scan centre, an arbitrary rotation, binary dithering texture, a k = 2 rainbow stronger than the spokes, a lighting gradient and noise. It tests both normal and "mirrored with inverted brightness" cases. Results:

- Maximum error in recovering the bending curve is 0.23°, rms about 0.04°;
- mirroring is identified correctly;
- the y/x scale ratio is recovered as 1.003;
- the radius errors of all 6 marker rings are within 0.016 mm.

### Not verified yet

Whether the pattern is visible in a real scan, and how much contrast it has, can only be measured in practice. You can first scan an already burned disc to see whether the texture of the burned area is clear.

If the disc parameters are far off, the pattern will rotate by more than 60° between two adjacent rings (0.05 mm), and k = 3 unwrapping will fail. There will then be fewer `good` rings, and `unrolled.png` will show dense spirals. Start with a roughly accurate preset rather than burning entirely from the nominal values.

## Texture ring test disc: find usable grey levels

Purpose: on ordinary DVD±R, find which "textures" other than A5 (dark) and 92 (bright) can consistently show intermediate brightness. This disc **needs no geometry calibration**.

### How it works

When burning a DVD, the drive first XORs the 2048 bytes of user data in each sector with a scrambling sequence (ECMA-267 section 16), then applies EFMPlus modulation. For the bytes actually burned on the disc to equal Q, the bytes written into the ISO must be P = Q XOR scrambling. There are only 16 scrambling sequences, selected by bits 7 to 4 of the physical sector number, so one ECC block (16 sectors) uses the same sequence throughout. The implementation in `discprobe/dvd.py` matches DiscImageStudio's `DvdDataFrameBuilder`.

The test disc consists of concentric rings, each burned with just one Q (or random data). Rings depend only on radius. Even a 1% error in geometry parameters only moves the ring edges by about 0.25 mm, and the scan analysis measures the edges' actual positions.

The default layout has 7 textures (A5, B9, 66, 64, E4, 92, random), each ring 1.4 mm wide, from 25 mm to 54.4 mm, in 3 groups at the inner, middle and outer radii. The ISO is about 4.0 GB. The order is shifted in each group so that a texture does not always sit at the same relative radius. The area inside 25 mm is filled with 92.

### Steps

1. Generate the ISO. To see only the layout without writing a file, add `--describe`:

   ```bash
   python -m discprobe rings --output rings.iso
   ```

   After writing, the tool automatically checks sampled sectors from each ring to confirm that descrambling gives the intended bytes. It also generates `rings.rings.json`, which the analysis needs.

2. Burn: use your burning software's "write image" function to burn `rings.iso` onto DVD±R. Windows Disc Image Burner works. The image contains an empty ISO 9660 filesystem at LBA 16 to 20 (only in the fill area inside 25 mm, without affecting the pattern), so that burning software will accept it; after burning, Explorer shows an empty disc. Record the disc brand, MID (`info` can read it) and write speed, as all of these may affect the result.

3. Look at it by eye first: can you distinguish the shades of the rings under a desk lamp and under diffuse light?

4. Scan: data side down, 600 dpi, **colour**, saved as PNG or TIFF. Turn off all automatic adjustments in the scanning software: auto exposure, levels, sharpening, descreening and colour restoration. Scanning the same disc 3 times, rotating it 90° each time, is recommended to estimate repeatability and the effect of lighting direction.

5. Analyse (you can pass several scans at once):

   ```bash
   python -m discprobe ringscan scan1.png scan2.png scan3.png --layout rings.rings.json
   ```

### What the analysis does

- **Measures ring edges.** Take the median brightness at each radius, find the steepest change in brightness near each predicted ring edge, then fit r² = a + c·LBA. This gives the actual radius of each ring, and also measures r0 and the ratio of "track pitch×sector length" to its nominal value. This is only radial geometry, with no angles involved.
- **Removes the effect of lighting.** The scanner's light and the disc's diffraction rainbow make brightness and contrast vary with angle and radius. Within each 5° angular interval, fit the A5 rings and the 92 rings of the 3 groups linearly against radius, separately, then convert each ring to a "level": 0 = A5 at the same position, 1 = 92 at the same position.
- **Selects a palette.** Combine each texture's levels across groups and scans and calculate the repeatability error σ. Sort from dark to bright. Adjacent levels must differ by at least 3σ to count as separate levels, giving the suggested palette.

### Output

- `textures.csv`: the mean level and standard deviation of each texture in the L (brightness) and R, G, B channels.
- `rings.csv`: details for each ring in each scan, including its actual radius, level, raw brightness and the amplitude of brightness variation with angle.
- `summary.json`: radial fit results, texture levels, pairwise differences in units of σ, the suggested palette and warnings.
- `unrolled_*.png`: the disc surface unrolled in (radius, angle), with the inner ring at the top and texture names on the left. Short red lines mark the fitted ring edges. Look at this first to check that the ring positions match.

### Things to note

- **What levels mean.** Levels are linear only if scanner output is linear with reflectance. Ordinary 8-bit PNG generally has gamma applied, so the order of the levels is reliable, but their spacing is distorted.
- **The scanner distinguishing levels does not mean the eye can.** Include only levels you can also distinguish by eye in the final palette.
- **Differences between the R, G, B channels.** If a texture has noticeably different levels in the three channels, it causes a colour change. This is a clue about diffraction colour.

### Self-test results

- The scrambling register has a period of 32767 (x¹⁵+x⁴+1 is a maximum-length sequence), and the 16 presets are all different.
- A small ISO can be verified throughout after writing; deliberately flipping a byte is detected by verification.
- Conditions for the synthetic scan: actual r0 of 23.96 mm, "track pitch×sector length" 0.8% above nominal; lighting varies with angle and radius; a random offset of 0.01 levels per ring; 66 and A5 are exactly as dark as each other. Results:
  - All 22 ring edges are found, r0 is recovered as 23.9597 mm and the ratio as 1.00795, with an edge rms of 0.003 mm;
  - texture level errors do not exceed 0.010;
  - the suggested palette is 66 64 E4 B9 RND 92, correctly merging A5 and 66 into one level.

## Multi-hypothesis calibration disc: measure the whole disc's geometry with two discs and two scans

The idea proposed by a user: assume geometry parameters, draw a pattern, scan it to see how much it is distorted, and work back to the true parameters; then try several hypotheses in parallel on one disc. This section implements that idea.

### Why two discs are needed

With geometry parameters 1% off, the pattern makes about 5 extra turns over a 1 mm radial span, so the scan is just grey. The first disc therefore only needs to "find the approximate range", and the second improves the precision.

### First disc: bracketing

- The disc surface is divided into 39 narrow bands (about 0.62 mm each), separated by 0.2 mm guard rings of pure 92.
- Each band has threefold spokes, but uses a different "hypothesis": multiply the nominal geometry's local turn rate by 1+s, with s from −1.2% to +1.2% in steps of 0.2%, for 13 settings in all.
- These 13 settings are repeated at the inner, middle and outer radii (3 groups), so a full set of hypotheses is available near each radius.
- Once burned on a real disc, only bands whose s differs from the true turn-rate error by less than about 0.15% have clear spokes; the rest blur to grey.

How the `calscan` analysis works:

1. **Locate the bands.** Fit r² = a + c·LBA to the guard ring edges to determine the sector number corresponding to each scanned ring.
2. **Measure each clear band.** The rate at which the spokes rotate with radius directly gives the true local turn rate there.
3. **Coarse fit.** Two or more bands at different radii give a linear solution for u = r0/b and v = p/b, the two ratios that determine all angles.
4. **Fine fit.** All bands share one unknown overall rotation, so their phases are fitted jointly too. Each band's "radius error" is fitted as an unknown with a prior (10 µm), so small radius errors from the scanner do not bias the result.
5. **Mirroring and inverted brightness.** The spokes contain a ninefold component phase-locked to the threefold component. This gives the pattern handedness, so a mirrored scan is detected automatically; reversing light and dark does not affect the result.

### Second disc: refinement

Use the first disc's fit to draw all 20 bands with the same (already very accurate) geometry. Every band now "matches", so radius errors no longer affect the phases, and precision is determined by phase noise. This amounts to the second step of Newton's method, and only this step is needed.

### Steps

1. Generate the first disc:

   ```bash
   python -m discprobe calib --output iso/cal1.iso
   ```

   If you already have closer parameters (for example, a DiscImageStudio preset for a brand, or r0 measured with a texture ring disc), you can use `--r0-mm/--pitch-um/--bit-nm` to centre the sweep on them.

2. Burn, scan (as for the texture ring disc: 600 dpi, no automatic adjustments, save as PNG/TIFF), then analyse:

   ```bash
   python -m discprobe calscan scan1.png --layout iso/cal1.cal.json
   ```

3. Generate the second disc using the first disc's result, then burn, scan and analyse:

   ```bash
   python -m discprobe calib --refine-from results\calscan-...\summary.json --output iso/cal2.iso
   ```

   ```bash
   python -m discprobe calscan scan2.png --layout iso/cal2.cal.json
   ```

4. In the second disc's `summary.json`, `fit.dis_equivalent` gives parameters you can enter directly into DiscImageStudio: the inner radius for a bit length of 133.3 nm, and the outer radius calculated from your disc's total sector count.

### Output

- `bands.csv`: one row per band, including whether it is clear, why it is not clear (blurred / rotating too fast / not straight), the measured local turn-rate error `s_local_needed`, whether the fine fit accepted it, the fit residual, and the fitted radius offset.
- `phase.csv`: signal-to-noise ratio and phase for each scanned ring.
- `summary.json`: u, v, r0 and track pitch converted using 133.3 nm, angle uncertainty over 24 to 58 mm, how many degrees the nominal geometry was originally off by, and `dis_equivalent`.
- `unrolled.png`: the unrolled view, with s for each band labelled on the left. Green means clear, grey means unclear.

### Self-test results

The synthetic disc's true geometry: r0 23.95 mm, track pitch 0.7365 µm, bit length 133.6 nm. Over 24 to 58 mm, it turns about 64000° further than the nominal geometry.

| | Clear bands | Angle error over 24 to 58 mm | Reported 1σ |
|---|---|---|---|
| Bracketing disc, normal scan | 9 / 39 | 1.3° (coarse fit 13°) | 2.3° |
| Bracketing disc, mirrored with inverted brightness | 9 / 39 | 4.7° (coarse fit 12°) | 2.3° |
| Refinement disc | 20 / 20 | **0.08°** | 0.023° |

- The bracketing disc's error mainly comes from the "radius-error prior": in bands that do not match exactly, every 1 µm of radius error gives several degrees of phase error, so only a precision of a few degrees is possible here. That is already enough to make every band of the refinement disc match.
- The uncertainty reported by the refinement disc is optimistic (the actual error is about 3.5 times as large), so allow some margin when judging it.

### Not verified yet

- **Visibility.** Each byte in a band is chosen as A5 or 92 with a given probability, and the scanner sees their average brightness. Whether this mixed texture has enough contrast on a real disc has to be checked on the first disc. A texture ring disc can also answer this first.
- **The scanner's own geometry errors.** Local stretching and periodic errors have not yet been measured; a checkerboard calibration board can be used to check them. The reliability of the refinement disc's result depends on this.
- **Hypothesis range.** The default only covers ±1.2%. If the first disc has no clear bands at all, you can widen it to ±2.5%: `--s-range 0.025 --s-step 0.0025 --groups 2` (the settings still overlap); or move the centre parameters elsewhere and try again.

## Measuring geometry from timing: the "ladder" (`geo`)

Have the drive measure the spiral geometry of a burned disc directly, without a scan.

### How it works

When the drive spins at a constant speed, converting the difference in completion time between reading reference sector R and target sector X into a rotation angle gives the angle between the ends of the two ECC blocks on the disc (plus a constant c, the difference between their decoding delays, ideally about 0):

φ(X) = Θ(n_X) − Θ(n_R) + c (modulo 360°)

Here Θ(n) is the same model used for the calibration disc, determined only by the two ratios u = r0/b and v = p/b.

The difficulty is that only the angle "modulo 360°" can be measured, while the nominal geometry is off by thousands of turns over long distances. The measurement therefore works outward rung by rung, like climbing a ladder:

1. **Stabilise the rotation speed.** Read the reference sector repeatedly until the measured period stops changing.
2. **First rung.** Start by measuring positions 1.5 turns and 4 turns from the reference. At such short distances the nominal model is only a few degrees off, so c can be determined.
3. **Extrapolate rung by rung.** Fit u, v and c after each rung (with loose priors on u and v), then choose the candidate furthest from the reference with a "prediction error below 25°" as the next rung. The prediction determines the number of whole turns; measure, then fit again. Each rung makes the model's prediction more accurate, and the reachable distance grows by multiples. The default 22 rungs for DVD and 36 rungs for CD can cover the full readable radius.
4. **Check the rotation speed.** Measure the reference sector's period again at every rung. If the speed changes during the measurement, wait for it to stabilise before measuring again.

### Usage

```bash
python -m discprobe geo --drive H:
```

- Before measuring, it compares the rotation at the inner and outer parts of the disc. If the drive is in CLV, it stops within seconds and says why, instead of spending a long time on a few useless points. Setting a speed can take some drives out of constant rotation until the disc is reloaded. If that happens, reload the disc, check that `timing` says CAV, then use `--speed keep`, which sends no speed command and leaves the drive as it is.
- By default it measures 3% to 85% of the burned area, with the read speed fixed at 4x (`--speed 5540`). This GH70N changes rotation speed beyond about 53 mm in the outer area, so the default avoids it.
- To use only the random-data rings on a texture ring disc:

  ```bash
  python -m discprobe geo --drive H: --rings-layout iso/rings.rings.json --texture RND
  ```

  Pure single-byte textures (especially `64`, `92`, `66`) are very difficult for this drive to read, triggering retries and changes in rotation speed.
- Output:
  - `targets.csv`: the measured phase, prediction, whole turns and fit residual at each rung;
  - `summary.json`: u, v, r0 and track pitch converted using 133.3 nm, angle uncertainty over the measured range and over 24 to 58 mm, and `dis_equivalent`.

### Findings from measurements on this drive (GH70N, Ritek F1 DVD-R)

- **Cache and FUA.** Repeated reads of the same sector without FUA take about 1.1 ms and come from the cache; with FUA they take about 42 to 47 ms and actually read the disc. The cache detection threshold has been changed from 1 ms to 3 ms.
- **The whole-turn problem.** With FUA, each reread always takes a whole number of turns, so you must wait a random 0 to 25 ms (`--host-delay-ms`) before each read. Otherwise, only a total duration of "a few turns" can be measured. This behaviour has been added to the simulator (`reread_delay_ms`).
- **Rotation speed.** With the read speed fixed at 4x, after about 30 s to stabilise, the rotation speed is 2831 rpm (21.195 ms per turn), unchanged over 26 to 47 mm.
- **Precision.** In random-data areas, the phase standard deviation for one reading is 0.43 to 0.55°, or ±0.07 to 0.09° after averaging 40 readings.
- **Self-test.** On the simulator, a 14-rung ladder gives about 1° of angle error over 0 to 85% of the disc, consistent with the reported 1σ.
- **Real disc.** A 21-rung run on the 3 random-data rings of a texture ring disc (33.6 to 45.8 mm) gave a residual rms of 0.096°, a constant c = −0.009° and 1σ of 0.13° within the measured range. See [KNOWLEDGE.md](KNOWLEDGE.md) (in Chinese).

## Burning pictures, textures and colour

Once the geometry has been measured from timing, it can be used directly to generate a burnable ISO (Windows Disc Image Burner can burn it), without taking photos or tracing points. Photos of the finished discs are in [`showcase/`](showcase/README.md).

**Burning pictures (`image`):**
- Generates a test grid by default; `--picture` uses a greyscale image (thresholded), keeping its proportions with its longer side spanning `--diameter-mm` (116 mm by default) and the remaining space left blank. Large images work too, but detail beyond this size is scaled away; `--design-npy` uses a 6000 × 6000 design array with 0.02 mm cells (viewed from the data side, y upwards).
- Boolean designs use the two textures `--dark` and `--light` (`A5` and `92` are recommended). uint8 label designs use `--textures`, giving each texture in label order: a single byte (`A5`), a repeated sequence with its phase set by the data-frame column (`8B00`), random data (`RND`) or a random mix (`MIX:92,4F`).
- Example:
  ```bash
  python -m discprobe image --geo <summary.json> --design-npy design.npy --textures RND A5 92 8B --output pic.iso
  ```
- After each generation, sectors are sampled and checked byte by byte against the design.

**Textures and colour:**
- `discprobe/efmplus.py`: an EFMPlus encoder with DSV selection (ported from DiscImageStudio). It predicts the pit and land patterns the burner actually writes and searches for periodic textures (`evidence/coverage/`). It also shows that the burner's DSV control holds pit/land coverage at 50% over large areas, so visible contrast can only come from run-length classes and along-track diffraction.
- `tiles`: a self-locating colour-chart target disc. Each tile has a differentially encoded number (readable even when light and dark are reversed) and a set of texture patches; `--ring-edges`, `--tile-mm`, `--cols` and `--scale` adjust the layout.
- `tilescan`: reads flatbed scans, first removes the scanner's column stripes, then automatically finds rotation and mirroring, reads the numbers and measures the patches.
- `discprobe/tilephoto.py`: reads phone photos. It uses the disc-edge ellipse and the image of the disc centre to find the vanishing line, fits a homography, then checks it against the numbers. `tools/flash_lut_tiles.py` calculates the camera position from flash photos and builds a lookup table of "texture × viewing geometry → colour".

**Viewing advice:** The rainbow "pizza slices" are diffraction from the factory groove. View near the specular direction of a small, bright light source (with the light right next to your eye or camera), and the picture is visible across the whole disc. See [`KNOWLEDGE.md`](KNOWLEDGE.md) (in Chinese) §10 to §10f.

## CD-R: textures, timing and burning pictures

`rings`, `random`, `timing`, `geo`, `image`, `tiles` and `gridscan` support `--media cd`; DVD remains the default. A CD sector has 57624 channel bits; implementation and timing assumptions are in the [CD physical model](CD_PHYSICAL_MODEL.md) (in Chinese). The measurement and grid-disc parts have been tested on an HL-DT-ST GH70N and CMC CD-R. Changing the drive or disc needs fresh verification.

For your first CD, follow the [README's CD route](../README.en.md#cd-route) first. You need at least 3 blank discs from the same batch (measuring, calibration, picture). This section gives the details of each step and other methods.

To see the light and dark areas produced by different data first, you can burn a texture ring disc that needs no angle calibration:

```powershell
python -m discprobe rings --media cd --output iso/cd-rings.iso
python -m discprobe ringscan scan1.png scan2.png --layout iso/cd-rings.rings.json --refs 0D,AA
```

The default is 15 rings, 26 to 56 mm, with textures `0D,AA,10,63,RND`. The CD layout automatically chooses `0D,AA` as the scan references; `--refs` can instead select the two textures measured as darkest and brightest. ISO LBA 16 to 20 stay in the inner background. CD images above **359,849 sectors** produce an error; they are not automatically shortened, and existing CD images or sidecar files with the same names are not overwritten.

**Burning.** Windows IMAPI2 writes CD data as Mode 2 Form 1, with user data starting at byte 24 of the sector, so `--cd-sector` defaults to `mode2form1`. Pre-scrambling with the Mode 1 offset turns the texture into noise. IMAPI needs a little room to close the disc: on a disc with 359,847 sectors, an image of 359,800 sectors was refused, while 359,600 worked. Burn at 8x on the GH70N; SATA resets have occurred at 40x.

```powershell
python -m discprobe random --media cd --output iso/cd-random.iso
powershell -ExecutionPolicy Bypass -File tools/burn_imapi.ps1 -Drive H: -Iso iso/cd-random.iso -Speed 8 -Burn -Reload
```

The drive does not report progress during burning, so the script prints a line every 30 seconds with the elapsed time and the remaining time estimated from the write speed. The tray opens after the burn; `-Reload` only pulls it back in and does not open it first. On a slim drive, push it back in yourself. Running `timing` with the tray open only reports that it is open.

**Measuring.** Burn a random-data disc first, then run timing. Use a low rotation speed: on the GH70N at `--speed 2822` (3226 rpm), reads complete about 0.2 ms late beyond 49.8 mm; this does not happen at `--speed 1411` (about 2080 rpm).

```powershell
python -m discprobe timing --media cd --drive H: --speed 1411
python -m discprobe geo --media cd --drive H: --speed 1411 --host-delay-ms 35 --ranges 2000-356000
python tools/geo_polyfit.py results/geo-H-... --write-correction correction.json --phi-degree 7
```

`geo_polyfit.py` prints the leave-one-out error for each polynomial degree; use it to choose the degree. The pitch on this batch of CMC discs has a wave: rms is 0.233° at constant pitch, 0.163° at quadratic and 0.080° at degree seven.

**Along-track constant.** Timing cannot measure "the absolute position of the data along the track", so this constant is still missing after measuring a CD's geometry. It makes radial lines twist in the shape of `c + a/r`. Its value differs greatly between paths: GH70N with IMAPI (Mode 2 Form 1) gives about 206 frames; TSSTcorp SN-208FB with cdrdao (Mode 1, [DiscImageStudio #130](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/130)) gives about 7 frames. The latter value comes from a fit to one photo and has not yet been checked on a second grid disc. Do not use someone else's value directly. There are two ways to determine this constant.

**Recommended: use DiscImageStudio's fine calibration.** Use `geo` in place of its coarse calibration and edge calibration to burn fewer discs and trace fewer points. The along-track constant has an effect equivalent to changing the inner radius by only about 0.3 µm (206 frames). Fine calibration already fits the radius, so by calculation it should absorb this too, without a grid disc. This route comes from CD-R measurements by kasumikira ([#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19415813)) and pugod124 ([disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2#issuecomment-6650565706)); we have not followed it ourselves yet.

1. Export the preset. For `--sectors`, use the number `info` gives on a blank disc, and enter the same number in DiscImageStudio. A different sector count also gives a different outer radius. If its **read-from-disc** gives a different number, go by `info` (see "`--sectors` means three things" above).

   ```powershell
   python -m discprobe disexport --geo <summary.json> --correction correction.json --sectors <sectors> --output dis_preset_cd.json
   ```

   `disexport` checks `media` in `summary.json` and exports CD results as CD presets (`sectors`, inner and outer radius and three pitch coefficients, with the speed fixed at 1200 mm/s). `--sectors` is required; the fit range defaults to the range measured by `geo`. No file is written if the preset differs from the measurement by more than 5°.

2. Put the preset into DiscImageStudio using either of two methods: enter the inner and outer radius, sector count and three coefficients by hand on the calibration page; or add the `preset` object from the output to the `cdPresets` array in `%LOCALAPPDATA%\DiscImageStudio\disc-presets.json`, then restart the program (the format is in its [preset documentation](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/blob/main/docs/DISC_PRESETS.md) (in Chinese). moodyos imported it successfully this way; we have not tried it ourselves).
3. On the assisted calibration page, choose **fine calibration** directly, create a target, burn the disc, take and rectify a photo, trace points along one thin arm of a cross line, then solve and apply. Fitting cubic pitch needs at least 12 points at different radii, covering 60% of the annulus width. Its [calibration guide](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/blob/main/docs/CALIBRATION.md) (in Chinese) has the steps.
4. After applying it, save it as a preset and burn pictures with these parameters.

Its CD calibration disc output is `.wav` or `.raw`, while a finished picture may use a Mode 1 data disc. We have not verified whether the along-track positions are the same on the two burning paths; if the lines in the finished picture twist again, check this first.

**To avoid tracing points by hand: burn a grid disc.** Generate a grid disc with your own estimate of the constant, or enter 0 if you have no estimate. After burning, look at the twist of the radial lines and correct the constant. The square grid lines are spaced 5 mm apart and create a false peak every 5 mm, so only the radial lines can be used to judge it (`evidence/cd-geo-20261104/grid2-scan/grid_spokes.py`). The constant can be worked back from the twist: fit `c + a/r`; one frame has a track length of about 0.163 mm, and `|a|` (radians·mm) divided by 0.163 is the difference in frames between the constant currently used and the true value. In #130, a disc was burned with 206 frames, and the twist gave a difference of 199 frames. A flatbed scan may not show it clearly (the scanner in #130 only gave a difference of about 3/255); a photo under a light can be used instead.

```powershell
python -m discprobe image --media cd --geo <summary.json> --correction correction.json --along-track-frames <frames> --output iso/cd-grid.iso
```

Once the constant has been determined, it can also be passed to `disexport --along-track-frames` to export a preset directly. Without it, the output warns that radial lines may be twisted. Others have already burned discs with CD presets: moodyos got the same outline as the original without fine calibration; FanJZSS exported with `--along-track-frames -100`, only about 2 frames from DIS fine calibration. Both are user reports; see the [README table](../README.en.md#drives-with-hands-on-reports).

**Another route: measure an audio-track disc burned by DiscImageStudio directly.** DiscImageStudio can burn a picture as one audio track (CD-DA). On such discs, `geo --media cd` switches to READ CD. Before each timed read, it reads a distant sector to evict the cached data (automatically increasing to 2, then 4 sectors if needed; only if that still fails does it fall back to the 1024-sector cache eviction used on data discs). It uses DiscImageStudio's own origin: sector k ends at byte 2352(k+1) in the audio-track byte stream written to the disc. The measured inner and outer radii are therefore the ones to enter for this kind of disc, and `dis_equivalent` in `summary.json` gives them directly using the sector count on the disc. Neither the 108-frame read tail nor the 206-frame along-track constant of the data-disc path is needed.

Only one constant remains: how many bytes before the end of the sector this drive's READ CD completes. Give it with `--read-offset-bytes`; it is recorded in `summary.json`. On the HP BU20N it is 0 (checked against a straight line burned on a disc); on the PLDS DU-8A5LH it is about −603 bytes (found by comparing results on the same disc with the BU20N). When reading with a different drive, check it against a straight line burned on a disc first.

```powershell
python -m discprobe geo --drive E: --media cd
python -m discprobe geo --drive E: --media cd --read-offset-bytes -603
```

Export a preset from this kind of result with `disexport`. It neither needs nor accepts `--along-track-frames`. `image` and `tiles` write data tracks with a different origin, so they reject these results; they still need results measured on a data disc.

The measurement is of the disc's own geometry, independent of the parameters used to burn it, so a probe disc burned with nominal parameters is enough. A banana CD-R measured on the BU20N differed from another independent program ([dis-cd-timing](https://github.com/WindowsNoEditor/disc-probe/tree/dis-cd-timing/contrib/dis-cd-timing)) by only +5 nm / −4 nm; straight lines burned using that program's results were straight.

`image --media cd` also accepts Boolean/label `--design-npy`, `--textures` and `--picture`. With `--picture`, the area inside a radius of 26 mm is automatically left blank because the file system is there. The drawing unit becomes 12 consecutive data symbols in a physical frame. Repeated textures have their phase set by "physical frame number ×32 + F2 slot", then user data is filled back through the CIRC mapping. Dark/light default to `0D`/`AA`; the design should leave an inner background margin, and generation is refused if file-system sectors overlap the pattern. CD timing results carry `media=cd`; DVD fits must not be used directly to burn CD pictures.

CD `tiles` use `0D`/`AA` as the number references, while `tilescan` and `tilephoto` reuse the original number and geometry processing. For CD, the historical field name `levels_a5_0_92_1` in the analysis output means `0D=0 / AA=1` for the numbers. Repeated sequences such as `0DAA` and `00FF` are candidates to test; they do not guarantee that the drive produces a fixed period along the whole track. CD groove diffraction is closer to the specular direction. For photos, use a small light source with an angular size below 10°, and fix the viewing geometry first.

Run `python -m discprobe selftest` to check scrambling, forward and inverse CIRC mapping, independent reverse reconstruction, corruption detection, the simulated ladder, synthetic scans and 3T to 11T / DSV consistency with the reference EFM. Software validation data is in [`evidence/cd-support/`](../evidence/cd-support/selftest-final.txt) and [`evidence/cd-support-20261104/`](../evidence/cd-support-20261104/validation.json). Real measurement results are in [`KNOWLEDGE.md`](KNOWLEDGE.md) (in Chinese) §12.
