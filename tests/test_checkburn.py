"""CheckBurn against the Lab, including ordinary ISO data and interrupted writes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event

import numpy as np
import pytest

from disclab.__main__ import lab_env
from disclab.box import make_box
from disclab.drive import LabDrive, LabRecorder
from disclab.lab import Lab, atomic_json
from discprobe import burner, cd, checkburn, device, discfiles, discid, dvd, guide, iso9660, randomdisc
from discprobe.checkburn_content import filesystem, probe
from discprobe.image_output import mark_checked


@pytest.fixture
def lab(tmp_path):
    root = (tmp_path / 'lab').resolve()
    fixture = Lab(root)
    make_box(fixture, 'dvd+r', 1, seed=178)
    with fixture.locked_state() as state:
        state['drives']['X:']['tray'] = fixture.box()['discs'][0]
    try:
        yield fixture
    finally:
        assert root.parent == tmp_path.resolve() and root.name == 'lab'
        shutil.rmtree(root)


def cli(lab, *args, status=0):
    env = dict(lab_env(lab), DISCPROBE_HOME=str(lab.root))
    child = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'discprobe', *map(str, args)],
                           env=env, cwd=lab.root, capture_output=True, text=True, encoding='utf-8', timeout=100)
    assert child.returncode == status, child.stdout + child.stderr
    return child.stdout


def report(lab, *args):
    return json.loads(cli(lab, 'checkburn', '--drive', 'X:', '--json', *args))


def outcomes(result):
    return {item['id']: item['status'] for item in result['checklist']}


def picture_iso(path, length=4096, *, attest=False):
    # Short binary fixture with two physically repeated tones, stored the same
    # way as image. No visual or full-disc parity is inferred from it.
    masks = dvd.MASKS[[dvd.preset_index(i) for i in range(length)]]
    tones = np.where(np.arange(length) < length // 2, 0xA5, 0xB9).astype(np.uint8)
    path.write_bytes((masks ^ tones[:, None]).tobytes())
    iso9660.add(path, length, 'DISCPROBE_IMAGE')
    if attest:
        mark_checked(path, [])


def virtual_write(lab, image):
    LabRecorder(lab, 'X:', 'dvd').write(image, 8, Event(), lambda **event: None)


def test_blank_and_empty_tray(lab):
    result = report(lab)
    disc = result['disc']
    assert disc['state'] == 'blank' and disc['closed'] is False
    assert disc['recorded_sectors'] == disc['used_fraction'] == 0
    assert disc['blank_capacity_sectors'] == lab.disc_truth(lab.box()['discs'][0])['capacity']
    assert outcomes(result) == dict(write='possible', image_as_file='excluded', lighting='unknown',
                                    geometry='unknown', media='unknown', drive='unknown')
    with lab.locked_state() as state:
        state['drives']['X:']['tray'] = None
    assert report(lab)['disc']['state'] == 'unavailable'


def test_pattern_fresh_and_saved_readback(lab, monkeypatch):
    image = lab.root / 'picture.iso'
    picture_iso(image, attest=True)
    source_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    cli(lab, 'burn', '--drive', 'X:', '--iso', image, '--speed', 8, '--yes-write')
    log = Path(f'{image}.burn.jsonl')
    old = json.loads(log.read_text(encoding='utf-8').splitlines()[-1])
    fresh = report(lab, '--iso', image)
    assert fresh['source'] == 'drive' and fresh['verification'] == old['verification']
    assert fresh['verification']['ok'] == 96
    assert fresh['disc']['last_lba'] == 4095 and fresh['disc']['recorded_sectors'] == 4096
    assert fresh['disc']['closed'] is True
    assert 0 < fresh['disc']['used_fraction'] < .002
    assert fresh['content']['kind'] == 'pattern'
    assert outcomes(fresh)['write'] == outcomes(fresh)['image_as_file'] == 'excluded'
    assert {item['id'] for item in fresh['checklist']} == {'write', 'lighting', 'drive', 'image_as_file', 'media', 'geometry'}

    def no_verify(*args, **kwargs):
        pytest.fail('a saved verification was available')

    monkeypatch.setattr(burner, 'verify_image', no_verify)
    reused = checkburn.check('X:', iso=image, burn_log=log, out=lab.root / 'results',
                             device_factory=lambda drive: LabDrive(lab, drive))
    assert reused['source'] == 'supplied_burn_log' and reused['verification'] == old['verification']
    assert outcomes(reused) == outcomes(fresh)
    assert hashlib.sha256(image.read_bytes()).hexdigest() == source_hash
    for lang, expected in [('zh', '已排除'), ('en', 'Ruled out')]:
        result = cli(lab, '--lang', lang, 'checkburn', '--drive', 'X:', '--burn-log', log)
        assert expected in result and 'webui' in result


def test_half_written(lab):
    image = lab.root / 'picture.iso'
    picture_iso(image, attest=True)
    answers = lab.answers()
    answers['faults'] = [dict(id='stop-halfway', kind='burn_interrupt', params=dict(fraction=.5))]
    atomic_json(lab.answers_path, answers)
    cli(lab, 'burn', '--drive', 'X:', '--iso', image, '--speed', 8, '--yes-write', status=1)
    plain = report(lab)
    compared = report(lab, '--iso', image)
    assert compared['disc']['last_lba'] == 2047 and compared['disc']['closed'] is False
    assert compared['disc']['expected_end'] == 4096 and compared['disc']['short']
    assert compared['verification']['unreadable'] == 48
    assert outcomes(plain)['write'] == outcomes(compared)['write'] == 'possible'


@pytest.mark.parametrize('together', [False, True])
def test_iso_stored_as_file_vs_picture_with_files(lab, together):
    outer = lab.root / 'disc.iso'
    files = lab.root / 'files'
    files.mkdir()
    picture_iso(files / '图片.iso', length=128)
    if together:
        picture_iso(outer)
    else:
        with outer.open('wb') as stream:
            stream.truncate(4096 * 2048)
    layout = discfiles.plan(files, 'inner', 4096)
    discfiles.write_files(outer, layout)
    virtual_write(lab, outer)
    result = report(lab)
    assert result['content']['filesystem']['format'] == 'Joliet'
    assert result['content']['files'] == ['图片.iso']
    assert result['content']['kind'] == ('pattern' if together else 'files')
    assert outcomes(result)['image_as_file'] == ('excluded' if together else 'possible')


def test_random_disc_without_log_and_nominal_preset(lab):
    image = lab.root / 'random.iso'
    randomdisc.write_iso(str(image), 4096, 178, log=lambda _: None)
    virtual_write(lab, image)
    assert not image.with_suffix('.iso.burn.jsonl').exists()
    mid = report(lab)['disc']['mid']
    geo = lab.root / 'results' / 'geo-X-20261120-100000'
    geo.mkdir(parents=True)
    atomic_json(geo / 'summary.json', dict(identity=dict(disc=mid), fit=dict(u=180000, v=5.5, media='dvd')))
    (geo / 'targets.csv').write_text('header\n' + 'sample\n' * guide.MIN_RUNGS, encoding='utf-8')
    assert report(lab)['calibration']['status'] == 'batch_record'
    result = report(lab, '--dis-nominal')
    assert result['content']['kind'] == 'random' and result['content']['samples']['random'] == 24
    assert outcomes(result)['image_as_file'] == 'excluded'
    assert outcomes(result)['geometry'] == 'possible'
    assert outcomes(result)['write'] == 'unknown'


def test_unique_id_reuses_matching_burn_even_when_later_burn_is_logged(lab, monkeypatch):
    image = lab.root / 'source.iso'
    randomdisc.write_iso(str(image), discid.MIN_SECTORS, 178, disc_id=True, log=lambda _: None)
    patched = discid.patch_burn(image, {}, speed=8, selected=8, media='dvd')
    body = patched.record['body']
    body['geometry']['preset_id'] = 'dvd-5-120mm'
    patched = discid.PatchedImage(image, discid.seal(body))
    written = lab.root / 'recorded.iso'
    with patched.open() as reader, written.open('wb') as target:
        shutil.copyfileobj(reader, target)
    virtual_write(lab, written)
    verification = dict(status='completed', ok=96, unreadable=0, untested=0, differing=0)
    info = dict(type='burn_result', result='completed', image=str(image), drive='X:', verification=verification)
    log = Path(f'{image}.burn.jsonl')
    log.write_text(json.dumps(dict(info, identity=patched.record)) + '\n' +
                   json.dumps(dict(info, identity={'body': {'id': 'different burns have different IDs'}},
                                   verification=dict(verification, ok=1))) + '\n', encoding='utf-8')
    monkeypatch.setattr(burner, 'verify_image', lambda *a, **k: pytest.fail('must reuse matching burn log'))
    found = checkburn.check('X:', iso=image, out=lab.root / 'results', device_factory=lambda d: LabDrive(lab, d))
    assert found['source'] == 'matched_burn_log' and found['verification'] == verification
    assert found['calibration'] == dict(status='nominal', source='disc_identity', preset_id='dvd-5-120mm')


def test_cd_audio_and_data_patterns():
    def audio(_lba, count):
        return (b'\x0d\xaa' * 1176) * count

    def data(lba, count):
        if lba < 32:
            return bytes(2048 * count)
        return (cd.SCRAMBLE[24:24 + 2048] ^ 0xAA).tobytes() * count

    assert probe(audio, 1024, 'cd', audio=True)['kind'] == 'pattern'
    assert probe(data, 1024, 'cd')['kind'] == 'pattern'


def test_root_extent_errors_and_unsupported_udf():
    def udf(_lba, _count):
        return b'\x00NSR02' + bytes(2042)

    assert filesystem(udf, 1024)['status'] == 'unsupported'
    pvd = bytearray(iso9660.sectors(4096, 'FIXTURE')[16])
    pvd[166:170] = (0xFFFFFFF0).to_bytes(4, 'little')
    assert filesystem(lambda lba, _: pvd if lba == 16 else bytes(2048), 4096)['status'] == 'unavailable'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows transport fallback')
def test_windows_transport_fallback_is_read_only(monkeypatch):
    from discprobe import imapi

    def denied(drive):
        assert drive == 'X:'
        raise PermissionError(5, 'SPTI not elevated')

    marker = object()
    monkeypatch.setattr(device, 'Device', denied)
    monkeypatch.setattr(imapi, 'ImapiDevice', lambda drive: marker)
    assert checkburn._open_device('X:') is marker
