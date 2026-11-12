"""`timing`: cache/FUA test, CAV/CLV check, and sector phase measurement.

Experiments, in order:
  1. cache  - repeated reads of one sector: plain, with FUA, and after a zero-length
              READ(12)+FUA at the same LBA (redumper's cache flush). A median command
              time under CACHE_HIT_US means the drive answered from its buffer.
  2. period - repeated reads of one sector at inner, middle and outer zones give the
              revolution period there. Equal periods mean CAV; periods growing with
              radius mean CLV, and then the phase method below is not valid.
  3. phase  - alternate a reference sector R and a target X. Under CAV the spindle
              phase advances at a fixed rate whatever the head does, so the phase of
              X's completion relative to R's is the angle between the two sectors on
              the disc (plus a constant decode latency), independent of seek times.
"""

from __future__ import annotations

import gc
import math
import random
import statistics
import time
from dataclasses import asdict, dataclass

from . import analysis, mmc
from .geometry import NOMINAL
from .scsi import DATA_IN, DATA_NONE

# Re-reading one sector from the media waits for most of a revolution (over 4 ms even
# at 10000 rpm); the GH70N answers cache hits in about 1.1 ms over SATA, so 1 ms was
# too tight.
CACHE_HIT_US = 3000.0
CACHE_RATIO = 3.0
EVICT_REGION_SECTORS = 32768
FAR_STEP_SECTORS = 5000
FAR_COUNTS = (1, 2, 4)      # far reads tried before each timed read on a CD-DA track
ZONES = (0.05, 0.5, 0.95)
MULTIPLE_TOLERANCE = 3e-3    # a zone period this close to k times another is k turns per completion
DEFAULT_TARGETS = (0.15, 0.35, 0.55, 0.75, 0.95)


@dataclass
class Event:
    experiment: str
    label: str
    lba: int
    command: str
    fua: bool
    t_start_ns: int
    t_end_ns: int
    duration_us: float
    status: int
    sense: str


# Medium errors in a row before giving up. A failing read can take the drive several seconds
# of retries (7.5 s each on a GP65NB60), so running every experiment anyway takes over an hour.
MAX_MEDIUM_ERRORS = 8
# "Becoming ready" in a row before giving up, seconds of it. Once or twice could pass by itself, but a disc going
# back in takes many seconds, and whatever comes after may not be the disc that was being measured.
MAX_LOADING_READS = 100
UNREADABLE_DISC = ("reads keep failing with medium errors ({sense}): the drive cannot read this disc reliably. "
                   "Picture, calibration and texture discs often behave like this. Timing needs plain data: "
                   "burn a random-data disc from the same batch (python -m discprobe random) and measure that.")


class NoReadableDisc(RuntimeError):
    pass


def duration_stats(results) -> dict:
    d = sorted(r.duration_us for r in results)
    if not d:
        return {"n": 0}

    def pct(p):
        return round(d[min(len(d) - 1, int(p * (len(d) - 1) + 0.5))], 1)
    return {"n": len(d), "p50_us": pct(0.5), "p95_us": pct(0.95), "p99_us": pct(0.99),
            "min_us": round(d[0], 1), "max_us": round(d[-1], 1),
            "failed": sum(1 for r in results if not r.ok)}


class TimingProbe:
    def __init__(self, dev, log=print, read_method: str = "auto", reps: int = 40,
                 period_reads: int = 60, targets=DEFAULT_TARGETS, ref_fraction: float = 0.05,
                 speed_kbs: int | None = None, pure_cav: bool = False, evict_sectors: int = 1024,
                 sectors: int = 1, host_delay_ms: float = 25.0, seed: int = 1, media="dvd",
                 stop_if_not_cav: bool = False, time_limit_s: float | None = None, cd_audio: bool = False):
        self.media = media
        # With media "cd", also accept a CD-DA track (a DiscImageStudio picture burn) and read it
        # with READ CD. Only geo uses this; it times audio sectors against their own origin.
        self.cd_audio = cd_audio
        self.audio = False
        self.stop_if_not_cav = stop_if_not_cav
        self._deadline = time.monotonic() + time_limit_s if time_limit_s else None
        self._time_limit_s = time_limit_s
        self._medium_errors = 0
        self._loading_reads = 0
        self.dev = dev
        self.host_delay_s = host_delay_ms / 1e3
        self._rng = random.Random(seed)
        self.sectors = sectors
        self.log = log
        self.read_method = read_method
        self.reps = reps
        self.period_reads = period_reads
        self.targets = tuple(targets)
        self.ref_fraction = ref_fraction
        self.speed_kbs = speed_kbs
        self.pure_cav = pure_cav
        self.evict_sectors = evict_sectors
        self.events: list[Event] = []
        self.summary: dict = {}
        self._experiment = ""
        self._evict_cursor = 0
        self.far_count = 1
        # Reads faster than this are taken as cache hits when the cache is defeated indirectly.
        # Raised by the cache test when a slow link makes cache hits slower (see cache_test).
        self.cache_hit_us = CACHE_HIT_US

    # ------------------------------------------------------------ plumbing

    def _cmd(self, cdb: bytes, alloc: int):
        return self.dev.execute(cdb, alloc, DATA_IN if alloc else DATA_NONE)

    def _read(self, lba: int, count: int = 1, fua: bool = False, label: str = ""):
        if self.method == "readcd":
            cdb, size = mmc.read_cd(lba, count), 2352 * count
        elif self.method == "read10":
            cdb, size = mmc.read10(lba, count, fua), 2048 * count
        else:
            cdb, size = mmc.read12(lba, count, fua), 2048 * count
        res = self._cmd(cdb, size)
        self._record(label, lba, self.method, fua, res)
        self._watch(res)
        return res

    def _watch(self, res):
        """Stop early when the disc has gone, reads keep failing or the run overstays its time limit.

        Without the first of these, every read left fails in a few ms and the run ends looking like a noisy drive.
        """
        if res.ok:
            self._medium_errors = self._loading_reads = 0
        else:
            gone = mmc.disc_gone(res.sense)
            if gone:
                raise NoReadableDisc(gone)
            if mmc.not_ready(res.sense):
                self._loading_reads += 1
                if self._loading_reads >= MAX_LOADING_READS:
                    raise NoReadableDisc(mmc.LOADING)
            elif res.sense is not None and res.sense.key == 3:
                self._medium_errors += 1
                if self._medium_errors >= MAX_MEDIUM_ERRORS:
                    raise NoReadableDisc(UNREADABLE_DISC.format(sense=res.sense))
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise NoReadableDisc(f"stopped after the {self._time_limit_s / 60:.0f} minute time limit "
                                 "(--max-minutes); reads are far slower than expected")

    def _record(self, label, lba, command, fua, res):
        self.events.append(Event(self._experiment, label, lba, command, fua, res.t_start_ns,
                                 res.t_end_ns, round(res.duration_us, 2), res.status, str(res.sense or "")))

    def _flush(self, lba: int):
        # Zero-length READ(12) with FUA, as redumper does before re-reading a sector;
        # whether a given firmware drops its cached copy is what the cache test checks.
        res = self._cmd(mmc.read12(lba, 0, fua=True), 0)
        self._record("flush", lba, "read12-0-fua", True, res)
        return res

    def _align(self, fraction: float) -> int:
        lba = int(self.last_lba * fraction)
        lba -= lba % self.block
        lba = max(0, min(lba, self.last_lba - self.block + 1))
        spec = self.summary.get("random_label")
        if spec:
            from .randomlabel import exclude_ranges
            safe = exclude_ranges([(0, self.last_lba + 1)], spec["exclude_lba"], self.block,
                                  max(3000, self.sectors + self.block))
            for span in spec.get('avoid_lba', []):
                safe = exclude_ranges(safe, span, self.block, max(3000, self.sectors + self.block))
            candidates = [max(a, min(lba, b - max(self.block, self.sectors))) for a, b in safe
                          if b - a >= max(self.block, self.sectors)]
            if not candidates:
                raise NoReadableDisc("no random data remains outside the label")
            lba = min(candidates, key=lambda x: abs(x - lba)) // self.block * self.block
        return lba

    def _far_lba(self, lba: int, i: int = 0) -> int:
        """The i-th far sector: a third of the disc away on the side with room, then 5000 sectors
        further apart for each next one, so each lands in a different cache segment."""
        third = self.last_lba // 3 + FAR_STEP_SECTORS * i
        return lba + third if lba < self.last_lba // 2 else lba - third

    def _far_reads(self, lba: int, k: int):
        for i in range(k):
            self._read(self._far_lba(lba, i), 1, label="far")

    def _evict(self):
        chunk = 32 if self.method != "readcd" else 27
        start = self._align(0.6)
        done = 0
        while done < self.evict_sectors:
            lba = start + self._evict_cursor
            self._read(lba, chunk, label="evict")
            self._evict_cursor = (self._evict_cursor + chunk) % EVICT_REGION_SECTORS
            done += chunk

    def _pause(self):
        # A random idle time before each timed read. Without it, back-to-back re-reads of
        # one sector all take the same whole number of revolutions, and the completion
        # times only reveal that multiple, never the revolution itself (seen on the GH70N:
        # every FUA re-read took exactly 42.37 ms).
        d = self._rng.uniform(0.0, self.host_delay_s)
        if hasattr(self.dev, "idle"):
            self.dev.idle(d)
        elif d > 0:
            time.sleep(d)

    def _measure(self, lba: int, label: str):
        if self.strategy == "far":
            # A sector (or a few) a third of the disc away moves the head and the read-ahead off
            # the target, so the timed read comes from the disc (READ CD has no FUA). The random
            # pause comes after it, as before every timed read.
            self._far_reads(lba, self.far_count)
            self._pause()
            return self._read(lba, self.sectors, label=label)
        self._pause()
        if self.strategy == "evict":
            self._evict()
        elif self.strategy == "flush":
            self._flush(lba)
        return self._read(lba, self.sectors, fua=self.strategy == "fua", label=label)

    def _usable(self, res) -> bool:
        # Dropping samples never biases the phase (it comes from the completion time,
        # not the wait), so when the cache is defeated indirectly anything that may be
        # a cache hit is dropped.
        if not res.ok:
            return False
        return self.strategy not in ("evict", "flush", "far") or res.duration_us >= self.cache_hit_us

    # ------------------------------------------------------------ steps

    def setup(self):
        self._experiment = "setup"
        ready = self._cmd(mmc.test_unit_ready(), 0)
        reason = mmc.not_ready(ready.sense)
        if reason:      # the checks below would blame the disc, or the --media setting
            raise NoReadableDisc(reason)
        cfg = self._cmd(mmc.get_configuration(), 4096)
        profile = mmc.parse_configuration(cfg.data).get("current_profile") if cfg.ok else None
        self.family = mmc.media_family(profile)
        self.block = mmc.block_sectors(self.family)

        cap = self._cmd(mmc.read_capacity(), 8)
        self.last_lba = mmc.parse_capacity(cap.data)["last_lba"] if cap.ok else None
        toc = self._cmd(mmc.read_toc(0), 2048)
        tracks = mmc.parse_toc(toc.data)["tracks"] if toc.ok else []
        audio = bool(tracks) and not tracks[0]["data"]
        self.audio = audio
        if self.media == "cd" and self.cd_audio and self.family == "cd" and audio:
            if self.read_method not in ("auto", "readcd"):
                raise NoReadableDisc("an audio track can only be read with READ CD")
        elif self.media == "cd" and (self.family != "cd" or audio or self.read_method == "readcd"):
            raise NoReadableDisc("--media cd requires a CD-ROM Mode 1 data track and READ(12)/READ(10), not READ CD")
        if self.last_lba is None and tracks and tracks[-1]["track"] == 0xAA:
            self.last_lba = tracks[-1]["start_lba"] - 1
        capacity_source = "read capacity" if self.last_lba else None
        if self.family == 'dvd' and self.last_lba:
            # READ CAPACITY can describe the whole medium on an open DVD.
            # Our pending marker supplies the actual first session's burned end.
            self.method = 'read10'
            self.load_layout()
            layout = self.summary.get('random_label', {})
            if layout.get('state') == 'pending':
                self.last_lba = min(self.last_lba, layout['total_sectors'] - 1)
                capacity_source = 'pending label recorded end'
        if (not self.last_lba or self.last_lba < 1000) and self.family == "bd":
            # An unrecorded BD-R or BD-RE reports a zero capacity, but its spiral is
            # grooved at the factory and the drive will still track and read across
            # the whole of it. GET PERFORMANCE is what knows how far it goes.
            perf = self._cmd(mmc.get_performance(0x10, 0x00), 2048)
            descs = mmc.parse_get_performance(perf.data, 0x00).get("descriptors", []) if perf.ok else []
            ends = [int(d["end_lba"]) for d in descs if int(d["end_lba"]) > 0]
            if ends:
                self.last_lba = max(ends)
                capacity_source = "get performance"
        if not self.last_lba or self.last_lba < 1000:
            raise NoReadableDisc("no readable recorded area; burn a test disc first (blank media has nothing to read)")

        self.method = self.read_method
        if self.method == "auto":
            self.method = "readcd" if audio else "read12"
        if self.method == "read12":
            res = self._read(self._align(0.5), label="probe")
            # Only a refused command means "try READ(10)"; a medium error says nothing about the opcode.
            if not res.ok and res.sense is not None and res.sense.key == 5:
                self.method = "read10"
        probes = [self._read(self._align(f), label="probe") for f in (0.5, 0.25, 0.75)]
        if not any(r.ok for r in probes):
            sense = next((r.sense for r in probes if r.sense is not None), None)
            if sense is not None and sense.key == 3:
                raise NoReadableDisc(UNREADABLE_DISC.format(sense=sense))
            raise NoReadableDisc(f"{self.method} fails on this disc ({sense})")

        if self.speed_kbs is not None or self.pure_cav:
            res = self._cmd(mmc.set_cd_speed(self.speed_kbs or 0xFFFF, 0xFFFF, self.pure_cav), 0)
            self.summary["set_cd_speed"] = {"requested_kBps": self.speed_kbs, "pure_cav": self.pure_cav,
                                            "status": res.status, "sense": str(res.sense or "")}
        self.summary["setup"] = {"profile": f"0x{profile:04X}" if profile is not None else None,
                                 "profile_name": mmc.PROFILES.get(profile), "family": self.family,
                                 "block_sectors": self.block, "sectors_per_read": self.sectors, "last_lba": self.last_lba,
                                 "capacity_source": capacity_source,
                                 "first_track_audio": audio, "read_method": self.method}
        self.log(f"Disc: {self.summary['setup']['profile_name']}, last LBA {self.last_lba}, "
                 f"reading with {self.method}")

        self._experiment = "warmup"
        warm = [self._read(self._align(f), label="warmup") for f in (0.0, 0.25, 0.5, 0.75, 1.0, 0.05)]
        bad = [r for r in warm if not r.ok and r.sense is not None and r.sense.key == 3]
        if len(bad) >= 3:
            raise NoReadableDisc(UNREADABLE_DISC.format(sense=bad[0].sense))

    def load_layout(self):
        """Read the optional in-band marker when a caller can reach the outer band."""
        # A simulated image explicitly knows whether it has layout sectors.
        # Keep the established no-layout timing simulation's reads and noise stream.
        if getattr(self.dev, 'layout_sectors', None) == {}:
            return
        if self.media == "dvd":
            from .randomlabel import START, END, MARKER_LBA, PENDING_LBA, STOP_SECTORS, read_marker
            self._experiment = 'layout'
            pending = None
            for anchor in (PENDING_LBA, MARKER_LBA, START):
                if anchor >= self.last_lba + 1:
                    continue
                # This runs before a timed-read method is selected during setup.
                result = self._read(anchor, label='layout')
                if result.ok:
                    spec = read_marker(result.data, self.last_lba + 1)
                    if spec:
                        if spec.get('marker_lba', START) != anchor:
                            raise ValueError('random-label marker at wrong address')
                        if spec.get('state') == 'pending':
                            pending = spec
                            # Do not probe the unrecorded outer band of the first session.
                            # After append-and-close the final band marker supersedes this one.
                            disc = self._cmd(mmc.read_disc_information(), 34)
                            state = mmc.parse_disc_information(disc.data) if disc.ok else {}
                            if state.get('disc_status') != 'complete':
                                self.summary['random_label'] = pending
                                return
                        else:
                            self.summary['random_label'] = spec
                            return
                elif anchor != PENDING_LBA and self.last_lba + 1 >= END:
                    # Unknown edge content must not become a timing target. Default geo
                    # still ends inside this band, even on an old disc with an unreadable edge.
                    self.summary["random_label"] = {"exclude_lba": [min(STOP_SECTORS, START), self.last_lba + 1], "unreadable_marker": True}
            if pending is not None:
                raise ValueError('closed pending-label disc has no valid appended layout; do not measure its outer area')

    def cache_test(self, reads: int = 40):
        self._experiment = "cache"
        lba = self._align(0.5)
        n = self.sectors
        plain = [self._read(lba, n, label="plain") for _ in range(reads)]
        out = {"lba": lba, "sectors": n, "plain": duration_stats(plain)}
        plain_cached = out["plain"]["p50_us"] < CACHE_HIT_US
        fua_media = flush_media = False
        if self.method != "readcd":
            fua = [self._read(lba, n, fua=True, label="fua") for _ in range(reads)]
            out["fua"] = duration_stats(fua)
            fua_media = out["fua"]["p50_us"] >= CACHE_HIT_US and all(r.ok for r in fua)
            # A cache hit over a slow link is not under CACHE_HIT_US (8 ms on an SDRW-08D2S-U over
            # USB, against 39 ms with FUA). Far slower with FUA also means plain reads are cached.
            if fua_media and out["fua"]["p50_us"] >= CACHE_RATIO * out["plain"]["p50_us"]:
                plain_cached = True
        elif self.media == "cd" and self.audio:
            return self._cache_test_audio(lba, n, reads, out)
        elif not plain_cached:
            # READ CD has no FUA bit, so compare with reads that follow an eviction instead. Over
            # USB an HP BU20N returned cached CD-DA sectors in about 10 ms, above CACHE_HIT_US,
            # while reads from the disc took several times longer.
            evicted = []
            for _ in range(max(8, reads // 4)):
                self._evict()
                evicted.append(self._read(lba, n, label="after-evict"))
            out["after_evict"] = duration_stats(evicted)
            slow = out["after_evict"]["p50_us"] >= CACHE_RATIO * out["plain"]["p50_us"]
            if slow and all(r.ok for r in evicted):
                plain_cached = True
                # Halfway (geometrically) between the cache hits and the reads from the disc.
                self.cache_hit_us = max(CACHE_HIT_US, math.sqrt(out["plain"]["p50_us"] *
                                                                 out["after_evict"]["p50_us"]))
                out["cache_hit_us"] = round(self.cache_hit_us, 1)
        if plain_cached and not fua_media:
            flushed = []
            for _ in range(reads):
                self._flush(lba)
                flushed.append(self._read(lba, n, label="after-flush"))
            out["after_flush"] = duration_stats(flushed)
            flush_media = out["after_flush"]["p50_us"] >= self.cache_hit_us and all(r.ok for r in flushed)
        if not plain_cached:
            self.strategy = "plain"
        elif fua_media:
            self.strategy = "fua"
        elif flush_media:
            self.strategy = "flush"
        else:
            self.strategy = "evict"
        out.update(plain_served_from_cache=plain_cached, fua_reads_media=fua_media,
                   flush_then_read_media=flush_media, strategy=self.strategy)
        self.summary["cache"] = out
        self.log("Cache: " + ", ".join(f"{k} p50 {v['p50_us']} us" for k, v in out.items()
                                       if isinstance(v, dict)) + f" -> strategy {self.strategy}")

    def _cache_test_audio(self, lba: int, n: int, reads: int, out: dict):
        """Cache test on a CD-DA track (geo on a DiscImageStudio picture burn).

        READ CD has no FUA bit and READ(12) is illegal on audio, so the cache is defeated by reading
        elsewhere first. One sector a third of the disc away is enough when the drive keeps a single
        read-ahead segment (HP BU20N, PLDS DU-8A5LH): strategy "far", one extra read per timed read.
        A target only a fraction of a turn from the previous read can sit in that read-ahead, so it is
        used even when plain re-reads look uncached. A drive that keeps several segments needs a few
        far reads (FAR_COUNTS); the eviction above is the last resort, since its slow blocks make
        the ladder's period fit alias."""
        plain = out["plain"]["p50_us"]
        cached = plain < CACHE_HIT_US
        far_from_disc = False
        for k in FAR_COUNTS:
            after_far = []
            for _ in range(max(8, reads // 4)):
                self._far_reads(lba, k)
                after_far.append(self._read(lba, n, label="after-far"))
            key = "after_far" if k == 1 else f"after_far_{k}"
            out[key] = duration_stats(after_far)
            far = out[key]["p50_us"]
            # Cached: fast re-reads, or re-reads several times faster than reads after far reads
            # (over USB a BU20N answered CD-DA cache hits in about 10 ms).
            cached = cached or far >= CACHE_RATIO * plain
            far_from_disc = far >= CACHE_HIT_US and far >= CACHE_RATIO * plain and all(r.ok for r in after_far)
            if not cached or far_from_disc:
                break
        if not cached or far_from_disc:
            self.strategy, self.far_count = "far", k
            out["far_reads"] = k
            if cached:
                # Halfway (geometrically) between the cache hits and the reads from the disc.
                self.cache_hit_us = max(CACHE_HIT_US, math.sqrt(plain * far))
        else:
            evicted = []
            for _ in range(max(8, reads // 4)):
                self._evict()
                evicted.append(self._read(lba, n, label="after-evict"))
            out["after_evict"] = duration_stats(evicted)
            ev = out["after_evict"]["p50_us"]
            self.strategy = "evict"
            if ev >= CACHE_HIT_US and ev >= CACHE_RATIO * plain:
                self.cache_hit_us = max(CACHE_HIT_US, math.sqrt(plain * ev))
            else:
                self.log("warning: neither a far read nor an eviction got this sector re-read from the disc")
        out["cache_hit_us"] = round(self.cache_hit_us, 1)
        out.update(plain_served_from_cache=cached, far_read_reads_media=far_from_disc, strategy=self.strategy)
        self.summary["cache"] = out
        self.log("Cache: " + ", ".join(f"{k} p50 {v['p50_us']} us" for k, v in out.items()
                                       if isinstance(v, dict)) + f" -> strategy {self.strategy}")

    def cover_one_turn(self, period_s: float):
        """The random pause before a timed read has to span a revolution to spread the phases."""
        self.host_delay_s = max(self.host_delay_s, 1.25 * period_s)

    def settle_spindle(self, rounds: int = 15, reads: int = 16):
        """Wait for a steady speed: a stopped or slowed drive spins up for a while after the first
        reads, and the first run then looks mixed or noisy while a second run looks fine."""
        self._experiment = "settle"
        lba, prev = self._align(0.5), None
        for _ in range(rounds):
            res = [self._measure(lba, "settle") for _ in range(reads)]
            times = [r.t_end_ns for r in res if self._usable(r)]
            fit = analysis.estimate_period(times) if len(times) >= 8 else None
            period = fit.period_s if fit and fit.coherence > 0.9 else None
            if period and prev and abs(period / prev - 1) < 2e-3:
                self.log(f"Spindle steady: T = {period * 1e3:.3f} ms ({60 / period:.1f} rpm)")
                self.summary["settle"] = {"steady": True, "period_ms": period * 1e3}
                if self.strategy == "fua":  # without the random pause, which would hide the whole turns
                    self.summary["settle"]["read"] = duration_stats(
                        [self._read(lba, self.sectors, fua=True, label="settled") for _ in range(8)])
                self.cover_one_turn(period)
                return
            prev = period
        self.log("Spindle did not reach a steady speed; expect noisy results")
        self.summary["settle"] = {"steady": False}

    def period_test(self, zones=None, announce_rotation=True):
        """One period per zone. `zones` overrides the three used to classify the spindle, which is
        what a CLV fit wants: more zones, spread further, because it fits a line through them.

        `announce_rotation` is for callers that judge the rotation themselves: this method's own
        verdict reads the first and last zone, and a caller that skips the ramp-up zone would be
        told the wrong thing twice."""
        self._experiment = "period"
        zones_out, times_by_zone = [], []
        for frac in (ZONES if zones is None else zones):
            lba = self._align(frac)
            reads = [self._measure(lba, f"zone{frac}") for _ in range(self.period_reads)]
            times = [r.t_end_ns for r in reads if self._usable(r)]
            fit = analysis.estimate_period(times)
            zone = {"fraction": frac, "lba": lba, "usable": len(times), "durations": duration_stats(reads),
                    "nominal_radius_mm": round(self._nominal_spiral().radius(lba), 3)}
            if fit:
                zone.update(fit.summary())
            zones_out.append(zone)
            times_by_zone.append(times)
            self.log(f"Zone {frac:.2f} (LBA {lba}): " + (
                f"T = {zone['period_ms']} ms ({zone['rpm']} rpm), jitter {zone['jitter_us']} us "
                f"= {zone['jitter_deg']} deg, coherence {zone['coherence']}" if fit else "no period found"))
        self._resolve_multiples(zones_out, times_by_zone)
        self.zones = zones_out
        self.summary["period"] = {"zones": zones_out, "rotation": self._classify(zones_out)}
        rotation = self.summary["period"]["rotation"]
        if announce_rotation:
            self.log(f"Rotation: {rotation['mode']}"
                     + (f" ({rotation['reason']})" if "reason" in rotation else ""))
        self._check_period(zones_out)

    def _resolve_multiples(self, zones, times_by_zone):
        """A zone whose period is a whole multiple of another zone's: the drive there completed reads only
        every k turns (seen on a GH70N: 62.22 ms at the inner zone, 20.75 ms elsewhere). The completions
        then fit k turns as well as one, and the period search takes the longest, so refit with the
        shorter period as the prior. A real speed change would not land on a whole multiple."""
        clear = [z for z in zones if z.get("period_ms") and z.get("coherence", 0) > 0.5]
        if len(clear) < 2:
            return
        base = min(z["period_ms"] for z in clear)
        for zone, times in zip(zones, times_by_zone):
            if zone not in clear:
                continue
            k = round(zone["period_ms"] / base)
            if k < 2 or abs(zone["period_ms"] / (k * base) - 1) > MULTIPLE_TOLERANCE:
                continue
            fit = analysis.estimate_period(times, prior_s=base / 1e3)
            if not fit or fit.coherence <= 0.5 or abs(fit.period_s * 1e3 / base - 1) > MULTIPLE_TOLERANCE:
                continue
            completion = zone["period_ms"]
            zone.update(fit.summary())
            zone.update(completion_period_ms=completion, completes_every_turns=k)
            self.log(f"Zone {zone['fraction']:.2f}: reads there completed only every {k} turns, so T = "
                     f"{zone['period_ms']} ms ({zone['rpm']} rpm), jitter {zone['jitter_deg']} deg")

    def _check_period(self, zones):
        """Catch a period that is not the spindle. A re-read from the disc takes whole turns on every
        drive so far. Reads served from cache follow the host instead: with a coarse sleep their
        completion times lock to the Windows timer tick (15.625 ms) and its harmonics."""
        import sys
        periods = [z["period_ms"] for z in zones if "period_ms" in z]
        if not periods:
            return
        T = statistics.median(periods)
        if sys.platform == "win32" and self.strategy in ("plain", "evict") and any(abs(15.625 / k - T) < 0.15 for k in (1, 2, 3)):
            self.log("Warning: this period looks like the Windows timer tick (15.625 ms), not the spindle")
        # The cache test runs before the spindle settles, so its FUA time can span two speeds.
        settle = self.summary.get("settle", {})
        fua = settle["read"]["p50_us"] if self.strategy == "fua" and "read" in settle else None
        if not fua:
            return
        turns = fua / 1e3 / T
        self.summary["period"]["fua_read_turns"] = round(turns, 3)
        if abs(turns - round(turns)) > 0.1:
            self.log(f"Warning: a FUA read takes {turns:.2f} turns of this period, not a whole number, "
                     "so this period may not be the spindle")

    def _nominal_key(self) -> str:
        return self.family if self.family in NOMINAL else "dvd"

    def _nominal_spiral(self):
        if self.media == "cd":
            from . import cd
            from .geometry import Spiral
            return Spiral(cd.R0_MM, cd.PITCH_UM * 1e-3, cd.SECTOR_BITS * cd.BIT_NM * 1e-6)
        return NOMINAL[self._nominal_key()]

    def _classify(self, zones) -> dict:
        valid = [z for z in zones if z.get("period_ms") and z.get("coherence", 0) > 0.5]
        noisy = [z.get("fraction", i) for i, z in enumerate(zones)
                 if not z.get("period_ms") or z.get("coherence", 0) <= 0.5]
        if noisy:  # a speed still changing shows up like this, and the two other zones alone can look CAV
            return {"mode": "unknown", "reason": f"zones {noisy} have no clear period; the speed may be changing, "
                                                 "try a fixed --speed"}
        if len(valid) < 2:
            return {"mode": "unknown", "reason": "fewer than two zones with a clear period"}
        inner, outer = valid[0], valid[-1]
        ratio = outer["period_ms"] / inner["period_ms"]
        clv_ratio = outer["nominal_radius_mm"] / inner["nominal_radius_mm"]
        if max(z["period_ms"] for z in valid) / min(z["period_ms"] for z in valid) < 1.03:
            mode = "CAV"
        elif abs(ratio - clv_ratio) / clv_ratio < 0.12:
            mode = "CLV"
        else:
            mode = "mixed (P-CAV / Z-CLV?)"
        return {"mode": mode, "period_ratio_outer_inner": round(ratio, 4),
                "nominal_clv_ratio": round(clv_ratio, 4)}

    def phase_test(self):
        self._experiment = "phase"
        ref = self._align(self.ref_fraction)
        prior = None
        for z in getattr(self, "zones", []):
            if z.get("period_ms") and z["fraction"] == min(ZONES, key=lambda f: abs(f - self.ref_fraction)):
                prior = z["period_ms"] / 1e3
        spiral = self._nominal_spiral()
        results = []
        span = -(-max(self.sectors, 1) // self.block) * self.block  # whole blocks the drive reads
        for frac in self.targets:
            x = self._align(frac)
            ref_times, x_times, x_reads = [], [], []
            for _ in range(self.reps):
                r = self._measure(ref, "ref")
                if self._usable(r):
                    ref_times.append(r.t_end_ns)
                xr = self._measure(x, "target")
                x_reads.append(xr)
                if self._usable(xr):
                    x_times.append(xr.t_end_ns)
            entry = {"target_fraction": frac, "ref_lba": ref, "target_lba": x, "read_end_lba": x + span,
                     "nominal_turns_between": round(spiral.turns(ref + span, x + span), 2),
                     "target_durations": duration_stats(x_reads)}
            if self.media == "cd":
                from .cd import read_end_bits, SECTOR_BITS
                nr, nx = read_end_bits(ref, self.sectors), read_end_bits(x, self.sectors)
                entry.update(read_end_bits=int(nx), read_tail_frames=108,
                             nominal_turns_between=round(spiral.turns(nr / SECTOR_BITS, nx / SECTOR_BITS), 2))
            fit = analysis.estimate_period(ref_times, prior_s=prior) if len(ref_times) >= 5 else None
            if fit and fit.coherence <= 0.5:
                entry["ref"] = fit.summary()
                entry["error"] = "reference has no clear period; try a fixed speed and measure again"
                self.log(f"Target {frac:.2f}: reference has no clear period; try a fixed speed and measure again")
            elif fit and x_times:
                entry["ref"] = fit.summary()
                entry["phase"] = analysis.robust_circular_mean(analysis.phase_offsets(fit, x_times))
                self.log(f"Target {frac:.2f} (LBA {x}): phase {entry['phase']['mean_deg']} deg "
                         f"+/- {entry['phase']['sem_deg']} (single-shot std {entry['phase']['std_deg']}, "
                         f"n={entry['phase']['used']}), ref jitter {entry['ref']['jitter_deg']} deg")
            else:
                entry["error"] = "not enough usable reads"
                self.log(f"Target {frac:.2f}: not enough usable reads")
            results.append(entry)
        rotation = self.summary.get("period", {}).get("rotation", {}).get("mode")
        self.summary["phase"] = {
            "valid_only_under_cav": True, "rotation_mode": rotation, "targets": results,
            "note": "phase = spindle phase of target completion minus reference completion; "
                    "it equals the disc angle between the ends of the two read blocks plus a "
                    "constant decode-latency term, modulo 360 degrees"}
        if rotation != "CAV":
            self.log("Warning: drive did not look CAV; phase values are not disc angles.")

    def run(self) -> dict:
        gc_was = gc.isenabled()
        gc.disable()
        try:
            self.setup()
            self.load_layout()
            self.cache_test()
            self.settle_spindle()
            self.period_test()
            mode = self.summary["period"]["rotation"]["mode"]
            if self.stop_if_not_cav and mode != "CAV":
                self.log(f"Rotation is {mode}, not CAV, so the phase test would not give disc angles; skipping it. "
                         "Try another --speed, or pass --force to run it anyway.")
            else:
                self.phase_test()
        finally:
            if gc_was:
                gc.enable()
        return self.summary

    def events_as_rows(self):
        return [asdict(e) for e in self.events]
