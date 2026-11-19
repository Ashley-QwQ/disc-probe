"""Rewritable state transitions and destructive gates, without physical devices."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import Mock, patch

import pytest

from discprobe import burner, eraser, mmc, webui, webui_catalog, i18n
from discprobe.measurement_disc import short_recording
from disclab.box import make_box
from disclab.drive import LabRecorder, LabDrive, erase_seconds, burn_seconds
from disclab.lab import Lab
from discprobe.info import quick
from tests.iso_fixture import write_checked_iso


@pytest.mark.parametrize('profile', [0x0A, 0x13, 0x14, 0x1A, 0x2A, 0x43])
def test_profiles_are_rewritable_without_erasable(profile):
    report = {'configuration': {'parsed': {'current_profile': profile}},
              'disc_information': {'parsed': {'erasable': False}}}
    disc = webui_catalog.disc_report(report)
    assert disc['rewritable'] is True
    assert disc['rewritable_sources'] == dict(current_profile=profile, profile_rewritable=True, erasable=False)


@pytest.mark.parametrize('profile', [None, 0, 0x09, 0x11, 0x1B, 0x41, 0x42])
def test_erasable_bit_and_write_once(profile):
    assert mmc.rewritable(profile, False)['rewritable'] is False
    assert mmc.rewritable(profile, True)['rewritable'] is True
    assert mmc.rewritable(profile)['rewritable_sources']['erasable'] is None


def recorder(tmp_path, monkeypatch, media='dvd-rw'):
    monkeypatch.setenv('DISCPROBE_HOME', str(tmp_path))
    monkeypatch.setenv('DISCLAB_BURN_TIME', 'quick')
    lab=Lab(tmp_path/'lab')
    make_box(lab, media, 1, seed=1)
    with lab.locked_state() as state:
        state['drives']['X:']['tray']=lab.box()['discs'][0]
    rec=LabRecorder(lab,'X:','cd' if media.startswith('cd') else 'bd' if media.startswith('bd') else 'dvd')
    return lab,rec


@pytest.mark.parametrize('media', ['dvd-rw','cd-rw','dvd+rw','bd-re'])
def test_lab_burn_erase_burn(tmp_path,monkeypatch,media):
    lab,rec=recorder(tmp_path,monkeypatch,media)
    image=write_checked_iso(tmp_path/'data.iso', bytes(2048*32))
    stop=threading.Event()
    rec.write(image,4,stop,lambda **_:None)
    assert rec.inspect()['blank'] is False
    disc=webui_catalog.disc_report(quick(LabDrive(lab,'X:')))
    assert disc['rewritable_sources']['erasable'] is True
    result=eraser.erase('X:',recorder=rec)
    assert result['result']=='completed' and rec.inspect()['blank'] is True
    rec.write(image,4,stop,lambda **_:None)
    assert rec.inspect()['blank'] is False


def test_write_once_refuses_before_erase(tmp_path,monkeypatch):
    _,rec=recorder(tmp_path,monkeypatch,'dvd-r')
    with patch.object(rec,'erase') as action:
        with pytest.raises(burner.BurnError,match='not rewritable'):
            eraser.erase('X:',recorder=rec)
        action.assert_not_called()


def test_explicit_erase_and_preflight(tmp_path,monkeypatch):
    _,rec=recorder(tmp_path,monkeypatch)
    image=write_checked_iso(tmp_path/'data.iso', bytes(2048*32))
    rec.write(image,4,threading.Event(),lambda **_:None)
    with patch.object(rec,'erase',wraps=rec.erase) as action:
        with pytest.raises(burner.BurnError,match='--erase'):
            burner.burn('X:',image,recorder=rec,yes_write=True)
        action.assert_not_called()
        with pytest.raises(burner.BurnError,match='Wrong disc kind'):
            burner.burn('X:',image,media='cd',recorder=rec,yes_write=True,erase=True)
        with pytest.raises(burner.BurnError,match='Unsupported write speed'):
            burner.burn('X:',image,speed=99,recorder=rec,yes_write=True,erase=True)
        action.assert_not_called()
        result=burner.burn('X:',image,recorder=rec,yes_write=True,erase=True,no_verify=True,
                           state_checker=lambda *a,**k:dict(status='completed'))
        assert result['result']=='completed'
        action.assert_called_once()


def test_partial_cancel_preserved_and_erase_cancellation(tmp_path,monkeypatch):
    lab,rec=recorder(tmp_path,monkeypatch)
    image=tmp_path/'data.iso';image.write_bytes(bytes(2048*100))
    stop=threading.Event()
    def progress(**fields):
        if fields.get('fraction',0)>=.5:stop.set()
    with pytest.raises(OSError,match='partial recording'):
        rec.write(image,4,stop,progress)
    disc=lab.state()['drives']['X:']['tray']
    before=lab.state()['burns'][disc]
    assert 0<before['sessions'][0]['sectors']<100
    stop.clear()
    with patch.object(eraser.ui,'event') as event:
        def interrupted(full,cancel,progress):
            cancel.set()
            raise burner.BurnError('stopped')
        with patch.object(rec,'erase',side_effect=interrupted):
            with pytest.raises(burner.BurnError,match='stopped'):
                eraser.erase('X:',recorder=rec,cancel=stop)
        assert any(c.args[0]=='erase_result' and c.kwargs['result']=='cancelled' for c in event.call_args_list)
    assert lab.state()['burns'][disc]==before


def test_erase_time_scale():
    assert erase_seconds(2298496,'dvd',False,'real')==pytest.approx(60)
    assert erase_seconds(2298496,'dvd',False,'.3')==pytest.approx(18)
    assert erase_seconds(2298496,'dvd',True,'real')==burn_seconds(2298496,1,'dvd','real')


@pytest.mark.parametrize('profile',[0x13,0x1A,0x2A,0x43])
def test_formatted_random_access_capacity(profile):
    from discprobe.capacity import recordable_capacity
    report=dict(configuration=dict(parsed=dict(current_profile=profile)),capacity=dict(parsed=dict(last_lba=999)))
    assert recordable_capacity(report)==(1000,'formatted rewritable address space (READ CAPACITY)')
    report['configuration']['parsed']['current_profile']=0x14
    assert recordable_capacity(report) is None


@pytest.mark.parametrize('media',['dvd-rw','cd-rw'])
def test_hooked_cli_erase_and_explicit_burn(tmp_path,monkeypatch,media):
    from disclab.__main__ import lab_env
    lab,rec=recorder(tmp_path,monkeypatch,media)
    image=write_checked_iso(tmp_path/'data.iso', bytes(2048*32))
    rec.write(image,4,threading.Event(),lambda **_:None)
    env=lab_env(lab)
    def cli(*args):
        return subprocess.run([sys.executable,'-X','utf8','-B','-m','discprobe',*map(str,args)],
                              cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    args=['burn','--drive','X:','--media',rec.media,'--iso',image,'--yes-write','--no-verify']
    refused=cli(*args)
    assert refused.returncode!=0 and '--erase' in refused.stdout+refused.stderr
    done=cli(*args,'--erase')
    assert done.returncode==0,done.stdout+done.stderr
    assert rec.inspect()['blank'] is False
    cleared=cli('erase','--drive','X:')
    assert cleared.returncode==0,cleared.stdout+cleared.stderr
    assert rec.inspect()['blank'] is True


def test_short_disc_copy():
    disc=dict(closed=True,blank=False,sectors=576,rewritable=True)
    en=short_recording(disc)
    assert 'Erase this rewritable disc' in en
    with patch.object(i18n,'_lang','zh'):
        assert '擦除这张可擦写盘' in i18n.tr(en)
    assert 'Replace it with a blank disc' in short_recording(dict(disc,rewritable=False))


def test_erase_action_has_token_and_flag_allowlist(tmp_path):
    argv,drive=webui.command(dict(action='erase',drive='X:',media='dvd',args=dict(full=True)),tmp_path,[dict(id='X:')])
    assert drive=='X:' and '--full' in argv and 'erase' in argv
    backend=webui.Backend(tmp_path,drive_provider=lambda:[dict(id='X:',disc=dict(blank=False,rewritable=True))])
    with pytest.raises(webui.APIError,match='token'):
        backend.start(dict(action='erase',drive='X:',media='dvd',args={}))


@pytest.mark.skipif(os.name!='nt',reason='Windows compiler-only fake COM test')
def test_compiled_imapi_erase_with_fake_com(tmp_path):
    script=Path(__file__).resolve().parents[1]/'tools/erase_imapi.ps1'
    source=script.read_text(encoding='utf-8').split("-TypeDefinition @'",1)[1].split("'@",1)[0]
    fake=r'''
public class EraseMaster { public int Count=1; public string this[int i] { get {return "recorder";} } }
public class EraseRecorder {
    public object[] CurrentProfiles; public string[] VolumePathNames=new string[]{"X:\\"};
    public void InitializeDiscRecorder(string name){}
}
public class EraseFormat {
    public object Recorder; public string ClientName; public bool FullErase; public bool Called;
    public bool IsCurrentMediaSupported(object rec){return true;}
    public void EraseMedia(){Called=true;}
}
public static class EraseHarness {
    public static void Run() {
        foreach(int profile in new int[]{0x0A,0x13,0x14,0x1A,0x43,0x11})foreach(bool full in new bool[]{false,true}) {
            var recorder=new EraseRecorder{CurrentProfiles=new object[]{profile}};
            var format=new EraseFormat(); int attached=0,detached=0; bool refused=false;
            try {
                MachineErase.RunWithFactory("X:",full,
                    n=>n.EndsWith("Master2")?(object)new EraseMaster():n.EndsWith("Recorder2")?(object)recorder:format,
                    (f,h)=>{attached++;h(f,12,60);},(f,h)=>{detached++;});
            } catch(InvalidOperationException){refused=true;}
            if(profile==0x11){if(!refused||format.Called)throw new Exception("write-once erase");}
            else if(refused||!format.Called||format.FullErase!=full||attached!=1||detached!=1)
                throw new Exception("erase dispatch or cleanup");
        }
        Console.WriteLine("FAKE_ERASE_PASSED");
    }
}
'''
    fixture=tmp_path/'fake-erase.ps1'
    fixture.write_text("$ErrorActionPreference='Stop'\nAdd-Type -ReferencedAssemblies System.dll,System.Core.dll,Microsoft.CSharp.dll -TypeDefinition @'\n"+source+fake+"\n'@\n[EraseHarness]::Run()\n",encoding='utf-8-sig')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(fixture)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'FAKE_ERASE_PASSED' in result.stdout


@pytest.mark.parametrize('full', [False,True])
@pytest.mark.parametrize('profile,expected', [(0x0A,'blank='),(0x14,'-blank'),(0x13,'-blank'),(0x1A,'-force'),(0x43,'-force')])
def test_linux_erase_tool_dispatch(monkeypatch,profile,expected,full):
    adapter=eraser.PlatformEraser('/dev/fake')
    disc=dict(rewritable=True,rewritable_sources=dict(current_profile=profile))
    process=Mock(stdout=[],wait=Mock(return_value=0))
    monkeypatch.setattr(eraser.sys,'platform','linux')
    with patch.object(adapter,'inspect',return_value=disc),patch.object(eraser,'tool',side_effect=lambda x:x),patch('shutil.which',return_value='wodim'),patch.object(eraser.subprocess,'Popen',return_value=process) as launch:
        adapter.erase(full,threading.Event(),lambda **_:None)
    args=launch.call_args.args[0]
    assert any(a.startswith(expected) for a in args)
    if full:assert any('full' in a or a=='blank=all' for a in args)
