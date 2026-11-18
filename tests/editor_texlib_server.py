"""Local-only API fixture; no drives or network services are consulted."""
from pathlib import Path
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe import webui

folder=Path(sys.argv[1])
folder.mkdir(parents=True,exist_ok=True)
if os.environ.get('EDITOR_NO_TEXLIB') == '1':
    os.environ.pop('DISCPROBE_TEXLIB',None)
elif not os.environ.get('EDITOR_TEXLIB_ROOT'):
    from test_editor_texlib import make_library
    library=folder/'fixture'
    make_library(library)
    os.environ['DISCPROBE_TEXLIB']=str(library)
else:
    os.environ['DISCPROBE_TEXLIB']=os.environ['EDITOR_TEXLIB_ROOT']
backend=webui.Backend(folder/'backend',drive_provider=lambda:[])
with webui.Server(backend,0) as server:
    print(server.server_port,flush=True)
    server.serve_forever()
