// Original vanilla DOM helpers. No framework or runtime dependencies.
export const language = lang => lang === 'en' ? 'en' : 'zh';
export const words = (lang, zh, en) => language(lang) === 'en' ? en : zh;

export function node(doc, tag, className, text) {
  const el = doc.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

export function motionOff(el) {
  const doc = el.ownerDocument;
  return doc.documentElement.dataset.motion === 'off' ||
    !!doc.defaultView?.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
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
