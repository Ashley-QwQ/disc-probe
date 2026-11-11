"""Disk-only home catalogue. Unknown identity and quality stay unknown."""
from pathlib import Path
import csv
import math
import hashlib
import json
from . import guide, mmc


def disc_report(report):
    from .info import disc_id
    from .capacity import recordable_capacity
    parsed = lambda key: guide._parsed(report, key)
    cfg = parsed('configuration')
    family = mmc.media_family(cfg.get('current_profile'))
    count = guide.sectors_from_info(report)
    blank = parsed('track_1').get('blank')
    if blank is None:
        status = parsed('disc_information').get('disc_status')
        blank = status in (0, 'empty') if status in (0, 1, 2, 'empty', 'incomplete', 'complete') else None
    disc = dict(present=family != 'unknown', media=family,
                kind=cfg.get('current_profile_name') or 'unknown',
                mid=disc_id(parsed('dvd_prerecorded_0e'), parsed('dvd_plus_adip_11'), parsed('atip')),
                blank=blank, sectors=count[0] if count else None)
    capacity = recordable_capacity(report)
    disc['capacity_sectors'] = capacity[0] if capacity else None
    disc['capacity_source'] = capacity[1] if capacity else None
    return disc


def catalogue(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    groups = {media: [] for media in ('dvd', 'cd', 'bd')}
    runs = guide.scan(str(out))
    infos = [r for r in runs if r.kind == 'info' and not r.simulated]
    metadata = guide._load(str(root / 'catalogue.json')) or {}
    linked_presets = {value.get('preset') for value in metadata.values() if isinstance(value, dict)}
    seen = set()
    for run in sorted(runs, key=lambda r: (r.geo_complete() if r.kind == 'geo' else False, r.when), reverse=True):
        if run.kind != 'geo' or run.simulated or not Path(run.path).resolve().is_relative_to(root):
            continue
        who = guide.identity_of(run, infos)
        mid = who.get('disc')
        if mid == 'unknown disc':
            mid = None
        # An unidentified measurement is its own entry, never an invented manufacturer.
        key = (run.media, mid, who.get('drive')) if mid else (run.media, run.path)
        if key in seen:
            continue
        seen.add(key)
        ident = hashlib.sha256(repr(key).encode()).hexdigest()[:20]
        saved = {**(run.summary.get('counter') or {}), **metadata.get(ident, {})}
        sectors = (run.summary.get('setup') or {}).get('last_lba')
        groups[run.media].append(dict(id=ident, row=run.media, name=saved.get('name') or mid or Path(run.path).name,
            mid=mid, sectors=sectors + 1 if isinstance(sectors, int) else None,
            s=guide.result_verdict(run, run.media), last=run.when.date().isoformat(),
            drive=who.get('drive'), left=saved.get('left'), of=saved.get('of'),
            geo=str(Path(run.path).relative_to(root)).replace('\\', '/'), inferred=who.get('inferred', False)))
    # Only explicit preset locations; do not traverse evidence or read held-out folders.
    locations = [*sorted((root / 'presets').glob('*.json')), *sorted((root / 'dis').glob('*.json')),
                 *sorted(root.glob('dis_preset*.json')), *sorted(root.glob('disc-presets.json'))]
    for path in locations:
        if path.resolve().is_relative_to(root):
            if path.relative_to(root).as_posix() in linked_presets:
                continue
            data = guide._load(str(path)) or {}
            if not isinstance(data, (dict, list)):
                continue
            presets = data if isinstance(data, list) else data.get('presets', [*data.get('dvdPresets', []), *data.get('cdPresets', []), *data.get('bluRayPresets', [])] or [data.get('preset', data)])
            if not isinstance(presets, list):
                continue
            for preset in presets:
                if not isinstance(preset, dict) or not preset.get('displayName') or not preset.get('id'):
                    continue
                media = 'cd' if 'sectors' in preset else 'bd' if 'layerCount' in preset else 'dvd'
                groups[media].append(dict(id='preset:' + str(preset['id']), row=media,
                    name=preset['displayName'], mid=None, sectors=preset.get('totalSectors', preset.get('sectors')),
                    s='unknown', last=None, drive=None, left=None, of=None, preset=str(path.relative_to(root))))
    return groups


def save_entry(root, out, payload):
    if not isinstance(payload, dict) or set(payload) - {'id', 'name', 'left', 'preset'}:
        raise ValueError('invalid catalogue entry')
    entries = [item for row in catalogue(root, out).values() for item in row]
    if not any(item['id'] == payload.get('id') for item in entries):
        raise ValueError('unknown catalogue entry')
    if 'name' in payload and (not isinstance(payload['name'], str) or not 1 <= len(payload['name'].strip()) <= 120):
        raise ValueError('invalid name')
    if 'left' in payload and (type(payload['left']) is not int or not 0 <= payload['left'] <= 100000):
        raise ValueError('invalid count')
    if 'preset' in payload:
        value = payload['preset']
        path = (Path(root) / value).resolve() if isinstance(value, str) else None
        if path is None or not path.is_relative_to((Path(root) / 'presets').resolve()) or path.suffix != '.json' or not path.is_file():
            raise ValueError('invalid preset path')
    path = Path(root) / 'catalogue.json'
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('catalogue must stay inside the workspace')
    data = guide._load(str(path)) or {}
    data[payload['id']] = {**data.get(payload['id'], {}), **{k: v for k, v in payload.items() if k != 'id'}}
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
    return dict(saved=True)


def measurement(run):
    """Saved observations only: residual and its uncertainty against LBA, no invented curve."""
    points = []
    try:
        with (Path(run.path) / 'targets.csv').open(encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                try:
                    point = {key: float(row[key]) for key in ('lba', 'residual_deg', 'sigma_deg')}
                    if all(math.isfinite(v) for v in point.values()) and point['sigma_deg'] >= 0:
                        points.append(point)
                except (KeyError, ValueError, TypeError):
                    continue
    except OSError:
        pass
    return dict(points=points, stopped=run.stopped, span_mm=run.fit.get('measured_span_mm'),
                sigma_deg=run.fit.get('angle_sigma_measured_span_deg'),
                rotation=run.rotation(), jitter_deg=guide._jitter(run.summary))
