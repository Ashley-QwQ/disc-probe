// The lamp view's two controls, over the canvas: a dial that turns the disc and a lever that sets the phone's height
// on the placement sheet's ruler (lamp-pose.mjs). Dragging follows the hand: each move sets the value and asks for a
// redraw; the lamp worker answers with quick frames until the hand stops (editor-lamp.mjs). Keys: arrows (Shift: in
// bigger steps), Home resets. Double-click resets too.
import { HEIGHT_MARKS_CM, HEIGHT_RANGE_CM, DESIGN_Z_MM, zOfCm, cmOfZ, snapCm } from "./lamp-pose.mjs";

const WORDS = {
  zh: { rotate: "转盘", height: "高度", design: "设计高度", deg: d => `${d}°`, cm: c => `${c} cm`, rotateAria: "光盘旋转角度", heightAria: "手机镜头离盘面的高度（放置纸上的刻度）", hint: "拖动；方向键微调，Home 复位" },
  en: { rotate: "Turn", height: "Height", design: "design height", deg: d => `${d}°`, cm: c => `${c} cm`, rotateAria: "Disc rotation", heightAria: "Phone lens height above the disc (placement sheet ruler)", hint: "Drag; arrow keys to nudge, Home to reset" },
};
const CSS = `
.lampctl { position: absolute; left: 56px; top: 50%; transform: translateY(-50%); z-index: 3; display: grid; gap: 14px; justify-items: center;
  padding: 12px 10px; border: 1px solid var(--rule); border-radius: 6px; background: color-mix(in srgb, var(--paper) 88%, transparent); color: var(--ink); user-select: none; -webkit-user-select: none; }
.lampctl[hidden] { display: none; }
.lampctl .lc { display: grid; justify-items: center; gap: 4px; outline: none; touch-action: none; cursor: grab; }
.lampctl .lc:active { cursor: grabbing; }
.lampctl .lc:focus-visible svg { outline: 2px solid var(--ink); outline-offset: 2px; border-radius: 4px; }
.lampctl .lbl { font-size: 12px; color: var(--ink-2); }
.lampctl output { font: 500 13px/1.2 var(--mono, monospace); font-variant-numeric: tabular-nums; }
.lampctl svg { display: block; overflow: visible; }
.lampctl .ring { fill: none; stroke: var(--rule-strong); stroke-width: 1.5; }
.lampctl .tick { stroke: var(--ink-2); stroke-width: 1; opacity: .6; }
.lampctl .tick.mark { stroke-width: 1.5; opacity: 1; }
.lampctl .knob { fill: var(--ink); }
.lampctl .stick { stroke: var(--ink); stroke-width: 2.5; stroke-linecap: round; }
.lampctl .tl { font: 10px var(--mono, monospace); fill: var(--ink-2); }
.lampctl .tl.mark { fill: var(--ink); font-weight: 600; }
.lampctl .track { stroke: var(--rule-strong); stroke-width: 4; stroke-linecap: round; }
@media (max-width: 760px) { .lampctl { left: 0; top: auto; bottom: 44px; transform: none; grid-auto-flow: column; gap: 10px; padding: 8px; } }
`;

const DIAL = 30, LEVER = 150;
const yOfCm = cm => LEVER * (1 - (Math.log(cm) - Math.log(HEIGHT_RANGE_CM[0])) / (Math.log(HEIGHT_RANGE_CM[1]) - Math.log(HEIGHT_RANGE_CM[0])));
const cmOfY = y => Math.exp(Math.log(HEIGHT_RANGE_CM[0]) + (1 - y / LEVER) * (Math.log(HEIGHT_RANGE_CM[1]) - Math.log(HEIGHT_RANGE_CM[0])));

// host: { parent, state() -> the design state (its .lampLook is written), lang() -> "zh"|"en", changed() (redraw), z() -> the
// pose's own lens height (mm) when state.lampLook.z is unset, mark(cm) -> true when it made that mark the work's height
// (the colour panel's scene.rig; then state.lampLook.z goes back to null) }
export class LampControls {
  constructor(host) {
    this.h = host;
    if (!document.querySelector("style[data-lampctl]")) { const st = document.createElement("style"); st.dataset.lampctl = ""; st.textContent = CSS; document.head.append(st); }
    const el = this.el = document.createElement("div");
    el.className = "lampctl"; el.hidden = true;
    let ticks = "";
    for (let a = 0; a < 360; a += 30) {
      const r = a * Math.PI / 180, big = a % 90 === 0, r0 = big ? DIAL - 7 : DIAL - 4;
      ticks += `<line class="tick${big ? " mark" : ""}" x1="${(r0 * Math.cos(r)).toFixed(1)}" y1="${(-r0 * Math.sin(r)).toFixed(1)}" x2="${(DIAL * Math.cos(r)).toFixed(1)}" y2="${(-DIAL * Math.sin(r)).toFixed(1)}"/>`;
    }
    let marks = "";
    for (let cm = 15; cm <= 80; cm += 5) if (!HEIGHT_MARKS_CM.includes(cm)) marks += `<line class="tick" x1="-5" x2="5" y1="${yOfCm(cm).toFixed(1)}" y2="${yOfCm(cm).toFixed(1)}"/>`;
    for (const cm of HEIGHT_MARKS_CM) { const y = yOfCm(cm).toFixed(1); marks += `<line class="tick mark" x1="-8" x2="8" y1="${y}" y2="${y}"/><text class="tl${cm === 21 ? " mark" : ""}" x="12" y="${y}" dy="3.5">${cm}</text>`; }
    el.innerHTML =
      `<div class="lc" data-c="rotate" tabindex="0" role="slider" aria-valuemin="0" aria-valuemax="359"><span class="lbl"></span>` +
      `<svg width="${2 * DIAL + 8}" height="${2 * DIAL + 8}" viewBox="${-DIAL - 4} ${-DIAL - 4} ${2 * DIAL + 8} ${2 * DIAL + 8}"><circle class="ring" r="${DIAL}"/>${ticks}<line class="stick" x1="0" y1="0" x2="0" y2="0"/><circle class="knob" r="6"/></svg><output></output></div>` +
      `<div class="lc" data-c="height" tabindex="0" role="slider" aria-valuemin="${HEIGHT_RANGE_CM[0]}" aria-valuemax="${HEIGHT_RANGE_CM[1]}"><span class="lbl"></span>` +
      `<svg width="56" height="${LEVER + 12}" viewBox="-12 -6 56 ${LEVER + 12}"><line class="track" x1="0" x2="0" y1="0" y2="${LEVER}"/>${marks}<circle class="knob" r="7"/></svg><output></output></div>`;
    host.parent.append(el);
    this.dial = el.querySelector('[data-c="rotate"]'); this.lever = el.querySelector('[data-c="height"]');
    for (const c of [this.dial, this.lever]) {
      c.addEventListener("pointerdown", e => this.down(e, c));
      c.addEventListener("pointermove", e => this.move(e, c));
      c.addEventListener("pointerup", e => this.up(e, c));
      c.addEventListener("pointercancel", e => this.up(e, c));
      c.addEventListener("keydown", e => this.key(e, c));
      c.addEventListener("dblclick", () => this.reset(c));
    }
    this.sync();
  }
  get lamp() { const s = this.h.state(); return (s.lampLook ??= { rotate: 0, z: null }); }
  get cm() { const z = this.lamp.z ?? this.h.z?.() ?? DESIGN_Z_MM; return cmOfZ(z); }
  show(on) {
    if (on && this.lang !== this.h.lang()) { this.lang = this.h.lang(); this.sync(); }
    if (this.el.hidden === !on) return;
    this.el.hidden = !on; if (on) this.sync();
  }
  set(c, value) {
    const l = this.lamp;
    if (c === this.dial) l.rotate = Math.round(((value % 360) + 360) % 360 * 10) / 10;
    else l.z = Math.round(zOfCm(value) * 10) / 10;
    this.sync(); this.h.changed();
  }
  reset(c) { if (c === this.dial) this.set(c, 0); else { this.lamp.z = null; this.sync(); this.h.changed(); } }
  at(e, c) {
    const svg = c.querySelector("svg").getBoundingClientRect();
    if (c === this.dial) return Math.atan2(-(e.clientY - svg.top - svg.height / 2), e.clientX - svg.left - svg.width / 2) * 180 / Math.PI;
    return cmOfY(Math.max(0, Math.min(LEVER, (e.clientY - svg.top) * (LEVER + 12) / svg.height - 6)));
  }
  down(e, c) {
    e.preventDefault(); c.focus(); c.setPointerCapture(e.pointerId);
    this.drag = { c, id: e.pointerId, a0: this.at(e, c), v0: c === this.dial ? this.lamp.rotate : this.cm };
    if (c === this.lever) this.set(c, snapCm(this.at(e, c)));
  }
  move(e, c) {
    const d = this.drag;
    if (!d || d.c !== c || d.id !== e.pointerId) return;
    // the dial turns by the angle the pointer went round its centre, so grabbing it anywhere does not make it jump
    if (c === this.dial) { let da = this.at(e, c) - d.a0; da -= 360 * Math.round(da / 360); d.a0 += da; d.v0 += da; this.set(c, d.v0); }
    else this.set(c, snapCm(this.at(e, c), e.shiftKey ? 0 : .8));
  }
  up(e, c) { if (this.drag?.id === e.pointerId) { this.drag = null; if (c === this.lever) this.commit(); } }
  // the lever let go on a mark: that is the work's height (the palettes exist for the marks only); between marks the
  // height stays the lamp view's own
  commit() {
    const cm = Math.round(this.cm * 10) / 10;
    if (HEIGHT_MARKS_CM.includes(cm) && this.lamp.z != null && this.h.mark?.(cm)) { this.lamp.z = null; this.sync(); this.h.changed(); }
  }
  key(e, c) {
    const big = e.shiftKey, k = e.key;
    let v = c === this.dial ? this.lamp.rotate : this.cm;
    if (k === "Home") { e.preventDefault(); this.reset(c); return; }
    const step = c === this.dial ? (big ? 15 : 1) : (big ? 5 : 1), sign = ["ArrowUp", "ArrowRight", "PageUp"].includes(k) ? 1 : ["ArrowDown", "ArrowLeft", "PageDown"].includes(k) ? -1 : 0;
    if (!sign) return;
    e.preventDefault(); e.stopPropagation();
    if (c === this.lever) {
      // to the next whole cm (or 5 cm), stopping at each mark on the way
      const next = sign > 0 ? Math.floor(v / step + 1e-6) * step + step : Math.ceil(v / step - 1e-6) * step - step;
      const mark = HEIGHT_MARKS_CM.find(m => sign > 0 ? m > v + 1e-6 && m < next : m < v - 1e-6 && m > next);
      v = Math.max(HEIGHT_RANGE_CM[0], Math.min(HEIGHT_RANGE_CM[1], mark ?? next));
    } else v += sign * step;
    this.set(c, v);
    if (c === this.lever) this.commit();
  }
  sync() {
    const t = WORDS[this.h.lang()] ?? WORDS.zh, l = this.lamp, rot = l.rotate ?? 0, cm = this.cm;
    const r = rot * Math.PI / 180, kx = (DIAL - 9) * Math.cos(r), ky = -(DIAL - 9) * Math.sin(r);
    const d = this.dial, v = this.lever;
    d.querySelector(".lbl").textContent = t.rotate; v.querySelector(".lbl").textContent = t.height;
    d.querySelector(".knob").setAttribute("cx", kx.toFixed(1)); d.querySelector(".knob").setAttribute("cy", ky.toFixed(1));
    d.querySelector(".stick").setAttribute("x2", kx.toFixed(1)); d.querySelector(".stick").setAttribute("y2", ky.toFixed(1));
    v.querySelector(".knob").setAttribute("cy", yOfCm(Math.max(HEIGHT_RANGE_CM[0], Math.min(HEIGHT_RANGE_CM[1], cm))).toFixed(1));
    const deg = Math.round(rot), cmText = Math.round(cm * 10) / 10, design = Math.abs(cm - 21) < .05;
    d.querySelector("output").textContent = t.deg(deg);
    v.querySelector("output").textContent = t.cm(cmText);
    d.setAttribute("aria-label", t.rotateAria); d.setAttribute("aria-valuenow", String(deg)); d.setAttribute("aria-valuetext", t.deg(deg));
    v.setAttribute("aria-label", t.heightAria); v.setAttribute("aria-valuenow", String(cmText)); v.setAttribute("aria-valuetext", t.cm(cmText) + (design ? ` (${t.design})` : ""));
    this.el.title = t.hint;
  }
}
