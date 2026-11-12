import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// Run the actual page function with a fake job, without loading a page or a drive.
const source = await readFile(new URL('../discprobe/web/home/calibrate.js', import.meta.url), 'utf8');
const body = source.slice(source.indexOf('async function realCalibrate('), source.indexOf('\nconst stopText ='));
for (const failures of [undefined, [], [{radius_mm:43.2}, {radius_mm:45}, {radius_mm:44}, {radius_mm:52}, {}, {radius_mm:null}, {radius_mm:NaN}]]) {
  const flow = {burnCheck:{verification:{failures}}, detected:{mid:'MID'}, blankSectors:2298496};
  const calls = [];
  const run = new Function('flow', 'realJob', 'finishCalibrate', 'stopText', `${body}; return realCalibrate;`)(
    flow, async (...args) => {calls.push(args); return {ok:true};}, () => {}, x => x);
  await run({iso:'iso/test.iso', speed:'keep'}, {burn_token:'token'});
  const [action, args, extra] = calls[0];
  assert.equal(action, 'calibrate');
  assert.equal(args.speed, "4x");
  assert.deepEqual(args.avoid_mm, failures?.length ? ['41.2-47', '50-54'] : []);
  assert.equal(args.iso, 'iso/test.iso');
  assert.equal(args.mid, 'MID');
  assert.equal(args.sectors, 2298496);
  assert.deepEqual(extra, {burn_token:'token'});
  assert.equal(flow.burnCheck, null);
}
console.log('Fixed calibration speed and merged avoided-radius arguments passed');
