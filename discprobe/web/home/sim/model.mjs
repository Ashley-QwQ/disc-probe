// Browser port of discprobe/simulate.py: sampled(), along_track(), render().
// textures.bin: little-endian float64, decoded single[A5], single[B9], groove;
// 261 RGB triples each. See README.md for source hash and extraction recipe.
export const DEFAULT_POSE = { rotate: 0, tilt: 0, lx: -43.66, ly: 89.79, lz: 330,
  cx: 0, cy: 70, cz: 330, exposure: 0 };

// numpy.rint uses ties-to-even, unlike Math.round.
const index = (d) => { const v = d / .005, n = Math.floor(v), f = v - n;
  return Math.min(260, f === .5 ? n + (n % 2) : Math.round(v)); };
const encode = (v) => Math.floor(255 * (v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055));

// Output remains a face-on map, as in simulate. Tilt moves both optical positions
// into the disc frame (art/sim_view.py); the UI foreshortens that map separately.
export async function render(design, width, lut, pose, size, fine = true, cancelled = () => false, yieldTask = () => Promise.resolve()) {
  const p = { ...DEFAULT_POSE, ...pose }, a = p.rotate * Math.PI / 180,
    ca = Math.cos(a), sa = Math.sin(a), t = p.tilt * Math.PI / 180,
    ct = Math.cos(t), st = Math.sin(t),
    cam = [p.cx, p.cy * ct + p.cz * st, -p.cy * st + p.cz * ct],
    light = [p.lx, p.ly * ct + p.lz * st, -p.ly * st + p.lz * ct],
    k = fine ? Math.max(1, Math.ceil(2000 / size)) : 1, n = size * k,
    mm = 120 / n, gain = 4 * 2 ** p.exposure, out = new Uint8ClampedArray(size * size * 4);
  for (let oy = 0; oy < size; oy++) {
    for (let ox = 0; ox < size; ox++) {
      let red = 0, green = 0, blue = 0;
      for (let j = 0; j < k; j++) for (let i = 0; i < k; i++) {
        const x = (ox * k + i + .5) * mm - 60, y = 60 - (oy * k + j + .5) * mm,
          r = Math.sqrt(x * x + y * y);
        if (r < 24.6 || r >= 57.6) continue;
        const dx = x * ca + y * sa, dy = -x * sa + y * ca,
          ix = Math.max(0, Math.min(width - 1, Math.floor((dx + 60) / 120 * width))),
          iy = Math.max(0, Math.min(width - 1, Math.floor((60 - dy) / 120 * width))),
          vx = cam[0] - x, vy = cam[1] - y, lx = light[0] - x, ly = light[1] - y,
          cn = Math.sqrt(vx * vx + vy * vy + cam[2] * cam[2]),
          ln = Math.sqrt(lx * lx + ly * ly + light[2] * light[2]),
          sx = vx / cn + lx / ln, sy = vy / cn + ly / ln,
          it = index(Math.abs(-sx * y + sy * x) / r) * 3 + (design[iy * width + ix] ? 0 : 783),
          ir = index(Math.abs(sx * x + sy * y) / r) * 3 + 1566;
        red += (lut[it] + .15 * lut[ir] + .05 * .177) * gain;
        green += (lut[it + 1] + .15 * lut[ir + 1] + .05 * .177) * gain;
        blue += (lut[it + 2] + .15 * lut[ir + 2] + .05 * .177) * gain;
      }
      red /= k * k; green /= k * k; blue /= k * k;
      const grey = .2126 * red + .7152 * green + .0722 * blue, at = (oy * size + ox) * 4;
      out[at] = encode(Math.max(0, Math.min(1, grey + .6 * (red - grey))));
      out[at + 1] = encode(Math.max(0, Math.min(1, grey + .6 * (green - grey))));
      out[at + 2] = encode(Math.max(0, Math.min(1, grey + .6 * (blue - grey))));
      out[at + 3] = 255;
    }
    if (oy % (fine ? 8 : 32) === 0) { await yieldTask(); if (cancelled()) return null; }
  }
  return out;
}
