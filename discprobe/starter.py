"""Explicit DVD starting geometry and evidence for its mandatory check disc."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import secrets

FORMAT = 'dp-starter-preset-v1'
FILE = 'starter.json'
CHECK_RANGE = (26.2, 57.0)
REFUSAL = '起步预设未通过检查，请回到测量盘流程。 / The starter preset did not pass its check. Return to the measurement disc.'
UNVERIFIED = '未验证：跨机器/跨批次没有实测数据。 / Unverified: no measurements across machines or batches.'
RUN_NAME = re.compile(r'starter-[0-9a-f]{24}')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    document = json.loads(raw)
    fit = document.get('fit') if isinstance(document, dict) else None
    if (not isinstance(fit, dict) or document.get('format') != FORMAT or fit.get('media') != 'dvd'
            or not all(type(fit.get(k)) in (int, float) and math.isfinite(fit[k]) and fit[k] > 0
                       for k in ('u', 'v', 'bit_nm_assumed'))
            or not isinstance(document.get('source'), dict) or not isinstance(document.get('drive_identity'), dict)
            or not isinstance(document.get('mid'), str) or not document['mid'].strip()
            or type(document.get('capacity_sectors')) is not int or document['capacity_sectors'] <= 32):
        raise ValueError('Invalid DVD starter preset')
    return document, digest(raw)


def is_record(path):
    path = Path(path)
    return path.name == FILE and RUN_NAME.fullmatch(path.parent.name) is not None


def run_file(folder):
    path = Path(folder) / FILE
    return path if is_record(path) and path.is_file() else Path(folder) / 'summary.json'


def identity(geolocation, drive):
    from .photo import drive_identity
    return drive_identity({'identity': {**geolocation, 'device_id': drive}}, '.')


def record_drive_identity(folder, who, drive):
    from .works import atomic, encoded
    if who and who.get('drive') and drive:
        folder = Path(folder)
        summary = folder / 'summary.json'
        atomic(folder / 'starter-source.json', encoded(dict(geo_sha256=digest(summary.read_bytes()),
                                                            drive_identity=identity(who, drive))))


def _source_identity(path, doc, sha):
    from .photo import photo_l
    try:
        saved = json.loads((path.parent / 'starter-source.json').read_bytes())
        if saved.get('geo_sha256') == sha:
            return saved['drive_identity']
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    # An older local calibration can prove its origin with its existing, accepted photo evidence.
    decision = photo_l(path)
    if decision.get('written'):
        return decision['provenance']['drive_identity']
    return doc.get('drive_identity')


def _sibling(path, name):
    if Path(name).name != name:
        raise ValueError('A correction must be a sibling of its calibration')
    target = path.with_name(name)
    if target.resolve().parent != path.parent:
        raise ValueError('A correction must stay beside its calibration')
    return json.loads(target.read_bytes())


def _candidate(source, fit, correction=None, prior=None):
    from . import coverage, photo
    if coverage.range_warning(fit, CHECK_RANGE, allow_dis_nominal=True):
        return None
    if not all(type(fit.get(k)) in (int, float) and math.isfinite(fit[k]) and fit[k] > 0
               for k in ('u', 'v', 'bit_nm_assumed')):
        return None
    mapped = {k: fit[k] for k in ('u', 'v', 'bit_nm_assumed')}
    mapped['media'] = 'dvd'
    mapped['measured_span_mm'] = fit.get('measured_span_mm')
    source['verification'] = 'same_drive' if source['kind'] == 'same_drive' else 'unverified_cross_machine_or_batch'
    if prior and prior['written']:
        mapped['u'] = photo.shifted_u(fit, prior)
        source['prior_L_mm'] = prior['L_mm']
        source['prior_photo_sha256'] = prior['provenance_sha256']
    else:
        source['prior_L_mm'] = None
    return dict(source=source, fit=mapped, correction=correction)


def candidates(root, out, who, mid):
    from . import community, guide, presets
    from .community_feed import read_feed
    from .dispitch import ANGLE_LIMIT_DEG, RADIUS_LIMIT_MM

    def match(candidate):
        return bool(mid) and community.mid_code(mid) == community.mid_code(candidate)

    found = []
    for run in guide.scan(str(out)):
        if run.kind != 'geo' or run.media != 'dvd' or run.simulated or not run.reliable(CHECK_RANGE):
            continue
        doc = run.summary
        recorded = doc.get('identity') or {}
        if not match(recorded.get('disc')) or recorded.get('drive') != who['model']:
            continue
        path = (Path(run.path) / 'summary.json').resolve()
        if path.parent.parent != out:
            continue
        sha = digest(path.read_bytes())
        same = _source_identity(path, doc, sha) == who
        source = dict(id='geo:' + path.parent.name, kind='same_drive' if same else 'same_model',
                      name=path.parent.name, path=path.relative_to(root).as_posix(), sha256=sha,
                      drive=recorded['drive'], measured_span_mm=run.fit.get('measured_span_mm'))
        try:
            from .photo import photo_l
            corrected = run.fit.get('correction_file')
            row = _candidate(source, run.fit, _sibling(path, corrected) if corrected else None,
                             photo_l(path, device_id=who['device_id']) if same else None)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if row:
            found.append(row)

    raw = community.BUNDLED.read_bytes()
    for item in read_feed(raw)['entries']:
        model = (item.get('drive') or '').split(' / ', 1)[0].strip()
        if item['media'] != 'dvd' or item['result'] == 'failed' or not match(item['disc'].get('mid')):
            continue
        if model.casefold() != who['model'].casefold():
            continue
        source = dict(id='community:' + item['id'], kind='community', name=item['id'],
                      drive=model, measured_span_mm=item['measured_span_mm'], sha256=digest(raw),
                      attribution=item['source'])
        try:
            parameters = item['parameters']
            if not parameters['innerRadiusMm'] <= CHECK_RANGE[0] < CHECK_RANGE[1] <= parameters['outerRadiusMm']:
                continue
            fit, comparison, correction = presets.geometry(parameters, 'dvd', with_correction=True)
            if (comparison['max_angle_error_deg'] > ANGLE_LIMIT_DEG
                    or comparison['max_radius_error_mm'] > RADIUS_LIMIT_MM):
                continue
            fit['image_compatible'] = True
            row = _candidate(source, fit, correction)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            continue
        if row:
            found.append(row)
    return sorted(found, key=lambda row: {'same_drive': 0, 'same_model': 1, 'community': 2}[row['source']['kind']])


def create(out, choice, who, mid, capacity):
    from .works import atomic, encoded
    folder = out / ('starter-' + secrets.token_hex(12))
    folder.mkdir(parents=True)
    path = folder / FILE
    doc = dict(format=FORMAT, status='batch_unconfirmed', mid=mid, capacity_sectors=capacity,
               drive_identity=who, **choice)
    atomic(path, encoded(doc))
    return path


def catalogue(root, out):
    from .photo import photo_l
    for path in sorted(out.glob('starter-*/starter.json'), reverse=True):
        if not is_record(path) or path.resolve() != path:
            continue
        try:
            doc, _ = read(path)
            if photo_l(path)['written']:
                yield dict(id='starter:' + path.parent.name, row='dvd', name=doc['mid'], mid=doc['mid'],
                           s='good', starter=True, drive=doc['drive_identity']['model'],
                           drive_id=doc['drive_identity']['device_id'], geo=path.relative_to(root).as_posix(),
                           capacity_sectors=doc['capacity_sectors'], measured_mm=doc['source']['measured_span_mm'],
                           checked_mm=list(CHECK_RANGE),
                           starter_source=doc['source'], history=[])
        except (OSError, ValueError, KeyError, TypeError):
            continue


def correction(doc):
    from .imagedisc import Correction, SplineCorrection
    data = doc.get('correction')
    if not data:
        return None
    lo, hi = data['radius_valid_mm']
    return (SplineCorrection(data['spline'], lo, hi) if 'spline' in data
            else Correction(data['poly_in_x'], lo, hi))


def target(path, doc, sha):
    return dict(path=str(path), sha256=sha, mid=doc['mid'])


def _local_writer(drive, recorder):
    from .burner import LinuxBurner, WindowsDVD
    from .device import Device
    from .info import identify
    with Device(drive) as device:
        current = identity(identify(device, 'dvd'), drive)
    engine = 'IMAPI' if isinstance(recorder, WindowsDVD) else 'growisofs' if isinstance(recorder, LinuxBurner) else type(recorder).__name__
    return current, dict(burner=drive, path=engine, mode='DVD single closed session')


def burn_binding(binding, drive, expected, recorder, *, media, append, keep_open, no_verify):
    if media != 'dvd' or append or keep_open or no_verify:
        raise ValueError('A starter check disc requires a closed DVD and verified read-back.')
    doc, sha = read(binding['path'])
    if sha != binding['sha256'] or (expected or {}).get('mid') != doc['mid']:
        raise ValueError('The starter preset or the check disc MID changed.')
    current, burn_path = _local_writer(drive, recorder)
    if current != doc['drive_identity']:
        raise ValueError('The check disc requires the local drive selected for this starter preset.')
    return dict(starter_sha256=sha, drive_identity=current, disc_id='SP-' + secrets.token_hex(6).upper(),
                burn_path=burn_path)


def check_picture_burn(decision, drive, expected, recorder, *, media, append, keep_open):
    from .photo import _provenance_hash
    proof = decision.get('provenance') or {}
    if (media != 'dvd' or append or keep_open or proof.get('kind') != 'starter_preset'
            or _provenance_hash(proof) != decision.get('provenance_sha256')):
        raise ValueError(REFUSAL)
    try:
        doc, sha = read(proof['starter'])
        current, burn_path = _local_writer(drive, recorder)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(REFUSAL) from error
    if (proof.get('starter_sha256') != sha or (expected or {}).get('mid') != doc['mid']
            or current != proof.get('drive_identity') or burn_path != proof.get('burn_path')):
        raise ValueError('这幅图须用检查盘的光驱、刻录方式和 MID。 / Use the check disc drive, write mode and MID for this picture.')


def save_burn(path, binding):
    from .works import atomic, encoded
    atomic(Path(path).parent / (binding['disc_id'] + '.burn.json'), encoded(binding))


def receipt(path, doc, sha, disc_id):
    from socket import gethostname
    if not isinstance(disc_id, str) or not re.fullmatch(r'SP-[0-9A-F]{12}', disc_id):
        raise ValueError('Enter the number printed after the verified check disc burn.')
    raw = Path(path).with_name(disc_id + '.burn.json').read_bytes()
    row = json.loads(raw)
    drive = row['drive_identity']
    burn = row['burn_path']
    if (row['disc_id'] != disc_id or row['starter_sha256'] != sha or drive != doc['drive_identity']
            or drive['machine'] != gethostname() or not drive.get('device_id') or not drive.get('model')
            or burn.get('burner') != drive['device_id']
            or not all(isinstance(burn.get(k), str) and burn[k].strip() for k in ('burner', 'path', 'mode'))):
        raise ValueError('The check disc does not match this local starter preset and burn path.')
    return dict(**row, burn_sha256=digest(raw))


def photo_decision(path, photo_path, *, device_id=None, media=None, frozen=None):
    from . import pcal, photo
    from .calib import SECTOR_BITS

    def refuse(reason):
        return dict(written=False, reason=reason)

    if media not in (None, 'dvd'):
        return refuse('different_media')
    try:
        doc, sha = read(path)
        path = Path(path).resolve()
        reading = Path(photo_path).resolve() if photo_path else path.with_name('photo.json')
        if reading != path.with_name('photo.json'):
            return refuse('different_run')
        if not reading.is_file():
            return refuse('no_photo')
        raw = reading.read_bytes()
        record = json.loads(raw)
        evidence = receipt(path, doc, sha, record.get('disc_id'))
        if device_id is not None and evidence['drive_identity']['device_id'] != device_id:
            return refuse('different_drive')
        if (record.get('source_starter') != evidence or record.get('burn_path') != evidence['burn_path']
                or Path(record['path']).resolve() != path.parent or record.get('media') != 'dvd'):
            return refuse('starter_evidence_mismatch')
        if record.get('reader_version') != 'v1' or record.get('reader_sha256') != photo.READER_SHA256:
            return refuse('unknown_reader')
        shots = [shot for shot in record['photos'] if shot.get('status') == 'ok']
        for shot in shots:
            if shot.get('disc_id') != evidence['disc_id']:
                return refuse('different_disc')
            if shot.get('design') != 'pn_burn':
                return refuse('different_target')
            status = pcal.verdict(shot)
            if status != 'ok':
                return refuse(status)
        agreement = photo.photo_agreement(shots)
        if record['verdict'] != 'ok' or not agreement['written']:
            reasons = [shot['status'] for shot in record['photos'] if shot['status'] != 'ok']
            shape_failure = next((reason for reason in ('shape_not_1_over_r', 'large_residual') if reason in reasons), None)
            if shape_failure or reasons and not shots:
                return refuse(shape_failure or reasons[0])
            return refuse(agreement.get('reason') or 'verdict_not_ok')
        offset = agreement['L_mm']
        if not math.isclose(offset, record['offset_mm'], abs_tol=1e-9):
            return refuse('inconsistent_L')
        provenance = dict(kind='starter_preset', starter=str(path), starter_sha256=sha, source=doc['source'],
                          photo_json=str(reading),
                          photo_sha256=digest(raw), reader_sha256=photo.READER_SHA256, reader_version='v1',
                          photo_ids=agreement['photo_ids'], input_sha256=agreement['input_sha256'],
                          L_mm=offset, **{k: v for k, v in evidence.items() if k != 'starter_sha256'})
        bits = offset / (doc['fit']['bit_nm_assumed'] * 1e-6)
        decision = dict(written=True, origin='starter-preset', L_mm=offset, channel_bits=bits,
                        sectors=bits / SECTOR_BITS, reader_version='v1', provenance=provenance,
                        provenance_sha256=photo._provenance_hash(provenance))
        if frozen is not None and decision != frozen:
            return refuse('invalid_saved_photo_L')
        return decision
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return refuse('invalid_starter_photo_evidence')


def add_parser(sub):
    parser = sub.add_parser('starter', help='列出或选用 DVD 起步预设 / List or select a DVD starter preset')
    parser.add_argument('--drive', required=True, help='装有空白 DVD 的本机光驱 / Local drive with a blank DVD')
    parser.add_argument('--source', help='显式选择来源 ID / Explicitly select a source ID')
    parser.add_argument('--out', default='results', help='保存批次记录的目录 / Directory for batch records')
    parser.set_defaults(func=run)


def run(args):
    from . import info, ui, webui_catalog
    from .device import Device
    from .drive_lock import drive_operation
    from .imagedisc import sectors_to_radius
    with drive_operation(args.drive, 'disc'):
        with Device(args.drive) as device:
            report = info.quick(device)
    disc = webui_catalog.disc_report(report)
    inq = (report['inquiry'].get('parsed') or {})
    who = identity({'drive': disc['drive_name'], 'firmware': inq.get('revision')}, args.drive)
    root = Path.cwd().resolve()
    out = (root / args.out).resolve()
    if not out.is_relative_to(root):
        raise SystemExit('The starter results folder must stay inside the workspace.')
    mid, capacity = disc['mid'], disc['capacity_sectors']
    rows = (candidates(root, out, who, mid) if disc['blank'] is True and disc['media'] == 'dvd'
            and mid and capacity and who['model'] else [])
    rows = [row for row in rows if _fits_blank(row['fit'], capacity, sectors_to_radius)]
    result = dict(candidates=[row['source'] for row in rows], mid=mid)
    if args.source:
        row = next((row for row in rows if row['source']['id'] == args.source), None)
        if row is None:
            raise SystemExit('起步来源不匹配，请用测量盘。 / No matching starter source; use a measurement disc.')
        path = create(out, row, who, mid, capacity)
        result.update(path=path.relative_to(root).as_posix(), source=row['source'],
                      checked_mm=list(CHECK_RANGE), capacity_sectors=capacity)
        print(f'{path}: 本批未确认，请先刻检查盘并拍照。 / Batch unconfirmed. Burn and photograph a check disc first.')
    for row in rows:
        source = row['source']
        print(f"{source['id']} · {source['drive']} · {source['measured_span_mm'] or '范围未知 / range unknown'}"
              + (f' · {UNVERIFIED}' if source['kind'] != 'same_drive' else ''))
    if not rows:
        print('没有可用的起步预设，请用测量盘。 / No usable starter preset. Use a measurement disc.')
    ui.event('result', step='starter', **result)


def _fits_blank(fit, capacity, sectors_to_radius):
    target_end = sectors_to_radius(fit['u'], fit['v'], fit['bit_nm_assumed'], CHECK_RANGE[1])
    return target_end <= capacity
