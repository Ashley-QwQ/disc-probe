"""The starter uses a separate evidence contract, with no physical drive access."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from discprobe import __main__ as cli
from discprobe import burn_gate, photo, pcal, starter, webui
from tests.test_webui_catalog import write_geo


def source(root, stamp='20261107-101500', mid='RITEKF1', drive='H:', machine=None):
    fit = dict(media='dvd', u=180518., v=5.591, bit_nm_assumed=133.3, chi2_per_dof=1,
               measured_span_mm=[25.8, 57.2], angle_sigma_measured_span_deg=.1)
    identity = {'drive': 'Example GH70N', 'firmware': 'A1', 'disc': mid}
    folder = write_geo(root, stamp, fit=fit, identity=identity)
    who = starter.identity(identity, drive)
    saved = {**who, 'machine': machine} if machine else who
    path = folder / 'summary.json'
    (folder / 'starter-source.json').write_text(json.dumps(dict(
        geo_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), drive_identity=saved)), encoding='utf-8')
    return path, who


def test_rank_source_and_keep_batch_unconfirmed(tmp_path):
    local, who = source(tmp_path)
    source(tmp_path, '20261108-101500', machine='other')
    source(tmp_path, '20261109-101500', mid='OTHER-MID')
    out = tmp_path / 'results'
    rows = starter.candidates(tmp_path, out, who, 'RITEKF1')
    assert [row['source']['kind'] for row in rows] == ['same_drive', 'same_model']
    assert rows[1]['source']['verification'] == 'unverified_cross_machine_or_batch'
    target = starter.create(out, rows[0], who, 'RITEKF1', 2295104)
    doc, sha = starter.read(target)
    assert doc['status'] == 'batch_unconfirmed'
    assert doc['source']['path'] == local.relative_to(tmp_path).as_posix()
    assert doc['source']['sha256'] == hashlib.sha256(local.read_bytes()).hexdigest()
    assert doc['source']['measured_span_mm'] == [25.8, 57.2]
    assert doc['source']['prior_L_mm'] is None and len(sha) == 64
    assert list(starter.catalogue(tmp_path, out)) == []
    assert starter.candidates(tmp_path, out, who, 'NO MATCH') == []


def setup_check(tmp_path):
    _, who = source(tmp_path)
    out = tmp_path / 'results'
    choice = starter.candidates(tmp_path, out, who, 'RITEKF1')[0]
    path = starter.create(out, choice, who, 'RITEKF1', 2295104)
    _, sha = starter.read(path)
    receipt = dict(starter_sha256=sha, drive_identity=who, disc_id='SP-000000000001',
                   burn_path=dict(burner='H:', path='IMAPI', mode='DVD single closed session'))
    return path, receipt


def shots(tmp_path, monkeypatch, *, damaged=False):
    photos = []
    for i in range(2):
        path = tmp_path / f'shot-{i}.png'
        Image.new('RGB', (6, 6), (i, 8, 16)).save(path)
        photos.append((str(i), path))

    def fake_read(rgb, design, **kwargs):
        row = dict(design=design.name, ring_locked=True, peak_z=25, runner_up_ratio=.5, n_inliers=30, n_votes=40,
                   max_gap_deg=30, r_span_mm=24, rms_deg=1.2 if damaged else .05, sigma_L_jack_mm=.02,
                   zone_spread_mm=.1, c_deg=float(rgb[0, 0, 0]) * 45, L_mm=.5)
        return dict(status=pcal.verdict(row), **row)

    monkeypatch.setattr(pcal, 'read_photo', fake_read)
    return photos


def test_requires_this_burn_and_disc_to_apply(tmp_path, monkeypatch):
    path, receipt = setup_check(tmp_path)
    inputs = shots(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='measurement disc'):
        photo.analyze(path.parent, 'dvd', inputs, disc_id=receipt['disc_id'])
    starter.save_burn(path, receipt)
    with pytest.raises(ValueError, match='measurement disc'):
        photo.analyze(path.parent, 'dvd', inputs, disc_id=receipt['disc_id'], burn_path='other')
    report = photo.analyze(path.parent, 'dvd', inputs, disc_id=receipt['disc_id'])
    assert report['starter'] == dict(written=True, reason=None)
    decision = photo.photo_l(path)
    assert decision['provenance']['kind'] == 'starter_preset'
    assert decision['provenance']['starter_sha256'] == receipt['starter_sha256']
    assert decision['provenance']['drive_identity'] == receipt['drive_identity']
    assert decision['provenance']['burn_path'] == receipt['burn_path']
    assert decision['provenance']['disc_id'] == receipt['disc_id']
    assert photo.photo_l(path, frozen=decision) == decision
    assert photo.photo_l(path, device_id='X:')['reason'] == 'different_drive'
    assert list(starter.catalogue(tmp_path, tmp_path / 'results'))[0]['starter'] is True
    path.write_text(path.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    assert not photo.photo_l(path)['written']


def test_failed_photos_refuse_image_and_return_to_measurement(tmp_path, monkeypatch, capsys):
    path, receipt = setup_check(tmp_path)
    starter.save_burn(path, receipt)
    report = photo.analyze(path.parent, 'dvd', shots(tmp_path, monkeypatch, damaged=True), disc_id=receipt['disc_id'])
    assert report['starter'] == dict(written=False, reason='large_residual')
    assert 'Return to the measurement disc' in capsys.readouterr().out
    parser, _, _ = cli._build_parser()
    iso = tmp_path / 'picture.iso'
    args = parser.parse_args(['image', '--geo', str(path), '--output', str(iso)])
    monkeypatch.setattr('discprobe.imagedisc.grid_design', lambda **kw: np.zeros((64, 64), bool))
    with pytest.raises(SystemExit, match='large_residual'):
        cli.cmd_image(args)
    assert not iso.exists()


def test_starter_is_an_explicit_read_only_web_action(tmp_path):
    payload = dict(action='starter', media='dvd', drive='H:', args={'source':'geo:geo-H-20261107-101500'})
    argv, drive = webui.command(payload, tmp_path, [{'id':'H:'}])
    assert drive == 'H:' and argv[-2:] == ['--source', payload['args']['source']]
    assert webui.burn_action(payload) is None
    assert burn_gate.batch_problem('RITEKF1', 'RITEKF1') is None
    with pytest.raises(webui.APIError):
        webui.command({**payload, 'media':'cd'}, tmp_path, [{'id':'H:'}])
