// The lamp view in the browser: a port of discprobe.simulate_a3.render (A3 v3 textures, Disc Lab's optics, a flat
// disc seen straight down). Same light, same constants, same table (lamp-a3v3.bin, written by tools/lamp_tables.py
// from simulate_a3v3.npz); tests/test_lamp_optics.py compares the two. Only the coverage differs: here each pixel
// holds at most two materials and the share of the second, from the editor's composer at the coverage grid (a
// dithered grey is the dark texture's share, editor-ops.darkShare), where the core counts the burn cells.
// Coordinates: mm, x right, y up (as simulate.py), disc centre at the origin. Prediction, not a photo.

export function loadTables(meta, buffer) {
  const xyz = new Float32Array(buffer);
  const { specs, delta, cmf } = meta;
  if (xyz.length !== specs.length * delta.n * 3) throw Error("lamp table size");
  return {
    meta, xyz, index: new Map(specs.map((s, i) => [s, i])), c: meta.constants,
    d0: delta.first, dstep: (delta.last - delta.first) / (delta.n - 1), dn: delta.n,
    cmf: Float64Array.from(cmf.values), c0: cmf.first_nm, cstep: (cmf.last_nm - cmf.first_nm) / (cmf.n - 1), cn: cmf.n,
    m: Float64Array.from(meta.xyz_to_srgb),
  };
}

export function canonical(spec) {
  spec = String(spec).trim();
  if (spec.toUpperCase() === "RND") return "RND";
  const hex = spec.toUpperCase(), n = hex.length / 2;
  for (let p = 1; p <= n; p++) {
    if (n % p) continue;
    const head = hex.slice(0, 2 * p);
    if (head.repeat(n / p) === hex) return head;
  }
  return hex;
}

// What one material contributes: its XYZ curve against the along-track factor (null: no light of its own, as
// recorded random data) read at d_t * scale, and how much of the mirror its marks take away.
export function materialCurve(T, material) {
  const spec = canonical(material.spec), a5 = T.index.get("A5");
  const dark = spec === "A5" ? 1 : T.c.OTHER_DARK;
  if (spec === "RND") return { curve: null, scale: 1, dark, known: true };
  const at = i => T.xyz.subarray(i * T.dn * 3, (i + 1) * T.dn * 3);
  if (T.index.has(spec)) return { curve: at(T.index.get(spec)), scale: 1, dark, known: true };
  const period = material.period_um ?? material.periods_um?.[0];
  if (!(period > 0) || !Number.isFinite(period)) return { curve: null, scale: 1, dark, known: false };
  return { curve: at(a5), scale: period / T.c.A5_PERIOD_UM, dark, known: false };
}

// Coverage from the editor's composer at an n x n grid (row 0 at the top, y = +60 mm): labels and the dark share of
// dithered cells (NaN elsewhere). Each pixel: slot a, slot b and b's share (0..255).
export function coverageFrom(labels, share, n, materials) {
  let dark = materials.findIndex(m => m.id === "dark");
  if (dark < 0) dark = materials.findIndex(m => m.spec === "A5");
  if (dark < 0) dark = 1;
  const a = new Uint8Array(n * n), b = new Uint8Array(n * n), w = new Uint8Array(n * n);
  for (let i = 0; i < n * n; i++) {
    const t = share ? share[i] : NaN;
    if (t === t && t > 0) { a[i] = 0; b[i] = dark; w[i] = Math.round(t * 255); }
    else a[i] = labels[i];
  }
  return { n, a, b, w };
}

const srgb = v => v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055;
const SRGB = new Uint8Array(65537);
for (let i = 0; i <= 65536; i++) SRGB[i] = Math.round(255 * srgb(i / 65536));

// the k-th smallest of v (reordering v), quickselect; `from`: v[0..from) are known to be <= the rest
function select(v, k, from = 0) {
  let lo = from, hi = v.length - 1;
  while (hi > lo) {
    const pivot = v[(lo + hi) >> 1];
    let i = lo, j = hi;
    while (i <= j) {
      while (v[i] < pivot) i++;
      while (v[j] > pivot) j--;
      if (i <= j) { const tmp = v[i]; v[i] = v[j]; v[j] = tmp; i++; j--; }
    }
    if (k <= j) hi = j; else if (k >= i) lo = i; else return v[k];
  }
  return v[k];
}

// One render: new LampFrame(...), rows(y0, y1) for every band (in any order), then finish() for RGBA bytes.
// pose: { camera, flash, rotate (deg), delta_scale }; opts: { size, k (samples per pixel side), annulus, edge, paper,
// exposure (stops over the model's own) }.
export class LampFrame {
  constructor(T, cov, materials, pose, { size = 400, k = 1, annulus = null, edge = null, paper = false, exposure = 0,
    diffractionOnly = false, traceDelta = false } = {}) {
    Object.assign(this, { T, cov, size, k, annulus, paper, exposure, diffractionOnly, edge: edge ?? T.c.EDGE_MM });
    this.delta = traceDelta ? new Float64Array((size * k) ** 2) : null;
    this.mats = materials.map(m => materialCurve(T, m));
    this.unknown = materials.filter((m, i) => !this.mats[i].known).map(m => m.id);
    const cam = pose.camera, fl = pose.flash;
    this.cam = cam; this.fl = fl; this.dscale = pose.delta_scale ?? T.meta.delta_scale ?? 1;
    const a = ((pose.rotate ?? 0) % 360) * Math.PI / 180;
    this.cos = Math.cos(a); this.sin = Math.sin(a);
    this.flNorm = Math.hypot(...fl);
    this.lampAng = Math.max(3 / Math.hypot(...cam), .004);
    const xyz = T.xyz, A5 = T.index.get("A5"), B9 = T.index.get("B9");
    let ref = 0;
    for (const s of [A5, B9]) for (let j = 0; j < T.dn; j++) ref = Math.max(ref, xyz[(s * T.dn + j) * 3 + 1]);
    this.ref = T.meta.reference_y ?? ref;
    this.rgb = new Float32Array(size * size * 3);
    this.rs = new Float32Array(size * size);
    this.clear = new Uint8Array(size * size);
  }
  rows(y0, y1) {
    const { T, cov, size, k, cam, fl, mats, cos, sin, dscale, lampAng, rgb, rs, clear, diffractionOnly, delta } = this;
    const c = T.c, m = T.m, n = size * k, cn = cov.n, step = 120 / n;
    const [ax, ay, az] = cam, [lx0, ly0, lz] = fl, az2 = az * az, lz2 = lz * lz;
    const irr0 = this.flNorm * this.flNorm, texGain = c.TEX_GAIN / this.ref;
    const inner = this.annulus?.[0] ?? -1, outer = this.annulus?.[1] ?? 1e9;
    const veil = c.VEIL_RGB.map(v => v * c.VEIL), desat = 1 - c.DESATURATE, kk = k * k;
    const d0 = T.d0, dinv = 1 / T.dstep, dn = T.dn, xyz = T.xyz, cmf = T.cmf, c0 = T.c0, cinv = 1 / T.cstep, cnn = T.cn;
    const rainGain = c.RAINBOW_GAIN, glareGain = c.GLARE_GAIN, zod = c.ZERO_ORDER_DARK, pitch = c.PITCH_UM * 1000;
    const glareW = .12 * lampAng, ca = cov.a, cb = cov.b, cw = cov.w;
    for (let py = y0; py < y1; py++) {
      for (let px = 0; px < size; px++) {
        let R = 0, G = 0, B = 0, rsum = 0, gmax = 0;
        for (let sy = 0; sy < k; sy++) {
          const y = 60 - (py * k + sy + .5) * step;
          for (let sx = 0; sx < k; sx++) {
            const x = (px * k + sx + .5) * step - 60, r = Math.sqrt(x * x + y * y);
            rsum += r;
            const ri = r > 0 ? 1 / r : 0, cA = x * ri, sA = y * ri;
            let vx = ax - x, vy = ay - y, nn = 1 / Math.sqrt(vx * vx + vy * vy + az2);
            let svx = vx * nn, svy = vy * nn;
            vx = lx0 - x; vy = ly0 - y;
            const ld2 = vx * vx + vy * vy + lz2;
            nn = 1 / Math.sqrt(ld2);
            svx += vx * nn; svy += vy * nn;
            const dt = Math.abs(-svx * sA + svy * cA), dr = svx * cA + svy * sA;
            if (delta) delta[(py * k + sy) * n + px * k + sx] = dt * dscale;
            const irr = irr0 / ld2;
            // textures, over the coverage pixel this sample falls in (the disc turned by rotate)
            let tX = 0, tY = 0, tZ = 0, att = 0;
            if (r >= inner && r < outer) {
              const dx = x * cos + y * sin, dy = -x * sin + y * cos;
              let ix = Math.floor((dx + 60) * cn / 120), iy = Math.floor((60 - dy) * cn / 120);
              ix = ix < 0 ? 0 : ix >= cn ? cn - 1 : ix; iy = iy < 0 ? 0 : iy >= cn ? cn - 1 : iy;
              const ci = iy * cn + ix, wb = cw[ci] / 255, wa = 1 - wb;
              for (let q = 0; q < 2; q++) {
                const share = q ? wb : wa;
                if (share <= 0) continue;
                const slot = q ? cb[ci] : ca[ci];
                if (diffractionOnly && slot === 0) continue;
                const mt = mats[slot];
                if (!mt) continue;
                att += share * mt.dark;
                if (!mt.curve) continue;
                // np.interp(d_t, delta, curve, left=0, right=0) on the table's even grid
                const f = (dt * dscale * mt.scale - d0) * dinv;
                if (!(f >= 0) || f > dn - 1) continue;
                const i = f | 0, t = f - i, cv = mt.curve, o = i * 3, o2 = i >= dn - 1 ? o : o + 3;
                tX += share * (cv[o] + (cv[o2] - cv[o]) * t);
                tY += share * (cv[o + 1] + (cv[o2 + 1] - cv[o + 1]) * t);
                tZ += share * (cv[o + 2] + (cv[o2 + 2] - cv[o + 2]) * t);
              }
              const g = irr * texGain; tX *= g; tY *= g; tZ *= g;
            }
            // XYZ -> linear sRGB, clipped, then the phone's desaturation
            let r0 = m[0] * tX + m[1] * tY + m[2] * tZ, g0 = m[3] * tX + m[4] * tY + m[5] * tZ, b0 = m[6] * tX + m[7] * tY + m[8] * tZ;
            r0 = r0 > 0 ? r0 : 0; g0 = g0 > 0 ? g0 : 0; b0 = b0 > 0 ? b0 : 0;
            if (diffractionOnly) {
              R += r0; G += g0; B += b0;
              continue;
            }
            const grey = (r0 + g0 + b0) / 3;
            r0 = grey + desat * (r0 - grey); g0 = grey + desat * (g0 - grey); b0 = grey + desat * (b0 - grey);
            // the grooves' rainbow
            if (r > 22.6 && r < 58.7 && dt < 9 * lampAng) {         // beyond, exp(-40): nothing to add
              const wt = Math.exp(-.5 * (dt / lampAng) ** 2) * irr * rainGain;
              const f = (pitch * Math.abs(dr) - c0) * cinv;
              if (wt > 1e-12 && f >= 0 && f <= cnn - 1) {
                const i = f | 0, t = f - i, j = i >= cnn - 1 ? i : i + 1;
                const X = (cmf[i * 3] * (1 - t) + cmf[j * 3] * t) * wt, Y = (cmf[i * 3 + 1] * (1 - t) + cmf[j * 3 + 1] * t) * wt,
                  Z = (cmf[i * 3 + 2] * (1 - t) + cmf[j * 3 + 2] * t) * wt;
                const rr = m[0] * X + m[1] * Y + m[2] * Z, rg = m[3] * X + m[4] * Y + m[5] * Z, rb = m[6] * X + m[7] * Y + m[8] * Z;
                r0 += rr > 0 ? rr : 0; g0 += rg > 0 ? rg : 0; b0 += rb > 0 ? rb : 0;
              }
            }
            // the flash's mirror glare and the room in the mirror, both darkened where marks were written
            let e = (Math.sqrt(dt * dt + dr * dr) / 2 - lampAng) / glareW;
            e = e < -60 ? -60 : e > 60 ? 60 : e;
            const wg = e > 40 ? 0 : 1 / (1 + Math.exp(e)), gl = glareGain * wg * irr;   // e > 40: below 1e-17
            let z0 = 1 - zod * att; z0 = z0 < 0 ? 0 : z0 > 1 ? 1 : z0;
            R += r0 + (gl * .95 + veil[0]) * z0; G += g0 + (gl + veil[1]) * z0; B += b0 + (gl * 1.05 + veil[2]) * z0;
            if (wg > gmax) gmax = wg;
          }
        }
        const o = py * size + px;
        rgb[o * 3] = R / kk; rgb[o * 3 + 1] = G / kk; rgb[o * 3 + 2] = B / kk;
        rs[o] = rsum / kk; clear[o] = gmax < .01 ? 1 : 0;
      }
    }
  }
  // exposure as simulate_a3: the 98th percentile of the clear disc's brightness shows at .85; then sRGB bytes.
  // Outside the disc (and the centre hole) is transparent; the clamp area and the rim are black (paper: white).
  finish(out = new Uint8ClampedArray(this.size * this.size * 4)) {
    const { size, rgb, rs, clear, edge, paper } = this, hub = this.T.c.HUB_MM;
    let count = 0;
    for (let i = 0; i < size * size; i++) if (clear[i] && rs[i] > 24 && rs[i] < 58) count++;
    let level = 1;
    if (count) {
      const v = new Float32Array(count);
      let j = 0;
      for (let i = 0; i < size * size; i++) if (clear[i] && rs[i] > 24 && rs[i] < 58) v[j++] = (rgb[i * 3] + rgb[i * 3 + 1] + rgb[i * 3 + 2]) / 3;
      // np.quantile(v, .98): linear between the two order statistics around .98 * (count - 1)
      const at = .98 * (count - 1), lo = Math.floor(at), t = at - lo;
      const a = select(v, lo), b = lo + 1 < count ? select(v, lo + 1, lo + 1) : a;
      level = a * (1 - t) + b * t;
    }
    const gain = .85 / Math.max(level, 1e-6) * 2 ** (this.exposure || 0), fill = paper ? 255 : 0;   // exposure: stops
    for (let i = 0; i < size * size; i++) {
      const r = rs[i];
      if (r >= 60 || r < 7.5) { out[i * 4 + 3] = 0; continue; }
      out[i * 4 + 3] = 255;
      if (r < hub || r >= edge) { out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = fill; continue; }
      for (let ch = 0; ch < 3; ch++) {
        let v = rgb[i * 3 + ch] * gain;
        v = v < 0 ? 0 : v > 1 ? 1 : v;
        out[i * 4 + ch] = SRGB[Math.round(v * 65536)];
      }
    }
    this.level = level;
    return out;
  }
}

// The whole render at once (tests, small sizes).
export function render(T, cov, materials, pose, opts = {}) {
  const f = new LampFrame(T, cov, materials, pose, opts);
  f.rows(0, f.size);
  return { rgba: f.finish(), level: f.level, unknown: f.unknown, delta: f.delta };
}
