#!/bin/bash
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit
exec ./linux/python/bin/python3 -X utf8 -B tools/launch_web.py "$@"
