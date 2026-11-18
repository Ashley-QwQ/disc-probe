"""Local-only API fixture; no drives or network services are consulted."""
from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe import webui

folder=Path(sys.argv[1])
folder.mkdir(parents=True,exist_ok=True)
if not os.environ.get('EDITOR_TEXLIB_ROOT'):
    from test_editor_texlib import make_library
    library=folder/'fixture'
    textures=make_library(library)
    candidates=folder/'colour-candidates.json'
    candidates.write_text(json.dumps([r['spec'] for r in textures]),encoding='utf-8')
    os.environ['DISCPROBE_COLOUR_MATERIALS']=str(candidates)
else:
    library=Path(os.environ['EDITOR_TEXLIB_ROOT'])
os.environ['DISCPROBE_TEXLIB']=str(library)
backend=webui.Backend(folder/'backend',drive_provider=lambda:[])
with webui.Server(backend,0) as server:
    print(server.server_port,flush=True)
    server.serve_forever()
