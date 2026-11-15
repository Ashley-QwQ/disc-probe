"""Loopback fixture for test_csp_browser.mjs; all hardware providers are stubbed."""
import json
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discprobe import webui, guide
from disclab.desk import Desk, ThreadingHTTPServer, handler_for
from disclab.lab import Lab

root = Path(sys.argv[1])
with patch.object(guide, 'optical_drives', return_value=[]):
    backend = webui.Backend(root / 'dp', drive_provider=lambda: [])
    run = backend.root / 'results/geo-X-20261115-120000'
    run.mkdir(parents=True)
    (run / 'summary.json').write_text('{}', encoding='utf-8')
    token = backend.photos.token(run.name)
    dp = webui.Server(backend, 0)
    subprocess.run([sys.executable, '-B', '-m', 'disclab', 'box', '--lab', str(root / 'lab'), '--count', '1', '--json'],
                   check=True, capture_output=True)
    lab = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Desk(Lab(root / 'lab'))))
    for server in (dp, lab):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps(dict(dp=dp.server_port, lab=lab.server_port, phone='/phone/' + token)), flush=True)
    try:
        sys.stdin.read()
    finally:
        for server in (dp, lab):
            server.shutdown()
            server.server_close()
