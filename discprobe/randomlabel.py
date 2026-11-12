"""DVD label glyphs, measured placement, and checksummed in-disc layout records."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import imagedisc
from .calib import SECTOR_BITS
from .geometry import NOMINAL

INNER_MM, OUTER_MM = 54.5, 57.5
HEIGHT_MM, CELL_MM = 2.4, 0.02
LIGHT, DARK = "66", "A5"
BIT_NM = 133.3
U = NOMINAL["dvd"].r0_mm / (BIT_NM * 1e-6)
V = NOMINAL["dvd"].pitch_mm / (BIT_NM * 1e-6)
START = imagedisc.sectors_to_radius(U, V, BIT_NM, INNER_MM)
END = imagedisc.sectors_to_radius(U, V, BIT_NM, OUTER_MM)
# Leave a random rim beyond the guard so setup's end-of-disc warmup stays off the band.
MIN_SECTORS = math.ceil((END + 3000 + 16) / 16) * 16
MAGIC = b"DISCPROBE_RANDOM_LABEL_V1\n"
PENDING_LBA = 32
# A discoverable address inside the band for both measured example batches.
# Reject geometries whose band does not contain it; never write a marker outside the band.
MARKER_LBA = 2050000
STOP_MM = 50.0
STOP_SECTORS = imagedisc.sectors_to_radius(U, V, BIT_NM, STOP_MM)


def marker(spec):
    payload = json.dumps(spec, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    data = MAGIC + hashlib.sha256(payload).hexdigest().encode() + b"\n" + payload + b"\n"
    if len(data) > 2048:
        raise ValueError("label metadata is too large")
    return data.ljust(2048, b"\0")


def read_marker(data, total_sectors):
    """An absent marker means an old random disc; a damaged recognized marker is an error."""
    if not data.startswith(MAGIC):
        return None
    try:
        digest, payload = data[len(MAGIC):].split(b"\n", 2)[:2]
        spec = json.loads(payload)
        if (hashlib.sha256(payload).hexdigest().encode() != digest
                or spec["kind"] != "random-label" or spec["version"] not in (1, 2)
                or not 0 <= spec["exclude_lba"][0] < spec["exclude_lba"][1] <= spec["total_sectors"] <= total_sectors):
            raise ValueError()
        if spec['version'] == 1 and spec['exclude_lba'] != [START, END]:
            raise ValueError()
        if spec['version'] == 2:
            a, b = spec['exclude_lba']
            if spec['state'] == 'pending':
                if [a, b] != [PENDING_LBA, PENDING_LBA + 1] or spec['marker_lba'] != PENDING_LBA:
                    raise ValueError()
            elif spec['state'] == 'written':
                if not a <= MARKER_LBA < b or spec['marker_lba'] != MARKER_LBA:
                    raise ValueError()
            else:
                raise ValueError()
        return spec
    except (ValueError, KeyError, TypeError, IndexError):
        raise ValueError("damaged random-label metadata; do not measure this disc") from None


def exclude_ranges(ranges, span, block=16, margin=3000):
    """Half-open ranges with the band and a read/latency guard removed, aligned inward."""
    lo, hi = span[0] - margin, span[1] + margin
    out = []
    for a, b in ranges:
        for x, y in ((a, min(b, lo)), (max(a, hi), b)):
            x = math.ceil(x / block) * block
            y = y // block * block
            if y - x > 64:
                out.append((x, y))
    return out


class Label:
    def __init__(self, text, sectors, media="dvd", geometry=None):
        from PIL import Image, ImageDraw, ImageFont
        if media != "dvd":
            raise ValueError("--label currently supports DVD only")
        if not text or not text.strip() or any(ord(c) < 32 or ord(c) > 126 for c in text):
            raise ValueError("--label needs printable ASCII text")
        if sectors < MIN_SECTORS:
            raise ValueError(f"--label needs at least {MIN_SECTORS} sectors for the band and random outer guard")
        if len(text) > 180:
            raise ValueError("--label is too long (maximum 180 ASCII characters)")
        font_path = Path(__file__).with_name("web") / "fonts" / "Archivo-VF.ttf"
        font = ImageFont.truetype(str(font_path), 140)
        font.set_variation_by_name("Bold")
        box = font.getbbox(text)
        image = Image.new("1", (box[2] - box[0], box[3] - box[1]))
        ImageDraw.Draw(image).text((-box[0], -box[1]), text, font=font, fill=1)
        height = round(HEIGHT_MM / CELL_MM)
        width = round(image.width * height / image.height)
        circumference = 2 * math.pi * (INNER_MM + OUTER_MM) / 2
        if width * CELL_MM > circumference - 4:
            raise ValueError("--label text does not fit around the disc")
        self.glyphs = np.asarray(image.resize((width, height), Image.Resampling.NEAREST), bool)
        self.copies = max(1, min(4, int(circumference // (width * CELL_MM + 6))))
        self.spec = dict(kind="random-label", version=1, media=media, text=text,
                         radius_mm=[INNER_MM, OUTER_MM], exclude_lba=[START, END],
                         total_sectors=sectors, u=U, v=V, bit_nm=BIT_NM,
                         light=LIGHT, dark=DARK, height_mm=HEIGHT_MM, cell_mm=CELL_MM,
                         copies=self.copies, font="Archivo Bold", geometry="nominal")
        if geometry is not None:
            u, v, bit = geometry['u'], geometry['v'], geometry.get('bit_nm_assumed', BIT_NM)
            if not all(math.isfinite(x) and x > 0 for x in (u, v, bit)):
                raise ValueError('invalid measured DVD geometry')
            a = imagedisc.sectors_to_radius(u, v, bit, INNER_MM)
            b = imagedisc.sectors_to_radius(u, v, bit, OUTER_MM)
            if not 0 <= a <= MARKER_LBA < b <= sectors - 3016:
                raise ValueError('measured label band/marker and outer guard do not fit the capacity')
            self.spec.update(version=2, state='written', u=u, v=v, bit_nm=bit,
                             exclude_lba=[a, b], marker_lba=MARKER_LBA,
                             completion_sectors=geometry.get('completion_sectors', 0), geometry='measured')

    @property
    def span(self):
        return self.spec['exclude_lba']

    def letters(self, r, angle):
        """Bright glyph cells; angle is counter-clockwise, data-side view, y up."""
        middle = (INNER_MM + OUTER_MM) / 2
        period = 2 * math.pi / self.copies
        arc = ((math.pi / 2 - angle + period / 2) % period - period / 2) * middle
        ix = np.floor(arc / CELL_MM + self.glyphs.shape[1] / 2).astype(np.int64)
        iy = np.floor((middle + HEIGHT_MM / 2 - r) / CELL_MM).astype(np.int64)
        valid = (ix >= 0) & (ix < self.glyphs.shape[1]) & (iy >= 0) & (iy < self.glyphs.shape[0])
        return valid & self.glyphs[np.clip(iy, 0, self.glyphs.shape[0] - 1),
                                   np.clip(ix, 0, self.glyphs.shape[1] - 1)]

    def patch(self, data, first_lba):
        """Modify a generated RNG chunk without changing the RNG stream or any other sector."""
        from .calib import GROUP_BITS, GROUP_BYTES
        start, end = self.span
        u, v, bit = (self.spec[k] for k in ('u', 'v', 'bit_nm'))
        a, b = max(first_lba, start), min(first_lba + len(data), end)
        if a >= b:
            return
        lbas = np.arange(a, b)
        n = lbas[:, None] * SECTOR_BITS + GROUP_BITS[None, :]
        s = np.sqrt(u * u + v * n / math.pi)
        q = np.where(self.letters(s * bit * 1e-6, -2 * n / (s + u)),
                     int(LIGHT, 16), int(DARK, 16)).astype(np.uint8)
        raw = np.repeat(q, GROUP_BYTES, axis=1) ^ imagedisc._scramble_masks("dvd", lbas)
        data[a - first_lba:b - first_lba] = raw
        anchor = self.spec.get('marker_lba', START)
        if a <= anchor < b:
            data[anchor - first_lba] = np.frombuffer(marker(self.spec), np.uint8)

    def design(self, u=U, v=V, bit_nm=BIT_NM, size=6000, align=True):
        """Inverse-map the actual spiral into the written design; optionally undo one global rotation.

        Return glyph mask and band mask. Nominal and actual radii are coupled by
        channel-bit position, not assumed equal. Row chunks keep memory bounded.
        """
        from .calib import theta
        start, end = self.span
        wu, wv, wb = (self.spec[k] for k in ('u', 'v', 'bit_nm'))
        out, band = np.zeros((size, size), bool), np.zeros((size, size), bool)
        c = (np.arange(size) + .5) * 120 / size - 60
        nc = ((start + end) / 2) * SECTOR_BITS
        rotation = float(theta(nc, wu, wv) - theta(nc, u, v)) if align else 0
        for row in range(0, size, 100):
            x, y = c[None, :], -c[row:row + 100, None]
            r = np.hypot(x, y)
            n = np.maximum(0, math.pi * ((r / (bit_nm * 1e-6)) ** 2 - u * u) / v)
            s = np.sqrt(np.maximum(0, wu * wu + wv * n / math.pi))
            angle = np.arctan2(y, x) + theta(n, u, v) - theta(n, wu, wv) + rotation
            band[row:row + 100] = (n >= start * SECTOR_BITS) & (n < end * SECTOR_BITS)
            out[row:row + 100] = self.letters(s * wb * 1e-6, angle)
        return out, band
