"""Community hints: download, search and explicit DIS-preset import. No drive access."""
from __future__ import annotations

from datetime import datetime, timezone
import http.client
import json
from pathlib import Path

from . import i18n, news, presets
from .community_feed import CommunityError, LIMIT, read_feed

DEFAULT_SOURCES=tuple(s.replace('/news/news.json','/news/community.json') for s in news.DEFAULT_SOURCES)
BUNDLED=news.BUNDLED/'community.json'
BUNDLED_SOURCE='bundled:faxnews/community.json'
WARNING='不是 DP 测的，这批盘还没确认，只当起点。'


def get_community(sources=None, *, cache=None, _test_http=False):
    """Use the fax downloader, including pinned public DNS, redirect checks and timeout."""
    root=Path(cache) if cache is not None else news.cache_dir()
    errors=[]
    def result(feed, origin, source, fetched):
        return dict(feed=feed,source=source,fetched_at=fetched,date=feed['date'],count=feed['count'],
                    errors=errors,**{'from':origin})
    for source in DEFAULT_SOURCES if sources is None else sources:
        try:
            raw, final=news._download(source,LIMIT,test_http=_test_http)
            feed=read_feed(raw)
            got=result(feed,'network',final,datetime.now(timezone.utc).isoformat())
            try:
                news._write(root/'community.json',json.dumps(got,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))
            except OSError:
                pass
            return got
        except (ValueError,OSError,http.client.HTTPException,UnicodeError,RecursionError) as exc:
            errors.append(dict(source=source,error=str(exc)))
    try:
        with (root/'community.json').open('rb') as stream:
            raw=stream.read(LIMIT*2+1)
        if len(raw)>LIMIT*2: raise CommunityError('cached community too large')
        saved=news._json(raw); feed=read_feed(saved['feed'])
        news._url(saved['source'],_test_http)
        if not isinstance(saved['fetched_at'],str) or len(saved['fetched_at'])>100:
            raise CommunityError('invalid cached time')
        return result(feed,'cache',saved['source'],saved['fetched_at'])
    except (ValueError,OSError,KeyError,TypeError,RecursionError,UnicodeError):
        with BUNDLED.open('rb') as stream:
            feed=read_feed(stream.read(LIMIT+1))
        return result(feed,'bundled',BUNDLED_SOURCE,None)


def search(feed, *, media=None, mid=None, sectors=None, search=None, include_failed=False):
    """Identity queries match MID OR capacity OR text; type is a hard filter.

    This makes capacity-only fallback visible while ranking an exact MID first.
    Also search alternate products sharing the exact numeric set.
    """
    if media is not None and media not in ('cd','dvd','bd'): raise ValueError('media must be cd, dvd or bd')
    if sectors is not None and (type(sectors) is not int or sectors<=0): raise ValueError('sectors must be positive')
    mid=(mid or '').strip().casefold(); query=(search or '').strip().casefold()
    rows=[]
    for e in feed['entries']:
        if media and media!=e['media'] or (not include_failed and e['result']=='failed'): continue
        discs=[e['disc'],*[s['disc'] for s in e['also'] if 'disc' in s]]
        same_mid=bool(mid) and any(mid==(d.get('mid') or '').casefold() for d in discs)
        same_sectors=sectors is not None and any(sectors==d.get('capacity_sectors') for d in discs)
        same_text=bool(query) and any(query in ' '.join(str(d.get(k) or '') for k in ('brand','type','ring_code')).casefold() for d in discs)
        if (mid or sectors is not None or query) and not (same_mid or same_sectors or same_text): continue
        rows.append(((not same_mid,not same_sectors,not same_text,e['id']),e))
    return [e for _,e in sorted(rows,key=lambda row:row[0])]


def notice(entry, zh=True):
    s=entry['source']; who='DIS 内置 '+str(s['version']) if s['kind']=='dis_builtin' else 'DIS 社区 '+str(s['author'] or '')
    span=entry['measured_span_mm']
    measured=f'{span[0]}–{span[1]} mm' if span else ('没有实测范围' if zh else 'no measured range')
    return f'来自 {who}，不是 DP 测的；{measured}；这批盘还没确认。' if zh else f'From {who}; not measured by DP; {measured}; this batch is unconfirmed.'


def import_entry(entry, directory='presets'):
    # Always use the existing importer and its numerical/image-compatibility gates.
    p=dict(entry['parameters'])
    if entry['media']!='cd' and 'sectors' in p:
        p['totalSectors']=p.pop('sectors')
    p.update(id='community-'+entry['id'],displayName=entry['disc'].get('brand') or entry['id'],
             description=notice(entry)+' '+entry['result_notes'])
    provenance=dict(id=entry['id'],url=entry['source']['url'],author=entry['source']['author'],
        date=entry['source']['date'],result=entry['result'],result_notes=entry['result_notes'],
        confidence=entry['confidence'],source=entry['source'],also=entry['also'],
        measured_span_mm=entry['measured_span_mm'],note=WARNING)
    return presets.import_file(json.dumps(p,ensure_ascii=False),entry['source']['url'],directory,
                               media=entry['media'],community_source=provenance)


def add_parser(sub):
    p=sub.add_parser('community',help='browse community hints; import only when explicitly requested')
    p.add_argument('--media',choices=('cd','dvd','bd'),help='filter community hints by disc type')
    p.add_argument('--mid',help='find community hints with this exact MID')
    p.add_argument('--sectors',type=int,help='find community hints with this sector count')
    p.add_argument('--search',help='search community disc brands and models')
    p.add_argument('--include-failed',action='store_true',help='include reports where these parameters failed')
    p.add_argument('--json',action='store_true',help='print community hints as JSON')
    p.add_argument('--import',dest='import_id',metavar='ID',help='explicitly import one community hint into the preset library')
    p.add_argument('--directory',default='presets',help='directory for explicitly imported community presets')
    p.set_defaults(func=run)


def run(args):
    got=get_community(); feed=got['feed']
    if args.import_id:
        row=next((e for e in feed['entries'] if e['id']==args.import_id),None)
        if row is None: raise SystemExit('unknown community ID: '+args.import_id)
        got['import']=import_entry(row,args.directory)
    got['entries']=search(feed,media=args.media,mid=args.mid,sectors=args.sectors,search=args.search,include_failed=args.include_failed)
    if args.json:
        print(json.dumps(got,ensure_ascii=False,allow_nan=False)); return 0
    zh=i18n.active()=='zh'
    origins={'network':'联网','cache':'上次的','bundled':'程序自带'}
    print(f"{'社区提示' if zh else 'Community hints'} · {got['date']} · {got['count']} · {origins[got['from']] if zh else got['from']}")
    print(got['source'])
    labels={'worked':'有人报告有效','partly':'有人报告部分有效','failed':'有人用这组失败了','unknown':'结果未确认'}
    for e in got['entries']:
        print(f"{e['id']} · {e['media'].upper()} · {e['disc'].get('brand') or ''} · {labels[e['result']] if zh else e['result']}")
        print(notice(e,zh)); print(e['source']['url'])
    if args.import_id: print(json.dumps(got['import'],ensure_ascii=False))
    return 0
