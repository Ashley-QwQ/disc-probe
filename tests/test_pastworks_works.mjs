// The works library client, its mock of the core routes (docs/goals/pastworks/SPEC.md), saving with
// If-Match / 409, and the archive's pure list helpers. Plain Node: no DOM, no server.
import assert from 'node:assert/strict';
import { createWorksClient, worksFor, setWorksForTest, mediaLabel, discCount, sortWorks, filterWorks, timeline, statusWord,
  unwrapWork, STATUSES } from '../discprobe/web/home/pastworks/works.mjs';
import { createMockWorks } from '../discprobe/web/home/pastworks/mock-works.mjs';
import { saveToLibrary } from '../discprobe/web/home/pastworks/save.mjs';
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

// the record: history first, discs not in the history added, oldest first
const tl = timeline({
  history: [
    { at: '2026-11-10T09:00:00Z', type: 'created' },
    { at: '2026-11-10T11:00:00Z', type: 'burned', disc: { code: 'KOI-A 2-03' }, drive: 'GH24', speed: '8x' },
    { at: '2026-11-10T10:00:00Z', type: 'iso', iso: 'C:\\out\\koi.iso' },
    { at: '2026-11-10T12:00:00Z', type: 'marked', status: 'failed', note: '内圈没刻上' },
    { at: '2026-11-10T12:30:00Z', type: 'something-new' },
  ],
  discs: [{ code: 'KOI-A 2-03', burned_at: '2026-11-10T11:00:00Z' }, { code: 'KOI-A 2-04', burned_at: '2026-11-10T11:30:00Z', drive: 'GH24' }],
}, 'zh');
assert.deepEqual(tl.map(e => e.text), ['创建', '出 ISO', '刻进 KOI-A 2-03', '刻进 KOI-A 2-04', '标成失败', 'something-new']);
assert.equal(tl[1].detail, 'koi.iso');
assert.equal(tl[2].detail, 'GH24 · 8x');
assert.equal(tl[4].detail, '内圈没刻上');
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
assert.equal(t1.updated_at, s1.updated_at, 'a picture alone leaves the save stamp');
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
assert.deepEqual(full.history.map(e => e.type), ['created', 'saved', 'renamed', 'marked', 'marked']);
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
assert.equal(await otherClient.design(imported.id), design());
assert.equal(other.calls.at(-2).headers['x-filename'], encodeURIComponent('锦鲤.zip'), 'file name sent percent-encoded');
const fromFile = await otherClient.importFile(new File([design({ media: 'cd', cell: 0.01 })], '月亮.discdesign'));
assert.equal(fromFile.name, '月亮'); assert.equal(fromFile.media, 'cd'); assert.equal(fromFile.cell_um, 10);
assert.equal(fromFile.source_file, '月亮.discdesign');
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
