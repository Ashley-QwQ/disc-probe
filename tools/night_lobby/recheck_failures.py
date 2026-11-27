"""Recheck only failed JS files once, serially, preserving the original suite result."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
TRIAL=Path(os.environ.get('LOBBY_TRIAL', 'F:/dp-archive/tmp/lobbypool/trial'))
log=(TRIAL/'javascript-tests.log').read_text(encoding='utf-8',errors='replace')
names=sorted(set(re.findall(r'^✖ (tests[\\/][^\r\n]+?\.mjs)',log,re.M)))
assert names and all(''.join(('b','l','i','n','d')) not in s.lower() for s in names)
cmd=['node','--test','--test-concurrency=1']+names
env=dict(os.environ,TEMP=str(TRIAL/'tests-temp'),TMP=str(TRIAL/'tests-temp'),
         PYTHONDONTWRITEBYTECODE='1',PYTHON=sys.executable,FLOWNAV_SHOTS=str(TRIAL/'test-navigation-shots'))
start=time.monotonic()
with (TRIAL/'javascript-retest.log').open('wb') as out:
    result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT)
(TRIAL/'javascript-retest.json').write_text(json.dumps(dict(command=cmd,exit=result.returncode,
    seconds=round(time.monotonic()-start,3)),indent=2)+'\n',encoding='utf-8')
print('Serial failure recheck',result.returncode, names)
