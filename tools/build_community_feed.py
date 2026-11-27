"""Build the deterministic community fax feed and identical bundled fallback."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe.community_feed import read_feed

OUTPUTS=(ROOT/'news/community.json', ROOT/'discprobe/web/home/faxnews/community.json')


def build(data):
    def source(e, extra=False):
        s=dict(kind=e.get('source_kind','community'),version=e.get('source_version'),
               url=e.get('source_url',e.get('url')),author=e.get('author'),
               date=e.get('posted','')[:10],builtin_id=e.get('builtin_id'),id=e.get('id'))
        if extra:
            s.update(result=e.get('result','unknown'),notes=e.get('result_notes',e.get('note',''))[:2000])
            if 'disc' in e: s['disc']=e['disc']
        return s
    entries=[]
    for e in data['entries']:
        p={k:v for k,v in e['parameters'].items() if k!='id'}
        also=[source(s,True) for s in e.get('additional_sources',[])]
        also += [source(s,True) for s in e.get('reports',[]) if s.get('source_url',s.get('url'))]
        entries.append(dict(id=e['id'],media=e['media'],disc=e['disc'],
            drive=' / '.join(str(v) for v in e['drive'].values() if v) or None,
            speed=e['burn'].get('speed'),parameters=p,result=e['result'],
            result_notes=e['result_notes'][:2000],confidence=e['confidence'],
            source=source(e),also=also,measured_span_mm=e.get('measured_span_mm')))
    feed=dict(format='dp-community',version=1,date=data['updates'][-1]['checked_through'][:10],
              count=len(entries),source='https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio',
              license='DIS built-in presets: GPL-3.0-or-later; community reports attributed to public GitHub usernames.',
              note='来自 DIS 社区或内置预设，不是 DP 测的；没有标注实测范围的就是没有实测范围；这批盘还没确认，只当起点。',entries=entries)
    read_feed(feed)
    return (json.dumps(feed,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check',action='store_true',help='check generated files without writing')
    args=ap.parse_args()
    raw=build(json.loads((ROOT/'data/community-calibrations/dis-github.json').read_text(encoding='utf-8')))
    for path in OUTPUTS:
        if args.check:
            if not path.exists() or path.read_bytes()!=raw: raise SystemExit('stale feed: '+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
    print(f'{len(json.loads(raw)["entries"])} entries, {len(raw)} bytes; both feeds '+('match' if args.check else 'written'))


if __name__=='__main__': main()
