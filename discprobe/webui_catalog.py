"""Disk-only home catalogue. Unknown identity and quality stay unknown."""
from pathlib import Path
import csv
import math
import hashlib
import json
import os
from datetime import datetime, timezone
from . import guide, mmc
from .capacity import catalogue_capacity, positive_sectors
from .coverage import assess_range, calibration_gaps


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


def batch_history(root, related, chosen, who, burns, issues):
    history = []
    for run in related:
        verdict = guide.result_verdict(run, run.media)
        state = 'needs' if issues[run.path] else 'ok' if verdict in ('good', 'usable') else 'needs' if (run.stopped or verdict in
            ('stopped_early', 'drive_changed', 'too_noisy', 'narrow_span')) else 'unknown'
        history.append(dict(kind='calibrate', state=state, when=run.when.isoformat(),
                            label='标定 / Calibration · ' + ('未通过 / Incomplete' if issues[run.path] else str(verdict or 'unknown'))))
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
    closed = True if status in (2, 'complete') else False if status in (1, 'incomplete') else None
    disc = dict(present=family != 'unknown', media=family,
                kind=cfg.get('current_profile_name') or 'unknown',
                mid=disc_id(parsed('dvd_prerecorded_0e'), parsed('dvd_plus_adip_11'), parsed('atip')),
                blank=blank, sectors=count[0] if count else None, closed=closed)
    capacity = recordable_capacity(report)
    disc['capacity_sectors'] = capacity[0] if capacity else None
    disc.update(mmc.rewritable(cfg.get('current_profile'), parsed('disc_information').get('erasable')))
    disc['capacity_source'] = capacity[1] if capacity else None
    disc['drive_name'] = f"{inquiry.get('vendor', '')} {inquiry.get('product', '')}".strip() or None
    from .measurement_disc import short_recording
    issue = short_recording(disc)
    if issue:
        disc['measurement_issue'] = dict(reason='short_recording', message=issue)
    return disc


def measured_ring(summary):
    """Every measured radius interval within the disc face, in millimetres."""
    from .coverage import assess_range
    fit = (summary or {}).get('fit') or {}
    return assess_range(fit, (0, 60))['covered_intervals_mm']


def calibration_record(run):
    record = guide._load(str(Path(run.path) / 'calibration.json'))
    return record if isinstance(record, dict) else {}


def calibration_issue(run, record, *, full=False):
    """Assess legacy runs as well as runs with a recorded calibration outcome."""
    fit = run.fit
    gaps = []
    if run.kind == 'geo' and 'u' in fit:
        if full or record:
            gaps = calibration_gaps(fit, run.media)
        else:
            # Legacy standalone measurements may intentionally cover a local ring.
            # Within that span a gap still needs to be visible in the catalogue.
            span = fit.get('measured_span_mm')
            if span and span[0] < span[1]:
                gaps = assess_range(fit, span)['extrapolated_mm']
    verdict = guide.result_verdict(run, run.media)
    if not (gaps or record.get('ok') is False or verdict not in ('good', 'usable')):
        return None
    from .geo import resume_supported
    return dict(missing_mm=gaps, reason=record.get('reason') or run.stopped, verdict=verdict,
                stopped=bool(run.stopped or verdict == 'stopped_early'),
                can_resume=run.kind == 'geo' and run.rungs() >= 6 and resume_supported(run.summary, run.media))


def _relative(root, value):
    if isinstance(value, str) and value and '\x00' not in value and 'blind' not in value.casefold():
        try:
            original = Path(os.path.abspath(root / value))
            if original.is_relative_to(root) and original.resolve() == original:
                return original.relative_to(root).as_posix()
        except (OSError, RuntimeError, ValueError):
            pass
    return None


def _preset_path(root, value):
    relative = _relative(root, value)
    if relative is None:
        return None
    path = Path(relative)
    if path.suffix.lower() != '.json' or relative == 'presets/catalogue.json':
        return None
    if path.parent in (Path('presets'), Path('dis')) or path.parent == Path('.') and (
        path.name.startswith('dis_preset') or path.name == 'disc-presets.json'
    ):
        return relative
    return None


def _capacity(root, mid, media, record, infos):
    disc = record.get('disc') or {}
    sectors, source = record.get('sectors'), record.get('capacity_source')
    if positive_sectors(sectors) and source in ('--sectors', 'blank disc before burning', 'free space of this blank disc'):
        return sectors, source
    reference = catalogue_capacity(mid, media, root)
    if reference:
        return reference
    if mid:
        for info in infos:
            report = guide._load(str(Path(info.path) / 'info.json')) or {}
            measured = disc_report(report)
            if measured['mid'] == mid and measured['media'] == media and measured['blank'] is True and measured['capacity_sectors']:
                return measured['capacity_sectors'], measured['capacity_source']
    if positive_sectors(sectors):
        return sectors, source
    return disc.get('capacity_sectors'), disc.get('capacity_source')


def catalogue(root, out, *, inventory=None, occupied=None, progress=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    occupied = occupied or {}
    groups = {media: [] for media in ('dvd', 'cd', 'bd')}
    runs = guide.scan(str(out))
    infos = [r for r in runs if r.kind == 'info' and not r.simulated]
    burns = saved_burns(root)
    metadata = guide._load(str(root / 'catalogue.json')) or {}
    metadata = {key: row for key, row in metadata.items() if isinstance(row, dict)} if isinstance(metadata, dict) else {}
    linked_presets = {_preset_path(root, value.get('preset')) for value in metadata.values() if isinstance(value, dict)}
    batches, records, issues, identities = {}, {}, {}, {}
    for run in runs:
        if run.kind not in ('geo', 'timing') or not Path(run.path).resolve().is_relative_to(root) or run.simulated:
            continue
        record = calibration_record(run)
        active = occupied.get(run.path)
        if run.kind == 'timing' and record.get('ok') is not False and not active:
            continue
        if active:
            run.summary = {**run.summary,
                           'args': {'media': active['media'], **(run.summary.get('args') or {})},
                           'identity': run.summary.get('identity') or active.get('identity')}
        who = guide.identity_of(run, infos)
        mid = who.get('disc')
        if mid == 'unknown disc':
            mid = None
        # An unidentified measurement is its own entry, never an invented manufacturer.
        key = (run.media, mid, who.get('drive')) if mid else (run.media, run.path)
        batches.setdefault(key, []).append(run)
        records[run.path], identities[run.path] = record, who
        issues[run.path] = None if active else calibration_issue(run, record)
    rows = []
    for key, related in batches.items():
        active = next((r for r in related if r.path in occupied), None)
        run = active or next((r for r in related if r.kind == 'geo' and not issues[r.path]), related[0])
        who, record, issue = identities[run.path], records[run.path], issues[run.path]
        mid = None if who['disc'] == 'unknown disc' else who['disc']
        ident = hashlib.sha256(repr(key).encode()).hexdigest()[:20]
        saved = {**(run.summary.get('counter') or {}), **metadata.get(ident, {})}
        sectors = (run.summary.get('setup') or {}).get('last_lba')
        capacity, capacity_source = _capacity(root, mid, run.media, record, infos)
        rings = measured_ring(run.summary)
        source = _relative(root, run.path)
        recent = related[0] if not issue and issues[related[0].path] else None
        entry = dict(id=ident, row=run.media, name=saved.get('name') or mid or Path(run.path).name,
            mid=mid, sectors=sectors + 1 if isinstance(sectors, int) else None,
            capacity_sectors=capacity, capacity_source=capacity_source,
            measured_intervals_mm=rings, measured_mm=max(rings, key=lambda iv: iv[1] - iv[0], default=None),
            s='incomplete' if issue else guide.result_verdict(run, run.media), last=run.when.date().isoformat(),
            drive=who.get('drive'), left=saved.get('left'), of=saved.get('of'),
            drive_id=record.get('drive_id') or (run.summary.get('args') or {}).get('drive') or
                (run.tag + ':' if run.tag and len(run.tag) == 1 and run.tag.isalpha() else run.tag),
            geo=source if run.kind == 'geo' else None, inferred=who.get('inferred', False),
            history=batch_history(root, [r for r in related if r.path not in occupied], run, who, burns, issues),
            calibration_issue=({**issue, 'geo': source if run.kind == 'geo' else None} if issue else
                {**issues[recent.path], 'geo': _relative(root, recent.path), 'previous_usable': True} if recent else None))
        disc = record.get('disc') or {}
        if isinstance(disc, dict) and disc.get('kind'):
            entry['media_kind'] = disc['kind']
        if active:
            entry.update(s='measuring', calibration_issue=None, measurement_progress={'phase': active.kind})
            if progress:
                entry['measurement_progress'].update(progress(occupied[active.path].get('job'), active.kind))
        if source and run.kind == 'geo' and run.media == 'cd' and entry['s'] in ('good', 'usable'):
            from .photo import MANUAL_L_FILE, photo_l
            folder = Path(run.path)
            evidence = [folder / name for name in ('photo.json', MANUAL_L_FILE)]
            known = all(path.resolve() == path for path in evidence) and any(path.is_file() for path in evidence)
            entry['along_track'] = dict(known=known and photo_l(folder, media='cd')['written'])
        presets = {_preset_path(root, saved.get('preset'))}
        presets.update(_preset_path(root, records[r.path].get('preset')) for r in related)
        presets.discard(None)
        linked_presets.update(presets)
        if inventory is not None:
            paths = {_relative(root, r.path) for r in related}
            for r in related:
                timing = (records[r.path].get('timing') or {}).get('path')
                path = _relative(root, timing)
                if path and (root / path).parent == out and Path(path).name.startswith('timing-'):
                    paths.add(path)
            inventory.setdefault(ident, set()).update(paths | presets)
        rows.append((not issue, run.when, entry))
    for _, _, entry in sorted(rows, key=lambda row: row[:2], reverse=True):
        groups[entry['row']].append(entry)
    # Only explicit preset locations; do not traverse evidence or read held-out folders.
    locations = [*sorted((root / 'presets').glob('*.json')), *sorted((root / 'dis').glob('*.json')),
                 *sorted(root.glob('dis_preset*.json')), *sorted(root.glob('disc-presets.json'))]
    for path in locations:
        if 'blind' not in path.as_posix().casefold() and path.resolve().is_relative_to(root):
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
                ident = 'preset:' + str(preset['id'])
                relative = path.relative_to(root).as_posix()
                if inventory is not None:
                    inventory.setdefault(ident, set()).add(relative)
                if relative in metadata.get(ident, {}).get('hidden_presets', []):
                    continue
                source = data.get('source') if isinstance(data, dict) else None
                media = source.get('media') if isinstance(source, dict) else None
                if media not in groups:
                    media = 'cd' if 'sectors' in preset else 'bd' if 'layerCount' in preset or 'invertMapping' in preset else 'dvd'
                fit = data.get('fit') if isinstance(data, dict) else None
                imported = isinstance(fit, dict) and fit.get('model') == 'dis_import'
                compatible = imported and fit.get('image_compatible') is True
                correction = None
                if compatible:
                    from .presets import linked_correction
                    try:
                        correction = linked_correction(path, data)
                    except (OSError, ValueError, KeyError, TypeError):
                        compatible = False
                if inventory is not None and correction:
                    linked = _relative(root, correction)
                    if linked:
                        inventory[ident].add(linked)
                groups[media].append(dict(id=ident, row=media,
                    name=metadata.get(ident, {}).get('name') or preset['displayName'], mid=None, sectors=preset.get('totalSectors', preset.get('sectors')),
                    s='imported' if compatible else 'unknown', last=None, drive=None, left=None, of=None, preset=str(path.relative_to(root)), history=[],
                    image_compatible=bool(compatible), imported=imported,
                    **({'nominal_mm': [preset['innerRadiusMm'], preset['outerRadiusMm']]} if compatible else {}),
                    correction_required=bool(fit.get('correction_required')) if imported else False,
                    import_status=source.get('status') if isinstance(source, dict) else None,
                    geo=str(path.relative_to(root)) if compatible else None))
    from .starter import catalogue as starter_batches
    groups['dvd'].extend(starter_batches(root, out))
    return groups


def save_entry(root, out, payload, *, occupied=None):
    photo_shift = None
    if not isinstance(payload, dict) or set(payload) - {'id', 'name', 'left', 'preset'}:
        raise ValueError('invalid catalogue entry')
    entries = [item for row in catalogue(root, out, occupied=occupied).values() for item in row]
    entry = next((item for item in entries if item['id'] == payload.get('id')), None)
    if not entry:
        raise ValueError('unknown catalogue entry')
    if entry['s'] == 'measuring':
        from .measurement_jobs import MeasurementRunning
        raise MeasurementRunning()
    if 'name' in payload and (not isinstance(payload['name'], str) or not 1 <= len(payload['name'].strip()) <= 120):
        raise ValueError('invalid name')
    if 'left' in payload and (type(payload['left']) is not int or not 0 <= payload['left'] <= 100000):
        raise ValueError('invalid count')
    if 'preset' in payload:
        if entry['s'] == 'incomplete':
            raise ValueError('calibration did not pass; complete the measurement before saving a preset')
        value = payload['preset']
        path = (Path(root) / value).resolve() if isinstance(value, str) else None
        if path is None or not path.is_relative_to((Path(root) / 'presets').resolve()) or path.suffix != '.json' or not path.is_file():
            raise ValueError('invalid preset path')
        # stored relative to the workspace, as catalogue() compares it: an absolute path would leave the
        # preset listed again as a batch of its own
        payload = {**payload, 'preset': path.relative_to(Path(root).resolve()).as_posix()}
        document = guide._load(str(path))
        source = document.get('source') if isinstance(document, dict) else None
        if not isinstance(document, dict) or not document:
            photo_shift = dict(written=False, reason='invalid_preset')
        elif isinstance(source, dict):
            photo_shift = source.get('photo_shift')
    path = Path(root) / 'catalogue.json'
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('catalogue must stay inside the workspace')
    data = read_metadata(path)
    previous = data.get(payload['id'])
    data[payload['id']] = {**(previous if isinstance(previous, dict) else {}),
                           **{k: v for k, v in payload.items() if k != 'id'}}
    from .works import atomic, encoded
    atomic(path, encoded(data))
    return dict(saved=True, **({'photo_shift': photo_shift} if photo_shift is not None else {}))


def read_metadata(path):
    try:
        data = json.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError('invalid catalogue metadata')
    return data


def measurement_retry(run, args, points, coverage, timing_advice):
    """Advise from saved core observations and the CLI's existing speed list."""
    from .geo import retryable_read_stop

    reason = (run.stopped or '').lower()
    rotation = run.rotation()
    jitter = guide._jitter(run.summary)
    fit = run.fit
    if run.kind == 'geo' and (fit.get('failed_candidates') or points and retryable_read_stop(reason)):
        kind = 'rung'
    elif 'medium error' in reason:
        kind = 'media'
    elif 'reads are far slower than expected' in reason:
        kind = 'slow'
    elif run.kind == 'timing' and rotation != 'CAV':
        kind = 'rotation' if rotation and rotation != 'unknown' else 'unknown'
    elif run.kind == 'timing' and jitter and max(jitter) > guide.GOOD_JITTER_DEG:
        kind = 'noisy'
    elif run.kind == 'geo' and (run.stopped or guide.result_verdict(run, run.media) not in ('good', 'usable')):
        kind = 'coverage' if coverage.get('missing_mm') else 'geo'
    else:
        return {}
    if kind == 'coverage':
        return dict(retry_kind=kind)
    advice = dict(timing_advice or guide.speed_advice(args, run.media, run.summary))
    current = getattr(args, 'speed', None)
    advice['lower_speeds'] = [speed for speed in guide.ALTERNATIVE_SPEEDS[run.media]
                              if isinstance(current, (int, float)) and int(speed) < current]
    field = 'speed_advice' if run.kind == 'timing' else 'retry_speed_advice'
    return {'retry_kind': kind, field: advice,
            **({'failed_rung': len(points) + 1} if kind == 'rung' and reason and points else {})}


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
    coverage_result = {}
    if run.kind == 'geo' and 'u' in run.fit:
        from .coverage import assess_range, default_range
        from .geo import resume_supported
        required = default_range(run.media, run.fit.get('measured_span_mm'))
        if required:
            coverage_result = dict(missing_mm=assess_range(run.fit, required)['extrapolated_mm'],
                                   can_resume=len(points) >= 6 and resume_supported(run.summary, run.media))
    detail = dict(points=points, stopped=run.stopped, span_mm=run.fit.get('measured_span_mm'),
                sigma_deg=run.fit.get('angle_sigma_measured_span_deg'),
                completion_status=run.fit.get('completion_status'), coverage=run.fit.get('coverage'),
                correction=run.fit.get('correction_file'), correction_validation=run.fit.get('correction_validation'),
                rotation=run.rotation(), jitter_deg=guide._jitter(run.summary), speed_advice=advice,
                **coverage_result)
    detail.update(measurement_retry(run, args, points, coverage_result, advice))
    return detail
