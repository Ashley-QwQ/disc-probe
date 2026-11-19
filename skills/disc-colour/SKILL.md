---
name: disc-colour
description: Use disc-probe to turn a photo or illustration into a colour DVD. Use when someone wants to preview a picture on a disc, make a colour DVD ISO, or optionally record that ISO after approving it.
---

# Make a colour DVD

Speak to the user in their language. Use the local CLI and keep their image and any derived files local. Leave system settings alone and access only the drive the user selected. Leave web pages to the user and avoid browser or computer-control tools. The user handles the tray and swaps discs.

## What to expect

The colour workflow is DVD-only. Illustrations, flat fills and well-defined colour blocks work best. Physical colour has only been verified on RITEK F1 DVD-R with a GH70N, and the result is darker and less saturated than the prediction. The colours depend on a fixed phone and flash position. New work includes a direction arrow at 12 o'clock by default.

## Check the geometry

From the project folder that contains the relevant `results/`, run:

```sh
python -m discprobe guide --media dvd
python -m discprobe results
python -m discprobe results geo
```

Use the drive identity, media identification and run notes to establish that a successful geometry measurement came from this drive and this batch of DVD-Rs. The same media ID can occur in more than one batch. Ask about the batch only if the local records cannot establish it. Use the matching run's explicit folder or `summary.json` for `--geo`. If the drive or batch is different or uncertain, measure again. Check the measured intervals and any quality or read-speed warnings before relying on a run.

For a new measurement, follow the DVD steps in the [manual](../../docs/MANUAL.en.md) and check the installed CLI's `--help`. In the examples, replace `X:` with the selected drive identifier (such as `E:` on Windows or `/dev/sr0` on Linux). Inspect a blank DVD-R from the target batch and choose a random ISO length within its writable capacity. This example uses the usual full DVD length.

```sh
python -m discprobe info --drive X:
python -m discprobe random --output random.iso --sectors 2295104
```

Get explicit permission to burn this calibration ISO onto that blank, then use:

```sh
python -m discprobe burn --drive X: --iso random.iso --yes-write
```

Measure the burned disc in the same drive. Choose readable ranges that cover the intended artwork, following the guide and manual. Here the recorded length is 2,295,104 sectors and the example uses an aligned end inside that length.

```sh
python -m discprobe geo --drive X: --ranges 0-2295088
python -m discprobe results geo
```

If the guide calls for checking the read speed or burning a grid to validate the measurement, follow the manual and get separate permission for any additional burn. If the artwork extends outside the measured intervals, remeasure this same calibration disc with wider readable ranges or agree on a smaller layout and preview it again.

## Make and review the prediction

Ask only for details you cannot get from the request or local context.

- The image path.
- The phone model. Look up the CLI ID under `phones` in [pose-swatches.json](../../discprobe/web/home/design/pose-swatches.json). For an unlisted model, use `--phone custom` and `--flash-mm` with the measured distance from the main lens centre to the flash centre (10–60 mm).
- The height from the table to the lens in centimetres. The alignment sheet places the main camera at about 22 cm (the preset is 22.3 cm).
- Use `--fit disc` to fill the available annulus, which can crop the source, or `--fit ring` to place the whole picture above the hub.

```sh
python -m discprobe colour-design "artwork.png" --phone iphone17pro --height 22.3 --fit disc -o work.json --preview preview.png
```

For example, an unlisted phone with a measured 48 mm flash-to-lens distance and artwork above the hub uses:

```sh
python -m discprobe colour-design "artwork.png" --phone custom --flash-mm 48 --height 22.3 --fit ring -o ring-work.json --preview ring-preview.png
```

The command picks textures for the chosen camera position using the bundled colour data. Show the generated PNG to the user and say, "This is a model prediction. The physical disc will be darker." Wait for the user's approval of that preview before composing or generating the colour ISO. If the design or camera position changes, show a fresh prediction and get approval again.

## Build the approved ISO

Here `work.json` is the approved colour work. Replace the example geometry folder with the verified matching result. Run both commands in the same directory. The Python one-liner works in PowerShell and POSIX shells. It passes each texture from the generated file as a separate argument in its original order.

```sh
python -m discprobe compose work.json --out design.npy
python -c "import json, subprocess, sys; from pathlib import Path; textures = json.loads(Path('design.textures.json').read_text(encoding='utf-8'))['textures']; subprocess.run([sys.executable, '-m', 'discprobe', 'image', '--geo', sys.argv[1], '--design-npy', 'design.npy', '--textures', *textures, '--r-max', '58', '--output', 'colour.iso'], check=True)" "results/geo-X-YYYYMMDD-HHMMSS"
```

`image --design` expects a project saved by `edit`. A colour work from `colour-design` goes through `compose`, then `image --design-npy` with the ordered `--textures` list. The 58 mm radius keeps the full artwork annulus in scope, subject to the disc capacity and measured coverage.

Check that `colour.iso.verification.json` exists with status `passed` and matches the ISO's byte size and modification time. Explain that disc-probe wrote this record after sampling the generated ISO against the design. It verifies image data before burning. If it is missing, stale or failed, investigate and regenerate the ISO. Never write, edit or fabricate the record.

## Burn only with explicit approval

Preview approval covers making the ISO. Burning is irreversible and needs separate, explicit consent for the specific ISO, drive and blank DVD-R. Ask the user to insert a fresh blank DVD-R from the measured batch. Inspect the selected drive again and confirm that its disc status is empty, the next writable address is zero and its writable capacity fits the ISO. If any of these checks is uncertain, stop before burning.

```sh
python -m discprobe info --drive X:
```

Tell the user that the default DVD speed is the supported speed closest to 8×. Run this only after they confirm the burn:

```sh
python -m discprobe burn --drive X: --iso colour.iso --yes-write
```

Report the automatic sampled read-back counts for matching, differing, unreadable and untested blocks. If the read-back is incomplete or reports a difference, tell the user before suggesting a retry. Leave the disc in the drive for the user to handle.

## View the result

Place the disc data-side up on the printed alignment sheet and line up the disc's 12 o'clock arrow with the sheet. The repository's [alignment-sheet generator](../../tools/make_rulers.py) includes a placement page. Use the phone's main camera at 1× with the flash on and follow the sheet's phone orientation. Turn on the camera grid and line up both horizontal and both vertical lines with the sheet's guides at the chosen height. Keep your back to room lights to reduce reflections. For viewing by eye, find a darker spot and look at the disc with your back to the light.

## Troubleshoot

Search the experimental offline troubleshooter with the user's actual error or question. If you have a relevant run folder, save a sanitized diagnostic with `diagnose`. Replace the example folder with that run.

```sh
python -m discprobe troubleshoot "disc read-back failed after burning"
python -m discprobe diagnose "results/geo-X-YYYYMMDD-HHMMSS"
```
