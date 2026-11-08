/** Optional browser integration test. Runtime users do not need Node/Playwright.
 * Run: node tests/editor_browser.mjs (requires playwright + its Chromium).
 * No drive or ISO writer is invoked. Everything created lives in a temp folder.
 */
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const directory = await mkdtemp(join(tmpdir(), 'discprobe-editor-browser-'));
const geometry = join(directory, 'synthetic test geometry.json');
await writeFile(geometry, JSON.stringify({ fit: {
  u: 180045, v: 5.55, bit_nm_assumed: 133.3, media: 'dvd',
  chi2_per_dof: 1, angle_sigma_measured_span_deg: 0.1,
} }));
const server = spawn(process.env.PYTHON || 'python', ['-m', 'discprobe', 'editor', '--no-browser',
  '--geo', geometry, '--output-dir', join(directory, 'art with spaces')], { cwd: root });
let output = '', serverErrors = '';
server.stdout.on('data', b => { output += b; });
server.stderr.on('data', b => { serverErrors += b; });
const waitFor = async (fn, timeout = 20_000) => {
  const end = Date.now() + timeout;
  while (!fn()) {
    if (Date.now() > end) throw new Error('Timed out waiting for local editor: ' + output + serverErrors);
    await new Promise(resolve => setTimeout(resolve, 50));
  }
};
let browser;
try {
  await waitFor(() => /http:\/\/127\.0\.0\.1:\d+\/#\S+/.test(output));
  const url = output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/)[0];
  browser = await chromium.launch({ headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}) });
  const page = await browser.newPage({ viewport: { width: 1480, height: 1050 }, acceptDownloads: true });
  const errors = [], requests = [];
  // Test-only observation: retain weak references, never application buffers.
  // It checks the exact offscreen raster drawn to the visible stage, not a
  // screenshot reduced to the monitor's pixel count.
  await page.addInitScript(() => {
    window.__editorCanvases = [];
    const create = Document.prototype.createElement;
    Document.prototype.createElement = function (...args) {
      const result = create.apply(this, args);
      if (String(args[0]).toLowerCase() === 'canvas') window.__editorCanvases.push(new WeakRef(result));
      return result;
    };
    const draw = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function (...args) {
      if (this.canvas.id === 'stage' && args[0] instanceof HTMLCanvasElement) window.__editorArt = new WeakRef(args[0]);
      return draw.apply(this, args);
    };
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  page.on('dialog', dialog => dialog.accept());
  await page.goto(url);
  await page.waitForSelector('html[data-ready="true"]');
  await page.waitForFunction(() => document.getElementById('status').textContent.includes('添加图片'));
  assert.equal(await page.locator('#media-label').inputValue(), 'DVD · 120 mm');
  assert.match(await page.locator('#geometry-label').inputValue(), /已选几何/);
  console.log('ok: empty canvas, config, worker and static assets load');

  const sources = await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = 320; c.height = 240;
    const x = c.getContext('2d');
    x.fillStyle = '#20d4be'; x.fillRect(0, 0, 320, 240);
    x.fillStyle = '#111111'; x.fillRect(40, 25, 25, 140); x.fillRect(40, 25, 95, 25); x.fillRect(40, 80, 70, 25);
    for (let n = 0; n < 128; n++) { x.fillStyle = `rgb(${n * 2} ${n * 2} ${n * 2})`; x.fillRect(150 + n, 50, 1, 115); }
    const first = c.toDataURL('image/png').split(',')[1];
    x.clearRect(0, 0, 320, 240); x.fillStyle = '#e97336'; x.beginPath(); x.arc(160, 120, 60, 0, Math.PI * 2); x.fill();
    return [first, c.toDataURL('image/png').split(',')[1]];
  });
  await page.locator('#image-files').setInputFiles(sources.map((s, i) => ({
    name: i ? 'orange circle.png' : 'asymmetric "F" & gray.png', mimeType: 'image/png', buffer: Buffer.from(s, 'base64'),
  })));
  await page.waitForFunction(() => document.querySelectorAll('#layer-list li').length === 2);
  await page.waitForFunction(() => document.getElementById('status').textContent.includes('2 个图层'));
  assert.equal(await page.locator('#layer-blend').inputValue(), 'source-over');
  // Hide the top layer, select the F image, then sample its unprocessed cyan.
  await page.locator('#layer-list li').first().locator('input[type=checkbox]').uncheck();
  await page.locator('#layer-list li').last().locator('button').click();
  await page.locator('details').evaluateAll(items => { for (const item of items) item.open = true; });
  await page.locator('#key-pick').click();
  let bounds = await page.locator('#viewport').boundingBox();
  let scale = Math.min(bounds.width - 72, bounds.height - 72) / 120;
  await page.mouse.click(bounds.x + bounds.width / 2 + 45 * scale, bounds.y + bounds.height / 2 + 29 * scale);
  assert.equal(await page.locator('#key-color').inputValue(), '#20d4be');
  await page.waitForFunction(() => document.getElementById('status').textContent.includes('尚未应用'));
  await page.locator('#key-cancel').click();
  await page.locator('#key-color').fill('#20d4be');
  await page.locator('#key-preview').click();
  await page.locator('#key-apply').click();
  await page.waitForFunction(() => !document.getElementById('status').textContent.includes('尚未应用') && document.getElementById('status').textContent.includes('2 个图层'));
  console.log('ok: two source layers, safe filenames, eyedropper, cancel and confirmed chroma key');

  bounds = await page.locator('#viewport').boundingBox();
  const center = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
  await page.mouse.move(center.x + 10, center.y - 30);
  await page.mouse.down(); await page.mouse.move(center.x + 50, center.y - 50, { steps: 6 }); await page.mouse.up();
  const movedX = Number(await page.locator('#layer-x').inputValue());
  assert(movedX > 1, 'drag changed physical layer x');
  await page.locator('#undo').click();
  assert.equal(Number(await page.locator('#layer-x').inputValue()), 0);
  await page.locator('#redo').click();
  assert.equal(Number(await page.locator('#layer-x').inputValue()), movedX);
  await page.locator('#zoom-in').click(); assert.equal(await page.locator('#zoom-label').textContent(), '125%');
  await page.locator('#zoom-fit').click();
  await page.locator('#layer-rotation').fill('17'); await page.locator('#layer-rotation').press('Tab');
  await page.locator('#adjust-exposure-number').fill('0.4'); await page.locator('#adjust-exposure-number').press('Tab');
  await page.locator('#adjust-gamma-number').fill('1.25'); await page.locator('#adjust-gamma-number').press('Tab');
  await page.locator('#tone-curve').click({ position: { x: 140, y: 62 } });
  await page.locator('[data-panel="detail"]').click();
  await page.locator('#adjust-sharpen-number').fill('12'); await page.locator('#adjust-sharpen-number').press('Tab');
  await page.locator('[data-panel="output"]').click();
  await page.locator('#output-mode').selectOption('blue-noise');
  await page.locator('#output-seed-number').fill('42'); await page.locator('#output-seed-number').press('Tab');
  await page.locator('#preview-mode').selectOption('output');
  await page.waitForFunction(() => document.getElementById('status').textContent.includes('2 个图层'));
  assert.equal(await page.locator('#status').getAttribute('data-error'), 'false');
  console.log('ok: physical drag, zoom, undo/redo, tone curve, detail and output adjustments');

  const projectDownload = page.waitForEvent('download');
  await page.locator('#save-project').click();
  const project = JSON.parse(await readFile(await (await projectDownload).path(), 'utf8'));
  assert.equal(project.assets.length, 2); assert(project.assets[0].source.startsWith('data:image/png;base64,'));
  assert.equal(project.state.layers[0].key.color.join(','), '32,212,190');
  assert.equal(project.state.layers[0].adjustments.gamma, 1.25);
  assert(project.state.layers[0].adjustments.curve.length > 2);
  assert.equal(project.state.output.mode, 'blue-noise');
  await page.locator('#project-file').setInputFiles({ name: 'roundtrip.discproject.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(project)) });
  await page.waitForFunction(() => document.querySelectorAll('#layer-list li').length === 2 && document.getElementById('status').textContent.includes('2 个图层'));
  assert.equal(Number(await page.locator('#layer-x').inputValue()), movedX);
  const profileDownload = page.waitForEvent('download'); await page.locator('#save-profile').click();
  const profile = JSON.parse(await readFile(await (await profileDownload).path(), 'utf8'));
  assert.equal(profile.output.mode, 'blue-noise'); assert.equal(profile.media, 'dvd');
  // Native preview must use the same annular flatten/diffusion pipeline as the
  // exported file; FS is sensitive to even a transparent hole outside artwork.
  await page.locator('#output-mode').selectOption('floyd-steinberg');
  await page.locator('#preview-size').selectOption('6000');
  await page.waitForFunction(() => document.getElementById('status').textContent.includes('原生网格预览'), null, { timeout: 120_000 });
  const native = await page.evaluate(async () => {
    const art = window.__editorArt.deref();
    const pixels = art.getContext('2d').getImageData(0, 0, art.width, art.height).data;
    const binary = new Uint8Array(art.width * art.height);
    for (let i = 0; i < binary.length; i++) binary[i] = pixels[i * 4 + 3] && pixels[i * 4] < 128 ? 1 : 0;
    const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', binary))].map(v => v.toString(16).padStart(2, '0')).join('');
    const nativeCanvases = window.__editorCanvases.map(ref => ref.deref()).filter(c => c && c.width * c.height > 12_000_000);
    return { width: art.width, sha256, largeCanvases: nativeCanvases.length };
  });
  assert.equal(native.width, 6000);
  assert(native.largeCanvases <= 1, 'native layers and intermediate canvases are released, not cached');
  console.log('ok: portable project roundtrip preserves sources, key, transforms and tone; output profile saves');

  await page.screenshot({ path: join(directory, 'editor-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: join(directory, 'editor-mobile.png'), fullPage: true });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'mobile has no horizontal overflow');
  await page.setViewportSize({ width: 1480, height: 1050 });
  await page.locator('#export-open').click();
  await page.locator('#export-name').fill('test artwork 中文');
  await page.locator('#export-confirm').click();
  await page.locator('#export-result').waitFor({ state: 'visible', timeout: 120_000 });
  const path = await page.locator('#exported-path').inputValue();
  const command = await page.locator('#export-command').inputValue();
  assert(path.startsWith(directory)); assert(command.includes('--diameter-mm 120')); assert(command.includes('--picture'));
  const check = execFileSync(process.env.PYTHON || 'python', ['-c',
    "import sys,json,hashlib,numpy as np; from PIL import Image; from discprobe.imagedisc import picture_design; p=sys.argv[1]; a=np.asarray(Image.open(p).convert('L')); b=picture_design(p,120); print(json.dumps({'shape':list(a.shape),'levels':np.unique(a).tolist(),'same':bool(np.array_equal(b,a<128)),'dark':int(b.sum()),'sha256':hashlib.sha256((a<128).astype(np.uint8).tobytes()).hexdigest()}))", path], { cwd: root, encoding: 'utf8' });
  const checkResult = JSON.parse(check.trim());
  assert.deepEqual(checkResult.shape, [6000, 6000]); assert.deepEqual(checkResult.levels, [0, 255]);
  assert(checkResult.same); assert(checkResult.dark > 1000);
  assert.equal(checkResult.sha256, native.sha256, '6000² native FS preview equals exported binary PNG pixel-for-pixel');
  await waitFor(() => server.exitCode !== null);
  assert.equal(server.exitCode, 0); assert.match(output, /Next, paste this command/);
  assert.deepEqual(errors, []);
  const origin = new URL(url).origin;
  assert(requests.every(r => r.startsWith(origin) || r.startsWith('data:') || r.startsWith('blob:')), 'no outside network requests');
  console.log('ok: 6000² grayscale + binary export, exact existing --picture roundtrip, shell command and terminal return');
  console.log(JSON.stringify({ directory, exportPath: path, darkPixels: checkResult.dark,
    requests: requests.length, pageErrors: errors.length }, null, 2));
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) server.kill('SIGINT');
}
