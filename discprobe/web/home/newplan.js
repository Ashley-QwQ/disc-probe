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
    title: "新作品", name: "作品名", nameHelp: "这件作品叫什么", tab: "Tab 采用",
    disc: "所使用的光盘", discHelp: "光盘的型号与批次", later: "先不填", inDrive: (n) => `驱内：${n}`,
    left: (l, o) => `还剩 ${l} / ${o} 张`, newPack: "新开一包 · 登记", kinds: "盘的种类", subs: "盘的类型",
    next: "下一步：放进图片", none: (k) => `还没有登记过 ${k}`,
    calOk: (d) => `已标定 · ${d}`, calNone: "这批盘还没标定。刻录前要先标定，也可以先画，刻录前再标。", calGo: "先去标定",
    calUnknown: (cd) => cd ? "要刻图，先用这批盘标定（至少 3 张同批空白盘，精细标定还要在 DIS 里做）；也可以先画，回头再标。" : "要刻图，先用这批盘标定一次（约一小时，至少两张同批空白盘，可能三张）；也可以先画，回头再标。",
    calEmpty: (k) => `还没有标定过的 ${k}。要刻图，先放一张这种空白盘进光驱，标定一次；也可以先画，回头再标。`,
    months: ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"],
    suggest: (m, d, w) => `${m}${d} 的 ${w}`, soon: "这一项以后接上",
    reading: "正在读光驱里的盘…", readFail: "没读到光驱里的盘，可以手动选。", trayOpen: "光驱托盘开着。",
    noDisc: "光驱里没有盘。", unknownBatch: (k, m) => `光驱里是 ${k}${m ? `（${m}）` : ""}，盘库里还没有这一批。`,
  },
  en: {
    title: "New work", name: "Name", nameHelp: "What is this work called?", tab: "Tab to use",
    disc: "Discs", discHelp: "Disc model and batch", later: "Decide later", inDrive: (n) => `In the drive: ${n}`,
    left: (l, o) => `${l} / ${o} left`, newPack: "Opened a new pack? Register it", kinds: "Disc kind", subs: "Disc type",
    next: "Next: add a picture", none: (k) => `No ${k} registered yet`,
    reading: "Reading the disc in the drive…", readFail: "Couldn't read the drive; choose by hand.", trayOpen: "The drive's tray is open.",
    noDisc: "No disc in the drive.", unknownBatch: (k, m) => `The drive holds a ${k}${m ? ` (${m})` : ""}; this batch isn't in the library yet.`,
    calOk: (d) => `Calibrated · ${d}`, calNone: "This batch isn't calibrated yet. It must be before burning; you can draw first and calibrate then.", calGo: "Calibrate first",
    calUnknown: (cd) => cd ? "To burn a picture, calibrate this batch first (at least 3 blanks from it; fine calibration is still done in DIS); or draw first and calibrate later." : "To burn a picture, calibrate this batch once (about an hour; at least two blanks from it, maybe three); or draw first and calibrate later.",
    calEmpty: (k) => `No ${k} has been calibrated yet. To burn a picture, put a blank of this kind in the drive and calibrate once; or draw first and calibrate later.`,
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
  W.batch.addEventListener("change", () => { state.touched = true; state.picked = chosen(); paintLeft(); });
  pullable();
  q(".np-cal-go").addEventListener("click", calibrateFirst);
  q(".np-pack").hidden = true;          // registering a new pack is not wired to the core yet: no dead button
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
  q(".np-disc-label").textContent = t.disc; q(".np-disc-help").textContent = state.discLine?.(t) ?? t.discHelp;
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
  state.list = api.catalogue(state.kind).filter((it) => subOf(state.kind, it) === sub().key);
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
// No batch picked: is there one that needs calibrating first? The disc in the drive when it is of this kind
// and not in the library, else none at all of this kind. Either way the detour starts on the new-disc place.
function unlisted() {
  const d = api.driveDisc?.();
  if (d?.present && d.media === state.kind && !state.list.some(isHeld)) return { kind: shortKind(d.kind) || KIND_KEY[d.media] || "?", mid: d.mid };
  return null;
}
function paintLeft() {
  const it = chosen(), t = T();
  W.q(".np-left").textContent = it && Number.isFinite(it.left) && Number.isFinite(it.of) ? t.left(it.left, it.of) : "";
  // calibrated or not: a batch with a measurement has its date; one without offers the detour
  const cal = W.q(".np-cal");
  if (!it) {
    const u = unlisted(), measured = state.list.some((x) => ["good", "usable"].includes(x.s));
    cal.hidden = !u && measured;
    cal.classList.remove("ok");
    W.q(".np-cal-text").textContent = u ? t.calUnknown(state.kind === "cd") : t.calEmpty(sub().label);
    W.q(".np-cal-go").hidden = false;
    return;
  }
  cal.hidden = false;
  cal.classList.toggle("ok", !!it.last);
  W.q(".np-cal-text").textContent = it.last ? t.calOk(it.last) : t.calNone;
  W.q(".np-cal-go").hidden = !!it.last;
}
// the detour: calibrate this batch, then come back to the form as it was.
// The sheet goes into the envelope as on "next"; then the camera moves right along the desk: this page (drive,
// envelope) leaves to the left while the calibration page (its desk, drive and paper) comes in from the right.
const PAN_IN = ".cal-stage, .ld";                // the calibration page's scene; its card comes out of the envelope after
const LAID = "#cal-ruler";                       // on the glass: does not travel with the scene; laid down after
async function calibrateFirst() {
  const item = chosen();          // none: the batch to calibrate is the one in the drive (the new-disc place)
  if (going) return;
  going = true;
  state.picked = item;
  const pan = !api.reduce;
  const calibrating = import("./calibrate.js");
  if (pan) { W.resetPull?.(); fileInto(); W.classList.add("filing"); await wait(1000); }
  const cal = await calibrating;
  api.useForPlan(state.kind, item);
  if (pan) root.classList.add("pan-in");                      // its layers wait off to the right
  let panned = false;
  const shown = cal.start(api, { returnTo: ({ id } = {}) => {
    // the batch just calibrated, by its library entry (its name may not match the disc in the drive)
    const saved = id && api.catalogue(state.kind).find((x) => x.id === id);
    if (saved) { state.picked = saved; state.sub = subOf(state.kind, saved); }
    reopen({ unfile: panned });
  }, returnAnim: pan ? (finish) => { panned = true; return panBack(finish); } : null });
  if (pan) {
    await Promise.race([shown, wait(1500)]);
    const opt = { duration: 760, easing: "cubic-bezier(.65, 0, .35, 1)" };
    const coming = [...document.querySelectorAll(PAN_IN)].map((el) => el.animate([{ translate: "100vw 0" }, { translate: "0 0" }], { ...opt, fill: "forwards" }));
    const going_ = W.animate([{ transform: "none" }, { transform: "translateX(-100vw)" }], { ...opt, fill: "forwards" });
    await Promise.all([going_.finished, ...coming.map((a) => a.finished)]).catch(() => {});
    root.classList.remove("pan-in");
    W.hidden = true; going_.cancel(); coming.forEach((a) => a.cancel());
    // the ruler comes down onto the glass (its shadow grows from nothing as it settles); the card comes out of
    // the envelope, the filing played backwards with the calibration's words on the sheet
    for (const el of document.querySelectorAll(LAID))
      el.animate([{ opacity: 0, transform: "translate(10px, -14px)" }, { opacity: 1, transform: "translate(0, 0)" }],
        { duration: 320, easing: "cubic-bezier(.2, .8, .2, 1)", composite: "add" });     // on top of the element's own placing
    await cardOut($("cal"));
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
  const anims = [back.animate(env, { duration: T }), front.animate(env, { duration: T }),
    card.animate(sheet, { duration: T, composite: "add" })];
  await Promise.all(anims.map((a) => a.finished)).catch(() => {});
  back.remove(); front.remove();
}
// ... and back in: the envelope rises under the card, the card slides down into the pocket; both stay (they leave
// with the scene). Returns what to move and to clean up.
async function cardIn(card) {
  const { back, front, dy, px } = envelopeFor(card);
  const T = 1000;
  const env = [{ transform: "translateY(110vh)", easing: RISE }, { transform: "none", offset: .5 }, { transform: "none" }];
  const sheet = [{ transform: "translateY(0)" }, { transform: "translateY(0)", offset: .42, easing: SLIDE }, { transform: `translateY(${px(dy)})` }];
  const anims = [back.animate(env, { duration: T, fill: "forwards" }), front.animate(env, { duration: T, fill: "forwards" }),
    card.animate(sheet, { duration: T, composite: "add", fill: "forwards" })];
  await Promise.all(anims.map((a) => a.finished)).catch(() => {});
  return { parts: [back, front], anims };
}
// From calibration back to this page, the way it came, backwards: the card into its envelope, the camera pans left
// (the calibration desk with the envelope leaves to the right, this page comes in from the left with its sheet in
// its envelope), and the sheet comes out while the envelope drops away. finish(): calibrate.js closes its page and
// hands back (reopen).
async function panBack(finish) {
  const card = $("cal"), ruler = document.getElementById("cal-ruler");
  ruler?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, fill: "forwards" });
  const inEnv = card && !card.hidden ? await cardIn(card) : { parts: [], anims: [] };
  // this page, filed, waiting off to the left (measured where it stands, then moved)
  W.hidden = false;
  W.classList.add("instant");
  fileInto(); W.classList.add("filing");
  W.getBoundingClientRect();
  W.classList.remove("instant");
  const opt = { duration: 760, easing: "cubic-bezier(.65, 0, .35, 1)", fill: "forwards" };
  const leaving = [...document.querySelectorAll(PAN_IN), card, ...inEnv.parts].filter(Boolean)
    .map((el) => el.animate([{ translate: "0 0" }, { translate: "100vw 0" }], opt));
  const coming = W.animate([{ transform: "translateX(-100vw)" }, { transform: "none" }], opt);
  await Promise.all([coming.finished, ...leaving.map((a) => a.finished)]).catch(() => {});
  finish();                                               // calibration closes; reopen() takes the sheet out
  coming.cancel(); leaving.forEach((a) => a.cancel()); inEnv.anims.forEach((a) => a.cancel());
  inEnv.parts.forEach((p) => p.remove()); ruler?.getAnimations().forEach((a) => a.cancel());
}
function reopen({ unfile = false } = {}) {
  root.dataset.mode = "newplan";
  sceneScale();
  $("back").hidden = false; $("next").disabled = false;
  if (unfile) {                        // came back panning, filed: the sheet comes out, then the envelope drops
    W.classList.add("unfiling");
    setTimeout(() => W.classList.remove("unfiling"), 1200);
  }
  W.classList.remove("leaving", "filing");
  W.hidden = false;
  paintDial(); fillBatches(); words_();
  if (!api.reduce && !unfile) W.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, easing: "ease-out" });
  W.q(".np-cal-go:not([hidden])")?.focus({ preventScroll: true });
}
// The disc in the drive, read when the form opens (read-only, a second or two): the dial and the batch follow
// it until the person picks a kind or a batch; the line under the batch says what was found.
async function readDrive() {
  if (!api.readDisc) return;
  const help = W.q(".np-disc-help");
  state.discLine = (t) => t.reading;
  help.textContent = T().reading;
  let disc;
  try { disc = await api.readDisc(); }
  catch { disc = undefined; }
  if (!isOn()) return;
  state.discLine = (t) => disc === undefined ? t.readFail : !disc ? t.discHelp : disc.tray === "open" ? t.trayOpen
    : !disc.present ? t.noDisc : held() && state.list.some(isHeld) ? t.discHelp : t.unknownBatch(shortKind(disc.kind) || KIND_KEY[disc.media] || "?", disc.mid);
  if (disc?.present && KINDS.includes(disc.media) && !state.touched) {
    const turn = KINDS.indexOf(disc.media) - KINDS.indexOf(state.kind);
    state.kind = disc.media; state.sub = firstSub(disc.media, state.item); state.picked = null;
    paintDial(Math.sign(turn)); fillBatches();
  }
  help.textContent = state.discLine(T());
}
// the type the page opens on: that of the disc in the drive, else of the last batch used, else -R
function firstSub(kind, item) {
  // the disc in the drive: its batch's type, or its own profile ("DVD-R Sequential")
  const d = api.driveDisc?.(), inDrive = d?.present && d.media === kind ? api.catalogue(kind).find(isHeld) : null;
  if (inDrive) return subOf(kind, inDrive);
  const name = (held() && KINDS.find((k) => SUBS[k].some((s) => s.re.test(held()))) === kind ? held() : item?.name) ?? "";
  return (SUBS[kind].find((s) => s.re.test(name)) ?? SUBS[kind].find((s) => s.key === "-R") ?? SUBS[kind][0]).key;
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
  const [col, item] = api.lastBatch();
  const kind = KINDS.includes(col) ? col : "dvd";
  state = { kind, sub: firstSub(kind, item), item, picked: null, file, list: [], seed: Math.floor(Math.random() * 1e6) };
  W.name.value = "";
  paintDial(); fillBatches(); words_();
  readDrive();
  // the camera flies at the drive: the lobby pushes in with the drive coming to the middle of the window;
  // the top view fades in over it with its disc in the middle and close, then settles (the disc moving
  // left, the sheet coming in)
  const fly = from?.getBoundingClientRect?.().width > 0 && !api.reduce;
  const push = fly ? pushLobby(from) : null;
  if (push) await wait(300);
  root.dataset.mode = "newplan";
  sceneScale();
  $("back").hidden = false; $("next").disabled = false;
  W.hidden = false;
  W.classList.remove("leaving", "filing");
  if (push) {
    const [tx, ty] = discPoint();
    W.style.transformOrigin = `${tx}px ${ty}px`;
    W.animate([{ transform: topStart(), opacity: 0 }, { opacity: 1, offset: .45 }, { transform: "none", opacity: 1 }], { duration: 760, easing: "cubic-bezier(.2, .8, .2, 1)" })
      .finished.finally(() => { push.done(); W.style.transformOrigin = ""; });
  }
  setTimeout(() => W.name.focus({ preventScroll: true }), api.reduce ? 0 : 700);
}
// where the top view has the blank disc (top.json: centre 512, 632.6 of 2560 x 1440), the picture covering the window
function discPoint() {
  const vw = innerWidth, vh = innerHeight, sw = Math.max(vw, vh * 16 / 9), sh = sw * 9 / 16;
  return [(vw - sw) / 2 + sw * 512 / 2560, (vh - sh) / 2 + sh * 632.59 / 1440];
}
const LOBBY_PUSH = 2.6, TOP_START = 1.5;    // how close the lobby camera gets; how close the top view starts
const mid = () => [innerWidth / 2, innerHeight / 2];
const pushTransform = (from) => {
  const r = from.getBoundingClientRect(), [sx, sy] = [r.left + r.width / 2, r.top + r.height / 2], [cx, cy] = mid();
  return { origin: `${sx}px ${sy}px`, to: `translate(${cx - sx}px, ${cy - sy}px) scale(${LOBBY_PUSH})` };
};
// the top view with its disc in the middle of the window, close (origin: the disc)
const topStart = () => { const [tx, ty] = discPoint(), [cx, cy] = mid(); return `translate(${cx - tx}px, ${cy - ty}px) scale(${TOP_START})`; };
// the lobby flying in (or, reversed, back out); it stays drawn under this page until done() (lobby.css .leaving)
function pushLobby(from, reverse = false) {
  const lobby = $("lobby"), art = $("lobby-art"), greet = lobby.querySelector(".lobby-greet");
  lobby.classList.add("leaving");
  const p = pushTransform(from);
  art.style.transformOrigin = p.origin;
  const frames = [{ transform: "none" }, { transform: p.to }], fade = [{ opacity: 1 }, { opacity: 0 }];
  const a = art.animate(reverse ? frames.reverse() : frames, { duration: 560, easing: reverse ? "cubic-bezier(.2, .8, .2, 1)" : "cubic-bezier(.5, 0, .6, 1)", fill: "forwards" });
  const g = greet?.animate(reverse ? fade.reverse() : fade, { duration: reverse ? 400 : 200, fill: "forwards" });
  return { finished: a.finished, done() { a.cancel(); g?.cancel(); art.style.transformOrigin = ""; lobby.classList.remove("leaving"); } };
}
function leave() {
  W.hidden = true;
  root.dataset.mode = "";
  $("back").hidden = true;
}
// back: the same flight backwards, the top view lifting off while the lobby camera pulls back out
export function back() {
  if (!W || W.hidden) return;
  if (api.reduce) { leave(); api.toLobby(); return; }
  const pull = pushLobby($("lobby-new"), true), [tx, ty] = discPoint();
  W.style.transformOrigin = `${tx}px ${ty}px`;
  W.animate([{ transform: "none", opacity: 1 }, { opacity: 1, offset: .55 }, { transform: topStart(), opacity: 0 }], { duration: 520, easing: "cubic-bezier(.5, 0, .9, .5)", fill: "forwards" })
    .finished.then(async () => {
      leave(); api.toLobby();
      W.getAnimations().forEach((a) => a.cancel()); W.style.transformOrigin = "";
      await pull.finished.catch(() => {});
      pull.done();
    });
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
async function next() {
  if (going) return;
  going = true;
  const name = W.name.value.trim() || suggestion(), item = chosen();
  // the envelope rises, the sheet slides in, both drop out of the frame
  W.resetPull?.();
  fileInto();
  W.classList.add("filing");
  const designing = import("./design.js");       // fetched and parsed while the envelope animates
  await wait(1000);
  W.classList.add("leaving");
  await wait(600);
  const design = await designing;
  api.useForPlan(state.kind, item);
  leave();
  W.classList.remove("filing", "leaving");
  design.start(api, { newPlan: true, fly: false, file: state.file, name, dropIn: true, noDisc: !item });
  going = false;
}
export const isOn = () => !!W && !W.hidden;
