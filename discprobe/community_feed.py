"""The bounded dp-community v1 wire format. No network or filesystem writes."""
from __future__ import annotations

from datetime import date
import json
import math
import re
from urllib.parse import urlsplit

LIMIT = 1024 * 1024
PARAMETERS = {'innerRadiusMm', 'outerRadiusMm', 'sectors', 'totalSectors', 'usableSectors',
              'pitchLinear', 'pitchQuadratic', 'pitchCubic', 'linearVelocityMmPerSecond',
              'channelBitLengthNm', 'invertMapping', 'linearDensity', 'r0_mm', 'pitch_um',
              'p0_um', 'interleave', 'u', 'v'}


class CommunityError(ValueError):
    pass


def need(ok, field):
    if not ok:
        raise CommunityError('invalid community feed: ' + field)


def text(value, limit=600, nullable=False):
    return (nullable and value is None) or (isinstance(value, str) and len(value) <= limit
        and not any(ord(c) < 32 and c not in '\n\t' for c in value))


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def github(value):
    if not text(value, 600) or any(ord(c) <= 32 for c in value) or '\\' in value:
        return False
    try:
        u = urlsplit(value)
        return u.scheme == 'https' and u.netloc == 'github.com' and u.path.startswith('/') and not u.query
    except ValueError:
        return False


def day(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def disc(value):
    need(isinstance(value, dict) and set(value) <= {'mid','brand','type','capacity_sectors','ring_code'}, 'disc')
    for k in ('mid','brand','type','ring_code'):
        need(text(value.get(k), nullable=True), 'disc.'+k)
    n = value.get('capacity_sectors')
    need(n is None or (type(n) is int and 0 < n <= 2**63-1), 'disc.capacity_sectors')


def provenance(value):
    need(isinstance(value, dict) and set(value) <= {'kind','version','url','author','date','builtin_id','disc','result','notes','id'}, 'source')
    need(value.get('kind') in ('community','dis_builtin'), 'source.kind')
    need(github(value.get('url')), 'source.url')
    need(day(value.get('date')), 'source.date')
    author = value.get('author')
    need(author is None or (isinstance(author,str) and bool(re.fullmatch(r'[A-Za-z0-9-]{1,39}(?:\[bot\])?',author))), 'source.author')
    for k in ('version','builtin_id','id'):
        need(text(value.get(k), 160, nullable=True), 'source.'+k)
    if value['kind'] == 'dis_builtin':
        need(bool(value.get('version')) and bool(value.get('builtin_id')), 'source.builtin version/id')
    if 'disc' in value:
        disc(value['disc'])
    if 'result' in value:
        need(value['result'] in ('worked','partly','failed','unknown'), 'source.result')
    if 'notes' in value:
        need(text(value['notes'],2000), 'source.notes')


def read_feed(raw):
    """Strictly validate bytes, objects, every row and nested field, without truncation."""
    if isinstance(raw, (bytes,str)):
        need(len(raw if isinstance(raw,bytes) else raw.encode('utf-8')) <= LIMIT, 'size')
        try:
            raw = json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(CommunityError('nonfinite JSON number')))
        except (ValueError,UnicodeError,RecursionError) as exc:
            raise CommunityError(str(exc)) from None
    need(isinstance(raw,dict) and set(raw) == {'format','version','date','count','source','license','note','entries'}, 'fields')
    need(raw['format'] == 'dp-community' and type(raw['version']) is int and raw['version'] == 1, 'format/version')
    need(day(raw['date']), 'date')
    need(github(raw['source']), 'source')
    need(text(raw['license'],200) and text(raw['note'],2000), 'license/note')
    rows=raw['entries']
    need(isinstance(rows,list) and len(rows) <= 2000 and type(raw['count']) is int and raw['count']==len(rows), 'count')
    seen=set()
    for e in rows:
        need(isinstance(e,dict) and set(e)=={'id','media','disc','drive','speed','parameters','result','result_notes','confidence','source','also','measured_span_mm'}, 'entry.fields')
        ident=e['id']
        need(isinstance(ident,str) and bool(re.fullmatch(r'[A-Za-z0-9-]{1,120}',ident)) and ident not in seen, 'entry.id')
        seen.add(ident)
        need(e['media'] in ('cd','dvd','bd'), 'media')
        disc(e['disc'])
        for k in ('drive','speed'):
            need(text(e[k],nullable=True), k)
        need(e['result'] in ('worked','partly','failed','unknown'), 'result')
        need(text(e['result_notes'],2000), 'result_notes')
        need(e['confidence'] in ('high','medium','low'), 'confidence')
        provenance(e['source'])
        need(isinstance(e['also'],list) and len(e['also']) <= 100, 'also')
        for s in e['also']: provenance(s)
        p=e['parameters']
        need(isinstance(p,dict) and bool(p) and set(p) <= PARAMETERS, 'parameters')
        for k,v in p.items():
            need(type(v) is bool if k in ('invertMapping','interleave') else number(v), 'parameters.'+k)
            if k in ('sectors','totalSectors','usableSectors'):
                need(type(v) is int and 0 < v <= 2**63-1, 'parameters.'+k)
        need(number(p.get('innerRadiusMm')) and number(p.get('outerRadiusMm')) and 0 < p['innerRadiusMm'] < p['outerRadiusMm'] <= 100, 'parameters.radii')
        need(type(p.get('sectors',p.get('totalSectors'))) is int, 'parameters.sectors')
        span=e['measured_span_mm']
        need(span is None or (isinstance(span,list) and len(span)==2 and all(map(number,span)) and 0 < span[0] < span[1] <= 100), 'measured_span_mm')
    try:
        need(len(json.dumps(raw,ensure_ascii=False,allow_nan=False).encode('utf-8')) <= LIMIT, 'size')
    except (ValueError,OverflowError,UnicodeError,RecursionError) as exc:
        raise CommunityError(str(exc)) from None
    return raw
