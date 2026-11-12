// The archive and the fall share one background, one camera coordinate, and one clock.
// Pure helpers stay importable by plain Node; no DOM or design module is loaded here.
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
const collator = new Intl.Collator("zh-u-co-pinyin", { numeric: true, sensitivity: "base" });
const han = /\p{Script=Han}/u;
export const planName = (p) => p.name || p.item?.name || "未命名作品 / Untitled work";
export function planTime(p) {
  for (const v of [p.updatedAt, p.updated_at, p.modifiedAt, p.createdAt, p.created_at, p.date]) {
    if (v == null || v === "") continue;
    const n = typeof v === "number" ? v : Date.parse(v);
    if (Number.isFinite(n)) return n;
  }
  return null; // In-memory design plans currently have no dates; never invent one.
}
export function sortPlans(plans, order = "time") {
  return plans.map((plan, index) => ({ plan, index })).sort((a, b) => {
    if (order === "name") {
      const an = planName(a.plan), bn = planName(b.plan);
      return Number(!han.test(an[0])) - Number(!han.test(bn[0])) || collator.compare(an, bn) || a.index - b.index;
    }
    // recentPlans() already supplies undated session works newest first. Stable ties retain it.
    return (planTime(b.plan) ?? -Infinity) - (planTime(a.plan) ?? -Infinity) || a.index - b.index;
  }).map(({ plan }) => plan);
}
export const DEPTHS = Object.freeze([
  // low visibility (the person's wish): the paper and its discs are the page; these only give it depth
  Object.freeze({ name: "far", speed: .16, size: 150, opacity: .08, blur: 0 }),
  Object.freeze({ name: "mid", speed: .43, size: 245, opacity: .14, blur: 0 }),
  Object.freeze({ name: "near", speed: .86, size: 370, opacity: .2, blur: 1.2 }),
]);
export const parallax = (camera, depth) => -camera * DEPTHS[depth].speed;
export const layerOffset = (camera, depth, period) => -((camera * DEPTHS[depth].speed % period + period) % period);
export const transitionTiming = (visits = 0, motionOff = false) => motionOff
  ? { push: 0, fall: 0, brake: 0, total: 0 }
  : visits > 0 ? { push: 120, fall: 320, brake: 160, total: 600 }
    : { push: 400, fall: 1000, brake: 500, total: 1900 };
// Integral of a triangular speed curve: accelerate for 2/3, brake for 1/3.
// Position and velocity are continuous at the join; both endpoints have zero speed.
export function fallPosition(progress) {
  const u = clamp(progress), a = 2 / 3;
  return u <= a ? u * u / a : 1 - (1 - u) ** 2 / (1 - a);
}
export function transitionFrame(elapsed, timing) {
  if (!timing.total) return { push: 1, travel: 1, paper: 1, opacity: 1 };
  return {
    push: ease(elapsed / timing.push),
    travel: fallPosition((elapsed - timing.push) / (timing.fall + timing.brake)),
    paper: 1 - (1 - clamp((elapsed - timing.push - timing.fall) / timing.brake)) ** 3,
    opacity: ease((elapsed / timing.push - .5) * 2),
  };
}
// The paper pulled past either end of the list: the drag grows with the square of how far it has gone
// (d over / d pull = 1 / (1 + (over / R)^2)), so it moves freely at first and stiffens fast; let go and it settles back.
// over + over^3 / (3 R^2) = pull, solved for over (odd, monotone, slower than linear).
export const RUBBER_R = 34;
export function rubber(pull, R = RUBBER_R) {
  const p = Math.abs(pull); if (!p) return 0;
  let o = Math.cbrt(3 * R * R * p);                        // the large-pull root, an upper bound; Newton from above
  for (let i = 0; i < 8; i++) o -= (o + o ** 3 / (3 * R * R) - p) / (1 + (o / R) ** 2);
  return Math.sign(pull) * Math.min(o, p);
}
export const unrubber = (over, R = RUBBER_R) => over + over ** 3 / (3 * R * R);
export const backAction = ({ phase, focused }) => phase === "exiting" ? "finish-exit"
  : phase === "entering" ? "reverse" : focused ? "unfocus" : "leave";

const asset = (path) => new URL(path, import.meta.url).href;
let cssReady;
function stylesheet() {
  if (!cssReady) cssReady = new Promise((resolve) => {
    const link = document.createElement("link"); link.rel = "stylesheet";
    link.href = asset("./pastworks.css"); link.onload = resolve; link.onerror = resolve; document.head.append(link);
  });
  return cssReady;
}

export function createPastWorks(api, { host = document.body, thumbnail, openPlan, newWork, onClose } = {}) {
  const root = document.documentElement, $ = api.$ || ((id) => document.getElementById(id));
  const page = document.createElement("section");
  page.className = "pw"; page.hidden = true; page.setAttribute("aria-label", "往期作品 / Past works");
  // .pw-hole: the dark of the box carried into the fall (light below, where the paper waits); under the envelopes
  page.innerHTML = `<div class="pw-background" aria-hidden="true"><div class="pw-hole"></div></div>
    <div class="pw-scroll" tabindex="-1"><article class="pw-paper">
      <header class="pw-heading"><h1>往期作品 <small lang="en">Past works</small></h1><p class="pw-count"></p>
        <div class="pw-sort" role="radiogroup" aria-label="排序 / Sort">
          <button type="button" role="radio" aria-checked="true" data-sort="time">最近 / Newest</button>
          <button type="button" role="radio" aria-checked="false" data-sort="name">名称 / Name</button></div></header>
      <div class="pw-grid"></div><p class="pw-empty" hidden>还没有作品，从第一封开始。 / No works yet. Start with the first envelope.</p>
    </article></div>
    <div class="pw-focus" hidden><div class="pw-focus-paper"></div><div class="pw-focus-art"></div>
      <p class="pw-details" tabindex="-1"></p><button class="pw-open pw-glass" type="button">打开作品 / Open work</button></div>
    <p class="pw-status" role="status" hidden></p>`;
  host.append(page);
  const q = (s) => page.querySelector(s), scroll = q(".pw-scroll"), paper = q(".pw-paper"), grid = q(".pw-grid");
  const focus = q(".pw-focus"), focusArt = q(".pw-focus-art"), details = q(".pw-details"), status = q(".pw-status");
  const controller = new AbortController(), signal = controller.signal;
  let phase = "closed", visits = 0, plans = [], selected = null, selectedButton = null, sortBy = "time";
  let camera = 0, scrollAt = 0, frameId = 0, flightId = 0, flight = null, entry = null, previous = null;
  let dimensions = { w: innerWidth, h: innerHeight, period: innerHeight + 520 };
  let timing = transitionTiming(), elapsed = 0, theme = "", thumbSerial = 0;
  let pull = 0, over = 0, settleId = 0, settleWait = 0, touchY = null;
  const thumbPlans = new Map();
  const layers = DEPTHS.map((d, depth) => {
    const layer = document.createElement("div"); layer.className = `pw-depth pw-${d.name}`;
    layer.style.opacity = `calc(${d.opacity} * var(--pw-lift, 1))`;     // brighter while falling (paintFlight) layer.style.filter = d.blur ? `blur(${d.blur}px)` : "";
    const images = [];
    // Two identical periods. At the wrap the next copy occupies exactly the old one's pixels.
    for (let copy = 0; copy < 2; copy++) for (let i = 0; i < 6; i++) {
      const img = document.createElement("img"); img.alt = ""; img.decoding = "async"; img.draggable = false;
      img.dataset.tumble = String((i + depth * 3) % 10);
      const seed = (i * 37 + depth * 23) % 101;
      const size = d.size * (.78 + seed / 210);
      Object.assign(img.style, { width: `${size}px`, height: `${size}px`, left: `${(i * 31 + depth * 17) % 108 - 12}%` });
      const base = (seed - 50) * .7;
      images.push({ img, i, copy, base, turn: (i % 2 ? 1 : -1) * (.002 + depth * .001) });
      layer.append(img);
    }
    q(".pw-background").append(layer);
    return { layer, images };
  });
  function paintBackground() {
    layers.forEach(({ layer, images }, depth) => {
      layer.style.transform = `translate3d(0, ${layerOffset(camera, depth, dimensions.period).toFixed(3)}px, 0)`;
      for (const { img, base, turn } of images) img.style.transform = `rotate(${(base + camera * turn).toFixed(3)}deg)`;
    });
  }
  function resize() {
    dimensions = { w: innerWidth, h: innerHeight, period: innerHeight + 520 };
    for (const { images } of layers) for (const { img, i, copy } of images)
      img.style.top = `${(copy + i / 6) * dimensions.period - 260}px`;
    if (flight) paintFlight(); else paintBackground();
  }
  function paintTheme() {
    const next = root.dataset.theme === "dark" ? "dark" : "paper";
    if (theme === next) return;
    theme = next;
    for (const { images } of layers) for (const { img } of images) {
      img.onerror = () => { img.onerror = null; img.src = asset(`./newplan/envelope_front_${theme}.webp`); };
      img.src = asset(`./pastworks/tumble_${img.dataset.tumble}_${theme}.webp`);
    }
    for (const img of page.querySelectorAll("[data-envelope]")) img.src = asset(`./pastworks/envelope_${img.dataset.envelope}_${theme}.webp`);
    for (const img of page.querySelectorAll("[data-blank]")) img.src = asset(`./caltop/anim/disc_${theme}.webp`);
    for (const [id, plan] of thumbPlans) fillThumbnail(plan, id);
  }
  function dateText(p) {
    const t = planTime(p);
    return t == null ? "日期未知 / Date unknown" : new Intl.DateTimeFormat(api.lang?.() === "en" ? "en-CA" : "zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(t);
  }
  // the archive bag lying on the paper (pastworks/envelope_*: the new-work page's bag before it grew tall), the
  // work's disc on its pocket, turned a little as a hand would leave it (the same turn every time for a work)
  function envelope(plan) {
    const art = document.createElement("span"); art.className = "pw-envelope";
    const key = plan ? String(plan.id ?? planName(plan)) : "new";
    let h = 0; for (const c of key) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    art.style.setProperty("--turn", `${(h % 41) - 20}deg`);
    art.style.setProperty("--tilt", `${((h >> 6) % 7) - 3}deg`);
    for (const side of ["back", "front"]) {
      const img = document.createElement("img"); img.alt = ""; img.draggable = false; img.decoding = "async";
      img.dataset.envelope = side; img.src = asset(`./pastworks/envelope_${side}_${theme}.webp`); art.append(img);
    }
    if (plan && thumbnail) {
      const disc = document.createElement("img"); disc.className = "pw-disc"; disc.alt = ""; disc.draggable = false;
      art.append(disc);
      // One small cached image per plan; no canvas or projection work in the scroll loop.
      disc.dataset.thumb = String(thumbSerial++);
      thumbPlans.set(disc.dataset.thumb, plan); fillThumbnail(plan, disc.dataset.thumb);
    } else {          // a blank disc (the calibration stage's own disc), waiting for the new work
      const blank = document.createElement("img"); blank.className = "pw-disc pw-blank"; blank.alt = ""; blank.draggable = false;
      blank.dataset.blank = "1"; blank.src = asset(`./caltop/anim/disc_${theme}.webp`); art.append(blank);
    }
    return art;
  }
  function fillThumbnail(plan, id) {
    Promise.resolve().then(() => thumbnail(plan, 256)).then((src) => {
      for (const image of page.querySelectorAll(".pw-disc")) if (image.dataset.thumb === id) image.src = src;
    }).catch(() => {
      for (const image of page.querySelectorAll(".pw-disc")) if (image.dataset.thumb === id) {
        image.parentElement.classList.add("pw-thumbnail-missing"); image.remove();
      }
    });
  }
  function error(message) { status.textContent = message; status.hidden = false; }
  function restoreFlight() {
    const lobby = entry?.lobby, art = entry?.art;
    if (art) { art.style.transform = entry.transform; art.style.transformOrigin = entry.origin; }
    lobby?.classList.remove("leaving", "pw-box-flight");
    if (lobby) { lobby.style.setProperty("--pw-shade", "0"); lobby.inert = entry.inert; }
  }
  function release() {
    page.hidden = true; page.inert = false; phase = "closed";
    cancelAnimationFrame(frameId); cancelAnimationFrame(flightId); frameId = flightId = 0; flight = null;
    restoreFlight();
    if (root.dataset.mode === "pastworks") {
      root.dataset.mode = previous.mode;
      if ($("back")) $("back").hidden = previous.backHidden;
    }
  }
  async function leaveFor(action) {
    if (phase !== "idle" || page.getAttribute("aria-busy") === "true") return;
    page.setAttribute("aria-busy", "true"); q(".pw-open").disabled = true;
    status.hidden = true;
    try { await action(); release(); }
    catch { error("没能打开作品，请重试。 / Could not open the work. Please try again."); }
    finally { page.removeAttribute("aria-busy"); q(".pw-open").disabled = false; }
  }
  function render() {
    grid.replaceChildren(); thumbPlans.clear();
    const fresh = document.createElement("button"); fresh.type = "button"; fresh.className = "pw-cell pw-new";
    fresh.append(envelope(null));
    const label = document.createElement("span"); label.className = "pw-cell-name"; label.innerHTML = `<i class="pw-no">00</i>新作品 <small lang="en">New work</small>`; fresh.append(label);
    fresh.addEventListener("click", () => leaveFor(() => newWork ? newWork() : api.newWork ? api.newWork() : $("lobby-new").click()), { signal });
    grid.append(fresh);
    let n = 0;
    for (const plan of sortPlans(plans, sortBy)) {
      const button = document.createElement("button"); button.type = "button"; button.className = "pw-cell";
      const name = document.createElement("span"), date = document.createElement("time"), no = document.createElement("i");
      no.className = "pw-no"; no.textContent = String(++n).padStart(2, "0");
      name.className = "pw-cell-name"; name.append(no, planName(plan)); date.textContent = dateText(plan);
      if (planTime(plan) != null) date.dateTime = new Date(planTime(plan)).toISOString();
      button.append(envelope(plan), name, date);
      button.addEventListener("click", () => select(plan, button), { signal }); grid.append(button);
    }
    q(".pw-empty").hidden = !!plans.length;
    q(".pw-count").textContent = plans.length ? `共 ${plans.length} 件 · ${plans.length} works` : "";
  }
  function select(plan, button) {
    if (phase !== "idle") return;
    const source = button.querySelector(".pw-envelope"), before = source.getBoundingClientRect();
    selected = plan; selectedButton = button;
    focusArt.replaceChildren(source.cloneNode(true));
    details.textContent = `${planName(plan)} · ${dateText(plan)}`;
    focus.hidden = false; scroll.inert = true; page.classList.add("pw-focused");
    const after = focusArt.firstElementChild.getBoundingClientRect();
    if (!motionOff()) focusArt.firstElementChild.animate([
      { transform: `translate(${before.left - after.left}px, ${before.top - after.top}px) scale(${before.width / after.width})` },
      { transform: "none" },
    ], { duration: 480, easing: "cubic-bezier(.2,.8,.2,1)" });
    details.focus({ preventScroll: true });
  }
  function unfocus() {
    focusArt.firstElementChild?.getAnimations().forEach((a) => a.cancel());
    selected = null; focus.hidden = true; scroll.inert = false; page.classList.remove("pw-focused");
    selectedButton?.focus({ preventScroll: true }); selectedButton = null;
  }
  // the page's own motion setting (index.html: Settings, else the system's)
  const motionOff = () => root.dataset.motion === "off" || (!root.dataset.motion && matchMedia("(prefers-reduced-motion: reduce)").matches);
  function paintFlight() {
    const f = transitionFrame(elapsed, timing), distance = dimensions.h * 7;
    camera = scrollAt - distance * (1 - f.travel); paintBackground();
    page.style.opacity = String(f.opacity);
    page.style.setProperty("--pw-lift", (1 + 1.2 * (1 - f.paper)).toFixed(3));     // the fall shows its envelopes, the landing fades them back
    page.style.setProperty("--pw-hole", (1 - f.paper).toFixed(3));                 // dark while falling, gone when the paper is down
    scroll.style.transform = `translate3d(0, ${(1 - f.paper) * dimensions.h * 1.15}px, 0) rotate(${-(1 - f.paper) * f.paper * 2}deg)`;
    if (entry?.art) {
      const { x, y, width, height } = entry.box;
      const zoom = Math.max(dimensions.w / width, dimensions.h / height);
      entry.art.style.transformOrigin = `${x}px ${y}px`;
      entry.art.style.transform = `translate(${(dimensions.w / 2 - x) * f.push}px, ${(dimensions.h / 2 - y) * f.push}px) scale(${1 + (zoom - 1) * f.push})`;
      entry.lobby.style.setProperty("--pw-shade", String(f.push * .88));
    }
  }
  function finishFlight() {
    const out = flight?.out; flight = null; cancelAnimationFrame(flightId); flightId = 0;
    if (out) {
      release(); api.toLobby?.(); onClose?.(); entry?.from?.focus?.({ preventScroll: true });
    } else {
      elapsed = timing.total; paintFlight(); page.style.opacity = ""; scroll.style.transform = "";
      phase = "idle"; scroll.inert = false; restoreFlight();
      grid.querySelector("button")?.focus({ preventScroll: true });
    }
  }
  function animate(out = false) {
    cancelAnimationFrame(flightId);
    phase = out ? "exiting" : "entering"; scroll.inert = true;
    if (entry?.lobby) { entry.lobby.classList.add("leaving", "pw-box-flight"); entry.lobby.inert = true; }
    flight = { out, last: null };
    if (motionOff() || !timing.total) { finishFlight(); return; }
    const step = (now) => {
      if (!flight) return;
      const dt = flight.last == null ? 0 : now - flight.last; flight.last = now;
      elapsed = clamp(elapsed + (out ? -dt : dt), 0, timing.total); paintFlight();
      if (out ? elapsed <= 0 : elapsed >= timing.total) finishFlight();
      else flightId = requestAnimationFrame(step);
    };
    paintFlight(); flightId = requestAnimationFrame(step);
  }
  function back() {
    if (phase === "closed") return;
    const action = backAction({ phase, focused: !!selected });
    if (action === "finish-exit") finishFlight();
    else if (action === "unfocus") unfocus();
    else if (action === "reverse") animate(true);
    else { timing = transitionTiming(visits > 1 ? 1 : 0); elapsed = timing.total; scrollAt = scroll.scrollTop; animate(true); }
  }
  function skip() {
    if (phase === "loading" && !page.hidden) { flight = { out: false }; finishFlight(); }
    else if (flight) finishFlight();
  }
  const active = () => phase !== "closed" && root.dataset.mode === "pastworks";
  function keydown(e) {
    if (!active() || e.defaultPrevented || e.isComposing) return;
    // Existing settings, shortcut help and terminal keep their own Escape.
    if (document.querySelector('.term:not([hidden]), .keys-help:not([hidden]), #set-menu:not([hidden])')) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); back(); }
    else if (e.key === "Enter" && (flight || phase === "loading")) { e.preventDefault(); e.stopImmediatePropagation(); skip(); }
  }
  window.addEventListener("keydown", keydown, { capture: true, signal });
  window.addEventListener("click", (e) => {
    if (!active() || (!flight && phase !== "loading") || e.target.closest?.("#back")) return;
    e.preventDefault(); e.stopImmediatePropagation(); skip();
  }, { capture: true, signal });
  $("back")?.addEventListener("click", (e) => { if (active()) { e.preventDefault(); e.stopImmediatePropagation(); back(); } }, { capture: true, signal });
  scroll.addEventListener("scroll", () => {
    if (phase !== "idle" || motionOff() || frameId) return;
    frameId = requestAnimationFrame(() => { frameId = 0; camera = scrollAt = scroll.scrollTop; paintBackground(); });
  }, { passive: true, signal });
  // Elastic ends: wheel or finger past the top/bottom slides the paper a little (paper.translate, never the scroll box,
  // which the fall moves); the background stays, as the desk under a sliding sheet would.
  const paintOver = () => { paper.style.translate = Math.abs(over) < .3 ? "" : `0 ${over.toFixed(2)}px`; };
  const atEdge = (push) => {
    const max = scroll.scrollHeight - scroll.clientHeight;
    return push > 0 ? scroll.scrollTop <= 0 : scroll.scrollTop >= max - 1;
  };
  function pullBy(push) {                       // push > 0 pulls the paper down (past the top)
    if (Math.sign(push) === -Math.sign(pull)) { // easing it back toward rest: no extra drag, stop at zero
      pull += push * .45; if (Math.sign(pull) === Math.sign(push)) pull = 0;
    } else pull += push * .45;
    pull = clamp(pull, -500, 500); over = rubber(pull); paintOver();
  }
  function settle() {
    cancelAnimationFrame(settleId); clearTimeout(settleWait);
    let last = null;
    const step = (now) => {
      const dt = last == null ? 16 : now - last; last = now;
      over *= Math.exp(-dt / 85);               // a quick, unbouncy return
      if (Math.abs(over) < .3) over = 0;
      pull = unrubber(over); paintOver();
      settleId = over ? requestAnimationFrame(step) : 0;
    };
    settleId = requestAnimationFrame(step);
  }
  const canPull = () => phase === "idle" && !selected && !motionOff();
  scroll.addEventListener("wheel", (e) => {
    if (!canPull() || e.ctrlKey) return;
    const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? scroll.clientHeight : 1), push = -dy;
    if (!push || (!pull && !atEdge(push))) return;
    e.preventDefault(); cancelAnimationFrame(settleId); pullBy(push);
    clearTimeout(settleWait); settleWait = setTimeout(settle, 130);
  }, { passive: false, signal });
  scroll.addEventListener("touchstart", (e) => { touchY = e.touches.length === 1 ? e.touches[0].clientY : null; }, { passive: true, signal });
  scroll.addEventListener("touchmove", (e) => {
    if (touchY == null || !canPull()) return;
    const y = e.touches[0].clientY, push = y - touchY; touchY = y;
    if (!push || (!pull && !atEdge(push))) return;
    e.preventDefault(); cancelAnimationFrame(settleId); pullBy(push / .45 * .6);
  }, { passive: false, signal });
  const touchEnd = () => { if (touchY != null) { touchY = null; if (pull) settle(); } };
  scroll.addEventListener("touchend", touchEnd, { signal });
  scroll.addEventListener("touchcancel", touchEnd, { signal });
  for (const b of page.querySelectorAll(".pw-sort button")) b.addEventListener("click", () => {
    if (sortBy === b.dataset.sort) return;
    sortBy = b.dataset.sort;
    for (const o of page.querySelectorAll(".pw-sort button")) o.setAttribute("aria-checked", String(o === b));
    scroll.scrollTop = 0; camera = scrollAt = 0; paintBackground(); render();
  }, { signal });
  q(".pw-open").addEventListener("click", () => {
    if (selected) leaveFor(() => openPlan ? openPlan(selected) : import("./design.js").then((d) => d.start(api, { plan: selected, fly: false })));
  }, { signal });
  window.addEventListener("resize", resize, { signal });
  window.addEventListener("dp-lang", () => { if (phase === "idle") { if (selected) unfocus(); render(); } }, { signal });
  const observer = new MutationObserver(() => {
    paintTheme();
    if (flight && motionOff()) finishFlight();
    if (motionOff()) focusArt.firstElementChild?.getAnimations().forEach((a) => a.finish());
  });
  observer.observe(root, { attributes: true, attributeFilter: ["data-theme", "data-motion"] });
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  reduced.addEventListener("change", () => { if (flight && motionOff()) finishFlight(); }, { signal });
  resize(); paintTheme();
  return {
    page,
    get state() { return { phase, visits, focused: !!selected, camera }; },
    async show(nextPlans = [], { from = $("lobby-open"), box = null } = {}) {
      if (phase !== "closed") return;
      phase = "loading";
      await stylesheet();
      previous = { mode: root.dataset.mode || "", backHidden: $("back")?.hidden ?? true };
      plans = [...nextPlans]; selected = null; focus.hidden = true; page.classList.remove("pw-focused");
      paintTheme(); render(); status.hidden = true;
      const lobby = $("lobby"), art = $("lobby-art"), rect = from?.getBoundingClientRect();
      entry = art && rect?.width ? { lobby, art, from,
        transform: art.style.transform, origin: art.style.transformOrigin, inert: lobby.inert,
        // The hotspot bounds the standing envelopes; the opening is its upper quarter.
        box: box || { x: rect.left + rect.width / 2, y: rect.top + rect.height / 4, width: rect.width * .7, height: rect.height * .28 } } : { from };
      timing = transitionTiming(visits, motionOff()); visits++; elapsed = 0;
      // Keep the lobby visible while textures decode. The first drawn archive frame is the
      // beginning of the push, never a flash of the resting paper before the fall.
      if (entry?.lobby) { entry.lobby.classList.add("leaving", "pw-box-flight"); entry.lobby.inert = true; }
      root.dataset.mode = "pastworks"; if ($("back")) $("back").hidden = false;
      page.hidden = false; scroll.inert = true; scroll.scrollTop = camera = scrollAt = 0; paintFlight();
      // Decode before moving the camera, but a missing art file cannot strand navigation.
      if (!motionOff()) await Promise.race([
        Promise.all([...layers.flatMap(({ images }) => images.map(({ img }) => img)), ...page.querySelectorAll("[data-envelope]")].map(img => img.decode().catch(() => {}))),
        new Promise((resolve) => setTimeout(resolve, 600)),
      ]);
      if (phase === "loading") animate();
    },
    back, skip,
    destroy() { if (phase !== "closed") release(); controller.abort(); observer.disconnect(); page.remove(); },
  };
}

let singleton, prepared;
export function prepare(api) {
  if (!prepared) prepared = Promise.all([stylesheet(), import("./design.js")]).then(([, design]) => {
    singleton = createPastWorks(api, { thumbnail: design.planThumbnail });
    return design;
  }).catch((e) => { prepared = null; throw e; });
  return prepared;
}
export async function start(api, options) {
  const design = await prepare(api);
  await singleton.show(design.recentPlans(), options);
}
