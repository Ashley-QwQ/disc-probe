// The new-plan page: what opens when "new work" is clicked in the lobby.
//
// The lobby flies to high above the drive and zooms in; the page is that view: the drive seen from above
// on the left, and on the right a large sheet of paper on the desk, running on under the footer, holding a
// short form: the plan's name (a suggestion taken with Tab), the disc (a half disc hanging from the sheet's
// top edge, with two rings of keys cut from concentric circles below it: the kind DVD / CD / BD on the
// inner ring, the type -R / +R / RW on the outer) and a suggested, editable disc batch. On "next" an
// archive envelope rises from below, the sheet slides into it, and both drop out of the frame while the
// next page comes down from above.
//
// Art: baked renders in ./newplan/ (made by art/newplan/render_newplan.py; positions in newplan.json):
// the drive from above on the lit desk, the paper sheet and its shadow, the envelope's back and front.
// All motion is transform / opacity only.

import * as presets from "./presetio.js";
import { driveTarget, pushLobby } from "./lobby.js";

const STR = {
  zh: {
    title: "新作品", name: "作品名", nameHelp: "这件作品叫什么", tab: "Tab 采用",
    disc: "盘类型 / Disc type", discHelp: "例如：Verbatim DVD-R 16x", noBatch: "没选盘：画好后要刻时再选",
    left: (l, o) => `还剩 ${l} / ${o} 张`, newPack: "新开一包 · 登记", kinds: "盘的种类", subs: "盘的类型",
    next: "下一步：放进图片", library: "去盘库看这批盘",
    calOk: (d) => `已标定 · ${d}`, calNone: "这批还没有参数：可以先画；要刻之前标定一次，或者带上已有参数", calGo: "标定这批",
    months: ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"],
    suggest: (m, d, w) => `${m}${d} 的 ${w}`, soon: "这一项以后接上",
    reading: "正在读光驱里的盘…", readFail: "没读到光驱里的盘，可以手动选。", trayOpen: "光驱托盘开着。",
    noDisc: "光驱里没有盘。",
  },
  en: {
    title: "New work", name: "Name", nameHelp: "What is this work called?", tab: "Tab to use",
    disc: "Disc type", discHelp: "For example: Verbatim DVD-R 16x", noBatch: "No disc selected: choose one when you are ready to burn",
    left: (l, o) => `${l} / ${o} left`, newPack: "Opened a new pack? Register it", kinds: "Disc kind", subs: "Disc type",
    next: "Next: add a picture", library: "View this batch in the library",
    reading: "Reading the disc in the drive…", readFail: "Couldn't read the drive; choose by hand.", trayOpen: "The drive's tray is open.",
    noDisc: "No disc in the drive.",
    calOk: (d) => `Calibrated · ${d}`, calNone: "This batch has no parameters yet: draw first; calibrate before burning, or bring your existing parameters", calGo: "Calibrate this batch",
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
// a batch's type: from its name ("Verbatim DVD-R 16x"); a batch named by its manufacturer code alone goes by
// the code's form: a DVD+R's ADIP code has slashes (MKM/001/00), a DVD-R's pre-recorded one does not
const subOf = (kind, it) => SUBS[kind].find((s) => s.re.test(it.name ?? ""))?.key ?? (kind === "dvd" && /\//.test(it.mid ?? "") ? "+R" : "-R");
// "DVD-R Sequential" -> "DVD-R": the profile's first word is the type people know
const shortKind = (k) => String(k ?? "").split(" ")[0];

let api, $, W = null, state = null, words = null, cssReady = Promise.resolve();
const T = () => STR[api.lang() === "en" ? "en" : "zh"];
const root = document.documentElement;
addEventListener("dp-presets-ready", () => { if (W && state) words_(); });
const motionOff = () => root.dataset.motion === "off" || (root.dataset.motion !== "on" && api.reduce);
const calibrated = (it) => !!it && ["good", "usable"].includes(it.s);
const imported = (it) => it?.imported && it.image_compatible === true;
const hasGeometry = (it) => calibrated(it) || imported(it);
function calibrationNotice() {
  const it = chosen(), zh = api.lang() !== "en";
  if (!it) return T().noBatch;
  const text = calibrated(it) ? T().calOk((it.last || "—").slice(0, 10))
    : imported(it) ? (zh ? "参数来自 DIS（未经 DP 实测）" : "Parameters from DIS (not measured by DP)") : T().calNone;
  return text + (state.kind === "cd" && !it.along_track?.known
    ? (zh ? "；沿轨常数未知" : "; along-track constant unknown") : "");
}

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
let dialFlight = null, nextPending = false;
function clearDialFlight() {
  dialFlight?.anims.forEach(a => a.cancel());
  dialFlight?.copies.forEach(el => el.remove());
  dialFlight = null;
}
new MutationObserver(() => { if (root.dataset.motion === "off") clearDialFlight(); })
  .observe(root, { attributes: true, attributeFilter: ["data-motion"] });
function paintDial(turn = 0) {
  clearDialFlight();
  const t = T(), svg = W.dial;
  svg.querySelector(".np-ring1").setAttribute("aria-label", t.kinds);
  const ring2 = svg.querySelector(".np-ring2");
  const label = svg.querySelector(".np-face-text");
  const oldLabel = turn && !motionOff() ? label.cloneNode(true) : null;
  const oldKeys = oldLabel ? ring2.cloneNode(true) : null;
  ring2.setAttribute("aria-label", t.subs);
  ring2.innerHTML = SUBS[state.kind].map((s, i) => keyMarkup(RING2, OUTER[i][0], OUTER[i][1], s.key, `data-sub="${s.key}"`)).join("");
  for (const k of svg.querySelectorAll(".np-key:not(.blank)")) {
    const on = k.dataset.kind ? k.dataset.kind === state.kind : k.dataset.sub === sub().key;
    k.classList.toggle("on", on);
    k.setAttribute("aria-checked", String(on));
    k.setAttribute("tabindex", on ? "0" : "-1");
    k.setAttribute("aria-label", k.dataset.kind ? KIND_KEY[k.dataset.kind] : SUBS[state.kind].find((s) => s.key === k.dataset.sub).label);
  }
  label.textContent = sub().label;
  if (oldLabel) {
    label.after(oldLabel); ring2.after(oldKeys);
    for (const copy of [oldLabel, oldKeys]) {
      copy.setAttribute("aria-hidden", "true"); copy.style.pointerEvents = "none";
      copy.removeAttribute("role");
      for (const key of copy.querySelectorAll("[tabindex]")) { key.removeAttribute("tabindex"); key.removeAttribute("role"); }
    }
    for (const el of [label, oldLabel]) Object.assign(el.style, { transformBox: "view-box", transformOrigin: "0px 0px" });
    const angle = Math.sign(turn) * 70, opt = { duration: 380, easing: "cubic-bezier(.2,.8,.2,1)", fill: "both" };
    const flight = dialFlight = { copies: [oldLabel, oldKeys], anims: [
      oldLabel.animate([{ transform: "rotate(0deg)", opacity: 1 }, { transform: `rotate(${angle}deg)`, opacity: 0 }], opt),
      label.animate([{ transform: `rotate(${-angle}deg)`, opacity: 0 }, { transform: "rotate(0deg)", opacity: 1 }], opt),
      oldKeys.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, fill: "both" }),
      ring2.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120, fill: "both" }),
    ] };
    Promise.all(flight.anims.map(a => a.finished)).catch(() => {}).then(() => { if (dialFlight === flight) clearDialFlight(); });
  }
}
function setKind(kind, turn = 0) {
  if (kind === state.kind) return;
  turn ||= KINDS.indexOf(kind) > KINDS.indexOf(state.kind) ? 1 : -1;
  state.kind = kind; state.edited = false; state.picked = null; state.newItem = null;
  state.sub = SUBS[kind].find((s) => s.key === "-R")?.key ?? SUBS[kind][0].key;
  paintDial(turn); fillBatches(); words_();
}
function setSub(key, turn = 0) {
  if (key === state.sub) return;
  const list = SUBS[state.kind], at = (k) => list.findIndex((s) => s.key === k);
  turn ||= at(key) > at(sub().key) ? 1 : -1;
  state.sub = key; state.edited = false; state.picked = null; state.newItem = null;
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
  $("back").addEventListener("click", (e) => {
    if (!isOn()) return;
    if (bagFlight) { e.stopImmediatePropagation(); bagFlight.cancel(); return; }
    if (going) return;
    e.stopImmediatePropagation(); back();
  }, { capture: true });
  $("next").addEventListener("click", (e) => { if (!isOn()) return; e.stopImmediatePropagation(); next(); }, { capture: true });
  W = document.createElement("section");
  W.className = "np"; W.hidden = true;
  W.innerHTML = `
    <div class="np-desk" aria-hidden="true"><div class="np-scene"></div></div>
    <h1 class="np-title"></h1>
    <div class="np-env-back" aria-hidden="true"></div>
    <form class="np-sheet" autocomplete="off" novalidate>
      <div class="np-head"></div>
      <div class="np-dial-clip"><div class="np-dial" id="np-dial">${dialMarkup()}</div></div>
      <label class="np-field np-first"><span class="np-label np-name-label"></span>
        <span class="np-input"><input class="np-name" name="name" spellcheck="false"><kbd class="np-tab">Tab</kbd></span>
        <small class="np-help np-name-help"></small></label>
      <div class="np-field"><label class="np-label np-disc-label" for="np-batch"></label>
        <div class="np-batch-control">
          <span class="np-input"><input id="np-batch" class="np-batch" name="batch" spellcheck="false"
            role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="np-matches"
            aria-describedby="np-cal-text np-disc-help"><kbd class="np-tab">Tab</kbd></span>
          <div id="np-matches" class="np-matches" role="listbox" hidden></div>
        </div>
        <div class="np-cal"><span class="np-cal-text" id="np-cal-text"></span>
          <button type="button" class="np-cal-go"></button>
          <span class="np-own"><button type="button" class="np-import"></button><span aria-hidden="true"> · </span><button type="button" class="np-type"></button></span></div>
        <small class="np-help"><span class="np-disc-help" id="np-disc-help"></span><span class="np-left"></span></small>
        <button type="button" class="np-library"></button></div>
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
  q(".np-library").addEventListener("click", () => {
    const it = chosen();
    if (!isLibrary(it) || !api.inspectBatch) return;
    W.hidden = true; root.dataset.mode = "";
    api.inspectBatch(state.kind, it, (kind, item) => {
      if (item) { state.kind = kind; state.sub = subOf(kind, item); state.picked = item; }
      reopen();
    });
  });
  for (const manual of [false, true]) q(manual ? ".np-type" : ".np-import").addEventListener("click", (event) => {
    const opener = event.currentTarget;
    const original = chosen(), formState = state;
    let importedItem = null;
    state.picked = original; state.touched = true;
    if (presets.open(opener, {state: 1, manual, media: state.kind,
      onImported: async (result) => {
        await api.syncState?.();
        if (state !== formState) return;
        const ids = result.written.map(({index}) => result.entries.find((row) => row.index === index))
          .filter((row) => row?.media === state.kind).map((row) => `preset:${row.preset.id}`);
        const item = ids.map((id) => api.catalogue(state.kind).find((it) => it.id === id && imported(it))).find(Boolean);
        importedItem = item;
        if (item) { state.picked = item; state.sub = subOf(state.kind, item); }
        else if (original) state.picked = api.catalogue(state.kind).find((it) => it.id === original.id) ?? original;
        if (root.dataset.mode === "newplan") { paintDial(); fillBatches(); words_(); }
      },
      onClose: () => {
        reopen();
        if (!original && !importedItem) { W.batch.value = ""; state.edited = true; paintLeft(); }
        opener.focus({preventScroll: true});
      },
    })) W.hidden = true;
  });
  addEventListener("dp-lang", () => { if (isOn()) { paintDial(); fillBatches(); words_(); } });
  W.name.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey && !W.name.value) { e.preventDefault(); W.name.value = suggestion(); W.name.select(); }
    if (e.key === "Enter") { e.preventDefault(); next(); }
  });
  W.dial.addEventListener("click", (e) => {
    const k = e.target.closest(".np-key:not(.blank)");
    if (!k) return;
    state.touched = true;
    if (k.dataset.kind) setKind(k.dataset.kind); else setSub(k.dataset.sub);
  });
  // the wheel turns the ring under the pointer; the arrow keys move along the focused ring
  W.dial.addEventListener("wheel", (e) => {
    e.preventDefault(); e.stopPropagation();          // the wheel over the dial turns it, it does not pull the sheet
    state.touched = true;
    stepDial(e.target.closest(".np-ring2") ? "sub" : "kind", e.deltaY > 0 ? 1 : -1);
  }, { passive: false });
  W.dial.addEventListener("keydown", (e) => {
    const k = e.target.closest(".np-key");
    if (!k) return;
    const dir = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (dir) { e.preventDefault(); state.touched = true; stepDial(k.dataset.kind ? "kind" : "sub", dir); }
  });
  W.batch.addEventListener("input", () => {
    state.touched = true; state.edited = true; state.picked = null; state.newItem = null;
    W.batch.placeholder = ""; paintLeft();
    if (W.batch.value.trim()) showMatches(); else hideMatches();
  });
  W.batch.addEventListener("focus", () => { if (W.batch.value) showMatches(); });
  W.batch.addEventListener("blur", hideMatches);
  W.batch.addEventListener("keydown", (e) => {
    if (e.isComposing) return;
    if (e.key === "Tab") {
      if (!e.shiftKey && !W.batch.value && !state.edited && state.suggested) {
        e.preventDefault(); pickBatch(state.suggested); W.batch.select();
      }
      hideMatches();
    } else if (["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      if (W.q(".np-matches").hidden) showMatches();
      const n = state.matches.length;
      if (n) {
        state.active = state.active < 0 ? (e.key === "ArrowDown" ? 0 : n - 1)
          : (state.active + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
        paintMatches();
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (!W.q(".np-matches").hidden && state.active >= 0) pickBatch(state.matches[state.active]);
      else hideMatches();
    } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); hideMatches(); }
  });
  q(".np-matches").addEventListener("pointerdown", (e) => e.preventDefault());
  q(".np-matches").addEventListener("click", (e) => {
    const option = e.target.closest("[data-match]");
    if (option) pickBatch(state.matches[Number(option.dataset.match)]);
  });
  q(".np-matches").addEventListener("wheel", (e) => e.stopPropagation());
  pullable();
  q(".np-cal-go").addEventListener("click", calibrateFirst);
  W.sheet.addEventListener("submit", (e) => { e.preventDefault(); next(); });
}
function toast(text) {
  W.toast.textContent = text; W.toast.classList.add("on");
  clearTimeout(W.toastT); W.toastT = setTimeout(() => W.toast.classList.remove("on"), 2400);
}
function words_() {
  const t = T(), q = W.q;
  q(".np-title").textContent = t.title;
  // printed on the drive's face: the size fits the face whatever the language (CJK ~1.05 em a glyph, Latin ~.62)
  q(".np-title").style.setProperty("--title-em", [...t.title].reduce((n, c) => n + (/[⺀-鿿]/.test(c) ? 1.05 : .62), 0).toFixed(2));
  q(".np-name-label").textContent = t.name; q(".np-name-help").textContent = t.nameHelp;
  q(".np-disc-label").textContent = t.disc;
  q(".np-cal-go").textContent = t.calGo;
  for (const cap of W.querySelectorAll(".np-tab")) cap.title = t.tab;
  q(".np-library").textContent = t.library;
  q(".np-import").textContent = api.lang() === "en" ? "Import from DIS" : "从 DIS 导入";
  q(".np-type").textContent = api.lang() === "en" ? "Type them in" : "手动填写";
  paintLeft();
  W.name.placeholder = suggestion();
  if (!nextPending && root.dataset.mode === "newplan") $("next-text").textContent = t.next;
}
// Keep usage separately from calibration dates. Neither a MID nor a catalogue's order is a brand.
function usage() {
  try {
    const ids = JSON.parse(localStorage.getItem("dp-disc-batches") || "[]");
    return Array.isArray(ids) ? ids : [];
  } catch { return []; }
}
function remember(item) {
  try {
    localStorage.setItem("dp-disc-kind", JSON.stringify([state.kind, state.sub]));
    if (isLibrary(item)) localStorage.setItem("dp-disc-batches", JSON.stringify([item.id, ...usage().filter((id) => id !== item.id)].slice(0, 100)));
  } catch {}
}
const isLibrary = (it) => !!it && state.list.includes(it);
const driveOfKind = () => state.detected?.present && state.detected.media === state.kind ? state.detected : null;
function newBatch(name) {
  const d = driveOfKind();
  const key = JSON.stringify([state.kind, name, d?.mid, d?.kind, d?.sectors]);
  if (state.newItems.has(key)) return state.newItems.get(key);
  // Deliberately no `mid`: export-rules uses that key to look up measured geometry by maker code.
  const item = { id: "new:" + crypto.randomUUID(), kind: "new", row: state.kind, name, s: "none",
    ...(d ? { readMid: d.mid, readKind: d.kind, readSectors: d.sectors } : {}) };
  state.newItems.set(key, item);
  return item;
}
function fillBatches() {
  state.list = api.catalogue(state.kind).filter((it) => (!it.imported || imported(it)) && subOf(state.kind, it) === sub().key);
  const [lastKind, last] = api.lastBatch(), recent = usage();
  let lastId;
  try { lastId = localStorage.getItem("dp-batch"); } catch {}
  const wasLast = (it) => !!lastId && it.id === lastId && lastKind === state.kind && it === last;
  const ordered = [...state.list].sort((a, b) => {
    const rank = (it) => wasLast(it) ? -1 : recent.includes(it.id) ? recent.indexOf(it.id) : Infinity;
    return rank(a) - rank(b);
  });
  const d = driveOfKind();
  state.suggested = d ? ordered.find((it) => d.mid && it.mid?.toLowerCase() === d.mid.toLowerCase())
    ?? newBatch([d.maker || d.manufacturer, shortKind(d.kind) || KIND_KEY[d.media]].filter(Boolean).join(" ") + (d.mid ? `（${d.mid}）` : ""))
    : !state.detected?.present ? ordered.find((it) => wasLast(it) || recent.includes(it.id)) ?? null : null;
  // A detour can return a newly calibrated/imported library entry. Otherwise preserve even an empty edit.
  if (state.picked && state.list.includes(state.picked)) {
    W.batch.value = state.picked.name; state.edited = true;
  } else if (!state.edited) W.batch.value = "";
  W.batch.placeholder = !state.edited ? state.suggested?.name ?? "" : "";
  hideMatches(); paintLeft();
}
function chosen() {
  const name = W.batch.value.trim();
  if (!name) return state.edited ? null : state.suggested;
  if (state.picked?.name === name && isLibrary(state.picked)) return state.picked;
  return state.list.find((it) => it.name.toLowerCase() === name.toLowerCase()) ?? newBatch(name);
}
function pickBatch(it) {
  state.edited = true; state.touched = true; state.picked = isLibrary(it) ? it : null;
  W.batch.value = it.name; W.batch.placeholder = "";
  hideMatches(); paintLeft();
}
function hideMatches() {
  W.q(".np-matches").hidden = true; W.batch.setAttribute("aria-expanded", "false");
  W.batch.removeAttribute("aria-activedescendant");
}
function showMatches() {
  const query = W.batch.value.trim().toLowerCase();
  state.matches = state.list.filter((it) => [it.name, it.mid].some((v) => v?.toLowerCase().includes(query)));
  state.active = -1; paintMatches();
}
function paintMatches() {
  const box = W.q(".np-matches"); box.replaceChildren();
  state.matches.forEach((it, i) => {
    const row = document.createElement("div"); row.id = `np-match-${i}`; row.dataset.match = i;
    row.setAttribute("role", "option"); row.setAttribute("aria-selected", String(i === state.active));
    const name = document.createElement("span"); name.textContent = it.name; row.append(name);
    if (it.mid) { const mid = document.createElement("small"); mid.textContent = it.mid; row.append(mid); }
    box.append(row);
  });
  box.hidden = !state.matches.length; W.batch.setAttribute("aria-expanded", String(!box.hidden));
  if (state.active >= 0) {
    W.batch.setAttribute("aria-activedescendant", `np-match-${state.active}`);
    box.children[state.active]?.scrollIntoView({ block: "nearest" });
  } else W.batch.removeAttribute("aria-activedescendant");
}
function paintLeft() {
  const it = chosen(), t = T(), d = state.detected, zh = api.lang() !== "en";
  if (!nextPending && root.dataset.mode === "newplan") $("next-text").textContent = t.next;
  W.q(".np-library").hidden = !isLibrary(it) || !api.inspectBatch;
  W.q(".np-left").textContent = it && Number.isFinite(it.left) && Number.isFinite(it.of) ? t.left(it.left, it.of) : "";
  W.q(".np-cal").classList.toggle("ok", hasGeometry(it));
  W.q(".np-cal-text").textContent = calibrationNotice();
  W.q(".np-cal-go").hidden = !it || hasGeometry(it);
  W.q(".np-own").hidden = !!it && hasGeometry(it) || !presets.ready();
  const mid = it?.readMid;
  W.q(".np-disc-help").textContent = state.reading ? t.reading : state.readFailed ? t.readFail
    : state.recognised ? (zh ? `光驱里认出的是 ${shortKind(d.kind) || KIND_KEY[d.media]}` : `The drive recognised ${shortKind(d.kind) || KIND_KEY[d.media]}`) + (mid ? ` · ${mid}` : "")
    : !it ? t.discHelp : d?.tray === "open" ? t.trayOpen : d && !d.present ? t.noDisc : t.discHelp;
}
// the detour: calibrate this batch, then come back to the form as it was.
// The sheet goes into the envelope as on "next"; then the camera moves right along the desk: this page (drive,
// envelope) leaves to the left while the calibration page (its desk, drive and paper) comes in from the right.
const PAN_IN = ".cal-stage, .ld";                // the calibration page's scene; its card comes out of the envelope after
const LAID = "#cal-ruler";                       // on the glass: does not travel with the scene; laid down after
let panFlight = null, cardFlight = null;
async function calibrateFirst() {
  const item = chosen();          // none: the batch to calibrate is the one in the drive (the new-disc place)
  if (going) return;
  going = true;
  state.picked = item;
  const pan = !motionOff();
  const calibrating = import("./calibrate.js");
  if (pan && !await bagging(false)) { going = false; return; }
  const cal = await calibrating;
  api.useForPlan(state.kind, isLibrary(item) ? item : null);
  if (pan) root.classList.add("pan-in");                      // its layers wait off to the right
  const flight = pan ? (panFlight = { anims: [], reversing: false }) : null;
  const stillCal = () => root.dataset.mode === "cal" && !flight?.reversing;
  let panned = false;
  const shown = cal.start(withInitialItem(item ? { ...item } : api.current().item), { returnTo: ({ id } = {}) => {
    // the batch just calibrated, by its library entry (its name may not match the disc in the drive)
    const saved = id && api.catalogue(state.kind).find((x) => x.id === id);
    if (saved) { state.picked = saved; state.sub = subOf(state.kind, saved); }
    reopen({ unfile: panned });
  }, returnAnim: pan ? (finish, reverseDisc) => { panned = true; return panBack(finish, reverseDisc); } : null });
  if (pan) {
    await Promise.race([shown, wait(1500)]);
    if (!stillCal()) return;
    const opt = { duration: 760, easing: "cubic-bezier(.65, 0, .35, 1)" };
    const coming = [...document.querySelectorAll(PAN_IN)].map((el) => el.animate([{ translate: "100vw 0" }, { translate: "0 0" }], { ...opt, fill: "forwards" }));
    const going_ = W.animate([{ transform: "none" }, { transform: "translateX(-100vw)" }], { ...opt, fill: "forwards" });
    flight.anims = [going_, ...coming];
    await Promise.all([going_.finished, ...coming.map((a) => a.finished)]).catch(() => {});
    if (!stillCal()) return;
    root.classList.remove("pan-in");
    cal.arrived();
    W.hidden = true; going_.cancel(); coming.forEach((a) => a.cancel());
    panFlight = null;
    // the ruler comes down onto the glass (its shadow grows from nothing as it settles); the card comes out of
    // the envelope, the filing played backwards with the calibration's words on the sheet
    for (const el of document.querySelectorAll(LAID))
      el.animate([{ opacity: 0, transform: "translate(10px, -14px)" }, { opacity: 1, transform: "translate(0, 0)" }],
        { duration: 320, easing: "cubic-bezier(.2, .8, .2, 1)", composite: "add" });     // on top of the element's own placing
    await cardOut($("cal"));
    if (!stillCal() || cardFlight?.reversing) return;
  } else W.hidden = true;
  W.classList.remove("filing", "leaving");
  going = false;
}
// the scene's scale for the glass shadows (index.html --mm): the top view covers the window, 3.455 px/mm at 2560 wide
function sceneScale() {
  if (root.dataset.mode !== "newplan") return;
  root.style.setProperty("--mm", `${(Math.max(innerWidth, innerHeight * 16 / 9) / 2560 * 3.455).toFixed(3)}px`);
}
addEventListener("resize", sceneScale);
// The envelope rises from below the window with the card in its pocket (only its top peeking out), the card slides
// up out of it to its place, and the envelope drops away. The tall envelope's bottom stays below the window.
function envelopeFor(card) {
  const r = card.getBoundingClientRect(), v = root.dataset.theme === "dark" ? "dark" : "paper";
  const we = r.width * 1.12, eh = we * ENV_H, peek = Math.min(56, r.height * .14);
  const pocket = Math.max(r.top + 2 * peek, Math.min(innerHeight * .62, r.bottom + 24));   // the slot while the card is in
  const dy = pocket - peek - r.top;                                                       // how far down the card sits then
  const px = (n) => `${n.toFixed(1)}px`;
  const part = (name) => {
    const e = document.createElement("div");
    Object.assign(e.style, { position: "fixed", zIndex: 2, left: px(r.left + r.width / 2 - we / 2), top: px(pocket - ENV_POCKET * eh),
      width: px(we), height: px(eh), pointerEvents: "none", filter: "var(--envelope-desk-drop)",
      background: `url(${new URL(`./newplan/envelope_${name}_${v}.webp`, import.meta.url).href}) 0 0 / 100% 100% no-repeat` });
    e.setAttribute("aria-hidden", "true");
    return e;
  };
  const back = part("back"), front = part("front");
  card.before(back); card.after(front);                   // back, the card, front: the card is in the pocket
  return { back, front, dy, px };
}
// one timeline, each stretch with its own easing (an easing on the whole would bend the stops)
const RISE = "cubic-bezier(.2, .8, .2, 1)", SLIDE = "cubic-bezier(.45, 0, .25, 1)", DROP = "cubic-bezier(.5, 0, .9, .5)";
async function cardOut(card) {
  if (!card || card.hidden) return;
  const { back, front, dy, px } = envelopeFor(card);
  const T = 1300, rise = RISE, slide = SLIDE, drop = DROP;
  const env = [{ transform: "translateY(110vh)", easing: rise }, { transform: "none", offset: .4 }, { transform: "none", offset: .62, easing: drop },
    { transform: "translateY(120vh)" }];
  const sheet = [{ transform: `translateY(calc(${px(dy)} + 110vh))`, easing: rise }, { transform: `translateY(${px(dy)})`, offset: .4 },
    { transform: `translateY(${px(dy)})`, offset: .46, easing: slide }, { transform: "translateY(0)", offset: .8 }, { transform: "translateY(0)" }];
  const anims = [back.animate(env, { duration: T, fill: "both" }), front.animate(env, { duration: T, fill: "both" }),
    card.animate(sheet, { duration: T, composite: "add", fill: "both" })];
  const flight = cardFlight = { card, parts: [back, front], anims, reversing: false };
  await Promise.all(anims.map((a) => a.finished)).catch(() => {});
  if (flight.reversing) return;                 // cardIn owns the reversed animations and their parts now
  anims.forEach((a) => a.cancel());
  back.remove(); front.remove();
  if (cardFlight === flight) cardFlight = null;
}
// ... and back in: the envelope rises under the card, the card slides down into the pocket; both stay (they leave
// with the scene). Returns what to move and to clean up.
async function cardIn(card, track) {
  if (cardFlight?.card === card) {
    const flight = cardFlight;
    flight.reversing = true;
    flight.anims.forEach((a) => a.reverse());
    track(flight.anims);
    await Promise.all(flight.anims.map((a) => a.finished)).catch(() => {});
    // The reversed envelope has left below the screen. Keep the card tucked away for the pan.
    return flight;
  }
  const { back, front, dy, px } = envelopeFor(card);
  const T = 1000;
  const env = [{ transform: "translateY(110vh)", easing: RISE }, { transform: "none", offset: .5 }, { transform: "none" }];
  const sheet = [{ transform: "translateY(0)" }, { transform: "translateY(0)", offset: .42, easing: SLIDE }, { transform: `translateY(${px(dy)})` }];
  const anims = [back.animate(env, { duration: T, fill: "forwards" }), front.animate(env, { duration: T, fill: "forwards" }),
    card.animate(sheet, { duration: T, composite: "add", fill: "forwards" })];
  track(anims);
  await Promise.all(anims.map((a) => a.finished)).catch(() => {});
  return { parts: [back, front], anims };
}
// From calibration back to this page, the way it came, backwards: the card into its envelope, the camera pans left
// (the calibration desk with the envelope leaves to the right, this page comes in from the left with its sheet in
// its envelope), and the sheet comes out while the envelope drops away. finish(): calibrate.js closes its page and
// hands back (reopen).
let returnFlight = null;
async function panBack(finish, reverseDisc) {
  going = true;
  const returning = returnFlight = { skipped: false, anims: new Set(), disc: new AbortController() };
  const track = anims => {
    for (const a of anims) { returning.anims.add(a); if (returning.skipped) a.finish(); }
  };
  const skip = e => {
    if (e?.type === "keydown" && e.key !== "Enter") return;
    if (e?.target?.closest?.("#back")) return;
    e?.preventDefault(); e?.stopImmediatePropagation();
    returning.skipped = true;
    returning.disc.abort();
    returning.anims.forEach(a => { if (a.playState !== "idle") a.finish(); });
    W.classList.add("instant"); W.classList.remove("unfiling");
  };
  const changed = new MutationObserver(() => { if (motionOff()) skip(); });
  addEventListener("click", skip, true); addEventListener("keydown", skip, true);
  changed.observe(root, { attributes: true, attributeFilter: ["data-motion"] });
  try {
    const disc = reverseDisc?.(returning.disc.signal) ?? Promise.resolve();
    if (panFlight) {
      const flight = panFlight;
      flight.reversing = true;
      flight.anims.forEach((a) => a.reverse());
      track(flight.anims);
      await Promise.all([disc, ...flight.anims.map((a) => a.finished)]).catch(() => {});
      finish();
      flight.anims.forEach((a) => a.cancel());
      root.classList.remove("pan-in");
      panFlight = null;
    } else {
      const card = $("cal"), ruler = document.getElementById("cal-ruler");
      if (ruler) track([ruler.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, fill: "forwards" })]);
      const [inEnv] = await Promise.all([card && !card.hidden ? cardIn(card, track) : { parts: [], anims: [] }, disc]);
      // this page, filed, waiting off to the left (measured where it stands, then moved)
      W.hidden = false;
      W.classList.add("instant");
      fileInto(); W.classList.add("filing");
      W.getBoundingClientRect();
      W.classList.remove("instant");
      const opt = { duration: 760, easing: "cubic-bezier(.65, 0, .35, 1)", fill: "forwards" };
      const leaving = returning.skipped ? [] : [...document.querySelectorAll(PAN_IN), card, ...inEnv.parts].filter(Boolean)
        .map((el) => el.animate([{ translate: "0 0" }, { translate: "100vw 0" }], opt));
      const coming = returning.skipped ? null : W.animate([{ transform: "translateX(-100vw)" }, { transform: "none" }], opt);
      track([coming, ...leaving].filter(Boolean));
      await Promise.all([coming, ...leaving].filter(Boolean).map(a => a.finished)).catch(() => {});
      finish();                                               // calibration closes; reopen() takes the sheet out
      coming?.cancel(); leaving.forEach((a) => a.cancel()); inEnv.anims.forEach((a) => a.cancel());
      inEnv.parts.forEach((p) => p.remove()); ruler?.getAnimations().forEach((a) => a.cancel());
      if (cardFlight === inEnv) cardFlight = null;
    }
    // Keep the skip active for the final extraction as well as the card and camera legs.
    W.getBoundingClientRect();
    const extraction = W.getAnimations({ subtree: true }); track(extraction);
    await Promise.all(extraction.map(a => a.finished)).catch(() => {});
  } finally {
    returning.disc.abort();
    changed.disconnect(); removeEventListener("click", skip, true); removeEventListener("keydown", skip, true);
    returning.anims.forEach(a => a.cancel());
    W.classList.remove("instant", "unfiling"); returnFlight = null;
    going = false;
  }
}
function reopen({ unfile = false } = {}) {
  root.dataset.mode = "newplan";
  sceneScale();
  $("back").hidden = false; $("next").disabled = false;
  if (unfile && !returnFlight?.skipped) { // came back panning, filed: the sheet comes out, then the envelope drops
    W.classList.add("unfiling");
  }
  W.classList.remove("leaving", "filing");
  W.hidden = false;
  paintDial(); fillBatches(); words_();
  if (!motionOff() && !unfile && !returnFlight?.skipped) W.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, easing: "ease-out" });
  W.q(".np-cal-go:not([hidden])")?.focus({ preventScroll: true });
}
// The disc in the drive, read when the form opens (read-only, a second or two): the dial and the batch follow
// it until the person picks a kind or a batch; the line under the batch says what was found.
async function readDrive() {
  if (!api.readDisc) return;
  const readingState = state;
  state.reading = true; paintLeft();
  let disc;
  try { disc = await api.readDisc(); } catch { disc = undefined; }
  if (state !== readingState || !isOn()) return;
  state.reading = false; state.readFailed = disc === undefined;
  state.recognised = !!disc?.present && KINDS.includes(disc.media);
  state.detected = disc;
  if (!state.touched) {
    if (state.recognised) {
      const turn = KINDS.indexOf(disc.media) - KINDS.indexOf(state.kind);
      state.kind = disc.media; state.sub = firstSub(disc.media, state.item); state.newItem = null;
      paintDial(Math.sign(turn));
    }
    fillBatches();
  } else { state.newItem = null; paintLeft(); }
}
// The actual profile wins over the last batch's type. ROM profiles have no recordable subtype.
function firstSub(kind, item) {
  const d = state?.detected ?? api.driveDisc?.();
  const name = d?.present && d.media === kind ? d.kind : item?.name;
  return (SUBS[kind].find((s) => s.re.test(name ?? "")) ?? SUBS[kind].find((s) => s.key === "-R") ?? SUBS[kind][0]).key;
}

// ---------------------------------------------------------------- the pull
// The sheet is paper lying on the desk: the wheel or a drag moves the whole of it (paper and form
// together), against a resistance that grows the further it goes, and it springs back when let go
// (the wheel stopping counts as letting go). Up, it can go most of the way to show what the footer
// covers; down, only a little.
function pullable() {
  const reach = () => ({ up: innerHeight * .42, down: innerHeight * .1 });
  // offered distance d (px, down positive) to where the sheet goes: d at first, then less and less
  const give = (d) => { const L = d < 0 ? reach().up : reach().down; return Math.sign(d) * L * (1 - Math.exp(-Math.abs(d) / L)); };
  let offered = 0, x = 0, v = 0, raf = 0, last = 0, idle = 0, held = false;
  const paint = () => W.sheet.style.setProperty("--pull", `${x.toFixed(2)}px`);
  const run = (t) => {
    const dt = Math.min(.05, (t - (last || t)) / 1000 || 1 / 60); last = t;
    const target = give(offered);
    if (held) { x += (target - x) * Math.min(1, dt * 30); v = 0; }          // following the hand or the wheel
    else { v += (170 * (target - x) - 22 * v) * dt; x += v * dt; }         // a spring back to rest
    paint();
    if (held || Math.abs(target - x) > .3 || Math.abs(v) > .3) raf = requestAnimationFrame(run);
    else { x = target; paint(); raf = 0; last = 0; }
  };
  const go = () => { if (!raf) raf = requestAnimationFrame(run); };
  const letGo = () => { held = false; offered = 0; go(); };
  W.addEventListener("wheel", (e) => {
    if (api.reduce || W.classList.contains("filing")) return;
    e.preventDefault();
    offered -= e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    held = true; go();
    clearTimeout(idle); idle = setTimeout(letGo, 140);
  }, { passive: false });
  // a drag on the paper itself (not on a field, a key or a link)
  W.sheet.addEventListener("pointerdown", (e) => {
    if (api.reduce || e.button !== 0 || e.target.closest("input, select, button, a, .np-key, kbd")) return;
    const y0 = e.clientY;
    let dragging = false;           // a press without moving stays a click (a label still focuses its field)
    const move = (m) => {
      if (!dragging && Math.abs(m.clientY - y0) < 5) return;
      if (!dragging) { dragging = true; W.sheet.setPointerCapture(e.pointerId); held = true; go(); }
      offered = m.clientY - y0;
    };
    const up = () => { W.sheet.removeEventListener("pointermove", move); W.sheet.removeEventListener("pointerup", up); W.sheet.removeEventListener("pointercancel", up); if (dragging) letGo(); };
    W.sheet.addEventListener("pointermove", move);
    W.sheet.addEventListener("pointerup", up);
    W.sheet.addEventListener("pointercancel", up);
  });
  W.resetPull = () => { offered = x = v = 0; held = false; paint(); };
}

// ---------------------------------------------------------------- in and out
const wait = (ms) => new Promise((r) => setTimeout(r, api.reduce ? 0 : ms));
// Everything the page needs before it can fly in: its words, its markup and style, and its pictures for the
// current theme decoded. The lobby calls this when the pointer (or focus) reaches the drive, so the first
// frame of the flight is not spent loading (it was one frame of about a quarter second).
let ready = null, readyTheme = "";
const ART = ["top", "paper", "paper_shadow", "envelope_back", "envelope_front"];
const kept = [];          // the decoded pictures, held so they stay decoded
export function prepare(homeApi) {
  api = homeApi; $ = api.$;
  const theme = root.dataset.theme === "dark" ? "dark" : "paper";
  if (ready && readyTheme === theme) return ready;
  readyTheme = theme;
  ready = (async () => {
    await loadWords();
    if (!W) build();
    await cssReady;
    await Promise.all(ART.map((n) => {
      const img = new Image();
      img.src = new URL(`./newplan/${n}_${theme}.webp`, import.meta.url).href;
      kept.push(img);
      return img.decode().catch(() => {});
    }));
    // Drawn once, invisibly, for a few frames: the graphics card rasterises the big pictures now rather
    // than in the first frame of the flight (where it stalled the flight for about a third of a second).
    if (!W.hidden || api.reduce) return;
    const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    Object.assign(W.style, { opacity: "0.002", pointerEvents: "none" });
    W.hidden = false;
    await frame(); await frame();
    if (root.dataset.mode !== "newplan" && !going) W.hidden = true;      // unless the page was opened (or is panning away) meanwhile
    Object.assign(W.style, { opacity: "", pointerEvents: "" });
  })();
  return ready;
}
export async function start(homeApi, { from = null, file = null } = {}) {
  api = homeApi; $ = api.$;
  await Promise.race([prepare(homeApi), wait(600)]);     // pictures still loading after 0.6 s come in late
  if (!W) build();
  await cssReady;
  nextPending = !!from && !motionOff();
  const [col, item] = api.lastBatch();
  const inDrive = api.driveDisc?.();
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem("dp-disc-kind") || "[]"); } catch {}
  const kind = inDrive?.present && KINDS.includes(inDrive.media) ? inDrive.media : KINDS.includes(saved[0]) ? saved[0] : KINDS.includes(col) ? col : "dvd";
  state = { kind, item, picked: null, file, list: [], newItems: new Map(), edited: false, recognised: !!inDrive?.present && KINDS.includes(inDrive.media),
            detected: inDrive, seed: Math.floor(Math.random() * 1e6) };
  state.sub = !inDrive?.present && saved[0] === kind && SUBS[kind].some((s) => s.key === saved[1]) ? saved[1] : firstSub(kind, item);
  W.name.value = "";
  paintDial(); fillBatches(); words_();
  // the camera flies at the drive: the lobby pushes in with the drive coming to the middle of the window;
  // the top view fades in over it with its disc in the middle and close, then settles (the disc moving
  // left, the sheet coming in)
  const fly = from?.getBoundingClientRect?.().width > 0 && !motionOff();
  leavingBack = false;
  pushOrigin = fly ? pushTransform(from) : null;       // measure before the lobby acquires a transform
  const push = fly ? pushLobby(pushOrigin) : null;
  pushFlight = push;
  if (push) await wait(300);
  root.dataset.mode = "newplan";
  sceneScale();
  $("back").hidden = false; $("next").disabled = false;
  W.hidden = false;
  if (!push) { nextPending = false; $("next-text").textContent = T().next; }
  readDrive();
  W.classList.remove("leaving", "filing");
  if (push) {
    const [tx, ty] = discPoint();
    W.style.transformOrigin = `${tx}px ${ty}px`;
    const transform = W.animate([{ transform: topStart() }, { transform: "none" }],
      { duration: 760, easing: "cubic-bezier(.2, .8, .2, 1)", fill: "both" });
    const opacity = W.animate([{ opacity: 0 }, { opacity: 1, offset: .65 }, { opacity: 1 }],
      { duration: 760, easing: "linear", fill: "both" });
    push.anims.push(transform, opacity);
    if (push.resized) push.anims.forEach(a => a.finish());
    Promise.all(push.anims.map((a) => a.finished)).catch(() => {}).then(() => {
      if (pushFlight !== push || leavingBack) return;
      push.done(); pushFlight = null; W.style.transformOrigin = "";
      nextPending = false;
      if (root.dataset.mode === "newplan") $("next-text").textContent = T().next;
    });
  }
  setTimeout(() => W.name.focus({ preventScroll: true }), api.reduce ? 0 : 700);
}
// where the top view has the blank disc (newplan.json top.disc: centre 512, 720 of 2560 x 1440 since the drive was
// turned round), the picture covering the window
function discPoint() {
  const vw = innerWidth, vh = innerHeight, sw = Math.max(vw, vh * 16 / 9), sh = sw * 9 / 16;
  return [(vw - sw) / 2 + sw * 512 / 2560, (vh - sh) / 2 + sh * 720 / 1440];
}
const TOP_START = 1.5;
const mid = () => [innerWidth / 2, innerHeight / 2];
const pushTransform = (from) => {
  const { x: sx, y: sy, diameter } = driveTarget(from), [cx, cy] = mid();
  const topDiameter = Math.max(innerWidth, innerHeight * 16 / 9) / 2560 * 414.6;
  const lobbyPush = topDiameter * TOP_START / diameter;
  return { origin: `${sx}px ${sy}px`, to: `translate(${cx - sx}px, ${cy - sy}px) scale(${lobbyPush})` };
};
// the top view with its disc in the middle of the window, close (origin: the disc)
const topStart = () => { const [tx, ty] = discPoint(), [cx, cy] = mid(); return `translate(${cx - tx}px, ${cy - ty}px) scale(${TOP_START})`; };
// the lobby flying in (or, reversed, back out); it stays drawn under this page until done() (lobby.css .leaving)
let pushFlight = null, pushOrigin = null, leavingBack = false;
addEventListener("resize", () => {
  pushOrigin = null;
  if (!pushFlight) return;
  pushFlight.resized = true;
  pushFlight.anims.forEach(a => { if (a.playState !== "idle") a.finish(); });
});
function leave() {
  W.hidden = true;
  root.dataset.mode = "";
  $("back").hidden = true;
}
// back: the same flight backwards, the top view lifting off while the lobby camera pulls back out
export async function back() {
  if (!W || W.hidden || leavingBack) return;
  leavingBack = true;
  if (api.reduce) { leave(); api.toLobby(); return; }
  if (pushFlight) {
    const push = pushFlight;
    push.anims.forEach((a) => a.reverse());
    await Promise.all(push.anims.map((a) => a.finished)).catch(() => {});
    leave(); api.toLobby(); push.done(); pushFlight = null;
    W.style.transformOrigin = "";
    return;
  }
  const pull = pushLobby(pushOrigin ?? pushTransform($("lobby-new")), true), [tx, ty] = discPoint();
  W.style.transformOrigin = `${tx}px ${ty}px`;
  const transform = W.animate([{ transform: "none" }, { transform: topStart() }],
    { duration: 520, easing: "cubic-bezier(.5, 0, .9, .5)", fill: "both" });
  const opacity = W.animate([{ opacity: 1 }, { opacity: 1, offset: .35 }, { opacity: 0 }],
    { duration: 520, easing: "linear", fill: "both" });
  await Promise.all([transform.finished, opacity.finished, pull.finished]).catch(() => {});
  leave(); api.toLobby();
  transform.cancel(); opacity.cancel(); W.style.transformOrigin = "";
  pull.done();
}
// Where the envelope stops and how the sheet goes in, measured from the page as it is laid out.
// Envelope picture (envelope.json): 1600 x 2494, pocket top 16.9 % down, its front ends 3.4 % above the
// picture's bottom: a tall bag whose bottom stays below the window. Paper picture: the sheet sits 60 px inside a
// 1400 px wide picture.
const ENV_H = 2494 / 1600, ENV_POCKET = 421.21 / 2494, ENV_FOOT = (2494 - 2408.55) / 2494;
function fileInto() {
  const r = W.sheet.getBoundingClientRect(), m = r.width * 60 / 1400;
  const pw = r.width - 2 * m, top = r.top + m, ph = innerHeight - top;      // the paper as seen, cut by the window
  const we = Math.min(pw * .92, innerWidth * .62), eh = we * ENV_H;
  const pocket = innerHeight / 3, depth = eh * (1 - ENV_POCKET - ENV_FOOT), peek = Math.min(64, depth * .14);
  const s = Math.min((depth + peek) / ph, we * .95 * .9 / pw);
  const cx = r.left + r.width / 2;
  const px = (n) => `${n.toFixed(1)}px`;
  W.style.setProperty("--env-w", px(we));
  W.style.setProperty("--env-x", px(cx - we / 2));
  W.style.setProperty("--env-y", px(pocket - ENV_POCKET * eh));
  W.style.setProperty("--file-x", px(cx - pw * s / 2 - m * s - r.left));
  W.style.setProperty("--file-y", px(pocket - peek - m * s - r.top));
  W.style.setProperty("--file-s", s.toFixed(4));
}
let going = false;
let bagFlight = null;
let bagged = false;
try { bagged = sessionStorage.getItem("dp-bagged") === "1"; } catch {}
async function bagging(drop = true) {
  W.resetPull?.(); fileInto();
  const total = motionOff() ? 0 : bagged ? 400 : 1000;
  if (total) { bagged = true; try { sessionStorage.setItem("dp-bagged", "1"); } catch {} }
  const filing = Math.round(total * .64), leaving = total - filing;
  W.style.setProperty("--bag-file", `${filing}ms`); W.style.setProperty("--bag-drop", `${leaving}ms`);
  let skipped = !total, cancelled = false, timer, wake;
  bagFlight = { cancel() {
    cancelled = true; clearTimeout(timer); wake?.();
    W.classList.remove("filing", "leaving");
  } };
  const skip = (e) => {
    if (e && e.type === "keydown" && e.key !== "Enter") return;
    if (e?.target?.closest?.("#back")) return;
    e?.preventDefault(); e?.stopImmediatePropagation();
    skipped = true; W.classList.add("instant"); clearTimeout(timer); wake?.();
  };
  const pause = ms => skipped || cancelled ? Promise.resolve() : new Promise(r => { wake = r; timer = setTimeout(r, ms); });
  const changed = new MutationObserver(() => { if (motionOff()) skip(); });
  addEventListener("click", skip, true); addEventListener("keydown", skip, true);
  changed.observe(root, { attributes: true, attributeFilter: ["data-motion"] });
  try {
    W.classList.add("filing"); await pause(filing);
    if (drop && !cancelled) { W.classList.add("leaving"); await pause(leaving); }
  } finally {
    clearTimeout(timer); changed.disconnect();
    removeEventListener("click", skip, true); removeEventListener("keydown", skip, true);
    W.classList.remove("instant");
    bagFlight = null;
  }
  return !cancelled;
}
async function next() {
  if (going) return;
  going = true;
  const name = W.name.value.trim() || suggestion(), item = chosen();
  hideMatches(); remember(item);
  // the envelope rises, the sheet slides in, both drop out of the frame
  const designing = import("./design.js");       // fetched and parsed while the envelope animates
  if (!await bagging()) { going = false; return; }
  const design = await designing;
  api.useForPlan(state.kind, item);
  // useForPlan locates only library objects. Supply the form's exact item for the editor's first read,
  // then delegate subsequent reads (e.g. calibration) to the home API as usual.
  // The desk remains under the arriving design sheet; the envelope stays dropped out of frame.
  await design.start(withInitialItem(item), { newPlan: true, fly: false, file: state.file, name, dropIn: true, noDisc: !item });
  W.hidden = true;
  W.classList.remove("filing", "leaving");
  going = false;
}
function withInitialItem(item) {
  let initial = true;
  const home = api, kind = state.kind, handoff = Object.create(home);
  handoff.current = () => {
    const current = home.current();
    if (!initial) return current;
    initial = false; return { ...current, col: kind, item };
  };
  return handoff;
}
export const isOn = () => !!W && !W.hidden;
// the plan's disc as the form stands (tests check it against design/export-rules.mjs)
export const currentItem = () => (W && state ? chosen() ?? null : null);
