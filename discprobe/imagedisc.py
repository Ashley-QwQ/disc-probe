"""Burnable DVD image of a picture, placed with a measured geometry (u = r0/b, v = p/b).

Every 16-byte group of every sector gets the picture's value at its position on the
disc: dark groups are recorded as one texture (A5), light ones as another. Positions
come from the same model the `geo` ladder fits,

    Theta(n) = 2n / (S + u),  S = sqrt(u^2 + v n / pi),  radius = b * S,

so u and v fix every angle exactly; the assumed bit length b only scales the picture
uniformly, which cannot bend a line. The disc turns counter-clockwise as seen by the
optical head (ECMA-267), so seen from the data side the track angle runs clockwise:
the picture is drawn in data-side view with y up, and its rotation on the disc is
arbitrary.
"""

from __future__ import annotations

import json
import math
import os
import re

import numpy as np

from . import dvd, iso9660
from .calib import GROUP_BITS, GROUP_BYTES, SECTOR_BITS, sector_bits, theta

CELL_MM = 0.02
HALF_MM = 60.0
SIZE = int(2 * HALF_MM / CELL_MM)
# The cell sizes a design may have, in micrometres, and its side in cells. 20 um is the default;
# 10 and 5 um were checked under a microscope on an LTVA1 burn (lines part at 5 um, a 10 um
# checkerboard is clear). The cell size is the design's: a square array of one of these sides.
CELL_SIDES = {20: 6000, 10: 12000, 5: 24000}


def cell_mm(design) -> float:
    """The cell size of a design, from its side: the array always spans the 120 mm disc."""
    return 2 * HALF_MM / design.shape[0]


def check_cells(design, cell_um: int | None = None) -> int:
    """The design's cell size in um, if it is one of CELL_SIDES (and the one asked for, if any)."""
    n = design.shape[0]
    um = next((u for u, side in CELL_SIDES.items() if side == n), None)
    if design.ndim != 2 or design.shape[1] != n or um is None:
        raise ValueError("a design is a square array of " + ", ".join(f"{s} x {s} ({u} um cells)" for u, s in CELL_SIDES.items()))
    if cell_um is not None and cell_um != um:
        raise ValueError(f"the design has {um} um cells ({n} x {n}), not {cell_um} um")
    return um


def _grid_coords(size: int = SIZE):
    c = (np.arange(size) + 0.5) * (2 * HALF_MM / size) - HALF_MM
    return c[None, :], -c[:, None]  # x right, y up


def grid_design(r_min=24.5, r_max=56.0, spacing=5.0, line=0.3, size: int = SIZE) -> np.ndarray:
    """True = dark. Cartesian grid, radial lines every 30 degrees, circles every
    spacing mm, and a block letter F (asymmetric, so a mirrored burn is obvious)."""
    x, y = _grid_coords(size)
    r = np.hypot(x, y)
    th = np.degrees(np.arctan2(y, x))
    half = line / 2
    near = lambda v: np.abs((v + spacing / 2) % spacing - spacing / 2) < half
    dark = near(x) | near(y)
    dark |= np.abs(r - np.round(r / spacing) * spacing) < half
    for a in range(0, 360, 30):
        d = np.abs(((th - a + 180) % 360) - 180)
        dark |= (np.radians(d) * r < max(0.2, half)) & (d < 90)
    # Letter F, 10 mm tall, in the upper half (stroke 1.2 mm).
    fx, fy, s = -3.0, 33.0, 1.2
    dark |= (x >= fx) & (x < fx + s) & (y >= fy) & (y < fy + 10)
    dark |= (x >= fx) & (x < fx + 6) & (y >= fy + 10 - s) & (y < fy + 10)
    dark |= (x >= fx) & (x < fx + 4.5) & (y >= fy + 5 - s / 2) & (y < fy + 5 + s / 2)
    return dark & (r >= r_min) & (r <= r_max)


def upright(im):
    """The picture the way up it was taken: a phone stores a sideways frame and a note saying which way to turn it."""
    from PIL import ImageOps
    return ImageOps.exif_transpose(im) if im.getexif().get(0x0112, 1) != 1 else im


def picture_design(path: str, diameter_mm: float = 116.0, threshold: float = 0.5, cell: float = CELL_MM) -> np.ndarray:
    """A grey picture fitted to a circle of the given diameter, thresholded (dark = True).

    Its longer side spans the diameter and it keeps its shape; what it doesn't cover stays light.
    """
    from PIL import Image
    n = round(diameter_mm / cell)
    side = round(2 * HALF_MM / cell)
    limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None       # Pillow's size limit guards against files from strangers; this one was chosen by hand
    try:
        with Image.open(path) as opened:
            im = upright(opened)
            longer = max(im.size)
            size = tuple(max(1, round(n * side / longer)) for side in im.size)
            g = np.asarray(im.convert("L").resize(size), dtype=np.float32) / 255
    finally:
        Image.MAX_IMAGE_PIXELS = limit
    out = np.zeros((side, side), bool)
    y, x = (side - g.shape[0]) // 2, (side - g.shape[1]) // 2
    out[y:y + g.shape[0], x:x + g.shape[1]] = g < threshold
    return out


def clear_inside(design: np.ndarray, r_mm: float) -> np.ndarray:
    """The design with everything inside this radius turned to background."""
    x, y = _grid_coords(design.shape[0])
    out = design.copy()
    out[np.hypot(x, y) < r_mm] = False
    return out


class Correction:
    """phi(r) in degrees: a polynomial in x = (r - 40) / 15, held constant outside [lo, hi] mm. A class rather than
    a closure so that write_iso can hand it to worker processes."""

    def __init__(self, coef, lo: float, hi: float):
        self.coef, self.lo, self.hi = np.asarray(coef, dtype=np.float64), float(lo), float(hi)

    def __call__(self, r):
        return np.polyval(self.coef, (np.clip(r, self.lo, self.hi) - 40.0) / 15.0)


def drawing_span(design):
    """Actual non-background pixels, in mm; row chunks avoid another full-size grid."""
    coords = (np.arange(design.shape[0]) + .5) * (2 * HALF_MM / design.shape[0]) - HALF_MM
    lo, hi = float('inf'), 0.
    for offset in range(0, len(coords), 128):
        y, x = np.nonzero(design[offset:offset + 128])
        if len(x):
            radii = np.hypot(coords[x], coords[y + offset])
            lo, hi = min(lo, float(radii.min())), max(hi, float(radii.max()))
    half_cell = HALF_MM / len(coords)
    return [max(0., lo - half_cell), hi + half_cell] if math.isfinite(lo) else None


def load_correction(path: str) -> Correction:
    """phi(r) in degrees from an angle-correction file (polynomial, held constant outside its range)."""
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    lo, hi = c["radius_valid_mm"]
    if 'spline' in c:
        return SplineCorrection(c['spline'], lo, hi)
    return Correction(c["poly_in_x"], lo, hi)


class SplineCorrection:
    """Same clipped phi(r) contract as Correction, with a cubic B-spline payload."""
    def __init__(self, spline, lo, hi):
        from scipy.interpolate import BSpline
        self.lo, self.hi = float(lo), float(hi)
        self.spline = BSpline(spline['t'], spline['c'], spline['k'])

    def __call__(self, r):
        return self.spline(np.clip(r, self.lo, self.hi))


def _timing_source(c: dict) -> str | None:
    """The tools/geo_polyfit.py command behind a correction, itself or as the base scans were added to."""
    return next((str(c[k]) for k in ("source", "base_source")
                 if str(c.get(k)).startswith("tools/geo_polyfit.py ")), None)


def correction_from_timing(path: str) -> bool:
    """True for a correction made from a geo run by tools/geo_polyfit.py, False for one from grid scans."""
    with open(path, encoding="utf-8") as f:
        return str(json.load(f).get("source")).startswith(("tools/geo_polyfit.py ", 'geo automatic'))


def geometry_fit(geo: str) -> dict | None:
    """u and v of a geo summary.json (or its folder), or None when it can't be read."""
    path = os.path.join(geo, "summary.json") if os.path.isdir(geo) else geo
    try:
        with open(path, encoding="utf-8") as f:
            fit = json.load(f).get("fit") or {}
        return {"u": float(fit["u"]), "v": float(fit["v"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _geometry_name(geometry) -> str:
    g = str(geometry).rstrip("\\/")
    parts = re.split(r"[\\/]", g)
    return parts[-2] if parts[-1].endswith(".json") and len(parts) > 1 else parts[-1]


def correction_unchecked(path: str) -> bool:
    """A grid-scan correction that records no geometry that can be read: which run it fits is unknown."""
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    return (not _timing_source(c) and not c.get("geo_fit")
            and not (c.get("geometry") and geometry_fit(str(c["geometry"]))))


def correction_other_run(path: str, u: float, v: float, geo_path: str) -> str | None:
    """The geo run a correction was made for, if it isn't this one. A timing correction's phi(r) is
    relative to that run's u and v; a grid-scan correction measures what a grid burned with one
    geometry left. With another run's either moves the picture by the wrong amount without any error."""
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    source = _timing_source(c)
    if not source:
        fit = c.get("geo_fit") or (geometry_fit(str(c["geometry"])) if c.get("geometry") else None)
        if not fit:
            return None
        same = math.isclose(fit["u"], u, rel_tol=1e-9) and math.isclose(fit["v"], v, rel_tol=1e-9)
        return None if same else _geometry_name(c.get("geometry") or "the run its grid was burned with")
    run = re.split(r"[\\/]", source.split(" ", 1)[1].rstrip("\\/"))[-1]
    fit = c.get("geo_fit")
    if fit:
        same = math.isclose(fit["u"], u, rel_tol=1e-9) and math.isclose(fit["v"], v, rel_tol=1e-9)
    else:       # written before geo_fit: the folder name is all there is, and "." says nothing
        same = not run.startswith("geo-") or run == os.path.basename(os.path.dirname(os.path.abspath(geo_path)))
    return None if same else run


def sectors_to_radius(u: float, v: float, bit_nm: float, r_mm: float, media: str = "dvd") -> int:
    s = r_mm / (bit_nm * 1e-6)
    n = math.pi * (s * s - u * u) / v
    return int(n // sector_bits(media)[0]) // 16 * 16


CHUNK = 2048

# Column of each user byte in its data-frame row (12 header bytes, 172 bytes per row);
# repeating sequences are phased by column so the period runs on along the recorded row.
_COL = (12 + np.arange(dvd.SECTOR_BYTES)) % 172


def _hash(lbas: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic pseudo-random uint64 per (sector, byte) (splitmix64 finaliser)."""
    with np.errstate(over="ignore"):
        x = (lbas[:, None].astype(np.uint64) * np.uint64(2048) + np.arange(dvd.SECTOR_BYTES, dtype=np.uint64)[None, :]
             + np.uint64(salt) * np.uint64(0x9E3779B97F4A7C15))
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


def texture_bytes(spec: str, lbas: np.ndarray) -> np.ndarray:
    """Recorded-domain bytes Q (sectors x 2048) of one texture:
    "A5" one byte; "8B00" a byte sequence repeated along each row; "RND" random bytes;
    "MIX:92,4F" a random choice from the listed bytes."""
    n = len(lbas)
    if spec == "RND":
        return (_hash(lbas, 1) & np.uint64(0xFF)).astype(np.uint8)
    if spec.startswith("MIX:"):
        pool = np.array([int(b, 16) for b in spec[4:].split(",")], np.uint8)
        return pool[(_hash(lbas, 2) % np.uint64(len(pool))).astype(np.int64)]
    seq = np.frombuffer(bytes.fromhex(spec), np.uint8)
    return np.broadcast_to(seq[_COL % len(seq)], (n, dvd.SECTOR_BYTES)).copy()


def _sample(design, u, v, bit_mm, lba0, count, correction=None, media="dvd"):
    """Design value at every 16-byte group of the given sectors (False / 0 outside)."""
    bits, group_bits = sector_bits(media)
    lbas = np.arange(lba0, lba0 + count)
    n = lbas[:, None].astype(np.float64) * bits + group_bits[None, :]
    s = np.sqrt(u * u + v * n / math.pi)
    th = -(2.0 * n / (s + u))  # theta's identical expression, reusing its square root
    r = bit_mm * s
    if correction is not None:
        # A byte at model angle th shows up at th + phi(r): give it the design there.
        th = th + np.radians(correction(r))
    size = design.shape[0]
    cell = 2 * HALF_MM / size
    ix = np.floor((r * np.cos(th) + HALF_MM) / cell).astype(np.int64)
    iy = np.floor((HALF_MM - r * np.sin(th)) / cell).astype(np.int64)
    ok = (ix >= 0) & (ix < size) & (iy >= 0) & (iy < size)
    return np.where(ok, design[np.clip(iy, 0, size - 1), np.clip(ix, 0, size - 1)], 0).astype(design.dtype)


def _textures(design: np.ndarray, dark: str, light: str, textures):
    """A boolean design picks light/dark; a label design (uint8) indexes `textures`."""
    if design.dtype == bool:
        return [light, dark]
    if not textures or int(design.max()) >= len(textures):
        raise ValueError("a label design needs one texture per label")
    return list(textures)


def _sector_q(design, texs, u, v, bit_mm, lba0, count, correction, media="dvd"):
    lbas = np.arange(lba0, lba0 + count)
    samples = _sample(design, u, v, bit_mm, lba0, count, correction, media)
    if all(len(t) == 2 for t in texs):
        # A single-byte texture has no phase: gather once per group, then
        # expand bytes, rather than expanding int64 labels and texture stacks.
        palette = np.array([bytes.fromhex(t)[0] for t in texs], dtype=np.uint8)
        indices = samples.astype(np.uint8) if samples.dtype == bool else samples.astype(np.int64, copy=False)
        groups = palette[indices]
        return np.broadcast_to(groups[:, :, None], (*groups.shape, GROUP_BYTES)).copy().reshape(count, dvd.SECTOR_BYTES)
    labels = np.repeat(samples.astype(np.int64),
                       GROUP_BYTES, axis=1)
    stack = np.stack([texture_bytes(t, lbas) for t in texs])
    return np.take_along_axis(stack, labels[None], 0)[0]


def _scramble_masks(media: str, lbas: np.ndarray) -> np.ndarray:
    """The mask the drive will XOR into these sectors: DVD's preset table or Blu-ray's register."""
    if media == "bd":
        from . import bd
        return bd.masks(lbas)
    if media != "dvd":
        raise ValueError(f"no scrambler for {media!r}: a picture disc is dvd or bd")
    return dvd.MASKS[((lbas + dvd.DATA_START_PSN) >> 4) & 0xF]


PARALLEL_MIN_SECTORS = 64 * CHUNK     # below this (tests, small rings) the pool costs more than it saves
_JOB: dict = {}


def workers() -> int:
    """Worker processes for write_iso: DISCPROBE_WORKERS if set (1 = in this process), else half the logical
    cores (about the physical ones), up to 6. On a 12-thread machine a chunk took 52 ms alone and 148 ms with
    twelve at once, and the total stopped improving past four to six. Each worker holds its own copy of the
    design (36 MB for a 6000 x 6000 one)."""
    try:
        n = int(os.environ.get("DISCPROBE_WORKERS", "0"))
    except ValueError:
        n = 0
    return n if n > 0 else max(1, min(6, (os.cpu_count() or 2) // 2))


def _job_init(job: dict) -> None:
    _JOB.clear()
    _JOB.update(job)
    if "design_file" in job:
        _JOB["design"] = np.load(job["design_file"], mmap_mode="r")


SHARED_DESIGN_BYTES = 64 << 20     # above this the workers read the design from one file, not a copy each


def _job_chunk(span):
    """The recorded bytes of sectors a .. a+n as written to the file: the design (or random data below
    lead_lba, seeded by the chunk start), scrambled as the drive will scramble it."""
    a, n = span
    j = _JOB
    q = _sector_q(j["design"], j["texs"], j["u"], j["v"], j["bit_mm"], a, n, j["correction"], j["media"])
    if a < j["lead_lba"]:
        k = min(n, j["lead_lba"] - a)
        q[:k] = np.random.default_rng(a).integers(0, 256, (k, dvd.SECTOR_BYTES), dtype=np.uint8)
    return a, n, (q ^ _scramble_masks(j["media"], np.arange(a, a + n))).tobytes()


def _job_chunk_to_file(span):
    """In a worker: compute a chunk and write it at its place in the file, so only (a, n) travels back."""
    a, n, data = _job_chunk(span)
    if "file" not in _JOB:
        _JOB["file"] = open(_JOB["path"], "r+b")
    f = _JOB["file"]
    f.seek((a - _JOB["first_lba"]) * dvd.SECTOR_BYTES)
    f.write(data)
    f.flush()
    return a, n


def _write_chunks(path: str, job: dict, spans, first_lba: int):
    """Write the chunks to path and yield (a, n) as each is done. Chunks are independent, so a large image goes
    to a pool of processes that each write their chunks in place (a full DVD on a 12-thread machine: about
    70 s in one process, 30 s in a pool). The chunk boundaries are the same either way, so the file is
    identical byte for byte."""
    total = sum(n for _, n in spans)
    count = workers()
    if count == 1 or total < PARALLEL_MIN_SECTORS:
        _job_init(job)
        try:
            with open(path, "wb") as f:
                for a, n, data in map(_job_chunk, spans):
                    f.write(data)
                    yield a, n
        finally:
            _JOB.clear()
        return
    print(f"Starting {count} worker processes (DISCPROBE_WORKERS={os.environ.get('DISCPROBE_WORKERS', 'auto')}); preparing image chunks...", flush=True)
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with open(path, "wb") as f:
        f.truncate(total * dvd.SECTOR_BYTES)
    shared = {**job, "path": path, "first_lba": first_lba}
    design_file = None
    if job["design"].nbytes > SHARED_DESIGN_BYTES:      # 576 MB at 5 um: once on disk, not once per worker
        design_file = path + ".design.npy"
        np.save(design_file, np.ascontiguousarray(job["design"]))
        shared = {k: v for k, v in shared.items() if k != "design"} | {"design_file": design_file}
    try:
        with ProcessPoolExecutor(max_workers=count, initializer=_job_init, initargs=(shared,)) as pool:
            for done in as_completed([pool.submit(_job_chunk_to_file, span) for span in spans]):
                yield done.result()
    finally:
        if design_file:
            try:
                os.remove(design_file)
            except OSError:
                pass


def write_iso(path: str, design: np.ndarray, u: float, v: float, bit_nm: float, total_sectors: int,
              dark: str = "A5", light: str = "B9", log=print, meta: dict | None = None, correction=None,
              textures=None, first_lba: int = 0, lead_lba: int = 0, media: str = "dvd") -> str:
    """With first_lba, the file holds only sectors first_lba.. for appending to a disc already written up to
    there; it then has no file system of its own. Sectors below lead_lba hold random data instead of the design:
    a GU70N in a USB case failed to write a picture from the first sector on, yet wrote textures after random data."""
    texs = _textures(design, dark, light, textures)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    job = {"design": design, "texs": texs, "u": u, "v": v, "bit_mm": bit_nm * 1e-6, "correction": correction,
           "media": media, "lead_lba": lead_lba}
    spans = [(a, min(CHUNK, total_sectors - a)) for a in range(first_lba, total_sectors, CHUNK)]
    next_report, count, written = 0.0, total_sectors - first_lba, 0
    for a, n in _write_chunks(path, job, spans, first_lba):
        written += n
        if written / count >= next_report - 1e-9:   # (steps of 0.01 add up to a hair over 1)
            log(f"  {100 * written / count:5.1f} %")
            next_report += getattr(log, "every", 0.2)
    if not first_lba:
        iso9660.add(path, total_sectors, "DISCPROBE_IMAGE")
    spec = {"kind": "dvd-picture", "media": media, "u": u, "v": v, "bit_nm": bit_nm,
            "total_sectors": total_sectors,
            "first_lba": first_lba, "lead_lba": lead_lba, "textures": texs, "cell_mm": cell_mm(design), **(meta or {})}
    if design.dtype == bool:
        spec.update(dark=dark, light=light)
    spec_path = os.path.splitext(path)[0] + ".image.json"
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
    return spec_path


def verify_iso(path: str, design: np.ndarray, u: float, v: float, bit_nm: float, total_sectors: int,
               dark: str = "A5", light: str = "B9", samples: int = 300, seed: int = 3, correction=None,
               textures=None, first_lba: int = 0, lead_lba: int = 0, media: str = "dvd") -> list[str]:
    """Descramble random sectors and compare every byte with a recomputation from the design (past lead_lba)."""
    problems = []
    if os.path.getsize(path) != (total_sectors - first_lba) * dvd.SECTOR_BYTES:
        return ["size mismatch"]
    texs = _textures(design, dark, light, textures)
    rng = np.random.default_rng(seed)
    with open(path, "rb") as f:
        for lba in rng.integers(max(32, first_lba, lead_lba), total_sectors, samples):
            f.seek((int(lba) - first_lba) * dvd.SECTOR_BYTES)
            rec = np.frombuffer(f.read(dvd.SECTOR_BYTES), dtype=np.uint8) ^ _scramble_masks(media, np.array([int(lba)]))[0]
            want = _sector_q(design, texs, u, v, bit_nm * 1e-6, int(lba), 1, correction, media)[0]
            if not np.array_equal(rec, want):
                problems.append(f"LBA {lba} differs from the design")
    return problems


def preview(design: np.ndarray, path: str, size: int = 1200) -> None:
    from PIL import Image
    pixels = np.empty(design.shape, np.uint8)
    np.equal(design, 0, out=pixels)
    pixels *= np.uint8(255)
    img = Image.fromarray(pixels).resize((size, size))
    img.save(path)
