#!/usr/bin/env bash
# Render the calibration page's top-down burner on glassbox (Git Bash):  bash run_caltop.sh [extra args...]
#   stage layers:      bash run_caltop.sh                  -> out/
#   animation layers:  SUB=out_anim bash run_caltop.sh --anim 1   -> out_anim/
# The model is opened read-only from D:\disc-video\pack\disc_explode_render.blend (never saved).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BL='E:\Blender\blender-5.2.2-windows-x64\blender.exe'
SUB="${SUB:-out}"
OUT="$HERE/$SUB"; mkdir -p "$OUT"
ssh glassbox "mkdir D:\disc-video\desk\caltop\$SUB 2>nul & mkdir D:\disc-video\desk\caltop\props 2>nul" </dev/null >/dev/null 2>&1
scp -q "$HERE/render_caltop.py" "$HERE/render_caltop_anim.py" glassbox:D:/disc-video/desk/caltop/ </dev/null || exit 1
scp -q "$HERE/props/penrose.json" glassbox:D:/disc-video/desk/caltop/props/ </dev/null || exit 1
timeout 3600 ssh glassbox "cd /d D:\disc-video\desk\caltop && $BL -b D:\disc-video\pack\disc_explode_render.blend --python render_caltop.py -- --outdir D:/disc-video/desk/caltop/$SUB $*" </dev/null 2>&1 | grep -E "\[caltop\]|\[anim\]|rror|Traceback|line [0-9]+" | tail -60
scp -q "glassbox:D:/disc-video/desk/caltop/$SUB/*.png" "glassbox:D:/disc-video/desk/caltop/$SUB/*.json" "$OUT/" </dev/null
ls "$OUT"
