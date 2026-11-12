"""Measured DVD labels, offline construction or read-only NWA discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import iso9660, randomlabel as L


def geometry(path):
    path = Path(path)
    if path.is_dir():
        path /= 'summary.json'
    raw = path.read_bytes()
    document = json.loads(raw)
    fit = document['fit']
    if (document.get('stopped') or fit.get('media', 'dvd') != 'dvd'
            or fit.get('model') == 'clv' or fit.get('track') == 'audio'):
        raise ValueError('label needs a completed DVD data geo result')
    from .read_completion import sectors
    sectors(fit.get('completion_sectors', 0))
    # Stored u already uses the stored completion convention. Do not apply it twice.
    return fit, dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest())


def measured_label(text, capacity, geo):
    fit, source = geometry(geo)
    label = L.Label(text, capacity, geometry=fit)
    label.spec['geometry_source'] = source
    L.marker(label.spec)  # check size before opening output
    return label


def pending(text, capacity, media):
    label = L.Label(text, capacity, media)
    return dict(kind='random-label', version=2, state='pending', media=media, text=text,
                radius_mm=[L.INNER_MM, L.OUTER_MM], planned_band_mm=[L.INNER_MM, L.OUTER_MM],
                exclude_lba=[L.PENDING_LBA, L.PENDING_LBA + 1], marker_lba=L.PENDING_LBA,
                total_sectors=L.STOP_SECTORS, capacity_sectors=capacity, stop_radius_mm=L.STOP_MM,
                geometry='pending', seed=1)


def disc_state(dev):
    """Read the open track's NWA and capacity, with no write commands."""
    from . import mmc
    def read(cdb, size, parser):
        r = dev.execute(cdb, data_len=size)
        if not r.ok:
            raise ValueError('cannot read DVD session information; use --start-lba explicitly')
        return parser(r.data)
    cfg = read(mmc.get_configuration(), 4096, mmc.parse_configuration)
    if mmc.media_family(cfg.get('current_profile')) != 'dvd':
        raise ValueError('label sessions currently support DVD only')
    disc = read(mmc.read_disc_information(), 34, mmc.parse_disc_information)
    if disc.get('disc_status') != 'incomplete':
        raise ValueError('label needs a recorded open DVD, not a blank or closed disc')
    last = disc.get('last_track_last_session')
    if not last:
        raise ValueError('drive did not report the last recorded track')
    track = read(mmc.read_track_information(last), 48, mmc.parse_track_information)
    if not track.get('nwa_valid'):
        track = read(mmc.read_track_information(0xff), 48, mmc.parse_track_information)
    if not track.get('nwa_valid') or track['next_writable'] <= 0 or track['free_blocks'] <= 0:
        raise ValueError('drive has no valid next writable address')
    return track['next_writable'], track['next_writable'] + track['free_blocks']


def write_iso(path, text, geo, start_lba, capacity=2295104, seed=1, log=print):
    label = measured_label(text, capacity, geo)
    a, b = label.span
    # NWA is the first sector AFTER the drive's border-out/border-in area.
    # For offline construction allow no overlap with the first session, and
    # reserve the demonstrated 47120-sector border plus a conservative guard.
    if not L.STOP_SECTORS + 47120 <= start_lba <= a - 3016 or start_lba % 16:
        raise ValueError('start LBA overlaps the planned border zone or label band; read the current NWA')
    end = b + 3024
    end = (end + 15) // 16 * 16
    if end > capacity:
        raise ValueError('label session exceeds disc capacity')
    label.spec.update(first_lba=start_lba, total_sectors=end, capacity_sectors=capacity, seed=seed,
                      avoid_lba=[[L.STOP_SECTORS, start_lba], [L.PENDING_LBA, L.PENDING_LBA + 1]])
    L.marker(label.spec)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    unfinished = Path(str(path) + iso9660.UNFINISHED)
    unfinished.touch()
    rng = np.random.default_rng(seed)
    # Generate absolute RNG chunks so filler is the same random stream as random.
    with path.open('wb') as stream:
        for first in range(0, end, 8192):
            count = min(8192, end - first)
            data = rng.integers(0, 256, count * 2048, dtype=np.uint8).reshape(count, 2048)
            if first + count <= start_lba:
                continue
            label.patch(data, first)
            stream.write(data[max(0, start_lba - first):].tobytes())
            log(f'  {100 * (first + count - start_lba) / (end - start_lba):5.1f} %')
    path.with_suffix('.image.json').write_text(json.dumps(label.spec, indent=2) + '\n', encoding='utf-8')
    unfinished.unlink()
    return label.spec


def run(args):
    try:
        start, capacity = args.start_lba, args.sectors
        if start is None:
            if not args.drive:
                raise ValueError('label needs --drive to read NWA, or offline --start-lba')
            import sys
            if sys.platform == 'win32':
                from .imapi import ImapiDevice as Device
            else:
                from .device import Device
            with Device(args.drive) as dev:
                start, available = disc_state(dev)
            capacity = min(capacity, available)
        spec = write_iso(args.output, args.text, args.geo, start, capacity)
        print(f"Label session: LBA {start}..{spec['total_sectors']}; append with --expect-start {start}")
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None
