"""Run exactly one CPU/8-thread base job with both themes, logging to F:."""
import json
import os
from pathlib import Path
import subprocess
import time

TRIAL = Path('F:/dp-archive/tmp/lobbypool/trial')
cmd = ['F:/dp-archive/tools/blender-5.2.2-windows-x64/blender.exe', '-b',
       str(TRIAL / 'stage/room_fax.blend'), '--disable-autoexec', '-t', '8',
       '--python-exit-code', '1', '--python', str(TRIAL / 'stage/render_fax_nightb.py'), '--',
       '--layers', 'base', '--ss', '4', '--no-mist', '--force', '--device', 'CPU',
       '--variants', 'paper,dark', '--outdir', str(TRIAL / 'F_lobby_a')]
env = dict(os.environ, TEMP=str(TRIAL), TMP=str(TRIAL), PYTHONDONTWRITEBYTECODE='1')
start = time.monotonic()
with (TRIAL / 'F_lobby_a.log').open('wb') as log:
    result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
record = dict(command=cmd, exit=result.returncode, seconds=round(time.monotonic() - start, 3),
              machine='local CPU, 8 threads', layers=['base'], variants=['paper', 'dark'])
(TRIAL / 'F_lobby_a-run.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record, indent=2))
raise SystemExit(result.returncode)
