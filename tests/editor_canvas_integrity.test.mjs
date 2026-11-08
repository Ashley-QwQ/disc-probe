/** Optional real-browser canary tests. Requires Playwright + Chromium.
 * node --test tests/editor_canvas_integrity.test.mjs
 * Injection simulates corrupt/denied APIs; it does not reproduce the user's
 * reported environment or identify any real browser extension.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const source = await readFile(new URL('../discprobe/editor_assets/canvas-integrity.mjs', import.meta.url), 'utf8');

test('Canvas integrity checks detect altered pixels and respect denied access', { timeout: 30_000 }, async t => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
  });
  try {
    for (const mode of ['normal', 'rgb-rounding', 'stripes', 'rgba-placeholder', 'readback-security', 'png-corrupt', 'png-security']) {
      await t.test(mode, async () => {
        const page = await browser.newPage();
        try {
          const result = await page.evaluate(async ({ source, mode }) => {
            const context = CanvasRenderingContext2D.prototype;
            const get = context.getImageData;
            let reads = 0, encodes = 0;
            context.getImageData = function (...args) {
              reads++;
              if (mode === 'readback-security') throw new DOMException('Readback denied by test', 'SecurityError');
              const image = get.apply(this, args);
              if (mode === 'stripes') {
                const row = image.data.slice(0, image.width * 4);
                for (let y = 1; y < image.height; y++) image.data.set(row, y * image.width * 4);
              } else if (mode === 'rgba-placeholder') {
                // A repeating 32-byte placeholder includes altered alpha; it
                // need not preserve the image or repeat identically per call.
                const bytes = Uint8Array.from({ length: 32 }, (_, i) => (i * 31 + reads * 17) & 255);
                for (let i = 0; i < image.data.length; i++) image.data[i] = bytes[i % 32];
              } else if (mode === 'rgb-rounding') {
                for (let i = 0; i < image.data.length; i++) if (i % 4 !== 3) image.data[i]++;
              }
              return image;
            };
            const encode = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function (...args) {
              encodes++;
              if (mode === 'png-security') throw new DOMException('Export denied by test', 'SecurityError');
              if (mode === 'png-corrupt') {
                const c = document.createElement('canvas'); c.width = this.width; c.height = this.height;
                c.getContext('2d').fillRect(0, 0, c.width, c.height);
                return encode.apply(c, args);
              }
              return encode.apply(this, args);
            };
            const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
            try {
              const { checkCanvasIntegrity } = await import(url);
              return { ...(await checkCanvasIntegrity()), reads, encodes };
            } finally { URL.revokeObjectURL(url); }
          }, { source, mode });
          assert.equal(result.checks.length, 3);
          assert.deepEqual(result.checks.map(c => c.name), ['readback', 'drawImage', 'pngRoundTrip']);
          assert(Number.isFinite(Date.parse(result.checkedAt)));
          if (mode === 'normal' || mode === 'rgb-rounding') {
            assert.equal(result.ok, true, JSON.stringify(result));
            assert(result.checks.every(c => c.changed === 0 && c.maxDelta <= 1));
          } else if (mode === 'stripes' || mode === 'rgba-placeholder') {
            assert.equal(result.ok, false);
            assert(result.checks.every(c => !c.ok && c.changed > 0 && c.maxDelta > 1));
          } else if (mode === 'readback-security') {
            assert.equal(result.ok, false);
            assert.match(result.checks[0].error, /readback: SecurityError/);
            assert.equal(result.checks[0].changed, null);
            assert.equal(result.reads, 1, 'permission failure is not retried through alternate paths');
            assert.equal(result.encodes, 0, 'no export API is attempted after readback denial');
            assert(result.checks.slice(1).every(c => /skipped/.test(c.error)));
          } else {
            assert.equal(result.ok, false);
            assert(result.checks.slice(0, 2).every(c => c.ok));
            assert.equal(result.checks[2].ok, false);
            if (mode === 'png-security') assert.match(result.checks[2].error, /pngRoundTrip: SecurityError/);
            else assert(result.checks[2].changed > 0);
          }
        } finally { await page.close(); }
      });
    }
  } finally { await browser.close(); }
});
