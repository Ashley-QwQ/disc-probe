"""Disk-only home catalogue. Unknown identity and quality stay unknown."""
from pathlib import Path
import csv
import math
import hashlib
import json
from datetime import datetime, timezone
from . import guide, mmc


def burn_state(result):
    if result.get('result') in ('failed', 'cancelled', 'stopped'):
        return 'needs'
    verify = result.get('verification') or {}
    if not isinstance(verify, dict):
        return 'unknown'
    if verify.get('differing') or verify.get('unreadable') or verify.get('failures'):
        return 'needs'
    if (result.get('result') == 'completed' and verify.get('status') == 'completed'
            and verify.get('untested') == 0 and verify.get('ok', 0) > 0):
        return 'ok'
    return 'unknown'


def saved_burns(root):
    """Only bounded, explicit saved links; never infer a batch from dates or file names."""
    found = []
    paths = [*sorted((root / '.webui-jobs').glob('*/burn.json')),
             *sorted((root / 'iso').glob('*.iso.burn.jsonl'))]
    for path in paths:
        if not path.resolve().is_relative_to(root):
            continue
        try:
            if path.name == 'burn.json':
                record = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(record, dict):
                    found.append(record)
                continue
            spec_path = path.with_name(path.name.removesuffix('.iso.burn.jsonl') + '.image.json')
            if not spec_path.resolve().is_relative_to(root):
                continue
            spec = guide._load(str(spec_path)) or {}
            geo = spec.get('geometry_from') if isinstance(spec, dict) else None
            if not isinstance(geo, str):
                continue
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue  # a truncated last line does not discard earlier completed burns
                if isinstance(record, dict) and record.get('type') == 'burn_result':
                    found.append(dict(record, geo=geo, log_path=str(path)))
        except (OSError, ValueError):
            continue
    # The web record and the engine log can describe the very same burn.
    unique = {}
    for record in found:
        key = (record.get('log_path'), record.get('time'))
        unique.setdefault(key if key[0] else id(record), record)
    return list(unique.values())


def batch_history(root, runs, infos, chosen, burns):
    who = guide.identity_of(chosen, infos)
    def matches(run):
        identity = guide.identity_of(run, infos)
        return (run.path == chosen.path or (who['disc'] != 'unknown disc' and
                run.media == chosen.media and identity['disc'] == who['disc'] and identity['drive'] == who['drive']))
    related = [r for r in runs if r.kind == 'geo' and not r.simulated and matches(r)
               and Path(r.path).resolve().is_relative_to(root)]
    history = []
    for run in related:
        verdict = guide.result_verdict(run, run.media)
        state = 'ok' if verdict in ('good', 'usable') else 'needs' if (run.stopped or verdict in
            ('stopped_early', 'drive_changed', 'too_noisy', 'narrow_span')) else 'unknown'
        history.append(dict(kind='calibrate', state=state, when=run.when.isoformat(),
                            label='标定 / Calibration · ' + str(verdict or 'unknown')))
    geo_paths = {Path(r.path).resolve() for r in related}
    for record in burns:
        geo = record.get('geo')
        linked = (root / geo).resolve() if isinstance(geo, str) else None
        if linked and linked.name == 'summary.json':
            linked = linked.parent
        identity = record.get('identity') or {}
        if not isinstance(identity, dict):
            identity = {}
        match = linked in geo_paths or (who['disc'] != 'unknown disc' and
            identity.get('disc') == who['disc'] and identity.get('drive') == who['drive'] and
            record.get('media') == chosen.media)
        if not match:
            continue
        when = record.get('time')
        if not isinstance(when, (int, float)) or not math.isfinite(when):
            continue
        try:
            when = datetime.fromtimestamp(when, timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            continue
        history.append(dict(kind='burn', state=burn_state(record), when=when,
                            label='刻录 / Burn · ' + str(record.get('result', 'unknown'))))
    return sorted(history, key=lambda item: datetime.fromisoformat(item['when']).timestamp())


def disc_report(report):
    from .info import disc_id
    from .capacity import recordable_capacity
    parsed = lambda key: guide._parsed(report, key)
    cfg = parsed('configuration')
    inquiry = parsed('inquiry')
    family = mmc.media_family(cfg.get('current_profile'))
    count = guide.sectors_from_info(report)
    blank = parsed('track_1').get('blank')
    if blank is None:
        status = parsed('disc_information').get('disc_status')
        blank = status in (0, 'empty') if status in (0, 1, 2, 'empty', 'incomplete', 'complete') else None
    # closed: the disc was finalized (READ DISC INFORMATION says complete); False while a session is open
    status = parsed('disc_information').get('disc_status')
    closed = True if status == 'complete' else False if status == 'incomplete' else None
    disc = dict(present=family != 'unknown', media=family,
                kind=cfg.get('current_profile_name') or 'unknown',
                mid=disc_id(parsed('dvd_prerecorded_0e'), parsed('dvd_plus_adip_11'), parsed('atip')),
                blank=blank, sectors=count[0] if count else None, closed=closed)
    capacity = recordable_capacity(report)
    disc['capacity_sectors'] = capacity[0] if capacity else None
    disc['capacity_source'] = capacity[1] if capacity else None
    disc['drive_name'] = f"{inquiry.get('vendor', '')} {inquiry.get('product', '')}".strip() or None
    return disc


def catalogue(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    groups = {media: [] for media in ('dvd', 'cd', 'bd')}
    runs = guide.scan(str(out))
    infos = [r for r in runs if r.kind == 'info' and not r.simulated]
    burns = saved_burns(root)
    metadata = guide._load(str(root / 'catalogue.json')) or {}
    def linked(value):
        # older pages saved the preset's absolute path; both spellings name the same file
        path = Path(value) if isinstance(value, str) else None
        if path is not None and path.is_absolute() and path.resolve().is_relative_to(root):
            return path.resolve().relative_to(root).as_posix()
        return value
    linked_presets = {linked(value.get('preset')) for value in metadata.values() if isinstance(value, dict)}
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
            geo=str(Path(run.path).relative_to(root)).replace('\\', '/'), inferred=who.get('inferred', False),
            history=batch_history(root, runs, infos, run, burns)))
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
                source = data.get('source') if isinstance(data, dict) else None
                media = source.get('media') if isinstance(source, dict) else None
                if media not in groups:
                    media = 'cd' if 'sectors' in preset else 'bd' if 'layerCount' in preset or 'invertMapping' in preset else 'dvd'
                fit = data.get('fit') if isinstance(data, dict) else None
                imported = isinstance(fit, dict) and fit.get('model') == 'dis_import'
                compatible = imported and fit.get('image_compatible') is True
                if compatible:
                    from .presets import linked_correction
                    try:
                        linked_correction(path, data)
                    except (OSError, ValueError, KeyError, TypeError):
                        compatible = False
                groups[media].append(dict(id='preset:' + str(preset['id']), row=media,
                    name=preset['displayName'], mid=None, sectors=preset.get('totalSectors', preset.get('sectors')),
                    s='unknown', last=None, drive=None, left=None, of=None, preset=str(path.relative_to(root)), history=[],
                    image_compatible=bool(compatible), imported=imported,
                    correction_required=bool(fit.get('correction_required')) if imported else False,
                    import_status=source.get('status') if isinstance(source, dict) else None,
                    geo=str(path.relative_to(root)) if compatible else None))
    return groups


def save_entry(root, out, payload):
    photo_shift = None
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
        # stored relative to the workspace, as catalogue() compares it: an absolute path would leave the
        # preset listed again as a batch of its own
        payload = {**payload, 'preset': path.relative_to(Path(root).resolve()).as_posix()}
        document = guide._load(str(path)) or {}
        source = document.get('source') if isinstance(document, dict) else None
        photo_shift = dict(written=False, reason='invalid_preset')
        if isinstance(source, dict):
            photo_shift = source.get('photo_shift', photo_shift)
    path = Path(root) / 'catalogue.json'
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('catalogue must stay inside the workspace')
    data = guide._load(str(path)) or {}
    data[payload['id']] = {**data.get(payload['id'], {}), **{k: v for k, v in payload.items() if k != 'id'}}
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
    return dict(saved=True, **({'photo_shift': photo_shift} if photo_shift is not None else {}))


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
    from argparse import Namespace
    args = Namespace(**{**(run.summary.get('args') or {}), 'media': run.media,
                        'out': str(Path(run.path).parent)})
    advice = guide.speed_advice(args, run.media, run.summary) if run.kind == 'timing' else None
    return dict(points=points, stopped=run.stopped, span_mm=run.fit.get('measured_span_mm'),
                sigma_deg=run.fit.get('angle_sigma_measured_span_deg'),
                completion_status=run.fit.get('completion_status'), coverage=run.fit.get('coverage'),
                correction=run.fit.get('correction_file'), correction_validation=run.fit.get('correction_validation'),
                rotation=run.rotation(), jitter_deg=guide._jitter(run.summary), speed_advice=advice)
