import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../discprobe/web/home/core-render.js', import.meta.url), 'utf8');
const { progressLine } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
globalThis.document = { createElement: () => ({ style: {}, textContent: '' }) };
const line = { replaceChildren(...parts) { this.text = parts.map(p => p.textContent).join(''); } };
const progress = progressLine(line, { reduce: () => true });
progress.update({ fraction: 1.05, stage: 'check points', eta_s: -12 });
assert.match(line.text, /100%/);
assert.doesNotMatch(line.text, /105%|-/);
progress.update({ fraction: -0.05, eta_s: -12 });
assert.match(line.text, /  0%/);
progress.stop();

// Exercise the actual footer method without booting the scene.
const html = readFileSync(new URL('../discprobe/web/home/index.html', import.meta.url), 'utf8');
const footerBody = html.match(/jobProgress\(p, media = "dvd"\) \{([\s\S]*?)\n    \},/)[1];
const bar = { dataset: {}, style: { setProperty(k, v) { this[k] = v; } }, classList: { remove() {}, add() {} } };
globalThis.document.querySelector = () => bar;
const footer = new Function('p', 'media', footerBody);
footer(1.05, 'dvd');
assert.equal(bar.style['--p'], '1.0000');
assert.equal(bar.dataset.pct, '100');
footer(-0.05, 'dvd');
assert.equal(bar.style['--p'], '0.0000');
assert.equal(bar.dataset.pct, '0');

// Replay an out-of-range event through calibrate's real job handler.
const calibrate = readFileSync(new URL('../discprobe/web/home/calibrate.js', import.meta.url), 'utf8');
const eventBody = calibrate.replace(/\r\n/g, '\n').match(/const onEvent = event => \{([\s\S]*?)\n  \};\n  try \{/)[1];
const handler = new Function('event', 'flow', 'f', 'current', 'flog', 'api', '$', 'T', 'action',
                            'imageRing', 'setPlate', 'showInterior', 'updateInterior', 'paintStage', 'paintRuler', 'isCal', 'paint', eventBody);
const flow = { realPhase: 'geo' }, current = {}, jobTime = {};
let fraction, interiorEta;
handler({ type: 'progress', fraction: 1.05, eta_s: -12, stage: 'geo' },
        flow, flow, current, { progress() {} }, { jobProgress(p) { fraction = p; } },
        () => jobTime, () => ({ leftSec: s => String(s) }), 'geo', null, () => {}, () => {},
        (p, eta) => { interiorEta = eta; }, () => {}, () => {}, () => false, () => {});
assert.equal(current.p, 1);
assert.equal(fraction, 1);
assert.equal(jobTime.textContent, '0');
assert.equal(interiorEta, 0);

// Unknown generation progress remains indeterminate; finite fractions reach the kit ring.
let ringValue;
handler({type:'progress',stage:'image'}, flow, flow, current, {progress(){}}, {jobProgress(){}},
        () => jobTime, () => ({leftSec:s=>String(s)}), 'random', {progress:p=>{ringValue=p;}},
        () => {}, () => {}, () => {}, () => {}, () => {}, () => true, () => {});
assert.equal(ringValue,null);
handler({type:'progress',fraction:.62}, flow, flow, current, {progress(){}}, {jobProgress(){}},
        () => jobTime, () => ({leftSec:s=>String(s)}), 'random', {progress:p=>{ringValue=p;}},
        () => {}, () => {}, () => {}, () => {}, () => {}, () => true, () => {});
assert.equal(ringValue,.62);

// Preview's actual shared Next renderer forwards unknown, finite and complete states.
const preview = readFileSync(new URL('../discprobe/web/home/preview.js',import.meta.url),'utf8');
const previewNext = preview.match(/function paintNext\(\) \{([\s\S]*?)\n\}/)[1];
const calls=[];
const paintPreview=new Function('state','makeRing','ringButton','T','nextStep','$','api','src','ctx',previewNext);
const meter={progress:p=>calls.push(p),done:()=>calls.push('done'),reset:()=>calls.push('reset')};
for(const state of [{phase:'making',fraction:null},{phase:'making',fraction:.62},{phase:'ready'}]) {
  paintPreview(state,meter,()=>meter,()=>({making2:()=>'',next:''}),()=>null,()=>({}),{nextWhy(){}},true,{});
}
assert.deepEqual(calls,[null,.62,'done']);

console.log('Web progress bounds passed');
