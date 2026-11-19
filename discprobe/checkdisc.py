"""Experimental PCAL-C round-two photo target; offline DVD image construction."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import numpy as np
from PIL import Image

TARGET_SHA256 = '052d1835137d0b9173251d14ea44212b85acef2e8eb7c3970957114991565be7'
FEATURES = Path(__file__).with_name('data') / 'check_target_features.png'
# Chosen for RITEKF1 DVD-R; unverified on other batches. Order is label identity.
# Source: docs/goals/calib-simple/layout_round2.json, textures.
TEXTURES = (
    'A37062', 'DD5AA565C8A4A565',
    '66C47EC0E4B6D9A37595759971AD66A67EC0E27BF894EE75B4CAEB66AD',
    'CC67', 'F9', '957CD4D880B2D5F2BDD2CB98FBD1D2DBD49569ECD8C5DBD2',
    '8DCDE6FBC0CDCBD5A3', 'E683D7787D15C08ED5912A978345D8858D8F2A2AFB8B',
    '8D91858EC8859195D18B92', 'RND',
)
RANDOM = ((24.6, 26.0), (57.85, 58.198))


def build_design() -> np.ndarray:
    """Rebuild target_B + round2.artifacts at the original 20 um cell centres.

    The PNG is the original boolean features.npy, losslessly packed as one bit
    per cell. Keep the uint64 hash, radius inequalities and row order unchanged.
    """
    with Image.open(FEATURES) as image:
        if image.mode != '1' or image.size != (6000, 6000):
            raise ValueError('The packaged check-disc feature map is invalid.')
        features = np.asarray(image, dtype=bool)
    labels = np.empty((6000, 6000), dtype=np.uint8)
    axis = (np.arange(6000) + .5) * .02 - 60
    ix = np.arange(6000, dtype=np.uint64)[None, :]
    for y0 in range(0, 6000, 200):
        radius = np.hypot(axis[None, :], axis[y0:y0+200, None])
        iy = np.arange(y0, y0+len(radius), dtype=np.uint64)[:, None]
        with np.errstate(over='ignore'):
            h = (ix + iy * 6000 + np.uint64(20261111)) * np.uint64(0x9E3779B97F4A7C15)
            h = (h ^ (h >> 30)) * np.uint64(0xBF58476D1CE4E5B9)
            h = (h ^ (h >> 27)) * np.uint64(0x94D049BB133111EB)
            h = h ^ (h >> 31)
        bright = (1 + h % 8).astype(np.uint8)
        block = bright.copy()
        block[features[y0:y0+len(radius)]] = 0  # polarity B
        rim = (radius >= 57.1) & (radius <= 57.7)
        block[rim] = bright[rim]
        block[(radius < 24.6) | (radius > 58.)] = 9
        for lo, hi in RANDOM:
            block[(radius >= lo) & (radius < hi)] = 9
        labels[y0:y0+len(radius)] = block
    return labels


def run(args):
    """Build and verify a target using timing geometry only, before any photo L."""
    from . import coverage, guide, image_output, imagedisc, ui
    from .works_link import check_work, image_completed

    path = Path(args.geo)
    if path.is_dir():
        path /= 'summary.json'
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
        fit = document['fit']
        if fit.get('media', 'dvd') != 'dvd':
            raise ValueError('The check disc is for DVD only; CD and Blu-ray are not supported yet.')
        u, v, bit = (float(fit[k]) for k in ('u', 'v', 'bit_nm_assumed'))
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('Use the geo run folder or its summary.json with a DVD geometry fit.') from None
    if not all(np.isfinite(x) and x > 0 for x in (u, v, bit)):
        raise ValueError('The DVD geometry fit must have positive finite u, v and bit length.')
    warning = coverage.range_warning(fit, [26.2, 57.0])
    if warning:
        raise ValueError('The measured geometry does not cover the photo target reliably from 26.2 to 57.0 mm; '
                         're-measure this batch with the new geo; no new burn is needed. ' + warning)
    total = args.sectors
    if total is None:
        last = (document.get('setup') or {}).get('last_lba')
        if type(last) is not int or last < 0:
            raise ValueError('The geo run has no known sector count; give --sectors N.')
        total = last + 1
    if type(total) is not int or total <= 32:
        raise ValueError('Give a sector count greater than 32 so the check disc can be written and verified.')
    if not args.output:
        args.output = 'iso/check-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.iso'
    check_work(args)
    design = build_design()
    meta = dict(check_disc=True, design='pcal round2', geometry_from=str(path.resolve()), experimental=True)
    print('Experimental photo check disc; textures chosen for RITEKF1 DVD-R, unverified on other batches.')
    with ui.writing(args.output, total) as log:
        spec = imagedisc.write_iso(args.output, design, u, v, bit, total,
                                  textures=TEXTURES, lead_lba=0, meta=meta, log=log)
        problems = image_output.verify_generated(args.output, imagedisc.verify_iso, design, u, v, bit, total,
                                                  textures=TEXTURES, lead_lba=0, samples=300)
    if problems:
        raise ValueError('Check-disc verification failed: ' + '; '.join(problems[:5]))
    print(f'Verified: 300 sampled sectors match the design. Spec: {spec}')
    image_completed(args)
    ui.iso_ready(args.output)
    for line in guide.burn_steps(args.output):
        print(line)
    print('After burning, photograph it from the page (or photo --run '
          f'{guide.quote(str(path.parent))} --disc-id <code>).')


def command(args):
    try:
        run(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
