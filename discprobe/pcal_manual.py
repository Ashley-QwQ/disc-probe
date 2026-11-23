"""Manual alignment using the frozen reader's registration, template and votes."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from . import pcal, pcal_assist


def _digest(data):
    return hashlib.sha256(data).hexdigest()


class Alignment:
    def __init__(self, path, record, shot, token):
        self.token = token
        self.record = record
        self.shot = shot
        self.limit_mm = 300 * pcal.CD_FRAME_MM if record["media"] == "cd" else 10.0
        # The reader's registration, when it found the disc; a person can replace it by clicking (register).
        self.reader_H = np.asarray(shot["H"], dtype=float) if shot.get("H") else None
        self.design = pcal.design_pn(rings=record["rings_mm"]) if record.get("rings_mm") else pcal.design_burn()
        try:
            with Image.open(path) as original:
                self.rgb = np.asarray(ImageOps.exif_transpose(original).convert("RGB"))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError("could not decode the selected photo") from exc
        self.height, self.width = self.rgb.shape[:2]
        self.reset()

    # ---- the hand-guided reading: registration -> candidates -> seeded read (pcal_assist; frozen pcal only)
    def reset(self):
        self.H = self.reader_H
        self.source = "reader"
        self.ring = dict(ring_rms_mm=self.shot.get("ring_rms_mm"), ring_frac=self.shot.get("ring_frac"),
                         ring_locked=self.shot.get("ring_locked") is True)
        self._polar = None
        self.cands = None
        self.last = None
        return self.lines()

    def _need_h(self):
        if self.H is None:
            raise ValueError("mark the disc first: click the outermost ring and the centre")

    def _polar_samples(self):
        self._need_h()
        if self._polar is None:
            self._polar = pcal_assist.polar(self.rgb, self.H, self.design)
        return self._polar

    def lines(self):
        """The registration the reading would use, as image polylines: the rim and the burned rings."""
        base = dict(token=self.token, width=self.width, height=self.height, source=self.source,
                    registered=self.H is not None, **self.ring)
        if self.H is None:
            return base
        drawn = pcal_assist.overlay_lines(self.H, self.design)
        return dict(base, rim=drawn["rim"], rings=drawn["rings"], H=self.H.tolist())

    def register(self, clicks, hub):
        out = pcal_assist.register(self.rgb, clicks, hub, self.design)
        self.H, self.source, self._polar, self.cands, self.last = out["H"], "clicks", None, None, None
        self.ring = dict(ring_rms_mm=out["ring_rms_mm"], ring_frac=out["ring_frac"], ring_locked=out["ring_locked"])
        return dict(self.lines(), clicked=out["clicked_points"])

    def candidates(self):
        radii, G, good, T = self._polar_samples()
        self.cands = pcal_assist.candidates(G, good, T, radii)
        self.last = None
        return [dict(c, arrow=pcal_assist.arrow_outline(self.H, c["L_scan_mm"], c["c_scan_rad"])) for c in self.cands]

    def read(self, index):
        if not self.cands or not 0 <= index < len(self.cands):
            raise ValueError("find the candidates first")
        c = self.cands[index]
        radii, G, good, T = self._polar_samples()
        res = pcal_assist.seeded_read(G, T, radii, self.design.zones, c["L_scan_mm"], c["c_scan_rad"],
                                      peak_z=c["peak_z"], runner_up_ratio=c["runner_up_ratio"],
                                      ring_locked=self.ring["ring_locked"], design_name=self.design.name)
        cells = pcal_assist.vote_cells(self.H, res.get("votes") or [], self.design.zones, res.get("vote_nsec", 12))
        # Counts only as the reader would count it: its verdict 'ok', and a clicked registration must lock the rings.
        trusted = res.get("status") == "ok" and (self.source == "reader" or bool(self.ring["ring_locked"]))
        self.last = dict(res, index=index, trusted=trusted)
        keep = ("status", "L_mm", "c_deg", "n_votes", "n_inliers", "rms_deg", "sigma_L_jack_mm", "zone_spread_mm",
                "max_gap_deg", "r_span_mm", "peak_z")
        frames = res["L_mm"] / pcal.CD_FRAME_MM if res.get("L_mm") is not None and self.record["media"] == "cd" else None
        return dict({k: res.get(k) for k in keep}, cells=cells, frames=frames, trusted=trusted,
                    registration=self.source, **self.ring)

    @property
    def radii(self):
        return self._polar_samples()[0]

    @property
    def G(self):
        return self._polar_samples()[1]

    @property
    def template(self):
        return self._polar_samples()[3]

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
        # Where the reader found the pattern on this photo: its stored votes, one per (sector, zone) cell,
        # as [sector centre angle, zone inner, zone outer, snr] in the disc plane, for drawing on the photo.
        zones = [tuple(z) for z in self.design.zones]
        evidence = []
        for vote in self.shot.get("votes") or []:
            sector, radius, snr = float(vote[0]), float(vote[1]), float(vote[3])
            lo, hi = min(zones, key=lambda z: abs((z[0] + z[1]) / 2 - radius))
            evidence.append([sector, lo, hi, snr])
        nsec = int(self.shot.get("vote_nsec") or 12)
        return dict(token=self.token, H=None if self.H is None else self.H.tolist(), width=self.width, height=self.height,
                    evidence=evidence, evidence_half_span=math.pi / nsec,
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
        if not shot or not shot.get("input_sha256"):
            raise ValueError("this photo has not been read yet")
        geometry = [record.get("media"), record.get("rings_mm"), shot.get("H"), shot.get("ring_locked")]
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
