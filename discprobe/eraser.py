"""Explicit erase path; measurement transports remain read-only."""
from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

from . import disc_identity, mmc, ui
from .burner import BurnError, parse_progress, tool
from .drive_lock import child_env, locked_drive


@locked_drive("info")
def inspect(drive):
    from .device import Device
    from .info import quick
    from .webui_catalog import disc_report
    with Device(drive) as dev:
        return disc_report(quick(dev))


class PlatformEraser:
    def __init__(self, drive):
        self.drive = drive

    def inspect(self):
        return inspect(self.drive)

    def erase(self, full, cancel, progress, *, before_write=None):
        disc = self.inspect()  # fresh evidence immediately before the destructive call
        if not disc.get('rewritable'):
            raise BurnError('This disc is not rewritable; erasing is refused.')
        profile = disc['rewritable_sources']['current_profile']
        if sys.platform == 'win32':
            from .resources import tool as resource_tool
            if not re.fullmatch('[A-Za-z]:', self.drive):
                raise BurnError('Windows drive must be a letter followed by a colon.')
            argv = [tool('powershell.exe'), '-NoProfile', '-NonInteractive', '-File',
                    str(resource_tool('erase_imapi.ps1')),
                    '-Drive', self.drive, *(['-Full'] if full else [])]
        elif sys.platform.startswith('linux'):
            if not self.drive.startswith('/dev/') or any(c in self.drive for c in '\r\n\0'):
                raise BurnError('Linux drive must be a /dev/ device path.')
            if profile == 0x0A:
                import shutil
                writer = shutil.which('wodim') or tool('cdrecord')
                argv = [writer, 'dev=' + self.drive, 'blank=' + ('all' if full else 'fast')]
            elif profile in (0x13, 0x14):
                argv = [tool('dvd+rw-format'), '-blank=full' if full else '-blank', self.drive]
            elif profile in (0x1A, 0x2A, 0x43):
                # Overwrite media: explicit reformat, not a claim of secure data destruction.
                argv = [tool('dvd+rw-format'), '-force=full' if full else '-force', self.drive]
            else:
                raise BurnError('No erase tool is known for this current profile; nothing was changed.')
        else:
            raise BurnError('Erasing on this platform is not implemented.')
        if cancel.is_set():
            raise BurnError('Erase cancelled before starting; nothing was changed.')
        if before_write is not None:
            before_write()
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   **({'creationflags': 0x08000000, 'env': child_env(self.drive)} if sys.platform == 'win32' else
                                      {'start_new_session': True, 'env': {**os.environ, 'LC_ALL': 'C'}}))
        stop = threading.Event()
        has_progress = threading.Event()
        started = time.monotonic()
        def watch():
            while not stop.wait(.25):
                # IMAPI2 EraseMedia has no CancelWrite. Do not kill it during media finalization.
                if cancel.is_set() and sys.platform != 'win32' and process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    return
                if sys.platform != 'win32' and not has_progress.is_set():
                    progress(stage='erasing', fraction=0, elapsed_s=time.monotonic()-started, eta_s=0)
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        lines = []
        try:
            for line in process.stdout:
                lines.append(line.rstrip())
                event = parse_progress(line)
                if event:
                    has_progress.set()
                    progress(**event)
                elif sys.platform != 'win32':
                    match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
                    if match:
                        has_progress.set()
                        fraction = min(.999, float(match[1])/100)
                        elapsed = time.monotonic()-started
                        progress(fraction=fraction, elapsed_s=elapsed,
                                 eta_s=elapsed*(1-fraction)/fraction if fraction else None)
            code = process.wait()
        finally:
            stop.set()
            watcher.join()
        if code:
            raise BurnError('Erase tool failed. ' + '\n'.join(lines[-20:]))
        return dict(overwrite_ready=profile in (0x1A, 0x2A, 0x43))


def adapter(drive):
    return PlatformEraser(drive)


@locked_drive("erase")
def erase(drive, *, full=False, cancel=None, recorder=None, expected_identity=None):
    if expected_identity is None and (recorder is None or isinstance(recorder, PlatformEraser)):
        expected_identity = disc_identity.expected_for_write(drive, erasing=True)
    if expected_identity is not None:
        disc_identity.require_identity(expected_identity, erasing=True)
    cancel = cancel or threading.Event()
    recorder = recorder or adapter(drive)
    disc = recorder.inspect()
    if not disc.get('rewritable'):
        raise BurnError('This disc is not rewritable; erasing is refused.')
    if cancel.is_set():
        raise BurnError('Erase cancelled before starting; nothing was changed.')
    started = time.monotonic()
    def progress(**fields):
        fields['stage'] = 'erasing'
        if fields.get('eta_s') == 0 and fields.get('fraction', 0) < 1:
            fields['eta_s'] = None
        ui.event('erase_progress', **fields)
    def before_write():
        if expected_identity is not None:
            disc_identity.check_identity(drive, expected_identity)
        if cancel.is_set():
            raise BurnError('Erase cancelled before starting; nothing was changed.')
        ui.say('Erasing the rewritable disc. Its contents will be cleared; keep the drive connected.')
        ui.event('erase_started', drive=drive, full=full, **{k:v for k,v in disc.items() if k.startswith('rewritable')})
        progress(fraction=0, elapsed_s=0, eta_s=0)

    try:
        options = {}
        if isinstance(recorder, PlatformEraser):
            options["before_write"] = before_write
        else:
            before_write()
        result = recorder.erase(full, cancel, progress, **options) or {}
        after = recorder.inspect()
        if cancel.is_set():
            raise BurnError('Erase was stopped; disc state is uncertain. Inspect it and erase again before burning.')
        if after.get('blank') is not True and not (result.get('overwrite_ready') and after.get('rewritable')):
            raise BurnError('The drive did not confirm blank or overwrite-ready media.')
    except disc_identity.DiscChanged:
        raise
    except (OSError, ValueError) as exc:
        ui.event('erase_result', result='cancelled' if cancel.is_set() else 'failed', reason=str(exc),
                 disc_state='unknown', next_action='inspect_and_erase_again', elapsed_s=time.monotonic()-started)
        ui.say('Erase did not finish. Disc state is uncertain; inspect it and erase again before burning.')
        raise BurnError(str(exc)) from exc
    result.update(result='completed', disc=after, elapsed_s=time.monotonic()-started)
    progress(fraction=1, elapsed_s=result['elapsed_s'], eta_s=0)
    ui.event('erase_result', **result)
    ui.say('Erase completed. The disc can be recorded again. Quick erase is not secure data removal.')
    return result


def run(args):
    cancel, stop = threading.Event(), threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    marker = os.environ.get('DISCPROBE_BURN_CANCEL')
    def watch():
        while not stop.wait(.1):
            if marker and Path(marker).exists():
                cancel.set()
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        expected = disc_identity.expected_for_write(args.drive, erasing=True)
        erase(args.drive, full=args.full, cancel=cancel, expected_identity=expected)
    except (BurnError, disc_identity.DiscChanged) as exc:
        ui.event('error', message=str(exc))
        raise SystemExit(str(exc)) from None
    finally:
        stop.set()
        watcher.join()
        signal.signal(signal.SIGINT, previous)
