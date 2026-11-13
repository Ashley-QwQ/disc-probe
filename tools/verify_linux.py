"""Copy cached wheels over SSH and check a fresh offline Linux installation.

No drive access; all remote work is below ~/dp-release-check/, nice 19, <=2 CPUs.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', choices=('x79', 'agentbox'), default='x79')
    ap.add_argument('--wheel', type=Path, required=True)
    ap.add_argument('--wheelhouse', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    wheel = args.wheel.resolve()
    inputs = [wheel, *sorted(args.wheelhouse.resolve().glob('*.whl'))]
    for path in inputs:
        if any('b' + 'lind' in p.casefold() for p in path.parts):
            ap.error('excluded input path')
        if not path.is_file():
            ap.error('missing wheel: ' + str(path))
    if len({p.name for p in inputs}) != len(inputs):
        ap.error('duplicate wheel filenames')
    inventory = []
    for p in inputs:
        with p.open('rb') as f:
            inventory.append(dict(file=p.name, size=p.stat().st_size, sha256=hashlib.file_digest(f,'sha256').hexdigest()))
    run = 'a9-' + str(time.time_ns())
    config = dict(run=run, wheel=wheel.name, inputs=inventory)
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', args.host, 'python3', '-']
    common = f"""import os,sys,json,base64,pathlib,subprocess,hashlib
cfg=json.loads(base64.b64decode('{encoded}'))
os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:])); os.nice(19)
root=pathlib.Path.home()/'dp-release-check'/cfg['run']
"""

    def remote(stage, script):
        done = subprocess.run(ssh,input=common+script,text=True,encoding='utf-8',capture_output=True)
        (out/(stage+'.log')).write_text(done.stdout+done.stderr,encoding='utf-8')
        if done.returncode:
            raise RuntimeError(f'{stage} failed ({done.returncode}); see {out/(stage+".log")}')

    result = dict(status='RUNNING',host=args.host,remote_root='~/dp-release-check/'+run,inputs=inventory)
    try:
        remote('preflight', """root.mkdir(parents=True,exist_ok=False)
(root/'wheelhouse').mkdir()
print(json.dumps(dict(root=str(root),affinity=sorted(os.sched_getaffinity(0)),nice=os.nice(0))))
""")
        destination = args.host+':dp-release-check/'+run+'/'
        subprocess.run(['scp', '-o', 'BatchMode=yes', *map(str,inputs), destination+'wheelhouse/'],check=True)
        verifier = Path(__file__).with_name('verify_package.py')
        subprocess.run(['scp','-o','BatchMode=yes',str(verifier),destination+'verify_package.py'],check=True)
        remote('verify', """for item in cfg['inputs']:
 p=root/'wheelhouse'/item['file']
 with p.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
def call(name,cmd):
 with (root/(name+'.log')).open('w') as log: subprocess.run(cmd,env=env,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
call('venv',['python3','-m','venv',str(root/'venv')])
py=str(root/'venv/bin/python')
call('install',[py,'-m','pip','install','--no-index','--find-links',str(root/'wheelhouse'),str(root/'wheelhouse'/cfg['wheel'])])
call('pip-check',[py,'-m','pip','check'])
call('package-verify',[py,'-B',str(root/'verify_package.py'),'--artifact',str(root/'wheelhouse'/cfg['wheel']),'--expected-root',str(root/'venv'),'--out',str(root/'proof')])
proof=json.loads((root/'proof/proof.json').read_text())
proof['offline_inputs']=cfg['inputs']
proof['host']=os.uname().nodename
proof['affinity']=sorted(os.sched_getaffinity(0)); proof['nice']=os.nice(0)
(root/'linux-proof.json').write_text(json.dumps(proof,indent=2))
print('PASS')
""")
        subprocess.run(['scp','-o','BatchMode=yes',destination+'linux-proof.json',str(out/'proof.json')],check=True)
        result['status']='PASS'
    except BaseException as exc:
        result['status']='BLOCKED'; result['error']=str(exc)
        raise
    finally:
        (out/'status.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
