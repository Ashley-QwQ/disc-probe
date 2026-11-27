import { render } from './model.mjs';
import { photoSurface } from './surface.mjs';
let design, width, latest = 0;
let tableError;
const table = fetch(new URL('./textures.bin', import.meta.url)).then(r => {
  if (!r.ok) throw Error('Texture table unavailable');
  return r.arrayBuffer();
}).then(b => { if (b.byteLength !== 18792) throw Error('Invalid texture table'); return new Float64Array(b); })
  .catch(error => { tableError = error; return null; });
// Yield to messages without the nested setTimeout 4 ms floor.
const channel = new MessageChannel();
const turns = [];
channel.port1.onmessage = () => turns.shift()?.();
const yieldTask = () => new Promise(resolve => { turns.push(resolve); channel.port2.postMessage(0); });
self.onmessage = async ({ data: m }) => {
  if (m.type === 'design') {
    latest++; width = m.bitmap.width;
    const surface = new OffscreenCanvas(width, width), g = surface.getContext('2d');
    g.drawImage(m.bitmap, 0, 0); m.bitmap.close();
    const rgba = g.getImageData(0, 0, width, width).data;
    design = new Uint8Array(width * width);
    for (let i = 0; i < design.length; i++) {
      const j = i * 4;
      design[i] = rgba[j + 3] >= 128 && .2126 * rgba[j] + .7152 * rgba[j + 1] + .0722 * rgba[j + 2] < 128 ? 1 : 0;
    }
    self.postMessage({ loaded: true }); return;
  }
  if (m.type === 'cancel') { latest++; return; }
  const token = ++latest;
  try {
    const lut = await table;
    if (!lut) throw tableError;
    if (token !== latest || !design) return;
    const start = performance.now();
    let pixels = await render(design, width, lut, m.pose, m.size, m.fine,
      () => token !== latest, yieldTask);
    const modelMs = performance.now() - start;
    if (pixels && m.pose.photoLook) pixels = await photoSurface(pixels, m.size, m.pose, () => token !== latest, yieldTask, { design, width });
    if (pixels && token === latest) self.postMessage({ id: m.id, size: m.size, fine: m.fine,
      ms: performance.now() - start, modelMs, buffer: pixels.buffer }, [pixels.buffer]);
  } catch (error) { self.postMessage({ id: m.id, error: error.message }); }
};
