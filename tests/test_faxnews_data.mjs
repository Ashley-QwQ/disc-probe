// The news fax's data rules (faxnews-data.mjs): what counts as a paper, how a day's paper is laid out, versions.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DEFAULT_SOURCE, readPaper, readSkin, layOut, compareVersions, parseVersion, pick, safeRef, resolveRef, PaperError, dayNumber}
  from '../discprobe/web/home/faxnews-data.mjs';

const home = new URL('../discprobe/web/home/', import.meta.url);
const sample = JSON.parse(readFileSync(new URL('faxnews/news.json', home), 'utf8'));
const clone = (x) => JSON.parse(JSON.stringify(x));
const refuses = (data, re) => assert.throws(() => readPaper(data), (e) => e instanceof PaperError && re.test(e.message), String(re));

// the bundled sample is a valid paper, and so are its skin parcels
const paper = readPaper(sample);
assert.equal(paper.date, '2026-11-14');
assert.equal(paper.sample, true);
assert.equal(paper.skins.length, 2);
assert.equal(paper.backgrounds.length, 3);
for (const s of paper.skins) {
  const parcel = JSON.parse(readFileSync(new URL(`faxnews/${s.package}`, home), 'utf8'));
  assert.equal(readSkin(parcel, s.id).id, s.id);
  assert.throws(() => readSkin(parcel, 'someone-else'), PaperError);
}
for (const a of paper.artworks) assert.ok(readFileSync(new URL(`faxnews/${a.image}`, home)).length > 1000, a.image);

// versions: numbers part by part, missing parts are 0, a prerelease before its release
assert.equal(compareVersions('1.0.0.0-alpha', 'v0.1.2.1'), 1);
assert.equal(compareVersions('v0.1.2.1', '0.1.2.1'), 0);
assert.equal(compareVersions('1.0', '1.0.0.0'), 0);
assert.equal(compareVersions('1.0.0.0-alpha', '1.0.0.0'), -1);
assert.equal(compareVersions('1.0-alpha.2', '1.0-alpha.10'), -1);
assert.equal(compareVersions('1.0-alpha', '1.0-beta'), -1);
assert.ok(Number.isNaN(compareVersions('soon', '1.0')));
assert.equal(parseVersion('1.2.3.4.5'), null);

// what is not a paper, and why
refuses(null, /not an object/);
refuses([], /not an object/);
refuses({...clone(sample), format: 'rss'}, /format/);
refuses({...clone(sample), version: 2}, /version/);
refuses({...clone(sample), date: '14/11/2026'}, /date/);
refuses({format: 'dp-fax-news', version: 1, date: '2026-11-14'}, /nothing to print/);
let bad = clone(sample); bad.skins[0].package = 'javascript:alert(1)'; refuses(bad, /skins\[0\]\.package/);
bad = clone(sample); bad.artworks[1].image = '//evil.example/x.png'; refuses(bad, /artworks\[1\]\.image/);
bad = clone(sample); bad.release.url = 'data:text/html,hi'; refuses(bad, /release\.url/);
bad = clone(sample); bad.skins[1].swatches = ['red', 'blue']; refuses(bad, /skins\[1\]\.swatches/);
bad = clone(sample); bad.backgrounds[0].pattern.size_mm = 9; refuses(bad, /backgrounds\[0\]\.pattern\.size_mm/);
bad = clone(sample); bad.jokes.push({de: 'nein'}); refuses(bad, /jokes\[6\]/);
bad = clone(sample); bad.changelog[0].story = 'x'.repeat(601); refuses(bad, /changelog\[0\]\.story/);
assert.equal(safeRef('https://example.com/a.json'), true);
assert.equal(safeRef('skins/a.json'), true);
assert.equal(safeRef('file:///C:/x'), false);
// unknown fields are dropped, lists are capped
bad = clone(sample); bad.extra = 1; bad.jokes = Array.from({length: 90}, (_, i) => `joke ${i}`);
const capped = readPaper(bad);
assert.equal('extra' in capped, false);
assert.equal(capped.jokes.length, 40);

// layout: a newer release leads; up to date, the newest story leads and says so
let lay = layOut(paper, {local: 'v0.1.2.1', day: '2026-11-14'});
assert.equal(lay.lead.kind, 'release');
assert.deepEqual(lay.stories.map((s) => s.version), ['0.1.2.1', '0.1.2.0', '0.1.1.9']);
lay = layOut(paper, {local: 'v1.0.0.0', day: '2026-11-14'});
assert.equal(lay.lead.kind, 'story');
assert.equal(lay.lead.version, '0.1.2.1');
assert.equal(lay.upToDate, true);
assert.equal(lay.stories.length, 2);
lay = layOut(paper, {local: '', day: '2026-11-14'});        // no local version known: nothing claimed newer
assert.equal(lay.lead.kind, 'story');
assert.equal(lay.upToDate, false);
// the day's picks: the same all day, the next one tomorrow
const a = layOut(paper, {day: '2026-11-14'}), b = layOut(paper, {day: '2026-11-14'}), c = layOut(paper, {day: '2026-11-15'});
assert.equal(a.joke, b.joke);
assert.notEqual(a.joke, c.joke);
assert.notEqual(a.background, c.background);
assert.equal(dayNumber('2026-11-15') - dayNumber('2026-11-14'), 1);

// text in either language; references relative to the paper's own address
assert.equal(pick({zh: '中', en: 'en'}, 'en'), 'en');
assert.equal(pick({zh: '中'}, 'en'), '中');
assert.equal(pick('plain', 'zh'), 'plain');
assert.equal(DEFAULT_SOURCE, '/api/news');
assert.equal(resolveRef('art/a.webp', 'https://news.example/dp/today.json'), '/api/news/asset?path=art%2Fa.webp&source=https%3A%2F%2Fnews.example%2Fdp%2Ftoday.json');
assert.equal(resolveRef('skins/a.json', DEFAULT_SOURCE), '/api/news/asset?path=skins%2Fa.json');
console.log('fax news data: sample paper and parcels, refusals, versions, layout and the day\'s picks passed');
