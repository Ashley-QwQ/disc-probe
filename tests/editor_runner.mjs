import fs from 'node:fs';
import * as O from '../discprobe/web/home/design/editor-ops.mjs';
import {render as pattern} from '../discprobe/web/home/design/pattern.mjs';
import {table} from '../discprobe/web/home/design/tone.mjs';
import {bayer, clustered, BLUE_NOISE_RANKS} from '../discprobe/web/home/design/processing.mjs';
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
let out;
if(d.action==='selection')out=O.selection(d.definition,d.grid,d.rgba);
if(d.action==='boolean')out=O.booleanMask(d.a,d.b,d.operation);
if(d.action==='compose')out=O.compose(d.document,d.grid);
if(d.action==='pattern')out=pattern(d.fill,d.grid);
if(d.action==='migrate')out=Buffer.from(JSON.stringify(O.migrate(d.document)));
if(d.action==='tone')out=Buffer.from(JSON.stringify({tables:d.tones.map(t=>[...table(t)]),
  tiles:{'blue-noise':[...BLUE_NOISE_RANKS],ordered:[...bayer(8)],clustered:[...clustered(8)]}}));
fs.writeFileSync(process.argv[3],Buffer.from(out.buffer,out.byteOffset,out.byteLength));
