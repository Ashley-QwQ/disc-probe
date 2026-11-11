// The new-plan page: what opens when "new work" is clicked in the lobby.
//
// The lobby flies to high above the drive and zooms in; the page is that view: the drive seen from above
// on the left, and on the right a large sheet of paper on the desk, running on under the footer, holding a
// short form: the plan's name (a suggestion taken with Tab), the disc (a half disc hanging from the sheet's
// top edge, with two rings of keys cut from concentric circles below it: the kind DVD / CD / BD on the
// inner ring, the type -R / +R / RW on the outer) and the disc batch (or "decide later"). On "next" an
// archive envelope rises from below, the sheet slides into it, and both drop out of the frame while the
// next page comes down from above.
//
// Art: baked renders in ./newplan/ (made by art/newplan/render_newplan.py; positions in newplan.json):
// the drive from above on the lit desk, the paper sheet and its shadow, the envelope's back and front.
// All motion is transform / opacity only.

const STR = {
  zh: {
    title: "新作品", name: "计划名", nameHelp: "我们怎么称呼这个计划", tab: "Tab 采用",
    disc: "所使用的光盘", discHelp: "光盘的型号与批次", later: "先不填", inDrive: (n) => `驱内：${n}`,
    left: (l, o) => `还剩 ${l} / ${o} 张`, newPack: "新开一包 · 登记", kinds: "盘的种类", subs: "盘的类型",
    next: "下一步：放进图片", none: (k) => `还没有登记过 ${k}`,
    calOk: (d) => `已标定 · ${d}`, calNone: "这批盘还没标定。刻录前要先标定，也可以先画，刻录前再标。", calGo: "先去标定",
    months: ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"],
    suggest: (m, d, w) => `${m}${d} 的 ${w}`, soon: "这一项以后接上",
  },
  en: {
    title: "New work", name: "Plan name", nameHelp: "What should we call this plan?", tab: "Tab to use",
    disc: "Discs", discHelp: "Disc model and batch", later: "Decide later", inDrive: (n) => `In the drive: ${n}`,
    left: (l, o) => `${l} / ${o} left`, newPack: "Opened a new pack? Register it", kinds: "Disc kind", subs: "Disc type",
    next: "Next: add a picture", none: (k) => `No ${k} registered yet`,
    calOk: (d) => `Calibrated · ${d}`, calNone: "This batch isn't calibrated yet. It must be before burning; you can draw first and calibrate then.", calGo: "Calibrate first",
    months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    suggest: (m, d, w) => `${m}${d}'s ${w}`, soon: "Not connected yet",
  },
};
// the kinds on the inner ring and, per kind, its types on the outer ring: the key's text, the whole
// name on the half disc, and which batch names are of that type
const KINDS = ["dvd", "cd", "bd"], KIND_KEY = { dvd: "DVD", cd: "CD", bd: "BD" };
const SUBS = {
  dvd: [{ key: "+R", label: "DVD+R", re: /DVD\+R(?!W)/i }, { key: "-R", label: "DVD-R", re: /DVD-R(?!W)/i }, { key: "RW", label: "DVD±RW", re: /DVD[-+]RW/i }],
  cd: [{ key: "-R", label: "CD-R", re: /CD-R(?!W)/i }, { key: "RW", label: "CD-RW", re: /CD-RW/i }],
  bd: [{ key: "-R", label: "BD-R", re: /BD-R(?!E)/i }, { key: "RE", label: "BD-RE", re: /BD-RE/i }],
};
const sub = () => SUBS[state.kind].find((s) => s.key === state.sub) ?? SUBS[state.kind][0];

let api, $, W = null, state = null, words = null, cssReady = Promise.resolve();
const T = () => STR[api.lang() === "en" ? "en" : "zh"];
const root = document.documentElement;

async function loadWords() {
  if (words) return words;
  try { words = await fetch(new URL("./data/plan-names.json", import.meta.url)).then((r) => r.json()); }
  catch { words = { zh: ["奇思妙想"], en: ["haiku"] }; }
  return words;
}
function suggestion() {
  const t = T(), now = new Date(), list = words?.[api.lang() === "en" ? "en" : "zh"] ?? [];
  const word = list.length ? list[state.seed % list.length] : (api.lang() === "en" ? "haiku" : "奇思妙想");
  return t.suggest(t.months[now.getMonth()], now.getDate(), word);
}

// ---------------------------------------------------------------- the disc dial
// Drawn in units of the half disc's radius (100), centred on the sheet's top edge. Angles are taken
// from straight down, positive to the left, so a key's text turns with the ring.
const R = 100, RING1 = [110, 150], RING2 = [158, 198], GAP = 6;
const INNER = [75, 45, 15, -15, -45, -75];            // six keys of 30 degrees: blank, DVD, CD, BD, blank, blank
const INNER_KIND = { 45: "dvd", 15: "cd", "-15": "bd" };
const OUTER = [[84, 50], [50, 16], [16, -18]];        // the types, from the left
const xy = (r, a) => [-r * Math.sin(a * Math.PI / 180), r * Math.cos(a * Math.PI / 180)];
function keyPath([r0, r1], a0, a1) {
  const g0 = (GAP / 2 / r0) * 180 / Math.PI, g1 = (GAP / 2 / r1) * 180 / Math.PI;
  const [p, q, s, u] = [xy(r1, a0 - g1), xy(r1, a1 + g1), xy(r0, a1 + g0), xy(r0, a0 - g0)];
  const f = (n) => n.toFixed(2);
  return `M${f(p[0])} ${f(p[1])}A${r1} ${r1} 0 0 0 ${f(q[0])} ${f(q[1])}L${f(s[0])} ${f(s[1])}A${r0} ${r0} 0 0 1 ${f(u[0])} ${f(u[1])}Z`;
}
function keyMarkup(ring, a0, a1, text, data) {
  const mid = (a0 + a1) / 2, [x, y] = xy((ring[0] + ring[1]) / 2, mid);
  const attrs = data ? `class="np-key" role="radio" tabindex="-1" ${data}` : `class="np-key blank" aria-hidden="true"`;
  return `<g ${attrs}><path d="${keyPath(ring, a0, a1)}"/>${text ? `<text transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${mid})" dy=".36em">${text}</text>` : ""}</g>`;
}
function dialMarkup() {
  const inner = INNER.map((c) => {
    const kind = INNER_KIND[c];
    return keyMarkup(RING1, c + 15, c - 15, kind ? KIND_KEY[kind] : "", kind ? `data-kind="${kind}"` : "");
  }).join("");
  const half = `M${-R} 0A${R} ${R} 0 0 0 ${R} 0Z`;
  return `<svg class="np-dial-svg" viewBox="-205 -2 410 207" aria-hidden="false">
    <defs><clipPath id="np-half"><path d="${half}"/></clipPath></defs>
    <path class="np-disc" d="${half}"/>
    <g clip-path="url(#np-half)"><g class="np-face">
      <circle class="np-hub" r="38"/><circle class="np-hole" r="20"/>
      <text class="np-face-text" y="70"></text></g></g>
    <g class="np-ring1" role="radiogroup">${inner}</g>
    <g class="np-ring2" role="radiogroup"></g>
  </svg>`;
}
function paintDial(turn = 0) {
  const t = T(), svg = W.dial;
  svg.querySelector(".np-ring1").setAttribute("aria-label", t.kinds);
  const ring2 = svg.querySelector(".np-ring2");
  ring2.setAttribute("aria-label", t.subs);
  ring2.innerHTML = SUBS[state.kind].map((s, i) => keyMarkup(RING2, OUTER[i][0], OUTER[i][1], s.key, `data-sub="${s.key}"`)).join("");
  for (const k of svg.querySelectorAll(".np-key:not(.blank)")) {
    const on = k.dataset.kind ? k.dataset.kind === state.kind : k.dataset.sub === sub().key;
    k.classList.toggle("on", on);
    k.setAttribute("aria-checked", String(on));
    k.setAttribute("tabindex", on ? "0" : "-1");
    k.setAttribute("aria-label", k.dataset.kind ? KIND_KEY[k.dataset.kind] : SUBS[state.kind].find((s) => s.key === k.dataset.sub).label);
  }
  svg.querySelector(".np-face-text").textContent = sub().label;
  if (turn) {
    const face = svg.querySelector(".np-face");
    face.classList.remove("turn-up", "turn-down"); void face.getBBox();
    face.classList.add(turn > 0 ? "turn-down" : "turn-up");
  }
}
function setKind(kind, turn = 0) {
  if (kind === state.kind) return;
  turn ||= KINDS.indexOf(kind) > KINDS.indexOf(state.kind) ? 1 : -1;
  state.kind = kind;
  state.sub = SUBS[kind].find((s) => s.key === "-R")?.key ?? SUBS[kind][0].key;
  paintDial(turn); fillBatches(); words_();
}
function setSub(key, turn = 0) {
  if (key === state.sub) return;
  const list = SUBS[state.kind], at = (k) => list.findIndex((s) => s.key === k);
  turn ||= at(key) > at(sub().key) ? 1 : -1;
  state.sub = key;
  paintDial(turn);
  fillBatches();
}
function stepDial(group, dir) {
  if (group === "kind") setKind(KINDS[(KINDS.indexOf(state.kind) + dir + KINDS.length) % KINDS.length], dir);
  else {
    const list = SUBS[state.kind], i = list.findIndex((s) => s.key === sub().key);
    setSub(list[(i + dir + list.length) % list.length].key, dir);
  }
  W.dial.querySelector(`.${group === "kind" ? "np-ring1" : "np-ring2"} .np-key.on`)?.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- the page
function build() {
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = new URL("./newplan.css", import.meta.url).href;
  cssReady = new Promise((ok) => { css.onload = ok; css.onerror = ok; });    // shown only once styled
  document.head.append(css);
  // the page's own back and next buttons (top left, bottom right) belong to this page while it is up
  $("back").addEventListener("click", (e) => { if (!isOn()) return; e.stopImmediatePropagation(); back(); }, { capture: true });
  $("next").addEventListener("click", (e) => { if (!isOn()) return; e.stopImmediatePropagation(); next(); }, { capture: true });
  W = document.createElement("section");
  W.className = "np"; W.hidden = true;
  W.innerHTML = `
    <div class="np-desk" aria-hidden="true"><div class="np-scene"></div></div>
    <h1 class="np-title"></h1>
    <div class="np-env-back" aria-hidden="true"></div>
    <form class="np-sheet" autocomplete="off" novalidate>
      <div class="np-head"></div>
      <div class="np-dial">${dialMarkup()}</div>
      <label class="np-field np-first"><span class="np-label np-name-label"></span>
        <span class="np-input"><input class="np-name" name="name" spellcheck="false"><kbd class="np-tab">Tab</kbd></span>
        <small class="np-help np-name-help"></small></label>
      <label class="np-field"><span class="np-label np-disc-label"></span>
        <select class="np-batch" name="batch"></select>
        <small class="np-help"><span class="np-disc-help"></span><span class="np-left"></span></small></label>
      <p class="np-cal" hidden><span class="np-cal-text"></span><button type="button" class="np-cal-go"></button></p>
      <button type="button" class="np-pack"></button>
    </form>
    <div class="np-env-front" aria-hidden="true"></div>
    <div class="np-toast" role="status"></div>`;
  document.body.append(W);
  // the letterhead: the folded wordmark (the header's own markup, so the half-disc P is the same one)
  // and the release after it
  const mark = document.createElement("div");
  mark.className = "wordmark np-wm"; mark.setAttribute("aria-hidden", "true");
  for (const n of $("wordmark").childNodes) if (!n.classList?.contains("wm-ver")) mark.append(n.cloneNode(true));
  const ver = document.createElement("small");
  ver.className = "np-ver"; ver.textContent = $("wm-ver").textContent;
  W.querySelector(".np-head").append(mark, ver);
  const q = (s) => W.querySelector(s);
  Object.assign(W, { q, sheet: q(".np-sheet"), name: q(".np-name"), batch: q(".np-batch"), dial: q(".np-dial-svg"), toast: q(".np-toast") });
  W.name.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey && !W.name.value) { e.preventDefault(); W.name.value = suggestion(); W.name.select(); }
    if (e.key === "Enter") { e.preventDefault(); next(); }
  });
  W.dial.addEventListener("click", (e) => {
    const k = e.target.closest(".np-key:not(.blank)");
    if (!k) return;
    if (k.dataset.kind) setKind(k.dataset.kind); else setSub(k.dataset.sub);
  });
  // the wheel turns the ring under the pointer; the arrow keys move along the focused ring
  W.dial.addEventListener("wheel", (e) => {
    e.preventDefault();
    stepDial(e.target.closest(".np-ring2") ? "sub" : "kind", e.deltaY > 0 ? 1 : -1);
  }, { passive: false });
  W.dial.addEventListener("keydown", (e) => {
    const k = e.target.closest(".np-key");
    if (!k) return;
    const dir = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (dir) { e.preventDefault(); stepDial(k.dataset.kind ? "kind" : "sub", dir); }
  });
  W.batch.addEventListener("change", () => { state.picked = chosen(); paintLeft(); });
  q(".np-cal-go").addEventListener("click", calibrateFirst);
  q(".np-pack").addEventListener("click", () => toast(T().soon));
  W.sheet.addEventListener("submit", (e) => { e.preventDefault(); next(); });
}
function toast(text) {
  W.toast.textContent = text; W.toast.classList.add("on");
  clearTimeout(W.toastT); W.toastT = setTimeout(() => W.toast.classList.remove("on"), 2400);
}
function words_() {
  const t = T(), q = W.q;
  q(".np-title").textContent = t.title;
  q(".np-name-label").textContent = t.name; q(".np-name-help").textContent = t.nameHelp;
  q(".np-disc-label").textContent = t.disc; q(".np-disc-help").textContent = t.discHelp;
  q(".np-pack").textContent = t.newPack + " ↗";
  q(".np-cal-go").textContent = t.calGo + " ↗";
  q(".np-tab").title = t.tab;
  W.name.placeholder = suggestion();
  $("next-text").textContent = t.next;
}
const held = () => api.heldDisc?.() ?? "";
const isHeld = (it) => { const h = held(); return !!h && (it.name === h || it.name?.startsWith(h + " ")); };
function fillBatches() {
  const t = T(), brand = (n) => api.T().brand?.(n) ?? n;
  state.list = api.catalogue(state.kind).filter((it) => sub().re.test(it.name ?? ""));
  W.batch.replaceChildren();
  const add = (value, text) => { const o = document.createElement("option"); o.value = value; o.textContent = text; W.batch.append(o); };
  add("", state.list.length ? t.later : `${t.later}（${t.none(sub().label)}）`);   // always on top: the drive may hold no disc yet
  state.list.forEach((it, i) => add(String(i), isHeld(it) ? t.inDrive(brand(it.name)) : brand(it.name)));
  // what was picked here stays picked (coming back from calibrating); else the disc in the drive, else the last batch
  const picked = state.list.indexOf(state.picked), inDrive = state.list.findIndex(isHeld), last = state.list.indexOf(state.item);
  W.batch.value = String([picked, inDrive, last].find((i) => i >= 0) ?? "");
  paintLeft();
}
function chosen() {
  const v = W.batch.value;
  return v === "" ? null : state.list[Number(v)] ?? null;
}
function paintLeft() {
  const it = chosen(), t = T();
  W.q(".np-left").textContent = it && Number.isFinite(it.left) && Number.isFinite(it.of) ? t.left(it.left, it.of) : "";
  // calibrated or not: a batch with a measurement has its date; one without offers the detour
  const cal = W.q(".np-cal");
  cal.hidden = !it;
  if (!it) return;
  cal.classList.toggle("ok", !!it.last);
  W.q(".np-cal-text").textContent = it.last ? t.calOk(it.last) : t.calNone;
  W.q(".np-cal-go").hidden = !!it.last;
}
// the detour: calibrate this batch, then come back to the form as it was
async function calibrateFirst() {
  const item = chosen();
  if (!item || going) return;
  state.picked = item;
  const cal = await import("./calibrate.js");
  api.useForPlan(state.kind, item);
  W.hidden = true;
  cal.start(api, { returnTo: () => reopen() });
}
function reopen() {
  root.dataset.mode = "newplan";
  $("back").hidden = false; $("next").disabled = false;
  W.classList.remove("leaving", "filing");
  W.hidden = false;
  paintDial(); fillBatches(); words_();
  if (!api.reduce) W.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, easing: "ease-out" });
  W.q(".np-cal-go:not([hidden])")?.focus({ preventScroll: true });
}
// the type the page opens on: that of the disc in the drive, else of the last batch used, else -R
function firstSub(kind, item) {
  const name = (held() && KINDS.find((k) => SUBS[k].some((s) => s.re.test(held()))) === kind ? held() : item?.name) ?? "";
  return (SUBS[kind].find((s) => s.re.test(name)) ?? SUBS[kind].find((s) => s.key === "-R") ?? SUBS[kind][0]).key;
}

// ---------------------------------------------------------------- in and out
const wait = (ms) => new Promise((r) => setTimeout(r, api.reduce ? 0 : ms));
export async function start(homeApi, { from = null, file = null } = {}) {
  api = homeApi; $ = api.$;
  await loadWords();
  if (!W) build();
  await cssReady;
  const [col, item] = api.lastBatch();
  const kind = KINDS.includes(col) ? col : "dvd";
  state = { kind, sub: firstSub(kind, item), item, picked: null, file, list: [], seed: Math.floor(Math.random() * 1e6) };
  W.name.value = "";
  paintDial(); fillBatches(); words_();
  root.dataset.mode = "newplan";
  $("back").hidden = false; $("next").disabled = false;
  W.hidden = false;
  W.classList.remove("leaving", "filing");
  // the zoom: the page grows out of the drive in the lobby
  const r = from?.getBoundingClientRect?.();
  if (r && !api.reduce) {
    const sx = r.width / innerWidth, x = r.left + r.width / 2 - innerWidth / 2, y = r.top + r.height / 2 - innerHeight / 2;
    W.animate([{ transform: `translate(${x}px, ${y}px) scale(${Math.max(sx, 0.15)})`, opacity: 0 }, { transform: "none", opacity: 1 }],
      { duration: 650, easing: "cubic-bezier(.2, .8, .2, 1)" });
  }
  setTimeout(() => W.name.focus({ preventScroll: true }), api.reduce ? 0 : 500);
}
function leave() {
  W.hidden = true;
  root.dataset.mode = "";
  $("back").hidden = true;
}
export function back() {
  if (!W || W.hidden) return;
  if (api.reduce) { leave(); api.toLobby(); return; }
  W.animate([{ transform: "none", opacity: 1 }, { transform: "scale(.6)", opacity: 0 }], { duration: 320, easing: "ease-in" })
    .finished.then(() => { leave(); api.toLobby(); });
}
// Where the envelope stops and how the sheet goes in, measured from the page as it is laid out.
// Envelope picture (envelope.json): 1600 x 1541, pocket top 27.3 % down, its front ends 6 % above the
// picture's bottom. Paper picture: the sheet sits 60 px inside a 1400 px wide picture.
function fileInto() {
  const r = W.sheet.getBoundingClientRect(), m = r.width * 60 / 1400;
  const pw = r.width - 2 * m, top = r.top + m, ph = innerHeight - top;      // the paper as seen, cut by the window
  const we = Math.min(pw * .92, innerWidth * .62, innerHeight * .95), eh = we * 1541 / 1600;
  const pocket = innerHeight / 3, depth = eh * (1 - .273 - .06), peek = Math.min(64, depth * .14);
  const s = Math.min((depth + peek) / ph, we * .95 * .9 / pw);
  const cx = r.left + r.width / 2;
  const px = (n) => `${n.toFixed(1)}px`;
  W.style.setProperty("--env-w", px(we));
  W.style.setProperty("--env-x", px(cx - we / 2));
  W.style.setProperty("--env-y", px(pocket - .273 * eh));
  W.style.setProperty("--file-x", px(cx - pw * s / 2 - m * s - r.left));
  W.style.setProperty("--file-y", px(pocket - peek - m * s - r.top));
  W.style.setProperty("--file-s", s.toFixed(4));
}
let going = false;
async function next() {
  if (going) return;
  going = true;
  const name = W.name.value.trim() || suggestion(), item = chosen();
  // the envelope rises, the sheet slides in, both drop out of the frame
  fileInto();
  W.classList.add("filing");
  await wait(1000);
  W.classList.add("leaving");
  await wait(600);
  const design = await import("./design.js");
  api.useForPlan(state.kind, item);
  leave();
  W.classList.remove("filing", "leaving");
  design.start(api, { newPlan: true, fly: false, file: state.file, name, dropIn: true, noDisc: !item });
  going = false;
}
export const isOn = () => !!W && !W.hidden;
