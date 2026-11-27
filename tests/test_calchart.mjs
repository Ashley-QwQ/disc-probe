import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// Match the other no-package tests: .js is a browser ES module, independently
// of Node's package type in the checkout.
const source = readFileSync(new URL('../discprobe/web/home/calchart.js', import.meta.url), 'utf8');
const { liveChart, resultChart } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const tags = (svg, name, cls) => [...svg.matchAll(new RegExp(`<${name}\\b[^>]*class="${cls}"[^>]*>`, 'g'))].map(m => m[0]);
const attr = (tag, name) => tag.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1];
const value = (tag, name) => Number(attr(tag, name));
const circles = svg => tags(svg, 'circle', 'cc-point');
const fitLine = svg => tags(svg, 'line', 'cc-fit')[0];
const close = (actual, expected, eps = .0002) => assert.ok(Math.abs(actual - expected) < eps, `${actual} != ${expected}`);
const x = r => 64 + (r - 24) / 34 * 480;
const y = (d, range) => 101 - d / range * 73;
let passed = 0;
function test(name, run) { run(); passed++; console.log(`PASS ${name}`); }

test('empty input and accessible SVG shell', () => {
  const svg = liveChart([]);
  assert.match(svg, /viewBox="0 0 560 220"/);
  assert.match(svg, /class="chart calchart"/);
  assert.match(svg, /width="100%" role="img" aria-label="[^"]+"/);
  assert.equal(circles(svg).length, 0);
  assert.equal(fitLine(svg), undefined);
  assert.match(svg, /还没读到/);
  assert.equal(resultChart({ points: [] }), '');
  assert.equal(resultChart(null), '');
});

test('one point has an open circle and sigma bars but no fit', () => {
  const svg = liveChart([{ r: 30, d: .1, s: .05 }]);
  assert.equal(circles(svg).length, 1);
  assert.equal(fitLine(svg), undefined);
  assert.equal(tags(svg, 'path', 'cc-error').length, 1);
  assert.match(svg, /\.cc-point\s*\{[^}]*stroke-width: 1\.5; fill: none;/);
  close(value(circles(svg)[0], 'cx'), x(30));
  close(value(circles(svg)[0], 'cy'), y(.1, .35));
});

test('unordered points: exact linear fit ends at measured endpoints', () => {
  const input = Object.freeze([58, 24, 40, 30].map(r => Object.freeze({ r, d: (r - 40) * .005, s: .02 })));
  const svg = liveChart(input), line = fitLine(svg), pts = circles(svg);
  assert.ok(line);
  close(value(line, 'x1'), x(24));
  assert.equal(value(line, 'x2'), value(pts.at(-1), 'cx'));
  close(value(line, 'y1'), y(-.08, .35));
  close(value(line, 'y2'), y(.09, .35));
  assert.deepEqual(input.map(p => p.r), [58, 24, 40, 30]);
  const partial = liveChart([{ r: 40, d: .1, s: .02 }, { r: 24, d: 0, s: .02 }]);
  close(value(fitLine(partial), 'x2'), x(40));
  assert.ok(value(fitLine(partial), 'x2') < x(58));
});

test('weighted least squares and sigma floor affect the fitted values', () => {
  const svg = liveChart([{ r: 24, d: 0, s: 0 }, { r: 41, d: .1, s: .01 }, { r: 58, d: 0, s: .02 }]);
  // Independent normal equations in t=(r-24)/17: weights 1, 1, 1/4.
  const S = 2.25, St = 1.5, Stt = 2, Sd = .1, Std = .1;
  const b = (S * Std - St * Sd) / (S * Stt - St ** 2), a = (Sd - b * St) / S;
  close(value(fitLine(svg), 'y1'), y(a, .35));
  close(value(fitLine(svg), 'y2'), y(a + 2 * b, .35));
});

test('hatched band uses median sigma and is clipped to the plot', () => {
  const svg = liveChart([{ r: 24, d: 0, s: .02 }, { r: 40, d: 0, s: .04 }]);
  const polygon = tags(svg, 'polygon', 'cc-band')[0];
  assert.match(svg, /patternTransform="rotate\(45\)"/);
  assert.match(svg, /clip-path="url\(#calchart-\d+-clip\)"/);
  assert.match(polygon, /fill="url\(#calchart-\d+-hatch\)"/);
  const coords = attr(polygon, 'points').split(' ').map(p => p.split(',').map(Number));
  close(coords[0][1], y(.03, .35));
  close(coords[2][1], y(-.03, .35));
  close(coords[1][0], x(40));
});

test('head at 40: dashed boundary and centred unread label', () => {
  const svg = liveChart([{ r: 30, d: 0, s: .02 }], { head: 40 });
  const head = tags(svg, 'line', 'cc-head')[0], text = tags(svg, 'text', 'cc-unread')[0];
  close(value(head, 'x1'), x(40));
  assert.equal(attr(head, 'stroke-dasharray'), '3 4');
  close(value(text, 'x'), (x(40) + x(58)) / 2);
  assert.match(svg, /还没读到/);
});

test('endpoint markers have clip clearance beyond both radius endpoints', () => {
  const svg = liveChart([{ r: 24, d: 0, s: .02 }, { r: 58, d: .1, s: .02 }]);
  const groups = [...svg.matchAll(/<g clip-path="url\(#([^)]+)\)">([\s\S]*?)<\/g>/g)];
  assert.equal(groups.length, 2);
  assert.match(groups[0][2], /class="cc-band"/);
  assert.doesNotMatch(groups[0][2], /<circle/);
  assert.equal(circles(groups[1][2]).length, 2);
  const clip = svg.match(new RegExp(`<clipPath id="${groups[1][1]}">(<rect[^>]+>)`))[1];
  assert.ok(value(clip, 'x') <= x(24) - 3.75);
  assert.ok(value(clip, 'x') + value(clip, 'width') >= x(58) + 3.75);
});

test('null head uses largest measured radius and respects 57 mm cutoff', () => {
  const svg = liveChart([{ r: 57.5, d: 0, s: .01 }, { r: 30, d: .1, s: .01 }]);
  assert.doesNotMatch(svg, /还没读到/);
  assert.equal(tags(svg, 'line', 'cc-head').length, 0);
  const partial = liveChart([{ r: 40, d: 0, s: .02 }, { r: 28, d: 0, s: .02 }]);
  close(value(tags(partial, 'line', 'cc-head')[0], 'x1'), x(40));
});

const results = Object.freeze([300, 100, 200].map(lba => Object.freeze({ lba, residual_deg: .05, sigma_deg: .02 })));
test('result radii use squared-radius LBA mapping and exact span ends', () => {
  const svg = resultChart({ points: results, span_mm: [28, 48], stopped: false });
  const pts = circles(svg);
  close(value(pts[0], 'cx'), x(28));
  close(value(pts[1], 'cx'), x(Math.sqrt((28 ** 2 + 48 ** 2) / 2)));
  close(value(pts[2], 'cx'), x(48));
  assert.match(svg, /半径 mm/);
  assert.doesNotMatch(svg, /还没读到/);
  assert.deepEqual(results.map(p => p.lba), [300, 100, 200]);
});

test('result without span uses linear LBA mapping and sector labels', () => {
  const svg = resultChart({ points: results, span_mm: null }, { zh: false });
  const pts = circles(svg);
  for (const [i, radius] of [24, 41, 58].entries()) close(value(pts[i], 'cx'), x(radius));
  assert.match(svg, /position \(sectors\)/);
  assert.match(svg, />100<\/text>/);
  assert.match(svg, />300<\/text>/);
  assert.match(resultChart({ points: results }), /位置（扇区）/);
});

test('stopped results mark the remaining region, including near the edge', () => {
  for (const end of [40, 57.5]) {
    const svg = resultChart({ points: results, span_mm: [28, end], stopped: true }, { zh: false });
    // the words where they fit; a sliver at the edge keeps only the dashed line
    if (end < 50) assert.match(svg, /not read yet/); else assert.doesNotMatch(svg, /not read yet/);
    close(value(tags(svg, 'line', 'cc-head')[0], 'x1'), x(end));
    assert.equal(value(fitLine(svg), 'x2'), value(circles(svg).at(-1), 'cx'));
  }
});

test('pattern and clip ids are unique across live and result charts', () => {
  const charts = [liveChart([]), liveChart([]), resultChart({ points: results })];
  const ids = charts.flatMap(svg => [...svg.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
  assert.equal(new Set(ids).size, ids.length);
  for (const svg of charts) for (const m of svg.matchAll(/url\(#([^)]*)\)/g)) assert.ok(svg.includes(`id="${m[1]}"`));
});

test('nonfinite and invalid points are skipped, including result LBAs', () => {
  const svg = liveChart([{ r: 30, d: .1, s: .02 }, { r: NaN, d: 0, s: .1 },
    { r: 40, d: Infinity, s: .1 }, { r: 50, d: 0, s: NaN }, { r: 51, d: 0, s: -1 }, null], { head: Infinity });
  assert.equal(circles(svg).length, 1);
  assert.doesNotMatch(svg, /NaN|Infinity/);
  const bad = [{ lba: NaN, residual_deg: 0, sigma_deg: .1 }, { lba: 2, residual_deg: Infinity, sigma_deg: .1 }];
  assert.equal(resultChart({ points: bad }), '');
  assert.equal(circles(resultChart({ points: [...results, ...bad] })).length, 3);
});

test('duplicate radii and single-LBA results have no singular fit', () => {
  const svg = liveChart([{ r: 30, d: .1, s: .02 }, { r: 30, d: -.1, s: .03 }]);
  assert.equal(fitLine(svg), undefined);
  const result = resultChart({ points: [results[0]], span_mm: [28, 48] });
  close(value(circles(result)[0], 'cx'), x(28));
  assert.equal(fitLine(result), undefined);
  assert.doesNotMatch(result, /NaN|Infinity/);
});

test('symmetric nicely rounded axes, themes and English labels', () => {
  const svg = liveChart([{ r: 30, d: .6, s: .1 }], { head: 40, zh: false });
  assert.match(svg, />\+0\.81°<\/text>/);
  assert.match(svg, />−0\.81°<\/text>/);
  assert.match(svg, />0<\/text>/);
  assert.match(svg, />turn offset<\/text>/);
  assert.match(svg, />radius mm<\/text>/);
  assert.match(svg, /not read yet/);
  assert.doesNotMatch(svg, /还没读到|转角偏差|半径/);
  for (const variable of ['--ink', '--ink-3', '--mono']) assert.ok(svg.includes(`var(${variable})`));
  assert.doesNotMatch(svg, /--copper|--accent|#[0-9a-f]{3,8}\b|rgba?\(/i);
});

console.log(`Calibration chart tests passed (${passed} cases)`);
