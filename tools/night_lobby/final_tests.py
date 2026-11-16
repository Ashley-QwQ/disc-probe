"""One related Python run and one complete allowed-path JS run, with F: temp files."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
p=argparse.ArgumentParser();p.add_argument('phase',choices=['python','javascript']);p.add_argument('--after-fix',action='store_true');options=p.parse_args();phase=options.phase
temp=FINAL/'tests-temp';temp.mkdir(exist_ok=True)
free={d:shutil.disk_usage(d+':/').free for d in ('D','F')};assert min(free.values())>=5_000_000_000
record=json.loads((FINAL/'tests.json').read_text(encoding='utf-8')) if (FINAL/'tests.json').exists() else dict(results=[])
previous=[row for row in record['results'] if row['name']==phase]
if previous:
    assert options.after_fix and previous[-1]['exit']!=0, 'Repeat only after fixing a recorded failure'
    shutil.copyfile(FINAL/(phase+'-tests.log'),FINAL/(phase+'-tests-before-fix.log'))
    for row in previous:row['name']=phase+'-before-fix'
if phase=='python':
    command=[sys.executable,'-X','utf8','-B','-m','pytest','-n','2','-p','no:cacheprovider',
        '--basetemp',str(temp/'pytest'),'tests/test_night_pool.py']
else:
    glob='*[bB][lL][iI][nN][dD]*'
    files=subprocess.check_output(['rg','--files','tests','-g','test_*.mjs','-g','!**/'+glob+'/**','-g','!**/'+glob],cwd=ROOT,text=True).splitlines()
    command=['node','--test','--test-concurrency=2']+sorted(files)
env=dict(os.environ,TEMP=str(temp),TMP=str(temp),PYTHONDONTWRITEBYTECODE='1',PYTHON=sys.executable,
    FLOWNAV_SHOTS=str(FINAL/'test-navigation-shots'),BRAND_TEST_TEMP=str(temp/'brand'))
start=time.monotonic()
with (FINAL/(phase+'-tests.log')).open('wb') as log:
    result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
record['results'].append(dict(name=phase,command=command,exit=result.returncode,
    seconds=round(time.monotonic()-start,3),free_bytes_before=free))
(FINAL/'tests.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(phase,result.returncode,record['results'][-1]['seconds'])
