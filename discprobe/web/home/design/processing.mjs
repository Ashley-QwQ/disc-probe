/**
 * Disc editor image operations. No DOM, network, packages, or implicit state.
 *
 * All images use straight-alpha, 8-bit sRGB RGBA. Artistic grayscale uses
 * normalized encoded RGB weights (the default agrees with Pillow's L mode).
 * Exposure alone is applied in linear light. Gamma > 1 brightens midtones.
 * Spatial radii are in final-output pixels, multiplied by previewScale.
 *
 * The existing writer has a 6000 x 6000 / 120 mm / 20 micrometre design grid.
 * Binary output modes therefore make a TWO-endpoint raster; `levels` controls
 * artistic posterization before that conversion, NOT physical texture count.
 * An output curve maps target gray to light-endpoint coverage. The identity is
 * uncalibrated; a user-provided curve is not proof of optical accuracy.
 */

const IDENTITY = Object.freeze([Object.freeze([0, 0]), Object.freeze([1, 1])]);
const DEFAULT_MIX = Object.freeze([0.299, 0.587, 0.114]);

export const DEFAULT_ADJUSTMENTS = Object.freeze({
  exposure: 0, brightness: 0, contrast: 0, highlights: 0, shadows: 0,
  blackPoint: 0, whitePoint: 255, gamma: 1, invert: false,
  curve: IDENTITY, mix: DEFAULT_MIX,
  highlightCompression: 0, shadowCompression: 0,
  clarity: 0, texture: 0, denoise: 0,
  sharpen: 0, sharpenRadius: 1, sharpenThreshold: 0,
  grain: 0, seed: 1,
});

export const DEFAULT_OUTPUT = Object.freeze({
  mode: "floyd-steinberg", levels: 256, strength: 1,
  matrixSize: 8, angle: 0, seed: 1, cellSize: 1, threshold: 0.5,
  outputCurve: IDENTITY,
});

export const OUTPUT_MODES = Object.freeze([
  "threshold", "floyd-steinberg", "ordered", "blue-noise", "clustered", "grayscale",
]);

const MAX_PIXELS = 36_000_000;
const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));
const byte = x => Math.round(clamp(x) * 255);
const smoothstep = (a, b, x) => {
  const t = clamp((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};

function number(value, lo, hi, name, integer = false) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < lo || value > hi
      || (integer && !Number.isInteger(value))) {
    throw new RangeError(`${name} must be ${integer ? "an integer " : ""}between ${lo} and ${hi}`);
  }
  return value;
}

function record(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${name} must be an object`);
  }
}

/** Strict, copied point lists. Artistic curves may be non-monotone. */
export function normalizeCurve(points, monotone = false) {
  if (!Array.isArray(points) || points.length < 2 || points.length > 256) {
    throw new RangeError("curve must have 2 to 256 [input, output] points");
  }
  const out = points.map((p, i) => {
    if (!Array.isArray(p) || p.length !== 2) throw new TypeError(`curve point ${i} must be [input, output]`);
    return [number(p[0], 0, 1, "curve input"), number(p[1], 0, 1, "curve output")];
  });
  if (out[0][0] !== 0 || out[out.length - 1][0] !== 1) {
    throw new RangeError("curve inputs must begin at 0 and end at 1");
  }
  for (let i = 1; i < out.length; i++) {
    if (out[i][0] <= out[i - 1][0]) throw new RangeError("curve inputs must be strictly increasing");
    if (monotone && out[i][1] < out[i - 1][1]) throw new RangeError("output curve must be monotone increasing");
  }
  return out;
}

function normalizeMix(mix) {
  if (!Array.isArray(mix) || mix.length !== 3) throw new TypeError("mix must have red, green, blue weights");
  const out = mix.map(v => number(v, 0, 4, "channel weight"));
  const sum = out[0] + out[1] + out[2];
  if (sum <= 0) throw new RangeError("at least one channel weight must be positive");
  return out.map(v => v / sum);
}

export function normalizeAdjustments(options = {}) {
  record(options, "adjustments");
  const out = { ...DEFAULT_ADJUSTMENTS, ...options };
  for (const key of ["brightness", "contrast", "highlights", "shadows", "clarity", "texture"]) {
    out[key] = number(out[key], -100, 100, key);
  }
  for (const key of ["highlightCompression", "shadowCompression", "denoise", "sharpen", "grain"]) {
    out[key] = number(out[key], 0, 100, key);
  }
  out.exposure = number(out.exposure, -5, 5, "exposure");
  out.blackPoint = number(out.blackPoint, 0, 255, "blackPoint");
  out.whitePoint = number(out.whitePoint, 0, 255, "whitePoint");
  if (out.blackPoint >= out.whitePoint) throw new RangeError("blackPoint must be lower than whitePoint");
  out.gamma = number(out.gamma, 0.1, 5, "gamma");
  out.sharpenRadius = number(out.sharpenRadius, 0.1, 32, "sharpenRadius");
  out.sharpenThreshold = number(out.sharpenThreshold, 0, 255, "sharpenThreshold");
  out.seed = number(out.seed, 0, 0xffffffff, "seed", true);
  if (typeof out.invert !== "boolean") throw new TypeError("invert must be a boolean");
  out.curve = normalizeCurve(out.curve);
  out.mix = normalizeMix(out.mix);
  // Only known, serializable settings leave the boundary.
  return Object.fromEntries(Object.keys(DEFAULT_ADJUSTMENTS).map(k => [k, out[k]]));
}

export function normalizeOutput(options = {}) {
  record(options, "output options");
  const out = { ...DEFAULT_OUTPUT, ...options };
  if (!OUTPUT_MODES.includes(out.mode)) throw new RangeError("unknown grayscale output mode");
  out.levels = number(out.levels, 2, 256, "levels", true);
  out.strength = number(out.strength, 0, 1, "strength");
  if (![2, 4, 8, 16, 32].includes(out.matrixSize)) throw new RangeError("matrixSize must be 2, 4, 8, 16, or 32");
  out.angle = number(out.angle, -360, 360, "angle");
  out.seed = number(out.seed, 0, 0xffffffff, "seed", true);
  out.cellSize = number(out.cellSize, 1, 256, "cellSize", true);
  out.threshold = number(out.threshold, 0, 1, "threshold");
  out.outputCurve = normalizeCurve(out.outputCurve, true);
  return Object.fromEntries(Object.keys(DEFAULT_OUTPUT).map(k => [k, out[k]]));
}

function imageInfo(image) {
  record(image, "image");
  const width = number(image.width, 1, 24000, "image width", true);     // a 5 µm export band is 24000 wide
  const height = number(image.height, 1, 12000, "image height", true);
  if (width * height > MAX_PIXELS) throw new RangeError("image exceeds the 36 megapixel editor limit");
  if (!(image.data instanceof Uint8Array || image.data instanceof Uint8ClampedArray)
      || image.data.length !== width * height * 4) {
    throw new TypeError("image data must be a width × height × 4 byte RGBA array");
  }
  return { width, height, data: image.data };
}

function mapCurve(points, x) {
  x = clamp(x);
  for (let i = 1; i < points.length; i++) {
    if (x <= points[i][0]) {
      const a = points[i - 1], b = points[i];
      const t = (x - a[0]) / (b[0] - a[0]);
      return a[1] + t * (b[1] - a[1]);
    }
  }
  return points[points.length - 1][1];
}

function hash32(value) {
  let x = value >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x7feb352d);
  x = Math.imul(x ^ (x >>> 15), 0x846ca68b);
  return (x ^ (x >>> 16)) >>> 0;
}

const linear = x => x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
const encoded = x => x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055;

function toneTable(a) {
  const table = new Float32Array(4097);
  const exposure = 2 ** a.exposure, contrast = 2 ** (a.contrast / 50);
  const black = a.blackPoint / 255, span = (a.whitePoint - a.blackPoint) / 255;
  for (let i = 0; i < table.length; i++) {
    let v = i / 4096;
    if (a.exposure) v = encoded(linear(v) * exposure);
    v = (v - black) / span;
    v = (v - 0.5) * contrast + 0.5 + a.brightness / 200;
    const bounded = clamp(v);
    v += 2 * a.shadows / 100 * bounded * (1 - bounded) ** 2;
    v += 2 * a.highlights / 100 * bounded ** 2 * (1 - bounded);
    v = clamp(v);
    // Shoulder/toe compression reserves headroom; it cannot recover clipped source data.
    // smoothstep's maximum derivative over a half-range is 3. Keeping the
    // amplitude below 1/3 prevents a strong toe/shoulder from reversing tones.
    v += 0.3 * a.shadowCompression / 100 * (1 - smoothstep(0, 0.5, v));
    v -= 0.3 * a.highlightCompression / 100 * smoothstep(0.5, 1, v);
    v = clamp(v) ** (1 / a.gamma);
    v = mapCurve(a.curve, v);
    table[i] = a.invert ? 1 - v : v;
  }
  return table;
}

/**
 * Separable alpha-weighted box filter, streamed through a small row ring.
 * The callback may replace values in place: each future horizontal row is
 * calculated before its source values can be changed. No full-size blur copies.
 * Transparent source RGB cannot bleed into opaque edges.
 */
function spatial(values, image, radius, apply) {
  const { width: w, height: h, data } = image;
  const r = Math.max(1, Math.min(Math.ceil(radius), Math.max(w, h)));
  const rows = Math.min(h, 2 * r + 1);
  const sums = new Float32Array(rows * w), weights = new Float32Array(rows * w);
  const vertical = new Float64Array(w), verticalWeight = new Float64Array(w);
  let added = -1, removed = 0;
  function addRow(y) {
    const ring = (y % rows) * w, offset = y * w;
    let sum = 0, weight = 0;
    const push = (x, sign) => {
      const a = data[(offset + x) * 4 + 3] / 255;
      sum += sign * values[offset + x] * a;
      weight += sign * a;
    };
    for (let x = 0; x <= Math.min(w - 1, r); x++) push(x, 1);
    for (let x = 0; x < w; x++) {
      sums[ring + x] = sum;
      weights[ring + x] = weight;
      vertical[x] += sums[ring + x];
      verticalWeight[x] += weights[ring + x];
      if (x - r >= 0) push(x - r, -1);
      if (x + r + 1 < w) push(x + r + 1, 1);
    }
  }
  for (let y = 0; y < h; y++) {
    const first = Math.max(0, y - r), last = Math.min(h - 1, y + r);
    while (removed < first) {
      const ring = (removed++ % rows) * w;
      for (let x = 0; x < w; x++) {
        vertical[x] -= sums[ring + x];
        verticalWeight[x] -= weights[ring + x];
      }
    }
    while (added < last) addRow(++added);
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (data[i * 4 + 3] && verticalWeight[x] > 1e-8) {
        values[i] = clamp(apply(values[i], vertical[x] / verticalWeight[x]));
      }
    }
  }
}

function toRGBA(values, image) {
  const data = new Uint8ClampedArray(image.data.length);
  for (let i = 0; i < values.length; i++) {
    const j = i * 4, v = byte(values[i]);
    data[j] = data[j + 1] = data[j + 2] = v;
    data[j + 3] = image.data[j + 3];
  }
  return { width: image.width, height: image.height, data };
}

/** Does not mutate the source; alpha is kept byte-for-byte. */
export function processRGBA(input, options = {}, context = {}) {
  const image = imageInfo(input), a = normalizeAdjustments(options);
  record(context, "processing context");
  const scale = number(context.previewScale ?? 1, 1 / 1000, 100, "previewScale");
  const table = toneTable(a), values = new Float32Array(image.width * image.height);
  for (let i = 0; i < values.length; i++) {
    const j = 4 * i;
    const v = (image.data[j] * a.mix[0] + image.data[j + 1] * a.mix[1] + image.data[j + 2] * a.mix[2]) / 255 * 4096;
    const k = Math.min(4095, Math.floor(v)), t = v - k;
    values[i] = table[k] + (table[k + 1] - table[k]) * t;
  }
  if (a.denoise) {
    const amount = a.denoise / 100, radius = (1 + amount * 3) * scale;
    const effective = amount * Math.min(1, radius), edge = 0.015 + amount * 0.15;
    spatial(values, image, radius, (v, b) => v + effective * (b - v) / (1 + ((v - b) / edge) ** 2));
  }
  for (const [amount, radius] of [[a.clarity, 20 * scale], [a.texture, 3 * scale]]) {
    if (amount) spatial(values, image, radius, (v, b) => v + amount / 100 * Math.min(1, radius) * (v - b));
  }
  if (a.sharpen) {
    const radius = a.sharpenRadius * scale, gain = 2 * a.sharpen / 100 * Math.min(1, radius);
    spatial(values, image, radius, (v, b) => Math.abs(v - b) >= a.sharpenThreshold / 255 ? v + gain * (v - b) : v);
  }
  if (a.grain) {
    const amount = a.grain / 100 * 0.3;
    for (let i = 0; i < values.length; i++) {
      const h = hash32(i ^ a.seed), noise = (h & 65535) / 65535 + (h >>> 16) / 65535 - 1;
      values[i] = clamp(values[i] + amount * noise);
    }
  }
  const output = toRGBA(values, image);
  if (context.histogram !== false) output.histogram = histogram(output);
  return output;
}

/** Luma histogram of visible pixels; fully transparent RGB is ignored. */
export function histogram(input, mix = DEFAULT_MIX) {
  const image = imageInfo(input), m = normalizeMix(mix), bins = new Uint32Array(256);
  for (let i = 0; i < image.data.length; i += 4) {
    if (image.data[i + 3]) bins[Math.round(image.data[i] * m[0] + image.data[i + 1] * m[1] + image.data[i + 2] * m[2])]++;
  }
  return bins;
}

/** 0.5% / 99.5% visible-pixel endpoints; uniform/empty images stay neutral. */
export function autoLevels(input, mix = DEFAULT_MIX) {
  const bins = histogram(input, mix);
  const count = bins.reduce((a, b) => a + b, 0);
  if (!count) return { blackPoint: 0, whitePoint: 255 };
  let blackPoint = 0, whitePoint = 255, sum = 0;
  const cutoff = Math.max(1, Math.ceil(count * 0.005));
  for (let i = 0; i < 256; i++) { sum += bins[i]; if (sum >= cutoff) { blackPoint = i; break; } }
  sum = 0;
  for (let i = 255; i >= 0; i--) { sum += bins[i]; if (sum >= cutoff) { whitePoint = i; break; } }
  return blackPoint < whitePoint ? { blackPoint, whitePoint } : { blackPoint: 0, whitePoint: 255 };
}

/**
 * Non-destructive RGB-distance key; tolerance/softness are percentages of the
 * RGB cube diagonal, not perceptual Delta E. UI must hold this as a draft until
 * the user confirms. Existing alpha is multiplied, never replaced with opaque.
 */
export function applyChromaKey(input, options = {}) {
  const image = imageInfo(input);
  record(options, "chroma key options");
  const color = options.color ?? [255, 255, 255];
  if (!Array.isArray(color) || color.length !== 3) throw new TypeError("key color must be [red, green, blue]");
  color.forEach(v => number(v, 0, 255, "key color", true));
  const tolerance = number(options.tolerance ?? 10, 0, 100, "key tolerance") / 100;
  const softness = number(options.softness ?? 0, 0, 100, "key softness") / 100;
  const data = new Uint8ClampedArray(image.data);
  for (let i = 0; i < data.length; i += 4) {
    if (!data[i + 3]) continue;
    const d = Math.hypot(data[i] - color[0], data[i + 1] - color[1], data[i + 2] - color[2]) / (255 * Math.sqrt(3));
    const keep = d <= tolerance ? 0 : softness ? smoothstep(tolerance, tolerance + softness, d) : 1;
    data[i + 3] = Math.round(data[i + 3] * keep);
  }
  return { width: image.width, height: image.height, data };
}

const bayerCache = new Map(), clusterCache = new Map();
export function bayer(size) {
  if (bayerCache.has(size)) return bayerCache.get(size);
  let n = 1, ranks = new Uint16Array([0]);
  while (n < size) {
    const out = new Uint16Array(n * n * 4), m = n * 2;
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      const v = ranks[y * n + x] * 4;
      out[y * m + x] = v;
      out[y * m + x + n] = v + 2;
      out[(y + n) * m + x] = v + 3;
      out[(y + n) * m + x + n] = v + 1;
    }
    ranks = out; n = m;
  }
  bayerCache.set(size, ranks);
  return ranks;
}

export function clustered(size) {
  if (clusterCache.has(size)) return clusterCache.get(size);
  const center = (size - 1) / 2;
  const pixels = Array.from({ length: size * size }, (_, i) => i);
  pixels.sort((a, b) => {
    const da = (a % size - center) ** 2 + (Math.floor(a / size) - center) ** 2;
    const db = (b % size - center) ** 2 + (Math.floor(b / size) - center) ** 2;
    return da - db || a - b;
  });
  const ranks = new Uint16Array(size * size);
  pixels.forEach((index, rank) => { ranks[index] = rank; });
  clusterCache.set(size, ranks);
  return ranks;
}

// Self-generated toroidal 32 × 32 void-and-cluster rank tile. Gaussian sigma
// 1.5, initial occupancy 102 / 1024 (NumPy default_rng(7353)); stable cluster /
// void exchange in 41 iterations. Rank by removing clusters down to zero,
// filling voids to half occupancy, then removing complement clusters.
// U16LE SHA-256: 00d06603b2277a26039c9162d0450f48a64564669e8c9181504884a1125b071d
// At 50% coverage, 0 < fx²+fy² <= 16 contains 0.0890% of non-DC DFT energy,
// vs 4.7056% for random balanced masks (mean of 1000, RNG seed 99817).
// It repeats every 32 cells, is not aperiodic, and is not an optical model.
const BLUE_NOISE_HEX = `
3621dd33a18125830b38c0c03fe1d233602221705e3ed17a1e53692e027d3f10f230205522e1cc35a08b33004b3dd1a0
0b81012ca3ee02f2071421a92db06e2941943102a91112d604a13c08d33215a23e3871802c301c3f215b0d11e22502e7
3b42240542810e834d2a10173550f838d0c53bc1dc0903882253d71981fe0b902629c11a3ac0e227721d2da398112079
3221a814b3a11d00893cb11c25c20315c24d0351412693210d729803b3a92c636e1c10921f52fc19605b34101116f28e
03737b0b431523c1702f71b90a33da05932e2ce37718400d1c612e30c2510fe17431b2623610733c51351c525f3ec1fb
12a2522b500c10629304438427b2ec19c1ee10c0ac2123c62b13920a91d90673e70d90001542bc0f52923780960e52e4
08618d3df1fd3913250c121b13800436d08c3e82823440f007123718a35328f2142dc3892381d63350282203041b1368
1e62f50ce16107c1c33f018c3450df29a22f17705d1b42d415533701a3bb14603d1ad12109d3fc1870c23bd15f04729f
3c20333332312c811325904e2c21df39312b3073a402325a3f82021102bb0d03283af2843090412112dd1162783970fa
17c2741273d10243703030a03b71650340b32bd2001193120c60842fb1a12601e80571730ec37c26a07534c1f20a822b
06937a09f1ab29016e1f40f623332726e3dc19507635f1761de27a3990483e10ad34b2462cd1c71493db1ae0072e332a
1ca2b221035e0d307a3ab2b314306a1c93470de2a024b3d002c34f1262151622ef1173ca0130a63170e02a616b3a8118
3f901b13e2f42403291b70183f72f610822700a38f0ff09a2ba1930d52d33750702281851f93a224e04f3732230c825b
2d80f438618e04010736f2682060bb37e1682ea1b020e1523312413d900b1c826b0cf2b835d0fc2d71e3132323045197
34e1ec06b2893e02c415708117f2ac0562533c40502c739f05f1ea0a228a14531d3f603215607d19b3e90aa2663be094
1472393a60b01d12220cb3163961d53261280a53420d225d11e3113660ef3b00611a52f220d28033f0212fd1661d329b
2e80d43241712fe0023c02851150253e619228d1e91633fd03a1ba15d2af1f124711f3760b53b510b21f2ad0e438000e
3eb1bc03e2721233561a706c2422cc0dd21c30001535c2ab20a2f008038a02934608e2631752d20601ac3aa078201124
06236c2093b908a2b70d81f83a51673520773ba11d1a20950f93c127619a0da2df1bf3d20081e736013a24f30a35426d
2bf1880e72e115822c3e313132d0491bd2a70ca26738b23432f0011252263ef1402960f731e23a0be3ff02a1910b6159
0982483400311da36b02028c0a425e38e1481ff2f804214e2cf1e434a09130503c20435b06f14d2f127e1042d11e13c3
3191203d527c0b730d18b2ed1eb0e130e01d3c909b1d73ea0bc1823a32aa1b53820b11892713a71b608833c22a372012
1b221905819e3a010507437d1393f32301992b41363392870682560ee04d15323d2d93e210202d20838314a0530f1291
39c0c42eb1441fa2b92431ce0362c908710336a2450db1a637f30f20c3ce2861140101cf31329e0d62c11a33de2ff151
07b3582953fa00632b0a13b827916d34920b05c3b200f2cb10d03816c2e90bf3943340972211783cf0642570b21f026c
1091db04c24c0e638517b10e31a0ba3d32991d430114f21e3d81d833e07f1f317e2a513d3ae05131f1373632e501f3b6
23f18333b1331c429d20f02724a1c00520f317d0ae28335108f2a812f2613fb03f2493670dc27f1b323b0eb1cd16431c
0cd2c53cc09c3080633e42e637113b3382d53743f50461af0e93ad01e3591b81002fa06d1e02de01439d0853f4297065
39a0391fc2733641500c91900832881f701623613020532026f1862162d00993b121318f3e510f35016a2c01f611b348
21814c0e319f0192292b61ed3b30fb39b19d07e2be0c339e13f0663140cc15e2ae00932c09326521a0bd31802b2641aa
2f93d62a23812e23c810a33d0302ee0a72703653061be0052a43d41a439025535712d28b1723950431bb3bf0ed37909e
00324407212c0ab1c205a2751692321223cd1600ea2543430af22d0fd02e1cb0821ef3c70c72f31292a32351792b0134
`.replace(/\s/g, "");

export const BLUE_NOISE_RANKS = Uint16Array.from({ length: 1024 },
  (_, i) => Number.parseInt(BLUE_NOISE_HEX.slice(i * 3, i * 3 + 3), 16));

function blueNoise() { return BLUE_NOISE_RANKS; }

function averagedCells(image, o) {
  const { width: w, height: h, data } = image, cell = o.cellSize;
  const width = Math.ceil(w / cell), height = Math.ceil(h / cell);
  const values = new Float32Array(width * height);
  const table = Float32Array.from({ length: o.levels }, (_, i) => mapCurve(o.outputCurve, i / (o.levels - 1)));
  if (cell === 1) {
    for (let i = 0; i < values.length; i++) {
      const j = i * 4;
      const index = Math.round((data[j] * 0.299 + data[j + 1] * 0.587 + data[j + 2] * 0.114) / 255 * (o.levels - 1));
      values[i] = data[j + 3] ? table[index] : NaN;
    }
    return { values, width, height };
  }
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    let sum = 0, weight = 0;
    for (let yy = y * cell; yy < Math.min(h, (y + 1) * cell); yy++) {
      for (let xx = x * cell; xx < Math.min(w, (x + 1) * cell); xx++) {
        const j = (yy * w + xx) * 4, a = data[j + 3] / 255;
        sum += (data[j] * 0.299 + data[j + 1] * 0.587 + data[j + 2] * 0.114) / 255 * a;
        weight += a;
      }
    }
    const index = weight ? Math.round(sum / weight * (o.levels - 1)) : o.levels - 1;
    values[y * width + x] = weight ? table[index] : NaN;
  }
  return { values, width, height };
}

// strip: part of a taller picture, rows y0.. of it (see renderOutput). Its last row is the next strip's first:
// it only gathers error here, and the next strip starts from those values, so the result is the same as in one piece.
function diffuse(values, w, h, o, strip = null) {
  const add = (x, y, error) => {
    if (x < 0 || x >= w || y >= h) return;
    const i = y * w + x;
    if (!Number.isNaN(values[i])) values[i] += error;
  };
  const y0 = strip?.y0 ?? 0, rows = strip?.more ? h - 1 : h;
  if (strip?.carry) values.set(strip.carry.subarray(0, w), 0);
  for (let y = 0; y < rows; y++) {
    const direction = (y + y0) % 2 ? -1 : 1;
    for (let x = direction > 0 ? 0 : w - 1; x >= 0 && x < w; x += direction) {
      const i = y * w + x, v = values[i];
      if (Number.isNaN(v)) continue;
      const q = v <= 0 ? 0 : v >= 1 ? 1 : v >= o.threshold ? 1 : 0;
      const error = (v - q) * o.strength;
      values[i] = q;
      if (error === 0) continue;
      add(x + direction, y, error * 7 / 16);
      add(x - direction, y + 1, error * 3 / 16);
      add(x, y + 1, error * 5 / 16);
      add(x + direction, y + 1, error / 16);
    }
  }
  if (strip) strip.carry = strip.more ? values.slice((h - 1) * w, h * w) : null;
}

/**
 * Posterize, apply coverage LUT, then optionally dither to two endpoints.
 * Burn export must call this AFTER compositing layers onto an opaque background:
 * alpha is preserved for editing/preview, not interpreted as a physical texture.
 * In particular the existing Python --picture loader discards PNG alpha.
 */
// strip (optional): { y0, more, carry } for a band of rows y0.. of a taller picture, drawn one band at a time.
// more: the band has one row below its own (the next band's first), for the error diffusion to run on into;
// carry: what the previous band left in that row (replaced on the way out). Needs cellSize 1.
export function renderOutputCells(input, options = {}, strip = null) {
  const image = imageInfo(input), o = normalizeOutput(options);
  if (strip && o.cellSize !== 1) throw new RangeError("a strip needs cellSize 1");
  const { values, width: w, height: h } = averagedCells(image, o);
  return ditherCells(values, w, h, o, strip);
}

// The page's tone controls have no spatial filters. Fuse their point transform
// with output-cell preparation, retaining BOTH the Float32 and byte rounding
// boundaries of processRGBA -> renderOutput. No intermediate RGBA is needed.
export function renderExportCells(input, adjustments = {}, options = {}, strip = null) {
  const image = imageInfo(input), a = normalizeAdjustments(adjustments), o = normalizeOutput(options);
  if (o.cellSize !== 1 || a.denoise || a.clarity || a.texture || a.sharpen || a.grain) {
    return renderOutputCells(processRGBA(image, adjustments, { previewScale: 1, histogram: false }), options, strip);
  }
  const table = toneTable(a), lookup = new Float32Array(256);
  const coverage = Float32Array.from({ length: o.levels }, (_, i) => mapCurve(o.outputCurve, i / (o.levels - 1)));
  for (let g = 0; g < 256; g++) {
    const index = Math.round((g * 0.299 + g * 0.587 + g * 0.114) / 255 * (o.levels - 1));
    lookup[g] = coverage[index];
  }
  const { width, height, data } = image, values = new Float32Array(width * height);
  for (let i = 0; i < values.length; i++) {
    const j = i * 4;
    if (!data[j + 3]) { values[i] = NaN; continue; }
    const v = (data[j] * a.mix[0] + data[j + 1] * a.mix[1] + data[j + 2] * a.mix[2]) / 255 * 4096;
    const k = Math.min(4095, Math.floor(v)), t = v - k;
    values[i] = lookup[byte(Math.fround(table[k] + (table[k + 1] - table[k]) * t))];
  }
  return ditherCells(values, width, height, o, strip);
}

function ditherCells(values, w, h, o, strip) {
  const y0 = strip?.y0 ?? 0;
  if (o.mode === "floyd-steinberg") {
    diffuse(values, w, h, o, strip);
  } else if (o.mode !== "grayscale") {
    let size = o.matrixSize, ranks;
    if (o.mode === "ordered") ranks = bayer(size);
    else if (o.mode === "clustered") ranks = clustered(size);
    else if (o.mode === "blue-noise") { ranks = blueNoise(); size = Math.sqrt(ranks.length); }
    const angle = ((o.angle % 360) + 360) % 360 * Math.PI / 180;
    const snap = v => Math.abs(v) < 1e-12 ? 0 : Math.abs(1 - Math.abs(v)) < 1e-12 ? Math.sign(v) : v;
    const c = snap(Math.cos(angle)), s = snap(Math.sin(angle));
    const phaseX = hash32(o.seed) % size, phaseY = hash32(o.seed ^ 0x9e3779b9) % size;
    const wrap = n => ((n % size) + size) % size;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x, v = values[i];
      if (Number.isNaN(v)) continue;
      let threshold = o.threshold;
      if (ranks) {
        const yy0 = y + y0, xx = wrap(Math.floor(c * x + s * yy0) + phaseX), yy = wrap(Math.floor(-s * x + c * yy0) + phaseY);
        threshold += o.strength * ((ranks[yy * size + xx] + 0.5) / ranks.length - 0.5);
      }
      values[i] = v <= 0 ? 0 : v >= 1 ? 1 : v >= threshold ? 1 : 0;
    }
  }
  return { values, width: w, height: h, cellSize: o.cellSize };
}

export function renderOutput(input, options = {}, strip = null) {
  const image = imageInfo(input);
  const { values, width: w, cellSize } = renderOutputCells(image, options, strip);
  const data = new Uint8ClampedArray(image.data.length);
  if (cellSize === 1) {
    for (let i = 0; i < values.length; i++) {
      const j = i * 4, v = values[i], g = Number.isNaN(v) ? 255 : byte(v);
      data[j] = data[j + 1] = data[j + 2] = g;
      data[j + 3] = image.data[j + 3];
    }
    return { width: image.width, height: image.height, data };
  }
  for (let y = 0; y < image.height; y++) for (let x = 0; x < image.width; x++) {
    const j = (y * image.width + x) * 4;
    const v = values[Math.floor(y / cellSize) * w + Math.floor(x / cellSize)];
    const g = Number.isNaN(v) ? 255 : byte(v);
    data[j] = data[j + 1] = data[j + 2] = g;
    data[j + 3] = image.data[j + 3];
  }
  return { width: image.width, height: image.height, data };
}

/**
 * A low-pass viewing SCHEMATIC, not a disc-reflectance simulator. It averages
 * raster dots; it has no dye, drive, wavelength, viewing geometry, or MTF data.
 */
export function physicalPreview(input, options = {}) {
  const image = imageInfo(input);
  record(options, "preview options");
  const radius = number(options.radiusPixels ?? 2, 0, 64, "preview radius");
  const scale = number(options.previewScale ?? 1, 1 / 1000, 100, "previewScale");
  const values = new Float32Array(image.width * image.height);
  for (let i = 0; i < values.length; i++) {
    const j = i * 4;
    values[i] = (image.data[j] * 0.299 + image.data[j + 1] * 0.587 + image.data[j + 2] * 0.114) / 255;
  }
  if (radius) {
    const effective = Math.min(1, radius * scale);
    spatial(values, image, radius * scale, (v, b) => v + effective * (b - v));
  }
  return toRGBA(values, image);
}

/** Sampling facts only; never claims a guaranteed physical feature resolution. */
export function estimateGrid(width, cellSize = 1, diameterMm = 120) {
  number(width, 1, 12000, "width", true);
  number(cellSize, 1, 256, "cellSize", true);
  number(diameterMm, 1, 120, "diameterMm");
  const pixelMicrons = diameterMm * 1000 / width;
  const cellMicrons = pixelMicrons * cellSize;
  const warnings = [];
  if (cellMicrons < 20) warnings.push("Below the current writer's 20 µm design grid; these cells cannot be passed through unchanged.");
  if (width !== 6000 || diameterMm !== 120) warnings.push("The burn raster is 6000 × 6000 across 120 mm; this view is resampled for output.");
  return { pixelMicrons, cellMicrons, designGridMicrons: 20, warnings };
}
