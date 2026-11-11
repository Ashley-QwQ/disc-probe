"""Offline MMC responses and mocked calibration children; no device is opened."""
import argparse
import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from discprobe import calibrate, info, mmc, webui_catalog
from discprobe.capacity import catalogue_capacity, recordable_capacity
from discprobe.scsi import DATA_IN, ScsiResult, Sense, check_allowed


def report(**entries):
    return {key: {'parsed': value} for key, value in entries.items()}


def dvd_response(sectors=2298496):
    d = bytearray(68)
    d[:2] = (66).to_bytes(2, 'big')
    d[4] = 1
    d[7:10] = (~((0x30000 + sectors - 1) >> 4) & 0xFFFFFF).to_bytes(3, 'big')  # complemented ECC block number
    d[20], d[28] = 3, 4
    d[21:27], d[29:35] = b'TEST  ', b'MID   '
    return bytes(d)


class Responses:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def execute(self, cdb, alloc, direction):
        check_allowed(cdb)
        assert direction == DATA_IN or alloc == 0
        self.calls.append(cdb)
        data = self.responses.get(cdb)
        return ScsiResult(0 if data is not None else 2, (data or b'')[:alloc],
                          None if data is not None else Sense(5, 0x24, 0), 0, 100)


def test_quick_and_full_read_prerecorded_capacity_separately_from_burn():
    responses = {
        mmc.test_unit_ready(): b'', mmc.inquiry(): bytes(96),
        mmc.get_configuration(): bytes([0, 0, 0, 4, 0, 0, 0, 0x11]),
        mmc.read_capacity(): (999999).to_bytes(4, 'big') + (2048).to_bytes(4, 'big'),
        mmc.read_disc_structure(0, 0x0E): dvd_response(),
    }
    for collect in (info.quick, info.collect):
        dev = Responses(responses)
        r = collect(dev)
        disc = webui_catalog.disc_report(r)
        assert disc['sectors'] == 1000000  # existing readable-length field
        assert disc['capacity_sectors'] == 2298496
        assert 'prerecorded' in disc['capacity_source']
        assert 'Recordable capacity: 2298496' in '\n'.join(info.summarize(r))
        assert mmc.read_disc_structure(0, 0x0E) in dev.calls


def test_finalized_dvd_r_on_gh70n():
    """Recorded from a GH70N (rev NYA2) with a finalized RITEKF1 DVD-R: profile DVD-ROM, 0Eh still answers."""
    raw = bytes.fromhex("006a00000140c1fd9ed8520002870d138788900003524954454b46000431000000000000"
                        "058880000000020006090f158788900007a8820020000000")
    pre = mmc.parse_dvd_r_prerecorded(raw)
    assert pre['last_recordable_address'] == 0xFD9ED8
    r = report(configuration={'current_profile': 0x10}, dvd_prerecorded_0e=pre,
               capacity={'last_lba': 2295103}, track_1={'blank': False, 'free_blocks': 0, 'track_size': 2295104})
    assert recordable_capacity(r) == (2298496, 'DVD-R prerecorded last recordable address (format 0Eh)')
    # A pressed DVD-ROM has no 0Eh MID, so nothing is inferred.
    assert recordable_capacity(report(configuration={'current_profile': 0x10},
                                      dvd_prerecorded_0e={'last_recordable_address': 0xFD9ED8})) is None


def test_cd_atip_and_disc_information_are_exclusive_leadout_addresses():
    d = bytearray(16)
    d[:2] = (14).to_bytes(2, 'big')
    d[12:15] = bytes([79, 59, 74])
    r = report(configuration={'current_profile': 9}, atip=mmc.parse_atip(d))
    assert recordable_capacity(r)[0] == 359849
    d[13] = 99
    assert recordable_capacity(report(configuration={'current_profile': 9}, atip=mmc.parse_atip(d))) is None
    di = bytearray(34)
    di[:2] = (32).to_bytes(2, 'big')
    di[2] = 2  # finalized, short readable length must not matter
    di[21:24] = bytes([79, 59, 74])
    r = report(configuration={'current_profile': 9}, disc_information=mmc.parse_disc_information(di),
               capacity={'last_lba': 1000})
    assert recordable_capacity(r)[0] == 359849


@pytest.mark.parametrize('end', [None, 0, 0x2FFFF, 0xFFFFFF])
def test_unknown_or_sentinel_addresses_never_use_readable_length(end):
    r = report(configuration={'current_profile': 0x11},
               dvd_prerecorded_0e={'last_recordable_address': end},
               capacity={'last_lba': 999999},
               track_1={'blank': False, 'free_blocks': 100, 'track_size': 1000000})
    assert recordable_capacity(r) is None
    assert webui_catalog.disc_report(r)['capacity_sectors'] is None


def test_short_unsupported_failed_and_other_profiles_stay_unknown():
    for n in range(35):
        assert 'last_recordable_address' not in mmc.parse_dvd_r_prerecorded(dvd_response()[:n])
    r = report(configuration={'current_profile': 0x2B},
               dvd_prerecorded_0e={'last_recordable_address': 0x260000})
    assert recordable_capacity(r) is None  # no single-layer calculation on dual layer
    r['configuration']['parsed']['current_profile'] = 0x11
    r['dvd_prerecorded_0e']['status'] = 2
    assert recordable_capacity(r) is None


def test_simulated_short_disc_has_no_implicit_blank_capacity():
    from discprobe.sim import SimDrive
    disc = webui_catalog.disc_report(info.quick(SimDrive(capacity=1000000)))
    assert disc['sectors'] == 1000000
    assert disc['capacity_sectors'] is None  # simulator has no prerecorded area


def test_catalogue_is_exact_mid_and_explicit_capacity_only(tmp_path):
    (tmp_path / 'presets').mkdir()
    path = tmp_path / 'presets/catalogue.json'
    path.write_text(json.dumps({'MID': {'sectors': 2298496, 'media': 'dvd'}}))
    assert catalogue_capacity('MID', 'dvd', tmp_path)[0] == 2298496
    assert catalogue_capacity('OTHER', 'dvd', tmp_path) is None
    assert catalogue_capacity('MID', 'cd', tmp_path) is None
    for entry in ({'last_lba': 999}, {'sectors': True}, {'sectors': -1},
                  {'sectors': 100, 'totalSectors': 101}, {'preset': 'elsewhere.json'}):
        path.write_text(json.dumps({'MID': entry}))
        assert catalogue_capacity('MID', 'dvd', tmp_path) is None
    path.write_text('{')
    assert catalogue_capacity('MID', 'dvd', tmp_path) is None


def run_calibration(monkeypatch, tmp_path, *, capacity=None, explicit=None, catalogue=None, burn=False):
    monkeypatch.chdir(tmp_path)
    disc = dict(present=True, blank=False, media='dvd', kind='DVD-R', mid='MID', sectors=1000000,
                capacity_sectors=capacity, capacity_source='test metadata')
    if catalogue:
        (tmp_path / 'presets').mkdir()
        (tmp_path / 'presets/catalogue.json').write_text(json.dumps({'MID': {'sectors': catalogue}}))
    parser = argparse.ArgumentParser()
    calibrate.add_parser(parser.add_subparsers())
    args = parser.parse_args(['calibrate', '--drive', 'SIM', '--preset', str(tmp_path / 'p.json'),
                              *(['--sectors', str(explicit)] if explicit is not None else []),
                              *(['--iso', 'measurement.iso', '--yes-write'] if burn else [])])
    calls, events = [], []
    reads = [dict(disc, blank=True, sectors=2298496, capacity_sectors=2298496), disc] if burn else [disc]

    def read(*a, **kw):
        return SimpleNamespace(stdout=json.dumps({'disc': reads.pop(0)}))

    def child(argv, **kw):
        command = argv[argv.index('discprobe') + 1:]
        calls.append(command)
        if command[0] == 'disexport':
            Path(args.preset).write_text('{}')
        return SimpleNamespace(poll=lambda: 0, returncode=0)

    monkeypatch.setattr(calibrate.subprocess, 'run', read)
    monkeypatch.setattr(calibrate.subprocess, 'Popen', child)
    monkeypatch.setattr(calibrate.guide, 'scan', lambda _: [SimpleNamespace(
        kind=k, when=datetime.datetime.now(), simulated=False, path=k + '-result') for k in ('timing', 'geo')])
    monkeypatch.setattr(calibrate.guide, 'result_verdict', lambda *a: 'good')
    monkeypatch.setattr(calibrate.ui, 'say', lambda *a, **kw: None)
    monkeypatch.setattr(calibrate.ui, 'event', lambda event_type, **kw: events.append(dict(type=event_type, **kw)))
    return args, calls, events


@pytest.mark.parametrize('capacity,explicit,catalogue,burn,expected', [
    (2298496, None, None, False, 2298496),
    (2298496, 2295104, 2000000, False, 2295104),
    (2298496, None, 2000000, False, 2298496),
    (None, None, 2295104, False, 2295104),
    (None, None, None, True, 2298496),
])
def test_calibrate_exports_whole_capacity(monkeypatch, tmp_path, capacity, explicit, catalogue, burn, expected):
    args, calls, events = run_calibration(monkeypatch, tmp_path, capacity=capacity, explicit=explicit,
                                          catalogue=catalogue, burn=burn)
    calibrate.run(args)
    export = next(c for c in calls if c[0] == 'disexport')
    assert export[export.index('--sectors') + 1] == str(expected)
    done = next(e for e in events if e['type'] == 'calibrated')
    assert done['ok'] and done['sectors'] == expected and done['capacity_source']


@pytest.mark.parametrize('explicit', [None, 0, -1])
def test_unknown_capacity_fails_without_export_or_measurement(monkeypatch, tmp_path, explicit):
    args, calls, events = run_calibration(monkeypatch, tmp_path, explicit=explicit)
    with pytest.raises(SystemExit, match='--sectors'):
        calibrate.run(args)
    assert calls == [] and not Path(args.preset).exists()
    assert any(e['type'] == 'calibrated' and e['ok'] is False for e in events)


def test_measurements_without_preset_do_not_require_blank_capacity(monkeypatch, tmp_path):
    args, calls, events = run_calibration(monkeypatch, tmp_path)
    args.preset = None
    calibrate.run(args)
    assert [c[0] for c in calls] == ['timing', 'geo']
    assert any(e['type'] == 'calibrated' and e['ok'] is True for e in events)
