import assert from 'node:assert/strict';
import {measurementRecovery, calibrationBudget, cdPhoto, afterBurn, budgetHTML, recoveryAction, recoveryCommands, remeasure, stopReason} from '../discprobe/web/home/guidance.mjs';
for (const lang of ['zh','en']) {
  const verdicts = ['good','usable','too_noisy','drive_changed','narrow_span','stopped_early','unknown'];
  for (const verdict of verdicts) {
    const result = {geo:{path:'results/test',verdict,measurement:{span_mm:[28,48]}}};
    const body = measurementRecovery(result)[lang];
    assert.ok(body.length > 8);
    assert.doesNotMatch(body, /--|timing|geo|disexport/);
    assert.equal(recoveryAction(result).id, ({good:'save',usable:'save'})[verdict] || 'measure');
  }
  assert.match(budgetHTML('cd',lang), /<ul>.*3/s);
  assert.match(budgetHTML('dvd',lang), /<ul>.*2/s);
  assert.match(budgetHTML('dvd',lang), /<details><summary>/);
  assert.doesNotMatch(budgetHTML('dvd',lang), /<details open/);
  assert.match(cdPhoto[lang], /DIS|DiscImageStudio/);
  assert.equal(afterBurn.length,3);
}
for (const span of [undefined, [48,28], [0,48], [28,59], [28,NaN]]) {
  assert.equal(recoveryAction({geo:{verdict:'narrow_span',path:'x',measurement:{span_mm:span}}}).id,'measure');
}
assert.equal(recoveryAction({geo:{verdict:'narrow_span',path:'x',measurement:{span_mm:[28,48]}}}).id,'measure');
assert.equal(recoveryAction({geo:{measurement:{stopped:'medium error'}}}).id,'blank');
assert.equal(recoveryAction({timing:{verdict:'good',measurement:{rotation:'CLV'}}}).id,'measure');
assert.equal(recoveryAction({geo:{verdict:'future_verdict'}}).id,'measure');
for (const rotation of ['CAV','CLV','unknown']) {
  const calls=[];
  await remeasure(async (action,args)=>{calls.push({action,args});return {verdict:'good',measurement:{rotation}};});
  assert.deepEqual(calls, rotation === 'CAV' ? [{action:'timing',args:{}},{action:'geo',args:{speed:'keep'}}] : [{action:'timing',args:{}}]);
}
for (const verdict of ['unknown','too_noisy','stopped_early']) {
  const calls=[];
  await remeasure(async action=>{calls.push(action);return {verdict,measurement:{rotation:'CAV'}};});
  assert.deepEqual(calls,['timing']);
}
await assert.rejects(remeasure(async()=>{throw new Error('cancelled');}),/cancelled/);
assert.match(recoveryCommands({geo:{verdict:'narrow_span',path:'results/test',measurement:{span_mm:[28,48]}}},{drive:'H:',media:'cd',sectors:300000}), /--r-min START --r-max END/);
// A failed job must still carry its saved result to the calibration page.
globalThis.location = {search:''};
globalThis.EventSource = class {addEventListener(){} close(){}};
globalThis.fetch = async () => ({ok:true,json:async()=>({events:[],exit:1,result:{ok:false,timing:{verdict:'too_noisy'}}})});
const source = await (await import('node:fs/promises')).readFile(new URL('../discprobe/web/home/api.js',import.meta.url),'utf8');
const api = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
await assert.rejects(api.follow('test'), error => error.result?.timing.verdict === 'too_noisy');
// calibrate's stop reasons in words: a burn that wrote is never offered as reusable, one that did not is
assert.match(stopReason('the burn did not finish', {burnStarted:true}).zh, /不能再用/);
assert.match(stopReason('the burn did not finish', {burnStarted:false}).en, /untouched/);
assert.doesNotMatch(stopReason('the burn did not finish', {burnStarted:false}).zh, /不能再用/);
assert.match(stopReason('no disc is ready in the drive').zh, /没有准备好的盘/);
assert.match(stopReason("the disc's maker code is ABC, not RITEKF1").en, /ABC.*RITEKF1/);
assert.match(stopReason('the disc is a cd disc, not dvd').zh, /CD.*DVD/);
assert.match(stopReason('the timing measurement was not usable (too_noisy)').zh, /转速检查没通过/);
assert.equal(stopReason('something new').en, 'something new');
const unsteady = stopReason("the drive's speed is not steady (63.50 ms a turn at 26 mm, 40.10 ms at 56 mm): the two periods differ and are not a whole number of turns apart");
assert.equal(unsteady.zh, '光驱在内圈和外圈测到的每圈时间对不上，也不是整圈的倍数，说明这次测量时转速在变。可以再测一次；如果每次都这样，这台光驱这次没法用来测几何。');
assert.ok(!/难读|避开/.test(unsteady.zh), 'no guessed cause');
assert.equal(unsteady.en, 'The time per turn near the centre and near the edge does not match, and is not a whole multiple either, so the drive was changing speed during this run. Measure again; if it happens every time, this drive cannot measure the geometry for now.');
for (const r of ['the burn did not finish','no disc is ready in the drive','cancelled during geo','the preset was not written'])
  for (const lang of ['zh','en']) assert.ok(!/[a-z_]{4,} [a-z]{3,} [a-z]{3,}/.test(stopReason(r)[lang]) || lang === 'en', r);
console.log('Bilingual recovery, budget and failed-job tests passed');
