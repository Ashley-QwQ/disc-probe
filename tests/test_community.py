import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from discprobe import community, news, zh
from discprobe.__main__ import _build_parser
from test_news import mirror


@pytest.fixture
def feed():
    return json.loads(community.BUNDLED.read_bytes())


def test_network_mirror_cache_bundle(mirror,tmp_path,feed):
    mirror.routes['/community']=(200,json.dumps(feed).encode(),{})
    urls=[mirror.url+'/missing',mirror.url+'/community']
    got=community.get_community(urls,cache=tmp_path,_test_http=True)
    assert got['from']=='network' and got['source']==urls[1]
    assert got['date']==feed['date'] and got['count']==len(feed['entries'])
    assert [p for p,_ in mirror.requests]==['/missing','/community']
    for _,headers in mirror.requests:
        assert set(headers)=={'Host','User-Agent'}
    cached=community.get_community([urls[0]],cache=tmp_path,_test_http=True)
    assert cached['from']=='cache' and cached['feed']==feed
    (tmp_path/'community.json').write_bytes(b'bad')
    assert community.get_community([urls[0]],cache=tmp_path,_test_http=True)['from']=='bundled'


@pytest.mark.parametrize('body,headers',[
    (b'x',{'Content-Length':str(news.PAPER_LIMIT+1)}),
    (b'x'*(news.PAPER_LIMIT+1),{}),
    (b'{}',{}), (b'{"n":NaN}',{}),
],ids=['large-header','large-body','bad-object','nonfinite'])
def test_bad_network_feed_retries(mirror,tmp_path,feed,body,headers):
    mirror.routes['/bad']=(200,body,headers)
    mirror.routes['/good']=(200,json.dumps(feed).encode(),{})
    got=community.get_community([mirror.url+'/bad',mirror.url+'/good'],cache=tmp_path,_test_http=True)
    assert got['from']=='network' and len(got['errors'])==1


def test_default_mirror_order_and_readonly_cache(monkeypatch,tmp_path,feed):
    calls=[]
    def download(url,limit,**kwargs):
        calls.append(url)
        if len(calls)==1: raise OSError('offline')
        return json.dumps(feed).encode(),url
    monkeypatch.setattr(news,'_download',download)
    monkeypatch.setattr(news,'_write',lambda *a:(_ for _ in ()).throw(OSError('full')))
    assert community.get_community(cache=tmp_path)['from']=='network'
    assert calls==list(community.DEFAULT_SOURCES)
    assert 'raw.githubusercontent.com' in calls[0] and 'cdn.jsdelivr.net' in calls[1]


def test_shared_ssrf_and_cache_bounds(tmp_path):
    for url in ('http://127.0.0.1/a','https://127.0.0.1/a','https://user@github.com/a'):
        assert community.get_community([url],cache=tmp_path)['from']=='bundled'
    (tmp_path/'community.json').write_bytes(b' '*(news.PAPER_LIMIT*2+1))
    assert community.get_community([],cache=tmp_path)['from']=='bundled'


def test_filter_priority_aliases_and_failed(feed):
    a,b,c=[copy.deepcopy(feed['entries'][0]) for _ in range(3)]
    for e,name in zip((a,b,c),('text','capacity','mid')):
        e['id']=name; e['disc'].update(mid=None,brand=name,capacity_sectors=1)
        e['result']='unknown'
        e['also']=[]
    b['disc']['capacity_sectors']=999
    c['disc']['mid']='EXACT'
    f={'entries':[a,b,c]}
    assert [e['id'] for e in community.search(f,mid='exact',sectors=999,search='text')]==['mid','capacity','text']
    c['result']='failed'
    assert community.search(f,mid='EXACT')==[]
    assert community.search(f,mid='EXACT',include_failed=True)==[c]
    a['also']=[{'disc':dict(mid='ALIAS')}]
    assert community.search(f,mid='alias')==[a]
    assert community.search(f,media='bd')==[]
    with pytest.raises(ValueError): community.search(f,sectors=-1)


def test_import_source_and_no_dp_measurement(feed,tmp_path):
    entry=next(e for e in feed['entries'] if e['id']=='I339-1')
    report=community.import_entry(entry,tmp_path)
    assert len(report['written'])==1
    path=Path(report['written'][0]['path']); saved=json.loads(path.read_text(encoding='utf-8'))
    s=saved['source']['community']
    assert {k:s[k] for k in ('id','result','confidence')}=={k:entry[k] for k in ('id','result','confidence')}
    assert s['url']==entry['source']['url'] and s['author']==entry['source']['author'] and s['date']==entry['source']['date']
    assert '不是 DP 测的' in s['note'] and '这批盘还没确认' in s['note'] and '只当起点' in s['note']
    assert saved['fit']['calibrated'] is False and saved['fit']['measured_span_mm'] is None
    assert s['measured_span_mm']==[25.648,54.205]
    assert community.import_entry(entry,tmp_path)['duplicates']


def test_cli_and_chinese_help(monkeypatch,tmp_path,feed,capsys):
    monkeypatch.setattr(community,'get_community',lambda:dict(feed=feed,source=community.BUNDLED_SOURCE,date=feed['date'],count=feed['count'],**{'from':'bundled'}))
    parser=_build_parser()[0]
    args=parser.parse_args(['community','--media','dvd','--mid','RITEKF1','--json'])
    assert args.func(args)==0
    got=json.loads(capsys.readouterr().out)
    assert got['from']=='bundled' and got['entries']
    assert 'feed' not in got and all(e['media']=='dvd' and e['result']!='failed' for e in got['entries'])
    assert not (tmp_path/'presets').exists()
    args=parser.parse_args(['community','--import','I339-1','--directory',str(tmp_path),'--json'])
    assert args.func(args)==0 and json.loads(capsys.readouterr().out)['import']['written']
    for action in parser._subparsers._group_actions[0].choices['community']._actions:
        if action.dest!='help': assert action.help in zh.TEXT


def test_mid_ignores_dye_note():
    from discprobe.community import mid_code
    assert mid_code('MCC 004 · AZO') == mid_code('mcc  004') == 'mcc 004'
