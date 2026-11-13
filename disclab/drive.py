"""The virtual drive (reads, timing, MMC replies) and the virtual recorder (burn) for one lab drive.

LabDrive extends discprobe.sim.SimDrive: the spindle, seek, cache and FUA model are SimDrive's; the spiral,
the timing angle, the capacity, the replies that identify drive and disc, the user data and the failures come
from the lab's truth and burn records. It goes through the same check_allowed() as every device.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import struct
import time

import numpy as np

from discprobe.geometry import Spiral
from discprobe.scsi import ScsiResult, Sense, check_allowed
from discprobe.sim import SimDrive

from .box import MEDIA
from .lab import Lab
from .physics import Disc

FAMILY_PROFILE = {"dvd": 0x10, "cd": 0x08, "bd": 0x40}
BLANK = 0


class NoDisc(Exception):
    pass


def _burn_mode(burn: dict | None) -> str | None:
    if not burn:
        return None
    return (burn.get("sessions") or [{}])[0].get("mode")


class LabDrive(SimDrive):
    def __init__(self, lab: Lab, name: str):
        self.lab = lab
        self.drive_name, dstate = lab.drive_for(name)
        answers = lab.answers()
        self.reader_id = dstate["reader"]
        self.reader = answers["readers"][self.reader_id]
        with lab.locked_state() as state:
            d = state["drives"][self.drive_name]
            d["opens"] = d.get("opens", 0) + 1
            opens = d["opens"]
            disc_id = None if d.get("open") else d.get("tray")
            burn = state.get("burns", {}).get(disc_id) if disc_id else None
        self.disc_id = disc_id
        self.burn = burn
        self.truth = answers["discs"][disc_id] if disc_id else None
        family = self.truth["family"] if self.truth else "dvd"
        self.family = family
        mspec = MEDIA[self.truth["media"]] if self.truth else MEDIA["dvd-r"]
        seed = int(hashlib.sha256(f"{answers['seed']}|{self.drive_name}|{opens}".encode()).hexdigest()[:8], 16)
        written = self._written_sectors()
        super().__init__(
            mode=self.reader["mode"], fua_honoured=self.reader["fua_honoured"],
            flush_honoured=self.reader["flush_honoured"], seed=seed, jitter_us=self.reader["jitter_us"],
            outlier_rate=self.reader["outlier_rate"], rev_period_ms=self.reader["rev_period_ms"][family],
            clv_speed_x=self.reader.get("clv_speed_x"), capacity=max(written, 1),
            cache_blocks=self.reader["cache_blocks"], reread_delay_ms=self.reader["reread_delay_ms"],
            media=family)
        self.name = self.drive_name
        self.profile = mspec["profile"]
        self.mid = mspec["mid"]
        self.disc = Disc(self.truth, burn) if self.truth else None
        if self.disc is not None:
            b = self.disc.b_mm
            self.spiral = Spiral(self.disc.u * b, self.disc.v * b, self.disc.bps * b)
            self._head_r = self.spiral.r0_mm
            if self.mode == "clv":
                self._w = self.clv_speed_mm_s / self._head_r
            key = family if family != "cd" else f"cd:{_burn_mode(burn) or 'mode2form1'}"
            self.d_bits = float(self.reader["completion_mm"].get(key, 0.0)) / b
            self.head_mm = float(self.reader["head_mm"])
        self._iso = []                 # (start, end, memmap)
        self._flaw_cache = {}
        self.closed = False

    # ------------------------------------------------------------ state
    def _written_sectors(self) -> int:
        if not self.burn:
            return 0
        return max(s["start_lba"] + s["sectors"] for s in self.burn["sessions"])

    def _sessions(self):
        if not self._iso and self.burn:
            for s in self.burn["sessions"]:
                path = Path(s["iso"])
                ok = path.is_file() and path.stat().st_size == s["sectors"] * 2048 and \
                    abs(path.stat().st_mtime - s.get("iso_mtime", path.stat().st_mtime)) < 2
                mm = np.memmap(path, np.uint8, "r") if ok else None
                if mm is None and s.get("head") and Path(s["head"]).is_file():
                    # The ISO was deleted to save space: the first sectors were kept at burn time.
                    head = np.fromfile(s["head"], np.uint8)
                    self._iso.append((s["start_lba"], s["start_lba"] + len(head) // 2048, head, s))
                    self._iso.append((s["start_lba"] + len(head) // 2048, s["start_lba"] + s["sectors"], None, s))
                    continue
                self._iso.append((s["start_lba"], s["start_lba"] + s["sectors"], mm, s))
        return self._iso

    # ------------------------------------------------------------ truth hooks for SimDrive
    def track_angle(self, sector: float) -> float:
        if self.disc is None:
            return super().track_angle(sector)
        return float(self.disc.timing_theta(sector * self.disc.bps, self.d_bits, self.head_mm))

    def _content(self, lba: int, count: int) -> bytes:
        out = bytearray()
        for k in range(lba, lba + count):
            for a, e, mm, s in self._sessions():
                if a <= k < e:
                    if mm is None:
                        raise OSError(f"disclab: the image burned on {self.disc_id} is gone or changed ({s['iso']})")
                    out += mm[(k - a) * 2048:(k - a + 1) * 2048].tobytes()
                    break
            else:
                out += bytes(2048)
        return bytes(out)

    def _unreadable(self, lba: int, count: int) -> bool:
        """A flaw arc, or a textured sector written too slowly (outer part of a low-speed texture burn)."""
        if self.disc is None:
            return False
        flaw = self.truth.get("flaw")
        for k in range(lba, lba + count, max(1, count // 4)):
            n = (k + 0.5) * self.disc.bps
            r = float(self.disc.data_radius(n))
            if flaw and flaw["r_mm"][0] <= r <= flaw["r_mm"][1]:
                a = math.degrees(float(self.disc.alpha(n))) % 360
                lo, hi = flaw["deg"][0] % 360, flaw["deg"][1] % 360
                if (lo <= a <= hi) if lo <= hi else (a >= lo or a <= hi):
                    return True
            for a_, e_, mm, s in self._sessions():
                if a_ <= k < e_ and s.get("low_speed_fail_mm") and r > s["low_speed_fail_mm"] and mm is not None:
                    q = mm[(k - a_) * 2048:(k - a_) * 2048 + 256]
                    if len(np.unique(q)) <= 8:       # a texture, not random data
                        return True
        return False

    # ------------------------------------------------------------ SCSI
    def execute(self, cdb: bytes, data_len: int = 0, direction: int = 1, timeout_s: int = 30) -> ScsiResult:
        check_allowed(cdb)
        op = cdb[0]
        t0 = self._clock + 20e-6

        def reply(status=0, data=b"", sense=None, dt=100e-6):
            self._clock = t0 + dt
            return ScsiResult(status, bytes(data)[:data_len], sense, int(t0 * 1e9), int(self._clock * 1e9))

        if op == 0x12:
            d = bytearray(96)
            d[0] = 0x05
            d[8:16] = self.reader["vendor"].ljust(8)[:8].encode()
            d[16:32] = self.reader["product"].ljust(16)[:16].encode()
            d[32:36] = self.reader["revision"].ljust(4)[:4].encode()
            return reply(data=d)
        if self.disc is None:
            if op == 0x46:
                return reply(data=self._configuration(None))
            return reply(2, sense=Sense(2, 0x3A, 0x02 if self._tray_open() else 0x00), dt=300e-6)
        written = self._written_sectors()
        if op == 0x46:
            return reply(data=self._configuration(self.profile))
        if op == 0x25:
            if not written:
                return reply(2, sense=Sense(5, 0x24, 0))
            return reply(data=(written - 1).to_bytes(4, "big") + (2048).to_bytes(4, "big"))
        if op == 0x51:
            return reply(data=self._disc_information(written))
        if op == 0x52:
            return reply(data=self._track_information(written))
        if op == 0xAD:
            return self._disc_structure(cdb, reply)
        if op == 0x43 and (cdb[2] & 0x0F) == 4 and self.family == "cd":
            return reply(data=self._atip())
        if op == 0x43 and not written:
            return reply(2, sense=Sense(5, 0x24, 0))
        if op in (0x28, 0xA8):
            lba = int.from_bytes(cdb[2:6], "big")
            count = int.from_bytes(cdb[7:9], "big") if op == 0x28 else int.from_bytes(cdb[6:10], "big")
            if count and (lba + count > written):
                return reply(2, sense=Sense(5, 0x21, 0), dt=2e-3)
            if count and self._unreadable(lba, count):
                self._clock = self._read(t0, lba, count, True) + 1.6   # the head goes there, then firmware retries
                return ScsiResult(2, b"", Sense(3, 0x11, 0x00), int(t0 * 1e9), int(self._clock * 1e9))
        if op == 0xAC and (cdb[1] & 0x0F) == 0x00 and not written:
            return reply(2, sense=Sense(5, 0x24, 0))
        if op == 0x5A:
            return reply(data=self._mode_page_2a())
        res = super().execute(cdb, data_len, direction, timeout_s)
        if op in (0x28, 0xA8) and res.status == 0 and self.family != "dvd":
            # SimDrive returns real content only for DVD; a lab disc returns what was burned.
            lba = int.from_bytes(cdb[2:6], "big")
            count = int.from_bytes(cdb[7:9], "big") if op == 0x28 else int.from_bytes(cdb[6:10], "big")
            res = ScsiResult(0, self._content(lba, count)[:data_len], None, res.t_start_ns, res.t_end_ns)
        return res

    def _tray_open(self):
        st = self.lab.state()["drives"].get(self.drive_name, {})
        return bool(st.get("open"))

    # ------------------------------------------------------------ MMC replies
    def _configuration(self, profile):
        profiles = sorted({0x08, 0x09, 0x0A, 0x10, 0x11, 0x13, 0x14, 0x1A, 0x1B, 0x40, 0x41, 0x43})
        body = b"".join(struct.pack(">HBB", p, 1 if p == profile else 0, 0) for p in profiles)
        feat0 = struct.pack(">HBB", 0x0000, 0x03, len(body)) + body
        feat1 = struct.pack(">HBB", 0x0001, 0x0B, 4) + struct.pack(">I", 2)      # core: ATAPI
        feat2 = struct.pack(">HBB", 0x0107, 0x01 if profile else 0x00, 4) + bytes(4)  # real time streaming
        payload = feat0 + feat1 + feat2
        return struct.pack(">IHH", len(payload) + 4, 0, profile or 0) + payload

    def _disc_information(self, written):
        d = bytearray(34)
        d[0:2] = (32).to_bytes(2, "big")
        closed = bool(self.burn and self.burn.get("closed", True))
        status = 0 if not written else (2 if closed else 1)
        last_state = 0 if not written else (3 if closed else 0)
        d[2] = (last_state << 2) | status
        d[3] = 1
        sessions = len(self.burn["sessions"]) if self.burn else 1
        d[4] = sessions
        d[5] = sessions
        d[6] = sessions + (0 if closed or not written else 1)
        d[7] = 0x20
        d[8] = 0x00 if self.family != "cd" else 0x20
        cap = self.truth["capacity"]
        if self.family == "cd":
            f = cap + 150
            d[21:24] = bytes([f // 4500, (f // 75) % 60, f % 75])
        else:
            d[20:24] = cap.to_bytes(4, "big")
        return bytes(d)

    def _track_information(self, written):
        d = bytearray(48)
        d[0:2] = (46).to_bytes(2, "big")
        cap = self.truth["capacity"]
        closed = bool(self.burn and self.burn.get("closed", True))
        d[2], d[3] = 1, 1
        d[5] = 0x04 if self.family != "cd" else 0x04
        blank = not written
        d[6] = (0x40 if blank else 0) | 0x01
        nwa = 0 if blank else (None if closed else written)
        d[7] = 0x01 if nwa is not None else 0x00
        if written:
            d[7] |= 0x02
        d[8:12] = (0).to_bytes(4, "big")
        d[12:16] = (nwa or 0).to_bytes(4, "big")
        free = cap - (written if nwa is not None else cap) if not blank else cap
        d[16:20] = max(free, 0).to_bytes(4, "big")
        d[20:24] = (16 if self.family == "dvd" else 32 if self.family == "bd" else 1).to_bytes(4, "big")
        d[24:28] = (written if written else cap).to_bytes(4, "big")
        d[28:32] = (max(written - 1, 0)).to_bytes(4, "big")
        return bytes(d)

    def _disc_structure(self, cdb, reply):
        media_type, fmt = cdb[1] & 0x0F, cdb[7]
        if self.family == "dvd" and media_type == 0:
            if fmt == 0x0E and self.profile in (0x11, 0x13, 0x14):
                d = bytearray(4 + 2048)
                d[0:2] = (2050).to_bytes(2, "big")
                d[4] = 1
                d[7:10] = (0x30000 + self.truth["capacity"] - 1).to_bytes(3, "big")[-3:]
                mid = self.mid.ljust(12)[:12].encode()
                d[20], d[28] = 3, 4
                d[21:27], d[29:35] = mid[:6], mid[6:12]
                return reply(data=d)
            if fmt == 0x11 and self.profile in (0x1A, 0x1B):
                d = bytearray(4 + 2048)
                d[0:2] = (2050).to_bytes(2, "big")
                maker, kind, rev = (self.mid.split("/") + ["", "", "1"])[:3]
                d[4 + 19:4 + 27] = maker.ljust(8)[:8].encode()
                d[4 + 27:4 + 30] = kind.ljust(3)[:3].encode()
                d[4 + 30] = int(rev or 1) & 0xFF
                return reply(data=d)
            if fmt in (0x00, 0x10) and self._written_sectors():
                d = bytearray(4 + 2048)
                d[0:2] = (2050).to_bytes(2, "big")
                d[4] = 0x20 if self.profile == 0x11 else 0xA1       # book type / version
                d[5] = 0x0F                                          # 120 mm, max rate
                d[6] = 0x02                                          # single layer, recordable
                d[7] = 0x00
                d[8:12] = (0x30000).to_bytes(4, "big")
                d[12:16] = (0x30000 + self.truth["capacity"] - 1).to_bytes(4, "big")
                return reply(data=d)
        if self.family == "bd" and media_type == 1 and fmt == 0:
            d = bytearray(4 + 4096)
            d[0:2] = (4098).to_bytes(2, "big")
            d[4:6] = b"DI"
            d[4 + 100:4 + 100 + len(self.mid)] = self.mid.encode()
            return reply(data=d)
        return reply(2, sense=Sense(5, 0x30, 0x02 if self.family == "dvd" else 0x05))

    def _atip(self):
        d = bytearray(4 + 24)
        d[0:2] = (26).to_bytes(2, "big")
        a = d[4:]
        a[0] = 0x45
        a[1] = 0x00
        a[2] = 0x80
        a[4:7] = bytes([97, 26, 66])
        cap = self.truth["capacity"] + 150
        a[8:11] = bytes([cap // 4500, (cap // 75) % 60, cap % 75])
        d[4:] = a
        return bytes(d)

    def _mode_page_2a(self):
        page = bytearray(30)
        page[0], page[1] = 0x2A, 28
        page[2] = 0x3F
        page[3] = 0x37
        speeds = self.reader["write_speeds_x"].get(self.family, [8])
        one_x = {"dvd": 1385, "cd": 176, "bd": 4495}[self.family]
        page[8:10] = int(max(speeds) * one_x * 2).to_bytes(2, "big")
        page[18:20] = int(max(speeds) * one_x).to_bytes(2, "big")
        header = bytearray(8)
        header[0:2] = (len(page) + 6).to_bytes(2, "big")
        return bytes(header + page)

    # ------------------------------------------------------------ device protocol
    def close(self):
        for _, _, mm, _ in self._iso:
            if mm is not None:
                del mm
        self._iso = []
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def idle(self, seconds: float) -> None:
        self._clock += seconds


class LabRecorder:
    """burner.adapter() for a lab drive: inspect the disc in the tray, then 'write' an image onto it."""

    def __init__(self, lab: Lab, drive: str, media: str):
        self.lab, self.media = lab, media
        self.drive, _ = lab.drive_for(drive)

    def _tray(self):
        st = self.lab.state()
        d = st["drives"][self.drive]
        disc = None if d.get("open") else d.get("tray")
        return st, d, disc

    def inspect(self):
        st, d, disc = self._tray()
        if not disc:
            return dict(media="unknown", blank=False, free_sectors=0, speeds_x=[])
        truth = self.lab.answers()["discs"][disc]
        burn = st.get("burns", {}).get(disc)
        reader = self.lab.answers()["readers"][d["reader"]]
        family = truth["family"]
        media = family if family == self.media else ("unknown" if family not in ("dvd", "cd") else family)
        if burn:
            written = max(s["start_lba"] + s["sectors"] for s in burn["sessions"])
            free = 0 if burn.get("closed", True) else truth["capacity"] - written
            blank = False
        else:
            # IMAPI burned 359600 sectors on an 80-minute CD-R (ATIP 359849) and refused 359800 (KNOWLEDGE, 2026-11-04).
            free, blank = truth["capacity"] - (249 if family == "cd" else 0), True
        return dict(media=media, blank=blank, free_sectors=free,
                    speeds_x=sorted(float(x) for x in reader["write_speeds_x"].get(family, [8])))

    def write(self, image, speed, cancel, progress, *, keep_open=False, append=False, expect_start=None):
        from .burnmap import extract_map
        path = Path(getattr(image, "path", image))
        if not isinstance(image, (str, os.PathLike)):
            raise OSError("disclab: patched (disc-id) images are not supported by the lab recorder yet")
        st, d, disc = self._tray()
        if not disc:
            raise OSError("disclab: no disc in the lab drive")
        answers = self.lab.answers()
        truth = answers["discs"][disc]
        writer = answers["writers"]["imapi"]
        size = path.stat().st_size
        sectors = size // 2048
        rng = np.random.default_rng(int(time.time() * 1e6) % (2 ** 32))
        start = expect_start or 0
        total = 20
        for i in range(total):                                # a lab burn takes a few seconds, with progress
            if cancel.is_set():
                raise OSError("disclab: burn cancelled")
            progress(stage="write", fraction=(i + 1) / total)
            time.sleep(0.05)
        progress(stage="speed", actual_speed_x=float(speed))
        mode = "dvd" if truth["family"] == "dvd" else "mode2form1"
        session = dict(iso=str(path), iso_size=size, iso_mtime=path.stat().st_mtime, start_lba=start, sectors=sectors,
                       speed_x=float(speed), writer="imapi", mode=mode, drive=self.drive,
                       write_offset_bits=float(writer["write_offset_bits"] + rng.normal(0, writer["jitter_bits"])),
                       low_speed_fail_mm=writer["low_speed_fail_mm"] if float(speed) <= writer["low_speed_x"] else None,
                       when=time.time())
        head = self.lab.root / "media" / (disc.replace(" ", "_") + f".s{expect_start or 0}.head.bin")
        head.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as src:
            head.write_bytes(src.read(1024 * 2048))
        session["head"] = str(head)
        with self.lab.locked_state() as state:
            burns = state.setdefault("burns", {})
            prev = burns.get(disc)
            if prev and prev.get("closed", True):
                raise OSError("disclab: the disc is already closed")
            if prev:
                session["write_offset_bits"] = prev["sessions"][0]["write_offset_bits"]
                prev["sessions"].append(session)
                prev["closed"] = not keep_open
            else:
                burns[disc] = dict(sessions=[session], closed=not keep_open)
            self.lab.event(state, "burn", disc=disc, drive=self.drive, iso=str(path), sectors=sectors, speed_x=speed)
        # Keep what was written, independent of the ISO file (which may be deleted to save space).
        if truth["family"] == "dvd":
            extract_map(self.lab, disc)
        return float(speed)
