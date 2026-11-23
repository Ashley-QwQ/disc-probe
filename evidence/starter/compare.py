"""Compare archived DVD geometry at equal channel addresses, without drive access."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import permutations
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from discprobe import calib, coverage, imagedisc, pcal
from evidence.eval_grid import LIMITS, aggregate


DRAWING = (25.0, 57.0)
CHECK = (26.2, 57.0)  # checkdisc.run
DRAWING_RADII = np.linspace(*DRAWING, 3201)
EXCLUDE = '*[bB][lL][iI][nN][dD]*'
EXCLUDED = re.compile(EXCLUDE[1:-1])
MODEL = 'HL-DT-ST DVD-RAM GH70N'

# Older summaries have no identity. These links are documented in KNOWLEDGE.md §6,
# PREREG_remeasure.md, and evidence/geo/gh70n-20261107/README.md.
LEGACY = {
    'rings_disc_summary.json': 'geo-H-20261103-131003',
    'random_disc_summary.json': 'geo-H-20261103-145334',
    'remeasure_ref262336_summary.json': 'geo-H-20261103-181720',
}
DISCS = {
    'geo-H-20261103-131003': ('11-03', 'rings'),
    'geo-H-20261103-145334': ('11-03', 'random'),
    'geo-H-20261103-181720': ('11-03', 'random'),
    'geo-H-20261107-183256': ('11-07', 'B'),
    'geo-H-20261107-191044': ('11-07', 'A'),
    'geo-H-20261107-201833': ('11-07', 'A'),
    'geo-H-20261107-204800': ('11-07', 'A'),
    'geo-H-20261107-210507': ('11-07', 'A'),
}


def file_paths(probe, integ, archive):
    sources = (
        (probe / 'results', ['**/geo-*/summary.json']),
        (probe / 'evidence/geo', ['**/geo-*/summary.json', *LEGACY]),
        (integ / 'evidence', ['**/geo-*/summary.json', '**/cd-geo-*/**/summary.json', *LEGACY]),
        (integ / 'presets', ['summary.json']),
        (archive, ['**/untracked/results*/geo-*/summary.json']),
    )
    for root, globs in sources:
        if EXCLUDED.search(str(root.resolve())) or not root.is_dir():
            raise ValueError(f'unavailable or excluded scan root: {root}')
        args = ['rg', '--files', '--hidden', '--no-ignore']
        for glob in (*globs, f'!**/{EXCLUDE}/**', f'!**/{EXCLUDE}'):
            args.extend(('-g', glob))
        result = subprocess.run([*args, '--', root], encoding='utf-8', capture_output=True)
        if result.returncode not in (0, 1) or result.stderr:
            raise RuntimeError(f'rg error for {root}: {result.stderr}')
        for name in sorted(result.stdout.splitlines()):
            path = Path(name)
            relative = path.relative_to(root).parts
            if root == probe / 'results' and (len(relative) != 2 or not relative[0].startswith('geo-')):
                continue
            if root == archive and (len(relative) != 5 or relative[1] != 'untracked'):
                continue
            if not EXCLUDED.search(str(path)) and not EXCLUDED.search(str(path.resolve())):
                yield path


def inventory(paths):
    groups, ignored = {}, {}
    for path in paths:
        raw = path.read_bytes()
        doc = json.loads(raw)
        fit = doc.get('fit') or {}
        setup = doc.get('setup') or {}
        media = fit.get('media') or setup.get('family')
        identity = doc.get('identity') or {}
        name = LEGACY.get(path.name, path.parent.name)
        simulated = any('-z-' in part.casefold() or 'sim' in part.casefold() for part in path.parts)
        mid, model = identity.get('disc'), identity.get('drive')
        if name in DISCS:
            mid, model = mid or 'RITEKF1', model or MODEL
        if all(isinstance(fit.get(k), (float, int)) and math.isfinite(fit[k]) and fit[k] > 0
               for k in ('u', 'v', 'bit_nm_assumed')) and (simulated or (media == 'dvd' and mid)):
            correction = fit.get('correction_file')
            correction_path = None
            if correction:
                correction_path = path.parent / correction
                if (Path(correction).name != correction or EXCLUDED.search(str(correction_path))
                        or EXCLUDED.search(str(correction_path.resolve()))):
                    raise ValueError(f'unsafe correction path in {path}')
            sha = hashlib.sha256(raw).hexdigest()
            key = (simulated, name, fit['u'], fit['v'], fit['bit_nm_assumed'], fit.get('reference_lba'))
            record = groups.setdefault(key, dict(
                name=name, simulated=simulated, media=media, mid=mid.strip().upper() if mid else None,
                model=model, firmware=identity.get('firmware') or ('NYA2' if name in DISCS else None),
                device_id=(doc.get('drive_identity') or {}).get('device_id') or identity.get('device_id'),
                pack_disc=DISCS.get(name), fit=fit, last_lba=setup.get('last_lba'), sources=[],
                correction_path=correction_path.as_posix() if correction_path else None))
            record['sources'].append(dict(path=path.as_posix(), sha256=sha))
            continue
        reason = 'missing documented MID or angular fit' if media == 'dvd' else f'outside DVD scope ({media})'
        ignored[path.as_posix()] = reason
    return sorted(groups.values(), key=lambda row: (row['simulated'], row['name'])), ignored


def radius_at(bits, fit):
    return fit['bit_nm_assumed'] * 1e-6 * np.sqrt(fit['u'] ** 2 + fit['v'] * bits / math.pi)


def make_map(record):
    fit = record['fit']
    correction_path = record['correction_path']
    correction = imagedisc.load_correction(correction_path) if correction_path else None

    def at(bits):
        radius = radius_at(bits, fit)
        angle = -calib.theta(bits, fit['u'], fit['v'])
        if correction is not None:
            angle += np.radians(correction(radius))
        return radius, angle

    return at


def compare(source, target, source_map, target_map, photo_radii):
    fit = target['fit']

    def errors(r):
        # A texture written at the address prescribed by A actually lands on B.
        bits = math.pi * ((r / (fit['bit_nm_assumed'] * 1e-6)) ** 2 - fit['u'] ** 2) / fit['v']
        rs, ts = source_map(bits)
        rt, tt = target_map(bits)
        return rs, tt - ts

    # Ideal per-sector votes have the same radial signal in all twelve photo sectors.
    # This isolates geometry; real votes, pose, contrast and group agreement are unmeasured.
    sectors = (np.arange(12) + .5) * (2 * math.pi / 12)
    r = np.tile(photo_radii, len(sectors))
    t = np.repeat(sectors, len(photo_radii))
    phase = errors(r)[1]
    q, residual, _, _ = pcal.fit_votes(t, r, phase)
    l_by_zone = []
    for zone in photo_radii:
        kept = r != zone
        l_by_zone.append(pcal.fit_votes(t[kept], r[kept], phase[kept])[0][1])
    photo_rms = float(np.degrees(np.sqrt(np.mean(residual ** 2))))
    zone_spread = float(np.ptp(l_by_zone))

    def metrics(radii):
        rs, raw = errors(radii)
        after = raw - (q[0] + q[1] / radii)
        centred = raw - raw.mean()
        radial = rs - radii
        pos = lambda angle: float(np.max(np.hypot(radial, 2 * np.sqrt(rs * radii) * np.sin(angle / 2))))
        return dict(raw_rms_deg=rms_deg(raw), before_rms_deg=rms_deg(centred),
                    before_pp_deg=float(np.degrees(np.ptp(raw))), after_rms_deg=rms_deg(after),
                    after_pp_deg=float(np.degrees(np.ptp(after))),
                    after_max_deg=float(np.degrees(np.max(np.abs(after)))),
                    radial_max_mm=float(np.max(np.abs(radial))), raw_pos_max_mm=pos(raw),
                    before_pos_max_mm=pos(centred), after_pos_max_mm=pos(after))

    after = errors(DRAWING_RADII)[1] - (q[0] + q[1] / DRAWING_RADII)
    mids, grid_phase = aggregate([(DRAWING_RADII, np.degrees(after))], hi=55)
    grid = dict(rms=float(np.sqrt(np.mean((grid_phase - grid_phase.mean()) ** 2))),
                pp=float(np.ptp(grid_phase)),
                u=float(abs(np.polyfit((mids - 40) / 14.3, grid_phase, 2)[0])))
    common_radii = DRAWING_RADII
    for record in (source, target):
        intervals = coverage.assess_range(record['fit'], DRAWING)['covered_intervals_mm']
        covered = np.zeros(common_radii.shape, dtype=bool)
        for lo, hi in intervals:
            covered |= (common_radii >= lo) & (common_radii <= hi)
        common_radii = common_radii[covered]
    check_warning = coverage.range_warning(source['fit'], CHECK)
    image_warning = coverage.range_warning(source['fit'], DRAWING)
    target_warning = coverage.range_warning(fit, DRAWING)
    if source['pack_disc'] and target['pack_disc'] and source['pack_disc'][0] == target['pack_disc'][0]:
        relation = 'same_disc' if source['pack_disc'] == target['pack_disc'] else 'same_documented_pack'
    else:
        relation = 'unverified_pack'
    return dict(mid=source['mid'], source=source['name'], target=target['name'], relation=relation,
                matching_model=source['model'] == target['model'], l_mm=float(q[1]),
                **metrics(DRAWING_RADII), grid=grid,
                common_radii_mm=[float(common_radii.min()), float(common_radii.max())] if common_radii.size else None,
                common_metrics=metrics(common_radii) if common_radii.size else None,
                grid_within_limits=all(grid[k] <= LIMITS[k] for k in LIMITS),
                photo_rms_deg=photo_rms, photo_zone_spread_mm=zone_spread,
                photo_within_shape_limits=(photo_rms <= pcal.GATE['rms_deg']
                                           and zone_spread <= pcal.GATE['zone_spread_mm']),
                source_check_warning=check_warning, source_image_warning=image_warning,
                target_image_warning=target_warning)


def rms_deg(radians):
    return float(np.degrees(np.sqrt(np.mean(radians ** 2))))


def community():
    reports = {}
    for rel in ('news/community.json', 'discprobe/web/home/faxnews/community.json'):
        raw = (REPO / rel).read_bytes()
        selected = [r for r in json.loads(raw)['entries']
                    if re.match(r'^RITEKF1\b', r['disc'].get('mid') or '', re.I)]
        reports[rel] = dict(sha256=hashlib.sha256(raw).hexdigest(), entries=selected)
    return reports


def totals(pairs):
    return dict(pairs=len(pairs), photo_shape=sum(p['photo_within_shape_limits'] for p in pairs),
                grid=sum(p['grid_within_limits'] for p in pairs),
                source_check=sum(not p['source_check_warning'] for p in pairs),
                source_image=sum(not p['source_image_warning'] for p in pairs),
                target_image=sum(not p['target_image_warning'] for p in pairs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, default=Path('D:/disc-probe'))
    parser.add_argument('--integ', type=Path, default=Path('D:/dp-dev/integ'))
    parser.add_argument('--archive', type=Path, default=Path('F:/dp-archive/worktree-leftovers-20261116'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if EXCLUDED.search(str(args.out.resolve())) or EXCLUDED.search(str(args.out)):
        parser.error('excluded output path')
    records, ignored = inventory(file_paths(args.probe, args.integ, args.archive))
    real = [r for r in records if not r['simulated']]
    polar = np.arange(pcal.R_MIN, pcal.R_MAX + 1e-6, pcal.DR)
    photo_radii = np.array([polar[(polar >= lo) & (polar <= hi)].mean() for lo, hi in pcal.design_burn().zones])
    maps = {id(r): make_map(r) for r in real}
    pairs = [compare(a, b, maps[id(a)], maps[id(b)], photo_radii)
             for a, b in permutations(real, 2) if a['mid'] == b['mid']]
    by_relation = {relation: totals([p for p in pairs if p['relation'] == relation])
                   for relation in sorted({p['relation'] for p in pairs})}
    result = dict(radii_mm=DRAWING, check_mm=CHECK, photo_radii_mm=photo_radii.tolist(),
                  photo_limits=pcal.GATE, grid_limits_deg=LIMITS, records=records, ignored=ignored,
                  community=community(), totals=totals(pairs), by_relation=by_relation, pairs=pairs)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f"Real DVD runs: {dict(Counter(r['mid'] for r in real))}; simulated runs: {len(records) - len(real)}")
    print(f"All directed pairs: {result['totals']}")
    for relation, counts in by_relation.items():
        print(f'{relation}: {counts}')


if __name__ == '__main__':
    main()
