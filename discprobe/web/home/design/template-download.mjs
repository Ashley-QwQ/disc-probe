import { CELLS } from "./export-rules.mjs";
import { lampPose } from "./lamp-pose.mjs";

export const GRID_PNG_LIMIT = 256 * 2 ** 20;
export const templateWords = lang => lang === 'en' ? {
  download: 'Download template', pitch: 'Grid pitch', prepare: 'Preparing…',
  import: 'Import template artwork', importing: 'Reading template artwork…',
  failed: 'Template download failed.', badArtwork: 'Use a full-size template PNG (6,000, 12,000 or 24,000 px square).',
  tooBig: 'Template PNGs can be up to 256 MiB. Try higher PNG compression at the same size.',
  files: 'Blank PNG and separate guide', large: size => `One open layer uses ${size} GiB before app overhead.`,
} : {
  download: '下载模板', pitch: '格距', prepare: '正在准备…',
  import: '导入模板作品', importing: '正在读取模板作品…',
  failed: '模板下载失败。', badArtwork: '请选择完整的模板 PNG（6000、12000 或 24000 像素见方）。',
  tooBig: '单张模板 PNG 最大 256 MiB。可保持尺寸，提高 PNG 压缩级别后再试。',
  files: '透明底稿 + 独立引导层', large: size => `打开一层约占 ${size} GiB，另计软件开销。`,
};

export function templateRequest(work, grid) {
  const geo = work.item?.geo || work.item?.preset || work.geo;
  if (!geo) throw new Error('请先为这件作品选择有几何的盘批次 / Choose a batch with geometry first.');
  const request = { geo, media: work.media,
    ...(work.item?.sectors ? { sectors: work.item.sectors } : {}),
    ...(work.item?.id?.startsWith('preset:') ? { preset_id: work.item.id.slice(7) } : {}) };
  if (grid === undefined) return request;
  if (!Object.hasOwn(CELLS, grid)) throw new Error('Choose 5, 10 or 20 µm.');
  const {camera, flash, rotate, delta_scale} = lampPose(work);
  const batch = work.item?.mid || work.item?.name;
  return { ...request, grid, pose: [...camera, ...flash].join(','), rotate,
    ...(batch ? { batch } : {}), ...(delta_scale === undefined ? {} : { delta_scale }) };
}

export function templateDetails(grid, lang) {
  const side = CELLS[grid], t = templateWords(lang);
  const pixels = side.toLocaleString(lang === 'en' ? 'en' : 'zh-CN');
  return `${pixels} × ${pixels} px · ${t.files}` +
    (grid === 5 ? ` · ${t.large((4 * side ** 2 / 2 ** 30).toFixed(2))}` : '');
}

export async function downloadTemplate(work, button, notify, grid, lang) {
  const label = button.textContent;
  const t = templateWords(lang);
  try {
    const payload = templateRequest(work, grid);
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = t.prepare;
    const response = await fetch('/api/template', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error((await response.json()).error || t.failed);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    const name = response.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
    link.href = url;
    link.download = name ? decodeURIComponent(name) : 'disc-template.zip';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (error) {
    notify(String(error.message || error));
  } finally {
    button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = label;
  }
}

// Read PNG metadata without asking the browser to decode a 24,000 px texture.
export async function gridArtworkPitch(file, explicit = false) {
  const data = new DataView(await file.slice(0, 64 * 1024).arrayBuffer());
  if (data.byteLength < 33 || data.getUint32(0) !== 0x89504e47 ||
      data.getUint32(4) !== 0x0d0a1a0a || data.getUint32(12) !== 0x49484452) return null;
  const width = data.getUint32(16), height = data.getUint32(20);
  const grid = Number(Object.keys(CELLS).find(pitch => CELLS[pitch] === width));
  if (!grid || width !== height) return null;
  if (explicit || new RegExp(`^dp_template_${grid}um_`, 'i').test(file.name)) return grid;
  for (let offset = 33; offset + 12 <= data.byteLength;) {
    const length = data.getUint32(offset), type = data.getUint32(offset + 4);
    if (type === 0x49444154 || offset + 12 + length > data.byteLength) break; // IDAT
    if (type === 0x70485973 && length === 9 && data.getUint8(offset + 16) === 1) { // pHYs
      const ppm = 1e6 / grid;
      if (Math.abs(data.getUint32(offset + 8) - ppm) <= 1 &&
          Math.abs(data.getUint32(offset + 12) - ppm) <= 1) return grid;
    }
    offset += 12 + length;
  }
  return null;
}
