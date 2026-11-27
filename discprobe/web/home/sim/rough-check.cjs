// Offline headless Edge checks. Exports canvas pixels only; no screen capture.
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dir = path.join(__dirname, 'evidence/rough'); fs.mkdirSync(dir, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, serviceWorkers: 'block' });
    const errors = [], blocked = [], requests = [];
    await context.route('**/*', r => { const url = new URL(r.request().url()); if (url.hostname === '127.0.0.1') { requests.push(url.pathname); return r.continue(); } blocked.push(url.origin); return r.abort(); });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:18746/home/dev-preview.html');
    await page.evaluate(() => {
      window.frames = []; window.lastFine = null; window.poses = [];
      const WorkerBase = Worker;
      window.Worker = class extends WorkerBase {
        constructor(...args) { super(...args); this.addEventListener('message', ({ data: m }) => {
          if (!m.buffer) return;
          window.frames.push({ ms: m.ms, modelMs: m.modelMs, fine: m.fine, id: m.id });
          if (m.fine) { const c = document.createElement('canvas'); c.width = c.height = m.size;
            c.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(m.buffer), m.size, m.size), 0, 0); window.lastFine = c.toDataURL().split(',')[1]; }
        }); }
        postMessage(m, ...args) {
          if (m.pose) window.poses.push(m.pose);
          if (m.type === 'design') {
            const c = document.createElement('canvas'); c.width = c.height = m.bitmap.width;
            const g = c.getContext('2d'); g.drawImage(m.bitmap, 0, 0);
            const rgba = g.getImageData(0, 0, c.width, c.height).data;
            window.testDesign = new Uint8Array(c.width * c.width); window.testWidth = c.width;
            for (let i = 0; i < window.testDesign.length; i++) { const j = i * 4;
              window.testDesign[i] = rgba[j + 3] >= 128 && .2126 * rgba[j] + .7152 * rgba[j + 1] + .0722 * rgba[j + 2] < 128 ? 1 : 0;
            }
          }
          super.postMessage(m, ...args);
        }
      };
    });
    const wait = () => page.waitForFunction(() => window.lastFine, null, { timeout: 60000 });
    const clear = () => page.evaluate(() => { window.lastFine = null; });
    const save = async name => { await wait(); fs.writeFileSync(path.join(dir, name + '.png'), Buffer.from(await page.evaluate(() => window.lastFine), 'base64')); };
    await page.locator('[data-v="look"]').click(); await save('default');
    const defaults = await page.locator('[data-photo="photoLook"]').isChecked();
    // Near-phone flash, tilted hand-held view. Move both optical handles using
    // their real keyboard handlers, then keep the default dev sample design.
    await clear();
    await page.locator('.pv-phone').focus(); for (let i = 0; i < 18; i++) await page.keyboard.press('ArrowDown');
    await page.locator('.pv-sun').focus(); for (let i = 0; i < 13; i++) await page.keyboard.press('ArrowDown');
    await page.locator('[data-k="tilt"]').fill('7'); await page.locator('[data-k="tilt"]').dispatchEvent('input');
    await save('phone-flash');
    const phonePose = await page.evaluate(() => window.poses.at(-1));
    await clear(); await page.locator('[data-photo="flash"]').uncheck(); await save('room-lamp');
    await clear(); await page.locator('[data-photo="photoLook"]').uncheck(); await save('pure-model');
    const disabled = await page.locator('[data-photo="wear"]').isDisabled();
    // Compare the actual UI off-switch output with the independent exact model
    // using the same demo bitmap captured before transfer to the worker.
    const offEquality = await page.evaluate(async () => {
      const { render } = await import('./sim/model.mjs');
      const lut = new Float64Array(await (await fetch('./sim/textures.bin')).arrayBuffer());
      const exact = await render(window.testDesign, window.testWidth, lut, window.poses.at(-1), 500);
      const img = new Image(); img.src = 'data:image/png;base64,' + window.lastFine; await img.decode();
      const c = document.createElement('canvas'); c.width = c.height = 500;
      const g = c.getContext('2d'); g.drawImage(img, 0, 0); const actual = g.getImageData(0, 0, 500, 500).data;
      let max = 0, mismatches = 0; for (let i = 0; i < exact.length; i++) { max = Math.max(max, Math.abs(exact[i] - actual[i])); if (exact[i] !== actual[i]) mismatches++; }
      return { max, mismatches, channels: exact.length };
    });
    await clear(); await page.locator('[data-photo="photoLook"]').check();
    await page.locator('[data-photo="flash"]').check();
    await page.locator('[data-photo="background"]').selectOption('1');
    await page.locator('[data-photo="wear"]').selectOption('100');
    await page.locator('[data-k="tilt"]').fill('-8'); await page.locator('[data-k="tilt"]').dispatchEvent('input');
    await save('table-saturated');
    const tablePose = await page.evaluate(() => window.poses.at(-1));
    // Actual continuous input: collect coarse frames and the settled fine pass.
    await page.evaluate(() => { window.frames = []; window.lastFine = null; });
    for (let i = 0; i < 24; i++) { await page.locator('.pv-sun').press(i < 12 ? 'ArrowRight' : 'ArrowLeft'); await page.waitForTimeout(24); }
    await wait(); const timings = await page.evaluate(() => window.frames);
    const layouts = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 960 });
      for (const lang of ['zh', 'en']) {
        if (await page.locator('html').getAttribute('lang') !== (lang === 'zh' ? 'zh-CN' : 'en')) await page.locator('#language').click();
        for (const theme of ['light', 'dark']) {
          await page.evaluate(t => document.documentElement.dataset.theme = t, theme);
          layouts.push(await page.evaluate(({ width, lang, theme }) => {
            const controls = [...document.querySelectorAll('[data-photo]')];
            return { width, lang, theme, count: controls.length, overflow: document.documentElement.scrollWidth > innerWidth,
              labels: controls.map(c => c.parentElement.textContent.trim()),
              heights: controls.map(c => c.closest('label').getBoundingClientRect().height),
              undefinedText: document.querySelector('.pv').textContent.includes('undefined') };
          }, { width, lang, theme }));
        }
      }
    }
    const math = await page.evaluate(async () => {
      const { reflectionPoint } = await import('./sim/surface.mjs');
      return { a: reflectionPoint({ cx: 0, cy: 0, lx: 20, ly: 0 }), b: reflectionPoint({ cx: 20, cy: 0, lx: 20, ly: 0 }) };
    });
    fs.writeFileSync(path.join(dir, 'checks.json'), JSON.stringify({ defaults, disabled, offEquality, phonePose, tablePose, timings, layouts, math, errors, blocked, requests: [...new Set(requests)] }, null, 2));
    if (!defaults || !disabled || offEquality.mismatches || errors.length || blocked.length || layouts.some(l => l.count !== 4 || l.overflow || l.undefinedText || l.heights.some(h => h < 44))) throw Error('Rough UI checks failed');
    console.log(JSON.stringify({ defaults, disabled, offEquality, phonePose, tablePose, timings, errors, blocked }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
