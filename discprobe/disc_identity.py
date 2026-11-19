"""Read-only identity evidence for the medium authorized for a write."""
from __future__ import annotations

import json
import os
import sys
import time

from .capacity import positive_sectors
from .drive_lock import locked_drive
from .mmc import media_family


EXPECTED_ENV = "DISCPROBE_EXPECTED_DISC"
_STABLE = ("media", "profile", "mid", "medium_id", "rewritable")
_FIELDS = (*_STABLE, "capacity_sectors", "blank", "closed", "sectors")
_UNAVAILABLE = "无法读取足够的光盘身份信息，已拒绝写入 / Not enough disc identity information to authorize writing."
_NOT_REWRITABLE = ("这张盘不能擦除：只有 DVD±RW、CD-RW 这类可擦写盘能擦 / "
                   "This disc cannot be erased: only rewritable discs (DVD±RW, CD-RW) can.")


class DiscChanged(ValueError):
    def __init__(self, message="光驱里的盘和确认时的不是同一张 / The disc in the drive is not the one that was confirmed."):
        super().__init__(message)


def from_disc_report(report):
    """Use the same shape for MMC evidence and injected read-only providers."""
    if not report or report.get("present") is False:
        report = {}
    identity = {key: report.get(key) for key in _FIELDS}
    if identity["profile"] is None:
        identity["profile"] = (report.get("rewritable_sources") or {}).get("current_profile")
    identity["read_at_ns"] = time.time_ns()
    return identity


def from_info(report):
    from .webui_catalog import disc_report

    ready = report.get("test_unit_ready") or {}
    if ready.get("status") != 0 or ready.get("error") or ready.get("sense"):
        return from_disc_report(None)

    disc = disc_report(report)
    # The MMC standard disc-information block marks DiskIdentification valid
    # with DID_V (byte 7, bit 7). Padding and stale bytes are not evidence.
    entry = report.get("disc_information") or {}
    if entry.get("status") == 0 and not entry.get("error"):
        raw = bytes.fromhex(entry.get("raw") or "")
        if len(raw) >= 16 and int.from_bytes(raw[:2], "big") >= 14 and raw[7] & 0x80:
            disc["medium_id"] = raw[12:16].hex()
    return from_disc_report(disc)


@locked_drive("disc")
def read_identity(drive) -> dict:
    from .device import Device
    from .info import quick

    try:
        try:
            device = Device(drive)
        except OSError as exc:
            # SPTI raises the native Windows error code from CreateFileW.
            if sys.platform != "win32" or exc.errno != 5:
                raise
            from .imapi import ImapiDevice
            device = ImapiDevice(drive)
        with device as opened:
            return from_info(quick(opened))
    except (OSError, ValueError) as exc:
        raise DiscChanged(_UNAVAILABLE) from exc


def require_identity(identity, *, erasing=False):
    if not isinstance(identity, dict):
        raise DiscChanged(_UNAVAILABLE)
    profile = identity.get("profile")
    if (type(profile) is not int or media_family(profile) not in ("cd", "dvd", "bd")
            or media_family(profile) != identity.get("media")
            or type(identity.get("blank")) is not bool
            or type(identity.get("rewritable")) is not bool
            or type(identity.get("read_at_ns")) is not int or identity["read_at_ns"] <= 0):
        raise DiscChanged(_UNAVAILABLE)
    # A finalized sequential disc may report its readable extent without
    # reporting its total capacity. Both are compared as identity evidence;
    # the readable extent is never used to decide whether an ISO will fit.
    has_size = any(positive_sectors(identity.get(key)) for key in ("capacity_sectors", "sectors"))
    if erasing and identity["rewritable"] is not True:
        raise DiscChanged(_NOT_REWRITABLE)
    if erasing and (not has_size
                    or not any(isinstance(identity.get(key), str) and identity[key].strip()
                               for key in ("mid", "medium_id"))):
        raise DiscChanged(_UNAVAILABLE)
    return identity


def matches(expected, current, *, after_erase=False):
    # Fresh snapshots have different timestamps. After an authorized erase the
    # media state and reported free capacity can change on the same disc.
    fields = _STABLE if after_erase else _FIELDS
    return all(expected.get(key) == current.get(key) for key in fields)


def check_identity(drive, expected, *, after_erase=False):
    """With the caller's write lock held, fail before submitting a destructive operation."""
    try:
        current = require_identity(read_identity(drive))
    except DiscChanged as exc:
        raise DiscChanged() from exc
    if not matches(expected, current, after_erase=after_erase):
        raise DiscChanged()


def encode_expected(drive, identity):
    return json.dumps({"drive": drive, "identity": identity}, separators=(",", ":"))


def expected_for_write(drive, *, erasing=False):
    encoded = os.environ.get(EXPECTED_ENV)
    if encoded is None:
        return require_identity(read_identity(drive), erasing=erasing)
    try:
        saved = json.loads(encoded)
        if saved["drive"] != drive:
            raise DiscChanged()
        return require_identity(saved["identity"], erasing=erasing)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        raise DiscChanged(_UNAVAILABLE) from exc
