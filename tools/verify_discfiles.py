"""Reproducible card-L acceptance: independent parse, Windows mount, virtual burn.

All artifacts stay under --root (use a D: path on this host). No real optical
drive is enumerated or opened. Windows mounts are always dismounted in finally.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe import discfiles as F, imagedisc, iso_read, mmc


def digest(path):
    with open(path,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def powershell(script):
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-File',str(script)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    if result.returncode:
        raise RuntimeError(result.stdout+'\n'+result.stderr)
    return result.stdout.strip()


def mount_check(image,source,artifacts):
    def literal(path):return str(path).replace("'","''")
    mount=artifacts/'mount.ps1';unmount=artifacts/'unmount.ps1'
    prefix="$ErrorActionPreference='Stop'\n[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)\n"
    mount.write_text(prefix+f"$disk=Mount-DiskImage -ImagePath '{literal(image)}' -StorageType ISO -PassThru\n"+
        "$volume=$disk | Get-Volume\nif (!$volume.DriveLetter) { throw 'No mounted drive letter' }\n"+
        "Write-Output ($volume.DriveLetter + ':\\')\n",encoding='utf-8-sig')
    unmount.write_text(prefix+f"Dismount-DiskImage -ImagePath '{literal(image)}'\n",encoding='utf-8-sig')
    count=total=0
    try:
        drive=Path(powershell(mount).splitlines()[-1])
        expected={p.relative_to(source).as_posix():p for p in source.rglob('*')}
        actual={p.relative_to(drive).as_posix():p for p in drive.rglob('*')}
        assert set(expected)==set(actual),(set(expected)-set(actual),set(actual)-set(expected))
        times=0
        for name,path in expected.items():
            target=actual[name]
            assert path.is_dir()==target.is_dir(),name
            assert int(path.stat().st_mtime)==int(target.stat().st_mtime),(name,path.stat().st_mtime,target.stat().st_mtime)
            times+=1
            if path.is_file():
                assert digest(path)==digest(target),name
                count+=1;total+=path.stat().st_size
        return dict(status='PASS',files=count,bytes=total,sha256_equal=count,timestamps_equal=times)
    finally:
        powershell(unmount)


def lab_check(image,artifacts):
    from disclab.lab import Lab
    from disclab.box import make_box
    from disclab.__main__ import lab_env
    from disclab.drive import LabDrive
    from discprobe.scsi import DATA_IN
    lab=Lab(artifacts/'virtual-lab')
    make_box(lab,'dvd-r',1,seed=17)
    with lab.locked_state() as state:
        state['drives']['X:']['tray']=lab.box()['discs'][0]
    result=subprocess.run([sys.executable,'-B','-m','disclab','dp','--lab',str(lab.root),'--',
                           'burn','--drive','X:','--iso',str(image),'--yes-write'],
                          cwd=ROOT,env=lab_env(lab),capture_output=True,text=True,encoding='utf-8',timeout=180)
    (artifacts/'virtual-burn.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
    total=image.stat().st_size//2048
    got=hashlib.sha256();want=hashlib.sha256()
    with image.open('rb') as source,LabDrive(lab,'X:') as drive:
        for lba in range(0,total,128):
            n=min(128,total-lba)
            reply=drive.execute(mmc.read10(lba,n),n*2048,DATA_IN)
            assert reply.ok,(lba,reply.sense)
            data=source.read(n*2048)
            assert reply.data==data,lba
            got.update(reply.data);want.update(data)
    return dict(status='PASS',sectors=total,bytes=total*2048,sha256=got.hexdigest(),iso_sha256=want.hexdigest())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--mount',action='store_true')
    parser.add_argument('--lab',action='store_true')
    args=parser.parse_args()
    args.root.mkdir(parents=True,exist_ok=True)
    os.environ['DISCPROBE_WORKERS']='2'
    source=args.root/'source 中文 files';source.mkdir(exist_ok=True)
    deep=source
    for i in range(12):deep=deep/f'深目录{i:02}'
    deep.mkdir(parents=True,exist_ok=True)
    (source/'空文件夹').mkdir(exist_ok=True)
    (source/'说明.txt').write_text('随盘文件与图案共存。\n'*127,encoding='utf-8')
    (source/'zero.bin').write_bytes(b'')
    (deep/'中文 数据.bin').write_bytes(bytes(range(256))*257+b'end')
    many=source/'多文件';many.mkdir(exist_ok=True)
    for i in range(130):(many/f'条目 {i:03}.txt').write_text(f'文件 {i}\n',encoding='utf-8')
    stamp=dt.datetime(2020,2,3,4,5,6,tzinfo=dt.timezone.utc).timestamp()
    for path in sorted(source.rglob('*'),reverse=True):os.utime(path,(stamp,stamp))
    os.utime(source,(stamp,stamp))
    expected={p.relative_to(source).as_posix():dict(bytes=p.stat().st_size,sha256=digest(p)) for p in source.rglob('*') if p.is_file()}
    (args.root/'source-manifest.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
    results={}
    for where in ('inner','outer'):
        work=args.root/where;work.mkdir(exist_ok=True)
        plan=F.plan(source,where,32768)
        design=imagedisc.grid_design(size=256)
        image=work/f'{where}.iso'
        print('Generating',image,flush=True)
        imagedisc.write_iso(str(image),design,180000,5.5,133.3,plan.total_sectors,file_layout=plan,log=lambda _:None)
        assert not imagedisc.verify_iso(image,design,180000,5.5,133.3,plan.total_sectors,file_layout=plan)
        tree=iso_read.read_tree(image,hashes=True)
        assert {name:{k:node[k] for k in ('bytes','sha256')} for name,node in tree.items()}==expected
        primary=iso_read.read_tree(image,joliet=False,hashes=True)
        assert sorted(n['sha256'] for n in primary.values())==sorted(n['sha256'] for n in expected.values())
        results[where]=dict(layout=plan.as_dict(),independent=dict(status='PASS',files=len(tree),bytes=sum(n['bytes'] for n in tree.values()),
              sha256_equal=len(tree),primary_files=len(primary)),mount=dict(status='NOT_RUN'),virtual=dict(status='NOT_RUN'))
        # Save partial evidence as well, so an unavailable Windows service is explicit.
        for name,enabled,fn in (('mount',args.mount,mount_check),('virtual',args.lab,lab_check)):
            if enabled:
                try:results[where][name]=fn(image,source,work) if name=='mount' else fn(image,work)
                except Exception as exc:results[where][name]=dict(status='FAIL',error=str(exc))
        (args.root/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(where,{k:v for k,v in results[where].items() if k!='layout'},flush=True)
    if any(result[key]['status']=='FAIL' for result in results.values() for key in ('mount','virtual')):return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
