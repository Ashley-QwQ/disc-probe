"""Run existing Node tests sequentially, offline, and inspect template palette schema."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    if sys.argv[1]=='template':
        for p,ds,fs in os.walk('D:/disc-probe/.claude/worktrees/editor-template'):
            ds[:]=[d for d in ds if d!='.git' and not re.search('b[l]ind',d,re.I)]
            if 'swatches.json' in fs:
                f=Path(p)/'swatches.json';d=json.loads(f.read_text(encoding='utf-8-sig'))
                print(f);print(json.dumps(d,ensure_ascii=True)[:3200])
        return
    output=ROOT/sys.argv[2] if len(sys.argv)>2 else ROOT/'evidence/editor'
    output.mkdir(parents=True,exist_ok=True)
    log=output/'node-tests.txt';results=[]
    files=sorted(p for p in (ROOT/'tests').iterdir() if p.name.startswith('test_') and p.suffix in ('.mjs','.cjs') and not re.search('b[l]ind',p.name,re.I))
    with log.open('w',encoding='utf8') as f:
        for p in files:
            r=subprocess.run(['node',str(p)],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=240)
            f.write(f'\n{p.name}: exit {r.returncode}\n{r.stdout}\n{r.stderr}')
            results.append(dict(file=p.name,exit=r.returncode))
    (output/'node-summary.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(f'{sum(r["exit"]==0 for r in results)}/{len(results)} Node files passed')
    sys.exit(any(r['exit'] for r in results))

if __name__=='__main__':main()
