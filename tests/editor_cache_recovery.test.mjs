/** Optional browser race regression; runtime users need no Node packages.
 * Run with Playwright installed: node --test tests/editor_cache_recovery.test.mjs
 *
 * The test injects the documented Gecko-style 32-byte Canvas placeholder into
 * Chromium, then delays delivery of one worker response. It does not claim to
 * run Firefox or reproduce the user's actual browser configuration. No drive,
 * ISO writer, production debug hooks, or external image services are used.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

test('late failed-generation worker results cannot repopulate the recovered layer cache',
  { timeout: 90_000 }, async () => {
    const directory = await mkdtemp(join(tmpdir(), 'discprobe-editor-cache-recovery-'));
    const server = spawn(process.env.PYTHON || 'python', ['-m', 'discprobe', 'editor',
      '--no-browser', '--output-dir', join(directory, 'exports')], { cwd: root });
    let stdout = '', stderr = '';
    server.stdout.on('data', data => { stdout += data; });
    server.stderr.on('data', data => { stderr += data; });
    let browser;
    try {
      const deadline = Date.now() + 15_000;
      while (!/http:\/\/127\.0\.0\.1:\d+\/#\S+/.test(stdout)) {
        if (server.exitCode !== null || Date.now() > deadline) {
          // Do not print stdout: it contains the local session capability URL.
          throw new Error('Local editor did not start: ' + stderr);
        }
        await new Promise(resolve => setTimeout(resolve, 25));
      }
      const url = stdout.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/)[0];
      browser = await chromium.launch({ headless: true,
        ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
          ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
      });
      const page = await browser.newPage({ viewport: { width: 1480, height: 1050 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        window.__testBlockPixels = false;
        window.__testHoldResult = false;
        window.__testHeldResults = [];
        window.__testLayerJobs = 0;

        // Hold delivery to the application's handler, not the worker's input.
        // This deterministically models a slow result crossing two cache clears.
        const NativeWorker = window.Worker;
        window.Worker = function (...args) {
          const worker = new NativeWorker(...args), layerIds = new Set();
          let handler;
          Object.defineProperty(worker, 'onmessage', {
            get() { return handler; }, set(callback) { handler = callback; },
          });
          worker.addEventListener('message', event => {
            if (window.__testHoldResult && layerIds.has(event.data.id)) {
              window.__testHeldResults.push(() => handler?.(event));
            } else handler?.(event);
          });
          const post = worker.postMessage.bind(worker);
          worker.postMessage = (message, ...rest) => {
            if (message.operation === 'layer') {
              window.__testLayerJobs++;
              layerIds.add(message.id);
            }
            return post(message, ...rest);
          };
          return worker;
        };
        window.Worker.prototype = NativeWorker.prototype;

        const read = CanvasRenderingContext2D.prototype.getImageData;
        window.__testNativeReadback = canvas => read.call(canvas.getContext('2d'),
          0, 0, canvas.width, canvas.height);
        CanvasRenderingContext2D.prototype.getImageData = function (...args) {
          const image = read.apply(this, args);
          if (window.__testBlockPixels) {
            // Eight repeated RGBA pixels, including altered alpha. A 1040 px
            // layer has identical rows; grayscale conversion produces bars.
            for (let i = 0; i < image.data.length; i++) image.data[i] = (i % 32) * 7 % 256;
          }
          return image;
        };
        const draw = CanvasRenderingContext2D.prototype.drawImage;
        CanvasRenderingContext2D.prototype.drawImage = function (...args) {
          if (this.canvas.id === 'stage' && args[0] instanceof HTMLCanvasElement) {
            window.__testArt = new WeakRef(args[0]);
          }
          return draw.apply(this, args);
        };
      });

      await page.goto(url);
      await page.waitForSelector('html[data-ready="true"][data-pixel-status="pass"]');
      await page.locator('details').evaluateAll(items => { for (const item of items) item.open = true; });
      await page.locator('#image-files').setInputFiles(join(root, 'docs/showcase/roses_source.jpg'));
      await page.waitForFunction(() => document.getElementById('status').textContent.includes('1 个图层'));
      assert.equal(await page.evaluate(() => window.__testLayerJobs), 1);

      // A pixel-read denial appears after the successful initial capability
      // check. Start a new processing job, but do not deliver its result yet.
      await page.evaluate(() => { window.__testBlockPixels = true; window.__testHoldResult = true; });
      await page.locator('#preset').selectOption('portrait');
      await page.waitForFunction(() => window.__testHeldResults.length === 1);
      await page.locator('#rerunDiagnostics').click();
      await page.waitForSelector('html[data-pixel-status="fail"]');

      // Recover access and pass diagnostics BEFORE the obsolete result arrives.
      await page.evaluate(() => { window.__testBlockPixels = false; });
      await page.locator('#rerunDiagnostics').click();
      await page.waitForSelector('html[data-pixel-status="pass"]');
      await page.evaluate(() => {
        window.__testHoldResult = false;
        window.__testHeldResults.splice(0).forEach(deliver => deliver());
      });
      await page.waitForFunction(() => document.getElementById('status').textContent.includes('1 个图层'));
      const result = await page.evaluate(() => {
        const canvas = window.__testArt.deref(), pixels = window.__testNativeReadback(canvas).data;
        let verticalChanges = 0;
        // Entire rectangle lies inside the photograph and writable annulus.
        for (let x = 250; x < 300; x++) {
          const first = pixels[(400 * canvas.width + x) * 4];
          for (let y = 401; y < 800; y++) {
            if (pixels[(y * canvas.width + x) * 4] !== first) verticalChanges++;
          }
        }
        return {
          status: document.documentElement.dataset.pixelStatus,
          mode: document.getElementById('preview-mode').value,
          width: canvas.width, height: canvas.height,
          layerJobs: window.__testLayerJobs, verticalChanges,
        };
      });
      assert.equal(result.status, 'pass');
      assert.equal(result.mode, 'edited');
      assert.equal(result.width, 1200); assert.equal(result.height, 1200);
      assert.equal(result.layerJobs, 3, 'recovery must process fresh pixels instead of using the late stale cache');
      assert(result.verticalChanges > 10_000, 'recovered photograph retains vertical subject structure, not repeated bars');
      assert.deepEqual(errors, []);
    } finally {
      if (browser) await browser.close();
      if (server.exitCode === null) server.kill('SIGINT');
    }
  });
