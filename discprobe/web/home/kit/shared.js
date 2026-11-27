// Original vanilla DOM helpers. No framework or runtime dependencies.
export const language = lang => lang === 'en' ? 'en' : 'zh';
export const words = (lang, zh, en) => language(lang) === 'en' ? en : zh;

// Safari can deliver compositionend before the confirming Enter keydown.
export const isActionEnter = event => event.key === 'Enter' && !event.isComposing && event.keyCode !== 229;

// Visibility is conjunctive: a foreground tab can still have an off-screen component.
// No layout/paint containment is added, so the existing visual treatment stays intact.
export function observeActivity(element, changed) {
  const doc = element.ownerDocument;
  let intersecting = true, active;
  const update = () => {
    const next = !doc.hidden && intersecting;
    if (next !== active) { active = next; changed(next); }
  };
  const Observer = doc.defaultView?.IntersectionObserver;
  const observer = Observer ? new Observer(entries => {
    intersecting = entries[entries.length - 1].isIntersecting; update();
  }) : null;
  doc.addEventListener('visibilitychange', update);
  observer?.observe(element);
  update();
  return () => { observer?.disconnect(); doc.removeEventListener('visibilitychange', update); };
}

// Decode our embedded project images locally; fetch(data:) would needlessly widen connect-src.
export function dataURLBlob(value) {
  const comma = value.indexOf(','), header = value.slice(5, comma);
  const bytes = /;base64$/i.test(header) ? Uint8Array.from(atob(value.slice(comma + 1)), c => c.charCodeAt(0))
    : new TextEncoder().encode(decodeURIComponent(value.slice(comma + 1)));
  return new Blob([bytes], { type: header.split(';')[0] || 'text/plain' });
}

export function node(doc, tag, className, text) {
  const el = doc.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

export function motionOff(el) {
  const doc = el.ownerDocument;
  return doc.documentElement.dataset.motion === 'off';
}

// Authored line drawings, in a 24 px viewBox; styling lives in kit.css.
export function icon(doc, kind) {
  const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.classList.add('kit-icon');
  const paths = {
    phone: ['M8 2.75h8a1.5 1.5 0 0 1 1.5 1.5v15.5a1.5 1.5 0 0 1-1.5 1.5H8a1.5 1.5 0 0 1-1.5-1.5V4.25A1.5 1.5 0 0 1 8 2.75Z', 'M10 18.5h4'],
    computer: ['M3 4.5h18v12H3Z', 'M12 16.5v4M8 20.5h8'],
    tick: ['m5 12 4.5 4.5L19 7'],
    arrow: ['M6 12h12m-5-5 5 5-5 5'],
  };
  for (const [i, d] of (paths[kind] || paths.computer).entries()) {
    const path = doc.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', d);
    if (i) path.classList.add('kit-icon-detail');
    svg.append(path);
  }
  return svg;
}
