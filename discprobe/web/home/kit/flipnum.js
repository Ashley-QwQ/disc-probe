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

  function set(text) {
    text = String(text);
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
  const observer = new doc.defaultView.MutationObserver(() => set(value));
  observer.observe(doc.documentElement, { attributes: true, attributeFilter: ['data-motion'] });
  const media = doc.defaultView.matchMedia?.('(prefers-reduced-motion: reduce)');
  const refreshMotion = () => set(value);
  media?.addEventListener('change', refreshMotion);
  const api = { set, destroy() {
    observer.disconnect(); media?.removeEventListener('change', refreshMotion); mounted.delete(el);
  } };
  mounted.set(el, api);
  set(value);
  return api;
}
