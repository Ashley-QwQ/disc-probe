"""Strict task gate: numerical regressions cannot waive unproved requirements."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent / 'slim_artifacts'
read = lambda name: json.loads((HERE / name).read_text(encoding='utf-8'))
recorded = read('recorded.json')
solutions = [s for r in recorded['runs'] for f in r['polyfit'].values()
             if all('value' in f.get(k, {}) for k in ('old', 'new')) for s in f.get('solutions', [])]
solutions += [s for f in recorded['joint'] if all('value' in f.get(k, {}) for k in ('old', 'new')) for s in f.get('solutions', [])]
presets = [r['disexport'] for r in recorded['runs'] if 'delta' in r.get('disexport', {})]
presets += [r for r in recorded['archived_presets'] if 'delta' in r]
cli = read('cli.json')
checks = dict(filters=all(r['passed'] for r in read('filters.json')),
              special=all(r['passed'] for r in read('special.json')),
              actual_f_tests=all(r['passed'] for r in read('special_actual.json')),
              iso=all(r.get('identical', False) for r in read('iso.json')),
              accepted_fit_differences=all(s['delta_observation_sigma'] < 1e-3 and s['delta_parameter_sigma'] < 1e-3 for s in solutions),
              accepted_fit_numerical_stationarity=all(s[k]['stationary'] for s in solutions for k in ('old', 'new')),
              preset_mapping_below_noise=all(p['full_map_max_difference_deg'] < .05 * 1e-3 for p in presets),
              preset_mapping_below_reported_source_sigma=all(p['full_map_max_difference_deg'] <
                  p['source_uncertainty']['angle_sigma_measured_span_deg'] * 1e-3
                  for p in presets if p.get('source_uncertainty', {}).get('angle_sigma_measured_span_deg', 0) > 0),
              preset_radius_below_source_sigma=all(p['delta']['innerRadiusMm'] < p['inner_radius_sigma_mm'] * 1e-3
                                                  for p in presets if p.get('inner_radius_sigma_mm', 0) > 0),
              complete_cli_output=all(r['stdout_identical'] and r['same_error'] for r in cli['runs']) and
                                  all(r['stdout_identical_except_destination'] for r in cli['joint']),
              tile_csv=read('photo.json')['csv_byte_identical'], beacon_outputs=read('beacon.json')['identical'] and read('beacon.json')['disc_identical'],
              source_no_scipy=not read('provenance.json')['production_scipy_imports'],
              scsi_unchanged=read('provenance.json')['protected']['identical'],
              retained_dependencies_unchanged=not read('retained_dependencies.json')['changed'],
              final_archives=all(read('final-artifacts.json')[k]['source_manifest_verified'] for k in ('core', 'full-win64')))
gaps = [
    'Nelder-Mead photo objective is not everywhere differentiable; first-order optimality is unproved.',
    'Photo pose covariance is not defined/reported by the existing model.',
    'FFT binary implementation round-off theorem is conditional, not machine-formally verified.',
    'Finite-difference certificates do not enclose the true derivative with intervals.',
    'Local rank and sampled pose alternatives do not detect every remote minimum.',
    '40 recorded photo summaries lack their original photos; four angular summaries lack targets.csv.',
    'Three complete geo_polyfit CLI replays fail on both backends; historical saved preset is not reproduced by current baseline either.'
    ,'Additional conservative 0.001 * 0.05-degree full-map gate fails for geo-H-20261106-014530: 0.000190106 degrees; retain this failed extra gate even though the source reports much larger uncertainty.'
]
result = dict(numerical_checks=checks, numerical_checks_pass=all(checks.values()), formal_equivalence_pass=False,
              strict_gate='FAIL', gaps=gaps, note='Do not publish this local verification pack as formally equivalent.')
(HERE / 'acceptance.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(dict(numerical_checks_pass=all(checks.values()), formal_equivalence_pass=False, strict_gate='FAIL')))
raise SystemExit(1)
