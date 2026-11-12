import assert from 'node:assert/strict';
import { lobbyStatus } from '../discprobe/web/home/lobby-state.js';

const state = (disc, jobs = []) => ({drives: [{id: 'fake', disc}], selectedDrive: 'fake', jobs});
for (const lang of ['zh', 'en']) {
  assert.ok(lobbyStatus(null, lang));
  assert.ok(lobbyStatus({drives: []}, lang));
  assert.ok(lobbyStatus({error: true}, lang));
  const unknown = lobbyStatus(state({present: true, kind: 'DVD-R', blank: null}), lang);
  assert.match(unknown, lang === 'zh' ? /不知道/ : /unknown/);
  const blank = lobbyStatus(state({present: true, kind: 'CD-R', blank: true}), lang);
  assert.match(blank, /CD-R/);
  assert.match(blank, lang === 'zh' ? /空白/ : /blank/);
  const written = lobbyStatus(state({present: true, kind: 'DVD-R', blank: false}), lang);
  assert.match(written, lang === 'zh' ? /已写过/ : /has been written/);
  // A running job takes precedence over a cached blank-disc report.
  const busy = lobbyStatus(state({present: true, blank: true}, [{drive: 'fake', exit: null}]), lang);
  assert.match(busy, lang === 'zh' ? /正在工作/ : /busy/);
  const finished = lobbyStatus(state({present: true, kind: 'CD-R', blank: true}, [{drive: 'fake', exit: 0}]), lang);
  assert.equal(finished, blank);
  assert.notEqual(lobbyStatus(state({present: false, tray: 'open'}), lang), lobbyStatus(state({present: false, tray: 'empty'}), lang));
}
// The selected drive wins; an unrelated drive's job must not mask it.
assert.match(lobbyStatus({selectedDrive: 'two', drives: [
  {id: 'one', disc: {present: true, blank: true, kind: 'CD-R'}},
  {id: 'two', disc: {present: true, blank: false, kind: 'DVD-R'}},
], jobs: [{drive: 'one', exit: null}]}, 'en'), /DVD-R.*written/);
console.log('Lobby state: bilingual states, unknown blankness, job precedence and drive selection passed.');
