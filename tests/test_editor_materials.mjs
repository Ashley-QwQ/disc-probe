import assert from 'node:assert/strict';
import fs from 'node:fs';
import {colourWord,identityRGB,materialPose} from '../discprobe/web/home/design/editor-materials.mjs';
import {TOOL_KEYS} from '../discprobe/web/home/design/editor-controls.mjs';
const palette=JSON.parse(fs.readFileSync(new URL('../discprobe/web/home/design/swatches.json',import.meta.url),'utf8'));
const frozen=JSON.parse(fs.readFileSync(new URL('../tools/editor-material-ids.json',import.meta.url),'utf8'));
assert.equal(Object.keys(TOOL_KEYS).length,9);assert.equal(new Set(Object.values(TOOL_KEYS)).size,9);
const entries=Object.values(palette.swatches);assert.equal(entries.length,255);
for(const old of frozen){const m=entries.find(m=>m.id===old.id);assert.equal(m.spec,old.spec);assert.deepEqual(m.srgb,old.rgb??old.srgb,'import RGB remains unchanged');
  const light=palette.display_colours[m.id];assert(light.rgb.every(c=>Number.isInteger(c)&&c>=0&&c<=255));
  for(const theme of [false,true]){const ink=identityRGB(m,25,32,theme);assert.equal(ink[0],ink[1]);assert.equal(ink[1],ink[2]);}
}
const lights=Object.values(palette.display_colours);assert(lights.some(v=>v.dark));assert(lights.some(v=>!v.dark));
assert(lights.filter(v=>!v.dark).every(v=>Math.max(...v.rgb)>=85&&Math.max(...v.rgb)-Math.min(...v.rgb)>=12),'near-black fans stay collapsed');
assert.equal(palette.display_model.module,'discprobe.simulate');assert.equal(palette.display_model.entry,'material_swatches');
assert.equal(colourWord({dark:false,hue:0},'zh'),'偏红');
assert.equal(materialPose({cam:[0,-70,330],follows:true},100).camera[1],100);
assert.equal(materialPose({cam:[0,-70,330],follows:false,lamp:[10,-50,400]},100).flash[1],50);
console.log('editor materials: core-generated colours; 255 stable identities; neutral map; pose conversion; nine tools');
