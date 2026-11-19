"""Offline MMC replies for issue #49, including the GH40N terminal sample."""

import json

import pytest

from discprobe import __main__ as cli, i18n, info, mmc
from discprobe.scsi import DATA_IN, ScsiResult, Sense, check_allowed


L0_SECTORS = 2086912
L0 = 'L0: 2086912 sectors (PSN 0x030000..0x22D7FF)'
MID = 'DVD+R MID: RITEK/S04/66 (from physical format info 0x00; ADIP 0x11 refused)'


def structure(payload):
    return (len(payload) + 2).to_bytes(2, 'big') + b'\0\0' + payload


def plus_dl_payload(end=0x22D7FF, *, manufacturer=b'RITEK\0\0\0', media_type=b'S04', revision=0x66,
                    category=0xE1, geometry=0x32):
    # ECMA-364 §14.4.2.1 and §18.8.1 Table 13, with Layer 0 and Layer 1 blocks.
    l0 = bytearray(256)
    l0[:4] = bytes([category, 0x0F, geometry, 0x10])
    l0[5:8], l0[9:12], l0[13:16] = bytes.fromhex('030000'), bytes.fromhex('fcffff'), end.to_bytes(3, 'big')
    l0[19:27], l0[27:30], l0[30], l0[31] = manufacturer, media_type, revision, 0x40
    return bytes(l0 + l0)


def boundary(sectors=L0_SECTORS, *, initialized=False):
    # MMC-6 Table 426, length 0x000A plus its two-byte field.
    return structure(bytes([0x80 if initialized else 0, 0, 0, 0]) + sectors.to_bytes(4, 'big'))


def performance(descriptors):
    rows = b''.join(value.to_bytes(4, 'big') for values in descriptors for value in values)
    return (len(rows) + 4).to_bytes(4, 'big') + bytes(4) + rows


class Gh40n:
    name = 'GH40N-fixture'

    def __init__(self, *, physical=None, adip=Sense(5, 0x24, 0), layer_capacity=None, profile=0x2B):
        if physical is None:
            physical = structure(plus_dl_payload().ljust(2048, b'\0'))
        self.calls = []
        page = bytearray(48)
        page[:2], page[12:14], page[30:32] = b'\x2a\x2e', b'\x08\x00', b'\x00\x04'
        for index, speed in enumerate((11080, 8310, 5540, 3324)):
            pos = 34 + index * 4
            page[pos:pos + 2] = speed.to_bytes(2, 'big')
        track = bytearray(48)
        track[:4], track[6:8] = b'\0\x2e\x01\x01', b'\x40\x01'
        track[16:20] = (4173824).to_bytes(4, 'big')
        self.responses = {
            mmc.test_unit_ready(): b'',
            mmc.inquiry(): bytes(8) + b'HL-DT-STDVD-RAM GH40N   NX05',
            mmc.get_configuration(): bytes([0, 0, 0, 4, 0, 0, 0, profile]),
            mmc.read_disc_information(): b'\x00\x20\x00\x01\x01\x01\x01' + bytes(27),
            mmc.read_track_information(1): bytes(track),
            mmc.read_capacity(): bytes.fromhex('0000000000000800'),
            mmc.read_toc(4, msf=True): Sense(5, 0x30, 2),
            mmc.read_disc_structure(0, 0x00): physical,
            mmc.read_disc_structure(0, 0x11): adip,
            mmc.read_disc_structure(0, 0x20, alloc=12): layer_capacity if layer_capacity is not None else boundary(),
            mmc.read_disc_structure(1, 0x00): b'',
            mmc.get_performance(0x10, 0x00): performance(((0, 4584, 2086911, 11086), (2086912, 11086, 4173823, 4584))),
            mmc.get_performance(0x14, 0x00): performance(((0, 8310, 299007, 8310), (299008, 11079, 3874815, 11079),
                                                        (3874816, 8310, 4173823, 8310))),
            mmc.get_performance(0, 0x03): performance([(0, 4173823, 4584, speed) for speed in (11080, 8310, 5540, 3324)]),
            mmc.mode_sense10(0x2A): bytes(8) + page,
        }

    def execute(self, cdb, alloc, direction, *, timeout_s):
        check_allowed(cdb)
        assert direction == DATA_IN or alloc == 0
        assert timeout_s <= info.COMMAND_TIMEOUT_S
        self.calls.append(cdb)
        response = self.responses.get(cdb, Sense(5, 0x24, 0))
        if isinstance(response, Sense):
            return ScsiResult(2, b'', response, 0, 100)
        return ScsiResult(0, response[:alloc], None, 0, 100)


def test_gh40n_cli_writes_mid_and_l0_with_sources(monkeypatch, tmp_path, capsys):
    dev = Gh40n()
    monkeypatch.setattr(cli, '_open', lambda args: dev)
    args = cli._build_parser()[0].parse_args(['info', '--sim', 'cav', '--out', str(tmp_path)])
    cli.cmd_info(args)
    lines = capsys.readouterr().out.splitlines()
    assert MID in lines
    assert L0 in lines
    dump, = tmp_path.glob('*/info.json')
    report = json.loads(dump.read_text(encoding='utf-8'))
    assert report['dvd_plus_mid'] == {'manufacturer_id': 'RITEK', 'media_type_id': 'S04',
                                      'product_revision': 0x26, 'product_revision_byte': 0x66, 'source': '0x00'}
    assert report['dvd_layer0'] == {'start_psn': 0x30000, 'end_psn': 0x22D7FF,
                                    'sectors': L0_SECTORS, 'source': '0x00'}
    assert report['dvd_plus_adip_11']['sense'] == '5/24/00'
    assert mmc.read_disc_structure(0, 0x20, alloc=12) not in dev.calls


def test_valid_adip_takes_priority_over_physical_format():
    adip = structure(plus_dl_payload(manufacturer=b'OTHER\0\0\0', media_type=b'A01', revision=0)[:256])
    report = info.collect(Gh40n(adip=adip))
    assert report['dvd_plus_mid']['source'] == '0x11'
    assert 'DVD+R MID: OTHER/A01/00' in info.summarize(report)


def test_incomplete_successful_adip_uses_physical_format():
    adip = structure(plus_dl_payload()[:30])
    report = info.collect(Gh40n(adip=adip))
    assert report['dvd_plus_mid']['source'] == '0x00'
    assert MID.replace('ADIP 0x11 refused', 'ADIP 0x11 could not be parsed') in info.summarize(report)


@pytest.mark.parametrize('payload', [
    plus_dl_payload()[:30], plus_dl_payload(manufacturer=b'RI\xffEK\0\0\0'), plus_dl_payload(media_type=b'S\x1f4'),
    plus_dl_payload(manufacturer=b'R\0TEK\0\0\0'), plus_dl_payload(media_type=b'\0\0\0'),
    plus_dl_payload(category=0xA1), plus_dl_payload(geometry=0x02), plus_dl_payload(revision=0xC0),
])
def test_malformed_mid_is_not_rendered(payload):
    physical = structure(payload)
    report = info.collect(Gh40n(physical=physical, adip=physical))
    assert 'dvd_plus_mid' not in report
    assert not any(line.startswith('DVD+R MID:') for line in info.summarize(report))


def test_mid_respects_the_declared_transfer_length():
    payload = plus_dl_payload()
    for malformed in (structure(payload[:30]) + payload[30:], structure(payload)[:34]):
        report = info.collect(Gh40n(physical=malformed, adip=malformed))
        assert 'dvd_plus_mid' not in report


@pytest.mark.parametrize('physical', [b'', structure(plus_dl_payload(end=0))])
def test_l0_uses_layer_capacity_when_pfi_cannot_supply_an_end(physical):
    report = info.collect(Gh40n(physical=physical))
    assert report['dvd_layer_capacity_20']['parsed'] == {'sectors': L0_SECTORS, 'initialized': False}
    assert report['dvd_layer0'] == {'start_psn': 0x30000, 'end_psn': 0x22D7FF,
                                    'sectors': L0_SECTORS, 'source': '0x20'}
    assert L0 in info.summarize(report)


@pytest.mark.parametrize('invalid_capacity', [Sense(5, 0x24, 0), boundary()[:11], boundary(0),
                                             boundary(L0_SECTORS + 1), boundary(0xFFFFFFFF)])
def test_no_l0_when_no_valid_layer_structure(invalid_capacity):
    report = info.collect(Gh40n(physical=structure(plus_dl_payload(end=0)), layer_capacity=invalid_capacity))
    assert 'dvd_layer0' not in report
    assert MID in info.summarize(report)
    assert not any(line.startswith('L0:') for line in info.summarize(report))


def test_dvd_r_dl_boundary_uses_initialized_0x20():
    report = info.collect(Gh40n(physical=b'', profile=0x16, layer_capacity=boundary(initialized=True)))
    assert report['dvd_layer0']['source'] == '0x20'
    assert 'dvd_plus_mid' not in report


def test_book_type_dvd_rom_does_not_imply_an_adip_mid():
    report = info.collect(Gh40n(physical=structure(plus_dl_payload(category=0))))
    assert L0 in info.summarize(report)
    assert 'dvd_plus_mid' not in report


def test_zh_summary_translates_both_lines():
    assert i18n._zh(MID) != MID and i18n._zh(L0) != L0
    assert 'RITEK/S04/66' in i18n._zh(MID)
    assert '0x030000..0x22D7FF' in i18n._zh(L0)
