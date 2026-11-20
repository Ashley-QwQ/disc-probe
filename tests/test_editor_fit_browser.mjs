// Offline editor in Edge. Measurements use the screen disc outline and the CSS opening.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, resolve, sep } from 'node:path';

const home = resolve('discprobe/web/home');
const fonts = resolve(home, '../fonts');
const out = resolve(process.env.EDITOR_FIT_OUT ?? tmpdir());
const phase = process.env.EDITOR_FIT_PHASE;
const baseline = phase === 'before' && process.env.EDITOR_FIT_BASE;
const baselineDesign = baseline && execFileSync('git', ['show', baseline + ':discprobe/web/home/design.js']);
const shots = phase && join(out, 'shots', phase);
if (shots) await mkdir(shots, { recursive: true });
await mkdir(out, { recursive: true });
const profile = await mkdtemp(join(out, 'edge-fit-'));
const extension = join(profile, 'test-zoom');
await mkdir(extension);
await writeFile(join(extension, 'manifest.json'), JSON.stringify({
  manifest_version: 3, name: 'Editor fit test zoom', version: '1.0', permissions: ['tabs'],
  background: { service_worker: 'zoom.js' },
}));
await writeFile(join(extension, 'zoom.js'), 'chrome.runtime.onInstalled.addListener(() => {});');
const html = (await readFile(join(home, 'index.html'), 'utf8'))
  .replace('data-handshake="pending"', 'data-handshake="fixture" data-theme="light"')
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '').replace('<head>', '<head><base href="/home/">')
  .replace('</body>', `<script type="module">
    import * as design from './design.js';
    const item = { kind: 'unset', name: 'DVD', mid: '', s: 'none' };
    const api = { $: id => document.getElementById(id), lang: () => window.fixtureLanguage ?? 'en',
      T: () => ({}), current: () => ({ col: 'dvd', item }), focusDisc: () => null,
      reduce: false, nextWhy() {}, state: () => ({}) };
    window.design = design;
    window.enter = (options = {}) => {
      const done = design.start(api, { newPlan: true, noDisc: true, fly: false,
        name: 'Short window DVD', ...options });
      window.actions = design.editorActions();
      return done;
    };
    window.measure = () => {
      const { cv, canvas, surface, shadow, zoom } = actions.editor.h.dom();
      const { s, dpr } = actions.editor.h.view();
      const frame = cv.getBoundingClientRect(), disc = shadow.getBoundingClientRect();
      const stage = surface.getBoundingClientRect();
      const x = disc.x + disc.width / 2, y = disc.y + disc.height / 2;
      const alpha = (x, y) => canvas.getContext('2d').getImageData(
        Math.round((x - stage.x) * canvas.width / stage.width),
        Math.round((y - stage.y) * canvas.height / stage.height), 1, 1).data[3];
      const rims = disc.width > 8 && !canvas.style.transform ? [
        alpha(x, disc.top + 2), alpha(x, disc.bottom - 2),
        alpha(disc.left + 2, y), alpha(disc.right - 2, y),
      ] : [];
      return { frame: frame.toJSON(), disc: disc.toJSON(), stage: stage.toJSON(),
        rims, s, dpr, zoom: zoom.textContent, view: actions.state().view,
        mask: getComputedStyle(surface).maskPosition, transform: getComputedStyle(canvas).transform,
        window: [innerWidth, innerHeight, devicePixelRatio] };
    };
  </script></body>`);
const mime = { '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
const server = createServer(async (req, res) => {
  try {
    const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (path === '/') {
      res.setHeader('Content-Type', 'text/html;charset=utf-8');
      res.end(html);
      return;
    }
    const file = path.startsWith('/fonts/') ? resolve(fonts, path.slice(7)) : resolve(home, path.slice(6));
    if ((!path.startsWith('/home/') && !path.startsWith('/fonts/')) ||
        (!file.startsWith(home + sep) && !file.startsWith(fonts + sep)) || /b[l]ind/i.test(file)) {
      res.writeHead(404).end();
      return;
    }
    const body = baselineDesign && file === join(home, 'design.js') ? baselineDesign : await readFile(file);
    res.setHeader('Content-Type', mime[extname(file)] ?? 'application/octet-stream');
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(0, '127.0.0.1');
await once(server, 'listening');
const edge = spawn(process.env.KIT_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', [
  '--headless=new', '--mute-audio', '--disable-background-networking', '--no-first-run',
  '--no-default-browser-check', '--remote-debugging-pipe', '--enable-unsafe-extension-debugging',
  `--user-data-dir=${profile}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'], windowsHide: true });

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const dimensions = [[1918, 893], [1366, 768], [1440, 800], [1280, 720]];
const views = ['proj', 'burn', 'lamp'];
const measurements = [], errors = [], pending = new Map();
let seq = 0, buffered = '';
edge.stdio[4].setEncoding('utf8');
edge.stdio[4].on('data', chunk => {
  buffered += chunk;
  let end;
  while ((end = buffered.indexOf('\0')) !== -1) {
    const message = JSON.parse(buffered.slice(0, end));
    buffered = buffered.slice(end + 1);
    pending.get(message.id)?.(message);
    pending.delete(message.id);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params);
  }
});
const cdp = (method, params = {}, sessionId) => new Promise((ok, fail) => {
  const id = ++seq;
  const timer = setTimeout(() => { pending.delete(id); fail(Error(method + ' timed out')); }, 30000);
  pending.set(id, message => {
    clearTimeout(timer);
    if (message.error) fail(Error(JSON.stringify(message.error)));
    else ok(message.result);
  });
  edge.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + '\0', err => {
    if (err) { clearTimeout(timer); pending.delete(id); fail(err); }
  });
});
try {
  const { id: extensionId } = await cdp('Extensions.loadUnpacked', { path: extension });
  let tab, worker;
  for (let i = 0; i < 200 && !(tab && worker); i++) {
    const { targetInfos } = await cdp('Target.getTargets');
    tab = targetInfos.find(target => target.type === 'page');
    worker = targetInfos.find(target => target.url === `chrome-extension://${extensionId}/zoom.js`);
    if (!(tab && worker)) await pause(25);
  }
  assert.ok(tab && worker, 'Edge starts with the local zoom extension');
  const attach = async target => (await cdp('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;
  const pageSession = await attach(tab), zoomSession = await attach(worker);
  const send = (method, params) => cdp(method, params, pageSession);
  const run = async (expression, sessionId = pageSession) => {
    const result = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result?.value;
  };
  const until = async expression => {
    for (let i = 0; i < 240; i++) {
      if (await run(expression)) return;
      await pause(25);
    }
    assert.fail(expression);
  };
  const frame = () => run('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))');
  const viewport = (width, height) => send('Emulation.setDeviceMetricsOverride', {
    width, height, deviceScaleFactor: 1, mobile: false,
  });
  const browserZoom = async zoom => {
    assert.equal(await run(`(async () => {
      const [tab] = await chrome.tabs.query({ active: true });
      await chrome.tabs.setZoom(tab.id, ${zoom});
      return chrome.tabs.getZoom(tab.id);
    })()`, zoomSession), zoom);
    await until(`Math.abs(devicePixelRatio - ${zoom}) < .001`);
  };
  const select = view => run(`document.querySelector('[data-v="${view}"]').click()`);
  const shot = async name => {
    const { data } = await send('Page.captureScreenshot', { format: 'png' });
    await writeFile(join(shots, name + '.png'), Buffer.from(data, 'base64'));
  };
  function check(name, m) {
    const { disc, frame } = m;
    const margins = [disc.left - frame.left, frame.right - disc.right,
      disc.top - frame.top, frame.bottom - disc.bottom];
    measurements.push({ name, margins, ...m });
    if (phase === 'before') return;
    assert.ok(disc.width > 8 && margins.every(margin => margin >= 2), JSON.stringify({ name, margins, ...m }));
    assert.ok(m.rims.length === 4 && m.rims.every(alpha => alpha >= 220), JSON.stringify({ name, ...m }));
    assert.equal(m.zoom, 'Fit', name);
  }
  const measure = async (name) => { await frame(); check(name, await run('measure()')); };

  await send('Page.enable');
  await send('Runtime.enable');
  for (const [width, height] of dimensions) {
    const size = `${width}x${height}`;
    await viewport(width, height);
    await send('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/?size=${size}` });
    await until(`location.search === '?size=${size}' && typeof enter === 'function'`);
    for (const zoom of [1, .9, 1.1]) {
      await browserZoom(zoom);
      const label = size + ' at ' + zoom;
      await run('enter({ dropIn: true })');
      await until('document.querySelector(".cv canvas").width > 300 && actions.editor.palette');
      await run('document.fonts.ready');
      await measure(label + ' new');
      const entry = await run(`new Promise(resolve => {
        const cv = document.querySelector('.cv');
        const samples = [];
        const observer = new ResizeObserver(() => samples.push(measure()));
        observer.observe(cv);
        enter({ dropIn: true });
        cv.animate([{ bottom: '100px' }, { bottom: '290px' }, { bottom: '100px' }],
          { duration: 320 }).finished.then(() => { observer.disconnect(); resolve(samples); });
      })`);
      assert.ok(entry.length > 2, label);
      for (const [i, m] of entry.entries()) check(label + ' entering ' + i, m);
      await measure(label + ' settled');

      await run(`(async () => {
        const image = document.createElement('canvas'); image.width = image.height = 160;
        const g = image.getContext('2d');
        g.fillStyle = '#ddd'; g.fillRect(0, 0, 160, 160);
        g.fillStyle = '#344754'; g.fillRect(16, 26, 124, 96);
        g.fillStyle = '#c09e66'; g.beginPath(); g.arc(110, 65, 23, 0, 2 * Math.PI); g.fill();
        const file = new File([await new Promise(r => image.toBlob(r))], 'short-window.png', { type: 'image/png' });
        const data = new DataTransfer(); data.items.add(file);
        const input = document.querySelector('.f-img');
        input.files = data.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      })()`);
      await until('actions.state().layers.length === 1');
      await run('(async () => { window.saved = await actions.projectText(); })()');
      for (const view of views) {
        await select(view);
        await measure(label + ' imported ' + view);
      }
      await run(`enter({ work: { id: 'fit-${zoom}', name: 'Short window DVD',
        media: 'dvd', updated_at: '2026-11-20', text: saved } })`);
      await until('actions.state().layers.length === 1');
      for (const view of views) {
        await select(view);
        await measure(label + ' existing ' + view);
      }
      if (shots && zoom === 1 && (width === 1918 || width === 1366)) {
        for (const theme of ['light', 'dark']) {
          await run(`document.documentElement.dataset.theme = '${theme}'`);
          for (const view of views) {
            await select(view);
            await frame();
            await shot(`${size}-${theme}-${view}`);
          }
        }
      }
    }
    await run(`for (let i = 0; i < 4; i++) dispatchEvent(new KeyboardEvent('keydown', { key: '+' }))`);
    await frame();
    const enlarged = await run('measure()');
    await viewport(width, height - 80);
    await frame();
    const resized = await run('measure()');
    assert.equal(resized.s, enlarged.s, size + ' preserves manual zoom');
    assert.ok(enlarged.disc.width > 1.5 * measurements.at(-1).disc.width, size + ' zoomed in');
    await run(`dispatchEvent(new KeyboardEvent('keydown', { key: '0' }))`);
    await measure(size + ' reset');
    if (width === 1918) {
      await viewport(width, height);
      await browserZoom(1);
      await run(`(() => {
        const work = JSON.parse(saved);
        work.cell = .005;
        enter({ work: { id: 'fine-grid', name: 'Fine-grid DVD',
          media: 'dvd', updated_at: '2026-11-20', text: JSON.stringify(work) } });
      })()`);
      await until('actions.state().cell === .005 && actions.state().layers.length === 1');
      await select('lamp');
      await measure(size + ' fine grid fit');
      await run(`(() => {
        const { canvas, surface } = actions.editor.h.dom();
        const { cx, cy, s } = actions.editor.h.view();
        const stage = surface.getBoundingClientRect();
        canvas.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: -100 * Math.log(6.5 / s),
          clientX: stage.x + cx, clientY: stage.y + cy, cancelable: true }));
      })()`);
      await frame();
      const sample = await run('measure()');
      assert.equal(sample.zoom, '3%');
      assert.ok(sample.disc.top < sample.frame.top && sample.disc.bottom > sample.frame.bottom);
      if (shots) await shot(size + '-manual-3-percent-lamp');
      measurements.push({ name: size + ' manual fine grid', ...sample });
      await run(`dispatchEvent(new KeyboardEvent('keydown', { key: '0' }))`);
      await measure(size + ' fine grid reset');
    }
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ measurements: measurements.length, screenshots: shots ? 13 : 0 }));
} finally {
  if (phase) await writeFile(join(out, `fit-${phase}.json`), JSON.stringify({ measurements, errors }, null, 2));
  edge.kill();
  server.close();
  await pause(500);
  assert.ok(profile.startsWith(out + sep));
  await rm(profile, { recursive: true, force: true, maxRetries: 6, retryDelay: 200 });
}
