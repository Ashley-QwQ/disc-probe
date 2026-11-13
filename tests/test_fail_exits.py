"""A6 exits: fake transports and saved records only; never open a device."""
import argparse
import ctypes
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

from discprobe import diagnostics, info, mmc, timing
from discprobe.scsi import ScsiResult, execute_probe


class Fake:
    name = 'FAKE'

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def execute(self, cdb, data_len=0, direction=1, timeout_s=None):
        self.calls.append((cdb, data_len, direction, timeout_s))
        assert 0 < timeout_s <= 5
        if self.fail is None or cdb[0] == self.fail:
            raise TimeoutError('fake timeout')
        return ScsiResult(0, b'', None, 0, 100)

    def close(self):
        pass


@pytest.mark.parametrize('opcode', [0x00, 0x12, 0x25, 0x46, 0x51, 0x52, 0x5A, 0x43, 0xAD, 0xAC])
def test_info_every_step_has_native_timeout_and_next_action(opcode):
    dev = Fake(opcode)
    report = info.collect(dev)
    matching = [entry for entry in report.values() if entry.get('cdb', '').startswith(f'{opcode:02x}')]
    assert matching and all('error' in entry for entry in matching)
    assert all('same disc' in entry['error'] for entry in matching)
    assert all(call[3] == 3 for call in dev.calls)


def test_info_ignored_driver_timeout_never_reuses_handle(monkeypatch):
    release = threading.Event()
    dev = Fake()
    def blocked(*args, **kwargs):
        dev.calls.append(args)
        release.wait(10)
        return ScsiResult(0, b'', None, 0, 0)
    dev.execute = blocked
    monkeypatch.setattr(info, 'COMMAND_TIMEOUT_S', .01)
    # Shorten only the test's wall bound, preserving the production native bound.
    real = info.InfoDevice._call
    monkeypatch.setattr(info.InfoDevice, '_call', lambda self, call, seconds, step: real(self, call, .02, step))
    bounded = info.InfoDevice(dev)
    try:
        report = info.collect(bounded)
        assert len(dev.calls) == 1
        assert bounded.failed and 'INQUIRY' in report['inquiry']['error']
        assert 'same disc' in report['test_unit_ready']['error']
    finally:
        release.set()
        bounded.close()


def test_info_open_execute_close_stay_on_one_worker():
    threads = []
    class Device:
        def __init__(self):
            threads.append(threading.get_ident())
        def execute(self, *args, **kwargs):
            threads.append(threading.get_ident())
            return ScsiResult(0, b'', None, 0, 0)
        def close(self):
            threads.append(threading.get_ident())
    dev = info.InfoDevice(opener=Device)
    dev.execute(mmc.test_unit_ready())
    dev.close()
    assert len(threads) == 3 and len(set(threads)) == 1
    assert threads[0] != threading.get_ident()


def test_info_total_budget_skips_more_drive_commands():
    raw = Fake()
    dev = info.InfoDevice(raw, budget_s=0)
    try:
        with pytest.raises(TimeoutError, match='READ CAPACITY skipped'):
            dev.execute(mmc.read_capacity())
        assert not raw.calls and dev.errors
    finally:
        dev.close()


def test_info_cli_failure_keeps_partial_report_and_bundle(tmp_path, monkeypatch):
    from discprobe import __main__ as cli
    monkeypatch.setattr(cli, '_open', lambda args: Fake())
    args = cli._build_parser()[0].parse_args(['info', '--sim', 'cav', '--out', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        cli.cmd_info(args)
    assert error.value.code == 1
    runs = list(tmp_path.iterdir())
    assert len(runs) == 1 and (runs[0] / 'info.json').is_file()
    assert (runs[0] / 'diagnostics.zip').is_file()
    assert 'TEST UNIT READY' in json.loads((runs[0] / 'failure.json').read_text())['reason']


def test_info_drive_choice_precedes_worker_and_uses_no_real_drive(tmp_path, monkeypatch):
    from discprobe import __main__ as cli
    calls = []
    def choose(args):
        calls.append(('choose', threading.get_ident()))
        args.drive = 'F:'
    def open_device(args):
        assert args.drive == 'F:'
        calls.append(('open', threading.get_ident()))
        return Fake()
    monkeypatch.setattr(cli, '_choose_drive', choose)
    monkeypatch.setattr(cli, '_open', open_device)
    args = cli._build_parser()[0].parse_args(['info', '--out', str(tmp_path)])
    with pytest.raises(SystemExit):
        cli.cmd_info(args)
    assert calls[0] == ('choose', threading.get_ident())
    assert calls[1][0] == 'open' and calls[1][1] != threading.get_ident()


def test_geo_failure_before_first_fit_still_saves_diagnostics(tmp_path, monkeypatch):
    from discprobe import __main__ as cli, geo
    monkeypatch.setattr(cli, '_identity', lambda *args: {})
    def stop(ladder):
        raise RuntimeError('the spindle speed never settled')
    monkeypatch.setattr(geo.Ladder, 'run', stop)
    args = cli._build_parser()[0].parse_args(['geo', '--sim', 'cav', '--out', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        cli.cmd_geo(args)
    assert error.value.code == 1
    run = next(tmp_path.iterdir())
    summary = json.loads((run / 'summary.json').read_text())
    assert summary['stopped'] == 'the spindle speed never settled'
    assert (run / 'diagnostics.zip').is_file()


def test_geo_ctrl_c_before_first_fit_keeps_original_interrupt(tmp_path, monkeypatch):
    from discprobe import __main__ as cli, geo
    monkeypatch.setattr(cli, '_identity', lambda *args: {})
    def interrupt(ladder):
        raise KeyboardInterrupt()
    monkeypatch.setattr(geo.Ladder, 'run', interrupt)
    args = cli._build_parser()[0].parse_args(['geo', '--sim', 'cav', '--out', str(tmp_path)])
    with pytest.raises(KeyboardInterrupt):
        cli.cmd_geo(args)
    run = next(tmp_path.iterdir())
    assert json.loads((run / 'summary.json').read_text())['stopped'] == 'interrupted'
    assert (run / 'diagnostics.zip').is_file()


def test_preflight_timeout_saves_a_run(tmp_path, monkeypatch):
    from discprobe import __main__ as cli
    args = cli._build_parser()[0].parse_args(['timing', '--sim', 'cav', '--out', str(tmp_path)])
    def timeout(*args):
        raise TimeoutError('GET CONFIGURATION timed out; retry the same disc')
    monkeypatch.setattr(cli, '_check_disc', timeout)
    with pytest.raises(SystemExit, match='GET CONFIGURATION'):
        cli._measurement_setup(Fake(), args, 'timing')
    run = next(tmp_path.iterdir())
    assert (run / 'diagnostics.zip').is_file()


@pytest.mark.parametrize('platform', ['win32', 'linux'])
def test_native_clv_entry_uses_platform_adapter_and_saves_stop(tmp_path, monkeypatch, platform):
    from discprobe import __main__ as cli, clv
    calls = []
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.setitem(sys.modules, 'discprobe.device', SimpleNamespace(
        raise_priority=lambda: calls.append('priority'), list_optical_drives=lambda: []))
    monkeypatch.setattr(cli, '_open', lambda args: (calls.append('open') or Fake()))
    monkeypatch.setattr(cli, '_check_disc', lambda *args: None)
    monkeypatch.setattr(cli, '_blu_ray_speed', lambda *args: None)
    monkeypatch.setattr(cli, '_identity', lambda *args: None)
    monkeypatch.setattr(cli, '_measuring', lambda dev, args: dev)
    class StoppedClv:
        def __init__(self, *args, **kwargs):
            self.tp = SimpleNamespace(summary={})
            self.summary = {}
        def run(self):
            raise RuntimeError('CLV CD has no sector-angle map; reuse this disc')
    monkeypatch.setattr(clv, 'ClvLadder', StoppedClv)
    args = cli._build_parser()[0].parse_args(['geo', '--media', 'cd', '--cd-clv',
        '--linear-mm-s', '19200', '--drive', 'FAKE', '--out', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        cli._geo_clv(args)
    assert error.value.code == 1 and calls == ['priority', 'open']
    run = next(tmp_path.iterdir())
    assert (run / 'diagnostics.zip').exists()
    assert 'CLV CD' in json.loads((run / 'summary.json').read_text())['stopped']


def test_spindle_failure_history_never_loops_failed_speeds(tmp_path):
    from discprobe import guide
    speeds = guide.ALTERNATIVE_SPEEDS['dvd']
    for index, speed in enumerate(speeds):
        run = tmp_path / f'timing-SIM-20261112-1200{index:02d}'
        run.mkdir()
        (run / 'summary.json').write_text(json.dumps(dict(stopped='the spindle speed never settled',
            simulated=True, args=dict(sim='cav', media='dvd', speed=int(speed)))))
    args = argparse.Namespace(out=str(tmp_path), sim='cav', drive=None, media='dvd', speed=int(speeds[-1]))
    advice = guide.speed_advice(args)
    assert advice['exhausted'] and advice['next_speed'] is None
    assert not advice['all_clv']


@pytest.mark.parametrize('intervals,status', [([[34, 44]], 'target_reached'),
    ([[25, 34], [38, 54]], 'target_reached'), ([[25, 54]], 'candidates_exhausted')])
def test_saved_incomplete_range_refuses_export_without_writing(tmp_path, intervals, status):
    from discprobe import __main__ as cli
    source = Path(__file__).resolve().parents[1] / 'evidence/geo/gh70n-20261107/geo-H-20261107-183256/summary.json'
    summary = json.loads(source.read_text(encoding='utf-8'))
    summary['fit'].update(measured_span_mm=[intervals[0][0], intervals[-1][1]],
                          coverage={'measured_intervals_mm': intervals}, completion_status=status)
    (tmp_path / 'summary.json').write_text(json.dumps(summary))
    output = tmp_path / 'preset.json'
    with pytest.raises(SystemExit, match='EXTRAPOLATION'):
        cli._main(['disexport', '--geo', str(tmp_path / 'summary.json'), '--sectors', '2295104',
                   '--r-min', '25', '--r-max', '58', '--output', str(output)])
    assert not output.exists()
    assert (tmp_path / 'diagnostics.zip').exists()


@pytest.mark.parametrize('cdb,alloc', [(mmc.inquiry(), 96), (mmc.read_capacity(), 8),
    (mmc.read_track_information(1), 48), (mmc.get_configuration(), 4096),
    (mmc.mode_sense10(0x2A), 256), (mmc.read12(100, 1, True), 2048),
    (mmc.read12(100, 0, True), 0), (mmc.read_cd(100, 1), 2352)])
def test_probe_timeout_preserves_cdb_payload_and_names_step(cdb, alloc):
    dev = Fake()
    with pytest.raises(OSError, match='same disc'):
        execute_probe(dev, cdb, alloc)
    assert dev.calls == [(cdb, alloc, 1 if alloc else 2, 5)]


def test_cache_probe_timeout_is_a_saved_failure(tmp_path, monkeypatch):
    probe = timing.TimingProbe(Fake(), log=lambda *a: None)
    with pytest.raises(timing.NoReadableDisc, match='INQUIRY') as error:
        probe._cmd(mmc.inquiry(), 96)
    diagnostics.save_failure(tmp_path, str(error.value))
    assert (tmp_path / 'diagnostics.zip').exists()


def test_optional_probe_identity_keeps_and_prints_step_error(capsys):
    from discprobe import __main__ as cli
    identity = cli._identity(argparse.Namespace(sim=None, media='dvd'), Fake())
    assert any('INQUIRY' in message for message in identity['probe_errors'])
    assert 'same disc' in capsys.readouterr().err


@pytest.mark.parametrize('strategy', ['plain', 'evict'])
def test_cached_host_tick_stops_separately_from_clv(strategy, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'win32')
    probe = timing.TimingProbe(Fake(), log=lambda *a: None)
    probe.strategy = strategy
    with pytest.raises(timing.NoReadableDisc, match='not proof of CLV') as error:
        probe.reject_fake_period(15.625)
    diagnostics.save_failure(tmp_path, str(error.value))
    failure = json.loads((tmp_path / 'failure.json').read_text())
    assert 'Reuse this disc' in failure['next_step'] and 'FUA' in failure['next_step']


def test_nonintegral_fua_period_stops(tmp_path):
    probe = timing.TimingProbe(Fake(), log=lambda *a: None)
    probe.strategy = 'fua'
    probe.summary = {'settle': {'read': {'p50_us': 15000}}, 'period': {'rotation': {'mode': 'CAV'}}}
    with pytest.raises(timing.NoReadableDisc, match='false period'):
        probe._check_period([{'period_ms': 10}])


@pytest.mark.parametrize('reason', ['rotation is CLV, not CAV', 'cache/false period',
    'narrow measured span', 'EXTRAPOLATION outside measured span', 'candidates_exhausted',
    'Experimental CD CLV sector angles unavailable'])
def test_each_failure_saves_summary_logs_settings_versions_and_cheap_step(tmp_path, reason):
    args = argparse.Namespace(speed=5540, out=str(tmp_path), func=None)
    (tmp_path / 'events.csv').write_text('command,status\nread12,2\n')
    target = diagnostics.save_failure(tmp_path, reason, args)
    with zipfile.ZipFile(target) as archive:
        assert {'summary.json', 'events.csv', 'settings.json', 'versions.json', 'failure.json', 'logs.txt'} <= set(archive.namelist())
        assert json.loads(archive.read('settings.json'))['speed'] == 5540
        failure = json.loads(archive.read('failure.json'))
        assert failure['reason'] == reason and 'disc' in failure['next_step']


def test_bundle_never_collects_photos_outside_files_or_personal_paths(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    source = {'args': {'out': str(run), 'input': 'C:\\Users\\Private Person\\photos\\x.png',
                       'picture': 'Pictures/Alice/private.png',
                       'images': ['Pictures/Another Person/photo.png'],
                       'sibling': str(run) + '-private/path.txt',
                       'other': '/home/Private Person/data.txt', 'parent': '../private-persons/file.txt',
                       'unc': '\\\\server\\private\\file.txt'}, 'stopped': 'read failure'}
    (run / 'summary.json').write_text(json.dumps(source))
    (run / 'photo.json').write_text('private photo metadata')
    (run / 'photo.png').write_bytes(b'photo')
    (run / 'run.log').write_text('read C:\\Users\\Private Person\\data.txt\n/home/private/data.txt')
    (tmp_path / 'secret.log').write_text('outside')
    target, names = diagnostics.bundle(run)
    with zipfile.ZipFile(target) as archive:
        content = '\n'.join(archive.read(n).decode() for n in names)
    assert 'Private Person' not in content and '/home/private' not in content and 'server' not in content
    assert 'private-persons' not in content
    assert 'Alice' not in content
    assert 'Another Person' not in content
    assert '-private' not in content
    assert 'photo.json' not in names and 'photo.png' not in names and 'secret.log' not in names
    assert json.loads((run / 'summary.json').read_text()) == source


def test_diagnose_command_lists_contents(tmp_path, capsys):
    from discprobe.__main__ import _main
    (tmp_path / 'summary.json').write_text('{"args":{"speed":3324}}')
    _main(['diagnose', str(tmp_path)])
    text = capsys.readouterr().out
    assert 'Contains:' in text and 'versions.json' in text and 'settings.json' in text


def test_windows_cd_refuses_before_tool_or_process_access(monkeypatch):
    from discprobe import burner
    tool = Mock(side_effect=AssertionError('must refuse before tool lookup'))
    monkeypatch.setattr(burner, 'tool', tool)
    with pytest.raises(burner.BurnError) as error:
        burner.WindowsDVD('E:', 'cd')
    text = str(error.value)
    assert 'DAO' in text and '--cd-sector mode2form1' in text and '写入前拒绝' in text
    tool.assert_not_called()


def test_burn_cli_refusal_saves_bundle_without_writing(tmp_path, monkeypatch):
    from discprobe import burner, __main__ as cli
    image = tmp_path / 'never-written.iso'
    args = cli._build_parser()[0].parse_args(['burn', '--drive', 'E:', '--iso', str(image), '--media', 'cd', '--yes-write'])
    def refuse(*args, **kwargs):
        raise burner.BurnError('CD DAO mode refused before writing')
    monkeypatch.setattr(burner, 'burn', refuse)
    with pytest.raises(SystemExit, match='CD DAO'):
        burner.run(args)
    assert not image.exists()
    assert Path(str(image) + '.diagnostics/diagnostics.zip').is_file()


def test_three_capacity_meanings_from_saved_blank():
    from discprobe.capacity import capacity_words
    path = Path(__file__).resolve().parents[1] / 'evidence/drive/info_blank_ritekf1.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    words = capacity_words(report)
    assert words['blank_writable_sectors'] == 2297888
    assert words['geometric_total_sectors'] == 2298496
    assert words['random_mirror_sectors'] is None
    text = '\n'.join(info.summarize(report))
    assert '2297888' in text and '2295104' in text and 'Geometric total' in text


def test_spti_timeout_header_and_error_without_opening_device(monkeypatch):
    if sys.platform != 'win32':
        pytest.skip('SPTI ABI is Windows-only')
    from discprobe import spti
    dev = object.__new__(spti.SptiDevice)
    dev._req = spti.SPTD_WITH_SENSE()
    dev._returned = ctypes.wintypes.DWORD()
    dev._handle, dev._buf = 123, None
    cdb = mmc.read_capacity()
    def ioctl(*args):
        assert dev._req.sptd.TimeOutValue == 5
        assert bytes(dev._req.sptd.Cdb)[:len(cdb)] == cdb
        ctypes.set_last_error(121)
        return False
    monkeypatch.setattr(spti, '_DeviceIoControl', ioctl)
    with pytest.raises(OSError, match='READ CAPACITY.*limit 5s'):
        dev.execute(cdb, timeout_s=5)


def test_sg_timeout_header_and_error_without_opening_device(monkeypatch):
    # Load the Linux module against a fake libc on Windows; no open/ioctl reaches an OS.
    libc = SimpleNamespace(ioctl=Mock())
    monkeypatch.setattr(ctypes, 'CDLL', lambda *a, **kw: libc)
    path = Path(__file__).resolve().parents[1] / 'discprobe/sg.py'
    spec = importlib.util.spec_from_file_location('discprobe._test_sg', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dev = object.__new__(module.SgDevice)
    dev._fd, dev.path = 123, '/dev/fake'
    dev._buf = ctypes.create_string_buffer(module.BUFFER_BYTES)
    dev._sense = ctypes.create_string_buffer(module.SENSE_BYTES)
    dev._cdb = ctypes.create_string_buffer(16)
    dev._hdr = module._SGIOHeader()
    cdb = mmc.inquiry()
    def ioctl(*args):
        assert dev._hdr.timeout == 5000
        assert dev._cdb.raw[:len(cdb)] == cdb
        dev._hdr.host_status = 3
        return 0
    libc.ioctl.side_effect = ioctl
    with pytest.raises(OSError, match='INQUIRY.*limit 5s'):
        dev.execute(cdb, timeout_s=5)
