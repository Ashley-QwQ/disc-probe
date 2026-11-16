"""Run the card's JS suite and related Python checks once, with temp data on F:."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TRIAL = Path(os.environ.get('LOBBY_TRIAL', 'F:/dp-archive/tmp/lobbypool/trial'))
temp = TRIAL / 'tests-temp'
temp.mkdir(exist_ok=True)
free = {d: shutil.disk_usage(d + ':/').free for d in ('D', 'F')}
assert min(free.values()) >= 5_000_000_000, free
env = dict(os.environ, TEMP=str(temp), TMP=str(temp), PYTHONDONTWRITEBYTECODE='1',
           PYTHON=sys.executable, FLOWNAV_SHOTS=str(TRIAL / 'test-navigation-shots'),
           BRAND_TEST_TEMP=str(temp / 'brand'))
glob = '*[bB][lL][iI][nN][dD]*'
files = subprocess.check_output(['rg', '--files', 'tests', '-g', 'test_*.mjs',
    '-g', '!**/' + glob + '/**', '-g', '!**/' + glob], cwd=ROOT, text=True).splitlines()
assert files and all(''.join(('b','l','i','n','d')) not in s.lower() for s in files)
commands = [
    ('javascript', ['node', '--test', '--test-concurrency=2'] + sorted(files)),
    ('python', [sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-n', '2',
                '-p', 'no:cacheprovider', '--basetemp', str(temp / 'pytest'), 'tests/test_night_pool.py']),
]
records = []
for name, command in commands:
    start = time.monotonic()
    with (TRIAL / (name + '-tests.log')).open('wb') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    records.append(dict(name=name, command=command, exit=result.returncode,
                        seconds=round(time.monotonic() - start, 3)))
    (TRIAL / 'tests.json').write_text(json.dumps(dict(free_bytes_before=free, results=records), indent=2) + '\n', encoding='utf-8')
    print(name, result.returncode, records[-1]['seconds'], flush=True)
