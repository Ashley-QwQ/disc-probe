"""Portable Windows launcher: bind first, then open the bundled lobby."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import webbrowser

# A direct script must also work with a regular Python in the source package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-only', action='store_true')
    parser.add_argument('--no-drives', action='store_true', help='offline design session; do not enumerate devices')
    args = parser.parse_args()
    from discprobe import api, guide, webui
    if args.no_drives or os.environ.get('DISC_PROBE_NO_DRIVES') == '1':
        guide.optical_drives = lambda: []
    gui, manifest = api.load_manifest(api.BUNDLED_GUI)
    api.check_manifest(manifest)
    backend = webui.Backend()
    with webui.Server(backend, 0, lan=not args.local_only, gui=gui) as server:
        url = f'http://127.0.0.1:{server.server_port}/home/'
        if server.token:
            url += '?token=' + server.token
        print(url, flush=True)
        # Only the OS browser is opened; the server stays owned by this console.
        if not webbrowser.open(url):
            print('Open this address in your browser / 请在浏览器打开上面的地址。', flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
