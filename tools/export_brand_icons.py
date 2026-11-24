"""Deterministic icon export using local Chromium SVG/canvas and Pillow PNG encoding.

No downloads. Repeated runs with the same SVGs, browser and Pillow yield identical
bytes. 16/24 px use icon-small; 32 px and above use icon. Night/ink is default.
Temporary browser files stay on D: unless --temp-dir explicitly overrides it.
"""
from __future__ import annotations

import argparse
import base64
from html import unescape
import io
import json
from pathlib import Path
import re
import struct
import tempfile

from PIL import Image

if __package__:
    from .browser import run_browser
else:
    from browser import run_browser

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "discprobe/web/brand"
PRODUCTS = ("probe", "lab", "neo")
SIZES = (16, 24, 32, 48, 64, 128, 180, 256, 512)


def png(data):
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    out = io.BytesIO()
    image.save(out, format="PNG", compress_level=9, optimize=False)
    return out.getvalue()


def ico(frames):
    """PNG-backed Windows Vista+ ICO, preserving each exact separately drawn size."""
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, payload = [], []
    for size, data in frames:
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        payload.append(data)
        offset += len(data)
    return header + b"".join(entries + payload)


def export(edge=None, temp_dir=Path("D:/dp-dev/tmp/brand/export")):
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_dir) as tmp:
        tmp = Path(tmp)
        sources = {p: {kind: "data:image/svg+xml;base64," + base64.b64encode(
            (BRAND / f"disc-{p}-{kind}-ink.svg").read_bytes()).decode("ascii")
            for kind in ("icon", "icon-small")} for p in PRODUCTS}
        page = tmp / "render.html"
        page.write_text('''<!doctype html><meta charset="utf-8"><pre id="out">PENDING</pre>
<script>
(async () => { try {
const sources = SOURCES, sizes = SIZES, result = {};
for (const [product, icons] of Object.entries(sources)) {
  result[product] = {};
  for (const size of sizes) {
    const image = new Image(); image.src = icons[size < 32 ? 'icon-small' : 'icon'];
    await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = size;
    canvas.getContext('2d').drawImage(image, 0, 0, size, size);
    result[product][size] = canvas.toDataURL('image/png').split(',')[1];
  }
}
document.getElementById('out').textContent = JSON.stringify(result);
} catch(e) { document.getElementById('out').textContent = 'ERROR: ' + e.stack; } })();
</script>'''.replace("SOURCES", json.dumps(sources)).replace("SIZES", json.dumps(SIZES)), encoding="utf-8")
        result = run_browser(tmp / "profile", ["--mute-audio",
                             "--virtual-time-budget=10000", "--dump-dom", page.as_uri()],
                             executable=edge, disable_gpu=True, check=True, timeout=90)
        match = re.search(r'<pre id="out">(.*?)</pre>', result.stdout.decode("utf-8"), re.S)
        if not match or not unescape(match[1]).startswith("{"):
            raise RuntimeError("Browser canvas export did not complete")
        rendered = json.loads(unescape(match[1]))
        for product in PRODUCTS:
            folder = BRAND / product
            folder.mkdir(exist_ok=True)
            frames = {int(s): png(base64.b64decode(data)) for s, data in rendered[product].items()}
            for size in (64, 128, 256, 512):
                (folder / f"disc-{product}-{size}.png").write_bytes(frames[size])
            (folder / "apple-touch-icon.png").write_bytes(frames[180])
            (folder / "favicon.ico").write_bytes(ico([(s, frames[s]) for s in (16, 32, 48)]))
            (folder / f"disc-{product}.ico").write_bytes(ico([(s, frames[s]) for s in (16, 24, 32, 48, 64, 128, 256)]))
            if product == "lab":
                lab = ROOT / "disclab/web/brand/lab"
                lab.mkdir(parents=True, exist_ok=True)
                for source in sorted(folder.iterdir()):
                    (lab / source.name).write_bytes(source.read_bytes())
        print("Exported 21 core icons + 7 identical Lab copies")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", "--edge", type=Path)
    parser.add_argument("--temp-dir", type=Path, default=Path("D:/dp-dev/tmp/brand/export"))
    args = parser.parse_args()
    export(args.browser, args.temp_dir)
