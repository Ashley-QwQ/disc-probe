// The disc goes into the drive (about one second), seen straight down with the camera on the disc: it lies on the
// desk in front of the open tray, rises (it grows a little, its shadow slides away and softens), the desk and
// everything on it slide down until the tray is under it, it settles, the tray carries it into the drive under the
// see-through shell. The lamp's warm pool stays on the drive; the shadows fall lower left, as everywhere.
// The last frame is the calibration stage (caltop/), on the same pixel grid, so the stage takes over without a seam.
//
//   import * as load from "./loaddisc.js";
//   await load.play(anchor)        anchor: the element whose box is the stage picture (caltop grid), e.g. .cs-art
//   load.desk(on, anchor)          the desk under the stage: grain, pool, the three objects (stays after play)
//   await load.slide(dir, anchor)  the last frame (one baked picture + pool + grain) slides out: "left" | "right" | "up" | "down"
//   await load.slide(dir, anchor, true)   ... or slides in from that side
// Sprites and placement: caltop/anim/anim.json (caltop/compose_anim.py). Motion off (the page's setting): straight to the last frame.

const BASE = new URL("./caltop/anim/", import.meta.url);
const STAGE = new URL("./caltop/", import.meta.url);
const T = { lift: [0, 300], travel: [140, 650], settle: [520, 760], close: [760, 1080], end: 1080 };
const DRIVE = ["trayshadow", "shadowbody", "under", "tray", "dshadow", "disc", "overbody", "overclamp", "lid"];
let meta = null, root = null, world = null, grain = null, els = {}, running = null, playing = false;

const ease = { out: (x) => 1 - (1 - x) ** 3, in: (x) => x * x, inOut: (x) => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2) };
const span = (ms, [a, b]) => Math.max(0, Math.min(1, (ms - a) / (b - a)));
const theme = () => (document.documentElement.dataset.theme === "dark" ? "dark" : "paper");
// the page's own motion setting (index.html: Settings, else the system's, ?motion forces it on)
const reduced = () => document.documentElement.dataset.motion === "off" ||
  (!document.documentElement.dataset.motion && matchMedia("(prefers-reduced-motion: reduce)").matches);

async function ready() {
  if (!meta) meta = await fetch(new URL("anim.json", BASE)).then((r) => r.json());
  if (!root) build();
  paintTheme();
}

function sprite(name, cls = "", file = name, base = BASE) {
  const b = meta.sprites[name]?.box || [0, 0, ...meta.image_size];
  const img = document.createElement("img");
  img.alt = ""; img.draggable = false; img.className = cls;
  img.dataset.file = file; img.dataset.base = base.href;
  Object.assign(img.style, { left: `${b[0]}px`, top: `${b[1]}px`, width: `${b[2] - b[0]}px`, height: `${b[3] - b[1]}px` });
  return img;
}
function group(cls, kids) {
  const g = document.createElement("div");
  g.className = "ld-g " + cls;
  g.append(...kids);
  return g;
}

function build() {
  const st = document.createElement("style");
  st.textContent = `
  .ld { position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; contain: strict; }
  .ld[hidden] { display: none; }
  .ld-grain { position: absolute; left: -10%; right: -10%; background-repeat: repeat; background-size: 384px; will-change: transform; }
  .ld-world { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
  .ld-world img, .ld-g { position: absolute; user-select: none; }
  .ld-g { left: 0; top: 0; will-change: transform, opacity; }
  .ld-world [hidden] { display: none; }`;
  document.head.append(st);
  root = document.createElement("div");
  root.className = "ld"; root.hidden = true; root.setAttribute("aria-hidden", "true");
  grain = document.createElement("div"); grain.className = "ld-grain";
  world = document.createElement("div"); world.className = "ld-world";
  const props = meta.props.map((p) => p.name);
  els.pool = sprite("pool");
  els.propShadows = props.map((p) => sprite(`prop_${p}_shadow`));
  els.props = props.map((p) => sprite(`prop_${p}`));
  els.trayshadow = group("", [sprite("trayshadow")]);
  els.shadowbody = sprite("shadowbody");
  els.under = sprite("under");
  els.tray = group("", [els.trayOpen = sprite("tray"), els.trayIn = sprite("trayin")]);
  els.dshadow = group("", [els.near = sprite("discshadow_near"), els.far = sprite("discshadow_far")]);
  els.disc = group("", [els.discStart = sprite("discstart"), els.discLit = sprite("disc")]);
  els.overbody = sprite("overbody");
  els.overclamp = sprite("overclamp");
  els.overclamp.style.opacity = meta.stage_opacity.occluders;
  els.lid = sprite("lid", "", "lid", STAGE);
  els.lid.style.opacity = meta.stage_opacity.lid;
  els.final = sprite("final"); els.final.hidden = true;
  world.append(els.pool, ...els.propShadows, ...els.props, els.final, ...DRIVE.map((k) => els[k]));
  root.append(grain, world);
  document.body.prepend(root);
  addEventListener("resize", () => { if (!root.hidden) place(lastAnchor, lastCam); });
  new MutationObserver(paintTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}
function paintTheme() {
  if (!root) return;
  const v = theme();
  for (const img of root.querySelectorAll("img")) {
    const src = new URL(`${img.dataset.file}_${v}.webp`, img.dataset.base).href;
    if (img.dataset.src !== src) { img.src = src; img.dataset.src = src; }
  }
  grain.style.backgroundImage = `url("${new URL(`desk_${v}.webp`, BASE).href}")`;
}

// the world on screen: the stage's grid onto the anchor's box, moved by cam (grid px) so the camera follows the disc
// the grain moves a little slower than the things on the desk (GRAIN of their speed)
const GRAIN = 0.85;
let lastAnchor = null, lastCam = [0, 0];
function place(anchor, cam = [0, 0]) {
  lastAnchor = anchor; lastCam = cam;
  const r = anchor.getBoundingClientRect(), s = r.width / meta.image_size[0];
  world.style.transform = `translate(${r.left}px, ${r.top}px) scale(${s}) translate(${-cam[0]}px, ${-cam[1]}px)`;
  const travel = Math.abs(meta.disc.start_px[1] - meta.disc.clamped_px[1]) * s;
  grain.style.top = "-64px"; grain.style.bottom = `${-travel - 64}px`;
  grain.style.transform = `translate(${-cam[0] * GRAIN * s}px, ${-cam[1] * GRAIN * s}px)`;
  return s;
}

const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
function lightAt(p) {             // the pool's strength at p (grid px)
  const [cx, cy] = meta.pool.centre_px, s = meta.pool.sigma_px;
  return Math.exp(-((p[0] - cx) ** 2 + (p[1] - cy) ** 2) / (2 * s * s));
}
const lit = (p, a, b) => Math.max(0, Math.min(1, (lightAt(p) - lightAt(a)) / (lightAt(b) - lightAt(a))));

// one frame of the story at ms
function frame(anchor, ms) {
  const d = meta.disc, apex = meta.apex_mm, pxmm = meta.px_per_mm, per = meta.shadow.per_mm_height;
  const C = d.clamped_px, travel = meta.tray.travel_px;
  const t = ease.inOut(span(ms, T.close));
  const recess = add(d.recess_open_px, [travel[0] * t, travel[1] * t]);
  let pos = mix(d.start_px, d.recess_open_px, ease.inOut(span(ms, T.travel)));
  if (ms >= T.close[0]) pos = mix(recess, add(recess, sub(C, d.recess_closed_px)), t);
  const h = apex * (ms < T.settle[0] ? ease.out(span(ms, T.lift)) : 1 - ease.in(span(ms, T.settle)));
  const cam = sub(pos, C);
  place(anchor, cam);
  // the disc: where it is, a touch larger when high, lit by the pool as it comes into it; translucent once inside
  const off = sub(pos, C), k = 1 + 0.1 * h / apex;
  els.disc.style.transform = `translate(${off[0]}px, ${off[1]}px) translate(${C[0]}px, ${C[1]}px) scale(${k}) translate(${-C[0]}px, ${-C[1]}px)`;
  els.discLit.style.opacity = lit(pos, d.start_px, C).toFixed(3);
  els.disc.style.opacity = (1 - (1 - meta.stage_opacity.disc) * t).toFixed(3);
  const sh = [per[0] * h * pxmm, -per[1] * h * pxmm];      // desk mm (+y = rear) to screen px
  els.dshadow.style.transform = `translate(${off[0] + sh[0]}px, ${off[1] + sh[1]}px)`;
  els.far.style.opacity = (h / apex).toFixed(3); els.near.style.opacity = (1 - h / apex).toFixed(3);
  // the tray: open until the disc is in, then home; lit as it goes in; its shadow gives way to the drive's
  const tt = `translate(${travel[0] * t}px, ${travel[1] * t}px)`;
  els.tray.style.transform = tt; els.trayshadow.style.transform = tt;
  els.trayIn.style.opacity = lit(recess, d.recess_open_px, d.recess_closed_px).toFixed(3);
  els.trayshadow.style.opacity = (1 - t).toFixed(3);
}

function showDrive(on) { for (const k of DRIVE) els[k].hidden = !on; }

// play: resolves when the last frame is on screen (and the stage may take over)
export async function play(anchor) {
  playing = true;
  try { await ready(); } catch (e) { playing = false; throw e; }
  if (running) running.stop();
  root.hidden = false; els.final.hidden = true; root.style.transform = "";
  showDrive(true);
  frame(anchor, 0);                            // placed before anything shows, even while pictures decode
  // the pictures ready before the first frame, but never wait long (a background tab may not decode at all)
  const decoded = Promise.all([...root.querySelectorAll("img")].filter((i) => !i.hidden).map((i) => i.decode().catch(() => {})));
  await Promise.race([decoded, new Promise((r) => setTimeout(r, 1200))]);
  return new Promise((resolve) => {
    let t0 = null, raf = 0, timer = 0, done = false;
    const finish = () => {
      if (done) return; done = true; cancelAnimationFrame(raf); clearTimeout(timer); running = null;
      frame(anchor, T.end); showDrive(false); place(anchor); playing = false; resolve();
    };
    running = { stop: finish };
    if (reduced() || document.hidden) { finish(); return; }
    const step = (now) => {
      if (t0 === null) t0 = now;
      const ms = now - t0;
      if (ms >= T.end) { finish(); return; }
      frame(anchor, ms);
      raf = requestAnimationFrame(step);
    };
    frame(anchor, 0);
    raf = requestAnimationFrame(step);
    timer = setTimeout(finish, T.end + 600);   // a hidden tab stops animation frames: end anyway
  });
}

// one still of the story at ms (0 .. about 1080), for checks and pictures
export async function pose(anchor, ms) {
  await ready();
  if (running) running.stop();
  root.hidden = false; els.final.hidden = true; showDrive(true); frame(anchor, ms);
}

// the desk under the stage (grain, pool, objects) without the moving drive
export async function desk(on, anchor) {
  if (!on) { running?.stop(); if (root) root.hidden = true; return; }
  await ready();
  if (playing) return;
  root.hidden = false; root.style.transform = ""; els.final.hidden = true; showDrive(false); place(anchor);
}

// the last frame as one picture slides out to (or in from) a side
export async function slide(dir, anchor, entering = false) {
  await ready();
  if (running) running.stop();
  root.hidden = false; showDrive(false); els.final.hidden = false;
  for (const e of [...els.props, ...els.propShadows]) e.hidden = true;
  place(anchor);
  const [dx, dy] = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] }[dir] || [-1, 0];
  const far = `translate(${dx * innerWidth}px, ${dy * innerHeight}px)`;
  const frames = entering ? [{ transform: far }, { transform: "none" }] : [{ transform: "none" }, { transform: far }];
  const a = root.animate(frames, { duration: reduced() ? 1 : 420, easing: "cubic-bezier(.65,0,.35,1)", fill: "forwards" });
  await a.finished.catch(() => {});
  a.cancel();
  els.final.hidden = true;
  for (const e of [...els.props, ...els.propShadows]) e.hidden = false;
  if (!entering) root.hidden = true;
}
