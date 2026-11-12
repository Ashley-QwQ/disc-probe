import { lobbyStatus } from "./lobby-state.js";
import { rugGreeting, nextLocalDayDelay } from "./lobby-weekday.js";

// The lobby: a corner desk with four things on it (docs/goals/gui-outline.md 3.0, art/desk NOTES "Lobby v3").
//
//   the optical drive, tray out with a blank disc   new work        (#lobby-new)
//   the file box of envelopes                       past works      (#lobby-open)
//   the monitor and keyboard                        terminal
//   the letter tray and tent card (target: fax)      import / export
//   the floor lamp                                  light / dark
//
// Art: baked renders, one layer per object (lobby/lobby.json, written by art/desk/export_lobby.py). The
// page draws the labels printed on the objects (each label's quad on its object's face), the click
// outlines, and the live status top left.
//
// The camera drifts a few pixels with the mouse: near layers move more than far ones (their depth in
// lobby.json), so the desk reads as a place. Off with reduced motion and on touch screens; DRIFT = 0
// turns it off.

const ART = "./lobby/lobby.json";
const DRIFT = 7;                      // screen px the nearest layer moves at the window's edge (the farthest: a third)
const STR = {
  zh: { newplan: "新作品", filebox: "往期作品", screen: "终端", fax: "导入导出", lamp: "开灯 / 关灯",
        soon: "这一项以后接上", last: "上次：" },
  en: { newplan: "New work", filebox: "Past works", screen: "Terminal", fax: "Import / Export", lamp: "Lamp: light / dark",
        soon: "Not connected yet", last: "Last: " },
};
let api, $, M = null, base = "", L = null;
const T = () => STR[api.lang() === "en" ? "en" : "zh"];
const root = document.documentElement;
const theme = () => (root.dataset.theme === "dark" ? "dark" : "paper");

// a box of w x h (canvas px) onto the quad TL, TR, BR, BL: the projective map as a CSS matrix3d
function quadMatrix(w, h, [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]) {
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3, dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  let g = 0, k = 0;
  if (Math.abs(dx3) > 1e-9 || Math.abs(dy3) > 1e-9) {
    const den = dx1 * dy2 - dx2 * dy1;
    g = (dx3 * dy2 - dx2 * dy3) / den; k = (dx1 * dy3 - dx3 * dy1) / den;
  }
  const a = x1 - x0 + g * x1, b = x3 - x0 + k * x3, d = y1 - y0 + g * y1, e = y3 - y0 + k * y3;
  return `matrix3d(${[a / w, d / w, 0, g / w, b / h, e / h, 0, k / h, 0, 0, 1, 0, x0, y0, 0, 1].map((v) => +v.toFixed(8)).join(",")})`;
}
const dist = ([ax, ay], [bx, by]) => Math.hypot(bx - ax, by - ay);

function build(meta, dir) {
  M = meta; base = dir;
  const [W, H] = M.size;
  const world = document.createElement("div");
  world.className = "lb-world";
  world.style.width = `${W}px`; world.style.height = `${H}px`;
  // depth to drift: the nearest layer 1, the farthest 1/3
  const ds = M.layers.map((l) => l.depth ?? 0), dn = Math.min(...ds), df = Math.max(...ds);
  const reach = (d) => (df > dn ? 1 - (2 / 3) * ((d - dn) / (df - dn)) : 1 / 3);
  const layer = {}, overs = [];
  for (const l of M.layers) {
    const g = document.createElement("div");
    g.className = l.hidden ? "lb-layer off" : "lb-layer"; g.dataset.name = l.name;     // hidden: shown on demand (the lit screen)
    g.style.setProperty("--reach", reach(l.depth ?? 0).toFixed(3));
    const img = document.createElement("img");
    img.alt = ""; img.decoding = "async"; img.draggable = false;
    const [x0, y0, x1, y1] = l.box;
    Object.assign(img.style, { left: `${x0}px`, top: `${y0}px`, width: `${x1 - x0}px`, height: `${y1 - y0}px` });
    g.append(img);
    world.append(g);
    layer[l.name] = g;
  }
  // per object: its click outline (an SVG polygon), its button (keyboard, screen readers) and its printed label
  const svgNS = "http://www.w3.org/2000/svg";
  for (const [key, t] of Object.entries(M.targets)) {
    const home = layer[t.layer] ?? layer.base, own = !!layer[t.layer] && t.layer !== "base";   // its own layer lifts
    // the label, outline and hit area sit above every picture layer (a layer shown later, like the lit
    // screen, must not cover them), drifting and lifting with their object's layer
    const g = document.createElement("div");
    g.className = "lb-layer lb-over"; g.dataset.over = key;
    g.style.setProperty("--reach", home.style.getPropertyValue("--reach"));
    const pts = t.hotspot;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const [bx, by, bw, bh] = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "lb-outline"); svg.setAttribute("viewBox", `${bx} ${by} ${bw} ${bh}`);
    Object.assign(svg.style, { left: `${bx}px`, top: `${by}px`, width: `${bw}px`, height: `${bh}px` });
    const poly = document.createElementNS(svgNS, "polygon");
    poly.setAttribute("points", pts.map((p) => p.join(",")).join(" "));
    svg.append(poly);
    svg.classList.toggle("own", own);
    svg.dataset.target = key;
    const btn = key === "newplan" ? $("lobby-new") : key === "filebox" ? $("lobby-open") : document.createElement("button");
    btn.type = "button"; btn.className = "lb-hit"; btn.dataset.target = key; btn.replaceChildren();
    Object.assign(btn.style, { left: `${bx}px`, top: `${by}px`, width: `${bw}px`, height: `${bh}px`,
      clipPath: `polygon(${pts.map(([x, y]) => `${(x - bx).toFixed(1)}px ${(y - by).toFixed(1)}px`).join(",")})` });
    g.append(svg, btn);
    if (t.label) {
      const q = t.label.quad, w = dist(q[0], q[1]), h = dist(q[0], q[3]);
      const lab = document.createElement("span");
      lab.className = own ? "lb-label own" : "lb-label"; lab.dataset.target = key;
      lab.setAttribute("aria-hidden", "true");
      Object.assign(lab.style, { width: `${w}px`, height: `${h}px`, transform: quadMatrix(w, h, q) });
      lab.style.setProperty("--h", `${h}px`);
      lab.append(document.createElement("i"));
      g.append(lab);
    }
    if (key === "lamp") {
      const hint = document.createElement("span");
      hint.className = "lb-lamp-hint"; hint.setAttribute("aria-hidden", "true");
      const [x, y] = M.lamp.bulb;
      Object.assign(hint.style, { left: `${x + 66}px`, top: `${y - 35}px` });
      g.append(hint);
      // Reuse the lamp's own image alpha, clipped to its shade, to brighten only the shade.
      const glow = layer.lamp.querySelector("img").cloneNode();
      glow.className = "lb-lamp-glow";
      const [lx, ly] = M.layers.find(l => l.name === "lamp").box;
      glow.style.clipPath = `ellipse(75px 75px at ${x - lx}px ${y - ly}px)`;
      layer.lamp.append(glow);
    }
    overs.push(g);
    btn.addEventListener("pointerenter", () => hover(key, true));
    btn.addEventListener("pointerleave", () => hover(key, false));
    btn.addEventListener("focus", () => hover(key, true));
    btn.addEventListener("blur", () => hover(key, false));
    if (!["newplan", "filebox"].includes(key)) btn.addEventListener("click", () => act(key));
  }
  world.append(...overs);
  const rug = M.greeting_faces?.runner;
  if (rug) {
    const q = rug.quad, w = dist(q[0], q[1]), h = dist(q[0], q[3]);
    const lab = document.createElement("span");
    lab.className = "lb-label lb-rug-greeting";
    Object.assign(lab.style, { width: `${w}px`, height: `${h}px`, transform: quadMatrix(w, h, q) });
    lab.style.setProperty("--h", `${h}px`);
    lab.append(document.createElement("i"));
    layer.base.append(lab); // Same floor and parallax; no button or separate target.
    L.rug = lab;
  }
  L.art.replaceChildren(world);
  L.world = world; L.layer = layer;
  paintTheme(); words(); fit();
  document.fonts?.ready.then(words);
}
// Longer words (English) shrink to fit their face, with a margin. A label that would shrink below
// about 35 % (the fax's narrow face in English) breaks onto two lines first ("Import /" over "export", 导入 over 导出) if its face is tall
// enough, and then fits.
function fitLabel(n, i) {
  if (!n.offsetWidth || !n.offsetHeight) return;      // the lobby is hidden (another page): fitted when it shows again
  const fit = () => {
    i.style.fontSize = "";
    const w = n.offsetWidth * .86, h = n.offsetHeight * .92, k = Math.min(1, w / i.offsetWidth, h / i.offsetHeight);
    if (k < 1) i.style.fontSize = `${k.toFixed(3)}em`;
    return k;
  };
  const multiline = i.textContent.includes("\n");
  i.style.whiteSpace = multiline ? "pre" : ""; i.style.lineHeight = multiline ? "1.05" : "";
  const words = i.textContent, one = fit();
  if (one >= .35 || multiline) return;
  const NL = String.fromCharCode(10);
  const cut = words.includes(" / ") ? words.replace(" / ", " /" + NL) : words.includes(" ") ? words.replace(" ", NL)
    : /^[　-鿿]{4}$/.test(words) ? words.slice(0, 2) + NL + words.slice(2) : null;
  if (!cut) return;
  i.textContent = cut; i.style.whiteSpace = "pre"; i.style.lineHeight = "1.05";
  if (fit() <= one) { i.textContent = words; i.style.whiteSpace = ""; i.style.lineHeight = ""; fit(); }
}
function hover(key, on) {
  const t = M.targets[key];
  on ||= L.root.querySelector(`.lb-hit[data-target="${key}"]`) === document.activeElement;
  if (on && key === "newplan") import("./newplan.js").then((m) => m.prepare(api)).catch(() => {});   // ready before the click
  if (on && key === "filebox") import("./pastworks.js").then((m) => m.prepare(api)).catch(() => {});
  if (t.layer !== "base") L.layer[t.layer]?.classList.toggle("lift", on);
  if (key === "lamp") L.root.classList.toggle("lamp-hot", on);
  L.root.querySelectorAll(`[data-target="${key}"]`).forEach((n) => n.classList.toggle("hot", on));
}
function act(key) {
  if (key === "lamp") { $("theme").click(); return; }
  if (key === "screen") { openTerminal(); return; }
  if (key === "fax") {                     // the letter tray: DIS presets in and out (presetio.js; hidden on an old server)
    import("./presetio.js").then((m) => { if (!m.open(document.activeElement)) toast(T().soon); }).catch(() => toast(T().soon));
    return;
  }
  toast(T().soon);
}
// the monitor: its screen lights up (the baked screen_on layer, when the art has it), then the terminal
// slides down; closing it turns the screen off again
async function openTerminal() {
  const term = await import("./terminal.js");
  if (term.isOpen()) return;
  lightScreen(true);
  await new Promise((r) => setTimeout(r, api.reduce ? 0 : 320));
  term.open(api, { closed: () => lightScreen(false) });
}
function lightScreen(on) {
  L.layer.screen_on?.classList.toggle("lit", on);
  L.root.classList.toggle("screen-lit", on);
}
function toast(text) {
  L.toast.textContent = text; L.toast.classList.add("on");
  clearTimeout(L.toastT); L.toastT = setTimeout(() => L.toast.classList.remove("on"), 2200);
}
function paintTheme() {
  if (!M) return;
  const th = theme();
  for (const l of M.layers) for (const img of L.layer[l.name].querySelectorAll("img")) img.src = `${base}${l.name}_${th}.webp`;
  lampWords();
  if (M.bg?.[th]) L.root.style.setProperty("--lb-bg", M.bg[th]); else L.root.style.removeProperty("--lb-bg");
}
function words() {
  if (!M) return;
  const t = T();
  for (const n of L.root.querySelectorAll(".lb-label[data-target]")) {
    const i = n.firstElementChild;
    i.textContent = t[n.dataset.target] ?? "";
    if (n.dataset.target === "fax" && api.lang() === "en") i.textContent = "Import /\nExport";
    fitLabel(n, i);
  }
  for (const n of L.root.querySelectorAll(".lb-hit")) n.setAttribute("aria-label", t[n.dataset.target] ?? n.dataset.target);
  lampWords();
  paintHello();
  paintRug();
}
function paintRug() {
  if (!L?.rug) return;
  const text = rugGreeting(api.lang());
  L.rug.setAttribute("aria-label", text);
  L.rug.firstElementChild.textContent = api.lang() === "en" ? text.replace(" ", "\n") : text;
  fitLabel(L.rug, L.rug.firstElementChild);
  clearTimeout(L.rugTimer);
  L.rugTimer = setTimeout(paintRug, nextLocalDayDelay());
}
// the scene fits the window (contain), centred; the header and the footer sit over its empty top and bottom
function fit() {
  if (!M) return;
  const [W, H] = M.size, vw = innerWidth, vh = innerHeight;
  const k = Math.min(vw / W, vh / H) * (vw < 720 ? 1.25 : 1);
  L.k = k;
  L.world.style.transform = `translate(${((vw - W * k) / 2).toFixed(1)}px, ${((vh - H * k) / 2).toFixed(1)}px) scale(${k.toFixed(5)})`;
}

function lampWords() {
  if (!L) return;
  const dark = theme() === "dark", en = api.lang() === "en";
  const text = en ? (dark ? "Lights on" : "Lights off") : (dark ? "开灯" : "关灯");
  const hint = L.root.querySelector(".lb-lamp-hint");
  if (hint) hint.textContent = text;
  L.root.querySelector('.lb-hit[data-target="lamp"]')?.setAttribute("aria-label", text);
}
// The home page owns updates; the lobby only reads its cached state.
function paintHello() {
  if (L) L.hello.textContent = lobbyStatus(api.lobbyState?.(), api.lang());
}
// the second line: the last plan, to pick up where it was left
export function paintRecent(plans, open) {
  if (!L) return;
  const p = plans?.[0];
  L.recent.replaceChildren();
  L.recent.hidden = !p;
  if (!p) return;
  const b = document.createElement("button");
  b.type = "button"; b.textContent = p.name ?? p.item?.name ?? "—";
  b.addEventListener("click", () => open(p));
  L.recent.append(T().last, b);
}

// ---------------------------------------------------------------- the drift
function drift() {
  const fine = matchMedia("(pointer: fine)").matches;
  if (!DRIFT || !fine) return;
  let tx = 0, ty = 0, x = 0, y = 0, raf = 0;
  L.drifters = [...L.world.querySelectorAll(".lb-layer")].map((g) => [g, Number(g.style.getPropertyValue("--reach")) || 0]);
  const step = () => {
    x += (tx - x) * 0.08; y += (ty - y) * 0.08;
    // in canvas px: the world is scaled by k
    // Each layer's own offset (its reach times the world's): a variable on the world would make every
    // element under it restyle on every frame (about a tenth of the main thread while the mouse moves).
    const s = DRIFT / (L.k || 1), dx = -x * s, dy = -y * s;
    for (const [g, r] of L.drifters) g.style.translate = `${(dx * r).toFixed(2)}px ${(dy * r).toFixed(2)}px`;
    raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.002 ? requestAnimationFrame(step) : 0;
  };
  L.root.addEventListener("pointermove", (e) => {
    if (api.reduce) { tx = ty = 0; if (!raf) raf = requestAnimationFrame(step); return; }
    tx = (e.clientX / innerWidth) * 2 - 1; ty = (e.clientY / innerHeight) * 2 - 1;
    if (!raf) raf = requestAnimationFrame(step);
  });
  L.root.addEventListener("pointerleave", () => { tx = ty = 0; if (!raf) raf = requestAnimationFrame(step); });
}

// ---------------------------------------------------------------- set up
export async function init(homeApi) {
  api = homeApi; $ = api.$;
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = new URL("./lobby.css", import.meta.url).href;
  document.head.append(css);
  const sec = $("lobby");
  L = { root: sec, art: $("lobby-art"), hello: $("lobby-hello"), recent: $("lobby-recent"), toast: document.createElement("div") };
  L.toast.className = "lb-toast"; L.toast.setAttribute("role", "status");
  sec.append(L.toast);
  // Own this entry in capture phase: index.html's old file-picker listener stays dormant.
  // The same native button answers the printed label/hotspot and the lobby keyboard path.
  $("lobby-open").addEventListener("click", async (e) => {
    e.preventDefault(); e.stopImmediatePropagation();
    if (root.dataset.mode === "pastworks") return;
    const button = $("lobby-open"); button.setAttribute("aria-busy", "true");
    try { await (await import("./pastworks.js")).start(api, { from: button }); }
    catch (error) { console.error("past works", error); toast(api.lang() === "en" ? "Could not open past works. Try again." : "没能打开往期作品，请重试。"); }
    finally { button.removeAttribute("aria-busy"); }
  }, { capture: true });
  paintHello();
  addEventListener("dp-drive-state", paintHello);
  const url = new URL(ART, import.meta.url);
  build(await fetch(url).then((r) => r.json()), new URL(".", url).href);
  addEventListener("resize", fit);
  new MutationObserver(paintTheme).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  addEventListener("dp-lang", words);
  // the labels are measured against their faces: words changed (language, fonts) while the lobby was hidden could not
  // be, so fit them again whenever the lobby comes back on screen
  let shown = false;
  new ResizeObserver(() => { const now = sec.offsetWidth > 0; if (now && !shown) words(); shown = now; }).observe(sec);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) paintRug(); });
  drift();
}
export const relabel = () => words();
