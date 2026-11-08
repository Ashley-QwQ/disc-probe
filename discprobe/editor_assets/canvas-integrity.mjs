/** Small, local Canvas capability check. Never reads a user image or changes
 * browser permissions. A failure blocks image processing/export, not project
 * saving. Passing is a canary, not proof that every image/size will work.
 *
 * PNG round-trip also uses getImageData: its failure does NOT independently
 * identify a PNG encoder fault when readback is already failing.
 */
const WIDTH = 19, HEIGHT = 13;
const NAMES = ['readback', 'drawImage', 'pngRoundTrip'];

function pattern() {
  const data = new Uint8ClampedArray(WIDTH * HEIGHT * 4);
  for (let y = 0; y < HEIGHT; y++) for (let x = 0; x < WIDTH; x++) {
    const i = (y * WIDTH + x) * 4;
    data[i] = (31 + 17 * x + 29 * y) & 255;
    data[i + 1] = (71 + 37 * x + 11 * y) & 255;
    data[i + 2] = (109 + 7 * x + 53 * y) & 255;
    data[i + 3] = 255;
  }
  return data;
}

function compare(expected, image) {
  if (image.width !== WIDTH || image.height !== HEIGHT
      || image.data.length !== expected.length) throw new Error('Unexpected Canvas pixel dimensions');
  let changed = 0, maxDelta = 0;
  for (let i = 0; i < expected.length; i += 4) {
    let different = false;
    for (let channel = 0; channel < 4; channel++) {
      const delta = Math.abs(image.data[i + channel] - expected[i + channel]);
      if (!Number.isFinite(delta)) throw new Error('Non-finite Canvas pixel data');
      maxDelta = Math.max(maxDelta, delta);
      // RGB allows one quantization step; this synthetic source is fully opaque.
      if (delta > (channel === 3 ? 0 : 1)) different = true;
    }
    if (different) changed++;
  }
  return { ok: changed === 0, changed, maxDelta };
}

async function decodePNG(url) {
  if (!url.startsWith('data:image/png;base64,') || url.length > 128 * 1024) {
    throw new Error('Canvas did not return a small PNG');
  }
  const image = new Image();
  let timer;
  try {
    await new Promise((resolve, reject) => {
      timer = setTimeout(() => {
        image.onload = image.onerror = null;
        reject(new Error('PNG decode timed out'));
      }, 3000);
      image.onload = () => { clearTimeout(timer); resolve(); };
      image.onerror = () => { clearTimeout(timer); reject(new Error('PNG decode failed')); };
      image.src = url;
    });
    if (image.naturalWidth !== WIDTH || image.naturalHeight !== HEIGHT) {
      throw new Error('Unexpected decoded PNG dimensions');
    }
    return image;
  } catch (error) { image.src = ''; throw error; }
  finally { clearTimeout(timer); image.onload = image.onerror = null; }
}

/** changed counts pixels outside tolerance; null means no measurement was
 * possible. Errors name the observed stage, never a presumed extension/cause.
 */
export async function checkCanvasIntegrity() {
  const expected = pattern(), checks = [], canvases = [];
  const make = () => {
    const canvas = document.createElement('canvas');
    canvas.width = WIDTH; canvas.height = HEIGHT; canvases.push(canvas);
    const ctx = canvas.getContext('2d', { colorSpace: 'srgb', willReadFrequently: true });
    if (!ctx) throw new Error('Canvas 2D is unavailable');
    ctx.imageSmoothingEnabled = false;
    return { canvas, ctx };
  };
  const record = async (name, operation) => {
    try { checks.push({ name, ...compare(expected, await operation()) }); }
    catch (error) {
      checks.push({ name, ok: false, changed: null, maxDelta: null,
        error: `${name}: ${error?.name || 'Error'}: ${String(error?.message || error).slice(0, 200)}` });
    }
    return !checks.at(-1).error;
  };
  let source, image;
  try {
    const readable = await record('readback', () => {
      source = make();
      const data = source.ctx.createImageData(WIDTH, HEIGHT);
      data.data.set(expected); source.ctx.putImageData(data, 0, 0);
      return source.ctx.getImageData(0, 0, WIDTH, HEIGHT);
    });
    if (readable) {
      const drawable = await record('drawImage', () => {
        const target = make(); target.ctx.drawImage(source.canvas, 0, 0);
        return target.ctx.getImageData(0, 0, WIDTH, HEIGHT);
      });
      if (drawable) await record('pngRoundTrip', async () => {
        image = await decodePNG(source.canvas.toDataURL('image/png'));
        const target = make(); target.ctx.drawImage(image, 0, 0);
        return target.ctx.getImageData(0, 0, WIDTH, HEIGHT);
      });
    }
    // Do not try alternate APIs after a read/write/security exception. In
    // particular, no OffscreenCanvas, iframe, or server-processing workaround.
    for (const name of NAMES.slice(checks.length)) {
      checks.push({ name, ok: false, changed: null, maxDelta: null,
        error: `${name}: skipped after the previous Canvas API error` });
    }
  } finally {
    if (image) image.src = '';
    for (const canvas of canvases) canvas.width = canvas.height = 1;
  }
  return { ok: checks.every(check => check.ok), checks, checkedAt: new Date().toISOString() };
}
