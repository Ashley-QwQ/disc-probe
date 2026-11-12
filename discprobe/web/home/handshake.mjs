// This module has no startup side effects, so previews and tests can use the same checks.
let available = null;
export const hasCapability = name => available === null || available.has(name);

export function parseRange(range) {
  if (typeof range !== 'string' || !range.trim()) throw Error('Invalid API range');
  return range.trim().split(/\s+/).map(token => {
    const m = /^(>=|<=|>|<|=)(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?$/.exec(token);
    if (!m) throw Error('Invalid API range');
    return [m[1], Number(m[2]), Number(m[3] || 0)];
  });
}
export function compareAPI(version, range) {
  if (typeof version !== 'string' || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) throw Error('Invalid API version');
  const [major, minor] = version.split('.').map(Number);
  for (const [op, a, b] of parseRange(range)) {
    const cmp = major === a ? Math.sign(minor - b) : Math.sign(major - a);
    if (!({'>=':cmp >= 0, '<=':cmp <= 0, '>':cmp > 0, '<':cmp < 0, '=':cmp === 0}[op])) {
      return cmp < 0 ? 'core' : 'gui';
    }
  }
  return null;
}
export function compatibility(manifest, core) {
  const update = compareAPI(core.api_version, manifest.required_api);
  const caps = new Set(core.capabilities);
  const missing = manifest.required_capabilities.filter(name => !caps.has(name));
  return { update: update || (missing.length ? 'core' : null), missing,
    optional: manifest.optional_capabilities.filter(name => !caps.has(name)) };
}
export function hideOptional(doc, missing) {
  // CSS also covers entry points mounted later by the design page.
  const style = doc.createElement('style');
  style.textContent = missing.map(name => `[data-capability="${name}"]{display:none!important}`).join('\n');
  doc.head.append(style);
  for (const entry of doc.querySelectorAll('[data-capability]')) {
    if (missing.includes(entry.dataset.capability)) entry.hidden = true;
  }
}
export function showSheet(doc, update, missing = []) {
  const zh = doc.documentElement.dataset.lang === 'zh';
  const sheet = doc.createElement('main'); sheet.id = 'gui-compatibility'; sheet.setAttribute('role', 'alert');
  const heading = doc.createElement('h1'), text = doc.createElement('p');
  heading.textContent = zh ? '页面暂时无法打开' : 'This page cannot open yet';
  text.textContent = update === 'core'
    ? (zh ? '请更新 disc-probe 核心，再重新打开页面。' : 'Update the disc-probe core, then reopen this page.')
    : update === 'gui'
      ? (zh ? '请更新 GUI 包，再重新打开页面。' : 'Update the GUI pack, then reopen this page.')
      : (zh ? '无法核对页面与核心版本。请确认本机服务正在运行，再重新打开页面。' : 'Cannot check the GUI and core versions. Check that the local server is running, then reopen this page.');
  sheet.append(heading, text);
  if (missing.length) { const detail = doc.createElement('p'); detail.textContent = (zh ? '缺少能力：' : 'Missing capabilities: ') + missing.join(', '); sheet.append(detail); }
  doc.body.replaceChildren(sheet);
  doc.documentElement.dataset.handshake = 'failed';
}
export async function handshake(doc = document, fetcher = fetch, address = location) {
  // File-based design previews are deliberately standalone; served GUIs always negotiate.
  if (address.protocol === 'file:') { doc.documentElement.dataset.handshake = 'ready'; return; }
  try {
    const token = new URLSearchParams(address.search).get('token');
    const get = async path => {
      const response = await fetcher(path, {headers: token ? {'X-Discprobe-Token':token} : {}, cache:'no-store', signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw Error('Handshake unavailable');
      return response.json();
    };
    const [manifest, core] = await Promise.all([get('/gui.json'), get('/api/version')]);
    const result = compatibility(manifest, core);
    if (result.update) { showSheet(doc, result.update, result.missing); return new Promise(() => {}); }
    available = new Set(core.capabilities);
    hideOptional(doc, result.optional);
    doc.documentElement.dataset.handshake = 'ready';
  } catch {
    showSheet(doc, null);
    return new Promise(() => {});
  }
}
