import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

from discprobe import community, webui


def test_http_community_refresh_filter_and_explicit_import(monkeypatch,tmp_path):
    feed=json.loads(community.BUNDLED.read_bytes()); calls=[]
    def get(sources=None):
        calls.append(sources)
        return dict(feed=feed,date=feed['date'],count=feed['count'],source=community.BUNDLED_SOURCE,**{'from':'bundled'})
    monkeypatch.setattr(community,'get_community',get)
    backend=SimpleNamespace(root=tmp_path,lock=threading.RLock(),close=lambda:None)
    server=webui.Server(backend,0)
    worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    def request(path,method='GET',payload=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        h={'Content-Type':'application/json'}; h.update(headers or {})
        try:
            conn.request(method,path,json.dumps(payload) if payload is not None else None,h)
            r=conn.getresponse(); return r.status,json.loads(r.read())
        finally: conn.close()
    try:
        code,value=request('/api/community?media=dvd&sectors=2297888')
        assert code==200 and value['entries'] and calls[-1]==[]
        assert all(e['result']!='failed' for e in value['entries'])
        assert not (tmp_path/'presets').exists()
        assert request('/api/community?refresh=1')[0]==200 and calls[-1] is None
        for query in ('source=https://github.com/a','sectors=-1','refresh=true','mid=a&mid=b'):
            assert request('/api/community?'+query)[0]==400
        assert request('/api/community','POST',{'id':'I339-1'}, {'Origin':'https://evil.example'})[0]==403
        assert request('/api/community','POST',{'id':'no-such-id'})[0]==400
        assert request('/api/community','POST',{'id':'I339-1','directory':'../elsewhere'})[0]==400
        code,value=request('/api/community','POST',{'id':'I339-1'})
        assert code==200 and len(value['written'])==1
        saved=json.loads(Path(value['written'][0]['path']).read_text(encoding='utf-8'))
        assert saved['source']['community']['id']=='I339-1'
    finally:
        server.shutdown(); server.server_close(); worker.join()
