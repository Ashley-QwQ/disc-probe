"""`info`: dump everything the drive reports about itself and the loaded disc."""

from __future__ import annotations

from . import mmc
from .scsi import DATA_IN, DATA_NONE, ScsiResult

import queue
import threading
import time

COMMAND_TIMEOUT_S = 3
INFO_BUDGET_S = 25
NEXT_ACTION = "Close other drive software, reload this same disc and retry info; share diagnostics if it repeats."


class InfoDevice:
    """Wall-clock and native bounds for info, including optional identity reads."""
    def __init__(self, dev=None, budget_s=INFO_BUDGET_S, *, opener=None):
        self.dev = dev
        self.deadline = time.monotonic() + budget_s
        self.failed = False
        self.errors = []
        self.requests = queue.Queue()
        self.closed = False
        # Opening, executing and closing share one thread: IMAPI COM objects and
        # CoUninitialize must stay on their creating thread as well.
        def worker():
            while True:
                request = self.requests.get()
                if request is None:
                    return
                call, result = request
                try:
                    result.put((call(), None))
                except BaseException as exc:
                    result.put((None, exc))
        threading.Thread(target=worker, daemon=True).start()
        if opener is not None:
            def open_device():
                self.dev = opener()
                return self.dev
            try:
                self._call(open_device, 5, 'open drive')
            except BaseException:
                self.failed = True
                self.close()
                raise

    def _call(self, call, seconds, step):
        result = queue.Queue(1)
        self.requests.put((call, result))
        try:
            value, error = result.get(timeout=max(.001, seconds))
        except queue.Empty:
            raise TimeoutError(f'{step} timed out after {seconds:g}s. {NEXT_ACTION}') from None
        if error is not None:
            raise error
        return value

    def __getattr__(self, name):
        return getattr(self.dev, name)

    def execute(self, cdb, data_len=0, direction=DATA_IN, timeout_s=COMMAND_TIMEOUT_S):
        from .scsi import check_allowed
        step = check_allowed(cdb)
        remaining = self.deadline - time.monotonic()
        if self.failed or remaining <= 0:
            message = f"{step} skipped after info timeout. {NEXT_ACTION}"
            if not self.failed:
                self.failed = True
                self.errors.append(message)
            raise TimeoutError(message)
        try:
            return self._call(lambda: self.dev.execute(cdb, data_len, direction,
                                timeout_s=min(timeout_s, COMMAND_TIMEOUT_S)),
                                min(COMMAND_TIMEOUT_S + 1, remaining), step)
        except OSError as exc:
            self.failed = True
            message = f"{step}: {exc}. {NEXT_ACTION}"
            self.errors.append(message)
            raise TimeoutError(message) from exc

    def close(self):
        if self.closed:
            return
        self.closed = True
        close = lambda: self.dev.close() if hasattr(self.dev, 'close') else None
        try:
            if self.failed:
                # Queue cleanup behind the outstanding ioctl, never underneath it.
                self.requests.put((close, queue.Queue(1)))
            else:
                self._call(close, 1, 'close drive')
        finally:
            self.requests.put(None)


def _run(dev, name: str, cdb: bytes, alloc: int, parser=None) -> dict:
    entry = {"cdb": cdb.hex(" ")}
    try:
        res: ScsiResult = dev.execute(cdb, alloc, DATA_IN if alloc else DATA_NONE,
                                      timeout_s=COMMAND_TIMEOUT_S)
    except OSError as e:
        entry["error"] = f"{name}: {e}. {NEXT_ACTION}"
        return entry
    entry["status"] = res.status
    if not res.ok:
        entry['error'] = f"{name} unavailable (status {res.status}, sense {res.sense}). Check that the disc is ready; this command may be unsupported."
    entry["duration_us"] = round(res.duration_us, 1)
    if res.sense:
        entry["sense"] = str(res.sense)
    if res.data:
        entry["raw"] = res.data.hex()
    if res.ok and parser and res.data:
        try:
            entry["parsed"] = parser(res.data)
        except Exception as e:  # keep the raw dump even if a parser trips
            entry["parse_error"] = repr(e)
    return entry


def collect(dev) -> dict:
    r: dict[str, dict] = {}
    r["test_unit_ready"] = _run(dev, "TUR", mmc.test_unit_ready(), 0)
    r["inquiry"] = _run(dev, "INQUIRY", mmc.inquiry(), 96, mmc.parse_inquiry)
    r["configuration"] = _run(dev, "GET CONFIGURATION", mmc.get_configuration(), 4096,
                              mmc.parse_configuration)
    r["disc_information"] = _run(dev, "READ DISC INFORMATION", mmc.read_disc_information(), 34,
                                 mmc.parse_disc_information)
    r["track_1"] = _run(dev, "READ TRACK INFORMATION", mmc.read_track_information(1), 48,
                        mmc.parse_track_information)
    # Where the next write would go: the last track of the last session is the open one.
    last = (r["disc_information"].get("parsed") or {}).get("last_track_last_session")
    if last and last > 1:
        r["track_last"] = _run(dev, "READ TRACK INFORMATION", mmc.read_track_information(last), 48,
                               mmc.parse_track_information)
    r["capacity"] = _run(dev, "READ CAPACITY", mmc.read_capacity(), 8, mmc.parse_capacity)
    r["toc"] = _run(dev, "READ TOC", mmc.read_toc(0), 2048, mmc.parse_toc)
    r["atip"] = _run(dev, "READ ATIP", mmc.read_toc(4, msf=True), 2048, mmc.parse_atip)
    r["dvd_physical"] = _run(dev, "DVD physical format", mmc.read_disc_structure(0, 0x00), 2052,
                             mmc.parse_dvd_physical)
    # 10h: for DVD-R, the physical format information recorded in the lead-in
    # (00h may come from the latest border-in instead).
    r["dvd_physical_leadin_10"] = _run(dev, "DVD lead-in physical format", mmc.read_disc_structure(0, 0x10),
                                       2052, mmc.parse_dvd_physical)
    r["dvd_prerecorded_0e"] = _run(dev, "DVD-R pre-recorded info", mmc.read_disc_structure(0, 0x0E),
                                   2052, mmc.parse_dvd_r_prerecorded)
    r["dvd_plus_adip_11"] = _run(dev, "DVD+R ADIP", mmc.read_disc_structure(0, 0x11), 2052,
                                 mmc.parse_dvd_plus_adip)
    r["bd_disc_information"] = _run(dev, "BD disc information", mmc.read_disc_structure(1, 0x00),
                                    4100, lambda d: {"ascii_runs": mmc.ascii_runs(d[4:])})
    r["perf_read_nominal"] = _run(dev, "GET PERFORMANCE read", mmc.get_performance(0x10, 0x00),
                                  8 + 16 * 16, lambda d: mmc.parse_get_performance(d, 0x00))
    r["perf_write_nominal"] = _run(dev, "GET PERFORMANCE write", mmc.get_performance(0x14, 0x00),
                                   8 + 16 * 16, lambda d: mmc.parse_get_performance(d, 0x00))
    r["perf_write_speeds"] = _run(dev, "GET PERFORMANCE write speeds", mmc.get_performance(0, 0x03),
                                  8 + 16 * 16, lambda d: mmc.parse_get_performance(d, 0x03))
    r["mode_page_2a"] = _run(dev, "MODE SENSE 2A", mmc.mode_sense10(0x2A), 256, mmc.parse_mode_page_2a)
    return r


def quick(dev) -> dict:
    """The few reads `collect` makes that say which disc this is: whether one is ready, its profile, blank or
    not, its size and its manufacturer code. Read-only, a second or two once the disc has spun up; the keys
    are those of `collect`, so the same parsers read either."""
    r: dict[str, dict] = {}
    r["test_unit_ready"] = _run(dev, "TUR", mmc.test_unit_ready(), 0)
    r["inquiry"] = _run(dev, "INQUIRY", mmc.inquiry(), 96, mmc.parse_inquiry)
    if "sense" in r["test_unit_ready"] or "error" in r["test_unit_ready"]:
        return r                                     # no disc ready (tray open, empty, still loading)
    r["configuration"] = _run(dev, "GET CONFIGURATION", mmc.get_configuration(), 4096, mmc.parse_configuration)
    family = mmc.media_family((r["configuration"].get("parsed") or {}).get("current_profile"))
    r["disc_information"] = _run(dev, "READ DISC INFORMATION", mmc.read_disc_information(), 34,
                                 mmc.parse_disc_information)
    r["track_1"] = _run(dev, "READ TRACK INFORMATION", mmc.read_track_information(1), 48,
                        mmc.parse_track_information)
    r["capacity"] = _run(dev, "READ CAPACITY", mmc.read_capacity(), 8, mmc.parse_capacity)
    if family == "cd":
        r["atip"] = _run(dev, "READ ATIP", mmc.read_toc(4, msf=True), 2048, mmc.parse_atip)
    elif family == "dvd":
        r["dvd_prerecorded_0e"] = _run(dev, "DVD-R pre-recorded info", mmc.read_disc_structure(0, 0x0E),
                                       2052, mmc.parse_dvd_r_prerecorded)
        if not (r["dvd_prerecorded_0e"].get("parsed") or {}).get("manufacturer_id"):
            r["dvd_plus_adip_11"] = _run(dev, "DVD+R ADIP", mmc.read_disc_structure(0, 0x11), 2052,
                                         mmc.parse_dvd_plus_adip)
    return r


def disc_id(mid: dict, adip: dict, atip: dict) -> str | None:
    """A disc's manufacturer code, in the form `info` prints it."""
    if mid.get("manufacturer_id"):
        return mid["manufacturer_id"].replace("\x00", " ").strip()
    if adip.get("manufacturer_id"):
        return f"{adip['manufacturer_id']}/{adip['media_type_id']}/{adip['product_revision']}"
    if atip.get("leadin_start_msf"):
        return f"ATIP {atip['leadin_start_msf']}"
    return None


def identify(dev, family: str | None = None) -> dict:
    """Which drive and disc a measurement used, so results can be told apart later. Reads only, before any timing."""
    errors = []
    def read(*args):
        entry = _run(dev, *args)
        if 'error' in entry and 'status' not in entry:
            errors.append(entry['error'])
        return entry.get('parsed') or {}
    inq = read("INQUIRY", mmc.inquiry(), 96, mmc.parse_inquiry)
    mid, adip, atip = {}, {}, {}
    if family == "cd":
        atip = read("READ ATIP", mmc.read_toc(4, msf=True), 2048, mmc.parse_atip)
    elif family != "bd":
        mid = read("DVD-R pre-recorded info", mmc.read_disc_structure(0, 0x0E), 2052, mmc.parse_dvd_r_prerecorded)
        if not mid.get("manufacturer_id"):
            adip = read("DVD+R ADIP", mmc.read_disc_structure(0, 0x11), 2052, mmc.parse_dvd_plus_adip)
    return {"drive": f"{inq.get('vendor', '')} {inq.get('product', '')}".strip() or None, "firmware": inq.get("revision"), "disc": disc_id(mid, adip, atip),
            **({'probe_errors': errors} if errors else {})}


def summarize(r: dict) -> list[str]:
    def parsed(key):
        return r.get(key, {}).get("parsed") or {}

    lines = []
    from .capacity import capacity_words
    words = capacity_words(r)
    geometric = words['geometric_total_sectors'] if words['geometric_total_sectors'] is not None else 'unknown'
    writable = words['blank_writable_sectors'] if words['blank_writable_sectors'] is not None else 'unknown'
    lines += [f"Geometric total: {geometric} sectors (whole medium; unknown is not zero)",
              f"Writable capacity of this blank: {writable} sectors (burn limit; unknown is not zero)",
              'Random-mirror length: not measured by info; random --sectors chooses the file length (DVD default 2295104).',
              'disexport --sectors chooses the mapping total to match DiscImageStudio; timing / geo use the readable recorded area.']
    lines.append('A blank DVD-R writable count such as 2297888 and a DVD+R random/preset length such as 2295104 can both be correct; they describe different limits.')
    from .capacity import recordable_capacity
    recordable = recordable_capacity(r)
    if recordable:
        meaning = 'confirmed blank free space' if words['blank_writable_sectors'] is not None else 'whole-medium reference; writable free space is unconfirmed'
        lines.append(f"Recordable capacity: {recordable[0]} sectors ({recordable[1]}; {meaning})")
    if mmc.not_ready(r.get('test_unit_ready', {}).get('sense')):
        lines.clear()  # an open/empty tray has no capacity to compare
    inq = parsed("inquiry")
    if inq:
        lines.append(f"Drive: {inq['vendor']} {inq['product']} rev {inq['revision']}")
    # Without a disc the profile reads as unknown and nearly every command fails; say why once.
    reason = mmc.not_ready(r.get("test_unit_ready", {}).get("sense"))
    if reason:
        lines.append(reason)
    cfg = parsed("configuration")
    if cfg and not reason:
        lines.append(f"Current profile: {cfg.get('current_profile_name')} "
                     f"(0x{cfg.get('current_profile') or 0:04X})")
    di = parsed("disc_information")
    if di:
        lines.append(f"Disc status: {di['disc_status']}, sessions {di['sessions']}, erasable {di['erasable']}")
    track = parsed("track_last") or parsed("track_1")
    if di and di.get("disc_status") in ("empty", "incomplete") and track.get("nwa_valid"):
        lines.append(f"Next writable address: LBA {track['next_writable']} ({track['free_blocks']} sectors free)")
    cap = parsed("capacity")
    if cap.get("last_lba") is not None:
        lines.append(f"Readable capacity: last LBA {cap['last_lba']} x {cap['block_length']} B")
    atip = parsed("atip")
    if atip:
        lines.append(f"ATIP: {atip['disc_type']}, lead-in start {atip['leadin_start_msf']} "
                     f"(manufacturer code), last lead-out start {atip['last_leadout_start_msf']} "
                     f"= LBA {atip['last_leadout_start_lba']}")
    phys = parsed("dvd_physical")
    if phys:
        # DVD+R written with book-type bitsetting may report DVD-ROM here; trust the profile.
        lines.append(f"DVD physical: {phys['book_type']} {phys['disc_size']}, {phys['layers']} layer(s), "
                     f"{phys['linear_density']}, {phys['track_density']} (nominal codes), "
                     f"PSN {phys['data_start_psn']}..{phys['data_end_psn']}")
    pre = parsed("dvd_prerecorded_0e")
    if pre.get("manufacturer_id"):
        lines.append(f"DVD-R MID: {pre['manufacturer_id']!r}")
    elif pre.get("ascii_runs"):
        lines.append(f"DVD-R pre-recorded text: {' | '.join(pre['ascii_runs'])}")
    adip = parsed("dvd_plus_adip_11")
    if adip.get("manufacturer_id"):
        lines.append(f"DVD+R MID: {adip['manufacturer_id']}/{adip['media_type_id']}/{adip['product_revision']}")
    for key, label in (("perf_read_nominal", "Read perf"), ("perf_write_nominal", "Write perf")):
        for desc in parsed(key).get("descriptors", []):
            lines.append(f"{label}: LBA {desc['start_lba']}..{desc['end_lba']}  "
                         f"{desc['start_kBps']} -> {desc['end_kBps']} kB/s "
                         f"(ratio {desc.get('end_over_start')})")
    for desc in parsed("perf_write_speeds").get("descriptors", []):
        lines.append(f"Write speed descriptor: read {desc['read_kBps']} / write {desc['write_kBps']} kB/s "
                     f"to LBA {desc['end_lba']}")
    page = parsed("mode_page_2a")
    if page:
        lines.append(f"Page 2A: buffer {page['buffer_kB']} kB, rotation {page['rotation_control_selected']}, "
                     f"write speeds {[(w['kBps'], w['rotation']) for w in page['write_speeds']]}")
    failed = [k for k, v in r.items() if v.get("status") not in (0, None) or "error" in v]
    if failed and not reason:
        lines.append("Not available on this drive/disc: " + ", ".join(
            f"{k} ({r[k].get('sense') or r[k].get('error')})" for k in failed))
    return lines
