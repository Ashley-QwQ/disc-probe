"""Create field tables and manifest evidence from the completed offline checks."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from slim_support import ROOT, ARTIFACTS, allowed, low_priority
low_priority()
import numpy as np
from discprobe.disexport import dis_angle_map


def save(name, value):
    (ARTIFACTS / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def map_difference(record, sectors, bit_nm, sector_bits):
    if not all('value' in record.get(k, {}) for k in ('old', 'new')):
        return
    old, new = record['old']['value'], record['new']['value']
    # Use the source medium's actual channel-bit length and sector encoding.
    # Fractional capacity normalizes n, but accumulated angle still scales
    # with sector_bits*bit_nm and must not be evaluated as a different medium.
    maps = [dis_angle_map(f['innerRadiusMm'], f['outerRadiusMm'], f['pitchLinear'], f['pitchQuadratic'],
                          f['pitchCubic'], sectors, bit_nm, sector_bits) for f in (old, new)]
    n = np.linspace(0, sectors * sector_bits, 20001)
    d = np.degrees(np.interp(n, maps[0][0], maps[0][1]) - np.interp(n, maps[1][0], maps[1][1]))
    # Export permits a free rotation; compare the same mean-removed map.
    d -= d.mean()
    record['full_map_max_difference_deg'] = float(np.max(np.abs(d)))


def zip_manifest(path):
    z = zipfile.ZipFile(path)
    entries = {}
    for e in z.infolist():
        if not allowed(e.filename):
            raise ValueError('excluded zip entry')
        if not e.is_dir():
            entries[e.filename.split('/', 1)[1]] = e
    return z, entries


def main():
    recorded = json.loads((ARTIFACTS / 'recorded.json').read_text(encoding='utf-8'))
    from discprobe import cd
    for rec in recorded['runs']:
        f = json.loads((Path(rec['path']) / 'summary.json').read_text(encoding='utf-8'))['fit']
        rec.get('disexport', {}).setdefault('source_uncertainty', {}).update({k: f[k] for k in
            ('u_sigma', 'v_sigma', 'angle_sigma_deg', 'angle_sigma_measured_span_deg', 'measured_span_mm') if k in f})
        map_difference(rec.get('disexport', {}), f.get('sectors', cd.CAPACITY if f.get('media') == 'cd' else 2295104),
                       f['bit_nm_assumed'], 57624 if f.get('media') == 'cd' else 38688)
    for rec in recorded['archived_presets']:
        archived = json.loads(Path(rec['path']).read_text(encoding='utf-8'))
        source = json.loads(Path(rec['source']['geo']).read_text(encoding='utf-8'))['fit']
        map_difference(rec, archived['preset'].get('totalSectors', archived['preset'].get('sectors')),
                       source['bit_nm_assumed'], 57624 if source.get('media') == 'cd' else 38688)
    save('recorded.json', recorded)
    inventory = json.loads((ARTIFACTS / 'inventory.json').read_text(encoding='utf-8'))
    photos = []
    for filename in inventory['json_files']:
        try:
            obj = json.loads(Path(filename).read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(obj, dict) and obj.get('photo'):
            matches = [p['path'] for p in inventory['photos'] if Path(p['path']).name == obj['photo']]
            photos.append(dict(summary=filename, expected_photo=obj['photo'], inputs=matches,
                               status='AVAILABLE' if matches else 'INPUT_MISSING'))
    save('photo_inputs.json', photos)
    old_path = Path('D:/disc-probe-dist/disc-probe-0.1.2.1-full-win64.zip')
    new_path = Path('D:/disc-probe-dist/slim-20261111/disc-probe-slim-20261111-full-win64.zip')
    old_zip, old = zip_manifest(old_path)
    new_zip, new = zip_manifest(new_path)
    removals = []
    for name in sorted(old.keys() - new.keys()):
        if '/scipy' in name.lower():
            reason = 'SciPy numerical dependency replaced; old backend exists only in test harness'
        elif name.endswith(('f2py.exe', 'numpy-config.exe')):
            reason = 'NumPy development CLI; no application/tool invokes Fortran compilation or build-configuration CLI'
        elif name.endswith(('_sqlite3.pyd', 'sqlite3.dll')):
            reason = 'No application/tool database feature or import; not loaded by checks'
        else:
            reason = 'REVIEW_REQUIRED'
        removals.append(dict(path=name, bytes=old[name].file_size, compressed_bytes=old[name].compress_size, reason=reason))
    unchanged, changed = [], []
    for name in sorted(old.keys() & new.keys()):
        if any(s in name for s in ('/PIL/', '/pillow-', '/numpy/', '/numpy-', '/numpy.libs/')):
            a, b = old_zip.read(old[name]), new_zip.read(new[name])
            (unchanged if a == b else changed).append(name)
    save('removals.json', removals)
    save('retained_dependencies.json', dict(unchanged=unchanged, changed=changed))
    groups = []
    for rec in recorded['runs']:
        for order, result in rec.get('polyfit', {}).items():
            if all('value' in result.get(k, {}) for k in ('old', 'new')):
                groups.append(('polyfit', rec['path'], order, result))
        if 'delta' in rec.get('geo', {}):
            groups.append(('geo', rec['path'], '', rec['geo']))
        if 'delta' in rec.get('disexport', {}):
            groups.append(('disexport', rec['path'], '', rec['disexport']))
    for rec in recorded['joint']:
        if all('value' in rec.get(k, {}) for k in ('old', 'new')):
            groups.append(('joint', 'GH70N 5 runs', str(rec['order']), rec))
    for rec in recorded['archived_presets']:
        if 'delta' in rec:
            groups.append(('archived_preset', rec['path'], '', rec))
    cli_path = ARTIFACTS / 'cli.json'
    if cli_path.exists():
        cli = json.loads(cli_path.read_text(encoding='utf-8'))
        for rec in cli['joint']:
            for name in ('summary.json', 'correction.json'):
                if name + '_delta' in rec:
                    groups.append(('joint_cli_' + name, 'GH70N 5 runs', rec['mode'], dict(delta=rec[name + '_delta'])))
    fields = {}
    for group, path, order, result in groups:
        for field, delta in result.get('delta', {}).items():
            family = re.sub(r'\[\d+\]', '[]', field)
            family = re.sub(r'\.\d{5,}', '.*', family)
            key = group, family
            if key not in fields or delta > fields[key]['max_delta']:
                fields[key] = dict(group=group, field=family, max_delta=delta, input=path, order=order)
    for row in fields.values():
        group, field = row['group'], row['field']
        row['printed_precision'] = 'JSON full float; no fixed decimal guarantee'
        row['uncertainty_comparison'] = 'not separately reported for this field'
        if group in ('polyfit', 'joint'):
            row['uncertainty_comparison'] = 'solution covariance and weighted observation-sigma comparison in recorded.json'
            if field in ('rms_deg', 'resid_deg[]', 'span_sigma_deg'):
                row['printed_precision'] = '.3f degrees; source sigma floor .05 degrees'
            elif field == 'b[]':
                row['printed_precision'] = '.3e'
            elif field == 'u':
                row['printed_precision'] = 'converted r0_mm .5f'
            elif field == 'v':
                row['printed_precision'] = 'converted pitch_um .6f'
            elif field == 'chi2':
                row['printed_precision'] = 'chi2/dof .2f'
        if group in ('disexport', 'archived_preset'):
            if field in ('innerRadiusMm', 'outerRadiusMm'):
                row['printed_precision'] = '.9f mm'
            elif field in ('pitchLinear', 'pitchQuadratic', 'pitchCubic'):
                row['printed_precision'] = '.3e'
            elif field in ('max_angle_diff_deg', 'rms_angle_diff_deg'):
                row['printed_precision'] = '.4f degrees'
            row['uncertainty_comparison'] = 'compare map difference to source angle noise; inner radius also to recorded u_sigma; shape covariance not reported'
        if group == 'geo':
            row['uncertainty_comparison'] = 'all deltas exactly zero; same reconstructed summary uncertainty'
    with (ARTIFACTS / 'field_deltas.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['group', 'field', 'max_delta', 'printed_precision', 'uncertainty_comparison', 'input', 'order'])
        writer.writeheader()
        writer.writerows(fields[k] for k in sorted(fields))
    save('field_deltas.json', [fields[k] for k in sorted(fields)])
    print(json.dumps(dict(removals=len(removals), unreviewed_removals=sum(r['reason'] == 'REVIEW_REQUIRED' for r in removals),
                          unchanged_dependency_files=len(unchanged), changed_dependency_files=len(changed),
                          photo_records=len(photos), missing_photos=sum(p['status'] == 'INPUT_MISSING' for p in photos))))


if __name__ == '__main__':
    main()
