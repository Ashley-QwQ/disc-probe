#!/bin/bash
cd ~/faxnews-lobby
BL=~/disc-video/blender/blender-5.2.2-linux-x64/blender
R="--disable-autoexec --python render_fax.py -- --ss 4 --device CPU --no-mist --variants paper,dark -t 14"
$BL -b room_round5.blend --disable-autoexec --python place_fax.py -- --fax fax_news.blend --parts parts.json --out room_fax.blend > log_place.txt 2>&1
$BL -b room_round5.blend --disable-autoexec --python place_fax.py -- --fax fax_news.blend --parts parts.json --out room_fax_parcel.blend --parcel >> log_place.txt 2>&1
date
$BL -b room_fax.blend $R --outdir final --layers base,faxnews,filebox --force > log_a.txt 2>&1
date
$BL -b room_fax_parcel.blend $R --outdir final_parcel --layers base,parcel --force > log_b.txt 2>&1
date
echo ALLDONE
