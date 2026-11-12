"""Run the requested frozen baseline in a new, filtered temporary copy."""
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/editor/round2'
OUT.mkdir(parents=True,exist_ok=True)

def main():
    commit=subprocess.check_output(['git','rev-parse','ac41295'],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive','--format=zip',commit],cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='dp-editor-ac41295-') as folder:
        base=Path(folder).resolve();count=0;excluded=0
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for info in z.infolist():
                if re.search('b[l]ind',info.filename,re.I):excluded+=1;continue
                target=(base/info.filename).resolve()
                if not target.is_relative_to(base):raise ValueError('archive path leaves temporary copy')
                if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info));count+=1
        env={**os.environ,'PYTHONPATH':str(base),'PYTHONIOENCODING':'utf-8','DISCPROBE_WORKERS':'1'}
        with (OUT/'selftest-base-ac41295.txt').open('w',encoding='utf8') as log:
            r=subprocess.run([sys.executable,'-m','discprobe','selftest'],cwd=base,env=env,stdout=log,stderr=subprocess.STDOUT)
        (OUT/'base-copy.json').write_text(json.dumps(dict(commit=commit,temporary_copy=str(base),files=count,excluded_path_entries=excluded,exit=r.returncode,source_worktrees_modified=False),indent=2),encoding='utf8')
        print(f'baseline {commit}: exit {r.returncode}; {count} files in temporary copy',flush=True)

if __name__=='__main__':main()
