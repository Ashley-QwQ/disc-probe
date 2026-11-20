import { hasCapability } from './handshake.mjs';

const el = (tag, text) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  return node;
};

export function burnChecklist(api, workId, burnId, signal) {
  if (!hasCapability('checkburn') || !api.backend?.request) return () => null;
  const route = `/api/works/${encodeURIComponent(workId)}/after-burn/checkburn?burn=${encodeURIComponent(burnId)}`;
  let open = false, busy = false, saved, live, error, repaint;
  const load = async now => {
    if (signal.aborted || busy) return;
    busy = true;
    error = null;
    repaint();
    try {
      const result = await api.backend.request(route, now ? {} : undefined);
      if (now) live = result;
      else saved = result;
    } catch (err) {
      error = err;
    } finally {
      busy = false;
      if (!signal.aborted) repaint();
    }
  };

  return function render() {
    const english = api.lang() === 'en';
    const L = (zh, en) => english ? en : zh;
    const words = pair => L(pair.zh, pair.en);
    const details = el('details');
    details.className = 'ab-report';
    details.dataset.capability = 'checkburn';
    details.open = open;
    const entry = el('summary', L('看不到图？', 'Can’t see the picture?'));
    const section = el('section');
    details.append(entry, section);
    const controls = el('div');
    controls.className = 'burn-actions';
    const read = el('button', L('读取光驱里的盘', 'Check the disc in the drive'));
    read.type = 'button';
    read.onclick = () => load(true);
    const restore = el('button', L('查看这次刻录的记录', 'Review the saved burn'));
    restore.type = 'button';
    restore.onclick = () => {
      live = null;
      error = null;
      if (saved) repaint();
      else load(false);
    };
    controls.append(read, restore);
    const status = el('p');
    status.setAttribute('role', 'status');
    const rows = el('div');
    section.append(status, rows, controls);

    repaint = () => {
      read.disabled = busy;
      restore.disabled = busy;
      restore.hidden = !live && !error && !!saved;
      controls.hidden = !saved && !error && busy;
      if (busy) status.textContent = L('正在读取检查结果……', 'Reading checks…');
      else if (error) status.textContent = L('没有完成，请重试。', 'Could not complete the check. Please retry.') + ` ${error.message}`;
      else if (live) status.textContent = L('以下是当前光驱里的盘。', 'These checks describe the disc currently in the drive.');
      else if (saved) status.textContent = L('以下来自这次刻录保存的记录。', 'These checks come from the saved burn record.');
      else status.textContent = '';
      const active = rows.contains(document.activeElement);
      rows.replaceChildren();
      const result = error ? null : live || saved;
      if (!result) return;
      const info = el('p', words(result.disc_summary));
      const heading = el('h2', L('刻后检查单', 'Post-burn checklist'));
      heading.tabIndex = -1;
      const checks = el('dl');
      checks.className = 'burn-checks';
      for (const item of result.checklist) {
        const label = el('dt', words(item.title));
        const detail = el('dd');
        detail.dataset.s = {excluded:'good', possible:'warn', unknown:'unknown'}[item.status];
        detail.append(el('strong', words(item.status_label)), ' ', words(item.message));
        if (item.link?.id === 'start-guide-light') {
          const guide = el('button', words(item.link.label));
          guide.type = 'button';
          guide.onclick = async () => (await import('./guide.js')).open(guide);
          detail.append(el('br'), guide);
        }
        checks.append(label, detail);
      }
      rows.append(heading, info, checks);
      if (active) heading.focus();
    };
    details.ontoggle = () => {
      if (!details.isConnected) return;
      open = details.open;
      if (open && !saved && !error) load(false);
    };
    repaint();
    return details;
  };
}
