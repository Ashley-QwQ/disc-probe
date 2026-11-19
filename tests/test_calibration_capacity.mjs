import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const source = readFileSync(new URL('../discprobe/web/home/calibrate.js', import.meta.url), 'utf8');
const section = (start, end) => {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + 1);
  assert.ok(first >= 0 && last > first);
  return source.slice(first, last);
};
const written = {present: true, media: 'dvd', mid: 'TEST', blank: false, sectors: 2295104};
const blank = {...written, blank: true, sectors: 2297888, capacity_sectors: 2297888};

function calibration(phase, reports = []) {
  const flow = {item: {row: 'dvd'}, detected: written, measureConfirmed: true, realPhase: phase};
  const measured = [];
  const check = runInNewContext(
    section('const needsBlankCapacity', 'function realError(') +
    section('async function inspectDisc(', '// The rest is the core') +
    '\nrealNext;',
    {
      flow, api: {selectedDrive: () => 'X:', lang: () => 'en'}, paint() {}, interruptedBurn() {}, shortDiscWords() {},
      liveText: (_, en) => en,
      realError: error => { flow.error = error.message; },
      realJob: async action => {
        assert.equal(action, 'info');
        assert.ok(reports.length, 'an unexpected disc check');
        return {disc: reports.shift()};
      },
      realCalibrate: ({sectors}) => measured.push(sectors ?? flow.blankSectors),
    },
  );
  return {flow, measured, check};
}

const manual = calibration('prepare');
for (const value of ['', '-1', '1.5', '25000001']) {
  manual.flow.manualSectors = value;
  await manual.check();
}
assert.deepEqual(manual.measured, [], 'readable length is not automatically used as blank capacity');
manual.flow.manualSectors = '2297888';
await manual.check();
assert.deepEqual(manual.measured, [2297888]);

const swap = calibration('capacityBlank', [written, {...blank, mid: 'OTHER'}, blank, blank, written]);
await swap.check();
assert.match(swap.flow.error, /Insert a blank/);
await swap.check();
assert.match(swap.flow.error, /maker code changed/);
assert.equal(swap.flow.blankSectors, undefined);
await swap.check();
assert.equal(swap.flow.blankSectors, 2297888);
assert.equal(swap.flow.realPhase, 'capacityWritten');
await swap.check();
assert.match(swap.flow.error, /measurement disc back/);
assert.deepEqual(swap.measured, []);
await swap.check();
assert.equal(swap.flow.realPhase, 'prepare');
await swap.check();
assert.deepEqual(swap.measured, [2297888]);

const catalogue = calibration('prepare');
catalogue.flow.catalogueSectors = 2297888;
await catalogue.check();
assert.deepEqual(catalogue.measured, [undefined], 'the core still chooses its catalogue fallback');
console.log('calibration capacity paths passed');
