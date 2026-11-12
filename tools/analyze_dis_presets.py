"""Reproducible full-data-area angle audit; offline and drive-free."""
import json
import argparse
import hashlib
from pathlib import Path

import numpy as np

from discprobe import bdexport, disexport, presets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--community', type=Path, default=Path('D:/disc-probe/data/community-calibrations/dis-github.json'))
    args = parser.parse_args()
    root = Path('tests/data/dis-presets')
    result = {'samples': 20001, 'radius_grid': disexport.GRID,
              'alignment': 'subtract mean angle; one free overall rotation', 'media': {}, 'fixture_approximation_max': {}}
    for media in ('cd', 'dvd', 'bd'):
        file = next(root.glob(f'*-builtin-{media}-0.json'))
        row = presets.parse(file.read_text(encoding='utf-8'))['entries'][0]
        fit, p = row['fit'], row['preset']
        total = p.get('sectors', p.get('totalSectors'))
        bit, bits = presets.density(media)
        if media == 'bd':
            out = bdexport.catalog_entry(bdexport.preset({}, total, 'audit', 'audit', 'synthetic audit',
                inner_mm=p['innerRadiusMm'], pitch_um=fit['pitch_um_at_bit']))
        else:
            converted = disexport.fit_preset(fit['u'], fit['v'], bit, total,
                p['innerRadiusMm'], p['outerRadiusMm'], sector_bits=bits)
            out = disexport.preset_json(converted, total, bit, 'audit', 'audit', 'synthetic audit', media)
        n, th, _ = disexport.dis_angle_map(out['innerRadiusMm'], out['outerRadiusMm'],
            *(out.get(k, 0) for k in presets.PITCH), total, bit, bits)
        check = np.linspace(0, total * bits, 20001)
        d = np.degrees(np.interp(check, n, th) - disexport.target_angle(check, fit['u'], fit['v'], bit))
        d -= d.mean()
        back, comparison = presets.geometry(out, media)
        roundtrip = np.degrees(disexport.target_angle(check, back['u'], back['v'], bit)
                               - disexport.target_angle(check, fit['u'], fit['v'], bit))
        roundtrip -= roundtrip.mean()
        result['media'][media] = {'dp_dis_dp_max_angle_error_deg': float(np.max(np.abs(roundtrip))),
            'dp_to_dis_max_angle_error_deg': float(np.max(np.abs(d))),
            'max_map_checked_leg_error_deg': max(float(np.max(np.abs(d))), comparison['max_angle_error_deg']),
            'input': file.name, 'tolerance_deg': .003,
            'back_import': comparison}
    result['fixtures'] = []

    def record(row, **identity):
        return dict(identity, media=row.get('media'), valid=row['valid'],
                    accepted=bool(row.get('image_compatible')), status=row.get('status'),
                    comparison=row.get('comparison'), issues=row.get('issues', []))

    for file in sorted(root.glob('*.json')):
        try:
            rows = presets.parse(file.read_text(encoding='utf-8'))['entries']
        except ValueError as exc:
            result['fixtures'].append(dict(file=file.name, accepted=False, comparison=None, issues=[str(exc)]))
            continue
        for row in rows:
            result['fixtures'].append(record(row, file=file.name, index=row['index'],
                                             id=row['preset'].get('id') if isinstance(row['preset'], dict) else None))
            if not row['valid']: continue
            media = row['media']; error = row['comparison']['max_angle_error_deg']
            previous = result['fixture_approximation_max'].get(media, {}).get('max_angle_error_deg', -1)
            if error > previous:
                result['fixture_approximation_max'][media] = {**row['comparison'], 'file': file.name,
                    'id': row['preset']['id'], 'image_compatible': row['image_compatible']}
    raw = args.community.read_bytes()
    result['community_source'] = dict(path=str(args.community), sha256=hashlib.sha256(raw).hexdigest())
    result['community'] = []
    for entry in json.loads(raw)['entries']:
        posted = entry.get('parameters') or {}
        p = {**posted, 'id': entry['id'], 'displayName': entry['disc'].get('brand') or entry['id'],
             'description': 'Community starting point ' + entry['source_url']}
        row = presets.parse(json.dumps(p), media=entry['media'])['entries'][0]
        result['community'].append(record(row, id=entry['id'], source_url=entry['source_url'],
            complete=all(k in posted for k in ('innerRadiusMm', 'outerRadiusMm', 'sectors' if entry['media']=='cd' else 'totalSectors')),
            pitch_fields=any(k in posted for k in presets.PITCH),
            nonzero_pitch=any(posted.get(k, 0) != 0 for k in presets.PITCH)))
    rows = result['community']
    result['summary'] = dict(records=len(rows), complete=sum(r['complete'] for r in rows),
        pitch_fields=sum(r['pitch_fields'] for r in rows), nonzero_pitch=sum(r['nonzero_pitch'] for r in rows),
        usable=sum(r['accepted'] for r in rows),
        usable_nonzero_pitch=sum(r['accepted'] and r['nonzero_pitch'] for r in rows))
    result['conversion'] = dict(samples=20001, angle_limit_deg=.01, radius_limit_mm=.005,
        max_degree=16, alignment='sector-zero anchored; signed data-side unwrapped angles',
        model='exact DIS arc integrands; constant CD area rule; BD unchanged')
    Path('docs/dis-presets/angle-audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    # Keep the audit tables generated by the same inputs and decisions as the JSON.
    report = Path('docs/dis-presets/REPORT.md')
    marker = '\n## Pitch correction follow-up (2026-11-12)\n'
    existing = report.read_text(encoding='utf-8')
    verification_marker = '\n## Pitch follow-up verification\n'
    verification = verification_marker + existing.split(verification_marker, 1)[1] if verification_marker in existing else ''
    text = existing.split(marker)[0]
    text += marker + '\n' + (
        'This section supersedes the earlier card\'s archive-only variable-pitch behavior above. '
        'CD/DVD imports now use the DIS arc-length model and the existing DP polynomial correction format. '
        'Degrees 0 through 16 are tried in order; the first with maximum unwrapped angle residual <= 0.01 degrees is selected. '
        'The full-area check uses 20,001 positions including sector zero and capacity. '
        'Radius residual must also be <= 0.005 mm. The fit range is the full DP radius interval; the correction is held constant outside it. '
        'Angles are anchored at sector zero; no mean rotation or modulo is removed for this conversion. '
        'The polynomial uses signed data-side angles: phi = -DIS accumulated magnitude + DP magnitude, '
        'because `_sample` starts at negative DP angle and adds phi. BD retains its previous comparison and has no DP image writer.\n\n'
        'Accepted means usable as DP image geometry, not physically calibrated. Converted status is '
        '“从 DIS 导入，换算成 DP 修正（未经 DP 实测）”; nominal status stays nominal and CD L remains unknown. '
        'Accepted corrections are sibling JSON files linked from their DP wrappers. CLI image resolves that link; '
        'the page explicitly selects compatible imported geometry and uses the same image command. '
        'The original DIS object is untouched and export ignores the DP-side correction.\n\n')
    text += f"Community source SHA-256: `{result['community_source']['sha256']}`. "
    text += (f"Of {len(rows)} records, {result['summary']['complete']} have complete geometry fields. "
             f"This read-only snapshot has {result['summary']['pitch_fields']} records carrying pitch fields and "
             f"{result['summary']['nonzero_pitch']} with nonzero pitch, rather than the card's 134/123. "
             f"**{result['summary']['usable_nonzero_pitch']} nonzero-pitch presets are now usable**; "
             f"{result['summary']['usable']} records total are usable. The denominator 123 cannot be reproduced from this source; "
             'no missing parameters, density aliases or unknown extensions were silently converted.\n\n')
    for title, records in [('Fixtures (every file and entry)', result['fixtures']), ('Community (all 174 records, including incomplete refusals)', rows)]:
        text += f'### {title}\n\n| Input / id | DP image | Max angle ° | Max radius mm | Degree | Reason if refused |\n|---|---|---:|---:|---:|---|\n'
        for r in records:
            c = r['comparison'] or {}
            fmt = lambda k: f"{c[k]:.12g}" if c.get(k) is not None else 'N/A'
            name = (r.get('file', '') + ' ' + str(r.get('id', ''))).strip()
            reason = '' if r['accepted'] else '; '.join(s for s in r['issues'] if any(w in s.lower() for w in ('exceeds', 'unknown fields', 'bd geometry', 'must', 'unsupported', 'invalid')))
            text += f"| {name} | {'accepted' if r['accepted'] else 'refused'} | {fmt('max_angle_error_deg')} | {fmt('max_radius_error_mm')} | {c.get('polynomial_degree') if c.get('polynomial_degree') is not None else 'none'} | {reason or ('invalid/incomplete document' if not r['accepted'] else '')} |\n"
        text += '\n'
    report.write_text(text + verification, encoding='utf-8')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__': main()
