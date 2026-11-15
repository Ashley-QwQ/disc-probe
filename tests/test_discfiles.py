"""Real files, independent directory parsing and pattern-sector exclusion."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from discprobe import discfiles as F, iso_read, imagedisc, discid, webui


@pytest.fixture
def folder(tmp_path):
    root=tmp_path/'随盘 文件'
    deep=root
    for i in range(12):
        deep=deep/f'目录{i}'
    deep.mkdir(parents=True)
    (deep/'中文 文件.txt').write_text('光盘上的中文文件\n'*300,encoding='utf-8')
    (root/'empty.bin').write_bytes(b'')
    (root/'unaligned.bin').write_bytes(bytes(range(256))*19)
    (root/'空文件夹').mkdir()
    many=root/'many'
    many.mkdir()
    for i in range(100):
        (many/f'文件{i:03}.txt').write_bytes(str(i).encode())
    stamp=dt.datetime(2020,2,3,4,5,6,tzinfo=dt.timezone.utc).timestamp()
    for parent,dirs,files in os.walk(root):
        for name in dirs+files:
            os.utime(Path(parent)/name,(stamp,stamp))
    os.utime(root,(stamp,stamp))
    return root


@pytest.mark.parametrize('where', ['inner','outer'])
def test_filesystem_and_pattern_never_overlap(folder,tmp_path,where,monkeypatch):
    layout=F.plan(folder,where,4096,margin=0)
    assert len(layout.as_dict()['occupied_lba'])==(1 if where=='inner' else 2)
    called=[]
    original=imagedisc._sector_q
    def guarded(*args,**kwargs):
        start,count=args[5:7]
        assert layout.is_picture(start,start+count)
        called.append((start,count))
        return original(*args,**kwargs)
    monkeypatch.setattr(imagedisc,'_sector_q',guarded)
    monkeypatch.setenv('DISCPROBE_WORKERS','1')
    design=np.ones((96,96),bool)
    iso=tmp_path/f'{where}.iso'
    spec=imagedisc.write_iso(str(iso),design,180000,5.5,133.3,4096,file_layout=layout,log=lambda _:None)
    assert called
    assert not imagedisc.verify_iso(iso,design,180000,5.5,133.3,4096,file_layout=layout)
    actual=iso_read.read_tree(iso,hashes=True,directories=True)
    for e in layout.entries[1:]:
        node=actual[e.relative]
        assert node['timestamp']==[120,2,3,4,5,6,0]
        if not e.directory:
            assert node['bytes']==e.size
            assert node['sha256']==hashlib.sha256(e.source.read_bytes()).hexdigest()
    primary=iso_read.read_tree(iso,joliet=False,hashes=True)
    assert sorted(x['sha256'] for x in primary.values())==sorted(x['sha256'] for x in actual.values() if 'sha256' in x)
    saved=json.loads(Path(spec).read_text(encoding='utf-8'))
    assert saved['disc_files']['picture_lba']==layout.picture_lba
    assert saved['disc_files']['sha256']=={k:v['sha256'] for k,v in actual.items() if 'sha256' in v}
    for a,b in layout.picture_lba:
        for e in layout.entries:
            if not e.directory and e.size:
                assert b<=e.lba or a>=e.lba+F.blocks(e.size)


@pytest.mark.parametrize('where', ['inner','outer'])
def test_empty_and_exact_capacity(tmp_path,where):
    source=tmp_path/'source'
    source.mkdir()
    plan=F.plan(source,where,1000,margin=0)
    assert plan.as_dict()['file_count']==0
    image=tmp_path/f'{where}.iso'
    design=np.zeros((32,32),bool)
    imagedisc.write_iso(str(image),design,180000,5.5,133.3,1000,file_layout=plan,log=lambda _:None)
    assert iso_read.read_tree(image,hashes=True)=={}
    capacity=1000-plan.metadata_end
    (source/'fit.bin').write_bytes(b'x'*(capacity*2048))
    plan=F.plan(source,where,1000,margin=0)
    assert plan.picture_lba==[]
    imagedisc.write_iso(str(image),design,180000,5.5,133.3,1000,file_layout=plan,log=lambda _:None)
    assert not imagedisc.verify_iso(image,design,180000,5.5,133.3,1000,file_layout=plan)
    assert iso_read.read_tree(image,hashes=True)['fit.bin']['sha256']==hashlib.sha256((source/'fit.bin').read_bytes()).hexdigest()
    with (source/'fit.bin').open('ab') as stream:
        stream.write(b'x')
    with pytest.raises(ValueError,match='files do not fit'):
        F.plan(source,where,1000,margin=0)


def test_limits_margin_and_large_file(tmp_path,monkeypatch):
    (tmp_path/'a').write_bytes(b'a')
    outer=F.plan(tmp_path,'outer',2000)
    assert outer.total_sectors==1888  # 95%, rounded down to DVD ECC units
    assert outer.margin==.05
    assert F.plan(tmp_path,'inner',2000).margin==0
    for margin in (-1,1,float('nan'),float('inf')):
        with pytest.raises(ValueError,match='margin'):
            F.plan(tmp_path,'outer',2000,margin=margin)
    with pytest.raises(ValueError,match='single-layer'):
        F.plan(tmp_path,'inner',2000,media='cd')
    original=Path.stat
    size=[F.MAX_FILE]
    def huge(path,*args,**kwargs):
        stat=original(path,*args,**kwargs)
        if path.name=='a':
            return SimpleNamespace(st_mode=stat.st_mode,st_size=size[0],st_mtime_ns=stat.st_mtime_ns)
        return stat
    monkeypatch.setattr(Path,'stat',huge)
    largest=F.plan(tmp_path,'inner',F.MAX_SECTORS)
    assert largest.entries[1].size==F.MAX_FILE
    assert largest.as_dict()['picture_sectors']>0
    size[0]=2**32
    with pytest.raises(ValueError,match='4 GiB-1'):
        F.plan(tmp_path,'inner',F.MAX_SECTORS)


def test_identity_copies_keep_files_intact(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir()
    (source/'a.txt').write_bytes(b'hello')
    monkeypatch.setenv('DISCPROBE_WORKERS','1')
    for where in ('inner','outer'):
        layout=F.plan(source,where,32768,margin=0,identity=True)
        iso=tmp_path/f'{where}.iso'
        imagedisc.write_iso(str(iso),np.zeros((32,32),bool),180000,5.5,133.3,32768,
                            file_layout=layout,disc_id=True,log=lambda _:None)
        identity=discid.read_image(iso,detailed=True)
        assert identity['reason']=='ok'
        assert [c['status'] for c in identity['copies']]==['ok']*4
        tree=iso_read.read_tree(iso,hashes=True)
        assert tree['a.txt']['sha256']==hashlib.sha256(b'hello').hexdigest()
        assert tree['DISCPROBE.ID']['lba']==21
        assert not imagedisc.verify_iso(iso,np.zeros((32,32),bool),180000,5.5,133.3,32768,file_layout=layout)


def test_changed_source_and_output_in_source_rejected(tmp_path):
    source=tmp_path/'source';source.mkdir()
    file=source/'a';file.write_bytes(b'one')
    layout=F.plan(source,'inner',1000)
    file.write_bytes(b'changed')
    image=tmp_path/'a.iso'
    with image.open('wb') as target:target.truncate(1000*2048)
    with pytest.raises(ValueError,match='Source changed'):
        F.write_files(image,layout)
    with pytest.raises(ValueError,match='outside the source'):
        imagedisc.write_iso(str(source/'out.iso'),np.zeros((16,16),bool),180000,5.5,133.3,1000,file_layout=layout)


def test_local_api_and_cli_share_layout(folder,tmp_path):
    from discprobe.discfiles_api import request
    layout=request(tmp_path,dict(folder=str(folder),files_at='outer',writable_sectors=4096))
    assert layout['picture_lba']==F.plan(folder,'outer',4096).picture_lba
    argv,_=webui.command(dict(action='image',args=dict(geo='summary.json',files=str(folder),files_at='outer',files_margin=.05,writable_sectors=4096)),tmp_path,[])
    assert argv[argv.index('--files')+1]==str(folder)
    with pytest.raises(ValueError,match='network'):
        request(tmp_path,dict(folder='//server/share',writable_sectors=4096))
    handler=webui.Handler.__new__(webui.Handler)
    handler.headers={'Host':'localhost:8765'};handler.client_address=('192.168.1.2',1)
    with pytest.raises(webui.APIError,match='localhost'):
        handler._local_files_only()
    handler.client_address=('127.0.0.1',1)
    handler._local_files_only()
    handler.headers={'Host':'192.168.1.2:8765'}
    with pytest.raises(webui.APIError):handler._local_files_only()


def test_image_cli_and_json_layout(folder,tmp_path):
    geometry=tmp_path/'summary.json'
    geometry.write_text(json.dumps(dict(fit=dict(media='dvd',u=180000,v=5.5,bit_nm_assumed=133.3,
                      capacity_sectors=4096,measured_span_mm=[23,59]))),encoding='utf-8')
    design=tmp_path/'drawing.npy'
    np.save(design,np.ones((6000,6000),bool))
    env={**os.environ,'DISCPROBE_WORKERS':'1','PYTHONUTF8':'1'}
    image=tmp_path/'cli.iso'
    command=[sys.executable,'-B','-m','discprobe']
    args=['--files',str(folder),'--files-at','outer','--files-margin','0','--writable-sectors','4096','--geo',str(geometry)]
    planned=subprocess.run(command+['files-layout',*args],env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert planned.returncode==0,planned.stdout+planned.stderr
    expected=json.loads(planned.stdout)
    result=subprocess.run(command+['image',*args,'--design-npy',str(design),'--output',str(image),'--no-photo-l'],
                           env=env,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    spec=json.loads(image.with_suffix('.image.json').read_text(encoding='utf-8'))
    assert spec['disc_files']['picture_lba']==expected['picture_lba']
    assert spec['disc_files']['files']==expected['files']
    assert len(iso_read.read_tree(image,hashes=True))==103
    refused=tmp_path/'refused.iso'
    stale=subprocess.run(command+['image',*args,'--design-npy',str(design),'--output',str(refused),
                                   '--no-photo-l','--files-plan-sha256','0'*64],env=env,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert stale.returncode!=0 and 'layout changed' in stale.stderr
    assert not refused.exists()
