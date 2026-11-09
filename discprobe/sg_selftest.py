"""Hardware-free Linux SG_IO checks: python -m discprobe.sg_selftest."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from unittest.mock import patch

from .scsi import DATA_OUT


def _raises(c, exception, call, what, matches=lambda e: True):
    try:
        call()
    except exception as e:
        c.check(matches(e), what)
    else:
        c.check(False, what)


def _completion(c, sg):
    print("Linux SG_IO completion and read-only commands (mock ioctl)")
    state = {}
    calls = []
    fixed_sense = bytes.fromhex("70 00 02 00 00 00 00 0a 00 00 00 00 3a 02")

    def ioctl(fd, request, arg):
        calls.append(request)
        hdr = ctypes.cast(arg, ctypes.POINTER(sg._SGIOHeader)).contents
        for field, value in state.items():
            if field not in ("payload", "sense", "rc", "errno"):
                setattr(hdr, field, value)
        payload = state.get("payload", b"abcd")
        if hdr.dxferp:
            ctypes.memmove(hdr.dxferp, payload, min(len(payload), hdr.dxfer_len))
        sense = state.get("sense", b"")
        if sense:
            ctypes.memmove(hdr.sbp, sense, min(len(sense), sg.SENSE_BYTES))
        ctypes.set_errno(state.get("errno", 0))
        return state.get("rc", 0)

    cdb = b"\x12\x00\x00\x00\x04\x00"
    with patch.object(sg.os, "open", return_value=123), patch.object(sg.os, "close"), \
            patch.object(sg._libc, "ioctl", side_effect=ioctl):
        with sg.SgDevice("sr0") as dev:
            result = dev.execute(cdb, 4)
            c.check(result.ok and result.data == b"abcd" and result.sense is None
                    and result.t_end_ns >= result.t_start_ns and calls == [sg.SG_IO],
                    "full transfer returns all bytes and ioctl timestamps")
            state.update(payload=b"xy", resid=2)
            c.check(dev.execute(cdb, 4).data == b"xy", "short transfer excludes stale buffer bytes")
            state.update(resid=8)
            c.check(dev.execute(cdb, 4).data == b"", "residual beyond request clamps to zero bytes")
            state.update(resid=-8, payload=b"abcd")
            c.check(dev.execute(cdb, 4).data == b"abcd", "negative residual clamps to requested bytes")
            state.clear()
            state.update(status=2, sense=fixed_sense, sb_len_wr=len(fixed_sense))
            result = dev.execute(cdb)
            c.check(not result.ok and result.status == 2 and str(result.sense) == "2/3A/02",
                    "CHECK CONDITION preserves not-ready sense")
            state.update(status=0, driver_status=8)
            result = dev.execute(cdb)
            c.check(not result.ok and result.status == 2 and str(result.sense) == "2/3A/02",
                    "driver sense with GOOD status becomes CHECK CONDITION")
            state.update(driver_status=0)
            result = dev.execute(cdb)
            c.check(not result.ok and str(result.sense) == "2/3A/02",
                    "sense bytes alone become CHECK CONDITION")
            state.update(status=2, sb_len_wr=3)
            c.check(dev.execute(cdb).sense is None, "sense parsing uses only the reported length")
            state.update(sb_len_wr=255)
            c.check(str(dev.execute(cdb).sense) == "2/3A/02", "reported sense length is bounded to the buffer")
            state.clear()
            state.update(host_status=1)
            _raises(c, OSError, lambda: dev.execute(cdb), "host failure raises EIO with transport statuses",
                    lambda e: e.errno == errno.EIO and "host status 0x0001" in str(e)
                    and "driver status 0x0000" in str(e))
            state.clear()
            state.update(driver_status=0x18)
            _raises(c, OSError, lambda: dev.execute(cdb), "non-sense driver bits raise EIO",
                    lambda e: e.errno == errno.EIO and "driver status 0x0018" in str(e))
            state.clear()
            state.update(rc=-1, errno=errno.EINVAL)
            _raises(c, OSError, lambda: dev.execute(cdb), "ioctl error keeps errno",
                    lambda e: e.errno == errno.EINVAL)
            before = len(calls)
            _raises(c, ValueError, lambda: dev.execute(b"\x12" * 17), "CDB longer than 16 bytes is refused")
            _raises(c, ValueError, lambda: dev.execute(b""), "empty CDB is refused")
            _raises(c, ValueError, lambda: dev.execute(cdb, -1), "negative transfer length is refused")
            _raises(c, ValueError, lambda: dev.execute(cdb, sg.BUFFER_BYTES + 1), "oversized transfer is refused")
            _raises(c, PermissionError, lambda: dev.execute(cdb, direction=DATA_OUT), "DATA_OUT is refused")
            _raises(c, PermissionError, lambda: dev.execute(b"\xff"), "opcode allowlist is enforced")
            c.check(len(calls) == before, "invalid requests never reach ioctl")


def _opening(c, sg):
    print("Linux SG_IO open fallback (mock open)")
    busy = OSError(errno.EBUSY, os.strerror(errno.EBUSY))
    denied = OSError(errno.EACCES, os.strerror(errno.EACCES))
    with patch.object(sg.os, "open", side_effect=[busy, 123]) as opened, \
            patch.object(sg.os, "close") as closed, \
            patch.object(sg, "_sg_for_sr", return_value="/dev/sg7"):
        with sg.SgDevice("sr0") as dev:
            c.check(dev.path == "/dev/sg7" and dev.name == "sg7"
                    and [call.args[0] for call in opened.call_args_list] == ["/dev/sr0", "/dev/sg7"],
                    "EBUSY on sr falls back to the mapped sg path")
        c.check(closed.call_args.args == (123,), "fallback descriptor is closed")
    with patch.object(sg.os, "open", side_effect=denied) as opened, \
            patch.object(sg, "_sg_for_sr") as mapped:
        _raises(c, OSError, lambda: sg.SgDevice("/dev/sr0"), "EACCES names path and permission hint",
                lambda e: e.errno == errno.EACCES and "/dev/sr0" in str(e)
                and denied.strerror in str(e) and "cdrom group" in str(e) and "disk group" not in str(e))
        c.check(opened.call_count == 1 and not mapped.called, "EACCES never attempts sg fallback")
    with patch.object(sg.os, "open", side_effect=[busy, denied]), \
            patch.object(sg, "_sg_for_sr", return_value="/dev/sg7"):
        _raises(c, OSError, lambda: sg.SgDevice("sr0"), "failed fallback names both paths and keeps first errno",
                lambda e: e.errno == errno.EBUSY and f"/dev/sr0: {busy.strerror}" in str(e)
                and f"/dev/sg7: {denied.strerror}" in str(e)
                and "another program" in str(e) and "cdrom group" in str(e))
    for name in ("sr0", "sg7", "/dev/sr0", "/dev/sg7"):
        with patch.object(sg.os, "open", return_value=123), patch.object(sg.os, "close"):
            with sg.SgDevice(name) as dev:
                c.check(dev.path == "/dev/" + os.path.basename(name) and dev.name == os.path.basename(name),
                        f"{name} resolves to a device path and filesystem-safe name")


def run(c):
    if sys.platform != "linux":
        print("Linux SG_IO checks skipped (requires Linux)")
        return
    try:
        from . import sg
    except (ImportError, OSError, AttributeError) as e:
        print(f"Linux SG_IO checks skipped ({e})")
        return
    print("Linux SG_IO header layout")
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        offsets = {"dxferp": 16, "cmdp": 24, "sbp": 32, "usr_ptr": 56,
                   "status": 64, "sb_len_wr": 67, "host_status": 68,
                   "driver_status": 70, "resid": 72, "info": 80}
        c.check(ctypes.sizeof(sg._SGIOHeader) == 88
                and all(getattr(sg._SGIOHeader, name).offset == offset for name, offset in offsets.items()),
                "64-bit sg_io_hdr is 88 bytes with expected pointer and completion offsets")
    else:
        print("  64-bit SG_IO header layout check skipped (32-bit process)")
    _completion(c, sg)
    _opening(c, sg)


def main():
    from .selftest import Checker
    c = Checker()
    run(c)
    print(f"\n{'all checks passed' if not c.failures else f'{c.failures} check(s) failed'}")
    return int(c.failures != 0)


if __name__ == "__main__":
    raise SystemExit(main())
