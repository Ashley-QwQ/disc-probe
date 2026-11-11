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

In the exact model path, no bands, alternate textures, CD spectrum, physical
hub appearance, specular flash, scratches, speckle, sensor noise or camera
tone curve are invented. The optional photo stage described below adds artistic
surface/camera effects after this path; it does not change the optical model. The
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

## Photo look (default on in the Preview UI)

`surface.mjs` adds a separate camera/surface approximation in the existing worker.
`model.mjs` and `textures.bin` are unchanged. The worker takes the exact path when
`pose.photoLook` is false or absent; the UI explicitly sends 1 by default. This
keeps existing programmatic callers and `verify.cjs` on the exact model.

The reflected light position is the plane intersection of the camera-to-mirrored
light ray, with the same tilt transform as the model. A clipped hotspot and
soft blue bloom follow it. Round 2 replaces uniform radial white streaks with
a tapered flame and an opposed thin spectral needle. The opposed needle is an explicit
approximation; round 3 replaces the flame with a fitted aperture/order hypothesis. Blurred environment lobes
move with the camera. The clear hub offsets a shared procedural backing, with
directional step-edge arcs, frosting and a thin outer rim.
A fixed seed makes dust, scratches and fingerprint ridges stable in disc space.
The final pipeline boosts chroma/contrast, clips highlights, adds a blue cast,
radial channel separation, a small unsharp halo, vignette and sensor grain.
This is an artistic prediction, never a physical-photo fidelity claim.

Controls in both languages: Photo look on/off; flash versus broad room lamp;
dust/scratches 0/45/100%; hand-coloured or dark-table backing. Existing five
pose/exposure sliders and light/camera handles remain. Reset restores all of
these defaults. Photo controls are disabled while viewing the pure model.

Both passes remain cancellable: 160 px while interacting, 500 px after 180 ms
idle. Surface processing yields every 16 rows and reuses two cached procedural
mark maps. Run `node discprobe/web/home/sim/rough-check.cjs` with the loopback
server above for UI-off pixel equality, default/control state, optical movement,
bilingual desktop/mobile checks, worker timings and canvas-only PNG exports.
`evidence/rough/checks.json` records the exact poses and measurements. The PNGs
are raw face-on worker maps; comparison boards apply the UI's cos(tilt) squash.
The CD-RW reference informs finish only: the DVD model does not predict CD.


## Round 2 evidence

`gratingWavelength` evaluates the 740 nm first-order radial grating relation.
The sampled +/-12 mm mirror neighborhoods at the three evidence poses remain
below 50 nm; a compact visible flame is therefore approximated explicitly.
Its radial axis and finite envelope follow the geometric mirror point. The
round-2 camera toe was removed in round 3; selective A5/environment darkening
preserves the exposed silver surface. Additive glare still clips.
See `codex-rough2-last.md` for the physical limits and visual assessment.

Run `rough2-check.cjs` with the existing loopback server, then
`python -B discprobe/web/home/sim/build-rough2-evidence.py` from the worktree
root. Three procedural block-pattern worker renders, timings, grating probes,
raw exports, reference comparison boards and a signature close-up are under
`evidence/rough2/`. Surrounding blanket pixels are evidence staging; the live
preview surrounding canvas stays black. No reference pixels enter the renderer.


## Round 3 hypothesis and evidence

`RADIAL_APERTURE` in `surface.mjs` exposes internal width/period parameters:
16 um effective radial aperture, 20 um long period, 10:1 outward-order blaze.
The suggested 40/40 um trial is preserved beside the fitted result. These are
appearance-fit hypotheses, not measurements or a demonstrated burn mechanism.
The stage integrates 400..700 nm in 25 nm steps, using the exact model's tilted
camera/light rays. A Gaussian-apodized central lobe has FWHM .886*lambda/w;
orders are centered at radial mismatch +/-lambda/period. Finite source width,
RGB response, gains, tangential softness and halo are approximate.

The worker passes the existing binary design to the photo stage for selective
A5 darkening. No global toe remains; silvery environment reflection stays bright.
Hub catches are broken, asymmetric and vary in width; the hole has a paired
bright/dark thickness cue. All controls and the exact off path are retained.

With the loopback server above, run `verify.cjs`, `rough-check.cjs`, and
`rough2-check.cjs` (set `ROUGH_EVIDENCE=rough3` to preserve old evidence).
Run `rough3-check.cjs` for wavelength/aperture scaling, mirror geometry,
blaze symmetry and rotated material selection, then
`python -B discprobe/web/home/sim/build-rough3-evidence.py` for local reference
composites and brightness statistics. See `codex-rough3-last.md` and
`evidence/rough3/brightness.json` for masks, measurements and limitations.
