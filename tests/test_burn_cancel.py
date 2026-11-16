"""Hardware-free cancellation provenance and the finalized-short-disc gate."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from discprobe import calibrate, i18n, webui, webui_catalog
from discprobe.measurement_disc import short_recording


def test_user_cancel_is_persisted_once_and_replayed(tmp_path):
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    folder = tmp_path / 'job'
    folder.mkdir()
    job = webui.Job('j-abcd', 'TEST', folder)
    job.action = 'calibrate'
    job.child = Mock()
    job.events.write_text(json.dumps(dict(type='step', name='burn'))+'\n'+
                          json.dumps(dict(type='progress',fraction=.16))+'\n',encoding='utf-8')
    backend.jobs[job.id] = job
    cursors = {}
    backend.events(cursors)
    backend.cancel(job.id)
    backend.cancel(job.id)
    job.child.cancel.assert_called_once()
    mark = json.loads((folder/'user-cancel.json').read_text(encoding='utf-8'))
    assert mark['by'] == 'user' and mark['phase'] == 'burn' and mark['fraction'] == .16
    assert backend.job_state(job.id)['cancellation'] == mark
    assert [e for e in backend.events(cursors) if e['type']=='cancelled'] == [mark]
    assert mark in backend.events({}, reconnect=True)
    restored = webui.Job(job.id, job.drive, folder)
    restored.read()
    assert restored.cancellation == mark and mark in restored.history
    job.exit = 1
    backend.cancel(job.id)
    job.child.cancel.assert_called_once()


@pytest.mark.parametrize('action,events,phase',[
    ('info',[], 'info'),('calibrate',[dict(type='step',name='timing')],'timing'),
    ('burn',[dict(type='verify_progress',fraction=.5)],'read-back'),
])
def test_read_only_stop_provenance_is_not_burn(tmp_path,action,events,phase):
    backend=webui.Backend(tmp_path,drive_provider=lambda:[])
    folder=tmp_path/'job';folder.mkdir()
    job=webui.Job('j-abcd','TEST',folder);job.action=action;job.child=Mock()
    job.events.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
    backend.jobs[job.id]=job
    backend.cancel(job.id)
    assert job.cancellation['phase']==phase


def test_finished_job_is_not_marked_as_user_cancelled(tmp_path):
    backend=webui.Backend(tmp_path,drive_provider=lambda:[])
    job=webui.Job('j-abcd','TEST',tmp_path);job.exit=0;job.child=Mock()
    backend.jobs[job.id]=job
    backend.cancel(job.id)
    assert job.cancellation is None and not (tmp_path/'user-cancel.json').exists()
    job.child.cancel.assert_not_called()


@pytest.mark.parametrize('closed',[True,False,None])
@pytest.mark.parametrize('sectors',[576,2295104])
def test_short_recording_gate_is_conservative(closed,sectors):
    issue=short_recording(dict(closed=closed,blank=False,sectors=sectors,capacity_sectors=2295104))
    assert bool(issue)==(closed is True and sectors==576)
    if issue:
        assert '576 sectors, about 1 MB' in issue
        assert '576 扇区，约 1 MB' in i18n._zh(issue)


def test_576_finalized_disc_never_starts_timing(monkeypatch,tmp_path):
    parser=argparse.ArgumentParser();calibrate.add_parser(parser.add_subparsers())
    args=parser.parse_args(['calibrate','--drive','TEST','--out',str(tmp_path)])
    monkeypatch.setattr(calibrate.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=json.dumps(dict(
        disc=dict(present=True,media='dvd',blank=False,closed=True,sectors=576)))))
    child=Mock();monkeypatch.setattr(calibrate.subprocess,'Popen',child)
    events=[];monkeypatch.setattr(calibrate.ui,'event',lambda kind,**kw:events.append(dict(type=kind,**kw)))
    with pytest.raises(SystemExit,match='576 sectors, about 1 MB'):
        calibrate.run(args)
    child.assert_not_called()
    assert [e['name'] for e in events if e['type']=='step']==['check']
    assert any(e['type']=='measurement_disc_rejected' and e['sectors']==576 for e in events)


@pytest.mark.parametrize('status',[2,'complete'])
def test_disc_report_exposes_short_recording(status):
    report={key:dict(parsed=value) for key,value in dict(
        configuration=dict(current_profile=0x11,current_profile_name='DVD-R'),
        disc_information=dict(disc_status=status),track_1=dict(blank=False),
        capacity=dict(last_lba=575)).items()}
    disc=webui_catalog.disc_report(report)
    assert disc['closed'] is True and disc['sectors']==576
    assert disc['measurement_issue']['reason']=='short_recording'
