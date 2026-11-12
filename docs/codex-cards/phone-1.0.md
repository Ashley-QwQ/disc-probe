# Task card: phone direct-upload calibration, ready for 1.0

Worktree: `D:/disc-probe/.claude/worktrees/web-walkthrough`.
- Do NOT commit, push, stash, reset or switch branches.
- No drives. Do not start or stop any server outside tests. A user's server runs on port 8772: never touch it.
- Do NOT edit `discprobe/scsi.py`, `discprobe/pcal.py`, `discprobe/geo.py`, `pastworks*`, `kit/`, `lobby*`, `newplan*`, `caltop/`.
  Another job is adding a blur check to the photo reader on another branch. Keep `photo.py`'s `REASONS` table as it is
  (you may read it) so that branch merges cleanly.

You MAY edit:
- `discprobe/webui.py`;
- `discprobe/photo.py` (except the REASONS entries);
- `discprobe/__main__.py` (the `webui` parser only);
- `discprobe/web/phone/index.html`;
- `discprobe/web/home/photocal.js` and `photocal.css`;
- `discprobe/web/home/calibrate.js` (the photo step only: functions around `pollPhotos`, `readPhoto`/`realJob('photo'...)`,
  `showPhotoResult`, `photoStamp`);
- `discprobe/web/home/guidance.mjs` (words);
- tests.

## Goal (the person's words)

For 1.0, phone calibration is a must, not an experiment. The person takes photos with the phone. The page reads them
and fits the along-track constant itself, and nobody drags curves by hand.

## What exists (read first)

- The routes in `webui.py`: `/api/phone-link`, `/api/photos` GET/POST, `/phone/<token>`, `/api/phone-devices`.
- `PhotoStore` in `photo.py`.
- `photo.analyze()`: it runs pcal v1 per photo, then `pcal.combine` needs **at least two photos with a clear peak**.
- The phone page `web/phone/index.html` only sends photos and shows a count.
- `photocal.js`: QR, devices, the photo strip with per-photo `reason`, the manual ring editor.
- `calibrate.js` photo step: it calls `realJob('photo', {run, media, photos:[id], rings_mm})` with ONE photo. That can
  never reach `ok`, because combine needs two or more. This is a bug to fix.
- Saving L into the preset with provenance: commit cf33585, `photo.photo_shift`.

## Do

1. **LAN on by default.**
   - `python -m discprobe webui` listens on the LAN with the session token, as `--lan` does today.
   - Add `--local-only` for 127.0.0.1 and no LAN. Keep `--lan` accepted as a no-op, and say so in its help.
   - The printed URL is still `http://127.0.0.1:<port>/home/?token=...`.
   - The security model is unchanged: the session token for the computer, a per-run photo token for phones, and phone
     tokens never reach the main API. Add a test that proves it.
2. **The address.**
   - Add `photo.lan_ips()`: all private, non-loopback, non-link-local IPv4 addresses, in a stable order. Keep `lan_ip()` as
     the first of them.
   - `/api/phone-link?run=&address=` builds the link for a chosen address. Only addresses from `lan_ips()` are accepted.
     The response lists `addresses`.
   - photocal shows a small chooser only when there is more than one address. The chosen one is remembered for the
     session.
3. **When the phone can't open the link.**
   - If no device has opened the link (the `/api/phone-devices` list stays empty) 25 s after the QR is shown, the phone
     block shows a quiet fold: "手机打不开链接？ / Phone can't open the link?". Inside:
     - same Wi-Fi as this computer (not a guest network);
     - Windows may have blocked it: allow Python on private networks in Windows Security → Firewall → Allow an app;
     - try the other address (if more than one).
   - Words zh first with en. No claims we can't check: we cannot test the firewall from this computer, so do not say
     that it is the firewall.
4. **The phone page.**
   - **Before sending:** re-encode each photo to JPEG in the browser (`createImageBitmap(file, {imageOrientation:
     'from-image'})`, canvas, quality .95, long side capped at 4096 px, never upscaled). This handles iPhone HEIC. If the
     decode fails, send the original file.
   - **After sending:** poll the run's photos with its photo token every 2 s (the listing is already token-scoped). Show
     each photo the phone sent as a small thumbnail with its state:
     - 读取中 / Reading;
     - 可以用 / Usable;
     - 重拍：<reason> / Retake: <reason>.
     Include a "重拍 / Retake" button that opens the camera again.
   - **Overall line:** "已收到 N 张。再拍 M 张不同角度的。" until the read is ok, then "够了，回到电脑上看结果。 / That's
     enough. Look at the computer."
   - **The listing:** extend it so each photo row carries the last read's `verdict`, `status` (the pcal code) and `reason`
     for that photo, from `<run>/photo.json`. No new route.
5. **Reason words.**
   - `photo.analyze` puts the pcal `status` code in each `per_photo` item, next to the English `reason`.
   - One table on the page side (guidance.mjs) maps codes to zh+en plain words, for both the phone and the computer.
     Unknown codes show the server's English `reason` as given. This keeps the coming blur check's code (e.g.
     `out_of_focus`) as one line to add.
   - Retake advice is concrete: whole disc in frame; turn the disc; move the light; tap to focus.
6. **Read automatically, all photos together.**
   - On the computer, when photos arrive the page runs the reader over ALL usable photos of the run: debounced 1.5 s,
     one job at a time, re-run when new photos arrive. No button, no ring dragging.
   - Fix the one-photo call. Results and the stamp show as today (ok/unsure/rejected). Per-photo reasons land in the
     strip and on the phone.
   - The manual ring editor stays reachable but folded under "手动调整 / Adjust by hand", closed by default. Nothing on the
     happy path asks for it.
7. **Burn path record.**
   - `photo.analyze` takes `burner/burn_path/burn_mode`, but the `photo` web action never passes them, so photo.json
     records null.
   - Pass what the calibration flow knows (the burner drive identity and the burn mode/path the measurement disc was
     burned with). Find where the page/core keep them and wire them through the action's allowed args.
   - If the flow truly can't know a field, leave it null and report which.
   - Check against `photo_shift`'s rules that a normal flow's ok result can be written into the preset.

8. **Browsers and screen shapes (the person asked for this explicitly).**
   - The phone page must work on iOS/iPadOS Safari and on Android browsers (Chrome, plus the common built-in ones such as
     Samsung Internet and the Chinese vendor browsers, which are Chromium-based).
   - Only use features they all have, or feature-detect with a fallback:
     - `createImageBitmap` with `imageOrientation` (older Safari ignores the option: fall back to `<img>` decode plus
       canvas; never rotate twice);
     - `canvas.toBlob` (fallback `toDataURL`);
     - canvas size limits (iOS caps canvas area at about 16.7 MP: the 4096 cap must keep below it);
     - no `structuredClone`, no top-level await, no CSS `:has()` for layout, no `dvh` without a `vh` fallback.
   - `<input type=file accept="image/*" capture="environment">` must still offer the camera on both platforms. Keep a
     second "从相册选 / From photos" input without `capture`.
   - Layout works on a phone held upright (360–430 px wide), a phone held sideways, and a tablet in both orientations
     (768–1366 px).
     - Safe-area insets via `env(safe-area-inset-*)`.
     - Touch targets at least 44 px.
     - Text that can be zoomed (no `user-scalable=no`).
     - No horizontal scroll at any of those sizes.
   - The computer-side photocal block (QR, chooser, fold) must also lay out on a tablet if someone uses the page there.
   - Test: a browser test that loads the phone page at 375x812, 812x375, 820x1180 and 1180x820 and checks no horizontal
     scroll and the 44 px targets. Use the repo's existing headless setup.
   - Report anything that can only be confirmed on a real device.

## Tests

Extend:
- `tests/test_photo.py`: lan_ips, address validation, `--local-only`, listing with read results, status codes in
  per_photo, burn path args;
- `tests/test_photo_wire*.mjs`: auto read with all photos, debounce, folded manual editor, address chooser, the fold
  after 25 s;
- a node test for the phone page logic (JPEG re-encode path and fallback, the per-photo states, the overall line);
- the reason table.

Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`. All must pass.

## Done means

Tests pass. Report:
- what changed per item;
- which burn-path fields the flow provides;
- anything you could not verify without a real phone.
