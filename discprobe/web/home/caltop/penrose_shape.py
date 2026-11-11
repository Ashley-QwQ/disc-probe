"""Penrose triangle desk object: the person's logo (props/penrose_logo.png) traced into three flat polygons, one per
grey tone (light / mid / dark), for render_caltop.py --anim to extrude into a low block. Seen straight down, the block's
top face is the logo; its shadow is that of a block a few mm tall (the eye reads the figure, the shadow says "low").

    python -I penrose_shape.py props/penrose_logo.png props/penrose.json [--width-mm 64]

Writes {"width_mm", "pieces": [{"tone": "light"|"mid"|"dark", "poly": [[x_mm, y_mm], ...]}]} with +y up (towards the
drive's rear) and the figure centred on its bounding box.
"""
import json
import sys

import cv2
import numpy as np
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
width_mm = float(sys.argv[sys.argv.index("--width-mm") + 1]) if "--width-mm" in sys.argv else 64.0
im = np.array(Image.open(src).convert("RGBA")).astype(np.int32)
inside = im[..., 3] > 128
g = im[..., :3].mean(axis=2)
tones = {"dark": inside & (g < 95), "mid": inside & (g >= 95) & (g < 155), "light": inside & (g >= 155)}
ys, xs = np.nonzero(inside)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
scale = width_mm / (x1 - x0)
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
pieces = []
for tone, m in tones.items():
    m = cv2.morphologyEx(m.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in cs:
        if cv2.contourArea(c) < 0.002 * inside.sum():
            continue
        p = cv2.approxPolyDP(c, 6.0, True)[:, 0, :]
        pieces.append({"tone": tone, "poly": [[round((x - cx) * scale, 3), round((cy - y) * scale, 3)] for x, y in p]})
        print(tone, len(p), "vertices, area %.0f px" % cv2.contourArea(c))
# the pieces share their edges: vertices of different pieces closer than 1.2 mm become one (their mean), so the
# tracing gaps close and the three faces meet on one line
pts = [(i, j) for i, p in enumerate(pieces) for j in range(len(p["poly"]))]
for i, j in pts:
    group = [(k, l) for k, l in pts if k != i and np.hypot(*np.subtract(pieces[k]["poly"][l], pieces[i]["poly"][j])) < 1.2]
    if group:
        allv = [pieces[i]["poly"][j]] + [pieces[k]["poly"][l] for k, l in group]
        m = [round(float(v), 3) for v in np.mean(allv, axis=0)]
        for k, l in [(i, j)] + group:
            pieces[k]["poly"][l] = m
out = {"width_mm": width_mm, "height_mm": round((y1 - y0) * scale, 3), "source": src.replace("\\", "/").split("/")[-1],
       "pieces": pieces}
with open(dst, "w") as fh:
    json.dump(out, fh, indent=1)
print("wrote", dst, len(pieces), "pieces")
