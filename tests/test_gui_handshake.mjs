import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compatibility, compareAPI, handshake, hideOptional, showSheet} from '../discprobe/web/home/handshake.mjs';
const manifest = JSON.parse(readFileSync(new URL('../discprobe/web/gui.json', import.meta.url)));
const core = {api_version:'1.5', capabilities:[...manifest.required_capabilities, ...manifest.optional_capabilities]};

test('current socket matches; old and new majors name the side to update', () => {
  assert.equal(compatibility(manifest,core).update,null);
  assert.equal(compareAPI('0.9',manifest.required_api),'core');
  assert.equal(compareAPI('2.0',manifest.required_api),'gui');
  assert.equal(compareAPI('1.12',manifest.required_api),null);
  assert.throws(() => compareAPI('1.0','^1'));
  assert.throws(() => compareAPI('1.0.1','>=1 <2'));
});
test('missing required capability stops startup; optional capability does not', () => {
  const result = compatibility(manifest,{...core,capabilities:core.capabilities.filter(c => c !== 'geo')});
  assert.equal(result.update,'core'); assert.deepEqual(result.missing,['geo']);
  const optional = compatibility(manifest,{...core,capabilities:manifest.required_capabilities});
  assert.equal(optional.update,null); assert.deepEqual(optional.optional,manifest.optional_capabilities);
  const withoutWorks = compatibility(manifest,{...core,capabilities:core.capabilities.filter(c => c !== 'works')});
  assert.equal(withoutWorks.update,null); assert.deepEqual(withoutWorks.optional,['works']);
});
for (const capability of ['geo-coverage','photo-manual-alignment','checkburn','burn-preflight']) {
  test(`an older core can lack ${capability}`, () => {
    assert.ok(manifest.optional_capabilities.includes(capability));
    const oldCore = compatibility(manifest,{api_version:'1.1',capabilities:core.capabilities.filter(c => c !== capability)});
    assert.equal(oldCore.update,null); assert.deepEqual(oldCore.optional,[capability]);
  });
}
for (const [capability, oldVersion] of [
  ['library-management', '1.3'], ['library-batch-details', '1.4'], ['grid-templates', '1.4'],
]) {
  test(`an older core can lack only ${capability}`, async () => {
    assert.ok(manifest.optional_capabilities.includes(capability));
    assert.deepEqual(compatibility(manifest, core).optional, []);
    const oldCore = {api_version:oldVersion, capabilities:core.capabilities.filter(c => c !== capability)};
    const result = compatibility(manifest, oldCore);
    assert.equal(result.update, null);
    assert.deepEqual(result.optional, [capability]);
    const doc = documentStub();
    doc.entries.push({dataset:{capability}});
    await handshake(doc, async path => ({ok:true,json:async()=>path==='/gui.json'?manifest:oldCore}),
      {protocol:'http:',search:''});
    assert.equal(doc.documentElement.dataset.handshake, 'ready');
    assert.equal(doc.entries.at(-1).hidden, true);
    assert.equal(doc.entries[0].hidden, undefined);
  });
}
function documentStub(lang='en') {
  const entries = [{dataset:{capability:'templates'}},{dataset:{capability:'geo'}}];
  return {documentElement:{dataset:{lang}}, entries,
    createElement:tag=>({tag,children:[],setAttribute(){},append(...items){this.children.push(...items);}}),
    head:{append(style){this.style=style;}}, querySelectorAll:()=>entries,
    body:{replaceChildren(sheet){this.sheet=sheet;}}};
}
test('four-part public core version completes the GUI handshake', async () => {
  const doc=documentStub();
  const publicCore={...core,core_version:'1.0.0.0-alpha'};
  const calls=[];
  const fetcher=async path=>{
    calls.push(path);
    return {ok:true,json:async()=>path==='/gui.json'?manifest:publicCore};
  };
  await handshake(doc,fetcher,{protocol:'http:',search:''});
  assert.equal(doc.documentElement.dataset.handshake,'ready');
  assert.deepEqual(calls.sort(),['/api/version','/gui.json']);
  assert.equal(compatibility(manifest,publicCore).update,null);
  assert.throws(()=>compareAPI(publicCore.core_version,manifest.required_api));
});
test('optional entry is hidden and CSS covers entries mounted later', () => {
  const doc=documentStub(); hideOptional(doc,['templates']);
  assert.equal(doc.entries[0].hidden,true); assert.equal(doc.entries[1].hidden,undefined);
  assert.match(doc.head.style.textContent,/data-capability="templates"/);
  const source=readFileSync(new URL('../discprobe/web/home/design.js',import.meta.url),'utf8');
  assert.match(source,/data-capability="templates"/);
});
test('one translated sheet replaces the workflow, without technical errors', () => {
  for (const lang of ['en','zh']) {
    const doc=documentStub(lang); showSheet(doc,'gui');
    assert.equal(doc.documentElement.dataset.handshake,'failed');
    assert.equal(doc.body.sheet.id,'gui-compatibility');
    assert.match(doc.body.sheet.children[1].textContent,lang==='zh'?/更新 GUI 包/:/Update the GUI pack/);
  }
});

test('transient connection failure retries and restores the original page only after negotiation', async () => {
  const doc = documentStub('zh'), original = {tag:'workflow'};
  doc.body.childNodes = [original];
  doc.body.replaceChildren = (...nodes) => {doc.body.childNodes = nodes;};
  let versions = 0;
  await handshake(doc, async path => {
    if(path === '/api/version' && ++versions < 3) throw Error('offline');
    return {ok:true,json:async()=>path==='/gui.json'?manifest:core};
  }, {protocol:'http:',search:''}, {delays:[0,0,0]});
  assert.equal(versions,3); assert.equal(doc.documentElement.dataset.handshake,'ready');
  assert.deepEqual(doc.body.childNodes,[original]);
});

test('required capability failure needs manual retry and cannot initialise early', async () => {
  const doc = documentStub('zh'); let retry, started = false, fixed = false, calls = 0;
  const create = doc.createElement;
  doc.createElement = tag => ({...create(tag),addEventListener(type,cb){if(tag==='button')retry=cb;}});
  const ready = handshake(doc,async path=>{
    calls++;return {ok:true,json:async()=>path==='/gui.json'?manifest:{...core,capabilities:fixed?core.capabilities:[]}};
  },{protocol:'http:',search:''},{delays:[0]}).then(()=>{started=true;});
  for(let n=0;n<20;n++)await Promise.resolve();
  assert.equal(started,false);assert.equal(calls,2);assert.equal(doc.documentElement.dataset.handshake,'failed');
  fixed=true;retry();await ready;assert.equal(started,true);assert.equal(calls,4);
});
