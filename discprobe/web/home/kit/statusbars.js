// after ObsidianUI status-bars, MIT. See LICENSE.obsidianui.txt.
// Event strip, keyboard navigation and date tooltip adapted for vanilla DOM.
import { language, node, words } from './shared.js';

export const statusState = state => ['ok', 'needs', 'unknown'].includes(state) ? state : 'unknown';
export function statusSummary(items, lang = 'zh') {
  const needs = items.filter(item => statusState(item.state) === 'needs').length;
  return words(lang, `${items.length} 次，${needs} 次要看`,
    `${items.length} ${items.length === 1 ? 'event' : 'events'}, ${needs} ${needs === 1 ? 'needs' : 'need'} attention`);
}
export function statusDate(when, lang = 'zh') {
  if (when === null || when === undefined || when === '') return words(lang, '日期未知', 'Date unknown');
  const date = new Date(when);
  if (!Number.isFinite(date.getTime())) return words(lang, '日期未知', 'Date unknown');
  // ISO calendar dates stay on that day, regardless of the viewer's time zone.
  const dateOnly = typeof when === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(when);
  return new Intl.DateTimeFormat(language(lang) === 'en' ? 'en-CA' : 'zh-CN', {
    dateStyle: 'medium', ...(dateOnly ? { timeZone: 'UTC' } : { timeStyle: 'short' }),
  }).format(date);
}

let uid = 0;
const mounted = new WeakMap();
export function statusBars(el, items = [], options = {}) {
  if (mounted.has(el)) {
    const api = mounted.get(el);
    api.update(items, options);
    return api;
  }
  const doc = el.ownerDocument;
  const summary = node(doc, 'p', 'kit-status-summary');
  summary.setAttribute('role', 'status');
  const strip = node(doc, 'div', 'kit-status-strip');
  strip.setAttribute('role', 'group');
  const tip = node(doc, 'div', 'kit-status-tip');
  tip.id = `kit-status-tip-${++uid}`;
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  el.classList.add('kit-status');
  el.replaceChildren(summary, strip, tip);
  let lang = 'zh';
  let buttons = [];
  let hovered = null;
  let focused = null;
  let dismissed = false;
  function show() {
    const button = hovered || focused;
    tip.hidden = !button || dismissed;
    if (tip.hidden) return;
    tip.textContent = button.getAttribute('aria-label');
    // Align to the event, clamping the tooltip inside the component.
    const x = button.offsetLeft + button.offsetWidth / 2 - tip.offsetWidth / 2;
    tip.style.left = `${Math.max(0, Math.min(el.clientWidth - tip.offsetWidth, x))}px`;
  }
  tip.addEventListener('pointerleave', () => { hovered = null; show(); });
  el.addEventListener('keydown', event => {
    if (event.key === 'Escape') { dismissed = true; tip.hidden = true; return; }
    const index = buttons.indexOf(doc.activeElement);
    if (index < 0) return;
    const to = { ArrowLeft: Math.max(0, index - 1), ArrowRight: Math.min(buttons.length - 1, index + 1),
      Home: 0, End: buttons.length - 1 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    buttons[to].focus();
  });
  function update(next, opts = {}) {
    lang = language(opts.lang ?? lang);
    const activeIndex = buttons.indexOf(doc.activeElement);
    hovered = focused = null;
    tip.hidden = true;
    summary.textContent = statusSummary(next, lang);
    strip.setAttribute('aria-label', summary.textContent);
    el.lang = lang === 'en' ? 'en' : 'zh-CN';
    buttons = next.map(item => {
      const state = statusState(item.state);
      const stateWord = { ok: words(lang, '正常', 'OK'), needs: words(lang, '要看', 'Needs attention'),
        unknown: words(lang, '不知道', 'Unknown') }[state];
      const button = node(doc, 'button', 'kit-status-event');
      button.type = 'button';
      button.dataset.state = state;
      button.setAttribute('aria-label', `${item.label || stateWord} · ${statusDate(item.when, lang)} · ${stateWord}`);
      button.setAttribute('aria-describedby', tip.id);
      const bar = node(doc, 'span', 'kit-status-bar');
      bar.setAttribute('aria-hidden', 'true');
      button.append(bar);
      button.addEventListener('pointerenter', () => { hovered = button; dismissed = false; show(); });
      button.addEventListener('pointerleave', event => {
        if (event.relatedTarget === tip || tip.contains(event.relatedTarget)) return;
        hovered = null; show();
      });
      button.addEventListener('focus', () => { focused = button; dismissed = false; show(); });
      button.addEventListener('blur', () => { focused = null; show(); });
      button.addEventListener('click', () => { dismissed = false; focused = button; show(); });
      return button;
    });
    strip.replaceChildren(...buttons);
    if (activeIndex >= 0 && buttons.length) buttons[Math.min(activeIndex, buttons.length - 1)].focus();
    else if (activeIndex >= 0) { summary.tabIndex = -1; summary.focus(); }
  }
  const api = { update };
  mounted.set(el, api);
  update(items, options);
  return api;
}
