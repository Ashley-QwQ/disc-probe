// The works library client, its mock of the core routes (docs/goals/pastworks/SPEC.md), saving with
// If-Match / 409, and the archive's pure list helpers. Plain Node: no DOM, no server.
import assert from 'node:assert/strict';
import { createWorksClient, worksFor, setWorksForTest, mediaLabel, discCount, sortWorks, filterWorks, timeline, statusWord,
  unwrapWork, STATUSES, burnedDiscs, discCode } from '../discprobe/web/home/pastworks/works.mjs';
import { createMockWorks } from '../discprobe/web/home/pastworks/mock-works.mjs';
import { saveToLibrary, afterISO, relativeGeo } from '../discprobe/web/home/pastworks/save.mjs';
import { arrange, gridStep } from '../discprobe/web/home/pastworks.js';

const design = (extra = {}) => JSON.stringify({ format: 'disc-probe design', version: 2, media: 'dvd', cell: 0.02, layers: [], ...extra });

// ---------------------------------------------------------------- pure helpers
assert.equal(mediaLabel({ media: 'dvd', disc_type: '-R' }), 'DVD-R');
assert.equal(mediaLabel({ media: 'dvd', disc_type: '+R' }), 'DVD+R');
assert.equal(mediaLabel({ media: 'cd', disc_type: 'RW' }), 'CD-RW');
assert.equal(mediaLabel({ media: 'bd' }), 'BD');
assert.equal(mediaLabel({}), '');
assert.equal(discCount({ discs: [{}, {}] }), 2);
assert.equal(discCount({}), 0);
assert.deepEqual(STATUSES, ['draft', 'iso_ready', 'burned', 'done', 'failed']);
assert.equal(statusWord('iso_ready', 'zh'), '已出 ISO');
assert.equal(statusWord('done', 'en'), 'Finished');
const ws = [
  { id: 'a', name: '岸边', status: 'draft', media: 'dvd', updated_at: '2026-11-10T10:00:00+08:00' },
  { id: 'b', name: 'Atlas 10', status: 'burned', media: 'cd', updated_at: '2026-11-12T10:00:00+08:00' },
  { id: 'c', name: 'Atlas 2', status: 'failed', media: 'dvd', updated_at: '2026-11-11T10:00:00+08:00' },
  { id: 'd', name: '长夜', status: 'done', media: 'bd', updated_at: null, created_at: '2026-01-01T00:00:00Z' },
];
assert.deepEqual(sortWorks(ws).map(w => w.id), ['b', 'c', 'a', 'd'], 'newest first, falling back to created_at');
assert.deepEqual(sortWorks(ws, 'name').map(w => w.id), ['a', 'd', 'c', 'b'], 'Chinese first by pinyin, then numeric Latin');
assert.deepEqual(filterWorks(ws, { status: 'failed' }).map(w => w.id), ['c']);
assert.deepEqual(filterWorks(ws, { media: 'dvd' }).map(w => w.id), ['a', 'c']);
assert.deepEqual(filterWorks(ws, { q: 'ＡＴＬＡＳ' }).map(w => w.id), ['b', 'c'], 'full-width IME input still matches');
assert.deepEqual(filterWorks(ws, { q: '  长 ' }).map(w => w.id), ['d']);
assert.deepEqual(filterWorks(ws, { q: 'atlas', media: 'cd' }).map(w => w.id), ['b']);
assert.deepEqual(unwrapWork({ work: { id: 'x' }, history: [1] }), { id: 'x', history: [1] });
assert.deepEqual(unwrapWork({ id: 'y' }), { id: 'y' });

// the record, in the core's shapes (works.py): events {type, time, changes | record}; discs[] holds ISOs and burns
const iso = { type: 'iso', iso_path: 'C:\\out\\koi.iso', iso_sha256: 'ab', time: '2026-11-10T10:00:00+00:00', drive: null, speed: null, disc_code: null, result: 'completed' };
const burn3 = { ...iso, type: 'burn', time: '2026-11-10T11:00:00+00:00', drive: 'E:', speed: 8, disc_code: 'KOI-A 2-03' };
const burn4 = { ...burn3, time: '2026-11-10T11:30:00+00:00', disc_code: 'KOI-A 2-04', result: 'verify failed' };
const real = {
  discs: [iso, burn3, burn4],
  history: [   // the last 50 only: burn4's event has dropped off, discs[] still has it
    { type: 'created', time: '2026-11-10T09:00:00+00:00' },
    { type: 'thumb', time: '2026-11-10T09:01:00+00:00' },
    { type: 'burn', time: '2026-11-10T11:00:01+00:00', record: burn3 },
    { type: 'iso', time: '2026-11-10T10:00:01+00:00', record: iso },
    { type: 'renamed', time: '2026-11-10T11:50:00+00:00', changes: { name: '锦鲤' } },
    { type: 'marked', time: '2026-11-10T12:00:00+00:00', changes: { status: 'failed', note: '内圈没刻上' } },
    { type: 'marked', time: '2026-11-10T12:10:00+00:00', changes: { batch: 'KOI-A' } },
    { type: 'something-new', time: '2026-11-10T12:30:00+00:00' },
  ],
};
assert.equal(discCount(real), 2, 'an ISO written is not a disc burned');
assert.deepEqual(burnedDiscs(real).map(discCode), ['KOI-A 2-03', 'KOI-A 2-04']);
const tl = timeline(real, 'zh');
assert.deepEqual(tl.map(e => e.text), ['创建', '出 ISO', '刻进 KOI-A 2-03', '刻进 KOI-A 2-04', '改名为“锦鲤”', '标成失败', '改了作品信息', 'something-new'],
  'picture uploads left out; a burn missing from the short history comes from discs[]; no doubles');
assert.equal(tl[1].detail, 'koi.iso');
assert.equal(tl[2].detail, 'E: · 8x');
assert.equal(tl[3].detail, 'E: · 8x · verify failed');
assert.equal(tl[5].detail, '内圈没刻上');
// older or looser shapes still read
const loose = timeline({ history: [{ at: '2026-11-10T11:00:00Z', type: 'burned', disc: { code: 'X-1' }, drive: 'GH24', speed: '8x' },
  { at: '2026-11-10T12:00:00Z', type: 'marked', status: 'done' }] }, 'en');
assert.deepEqual(loose.map(e => [e.text, e.detail]), [['Burned onto X-1', 'GH24 · 8x'], ['Marked finished', '']]);
assert.deepEqual(timeline({}, 'en'), []);

// the grid: unsaved session plans first, filtered and searched alongside the works
const plans = [{ name: '新的', media: 'dvd' }, { name: 'Moon', media: 'cd' }];
assert.deepEqual(arrange({ works: ws, plans }).map(e => e.plan?.name ?? e.work.id), ['新的', 'Moon', 'b', 'c', 'a', 'd']);
assert.deepEqual(arrange({ works: ws, plans }, { status: 'burned' }).map(e => e.plan?.name ?? e.work.id), ['b'], 'a status hides plans');
assert.deepEqual(arrange({ works: ws, plans }, { media: 'cd' }).map(e => e.plan?.name ?? e.work.id), ['Moon', 'b']);
assert.deepEqual(arrange({ works: [], plans }, { q: 'moon' }).map(e => e.plan.name), ['Moon']);
// arrow keys on a 4-column grid of 10
assert.equal(gridStep(0, 'ArrowRight', 10, 4), 1);
assert.equal(gridStep(0, 'ArrowLeft', 10, 4), 0);
assert.equal(gridStep(1, 'ArrowDown', 10, 4), 5);
assert.equal(gridStep(8, 'ArrowDown', 10, 4), 8, 'no row below: stay');
assert.equal(gridStep(5, 'ArrowUp', 10, 4), 1);
assert.equal(gridStep(5, 'End', 10, 4), 9);
assert.equal(gridStep(5, 'Home', 10, 4), 0);
console.log('Works helpers: labels, sorting, filtering, search, record and grid keys passed');

// ---------------------------------------------------------------- the client against the mock routes
let clock = Date.parse('2026-11-12T10:00:00+08:00');
const mock = createMockWorks({ now: () => (clock += 1000) });
const client = createWorksClient({ fetch: mock.fetch, token: 'tok' });
const w1 = await client.create({ name: '锦鲤 / Koi', media: 'dvd' });
assert.match(w1.id, /^w-\d{8}-\d{6}-[0-9a-f]{4}$/);
assert.equal(w1.status, 'draft');
assert.ok(mock.calls.every(c => c.headers['x-discprobe-token'] === 'tok'), 'every call carries the session token');
assert.equal((await client.list()).length, 1);
await assert.rejects(client.design(w1.id), e => e.status === 404, 'a new work has no design yet');
const s1 = await client.saveDesign(w1.id, design(), w1.updated_at);
assert.ok(Date.parse(s1.updated_at) > Date.parse(w1.updated_at));
assert.equal(await client.design(w1.id), design(), 'design stored verbatim');
assert.equal(mock.calls.at(-2).headers['if-match'], w1.updated_at);
await assert.rejects(client.saveDesign(w1.id, design({ x: 1 }), w1.updated_at), e => e.status === 409, 'stale If-Match is a conflict');
await assert.rejects(client.saveDesign(w1.id, '{"format":"nope"}', s1.updated_at), e => e.status === 400);
const png = new Blob([new Uint8Array([137, 80, 78, 71])], { type: 'image/png' });
const t1 = await client.putThumb(w1.id, png);
assert.ok(Date.parse(t1.updated_at) > Date.parse(s1.updated_at), 'a picture moves updated_at, as in the core');
const listed = (await client.list())[0];
assert.ok(listed.thumb_url, 'list gives thumb_url once a picture exists');
const url = await client.thumbURL(listed);
assert.equal(await client.thumbURL(listed), url, 'thumbnail object URL cached per save');
assert.equal((await (await fetch(url)).arrayBuffer()).byteLength, 4);
const r1 = await client.rename(w1.id, '锦鲤');
assert.equal(r1.name, '锦鲤');
await assert.rejects(client.rename(w1.id, '  '), e => e.status === 400);
await assert.rejects(client.mark(w1.id, 'failed'), e => e.status === 400, 'failed needs a reason');
const m1 = await client.mark(w1.id, 'failed', '外圈发白');
assert.equal(m1.status, 'failed'); assert.equal(m1.note, '外圈发白');
await client.mark(w1.id, 'done');
const full = await client.get(w1.id);
assert.ok(Array.isArray(full.history));
assert.deepEqual(full.history.map(e => e.type), ['created', 'saved', 'thumb', 'renamed', 'marked', 'marked']);
const d1 = await client.duplicate(w1.id);
assert.notEqual(d1.id, w1.id); assert.equal(d1.status, 'draft');
assert.equal(await client.design(d1.id), design(), 'duplicate carries the design');
await client.remove(d1.id);
assert.equal((await client.list()).some(w => w.id === d1.id), false, 'deleted work leaves the list');
await assert.rejects(client.get(d1.id), e => e.status === 404);
const back = await client.restore(d1.id);
assert.equal(back.id, d1.id);
assert.equal((await client.list()).length, 2, 'restored');
// export, then import elsewhere
const { blob, name } = await client.exportZip(w1.id, '锦鲤');
assert.equal(name, '锦鲤.zip');
const other = createMockWorks();
const otherClient = createWorksClient({ fetch: other.fetch });
const imported = await otherClient.importFile(new File([blob], name, { type: 'application/zip' }));
assert.equal(imported.name, '锦鲤'); assert.equal(imported.status, 'done');
assert.equal(imported.id, w1.id, 'a zip keeps its id');
await assert.rejects(otherClient.importFile(new File([blob], name, { type: 'application/zip' })), e => e.status === 409, 'the same zip twice is a conflict');
assert.equal(await otherClient.design(imported.id), design());
assert.equal(other.calls.at(-2).headers['x-filename'], encodeURIComponent('锦鲤.zip'), 'file name sent percent-encoded');
const fromFile = await otherClient.importFile(new File([design({ media: 'cd', cell: 0.01 })], '月亮.discdesign'));
assert.equal(fromFile.name, '月亮'); assert.equal(fromFile.media, 'cd'); assert.equal(fromFile.cell_um, 10);
assert.equal(other.calls.at(-1).url.includes('/import') || other.calls.at(-2).url.includes('/import'), false,'a .discdesign is made and saved, not sent through /import with its name in a header');
await assert.rejects(otherClient.importFile(new File(['hello'], 'x.discdesign')), e => e.status === 400);
// list shape: bare arrays are read too
const bare = createWorksClient({ fetch: async () => new Response(JSON.stringify([{ id: 'w', name: 'n' }]), { status: 200 }) });
assert.deepEqual((await bare.list()).map(w => w.id), ['w']);
console.log('Works client: create, save with If-Match, 409, thumbnail, rename, mark, duplicate, bin and restore, export and import passed');

// ---------------------------------------------------------------- saving from the design page
const lib = createMockWorks({ now: () => (clock += 1000) });
const c2 = createWorksClient({ fetch: lib.fetch });
const plan = { media: 'cd', name: '海' };
let asked = 0;
const thumb = async () => png;
const first = await saveToLibrary({ client: c2, plan, text: design({ media: 'cd' }), thumb, name: '海', ask: async () => { asked++; return null; } });
assert.ok(plan.work?.id, 'first save makes the work');
assert.equal(first.work.media, 'cd');
assert.equal(lib.works.size, 1); assert.ok(lib.thumbs.has(plan.work.id), 'thumbnail uploaded');
assert.equal(first.note, '已存进作品库：海');
const id = plan.work.id;
await saveToLibrary({ client: c2, plan, text: design({ media: 'cd', n: 2 }), thumb, name: '海', ask: async () => { asked++; return null; } });
assert.equal(lib.works.size, 1, 'second save reuses the work');
assert.equal(asked, 0, 'no false conflict from its own saves or its picture');
lib.touch(id);                               // another window saves
assert.equal(await saveToLibrary({ client: c2, plan, text: design({ n: 3 }), thumb, name: '海', ask: async () => { asked++; return null; } }), null, 'cancel keeps both untouched');
assert.equal(asked, 1);
assert.match(lib.designs.get(id), /"n":2/);
const over = await saveToLibrary({ client: c2, plan, text: design({ n: 4 }), thumb, name: '海', ask: async () => 'overwrite' });
assert.equal(over.work.id, id); assert.match(lib.designs.get(id), /"n":4/);
lib.touch(id);
const copy = await saveToLibrary({ client: c2, plan, text: design({ n: 5 }), thumb, name: '海', lang: 'en', ask: async () => 'copy' });
assert.notEqual(copy.work.id, id); assert.equal(plan.work.id, copy.work.id, 'the plan follows the copy');
assert.match(lib.designs.get(id), /"n":4/, 'the other window’s save is kept');
assert.equal(copy.work.name, '海 (copy)'); assert.equal(copy.note, 'Saved as a new work: 海 (copy)');
await c2.remove(copy.work.id);
const moved = await saveToLibrary({ client: c2, plan, text: design({ n: 6 }), thumb, name: '海', ask: async () => 'overwrite' });
assert.ok(moved.work.id !== copy.work.id && lib.works.has(moved.work.id), 'a work binned elsewhere saves as a new one');
const noThumb = await saveToLibrary({ client: c2, plan, text: design({ n: 7 }), thumb: async () => { throw Error('no canvas'); }, name: '海' });
assert.match(noThumb.note, /缩略图没有传上去/);
console.log('Design page saving: first save, reuse, 409 cancel / overwrite / keep both, binned work, picture failure passed');

// two Ctrl+S at once: one after the other, one work, no false conflict
{
  const lib3 = createMockWorks({ now: () => (clock += 1000) }), c4 = createWorksClient({ fetch: lib3.fetch }), p = { media: 'cd' };
  const ask = async () => { throw Error('false conflict'); };
  const [a, b] = await Promise.all([saveToLibrary({ client: c4, plan: p, text: design({ n: 1 }), thumb, name: '双', ask }),
    saveToLibrary({ client: c4, plan: p, text: design({ n: 2 }), thumb, name: '双', ask })]);
  assert.equal(lib3.works.size, 1, 'one work, not two'); assert.equal(a.work.id, b.work.id);
  assert.match(lib3.designs.get(p.work.id), /"n":2/, 'the later save lands last');
  console.log('Overlapping saves: queued, one work, no false conflict passed');
}

// ---------------------------------------------------------------- after an ISO for the work
{
  const lib2 = createMockWorks({ now: () => (clock += 1000) });
  const c3 = createWorksClient({ fetch: lib2.fetch });
  const p = { media: 'dvd' };
  await saveToLibrary({ client: c3, plan: p, text: design(), thumb, name: '光' });
  let before = p.work.updated_at;
  lib2.link(p.work.id, { type: 'iso', iso_path: 'iso/光.iso' });          // the core's image --work, on success
  const w = await afterISO({ client: c3, plan: p, before, geo: 'results\\geo-E-20261112' });
  assert.equal(w.status, 'iso_ready');
  assert.equal(w.geo_run, 'results/geo-E-20261112', 'the geometry really used, as a data-root path');
  assert.equal(p.work.updated_at, lib2.works.get(p.work.id).updated_at, 'the page follows the stamps its own ISO moved');
  await saveToLibrary({ client: c3, plan: p, text: design({ n: 1 }), thumb, name: '光', ask: async () => { throw Error('false conflict'); } });
  assert.equal(timeline(await c3.get(p.work.id), 'zh').find(e => e.text === '记下所用几何')?.detail, 'results/geo-E-20261112');
  before = p.work.updated_at;
  lib2.touch(p.work.id);                                                    // another window saves meanwhile
  lib2.link(p.work.id, { type: 'iso', iso_path: 'iso/光2.iso' });
  await afterISO({ client: c3, plan: p, before, geo: 'D:/elsewhere/geo' });
  assert.equal(p.work.updated_at, before, 'someone else saved: keep the old stamp so the next save asks');
  const q = { media: 'dvd' };
  await saveToLibrary({ client: c3, plan: q, text: design(), thumb, name: '刻' });
  const qBefore = q.work.updated_at;
  lib2.link(q.work.id, { type: 'burn', iso_path: 'iso/刻.iso', drive: 'E:', speed: 4, disc_code: 'KOI-A 2-05' });   // burn --work, on success
  const burnt = await afterISO({ client: c3, plan: q, before: qBefore, geo: null });
  assert.equal(burnt.status, 'burned'); assert.equal(discCount(burnt), 1);
  assert.equal(q.work.updated_at, lib2.works.get(q.work.id).updated_at, 'after a burn the page follows the stamp too');
  assert.equal(relativeGeo('D:/elsewhere/geo'), null); assert.equal(relativeGeo('a/../b'), null); assert.equal(relativeGeo('/abs'), null);
  assert.equal(await afterISO({ client: c3, plan: {}, before, geo: 'x' }), null, 'a plan outside the library: nothing to note');
  console.log('After an ISO: geometry noted, stamps followed, another window still caught passed');
}

// ---------------------------------------------------------------- which library a page gets
setWorksForTest(null);
assert.equal(await worksFor({}, { capable: false }), null, 'a core without works: the in-memory list');
setWorksForTest(null);
const demo = await worksFor({ backend: { mock: true } }, { capable: false });
assert.ok(demo.mock, 'demo pages get the in-browser mock');
setWorksForTest(null);
assert.ok(!(await worksFor({}, { capable: true })).mock, 'a capable core gets the real client');
setWorksForTest(null);
console.log('Library choice: none, mock, real passed');
