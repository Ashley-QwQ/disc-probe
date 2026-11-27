# Design editor extension

Mode: Operate. The user imports artwork, selects regions, assigns materials and continues to preview. The established visual system and all other routes remain in place.

## Direction contract

THESIS: Put the disc and its writable region at the centre of import and material assignment. Drawing remains a small supporting tool.

OWN-WORLD: Preserve the paper and ink themes, monochrome controls, 4/8 px corners and existing glass shadow tokens. Material fans and the disc carry predicted colour.

STORY: Import an external picture, organize layers, select a disc region, apply a material or pattern, save a portable work and continue to preview.

FIRST VIEWPORT: Existing three-column editor: layers and selection tools on the left, disc object and radius ruler in the middle, material fans and assignment controls on the right. Back stays top left and Next bottom right. Side columns scroll independently.

FORM: Extend the incumbent editor. No replacement visual world, new palette, scene imagery or external libraries. The supplied brief fixes the direction; there is no generated alternative seed.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Evidence: `evidence/editor/screenshots/` contains generated browser captures, not authored product imagery. The input SVG and PNG are synthetic test drawings made by `tools/editor_capture_plan.py`. No other shipping raster was created or replaced. Existing DESIGN.md remains authoritative.

## Round two refinement

The user's screenshot review supersedes the first-round control layout. Keep the same world and data operations. The left column is a compact list of layers and saved masks. Nine icon tools live at the canvas edge; the active tool's options sit in a reserved top dock, with status below the disc. Material fans are hue ordered using the existing realistic preview's spectral response and saturation/encoding; non-colouring entries are collapsed. The right content scrolls independently above its pinned fill action. Shortcuts appear only on tool hover/focus, with Space temporarily selecting Hand. Evidence is the 60-image matrix in `evidence/editor/round2/`, including all nine active tools and the three-layer/two-mask list.

## Material identity and light

The default Design canvas now uses neutral fine marks to identify assignments. Predicted material colour stays in the panel. Under the lamp is a separate per-pixel first-order model: the local along-track pose projection sets wavelength, with dark sectors outside the visible order and existing preview tone/saturation. Its pose maps are cached independently of assignments. This supersedes round two's flat sampled-colour canvas fills. Eight paired theme/language captures and bounded model evidence live in `evidence/editor/lamp/`; no authored product imagery was added. The missing multi-byte spectra and photo-validation boundaries remain explicit.

## Round four: the core is the optical authority

This supersedes the first-order browser model above. Under the lamp now transports PNGs from the same `discprobe.simulate.render` as the release CLI: 200 px quick sampling first, then a fine-sampled image at the displayed disc resolution. A quiet progress line stays outside the disc. Pose changes wait 220 ms, stale responses are discarded, and both client and core caches are bounded. Unpatterned groove rainbow, linear-light averaging and phone saturation come from the core. No new browser optical model or coloured placeholder remains; Design keeps its neutral identity marks. Swatch display colours are produced by that core too. Evidence: twelve captures, source hashes and labelled release comparisons in `evidence/editor/round4/`. Bundled figures artwork and supplied release images are evidence sources, with no new shipping raster or changes to other surfaces.
