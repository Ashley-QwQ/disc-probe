import assert from 'node:assert/strict';
import { sortPlans, planTime, DEPTHS, parallax, layerOffset, fallPosition, transitionTiming, transitionFrame, backAction, rubber, unrubber, RUBBER_R } from '../discprobe/web/home/pastworks.js';

const time = [
  { name: 'old', date: '2026-01-01' }, { name: 'unknown' },
  { name: 'new', updatedAt: Date.UTC(2026, 10, 11) }, { name: 'bad', date: 'not a date' },
  { name: 'middle', created_at: '2026-08-01' },
];
assert.deepEqual(sortPlans(time).map(p => p.name), ['new', 'middle', 'old', 'unknown', 'bad']);
assert.deepEqual(time.map(p => p.name), ['old', 'unknown', 'new', 'bad', 'middle'], 'input is not mutated');
assert.equal(planTime({ date: 'bad', createdAt: '2026-11-10' }), Date.parse('2026-11-10'));
assert.equal(planTime({ updatedAt: null }), null);
assert.equal(planTime({ updatedAt: 0 }), 0);
const session = [{ name: 'recent session' }, { name: 'earlier session' }];
assert.deepEqual(sortPlans(session), session, 'undated session works retain recentPlans order');
const names = ['竹', 'Atlas 10', '阿', 'Beta', '常', '波', 'Atlas 2', '雨', 'りんご', 'éclair'];
const sorted = sortPlans(names.map(name => ({ name })), 'name').map(p => p.name);
assert.deepEqual(sorted.slice(0, 5), ['阿', '波', '常', '雨', '竹']);
assert.deepEqual(sorted.slice(5, 9), ['Atlas 2', 'Atlas 10', 'Beta', 'éclair']);
assert.equal(sorted.at(-1), 'りんご');
const twins = [{ name: 'A', id: 2 }, { name: 'a', id: 1 }];
assert.deepEqual(sortPlans(twins, 'name'), twins, 'collation ties remain stable');

for (let depth = 0; depth < 3; depth++) {
  assert.ok(parallax(0, depth) === 0);
  assert.equal(parallax(200, depth), -200 * DEPTHS[depth].speed);
  assert.equal(parallax(-200, depth), 200 * DEPTHS[depth].speed);
  const period = 1400;
  for (const camera of [-100000, -1, 0, 1, 500, 100000]) {
    const y = layerOffset(camera, depth, period);
    assert.ok(y <= 0 && y > -period);
    assert.ok(Math.abs(layerOffset(camera + period / DEPTHS[depth].speed, depth, period) - y) < 1e-8);
  }
}
assert.ok(Math.abs(parallax(100, 0)) < Math.abs(parallax(100, 1)));
assert.ok(Math.abs(parallax(100, 1)) < Math.abs(parallax(100, 2)));
assert.ok(DEPTHS[0].size < DEPTHS[1].size && DEPTHS[1].size < DEPTHS[2].size);
assert.ok(DEPTHS[0].opacity < DEPTHS[1].opacity && DEPTHS[1].opacity < DEPTHS[2].opacity);

let last = 0;
for (let i = 0; i <= 10000; i++) {
  const p = fallPosition(i / 10000); assert.ok(p >= last && p <= 1); last = p;
}
assert.equal(fallPosition(-1), 0); assert.equal(fallPosition(2), 1);
const h = .00001, speed = u => (fallPosition(u + h) - fallPosition(u - h)) / (2 * h);
assert.ok(speed(.3) > speed(.1), 'fall accelerates');
assert.ok(speed(.9) < speed(.75), 'braking slows the fall');
assert.ok(Math.abs(speed(2 / 3 - h) - speed(2 / 3 + h)) < .001, 'velocity continuous at brake');
assert.ok(speed(0) < .0001 && speed(1) < .0001, 'starts and ends at rest');
const first = transitionTiming(0), second = transitionTiming(1);
assert.deepEqual(first, { push: 400, fall: 1000, brake: 500, total: 1900 });
assert.deepEqual(second, { push: 120, fall: 320, brake: 160, total: 600 });
assert.deepEqual(transitionTiming(200), second);
assert.equal(transitionTiming(0, true).total, 0);
for (const t of [first, second]) {
  assert.deepEqual(transitionFrame(0, t), { push: 0, travel: 0, paper: 0, opacity: 0 });
  assert.deepEqual(transitionFrame(t.total, t), { push: 1, travel: 1, paper: 1, opacity: 1 });
  assert.equal(transitionFrame(t.push, t).travel, 0);
  assert.equal(transitionFrame(t.push + t.fall, t).paper, 0);
  // Reverse traverses exactly the same states, rather than a separate approximation.
  const forwards = Array.from({ length: 101 }, (_, i) => transitionFrame(t.total * i / 100, t));
  const backwards = Array.from({ length: 101 }, (_, i) => transitionFrame(t.total * (100 - i) / 100, t));
  assert.deepEqual(backwards.reverse(), forwards);
}
assert.equal(backAction({ phase: 'entering', focused: false }), 'reverse');
assert.equal(backAction({ phase: 'entering', focused: true }), 'reverse');
assert.equal(backAction({ phase: 'exiting', focused: true }), 'finish-exit');
assert.equal(backAction({ phase: 'idle', focused: true }), 'unfocus');
assert.equal(backAction({ phase: 'idle', focused: false }), 'leave');
console.log('Past works sorting, depth, continuous fall, repeat timing and back order passed');

// elastic ends: odd, monotone, slower than linear, drag growing with the square of the distance, invertible
assert.equal(rubber(0), 0);
let prevO = 0;
for (let p = 1; p <= 900; p += 7) {
  const o = rubber(p);
  assert.ok(o > prevO && o <= p, 'monotone and sublinear');
  assert.equal(rubber(-p), -o, 'odd');
  assert.ok(Math.abs(unrubber(o) - p) < 1e-6, 'inverse');
  prevO = o;
}
const slope = (o) => 1 / (1 + (o / RUBBER_R) ** 2);
for (const o of [5, 20, 60]) {
  const p = unrubber(o), d = (rubber(p + .01) - rubber(p - .01)) / .02;
  assert.ok(Math.abs(d - slope(o)) < 1e-4, 'drag is 1 + (over/R)^2');
}
assert.ok(rubber(900) < 140, 'only a little');
