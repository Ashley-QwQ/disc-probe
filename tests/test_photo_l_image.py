"""Offline photo policy and the actual CD/DVD image samplers."""
import copy
import datetime
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from discprobe import cd, cdimage, imagedisc, pcal, photo, rings, webui
from discprobe import __main__ as cli
from discprobe.calib import theta, SECTOR_BITS


def run_files(root, media="dvd"):
    folder = root / "geo-H-20261112-010101"
    folder.mkdir(parents=True)
    bit = cd.BIT_NM if media == "cd" else 133.3
    fit = dict(media=media, u=25 / (bit * 1e-6), v=.016 / (bit * 1e-6), bit_nm_assumed=bit)
    geo = dict(fit=fit, identity=dict(drive="test drive", device_id="H:"))
    summary = folder / "summary.json"
    summary.write_text(json.dumps(geo), encoding="utf-8")
    shots = [dict(id=str(i), disc_id="physical-target-01", status="ok", L_mm=20., zone_spread_mm=.2,
                  c_deg=30 * i, input_sha256=str(i + 1) * 64) for i in range(2)]
    record = dict(path=str(folder), media=media, verdict="ok", offset_mm=20.,
                  L_frames=20 / pcal.CD_FRAME_MM if media == "cd" else None,
                  disc_id="physical-target-01", photos=shots, reader_version="v1",
                  reader_sha256=photo.READER_SHA256,
                  burn_path=dict(burner="H:", path="recorded writer", mode="recorded mode"),
                  source_geo=dict(run_id=folder.name, sha256=hashlib.sha256(summary.read_bytes()).hexdigest(),
                                  drive_identity=photo.drive_identity(geo, folder)))
    target = folder / "photo.json"
    target.write_text(json.dumps(record), encoding="utf-8")
    return summary, target, record, fit


@pytest.mark.parametrize("media", ["cd", "dvd"])
@pytest.mark.parametrize("change,reason", [
    ("none", None), ("absent", "no_photo"), ("refused", "verdict_not_ok"),
    ("unknown", "missing_L"), ("group", "verdict_not_ok"), ("one", "one_photo_provisional"),
    ("disagree", "photos_disagree"), ("pose", "same_pose"),
    ("duplicate", "duplicate_photo"), ("spread", "unknown_spread_or_pose"),
    ("other_drive", "different_drive"), ("other_run", "different_run"),
    ("burn", "unknown_burn_path"), ("disc", "unknown_disc"), ("other_disc", "different_disc"),
    ("reader", "unknown_reader"), ("BD", "unsupported_media"), ("CLV", "unsupported_model"),
])
def test_application_rules(tmp_path, media, change, reason):
    summary, target, record, fit = run_files(tmp_path, media)
    if change == "absent":
        target.unlink()
    elif change == "refused":
        record['verdict'] = 'unsure'
    elif change == "unknown":
        record['offset_mm'] = None
    elif change == "group":
        record['group'] = dict(status='unknown')
    elif change == "one":
        record['photos'] = record['photos'][:1]
    elif change == "disagree":
        record['photos'][1]['L_mm'] += 1
    elif change == "pose":
        record['photos'][1]['c_deg'] = 5
    elif change == "duplicate":
        record['photos'][1]['input_sha256'] = record['photos'][0]['input_sha256']
    elif change == "spread":
        record['photos'][1]['zone_spread_mm'] = None
    elif change == "other_drive":
        record['source_geo']['drive_identity']['device_id'] = 'I:'
    elif change == "other_run":
        record['source_geo']['sha256'] = '0' * 64
    elif change == "burn":
        record['burn_path']['mode'] = None
    elif change == "disc":
        record.pop('disc_id')
    elif change == "other_disc":
        record['photos'][1]['disc_id'] = 'physical-target-02'
    elif change == "reader":
        record.pop('reader_sha256')
    elif change in ("BD", "CLV"):
        data = json.loads(summary.read_text())
        data['fit'].update(media='bd' if change == 'BD' else media, model='clv')
        summary.write_text(json.dumps(data))
    if change != "absent":
        target.write_text(json.dumps(record))
    decision = photo.photo_l(summary, media=media)
    if reason is None:
        assert decision['written'] and decision['L_mm'] == 20
        assert decision['provenance']['disc_id'] == record['disc_id']
        assert decision['provenance']['photo_sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert decision['reader_version'] == 'v1'
    else:
        assert not decision['written'] and decision['reason'].startswith(reason)
        assert not {'L_mm', 'frames', 'sectors', 'channel_bits'} & decision.keys()
        assert photo.shifted_u(fit, decision) == fit['u']


def test_all_shots_must_agree_no_majority_rescue():
    shots = [dict(status='ok', L_mm=x, zone_spread_mm=.1, c_deg=i * 30,
                  id=str(i), input_sha256=str(i + 1) * 64) for i, x in enumerate([1, 1.02, 1.4])]
    assert photo.photo_agreement(shots)['reason'] == 'photos_disagree'
    # Refused shots, however, cannot supply a second acceptable input.
    shots[1]['status'] = shots[2]['status'] = 'poor_angle_coverage'
    assert photo.photo_agreement(shots)['reason'] == 'one_photo_provisional'


@pytest.mark.parametrize("media", ["cd", "dvd"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_geometry_and_actual_iso_bytes(tmp_path, media, sign, monkeypatch):
    monkeypatch.setenv('DISCPROBE_WORKERS', '1')
    from discprobe import iso9660
    class FixedDate(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 12, 12, 0, 0, tzinfo=tz)
    # ISO 9660 carries wall-clock timestamps; compare at the same instant.
    monkeypatch.setattr(iso9660.datetime, 'datetime', FixedDate)
    summary, target, record, fit = run_files(tmp_path, media)
    if sign < 0:
        record['offset_mm'] *= -1
        if record['L_frames'] is not None:
            record['L_frames'] *= -1
        for shot in record['photos']:
            shot['L_mm'] *= -1
        target.write_text(json.dumps(record))
    decision = photo.photo_l(summary, media=media)
    u, v = fit['u'], fit['v']
    shifted = photo.shifted_u(fit, decision)
    bits = cd.SECTOR_BITS if media == 'cd' else SECTOR_BITS
    L = record['offset_mm']
    d = L / pcal.CD_FRAME_MM * cd.FRAME_BITS if media == 'cd' else L / (133.3e-6)
    assert decision['channel_bits'] == pytest.approx(d)
    assert decision['sectors'] == pytest.approx(d / bits)
    n = np.array([100, 1000, 4095]) * bits
    expected = theta(n - d, u, v) - theta(-d, u, v)
    np.testing.assert_allclose(theta(n, shifted, v), expected, atol=1e-10, rtol=0)
    assert np.max(np.abs(theta(n, shifted, v) - theta(n, u, v))) > .01

    coords = (np.arange(600) + .5) * .2 - 60
    x, y = np.meshgrid(coords, coords)
    design = ((np.floor(np.arctan2(y, x) * 60).astype(int) % 2) != 0) & (np.hypot(x, y) > 26)
    writer = cdimage if media == 'cd' else imagedisc
    opts = dict(log=lambda *a: None)
    if media == 'cd':
        opts.update(dark='0D', light='AA')
    before, after, without = [tmp_path / f'{s}.iso' for s in ('before', 'after', 'without')]
    writer.write_iso(str(before), design, u, v, fit['bit_nm_assumed'], 4096, **opts)
    saved = writer.write_iso(str(after), design, shifted, v, fit['bit_nm_assumed'], 4096,
                             meta=dict(photo_l=decision), **opts)
    assert before.read_bytes() != after.read_bytes()
    target.unlink()
    refused = photo.photo_l(summary, media=media)
    writer.write_iso(str(without), design, photo.shifted_u(fit, refused), v,
                     fit['bit_nm_assumed'], 4096, meta=dict(photo_l=refused), **opts)
    assert before.read_bytes() == without.read_bytes()
    # Reopening the output uses its captured evidence, even after photo.json is removed.
    reloaded = json.loads(Path(saved).read_text())
    same = photo.image_photo_l(summary, after, media=media)
    assert same == decision == reloaded['photo_l']
    assert photo.shifted_u(fit, same) == reloaded['u']
    assert photo.image_photo_l(summary, after, media=media, disabled=True)['reason'] == 'opted_out'
    assert photo.image_photo_l(summary, after, media=media, device_id='I:')['reason'] == 'different_drive'
    broken = copy.deepcopy(decision)
    broken['L_mm'] += 1
    assert not photo.photo_l(summary, media=media, frozen=broken)['written']


@pytest.mark.parametrize('media', ['cd', 'dvd'])
@pytest.mark.parametrize('disabled', [False, True])
def test_image_cli_hands_the_shift_to_writer(tmp_path, media, disabled):
    summary, target, record, fit = run_files(tmp_path, media)
    parser, _, _ = cli._build_parser()
    args = parser.parse_args(['image', '--geo', str(summary), '--media', media,
                              '--output', str(tmp_path / 'cli.iso')] + (['--no-photo-l'] if disabled else []))
    design = np.zeros((600, 600), bool)
    writer = cdimage if media == 'cd' else imagedisc
    with patch.object(imagedisc, 'grid_design', return_value=design), \
         patch.object(writer, 'sectors_to_radius', return_value=128), \
         patch.object(writer, 'write_iso', return_value=str(tmp_path / 'cli.image.json')) as write, \
         patch.object(writer, 'verify_iso', return_value=[]), patch.object(imagedisc, 'preview'), \
         patch.object(cli, '_warn_other_run'), patch.object(cli, '_image_ready'):
        cli.cmd_image(args)
    decision = write.call_args.kwargs['meta']['photo_l']
    assert decision['written'] is not disabled
    assert write.call_args.args[2] == photo.shifted_u(fit, decision)


@pytest.mark.parametrize('media', ['cd', 'dvd'])
def test_rings_cli_uses_and_persists_shift(tmp_path, media):
    from discprobe import cdrings
    summary, target, record, fit = run_files(tmp_path, media)
    parser, _, _ = cli._build_parser()
    args = parser.parse_args(['rings', '--geo', str(summary), '--media', media, '--describe'])
    if media == 'cd':
        args.textures = '0D,AA'
        args.filler = 'AA'
    args.start_mm = 27
    args.groups = 2
    args.ring_width_mm = .2
    cls = cdrings.RingLayout if media == 'cd' else rings.RingLayout
    built = []
    original = cls.build
    def capture(layout):
        built.append(layout)
        return original(layout)
    with patch.object(cls, 'build', capture):
        cli.cmd_rings(args)
    layout = built[-1]
    decision = photo.photo_l(summary, media=media)
    assert layout.r0_mm == photo.shifted_u(fit, decision) * fit['bit_nm_assumed'] * 1e-6
    saved = tmp_path / 'rings.rings.json'
    layout.save(saved)
    restored = rings.RingLayout.load(saved)
    assert restored.photo_l == decision
    assert restored.rings == layout.rings


def test_web_command_needs_no_client_L(tmp_path):
    summary, target, record, fit = run_files(tmp_path)
    argv, drive = webui.command(dict(action='image', media='dvd', args=dict(
        geo=str(summary), design_npy='designs/picture.npy', output='iso/picture.iso', r_max=52)), tmp_path, [])
    assert drive is None and '--along-track-frames' not in argv
    assert argv[argv.index('--geo') + 1] == str(summary.resolve())


def test_web_image_result_contains_server_decision(tmp_path):
    summary, target, record, fit = run_files(tmp_path)
    decision = photo.photo_l(summary, media='dvd')
    output = tmp_path / 'iso/picture.iso'
    output.parent.mkdir()
    output.write_bytes(bytes(4096))
    output.with_suffix('.image.json').write_text(json.dumps(dict(photo_l=decision)))
    class FinishedChild:
        def __init__(self, argv, **kwargs):
            assert '--along-track-frames' not in argv
            assert argv[argv.index('--reading-drive') + 1] == 'H:'
        def wait(self):
            return 0
        def close(self):
            pass
        def cancel(self):
            pass
    backend = webui.Backend(tmp_path, runner=FinishedChild,
                            drive_provider=lambda: [dict(id='H:', disc=None)])
    try:
        started = backend.start(dict(action='image', media='dvd', drive='H:', args=dict(
            geo=str(summary), design_npy='designs/picture.npy', output='iso/picture.iso')))
        job = backend.get_job(started['job'])
        assert job.finished.wait(5)
        assert job.exit == 0
        assert job.result['photo_l'] == decision
        assert job.result['path'] == 'iso/picture.iso'
        assert any(e.get('step') == 'image' and e.get('photo_l') == decision for e in job.history)
    finally:
        backend.close()


def test_burn_log_reuses_iso_evidence_without_reading_new_photo(tmp_path):
    from discprobe import burner
    summary, target, record, fit = run_files(tmp_path)
    decision = photo.photo_l(summary, media='dvd')
    image = tmp_path / 'picture.iso'
    image.write_bytes(bytes(4096))
    image.with_suffix('.image.json').write_text(json.dumps(dict(photo_l=decision)))
    target.unlink()
    recorder = Mock()
    recorder.inspect.return_value = dict(blank=True, media='dvd', free_sectors=20, speeds_x=[4])
    recorder.write.return_value = 4
    with patch.object(burner, 'adapter', side_effect=AssertionError('no drive access')), \
         patch.object(burner.ui, 'event') as event:
        for _ in range(2):
            burner.burn('H:', image, yes_write=True, no_verify=True, recorder=recorder)
    rows = [json.loads(line) for line in Path(str(image) + '.burn.jsonl').read_text().splitlines()]
    assert len(rows) == 6 and all(row['photo_l'] == decision for row in rows)
    assert event.call_args.kwargs['photo_l'] == decision


def test_saved_decision_rechecks_run_and_policy(tmp_path):
    summary, target, record, fit = run_files(tmp_path)
    decision = photo.photo_l(summary, media='dvd')
    changed = copy.deepcopy(decision)
    changed['provenance']['policy'] = 'other-policy'
    assert not photo.photo_l(summary, media='dvd', frozen=changed)['written']
    data = json.loads(summary.read_text())
    data['fit']['u'] += 1
    summary.write_text(json.dumps(data))
    assert photo.photo_l(summary, media='dvd', frozen=decision)['reason'] == 'different_run'
