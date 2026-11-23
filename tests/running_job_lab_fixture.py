"""A recorded virtual DVD, with optional pacing in its simulated drive."""
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from disclab.__main__ import lab_env
    from disclab.practice import prepare

    lab = prepare(Path(sys.argv[1]))
    with lab.locked_state() as state:
        disc = state['drives']['X:']['tray']
        sectors = lab.answers()['discs'][disc]['capacity']
        # The hook supplies deterministic random sectors without allocating a DVD image.
        state.setdefault('burns', {})[disc] = dict(closed=True, sessions=[
            dict(iso=str(lab.root / 'recorded.iso'), start_lba=0, sectors=sectors,
                 speed_x=4, writer='imapi', mode='dvd', drive='X:')])
    hook = lab.root / 'test-hook'
    hook.mkdir()
    (hook / 'sitecustomize.py').write_text('''
import sys
import time
import os
from pathlib import Path
from disclab.boot import sitecustomize

import numpy as np
from disclab.drive import LabDrive

def contents(self, lba, count):
    return b"".join(np.random.default_rng(sector).bytes(2048)
                    for sector in range(lba, lba + count))

LabDrive._content = contents

if any(arg == "geo" for arg in sys.orig_argv):
    execute = LabDrive.execute

    def paced(self, cdb, *args, **kwargs):
        if cdb[0] in (0x28, 0xa8):
            time.sleep(.009)
        return execute(self, cdb, *args, **kwargs)

    LabDrive.execute = paced
    from discprobe import ui

    event = ui.event
    lab = Path(os.environ["DISCPROBE_DISCLAB"])
    remaining = 4800
    paused = False
    progress_count = 0

    def wait_for(name):
        deadline = time.monotonic() + 120
        while not (lab / name).exists() and time.monotonic() < deadline:
            time.sleep(.025)

    def send_progress(fields):
        global progress_count
        if not progress_count:
            wait_for("memory-sample-0")
        event("progress", **fields)
        progress_count += 1
        if progress_count % 240 == 0:
            wait_for(f"memory-sample-{progress_count // 240}")

    def observe(kind, **fields):
        global paused, remaining
        if kind != "progress":
            event(kind, **fields)
            return
        if os.environ.get("RUNJOB_MEMORY"):
            # A real long-running page receives up to four updates per second.
            # Replay that event volume through the real job and HTTP paths.
            send_progress(fields)
            for _ in range(min(48, remaining)):
                eta = fields.get("eta_s")
                send_progress({**fields, "eta_s": (eta or 0) + remaining / 4800})
                remaining -= 1
        else:
            event(kind, **fields)
            if not paused and (fields.get("fraction") or 0) >= .48:
                paused = True
                (lab / "midpoint").touch()
                wait_for("continue")

    ui.event = observe
''', encoding='utf-8')
    env = lab_env(lab)
    env['PYTHONPATH'] = os.pathsep.join((str(hook), env['PYTHONPATH']))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    print(f'PORT {port}', flush=True)
    return subprocess.call([sys.executable, '-B', '-m', 'discprobe', 'webui', '--new-instance',
                            '--local-only', '--port', str(port)], cwd=lab.root, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
