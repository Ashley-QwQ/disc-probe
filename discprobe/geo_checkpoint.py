"""On-disk checkpoints for the angular geometry ladder."""
from __future__ import annotations

import csv
import datetime
import io
import json
import math
import os
from pathlib import Path
import time


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _replace(temp, path):
    if os.name != 'nt':
        os.replace(temp, path)
        _sync_directory(path.parent)
        return

    import ctypes
    move = ctypes.WinDLL('kernel32', use_last_error=True).MoveFileExW
    move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
    # REPLACE_EXISTING | WRITE_THROUGH. A reader may briefly deny delete sharing.
    for attempt in range(20):
        if move(str(temp), str(path), 0x9):
            return
        error = ctypes.get_last_error()
        if error not in (5, 32) or attempt == 19:
            raise ctypes.WinError(error)
        time.sleep(.025)


def atomic_write(path, write, *, binary=False, newline=None):
    temp = path.with_suffix(path.suffix + '.tmp')
    mode, options = ('wb', {}) if binary else ('w', dict(encoding='utf-8', newline=newline))
    try:
        with temp.open(mode, **options) as stream:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def write_json(path, document):
    atomic_write(path, lambda stream: json.dump(document, stream, indent=2, default=float))


def write_targets(path, targets):
    def write(stream):
        writer = csv.writer(stream)
        writer.writerow(["lba", "n_bits", "phase_deg", "sigma_deg", "std_deg", "used", "predicted_deg",
                         "unwrapped_deg", "model_deg", "residual_deg", "period_ms"])
        for t in targets:
            model = t.get('model_deg', t['predicted_deg'])
            writer.writerow([t["lba"], f"{t['n']:.0f}", t["phase_deg"], f"{t['sigma_deg']:.3f}", t["std_deg"], t["used"],
                             f"{t['predicted_deg']:.3f}", f"{t['unwrapped_deg']:.3f}", f"{model:.3f}",
                             f"{t.get('residual_deg', t['unwrapped_deg'] - model):.3f}", t["period_ms"]])
    atomic_write(path, write, newline='')


def event_bytes(rows, *, header):
    if not rows:
        return b''
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    if header:
        writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def read_events(folder, checkpoint):
    size = checkpoint['events_bytes']
    if not size:
        return b''
    with (folder / 'events.csv').open('rb') as stream:
        data = stream.read(size)
    if len(data) != size or not data.endswith(b'\n'):
        raise ValueError('events.csv is missing checkpointed reads; keep the raw files together')
    return data


def source_path(path):
    path = Path(path)
    path = path / 'summary.json' if path.is_dir() else path
    if path.name == 'summary.json' and not path.exists():
        partial = path.with_name('partial.json')
        if partial.is_file():
            return partial
    return path


class Checkpoint:
    def __init__(self, folder, previous_events=b''):
        self.folder = Path(folder)
        self.path = self.folder / 'partial.json'
        self.events = bytearray(previous_events)
        self.written = 0

    def write_events(self, probe):
        size = len(self.events)
        rows = probe.events_as_rows(self.written) if self.written else probe.events_as_rows()
        self.events.extend(event_bytes(rows, header=not size))
        try:
            if self.events and (len(self.events) != size or not (self.folder / 'events.csv').exists()):
                atomic_write(self.folder / 'events.csv', lambda stream: stream.write(self.events), binary=True)
        except OSError:
            del self.events[size:]
            raise
        self.written += len(rows)

    def save(self, ladder):
        fit = ladder.result() if ladder.cov is not None else None
        if fit is None and ladder.targets:
            fit = dict(u=ladder.u, v=ladder.v, c_deg=math.degrees(ladder.c),
                       period_ms=ladder.T * 1000, reference_lba=ladder.ref,
                       completion_sectors=ladder.completion_sectors)
            if ladder.audio:
                fit['track'] = 'audio'
        if fit is not None:
            fit.update(media=ladder.media, completion_status='interrupted')
        document = ladder.output_summary(fit, 'measurement interrupted')
        self.write_events(ladder.tp)
        write_targets(self.folder / 'targets.csv', ladder.targets)
        # CSV files always contain complete rows. If interrupted between replacements,
        # the previous marker still identifies its exact targets and raw event prefix.
        document['checkpoint'] = dict(
            rungs=len(ladder.targets), events_bytes=len(self.events),
            updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            targets=ladder.targets, sentinels=getattr(ladder, 'sentinels', []),
            max_targets=ladder.max_targets)
        if os.name != 'nt' and not self.path.exists():
            _sync_directory(self.folder.parent)
        write_json(self.path, document)

    def finish(self):
        try:
            self.path.unlink(missing_ok=True)
        except PermissionError:
            # A published summary takes precedence over a stale marker.
            pass
