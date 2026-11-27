# Task-card verification, 2026-11-13

Historical report; machine-specific paths below have been replaced with relative LABS/ placeholders. These are records of that earlier check, not instructions to launch a server during packaging verification.

Only `disclab/web.py` and files in `disclab/tests/` were edited/added. No protected-module fixes, packaging changes, commits, pushes, real drive access or physical burns were performed. Test burns used the lab recorder and 4096-sector (8 MiB) ISOs.

## Commands

From `the folder containing disclab/`:

```powershell
python -m disclab web --lab LABS/codex-lab --port 8853 --media dvd
python -m disclab upload --url http://127.0.0.1:8853 --run geo-X-20261113-143516 --photos LABS/lab2/photos/try/IMG_00300.jpg LABS/lab2/photos/try/IMG_00301.jpg
python -m pytest disclab/tests -q
```

The first two commands are the task card's requested commands. They cannot currently complete together under its hard rules, for the reasons below. The temporary copies have been removed after verification, so recreate a copy before rerunning.

## Required external-copy check

Copied `lab2` to `LABS/codex-lab`, excluding `iso` directories and retaining burn records with their shared ISO references. Launched the exact requested web command, with repository cwd and `lab_env`.

```text
http://127.0.0.1:8853/home/
discprobe.webui.APIError: path must stay inside the workspace
LAUNCHER_EXIT 1
```

`discprobe/webui.py:524-526` makes the backend root the child cwd, then validates `--out` with `local_path`; `discprobe/webui.py:85-87` rejects the absolute results directory outside that root. No supported workspace-root option exists in this launcher command. Changing cwd or that guard would contradict the card.

## Supplemental check with a copy inside the worktree

Used a second temporary copy at `disclab/tests/codex-manual-lab` containing box/answers/state, results and media maps. Queried the real server using standard-library urllib on port 8853:

```text
DRIVES [{"id": "X:", "name": "X:", "disc": null}]
PAGE 200 text/html
RUN geo-X-20261113-143516
PHONE_LINK {"url": null, "qr_svg": null, "addresses": [], "address": null}
UPLOAD_EXIT 1
server returned no phone link (--local-only disables phone tokens)
PHOTO_NAMES []
```

`discprobe/webui.py:1179-1186` deliberately returns no phone link when the local-only server has no main session token. Consequently, no phone capability can be obtained over this API for the mandated launcher. The uploader reports this and exits without sending photos. It does not substitute computer-authenticated uploads for phone-authenticated ones. The two-photo live upload/listing acceptance check remains blocked.

Unit tests verify the exact phone protocol against captured urllib requests: GET phone link, GET phone page, POST raw file bytes with `X-Photo-Token`, image `Content-Type`, percent-encoded `X-Filename`, and final computer-authenticated GET listing using a separate cookie jar and no photo token. They also verify failed upload replies and a final listing on HTTP upload errors. Browser canvas JPEG conversion is not implemented; this standard-library helper sends supplied image files directly, matching the page's original-file fallback.

The Windows console check sent Ctrl+Break and stopped both processes (Windows control-event exit status `3221225786`). Shutdown forwarding is additionally covered by a unit test. Ctrl+C could not be confirmed in this automation console; its signal was ignored, and those attempts were stopped with targeted process-tree termination. No task-started Python process or listener on 8853 remained at final verification.

## Observations in unchanged disclab modules

- `disclab/photos.py:240`: rendering the fixed-seed test disc with `Pose(width=640, height=480, dist_mm=600)` emits `RuntimeWarning: overflow encountered in exp`. It still returns a varied `(480, 640, 3)` uint8 image; the warning is not filtered or fixed.
- `disclab/physics.py:36` reads `burn['write_offset_bits']`, whereas `disclab/drive.py:390,399` stores offsets in `burn['sessions'][i]['write_offset_bits']`. For the copied LAB-A 1-02 burn, the first session offset is `9.605935108292183`, but `Disc(truth, burn).w_bits` is `0.0`. Nonzero session offsets are therefore ignored by the physics consumer. No fix was needed for these tests, and none was made.

Both temporary lab copies were deleted. Original `lab2` JSON hashes and all tracked repository files were checked against the pre-work snapshot. No scratch artifacts are retained.

## Final acceptance output and scope

```text
$ python -m pytest disclab/tests -q
20 passed, 1 warning in 27.31s

$ git status --short
?? DISCLAB_REPORT.md
?? disclab/
```

The entire `disclab/` tree was already untracked at task start. SHA-256 comparison against the initial snapshot confirms the only existing file changed by this task is `disclab/web.py`; the only additions under that tree are `disclab/tests/test_disclab.py` and this report. All tracked file hashes and original lab2 JSON hashes match. The unrelated untracked `DISCLAB_REPORT.md` appeared during this work and was left untouched.
