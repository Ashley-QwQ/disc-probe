// Hypothesis optics plus artistic camera/surface stage, after the exact model.
// Distances are millimetres in the model's disc frame. No photographic assets.
import { DEFAULT_POSE } from './model.mjs';
const clamp = v => Math.max(0, Math.min(1, v));
const gauss = (x, y, sx, sy = sx) => Math.exp(-.5 * ((x / sx) ** 2 + (y / sy) ** 2));
export function reflectionPoint(pose) {
  const p = { ...DEFAULT_POSE, ...pose }, t = p.tilt * Math.PI / 180;
  const frame = (x, y, z) => [x, y * Math.cos(t) + z * Math.sin(t), -y * Math.sin(t) + z * Math.cos(t)];
  const c = frame(p.cx, p.cy, p.cz), l = frame(p.lx, p.ly, p.lz);
  // Line from camera to the light mirrored across z=0 intersects the surface.
  const f = c[2] / (c[2] + l[2]);
  return [c[0] + f * (l[0] - c[0]), c[1] + f * (l[1] - c[1])];
}
function random(seed) { return () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }; }
// Cache stable physical marks at each progressive resolution. Rotation is applied
// at lookup, so marks stay on the disc rather than swimming with the camera.
const marks = new Map();
function surfaceMarks(size) {
  if (marks.has(size)) return marks.get(size);
  const c = new OffscreenCanvas(size, size), g = c.getContext('2d'), rnd = random(0x51face);
  g.scale(size / 120, size / 120); g.translate(60, 60);
  for (let i = 0; i < 620; i++) {
    const x = rnd() * 120 - 60, y = rnd() * 120 - 60;
    g.strokeStyle = `rgba(255,255,255,${.12 + rnd() * .55})`; g.lineWidth = .025 + rnd() * .065;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (rnd() - .5) * 3, y + (rnd() - .5) * 2); g.stroke();
  }
  for (let i = 0; i < 1100; i++) {
    g.fillStyle = `rgba(255,255,255,${.15 + rnd() * .7})`;
    g.beginPath(); g.arc(rnd() * 120 - 60, rnd() * 120 - 60, .025 + rnd() ** 4 * .15, 0, Math.PI * 2); g.fill();
  }
  for (let i = 0; i < 28; i++) {
    g.strokeStyle = 'rgba(255,255,255,.07)'; g.lineWidth = .085;
    g.beginPath(); g.ellipse(24, 16, 4 + i * .23, 7 + i * .25, -.45, .3, 2.7); g.stroke();
  }
  const data = g.getImageData(0, 0, size, size).data; marks.set(size, data); return data;
}
// First-order radial DVD grating diagnostic. Units: 740 nm track pitch.
// Near a mirror point this tends to zero, outside the visible spectrum; a
// compact visible flame therefore needs the explicit approximation below.
export function gratingWavelength(X, Y, pose) {
  const p = { ...DEFAULT_POSE, ...pose }, t = p.tilt * Math.PI / 180;
  const ct = Math.cos(t), st = Math.sin(t), r = Math.hypot(X, Y);
  const ray = (x, y, z) => {
    const dx = x - X, dy = y * ct + z * st - Y, dz = -y * st + z * ct;
    const n = Math.hypot(dx, dy, dz); return [dx / n, dy / n];
  };
  const c = ray(p.cx, p.cy, p.cz), l = ray(p.lx, p.ly, p.lz);
  return r > 0 ? 740 * Math.abs((c[0] + l[0]) * X / r + (c[1] + l[1]) * Y / r) : 0;
}
// Internal hypothesis parameters, NOT measured properties of a burned disc.
export const RADIAL_APERTURE = Object.freeze({ widthUm: 16, periodUm: 20,
  zeroGain: 5, orderGain: 16, oppositeOrder: .10, sourceFwhm: .004,
  tangentSigma: .0045 });
function opticalFrame(p) {
  const t = p.tilt * Math.PI / 180, ct = Math.cos(t), st = Math.sin(t);
  return [[p.cx, p.cy * ct + p.cz * st, -p.cy * st + p.cz * ct],
    [p.lx, p.ly * ct + p.lz * st, -p.ly * st + p.lz * ct]];
}
function mismatch(X, Y, frame) {
  const r = Math.hypot(X, Y), s = [0, 0];
  for (const a of frame) {
    const dx = a[0] - X, dy = a[1] - Y, n = Math.hypot(dx, dy, a[2]);
    s[0] += dx / n; s[1] += dy / n;
  }
  return r > .001 ? [(s[0] * X + s[1] * Y) / r, (-s[0] * Y + s[1] * X) / r] : s;
}
export function radialMismatch(X, Y, pose) {
  return mismatch(X, Y, opticalFrame({ ...DEFAULT_POSE, ...pose }));
}
// Gaussian-apodized central lobe: matched to rectangular-aperture sinc² FWHM
// .886 lambda/w, convolved with a finite source. No claim of coherent sidelobes.
// A LUT integrates 13 wavelength samples once, rather than per output pixel.
const apertureTables = new Map();
function apertureTable(params) {
  const key = JSON.stringify(params); if (apertureTables.has(key)) return apertureTables.get(key);
  const table = new Float32Array(2401 * 3);
  for (let i = 0; i <= 2400; i++) {
    const q = (i - 1200) * .0001;
    for (let nm = 400; nm <= 700; nm += 25) {
      const lambda = nm / 1000, fwhm = Math.hypot(.886 * lambda / params.widthUm, params.sourceFwhm);
      const lobe = d => Math.exp(-4 * Math.LN2 * (d / fwhm) ** 2);
      // Negative mismatch is radially OUTWARD of the mirror point. Explicit
      // 10:1 blaze hypothesis favours that order; red peaks farther out.
      const power = params.zeroGain * lobe(q) + params.orderGain *
        (lobe(q + lambda / params.periodUm) + params.oppositeOrder * lobe(q - lambda / params.periodUm));
      const rgb = spectrum((nm - 400) / 300);
      for (let c = 0; c < 3; c++) table[i * 3 + c] += power * rgb[c] / 5;
    }
  }
  apertureTables.set(key, table); return table;
}
export function apertureRGB(q, params = RADIAL_APERTURE) {
  const table = apertureTable(params), u = Math.max(0, Math.min(2400, q / .0001 + 1200));
  const i = Math.min(2399, Math.floor(u)), f = u - i;
  return [0, 1, 2].map(c => table[i * 3 + c] * (1 - f) + table[(i + 1) * 3 + c] * f);
}
// Continuous approximate camera RGB response, deliberately not a calibrated SPD.
const spectrum = t => [
  Math.exp(-(((t - .85) / .28) ** 2)) + .20 * Math.exp(-(((t - .05) / .12) ** 2)),
  Math.exp(-(((t - .44) / .24) ** 2)),
  Math.exp(-(((t - .10) / .25) ** 2))
];
// A shared backing for the open hole and refracted hub: no painted hub colour.
function backing(X, Y, table) {
  const fold = .5 + .5 * Math.sin(Y * .16 + Math.sin(X * .09) * 2);
  if (table) return [.018 + fold * .018, .022 + fold * .018, .035 + fold * .02];
  const edge = Y + .72 * X + 2 + 2 * Math.sin(X * .07);
  const hand = clamp((10 - edge) / 5);
  const flesh = .76 + .12 * Math.sin(X * .06) - .11 * gauss(X + 10, Y + 14, 6, 20);
  const crease = .055 * gauss(Y + .55 * X + 14 + Math.sin(X * .09), 0, .38);
  const bed = [.055 + fold * .06, .072 + fold * .075, .085 + fold * .08];
  return bed.map((b, c) => b * (1 - hand) + ([flesh, flesh * .62, flesh * .57][c] - crease) * hand);
}
export async function photoSurface(source, size, pose, cancelled, yieldTask, material) {
  const p = { ...DEFAULT_POSE, flash: 1, wear: 45, background: 0, ...pose };
  const [hx, hy] = reflectionPoint(p), flash = !!p.flash, m = surfaceMarks(size), hn = Math.hypot(hx, hy);
  const out = new Uint8ClampedArray(source.length), a = p.rotate * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
  const rnd = random(0xface123), ev = 2 ** (p.exposure * .5), wear = p.wear / 100;
  const fresnel = .12 + .5 * (1 - Math.cos(p.tilt * Math.PI / 180)) ** 2;
  const ux = hn > .1 ? hx / hn : 0, uy = hn > .1 ? hy / hn : 1;
  const visibleFlash = gauss(Math.max(0, hn - 59), 0, 8) * (flash ? 1 : .06);
  const frame = opticalFrame(p), aperture = apertureTable(RADIAL_APERTURE);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const X = (x + .5) / size * 120 - 60, Y = 60 - (y + .5) / size * 120, r = Math.hypot(X, Y), j = (y * size + x) * 4;
      if (r >= 59.8) continue;
      const dx = X - hx, dy = Y - hy;
      const hot = gauss(dx, dy, flash ? .65 : 5, flash ? .85 : 9);
      const bloom = gauss(dx, dy, flash ? 7 : 13) * (flash ? .58 : .16);
      const wash = gauss(dx, dy, 19, 30) * (flash ? .09 : .04);
      const cross = X * uy - Y * ux, along = X * ux + Y * uy;
      const [qr, qt] = mismatch(X, Y, frame);
      const qi = Math.max(0, Math.min(2400, qr / .0001 + 1200)), ai = Math.min(2399, Math.floor(qi)), af = qi - ai;
      // Tangential finite-source spread makes a fat core, not a drawn line.
      // Gate the local branch so a second radial solution cannot become a
      // duplicate flame across the hub; the opposed needle remains separate.
      const flame = gauss(qt, 0, RADIAL_APERTURE.tangentSigma) * visibleFlash *
        clamp((along - 12) / 8);
      // Opposed thin spectral spokes, with a finite, tapered end, no uniform
      // white radial line. Their direction also follows the optical handles.
      const nr = -along, nt = clamp((nr - 23) / 36);
      const needleEnv = nr > 19 ? gauss(nr - 40, 0, 20) * visibleFlash : 0;
      const needleColour = spectrum(nt);
      const needleWidth = .10 + .22 * nt;
      const u = X + p.cx * .22, v = Y + p.cy * .16;
      const room = .35 + .23 * Math.sin(u * .063 + .9) * Math.cos(v * .048) - .42 * gauss(u + 27, v - 13, 10, 23) - .28 * gauss(u - 31, v + 24, 14, 9);
      const rim = Math.exp(-(((r - 59.35) / .16) ** 2)) * (.12 + .7 * gauss(dx, dy, 40));
      // Paired dark/light step edges, directional arcs and a frosted clamp band.
      const theta = Math.atan2(Y, X), az = Math.atan2(hy, hx);
      const arc = .02 + .88 * Math.max(0, Math.cos(theta - az + .35)) ** 12 +
        .30 * Math.max(0, Math.cos(theta - az - 2.5)) ** 22;
      let ring = 0, shadow = 0;
      for (const [i, radius] of [7.65, 8.5, 10.1, 16.8, 17.5, 20.5].entries()) {
        const phase = theta - az + i * .73;
        const width = .055 + .13 * (.5 + .5 * Math.sin(phase * 2 + i));
        const broken = clamp((Math.sin(phase * (3 + i % 3) + i) + .35) * 2);
        const edge = r - radius - .06 * Math.sin(theta * 3 + i);
        const catchLight = .85 * Math.max(0, Math.cos(phase)) ** (5 + i) +
          .18 * Math.max(0, Math.cos(phase - 2.4)) ** 18;
        ring += gauss(edge, 0, width) * catchLight * broken;
        shadow += gauss(edge - .18, 0, width * 1.5) * (.06 + catchLight * .2);
      }
      const mx = Math.floor((X * ca + Y * sa + 60) / 120 * size), my = Math.floor((60 + X * sa - Y * ca) / 120 * size);
      const mark = m[(Math.max(0, Math.min(size - 1, my)) * size + Math.max(0, Math.min(size - 1, mx))) * 4 + 3] / 255 * wear * (.05 + bloom * 1.6 + rim + .2 * (r / 60) ** 8);
      let rgb;
      if (r < 24.6) {
        const hole = r < 7.5;
        const offset = hole ? 0 : .6 + 1.1 * gauss(r - 17, 0, 1.8);
        const behind = backing(X + offset * X / r, Y + offset * Y / r, p.background);
        const frost = !hole && r > 10.2 && r < 16.6 ? .075 : 0;
        const reflection = (.025 + .065 * Math.sin(theta + r * .12) ** 8) * (hole ? 0 : 1);
        const ringColour = spectrum((theta / Math.PI * 2 + r * .06 + 4) % 1);
        const holeSide = Math.cos(theta - az - .45);
        const innerRim = gauss(r - 7.65, 0, .19);
        rgb = behind.map((b, c) => hole ? b * (1 - gauss(r - 7.42, 0, .16) * .6) :
          r > 20.7 ? .09 + room * .2 + ringColour[c] * arc * .09 :
          b * (.76 - shadow) + frost + reflection * [.65, .85, 1.25][c] + ring * [.55, .65, .8][c] +
          innerRim * (Math.max(0, holeSide) * .7 - Math.max(0, -holeSide) * .24) +
          (r > 17.5 ? ringColour[c] * arc * .17 : 0));
      } else if (r > 57.6) rgb = [.025 + room * .09, .035 + room * .1, .055 + room * .14];
      else {
        const shift = Math.max(1, Math.round(size / 500)), sx = X > 0 ? shift : -shift;
        const at = (xx, yy, c) => source[(Math.max(0, Math.min(size - 1, yy)) * size + Math.max(0, Math.min(size - 1, xx))) * 4 + c] / 255;
        rgb = [0, 1, 2].map(c => {
          const b = at(x + (c - 1) * sx, y, c), blur = (at(x - 1, y, c) + at(x + 1, y, c) + at(x, y - 1, c) + at(x, y + 1, c)) / 4;
          return b + .16 * (b - blur);
        });
        const grey = rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
        // The binary material identity comes from the SAME rotated design as
        // the exact model, never from a dark-pixel threshold on its RGB result.
        const ix = Math.max(0, Math.min((material?.width || 1) - 1, Math.floor((X * ca + Y * sa + 60) / 120 * (material?.width || 1))));
        const iy = Math.max(0, Math.min((material?.width || 1) - 1, Math.floor((60 + X * sa - Y * ca) / 120 * (material?.width || 1))));
        const dark = material?.design[iy * material.width + ix] || 0;
        const darkReflection = clamp(1.1 * gauss(u + 27, v - 13, 10, 23) + .85 * gauss(u - 31, v + 24, 14, 9));
        const silver = (.38 + .09 * Math.sin(u * .025 + v * .017)) * (1 - .88 * darkReflection);
        rgb = rgb.map((b, c) => {
          const colour = Math.max(0, grey + 3.2 * (b - grey));
          const reflected = silver * [.84, .98, 1.12][c] + room * fresnel * [.08, .12, .24][c];
          return (colour * 1.1 + reflected) * (1 - dark * .88) * (1 - darkReflection * .65);
        });
      }
      const noise = (rnd() + rnd() + rnd() - 1.5) * .012;
      for (let c = 0; c < 3; c++) {
        // No global black-point subtraction or toe: silver stays exposed.
        let b = rgb[c] * [.97, 1, flash ? 1.04 : 1.01][c];
        if (r >= 7.5) {
          const active = r > 20.5 && r < 59.6;
          const needle = active ? needleEnv * (gauss(cross, 0, needleWidth) * needleColour[c] * 3.2 + gauss(cross, 0, .85) * needleColour[c] * .2) : 0;
          const spectral = aperture[ai * 3 + c] * (1 - af) + aperture[(ai + 1) * 3 + c] * af;
          const fire = active ? flame * spectral + spectral * visibleFlash * gauss(qt, 0, .022) * .015 * clamp((along - 12) / 8) : 0;
          b += ev * (hot * 3 + bloom * [.3, .6, 1.4][c] + wash * [.25, .4, .9][c] + rim * [.6, .8, 1][c] + mark + needle + fire);
        }
        b *= 1 - .15 * (r / 60) ** 2;
        out[j + c] = 255 * clamp(b + noise + (rnd() - .5) * .006);
      }
      out[j + 3] = Math.min(255, (59.8 - r) / (120 / size) * 255);
    }
    if (y % 16 === 0) { await yieldTask(); if (cancelled()) return null; }
  }
  return out;
}
