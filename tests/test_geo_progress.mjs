import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { countdown, countdownText } from '../discprobe/web/home/kit/countdown.mjs';

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
const normalized = calibrate.replace(/\r\n/g, '\n');
const eventBody = normalized.match(/const onEvent = event => \{([\s\S]*?)\n  \};\n  try \{/)[1];
const stageSetup = normalized.match(/^const stepEta = .*;$/m)[0];
const handler = new Function('event', 'flow', 'f', 'current', 'flog', 'api', '$', 'action',
  'imageRing', 'setPlate', 'showInterior', 'updateInterior', 'paintStage', 'paintRuler', 'isCal', 'paint',
  'closeBurnStop', 'STEP_PHASE', 'sfx', 'stepWords', 'paintJob', stageSetup + eventBody);
const noop = () => {};
const flow = { realPhase: 'geo' }, current = {clock: {estimate(s) { eta = s; }, clear() { eta = null; }}};
let fraction, eta, interiorEta, ringValue, jobPaints = 0;
const jobName = {};
const reply = (event, action = 'geo') => handler(event, flow, flow, current, {log:noop, progress:noop},
  {jobProgress(p) { fraction = p; }}, () => jobName, action, {progress(p) { ringValue = p; }},
  noop, noop, (p, s) => { interiorEta = s; }, noop, noop, () => true, noop,
  noop, {geo:'geo', preset:'saving'}, {step:noop}, name => ({geo:'Geometry', burn:'Burning'})[name], () => jobPaints++);
reply({ type: 'progress', fraction: 1.05, eta_s: -12, stage: 'geo' });
assert.equal(current.p, 1);
assert.equal(fraction, 1);
assert.equal(countdownText(eta), '0:00');
assert.equal(interiorEta, 0);

// The last estimate from rotation is replaced as soon as the geometry step starts.
flow.realPhase = 'timing';
current.clock.estimate(1);
reply({type:'step', name:'geo'});
assert.equal(flow.realPhase, 'geo');
assert.equal(countdownText(eta), '5:00');
assert.equal(jobName.textContent, 'Geometry');
reply({type:'geo_point', rung:1, radius_mm:41.1, residual_deg:0.1, sigma_deg:0.2});
reply({type:'geo_point', rung:1, radius_mm:41.1, residual_deg:0.1, sigma_deg:0.2});
assert.deepEqual(flow.points,[{rung:1,r:41.1,d:0.1,s:0.2}]);
assert.equal(flow.head, 41.1);
reply({type:'log', text:' 41.1 mm: moved +0.100 deg (+/- 0.200)'});
assert.deepEqual(flow.tape,['41.1 mm: moved +0.100 deg (+/- 0.200)']);
assert.equal(flow.points.length, 1);
reply({type:'progress', fraction:.4, eta_s:292});
assert.equal(countdownText(eta), '4:52');
reply({type:'step', name:'preset'});
assert.equal(countdownText(eta), '');
flow.repairingCoverage = true;
reply({type:'step', name:'geo'});
assert.equal(countdownText(eta), '2:00');
assert.deepEqual(flow.points, []);
const beforeBurn = jobPaints;
reply({type:'burn_speed'});
assert.equal(jobName.textContent, 'Burning');
assert.equal(jobPaints, beforeBurn + 1);

// Unknown generation progress remains indeterminate; finite fractions reach the kit ring.
reply({type:'progress',stage:'image'}, 'random');
assert.equal(ringValue,null);
reply({type:'progress',fraction:.62}, 'random');
assert.equal(ringValue,.62);

// The clock keeps counting between events. Corrections change the rate one step at a time.
const nativeSet = globalThis.setTimeout, nativeClear = globalThis.clearTimeout;
const nativePerformance = globalThis.performance;
let now = 0, scheduled;
globalThis.performance = {now: () => now};
globalThis.setTimeout = (callback, delay) => (scheduled = {callback, delay});
globalThis.clearTimeout = () => { scheduled = undefined; };
const advance = () => {
  const {callback, delay} = scheduled;
  scheduled = undefined;
  now += delay;
  callback();
  return delay;
};
try {
  const values = [];
  const clock = countdown(s => values.push(countdownText(s)));
  clock.estimate(300);
  clock.estimate(292);
  advance();
  assert.equal(advance(), 1000);
  clock.estimate(20);
  advance();
  assert.equal(advance(), 850);
  clock.estimate(400);
  advance();
  assert.equal(advance(), 1150);
  clock.estimate(null);
  advance();
  assert.deepEqual(values, ['4:52', '4:51', '4:50', '4:49', '4:48', '4:47', '4:46']);
  clock.clear();
  assert.equal(scheduled, undefined);
  assert.equal(values.at(-1), '');
  clock.estimate(1);
  advance();
  advance();
  assert.deepEqual(values.slice(-2), ['0:01', '0:00']);
  assert.equal(scheduled, undefined);
  // the job went on past its estimate and reports a new one: the clock counts again instead of sitting at 0:00
  clock.estimate(370);
  assert.equal(values.at(-1), '6:10');
  advance();
  assert.equal(values.at(-1), '6:09');
  clock.estimate(0.4);
  assert.ok(scheduled, 'an estimate under a second does not restart a running clock');
} finally {
  globalThis.setTimeout = nativeSet;
  globalThis.clearTimeout = nativeClear;
  globalThis.performance = nativePerformance;
}

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
