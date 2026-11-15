// Files are local paths, never browser uploads. Only the core allocates sectors.
const escape = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const localFilesAvailable = (host = location.hostname) => ['localhost', '127.0.0.1'].includes(host);
export const occupiedRings = (files) => files?.layout ? [
  ...files.layout.occupied_radius_mm,
  ...(files.layout.margin_radius_mm ? [files.layout.margin_radius_mm] : []),
] : [];
export function filePictureRange(files, fallback) {
  const ranges = files?.layout?.picture_radius_mm;
  if (!ranges?.length) return files?.layout ? [fallback[0], fallback[0]] : fallback;
  return [Math.max(fallback[0], ranges[0][0]), Math.min(fallback[1], ranges.at(-1)[1])];
}
export function fileArguments(files) {
  if (!files) return {};
  if (!files.layout) throw Error('请先检查随盘文件布局 / check the files layout first');
  return {files:files.folder, files_at:files.where, files_margin:files.layout.files_margin,
    writable_sectors:files.layout.writable_sectors,
    ...(files.layout.layout_sha256?{files_plan_sha256:files.layout.layout_sha256}:{})};
}
export async function refreshFiles(files, context = {}) {
  const response = await fetch('/api/files-layout', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:files.folder, files_at:files.where ?? 'inner', margin:files.margin,
      writable_sectors:files.writable || undefined, ...context})});
  const result = await response.json();
  if (!response.ok) throw Error(result.error ?? '无法检查文件布局 / layout check failed');
  return {...files, folder:result.folder, layout:result};
}
export function mountFilesStep(parent, {getFiles, setFiles, context, onChange, lang='zh', media='dvd'}) {
  if (!document.querySelector('link[data-disc-files-style]')) {
    const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('./disc-files.css',import.meta.url);link.dataset.discFilesStyle='';document.head.append(link);
  }
  const zh = lang !== 'en', files = getFiles();
  const section = document.createElement('section');
  section.className = 'disc-files-step';
  const allowed = localFilesAvailable() && media === 'dvd';
  const why = media !== 'dvd' ? (zh ? '目前只支持 DVD±R 单层。' : 'DVD single-layer only for now.') :
    (zh ? '请在运行核心的电脑打开 localhost；手机和局域网无法选择这台电脑的文件夹。' : 'Open localhost on the core computer. Phones and LAN clients cannot select its folders.');
  section.innerHTML = `<h3>${zh?'随盘文件':'Files on the disc'}</h3>`+
    `<p class="note">${zh?'任何电脑都能直接读这些文件；图案在剩下的地方。':'Computers can read these files directly; the picture uses the remaining area.'}</p>`+
    (!allowed ? `<p class="note quiet">${why}</p>${files?`<button class="sbtn" type="button" data-files="clear">${zh?'清除文件':'Clear files'}</button>`:''}` :
    `<label>${zh?'本机文件夹路径':'Local folder path'}<input data-files="folder" type="text" spellcheck="false" value="${escape(files?.folder)}" placeholder="D:\\作品\\随盘文件"></label>`+
    `<label>${zh?'放置位置':'Placement'}<select data-files="where"><option value="inner" ${files?.where==='outer'?'':'selected'}>${zh?'内圈':'Inner'}</option><option value="outer" ${files?.where==='outer'?'selected':''}>${zh?'外圈':'Outer'}</option></select></label>`+
    `<details><summary>${zh?'容量与安全余量':'Capacity and safety margin'}</summary>`+
    `<label>${zh?'可写扇区数（可留空，使用实测几何）':'Writable sectors (optional with geometry)'}<input data-files="writable" type="number" min="32" max="2295104" step="1" value="${escape(files?.writable)}"></label>`+
    `<label>${zh?'外圈安全余量（比例）':'Outer safety margin (fraction)'}<input data-files="margin" type="number" min="0" max="0.99" step="0.01" value="${escape(files?.margin)}" placeholder="0.05"></label>`+
    `<p class="note quiet">${zh?'外圈默认留出 5% 扇区，避开盘边；可填 0。内圈为 0。':'Outer placement reserves 5% of sectors at the rim by default; use 0 for none. Inner uses 0.'}</p></details>`+
    `<div class="row2"><button class="sbtn" type="button" data-files="check">${zh?'检查布局':'Check layout'}</button><button class="sbtn" type="button" data-files="clear">${zh?'清除文件':'Clear files'}</button></div>`)+
    `<p class="note quiet" role="status" aria-live="polite" data-files="status"></p>`;
  parent.append(section);
  const q = name => section.querySelector(`[data-files="${name}"]`), status=q('status');
  if (!allowed) {
    q('clear')?.addEventListener('click',()=>{setFiles(null);onChange();section.remove();mountFilesStep(parent,{getFiles,setFiles,context,onChange,lang,media});});
    return;
  }
  const sayLayout = () => {
    const layout=getFiles()?.layout;
    status.textContent=layout ? `${layout.file_count} ${zh?'个文件':'files'} · ${layout.file_sectors} ${zh?'文件扇区':'file sectors'} + ${layout.metadata_sectors} ${zh?'元数据扇区':'metadata sectors'} · ${zh?'图案':'Picture'} ${layout.picture_radius_mm.map(([a,b])=>`${a.toFixed(2)}–${b.toFixed(2)} mm`).join(', ')}${layout.radius_source==='nominal' ? (zh?'（标称半径，出图前按实测更新）':' (nominal radii; updated from measurement before export)') : ''}` : '';
  };
  sayLayout();
  let revision=0;
  const values = () => ({folder:q('folder').value.trim(), where:q('where').value,
    margin:q('margin').value==='' ? undefined : Number(q('margin').value),
    writable:q('writable').value==='' ? undefined : Number(q('writable').value)});
  for (const name of ['folder','where','margin','writable']) q(name).addEventListener('input',()=>{
    revision++; setFiles(values()); onChange();
    status.textContent=zh?'设置已改变，请检查布局。':'Settings changed. Check the layout.';
  });
  q('clear').addEventListener('click',()=>{ revision++; setFiles(null); onChange(); section.remove(); mountFilesStep(parent,{getFiles,setFiles,context,onChange,lang,media}); });
  q('check').addEventListener('click',async()=>{
    const turn=++revision;
    q('check').disabled=true; section.setAttribute('aria-busy','true');
    status.textContent=zh?'正在检查文件与扇区…':'Checking files and sectors…';
    const chosen=values(); setFiles(chosen); onChange();
    try {
      if (!q('writable').checkValidity() || !q('margin').checkValidity()) throw Error(zh?'请检查容量与余量。':'Check capacity and margin.');
      const result=await refreshFiles(chosen,await context());
      if (turn!==revision || !section.isConnected) return;
      setFiles(result); onChange(); sayLayout();
    } catch(error) {
      if(turn===revision) status.textContent=error.message;
    } finally { q('check').disabled=false; section.removeAttribute('aria-busy'); }
  });
}

export function drawFileGuides(g, view, rings, cssVar) {
  for(const [inner,outer] of rings) {
    if(outer<=inner) continue;
    const {cx,cy,s}=view, R=outer*s;
    g.save(); g.beginPath(); g.arc(cx,cy,R,0,2*Math.PI); g.arc(cx,cy,inner*s,0,2*Math.PI,true); g.clip('evenodd');
    g.fillStyle=cssVar('--dim'); g.fillRect(cx-R,cy-R,2*R,2*R);
    g.strokeStyle=cssVar('--ink-3'); g.globalAlpha=.45; g.lineWidth=1;
    for(let k=-2*R;k<2*R;k+=9){g.beginPath();g.moveTo(cx+k-R,cy+R);g.lineTo(cx+k+R,cy-R);g.stroke();}
    g.restore();
  }
}
