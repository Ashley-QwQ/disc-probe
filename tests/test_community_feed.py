import copy
import json
from pathlib import Path

import pytest

from discprobe.community_feed import CommunityError, LIMIT, read_feed
from tools.build_community_feed import build, OUTPUTS, ROOT


def sample():
    return json.loads(OUTPUTS[0].read_bytes())


def test_generated_data_and_reproducible_bundle():
    research=json.loads((ROOT/'data/community-calibrations/dis-github.json').read_text(encoding='utf-8'))
    raw=build(research)
    assert all(p.read_bytes()==raw for p in OUTPUTS)
    feed=read_feed(raw)
    assert feed['count']==len(research['entries'])
    assert len(raw)<LIMIT
    assert len({e['id'] for e in research['entries']})==len(research['entries'])
    for original,row in zip(research['entries'],feed['entries']):
        assert row['id']==original['id']
        assert row['parameters']=={k:v for k,v in original['parameters'].items() if k!='id'}


@pytest.mark.parametrize('change',[
    lambda d:d.update(version=True),
    lambda d:d.update(count=1),
    lambda d:d.update(date='2026-02-30'),
    lambda d:d['entries'].append(d['entries'][0]),
    lambda d:d['entries'][0].update(media='usb'),
    lambda d:d['entries'][0].update(drive=['bad']),
    lambda d:d['entries'][0]['disc'].update(mid='x'*601),
    lambda d:d['entries'][0]['source'].update(url='http://github.com/a/b'),
    lambda d:d['entries'][0]['source'].update(url='https://github.com.evil.test/a'),
    lambda d:d['entries'][0]['source'].update(url='https://user@github.com/a'),
    lambda d:d['entries'][0]['parameters'].update(innerRadiusMm=float('nan')),
    lambda d:d['entries'][0]['parameters'].update(pitchCubic=float('inf')),
    lambda d:d['entries'][0]['parameters'].update(sectors=True),
    lambda d:d['entries'][0].update(measured_span_mm=[54,25]),
    lambda d:d['entries'][0].update(also=[dict(kind='dis_builtin',url='https://github.com/a/b',date='2026-01-01')]),
])
def test_bad_fields(change):
    data=sample(); change(data)
    with pytest.raises(CommunityError): read_feed(data)


def test_bad_wire():
    for raw in (b'x'*(LIMIT+1), b'{}', b'{"number": NaN}', b'\xff', b'['*2000):
        with pytest.raises(CommunityError): read_feed(raw)


def test_unknown_never_becomes_a_measured_span():
    assert any(e['measured_span_mm'] is None for e in sample()['entries'])
