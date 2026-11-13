// The start guide: one sheet that says the four things before a first disc, shows where the person is from
// what is on disk (never from what this page believes), and what to check when no picture shows.
// Opened from the lobby, the settings menu and, the first time, a line in the lobby greeting.
// Nothing here starts a job, a burn or a measurement. The animation is SVG and timers, with no 3D context, and with
// motion off, the page in the background, or Skip, the last scene stands with all four captions in a list.

import { introCards, disShortcut, lightScenes, journey, statusWords, troubleChecks, troubleNote } from "./guidance.mjs";

const SEEN = "dp-guide-seen", MEDIA = "dp-guide-media", SCENE_MS = 3200;
const STR = {
  zh: {
    title: "新手引导", open: "看新手引导", close: "关闭引导", offer: "第一次用？花两分钟看一下流程。", offerSeen: "不知道下一步？",
    animLabel: "光怎么变成图的教学动画", prev: "看上一幕", next: "看下一幕", replay: "重看动画", skip: "跳过动画",
    sceneOf: (n, t) => `第 ${n} 幕，共 ${t} 幕`, beforeH: "开始之前", wayH: "你现在在哪一步", wayNote: "进度读自这台电脑上的结果文件。程序看不到的事，会写“还不知道”，不会当成已完成。",
    mediaLabel: "盘的种类", refresh: "重新读取进度", reading: "正在读取进度……", troubleH: "没出图，先查这三样", troubleLead: "按顺序查，前一样没问题再查下一样。", why: "什么时候再刻：",
    latest: "读取时间", mark: { done: "完成", now: "现在", todo: "未做", unknown: "未知", problem: "要处理" },
    nowHere: "现在做这一步", goalLabel: "盘数目标", settingsRow: "新手引导", useNow: (label) => label,
    footReady: "可以刻第一张成品", footDefault: "走到“可以刻第一张成品”为止。", read: "读开始之前的四件事", dataLabel: "读数",
  },
  en: {
    title: "Start guide", open: "Open the guide", close: "Close the guide", offer: "First time here? Two minutes on how it goes.", offerSeen: "Not sure what is next?",
    animLabel: "Teaching animation: how light becomes a picture", prev: "Show the previous scene", next: "Show the next scene", replay: "Replay the animation", skip: "Skip the animation",
    sceneOf: (n, t) => `Scene ${n} of ${t}`, beforeH: "Before you start", wayH: "Where you are", wayNote: "Progress is read from the result files on this computer. What the program cannot see is marked “Not known”, never counted as done.",
    mediaLabel: "Disc type", refresh: "Read the progress again", reading: "Reading the progress…", troubleH: "No picture? Check these three", troubleLead: "In this order. Go on to the next only when the last is fine.", why: "When another disc is justified: ",
    latest: "Read", mark: { done: "Done", now: "Now", todo: "Not yet", unknown: "Not known", problem: "Needs attention" },
    nowHere: "Do this step now", goalLabel: "Disc goal", settingsRow: "Start guide", useNow: (label) => label,
    footReady: "Ready to burn the first picture", footDefault: "The guide ends at “ready to burn the first picture”.", read: "Read the four things", dataLabel: "Reading",
  },
};

const root = document.documentElement;
let api, sheet, opener = null, media = "dvd", scene = 3, timer = 0, playing = false, stateNow = null, token = 0;
const T = () => STR[api.lang() === "en" ? "en" : "zh"];
const L = (p) => p[api.lang() === "en" ? "en" : "zh"];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel) => sheet.querySelector(sel);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
export const seen = () => store.get(SEEN) === "1";
const motionOn = () => root.dataset.motion === "on";

// ---------------------------------------------------------------- the teaching animation
const TRACKS = Array.from({ length: 49 }, (_, i) => `M${120 + i * 8} 168v12`).join("");
const RAY_COLOURS = ["#c04a6a", "#d08a3e", "#b9a52f", "#4fa174", "#4a7fd0"];
function animation() {
  // the beam meets the surface at x 378; the rays leave it at 52, 42, 32, 22 and 12 degrees, red the steepest;
  // the fourth reaches the eye
  const rays = RAY_COLOURS.map((c, i) => { const a = [52, 42, 32, 22, 12][i] * Math.PI / 180; return `<line class="sg-ray" data-i="${i}" x1="378" y1="168" x2="${(378 + 200 * Math.cos(a)).toFixed(1)}" y2="${(168 - 200 * Math.sin(a)).toFixed(1)}" stroke="${c}"/>`; }).join("");
  return `<svg class="sg-fig" viewBox="0 0 640 224" role="img" aria-label="${esc(T().animLabel)}">
    <path class="sg-tracks" d="${TRACKS}"/><path class="sg-surface" d="M112 168H512"/>
    <g class="sg-beamg"><circle class="sg-lamp" cx="64" cy="28" r="9"/><line class="sg-beam" x1="72" y1="34" x2="378" y2="166"/></g>
    <g class="sg-raysg">${rays}</g>
    <g class="sg-eyeg"><path class="sg-eye" d="M572 93q30-26 60 0q-30 26-60 0z"/><circle class="sg-pupil" cx="602" cy="93" r="6"/></g>
    <g class="sg-pic"><rect x="344" y="160" width="68" height="28" rx="2"/><text x="378" y="214" text-anchor="middle">${esc(L({ zh: "图案", en: "picture" }))}</text></g>
  </svg>`;
}
function paintScene() {
  const t = T();
  sheet.dataset.scene = String(scene + 1);
  $(".sg-caption").textContent = `${t.sceneOf(scene + 1, lightScenes.length)}：${L(lightScenes[scene])}`;
  sheet.querySelectorAll(".sg-scenes li").forEach((li, i) => { li.dataset.on = String(i === scene); if (i === scene) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current"); });
  $("[data-act=prev]").disabled = scene === 0;
  $("[data-act=next]").disabled = scene === lightScenes.length - 1;
}
function stop() { clearTimeout(timer); timer = 0; }
function tick() {
  stop();
  if (!playing || document.hidden || !motionOn() || sheet.hidden) return;
  timer = setTimeout(() => {
    if (scene < lightScenes.length - 1) { scene++; paintScene(); tick(); } else playing = false;
  }, SCENE_MS);
}
function replay() { scene = 0; playing = motionOn(); paintScene(); tick(); }
function skip() { playing = false; stop(); scene = lightScenes.length - 1; paintScene(); }
function step(d) { playing = false; stop(); scene = Math.min(lightScenes.length - 1, Math.max(0, scene + d)); paintScene(); }

// ---------------------------------------------------------------- the progress
async function readState() {
  const mine = ++token;
  const body = $("#sg-way-body");
  body.setAttribute("aria-busy", "true");
  let state = null;
  try { state = api.backend.mock ? null : await api.backend.request(`/api/state?media=${media}`); } catch { state = null; }
  if (mine !== token) return;
  stateNow = { state, at: new Date() };
  paintWay();
}
function paintWay() {
  if (!stateNow) return;
  const t = T(), g = journey(stateNow.state || {}, { media, withIntro: false });
  const body = $("#sg-way-body");
  body.removeAttribute("aria-busy");
  body.innerHTML = `<ol class="sg-steps">${g.rows.map((r) => {
    const unknown = r.unknown ? `<p class="sg-unk"><b>${esc(L({ zh: "还不知道：", en: "Not known: " }))}</b>${esc(L(r.unknown))}</p>` : "";
    return `<li data-status="${r.status}"${r.now ? ' data-now="true" aria-current="step"' : ""}>
      <span class="sg-tick" aria-hidden="true"></span>
      <div><h4>${esc(L(r.title))}<span class="sg-state">${esc(r.now && r.status === "todo" ? t.nowHere : L(statusWords[r.status]) + (r.now ? ` · ${t.nowHere}` : ""))}</span></h4>
      <p>${esc(L(r.known))}</p>${unknown}${r.data ? `<p class="sg-data" aria-label="${esc(t.dataLabel)}">${esc(r.data)}</p>` : ""}</div></li>`;
  }).join("")}</ol>`;
  const now = g.rows.find((r) => r.now);
  const foot = $(".sg-foot-say"), go = $("[data-act=go]");
  foot.textContent = g.milestone.reached ? L(g.milestone.words) : `${L(g.milestone.words)}`;
  sheet.dataset.reached = String(g.milestone.reached);
  go.hidden = !now?.next;
  if (now?.next) { go.textContent = L(now.next.label); go.dataset.kind = now.next.kind; }
  $("#sg-read-at").textContent = `${t.latest} ${stateNow.at.toLocaleTimeString()}`;
}

// ---------------------------------------------------------------- the sheet
function build() {
  if (!document.querySelector('link[href$="guide.css"]')) {
    const css = document.createElement("link"); css.rel = "stylesheet"; css.href = new URL("./guide.css", import.meta.url).href; document.head.append(css);
  }
  sheet = document.createElement("section");
  sheet.className = "startguide"; sheet.hidden = true; sheet.setAttribute("role", "dialog"); sheet.setAttribute("aria-modal", "true"); sheet.setAttribute("aria-labelledby", "sg-title");
  document.body.append(sheet);
  sheet.addEventListener("keydown", (e) => {
    e.stopPropagation();                                   // keys.js (Esc = back, Enter = next) is not for this sheet
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key === "Tab") {
      const f = [...sheet.querySelectorAll("button:not([disabled]):not([hidden]), summary, a[href]")].filter((n) => n.getClientRects().length);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === sheet.querySelector("#sg-title"))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  sheet.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const a = b.dataset.act;
    if (a === "close") close();
    else if (a === "prev") step(-1);
    else if (a === "next") step(1);
    else if (a === "replay") replay();
    else if (a === "skip") skip();
    else if (a === "refresh") readState();
    else if (a === "dis") importPreset(b);
    else if (a === "go") go(b.dataset.kind);
    else if (b.dataset.media) { media = b.dataset.media; store.set(MEDIA, media); paintMedia(); readState(); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else tick(); });
  addEventListener("dp-lang", () => { if (sheet && !sheet.hidden) render(); paintOffer(); });
  new MutationObserver(() => { if (!sheet.hidden) { if (!motionOn()) { playing = false; stop(); } } }).observe(root, { attributes: true, attributeFilter: ["data-motion"] });
}
function render() {
  const t = T();
  sheet.innerHTML = `<header class="sg-bar"><h2 id="sg-title" tabindex="-1">${esc(t.title)}</h2><button type="button" class="sg-btn" data-act="close">${esc(t.close)}</button></header>
  <div class="sg-scroll"><div class="sg-col">
    <section aria-labelledby="sg-before"><h3 id="sg-before">${esc(t.beforeH)}</h3>
      <div class="sg-anim">${animation()}
        <p class="sg-caption" role="status" aria-live="polite"></p>
        <div class="sg-controls" role="group" aria-label="${esc(t.animLabel)}">
          <button type="button" class="sg-btn" data-act="prev">${esc(t.prev)}</button><button type="button" class="sg-btn" data-act="next">${esc(t.next)}</button>
          <button type="button" class="sg-btn" data-act="replay">${esc(t.replay)}</button><button type="button" class="sg-btn" data-act="skip">${esc(t.skip)}</button></div>
        <ol class="sg-scenes">${lightScenes.map((s) => `<li>${esc(L(s))}</li>`).join("")}</ol></div>
      ${introCards.map((c) => `<article class="sg-card" id="sg-${c.id}"><h4>${esc(L(c.title))}</h4><p>${esc(L(c.body))}</p>${c.list ? `<ul>${c.list.map((x) => `<li>${esc(L(x))}</li>`).join("")}</ul>` : ""}</article>`).join("")}
      <article class="sg-dis"><h4>${esc(L(disShortcut.title))}</h4><p>${esc(L(disShortcut.body))}</p>
        <p><button type="button" class="sg-btn" data-act="dis">${esc(L(disShortcut.button))}</button> <span class="sg-miss" role="status" aria-live="polite"></span></p></article>
    </section>
    <section aria-labelledby="sg-way"><h3 id="sg-way">${esc(t.wayH)}</h3><p class="sg-note">${esc(t.wayNote)}</p>
      <div class="sg-media" role="group" aria-label="${esc(t.mediaLabel)}">${["dvd", "cd", "bd"].map((m) => `<button type="button" class="sg-btn" data-media="${m}">${m.toUpperCase()}</button>`).join("")}
        <button type="button" class="sg-btn" data-act="refresh">${esc(t.refresh)}</button><span id="sg-read-at" class="sg-note"></span></div>
      <div id="sg-way-body" aria-live="polite"><p class="sg-note">${esc(t.reading)}</p></div></section>
    <section aria-labelledby="sg-trouble" id="sg-trouble-sec"><h3 id="sg-trouble">${esc(t.troubleH)}</h3><p class="sg-note">${esc(t.troubleLead)}</p>
      <ol class="sg-checks">${troubleChecks.map((c) => `<li><h4>${esc(L(c.title))}</h4><p>${esc(L(c.body))}</p>${c.reburn ? `<p class="sg-why"><b>${esc(t.why)}</b>${esc(L(c.reburn))}</p>` : ""}</li>`).join("")}</ol>
      <p>${esc(L(troubleNote))}</p></section>
  </div></div>
  <footer class="sg-foot"><p class="sg-foot-say" role="status"></p><button type="button" class="sg-btn sg-primary" data-act="go" hidden></button></footer>`;
  paintMedia(); paintScene(); paintImport();
  if (stateNow) paintWay(); else readState();
}
function paintMedia() { sheet.querySelectorAll("[data-media]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.media === media))); }
async function paintImport() {
  const btn = $("[data-act=dis]");
  const ok = await import("./presetio.js").then((m) => m.ready()).catch(() => false);
  if (!sheet.hidden && btn?.isConnected) { btn.disabled = !ok; $(".sg-miss").textContent = ok ? "" : L(disShortcut.missing); }
}
async function importPreset(btn) {
  const m = await import("./presetio.js").catch(() => null);
  if (!m?.open(btn)) $(".sg-miss").textContent = L(disShortcut.missing);
}
function go(kind) {
  if (kind === "newwork") { close(); api.newWork?.(); }
  else if (kind === "refresh") readState();
  else if (kind === "trouble") $("#sg-trouble-sec")?.scrollIntoView({ behavior: motionOn() ? "smooth" : "auto", block: "start" });
  else if (kind === "read") $("#sg-before")?.scrollIntoView({ behavior: motionOn() ? "smooth" : "auto", block: "start" });
}
export function open(from) {
  if (!sheet) return false;
  opener = from ?? document.activeElement;
  stateNow = null;
  render();
  sheet.hidden = false;
  // motion off: the last scene already stands, with all four captions; on: it plays once from the first
  scene = motionOn() ? 0 : lightScenes.length - 1;
  playing = motionOn();
  paintScene(); tick();
  $("#sg-title").focus();
  return true;
}
export function close() {
  if (!sheet || sheet.hidden) return;
  stop(); playing = false; sheet.hidden = true;
  store.set(SEEN, "1"); paintOffer();
  // the lobby's line is rebuilt when the guide closes, so the opener may be gone: go to its new button
  const back = opener?.isConnected ? opener : document.querySelector("#lobby-guide button") ?? document.getElementById("settings");
  back?.focus?.();
}
export const isOpen = () => !!sheet && !sheet.hidden;

// The lobby's line under the greeting, and the settings menu's row: both open the same sheet.
function paintOffer() {
  const line = document.getElementById("lobby-guide");
  if (line) {
    const t = T();
    line.innerHTML = `<span>${esc(seen() ? t.offerSeen : t.offer)}</span> <button type="button">${esc(t.open)}</button>`;
    line.querySelector("button").onclick = (e) => open(e.currentTarget);
  }
  const row = document.getElementById("set-guide");
  if (row) {
    const t = T();
    row.querySelector("span").textContent = t.settingsRow;
    const b = row.querySelector("button"); b.textContent = t.open; b.onclick = (e) => { e.stopPropagation(); const gear = document.getElementById("settings"); gear?.click(); open(gear); };
  }
}
export function init(homeApi) {
  api = homeApi;
  media = ["dvd", "cd", "bd"].includes(store.get(MEDIA)) ? store.get(MEDIA) : "dvd";
  build();
  paintOffer();
  return { open, close };
}
