"""`cdprobe`: a DiscImageStudio project for a CD probe disc, with a matching probe pattern.

One disc calibrates a CD-R type: burn this project with DiscImageStudio on a blank of that type,
then `geo --media cd` measures the burned disc itself and gives the inner and outer radius to use
for the type (its summary's dis_equivalent). The burn values only have to be roughly right: the
timing measures the disc, not the project. Close values keep the probe pattern readable, so a
burned disc can be checked by eye against the measurement.

The project is DiscImageStudio's .discproj (schema 2, as written by v1.4.0 to v1.4.2; the loader
rejects unknown fields): CD, the radii and the sector count, constant pitch (DiscImageStudio uses
only the radii pair for CD), one layer, the pattern at 100 %, no offset or rotation, 2 tone levels
without dither, interleave on. A layer at 100 % spans +-ro, the project's outer radius
(DesignLayerViewModel.LoadImage), so the pattern is drawn for that band. DiscImageStudio composes
a CD on a canvas of +-57.5 mm and samples white beyond it, so past 57.5 mm only the parts of the
outer ring and spokes away from the image axes survive.

The pattern (black lines on white; image x right, y down, angle clockwise on screen = along the
track, data side, unmirrored):
  - 12 straight spokes every 30 deg, 0.45 mm wide, across the whole band;
  - rings 0.30 mm wide at every multiple of 5 mm, plus one at each band edge;
  - a 1.6 mm radial tick on each ring at 10 deg, so spoke 0 can be followed ring by ring on a
    twisted disc;
  - a polar "F" in the ring gap nearest the band middle at 195 deg; it reads normally on the data
    side and only shears under a twist, so a mirrored photo shows at once;
  - a twist gauge (default on): the half band from 105 to 285 deg inverted. The spokes become
    hairlines once the burn values are about 1 um off; the gauge's edges then wind into a two-start
    spiral that stays visible up to about 100 um off.
The PNG carries the feature list as JSON in a tEXt chunk "DiscImageStudio-probe-pattern".
"""

from __future__ import annotations

import datetime
import json
import math
import os
import struct
import uuid
import zlib

TEXT_KEY = "DiscImageStudio-probe-pattern"
SECTOR_MM = 1200.0 / 75.0       # track length per sector at DiscImageStudio's fixed 1200 mm/s
# Default burn values: the inner radius and pitch typical of the 80-minute CD-Rs measured so far
# (24.912-24.922 mm, 1.4865-1.4926 um); ro follows from the sector count.
GENERIC_RI_MM = 24.92
GENERIC_PITCH_UM = 1.4865
CANVAS_MM = 57.5                # CdDiscParameters.StandardImageOuterRadiusMm
MIN_SECTORS, MAX_SECTORS = 10_000, 450_000


def generic_radii(sectors: int) -> tuple[float, float]:
    """ri and the ro that gives the generic pitch over this many sectors (area formula)."""
    ri = GENERIC_RI_MM
    return ri, math.sqrt(ri * ri + GENERIC_PITCH_UM * 1e-3 * sectors * SECTOR_MM / math.pi)


def pitch_um(ri: float, ro: float, sectors: int) -> float:
    return math.pi * (ro * ro - ri * ri) / (sectors * SECTOR_MM) * 1e3


def check(ri: float, ro: float, sectors: int) -> None:
    if not MIN_SECTORS <= sectors <= MAX_SECTORS:
        raise ValueError(f"--sectors {sectors} is outside {MIN_SECTORS}..{MAX_SECTORS}; give the blank's capacity "
                         "from `info`")
    if not (all(math.isfinite(v) for v in (ri, ro)) and 15 < ri < 35 and ri + 5 < ro < 62):
        raise ValueError(f"radii {ri} / {ro} mm are not those of a CD")


# ------------------------------------------------------------------------------------------------ pattern

def png_bytes(w: int, h: int, rows, texts: dict | None = None) -> bytes:
    """8-bit greyscale PNG, filter 0 on every row."""
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    for k, v in (texts or {}).items():
        out += chunk(b"tEXt", k.encode("latin-1") + b"\x00" + v.encode("latin-1"))
    return out + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


class Raster:
    """Binary canvas; pixel (i, j) has its centre at ((i + 0.5 - W/2) * mmpx, (j + 0.5 - W/2) * mmpx) mm."""

    def __init__(self, size: int, span_mm: float):
        self.W = size
        self.mmpx = 2.0 * span_mm / size
        self.px = bytearray(b"\xff") * (size * size)

    def col_range(self, lo, hi):
        i0 = max(0, int(math.ceil(lo / self.mmpx + self.W / 2 - 0.5)))
        i1 = min(self.W - 1, int(math.floor(hi / self.mmpx + self.W / 2 - 0.5)))
        return i0, i1

    def ycoord(self, j):
        return (j + 0.5 - self.W / 2) * self.mmpx

    def fill_row(self, j, i0, i1):
        if i1 >= i0:
            self.px[j * self.W + i0: j * self.W + i1 + 1] = bytes(i1 - i0 + 1)

    def strip(self, angle_deg, s0, s1, width):
        """Rectangle along direction angle: s0 <= p.u <= s1, |p.n| <= width/2 (u = (cos, sin), n = (-sin, cos))."""
        a = math.radians(angle_deg)
        ux, uy = math.cos(a), math.sin(a)
        hw = width / 2
        ys = [s * uy + t * ux for s in (s0, s1) for t in (-hw, hw)]
        j0, j1 = self.col_range(min(ys), max(ys))
        for j in range(j0, j1 + 1):
            y = self.ycoord(j)
            lo, hi = -1e9, 1e9
            for a_, b_, vlo, vhi in ((ux, y * uy, s0, s1), (-uy, y * ux, -hw, hw)):
                if abs(a_) < 1e-15:
                    if not vlo <= b_ <= vhi:
                        lo, hi = 1.0, 0.0
                    continue
                xa, xb = sorted(((vlo - b_) / a_, (vhi - b_) / a_))
                lo, hi = max(lo, xa), min(hi, xb)
            if lo <= hi:
                self.fill_row(j, *self.col_range(lo, hi))

    def annulus(self, r_lo, r_hi):
        j0, j1 = self.col_range(-r_hi, r_hi)
        for j in range(j0, j1 + 1):
            y = self.ycoord(j)
            if abs(y) > r_hi:
                continue
            xo = math.sqrt(r_hi * r_hi - y * y)
            if abs(y) < r_lo:
                xi = math.sqrt(r_lo * r_lo - y * y)
                self.fill_row(j, *self.col_range(-xo, -xi))
                self.fill_row(j, *self.col_range(xi, xo))
            else:
                self.fill_row(j, *self.col_range(-xo, xo))

    def sector(self, r_lo, r_hi, a_lo_deg, a_hi_deg):
        """Annular sector r_lo <= r <= r_hi, a_lo <= angle <= a_hi (degrees, clockwise on screen)."""
        mid = math.radians((a_lo_deg + a_hi_deg) / 2)
        half = math.radians((a_hi_deg - a_lo_deg) / 2)
        pts = [(r * math.cos(mid + t * half), r * math.sin(mid + t * half))
               for r in (r_lo, r_hi) for t in [k / 8 - 1 for k in range(17)]]
        i0, i1 = self.col_range(min(p[0] for p in pts) - self.mmpx, max(p[0] for p in pts) + self.mmpx)
        j0, j1 = self.col_range(min(p[1] for p in pts) - self.mmpx, max(p[1] for p in pts) + self.mmpx)
        for j in range(j0, j1 + 1):
            y = self.ycoord(j)
            for i in range(i0, i1 + 1):
                x = (i + 0.5 - self.W / 2) * self.mmpx
                r = math.hypot(x, y)
                if r_lo <= r <= r_hi and abs(math.remainder(math.atan2(y, x) - mid, 2 * math.pi)) <= half:
                    self.px[j * self.W + i] = 0

    def invert_halfplane(self, edge_deg, r_lo, r_hi):
        """Invert r_lo <= r <= r_hi on the clockwise side of the diameter at edge_deg."""
        a = math.radians(edge_deg)
        nx, ny = -math.sin(a), math.cos(a)            # n.p > 0 on that side
        inv = bytes(255 - v for v in range(256))
        j0, j1 = self.col_range(-r_hi, r_hi)
        for j in range(j0, j1 + 1):
            y = self.ycoord(j)
            if abs(y) > r_hi:
                continue
            xo = math.sqrt(r_hi * r_hi - y * y)
            parts = [(-xo, xo)]
            if abs(y) < r_lo:
                xi = math.sqrt(r_lo * r_lo - y * y)
                parts = [(-xo, -xi), (xi, xo)]
            for lo, hi in parts:
                if abs(nx) < 1e-15:
                    if ny * y <= 0:
                        continue
                elif nx > 0:
                    lo = max(lo, -ny * y / nx)
                else:
                    hi = min(hi, -ny * y / nx)
                if lo <= hi:
                    i0, i1 = self.col_range(lo, hi)
                    if i1 >= i0:
                        k0, k1 = j * self.W + i0, j * self.W + i1 + 1
                        self.px[k0:k1] = self.px[k0:k1].translate(inv)

    def rows(self):
        return [bytes(self.px[j * self.W:(j + 1) * self.W]) for j in range(self.W)]


def design(r0: float, r1: float, gauge: bool = True, spoke_w=0.45, ring_w=0.30, ring_step=5.0, edge_gap=1.3,
           tick_angle=10.0, tick_len=1.6, tick_w=0.45, glyph_angle=195.0, glyph_h=3.6, glyph_w=2.8, glyph_st=0.6,
           nspokes=12, gauge_edge=105.0) -> dict:
    """Feature list in image mm (also written into the PNG)."""
    if not 0 < r0 < r1:
        raise ValueError("the band needs 0 < ri < ro")
    rings = [{"r": r0 + ring_w / 2, "width": ring_w, "edge": "inner"}]
    k = math.ceil(r0 / ring_step)
    while k * ring_step < r1:
        R = k * ring_step
        if R - r0 >= edge_gap and r1 - R >= edge_gap:
            rings.append({"r": R, "width": ring_w, "edge": None})
        k += 1
    rings.append({"r": r1 - ring_w / 2, "width": ring_w, "edge": "outer"})
    ticks = []
    for rg in rings:
        if rg["edge"] == "inner":
            a, b = r0, r0 + tick_len
        elif rg["edge"] == "outer":
            a, b = r1 - tick_len, r1
        else:
            a, b = rg["r"] - tick_len / 2, rg["r"] + tick_len / 2
        ticks.append({"ring": rg["r"], "angle": tick_angle, "r0": a, "r1": b, "width": tick_w})
    gaps = []
    for ra, rb in zip(rings, rings[1:]):
        lo, hi = ra["r"] + ra["width"] / 2, rb["r"] - rb["width"] / 2
        if hi - lo >= glyph_h + 0.8:
            gaps.append(((lo + hi) / 2, lo, hi))
    if not gaps:
        raise ValueError("no ring gap is wide enough for the glyph")
    mid = (r0 + r1) / 2
    gc = min(gaps, key=lambda g: abs(g[0] - mid))[0]
    spokes = [{"angle": 360.0 * i / nspokes, "r0": r0, "r1": r1, "width": spoke_w} for i in range(nspokes)]
    feat = {"version": 1, "band": [r0, r1], "span_mm": r1, "spokes": spokes, "rings": rings, "ticks": ticks,
            "glyph": {"char": "F", "style": "polar", "r": gc, "angle": glyph_angle, "height": glyph_h,
                      "width": glyph_w, "stroke": glyph_st, "mid_bar": 0.8, "mid_bar_v": 0.05},
            "frame": "x right, y down, angle = atan2(y, x) clockwise on screen (data side, unmirrored); "
                     "image spans +-span_mm at 100 % scale"}
    if gauge:
        feat["gauge"] = {"type": "halfplane-xor", "edges": [gauge_edge, gauge_edge + 180.0],
                         "inverted": [gauge_edge, gauge_edge + 180.0], "r0": r0, "r1": r1}
    return feat


def glyph_strokes(g: dict):
    """F as three annular sectors (r_lo, r_hi, a_lo, a_hi) in degrees; up = outward, right = clockwise."""
    rc, ac, h, wd, st = g["r"], g["angle"], g["height"], g["width"], g["stroke"]
    left = ac - math.degrees(wd / 2 / rc)
    right = ac + math.degrees(wd / 2 / rc)
    stem = (rc - h / 2, rc + h / 2, left, left + math.degrees(st / rc))
    top = (rc + h / 2 - st, rc + h / 2, left, right)
    vm = rc + g["mid_bar_v"] * h
    midb = (vm - st / 2, vm + st / 2, left, left + math.degrees(g["mid_bar"] * wd / rc))
    return [stem, top, midb]


def render(feat: dict, size: int) -> Raster:
    ras = Raster(size, feat["span_mm"])
    for sp in feat["spokes"]:
        ras.strip(sp["angle"], sp["r0"], sp["r1"], sp["width"])
    for rg in feat["rings"]:
        ras.annulus(rg["r"] - rg["width"] / 2, rg["r"] + rg["width"] / 2)
    for tk in feat["ticks"]:
        ras.strip(tk["angle"], tk["r0"], tk["r1"], tk["width"])
    for s in glyph_strokes(feat["glyph"]):
        ras.sector(*s)
    if "gauge" in feat:
        g = feat["gauge"]
        ras.invert_halfplane(g["edges"][0], g["r0"], g["r1"])
    return ras


# ------------------------------------------------------------------------------------------------ project

def windows_path(p: str) -> str:
    return os.path.abspath(p).replace("/", "\\")


def project(name: str, ri: float, ro: float, sectors: int, pattern: str, audio: str) -> dict:
    """A DiscImageStudio CD project in schema 2, field for field as v1.4.0-v1.4.2 read and write it."""
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "schemaVersion": 2,
        "name": name,
        "discFamily": "cd",
        "geometry": {"innerRadiusMm": float(ri), "outerRadiusMm": float(ro), "sectors": int(sectors),
                     "pitchLinear": 0, "pitchQuadratic": 0, "pitchCubic": 0},
        "layers": [{"id": uuid.uuid4().hex, "name": os.path.basename(pattern), "imagePath": windows_path(pattern),
                    "visible": True, "translateXMm": 0, "translateYMm": 0, "rotationDeg": 0, "scale": 1}],
        "outputs": {"outputPath": windows_path(audio), "writeCue": True, "dataDirectory": "",
                    "volumeLabel": "CD_IMAGE", "interleave": True},
        "calibrationSessionPath": None,
        "thumbnailPngBase64": None,
        "createdUtc": now,
        "modifiedUtc": now,
        "tone": {"ditherStrength": 0, "levels": 2, "brightness": 0, "srgbLinearization": False},
        "bluRay": None,
    }


def write(path: str, sectors: int, radii: tuple[float, float] | None = None, gauge: bool = True,
          size: int = 4096, name: str | None = None, force: bool = False) -> dict:
    """Write <path> (.discproj), its pattern <stem>.png next to it; the burn writes <stem>.wav there."""
    ri, ro = radii if radii else generic_radii(sectors)
    check(ri, ro, sectors)
    stem = os.path.splitext(path)[0]
    pattern, audio = stem + ".png", stem + ".wav"
    for p in (path, pattern):
        if os.path.exists(p) and not force:
            raise FileExistsError(f"{p} exists (add --force to overwrite it)")
    feat = design(ri, ro, gauge=gauge)
    feat["size_px"] = size
    ras = render(feat, size)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(pattern, "wb") as f:
        f.write(png_bytes(size, size, ras.rows(), {TEXT_KEY: json.dumps(feat, separators=(",", ":"))}))
    doc = project(name or os.path.basename(stem), ri, ro, sectors, pattern, audio)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    return {"project": os.path.abspath(path), "pattern": os.path.abspath(pattern), "ri": ri, "ro": ro,
            "sectors": sectors, "pitch_um": pitch_um(ri, ro, sectors), "beyond_canvas": ro > CANVAS_MM}
