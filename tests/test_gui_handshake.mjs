import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compatibility, compareAPI, hideOptional, showSheet} from '../discprobe/web/home/handshake.mjs';
const manifest = JSON.parse(readFileSync(new URL('../discprobe/web/gui.json', import.meta.url)));
const core = {api_version:'1.0', capabilities:[...manifest.required_capabilities, ...manifest.optional_capabilities]};

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
  assert.equal(optional.update,null); assert.deepEqual(optional.optional,['templates','presets-io','works']);
  const withoutWorks = compatibility(manifest,{...core,capabilities:core.capabilities.filter(c => c !== 'works')});
  assert.equal(withoutWorks.update,null); assert.deepEqual(withoutWorks.optional,['works']);
});
function documentStub(lang='en') {
  const entries = [{dataset:{capability:'templates'}},{dataset:{capability:'geo'}}];
  return {documentElement:{dataset:{lang}}, entries,
    createElement:tag=>({tag,children:[],setAttribute(){},append(...items){this.children.push(...items);}}),
    head:{append(style){this.style=style;}}, querySelectorAll:()=>entries,
    body:{replaceChildren(sheet){this.sheet=sheet;}}};
}
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
