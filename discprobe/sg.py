"""Linux SCSI pass-through (SG_IO) for optical drives.

Same contract as spti.py: open an optical drive, send a raw SCSI CDB with one
ioctl, and timestamp with time.perf_counter_ns() immediately around that ioctl.
SG_IO works on both /dev/srN (the sr driver's generic SCSI ioctl) and /dev/sgN
(the raw sg driver); the open tries the given path and, when it is an sr device
the kernel reports busy (EBUSY), its matching sg device. A mounted disc does not
by itself make sr busy: a plain O_RDWR open succeeds alongside the mount.
"""

from __future__ import annotations

import ctypes
import errno
import os
import time

from .scsi import DATA_IN, DATA_OUT, ScsiResult, check_allowed, parse_sense

SG_IO = 0x2285
SG_DXFER_NONE = -1
SG_DXFER_FROM_DEV = -3

BUFFER_BYTES = 128 * 1024
SENSE_BYTES = 32

_libc = ctypes.CDLL(None, use_errno=True)
_libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
_libc.ioctl.restype = ctypes.c_int


class _SGIOHeader(ctypes.Structure):
    # struct sg_io_hdr from <scsi/sg.h>; field order and types must match, ctypes
    # applies the same natural alignment as the C compiler.
    _fields_ = [
        ("interface_id", ctypes.c_int),        # 'S'
        ("dxfer_direction", ctypes.c_int),     # SG_DXFER_* above
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),            # milliseconds
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]


def list_optical_drives() -> list[str]:
    """Return the sr device nodes that are optical drives, e.g. ['/dev/sr0']."""
    drives = []
    try:
        names = os.listdir("/sys/block")
    except OSError:
        return drives
    for name in sorted(names):
        if not name.startswith("sr"):
            continue
        path = f"/dev/{name}"
        if not os.path.exists(path):
            continue
        type_path = f"/sys/block/{name}/device/type"
        try:
            with open(type_path) as f:
                if f.read().strip() != "5":  # TYPE_ROM = optical
                    continue
        except OSError:
            pass  # sr* is already optical by construction; keep it
        drives.append(path)
    return drives


def _resolve(drive: str) -> str:
    d = drive.strip()
    if d.startswith("/dev/"):
        return d
    name = os.path.basename(d.rstrip("/"))
    if name.startswith(("sr", "sg")) and "/" not in name:
        return f"/dev/{name}"
    return d


def _sg_for_sr(sr_path: str) -> str | None:
    """Map /dev/srN to its /dev/sgN via the shared SCSI device in sysfs."""
    name = os.path.basename(sr_path)
    dev = os.path.realpath(f"/sys/block/{name}/device")
    if not os.path.isdir(dev):
        return None
    try:
        entries = os.listdir("/sys/class/scsi_generic")
    except OSError:
        return None
    for sg in sorted(entries):
        if os.path.realpath(f"/sys/class/scsi_generic/{sg}/device") == dev:
            return f"/dev/{sg}"
    return None


def raise_priority() -> bool:
    # FIFO prevents preemption by normal tasks while running, not during the SG_IO
    # wait itself. Pin to one CPU to avoid migration; fall back to a high nice value.
    ok = False
    try:
        lo = os.sched_get_priority_min(os.SCHED_FIFO)
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(lo))
        ok = True
    except (OSError, AttributeError):
        pass
    try:
        cpu = min(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {cpu})
    except (OSError, AttributeError):
        pass
    if ok:
        return True
    try:
        os.nice(-20)
        return True
    except OSError:
        return False


class SgDevice:
    def __init__(self, drive: str):
        self.path = _resolve(drive)
        self.name = os.path.basename(self.path)
        self._fd = None
        self._buf = ctypes.create_string_buffer(BUFFER_BYTES)
        self._sense = ctypes.create_string_buffer(SENSE_BYTES)
        self._cdb = ctypes.create_string_buffer(16)
        self._hdr = _SGIOHeader()

        candidates = [self.path]
        failures = []
        for cand in candidates:
            try:
                # O_RDWR so SET CD SPEED clears the kernel's read-only command
                # filter; O_NONBLOCK so a bare sg open never hangs.
                self._fd = os.open(cand, os.O_RDWR | os.O_NONBLOCK)
                self.path, self.name = cand, os.path.basename(cand)
                break
            except OSError as e:
                failures.append((cand, e))
                if len(failures) == 1 and e.errno == errno.EBUSY and self.name.startswith("sr"):
                    sg = _sg_for_sr(self.path)
                    if sg:
                        candidates.append(sg)
        if self._fd is None:
            self._raise_open_error(failures)

    def _raise_open_error(self, failures):
        hint = ""
        if any(err.errno in (errno.EPERM, errno.EACCES) for _, err in failures):
            hint += " (add your user to the cdrom group, or run as root)"
        if any(err.errno == errno.EBUSY for _, err in failures):
            hint += " (another program may hold the drive exclusively: close burning software, or pass /dev/sgN)"
        msg = "cannot open " + "; ".join(f"{path}: {err.strerror}" for path, err in failures)
        first = failures[0][1]
        raise OSError(first.errno, msg + hint) from first

    def execute(self, cdb: bytes, data_len: int = 0, direction: int = DATA_IN,
                timeout_s: int = 30) -> ScsiResult:
        if not 1 <= len(cdb) <= 16:
            raise ValueError("CDB length must be between 1 and 16 bytes")
        if data_len < 0:
            raise ValueError("transfer length must not be negative")
        check_allowed(cdb)
        if direction == DATA_OUT:
            raise PermissionError("data-out commands are not used by this probe")
        if data_len > BUFFER_BYTES:
            raise ValueError(f"transfer of {data_len} bytes exceeds the {BUFFER_BYTES}-byte buffer")

        hdr = self._hdr
        ctypes.memset(ctypes.byref(hdr), 0, ctypes.sizeof(hdr))
        ctypes.memset(self._cdb, 0, 16)
        ctypes.memmove(self._cdb, cdb, len(cdb))
        ctypes.memset(self._sense, 0, SENSE_BYTES)

        hdr.interface_id = ord("S")
        hdr.dxfer_direction = SG_DXFER_FROM_DEV if data_len else SG_DXFER_NONE
        hdr.cmd_len = len(cdb)
        hdr.mx_sb_len = SENSE_BYTES
        hdr.dxfer_len = data_len
        hdr.dxferp = ctypes.addressof(self._buf) if data_len else None
        hdr.cmdp = ctypes.addressof(self._cdb)
        hdr.sbp = ctypes.addressof(self._sense)
        hdr.timeout = max(1, int(timeout_s * 1000))

        t0 = time.perf_counter_ns()
        rc = _libc.ioctl(self._fd, SG_IO, ctypes.byref(hdr))
        t1 = time.perf_counter_ns()
        if rc != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"SG_IO on {self.path} failed: {os.strerror(err)}")

        if hdr.host_status or hdr.driver_status & ~0x08:
            raise OSError(errno.EIO, f"SG_IO on {self.path} failed: "
                          f"host status 0x{hdr.host_status:04X}, driver status 0x{hdr.driver_status:04X}")
        transferred = max(0, min(data_len, data_len - hdr.resid))
        data = ctypes.string_at(ctypes.addressof(self._buf), transferred) if transferred else b""
        sense = None
        if hdr.status or hdr.driver_status & 0x08 or hdr.sb_len_wr:
            sense = parse_sense(ctypes.string_at(ctypes.addressof(self._sense), min(hdr.sb_len_wr, SENSE_BYTES)))
        # Like SPTI CHECK CONDITION, driver sense must reach callers as a failed
        # result, so media-removal and not-ready handling cannot mistake it for success.
        status = hdr.status or (0x02 if hdr.driver_status & 0x08 or sense is not None else 0)
        return ScsiResult(status, data, sense, t0, t1)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
