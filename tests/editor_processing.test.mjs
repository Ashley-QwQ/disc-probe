// Run without npm packages: node --test tests/editor_processing.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_ADJUSTMENTS, DEFAULT_OUTPUT, OUTPUT_MODES, normalizeAdjustments,
  normalizeOutput, normalizeCurve, processRGBA, applyChromaKey, autoLevels,
  histogram, renderOutput, physicalPreview, estimateGrid,
} from "../discprobe/editor_assets/processing.mjs";

function image(width, height, fn) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const value = fn(x, y);
    data.set(typeof value === "number" ? [value, value, value, 255] : value, (y * width + x) * 4);
  }
  return { width, height, data };
}
const grays = im => Array.from(im.data).filter((_, i) => i % 4 === 0);
const alphas = im => Array.from(im.data).filter((_, i) => i % 4 === 3);
const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
const flat = (n = 32, gray = 128) => image(n, n, () => gray);
const ramp = image(256, 1, x => x);

// Vary both axes, all three channels, and local detail. A horizontal ramp alone
// would make a regression that repeats one scanline look like a valid image.
function texturedImage(width, height, transparent = false) {
  return image(width, height, (x, y) => {
    const u = x / Math.max(1, width - 1), v = y / Math.max(1, height - 1);
    const r = Math.round(125 + 70 * Math.sin(5 * u + 3 * v) + 30 * Math.cos(15 * v));
    const g = Math.round(120 + 65 * Math.cos(4 * u - 7 * v) + 30 * Math.sin(17 * u));
    const b = Math.round(125 + 70 * Math.sin(8 * u * v + 2 * v) + 25 * Math.cos(11 * (u + v)));
    return [r, g, b, transparent ? ((x * 17 + y * 29) % 7 ? 255 : 0) : 255];
  });
}

function transpose(source) {
  return image(source.height, source.width, (x, y) =>
    source.data.subarray((x * source.width + y) * 4, (x * source.width + y) * 4 + 4));
}

// Deliberately independent of the production streaming/ring implementation:
// build a complete summed-area table from an unmodified source at every stage.
function referenceSpatial(values, source, radius, apply) {
  const { width: w, height: h, data } = source, stride = w + 1;
  const r = Math.max(1, Math.min(Math.ceil(radius), Math.max(w, h)));
  const sums = new Float64Array(stride * (h + 1));
  const weights = new Float64Array(sums.length);
  for (let y = 0; y < h; y++) {
    let sum = 0, weight = 0;
    for (let x = 0; x < w; x++) {
      const pixel = y * w + x, i = (y + 1) * stride + x + 1, alpha = data[pixel * 4 + 3] / 255;
      sum += values[pixel] * alpha; weight += alpha;
      sums[i] = sums[i - stride] + sum;
      weights[i] = weights[i - stride] + weight;
    }
  }
  const result = values.slice();
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x;
    if (!data[i * 4 + 3]) continue;
    const left = Math.max(0, x - r), right = Math.min(w, x + r + 1);
    const top = Math.max(0, y - r), bottom = Math.min(h, y + r + 1);
    const area = table => table[bottom * stride + right] - table[top * stride + right]
      - table[bottom * stride + left] + table[top * stride + left];
    const weight = area(weights);
    if (weight > 1e-8) result[i] = Math.min(1, Math.max(0, apply(values[i], area(sums) / weight)));
  }
  return result;
}

test("default tone is identity for gray and uses Pillow-compatible RGB weights", () => {
  assert.deepEqual(grays(processRGBA(ramp)), grays(ramp));
  const source = image(4, 1, x => [[255, 0, 0, 255], [0, 255, 0, 127], [0, 0, 255, 1], [20, 20, 20, 0]][x]);
  const result = processRGBA(source);
  assert.deepEqual(grays(result), [76, 150, 29, 20]);
  assert.deepEqual(alphas(result), [255, 127, 1, 0]);
  assert.equal(result.histogram.reduce((a, b) => a + b, 0), 3);
});

test("non-square color images preserve both axes and every neutral pixel", () => {
  for (const [width, height] of [[317, 193], [193, 317], [1040, 781]]) {
    const source = texturedImage(width, height), before = source.data.slice();
    const result = processRGBA(source);
    assert.deepEqual(source.data, before);
    assert.equal(result.width, width); assert.equal(result.height, height);
    let verticalChanges = 0, horizontalChanges = 0;
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const expected = Math.round(source.data[i] * 0.299 + source.data[i + 1] * 0.587 + source.data[i + 2] * 0.114);
      assert.ok(Math.abs(result.data[i] - expected) <= 1, `pixel ${x}, ${y} of ${width}×${height}`);
      if (x && result.data[i] !== result.data[i - 4]) horizontalChanges++;
      if (y && result.data[i] !== result.data[i - width * 4]) verticalChanges++;
    }
    assert.ok(horizontalChanges > width * height / 20, 'horizontal subject structure remains');
    assert.ok(verticalChanges > width * height / 20, 'vertical subject structure remains, not repeated gray bars');
  }
});

test("Portrait processing of landscape and portrait textures is transpose-equivariant", () => {
  for (const [width, height] of [[317, 193], [193, 317]]) {
    const source = texturedImage(width, height);
    for (const previewScale of [0.2, 1]) {
      for (const levels of [{}, { blackPoint: 58, whitePoint: 215 }]) {
        const options = { shadows: 12, highlights: -12, clarity: 8, denoise: 10, ...levels };
        const result = processRGBA(source, options, { previewScale });
        const rotated = transpose(processRGBA(transpose(source), options, { previewScale }));
        for (let i = 0; i < result.data.length; i += 4) {
          assert.ok(Math.abs(result.data[i] - rotated.data[i]) <= 1,
            `Portrait pixel ${i / 4} of ${width}×${height}, previewScale ${previewScale}`);
        }
        assert.ok(result.histogram.filter(n => n > 0).length > 100, 'photo-like tones remain distributed');
      }
    }
  }
});

test("Portrait spatial stages match an independent 2D reference on non-square alpha textures", () => {
  for (const [width, height] of [[173, 97], [97, 173]]) {
    const source = texturedImage(width, height, true);
    for (const previewScale of [0.2, 1]) {
      let values = Float32Array.from({ length: width * height }, (_, i) => {
        const j = i * 4;
        return (source.data[j] * 0.299 + source.data[j + 1] * 0.587 + source.data[j + 2] * 0.114) / 255;
      });
      const denoiseRadius = 1.3 * previewScale, effective = 0.1 * Math.min(1, denoiseRadius);
      values = referenceSpatial(values, source, denoiseRadius,
        (v, b) => v + effective * (b - v) / (1 + ((v - b) / 0.03) ** 2));
      values = referenceSpatial(values, source, 20 * previewScale,
        (v, b) => v + 0.08 * Math.min(1, 20 * previewScale) * (v - b));
      const result = processRGBA(source, { clarity: 8, denoise: 10 }, { previewScale });
      for (let i = 0; i < values.length; i++) {
        assert.ok(Math.abs(result.data[i * 4] - Math.round(values[i] * 255)) <= 1,
          `independent reference at ${i} of ${width}×${height}, previewScale ${previewScale}`);
      }
      assert.deepEqual(alphas(result), alphas(source));
    }
  }
});

test("normalizers make independent settings and keep defaults immutable", () => {
  const a = normalizeAdjustments(), b = normalizeAdjustments();
  a.curve[0][1] = 1; a.mix[0] = 9;
  assert.equal(b.curve[0][1], 0);
  assert.equal(DEFAULT_ADJUSTMENTS.curve[0][1], 0);
  assert.equal(DEFAULT_ADJUSTMENTS.mix[0], 0.299);
  assert.equal(normalizeOutput().levels, DEFAULT_OUTPUT.levels);
  assert.equal(normalizeAdjustments({ unknown: "ignored" }).unknown, undefined);
});

test("invalid, nonfinite and out-of-range settings fail before processing", () => {
  for (const value of [NaN, Infinity, -Infinity, "1", null]) {
    assert.throws(() => normalizeAdjustments({ gamma: value }));
    assert.throws(() => normalizeOutput({ strength: value }));
  }
  assert.throws(() => normalizeAdjustments({ exposure: 6 }));
  assert.throws(() => normalizeAdjustments({ blackPoint: 200, whitePoint: 100 }));
  assert.throws(() => normalizeAdjustments({ blackPoint: 0, whitePoint: 0 }));
  assert.throws(() => normalizeAdjustments({ mix: [0, 0, 0] }));
  assert.throws(() => normalizeAdjustments({ mix: [1, -1, 1] }));
  assert.throws(() => normalizeAdjustments({ invert: "false" }));
  assert.throws(() => normalizeOutput({ cellSize: 0 }));
  assert.throws(() => normalizeOutput({ cellSize: 1.5 }));
  assert.throws(() => normalizeOutput({ mode: "made-up" }));
  assert.throws(() => normalizeOutput({ matrixSize: 3 }));
  assert.throws(() => normalizeOutput({ seed: -1 }));
  assert.throws(() => normalizeOutput({ levels: 257 }));
  assert.throws(() => normalizeAdjustments([]));
  assert.throws(() => processRGBA(ramp, {}, "invalid"));
  assert.throws(() => applyChromaKey(ramp, 3));
  assert.throws(() => physicalPreview(ramp, []));
});

test("curve input must be ordered and covered, output LUT must be monotone", () => {
  for (const curve of [[], [[0, 0]], [[0.1, 0], [1, 1]], [[0, 0], [0, 0.2], [1, 1]], [[0, NaN], [1, 1]]]) {
    assert.throws(() => normalizeCurve(curve));
  }
  assert.deepEqual(normalizeCurve([[0, 1], [1, 0]]), [[0, 1], [1, 0]]);
  assert.throws(() => normalizeOutput({ outputCurve: [[0, 1], [1, 0]] }));
});

test("exposure operates in linear light and gamma brightens midtones", () => {
  const exposed = grays(processRGBA(ramp, { exposure: 1 }));
  const expected = Math.round((1.055 * ((((128 / 255 + 0.055) / 1.055) ** 2.4 * 2) ** (1 / 2.4)) - 0.055) * 255);
  assert.ok(Math.abs(exposed[128] - expected) <= 1);
  assert.equal(exposed[0], 0); assert.equal(exposed[255], 255);
  const gamma = grays(processRGBA(ramp, { gamma: 2 }));
  assert.ok(Math.abs(gamma[128] - Math.sqrt(128 / 255) * 255) <= 1);
  assert.equal(gamma[0], 0); assert.equal(gamma[255], 255);
});

test("input levels, inversion and custom curve have distinct correct effects", () => {
  const levels = grays(processRGBA(ramp, { blackPoint: 50, whitePoint: 200 }));
  assert.equal(levels[50], 0); assert.equal(levels[200], 255);
  assert.ok(Math.abs(levels[125] - 128) <= 1);
  assert.deepEqual(grays(processRGBA(ramp, { invert: true })), grays(ramp).map(v => 255 - v));
  const curve = grays(processRGBA(ramp, { curve: [[0, 0], [0.5, 0.25], [1, 1]] }));
  assert.ok(Math.abs(curve[128] - 65) <= 1);
});

test("tone, compression and channel mixer controls are active", () => {
  const source = image(3, 1, x => [64, 128, 192][x]);
  const base = grays(processRGBA(source));
  for (const [key, value] of Object.entries({ brightness: 20, contrast: 20, highlights: 40, shadows: 40,
    highlightCompression: 50, shadowCompression: 50 })) {
    assert.notDeepEqual(grays(processRGBA(source, { [key]: value })), base, key);
  }
  assert.ok(grays(processRGBA(ramp, { shadowCompression: 50 }))[0] > 0);
  assert.ok(grays(processRGBA(ramp, { highlightCompression: 50 }))[255] < 255);
  const colors = image(3, 1, x => [[255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]][x]);
  assert.deepEqual(grays(processRGBA(colors, { mix: [1, 0, 0] })), [255, 0, 0]);
  assert.deepEqual(grays(processRGBA(colors, { mix: [2, 2, 0] })), [128, 128, 0]);
});

test("strong shadow/highlight compression never reverses brightness order", () => {
  for (const options of [{ shadowCompression: 100 }, { highlightCompression: 100 },
    { shadowCompression: 100, highlightCompression: 100 }]) {
    const values = grays(processRGBA(ramp, options));
    for (let i = 1; i < values.length; i++) assert.ok(values[i] >= values[i - 1], `${JSON.stringify(options)} at ${i}`);
  }
});

test("spatial filters and grain do not mutate their input or alpha", () => {
  const source = image(24, 17, (x, y) => [70 + ((x * 13 + y * 7) % 100), 120, 140, (x * 19) % 256]);
  const before = source.data.slice();
  const result = processRGBA(source, { denoise: 20, clarity: 15, texture: 10, sharpen: 25, grain: 10 });
  assert.deepEqual(source.data, before);
  assert.deepEqual(alphas(result), alphas(source));
  assert.notDeepEqual(grays(result), grays(processRGBA(source)));
});

test("sharpen threshold, radius, texture and clarity are functional", () => {
  const source = image(31, 13, (x, y) => x === 15 ? 160 : 100 + (x > 15 ? 10 : 0));
  const base = grays(processRGBA(source));
  for (const key of ["sharpen", "clarity", "texture"]) {
    assert.notDeepEqual(grays(processRGBA(source, { [key]: 60 })), base, key);
  }
  assert.deepEqual(grays(processRGBA(source, { sharpen: 100, sharpenThreshold: 255 })), base);
  assert.notDeepEqual(grays(processRGBA(source, { sharpen: 60, sharpenRadius: 1 })),
    grays(processRGBA(source, { sharpen: 60, sharpenRadius: 8 })));
  assert.notDeepEqual(grays(processRGBA(source, { sharpen: 60 }, { previewScale: 1 })),
    grays(processRGBA(source, { sharpen: 60 }, { previewScale: 0.1 })));
});

test("denoise reduces small variations and transparent RGB does not bleed", () => {
  const noisy = image(25, 25, (x, y) => 128 + (x % 2 ? 8 : -8) + (y % 2 ? 5 : -5));
  const variance = a => { const m = mean(a); return mean(a.map(v => (v - m) ** 2)); };
  assert.ok(variance(grays(processRGBA(noisy, { denoise: 80 }))) < variance(grays(noisy)));
  const dark = image(9, 9, (x, y) => x < 3 ? [0, 0, 0, 0] : [128, 128, 128, 255]);
  const light = image(9, 9, (x, y) => x < 3 ? [255, 255, 255, 0] : [128, 128, 128, 255]);
  const a = processRGBA(dark, { denoise: 100, sharpen: 100, clarity: 100 });
  const b = processRGBA(light, { denoise: 100, sharpen: 100, clarity: 100 });
  for (let i = 0; i < a.data.length; i += 4) if (a.data[i + 3]) assert.equal(a.data[i], b.data[i]);
});

test("streamed box filter agrees with a non-streaming alpha-weighted reference", () => {
  const source = image(13, 9, (x, y) => { const g = (x * 43 + y * 71) % 256; return [g, g, g, (x + y) % 5 ? 255 : 0]; });
  const result = physicalPreview(source, { radiusPixels: 2 });
  for (let y = 0; y < source.height; y++) for (let x = 0; x < source.width; x++) {
    const i = (y * source.width + x) * 4;
    if (!source.data[i + 3]) continue;
    let sum = 0, weight = 0;
    for (let yy = Math.max(0, y - 2); yy <= Math.min(source.height - 1, y + 2); yy++) {
      for (let xx = Math.max(0, x - 2); xx <= Math.min(source.width - 1, x + 2); xx++) {
        const j = (yy * source.width + xx) * 4, a = source.data[j + 3] / 255;
        sum += source.data[j] * a; weight += a;
      }
    }
    assert.ok(Math.abs(result.data[i] - Math.round(sum / weight)) <= 1, `at ${x}, ${y}`);
  }
  assert.deepEqual(alphas(result), alphas(source));
});

test("grain is deterministic per seed and different seeds change the pattern", () => {
  const source = flat();
  assert.deepEqual(processRGBA(source, { grain: 25, seed: 42 }).data, processRGBA(source, { grain: 25, seed: 42 }).data);
  assert.notDeepEqual(processRGBA(source, { grain: 25, seed: 42 }).data, processRGBA(source, { grain: 25, seed: 43 }).data);
});

test("auto levels excludes transparent RGB and handles uniform or empty images", () => {
  const source = image(4, 1, x => [[0, 0, 0, 0], [50, 50, 50, 255], [200, 200, 200, 255], [255, 255, 255, 0]][x]);
  assert.deepEqual(autoLevels(source), { blackPoint: 50, whitePoint: 200 });
  assert.deepEqual(autoLevels(flat(10, 128)), { blackPoint: 0, whitePoint: 255 });
  assert.deepEqual(autoLevels(image(2, 1, () => [40, 20, 80, 0])), { blackPoint: 0, whitePoint: 255 });
  assert.equal(histogram(source).reduce((a, b) => a + b, 0), 2);
});

test("chroma key previews are non-destructive and preserve existing transparency", () => {
  const source = image(4, 1, x => [[255, 255, 255, 255], [255, 255, 254, 255], [255, 0, 0, 128], [10, 20, 30, 0]][x]);
  const copy = source.data.slice();
  const exact = applyChromaKey(source, { color: [255, 255, 255], tolerance: 0 });
  assert.deepEqual(alphas(exact), [0, 255, 128, 0]);
  assert.deepEqual(source.data, copy);
  const loose = applyChromaKey(source, { color: [255, 255, 255], tolerance: 1 });
  assert.deepEqual(alphas(loose), [0, 0, 128, 0]);
  assert.deepEqual(alphas(applyChromaKey(source, { color: [0, 0, 0], tolerance: 100 })), [0, 0, 0, 0]);
});

test("key feathering produces partial alpha without changing foreground RGB", () => {
  const source = image(1, 1, () => [128, 128, 128, 200]);
  const output = applyChromaKey(source, { color: [255, 255, 255], tolerance: 30, softness: 40 });
  assert.ok(output.data[3] > 0 && output.data[3] < 200);
  assert.deepEqual(Array.from(output.data.slice(0, 3)), [128, 128, 128]);
  assert.throws(() => applyChromaKey(source, { color: [1, 2] }));
  assert.throws(() => applyChromaKey(source, { tolerance: NaN }));
});

test("grayscale output posterizes to requested artistic levels", () => {
  const result = renderOutput(ramp, { mode: "grayscale", levels: 4 });
  assert.deepEqual([...new Set(grays(result))], [0, 85, 170, 255]);
  assert.deepEqual(grays(renderOutput(ramp, { mode: "grayscale" })), grays(ramp));
  const mapped = renderOutput(ramp, { mode: "grayscale", outputCurve: [[0, 0], [0.5, 0.8], [1, 1]] });
  assert.ok(grays(mapped)[128] > 200);
});

for (const mode of OUTPUT_MODES.filter(m => m !== "grayscale")) {
  test(`${mode} output has only two RGB endpoints and preserves alpha`, () => {
    const source = image(64, 17, (x, y) => [(x * 4) % 256, (y * 15) % 256, 128, (x * 37 + y * 13) % 256]);
    const before = source.data.slice();
    const result = renderOutput(source, { mode, levels: 7 });
    for (let i = 0; i < result.data.length; i += 4) {
      assert.ok(result.data[i] === 0 || result.data[i] === 255);
      assert.equal(result.data[i + 1], result.data[i]);
      assert.equal(result.data[i + 2], result.data[i]);
    }
    assert.deepEqual(alphas(result), alphas(source));
    assert.deepEqual(source.data, before);
  });
  test(`${mode} keeps pure endpoints, including extreme threshold settings`, () => {
    for (const threshold of [0, 0.5, 1]) {
      assert.ok(grays(renderOutput(flat(8, 0), { mode, threshold })).every(v => v === 0));
      assert.ok(grays(renderOutput(flat(8, 255), { mode, threshold })).every(v => v === 255));
    }
  });
}

test("dither strength zero agrees with nearest-threshold output", () => {
  const source = image(30, 11, (x, y) => (x * 7 + y * 13) % 256);
  const expected = renderOutput(source, { mode: "threshold" });
  for (const mode of ["floyd-steinberg", "ordered", "blue-noise", "clustered"]) {
    assert.deepEqual(renderOutput(source, { mode, strength: 0 }).data, expected.data, mode);
  }
});

test("Floyd–Steinberg and ranked masks preserve average flat-field coverage", () => {
  for (const mode of ["floyd-steinberg", "ordered", "blue-noise", "clustered"]) {
    for (const gray of [32, 96, 128, 192, 224]) {
      const result = renderOutput(flat(128, gray), { mode, matrixSize: 16 });
      assert.ok(Math.abs(mean(grays(result)) / 255 - gray / 255) < 0.015, `${mode}: ${gray}`);
    }
  }
});

test("blue-noise tile is balanced and suppresses low spatial frequencies", () => {
  const result = renderOutput(flat(32, 128), { mode: "blue-noise" });
  const values = grays(result).map(v => v / 255), average = mean(values);
  assert.equal(values.reduce((a, b) => a + b, 0), 514);
  let lowEnergy = 0;
  for (let fy = -4; fy <= 4; fy++) for (let fx = -4; fx <= 4; fx++) {
    if (fx * fx + fy * fy === 0 || fx * fx + fy * fy > 16) continue;
    let re = 0, im = 0;
    for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) {
      const phase = 2 * Math.PI * (fx * x + fy * y) / 32, value = values[y * 32 + x] - average;
      re += value * Math.cos(phase); im += value * Math.sin(phase);
    }
    lowEnergy += re * re + im * im;
  }
  const totalEnergy = 1024 * values.reduce((sum, v) => sum + (v - average) ** 2, 0);
  assert.ok(lowEnergy / totalEnergy < 0.005, `low-frequency share ${lowEnergy / totalEnergy}`);
});

test("matrix size, orientation, seed and output curve change the pattern", () => {
  const source = flat(64, 91);
  assert.notDeepEqual(renderOutput(source, { mode: "ordered", matrixSize: 2 }).data,
    renderOutput(source, { mode: "ordered", matrixSize: 8 }).data);
  assert.notDeepEqual(renderOutput(source, { mode: "clustered", angle: 0 }).data,
    renderOutput(source, { mode: "clustered", angle: 27 }).data);
  const a = renderOutput(source, { mode: "blue-noise", seed: 42 });
  assert.deepEqual(a.data, renderOutput(source, { mode: "blue-noise", seed: 42 }).data);
  assert.notDeepEqual(a.data, renderOutput(source, { mode: "blue-noise", seed: 43 }).data);
  assert.ok(mean(grays(renderOutput(source, { mode: "ordered", outputCurve: [[0, 0], [0.5, 0.8], [1, 1]] })))
    > mean(grays(renderOutput(source, { mode: "ordered" }))));
});

test("ordered rotations are stable at equivalent cardinal angles", () => {
  const source = flat(64, 128);
  for (const mode of ["ordered", "blue-noise", "clustered"]) {
    const base = renderOutput(source, { mode, angle: 0 }).data;
    assert.deepEqual(renderOutput(source, { mode, angle: 360 }).data, base, mode);
    assert.deepEqual(renderOutput(source, { mode, angle: -360 }).data, base, mode);
    assert.deepEqual(renderOutput(source, { mode, angle: 90 }).data,
      renderOutput(source, { mode, angle: -270 }).data, mode);
  }
});

test("cell size averages coverage then replicates cells, including partial edges", () => {
  const source = image(5, 3, (x, y) => x % 2 ? 255 : 0);
  const result = renderOutput(source, { mode: "threshold", cellSize: 2 });
  assert.deepEqual(grays(result).slice(0, 5), [255, 255, 255, 255, 0]);
  assert.deepEqual(grays(result).slice(0, 5), grays(result).slice(5, 10));
  const graded = renderOutput(source, { mode: "grayscale", cellSize: 2 });
  assert.ok(Math.abs(grays(graded)[0] - 128) <= 1);
});

test("transparent RGB never contributes to output coverage or diffused error", () => {
  const a = image(20, 20, (x, y) => x % 3 ? [128, 128, 128, 255] : [0, 0, 0, 0]);
  const b = image(20, 20, (x, y) => x % 3 ? [128, 128, 128, 255] : [255, 255, 255, 0]);
  for (const cellSize of [1, 2, 3]) {
    assert.deepEqual(renderOutput(a, { cellSize }).data, renderOutput(b, { cellSize }).data);
  }
});

test("invalid image shapes are rejected rather than silently overallocating", () => {
  assert.throws(() => processRGBA({ width: 2, height: 2, data: new Uint8Array(3) }));
  assert.throws(() => processRGBA({ width: 1.5, height: 2, data: new Uint8Array(12) }));
  assert.throws(() => renderOutput({ width: 12000, height: 12000, data: new Uint8Array() }));
  assert.throws(() => histogram({ width: 1, height: 1, data: [0, 0, 0, 255] }));
});

test("grid warnings use real 20 micrometre writer resolution, not optical promises", () => {
  assert.deepEqual(estimateGrid(6000), { pixelMicrons: 20, cellMicrons: 20, designGridMicrons: 20, warnings: [] });
  assert.equal(estimateGrid(6000, 4).cellMicrons, 80);
  assert.equal(estimateGrid(12000).warnings.length, 2);
  assert.equal(estimateGrid(1200).pixelMicrons, 100);
  assert.ok(estimateGrid(1200).warnings.length > 0);
});

test("schematic preview with radius zero keeps the raster unchanged", () => {
  assert.deepEqual(physicalPreview(ramp, { radiusPixels: 0 }).data, ramp.data);
});
