import {test} from 'node:test';
import assert from 'node:assert/strict';
import {templateRequest} from '../discprobe/web/home/design/template-download.mjs';

test('template uses selected batch geometry and sector count, never another batch', () => {
  assert.deepEqual(templateRequest({media:'dvd', geo:'old.json', item:{geo:'mine.json',sectors:1234567}}),
    {geo:'mine.json',media:'dvd',sectors:1234567});
  assert.deepEqual(templateRequest({media:'bd', item:{preset:'presets/discs.json',id:'preset:my-disc'}}),
    {geo:'presets/discs.json',media:'bd',preset_id:'my-disc'});
  assert.throws(() => templateRequest({media:'dvd',item:{kind:'unset'}}), /geometry/);
});
