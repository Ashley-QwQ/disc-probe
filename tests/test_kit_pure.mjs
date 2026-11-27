import assert from 'node:assert/strict';
import { characterChanges } from '../discprobe/web/home/kit/flipnum.js';
import { statusDate, statusState, statusSummary } from '../discprobe/web/home/kit/statusbars.js';
import { deviceMeta, timeWords } from '../discprobe/web/home/kit/devices.js';
import { HOLD_MS, initialHold, keyboardReducer, slideProgress, slideThreshold } from '../discprobe/web/home/kit/slideconfirm.js';
import { clampProgress } from '../discprobe/web/home/kit/ringbutton.js';

const changed = (a, b) => characterChanges(a, b).filter(c => c.changed).map(({ from, to, direction }) => [from, to, direction]);
assert.deepEqual(changed('62%', '63%'), [['2', '3', 'up']]);
assert.deepEqual(changed('62%', '61%'), [['2', '1', 'down']]);
assert.deepEqual(changed('19%', '20%'), [['1', '2', 'up'], ['9', '0', 'up']]);
assert.deepEqual(changed('20%', '19%'), [['2', '1', 'down'], ['0', '9', 'down']]);
assert.deepEqual(changed('约 4 分钟', '约 3 分钟'), [['4', '3', 'down']]);
assert.deepEqual(changed('01 / 08', '02 / 07'), [['1', '2', 'up'], ['8', '7', 'down']]);
assert.deepEqual(changed('62%', '62%'), []);
assert.equal(characterChanges('9%', '10%').at(-1).previousIndex, 1);
assert.equal(characterChanges('99%', '100%').at(-1).changed, false);
assert.equal(characterChanges('100%', '99%').at(-1).previousIndex, 3);
assert.equal(characterChanges('约 9 分钟', '约 10 分钟').at(-1).changed, false);
assert.deepEqual(characterChanges('💿 1', '💿 2').map(c => c.to), ['💿', ' ', '2']);
assert.deepEqual(changed('90071992547409930', '90071992547409929').map(c => c[2]), ['down', 'down']);
assert.deepEqual(characterChanges('123', ''), []);
assert.equal(characterChanges('', '62%').length, 3);

const items = Array.from({ length: 12 }, (_, i) => ({ state: i < 2 ? 'needs' : 'ok' }));
assert.equal(statusSummary(items), '12 次，2 次要看');
assert.equal(statusSummary(items, 'en'), '12 events, 2 need attention');
assert.equal(statusSummary([{ state: 'needs' }], 'en'), '1 event, 1 needs attention');
assert.equal(statusSummary([]), '0 次，0 次要看');
assert.equal(statusSummary([{ state: 'other' }]), '1 次，0 次要看');
assert.equal(statusState('bad'), 'unknown');
assert.equal(statusDate(null), '日期未知');
assert.equal(statusDate('bad', 'en'), 'Date unknown');
assert.match(statusDate('2026-11-11', 'en'), /Nov 11, 2026/);
assert.match(statusDate('2026-11-11'), /2026.*11.*11/);

const now = Date.UTC(2026, 10, 11, 12);
assert.equal(timeWords(now, now), '刚连上');
assert.equal(timeWords(now - 59999, now, 'en'), 'Just connected');
assert.equal(timeWords(now - 60000, now, 'en'), 'Connected for 1 minute');
assert.equal(timeWords(now - 180000, now), '已连上 3 分钟');
assert.equal(timeWords(now - 3600000, now, 'en'), 'Connected for 1 hour');
assert.equal(timeWords(now - 7200000, now), '已连上 2 小时');
assert.equal(timeWords(now - 86400000, now), '已连上 1 天');
assert.equal(timeWords(new Date(now - 2 * 86400000).toISOString(), now, 'en'), 'Connected for 2 days');
assert.equal(timeWords(now + 1000, now), '刚连上');
for (const since of [null, undefined, '', 'bad']) assert.equal(timeWords(since, now), '连接时间未知');
assert.equal(deviceMeta({ since: now - 180000, sent: 2 }, now), '已连上 3 分钟 · 发来 2 张');
assert.equal(deviceMeta({ since: now, sent: 1 }, now, 'en'), 'Just connected · Sent 1 photo');
assert.equal(deviceMeta({ since: now, sent: -2 }, now, 'en'), 'Just connected · Sent 0 photos');
assert.equal(deviceMeta({ since: now }, now, 'en'), 'Just connected · Photo count unknown');

assert.equal(HOLD_MS, 1000);
assert.equal(slideProgress(-5, 100), 0);
assert.equal(slideProgress(50, 100), .5);
assert.equal(slideProgress(200, 100), 1);
assert.equal(slideThreshold(99.99, 100), false);
assert.equal(slideThreshold(100, 100), true);
for (const travel of [0, -1, NaN, Infinity]) assert.equal(slideThreshold(100, travel), false);
assert.equal(slideThreshold(NaN, 100), false);
for (const key of ['Enter', ' ', 'ArrowLeft', 'Home']) {
  assert.deepEqual(keyboardReducer(initialHold(), { type: 'down', key, now: 0 }), initialHold());
}
for (const key of ['ArrowRight', 'End']) {
  let state = keyboardReducer(initialHold(), { type: 'down', key, now: 50 });
  state = keyboardReducer(state, { type: 'down', key, repeat: true, now: 800 });
  assert.equal(state.started, 50);
  state = keyboardReducer(state, { type: 'tick', now: 1049 });
  assert.equal(state.phase, 'holding');
  assert.equal(state.progress, .999);
  assert.deepEqual(keyboardReducer(state, { type: 'up', key }), initialHold());
  state = keyboardReducer(state, { type: 'tick', now: 1050 });
  assert.equal(state.phase, 'confirmed');
  assert.equal(keyboardReducer(state, { type: 'down', key, now: 2000 }).phase, 'confirmed');
  assert.equal(keyboardReducer(state, { type: 'reset' }).phase, 'idle');
}
let state = keyboardReducer(initialHold(), { type: 'down', key: 'End', now: 0 });
assert.deepEqual(keyboardReducer(state, { type: 'cancel' }), initialHold());
assert.deepEqual(keyboardReducer(state, { type: 'down', key: 'Escape' }), initialHold());
state = keyboardReducer(state, { type: 'disable' });
assert.equal(keyboardReducer(state, { type: 'tick', now: 10000 }).phase, 'disabled');
assert.equal(keyboardReducer(state, { type: 'down', key: 'End', now: 10000 }).phase, 'disabled');
assert.equal(keyboardReducer(initialHold(), { type: 'down', key: 'End', now: NaN }).phase, 'idle');
assert.equal(keyboardReducer(initialHold(), { type: 'down', key: 'End', repeat: true, now: 0 }).phase, 'idle');

for (const [input, expected] of [[-.3, 0], [0, 0], [.62, .62], [1, 1], [1.3, 1], [Infinity, 1], [-Infinity, 0], [NaN, 0], [undefined, 0], ['.5', 0], [null, null]]) {
  assert.equal(clampProgress(input), expected);
}
console.log('UI kit pure helpers passed');
