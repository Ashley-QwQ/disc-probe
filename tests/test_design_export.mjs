import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as R from '../discprobe/web/home/design/export-rules.mjs';
import * as O from '../discprobe/web/home/design/editor-ops.mjs';

// --- geometry: a plan's batch decides; another batch's newest record is never taken silently
const ritek = {id: 'r1', mid: 'RITEKF1', name: 'RITEKF1', s: 'good', geo: 'results/geo-ritek', last: '2026-11-07'};
const verb = {id: 'v1', mid: 'MCC03RG20', name: 'Verbatim', s: 'good', geo: 'results/geo-verb', last: '2026-11-11'};
const fresh = {id: 'n1', mid: 'CMC MAG', name: 'CMC', s: 'none', geo: null};
const cat = [ritek, verb, fresh];
const newest = 'C:/ws/results/geo-verb';                 // the newest finished run is the other batch's
assert.deepEqual(R.geoChoice({item: ritek}, cat, newest), {path: ritek.geo, source: 'batch', name: 'RITEKF1'});
// a batch picked but not measured: no geometry, even though another batch has a newer one
assert.equal(R.geoChoice({item: fresh}, cat, newest).source, 'none');
assert.equal(R.geoChoice({item: fresh}, cat, newest).path, null);
// a geometry kept from before (another batch) does not override the plan's batch
assert.equal(R.geoChoice({item: ritek, geo: verb.geo}, cat, newest).path, ritek.geo);
assert.equal(R.geoChoice({item: fresh, geo: verb.geo}, cat, newest).path, null);
// no batch at all ("decide later"): the newest record, by name, so the checklist can say whose it is
const later = {kind: 'unset', name: '还没选盘', mid: '', s: 'none'};
assert.deepEqual(R.geoChoice({item: later}, cat, newest), {path: newest, source: 'latest', name: 'Verbatim', when: '2026-11-11'});
assert.equal(R.geoChoice({item: later, geo: ritek.geo}, cat, newest).source, 'saved');
assert.equal(R.geoChoice({item: later}, cat, null).source, 'none');
// imported presets keep their own rule
const dis = {imported: true, image_compatible: true, correction_required: true, geo: 'presets/x.json', name: 'DIS'};
assert.equal(R.geoChoice({item: dis}, [...cat, dis], newest).source, 'imported_corrected');
assert.equal(R.geoChoice({item: {...dis, image_compatible: false}}, [...cat, dis], newest).path, null);

// --- textures: black and white by default; the labels stay, only the texture list changes
const doc = O.migrate({version: 2, media: 'dvd', layers: [{id: 1, kind: 'image', shape: {type: 'rectangle'}, width: 20, height: 20, x: 40, y: 0}],
  materials: [{id: 'background', spec: 'B9'}, {id: 'observation_0000', spec: 'A5', period_um: .853}, {id: 'red', spec: '66', period_um: 1.1}],
  assignments: [{id: 'a', layer: 1, material: 'red'}]});
const bw = R.burnDocument(doc, 'dvd');
assert.deepEqual(bw.textures, ['B9', 'A5', 'A5']);
assert.equal(bw.mode, 'bw');
assert.deepEqual(R.burnDocument(doc, 'cd').textures, ['AA', '0D', '0D']);            // a CD burns its own pair
assert.deepEqual(R.burnDocument(doc, 'dvd', 'experimental').textures, ['B9', 'A5', '66']);
assert.equal(R.burnDocument(doc, 'cd', 'experimental').mode, 'bw');                   // no experiment on CD
// same labels either way
const g = O.grid(120);
assert.deepEqual([...O.compose(bw.doc, g)], [...O.compose(doc, g)]);
// what may come back from the core
assert.deepEqual(R.checkTextures(['B9', 'A5'], 'dvd', 'bw'), []);
assert.deepEqual(R.checkTextures(['B9', '66'], 'dvd', 'bw'), ['66']);
assert.deepEqual(R.checkTextures(['B9', '66'], 'dvd', 'experimental'), []);
assert.deepEqual(R.checkTextures(['AA', '0D'], 'cd', 'bw'), []);
// detecting colour and effect content from the composed slots
const labels = O.compose(doc, g), slots = [...new Set(labels)];
assert.deepEqual(R.experimentalContent(doc, 'dvd', slots).colours, ['66']);
const plain = {...doc, assignments: [{id: 'b', layer: 1, material: 'observation_0000'}]};
assert.equal(R.experimentalContent(plain, 'dvd', [...new Set(O.compose(plain, g))]).any, false);
const effect = {...doc, assignments: [{id: 'c', layer: 1, effect: {kind: 'flow', y1: 55, y2: 100}}]};
assert.equal(R.experimentalContent(effect, 'dvd', []).effects, 1);
assert.equal(R.experimentalContent({...effect, layers: [{...doc.layers[0], visible: false}]}, 'dvd', []).any, false);

// --- grids and sampling
assert.deepEqual(Object.keys(R.CELLS).map(Number).sort((a, b) => a - b), [5, 10, 20]);
assert.equal(R.DEFAULT_CELL_UM, 20);
for (const um of [20, 10, 5]) assert(R.COST[um].minutes > 0 && R.COST[um].gb > 0);
assert.equal(R.pictureSampling([{kind: 'image', w: 2048, width: 100}]), 100000 / 2048);
assert.equal(R.pictureSampling([{kind: 'image', w: 2048, width: 100, visible: false}]), null);

// --- the page uses these rules for what it sends and what it says
const page = fs.readFileSync(new URL('../discprobe/web/home/design.js', import.meta.url), 'utf8');
assert.match(page, /burn = burnDocument\(editor\.document\(\), S\.media, effects\);/);
assert.match(page, /checkTextures\(saved\.textures_used \?\? saved\.textures, S\.media, burn\.mode\)/);
assert.match(page, /effects: "bw",/);
assert.match(page, /plan\.geo = null;/);
console.log('design export rules: geometry choice, black-and-white textures, grids passed');
