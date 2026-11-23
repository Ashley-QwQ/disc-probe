"""Live result-directory ownership shared by measurements and the disc library."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from .drive_lock import FileLocked, file_lock
from .works import Store, WorkError, atomic, encoded


_active = ContextVar('measurement_job', default=None)
_PARENT = 'DISCPROBE_MEASUREMENT_PARENT'
_ID = re.compile(r'[0-9a-f]{32}')


class MeasurementRunning(WorkError):
    code = 'measurement_running'

    def __init__(self):
        super().__init__('This batch is being measured. Wait for the measurement to finish before renaming or deleting it.', 409)


def _registry(out):
    location = os.path.normcase(Path(out).resolve())
    key = hashlib.sha256(os.fsencode(location)).hexdigest()
    return Store(out).root / '.measurement-jobs' / key


@contextmanager
def track(out, media):
    """An OS lock ends ownership even if the process is terminated."""
    store = Store(out)
    key = uuid.uuid4().hex
    root = _registry(out)
    lease = root / (key + '.lock')
    parent = os.environ.get(_PARENT, '')
    keys = [key]
    if _ID.fullmatch(parent):
        keys.append(parent)
    try:
        with file_lock(lease):
            token = _active.set((root, store, keys, media, []))
            try:
                yield
            finally:
                _active.reset(token)
    finally:
        # A reader may hold a handle to a completed lease on Windows.
        with store._locked():
            (root / (key + '.json')).unlink(missing_ok=True)
            lease.unlink(missing_ok=True)


def child_env():
    tracked = _active.get()
    return {_PARENT: tracked[2][0]} if tracked else {}


def _record(root, keys, path, details):
    for key in keys:
        marker = root / (key + '.json')
        try:
            paths = json.loads(marker.read_bytes())
        except FileNotFoundError:
            paths = {}
        paths[str(Path(path).resolve())] = details
        atomic(marker, encoded(paths))


@contextmanager
def allocating():
    """Publish the actual allocated path before a concurrent library scan can see it."""
    tracked = _active.get()
    if tracked is None:
        yield lambda path: None
        return
    root, store, keys, media, paths = tracked
    with store._locked():
        def register(path):
            details = dict(media=media, job=os.environ.get('DISCPROBE_JOB'))
            paths.append((path, details))
            _record(root, keys, path, details)
        yield register


def identify(identity):
    tracked = _active.get()
    if tracked is None or not tracked[-1]:
        return
    root, store, keys, _, paths = tracked
    path, details = paths[-1]
    with store._locked():
        details['identity'] = identity
        _record(root, keys, path, details)


def occupied(out):
    """Call with the works lock held, as for other library reads and mutations."""
    root = _registry(out)
    paths = {}
    for marker in root.glob('*.json'):
        if not _ID.fullmatch(marker.stem):
            continue
        try:
            with file_lock(marker.with_suffix('.lock'), create=False):
                pass
        except FileLocked:
            paths.update(json.loads(marker.read_bytes()))
            continue
        except FileNotFoundError:
            pass
        marker.unlink(missing_ok=True)
        marker.with_suffix('.lock').unlink(missing_ok=True)
    return paths


def changes(out):
    """The lobby's state stream notices a measurement before a summary is written."""
    markers = []
    for marker in _registry(out).glob('*.json'):
        if _ID.fullmatch(marker.stem):
            try:
                markers.append((marker.name, marker.stat().st_mtime_ns))
            except FileNotFoundError:
                pass
    return sorted(markers)
