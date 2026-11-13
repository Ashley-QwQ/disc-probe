// The start guide's words and rules, without a browser or a drive: what is said before a first disc, how
// progress is read from what is on disk (never from what the page believes), and what is said when no
// picture shows.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {introCards, disShortcut, lightScenes, journey, troubleChecks, troubleNote, discGoal, discRoute, retakeNote, stepAdvice, adviceHTML, afterBurn, calibrationBudget} from '../discprobe/web/home/guidance.mjs';

const both = (p) => [p.zh, p.en];
const step = (id, done, extra = {}) => ({id, done, ...extra});
const ready = [step('packages', true), step('drive', true, {detail: 'H:'})];
const rows = (g) => Object.fromEntries(g.rows.map(r => [r.id, r]));

// 1. the four things, in order, both languages
assert.deepEqual(introCards.map(c => c.id), ['how', 'need', 'discs', 'retake']);
for (const c of introCards) for (const t of both(c.title).concat(both(c.body))) assert.ok(t.length > 3, c.id);
assert.match(introCards[0].body.zh, /衍射/); assert.match(introCards[0].body.en, /diffraction/);
assert.match(introCards[2].body.zh, /第 3 张.*第 4 张.*不是保证/); assert.match(introCards[2].body.en, /disc 3.*disc 4.*not a promise/);
assert.match(retakeNote.zh, /重拍.*不用重刻/); assert.match(retakeNote.en, /retaken, not re-burned/);
assert.equal(discRoute.length, 4);
assert.match(disShortcut.button.zh, /^导入/); assert.match(disShortcut.button.en, /^Import/);
assert.match(disShortcut.body.zh, /不是 disc-probe 自己测的/);          // imported geometry is not DP's own measurement
assert.equal(lightScenes.length, 4);

// 2. no stale or contradictory disc counts anywhere in the page files this guide covers
//    ("至少两张不同角度" is the two-photo rule for photo L, not a disc count)
const home = new URL('../discprobe/web/home/', import.meta.url);
for (const f of ['guidance.mjs', 'newplan.js', 'preview.js', 'calibrate.js', 'guide.js']) {
  const text = readFileSync(new URL(f, home), 'utf8');
  assert.doesNotMatch(text, /至少 ?[23] 张同批|至少两张(?!不同角度)|at least [23] blanks|at least two blanks|maybe three|可能三张|可能 3 张/, f);
  assert.doesNotMatch(text, /网页拍照标定还没做好|Web photo calibration is not ready|CD photo calibration is not ready/, f);
}
for (const media of ['dvd', 'cd']) for (const l of ['zh', 'en']) {
  const b = calibrationBudget(media);
  assert.ok(b.items[0] === discGoal && b.details[l].includes(discRoute[3][l]), media + l);
}

// 3. progress comes from disk results; what the program cannot see is "unknown", never "done"
const g0 = journey({media: 'dvd', steps: [...ready, step('random_disc', false, {detail: 'not made yet'}), step('timing', false), step('geo', false), step('photo_l', false), step('picture_iso', false), step('burn', false)]}, {withIntro: false});
assert.deepEqual(g0.rows.map(r => r.id), ['ready', 'disc1', 'timing', 'geo', 'check', 'picture', 'burn']);
assert.equal(g0.current, 'disc1'); assert.equal(rows(g0).disc1.now, true);
assert.equal(g0.milestone.reached, false);
for (const id of ['check', 'burn']) assert.equal(rows(g0)[id].status, 'unknown', id);             // only the person can tell
assert.equal(rows(g0).burn.human, true);
// a measurement file that exists is not a disc that was burned
const g1 = journey({media: 'dvd', steps: [...ready, step('random_disc', false, {detail: 'iso/random.iso written; burn it'})]}, {withIntro: false});
assert.equal(rows(g1).disc1.status, 'unknown'); assert.match(rows(g1).disc1.unknown.zh, /还不知道/);
// a result that cannot be used is a problem with the same words the calibration page uses, not a quiet "todo"
const g2 = journey({media: 'dvd', steps: [...ready, step('random_disc', true), step('timing', false, {verdict: 'too_noisy'}), step('geo', false)]}, {withIntro: false});
assert.equal(rows(g2).timing.status, 'problem'); assert.equal(g2.current, 'timing');
assert.match(rows(g2).timing.unknown.zh, /保留这张测量盘/);
// everything measured and a picture file made: ready to burn the first picture, and nothing claims it was burned or seen
const done = [...ready, step('random_disc', true), step('timing', true, {verdict: 'good'}), step('geo', true, {verdict: 'good'}), step('picture_iso', true, {detail: 'iso/picture.iso'}), step('burn', false)];
const g3 = journey({media: 'dvd', steps: done}, {withIntro: false});
assert.equal(g3.milestone.reached, true); assert.match(g3.milestone.words.zh, /可以刻第一张成品/);
assert.equal(rows(g3).burn.status, 'unknown'); assert.equal(g3.current, 'burn');
assert.ok(!g3.rows.some(r => r.status === 'done' && r.human));
// a CD is not ready for a clean first picture without its constant: the words say so, and the check row stays in the way
const g4 = journey({media: 'cd', steps: done}, {withIntro: false});
assert.match(g4.milestone.words.zh, /沿轨常数还没确认/); assert.equal(g4.current, 'check');
// no state at all (the service did not answer): nothing is ticked
const g5 = journey({}, {withIntro: false});
assert.equal(g5.offline, true); assert.ok(g5.rows.every(r => r.status === 'unknown')); assert.equal(g5.milestone.reached, false);
// the intro row is only a reminder and says so
const g6 = journey({media: 'dvd', steps: ready}, {intro: true});
assert.equal(g6.rows[0].id, 'intro'); assert.equal(g6.rows[0].status, 'done'); assert.match(g6.rows[0].known.zh, /只是个提醒/);
// every row in both languages, with a next action when it is not done
for (const g of [g0, g1, g2, g3, g4, g5, g6]) for (const r of g.rows) {
  for (const t of both(r.title)) assert.ok(t.length > 1);
  if (r.status !== 'done') assert.ok(r.next?.label?.zh && r.next?.label?.en, r.id);
}

// 4. when nothing shows: the light, then the burn report, then the geometry; another disc only with its reason
assert.deepEqual(troubleChecks.map(c => c.id), ['light', 'burn', 'geo']);
assert.equal(troubleChecks[0].reburn, null);
for (const c of troubleChecks.slice(1)) for (const t of both(c.reburn)) assert.match(t, /原因|Why/);
assert.match(troubleNote.zh, /不会自动让你再刻一张/); assert.match(troubleNote.en, /never asks you to burn again on its own/);
assert.match(afterBurn[1].zh, /先别再刻/); assert.match(afterBurn[1].en, /do not burn again yet/);
assert.match(afterBurn[1].zh, /只有光照和刻录报告都没问题/); assert.match(afterBurn[1].en, /Only if the light and the burn report are fine/);

// 5. every calibration phase says what is not known yet and what to do next; a wait with no measure says so
for (const ph of ['inspect', 'prepare', 'random', 'burn', 'burning', 'checking', 'timing', 'geo', 'saving', 'review', 'saved']) {
  const a = stepAdvice(ph); assert.ok(a?.unknown?.zh && a.next?.en, ph);
  assert.match(adviceHTML(ph, 'zh'), /还不知道：.*下一步：/s); assert.match(adviceHTML(ph, 'en'), /Not known yet: .*Next: /s);
}
assert.match(stepAdvice('random').unknown.zh, /没有进度可量/);
assert.match(stepAdvice('review', {good: false}).next.zh, /不需要再刻一张盘/);
assert.equal(stepAdvice('photo'), null);
assert.match(adviceHTML('timing', 'en'), /^<div class="cal-guide">/);

// 6. the sheet does not depend on WebGL, motion or the page being in front, and its buttons are verb + object
const guide = readFileSync(new URL('guide.js', home), 'utf8');
assert.ok(!/webgl|getContext|requestAnimationFrame/i.test(guide), 'no WebGL, canvas or frame loop');
assert.match(guide, /document\.hidden/); assert.match(guide, /motionOn\(\)/);
for (const label of ['看上一幕', '看下一幕', '重看动画', '跳过动画', '关闭引导', '重新读取进度', '看新手引导']) assert.ok(guide.includes(label), label);
// 7. a wait that has no measure of its own does not fill over a guessed time (the disc check)
const calibrate = readFileSync(new URL('calibrate.js', home), 'utf8');
assert.ok(!/CHECK_MS|checkTimer/.test(calibrate), 'the disc check bar is not a timer');
assert.match(calibrate, /读取中/);
console.log('Start guide tests passed');
