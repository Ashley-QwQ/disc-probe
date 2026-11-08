/** Optional real-browser failure/recovery test. Requires Playwright + Chromium.
 * node --test tests/editor_recovery.test.mjs
 * Only the test changes getImageData. Native readback retained by the observer
 * verifies what the UI actually draws; production code never uses that escape.
 * No drive, ISO writer, or successful artwork export is invoked.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

test('Canvas readback failure preserves originals and blocks export until a successful recheck', { timeout: 60_000 }, async () => {
  const directory = await mkdtemp(join(tmpdir(), 'discprobe-editor-recovery-'));
  const geometry = join(directory, 'geometry.json'), exports = join(directory, 'exports');
  await writeFile(geometry, JSON.stringify({ fit: {
    u: 180045, v: 5.55, bit_nm_assumed: 133.3, media: 'dvd',
    chi2_per_dof: 1, angle_sigma_measured_span_deg: 0.1,
  } }));
  const sourcePath = join(root, 'docs/showcase/figures_tuned_7312.jpg');
  const sourceBytes = await readFile(sourcePath);
  const sourceURL = 'data:image/jpeg;base64,' + sourceBytes.toString('base64');
  const server = spawn(process.env.PYTHON || 'python', ['-m', 'discprobe', 'editor', '--no-browser',
    '--geo', geometry, '--output-dir', exports], { cwd: root });
  let stdout = '', stderr = '', browser;
  server.stdout.on('data', data => { stdout += data; });
  server.stderr.on('data', data => { stderr += data; });
  try {
    const deadline = Date.now() + 15_000;
    while (!/http:\/\/127\.0\.0\.1:\d+\/#\S+/.test(stdout)) {
      if (server.exitCode !== null || Date.now() > deadline) throw new Error(stdout + stderr);
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    const url = stdout.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/)[0];
    browser = await chromium.launch({ headless: true,
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
    });
    const page = await browser.newPage({ viewport: { width: 1480, height: 1050 }, acceptDownloads: true });
    const errors = [], exportRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    page.on('request', request => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/export') exportRequests.push(request.url());
    });
    await page.addInitScript(() => {
      const prototype = CanvasRenderingContext2D.prototype;
      const nativeRead = prototype.getImageData;
      window.__recoveryNativeRead = nativeRead;
      window.__blockedLargeReads = 0;
      const alteredRead = function (...args) {
        if (this.canvas.width * this.canvas.height > 1000) window.__blockedLargeReads++;
        const pixels = nativeRead.apply(this, args);
        const tile = [22, 91, 180, 74, 200, 35, 70, 212, 110, 245, 34, 133, 85, 66, 141, 250,
          49, 160, 211, 94, 234, 180, 46, 190, 121, 75, 250, 233, 67, 218, 153, 164];
        for (let i = 0; i < pixels.data.length; i++) pixels.data[i] = tile[i % tile.length];
        return pixels;
      };
      window.__recoverySetFault = active => { prototype.getImageData = active ? alteredRead : nativeRead; };
      window.__recoverySetFault(true);
      const draw = prototype.drawImage;
      prototype.drawImage = function (...args) {
        if (this.canvas.id === 'stage' && args[0] instanceof HTMLCanvasElement) window.__recoveryArt = new WeakRef(args[0]);
        return draw.apply(this, args);
      };
    });
    await page.goto(url);
    await page.waitForSelector('html[data-ready="true"][data-pixel-status="fail"]');
    await page.waitForSelector('#diagnosticText', { state: 'attached' });
    await page.waitForSelector('#rerunDiagnostics', { state: 'attached' });
    assert.equal(await page.locator('#export-open').isDisabled(), true);
    assert.equal(await page.locator('#export-confirm').isDisabled(), true);
    assert.match(await page.locator('#diagnosticText').inputValue(), /Canvas integrity: FAIL/);

    await page.locator('#image-files').setInputFiles(sourcePath);
    await page.waitForFunction(() => document.querySelectorAll('#layer-list li').length === 1
      && document.getElementById('status').textContent.includes('仅显示原图'));
    const visibleOriginal = await page.evaluate(async source => {
      const image = new Image(); image.src = source; await image.decode();
      const art = window.__recoveryArt.deref(), size = art.width;
      const scale = size / 120, widthMm = 104 * Math.min(1, image.naturalWidth / image.naturalHeight);
      const width = Math.round(widthMm * scale), height = Math.round(width * image.naturalHeight / image.naturalWidth);
      const raster = document.createElement('canvas'); raster.width = width; raster.height = height;
      const r = raster.getContext('2d', { willReadFrequently: true }); r.imageSmoothingQuality = 'high'; r.drawImage(image, 0, 0, width, height);
      const reference = document.createElement('canvas'); reference.width = reference.height = size;
      const x = reference.getContext('2d', { willReadFrequently: true }); x.fillStyle = '#ffffff'; x.fillRect(0, 0, size, size);
      x.imageSmoothingQuality = 'high';
      const w = widthMm * scale, h = w * image.naturalHeight / image.naturalWidth;
      x.drawImage(raster, (size - w) / 2, (size - h) / 2, w, h);
      x.globalCompositeOperation = 'destination-in'; x.beginPath();
      x.arc(size / 2, size / 2, 56 * scale, 0, Math.PI * 2);
      x.arc(size / 2, size / 2, 24.5 * scale, 0, Math.PI * 2, true); x.fill('evenodd');
      const native = window.__recoveryNativeRead;
      const actual = native.call(art.getContext('2d'), 0, 0, size, size);
      const expected = native.call(x, 0, 0, size, size);
      let differences = 0, maxDelta = 0;
      for (let i = 0; i < actual.data.length; i++) {
        const delta = Math.abs(actual.data[i] - expected.data[i]);
        if (delta > 1) differences++;
        maxDelta = Math.max(maxDelta, delta);
      }
      window.__recoveryOriginal = actual;
      return { differences, maxDelta, size, largeReads: window.__blockedLargeReads };
    }, sourceURL);
    assert.equal(visibleOriginal.size, 1200);
    assert.equal(visibleOriginal.differences, 0, 'blocked UI still draws the actual source photograph, not placeholder bars');
    assert.equal(visibleOriginal.largeReads, 0, 'the blocked app does not extract pixels from the user image');
    assert.equal(exportRequests.length, 0);

    const downloadPromise = page.waitForEvent('download');
    await page.locator('#save-project').click();
    const download = await downloadPromise;
    const project = JSON.parse(await readFile(await download.path(), 'utf8'));
    assert.equal(project.assets.length, 1);
    assert.equal(project.state.layers.length, 1);
    assert(Buffer.from(project.assets[0].source.split(',')[1], 'base64').equals(sourceBytes),
      'blocked-session project preserves the original compressed asset byte-for-byte');
    await page.screenshot({ path: join(directory, 'blocked-original.png'), fullPage: true });

    await page.evaluate(() => { window.__previousRecoveryArt = window.__recoveryArt.deref(); window.__recoverySetFault(false); });
    await page.locator('details').evaluateAll(items => { for (const item of items) item.open = true; });
    await page.locator('#rerunDiagnostics').click();
    await page.waitForSelector('html[data-pixel-status="pass"]');
    await page.waitForFunction(() => window.__recoveryArt.deref() !== window.__previousRecoveryArt
      && document.getElementById('status').textContent.includes('1 个图层'));
    const recovered = await page.evaluate(() => {
      const art = window.__recoveryArt.deref(), original = window.__recoveryOriginal;
      const data = window.__recoveryNativeRead.call(art.getContext('2d'), 0, 0, art.width, art.height).data;
      let count = 0, error = 0, rows = 0, rowDifference = 0;
      for (let y = 0; y < art.height - 17; y += 3) for (let x = 0; x < art.width; x += 3) {
        const i = (y * art.width + x) * 4, j = ((y + 17) * art.width + x) * 4;
        if (original.data[i + 3] !== 255 || data[i + 3] !== 255) continue;
        const gray = original.data[i] * 0.299 + original.data[i + 1] * 0.587 + original.data[i + 2] * 0.114;
        if (gray > 250) continue;
        count++; error += Math.abs(gray - data[i]);
        if (data[j + 3] === 255) { rows++; rowDifference += Math.abs(data[i] - data[j]); }
      }
      return { meanError: error / count, rowDifference: rowDifference / rows };
    });
    assert(recovered.meanError < 1.5, `recovery must rerender correct neutral grayscale: ${recovered.meanError}`);
    assert(recovered.rowDifference > 5, 'recovered preview preserves vertical image variation');
    assert.equal(await page.locator('#export-open').isDisabled(), false);
    assert.equal(await page.locator('#export-confirm').isDisabled(), false);
    await page.screenshot({ path: join(directory, 'recovered-grayscale.png'), fullPage: true });

    await page.locator('#export-open').click();
    await page.waitForFunction(() => document.getElementById('export-dialog').open);
    await page.evaluate(() => window.__recoverySetFault(true));
    // The button is still enabled from the last successful check. Only the
    // internal pre-export check can detect this late permission/environment change.
    assert.equal(await page.locator('#export-confirm').isDisabled(), false);
    await page.locator('#export-confirm').click();
    await page.waitForSelector('html[data-pixel-status="fail"]');
    await page.waitForFunction(() => document.getElementById('export-message').textContent.includes('画布像素读取'));
    assert.equal(await page.locator('#export-confirm').isDisabled(), true);
    assert.equal(exportRequests.length, 0, 'no export POST escapes either the startup or pre-export guard');
    assert.equal(server.exitCode, null, 'failed export leaves the local service available');
    const savedFiles = await readdir(exports).catch(error => { if (error.code === 'ENOENT') return []; throw error; });
    assert.deepEqual(savedFiles, [], 'failed integrity checks create no export folder or partial files');
    await page.locator('#export-close').click();
    await page.waitForFunction(() => !document.getElementById('export-dialog').open);
    assert.equal(await page.locator('#save-project').isEnabled(), true);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ directory, visibleOriginal, recovered, exportPosts: exportRequests.length,
      preservedAssetBytes: sourceBytes.length }, null, 2));
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null) server.kill('SIGINT');
  }
});
