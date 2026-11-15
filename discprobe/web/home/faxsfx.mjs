// The news fax's sounds, made on the spot with Web Audio (no files): the dial keys (DTMF pairs), the ring
// while the paper is on its way, the busy tone when the line is dead, the short whistle of the connection, the
// printer, and the bell when a parcel arrives. They follow the home page's mute switch (M) and stay quiet until
// the person has used the page, like sfx.js. Every sound has words on the page next to it.

import { allowed } from "./sfx.js";

const VOLUME = 0.12;
let ctx = null;
const audio = () => {
  if (!allowed()) return null;
  try {
    ctx ??= new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  } catch { return null; }
};
// one or two sine tones from t0 for dur seconds, with short ramps so nothing clicks
function tone(freqs, t0, dur, gain = 1, type = "sine") {
  const c = audio(); if (!c) return () => {};
  const g = c.createGain(), at = c.currentTime + t0;
  g.gain.setValueAtTime(0, at);
  g.gain.linearRampToValueAtTime(VOLUME * gain / freqs.length, at + 0.012);
  g.gain.setValueAtTime(VOLUME * gain / freqs.length, at + Math.max(0.013, dur - 0.02));
  g.gain.linearRampToValueAtTime(0, at + dur);
  g.connect(c.destination);
  const oscs = freqs.map((f) => { const o = c.createOscillator(); o.type = type; o.frequency.value = f; o.connect(g); o.start(at); o.stop(at + dur + 0.02); return o; });
  return () => { try { const now = c.currentTime; g.gain.cancelScheduledValues(now); g.gain.setValueAtTime(0, now); oscs.forEach((o) => o.stop(now + 0.01)); } catch {} };
}
const DTMF_ROW = { 1: 697, 2: 697, 3: 697, 4: 770, 5: 770, 6: 770, 7: 852, 8: 852, 9: 852, "*": 941, 0: 941, "#": 941 };
const DTMF_COL = { 1: 1209, 4: 1209, 7: 1209, "*": 1209, 2: 1336, 5: 1336, 8: 1336, 0: 1336, 3: 1477, 6: 1477, 9: 1477, "#": 1477 };
export const key = (k) => { if (DTMF_ROW[k]) tone([DTMF_ROW[k], DTMF_COL[k]], 0, 0.11, 0.9); };
// the ring back tone (440 + 480 Hz, 0.9 s on, 1.4 s off) until stop() is called
export function ring() {
  let stopped = false, cut = () => {}, timer = 0;
  const once = () => { if (stopped) return; cut = tone([440, 480], 0, 0.9, 0.7); timer = setTimeout(once, 2300); };
  once();
  return () => { stopped = true; clearTimeout(timer); cut(); };
}
// the line answered: two short fax whistles
export const connect = () => { tone([1100], 0, 0.22, 0.55); tone([2100], 0.3, 0.32, 0.45); };
// nobody there: three short busy beeps
export const busy = () => { for (let i = 0; i < 3; i++) tone([480, 620], i * 0.5, 0.25, 0.7); };
// the thermal printer: quick soft ticks over dur seconds
export function print(dur) {
  const c = audio(); if (!c) return;
  for (let t = 0; t < dur; t += 0.085) tone([180 + 40 * Math.sin(t * 9)], t, 0.03, 0.35, "square");
}
// a desk bell: a struck partial series that decays
export function bell() {
  const c = audio(); if (!c) return;
  const at = c.currentTime;
  for (const [f, a, d] of [[1318, 1, 1.6], [2637, .45, .9], [3951, .2, .5], [1976, .25, 1.1]]) {
    const o = c.createOscillator(), g = c.createGain();
    o.frequency.value = f; o.connect(g); g.connect(c.destination);
    g.gain.setValueAtTime(0, at); g.gain.linearRampToValueAtTime(VOLUME * a, at + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, at + d);
    o.start(at); o.stop(at + d + 0.05);
  }
}
