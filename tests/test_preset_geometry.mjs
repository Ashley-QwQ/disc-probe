import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {geoChoice} from '../discprobe/web/home/design/export-rules.mjs';
// The page's geometry selector (export-rules.geoChoice, which design.js's projectGeo and the preview checklist use).
const projectGeo = (state, plan) => geoChoice(plan, state.catalogue?.[plan.media] ?? [],
  state.steps?.find((x) => x.id === 'geo' && x.done)?.result ?? null).path;
const source = readFileSync(new URL('../discprobe/web/home/design.js', import.meta.url), 'utf8');
const imported = {imported:true, image_compatible:true, s:'unknown', geo:'presets/dis-a.json'};
const measured = {s:'good', geo:'results/geo-old'};
const state = {catalogue:{dvd:[imported,measured]},steps:[{id:'geo',done:true,result:measured.geo}]};
assert.equal(projectGeo(state,{media:'dvd',geo:measured.geo,item:imported}), imported.geo);
assert.equal(projectGeo(state,{media:'dvd',geo:imported.geo}), imported.geo);
assert.equal(projectGeo(state,{media:'dvd',item:{...imported,image_compatible:false}}), null);
assert.equal(projectGeo({...state,catalogue:{dvd:[measured]}},{media:'dvd',item:imported}), null);
assert.equal(projectGeo(state,{media:'dvd',item:measured}), measured.geo);
assert.match(source, /const geo = planGeo\(state\), geoPath = geo\.path;/);
assert.match(source, /args: \{ geo: geoPath, design_npy:/);
assert.match(source, /const planGeo = \(state, plan = S\) => geoChoice\(/);
const preview = readFileSync(new URL('../discprobe/web/home/preview.js', import.meta.url), 'utf8');
assert.match(preview, /imported: "Imported from DIS, converted to DP geometry \(not measured by DP\)"/);
console.log('Imported preset page geometry selection passed');
