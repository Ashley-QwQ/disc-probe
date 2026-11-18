"""Portable Windows launcher: bind first, then open the bundled lobby."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

# A direct script must also work with a regular Python in the source package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-only', action='store_true')
    parser.add_argument('--new-instance', action='store_true', help='start a separate service without replacing the existing instance')
    parser.add_argument('--no-drives', action='store_true', help='offline design session; do not enumerate devices')
    args = parser.parse_args()
    from discprobe import api, guide, webui, web_instance
    if args.no_drives or os.environ.get('DISC_PROBE_NO_DRIVES') == '1':
        guide.optical_drives = lambda: []
    lan = not args.local_only
    web_instance.launch(lambda port: webui.Server(webui.Backend(), port, lan=lan, gui=api.BUNDLED_GUI),
                        0, lan=lan, new_instance=args.new_instance, open_browser=True)


if __name__ == '__main__':
    main()
