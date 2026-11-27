import { flipNumber } from "./kit/flipnum.js";
// The calibration page's stage: the burner seen straight down with its top shell see-through (caltop/,
// rendered by caltop/render_caltop.py), the disc as the main character. The page draws on the disc what is
// happening: a band for writing progress and one coloured ring per measured radius, a thin pointer from
// the centre to the head with its radius, a copper band where
// reading stopped, a dashed place when there is no disc. A big percent and the time left sit lower left.
//
//   const st = await stage(api); st.show(true); st.set({ disc, read, readRadii, head, headKnown, band, percent, left, busy });
//     disc: "in" | "none" | "blank"     read: [r0, r1] mm written (rainbow), or null
//     readRadii: measured radii in mm from the geometry events
//     head: mm of the head (pointer), or null; headKnown false: the pointer without a number
//     band: [r0, r1] mm where it stopped (copper), or null        busy: the drive is working (shell a touch darker)
//     percent: 0..100 or null; left: words for the time left
// Nothing here talks to the drive; it only draws what the page tells it.

const ORDER = ["shadow", "bg", "sled", "mid", "disc", "glow", "over", "occluders", "lid"];
const BASE = new URL("./caltop/", import.meta.url);
let meta = null, el = null, state = {}, api = null;
let art, g, sled, glow, label, big, percent, time, percentFlip, timeFlip, rainbow;
let frame = 0, shownHead = null, headMove = null, artScale = 1, ink, paper, copper;
let rings = new Map();
let listeners, observer;
const motionMs = 400;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

// the colour of the radius the head is at: the same OKLCH rainbow as the rest of the page (calibrate.js, ui.py)
function oklch(l, c, hDeg) {
  const h = (hDeg * Math.PI) / 180, a = c * Math.cos(h), b = c * Math.sin(h);
  const L = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3, M = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3, S = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S, -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S, -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S];
  return "#" + lin.map((v) => Math.round(Math.min(1, v <= 0 ? 0 : v < 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055) * 255).toString(16).padStart(2, "0")).join("");
}
const rainbowAt = (mm) => oklch(0.72, 0.12, 262 - Math.min(1, Math.max(0, (mm - 24) / 34)) * 237);
function theme() { return document.documentElement.dataset.theme === "dark" ? "dark" : "paper"; }

function build() {
  el = document.createElement("div");
  el.className = "cal-stage";
  el.hidden = true;
  const [W, H] = meta.image_size;
  // the picture has room for the shadow on its left and below: centre the drive itself, the shadow spills over
  const [bx0, by0, bx1, by1] = meta.body_px || [0, 0, W, H];
  const shift = `translate:${((W / 2 - (bx0 + bx1) / 2) / W * 100).toFixed(2)}% ${((H / 2 - (by0 + by1) / 2) / H * 100).toFixed(2)}%`;
  el.innerHTML = `<div class="cs-art" style="--cs-aspect:${W / H};aspect-ratio:${W}/${H};${shift}">` +
    ORDER.map((k) => k === "over" ? `<canvas class="cs-over" width="${W}" height="${H}"></canvas>` : `<img class="cs-${k}" alt="" draggable="false">`).join("") +
    // the disc turning while the drive works: one grey arc near the rim going round (designer: "光驱正忙")
    `<svg class="cs-spin" viewBox="0 0 ${W} ${H}" aria-hidden="true" style="--spin-o:${(meta.disc.centre_px[0] / W * 100).toFixed(2)}% ${(meta.disc.centre_px[1] / H * 100).toFixed(2)}%"><path d="${spinArc()}"/></svg>` +
    `<span class="cs-label" hidden></span></div>` +
    `<p class="cs-big" hidden><b></b><span></span></p>`;
  document.body.append(el);
  [art, sled, glow, label, big] = ["art", "sled", "glow", "label", "big"].map(name => el.querySelector(`.cs-${name}`));
  g = el.querySelector(".cs-over").getContext("2d");
  const [cx, cy] = meta.disc.centre_px, outer = 60;
  rainbow = g.createRadialGradient(cx, cy, 0, cx, cy, outer * meta.scale.px_per_mm);
  for (let mm = 0; mm <= outer; mm += 0.5) rainbow.addColorStop(mm / outer, rainbowAt(mm));
  percent = big.querySelector("b");
  time = big.querySelector("span");
  percentFlip = flipNumber(percent, {lang:api.lang()});
  timeFlip = flipNumber(time, {lang:api.lang(), live:false});
  listeners = new AbortController();
  addEventListener("dp-theme", paintArt, { signal: listeners.signal });
  const motionChanged = () => { if (motionOff() && frame) settleMotion(); };
  observer = new MutationObserver(records => {
    if (records.some(record => record.attributeName === "data-theme")) paintArt();
    motionChanged();
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-motion"] });
  reducedMotion.addEventListener("change", motionChanged, { signal: listeners.signal });
  paintArt();
}
function spinArc() {
  const [cx, cy] = meta.disc.centre_px, r = 56.5 * meta.scale.px_per_mm, a0 = -Math.PI / 2, a1 = a0 + Math.PI * 40 / 180;
  const pt = (a) => `${(cx + r * Math.cos(a)).toFixed(1)} ${(cy + r * Math.sin(a)).toFixed(1)}`;
  return `M ${pt(a0)} A ${r.toFixed(1)} ${r.toFixed(1)} 0 0 1 ${pt(a1)}`;
}
function paintArt() {
  if (!el) return;
  [ink, paper, copper] = ["--ink", "--paper", "--copper"].map(cssVar);
  const v = theme();
  for (const k of ORDER) {
    if (k === "over") continue;
    const img = el.querySelector(`.cs-${k}`), src = new URL(`${k}_${v}.webp`, BASE).href;
    if (img.dataset.src !== src) { img.src = src; img.dataset.src = src; }
  }
  draw();
}

function draw(now = performance.now()) {
  if (!el || el.hidden) return;
  const s = state, [W, H] = meta.image_size;
  const [cx, cy] = meta.disc.centre_px, pxmm = meta.scale.px_per_mm, R = (mm) => mm * pxmm;
  art.dataset.disc = s.disc || "in";
  art.classList.toggle("busy", !!s.busy);
  art.classList.toggle("spinning", !!s.busy && s.disc !== "none");
  g.clearRect(0, 0, W, H);
  // the head: the sled slides along its travel; the laser spot with it while it reads
  const [rIn, rOut] = meta.sled.radius_mm, travel = rOut - rIn;
  const head = Number.isFinite(shownHead) ? Math.max(rIn, Math.min(rOut, shownHead)) : rIn;
  const t = (head - rIn) / travel, [ox, oy] = meta.sled.offset_px;
  const move = `translate(${(ox * t / W * 100).toFixed(3)}%, ${(oy * t / H * 100).toFixed(3)}%)`;
  sled.style.transform = move;
  glow.style.transform = move; glow.hidden = !s.busy || s.disc !== "in";
  if (s.disc === "none") {                 // the empty place where the disc goes
    g.save(); g.setLineDash([R(2.4), R(1.8)]); g.strokeStyle = copper; g.lineWidth = R(0.5);
    g.beginPath(); g.arc(cx, cy, R(60), 0, Math.PI * 2); g.stroke(); g.restore();
  }
  if (s.disc !== "none" && s.read) {       // the continuous band belongs to sequential writing
    const [a, b] = s.read;
    if (b > a) {
      g.save(); g.globalAlpha = 0.85; g.fillStyle = rainbow;
      g.beginPath(); g.arc(cx, cy, R(b), 0, Math.PI * 2); g.arc(cx, cy, R(a), 0, Math.PI * 2, true); g.fill();
      g.restore();
    }
  }
  if (s.disc === "in" && rings.size) {
    g.save(); g.lineWidth = R(0.5); g.strokeStyle = rainbow;
    for (const [radius, start] of rings) {
      g.globalAlpha = 0.85 * (1 - (1 - motionFraction(now, start)) ** 3);
      g.beginPath(); g.arc(cx, cy, R(radius), 0, Math.PI * 2); g.stroke();
    }
    g.restore();
  }
  if (s.band) {                            // where reading stopped: a copper band, the one thing to look at
    g.save(); g.fillStyle = copper; g.globalAlpha = 0.55;
    g.beginPath(); g.arc(cx, cy, R(s.band[1]), 0, Math.PI * 2); g.arc(cx, cy, R(s.band[0]), 0, Math.PI * 2, true); g.fill();
    g.restore();
  }
  // the pointer: from the centre along the head's travel to the head, a small ring at the head
  if (s.disc === "in" && Number.isFinite(s.head)) {
    const [ux, uy] = unit(meta.sled.px_per_mm), hx = cx + ux * R(head), hy = cy + uy * R(head);
    g.save(); g.strokeStyle = ink; g.lineWidth = Math.max(1.5, R(0.25));
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(hx, hy); g.stroke();
    g.fillStyle = paper; g.beginPath(); g.arc(hx, hy, R(1.4), 0, Math.PI * 2); g.fill(); g.stroke();
    g.restore();
    const zh = api?.lang() === "zh";
    const words = s.headKnown === false ? (zh ? "光头在读" : "Head reading") : (zh ? `光头在 ${head.toFixed(1)} mm` : `Head at ${head.toFixed(1)} mm`);
    if (label.textContent !== words) label.textContent = words;
    label.style.transform = `translate(${(hx * artScale).toFixed(2)}px, ${(hy * artScale).toFixed(2)}px)`;
    label.hidden = false;
  } else label.hidden = true;
  big.hidden = !Number.isFinite(s.percent);
  if (!big.hidden) {
    const value = `${Math.round(s.percent)}%`;
    if (percent.dataset.flipValue !== value) percentFlip.set(value);
    drawTime(s.left || "");
  }
}

function drawTime(text) {
  if (time.dataset.flipValue !== text) timeFlip.set(text);
}
const motionOff = () => api.reduce || reducedMotion.matches || document.documentElement.dataset.motion === "off";
const motionFraction = (now, start) => Math.max(0, Math.min(1, (now - start) / motionMs));
function settleMotion() {
  cancelAnimationFrame(frame);
  frame = 0;
  headMove = null;
  shownHead = state.head;
  for (const radius of rings.keys()) rings.set(radius, -Infinity);
  draw();
}
function animate(now) {
  frame = 0;
  if (headMove) {
    const {from, to, start} = headMove, t = motionFraction(now, start);
    shownHead = from + (to - from) * (1 - (1 - t) ** 3);
    if (t === 1) headMove = null;
  }
  draw(now);
  if (headMove || [...rings.values()].some(start => now - start < motionMs)) frame = requestAnimationFrame(animate);
}
function set(next) {
  const now = performance.now();
  let added = false;
  const latest = new Map();
  for (const radius of next.readRadii ?? []) {
    if (!Number.isFinite(radius) || radius <= 0 || radius > meta.disc.radius_mm) continue;
    if (!rings.has(radius)) added = true;
    latest.set(radius, rings.get(radius) ?? now);
  }
  rings = latest;
  if (next.head !== state.head) {
    headMove = Number.isFinite(shownHead) && Number.isFinite(next.head) ? {from:shownHead, to:next.head, start:now} : null;
    if (!headMove) shownHead = next.head;
  }
  state = next;
  if (el.hidden || motionOff()) {
    settleMotion();
    return;
  }
  if (!frame && (headMove || added)) frame = requestAnimationFrame(animate);
  draw(now);
}
// the scene's scale for the glass shadows (index.html --mm): the stage picture's px per mm on screen
function scale() {
  if (!art || el.hidden) return;
  const w = art.getBoundingClientRect().width;
  if (!w) return;
  artScale = w / meta.image_size[0];
  document.documentElement.style.setProperty("--mm", `${(artScale * meta.scale.px_per_mm).toFixed(3)}px`);
}
addEventListener("resize", () => { scale(); draw(); });
const unit = ([x, y]) => { const n = Math.hypot(x, y) || 1; return [x / n, y / n]; };
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export async function stage(homeApi) {
  api = homeApi;
  if (!meta) meta = await fetch(new URL("caltop.json", BASE)).then((r) => r.json());
  if (!el) build();
  return {
    show(on) {
      if (el.hidden === !on) return;
      el.hidden = !on;
      if (on) scale();
      settleMotion();
    },
    art: () => el.querySelector(".cs-art"),          // the picture's box: the grid loaddisc.js lines up with
    hold(on) { el.style.visibility = on ? "hidden" : ""; },   // laid out but unseen while the disc goes in
    set,
    time(text) { state.left = text; if (!el.hidden) drawTime(text); },
    destroy() {
      if (!el) return;
      listeners.abort(); observer.disconnect();
      cancelAnimationFrame(frame); frame = 0;
      percentFlip.destroy(); timeFlip.destroy();
      g.canvas.width = g.canvas.height = 0;
      el.remove();
      el = art = g = sled = glow = label = big = percent = time = percentFlip = timeFlip = rainbow = null;
      shownHead = headMove = null;
      rings.clear(); state = {};
    },
  };
}
