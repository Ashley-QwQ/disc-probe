# Experimental tools — not part of any calibration path

Everything in this directory is offline analysis code kept for the record. `discprobe` itself
never imports it, `python -m discprobe selftest` never calls it, and no preset a user installs
ever comes out of it.

The rule this directory exists to enforce: **a Blu-ray geometry measurement is drive I/O only.**
`geo --media bd` times the spindle and fits `T^2 = b + a*n`; `disexport` turns that fit into a
DiscImageStudio preset. Asking a terminal user to photograph a disc, pick its centre and supply a
scale is not a deliverable, so nothing here may grow into the product.

| file | what it does | status |
| --- | --- | --- |
| `bd_gen2.py` | gen-2 test pattern (two unequal wedges) plus a polar matcher that reads a photograph of it back | frozen experiment (see `docs/research/BD_SPOKE_SHEAR_REPORT.md` §6) |

`bd_gen2.py` is the only file here, and it stays as the record of the §4.3 measurement path: the
handedness bug it exposed (a template drawn with `y = +r*sin(t)` against a sampler that reads
`y = cy - r*sin(t)`) and the six-angle injection sweep that came out of fixing it. Reproducing it
needs a synthetic image, not a drive:

```
python tools/experimental/bd_gen2.py --selftest          # six injected twists, ~45 s
python tools/experimental/bd_gen2.py --design iso/gen2-design.png
```

Read its numbers as a check on the matcher's maths, never as a measurement of a disc.
