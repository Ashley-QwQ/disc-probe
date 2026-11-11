// Canvas-only offline evidence. No screen capture or external requests.
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dir = path.join(__dirname, 'evidence', process.env.ROUGH_EVIDENCE || 'rough2'); fs.mkdirSync(dir, { recursive: true });
const cases = [
  { name: 'IMG_7498', pose: { tilt: 30, cx: -27, cy: -164, lx: -22, ly: -159, cz: 330, lz: 330 } },
  { name: 'IMG_7499', pose: { tilt: 27, cx: -43, cy: -149, lx: -38, ly: -144, cz: 330, lz: 330 } },
  { name: 'IMG_7503', pose: { tilt: 30, cx: -48, cy: -155, lx: -43, ly: -150, cz: 330, lz: 330 } }
];
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
  try {
    const context = await browser.newContext({ serviceWorkers: 'block' }), blocked = [], errors = [];
    await context.route('**/*', r => { if (new URL(r.request().url()).hostname === '127.0.0.1') return r.continue(); blocked.push(r.request().url()); return r.abort(); });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:18746/home/dev-preview.html');
    const results = [];
    for (const c of cases) {
      const result = await page.evaluate(async ({ pose }) => {
        const { reflectionPoint, gratingWavelength, photoSurface, RADIAL_APERTURE, radialMismatch, apertureRGB } = await import('./sim/surface.mjs');
        const p = { rotate: 0, exposure: 0, photoLook: 1, flash: 1, wear: 45, background: 0, ...pose };
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1200;
        const g = canvas.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 1200, 1200); g.fillStyle = '#000';
        // Six concentric rows of irregular black angular blocks on white.
        for (let row = 0; row < 6; row++) for (let col = 0; col < 56; col++) {
          const a = col / 56 * Math.PI * 2 + row * .019, w = (.35 + ((col * 7 + row * 3) % 9) / 18) * Math.PI * 2 / 56;
          g.beginPath(); g.arc(600, 600, (28 + row * 5) * 10, a, a + w);
          g.arc(600, 600, (25 + row * 5) * 10, a + w, a, true); g.closePath(); g.fill();
        }
        const designPNG = canvas.toDataURL().split(',')[1];
        const worker = new Worker('./sim/worker.mjs', { type: 'module' });
        const response = () => new Promise((resolve, reject) => { worker.onmessage = e => e.data.error ? reject(Error(e.data.error)) : resolve(e.data); worker.onerror = reject; });
        const load = response(); const bitmap = await createImageBitmap(canvas); worker.postMessage({ type: 'design', bitmap }, [bitmap]); await load;
        const timings = []; let image;
        try {
          for (const fine of [false, false, false, false, false, true, true, true]) {
            const done = response(); worker.postMessage({ id: 1, pose: p, size: fine ? 500 : 160, fine });
            const m = await done; timings.push({ fine, ms: m.ms, modelMs: m.modelMs, surfaceMs: m.ms - m.modelMs });
            if (fine) { image = new Uint8ClampedArray(m.buffer); }
          }
        } finally { worker.terminate(); }
        const raw = document.createElement('canvas'); raw.width = raw.height = 500;
        raw.getContext('2d').putImageData(new ImageData(image, 500, 500), 0, 0);
        const view = document.createElement('canvas'); view.width = view.height = 640; const v = view.getContext('2d');
        // Procedural blanket. Canvas presentation uses exactly the UI squash.
        v.fillStyle = '#10161e'; v.fillRect(0, 0, 640, 640);
        for (let y = 0; y < 640; y++) { const f = .5 + .5 * Math.sin(y * .025 + Math.sin(y * .011) * 2);
          v.fillStyle = `rgb(${22 + f * 26},${29 + f * 31},${36 + f * 32})`; v.fillRect(0, y, 640, 1); }
        const h = 580 * Math.cos(p.tilt * Math.PI / 180); v.drawImage(raw, 30, (640 - h) / 2, 580, h);
        const [hx, hy] = reflectionPoint(p), hn = Math.hypot(hx, hy), wavelengths = [];
        for (let d = -12; d <= 12; d++) wavelengths.push(gratingWavelength(hx + d * hx / hn, hy + d * hy / hn, p));
        const radialProfile = [];
        for (let d = -12; d <= 12; d += .25) {
          const q = radialMismatch(hx + d * hx / hn, hy + d * hy / hn, p)[0];
          radialProfile.push({ d, q, rgb: apertureRGB(q) });
        }
        // Only the recorded annulus, excluding transparent corners and the hub.
        const channels = [];
        for (let y = 0; y < 500; y++) for (let x = 0; x < 500; x++) {
          const r = Math.hypot((x + .5) * .24 - 60, 60 - (y + .5) * .24);
          if (r > 24.6 && r < 57.6) for (let c = 0; c < 3; c++) channels.push(image[(y * 500 + x) * 4 + c]);
        }
        const blank = new Uint8ClampedArray(160 * 160 * 4);
        const cancelled = await photoSurface(blank, 160, p, () => true, () => Promise.resolve());
        return { png: view.toDataURL().split(',')[1], raw: raw.toDataURL().split(',')[1], designPNG,
          pose: p, timings, mirror: [hx, hy], firstOrderNearMirrorNm: { min: Math.min(...wavelengths), max: Math.max(...wavelengths) },
          radialAperture: RADIAL_APERTURE, radialProfile,
          cancellation: cancelled === null, darkChannelFraction: channels.filter(v => v < 12).length / channels.length };
      }, c);
      for (const [field, suffix] of [['png', 'view'], ['raw', 'raw'], ['designPNG', 'design']]) {
        fs.writeFileSync(path.join(dir, `${c.name}-${suffix}.png`), Buffer.from(result[field], 'base64')); delete result[field];
      }
      results.push({ name: c.name, ...result });
    }
    fs.writeFileSync(path.join(dir, 'checks.json'), JSON.stringify({ results, blocked, errors }, null, 2));
    if (blocked.length || errors.length || results.some(r => !r.cancellation || r.firstOrderNearMirrorNm.max >= 380)) throw Error('rough2 checks failed');
    console.log(JSON.stringify({ results, blocked, errors }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
