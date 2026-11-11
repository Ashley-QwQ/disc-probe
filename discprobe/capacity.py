"""Recordable area, deliberately separate from READ CAPACITY's readable length."""
from __future__ import annotations

import json
from pathlib import Path


def positive_sectors(value) -> bool:
    return type(value) is int and 0 < value < 0xFFFFFFFF


def recordable_capacity(report: dict) -> tuple[int, str] | None:
    """Use only fields describing the whole medium, never a written track's size.

    DVD-R format 0Eh is prerecorded (unaffected by closing a short burn); its
    inclusive physical end address is relative to the DVD data-zone PSN 30000h.
    Normal CD ATIP and disc-information lead-out addresses are exclusive LBAs.
    DVD physical format 00h/10h and track free/reserved sizes are intentionally
    excluded: borders, reservations and finalization can limit them to the burn.
    """
    def parsed(key):
        entry = report.get(key) or {}
        return (entry.get('parsed') or {}) if entry.get('status', 0) == 0 and not entry.get('error') else {}

    profile = parsed('configuration').get('current_profile')
    track = parsed('track_1')
    if track.get('blank') is True and track.get('track_start') == 0 and positive_sectors(track.get('free_blocks')):
        return track['free_blocks'], 'free space of this blank disc'
    pre = parsed('dvd_prerecorded_0e')
    # Single-layer DVD-R/RW sequential. A finalized DVD-R reads back as DVD-ROM (0x10) on the GH70N, but still answers
    # format 0Eh with its MID, which a pressed DVD-ROM cannot.
    if profile in (0x11, 0x14) or (profile == 0x10 and pre.get('manufacturer_id')):
        raw = pre.get('last_recordable_address')
        if type(raw) is int and 0 <= raw <= 0xFFFFFF:
            # The pre-pit field holds the ECC block number, one's-complemented (GH70N, RITEKF1: fd9ed8 -> block
            # 0x26127 -> last PSN 0x26127F -> 2298496 sectors, the 4.7 GB DVD-R capacity).
            end = (~raw & 0xFFFFFF) * 16 + 15
            sectors = end - 0x30000 + 1
            if 0 < sectors <= 2_400_000:
                return sectors, 'DVD-R prerecorded last recordable address (format 0Eh)'
    if profile in (0x09, 0x0A):
        atip = parsed('atip')
        # Nonzero subtypes may encode a special additional lead-out instead.
        end = atip.get('last_leadout_start_lba')
        if atip.get('disc_subtype') == 0 and positive_sectors(end):
            return end, 'last possible lead-out start in CD ATIP'
        di = parsed('disc_information')
        msf = di.get('last_possible_leadout_msf')
        if (isinstance(msf, list) and len(msf) == 3
                and all(type(v) is int for v in msf)
                and 0 <= msf[0] < 90 and 0 <= msf[1] < 60 and 0 <= msf[2] < 75):
            from .mmc import msf_to_lba
            end = msf_to_lba(*msf)
            if positive_sectors(end):
                return end, 'last possible lead-out start in CD disc information'
    return None


def catalogue_capacity(mid: str | None, media: str, root: Path | None = None) -> tuple[int, str] | None:
    """Optional presets/catalogue.json: {MID: {sectors: N, media: dvd}}.

    Capacity aliases allow catalogue entries using the preset's totalSectors or
    the disc report's capacity_sectors. Geometry/readable lengths are never used.
    """
    if not mid:
        return None
    path = (root or Path.cwd()) / 'presets' / 'catalogue.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    entry = data.get(mid) if isinstance(data, dict) else None
    if not isinstance(entry, dict) or entry.get('media', media) != media:
        return None
    values = [entry[key] for key in ('capacity_sectors', 'sectors', 'totalSectors') if key in entry]
    if values and all(positive_sectors(v) and v == values[0] for v in values):
        return values[0], f'presets/catalogue.json MID {mid}'
    return None
