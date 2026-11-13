# Showcase

Phone photos of discs burned with timing-only geometry: the pre-registered re-measurement
`evidence/geo/remeasure_ref262336_summary.json`, with no photo calibration, no scan correction
and no test burn. Each design was burned once (HL-DT-ST GH70N, Ritek F1 DVD-R, Windows Disc
Image Burner, default speed). Photos are cropped to the disc and downsized; background details
are blurred.

| File | Disc |
|---|---|
| `qingming_full.jpg`, `qingming_title.jpg`, `qingming_inner_ring.jpg` | 清明上河图 (Along the River During the Qingming Festival) on two conformal rings, A5 ink on 92 silk |
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
