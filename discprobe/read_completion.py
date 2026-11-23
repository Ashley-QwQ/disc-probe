"""DVD read-completion convention, registry and device-free reapplication.

Positive sectors mean completion later than the containing ECC block's end.
An omitted completion_sectors is the legacy value zero. Keep that sparse encoding
so zero-offset summaries and preset exports retain their original bytes.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil

from . import geo_checkpoint

HELP = "DVD: read completion offset in sectors after the ECC block end (geo default: drive registry or 0; export default: stored value)"
REFIT_HELP = "reapply the completion offset to an existing geo folder or summary without drive access; --out is a new folder"


def sectors(value):
    if type(value) is not int or not -65536 <= value <= 65536:
        raise ValueError("completion sectors must be an integer between -65536 and 65536")
    return value


def argument(value):
    return sectors(int(value))


def inquiry_key(identity):
    """INQUIRY vendor/product/firmware, ignoring case and padding."""
    identity = identity or {}
    drive = str(identity.get('drive') or '').split(maxsplit=1)
    vendor = identity.get('vendor') or (drive[0] if len(drive) == 2 else '')
    product = identity.get('product') or (drive[1] if len(drive) == 2 else '')
    revision = identity.get('revision') or identity.get('firmware') or ''
    norm = lambda value: ' '.join(str(value).split()).upper()
    return tuple(map(norm, (vendor, product, revision)))


def drive_registry_paths(root=None):
    """The workspace registry and the one beside the source package, in lookup order."""
    source = Path(__file__).resolve().parents[1]
    roots = [Path(root)] if root is not None else dict.fromkeys([Path.cwd(), source])
    return [folder / 'presets' / 'drives.json' for folder in roots]


def drive_entry(identity, root=None):
    """Exact INQUIRY match. Never match by substring."""
    key = inquiry_key(identity)
    if not all(key):
        return None
    for path in drive_registry_paths(root):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        for entry in data.get('dvd_read_completion', []):
            if inquiry_key({k: entry[k] for k in ('vendor', 'product', 'firmware')}) == key:
                sectors(entry['completion_sectors'])
                return copy.deepcopy(entry)
    return None


def resolve(identity, explicit=None, media='dvd', root=None):
    if media != 'dvd':
        if explicit is not None:
            raise ValueError("--completion-sectors is for DVD")
        return 0, None
    if explicit is not None:
        return sectors(explicit), dict(origin='manual')
    entry = drive_entry(identity, root)
    return (entry['completion_sectors'], dict(origin='registry', **entry)) if entry else (0, None)


def notice(value, source):
    if source and source.get('origin') == 'registry':
        key = ' / '.join(source[k] for k in ('vendor', 'product', 'firmware'))
        return f"DVD completion offset: {value} sectors (registry: {key}; {source['evidence']})"
    return f"DVD completion offset: {value} sectors ({source['origin'] if source else 'unregistered; default'})"


def corrected_u(u, v, delta):
    from .calib import SECTOR_BITS
    square = u * u - v * sectors(delta) * SECTOR_BITS / math.pi
    if not math.isfinite(square) or square <= 0:
        raise ValueError("completion offset gives a nonpositive inner radius")
    return math.sqrt(square)


def summary_path(path):
    path = Path(path)
    return path / 'summary.json' if path.is_dir() else path


def _event_phases(stream, rows, summary):
    """Replay accepted rung blocks; retries/check points are matched to saved phases.

    targets.csv keeps the accepted rung and its turn count. events.csv also has
    rejected retries, so a target is used only when its phase agrees with that rung.
    """
    from . import analysis
    from .geo import MIN_SIGMA_DEG, MEASURE_COHERENCE
    from .timing import CACHE_HIT_US
    groups, refs, targets, lba = [], [], [], None
    ref = summary['fit']['reference_lba']
    cache = summary.get('cache') or {}
    threshold = cache.get('cache_hit_us', CACHE_HIT_US)
    def usable(row):
        return int(row['status']) == 0 and (cache.get('strategy') not in ('flush', 'far', 'evict')
                                              or float(row['duration_us']) >= threshold)
    def finish():
        if targets:
            groups.append((lba, refs[:], targets[:]))
    pending = None
    for row in csv.DictReader(stream):
        if row['label'] not in ('ref', 'target'):
            if row['label'] in ('settle', 'rotation'):
                finish()
                refs, targets, lba, pending = [], [], None, None
            continue
        if row['label'] == 'ref':
            pending = row
            continue
        x = int(row['lba'])
        if x != lba:
            finish()
            refs, targets, lba = [], [], x
        if pending and int(pending['lba']) == ref and usable(pending):
            refs.append(int(pending['t_end_ns']))
        if usable(row):
            targets.append(int(row['t_end_ns']))
        pending = None
    finish()
    replay = []
    for row in rows:
        candidates = []
        for x, rt, xt in groups:
            if x != row['lba'] or len(rt) < 8 or len(xt) < 8:
                continue
            period = row['period_ms'] / 1000
            fit = analysis.estimate_period(rt, prior_s=period, prior_window=.02)
            if not fit or fit.coherence < MEASURE_COHERENCE:
                continue
            ph = analysis.robust_circular_mean(analysis.phase_offsets(fit, xt))
            if ph['mean_deg'] is None:
                continue
            error = abs((ph['mean_deg'] - row['phase_deg'] + 180) % 360 - 180)
            if error <= .02:
                candidates.append((error, ph))
        if not candidates:
            raise ValueError(f"events.csv cannot reproduce accepted rung LBA {row['lba']}; keep the raw files together")
        ph = min(candidates, key=lambda x: x[0])[1]
        new = dict(row)
        turns = round((row['unwrapped_deg'] - row['phase_deg']) / 360)
        new.update(phase_deg=ph['mean_deg'], unwrapped_deg=ph['mean_deg'] + 360 * turns,
                   sigma_deg=max(ph['sem_deg'], MIN_SIGMA_DEG), std_deg=ph['std_deg'], used=ph['used'])
        replay.append(new)
    return replay


def reapply(path, value):
    """Return a new summary and optional rungs, without changing the source files."""
    path = geo_checkpoint.source_path(path)
    raw = path.read_bytes()
    return _reapply(path, raw, json.loads(raw), value)


def _reapply(path, raw, document, value):
    from .geo import Ladder
    from .calscan import _report
    from .calib import SECTOR_BITS
    fit = document.get('fit')
    if not fit:
        raise ValueError('the measurement stopped before a geometry fit was available')
    checkpoint = document.get('checkpoint')
    media = fit.get('media', 'dvd')
    if (media != 'dvd' and not (checkpoint and media == 'cd' and value == 0)
            or fit.get('model') == 'clv'):
        raise ValueError("--completion-sectors is for DVD")
    value = sectors(value)
    old = sectors(fit.get('completion_sectors', 0))
    if value == old and not checkpoint:
        return document, None, 'unchanged'
    # Validate the requested absolute value before calculating its difference.
    delta = value - old
    square = fit['u'] ** 2 - fit['v'] * delta * SECTOR_BITS / math.pi
    if not math.isfinite(square) or square <= 0:
        raise ValueError("completion offset gives a nonpositive inner radius")
    u = math.sqrt(square)
    target_file = path.with_name('targets.csv')
    event_file = path.with_name('events.csv')
    rows = None
    saved_prior = bool(fit.get('fit_prior'))
    # Merged fits have independent reference phases and no single rung table.
    if checkpoint or (target_file.exists() and fit.get('reference_lba') is not None):
        if checkpoint:
            rows = [{**t, 'lba': int(t['lba'])} for t in checkpoint['targets']]
        else:
            with target_file.open(encoding='utf-8', newline='') as stream:
                rows = [{**{k: float(v) for k, v in row.items() if v}, 'lba': int(row['lba'])}
                        for row in csv.DictReader(stream)]
        if len(rows) < 3:
            raise ValueError("targets.csv needs at least three accepted rungs")
        event_data = geo_checkpoint.read_events(path.parent, checkpoint) if checkpoint else None
        method = 'targets_refit'
        if event_data or (checkpoint is None and event_file.exists()):
            with (io.StringIO(event_data.decode('utf-8'), newline='') if checkpoint else
                  event_file.open(encoding='utf-8', newline='')) as stream:
                try:
                    rows = _event_phases(stream, rows, document)
                    method = 'events_refit'
                except ValueError:
                    if not checkpoint:
                        raise
        prior = fit.get('fit_prior') or (document.get('args') or {} if checkpoint else {})
        ladder = Ladder(None, media=media, completion_sectors=value,
                        r0_mm=prior.get('r0_mm'), pitch_um=prior.get('pitch_um'), bit_nm=fit['bit_nm_assumed'],
                        sigma_u=prior.get('sigma_u'), sigma_v=prior.get('sigma_v'),
                        read_offset_bytes=fit.get('read_offset_bytes', 0))
        ladder.audio = fit.get('track') == 'audio'
        ladder.ref = fit['reference_lba']
        ladder.n_ref = ladder._n_end(ladder.ref)
        ladder.targets = rows
        for row in rows:
            row['n'] = ladder._n_end(row['lba'])
        ladder.u, ladder.v, ladder.c = u, fit['v'], math.radians(fit.get('c_deg', 0))
        ladder.T = fit.get('period_ms', 0) / 1000 if fit.get('period_ms') else None
        ladder.tp.last_lba = (document.get('setup') or {}).get('last_lba', 2295103)
        ladder.fit()
        fit.update(ladder.result())
    else:
        method = 'closed_form'
        # Update physical equivalents; phase residuals are invariant under this
        # coordinate change. The full covariance is absent from legacy summaries.
        layout = Ladder(None, bit_nm=fit['bit_nm_assumed']).prior
        physical = _report(u, fit['v'], None, (u, fit['v']), layout, None)
        for key in ('u', 'coarse_u', 'r0_mm_at_bit', 'dis_equivalent', 'nominal_error_deg'):
            fit[key] = physical[key]
    if media == 'dvd':
        fit['completion_sectors'] = value
        fit['completion_source'] = dict(origin='manual')
    inputs = {path.name if checkpoint else 'summary.json': hashlib.sha256(raw).hexdigest()}
    if checkpoint:
        if event_data:
            inputs[event_file.name] = hashlib.sha256(event_data).hexdigest()
    else:
        for file in (target_file, event_file):
            if file.exists():
                inputs[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    fit['completion_adjustment'] = dict(method=method, from_sectors=old, to_sectors=value,
                                        input_sha256=inputs,
                                        prior='saved' if saved_prior else 'legacy DVD defaults',
                                        uncertainty='refitted' if rows else 'legacy covariance unavailable; not recomputed')
    return document, rows, method


def load_fit(path, completion_sectors=None):
    path = summary_path(path)
    if completion_sectors is None:
        return json.loads(path.read_text(encoding='utf-8'))['fit'], 'stored'
    document, _, method = reapply(path, completion_sectors)
    return document['fit'], method


def save_reapplied(path, value, output, source=None):
    """Write a separate result; copying events preserves original timestamps exactly."""
    path = geo_checkpoint.source_path(path).resolve()
    output = Path(output).resolve()
    if output.is_relative_to(path.parent) or output.exists():
        raise ValueError("--out must be a new folder; source results are read-only")
    raw = path.read_bytes()
    saved = json.loads(raw)
    document, rows, method = _reapply(path, raw, saved, value)
    checkpoint = document.pop('checkpoint', None)
    if source and method != 'unchanged':
        document['fit']['completion_source'] = source
    output.mkdir(parents=True)
    if rows:
        keys = ['lba', 'n', 'phase_deg', 'sigma_deg', 'std_deg', 'used', 'predicted_deg',
                'unwrapped_deg', 'model_deg', 'residual_deg', 'period_ms']
        with (output / 'targets.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['n_bits' if k == 'n' else k for k in keys])
            writer.writeheader()
            for row in rows:
                writer.writerow({'n_bits' if k == 'n' else k: row[k] for k in keys})
    elif path.with_name('targets.csv').exists():
        shutil.copyfile(path.with_name('targets.csv'), output / 'targets.csv')
    if checkpoint:
        event_data = geo_checkpoint.read_events(path.parent, checkpoint)
        if event_data:
            (output / 'events.csv').write_bytes(event_data)
    elif path.with_name('events.csv').exists():
        shutil.copyfile(path.with_name('events.csv'), output / 'events.csv')
    if method == 'unchanged':
        shutil.copyfile(path, output / 'summary.json')
    else:
        (output / 'summary.json').write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding='utf-8')
    return document['fit'], method
