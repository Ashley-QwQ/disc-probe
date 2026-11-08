/** Optional image-import regression test; runtime users need no Node packages.
 * Run with Playwright installed: node --test tests/editor_imports.test.mjs
 * Sources are repository photographs and generated JPEG/EXIF diagnostics, NOT
 * the user's unavailable source photograph. No drive or ISO writer is invoked.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

test('JPEG and EXIF imports retain two-dimensional content through grayscale edits', { timeout: 180_000 }, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'discprobe-editor-imports-'));
  const geometry = join(directory, 'geometry.json');
  await writeFile(geometry, JSON.stringify({ fit: {
    u: 180045, v: 5.55, bit_nm_assumed: 133.3, media: 'dvd',
    chi2_per_dof: 1, angle_sigma_measured_span_deg: 0.1,
  } }));
  execFileSync(process.env.PYTHON || 'python', ['-c', `
from PIL import Image, ImageDraw
import numpy as np, os, sys
folder = sys.argv[1]
y, x = np.mgrid[:360, :640]
rgb = np.stack((30 + x * 190 / 639, 25 + y * 205 / 359,
                20 + ((x // 55 + y // 40) % 2) * 190), axis=-1).astype(np.uint8)
image = Image.fromarray(rgb, 'RGB')
draw = ImageDraw.Draw(image)
draw.rectangle((45, 30, 110, 300), fill=(15, 15, 15))
draw.rectangle((45, 30, 250, 80), fill=(15, 15, 15))
draw.rectangle((45, 140, 200, 185), fill=(15, 15, 15))
image.save(os.path.join(folder, 'diagnostic-landscape.jpg'), quality=94)
image.convert('L').save(os.path.join(folder, 'diagnostic-grayscale.jpg'), quality=94)
image.convert('CMYK').save(os.path.join(folder, 'diagnostic-cmyk.jpg'), quality=94)
exif = Image.Exif(); exif[274] = 6
image.save(os.path.join(folder, 'diagnostic-exif-6.jpg'), quality=94, exif=exif)
`, directory], { cwd: root });

  const server = spawn(process.env.PYTHON || 'python', ['-m', 'discprobe', 'editor', '--no-browser',
    '--geo', geometry, '--output-dir', join(directory, 'exports')], { cwd: root });
  let stdout = '', stderr = '';
  server.stdout.on('data', data => { stdout += data; });
  server.stderr.on('data', data => { stderr += data; });
  let browser;
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
    for (const [name, path, dimensions] of [
      ['repo-photo-landscape', join(root, 'docs/showcase/figures_tuned_7312.jpg'), [1000, 960]],
      ['repo-photo-portrait', join(root, 'docs/showcase/qingming_title.jpg'), [1270, 1600]],
      ['diagnostic-landscape', join(directory, 'diagnostic-landscape.jpg'), [640, 360]],
      ['diagnostic-exif-6', join(directory, 'diagnostic-exif-6.jpg'), [360, 640]],
      ['diagnostic-grayscale', join(directory, 'diagnostic-grayscale.jpg'), [640, 360]],
      ['diagnostic-cmyk', join(directory, 'diagnostic-cmyk.jpg'), [640, 360]],
    ]) {
      await t.test(name, async () => {
        const page = await browser.newPage({ viewport: { width: 1480, height: 1050 } });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('dialog', dialog => dialog.accept());
        await page.addInitScript(() => {
          const draw = CanvasRenderingContext2D.prototype.drawImage;
          CanvasRenderingContext2D.prototype.drawImage = function (...args) {
            if (this.canvas.id === 'stage' && args[0] instanceof HTMLCanvasElement) {
              window.__importArt = new WeakRef(args[0]);
            }
            return draw.apply(this, args);
          };
          // Record input dimensions and worker output descriptors without keeping
          // any detached/transferred buffers alive or changing transfer semantics.
          window.__importJobs = [];
          const post = Worker.prototype.postMessage;
          Worker.prototype.postMessage = function (message, ...rest) {
            if (message.operation === 'layer') {
              window.__importJobs.push({
                id: message.id, width: message.image.width, height: message.image.height,
                inputLength: message.image.data.length,
                inputType: message.image.data.constructor.name,
              });
              window.__lastLayerInput = { ...message, image: {
                ...message.image, data: message.image.data.slice(),
              } };
              const result = ({ data }) => {
                if (data.id !== message.id) return;
                window.__lastLayerOutput = data.result;
                this.removeEventListener('message', result);
              };
              this.addEventListener('message', result);
            }
            return post.call(this, message, ...rest);
          };
        });
        try {
          await page.goto(url);
          await page.waitForSelector('html[data-ready="true"]');
          await page.locator('#image-files').setInputFiles(path);
          await page.waitForFunction(() => document.querySelectorAll('#layer-list li').length === 1
            && document.getElementById('status').textContent.includes('1 个图层'));

          const changeView = async (id, value) => {
            await page.evaluate(() => { window.__previousArt = window.__importArt?.deref(); });
            await page.locator(id).selectOption(value);
            await page.waitForFunction(() => window.__importArt?.deref()
              && window.__importArt.deref() !== window.__previousArt
              && document.getElementById('status').textContent.includes('1 个图层'));
          };
          await changeView('#preview-mode', 'original');
          const original = await page.evaluate(() => {
            const c = window.__importArt.deref();
            window.__originalPixels = c.getContext('2d').getImageData(0, 0, c.width, c.height);
            return { width: c.width, height: c.height };
          });
          assert.deepEqual(original, { width: 1200, height: 1200 });

          const compare = () => page.evaluate(() => {
            const c = window.__importArt.deref(), ref = window.__originalPixels;
            const got = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            const before = ref.data, width = c.width, height = c.height;
            let count = 0, error = 0, sumX = 0, sumY = 0, sumXX = 0, sumYY = 0, sumXY = 0;
            let pairs = 0, referenceRows = 0, editedRows = 0;
            const gray = (data, i) => data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
            for (let y = 1; y < height - 18; y += 3) for (let x = 1; x < width - 1; x += 3) {
              const i = (y * width + x) * 4, j = ((y + 17) * width + x) * 4;
              if (before[i + 3] !== 255 || got[i + 3] !== 255) continue;
              const a = gray(before, i), b = gray(got, i);
              // Exclude the white backing, which would falsely inflate content
              // correlation when a narrow photograph is centered on the disc.
              if (a > 250) continue;
              count++; error += Math.abs(a - b);
              sumX += a; sumY += b; sumXX += a * a; sumYY += b * b; sumXY += a * b;
              if (before[j + 3] === 255 && got[j + 3] === 255 && gray(before, j) < 250) {
                pairs++; referenceRows += Math.abs(a - gray(before, j));
                editedRows += Math.abs(b - gray(got, j));
              }
            }
            return { count, meanError: error / count,
              correlation: (count * sumXY - sumX * sumY)
                / Math.sqrt((count * sumXX - sumX ** 2) * (count * sumYY - sumY ** 2)),
              referenceRowDifference: referenceRows / pairs, editedRowDifference: editedRows / pairs,
              jobs: window.__importJobs,
            };
          });

          await changeView('#preview-mode', 'edited');
          const neutral = await compare();
          await changeView('#preset', 'portrait');
          const portrait = await compare();
          const workerComparison = await page.evaluate(async () => {
            const { processRGBA } = await import('/processing.mjs');
            const input = window.__lastLayerInput, output = window.__lastLayerOutput;
            const direct = processRGBA(input.image, input.adjustments, { previewScale: input.previewScale });
            let mismatches = 0;
            for (let i = 0; i < direct.data.length; i++) if (direct.data[i] !== output.data[i]) mismatches++;
            return { mismatches, inputLength: input.image.data.length,
              outputLength: output.data.length, width: output.width, height: output.height };
          });
          assert.equal(workerComparison.mismatches, 0, 'worker transfer preserves the direct engine result byte-for-byte');
          assert.equal(workerComparison.outputLength, workerComparison.inputLength);
          await page.evaluate(() => { window.__previousArt = window.__importArt.deref(); });
          await page.locator('#auto-enhance').click();
          await page.waitForFunction(() => window.__importArt.deref() !== window.__previousArt
            && document.getElementById('status').textContent.includes('1 个图层'));
          const enhanced = await compare();
          await page.screenshot({ path: join(directory, `${name}-portrait.png`) });
          const job = neutral.jobs.at(-1);
          assert(job && job.inputType === 'Uint8ClampedArray');
          assert.equal(job.inputLength, job.width * job.height * 4, 'worker receives correctly sized RGBA');
          assert(Math.abs(job.width / job.height - dimensions[0] / dimensions[1]) < 0.003,
            'EXIF orientation and nonsquare proportions survive import');
          console.log(JSON.stringify({ name, neutral: { ...neutral, jobs: neutral.jobs.length },
            portrait: { ...portrait, jobs: portrait.jobs.length },
            enhanced: { ...enhanced, jobs: enhanced.jobs.length }, workerComparison,
            screenshot: join(directory, `${name}-portrait.png`) }));
          assert(neutral.meanError < 1.5, `neutral grayscale must match independent RGB reference: ${neutral.meanError}`);
          assert(neutral.correlation > 0.995, `neutral spatial content changed: correlation ${neutral.correlation}`);
          assert(portrait.correlation > 0.9, `portrait lost image structure: correlation ${portrait.correlation}`);
          assert(portrait.editedRowDifference > portrait.referenceRowDifference * 0.3,
            'portrait must not collapse different image rows into repeated vertical bars');
          assert(enhanced.correlation > 0.85, `auto-enhance lost image structure: correlation ${enhanced.correlation}`);
          assert(enhanced.editedRowDifference > enhanced.referenceRowDifference * 0.3,
            'auto-enhance must not collapse different image rows into repeated vertical bars');
          assert.deepEqual(errors, []);
        } finally { await page.close({ runBeforeUnload: false }); }
      });
    }
    console.log('Import regression artifacts: ' + directory);
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null) server.kill('SIGINT');
  }
});
