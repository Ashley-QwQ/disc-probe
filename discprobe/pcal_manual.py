"""Manual alignment using the frozen reader's registration, template and votes."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from . import pcal


def _digest(data):
    return hashlib.sha256(data).hexdigest()


class Alignment:
    def __init__(self, path, record, shot, token):
        self.token = token
        self.record = record
        self.shot = shot
        self.limit_mm = 300 * pcal.CD_FRAME_MM if record["media"] == "cd" else 10.0
        self.H = np.asarray(shot["H"], dtype=float)
        self.design = pcal.design_pn(rings=record["rings_mm"]) if record.get("rings_mm") else pcal.design_burn()
        try:
            with Image.open(path) as original:
                image = np.asarray(ImageOps.exif_transpose(original).convert("RGB"))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError("could not decode the selected photo") from exc
        self.height, self.width = image.shape[:2]
        origin = self.H @ [0, 0, 1]
        point = self.H @ [40, 0, 1]
        px_per_mm = np.linalg.norm(point[:2] / point[2] - origin[:2] / origin[2]) / 40
        sigma = round(max(0.5, 0.08 * px_per_mm), 1)
        lg = np.log(cv2.GaussianBlur(image.astype(np.float32), (0, 0), sigma) + 2.0)
        self.radii, self.G, _ = pcal.prepare_polar(lg, self.H, self.design)
        self.template = pcal._template_f(self.design, self.radii)

    def overlay(self):
        bands = []
        for lo, hi in self.design.zones:
            r = (lo + hi) / 2
            # PN chip edges are quantized here to the midpoint between the two
            # reader samples that straddle the edge (within 0.05 degrees).
            chips = self.design.template([r])[0]
            edges = np.flatnonzero(chips != np.roll(chips, 1))
            angles = ((edges - 0.5) * (math.tau / len(chips))) % math.tau
            bands.append([lo, hi, angles.tolist()])
        cd = self.record["media"] == "cd"
        maximum = self.limit_mm
        step = pcal.CD_FRAME_MM / 4 if cd else 0.025
        offset = self.shot.get("L_mm", self.shot.get("L_scan_mm", 0))
        angle = self.shot.get("c_deg", math.degrees(self.shot.get("c_scan_rad", 0)))
        return dict(token=self.token, H=self.H.tolist(), width=self.width, height=self.height,
                    bands=bands, rings=[r for r, _, _ in self.design.rings],
                    L_mm=min(maximum, max(-maximum, offset)), c_deg=angle % 360,
                    ring_locked=self.shot.get("ring_locked") is True,
                    range_mm=dict(min=-maximum, max=maximum, step=step))

    def score(self, offset, angle):
        # A zero search window evaluates the exact hypothesis. SNR is against
        # each cell's off-angle correlations, using the reader's RGB magnitude.
        votes = pcal.votes(self.G, self.template, self.radii, self.design.zones,
                           math.radians(angle), offset, half_win_deg=0)
        evidence = [(sector, radius) for sector, radius, _, snr, _ in votes if snr >= pcal.CRED_SNR]
        # A concentration in one radius band or one angle is weak evidence for L.
        sectors = len({sector for sector, _ in evidence})
        radii = len({radius for _, radius in evidence})
        return dict(agreeing=len(evidence), cells=len(votes),
                    weak=not self.shot.get("ring_locked") or len(evidence) < 4 or sectors < 2 or radii < 2)


class AlignmentCache:
    """Bound memory by retaining polar samples for just the last selected photo."""
    def __init__(self):
        import threading
        self.lock = threading.Lock()
        self.current = None

    def get(self, folder, path, ident):
        summary = _digest((folder / "summary.json").read_bytes())
        record = json.loads((folder / "photo.json").read_bytes())
        if record.get("source_geo", {}).get("sha256") != summary:
            raise ValueError("the measurement changed; read the photo again")
        shot = next((p for p in record["photos"] if p.get("id") == ident), None)
        if not shot or not shot.get("H") or not shot.get("input_sha256"):
            raise ValueError("the reader has no registration for this photo")
        geometry = [record.get("media"), record.get("rings_mm"), shot["H"], shot.get("ring_locked")]
        with self.lock:
            stat = path.stat()
            key = (path, stat.st_size, stat.st_mtime_ns, summary, shot["input_sha256"], json.dumps(geometry))
            if self.current and self.current[0] == key:
                return self.current[1]
            if _digest(path.read_bytes()) != shot["input_sha256"]:
                raise ValueError("the photo changed; read it again")
            token = _digest(str(Path(folder).resolve()).encode() + repr(key).encode())
            alignment = Alignment(path, record, shot, token)
            self.current = (key, alignment)
            return alignment
