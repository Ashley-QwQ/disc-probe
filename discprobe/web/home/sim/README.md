# Simulated DVD appearance

`model.mjs` ports `discprobe/simulate.py` for dark A5 / light B9. Coordinates
are millimetres, x right and y up; the default camera is (0, 70, 330), flash
(-43.66, 89.79, 330). Positive disc rotation is counterclockwise. Exposure is
in stops relative to Python's gain of 4. The default is 0 EV.

`textures.bin` is 18,792 bytes: little-endian float64 RGB triples, 261 entries
each for decoded A5, decoded B9, then groove. Source:

- `discprobe/simulate_lut.npz`
- SHA256 `fe930edca10e4ea1fc9e3dd19d5ee1201a51336351a66c33a5ae345bc530937c`

Extraction, using the installed numpy, from the worktree root:

```python
with np.load('discprobe/simulate_lut.npz') as z:
    data = np.concatenate([
        ((z['single'][[0xa5, 0xb9]] / 255.) ** 2 - .02).ravel(),
        z['groove'].astype(float).ravel(),
    ]).astype('<f8')
    data.tofile('discprobe/web/home/sim/textures.bin')
```

The coarse pass is 160 square, with one sample per output pixel. After 180 ms
without input, the refined pass is 500 square, averaging a 2000-square grid in
linear light, then desaturating, clipping and encoding sRGB. Worker jobs yield
to new messages every eight output rows; stale jobs discard their output.
Only the latest pose is submitted once per animation frame. Worker lifetime
ends when leaving the simulated view or preview page.

The design callback is requested at 50 px/mm. Its canvas is transferred as an
ImageBitmap; worker readback classifies opaque pixels below luminance 128 as
dark, all other pixels as light. This is a binary input contract, not another
tone or dither pass. Actual callback resolution is honored. The current
`design.js` projection caps requests at 20 px/mm; this surface cannot recover
design cells already lost by that callback. Its synchronous composition also
cannot be moved into a worker without changing that upstream interface. First
entry may therefore block during composition; interactive optical rendering
does not call the callback again.

Tilt applies the inverse x rotation from `art/sim_view.py` to camera and flash.
The presentation compresses the map by cos(tilt); it is an orthographic
approximation, without perspective or occlusion. Rotation, light movement,
camera movement and exposure affect the optical calculation, not a colored
overlay. Sun and phone handles support dragging and arrow keys, with bounded
positions. Reset restores all pose and exposure values.

No bands, alternate textures, CD spectrum, physical hub appearance, specular
flash, scratches, speckle, sensor noise or camera tone curve are invented. The
room term and groove approximation are those of Python. The design page's
0.08 peak-width envelope is for its effect overlays; adding it here would
broaden the source lookup table again and break the Python comparison.

## Offline verification

Use an unused loopback port, and stop the server afterward:

```powershell
python -B -m http.server 18746 --bind 127.0.0.1 --directory discprobe/web
node discprobe/web/home/sim/verify.cjs
```

The script uses an already installed Playwright and headless Edge. Override
`PLAYWRIGHT_PATH` if needed. It never installs packages or accesses a drive.
Browser requests are restricted to 127.0.0.1. It generates a boolean 6000-square
test design (two halves plus 0.06 mm stripes), runs the requested Python
`simulate --design-npy` command at three poses, exports browser canvas pixels,
checks the complete bitmap-to-worker path at the default pose, exercises the
page, and records timings, layouts and a deliberate local table-load failure.
The large temporary NPY is removed after success. PNGs are rendered canvas
artifacts, not desktop or browser-window screen captures.

See `evidence/comparison.json` and `evidence/browser-check.json` for bounded
numerical results. The compared 500 px fixtures match exactly; this does not
prove equality for every design/pose or fidelity to a physical phone photo.
