"""Isolated CPU-kernel compatibility probe; no evidence or validation thresholds altered."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
output=FINAL/'cpu-compat-filebox';assert not output.exists()
command=['F:/dp-archive/tools/blender-5.2.2-windows-x64/blender.exe','-b',str(FINAL/'stage/room_fax.blend'),
    '--disable-autoexec','-t','8','--python-exit-code','1','--python',str(FINAL/'stage/render_fax_nightb.py'),'--',
    '--layers','filebox','--variants','paper','--ss','4','--no-mist','--force','--device','CPU','--outdir',str(output)]
env=dict(os.environ,TEMP=str(FINAL),TMP=str(FINAL),PYTHONDONTWRITEBYTECODE='1',CYCLES_CPU_NO_AVX2='1')
start=time.monotonic()
with (FINAL/'cpu-compat-filebox.log').open('wb') as log:
    child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    set_priority=ctypes.windll.kernel32.SetPriorityClass
    set_priority.argtypes=[wintypes.HANDLE,wintypes.DWORD];set_priority.restype=wintypes.BOOL
    assert set_priority(wintypes.HANDLE(int(child._handle)),0x4000)
    result=child.wait()
record=dict(command=command,exit=result,seconds=round(time.monotonic()-start,3),
    environment=dict(CYCLES_CPU_NO_AVX2='1'),priority='BELOW_NORMAL',purpose='Test reproduction compatibility with original pre-AVX2 x79 CPU; paper only; no publication')
(FINAL/'cpu-compat-filebox-run.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(record)
assert result==0
