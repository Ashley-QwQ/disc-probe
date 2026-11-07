"""Simulated optical drive, to exercise the timing pipeline without hardware.

Models a spindle (CAV with slow drift, or CLV that re-locks after each seek), seek
times that are random and long, a read cache with read-ahead that may or may not
honour FUA, decode latency, host jitter and occasional large outliers. The disc
geometry is deliberately off-nominal, so the measured phases have to come from the
timing, not from the probe's nominal model.
"""

from __future__ import annotations

import math
import random
import struct

from . import mmc
from .geometry import DVD_SECTOR_MM, ONE_X_MM_S, Spiral
from .scsi import ScsiResult, Sense, check_allowed

TWO_PI = 2.0 * math.pi


class SimDrive:
    def __init__(self, mode: str = "cav", fua_honoured: bool = True, flush_honoured: bool = False, seed: int = 1,
                 jitter_us: float = 60.0, outlier_rate: float = 0.01,
                 rev_period_ms: float | None = None, clv_speed_x: float | None = None,
                 capacity: int | None = None, cache_blocks: int | None = None, reread_delay_ms: float = 0.0,
                 media="dvd", cd_u=None, cd_v=None, cd_audio: bool = False, cd_read_offset_bytes: float = 0.0,
                 patterns=()):
        self.media = media
        # A DVD reads back as random data, except (lba_start, lba_end, byte) stretches written as one
        # scrambled-domain byte, like a texture ring or a picture.
        self.patterns = tuple(patterns)
        # A CD-DA track (a DiscImageStudio picture burn): READ CD only, and reads complete at the
        # end of the sector in the audio stream, cd_read_offset_bytes earlier (the drive's offset).
        self.cd_audio = media == "cd" and cd_audio
        self.cd_read_offset_bytes = cd_read_offset_bytes
        if rev_period_ms is None:
            rev_period_ms = 20.0 if media == "cd" else 6.6
        if clv_speed_x is None:
            clv_speed_x = 16.0 if media == "cd" else 8.0
        if capacity is None:
            capacity = {"cd": 359849, "bd": 12088319}.get(media, 2295104)
        self.name = f"SIM-{mode}{'' if fua_honoured else '-nofua'}{'-flush' if flush_honoured else ''}"
        if media == "cd":
            self.name += "-cda" if self.cd_audio else "-cd"
        self.mode = mode
        self.fua_honoured = fua_honoured
        self.flush_honoured = flush_honoured
        self.rng = random.Random(seed)
        self.jitter_s = jitter_us * 1e-6
        self.outlier_rate = outlier_rate
        self.capacity = capacity
        self.block = 16
        # Off-nominal: 0.735 um pitch, 133.6 nm channel bit, start radius 23.93 mm.
        self.spiral = Spiral(23.93, 0.735e-3, DVD_SECTOR_MM * 133.6 / 133.3)
        if media == "cd":
            from . import cd
            b = cd.BIT_NM * 1e-6
            self.block = 1
            self.spiral = Spiral((cd_u if cd_u is not None else cd.R0_MM / b * 1.01) * b,
                                 (cd_v if cd_v is not None else cd.PITCH_UM * 1e-3 / b * 0.99) * b,
                                 cd.SECTOR_BITS * b)
        elif media == "bd":
            from .geometry import BD_SECTOR_MM
            # Off-nominal on purpose: 0.3185 um pitch, start radius 24.02 mm.
            self.block = 1
            self.spiral = Spiral(24.02, 0.3185e-3, BD_SECTOR_MM)
        self.clv_speed_mm_s = clv_speed_x * ONE_X_MM_S[media]
        # One read plus two blocks of read-ahead (a single segment, like the HP BU20N, which a far
        # read clears) on a CD-DA track; six blocks otherwise.
        self.cache_blocks = cache_blocks if cache_blocks is not None else (3 if self.cd_audio else 6)
        # Fixed firmware overhead before a media read can start; several revolutions on
        # the GH70N, so back-to-back re-reads all span the same whole number of turns.
        self.reread_delay_s = reread_delay_ms / 1e3
        self._cache: list[int] = []
        self._clock = 1000.0
        self._head_r = self.spiral.r0_mm
        # Spindle state: phase(t) = phi + w*(t - t_s) + 0.5*alpha*(t - t_s)^2
        self._t_s = self._clock
        self._phi = self.rng.uniform(0, TWO_PI)
        if mode == "cav":
            self._w = TWO_PI / (rev_period_ms * 1e-3)
            self._alpha = self._w * 2e-6  # about 2 ppm/s of drift
        else:
            self._w = self.clv_speed_mm_s / self._head_r
            self._alpha = 0.0

    # ------------------------------------------------------------ spindle

    def _phase(self, t: float) -> float:
        dt = t - self._t_s
        return self._phi + self._w * dt + 0.5 * self._alpha * dt * dt

    def _omega(self, t: float) -> float:
        return self._w + self._alpha * (t - self._t_s)

    def _time_to_reach(self, t: float, target_phase: float) -> float:
        """First time >= t when the unwrapped phase reaches target_phase (which is >= phase(t))."""
        for _ in range(4):
            t += (target_phase - self._phase(t)) / self._omega(t)
        return t

    def _relock(self, t: float, radius: float):
        if self.mode == "clv":
            self._phi = self._phase(t)
            self._t_s = t
            self._w = self.clv_speed_mm_s / radius

    # ------------------------------------------------------------ geometry truth

    def _end_sectors(self, end: float) -> float:
        """Where the read of the block ending at `end` (in sectors) completes on the spiral."""
        if self.cd_audio:
            return end - self.cd_read_offset_bytes / 2352
        if self.media == "cd":
            return end + 108 / 98  # independent of the ladder's read-end helper
        return end

    def block_end_angle(self, lba: int, count: int = 1) -> float:
        last_block_end = ((lba + count - 1) // self.block + 1) * self.block
        return self.spiral.angle(self._end_sectors(last_block_end)) % TWO_PI

    def true_phase_deg(self, ref_lba: int, target_lba: int) -> float:
        return math.degrees((self.block_end_angle(target_lba) - self.block_end_angle(ref_lba)) % TWO_PI)

    def idle(self, seconds: float) -> None:
        """Host-side pause between commands, on the simulated clock."""
        self._clock += seconds

    def _content(self, lba: int, count: int) -> bytes:
        from . import dvd
        out = bytearray()
        for k in range(lba, lba + count):
            byte = next((b for a, e, b in self.patterns if a <= k < e), None)
            mask = dvd.MASKS[dvd.preset_index(k)]
            if byte is None:
                out += bytes(mask[::-1] ^ (k * 2654435761 % 251))  # random to the content check, cheap
            else:
                out += bytes(mask ^ byte)
        return bytes(out)

    # ------------------------------------------------------------ SCSI

    def execute(self, cdb: bytes, data_len: int = 0, direction: int = 1, timeout_s: int = 30) -> ScsiResult:
        check_allowed(cdb)
        t_issue = self._clock + 15e-6 + self.rng.uniform(0, 10e-6)
        op = cdb[0]
        status, data, sense = 0, b"", None
        if op in (0x28, 0xA8, 0xBE):
            lba = int.from_bytes(cdb[2:6], "big")
            if self.cd_audio and op == 0xBE:
                count = int.from_bytes(cdb[6:9], "big")
            elif self.cd_audio:
                status, sense = 2, Sense(5, 0x64, 0)  # READ(10)/(12) on an audio track
                count = 0
            elif op == 0x28:
                count = int.from_bytes(cdb[7:9], "big")
            elif op == 0xA8:
                count = int.from_bytes(cdb[6:10], "big")
            else:
                status, sense = 2, Sense(5, 0x64, 0)  # illegal mode for this track
                count = 0
            fua = bool(cdb[1] & 0x08)
            if status == 0 and count == 0 and op == 0xA8:
                # Zero-length READ(12): optionally drops the cache, never touches media.
                if fua and self.flush_honoured:
                    self._cache.clear()
                self._clock = t_issue + 60e-6
                return ScsiResult(0, b"", None, int(t_issue * 1e9), int(self._clock * 1e9))
            if status == 0 and (lba + count > self.capacity or count == 0):
                status, sense = 2, Sense(5, 0x21, 0)
            if status == 0:
                t_end = self._read(t_issue, lba, count, fua)
                data = (self._content(lba, count) if self.media == "dvd" and op != 0xBE
                        else bytes((2352 if op == 0xBE else 2048) * count))[:data_len]
            else:
                t_end = t_issue + 200e-6
        else:
            t_end = t_issue + 100e-6
            if op == 0x12:
                d = bytearray(96)
                d[8:16] = b"SIMULATE"
                d[16:32] = self.name.ljust(16).encode()
                d[32:36] = b"0.01"
                data = bytes(d)
            elif op == 0x46:
                profile = {"cd": 0x08, "bd": 0x41}.get(self.media, 0x11)
                data = bytes([0, 0, 0, 4, 0, 0, 0x00, profile])
            elif op == 0xAC and (cdb[1] & 0x0F) == 0x00:
                # GET PERFORMANCE type 00h: the start and end read rate. Under CLV they are equal;
                # under CAV their ratio is the radius ratio of the range.
                def kbps(lba: int) -> int:
                    r = self.spiral.radius(max(0.0, float(lba)))
                    v = self.clv_speed_mm_s if self.mode == "clv" else self._w * r
                    return int(round(v / self.spiral.sector_mm * 2048 / 1000))
                body = struct.pack(">IIII", 0, kbps(0), self.capacity - 1, kbps(self.capacity - 1))
                data = struct.pack(">I", 20) + bytes(4) + body
            elif op == 0x25:
                data = (self.capacity - 1).to_bytes(4, "big") + (2048).to_bytes(4, "big")
            elif op == 0x43 and (cdb[2] & 0x0F) == 0:
                adr_ctl = 0x10 if self.cd_audio else 0x14  # control bit 2 set: data track
                data = bytes([0, 18, 1, 1, 0, adr_ctl, 1, 0, 0, 0, 0, 0,
                              0, adr_ctl, 0xAA, 0, *self.capacity.to_bytes(4, "big")])
            elif op in (0x00, 0xBB):
                pass
            else:
                status, sense = 2, Sense(5, 0x24, 0)
        self._clock = t_end
        return ScsiResult(status, data[:data_len], sense, int(t_issue * 1e9), int(t_end * 1e9))

    def _read(self, t: float, lba: int, count: int, fua: bool) -> float:
        first_block = lba // self.block
        last_block = (lba + count - 1) // self.block
        blocks = list(range(first_block, last_block + 1))
        bypass = fua and self.fua_honoured
        if not bypass and all(b in self._cache for b in blocks):
            return t + 80e-6 + 1e-6 * count * 2 + abs(self.rng.gauss(0, 10e-6))

        start = first_block * self.block
        end = (last_block + 1) * self.block
        r_target = self.spiral.radius(start)
        dr = abs(r_target - self._head_r)
        if dr < 2 * self.spiral.pitch_mm:
            seek = 0.15e-3
        else:
            seek = (0.8e-3 + 70e-3 * math.sqrt(dr / 34.0)) * max(0.5, 1 + 0.1 * self.rng.gauss(0, 1))
        t_arrive = t + seek + 0.1e-3 + self.reread_delay_s
        self._relock(t_arrive, r_target)

        # The head sits at a fixed lab angle; disc angle theta is under it when the
        # unwrapped spindle phase equals theta modulo 2*pi.
        theta_start = self.spiral.angle(start)
        theta_end = self.spiral.angle(self._end_sectors(end))
        phase_now = self._phase(t_arrive)
        wait = (theta_start - phase_now) % TWO_PI
        t_start_pass = self._time_to_reach(t_arrive, phase_now + wait)
        t_end_pass = self._time_to_reach(t_start_pass, self._phase(t_start_pass) + (theta_end - theta_start))
        self._head_r = self.spiral.radius(end)

        self._cache = [b for b in self._cache if b not in blocks] + blocks + [last_block + 1, last_block + 2]
        self._cache = self._cache[-self.cache_blocks:]

        done = t_end_pass + 0.25e-3 + self.rng.gauss(0, self.jitter_s)
        if self.rng.random() < self.outlier_rate:
            done += self.rng.uniform(0.3e-3, 3e-3)
        return max(done, t_end_pass)
