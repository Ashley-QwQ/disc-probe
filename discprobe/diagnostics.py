"""Small, opt-in-shareable run bundles. No device access, photos or outside files."""
from __future__ import annotations

import csv
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import re
import zipfile

FILES = ('summary.json', 'info.json', 'failure.json', 'events.csv', 'targets.csv', 'zones.csv',
         'probes.json', 'correction.json', 'run.log', 'timing.log', 'geo.log', 'burn.log')
MAX_FILE_BYTES = 8 * 1024 * 1024
PATH_FIELDS = {'out', 'output', 'image', 'images', 'inputs', 'iso', 'geo', 'picture', 'design', 'design_npy',
               'source_file', 'correction', 'register', 'rings_layout', 'layout', 'log_path', 'cwd', 'path', 'file'}


def clean(value, root):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            safe = clean(item, root)
            if str(key).lower() in PATH_FIELDS and isinstance(safe, str) and safe and not safe.startswith('<RUN>'):
                safe = '<outside-run>'
            elif str(key).lower() in PATH_FIELDS and isinstance(safe, list):
                safe = ['<outside-run>' if isinstance(v, str) and v and not v.startswith('<RUN>') else v for v in safe]
            result[clean(str(key), root)] = safe
        return result
    if isinstance(value, (list, tuple)):
        return [clean(v, root) for v in value]
    if not isinstance(value, str):
        return value
    text = value
    for prefix in (str(root), root.as_posix()):
        text = re.sub(re.escape(prefix) + r'(?=$|[\\/])', '<RUN>', text)
    if text.startswith(('/', '\\')):
        return '<outside-run>'
    text = re.sub(r'\\\\[^\r\n"\'<>]*', '<outside-run>', text)
    text = re.sub(r'(?<!\w)(?:\.\.[\\/])+[^\r\n"\'<>;,]*', '<outside-run>', text)
    # Remove whole absolute path fragments, including Windows paths with spaces.
    text = re.sub(r'[A-Za-z]:[\\/][^\r\n"\'<>]*', '<outside-run>', text)
    return re.sub(r'(?<![\w:>])/(?=[^\s])[^\r\n"\'<>;,]*', '<outside-run>', text)


def advice(reason):
    text = reason.lower()
    if 'cache' in text or 'host' in text or 'fake' in text:
        return ('Reuse this disc. Compare FUA or cache eviction with timing; a host timer period is not CLV. '
                'Do not fit geometry until real rotation is distinguished.')
    if 'clv' in text or 'cav' in text or 'constant speed' in text or 'settled' in text:
        return ('Reuse this disc. Try one untried read speed from timing history, then another available drive. '
                'For CLV CD, use DiscImageStudio calibration; experimental CD CLV cannot supply sector angles.')
    if any(word in text for word in ('span', 'extrapolat', 'coverage', 'candidate', 'range', 'bridge')):
        return ('Use the saved measured intervals to shrink the artwork, or re-read the missing range on this same disc. '
                'Do not relax chi2, whole-turn or coverage gates. No new burn is needed for this check.')
    return ('Save and inspect these logs first. Close other drive software and retry the read on this same disc. '
            'A new burn is a last resort: only if no usable recorded data remains and no existing data disc is available.')


def bundle(run):
    root = Path(run).resolve(strict=True)
    if root.is_file() and root.name == 'summary.json':
        root = root.parent
    if not root.is_dir():
        raise ValueError('diagnose RUN needs a run folder or its summary.json')
    entries, omitted = {}, []
    for name in FILES:
        path = root / name
        if not path.exists():
            continue
        if path.is_symlink() or path.resolve().parent != root or path.stat().st_size > MAX_FILE_BYTES:
            omitted.append(name)
            continue
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        if path.suffix == '.json':
            try:
                text = json.dumps(clean(json.loads(text), root), ensure_ascii=False, indent=2)
            except ValueError:
                text = clean(text, root)
        elif path.suffix == '.csv':
            output = io.StringIO(newline='')
            writer = csv.writer(output)
            for row in csv.reader(io.StringIO(text)):
                writer.writerow([clean(v, root) for v in row])
            text = output.getvalue()
        else:
            text = clean(text, root)
        entries[name] = text
    if not entries:
        raise ValueError('No recognized run records found; choose the folder containing summary.json or info.json.')
    try:
        summary = json.loads(entries.get('summary.json', '{}'))
        if not isinstance(summary, dict):
            raise ValueError('summary must be an object')
    except ValueError:
        entries['unparsed-summary.txt'] = entries.pop('summary.json', '')
        summary = {}
    entries.setdefault('summary.json', json.dumps({'status': 'unknown', 'note': 'No parseable summary; see run records.'}))
    entries['settings.json'] = json.dumps(summary.get('args') or {}, ensure_ascii=False, indent=2)
    versions = {'python': platform.python_version(), 'system': platform.system()}
    from .version import __version__
    versions['discprobe'] = __version__
    for name in ('numpy', 'Pillow', 'scipy', 'opencv-python'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = 'not installed'
    entries['versions.json'] = json.dumps(versions, indent=2)
    entries['logs.txt'] = '\n'.join(name for name in entries if name.endswith(('.csv', '.log'))) or 'No command log was saved before this run stopped.'
    entries['README.txt'] = ('Run diagnostics: sanitized copies only; originals remain in the run.\n'
                             'Contains summary, settings, versions and available command/measurement logs.\n'
                             'No photos, images, environment variables or outside files are included.\n'
                             'Inspect the archive before sharing.\nOmitted: ' + ', '.join(omitted))
    target = root / 'diagnostics.zip'
    if target.is_symlink():
        raise ValueError('Refusing a diagnostics.zip symlink')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return target, sorted(entries)


def save_failure(run, reason, args=None):
    root = Path(run)
    root.mkdir(parents=True, exist_ok=True)
    record = dict(reason=reason, next_step=advice(reason))
    (root / 'failure.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    if not (root / 'summary.json').exists():
        summary = dict(stopped=reason, args={k: v for k, v in vars(args).items() if k != 'func'} if args else {})
        (root / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    target, names = bundle(root)
    print(f'Stopped: {reason}\nDiagnostics: {target}\nNext: {record["next_step"]}', flush=True)
    return target


def run(args):
    try:
        target, names = bundle(args.run)
    except (OSError, ValueError) as exc:
        raise SystemExit(f'diagnose: {exc}') from None
    print(f'Diagnostics: {target}\nContains: ' + ', '.join(names))
