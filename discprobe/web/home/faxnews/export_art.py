"""Copy the news fax's top-down renders (render_faxnews.py --mode fax) into the page: the desk picture as is, the
handset and its shadow cropped to what they cover (both themes share one box), and faxnews/fax.json in the page's
shape. Run:  python -I export_art.py <render out dir> <this folder>"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
meta = json.loads((src / "fax.json").read_text(encoding="utf-8"))
W, H = meta["canvas_size"]
THEMES = ("paper", "dark")


def crop_box(name, pad=4):
    boxes = []
    for t in THEMES:
        a = np.asarray(Image.open(src / f"{name}_{t}.png"))[..., 3] > 1
        ys, xs = np.where(a.any(1))[0], np.where(a.any(0))[0]
        boxes.append((xs[0], ys[0], xs[-1] + 1, ys[-1] + 1))
    return [max(0, int(min(b[0] for b in boxes)) - pad), max(0, int(min(b[1] for b in boxes)) - pad),
            min(W, int(max(b[2] for b in boxes)) + pad), min(H, int(max(b[3] for b in boxes)) + pad)]


for t in THEMES:
    Image.open(src / f"top_{t}.png").convert("RGB").save(dst / f"top_{t}.webp", "WEBP", quality=92, method=6)
boxes = {}
for name in ("handset", "handset_shadow"):
    boxes[name] = crop_box(name)
    for t in THEMES:
        Image.open(src / f"{name}_{t}.png").convert("RGBA").crop(boxes[name]).save(dst / f"{name}_{t}.webp", "WEBP", quality=92,
                                                                                   method=6, exact=True)
keys = {}
for k, v in meta["keys"].items():
    keys[k.replace("fax_key_", "")] = {"quad": v["quad"], "centre": v["centre"]}
out = {
    "canvas": [W, H], "px_per_mm": meta["px_per_mm"], "focus": meta["focus"], "body_rect": meta["body_rect"],
    "handset": {"box": boxes["handset"], "centre": meta["handset_centre"]},
    "handset_shadow": {"box": boxes["handset_shadow"], "offset_px": meta["shadow"]["offset_px"]},
    "screen_quad": meta["screen_quad"], "keys": keys, "slot": meta["slot"],
    "source": {"model": "art/desk/fax-news/fax_news.blend", "sha256": meta["source_sha256"], "renderer": "render_faxnews.py --mode fax",
               "camera": meta["camera"], "samples": meta["samples"], "supersampling": meta["supersampling"]},
}
(dst / "fax.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("exported", boxes)
