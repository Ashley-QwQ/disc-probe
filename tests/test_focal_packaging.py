"""Keep locally regenerated focal maps out of every source packaging route."""
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(relative):
    spec=importlib.util.spec_from_file_location('focal_packaging_tool',ROOT/relative)
    tool=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def fixture(root):
    data=root/'data/focal'
    data.mkdir(parents=True)
    (data/'delta_map_1x.npy').write_bytes(b'local cache; never package')
    (data/'pose_1x.json').write_text('{}\n',encoding='utf-8')
    (root/'release-build.json').write_text('{}\n',encoding='utf-8')


def test_wheel_and_sdist_file_selection_excludes_local_map(tmp_path,monkeypatch):
    backend=load('_build_backend.py')
    fixture(tmp_path)
    monkeypatch.setattr(backend,'ROOT',tmp_path)
    assert [relative for _,relative in backend.files('data')] == ['data/focal/pose_1x.json']


@pytest.mark.parametrize('mode',['worktree','ref','snapshot'])
def test_windows_source_selection_excludes_even_tracked_map(tmp_path,monkeypatch,mode):
    tool=load('tools/build_winpack.py')
    source=tmp_path/'source';source.mkdir()
    fixture(source)
    if mode != 'snapshot':
        for args in [('init','--quiet'),('add','data','release-build.json'),
                     ('-c','user.name=Focal Test','-c','user.email=focal@example.invalid',
                      'commit','--quiet','-m','packaging fixture')]:
            subprocess.run(['git','-C',str(source),*args],check=True,capture_output=True)
    monkeypatch.setattr(tool,'HERE',str(source))
    monkeypatch.setattr(tool,'SOURCE',('data',))
    target=tmp_path/'package'
    args=SimpleNamespace(source_root=str(source) if mode=='snapshot' else None,
                         worktree=mode=='worktree',ref='HEAD')
    tool.copy_source(args,str(target))
    assert (target/'data/focal/pose_1x.json').is_file()
    assert not (target/'data/focal/delta_map_1x.npy').exists()
