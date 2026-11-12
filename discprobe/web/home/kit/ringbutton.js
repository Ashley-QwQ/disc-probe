// Original implementation. Behaviour reference: Rewamp NeumorphicDownloadButtonShowcase.
// No Rewamp code or CSS copied. The supplied button and its label remain usable.
import { icon, language, node, words } from './shared.js';

export function clampProgress(value) {
  if (value === null) return null;
  if (typeof value !== 'number' || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

const mounted = new WeakMap();
let uid = 0;
export function ringButton(btn, { lang = 'zh' } = {}) {
  if (mounted.has(btn)) return mounted.get(btn);
  lang = language(lang);
  const doc = btn.ownerDocument;
  const originalBusy = btn.getAttribute('aria-busy');
  const originalDescription = btn.getAttribute('aria-describedby');
  const badge = node(doc, 'span', 'kit-ring-badge');
  const meter = node(doc, 'span', 'kit-ring-meter');
  // Native buttons can flatten descendant semantics. Expose progress via the
  // button's explicit description rather than a progressbar nested inside it.
  meter.setAttribute('aria-hidden', 'true');
  const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  for (const name of ['kit-ring-track', 'kit-ring-fill']) {
    const circle = doc.createElementNS(svg.namespaceURI, 'circle');
    circle.setAttribute('cx', '12'); circle.setAttribute('cy', '12'); circle.setAttribute('r', '9');
    circle.setAttribute('pathLength', '100'); circle.classList.add(name); svg.append(circle);
  }
  const fill = svg.lastChild;
  meter.append(svg);
  const tick = icon(doc, 'tick');
  badge.append(meter, tick);
  const label = node(doc, 'span', 'kit-ring-label');
  label.append(...Array.from(btn.childNodes));
  const status = node(doc, 'span', 'kit-sr');
  status.setAttribute('role', 'status');
  const description = node(doc, 'span', 'kit-sr');
  description.id = `kit-ring-description-${++uid}`;
  btn.classList.add('kit-ring-button');
  btn.lang = lang === 'en' ? 'en' : 'zh-CN';
  btn.append(badge, label, status, description);
  function describe(text) {
    description.textContent = text;
    btn.setAttribute('aria-describedby', [originalDescription, description.id].filter(Boolean).join(' '));
  }
  function restoreBusy() {
    if (originalBusy === null) btn.removeAttribute('aria-busy');
    else btn.setAttribute('aria-busy', originalBusy);
  }
  const api = {
    progress(value) {
      const p = clampProgress(value);
      badge.hidden = false; meter.hidden = false; tick.hidden = true;
      btn.dataset.kitProgress = p === null ? 'indeterminate' : 'determinate';
      btn.setAttribute('aria-busy', 'true');
      if (p === null) {
        describe(words(lang, '正在处理，进度未知', 'Working, progress unknown'));
        fill.style.strokeDashoffset = '75';
      } else {
        describe(words(lang, `进度 ${Math.round(p * 100)}%`, `Progress ${Math.round(p * 100)}%`));
        fill.style.strokeDashoffset = String(100 * (1 - p));
      }
      status.textContent = '';
    },
    done() {
      badge.hidden = false; meter.hidden = true; tick.hidden = false;
      btn.dataset.kitProgress = 'done'; restoreBusy();
      status.textContent = words(lang, '已完成', 'Complete');
      describe(status.textContent);
    },
    reset() {
      badge.hidden = true; tick.hidden = true; meter.hidden = true;
      delete btn.dataset.kitProgress; restoreBusy(); status.textContent = '';
      description.textContent = '';
      if (originalDescription === null) btn.removeAttribute('aria-describedby');
      else btn.setAttribute('aria-describedby', originalDescription);
    },
  };
  mounted.set(btn, api);
  api.reset();
  return api;
}
