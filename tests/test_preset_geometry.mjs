import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
// Execute the actual page selector without its canvas and worker dependencies.
const source = readFileSync(new URL('../discprobe/web/home/design.js', import.meta.url), 'utf8');
const selector = source.slice(source.indexOf('export function projectGeo('), source.indexOf('// ---------------------------------------------------------------- building the page'));
const {projectGeo} = await import('data:text/javascript;base64,' + Buffer.from(selector).toString('base64'));
const imported = {imported:true, image_compatible:true, s:'unknown', geo:'presets/dis-a.json'};
const measured = {s:'good', geo:'results/geo-old'};
const state = {catalogue:{dvd:[imported,measured]},steps:[{id:'geo',done:true,result:measured.geo}]};
assert.equal(projectGeo(state,{media:'dvd',geo:measured.geo,item:imported}), imported.geo);
assert.equal(projectGeo(state,{media:'dvd',geo:imported.geo}), imported.geo);
assert.equal(projectGeo(state,{media:'dvd',item:{...imported,image_compatible:false}}), null);
assert.equal(projectGeo({...state,catalogue:{dvd:[measured]}},{media:'dvd',item:imported}), null);
assert.equal(projectGeo(state,{media:'dvd',item:measured}), measured.geo);
assert.match(source, /const geoPath = projectGeo\(state\)/);
assert.match(source, /args: \{ geo: geoPath, design_npy:/);
const preview = readFileSync(new URL('../discprobe/web/home/preview.js', import.meta.url), 'utf8');
assert.match(preview, /imported: "Imported from DIS, converted to DP geometry \(not measured by DP\)"/);
console.log('Imported preset page geometry selection passed');
