// Short sounds for what happens while the person may be looking elsewhere: a step of a long job begins,
// everything is done, something needs them. The user's choice (sfx/README.md):
//   step(i)    the steps of a job in turn (0..3; later steps are quiet)
//   done()     all done: a calibration saved, a burn written and read back cleanly
//   problem()  something they can recover from (two sounds, taken in turn)
//   failure()  a real failure (a burn that wrote part of a disc and stopped)
// On by default, quiet, and only after the person has used the page (browsers refuse sound before that,
// and a page that plays on its own startles). The mute switch is the home page's (M), kept per browser.
// Sound is only ever a second channel: every sound has words on the page next to it.

const KEY = "dp-sound", VOLUME = 0.3;
const url = (name) => new URL(`./sfx/${name}.mp3`, import.meta.url).href;
let used = false, flip = false, memory = null;   // memory: the switch, when storage is unavailable
const cache = new Map();
for (const ev of ["pointerdown", "keydown"]) addEventListener(ev, () => { used = true; }, { capture: true, once: true });

export function soundOn() {
  try { return localStorage.getItem(KEY) !== "off"; } catch { return true; }
}
export function setSound(on) {
  try { localStorage.setItem(KEY, on ? "on" : "off"); } catch { /* private window: this page only */ }
  memory = on;
  dispatchEvent(new CustomEvent("dp-sound", { detail: on }));
}
const enabled = () => memory ?? soundOn();

function play(name) {
  if (!used || !enabled()) return;
  try {
    let a = cache.get(name);
    if (!a) { a = new Audio(url(name)); a.preload = "auto"; cache.set(name, a); }
    a.volume = VOLUME;
    a.currentTime = 0;
    a.play()?.catch?.(() => {});
  } catch { /* no audio here: the words on the page still say it */ }
}
// four rising notes; a fifth step and beyond stay quiet rather than repeat one (done() is the last note)
export const step = (i) => { if ((i | 0) <= 3) play(`step-${Math.max(0, i | 0)}`); };
export const done = () => play("step-4");
export const problem = () => { flip = !flip; play(flip ? "error-a" : "error-b"); };
export const failure = () => play("error-long");
