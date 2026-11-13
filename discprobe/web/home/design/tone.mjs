// Tone and dithering of a picture layer on the grid being composed: the page's copy of discprobe/editor_tone.py.
// Integer arithmetic only, so the page and the core give the same cells (tests/test_editor_ops.py checks it).
// Spec: docs/EDITOR_DOCUMENT.md, "Tone and dither".
import { bayer, clustered, BLUE_NOISE_RANKS } from "./processing.mjs";

export const MODES = ["floyd-steinberg", "blue-noise", "ordered", "clustered", "threshold"];
export const DEFAULT_TONE = Object.freeze({ brightness: 0, contrast: 0, highlights: 0, shadows: 0, dither: "floyd-steinberg", strength: 100 });
const TILES = { "blue-noise": [32, BLUE_NOISE_RANKS], ordered: [8, bayer(8)], clustered: [8, clustered(8)] };
const fdiv = (a, b) => Math.floor(a / b);            // Python's // for these (safe) integers

// A layer's tone with defaults filled and checked.
export function tone(t = {}) {
  const o = { ...DEFAULT_TONE, ...(t ?? {}) };
  for (const k of ["brightness", "contrast", "highlights", "shadows"]) {
    if (!Number.isInteger(o[k]) || o[k] < -100 || o[k] > 100) throw new RangeError(`tone ${k} must be a whole number from -100 to 100`);
  }
  if (!Number.isInteger(o.strength) || o.strength < 0 || o.strength > 100) throw new RangeError("tone strength must be a whole number from 0 to 100");
  if (!MODES.includes(o.dither)) throw new RangeError("unknown dither mode");
  return Object.fromEntries(Object.keys(DEFAULT_TONE).map((k) => [k, o[k]]));
}

// Grey 0..255 -> toned grey 0..255 (editor_tone.table).
export function table(t) {
  const { contrast, brightness: b, shadows: sh, highlights: hi } = tone(t), k = 100 + contrast, out = new Uint8Array(256);
  for (let u = 0; u < 256; u++) {
    let v = fdiv(fdiv((2 * u - 255) * k, 100) + 255 + fdiv(b * 255, 100), 2);
    v = Math.min(255, Math.max(0, v));
    const w = 255 - v;
    v += fdiv(2 * sh * v * w * w, 6502500) + fdiv(2 * hi * v * v * w, 6502500);
    out[u] = Math.min(255, Math.max(0, v));
  }
  return out;
}

export const luminance = (r, g, b) => fdiv(2126 * r + 7152 * g + 722 * b, 10000);

// Floyd-Steinberg state of one layer across the rows of one grid (editor_tone.Diffusion).
export class Diffusion {
  constructor(width, strength) { this.w = width; this.s = strength; this.acc = new Float64Array(width + 2); }
  // grey: Int32Array/Uint8Array, take: Uint8Array of the row's width; fills dark (Uint8Array) and returns it
  row(j, grey, take, dark = new Uint8Array(this.w)) {
    const { w, s, acc } = this, next = new Float64Array(w + 2);
    dark.fill(0);
    let x0 = -1, x1 = -1;
    for (let x = 0; x < w; x++) if (take[x]) { if (x0 < 0) x0 = x; x1 = x; }
    if (x0 >= 0) {
      const d = j % 2 === 0 ? 1 : -1;
      let carry = 0;
      for (let x = d > 0 ? x0 : x1; x >= x0 && x <= x1; x += d) {
        if (!take[x]) { carry = 0; continue; }
        const v = grey[x] + fdiv(acc[x + 1] + carry, 1600);
        let e;
        if (v < 128) { dark[x] = 1; e = v * s; } else e = (v - 255) * s;
        carry = 7 * e;
        next[x + 1 - d] += 3 * e; next[x + 1] += 5 * e; next[x + 1 + d] += e;
      }
    }
    this.acc = next;
    return dark;
  }
}

// A threshold-tile mode's dark flag for global cell (i, j) (editor_tone.matrix_dark).
export function matrixDark(mode, strength, i, j, grey) {
  if (mode === "threshold") return grey < 128;
  const [n, ranks] = TILES[mode], nn = n * n, r = ranks[(j % n) * n + (i % n)];
  return grey * 200 * nn < 25500 * nn + strength * 255 * (2 * r + 1 - nn);
}
