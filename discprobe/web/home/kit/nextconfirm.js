// Put the kit's deliberate confirmation in the shared Next area for one step.
import { slideConfirm } from './slideconfirm.js';
const mounted = new WeakMap();
export function nextConfirm(button, { active = false, disabled = false, lang = 'zh', done } = {}) {
  let current = mounted.get(button);
  if (!active || current?.lang !== lang) {
    if (current) { current.slider.destroy(); current.host.remove(); mounted.delete(button); }
    current = null;
    button.hidden = false;
  }
  if (!active) return;
  if (!current) {
    const host = button.ownerDocument.createElement('div');
    host.className = 'next-confirm';
    host.setAttribute('aria-describedby', 'next-why');
    button.after(host);
    current = { host, lang, done };
    current.slider = slideConfirm(host, { lang, disabled,
      label: lang === 'en' ? 'Slide to burn' : '滑动确认刻录', done: () => current.done?.() });
    mounted.set(button, current);
  }
  current.done = done;
  current.slider.setDisabled(disabled);
  button.hidden = true;
}
