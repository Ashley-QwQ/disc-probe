// A small adapter only: geometry, materials and rendering all live in Python.
export function templateRequest(work) {
  const geo = work.item?.geo || work.item?.preset || work.geo;
  if (!geo) throw new Error('请先为这件作品选择有几何的盘批次 / Choose a batch with geometry first.');
  return { geo, media: work.media,
    ...(work.item?.sectors ? { sectors: work.item.sectors } : {}),
    ...(work.item?.id?.startsWith('preset:') ? { preset_id: work.item.id.slice(7) } : {}) };
}

export async function downloadTemplate(work, button, notify) {
  const label = button.textContent;
  try {
    const payload = templateRequest(work);
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = '正在准备 / Preparing…';
    const response = await fetch('/api/template', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error((await response.json()).error || '模板下载失败 / Template download failed');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url; link.download = 'disc-template.zip';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (error) {
    notify(String(error.message || error));
  } finally {
    button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = label;
  }
}
