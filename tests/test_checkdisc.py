"""Offline photo-target construction, CLI gates and web command validation."""
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest

from discprobe import checkdisc, imagedisc, webui
from discprobe.__main__ import main
from discprobe.geo import CD_AUDIO_RANGE, Ladder
from discprobe.sim import SimDrive


@pytest.fixture(scope='module')
def target():
    return checkdisc.build_design()


def test_packaged_target_hash(target):
    # The recorded hash is of the complete .npy file, including its header.
    saved = io.BytesIO()
    np.save(saved, target)
    assert target.dtype == np.uint8 and target.shape == (6000, 6000)
    assert hashlib.sha256(saved.getvalue()).hexdigest() == checkdisc.TARGET_SHA256 == (
        '052d1835137d0b9173251d14ea44212b85acef2e8eb7c3970957114991565be7')


def test_research_target_and_texture_order(target):
    source = Path(__file__).resolve().parents[1]/'docs/goals/calib-simple'
    if not (source/'target_round2.npy').exists():
        pytest.skip('calib-simple reference is absent; packaged target hash is checked separately')
    assert np.array_equal(target, np.load(source/'target_round2.npy'))
    assert list(checkdisc.TEXTURES) == json.loads((source/'layout_round2.json').read_text())['textures']


def geo(tmp_path, media='dvd', intervals=None, last=127):
    fit = dict(media=media, u=27/133.3e-6, v=.74/.1333, bit_nm_assumed=133.3,
               coverage=dict(measured_intervals_mm=intervals if intervals is not None else [[26, 57.1]]))
    path = tmp_path/'summary.json'
    path.write_text(json.dumps(dict(fit=fit, setup=dict(last_lba=last))))
    return path, fit


@pytest.mark.parametrize('media', ['cd', 'bd'])
def test_refuse_other_media(tmp_path, media):
    path, _ = geo(tmp_path, media)
    with pytest.raises(SystemExit, match='DVD only'):
        main(['checkdisc', '--geo', str(path)])
    assert not list(tmp_path.glob('*.iso'))


@pytest.mark.parametrize('intervals', [[[26.2, 54]], [[27, 58]], [[26, 40], [41, 58]], []])
def test_refuse_unmeasured_reader_features(tmp_path, intervals):
    path, _ = geo(tmp_path, intervals=intervals)
    with pytest.raises(SystemExit, match='re-measure this batch with the new geo; no new burn'):
        main(['checkdisc', '--geo', str(path)])
    assert not list(tmp_path.glob('*.iso'))


def test_unknown_capacity_requires_sectors(tmp_path):
    path, _ = geo(tmp_path, last=None)
    with pytest.raises(SystemExit, match='no known sector count'):
        main(['checkdisc', '--geo', str(path)])


@pytest.mark.parametrize('explicit', [False, True])
def test_small_iso_cli(tmp_path, monkeypatch, target, explicit, capsys):
    from discprobe import guide
    monkeypatch.setattr(guide, 'optical_drives', lambda: [])
    monkeypatch.setenv('DISCPROBE_WORKERS', '1')
    monkeypatch.setattr(checkdisc, 'build_design', lambda: target)
    # Any photo-L access would fail this test. The original u must reach the ISO.
    from discprobe import photo
    monkeypatch.setattr(photo, 'image_photo_l', lambda *a, **k: pytest.fail('checkdisc must not use photo L'))
    path, fit = geo(tmp_path, last=None if explicit else 127)
    output = tmp_path/'check.iso'
    argv = ['checkdisc', '--geo', str(path if explicit else tmp_path), '--output', str(output)]
    if explicit:
        argv += ['--sectors', '128']
    main(argv)
    spec = json.loads(output.with_suffix('.image.json').read_text())
    assert output.stat().st_size == 128*2048
    assert spec['check_disc'] is True and spec['experimental'] is True
    assert spec['geometry_from'] == str(path.resolve()) and spec['u'] == fit['u']
    assert spec['design'] == 'pcal round2' and spec['lead_lba'] == 0
    assert spec['textures'] == list(checkdisc.TEXTURES)
    assert imagedisc.verify_iso(str(output), target, fit['u'], fit['v'], fit['bit_nm_assumed'],
                               128, textures=checkdisc.TEXTURES, samples=300) == []
    assert 'After burning, photograph it' in capsys.readouterr().out


def test_verification_failure_does_not_link_work(tmp_path, monkeypatch, target):
    from discprobe import works_link
    path, _ = geo(tmp_path)
    monkeypatch.setattr(checkdisc, 'build_design', lambda: target)
    monkeypatch.setattr(imagedisc, 'write_iso', lambda *a, **k: 'fake.image.json')
    monkeypatch.setattr(imagedisc, 'verify_iso', lambda *a, **k: ['LBA 50 differs'])
    monkeypatch.setattr(works_link, 'image_completed', lambda *a: pytest.fail('failed ISO linked'))
    with pytest.raises(SystemExit, match='verification failed'):
        main(['checkdisc', '--geo', str(path), '--output', str(tmp_path/'bad.iso')])


def test_webui_whitelist(tmp_path):
    assert 'checkdisc' in webui.ACTIONS and 'checkdisc' not in webui.DRIVE_ACTIONS
    assert webui.OPTIONS['checkdisc'] == dict(geo='geo', output='path', sectors='sectors',
                                             work='work', disc_code='disc_code')
    argv, drive = webui.command(dict(action='checkdisc', args=dict(
        geo='geo-run', output='check.iso', sectors=128, work='w-20261113-123456-abcd', disc_code='PCAL-C 4-02')),
        tmp_path.resolve(), [])
    assert drive is None and '--drive' not in argv and '--media' not in argv
    assert argv[argv.index('--disc-code')+1] == 'PCAL-C 4-02'
    for payload in (dict(action='checkdisc', media='cd'), dict(action='checkdisc', media='bd'),
                    dict(action='checkdisc', args={}),
                    dict(action='checkdisc', args=dict(geo='g', no_photo_l=True))):
        with pytest.raises(webui.APIError):
            webui.command(payload, tmp_path.resolve(), [])


@pytest.mark.parametrize('media,audio,fractions', [
    ('dvd', False, (.01, .98)), ('cd', False, (.01, .98)),
    ('cd', True, CD_AUDIO_RANGE), ('bd', False, (.03, .85)),
])
def test_default_geo_ranges(media, audio, fractions):
    dev = SimDrive(media=media, cd_audio=audio)
    ladder = Ladder(dev, media=media, log=lambda *_: None)
    # Inspect actual setup and range selection, before costly fitting.
    class Selected(Exception):
        pass
    def selected():
        raise Selected
    ladder.check_rotation = selected
    with pytest.raises(Selected):
        ladder.run()
    last, block = ladder.tp.last_lba, ladder.block
    assert ladder.ranges == [(int(last*fractions[0])//block*block,
                              int(last*fractions[1])//block*block)]
