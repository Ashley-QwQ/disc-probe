import {
  DEFAULT_ADJUSTMENTS, DEFAULT_OUTPUT, normalizeAdjustments, normalizeOutput,
  processRGBA, applyChromaKey, renderOutput, physicalPreview, autoLevels, histogram,
} from './processing.mjs';
import { checkCanvasIntegrity } from './canvas-integrity.mjs';

// The server only saves exports. Original pictures, undo history, and all image
// operations live in this browser session; there are no third-party requests.
const $ = id => document.getElementById(id);
const clone = value => structuredClone(value);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
// Canvas overlays share the CSS theme. Artwork pixels never use UI colours.
const themeColor = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
// A display-only comparison: repeated normalization can change an RGB weight
// by one floating-point ulp. It must not turn a saved preset into "custom".
const settingsKey = value => JSON.stringify(value, (_, v) =>
  typeof v === 'number' ? Number(v.toFixed(9)) : v);
const GRID = 6000, DIAMETER = 120, MAX_LAYERS = 16, MAX_SOURCE_PIXELS = 36_000_000;
const MAX_TOTAL_SOURCE_PIXELS = 48_000_000, MAX_CACHE_PIXELS = 12_000_000;
const MAX_SOURCE_BYTES = 24 * 1024 * 1024, MAX_PROJECT_BYTES = 100 * 1024 * 1024;
const PRESETS = {
  neutral: {}, portrait: { shadows: 12, highlights: -12, clarity: 8, denoise: 10 },
  landscape: { contrast: 14, clarity: 18, texture: 10, sharpen: 15 },
  illustration: { contrast: 8, denoise: 5, sharpen: 12 },
  lineart: { contrast: 45, blackPoint: 25, whitePoint: 230, sharpen: 15 },
  soft: { contrast: -10, highlightCompression: 10, shadowCompression: 10 },
};
const token = location.hash.slice(1);
const EDITOR_BUILD = '2026.11.08.2';
let config, state, dirty = false, sessionEnded = false, exporting = false, pendingEdits = 0;
let assets = new Map(), layerCache = new Map();
let cacheEpoch = 0;
let past = [], future = [], lastEdit = '', lastEditTime = 0;
let camera = { zoom: 1, x: 0, y: 0 }, tool = 'select', spaceHeld = false;
let drag = null, keyDraft = null, keyPicking = false;
let revision = 0, rendering = false, renderWanted = false, previewCanvas = null;
let exportResult = null, nextJob = 1, worker = null;
let integrity = null, integrityJob = null;
const jobs = new Map(), controlInputs = new Map();

function report(text, error = false) {
  $('status').textContent = text;
  $('status').dataset.error = String(error);
}
function fail(error) {
  console.error(error);
  report(error.message || String(error), true);
}
function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function finite(value, lo, hi, label) {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n) || n < lo || n > hi) throw new Error(`${label}: ${lo}–${hi}`);
  return n;
}
function selected() { return state?.layers.find(layer => layer.id === state.selectedId); }
function uid() { return crypto.randomUUID(); }
function selectedRequired() {
  const layer = selected();
  if (!layer) throw new Error('请先导入并选择一个图层。');
  if (layer.locked) throw new Error('这个图层已锁定，请先解锁。');
  return layer;
}

function updateDiagnostics() {
  const status = integrity ? integrity.ok ? 'PASS' : 'FAIL' : 'CHECKING';
  document.documentElement.dataset.pixelStatus = status.toLowerCase();
  const lines = [
    `disc-probe editor ${EDITOR_BUILD}`, `Browser: ${navigator.userAgent}`,
    `Canvas integrity: ${status}`, `Worker: ${worker ? 'active' : 'main-thread fallback'}`,
    ...((integrity?.checks || []).map(item => `${item.name}: ${item.ok ? 'PASS' : 'FAIL'}; changed=${item.changed}; maxDelta=${item.maxDelta}${item.error ? '; ' + item.error : ''}`)),
    'No image contents, filenames, paths, or session token are included.',
  ];
  if ($('diagnosticText')) $('diagnosticText').value = lines.join('\n');
  if ($('integrityNotice')) {
    $('integrityNotice').hidden = !integrity || integrity.ok;
    $('integrityNotice').textContent = '画布像素读取异常，已暂停调色和导出。下方仅显示未处理的原图。浏览器的 Canvas 权限、防指纹设置或扩展可能改写像素；请检查当前本地站点的权限，再到「诊断信息」点「重新检测」。原图未被修改，仍可保存工程；无需关闭全局隐私保护。';
  }
  if ($('rerunDiagnostics')) $('rerunDiagnostics').disabled = !!integrityJob || exporting;
}
async function verifyPixels() {
  if (integrityJob) return integrityJob;
  integrityJob = (async () => {
    const previous = integrity?.ok;
    try { integrity = await checkCanvasIntegrity(); }
    catch (error) { integrity = { ok: false, checks: [{ name: 'check', ok: false,
      changed: null, maxDelta: null, error: String(error.message || error) }] }; }
    if (!integrity.ok) {
      // Keep only direct image drawing available. Never attempt an offscreen or
      // server-side route around a denied Canvas extraction permission.
      $('preview-mode').value = 'original';
      clearLayerCache();
      releaseCanvas(previewCanvas); previewCanvas = null;
      drawHistogram([]);
      requestRender();
    } else if (previous === false) {
      clearLayerCache();
      releaseCanvas(previewCanvas); previewCanvas = null;
      $('preview-mode').value = 'edited';
      requestRender();
    }
    return integrity.ok;
  })();
  updateDiagnostics();
  try { return await integrityJob; }
  finally { integrityJob = null; updateDiagnostics(); if (state) syncUI(); }
}
function requirePixels() {
  if (!integrity?.ok) throw new Error('画布像素读取未通过检查。请在「诊断信息」重新检测；允许当前本地站点读取 Canvas 后再调色或导出。');
}

function remember(key = '') {
  const now = performance.now();
  if (!key || key !== lastEdit || now - lastEditTime > 600) {
    past.push(clone(state));
    if (past.length > 30) past.shift();
  }
  lastEdit = key;
  lastEditTime = now;
  future = [];
  dirty = true;
}
function change(callback, key = '', update = true) {
  if (exporting) throw new Error('正在导出，请等待完成后再修改画布。');
  remember(key);
  callback();
  if (update) syncUI();
  requestRender();
}
function historyStep(redo) {
  const from = redo ? future : past, to = redo ? past : future;
  if (!from.length || exporting) return;
  to.push(clone(state));
  state = from.pop();
  keyDraft = null;
  lastEdit = '';
  dirty = true;
  syncUI();
  requestRender();
}

function stopWorker(message, restart = false) {
  worker?.terminate();
  worker = null;
  for (const job of jobs.values()) {
    clearTimeout(job.timer);
    job.reject(new Error(message));
  }
  jobs.clear();
  if (restart) setupWorker();
}
function setupWorker() {
  try {
    worker = new Worker('/worker.js', { type: 'module' });
    worker.onmessage = ({ data }) => {
      const job = jobs.get(data.id);
      if (!job) return;
      clearTimeout(job.timer);
      jobs.delete(data.id);
      data.error ? job.reject(new Error(data.error)) : job.resolve(data.result);
    };
    worker.onerror = () => stopWorker('图像工作线程出错，请重新打开编辑器；原图文件没有被修改。');
  } catch { worker = null; }
}
async function work(operation, image, options = {}) {
  if (!worker) {
    await new Promise(resolve => requestAnimationFrame(resolve));
    if (operation === 'layer') {
      return processRGBA(options.key ? applyChromaKey(image, options.key) : image,
        options.adjustments, { previewScale: options.previewScale });
    }
    return operation === 'soft' ? physicalPreview(image, options.options)
      : renderOutput(image, options.options);
  }
  const id = nextJob++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      // Discard the stalled job rather than leaving all retries queued behind it.
      stopWorker('这次图像处理用时过长，已重启工作线程。请降低预览分辨率或减少图层后重试。', true);
    }, 180_000);
    jobs.set(id, { resolve, reject, timer });
    try { worker.postMessage({ id, operation, image, ...options }, [image.data.buffer]); }
    catch (error) { clearTimeout(timer); jobs.delete(id); reject(error); }
  });
}
function canvas(width, height = width) {
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  return c;
}
function imageOf(c) {
  requirePixels();
  const im = c.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, c.width, c.height);
  return { width: im.width, height: im.height, data: im.data };
}
function canvasOf(image) {
  const c = canvas(image.width, image.height);
  c.getContext('2d').putImageData(new ImageData(image.data, image.width, image.height), 0, 0);
  return c;
}
function sampling(ctx) {
  ctx.imageSmoothingEnabled = state.resampling !== 'nearest';
  ctx.imageSmoothingQuality = state.resampling === 'high' ? 'high' : 'low';
}
function keyFor(layer) { return keyDraft && keyDraft.layerId === layer.id ? keyDraft.key : layer.key; }
function releaseCanvas(c) { if (c) c.width = c.height = 1; }
function clearLayerCache() {
  cacheEpoch++;
  for (const entry of layerCache.values()) releaseCanvas(entry.canvas);
  layerCache.clear();
}
function cacheRaster(id, signature, result) {
  const previous = layerCache.get(id);
  if (previous) { releaseCanvas(previous.canvas); layerCache.delete(id); }
  const area = result.width * result.height;
  if (area > MAX_CACHE_PIXELS) return;
  let used = [...layerCache.values()].reduce((n, entry) => n + entry.canvas.width * entry.canvas.height, 0);
  for (const [oldId, entry] of layerCache) {
    if (used + area <= MAX_CACHE_PIXELS) break;
    used -= entry.canvas.width * entry.canvas.height;
    releaseCanvas(entry.canvas); layerCache.delete(oldId);
  }
  layerCache.set(id, { signature, canvas: result });
}
async function layerRaster(layer, size, raw = false, committed = false) {
  const epoch = cacheEpoch;
  const asset = assets.get(layer.assetId);
  if (!asset) throw new Error(`缺少图层原图：${layer.name}`);
  let width = Math.max(1, Math.round(layer.widthMm / DIAMETER * size));
  let height = Math.max(1, Math.round(width * asset.height / asset.width));
  const limit = Math.min(1, GRID / width, GRID / height,
    Math.sqrt(MAX_SOURCE_PIXELS / (width * height)));
  width = Math.max(1, Math.round(width * limit));
  height = Math.max(1, Math.round(height * limit));
  const key = committed ? layer.key : keyFor(layer);
  const signature = JSON.stringify([layer.assetId, width, height, raw,
    raw ? null : layer.adjustments, raw ? null : key, state.resampling]);
  const cacheable = size < GRID && width * height <= MAX_CACHE_PIXELS;
  const cached = cacheable ? layerCache.get(layer.id) : null;
  if (cached?.signature === signature) {
    layerCache.delete(layer.id); layerCache.set(layer.id, cached);
    return cached.canvas;
  }
  const input = canvas(width, height);
  const ctx = input.getContext('2d', { willReadFrequently: true });
  sampling(ctx);
  ctx.drawImage(asset.image, 0, 0, width, height);
  try {
    if (!raw) {
      const image = await work('layer', imageOf(input), {
        adjustments: layer.adjustments, key,
        previewScale: width / (layer.widthMm / DIAMETER * GRID),
      });
      ctx.putImageData(new ImageData(image.data, width, height), 0, 0);
    }
    // A delayed Worker result may have been read before a failed integrity
    // check. Never let it repopulate caches cleared during permission recovery.
    if (cacheable && epoch === cacheEpoch) cacheRaster(layer.id, signature, input);
    return input;
  } catch (error) { releaseCanvas(input); throw error; }
}
function ringPath(ctx, size) {
  const center = size / 2, scale = size / DIAMETER;
  ctx.beginPath();
  ctx.arc(center, center, state.disc.outerRadiusMm * scale, 0, Math.PI * 2);
  ctx.arc(center, center, state.disc.innerRadiusMm * scale, 0, Math.PI * 2, true);
}
async function compose(size, { raw = false, committed = false, transparent = false, checkRevision = null } = {}) {
  if (size === GRID) clearLayerCache();
  const c = canvas(size), ctx = c.getContext('2d', { willReadFrequently: true });
  if (!transparent) {
    ctx.fillStyle = state.disc.background;
    ctx.fillRect(0, 0, size, size);
  }
  for (const layer of state.layers) {
    if (!layer.visible || layer.opacity === 0) continue;
    const raster = await layerRaster(layer, size, raw, committed);
    if (checkRevision !== null && checkRevision !== revision) {
      if (layerCache.get(layer.id)?.canvas !== raster) releaseCanvas(raster);
      releaseCanvas(c); return null;
    }
    const asset = assets.get(layer.assetId), scale = size / DIAMETER;
    const w = layer.widthMm * scale, h = w * asset.height / asset.width;
    ctx.save();
    ctx.globalAlpha = layer.opacity;
    ctx.globalCompositeOperation = layer.blend;
    sampling(ctx);
    ctx.translate(size / 2 + layer.x * scale, size / 2 - layer.y * scale);
    ctx.rotate(layer.rotation * Math.PI / 180);
    ctx.drawImage(raster, -w / 2, -h / 2, w, h);
    ctx.restore();
    // Full-grid layers are ephemeral; retaining sixteen of them would add GBs.
    if (layerCache.get(layer.id)?.canvas !== raster) releaseCanvas(raster);
  }
  ctx.globalCompositeOperation = 'destination-in';
  ringPath(ctx, size);
  ctx.fill('evenodd');
  ctx.globalCompositeOperation = 'source-over';
  return c;
}
function flatten(source) {
  const c = canvas(source.width, source.height), ctx = c.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.drawImage(source, 0, 0);
  return c;
}
function exactBinaryRing(image) {
  const { width, height, data } = image, px = DIAMETER / width;
  const lo = state.disc.innerRadiusMm ** 2, hi = state.disc.outerRadiusMm ** 2;
  for (let y = 0; y < height; y++) {
    const dy = (y + 0.5) * px - DIAMETER / 2;
    for (let x = 0; x < width; x++) {
      const dx = (x + 0.5) * px - DIAMETER / 2, i = (y * width + x) * 4;
      const inside = dx * dx + dy * dy >= lo && dx * dx + dy * dy <= hi;
      const v = inside && data[i] < 128 ? 0 : 255;
      data[i] = data[i + 1] = data[i + 2] = v;
      data[i + 3] = 255;
    }
  }
  return image;
}
async function binaryOutput(source, output) {
  // Error diffusion must see the same opaque white exterior in preview and
  // export; feeding it transparent pixels changes dots inside the annulus too.
  const opaque = flatten(source), pixels = imageOf(opaque);
  releaseCanvas(opaque);
  return exactBinaryRing(await work('output', pixels, { options: output }));
}

function requestRender() {
  revision++;
  renderWanted = true;
  if (!rendering && !exporting) requestAnimationFrame(render);
}
async function render() {
  if (rendering || exporting || !state) return;
  rendering = true;
  try {
    while (renderWanted && !exporting) {
      renderWanted = false;
      const version = revision, size = Number($('preview-size').value);
      const mode = integrity?.ok ? $('preview-mode').value : 'original';
      if (state.layers.length) report(`正在生成 ${size} px 预览…`);
      const composite = await compose(size, {
        raw: mode === 'original', transparent: !!keyDraft && mode === 'edited', checkRevision: version,
      });
      if (!composite || version !== revision) continue;
      let pixels = integrity?.ok ? imageOf(composite) : null;
      drawHistogram(pixels ? histogram(pixels) : []);
      let result = composite;
      if (mode === 'output' || mode === 'soft') {
        pixels = null;
        let out = await binaryOutput(composite, {
          ...state.output, cellSize: Math.max(1, Math.round(state.output.cellSize * size / GRID)),
        });
        releaseCanvas(composite);
        if (version !== revision) continue;
        if (mode === 'soft') out = await work('soft', out, {
          options: { radiusPixels: Math.max(1, 2 * state.output.cellSize * size / GRID), previewScale: 1 },
        });
        result = canvasOf(out);
        const ctx = result.getContext('2d');
        ctx.globalCompositeOperation = 'destination-in';
        ringPath(ctx, size); ctx.fill('evenodd');
        ctx.globalCompositeOperation = 'source-over';
      } else if ($('clipping-warning').checked && mode !== 'original') {
        for (let i = 0; i < pixels.data.length; i += 4) {
          if (!pixels.data[i + 3]) continue;
          if (pixels.data[i] <= 1) {
            pixels.data[i] = 40; pixels.data[i + 1] = 118; pixels.data[i + 2] = 255;
          } else if (pixels.data[i] >= 254) {
            pixels.data[i] = 255; pixels.data[i + 1] = 77; pixels.data[i + 2] = 66;
          }
        }
        result = canvasOf(pixels);
      }
      if (version !== revision) continue;
      releaseCanvas(previewCanvas);
      previewCanvas = result;
      drawStage();
      updateWarnings();
      const suffix = keyDraft ? '去背预览尚未应用' : mode === 'soft' ? '视觉平均示意，不是实物预测'
        : size === GRID ? '原生网格预览' : '快速预览；导出将以 6000 px 重新计算';
      report(!integrity?.ok ? '像素读取检查未通过：仅显示原图，请打开「诊断信息」。'
        : state.layers.length ? `${state.layers.length} 个图层 · ${size} px · ${suffix}` : '从「添加图片」开始，也可以把图片拖到画布。');
    }
  } catch (error) { fail(error); }
  finally {
    rendering = false;
    if (renderWanted && !exporting) requestAnimationFrame(render);
  }
}

function viewportGeometry() {
  const rect = $('viewport').getBoundingClientRect();
  const base = Math.max(1, Math.min(rect.width - 72, rect.height - 72)) / DIAMETER;
  return { width: rect.width, height: rect.height, scale: base * camera.zoom,
    cx: rect.width / 2 + camera.x, cy: rect.height / 2 + camera.y };
}
function screenPoint(event) {
  const rect = $('stage').getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}
function worldPoint(point) {
  const g = viewportGeometry();
  return { x: (point.x - g.cx) / g.scale, y: -(point.y - g.cy) / g.scale };
}
function layerLocal(layer, world) {
  const a = layer.rotation * Math.PI / 180;
  const dx = world.x - layer.x, dy = -(world.y - layer.y);
  return { x: dx * Math.cos(a) + dy * Math.sin(a), y: -dx * Math.sin(a) + dy * Math.cos(a) };
}
function layerHeight(layer) {
  const a = assets.get(layer.assetId);
  return layer.widthMm * a.height / a.width;
}
function drawStage() {
  if (!state) return;
  const c = $('stage'), g = viewportGeometry(), dpr = Math.min(devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(g.width * dpr)), height = Math.max(1, Math.round(g.height * dpr));
  if (c.width !== width || c.height !== height) { c.width = width; c.height = height; }
  const ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, g.width, g.height);
  ctx.save();
  ctx.translate(g.cx, g.cy);
  const radius = DIAMETER / 2 * g.scale;
  ctx.fillStyle = '#dadcda';
  ctx.beginPath(); ctx.arc(0, 0, radius, 0, Math.PI * 2); ctx.fill();
  ctx.save();
  ctx.beginPath();
  ctx.arc(0, 0, state.disc.outerRadiusMm * g.scale, 0, Math.PI * 2);
  ctx.arc(0, 0, state.disc.innerRadiusMm * g.scale, 0, Math.PI * 2, true);
  ctx.clip('evenodd');
  ctx.fillStyle = '#fff'; ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
  if (keyDraft && $('preview-mode').value === 'edited') {
    ctx.fillStyle = '#e5e7e9';
    const step = 12;
    for (let y = -radius; y < radius; y += step) for (let x = -radius; x < radius; x += step) {
      if ((Math.floor((x + radius) / step) + Math.floor((y + radius) / step)) % 2 === 0) ctx.fillRect(x, y, step, step);
    }
  }
  if (previewCanvas) {
    ctx.imageSmoothingEnabled = !['output'].includes($('preview-mode').value);
    ctx.drawImage(previewCanvas, -radius, -radius, radius * 2, radius * 2);
  }
  ctx.restore();
  ctx.strokeStyle = '#9c9f9d'; ctx.lineWidth = 1;
  for (const r of [60, state.disc.outerRadiusMm, state.disc.innerRadiusMm, 7.5]) {
    ctx.beginPath(); ctx.arc(0, 0, r * g.scale, 0, Math.PI * 2); ctx.stroke();
  }
  ctx.fillStyle = '#242825'; ctx.beginPath(); ctx.arc(0, 0, 7.5 * g.scale, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = '#9ea6a0';
  ctx.beginPath(); ctx.moveTo(-4, 0); ctx.lineTo(4, 0); ctx.moveTo(0, -4); ctx.lineTo(0, 4); ctx.stroke();
  ctx.textAlign = 'center';
  const layer = selected();
  if (layer?.visible) {
    const w = layer.widthMm * g.scale, h = layerHeight(layer) * g.scale;
    ctx.save();
    ctx.translate(layer.x * g.scale, -layer.y * g.scale); ctx.rotate(layer.rotation * Math.PI / 180);
    ctx.strokeStyle = layer.locked ? '#8a9893' : themeColor('--accent'); ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]); ctx.strokeRect(-w / 2, -h / 2, w, h); ctx.setLineDash([]);
    if (!layer.locked) {
      ctx.fillStyle = '#fff';
      for (const [x, y] of [[-w / 2, -h / 2], [w / 2, -h / 2], [-w / 2, h / 2], [w / 2, h / 2]]) {
        ctx.fillRect(x - 4, y - 4, 8, 8); ctx.strokeRect(x - 4, y - 4, 8, 8);
      }
    }
    ctx.restore();
  }
  ctx.restore();
  if ($('canvas-empty')) $('canvas-empty').hidden = !!state.layers.length;
  $('zoom-label').textContent = `${Math.round(camera.zoom * 100)}%`;
  c.dataset.tool = keyPicking ? 'eyedropper' : spaceHeld ? 'pan' : tool;
}
function zoom(factor, point) {
  const g = viewportGeometry();
  const anchor = point || { x: g.width / 2, y: g.height / 2 };
  const next = clamp(camera.zoom * factor, 0.25, 24), f = next / camera.zoom;
  camera.x = anchor.x - g.width / 2 - (anchor.x - g.cx) * f;
  camera.y = anchor.y - g.height / 2 - (anchor.y - g.cy) * f;
  camera.zoom = next;
  drawStage();
}
function setTool(value) {
  tool = value; keyPicking = value === 'eyedropper';
  $('tool-select').setAttribute('aria-pressed', String(value === 'select'));
  $('tool-pan').setAttribute('aria-pressed', String(value === 'pan'));
  $('key-pick').setAttribute('aria-pressed', String(keyPicking));
  drawStage();
}
function pickColor(point) {
  requirePixels();
  const layer = selectedRequired(), local = layerLocal(layer, worldPoint(point));
  const w = layer.widthMm, h = layerHeight(layer);
  if (Math.abs(local.x) > w / 2 || Math.abs(local.y) > h / 2) throw new Error('请点击所选图层的背景。');
  const asset = assets.get(layer.assetId), c = canvas(1), ctx = c.getContext('2d', { willReadFrequently: true });
  const x = clamp(Math.floor((local.x / w + 0.5) * asset.width), 0, asset.width - 1);
  const y = clamp(Math.floor((local.y / h + 0.5) * asset.height), 0, asset.height - 1);
  ctx.drawImage(asset.image, x, y, 1, 1, 0, 0, 1, 1);
  const rgba = ctx.getImageData(0, 0, 1, 1).data;
  if (!rgba[3]) throw new Error('该位置已透明，请选一个有颜色的背景像素。');
  $('key-color').value = '#' + [...rgba.slice(0, 3)].map(v => v.toString(16).padStart(2, '0')).join('');
  setTool('select'); previewKey();
}
function pointerDown(event) {
  if (exporting || event.button > 1) return;
  const point = screenPoint(event);
  if (keyPicking) { try { pickColor(point); } catch (error) { fail(error); } return; }
  $('stage').focus({ preventScroll: true });
  if (tool === 'pan' || spaceHeld || event.button === 1) {
    drag = { mode: 'pan', pointer: event.pointerId, point, camera: { ...camera } };
  } else {
    const world = worldPoint(point), current = selected();
    if (current?.visible && !current.locked) {
      const p = layerLocal(current, world), h = layerHeight(current), tolerance = 10 / viewportGeometry().scale;
      if (Math.abs(Math.abs(p.x) - current.widthMm / 2) < tolerance && Math.abs(Math.abs(p.y) - h / 2) < tolerance) {
        remember();
        drag = { mode: 'resize', pointer: event.pointerId, layer: current.id,
          distance: Math.max(0.01, Math.hypot(p.x, p.y)), width: current.widthMm };
      }
    }
    if (!drag) {
      const hit = [...state.layers].reverse().find(layer => {
        if (!layer.visible || layer.locked) return false;
        const p = layerLocal(layer, world);
        return Math.abs(p.x) <= layer.widthMm / 2 && Math.abs(p.y) <= layerHeight(layer) / 2;
      });
      if (hit) {
        state.selectedId = hit.id; keyDraft = null;
        remember();
        drag = { mode: 'move', pointer: event.pointerId, layer: hit.id, world, x: hit.x, y: hit.y };
        syncUI();
      } else { state.selectedId = null; syncUI(); drawStage(); }
    }
  }
  if (drag) $('stage').setPointerCapture(event.pointerId);
  event.preventDefault();
}
function pointerMove(event) {
  if (!drag || drag.pointer !== event.pointerId) return;
  const point = screenPoint(event);
  if (drag.mode === 'pan') {
    camera.x = drag.camera.x + point.x - drag.point.x;
    camera.y = drag.camera.y + point.y - drag.point.y;
    drawStage(); return;
  }
  const layer = state.layers.find(l => l.id === drag.layer), world = worldPoint(point);
  if (!layer) return;
  if (drag.mode === 'resize') {
    const p = layerLocal(layer, world);
    layer.widthMm = clamp(drag.width * Math.hypot(p.x, p.y) / drag.distance, 0.1, 500);
  } else {
    const step = event.shiftKey ? 1 : 0.01;
    layer.x = clamp(Math.round((drag.x + world.x - drag.world.x) / step) * step, -240, 240);
    layer.y = clamp(Math.round((drag.y + world.y - drag.world.y) / step) * step, -240, 240);
  }
  syncTransform(); drawStage(); requestRender();
}
function pointerUp(event) {
  if (drag?.pointer !== event.pointerId) return;
  try { $('stage').releasePointerCapture(event.pointerId); } catch {}
  drag = null; lastEdit = ''; syncUI();
}

function drawHistogram(bins) {
  const c = $('histogram'), ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  const values = Array.isArray(bins) || ArrayBuffer.isView(bins) ? bins : bins.bins || bins.histogram || [];
  const highest = Math.max(1, ...values);
  ctx.fillStyle = '#bfc3c9';
  for (let i = 0; i < 256; i++) {
    const h = Math.sqrt((values[i] || 0) / highest) * (c.height - 6);
    ctx.fillRect(i / 256 * c.width, c.height - h, Math.ceil(c.width / 256), h);
  }
}
function updateWarnings() {
  // The fixed software-grid explanation already appears beside the canvas.
  // Keep the expandable note list for actionable conditions, not repeated copy.
  const warnings = (config.warnings || []).filter(w => !w.startsWith('The image writer uses a 20 micrometre'))
    .map(w => w.startsWith('No measured geometry is selected')
      ? '尚未选择几何测量：可以先设计和导出，生成刻录镜像前再完成 geo 测量。' : w);
  if (Number($('preview-size').value) !== GRID && ['output', 'soft'].includes($('preview-mode').value)) {
    warnings.push('低分辨率网点预览不逐像素对应导出。检查细节时切到「原生网格」。');
  }
  if (state.output.mode === 'threshold') warnings.push('阈值模式不保留连续灰阶；照片通常适合误差扩散或蓝噪声。');
  for (const layer of state.layers) {
    if (!layer.visible) continue;
    const asset = assets.get(layer.assetId);
    const sourceUm = layer.widthMm / asset.width * 1000;
    if (sourceUm > 200) warnings.push(`「${layer.name}」原图像素约 ${sourceUm.toFixed(0)} μm，放大不会补回细节。`);
  }
  $('warnings').replaceChildren(...warnings.map(w => element('li', w)));
  if ($('warning-count')) $('warning-count').textContent = warnings.length ? `${warnings.length} 条提示` : '设计提示';
  const notes = $('warnings').closest('details');
  if (notes) notes.hidden = warnings.length === 0;
}

const TONE = [
  ['exposure', '曝光 · Exposure', -5, 5, 0.05, ' EV'],
  ['brightness', '亮度 · Brightness', -100, 100, 1],
  ['contrast', '对比度 · Contrast', -100, 100, 1],
  ['highlights', '高光 · Highlights', -100, 100, 1],
  ['shadows', '阴影 · Shadows', -100, 100, 1],
  ['blackPoint', '黑点 · Blacks', 0, 254, 1],
  ['whitePoint', '白点 · Whites', 1, 255, 1],
  ['gamma', '中间调 · Gamma', 0.1, 5, 0.05],
  ['highlightCompression', '高光压缩 · Shoulder', 0, 100, 1],
  ['shadowCompression', '阴影压缩 · Toe', 0, 100, 1],
  ['mix0', '红色转灰度 · Red', 0, 1, 0.01],
  ['mix1', '绿色转灰度 · Green', 0, 1, 0.01],
  ['mix2', '蓝色转灰度 · Blue', 0, 1, 0.01],
];
const DETAIL = [
  ['sharpen', '锐化 · Sharpen', 0, 100, 1],
  ['sharpenRadius', '锐化半径 · Radius', 0.1, 32, 0.1, ' px'],
  ['sharpenThreshold', '锐化阈值 · Threshold', 0, 255, 1],
  ['clarity', '局部对比 · Clarity', -100, 100, 1],
  ['texture', '纹理 · Texture', -100, 100, 1],
  ['denoise', '降噪 · Denoise', 0, 100, 1],
  ['grain', '颗粒 · Grain', 0, 100, 1],
  ['seed', '颗粒种子 · Seed', 0, 65535, 1],
];
const OUTPUT = [
  ['levels', '目标灰阶 · Posterize', 2, 256, 1],
  ['strength', '抖动强度 · Strength', 0, 1, 0.05],
  ['threshold', '二值阈值 · Threshold', 0, 1, 0.01],
  ['cellSize', '网点单位 · Grid cells', 1, 64, 1, ' × 20 μm'],
  ['angle', '规则网点方向 · Angle', -180, 180, 1, '°'],
  ['seed', '抖动种子 · Seed', 0, 65535, 1],
];
function getSetting(key, output) {
  if (output) return state.output[key];
  const a = selected()?.adjustments || DEFAULT_ADJUSTMENTS;
  return key.startsWith('mix') ? a.mix[Number(key.at(-1))] : a[key];
}
function setSetting(key, value, output) {
  requirePixels();
  if (output) {
    const candidate = normalizeOutput({ ...state.output, [key]: value });
    change(() => { state.output = candidate; }, `output-${key}`, false);
  } else {
    const layer = selectedRequired(), candidate = clone(layer.adjustments);
    if (key.startsWith('mix')) candidate.mix[Number(key.at(-1))] = value;
    else candidate[key] = value;
    if (key === 'blackPoint') candidate.blackPoint = Math.min(value, candidate.whitePoint - 1);
    if (key === 'whitePoint') candidate.whitePoint = Math.max(value, candidate.blackPoint + 1);
    const valid = normalizeAdjustments(candidate);
    change(() => { layer.adjustments = valid; }, `${layer.id}-${key}`, false);
  }
  syncControls();
}
function addControls(container, definitions, output = false) {
  for (const [key, label, min, max, step, suffix = ''] of definitions) {
    const row = element('div', undefined, 'control adjustment'), line = element('div', undefined, 'control-heading adjustment-label');
    const prefix = output ? 'output-' : 'adjust-';
    const shortLabel = { angle: '网点方向', cellSize: '网点大小', mix0: '红色权重',
      mix1: '绿色权重', mix2: '蓝色权重' }[key] || label.split(' · ')[0];
    const caption = element('label', shortLabel); caption.htmlFor = prefix + key;
    caption.title = label + suffix;
    const number = element('input'); number.type = 'number'; number.min = min; number.max = max; number.step = step;
    number.setAttribute('aria-label', label + suffix); number.id = prefix + key + '-number';
    const range = element('input'); range.type = 'range'; range.min = min; range.max = max; range.step = step;
    range.id = prefix + key; range.setAttribute('aria-label', label);
    line.append(caption, number); row.append(line, range);
    if (suffix) row.append(element('span', suffix.trim(), 'control-unit'));
    for (const input of [number, range]) {
      input.addEventListener('input', () => {
        if (input.value === '') return;
        try { setSetting(key, finite(input.value, min, max, label), output); }
        catch (error) { fail(error); }
      });
      input.addEventListener('change', () => { lastEdit = ''; syncControls(); });
    }
    $(container).append(row);
    controlInputs.set(prefix + key, { range, number, key, output });
  }
}
function setupControls() {
  addControls('tone-controls', TONE.slice(0, 8));
  addControls('tone-advanced-controls', TONE.slice(8));
  const invertLabel = element('label', undefined, 'check-label'), invert = element('input');
  invert.type = 'checkbox'; invert.id = 'adjust-invert';
  invertLabel.append(invert, document.createTextNode('黑白反相'));
  $('tone-controls').append(invertLabel);
  invert.onchange = () => { try { setSetting('invert', invert.checked, false); } catch (error) { fail(error); } };
  addControls('detail-controls', DETAIL);
  const label = element('label', '灰阶输出算法'), mode = element('select');
  mode.id = 'output-mode'; label.htmlFor = mode.id;
  for (const [value, text] of [
    ['floyd-steinberg', 'Floyd–Steinberg · 误差扩散'], ['ordered', 'Bayer · 有序抖动'],
    ['blue-noise', 'Blue noise · 蓝噪声'], ['clustered', 'Clustered · 聚集网点'], ['threshold', 'Threshold · 纯黑白'],
  ]) { const option = element('option', text); option.value = value; mode.append(option); }
  mode.onchange = () => { try { setSetting('mode', mode.value, true); } catch (error) { fail(error); } };
  $('output-controls').append(label, mode);
  addControls('output-controls', OUTPUT, true);
  const ml = element('label', '有序 / 聚集网点矩阵'), matrix = element('select');
  matrix.id = 'output-matrix'; ml.htmlFor = matrix.id;
  for (const n of [2, 4, 8, 16, 32]) { const op = element('option', `${n} × ${n}`); op.value = n; matrix.append(op); }
  matrix.onchange = () => setSetting('matrixSize', Number(matrix.value), true);
  $('output-controls').append(ml, matrix,
    element('p', '灰阶级数是艺术色阶；当前刻图使用两种明暗纹理。网点单位至少 20 μm。角度和种子调整有序、蓝噪声及聚集网点的方向 / 相位，不影响误差扩散。', 'help'));
}
function syncControls() {
  for (const { range, number, key, output } of controlInputs.values()) {
    const value = getSetting(key, output);
    range.value = value; number.value = Number(Number(value).toFixed(3));
    range.style.setProperty('--range-progress', `${100 * (Number(value) - Number(range.min)) / (Number(range.max) - Number(range.min))}%`);
    range.disabled = number.disabled = exporting || !integrity?.ok || (!output && (!selected() || selected().locked));
  }
  $('adjust-invert').checked = selected()?.adjustments.invert || false;
  $('adjust-invert').disabled = exporting || !integrity?.ok || !selected() || selected().locked;
  $('output-mode').value = state.output.mode;
  $('output-matrix').value = state.output.matrixSize;
  $('output-mode').disabled = $('output-matrix').disabled = exporting || !integrity?.ok;
  const layer = selected(), editable = !!layer && !layer.locked && !exporting && !!integrity?.ok;
  for (const id of ['auto-levels', 'auto-enhance', 'reset-adjustments', 'reset-curve', 'copy-settings', 'paste-settings', 'preset']) $(id).disabled = !editable;
  if (!$('preset').querySelector('option[value="custom"]')) {
    const option = element('option', '自定义'); option.value = 'custom'; $('preset').append(option);
  }
  $('preset').value = layer ? Object.entries(PRESETS).find(([, preset]) =>
    settingsKey(normalizeAdjustments(preset)) === settingsKey(layer.adjustments))?.[0] || 'custom' : 'neutral';
}
function syncTransform() {
  const layer = selected();
  const values = { 'layer-name': layer?.name || '', 'layer-x': layer?.x || 0, 'layer-y': layer?.y || 0,
    'layer-width': layer?.widthMm || 90, 'layer-rotation': layer?.rotation || 0,
    'layer-opacity': layer ? Math.round(layer.opacity * 100) : 100 };
  for (const [id, value] of Object.entries(values)) {
    if (document.activeElement !== $(id)) $(id).value = typeof value === 'number' ? Number(value.toFixed(3)) : value;
    $(id).disabled = !layer || layer.locked || exporting;
  }
  $('layer-lock').checked = layer?.locked || false; $('layer-lock').disabled = !layer;
  $('layer-blend').value = layer?.blend || 'source-over'; $('layer-blend').disabled = !layer || layer.locked;
  for (const id of ['layer-up', 'layer-down', 'layer-duplicate', 'layer-delete']) $(id).disabled = !layer || layer.locked || exporting;
}
function syncLayers() {
  $('layer-list').replaceChildren();
  for (const layer of [...state.layers].reverse()) {
    const row = element('li', undefined, 'layer-item');
    row.dataset.selected = String(layer.id === state.selectedId);
    const visibility = element('input'); visibility.type = 'checkbox'; visibility.checked = layer.visible;
    visibility.setAttribute('aria-label', `显示 ${layer.name}`);
    visibility.onchange = () => change(() => { layer.visible = visibility.checked; });
    const button = element('button', layer.name, 'layer-name'); button.type = 'button'; button.title = layer.name;
    button.setAttribute('aria-pressed', String(layer.id === state.selectedId));
    button.onclick = () => { state.selectedId = layer.id; keyDraft = null; syncUI(); requestRender(); };
    const thumbnail = element('img', undefined, 'layer-thumb');
    thumbnail.src = assets.get(layer.assetId).source; thumbnail.alt = ''; thumbnail.draggable = false;
    thumbnail.onclick = () => button.click();
    row.append(thumbnail, visibility, button, element('span', layer.locked ? '锁定' : `${Math.round(layer.opacity * 100)}%`, 'layer-tag'));
    $('layer-list').append(row);
  }
  if ($('layer-empty')) $('layer-empty').hidden = !!state.layers.length;
}
function syncUI() {
  if (!state) return;
  syncLayers(); syncTransform(); syncControls();
  $('undo').disabled = !past.length || exporting; $('redo').disabled = !future.length || exporting;
  $('disc-inner').value = state.disc.innerRadiusMm; $('disc-outer').value = state.disc.outerRadiusMm;
  $('disc-background').value = state.disc.background;
  $('resampling').value = state.resampling;
  $('profile-name').value = state.profileName;
  const layer = selected(), key = keyFor(layer || {}) || { color: [255, 255, 255], tolerance: 8, softness: 2 };
  $('key-color').value = '#' + key.color.map(v => v.toString(16).padStart(2, '0')).join('');
  $('key-tolerance').value = key.tolerance; $('key-softness').value = key.softness;
  $('key-tolerance').style.setProperty('--range-progress', `${key.tolerance}%`);
  $('key-softness').style.setProperty('--range-progress', `${key.softness}%`);
  $('key-tolerance-value').textContent = `${key.tolerance}%`; $('key-softness-value').textContent = `${key.softness}%`;
  for (const id of ['key-pick', 'key-preview', 'key-apply', 'key-cancel', 'key-clear', 'key-color', 'key-tolerance', 'key-softness']) $(id).disabled = exporting || !integrity?.ok || !layer || layer.locked;
  $('export-open').disabled = exporting || sessionEnded || !integrity?.ok;
  $('export-confirm').disabled = exporting || sessionEnded || !integrity?.ok;
  $('preview-mode').disabled = !integrity?.ok;
  $('clipping-warning').disabled = !integrity?.ok;
  drawCurve(false); drawCurve(true); drawStage();
}

function curvePoints(output) { return output ? state.output.outputCurve : selected()?.adjustments.curve || DEFAULT_ADJUSTMENTS.curve; }
function drawCurve(output) {
  const c = $(output ? 'output-curve' : 'tone-curve'), ctx = c.getContext('2d'), p = 12;
  ctx.clearRect(0, 0, c.width, c.height); ctx.strokeStyle = '#3a3e45'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const x = p + (c.width - 2 * p) * i / 4, y = p + (c.height - 2 * p) * i / 4;
    ctx.beginPath(); ctx.moveTo(x, p); ctx.lineTo(x, c.height - p); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(p, y); ctx.lineTo(c.width - p, y); ctx.stroke();
  }
  const pts = curvePoints(output); ctx.strokeStyle = themeColor('--accent'); ctx.lineWidth = 2; ctx.beginPath();
  pts.forEach(([x, y], i) => {
    const px = p + x * (c.width - 2 * p), py = c.height - p - y * (c.height - 2 * p);
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }); ctx.stroke();
  for (const [x, y] of pts) {
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(p + x * (c.width - 2 * p), c.height - p - y * (c.height - 2 * p), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  }
}
function setupCurve(output) {
  const c = $(output ? 'output-curve' : 'tone-curve'); let active = null;
  const point = event => {
    const r = c.getBoundingClientRect();
    return [clamp(((event.clientX - r.left) / r.width * c.width - 12) / (c.width - 24), 0, 1),
      clamp((c.height - 12 - (event.clientY - r.top) / r.height * c.height) / (c.height - 24), 0, 1)];
  };
  const assign = pts => { if (output) state.output.outputCurve = pts; else selected().adjustments.curve = pts; drawCurve(output); requestRender(); };
  c.onpointerdown = event => {
    if (event.button !== 0 || exporting || !integrity?.ok || (!output && (!selected() || selected().locked))) return;
    const p = point(event), pts = clone(curvePoints(output));
    active = pts.findIndex(v => Math.hypot(v[0] - p[0], v[1] - p[1]) < 0.08);
    remember();
    if (active < 0) {
      if (pts.length >= 32) return;
      const x = clamp(p[0], 0.005, 0.995);
      if (pts.some(v => Math.abs(v[0] - x) < 0.004)) return;
      pts.push([x, p[1]]); pts.sort((a, b) => a[0] - b[0]); active = pts.findIndex(v => v[0] === x);
      if (output) pts[active][1] = clamp(pts[active][1], pts[active - 1][1], pts[active + 1][1]);
      assign(pts);
    }
    c.setPointerCapture(event.pointerId); event.preventDefault();
  };
  c.onpointermove = event => {
    if (active === null || active < 0) return;
    const p = point(event), pts = clone(curvePoints(output));
    if (active > 0 && active < pts.length - 1) pts[active][0] = clamp(p[0], pts[active - 1][0] + 0.001, pts[active + 1][0] - 0.001);
    pts[active][1] = output ? clamp(p[1], active ? pts[active - 1][1] : 0, active < pts.length - 1 ? pts[active + 1][1] : 1) : p[1];
    assign(pts);
  };
  c.onpointerup = c.onpointercancel = () => { active = null; lastEdit = ''; syncUI(); };
  c.oncontextmenu = event => {
    event.preventDefault();
    if (!integrity?.ok || exporting || (!output && (!selected() || selected().locked))) return;
    const p = point(event), pts = clone(curvePoints(output));
    const i = pts.findIndex(v => Math.hypot(v[0] - p[0], v[1] - p[1]) < 0.1);
    if (i > 0 && i < pts.length - 1) change(() => { pts.splice(i, 1); assign(pts); });
  };
}
function draftKey() {
  const hex = $('key-color').value;
  return { color: [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)),
    tolerance: Number($('key-tolerance').value), softness: Number($('key-softness').value) };
}
function previewKey() {
  const layer = selectedRequired();
  keyDraft = { layerId: layer.id, key: draftKey() };
  $('preview-mode').value = 'edited';
  $('key-tolerance-value').textContent = `${keyDraft.key.tolerance}%`;
  $('key-softness-value').textContent = `${keyDraft.key.softness}%`;
  $('key-tolerance').style.setProperty('--range-progress', `${keyDraft.key.tolerance}%`);
  $('key-softness').style.setProperty('--range-progress', `${keyDraft.key.softness}%`);
  requestRender();
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('无法读取选择的文件。'));
    reader.readAsDataURL(file);
  });
}
async function decodeSource(source, name, remainingPixels = MAX_SOURCE_PIXELS) {
  if (typeof source !== 'string' || source.length > MAX_SOURCE_BYTES * 1.4 || !/^data:image\/(png|jpeg|webp|bmp);base64,/i.test(source)) {
    throw new Error('只接受本地 PNG / JPEG / WebP / BMP，每张不超过 24 MiB。');
  }
  const image = new Image(); image.src = source;
  await image.decode();
  if (!image.naturalWidth || image.naturalWidth * image.naturalHeight > MAX_SOURCE_PIXELS) {
    image.src = ''; throw new Error('单张原图最多 3600 万像素，请先缩小超大图片。');
  }
  if (image.naturalWidth * image.naturalHeight > remainingPixels) {
    image.src = ''; throw new Error('原图解码总量最多 4800 万像素（同一原图的副本只计一次）。请缩小原图，或保存工程并重新打开以释放历史原图。');
  }
  return { source, name: String(name).slice(0, 120), image, width: image.naturalWidth, height: image.naturalHeight };
}
async function addImages(files) {
  if (exporting || pendingEdits) throw new Error('请等待当前导入、调整或导出完成。');
  pendingEdits++;
  try {
  if (files.length + state.layers.length > MAX_LAYERS) throw new Error(`最多 ${MAX_LAYERS} 个图层。`);
  await verifyPixels();
  const incoming = [];
  let totalPixels = [...assets.values()].reduce((n, a) => n + a.width * a.height, 0);
  let totalBytes = [...assets.values()].reduce((n, a) => n + a.source.length, 0);
  try {
  for (const file of files) {
    if (file.size > MAX_SOURCE_BYTES) throw new Error(`${file.name} 大于 24 MiB。`);
    report(`正在载入 ${file.name}…`);
    const source = await readFile(file);
    totalBytes += source.length;
    if (totalBytes > MAX_PROJECT_BYTES) throw new Error('当前会话的原图总量过大，请保存工程并重新打开后再添加。');
    const asset = await decodeSource(source, file.name, MAX_TOTAL_SOURCE_PIXELS - totalPixels);
    totalPixels += asset.width * asset.height;
    incoming.push(asset);
  }
  } catch (error) { for (const asset of incoming) asset.image.src = ''; throw error; }
  if (!incoming.length) return;
  change(() => {
    for (const asset of incoming) {
      const assetId = uid(), id = uid(); assets.set(assetId, asset);
      state.layers.push({ id, assetId, name: asset.name, x: 0, y: 0,
        widthMm: 104 * Math.min(1, asset.width / asset.height), rotation: 0,
        opacity: 1, visible: true, locked: false, blend: 'source-over', adjustments: clone(DEFAULT_ADJUSTMENTS), key: null });
      state.selectedId = id;
    }
    keyDraft = null;
  });
  } finally { pendingEdits--; }
}
function download(name, type, content) {
  const url = URL.createObjectURL(new Blob([content], { type })), a = element('a');
  a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
function safeName(name) { return String(name || 'artwork').replace(/[^\p{L}\p{N}_. -]/gu, '-').slice(0, 80) || 'artwork'; }
function projectObject(embed = false) {
  const used = [...new Set(state.layers.map(l => l.assetId))];
  return { format: 'discprobe-editor-project', version: 1, media: config.media,
    canvasMm: DIAMETER, gridSize: GRID, state: clone(state),
    assets: used.map(id => ({ id, name: assets.get(id).name, width: assets.get(id).width, height: assets.get(id).height,
      ...(embed ? { source: assets.get(id).source } : {}) })) };
}
function validateKey(key) {
  if (key === null || key === undefined) return null;
  if (!Array.isArray(key.color) || key.color.length !== 3) throw new Error('去背颜色无效。');
  return { color: key.color.map(v => Math.round(finite(v, 0, 255, '背景色'))),
    tolerance: finite(key.tolerance, 0, 100, '去背阈值'), softness: finite(key.softness, 0, 100, '去背羽化') };
}
function validDisc(d) {
  const innerRadiusMm = finite(d.innerRadiusMm, config.media === 'cd' ? 26 : 24.5, 57.9, '内圈半径');
  const outerRadiusMm = finite(d.outerRadiusMm, innerRadiusMm + 0.01, 58, '外圈半径');
  if (!/^#[0-9a-f]{6}$/i.test(d.background)) throw new Error('背景颜色无效。');
  // The canvas is a grayscale artwork. Keep its solid background grayscale too,
  // so the editable PNG and the tone preview agree with the binary handoff.
  const rgb = [1, 3, 5].map(i => parseInt(d.background.slice(i, i + 2), 16));
  const gray = Math.round(rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114).toString(16).padStart(2, '0');
  return { innerRadiusMm, outerRadiusMm, background: '#' + gray.repeat(3) };
}
async function loadProject(file) {
  if (exporting || pendingEdits) throw new Error('请等待当前导入、调整或导出完成。');
  pendingEdits++;
  try {
  await verifyPixels();
  if (file.size > MAX_PROJECT_BYTES) throw new Error('项目文件过大。');
  const p = JSON.parse(await file.text());
  if (p.format !== 'discprobe-editor-project' || p.version !== 1 || p.media !== config.media || p.canvasMm !== DIAMETER) {
    throw new Error('项目格式或盘型不匹配。请使用相同 --media 打开编辑器。');
  }
  if (!Array.isArray(p.assets) || p.assets.length > MAX_LAYERS || !Array.isArray(p.state?.layers) || p.state.layers.length > MAX_LAYERS) throw new Error('项目图层列表无效。');
  const map = new Map();
  let totalPixels = 0, loaded = false;
  try {
  for (const a of p.assets) {
    if (typeof a.id !== 'string' || map.has(a.id)) throw new Error('项目图片编号无效。');
    const asset = await decodeSource(a.source, a.name, MAX_TOTAL_SOURCE_PIXELS - totalPixels);
    totalPixels += asset.width * asset.height;
    map.set(a.id, asset);
  }
  const ids = new Set(), layers = p.state.layers.map(l => {
    if (!map.has(l.assetId) || typeof l.id !== 'string' || ids.has(l.id)) throw new Error('项目图层引用无效。');
    ids.add(l.id);
    if (!['source-over', 'multiply', 'screen'].includes(l.blend)) throw new Error('图层混合模式无效。');
    return { id: l.id, assetId: l.assetId, name: String(l.name || 'Image').slice(0, 120),
      x: finite(l.x, -240, 240, 'X'), y: finite(l.y, -240, 240, 'Y'),
      widthMm: finite(l.widthMm, 0.1, 500, '图层宽度'), rotation: finite(l.rotation, -360, 360, '旋转'),
      opacity: finite(l.opacity, 0, 1, '不透明度'), visible: l.visible !== false, locked: l.locked === true,
      blend: l.blend, adjustments: normalizeAdjustments(l.adjustments), key: validateKey(l.key) };
  });
  const output = normalizeOutput(p.state.output);
  if (output.mode === 'grayscale') throw new Error('刻图输出必须选择二值输出模式，灰阶原稿会单独导出。');
  const next = { layers, selectedId: ids.has(p.state.selectedId) ? p.state.selectedId : layers.at(-1)?.id || null,
    disc: validDisc(p.state.disc), output,
    resampling: ['nearest', 'linear', 'high'].includes(p.state.resampling) ? p.state.resampling : 'high',
    profileName: String(p.state.profileName || '未校准 / Identity').slice(0, 120) };
  if (dirty && !confirm('载入项目会替换当前画布。未保存的修改将丢失，继续吗？')) return;
  for (const asset of assets.values()) asset.image.src = '';
  assets = map; loaded = true; state = next; clearLayerCache(); past = []; future = []; keyDraft = null; dirty = false;
  camera = { zoom: 1, x: 0, y: 0 }; syncUI(); requestRender();
  } finally { if (!loaded) for (const asset of map.values()) asset.image.src = ''; }
  } finally { pendingEdits--; }
}
async function copyText(text, fallback) {
  try { await navigator.clipboard.writeText(text); report('已复制。'); }
  catch {
    if (fallback) { fallback.focus(); fallback.select(); report('浏览器未允许自动复制，文本已选中，请按 Ctrl+C / ⌘C。'); }
    else prompt('请复制下列内容：', text);
  }
}
async function setAuto(enhance) {
  requirePixels();
  if (exporting || pendingEdits) throw new Error('请等待当前导入、调整或导出完成。');
  pendingEdits++;
  try {
  const layer = selectedRequired(), raw = await layerRaster(layer, 600, true);
  if (!state.layers.includes(layer)) return;
  const keyed = layer.key ? applyChromaKey(imageOf(raw), layer.key) : imageOf(raw);
  const levels = autoLevels(keyed, layer.adjustments.mix);
  const next = normalizeAdjustments({ ...layer.adjustments, ...levels,
    ...(enhance ? { contrast: 10, highlights: -10, shadows: 10 } : {}) });
  change(() => { layer.adjustments = next; });
  } finally { pendingEdits--; }
}

async function exportArtwork() {
  if (exporting || sessionEnded) return;
  requirePixels();
  if (pendingEdits) throw new Error('图片还在导入或计算自动调整，请等待完成后再导出。');
  if (keyDraft) throw new Error('请先「应用去背」或「取消预览」，再导出。');
  exporting = true; revision++; renderWanted = false;
  $('export-confirm').disabled = true;
  $('export-message').textContent = '正在以 6000 × 6000 重新渲染，请稍候。';
  syncUI();
  try {
    if (!await verifyPixels()) requirePixels();
    // Let any in-flight preview finish before allocating the full export raster.
    while (rendering) await new Promise(resolve => setTimeout(resolve, 30));
    const source = await compose(GRID, { committed: true });
    const gray = flatten(source);
    source.width = source.height = 1;
    const grayscalePng = $('export-grayscale').checked ? gray.toDataURL('image/png') : undefined;
    $('export-message').textContent = '正在生成可直接交给 image 的二值网点图…';
    const image = await binaryOutput(gray, normalizeOutput(state.output));
    gray.width = gray.height = 1;
    const final = canvasOf(image);
    const payload = { name: safeName($('export-name').value), png: final.toDataURL('image/png'),
      ...(grayscalePng ? { grayscalePng } : {}), finish: $('export-finish').checked,
      metadata: { innerRadiusMm: state.disc.innerRadiusMm, outerRadiusMm: state.disc.outerRadiusMm,
        media: config.media, gridSize: GRID, discDiameterMm: DIAMETER, output: clone(state.output),
        profileName: state.profileName, calibrationStatus: 'user-supplied-unverified', project: projectObject(false) } };
    final.width = final.height = 1;
    $('export-message').textContent = '正在保存到本机并准备下一步命令…';
    const response = await fetch('/api/export', { method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-Discprobe-Token': token,
    }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '保存失败，请检查终端中的错误。');
    exportResult = result;
    $('exported-path').value = result.path;
    $('export-result').hidden = false;
    updateCommand();
    const details = [
      result.ready
        ? '已保存最终二值图；检查导出图后，复制下面的命令在原终端运行。编辑器不会自行刻录。'
        : '图片已保存，但所需几何尚未就绪。请先完成下面列出的测量或配置步骤，不要直接刻录。',
      result.grayscalePath ? `灰阶原稿：${result.grayscalePath}` : '',
      ...(result.warnings || []),
      !result.ready ? '几何尚未就绪：请按提示先完成测量或改用正确的盘型。' : '',
      payload.finish ? '本地服务已退出，原终端可以继续输入命令。' : '本地服务仍在运行；执行命令前在原终端按 Ctrl+C，或使用第二个终端。',
    ].filter(Boolean);
    $('export-message').textContent = details.join('\n');
    if (payload.finish) sessionEnded = true;
    report(result.ready ? '导出成功。请检查导出图，再运行复制的 image 命令。'
      : '图片已导出；尚需完成或选择兼容的几何测量。');
  } finally {
    exporting = false; clearLayerCache();
    $('export-confirm').disabled = sessionEnded;
    syncUI();
    if (renderWanted && !sessionEnded) requestRender();
  }
}
function updateCommand() {
  const command = exportResult?.commands?.[$('export-shell').value] || exportResult?.command;
  $('export-command').value = command || '所选几何不能用于数据轨刻图。请查看上方提示；图片已经保存。';
  $('copy-command').disabled = !command;
}

function bind() {
  const click = (id, fn) => $(id).addEventListener('click', () => Promise.resolve().then(fn).catch(fail));
  click('rerunDiagnostics', async () => {
    if (exporting || pendingEdits) throw new Error('请先等待当前导入或导出完成。');
    revision++;
    report('正在检查本地画布的像素读写…');
    await verifyPixels();
    requestRender();
  });
  click('copyDiagnostics', () => copyText($('diagnosticText').value, $('diagnosticText')));
  click('add-images', () => $('image-files').click());
  $('image-files').onchange = async event => { try { await addImages([...event.target.files]); } catch (error) { fail(error); } finally { event.target.value = ''; } };
  click('undo', () => historyStep(false)); click('redo', () => historyStep(true));
  click('tool-select', () => setTool('select')); click('tool-pan', () => setTool('pan'));
  click('zoom-in', () => zoom(1.25)); click('zoom-out', () => zoom(0.8));
  click('zoom-fit', () => { camera = { zoom: 1, x: 0, y: 0 }; drawStage(); });
  $('preview-mode').onchange = $('preview-size').onchange = $('clipping-warning').onchange = requestRender;
  $('resampling').onchange = () => change(() => { state.resampling = $('resampling').value; });
  $('stage').addEventListener('pointerdown', pointerDown);
  $('stage').addEventListener('pointermove', pointerMove);
  $('stage').addEventListener('pointerup', pointerUp);
  $('stage').addEventListener('pointercancel', pointerUp);
  $('stage').addEventListener('wheel', event => { event.preventDefault(); zoom(Math.exp(-event.deltaY * 0.001), screenPoint(event)); }, { passive: false });
  $('viewport').addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; });
  $('viewport').addEventListener('drop', event => { event.preventDefault(); addImages([...event.dataTransfer.files]).catch(fail); });
  new ResizeObserver(drawStage).observe($('viewport'));
  const transformFields = { 'layer-x': ['x', -240, 240], 'layer-y': ['y', -240, 240],
    'layer-width': ['widthMm', 0.1, 500], 'layer-rotation': ['rotation', -360, 360], 'layer-opacity': ['opacity', 0, 100] };
  for (const [id, [key, lo, hi]] of Object.entries(transformFields)) {
    $(id).onchange = () => { try {
      const layer = selectedRequired(), value = finite($(id).value, lo, hi, key);
      change(() => { layer[key] = key === 'opacity' ? value / 100 : value; });
    } catch (error) { fail(error); syncTransform(); } };
  }
  $('layer-name').onchange = () => { try { const layer = selectedRequired(); change(() => { layer.name = $('layer-name').value.trim().slice(0, 120) || 'Image'; }); } catch (error) { fail(error); } };
  $('layer-lock').onchange = () => { const layer = selected(); if (layer) change(() => { layer.locked = $('layer-lock').checked; }); };
  $('layer-blend').onchange = () => { try { const layer = selectedRequired(); change(() => { layer.blend = $('layer-blend').value; }); } catch (error) { fail(error); } };
  for (const [id, offset] of [['layer-up', 1], ['layer-down', -1]]) click(id, () => {
    const layer = selectedRequired(), i = state.layers.indexOf(layer), next = i + offset;
    if (next >= 0 && next < state.layers.length) change(() => { [state.layers[i], state.layers[next]] = [state.layers[next], state.layers[i]]; });
  });
  click('layer-duplicate', () => {
    const layer = selectedRequired(); if (state.layers.length >= MAX_LAYERS) throw new Error(`最多 ${MAX_LAYERS} 个图层。`);
    change(() => { const next = { ...clone(layer), id: uid(), name: layer.name + ' 副本', x: clamp(layer.x + 2, -240, 240), y: clamp(layer.y - 2, -240, 240) }; state.layers.push(next); state.selectedId = next.id; });
  });
  click('layer-delete', () => {
    const layer = selectedRequired(); change(() => { state.layers = state.layers.filter(l => l.id !== layer.id); state.selectedId = state.layers.at(-1)?.id || null; keyDraft = null; layerCache.delete(layer.id); });
  });
  for (const id of ['disc-inner', 'disc-outer', 'disc-background']) $(id).onchange = () => {
    try { const disc = validDisc({ innerRadiusMm: Number($('disc-inner').value), outerRadiusMm: Number($('disc-outer').value), background: $('disc-background').value }); change(() => { state.disc = disc; }); }
    catch (error) { fail(error); syncUI(); }
  };
  click('key-pick', () => { selectedRequired(); setTool('eyedropper'); report('点击所选图层中要去掉的背景色，再调整阈值。'); });
  click('key-preview', previewKey);
  for (const id of ['key-color', 'key-tolerance', 'key-softness']) $(id).oninput = () => { try { previewKey(); } catch (error) { fail(error); } };
  click('key-apply', () => { const layer = selectedRequired(), key = draftKey(); change(() => { layer.key = key; keyDraft = null; }); });
  click('key-cancel', () => { keyDraft = null; setTool('select'); syncUI(); requestRender(); });
  click('key-clear', () => { const layer = selectedRequired(); change(() => { layer.key = null; keyDraft = null; }); });
  click('auto-levels', () => setAuto(false)); click('auto-enhance', () => setAuto(true));
  click('reset-adjustments', () => { const layer = selectedRequired(); change(() => { layer.adjustments = clone(DEFAULT_ADJUSTMENTS); }); });
  click('reset-curve', () => { const layer = selectedRequired(); change(() => { layer.adjustments.curve = [[0, 0], [1, 1]]; }); });
  click('reset-output-curve', () => change(() => { state.output.outputCurve = [[0, 0], [1, 1]]; }));
  click('copy-settings', () => copyText(JSON.stringify({ format: 'discprobe-adjustments', version: 1, adjustments: selectedRequired().adjustments })));
  click('paste-settings', async () => {
    const layer = selectedRequired(); let text;
    try { text = await navigator.clipboard.readText(); } catch { text = prompt('粘贴之前复制的图层调色参数 JSON：'); }
    if (!text) return;
    if (exporting || !state.layers.includes(layer)) throw new Error('画布状态已变化，请完成当前操作后重新粘贴。');
    if (text.length > 50_000) throw new Error('参数内容过大。');
    const parsed = JSON.parse(text);
    if (parsed.format !== 'discprobe-adjustments' || parsed.version !== 1) throw new Error('不是有效的图层调色参数。');
    const settings = normalizeAdjustments(parsed.adjustments);
    change(() => { layer.adjustments = settings; });
  });
  $('preset').onchange = () => {
    try {
      requirePixels();
      const layer = selectedRequired(), preset = PRESETS[$('preset').value];
      if (!preset) return;
      change(() => { layer.adjustments = normalizeAdjustments(preset); });
    } catch (error) { fail(error); }
  };
  click('save-project', () => { download(safeName($('export-name').value) + '.discproject.json', 'application/json', JSON.stringify(projectObject(true))); dirty = false; report('项目已下载，包含原图和非破坏性图层参数。'); });
  click('open-project', () => $('project-file').click());
  $('project-file').onchange = async event => { try { if (event.target.files[0]) await loadProject(event.target.files[0]); } catch (error) { fail(error); } finally { event.target.value = ''; } };
  $('profile-name').onchange = () => change(() => { state.profileName = $('profile-name').value.trim().slice(0, 120) || '未校准 / Identity'; });
  click('save-profile', () => download(safeName(state.profileName) + '.discprofile.json', 'application/json', JSON.stringify({
    format: 'discprobe-output-profile', version: 1, media: config.media, name: state.profileName,
    output: state.output, resampling: state.resampling, calibrationStatus: 'user-supplied-unverified',
  }, null, 2)));
  click('open-profile', () => $('profile-file').click());
  $('profile-file').onchange = async event => {
    try {
      const file = event.target.files[0]; if (!file) return;
      if (file.size > 100_000) throw new Error('配置文件过大。');
      const p = JSON.parse(await file.text());
      if (exporting) throw new Error('请等待导出完成后再载入配置。');
      if (p.format !== 'discprobe-output-profile' || p.version !== 1 || p.media !== config.media) throw new Error('灰阶配置格式或盘型不匹配。');
      const output = normalizeOutput(p.output); if (output.mode === 'grayscale') throw new Error('配置必须使用二值输出模式。');
      change(() => { state.output = output; state.profileName = String(p.name || '用户配置').slice(0, 120);
        if (['nearest', 'linear', 'high'].includes(p.resampling)) state.resampling = p.resampling; });
    } catch (error) { fail(error); } finally { event.target.value = ''; }
  };
  const panelTabs = [...document.querySelectorAll('[data-panel]')];
  for (const button of panelTabs) {
    button.tabIndex = button.getAttribute('aria-selected') === 'true' ? 0 : -1;
    button.onclick = () => {
    for (const b of panelTabs) {
      b.setAttribute('aria-selected', String(b === button)); b.tabIndex = b === button ? 0 : -1;
    }
    for (const name of ['tone', 'detail', 'output']) $('panel-' + name).hidden = name !== button.dataset.panel;
    };
    button.onkeydown = event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const i = panelTabs.indexOf(button), offset = event.key === 'ArrowLeft' ? -1 : 1;
      const next = event.key === 'Home' ? panelTabs[0] : event.key === 'End' ? panelTabs.at(-1)
        : panelTabs[(i + offset + panelTabs.length) % panelTabs.length];
      next.click(); next.focus();
    };
  }
  click('export-open', () => { $('export-dialog').showModal(); });
  click('export-close', () => { if (!exporting) $('export-dialog').close(); });
  $('export-dialog').addEventListener('cancel', event => { if (exporting) event.preventDefault(); });
  click('export-confirm', async () => { try { await exportArtwork(); } catch (error) { $('export-message').textContent = error.message; throw error; } });
  $('export-shell').onchange = updateCommand;
  click('copy-command', () => copyText($('export-command').value, $('export-command')));
  click('copy-path', () => copyText($('exported-path').value, $('exported-path')));
  setupCurve(false); setupCurve(true);
  window.addEventListener('keydown', event => {
    if (event.target.closest('input, textarea, select, button') || $('export-dialog').open) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); historyStep(event.shiftKey); }
    else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') { event.preventDefault(); historyStep(true); }
    else if (event.code === 'Space') { spaceHeld = true; event.preventDefault(); drawStage(); }
    else if (event.key === 'Escape') { keyDraft = null; setTool('select'); requestRender(); }
    else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key) && selected() && !selected().locked) {
      event.preventDefault(); const step = event.shiftKey ? 1 : 0.1;
      change(() => { const l = selected(); if (event.key === 'ArrowLeft') l.x = clamp(l.x - step, -240, 240);
        if (event.key === 'ArrowRight') l.x = clamp(l.x + step, -240, 240);
        if (event.key === 'ArrowUp') l.y = clamp(l.y + step, -240, 240);
        if (event.key === 'ArrowDown') l.y = clamp(l.y - step, -240, 240); }, 'nudge');
    } else if ((event.key === 'Delete' || event.key === 'Backspace') && selected() && !selected().locked) {
      event.preventDefault(); $('layer-delete').click();
    }
  });
  window.addEventListener('keyup', event => { if (event.code === 'Space') { spaceHeld = false; drawStage(); } });
  window.addEventListener('blur', () => { spaceHeld = false; drag = null; drawStage(); });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
}

async function main() {
  const response = await fetch('/api/config', { headers: { 'X-Discprobe-Token': token } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请从 python -m discprobe editor 打开的完整本机链接进入。');
  config = data;
  state = { layers: [], selectedId: null,
    disc: { innerRadiusMm: config.innerRadiusMm, outerRadiusMm: config.outerRadiusMm, background: '#ffffff' },
    output: clone(DEFAULT_OUTPUT), resampling: 'high', profileName: '未校准 / Identity' };
  $('media-label').value = `${config.media.toUpperCase()} · 120 mm`;
  $('geometry-label').value = config.geometryReady ? '已选几何 · ' + config.geometryPath : '可先设计 · 几何待确认';
  $('geometry-label').title = config.geometryPath || config.geometryStatus;
  $('disc-inner').min = config.media === 'cd' ? 26 : 24.5;
  // The Windows release's Start.bat opens CMD, not PowerShell. Other shells
  // remain explicitly selectable in the export dialog.
  $('export-shell').value = /Win/i.test(navigator.platform) ? 'cmd' : 'posix';
  setupWorker(); setupControls(); bind();
  await verifyPixels();
  syncUI(); requestRender();
  document.documentElement.dataset.editorBuild = EDITOR_BUILD;
  document.documentElement.dataset.ready = 'true';
}
main().catch(error => { fail(error); $('export-open').disabled = true; });
