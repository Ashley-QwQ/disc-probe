// Original implementation. Behaviour reference: Rewamp SlideToConfirmButtonShowcase.
// No Rewamp code or CSS copied; the deliberate drag/hold is specified by our task card.
import { icon, language, node, words } from './shared.js';

export const HOLD_MS = 1000;
export function slideProgress(distance, travel) {
  if (!Number.isFinite(distance) || !Number.isFinite(travel) || travel <= 0) return 0;
  return Math.min(1, Math.max(0, distance / travel));
}
export const slideThreshold = (distance, travel) => slideProgress(distance, travel) === 1;
export const initialHold = () => ({ phase: 'idle', started: null, key: null, progress: 0 });

/** A repeated keydown never restarts or completes the clock. Only elapsed hold time does. */
export function keyboardReducer(state, action) {
  if (action.type === 'reset') return initialHold();
  if (action.type === 'disable') return { ...initialHold(), phase: 'disabled' };
  if (state.phase === 'disabled' || state.phase === 'confirmed') return state;
  if (action.type === 'cancel' || (action.type === 'down' && action.key === 'Escape')) return initialHold();
  if (action.type === 'down' && ['ArrowRight', 'End'].includes(action.key)) {
    if (state.phase !== 'idle' || action.repeat || !Number.isFinite(action.now)) return state;
    return { phase: 'holding', started: action.now, key: action.key, progress: 0 };
  }
  if (action.type === 'tick' && state.phase === 'holding' && Number.isFinite(action.now)) {
    const progress = slideProgress(action.now - state.started, HOLD_MS);
    return { ...state, progress, phase: progress === 1 ? 'confirmed' : 'holding' };
  }
  if (action.type === 'up' && action.key === state.key) return initialHold();
  return state;
}

const mounted = new WeakMap();
let uid = 0;
export function slideConfirm(el, { label, done = () => {}, lang = 'zh', disabled = false } = {}) {
  mounted.get(el)?.destroy();
  lang = language(lang);
  const doc = el.ownerDocument, win = doc.defaultView;
  const controller = new win.AbortController();
  const signal = controller.signal;
  const track = node(doc, 'div', 'kit-slide-track');
  const caption = node(doc, 'span', 'kit-slide-label', label || words(lang, '滑动确认', 'Slide to confirm'));
  const knob = node(doc, 'span', 'kit-slide-knob');
  knob.tabIndex = 0;
  knob.setAttribute('role', 'slider');
  knob.setAttribute('aria-label', caption.textContent);
  knob.setAttribute('aria-valuemin', '0');
  knob.setAttribute('aria-valuemax', '100');
  knob.setAttribute('aria-orientation', 'horizontal');
  knob.append(icon(doc, 'arrow'));
  const help = node(doc, 'p', 'kit-slide-help', words(lang,
    '拖到最右端后松开，或聚焦后按住 → / End 1 秒。',
    'Drag to the end and release, or focus and hold Right / End for 1 second.'));
  help.id = `kit-slide-help-${++uid}`;
  knob.setAttribute('aria-describedby', help.id);
  const announcement = node(doc, 'span', 'kit-sr');
  announcement.setAttribute('role', 'status');
  el.classList.add('kit-slide');
  el.lang = lang === 'en' ? 'en' : 'zh-CN';
  track.append(caption, knob);
  el.replaceChildren(track, help, announcement);
  let state = initialHold(), pointer = null, frame = 0, confirmed = false;
  let startX = 0, travel = 0, p = 0, disposed = false;
  const isDisabled = () => disabled || el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';
  function paint(progress, dragging = false) {
    p = progress;
    const available = Math.max(0, track.clientWidth - knob.offsetWidth - 8);
    knob.style.transform = `translateX(${progress * available}px)`;
    track.dataset.dragging = String(dragging);
    knob.setAttribute('aria-valuenow', String(Math.round(progress * 100)));
    knob.setAttribute('aria-valuetext', confirmed ? words(lang, '已确认', 'Confirmed') : `${Math.round(progress * 100)}%`);
  }
  function stop() {
    win.cancelAnimationFrame(frame);
    frame = 0;
    const captured = pointer;
    pointer = null;
    if (captured !== null && knob.hasPointerCapture?.(captured)) knob.releasePointerCapture(captured);
  }
  function cancel() {
    stop();
    if (confirmed) return;
    state = isDisabled() ? keyboardReducer(state, { type: 'disable' }) : initialHold();
    paint(0);
  }
  function syncDisabled() {
    const off = isDisabled();
    knob.setAttribute('aria-disabled', String(off || confirmed));
    knob.tabIndex = off ? -1 : 0;
    track.dataset.disabled = String(off);
    if (off) cancel();
    else if (!confirmed && state.phase === 'disabled') state = initialHold();
  }
  function confirm() {
    if (confirmed || disposed || isDisabled()) return cancel();
    confirmed = true;
    stop();
    state = { ...initialHold(), phase: 'confirmed', progress: 1 };
    caption.textContent = words(lang, '已确认', 'Confirmed');
    knob.replaceChildren(icon(doc, 'tick'));
    track.dataset.confirmed = 'true';
    announcement.textContent = caption.textContent;
    paint(1);
    syncDisabled();
    done();
  }
  function tick(now) {
    if (disposed || isDisabled() || doc.hidden || doc.activeElement !== knob) return cancel();
    state = keyboardReducer(state, { type: 'tick', now });
    paint(state.progress, true);
    if (state.phase === 'confirmed') confirm();
    else if (state.phase === 'holding') frame = win.requestAnimationFrame(tick);
  }
  knob.addEventListener('keydown', event => {
    if (isDisabled() || confirmed || pointer !== null) return;
    if (['ArrowRight', 'End', 'Enter', ' ', 'Escape'].includes(event.key)) event.preventDefault();
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return cancel();
    const previous = state;
    state = keyboardReducer(state, { type: 'down', key: event.key, repeat: event.repeat, now: win.performance.now() });
    if (state.phase === 'idle') cancel();
    else if (state.phase === 'holding' && previous.phase !== 'holding') frame = win.requestAnimationFrame(tick);
  }, { signal });
  knob.addEventListener('keyup', event => {
    state = keyboardReducer(state, { type: 'up', key: event.key });
    if (!confirmed && state.phase === 'idle') cancel();
  }, { signal });
  knob.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !event.isPrimary || isDisabled() || confirmed || pointer !== null) return;
    event.preventDefault();
    cancel();
    knob.focus();
    startX = event.clientX;
    travel = Math.max(0, track.clientWidth - knob.offsetWidth - 8);
    pointer = event.pointerId;
    knob.setPointerCapture(pointer);
    paint(0, true);
  }, { signal });
  knob.addEventListener('pointermove', event => {
    if (event.pointerId !== pointer) return;
    if (isDisabled()) return cancel();
    paint(slideProgress(event.clientX - startX, travel), true);
  }, { signal });
  knob.addEventListener('pointerup', event => {
    if (event.pointerId !== pointer) return;
    if (!isDisabled() && slideThreshold(event.clientX - startX, travel)) confirm();
    else cancel();
  }, { signal });
  knob.addEventListener('pointercancel', cancel, { signal });
  knob.addEventListener('lostpointercapture', () => { if (pointer !== null) cancel(); }, { signal });
  knob.addEventListener('blur', cancel, { signal });
  win.addEventListener('blur', cancel, { signal });
  win.addEventListener('resize', () => { if (!confirmed) cancel(); else paint(1); }, { signal });
  doc.addEventListener('visibilitychange', () => { if (doc.hidden) cancel(); }, { signal });
  const observer = new win.MutationObserver(syncDisabled);
  observer.observe(el, { attributes: true, attributeFilter: ['disabled', 'aria-disabled'] });
  const api = {
    setDisabled(value) { disabled = !!value; syncDisabled(); },
    reset() {
      cancel(); confirmed = false; state = initialHold();
      caption.textContent = label || words(lang, '滑动确认', 'Slide to confirm');
      knob.replaceChildren(icon(doc, 'arrow')); delete track.dataset.confirmed;
      announcement.textContent = ''; paint(0); syncDisabled();
    },
    destroy() { disposed = true; stop(); observer.disconnect(); controller.abort(); mounted.delete(el); },
  };
  mounted.set(el, api);
  paint(p); syncDisabled();
  return api;
}
