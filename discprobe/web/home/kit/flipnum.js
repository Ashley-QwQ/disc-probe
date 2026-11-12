// after ObsidianUI flip-text / text-stream, MIT. See LICENSE.obsidianui.txt.
// Per-character windows and vertical movement adapted as a new numeric updater.
import { motionOff, node } from './shared.js';

/** Pure roll plan. Numeric runs are right aligned; each run has its own direction. */
export function characterChanges(before, after) {
  const old = Array.from(String(before));
  const next = Array.from(String(after));
  const a = String(before).match(/\d+|\D+/gu) || [];
  const b = String(after).match(/\d+|\D+/gu) || [];
  const plan = [];
  let offset = 0;
  if (a.length === b.length && a.every((part, i) => /^\d/.test(part) === /^\d/.test(b[i]))) {
    b.forEach((part, i) => {
      const prev = Array.from(a[i]);
      const chars = Array.from(part);
      const numeric = /^\d/.test(part);
      const direction = numeric && BigInt(part) < BigInt(a[i]) ? 'down' : 'up';
      chars.forEach((to, j) => {
        const index = numeric ? j + prev.length - chars.length : j;
        const from = index >= 0 ? prev[index] : undefined;
        plan.push({ from, to, changed: from !== to, direction: from === to ? null : direction,
          previousIndex: from === undefined ? -1 : offset + index });
      });
      offset += prev.length;
    });
    return plan;
  }
  let prefix = 0, suffix = 0;
  while (prefix < old.length && prefix < next.length && old[prefix] === next[prefix]) prefix++;
  while (suffix < old.length - prefix && suffix < next.length - prefix &&
         old[old.length - 1 - suffix] === next[next.length - 1 - suffix]) suffix++;
  return next.map((to, i) => {
    const index = i < prefix ? i : i >= next.length - suffix ? old.length - next.length + i :
      (i < old.length - suffix ? i : -1);
    const from = old[index];
    return { from, to, changed: from !== to, direction: from === to ? null : 'up', previousIndex: index };
  });
}

const mounted = new WeakMap();
/** Observe ordinary textContent assignments; internal renders are disconnected. */
export function flipWatch(el, options = {}) {
  const number = flipNumber(el, options);
  number.watch();
  return number;
}
// Read the supplied value, excluding animated old glyphs and the duplicate visual layer.
export function flipValue(el) {
  return el.querySelector('.kit-sr')?.textContent ?? el.textContent;
}
export function flipNumber(el, { lang = 'zh' } = {}) {
  if (mounted.has(el)) return mounted.get(el);
  const doc = el.ownerDocument;
  let value = el.textContent || '';
  let cells = [];
  const visual = node(doc, 'span', 'kit-flip-visual');
  visual.setAttribute('aria-hidden', 'true');
  const readable = node(doc, 'span', 'kit-sr');
  el.classList.add('kit-flip');
  el.lang = lang === 'en' ? 'en' : 'zh-CN';
  el.setAttribute('aria-live', 'polite');
  el.setAttribute('aria-atomic', 'true');

  let textObserver = null;
  const observeText = () => textObserver?.observe(el, { childList: true, characterData: true, subtree: true });
  function set(text) {
    textObserver?.disconnect();
    try { render(text); } finally { observeText(); }
  }
  function render(text) {
    text = String(text);
    el.dataset.flipValue = text;
    if (motionOff(el)) {
      el.textContent = text;
      value = text;
      cells = [];
      return;
    }
    if (el.firstChild !== visual) {
      visual.replaceChildren();
      el.replaceChildren(visual, readable);
    }
    const oldCells = cells;
    cells = characterChanges(value, text).map(change => {
      const existing = oldCells[change.previousIndex];
      if (!change.changed && existing) return existing;
      const cell = node(doc, 'span', 'kit-flip-cell');
      const current = node(doc, 'span', 'kit-flip-current', change.to);
      cell.append(current);
      if (change.changed && change.from !== undefined && current.animate) {
        const previous = node(doc, 'span', 'kit-flip-previous', change.from);
        cell.append(previous);
        const sign = change.direction === 'down' ? -1 : 1;
        const timing = { duration: 240, easing: 'cubic-bezier(.2,.8,.2,1)' };
        current.animate([{ transform: `translateY(${sign * 100}%)` }, { transform: 'translateY(0)' }], timing);
        const exit = previous.animate([{ transform: 'translateY(0)' }, { transform: `translateY(${-sign * 100}%)` }], timing);
        exit.onfinish = () => previous.remove();
        exit.oncancel = () => previous.remove();
      }
      return cell;
    });
    // Moving an unchanged node retains its active animation and its identity.
    visual.replaceChildren(...cells);
    readable.textContent = text;
    value = text;
  }
  function refreshMotion() {
    const pending = textObserver?.takeRecords() || [];
    const external = pending.some(r => r.target === el || !visual.contains(r.target));
    set(external ? flipValue(el) : value);
  }
  const observer = new doc.defaultView.MutationObserver(refreshMotion);
  observer.observe(doc.documentElement, { attributes: true, attributeFilter: ['data-motion'] });
  const media = doc.defaultView.matchMedia?.('(prefers-reduced-motion: reduce)');
  media?.addEventListener('change', refreshMotion);
  const api = { set, watch() {
    if (textObserver) return;
    textObserver = new doc.defaultView.MutationObserver(records => {
      // Animation cleanup inside the visual layer is not an external value change.
      if (records.some(r => r.target === el || !visual.contains(r.target))) {
        set(el.firstChild === visual ? readable.textContent : el.textContent);
      }
    });
    observeText();
  }, destroy() {
    textObserver?.disconnect();
    observer.disconnect(); media?.removeEventListener('change', refreshMotion); mounted.delete(el);
  } };
  mounted.set(el, api);
  set(value);
  return api;
}
