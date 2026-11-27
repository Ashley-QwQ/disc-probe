"""Random-data image for full-disc timing calibration (`geo`).

Pure single-byte textures make the GH70N retry and change speed, so the ladder needs
a disc that reads like ordinary data. Seeded random bytes everywhere, plus the empty
ISO 9660 header that burning tools require.

Blu-ray takes the same 2048-byte sectors, so one writer covers both; only the capacity
differs, and `geo --media bd` needs a disc recorded out to a radius it can fit a line
through, which for a single layer means most of 25 GB.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from . import dvd, image_output, iso9660, ui

DEFAULT_SECTORS = 2295104  # fits DVD+R and DVD-R single layer
CHUNK_SECTORS = 8192


def write_iso(path: str, sectors: int = DEFAULT_SECTORS, seed: int = 1, log=print, media="dvd", label=None, geo=None,
              *, disc_id=False, disc_id_code=None) -> None:
    # Validate before opening/truncating any output. With no label the old byte stream is unchanged.
    overlay = None
    spec = None
    if label is not None:
        from .labelsession import measured_label, pending
        if geo:
            if media != 'dvd':
                raise ValueError('--label currently supports DVD only')
            overlay = measured_label(label, sectors, geo)
            spec = overlay.spec
        else:
            spec = pending(label, sectors, media)
            spec['seed'] = seed
            sectors = spec['total_sectors']
    elif geo:
        raise ValueError('--geo requires --label')
    from . import discid
    identity = None
    if discid.requested(disc_id, disc_id_code):
        discid.positions(sectors)  # after the pending layout chooses the first-session end
        identity = discid.create(code=disc_id_code, command="random", seed=seed, textures=["RND"])
        discid.encode_copy(identity, 0)
        if spec is not None:
            metadata = [spec['marker_lba']]
            if any(a <= marker < b for a,b in discid.layout(sectors, media)['overwritten_lba'] for marker in metadata):
                raise ValueError('identity slot overlaps label metadata')
            spec['disc_identity_layout'] = discid.layout(sectors, media)
        discid.notice()
    if media == "cd":
        from . import cd, cdimage
        cd.check_capacity(sectors)
        cdimage._new_paths(path, ".random.json")
    elif media == "bd":
        from .bdexport import BD_SECTORS_PER_LAYER
        if sectors > BD_SECTORS_PER_LAYER:
            raise ValueError(f"{sectors:,} sectors do not fit on a single-layer Blu-ray "
                             f"({BD_SECTORS_PER_LAYER:,}); lower --sectors")
    with ui._whole_or_gone(path):
        problems = _write_checked(path, sectors, seed, log, media, overlay, spec, identity)
    if problems:
        raise ValueError('随机镜像未通过自检。 / Random image failed verification: ' + '; '.join(problems[:5]))


def _write_checked(path, sectors, seed, log, media, overlay, spec, identity):
    from . import discid
    from .randomlabel import PENDING_LBA, marker

    samples = []
    overwritten = [(16, 21)] if sectors >= 21 else []
    if identity:
        overwritten += discid.layout(sectors, media)['overwritten_lba']
    if spec and spec.get('state') == 'pending':
        overwritten.append((PENDING_LBA, PENDING_LBA + 1))
    rng = np.random.default_rng(seed)
    done, next_report = 0, 0.0
    with open(path, "xb" if media == "cd" else "wb") as f:
        while done < sectors:
            n = min(CHUNK_SECTORS, sectors - done)
            data = rng.integers(0, 256, n * dvd.SECTOR_BYTES, dtype=np.uint8)
            if overlay is not None:
                overlay.patch(data.reshape(n, dvd.SECTOR_BYTES), done)
            for lba in range(done + n - 1, done - 1, -1):
                if not any(a <= lba < b for a, b in overwritten):
                    at = (lba - done) * dvd.SECTOR_BYTES
                    samples.append((lba, data[at:at + dvd.SECTOR_BYTES].tobytes()))
                    break
            f.write(data.tobytes())
            done += n
            if done / sectors >= next_report - 1e-9:   # (steps of 0.01 add up to a hair over 1)
                log(f"  {100 * done / sectors:5.1f} %")
                next_report += getattr(log, "every", 0.2)
    iso9660.add(path, sectors, "DISCPROBE_RANDOM", identity)
    with open(os.path.splitext(path)[0] + '.capacity.json', 'w', encoding='utf-8') as f:
        json.dump(dict(random_mirror_sectors=sectors, geometric_total_sectors=None,
                       blank_writable_sectors=None,
                       uses='random --sectors is this file length; burn checks blank writable capacity'), f, indent=2)
    if spec and spec.get('state') == 'pending':
        with open(path, 'r+b') as f:
            f.seek(PENDING_LBA * 2048)
            f.write(marker(spec))
    spec_path = Path(path).with_suffix('.image.json')
    if spec is not None:
        spec_path.write_text(json.dumps(spec, indent=2), encoding='utf-8')
    else:
        # An overwrite must not attach the previous image's layout to this ISO.
        spec_path.unlink(missing_ok=True)
    return image_output.verify_generated(path, image_output.verify_written_sectors, sectors, samples,
                                         volume=sectors >= 21)
