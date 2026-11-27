# The contract between the photo core (card photo-core.md) and the page wiring (card photo-wire.md)

Both jobs build against exactly this; neither changes it without saying so in its report.

## HTTP (discprobe/webui.py, same server and same LAN-session check as the other /api routes)

- `GET  /api/phone-link?run=<run_id>` -> `{"url": "http://<lan-ip>:<port>/phone/<token>", "qr_svg": "<svg ...>"}`
  `url` is null (and `qr_svg` null) when the server is not reachable from the LAN; the page then shows the honest line.
- `POST /api/photos?run=<run_id>` body = the image bytes (Content-Type image/jpeg|png|heic|webp), header
  `X-Filename` -> `{"id": "...", "name": "...", "url": "/api/photos/<run_id>/<id>", "time": <unix>}`.
  Photos are stored under the calibration run's own results folder: `<results>/<run>/photos/<id>.<ext>`.
- `GET  /api/photos?run=<run_id>` -> `{"photos": [{id, name, url, time}, ...]}` (oldest first)
- `GET  /api/photos/<run_id>/<id>` -> the image bytes.
- `GET  /phone/<token>` -> the phone page (one small HTML page, no build step): viewfinder hint ("把整张盘放进圈里"), a
  shutter (an `<input type=file accept=image/* capture=environment>`), a gallery pick, the sent thumbnails. It uploads to
  `POST /api/photos?run=...` with the token as the auth (the token is single-run, unguessable, expires with the run).
- The computer page learns of new photos by polling `GET /api/photos` every 2 s while the photo page is open (or SSE if
  the server already has a suitable channel; say which).

## Job (the existing /api/run job mechanism)

- action `"photo"`, args `{ "run": "<run_id>", "media": "cd"|"dvd", "photos": ["<id>", ...], "rings_mm": [r, ...] | null }`
- events: the usual `log` / `progress` (stage `"reading photo i/n"`) / `error`
- result: `{ "verdict": "ok"|"unsure"|"rejected",
             "per_photo": [{"id", "verdict", "reason"}],   // reason in plain words, e.g. "反光强" / "strong glare"
             "rings_mm": [r, ...] | null,                 // where the reader put the target rings (for the overlay)
             "offset_mm": number | null,                  // mean alignment offset, for "平均偏差"
             "L_frames": number | null,                   // CD only: the along-track constant, when read
             "confidence": number | null, "path": "<results folder>" }`
  When the reader cannot tell, verdict is "unsure" or "rejected" with reasons: it says it does not know; it never guesses.

## Page options (photocal.js photoPage opts, already written)

`phoneUrl` <- `/api/phone-link`.url, `phoneQrSvg` <- .qr_svg, `photos` <- `/api/photos`,
`autoAlign(photo, rings)` -> runs job "photo" and maps the result to `{ rings, offsetMm }`.
