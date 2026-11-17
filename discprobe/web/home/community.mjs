// Community hints never select a batch or a geometry. Only an explicit import writes.
export const resultText = (value, zh = true) => ({
  worked: zh ? '有人报告有效' : 'reported working',
  partly: zh ? '有人报告部分有效' : 'reported partly working',
  failed: zh ? '有人用这组失败了' : 'reported failed',
  unknown: zh ? '结果未确认' : 'outcome unconfirmed',
})[value] || (zh ? '结果未确认' : 'outcome unconfirmed');

export function safeGithub(value) {
  if (typeof value !== 'string' || value.length > 600 || /[\s\\]/.test(value)) return false;
  try { const u = new URL(value); return u.protocol === 'https:' && u.host === 'github.com' && !u.username && !u.password && !u.search; }
  catch { return false; }
}
export function notice(entry, zh = true, {author = true} = {}) {
  const s = entry.source, from = s.kind === 'dis_builtin' ? `DIS ${s.version}` : `DIS ${zh ? '社区' : 'community'}${author && s.author ? ' ' + s.author : ''}`;
  const span = entry.measured_span_mm?.join('–');
  return zh ? `来自 ${from}，不是 DP 测的；${span ? `${span} mm` : '没有实测范围'}；这批盘还没确认。`
    : `From ${from}; not measured by DP; ${span ? `${span} mm measured` : 'no measured range'}; this batch is unconfirmed.`;
}
// Drives and posts write a MID with a dye note after a middle dot ("MCC 004 · AZO"); compare the code only.
export const midCode = (value) => String(value || '').split(/[·•]/)[0].trim().replace(/\s+/g, ' ').toLowerCase();
export function matches(entries, {media, mid, sectors, includeFailed = false} = {}) {
  const code = midCode(mid);
  return entries.filter(e => {
    if (media && e.media !== media || !includeFailed && e.result === 'failed') return false;
    const discs = [e.disc, ...(e.also || []).map(s => s.disc).filter(Boolean)];
    return discs.some(d => code && midCode(d.mid) === code || sectors != null && d.capacity_sectors === sectors);
  }).sort((a,b) => {
    const discs = e => [e.disc, ...(e.also || []).map(s => s.disc).filter(Boolean)];
    const midRank = e => discs(e).some(d => code && midCode(d.mid) === code) ? 0 : 1;
    const sectorRank = e => discs(e).some(d => sectors != null && d.capacity_sectors === sectors) ? 0 : 1;
    return midRank(a) - midRank(b) || sectorRank(a) - sectorRank(b) || a.id.localeCompare(b.id);
  });
}
export async function receive({refresh = false, fetcher = fetch, signal} = {}) {
  const r = await fetcher(`/api/community${refresh ? '?refresh=1' : ''}`, {method:'GET',cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',signal});
  if (!r.ok) throw Error(`HTTP ${r.status}`);
  const raw = await r.text();
  if (raw.length > 2 * 1024 * 1024) throw Error('community response too large');
  const value = JSON.parse(raw);
  if (value.feed?.format !== 'dp-community' || value.feed?.version !== 1 || !Array.isArray(value.feed.entries)
      || value.count !== value.feed.entries.length || !['network','cache','bundled'].includes(value.from)
      || value.feed.entries.some(e => !safeGithub(e.source?.url) || !e.disc || !Array.isArray(e.also)
        || e.also.some(s => !safeGithub(s.url)))) throw Error('invalid community response');
  return value;
}
// A MID names the dye maker's product; a sector count is shared by most discs of one standard
// (nearly every DVD-R has the same one). So a MID match, when there is one, is the only hint; a
// capacity-only match is offered as weaker evidence and says so.
export function hint(entries, identity, zh = true) {
  const code = String(identity?.mid || '').trim();
  const byMid = code ? matches(entries, {...identity, sectors: null}) : [];
  const rows = byMid.length ? byMid : matches(entries, {...identity, mid: null});
  if (!rows.length) return null;
  const counts = [...new Set(rows.map(e => resultText(e.result,zh)))].join('、');
  const source = notice(rows[0], zh, {author: rows.length === 1});
  const what = byMid.length ? (zh ? `同 MID 的社区记录 ${rows.length} 条` : `${rows.length} community records with this MID`)
    : (zh ? `容量相同的社区记录 ${rows.length} 条（不一定是同一种盘）` : `${rows.length} community records with this capacity (not necessarily the same disc)`);
  return {rows, byMid: byMid.length > 0, text: zh ? `${what} · ${counts}。${source}` : `${what} · ${counts}. ${source}`};
}
export function mountList(parent, got, {zh = true, onImported, fetcher = fetch} = {}) {
  const el = (tag,cls,text) => {const n = document.createElement(tag); n.className = cls; if (text != null) n.textContent = text; return n;};
  const section = el('section','fx-col fx-community');
  section.append(el('h3','fx-sect',zh ? '社区提示' : 'Community hints'));
  const from = {network:'联网',cache:'上次的',bundled:'程序自带'};
  section.append(el('p','fx-byline',`${got.date} · ${got.count} · ${zh ? from[got.from] : got.from}`));
  const label = el('label','fx-note',zh ? '盘类型 ' : 'Disc type '), select = el('select','fx-btn');
  for (const media of ['cd','dvd','bd']) {const o = el('option','',media.toUpperCase()); o.value = media; select.append(o);}
  label.append(select); section.append(label);
  const failedLabel = el('label','fx-note'), failed = el('input',''); failed.type = 'checkbox';
  failedLabel.append(failed,document.createTextNode(zh ? ' 也看失败记录' : ' Include failed reports')); section.append(failedLabel);
  const list = el('div',''); section.append(list);
  function paint() {
    list.replaceChildren();
    for (const row of got.feed.entries.filter(e => e.media === select.value && (failed.checked || e.result !== 'failed'))) {
      const detail = el('details','fx-story'), summary = el('summary','',`${row.disc.brand || row.id} · ${resultText(row.result,zh)}`);
      detail.append(summary,el('p','fx-byline',`${row.id} · ${row.source.author || 'DIS'} · ${row.source.date} · ${row.confidence}`),
        el('p','',notice(row,zh)),el('p','',row.result_notes),
        el('p','fx-note',[row.disc.mid,row.disc.type,row.disc.ring_code,row.disc.capacity_sectors,row.drive,row.speed].filter(Boolean).join(' · ')),
        el('pre','fx-note',JSON.stringify(row.parameters,null,2)));
      for (const s of [row.source,...row.also]) {
        if (!safeGithub(s.url)) continue;
        const a = el('a','fx-btn',[s.kind === 'dis_builtin' ? `DIS ${s.version}` : (zh ? '原帖' : 'Original post'),s.author,s.disc?.brand,s.result ? resultText(s.result,zh) : ''].filter(Boolean).join(' · '));
        a.href=s.url; a.target='_blank'; a.rel='noopener noreferrer'; detail.append(a);
      }
      const button = el('button','fx-btn',zh ? '导入预设库（只当起点）' : 'Import as a starting point'); button.type='button';
      const status = el('p','fx-note'); status.setAttribute('role','status');
      button.addEventListener('click',async () => {
        button.disabled=true; status.textContent=zh ? '正在导入…' : 'Importing…';
        try {
          const r=await fetcher('/api/community',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:row.id})});
          const result=await r.json(); if (!r.ok || result.error) throw Error(result.error || `HTTP ${r.status}`);
          if (!result.written?.length && !result.duplicates?.length) throw Error(result.entries?.[0]?.issues?.join('; ') || 'Import refused');
          globalThis.dispatchEvent(new Event('dp-catalogue-changed')); await onImported?.(result);
          status.textContent=(zh ? '已进预设库。' : 'Saved in preset library. ') + notice(row,zh);
        } catch(e) {status.textContent=(zh ? '未导入：' : 'Not imported: ') + e.message;}
        finally {button.disabled=false;}
      });
      detail.append(button,status); list.append(detail);
    }
    if (!list.children.length) list.append(el('p','fx-note',zh ? '没有这类记录。' : 'No records of this type.'));
  }
  select.addEventListener('change',paint); failed.addEventListener('change',paint); paint(); parent.append(section);
  return section;
}
