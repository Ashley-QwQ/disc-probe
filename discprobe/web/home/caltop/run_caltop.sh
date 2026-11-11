#!/usr/bin/env bash
# Render the calibration page's top-down burner on glassbox (Git Bash):  bash run_caltop.sh [extra args...]
# The model is opened read-only from D:\disc-video\pack\disc_explode_render.blend (never saved).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BL='E:\Blender\blender-5.2.2-windows-x64\blender.exe'
OUT="$HERE/out"; mkdir -p "$OUT"
ssh glassbox "mkdir D:\disc-video\desk\caltop\out 2>nul" </dev/null >/dev/null 2>&1
scp -q "$HERE/render_caltop.py" glassbox:D:/disc-video/desk/caltop/ </dev/null || exit 1
timeout 2400 ssh glassbox "cd /d D:\disc-video\desk\caltop && $BL -b D:\disc-video\pack\disc_explode_render.blend --python render_caltop.py -- --outdir D:/disc-video/desk/caltop/out $*" </dev/null 2>&1 | grep -E "\[caltop\]|rror|Traceback|line [0-9]+" | tail -40
scp -q "glassbox:D:/disc-video/desk/caltop/out/*.png" "glassbox:D:/disc-video/desk/caltop/out/caltop.json" "$OUT/" </dev/null
ls "$OUT"
