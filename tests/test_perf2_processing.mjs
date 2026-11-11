// Frozen SHA-256 from the pre-optimization implementation, 2026-11-10.
// Run with: node tests/test_perf2_processing.mjs
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { processRGBA, renderOutput, renderOutputCells, renderExportCells, OUTPUT_MODES } from '../discprobe/web/home/design/processing.mjs';
const hash = data => createHash('sha256').update(data).digest('hex');
const width = 83, height = 67, data = new Uint8ClampedArray(width * height * 4);
let seed = 98765;
for (let i = 0; i < data.length; i++) { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; data[i] = seed >>> 24; }
for (let i = 0; i < width * height; i++) {
  if (i % 7 === 0) data.fill(255, i * 4, i * 4 + 4);
  if (i % 11 === 0) data[i * 4 + 3] = 0;
  if (i % 13 === 0) data.fill(0, i * 4, i * 4 + 3);
}
const image = { width, height, data }, snapshots = [];
for (const adjustments of [{}, { brightness: 13, contrast: -17, highlights: 30, shadows: -12, gamma: 1 / 2.2 },
  { denoise: 20, clarity: 23, texture: -8, sharpen: 40, grain: 7, seed: 19 }]) {
  const toned = processRGBA(image, adjustments, { histogram: false });
  assert.equal(toned.histogram, undefined);
  for (const mode of OUTPUT_MODES) for (const cellSize of [1, 3]) {
    const options = { mode, cellSize, levels: mode === 'grayscale' ? 4 : 256, angle: 37, strength: .73, seed: 9 };
    const rendered = renderOutput(toned, options);
    snapshots.push(hash(rendered.data));
    if (cellSize === 1) {
      const { values } = renderOutputCells(toned, options);
      assert.deepEqual(renderExportCells(image, adjustments, options).values, values);
      for (let i = 0; i < values.length; i++) assert.equal(values[i] < .5, rendered.data[i * 4] < 128);
    }
  }
}
assert.equal(hash(snapshots.join('')), 'f19ef76f74a7bcd6ddb0a8f7b75286ea4230011b78b073e220f92dc39eb4230d');
// Banded Floyd-Steinberg must match one piece, including its carried row.
for (const strength of [0, .73, 1]) {
  const expected = renderOutput(image, { strength }).data;
  const strip = { y0: 0, more: true, carry: null };
  for (let y = 0; y < height; y += 9) {
    const rows = Math.min(9, height - y), more = y + rows < height;
    const band = { width, height: rows + Number(more), data: data.slice(y * width * 4, (y + rows + Number(more)) * width * 4) };
    Object.assign(strip, { y0: y, more });
    const actual = renderOutput(band, { strength }, strip).data.subarray(0, rows * width * 4);
    assert.deepEqual(actual, expected.subarray(y * width * 4, (y + rows) * width * 4));
  }
}
for (const mode of OUTPUT_MODES) {
  const adjustments = { brightness: 13, gamma: 1 / 2.2 }, options = { mode, strength: .73, levels: 4 };
  const expected = renderOutputCells(processRGBA(image, adjustments), options).values;
  const strip = { y0: 0, more: true, carry: null };
  for (let y = 0; y < height; y += 9) {
    const rows = Math.min(9, height - y), more = y + rows < height;
    const band = { width, height: rows + Number(more), data: data.slice(y * width * 4, (y + rows + Number(more)) * width * 4) };
    Object.assign(strip, { y0: y, more });
    assert.deepEqual(renderExportCells(band, adjustments, options, strip).values.subarray(0, rows * width),
      expected.subarray(y * width, (y + rows) * width));
  }
}
console.log('PASS: 36 frozen processing hashes, packed decisions, and diffusion carry');
