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
// The server's saved speed history drives both copy and execution, including after reload.
for (const media of ['cd','dvd','bd']) {
  const previous = {timing:{verdict:'too_noisy',measurement:{rotation:'CLV',speed_advice:{media,next_speed:'7056',exhausted:false,all_clv:false}}}};
  assert.match(measurementRecovery(previous).en, /untried 7056/);
  const calls=[];
  await remeasure(async (action,args)=>{calls.push({action,args});return {verdict:'too_noisy',measurement:{rotation:'CLV'}};},previous);
  assert.deepEqual(calls,[{action:'timing',args:{speed:'7056'}}]);
  assert.match(recoveryCommands(previous,{drive:'E:',media,sectors:359849}),/timing.*--speed 7056/);
  Object.assign(previous.timing.measurement.speed_advice,{next_speed:null,exhausted:true,all_clv:true});
  assert.equal(recoveryAction(previous).id,'drive');
  assert.match(measurementRecovery(previous).en,/every speed tried/);
  assert.match(measurementRecovery(previous).zh,/恒定线速度/);
  await remeasure(async ()=>{throw new Error('must not repeat an exhausted speed');},previous);
  const commands=recoveryCommands(previous,{drive:'E:',media,sectors:359849});
  assert.doesNotMatch(commands,/ timing |SPEED|null|undefined/);
  if (media === 'bd') assert.match(commands,/geo.*--media bd.*--bd-zones 25/);
}
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
const variable = {geo:{path:'results/geo-test',verdict:'good',measurement:{
  completion_status:'target_reached',correction:'correction.json',span_mm:[24.5,57.9]}}};
assert.match(measurementRecovery(variable).zh, /轨距.*自动.*修正/);
assert.match(measurementRecovery(variable).en, /automatically/);
assert.match(recoveryCommands(variable,{drive:'SIM',media:'dvd',sectors:2295104}), /--correction.*correction.json/);
const partial = {geo:{verdict:'stopped_early',measurement:{completion_status:'candidates_exhausted',
  coverage:{measured_intervals_mm:[[40.5,44.6]]}}}};
assert.match(measurementRecovery(partial).zh, /40.5.*44.6.*外推/);
assert.equal(recoveryAction(partial).id,'measure');
const unsteady = stopReason("the drive's speed is not steady (63.50 ms a turn at 26 mm, 40.10 ms at 56 mm): the two periods differ and are not a whole number of turns apart");
assert.equal(unsteady.zh, '光驱在内圈和外圈测到的每圈时间对不上，也不是整圈的倍数，说明这次测量时转速在变。可以再测一次；如果每次都这样，这台光驱这次没法用来测几何。');
assert.ok(!/难读|避开/.test(unsteady.zh), 'no guessed cause');
assert.equal(unsteady.en, 'The time per turn near the centre and near the edge does not match, and is not a whole multiple either, so the drive was changing speed during this run. Measure again; if it happens every time, this drive cannot measure the geometry for now.');
for (const r of ['the burn did not finish','no disc is ready in the drive','cancelled during geo','the preset was not written'])
  for (const lang of ['zh','en']) assert.ok(!/[a-z_]{4,} [a-z]{3,} [a-z]{3,}/.test(stopReason(r)[lang]) || lang === 'en', r);
console.log('Bilingual recovery, budget and failed-job tests passed');
