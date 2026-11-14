# Showcase

Phone photos of discs burned with timing-only geometry: the pre-registered re-measurement
`evidence/geo/remeasure_ref262336_summary.json`, with no photo calibration, no scan correction
and no test burn. Each design was burned once (HL-DT-ST GH70N, Ritek F1 DVD-R, Windows Disc
Image Burner, default speed). Photos are cropped to the disc and downsized; background details
are blurred.

| File | Disc |
|---|---|
| `qingming_full.jpg`, `qingming_title.jpg`, `qingming_inner_ring.jpg` | 清明上河图 (Along the River During the Qingming Festival) on two conformal rings, A5 ink on 92 silk |
| `qingming5um_wide.jpg`, `qingming5um_figures.jpg`, `qingming5um_street.jpg`, `qingming5um_trees.jpg`, `qingming5um_houses.jpg`, `qingming5um_roof.jpg` | A second Qingming disc (`qmsht5.iso`), drawn with cells of about 4 to 6 µm. Phone photos through a reversed SLR lens; resized to 2000 px, metadata stripped. Magnification differs per shot: the lens field is about 5 to 23 mm across (about 3.8 to 17 µm per pixel of these files) |
| `qingming5um_overview.jpg`, `qingming5um_<n>_<name>_pair.jpg`, `qingming5um_<n>_<name>_scale.jpg` | In the web UI's paper style: where each close-up was taken, on a render of `qmsht5.iso` itself (regenerated from its recipe, SHA-256 identical to the burned image), next to a 550 ml bottle at the same scale (Blender toon render, lying on its side with 95 % water, the wordmark wrapped round its label, its own 3D-cast shadow; source in `docs/goals/showcase/bottle/`); each pair is the locator disc and the close-up printed on paper, joined by copper rings and a dashed line. `_scale` is the close-up alone with an inverted-colour scale bar. Position and scale come from matching each photo to the design (SIFT, similarity transform), checked by overlaying the design on every photo |
| `banner_light.png`, `banner_dark.png` | README banner in the web UI's paper and ink themes: the wordmark and the Qingming disc rendered from its ISO |
| `dense_motifs.jpg` | Dense tiling of small motifs with an outer resolution band |
| `grid_lines_zoom.jpg` | Part of a 600 dpi flatbed scan of the timing-only grid disc (`iso/grid3.iso`), high-pass filtered, about 38 mm across. A scan, not a phone photo |
| `palette_target.jpg` | Self-locating texture palette target (`python -m discprobe tiles`) |
| `rosettes_a.jpg`, `rosettes_b.jpg`, `rosettes_c.jpg`, `rosettes_closeup.jpg` | Four-colour rosettes (`tools/compose_rosettes.py`): petals in `A5`, `92`, `66` and 64T `ED00`, centres in 48T, background an aperiodic 8T mix. Phone flash, three viewpoints; the petal colours come from along-track diffraction and change with the angle |
| `ltva1_microscope_1px.jpg`, `ltva1_microscope_2px.jpg`, `ltva1_microscope_3px.jpg` | LTVA1's resolution test ([DiscImageStudio #108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108#discussioncomment-19463898)): a 23,200 px (5 µm per pixel) pattern on a Ritek DVD+R in an LG GU70N, built with a one-off patch, under a microscope (10× objective, 16× eyepiece, 2× Barlow). The digit is the pixel size; the "2" is upside down and mirrored. Downsized; used at LTVA1's request |
| `pugod124_cd.jpg` | Memorex CD-R by pugod124 ([disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2)), `geo` then fine calibration in DiscImageStudio; used with permission |
| `lut_target_design.png`, `lut_target.jpg` | Colour-table target (`iso/lut2.iso`): 75 self-locating tiles, each with an ID and 18 texture swatches. The design render uses one false colour per texture; the photo is the burned disc under a small light, background masked |
| `roses_source.jpg`, `roses_7161.jpg`, `roses_7185.jpg`, `roses_design.png`, `roses_layout.png` | Rose picture with data on one RITEKF1 DVD-R. `roses_source.jpg` is the original, made with GPT Image. The two photos were taken from viewpoints found by hand under an iPad torch, with the background masked. The colour varies with the viewpoint, and the data (1.38 GB) read back without an error on a GH70N. `roses_design.png` is the design and `roses_layout.png` shows where the data is |

The painting is in the public domain; the scan it was made from and the design files are not
published here.
