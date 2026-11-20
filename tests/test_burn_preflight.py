import json

import pytest

from discprobe import burn_gate, burner, mmc, webui
from tests.iso_fixture import write_checked_iso


@pytest.fixture
def preflight(tmp_path, monkeypatch):
    (tmp_path / 'iso').mkdir()
    image = tmp_path / 'iso/work.iso'
    write_checked_iso(image, bytes(4 * 2048))
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps({'identity': {'disc': 'RITEKF1'}}), encoding='utf-8')
    image.with_suffix('.image.json').write_text(json.dumps({'geometry_from': str(summary)}), encoding='utf-8')
    disc = dict(present=True, media='dvd', profile=0x11, blank=True, rewritable=False,
                capacity_sectors=25, sectors=25, mid='TYG02')
    backend = webui.Backend(tmp_path, drive_provider=lambda: [dict(id='X:', disc=dict(disc))])
    monkeypatch.setattr(burner, 'inspect_drive', lambda *_: dict(media=disc['media'], blank=disc['blank'],
                                                                free_sectors=disc['capacity_sectors'], speeds_x=[4, 8]))
    return backend, disc


@pytest.mark.parametrize('action', ('burn', 'calibrate'))
def test_mid_warning_and_disc_bound_override(preflight, action):
    backend, disc = preflight
    request = dict(action=action, drive='X:', media='dvd', args={'iso': 'iso/work.iso'})
    response = backend.burn_check(request)
    assert response['gate']['actual_mid'] == 'TYG02'
    assert response['gate']['expected_mid'] == 'RITEKF1'
    for language in ('zh', 'en'):
        assert 'TYG02' in response['gate'][language] and 'RITEKF1' in response['gate'][language]
    with pytest.raises(webui.APIError) as error:
        backend.burn_token(request)
    assert (error.value.status, error.value.code) == (409, 'other_batch')
    approved = dict(request, args=dict(request['args'], confirmed_mid='TYG02'))
    token = backend.burn_token(approved)['token']
    with pytest.raises(webui.APIError, match='does not match the action'):
        backend.start(dict(request, burn_token=token))
    token = backend.burn_token(approved)['token']
    disc['mid'] = 'MCC03RG20'
    with pytest.raises(webui.APIError, match='does not match the current medium'):
        backend.start(dict(approved, burn_token=token))
    assert backend.jobs == {}


def test_saved_batch_wins_and_provenance_is_the_fallback(tmp_path):
    image = tmp_path / 'work.iso'
    geometry = tmp_path / 'summary.json'
    geometry.write_text('{"identity":{"disc":"MEASURED"}}', encoding='utf-8')
    image.with_suffix('.image.json').write_text(json.dumps({'geometry_from': str(geometry)}), encoding='utf-8')
    assert burn_gate.expected_batch(image, work={'batch': {'mid': 'SELECTED'}}) == 'SELECTED'
    assert burn_gate.expected_batch(image, work={'batch': {'name': 'No MID'}}) == 'MEASURED'
    assert burn_gate.batch_problem(' measured ', 'MEASURED') is None


@pytest.mark.parametrize('changes,code', [
    ({'blank': False, 'closed': False}, 'recorded_open'),
    ({'blank': False, 'closed': True, 'profile': 0x10}, 'finalized'),
    ({'blank': False, 'rewritable': True}, 'recorded_rw'),
    ({'media': 'cd', 'profile': 0x09}, 'wrong_media'),
    ({'capacity_sectors': 2}, 'too_small'),
])
def test_media_refusals_include_recovery_in_both_languages(preflight, changes, code):
    backend, disc = preflight
    disc.update(changes)
    result = backend.burn_check(dict(action='burn', drive='X:', media='dvd', args={'iso': 'iso/work.iso'}))
    assert result['gate']['code'] == code
    assert any(word in result['gate']['zh'] for word in ('换', '检查'))
    assert any(word in result['gate']['en'].lower() for word in ('insert', 'check'))
    assert backend.jobs == {}


@pytest.mark.parametrize('reason,code', [(mmc.TRAY_OPEN, 'tray_open'), (mmc.NO_DISC, 'no_disc')])
def test_distinct_tray_refusals(reason, code):
    assert burn_gate.medium_problem({'not_ready': reason}, 'dvd')['code'] == code
