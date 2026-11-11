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
                            'setPlate', 'showInterior', 'updateInterior', 'paintStage', 'paintRuler', 'isCal', 'paint', eventBody);
const flow = { realPhase: 'geo' }, current = {}, jobTime = {};
let fraction, interiorEta;
handler({ type: 'progress', fraction: 1.05, eta_s: -12, stage: 'geo' },
        flow, flow, current, { progress() {} }, { jobProgress(p) { fraction = p; } },
        () => jobTime, () => ({ leftSec: s => String(s) }), 'geo', () => {}, () => {},
        (p, eta) => { interiorEta = eta; }, () => {}, () => {}, () => false, () => {});
assert.equal(current.p, 1);
assert.equal(fraction, 1);
assert.equal(jobTime.textContent, '0');
assert.equal(interiorEta, 0);

console.log('Web progress bounds passed');
