// Offline verification. Serve discprobe/web at 127.0.0.1:18746 first.
// PLAYWRIGHT_PATH may point to an existing installation; never installs anything.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const evidence = path.join(__dirname, 'evidence'); fs.mkdirSync(evidence, { recursive: true });
function python(code, args = []) {
  const r = spawnSync('python', ['-B', ...args, ...(code ? ['-c', code] : [])], { encoding: 'utf8', maxBuffer: 1024 * 1024 * 4 });
  if (r.status) throw Error(r.stderr || r.stdout); return r.stdout;
}
const designFile = path.join(evidence, 'design.npy');
python(`import numpy as np
n=6000
x=(np.arange(n)+.5)/n
y=x[:,None]
d=np.broadcast_to(x[None,:]<.5,(n,n)).copy()
d[((y>.58)&(y<.83))[:,0],:]=(np.arange(n)//3)%2
np.save(r'${designFile}',d)
`);
const cases = [
  { name: 'default', pose: {}, args: [] },
  { name: 'rotate37', pose: { rotate: 37 }, args: ['--rotate', '37'] },
  { name: 'moved', pose: { cx: 25, cy: 40, cz: 280, lx: -80, ly: 115, lz: 310 }, args: ['--camera', '25', '40', '280', '--flash', '-80', '115', '310'] },
];
for (const c of cases) python(null, ['-m', 'discprobe', 'simulate', '--design-npy', designFile, '--output', path.join(evidence, `python-${c.name}.png`), '--size', '500', ...c.args]);
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, serviceWorkers: 'block' });
    const blocked = [], errors = [];
    await context.route('**/*', route => { const u = new URL(route.request().url());
      if (u.hostname === '127.0.0.1') return route.continue(); blocked.push(u.origin); return route.abort(); });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:18746/home/dev-preview.html');
    const renders = [];
    for (const c of cases) {
      const result = await page.evaluate(async ({ pose }) => {
        const { render } = await import('./sim/model.mjs');
        const lut = new Float64Array(await (await fetch('./sim/textures.bin')).arrayBuffer());
        const n = 6000, design = new Uint8Array(n * n);
        for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) design[y * n + x] =
          (y + .5) / n > .58 && (y + .5) / n < .83 ? Math.floor(x / 3) % 2 : (x + .5) / n < .5;
        const start = performance.now(), data = await render(design, n, lut, pose, 500);
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 500;
        canvas.getContext('2d').putImageData(new ImageData(data, 500, 500), 0, 0);
        return { ms: performance.now() - start, png: canvas.toDataURL().split(',')[1] };
      }, c);
      fs.writeFileSync(path.join(evidence, `browser-${c.name}.png`), Buffer.from(result.png, 'base64'));
      renders.push({ name: c.name, ms: result.ms });
    }
    const workerPNG = await page.evaluate(async () => {
      const { SimView } = await import('./sim/view.mjs');
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => { v.stop(); reject(Error('Worker render timed out')); }, 15000);
        const v = new SimView({ render() {
          const c = document.createElement('canvas'); c.width = c.height = 6000;
          const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 6000, 6000);
          g.fillStyle = '#000'; g.fillRect(0, 0, 3000, 6000);
          g.fillStyle = '#fff'; g.fillRect(0, 3480, 6000, 1500);
          g.fillStyle = '#000'; for (let x = 3; x < 6000; x += 6) g.fillRect(x, 3480, 3, 1500);
          return c;
        } }, () => {
          if (v.status === 'error') { clearTimeout(timer); v.stop(); reject(Error('Worker failed')); }
          if (v.status === 'ready') { clearTimeout(timer); const png = v.canvas.toDataURL().split(',')[1]; v.stop(); resolve(png); }
        });
        v.request({});
      });
    });
    fs.writeFileSync(path.join(evidence, 'worker-default.png'), Buffer.from(workerPNG, 'base64'));
    // Observe actual worker output and UI long tasks, then exercise real pointer dragging.
    await page.evaluate(() => {
      window.workerFrames = []; const Original = window.Worker;
      window.Worker = class extends Original { constructor(...args) { super(...args); this.addEventListener('message', e => {
        if (e.data.buffer) window.workerFrames.push({ ms: e.data.ms, fine: e.data.fine, at: performance.now() });
      }); }};
      window.longTasks = []; new PerformanceObserver(l => window.longTasks.push(...l.getEntries().map(e => ({ start: e.startTime, ms: e.duration })))).observe({ type: 'longtask', buffered: false });
    });
    await page.locator('[data-v="look"]').click();
    await page.waitForFunction(() => window.workerFrames.some(f => f.fine), null, { timeout: 60000 });
    const initialization = await page.evaluate(() => ({ frames: window.workerFrames, longTasks: window.longTasks }));
    fs.writeFileSync(path.join(evidence, 'demo-stage.png'), Buffer.from(await page.locator('canvas.main').evaluate(c => c.toDataURL().split(',')[1]), 'base64'));
    await page.evaluate(() => {
      window.workerFrames = []; window.longTasks = []; window.rafTimes = []; window.measuring = true;
      let last; function tick(t) { if (last) window.rafTimes.push(t - last); last = t; if (window.measuring) requestAnimationFrame(tick); } requestAnimationFrame(tick);
    });
    const sun = await page.locator('.pv-sun').boundingBox();
    await page.mouse.move(sun.x + 22, sun.y + 22); await page.mouse.down();
    for (let i = 1; i <= 90; i++) {
      await page.mouse.move(sun.x + 22 + 65 * Math.sin(i / 90 * Math.PI * 2), sun.y + 22 + 45 * Math.sin(i / 90 * Math.PI));
      await page.waitForTimeout(16);
    }
    await page.mouse.up();
    await page.waitForFunction(() => window.workerFrames.some(f => f.fine), null, { timeout: 60000 });
    const drag = await page.evaluate(() => { window.measuring = false; return { frames: window.workerFrames, raf: window.rafTimes, longTasks: window.longTasks }; });
    // Both languages/themes and viewport classes in one bounded layout inspection.
    const layouts = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 960 });
      for (const lang of ['zh', 'en']) {
        if (await page.locator('html').getAttribute('lang') !== (lang === 'zh' ? 'zh-CN' : 'en')) await page.locator('#language').click();
        for (const theme of ['light', 'dark']) {
          await page.evaluate(t => document.documentElement.dataset.theme = t, theme);
          layouts.push(await page.evaluate(({ width, lang, theme }) => {
            const controls = [...document.querySelectorAll('.pv-ctl input')];
            const box = e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
            return { width, lang, theme, controls: controls.length, labels: controls.map(e => e.parentElement.textContent),
              cv: box(document.querySelector('.pv .cv')), column: box(document.querySelector('.pv .col-r')),
              overflow: document.documentElement.scrollWidth > innerWidth, undefinedText: document.querySelector('.pv').textContent.includes('undefined') };
          }, { width, lang, theme }));
        }
      }
    }
    // Range controls, reset, keyboard bounds, CD and leaving/re-entering.
    await page.setViewportSize({ width: 1440, height: 960 });
    for (const [key, value] of [['rotate', '37'], ['tilt', '12'], ['exposure', '2'], ['cz', '280'], ['lz', '310']]) {
      await page.locator(`[data-k="${key}"]`).fill(value); await page.locator(`[data-k="${key}"]`).dispatchEvent('input');
    }
    await page.locator('.pv-phone').focus(); await page.keyboard.press('ArrowLeft');
    await page.locator('[data-a="reset-look"]').click();
    const reset = await page.locator('[data-k="rotate"]').inputValue();
    await page.locator('[data-v="off"]').click(); await page.locator('[data-v="read"]').click();
    await page.locator('#scenario').selectOption('cd'); await page.locator('[data-v="look"]').click();
    const cd = await page.locator('.cv-note').textContent();
    await page.locator('#scenario').selectOption('empty');
    const empty = await page.locator('.empty-c').isVisible();
    // Fail the local texture-table request to check the recoverable error state.
    await context.route('**/sim/textures.bin', route => route.abort());
    await page.locator('#scenario').selectOption('dvd');
    await page.locator('[data-v="look"]').click();
    await page.waitForFunction(() => /failed|没有完成/.test(document.querySelector('.cv-note').textContent));
    const errorState = await page.locator('.cv-note').textContent();
    const result = { renders, initialization, drag, layouts, reset, cd, empty, errorState, errors, blocked };
    fs.writeFileSync(path.join(evidence, 'browser-check.json'), JSON.stringify(result, null, 2));
    if (errors.length || layouts.some(l => l.overflow || l.undefinedText || l.controls !== 5) || reset !== '0' || !empty) throw Error('Browser checks failed; see browser-check.json');
  } finally { await browser.close(); }
  console.log(python(`import numpy as np,json
from pathlib import Path
from PIL import Image
p=Path(r'${evidence}')
results=[]
for name in ['default','rotate37','moved']:
 a=np.array(Image.open(p/('python-'+name+'.png'))).astype(float)
 b=np.array(Image.open(p/('browser-'+name+'.png')))[...,:3].astype(float)
 d=np.abs(a-b)
 results.append(dict(name=name,mae=float(d.mean()),max=float(d.max()),equal_percent=float((d==0).mean()*100),python_mean=a.mean((0,1)).tolist(),browser_mean=b.mean((0,1)).tolist(),peak_rows_python=a.mean(1).argmax(0).tolist(),peak_rows_browser=b.mean(1).argmax(0).tolist()))
a=np.array(Image.open(p/'python-default.png')).astype(float)
b=np.array(Image.open(p/'worker-default.png'))[...,:3].astype(float)
results.append(dict(name='worker-default',mae=float(np.abs(a-b).mean()),max=float(np.abs(a-b).max())))
(p/'comparison.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))`));
  // Large reproducible input is transient; the generator and PNG evidence remain.
  fs.unlinkSync(designFile);
})().catch(e => { console.error(e); process.exitCode = 1; });

