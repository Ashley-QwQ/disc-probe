"""Where pictures sit on the disc, apart from any interface: what `edit` saves and `image --design` reads.

A project is a small JSON file holding pictures, where they sit, how big, how far they are turned and where grey
turns dark. Places are in mm from the disc's centre, x to the right and y down, seen from the data side like the
previews. `render` makes the grid `image` burns at any size, so a preview and the final design share one path.
Nothing here draws on a screen or touches a drive.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os

import numpy as np

from . import imagedisc

VERSION = 1
DEFAULT_SIZE_MM = 116.0
PREVIEW_SOURCE_PX = 1024    # a preview never needs more of a picture than this, however large the file is
LIMITS = {"x_mm": (-120.0, 120.0), "y_mm": (-120.0, 120.0), "size_mm": (1.0, 240.0), "threshold": (0.01, 0.99),
          "trim_left": (0.0, 0.98), "trim_top": (0.0, 0.98), "trim_right": (0.0, 0.98), "trim_bottom": (0.0, 0.98)}
MOST_TRIM = 0.98            # of the picture's width or height, across both of its sides


@dataclasses.dataclass
class Layer:
    path: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    size_mm: float = DEFAULT_SIZE_MM    # the picture's longer side; it keeps its shape
    rotation_deg: float = 0.0           # clockwise as seen
    threshold: float = 0.5
    invert: bool = False
    trim_left: float = 0.0              # shares of the picture hidden from each side; the rest stays where it is
    trim_top: float = 0.0
    trim_right: float = 0.0
    trim_bottom: float = 0.0


@dataclasses.dataclass
class Project:
    layers: list[Layer]


@dataclasses.dataclass
class Source:
    """A picture in memory: grey, its opaque part, and the shape of the file it came from."""
    grey: object
    mask: object
    shape: tuple[int, int]


def read_source(path: str, max_side: int | None = None) -> Source:
    from PIL import Image
    limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None       # Pillow's size limit guards against files from strangers; this one was chosen by the user
    try:
        with Image.open(path) as opened:
            shape = opened.size[::-1] if opened.getexif().get(0x0112, 1) in (5, 6, 7, 8) else opened.size
            if max_side:
                opened.draft("L", (max_side, max_side))
            im = imagedisc.upright(opened)
            mask = None
            if "A" in im.getbands() or "transparency" in im.info:
                rgba = im.convert("RGBA")
                alpha = rgba.getchannel("A")
                if alpha.getextrema()[0] < 255:
                    mask = alpha
                grey = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("L")
            else:
                grey = im.convert("L")
    except OSError as e:
        raise ValueError(f"cannot read the picture {path}: {e}") from None
    finally:
        Image.MAX_IMAGE_PIXELS = limit
    if max_side:
        grey.thumbnail((max_side, max_side))
        if mask is not None:
            mask = mask.resize(grey.size)
    return Source(grey, mask, shape)


def _visible(source: Source, layer: Layer, size: tuple[int, int]):
    """What shows of the picture at this size: its opaque part less what is trimmed. None if all of it."""
    from PIL import Image
    mask = source.mask.resize(size) if source.mask is not None else None
    if not (layer.trim_left or layer.trim_top or layer.trim_right or layer.trim_bottom):
        return mask
    width, height = size
    box = (round(layer.trim_left * width), round(layer.trim_top * height),
           width - round(layer.trim_right * width), height - round(layer.trim_bottom * height))
    keep = Image.new("L", size, 0)
    if box[0] < box[2] and box[1] < box[3]:
        keep.paste(mask.crop(box) if mask is not None else 255, box)
    return keep


def auto_threshold(source: Source, layer: Layer) -> float | None:
    """Where this picture's dark and light parts separate best (Otsu), or None if it has only one shade."""
    counts = np.array(source.grey.histogram(_visible(source, layer, source.grey.size)), dtype=np.float64)
    total = counts.sum()
    if not total:
        return None
    below = np.cumsum(counts)[:-1]
    above = total - below
    weighted = np.cumsum(counts * np.arange(256))[:-1]
    usable = (below > 0) & (above > 0)
    if not usable.any():
        return None
    between = np.zeros(255)
    mean_below, mean_above = weighted[usable] / below[usable], (weighted[-1] + 255 * counts[255] - weighted[usable]) / above[usable]
    between[usable] = below[usable] * above[usable] * (mean_below - mean_above) ** 2
    return round((int(np.argmax(between)) + 1) / 255, 3)


def _place(out: np.ndarray, source: Source, layer: Layer) -> None:
    from PIL import Image
    size = out.shape[0]
    cell = 2 * imagedisc.HALF_MM / size
    across = layer.size_mm / cell
    longer = max(source.shape)
    fitted = tuple(max(1, round(across * side / longer)) for side in source.shape)
    grey = source.grey.resize(fitted)
    mask = _visible(source, layer, fitted)
    if layer.rotation_deg % 360:
        if mask is None:
            mask = Image.new("L", fitted, 255)
        grey = grey.rotate(-layer.rotation_deg, Image.BILINEAR, expand=True, fillcolor=255)
        mask = mask.rotate(-layer.rotation_deg, Image.BILINEAR, expand=True, fillcolor=0)
    dark = np.asarray(grey) < layer.threshold * 255
    if layer.invert:
        dark = ~dark
    height, width = dark.shape
    top = (size - height) // 2 + round(layer.y_mm / cell)
    left = (size - width) // 2 + round(layer.x_mm / cell)
    y0, y1, x0, x1 = max(top, 0), min(top + height, size), max(left, 0), min(left + width, size)
    if y0 >= y1 or x0 >= x1:
        return
    part = dark[y0 - top:y1 - top, x0 - left:x1 - left]
    if mask is None:
        out[y0:y1, x0:x1] = part
    else:
        keep = np.asarray(mask)[y0 - top:y1 - top, x0 - left:x1 - left] >= 128
        out[y0:y1, x0:x1][keep] = part[keep]


def render(project: Project, size: int = imagedisc.SIZE, sources: dict[str, Source] | None = None) -> np.ndarray:
    """The design at `size` x `size` (dark = True). What no layer covers stays light. Without `sources` it reads each file whole."""
    out = np.zeros((size, size), bool)
    for layer in project.layers:
        source = sources[layer.path] if sources else read_source(layer.path)
        _place(out, source, layer)
    return out


def coverage(dark: np.ndarray, r_min: float, r_max: float) -> tuple[float, float]:
    """How dark the drawable ring is, and how much of the dark area falls where nothing can be drawn."""
    cell = 2 * imagedisc.HALF_MM / dark.shape[0]
    c = (np.arange(dark.shape[0]) + 0.5) * cell - imagedisc.HALF_MM
    radius = np.hypot(c[None, :], c[:, None])
    ring = (radius >= r_min) & (radius <= r_max)
    total = dark.sum()
    return float(dark[ring].mean()) if ring.any() else 0.0, float((dark & ~ring).sum() / total) if total else 0.0


def clamped(layer: Layer) -> Layer:
    values = {name: min(max(getattr(layer, name), low), high) for name, (low, high) in LIMITS.items()}
    turned = (layer.rotation_deg + 180) % 360 - 180
    return dataclasses.replace(layer, rotation_deg=turned if turned != -180 else 180.0, **values)


def save(project: Project, path: str) -> None:
    """Pictures are kept relative to the project where they can be, so a folder can move as a whole."""
    folder = os.path.dirname(os.path.abspath(path))
    layers = []
    for layer in project.layers:
        entry = dataclasses.asdict(layer)
        try:
            entry["path"] = os.path.relpath(os.path.abspath(layer.path), folder).replace(os.sep, "/")
        except ValueError:      # on another Windows drive
            entry["path"] = os.path.abspath(layer.path)
        layers.append(entry)
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "layers": layers}, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(temporary, path)


def _number(entry: dict, name: str, default: float, where: str) -> float:
    value = entry.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where}: {name} must be a number")
    return float(value)


def load(path: str) -> Project:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ValueError(f"cannot read the design {path}: {e}") from None
    except ValueError:
        raise ValueError(f"{path} is not a design file (it is not JSON)") from None
    if not isinstance(data, dict) or not isinstance(data.get("layers"), list) or not data["layers"]:
        raise ValueError(f"{path} is not a design file (it has no layers)")
    if data.get("version") != VERSION:
        raise ValueError(f"{path} is design version {data.get('version')}; this disc-probe reads version {VERSION}")
    folder = os.path.dirname(os.path.abspath(path))
    layers = []
    for entry in data["layers"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"{path}: each layer needs the path of its picture")
        layers.append(clamped(Layer(os.path.normpath(os.path.join(folder, entry["path"])),
                                    _number(entry, "x_mm", 0.0, path), _number(entry, "y_mm", 0.0, path),
                                    _number(entry, "size_mm", DEFAULT_SIZE_MM, path),
                                    _number(entry, "rotation_deg", 0.0, path), _number(entry, "threshold", 0.5, path),
                                    entry.get("invert") is True, *(_number(entry, name, 0.0, path) for name in
                                                                   ("trim_left", "trim_top", "trim_right", "trim_bottom")))))
    return Project(layers)
