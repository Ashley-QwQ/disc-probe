// after ObsidianUI active-sessions, MIT. See LICENSE.obsidianui.txt.
// Current-device ordering, pending/error rows and focus recovery adapted; icons and copy are ours.
import { icon, language, node, words } from './shared.js';

/** `since` is a Date, epoch milliseconds or ISO string. Unknown is never guessed. */
export function timeWords(since, now = Date.now(), lang = 'zh') {
  const time = since === null || since === undefined || since === '' ? NaN : new Date(since).getTime();
  if (!Number.isFinite(time) || !Number.isFinite(now)) return words(lang, '连接时间未知', 'Connection time unknown');
  const minutes = Math.floor(Math.max(0, now - time) / 60000);
  if (minutes < 1) return words(lang, '刚连上', 'Just connected');
  const [count, zh, en] = minutes < 60 ? [minutes, '分钟', 'minute'] : minutes < 1440 ?
    [Math.floor(minutes / 60), '小时', 'hour'] : [Math.floor(minutes / 1440), '天', 'day'];
  return words(lang, `已连上 ${count} ${zh}`, `Connected for ${count} ${en}${count === 1 ? '' : 's'}`);
}
export function deviceMeta(device, now = Date.now(), lang = 'zh') {
  if (!Number.isFinite(device.sent)) return `${timeWords(device.since, now, lang)} · ${words(lang, '照片数未知', 'Photo count unknown')}`;
  const count = Number.isFinite(device.sent) ? Math.max(0, Math.floor(device.sent)) : 0;
  return `${timeWords(device.since, now, lang)} · ${words(lang, `发来 ${count} 张`, `Sent ${count} ${count === 1 ? 'photo' : 'photos'}`)}`;
}

const mounted = new WeakMap();
export function deviceList(el, devices = [], options = {}) {
  if (mounted.has(el)) {
    const api = mounted.get(el);
    api.update(devices, options);
    return api;
  }
  const doc = el.ownerDocument;
  let items = [], opts = {}, lang = 'zh';
  const pending = new Set(), errors = new Set();
  const list = node(doc, 'ul', 'kit-device-rows');
  const empty = node(doc, 'p', 'kit-device-empty');
  empty.tabIndex = -1;
  const announcement = node(doc, 'span', 'kit-sr');
  announcement.setAttribute('role', 'status');
  el.classList.add('kit-devices');
  el.replaceChildren(list, empty, announcement);

  function render() {
    const active = doc.activeElement;
    const focusedId = list.contains(active) ? active.dataset.deviceId : undefined;
    lang = language(opts.lang);
    el.lang = lang === 'en' ? 'en' : 'zh-CN';
    list.setAttribute('aria-label', words(lang, '已连接的设备', 'Connected devices'));
    const ordered = [...items].sort((a, b) => Number(!!b.thisDevice) - Number(!!a.thisDevice));
    list.replaceChildren(...ordered.map(device => {
      const row = node(doc, 'li', 'kit-device-row');
      row.append(icon(doc, device.kind));
      const content = node(doc, 'div', 'kit-device-content');
      const title = node(doc, 'p', 'kit-device-name', device.name || words(lang, '未命名设备', 'Unnamed device'));
      if (device.thisDevice) title.append(node(doc, 'span', 'kit-device-current', words(lang, '本机', 'This device')));
      const meta = node(doc, 'p', 'kit-device-meta', deviceMeta(device, opts.now ?? Date.now(), lang));
      content.append(title, meta);
      if (errors.has(device.id)) {
        const error = node(doc, 'p', 'kit-device-error', words(lang, '未能断开，请重试。', 'Could not disconnect. Try again.'));
        error.setAttribute('role', 'alert');
        content.append(error);
      }
      row.append(content);
      if (!device.thisDevice) {
        const button = node(doc, 'button', 'kit-text-button', pending.has(device.id) ?
          words(lang, '正在断开…', 'Disconnecting…') : words(lang, '断开', 'Disconnect'));
        button.type = 'button';
        button.dataset.deviceId = String(device.id);
        // Keep a pending action focusable, so replacing the row does not lose keyboard focus.
        button.disabled = typeof opts.onDisconnect !== 'function';
        button.setAttribute('aria-disabled', String(pending.has(device.id) || button.disabled));
        button.setAttribute('aria-label', `${words(lang, '断开', 'Disconnect')} ${device.name || words(lang, '未命名设备', 'Unnamed device')}`);
        button.setAttribute('aria-busy', String(pending.has(device.id)));
        button.addEventListener('click', async () => {
          if (pending.has(device.id) || !opts.onDisconnect) return;
          pending.add(device.id);
          errors.delete(device.id);
          render();
          try {
            await opts.onDisconnect(device.id, device);
            // Use the latest list when concurrent disconnects settle.
            const current = doc.activeElement;
            const losingFocus = list.contains(current) && current.dataset.deviceId === String(device.id);
            items = items.filter(item => item.id !== device.id);
            render();
            if (losingFocus) (list.querySelector('button:not(:disabled)') || empty).focus();
            announcement.textContent = words(lang, `已断开 ${device.name}`, `Disconnected ${device.name}`);
          } catch {
            errors.add(device.id);
          } finally {
            pending.delete(device.id);
            render();
          }
        });
        row.append(button);
      }
      return row;
    }));
    empty.textContent = items.length ? words(lang, '所有设备均已列出。', 'All connected devices are listed.') :
      words(lang, '还没有设备连上。', 'No devices connected.');
    empty.classList.toggle('kit-sr', items.length > 0);
    if (focusedId !== undefined) {
      const target = Array.from(list.querySelectorAll('button')).find(button => button.dataset.deviceId === focusedId);
      if (target && !target.disabled) target.focus();
    }
  }
  function update(next, nextOptions = {}) { items = [...next]; opts = { ...opts, ...nextOptions }; render(); }
  const api = { update };
  mounted.set(el, api);
  update(devices, options);
  return api;
}
