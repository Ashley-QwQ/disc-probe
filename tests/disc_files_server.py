"""Isolated, device-free backend for the shipped design-page browser check."""
import json
from pathlib import Path
import sys
from discprobe.webui import Backend, Server

root=Path(sys.argv[1]).resolve()
root.mkdir(parents=True,exist_ok=True)
source=root/'demo files'
source.mkdir(exist_ok=True)
from .sparse_fixture import zero_file
zero_file(source/'large.bin',256*1024*1024)
(source/'说明.txt').write_text('截图验收使用的合成文件。',encoding='utf-8')
server=Server(Backend(root,drive_provider=lambda:[]),port=0)
(root/'server-info.json').write_text(json.dumps(dict(url=f'http://127.0.0.1:{server.server_port}',folder=str(source))),encoding='utf-8')
try:server.serve_forever()
finally:server.server_close()
