# Burn a disc of a character you love

[中文](first-colour-disc.zh.md)

You have a picture of a character you love and want it on the data side of a DVD, in colour when you tilt the disc to the right angle. This page walks the whole way once: what to get ready, where each step is in the web app, roughly how long it takes, which pictures come out well, and what to check first when something looks wrong. Every step with screenshots is in [Make a colour DVD](colour.md).

## Get ready

- **A writer.** Our tested drive is the LG GH70N. Other drives may work; measure one first as the web app guides you. [Drives with hands-on reports](../README.en.md#drives-with-hands-on-reports)
- **At least 3 blank DVD-Rs from the same batch.** One becomes the measurement disc, one the check disc, one the picture. Colour has been burned and checked only on RITEK F1 discs (media code RITEKF1). Measure different batches separately, even when the media code matches. [Why calibrate](why-calibrate.md)
- **A phone.** Shoot with the 1× main camera and the flash on. The software needs the distance from that lens to the flash: the iPhone 17 Pro has a preset; for other phones, measure it and enter it as **Custom**. [Phone and flash](colour.md#set-up-the-phone-and-flash)
- **A printed placement sheet.** Print it at actual size (100%) to line up the disc and the phone.

## The whole way, a little over an hour

| Step | In the web app | About |
|---|---|---|
| 1. Calibrate the batch | **New work** in the lobby, choose the disc's batch, **Calibrate this batch**. Burn a measurement disc, then measure rotation and geometry; after saving, **Burn the check disc** and take 3 phone photos to correct the positions. Photograph it right after burning if you can, and write its number on the inner ring. To photograph it later, open the batch in the library, choose **Check disc burned already? Photograph it**, and select the burn that matches your disc | 14 min to burn, 6–8 min to measure, about 7 min for the check disc plus photos |
| 2. Make the picture | **Import picture**, select its layer, **Colour → Colour picture**, pick your phone and shooting height, **Fill**. Keep **Add direction arrow (12 o'clock)** | as long as you like |
| 3. Check the prediction | Open **Under the lamp**, then **Compare**: the original on the left, the model's prediction of the disc on the right | a few minutes |
| 4. Burn | **Next: preview**, check the batch under **Before burning**, keep **Burn the experimental textures instead** selected, **Next: make the file and burn**, confirm the blank and 8×, slide to burn | about 7 min at 8× |
| 5. Look and photograph | Disc data side up, its arrow on the sheet's arrow, flash on | a few minutes |

A batch is calibrated once. For the second and third pictures on the same batch, start at step 2.

## Pictures that come out well

The colours on a disc come from diffraction, not from a screen. From the discs burned so far:

- **A dark background with bright accents works best.** A deep background and a patch of vivid red, orange, pink or cyan on the character beats a picture that is bright all over.
- **Reds and oranges stand out most**, often brighter on the disc than in the prediction. **Blues and purples come out darker.**
- **Large white or grey areas look dull.** They tend to go grey and drift towards yellow-green. Let white clothes go warm, or make the background dark.
- **Keep what matters out of the hub and the hatched band.** The hub is clear plastic and takes nothing. The band hatched in **Under the lamp** cannot show colour from this shooting position.
- **Drawing in another program?** Export the design template first, draw on its disc and visible areas, then import the result.

The colours are right only near the designed position. Move the phone a few centimetres and they all change; rainbow bands sweep across. That is how a disc behaves.

## Looking at the finished disc

- **Photographing:** turn off bright lights or stand with the ceiling lamp behind you. Lay the disc flat on a dark surface, data side up, its 12 o'clock arrow on the sheet's arrow. Put the main lens where the sheet marks it, 22.3 cm above the table (or the height you designed for), and set the flash to **On**, not Auto. [Shooting details](colour.md#set-up-the-phone-and-flash)
- **By eye:** hold a small lamp beside your eye and tilt the disc slowly.

## When something looks wrong

- **The colours are off:** check four things first: the arrow lined up, the 1× main camera, the flash on, the height. Then that the disc lies flat. [Common problems](colour.md#common-problems)
- **Only rings, or a twisted picture:** most likely the batch was not measured well, or a different batch was used. Look at the sampled read-back in the burn report and at the measured range. [After-burn checklist](../discprobe/web/home/checkburn.js) · [Why calibrate](why-calibrate.md)
- **The burn or read-back failed:** the burn report says where. Read it before trying another speed the drive supports.
- **Stuck at the measurement:** the page suggests a reading speed, and can continue from the step that failed.

Curious how it works? See [How a disc becomes a picture](how-disc-images-work.md).
