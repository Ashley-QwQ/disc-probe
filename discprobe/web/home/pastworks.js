// The archive and the fall share one background, one camera coordinate, and one clock.
// Pure helpers stay importable by plain Node; no DOM or design module is loaded here.
// The archive lists the core's works library (/api/works, pastworks/works.mjs); a core without one
// leaves the page its old in-memory list of this session's plans, and says so.
import { hasCapability } from "./handshake.mjs";
import { mediaLabel, discCount, discCode, burnedDiscs, discTime, discISO, workTime, sortWorks, filterWorks, statusWord, timeline, dateText as libDate,
  words as libWords, STATUSES, MEDIA } from "./pastworks/works.mjs";
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
// What the grid shows: plans not in the library first (they are the newest, and unsaved), then the
// library's works, each list sorted and filtered the same way. A status filter hides the plans.
export function arrange({ works = [], plans = [] }, { sort = "time", status = "", media = "", q = "" } = {}) {
  const fold = (s) => String(s ?? "").normalize("NFKC").toLocaleLowerCase(), needle = fold(q).trim();
  const loose = status ? [] : sortPlans(plans, sort).filter((p) => (!media || p.media === media) && (!needle || fold(planName(p)).includes(needle)));
  return [...loose.map((plan) => ({ plan })), ...sortWorks(filterWorks(works, { status, media, q }), sort).map((work) => ({ work }))];
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
// Arrow keys across the grid: cells in reading order, `columns` per row
export function gridStep(index, key, count, columns) {
  const to = key === "ArrowRight" ? index + 1 : key === "ArrowLeft" ? index - 1
    : key === "ArrowDown" ? index + columns : key === "ArrowUp" ? index - columns
      : key === "Home" ? 0 : key === "End" ? count - 1 : index;
  return to < 0 || to >= count ? index : to;
}

// The page's words. The title keeps both languages (the archive's printed heading); the rest follows the page's language.
const SAY = {
  zh: {
    search: "搜名字", searchLabel: "按名字搜作品", all: "全部", status: "状态", media: "盘种", sortLabel: "排序", newest: "最近", byName: "名称",
    import: "导入作品", importHint: "导入 .zip 或 .discdesign", drop: "松手导入作品", count: (n, shown) => shown === n ? `共 ${n} 件` : `共 ${n} 件 · 显示 ${shown} 件`,
    loading: "正在读作品库…", newWork: "新作品", open: "打开作品", opening: "正在打开…",
    rename: "改名", renameHint: "改名（F2）", copy: "复制", exportZip: "导出 zip", markDone: "标成成品", markFailed: "标成失败…", bin: "移到回收站",
    reasonLabel: "失败原因（会写进记录）", reasonHint: "例如：内圈有一圈没刻上", confirmFailed: "标成失败", cancel: "取消", reason: "失败原因",
    created: "创建", updated: "最后修改", opened: "上次打开", geo: "几何", batch: "盘批次", photoL: "照片 L", source: "导入自", cell: (u) => `${u} µm 格子`,
    discsTitle: (n) => `刻过的盘（${n}）`, noDiscs: "还没刻过盘。", log: "记录", noLog: "还没有记录。", logLoading: "正在读记录…",
    unsaved: "未存进库", unsavedNote: "这件作品还没存进作品库。打开它，在设计页按 Ctrl+S 保存。",
    noCore: "这台核心不保存作品：这里只有这次打开页面以来的作品，关掉浏览器就没了。要留下来，在设计页用“另存为”（Ctrl+Shift+S）存成文件。",
    mock: "演示数据：作品库只在这个页面里，刷新就清空。",
    loadFailed: (m) => `读不到作品库（${m}）。下面只有这次打开页面以来的作品。`, retry: "重试",
    emptyLibrary: "作品库还是空的。第一步：点上面的“新作品”，放一张图进去；做好后按 Ctrl+S 存进库。已有 .discdesign 或导出的 zip，拖到这一页就能导入。",
    emptyMemory: "还没有作品。第一步：点上面的“新作品”，放一张图进去。",
    noMatch: "没有符合的作品。", clear: "清除筛选",
    renamed: (n) => `已改名为“${n}”`, copied: (n) => `已复制为“${n}”`, binned: (n) => `已把“${n}”移到回收站`, undo: "撤销", restored: (n) => `已恢复“${n}”`,
    marked: (s) => `已标成${s}`, exported: (n) => `已导出 ${n}`, imported: (n) => `已导入“${n}”`, importFailed: (f, m) => `没能导入 ${f}：${m}`,
    importExists: (f) => `${f} 里的作品已经在库里或回收站里，没有重复导入。要另一份，在库里复制它。`,
    failed: (m) => `没做成：${m}`, emptyName: "名字不能是空的。", openFailed: "没能打开作品，请重试。",
  },
  en: {
    search: "Search names", searchLabel: "Search works by name", all: "All", status: "Status", media: "Disc", sortLabel: "Sort", newest: "Newest", byName: "Name",
    import: "Import works", importHint: "Import a .zip or .discdesign", drop: "Drop to import", count: (n, shown) => shown === n ? `${n} works` : `${shown} of ${n} works`,
    loading: "Reading the library…", newWork: "New work", open: "Open work", opening: "Opening…",
    rename: "Rename", renameHint: "Rename (F2)", copy: "Duplicate", exportZip: "Export zip", markDone: "Mark finished", markFailed: "Mark failed…", bin: "Move to bin",
    reasonLabel: "Why it failed (goes into the record)", reasonHint: "e.g. the inner ring did not burn", confirmFailed: "Mark failed", cancel: "Cancel", reason: "Why it failed",
    created: "Created", updated: "Last changed", opened: "Last opened", geo: "Geometry", batch: "Disc batch", photoL: "Photo L", source: "Imported from", cell: (u) => `${u} µm cells`,
    discsTitle: (n) => `Discs burned (${n})`, noDiscs: "No discs burned yet.", log: "Record", noLog: "Nothing recorded yet.", logLoading: "Reading the record…",
    unsaved: "Not in the library", unsavedNote: "This work is not in the library yet. Open it and press Ctrl+S on the design page.",
    noCore: "This core does not keep works: only the works opened since this page loaded are here, and closing the browser loses them. To keep one, use Save as (Ctrl+Shift+S) on the design page.",
    mock: "Sample data: this library lives in this page only and empties on reload.",
    loadFailed: (m) => `Could not read the library (${m}). Only this session's works are below.`, retry: "Retry",
    emptyLibrary: "The library is empty. First step: choose New work above and put a picture in it; press Ctrl+S when it looks right. Have a .discdesign or an exported zip? Drop it on this page to import it.",
    emptyMemory: "No works yet. First step: choose New work above and put a picture in it.",
    noMatch: "No works match.", clear: "Clear filters",
    renamed: (n) => `Renamed to “${n}”`, copied: (n) => `Duplicated as “${n}”`, binned: (n) => `Moved “${n}” to the bin`, undo: "Undo", restored: (n) => `Restored “${n}”`,
    marked: (s) => `Marked ${s.toLowerCase()}`, exported: (n) => `Exported ${n}`, imported: (n) => `Imported “${n}”`, importFailed: (f, m) => `Could not import ${f}: ${m}`,
    importExists: (f) => `The work in ${f} is already in the library or the bin, so it was not imported again. To have another copy, duplicate it.`,
    failed: (m) => `That did not work: ${m}`, emptyName: "A name cannot be empty.", openFailed: "Could not open the work. Please try again.",
  },
};
const ICON = {
  search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/></svg>',
  done: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  failed: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16v.5"/></svg>',
  import: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/></svg>',
};

const asset = (path) => new URL(path, import.meta.url).href;
let cssReady;
function stylesheet() {
  if (!cssReady) cssReady = new Promise((resolve) => {
    const link = document.createElement("link"); link.rel = "stylesheet";
    link.href = asset("./pastworks.css"); link.onload = resolve; link.onerror = resolve; document.head.append(link);
  });
  return cssReady;
}

// options.works: the library client (pastworks/works.mjs) or null for the in-memory list;
// openWork(work, text): enter the design page with a library work; recent(): this session's plans (to keep
// their saved stamps in step after a rename here); mock: say the library is sample data.
export function createPastWorks(api, { host = document.body, thumbnail, openPlan, newWork, onClose, works = null, openWork, recent, mock = false } = {}) {
  const root = document.documentElement, $ = api.$ || ((id) => document.getElementById(id));
  const lang = () => api.lang?.() === "en" ? "en" : "zh", say = () => SAY[lang()];
  const page = document.createElement("section");
  page.className = "pw"; page.hidden = true; page.setAttribute("aria-label", "往期作品 / Past works");
  // .pw-hole: the dark of the box carried into the fall (light below, where the paper waits); under the envelopes
  page.innerHTML = `<div class="pw-background" aria-hidden="true"><div class="pw-hole"></div></div>
    <div class="pw-scroll" tabindex="-1"><article class="pw-paper">
      <header class="pw-heading"><h1>往期作品 <small lang="en">Past works</small></h1><p class="pw-count"></p>
        <div class="pw-sort" role="radiogroup">
          <button type="button" role="radio" aria-checked="true" data-sort="time"></button>
          <button type="button" role="radio" aria-checked="false" data-sort="name"></button></div></header>
      <div class="pw-tools">
        <label class="pw-search">${ICON.search}<input type="search" enterkeyhint="search" autocomplete="off" spellcheck="false"></label>
        <div class="pw-filter" role="radiogroup" data-filter="status"></div>
        <div class="pw-filter" role="radiogroup" data-filter="media"></div>
        <button type="button" class="pw-import">${ICON.import}<span></span></button>
        <input type="file" class="pw-file" accept=".zip,.discdesign,.json,application/zip,application/json" multiple hidden>
      </div>
      <p class="pw-note" hidden><span></span> <button type="button" class="pw-link" hidden></button></p>
      <div class="pw-grid"></div><p class="pw-empty" hidden><span></span> <button type="button" class="pw-link" hidden></button></p>
    </article></div>
    <div class="pw-focus" hidden><div class="pw-focus-paper"></div><div class="pw-focus-art"></div>
      <div class="pw-details" tabindex="-1"></div><button class="pw-open pw-glass" type="button"></button></div>
    <div class="pw-drop" hidden><p></p></div>
    <div class="pw-status" role="status" hidden><span></span><button type="button" class="pw-link" hidden></button></div>`;
  host.append(page);
  const q = (s) => page.querySelector(s), scroll = q(".pw-scroll"), paper = q(".pw-paper"), grid = q(".pw-grid");
  const focus = q(".pw-focus"), focusArt = q(".pw-focus-art"), details = q(".pw-details"), status = q(".pw-status");
  const search = q(".pw-search input"), fileInput = q(".pw-file"), drop = q(".pw-drop");
  const controller = new AbortController(), signal = controller.signal;
  let phase = "closed", visits = 0, plans = [], selected = null, selectedButton = null, sortBy = "time";
  let library = null, loadError = null, undoing = null, filter = { status: "", media: "", q: "" }, loadSerial = 0, statusTimer = 0;
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
  const entryName = (e) => e.work ? String(e.work.name ?? "") : planName(e.plan);
  const entryTime = (e) => e.work ? workTime(e.work) : planTime(e.plan);
  function dateText(e, opts) {
    const t = entryTime(e);
    return t == null ? libWords(lang()).unknownDate : libDate(t, lang(), opts);
  }
  // the archive bag lying on the paper (pastworks/envelope_*: the new-work page's bag before it grew tall), the
  // work's disc on its pocket, turned a little as a hand would leave it (the same turn every time for a work)
  function envelope(e) {
    const art = document.createElement("span"); art.className = "pw-envelope";
    const key = e ? String(e.work?.id ?? e.plan?.id ?? entryName(e)) : "new";
    let h = 0; for (const c of key) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    art.style.setProperty("--turn", `${(h % 41) - 20}deg`);
    art.style.setProperty("--tilt", `${((h >> 6) % 7) - 3}deg`);
    for (const side of ["back", "front"]) {
      const img = document.createElement("img"); img.alt = ""; img.draggable = false; img.decoding = "async";
      img.dataset.envelope = side; img.src = asset(`./pastworks/envelope_${side}_${theme}.webp`); art.append(img);
    }
    const blankDisc = () => {   // a blank disc (the calibration stage's own disc): the new work, or a work with no picture yet
      const blank = document.createElement("img"); blank.className = "pw-disc pw-blank"; blank.alt = ""; blank.draggable = false;
      blank.dataset.blank = "1"; blank.src = asset(`./caltop/anim/disc_${theme}.webp`); return blank;
    };
    if (e?.plan && thumbnail) {
      const disc = document.createElement("img"); disc.className = "pw-disc"; disc.alt = ""; disc.draggable = false;
      art.append(disc);
      // One small cached image per plan; no canvas or projection work in the scroll loop.
      disc.dataset.thumb = String(thumbSerial++);
      thumbPlans.set(disc.dataset.thumb, e.plan); fillThumbnail(e.plan, disc.dataset.thumb);
    } else if (e?.work && works) {
      const disc = blankDisc(); art.append(disc);
      // the core's picture (uploaded at save, else drawn by the core); a blank disc until it comes, or if it never does
      works.thumbURL(e.work).then((src) => { disc.src = src; disc.classList.remove("pw-blank"); delete disc.dataset.blank; }, () => {});
    } else art.append(blankDisc());
    if (e?.work?.status === "done" || e?.work?.status === "failed") {
      const mark = document.createElement("span"); mark.className = `pw-stamp pw-stamp-${e.work.status}`;
      mark.textContent = statusWord(e.work.status, lang()); mark.setAttribute("aria-hidden", "true"); art.append(mark);
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
  // the line at the bottom: what just happened, with its undo when there is one
  // (an undo also answers Ctrl+Z while it is on screen)
  function notice(message, { action = null, run = null, time = 6000 } = {}) {
    clearTimeout(statusTimer);
    const [text, button] = status.children;
    text.textContent = message; button.hidden = !action; button.textContent = action ?? "";
    undoing = run ? () => { undoing = null; status.hidden = true; run(); } : null;
    button.onclick = undoing;
    if (action && run) button.title = `${action} (Ctrl+Z)`;
    status.hidden = false;
    if (time) statusTimer = setTimeout(() => { status.hidden = true; undoing = null; }, time);
  }
  const error = (message) => notice(message, { time: 0 });
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
    page.setAttribute("aria-busy", "true"); q(".pw-open").disabled = true; q(".pw-open").textContent = say().opening;
    status.hidden = true;
    try { await action(); release(); }
    catch { error(say().openFailed); }
    finally { page.removeAttribute("aria-busy"); q(".pw-open").disabled = false; q(".pw-open").textContent = say().open; }
  }

  // ------------------------------------------------------------ the list
  const usingLibrary = () => !!(works && library && !loadError);
  const loosePlans = () => usingLibrary() ? plans.filter((p) => !p.work) : plans;
  function radios(box, name, options, value) {
    box.replaceChildren();
    box.setAttribute("aria-label", name);
    for (const [v, label, count] of options) {
      const b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(v === value)); b.dataset.value = v;
      b.tabIndex = v === value ? 0 : -1;
      b.append(label);
      if (count != null) { const c = document.createElement("small"); c.textContent = count; b.append(c); }
      box.append(b);
    }
  }
  function words() {
    const s = say();
    q(".pw-sort").setAttribute("aria-label", s.sortLabel);
    q('.pw-sort [data-sort="time"]').textContent = s.newest; q('.pw-sort [data-sort="name"]').textContent = s.byName;
    search.placeholder = s.search; search.setAttribute("aria-label", s.searchLabel);
    q(".pw-import span").textContent = s.import; q(".pw-import").title = s.importHint;
    q(".pw-open").textContent = s.open; drop.firstElementChild.textContent = s.drop;
  }
  function paintTools() {
    const s = say(), lib = usingLibrary(), all = library ?? [];
    const statusBox = q('[data-filter="status"]'), mediaBox = q('[data-filter="media"]');
    statusBox.hidden = !lib || !all.length; q(".pw-import").hidden = !lib;
    if (lib) {
      const counts = {}; for (const w of all) counts[w.status] = (counts[w.status] ?? 0) + 1;
      radios(statusBox, s.status, [["", s.all, null], ...STATUSES.filter((v) => counts[v] || filter.status === v).map((v) => [v, statusWord(v, lang()), counts[v] ?? 0])], filter.status);
    }
    const kinds = new Set([...all.map((w) => w.media), ...loosePlans().map((p) => p.media)]);
    radios(mediaBox, s.media, [["", s.all, null], ...MEDIA.filter((m) => kinds.has(m) || filter.media === m).map((m) => [m, m.toUpperCase(), null])], filter.media);
    mediaBox.hidden = kinds.size < 2 && !filter.media;
    const [noteText, noteButton] = q(".pw-note").children;
    noteButton.hidden = true;
    let note = "";
    if (works && loadError) { note = s.loadFailed(loadError); noteButton.hidden = false; noteButton.textContent = s.retry; noteButton.onclick = () => load(); }
    else if (!works) note = s.noCore;
    else if (mock) note = s.mock;
    noteText.textContent = note; q(".pw-note").hidden = !note;
    q(".pw-note").classList.toggle("pw-warn", !!(works && loadError) || !works);
  }
  function cellFor(e, n) {
    const s = say(), button = document.createElement("button"); button.type = "button"; button.className = "pw-cell";
    const name = document.createElement("span"), no = document.createElement("i"), label = document.createElement("b");
    no.className = "pw-no"; no.textContent = String(n).padStart(2, "0");
    name.className = "pw-cell-name"; label.className = "pw-label"; label.textContent = entryName(e); name.append(no, label);
    const meta = document.createElement("span"); meta.className = "pw-meta";
    const date = document.createElement("time"); date.textContent = dateText(e);
    const t = entryTime(e); if (t != null) date.dateTime = new Date(t).toISOString();
    if (e.work) {
      const w = e.work, st = document.createElement("span");
      st.className = `pw-state pw-state-${w.status}`; st.innerHTML = ICON[w.status] ?? ""; st.append(statusWord(w.status, lang()));
      const n = discCount(w);
      meta.append(mediaLabel(w), " · ", st, " · ", n ? libWords(lang()).discs(n) : libWords(lang()).noDiscs);
      button.dataset.id = w.id;
    } else {
      const parts = e.plan.media ? [String(e.plan.media).toUpperCase()] : [];
      if (usingLibrary()) { const st = document.createElement("span"); st.className = "pw-state pw-state-unsaved"; st.textContent = s.unsaved; parts.push(st); }
      parts.forEach((p, i) => meta.append(...(i ? [" · ", p] : [p])));
    }
    button.append(envelope(e), name, meta, date);
    button.addEventListener("click", () => select(e, button), { signal });
    return button;
  }
  // the grid drawn again; the card that had the keyboard keeps it (a list arriving late must not drop focus)
  function render() {
    const held = grid.contains(document.activeElement) ? document.activeElement.closest(".pw-cell") : null;
    const heldKey = held ? held.dataset.id ?? (held.classList.contains("pw-new") ? "" : null) : null;
    paintGrid();
    if (heldKey != null) ((heldKey && grid.querySelector(`[data-id="${CSS.escape(heldKey)}"]`)) || grid.querySelector(".pw-new"))?.focus({ preventScroll: true });
  }
  function paintGrid() {
    grid.replaceChildren(); thumbPlans.clear();
    const s = say();
    const fresh = document.createElement("button"); fresh.type = "button"; fresh.className = "pw-cell pw-new";
    fresh.append(envelope(null));
    const label = document.createElement("span"); label.className = "pw-cell-name";
    label.innerHTML = `<i class="pw-no">00</i><b class="pw-label"></b>`; label.lastChild.textContent = s.newWork; fresh.append(label);
    fresh.addEventListener("click", () => leaveFor(() => newWork ? newWork() : api.newWork ? api.newWork() : $("lobby-new").click()), { signal });
    grid.append(fresh);
    paintTools();
    if (works && !library && !loadError) { q(".pw-count").textContent = s.loading; q(".pw-empty").hidden = true; return; }
    const lib = usingLibrary(), source = { works: lib ? library : [], plans: loosePlans() };
    const shown = arrange(source, { sort: sortBy, ...filter }), total = source.works.length + source.plans.length;
    let n = 0;
    for (const e of shown) grid.append(cellFor(e, ++n));
    const [emptyText, emptyButton] = q(".pw-empty").children;
    const filtered = !!(filter.status || filter.media || filter.q.trim());
    emptyButton.hidden = !(filtered && !shown.length);
    emptyButton.textContent = s.clear; emptyButton.onclick = clearFilters;
    emptyText.textContent = shown.length ? "" : filtered ? s.noMatch : lib ? s.emptyLibrary : s.emptyMemory;
    q(".pw-empty").hidden = !!shown.length;
    q(".pw-count").textContent = total ? s.count(total, shown.length) : "";
  }
  function clearFilters() {
    filter = { status: "", media: "", q: "" }; search.value = ""; render();
    q('[data-filter="status"] [aria-checked="true"], .pw-search input')?.focus({ preventScroll: true });
  }
  // the library from the core; the session's plans if it cannot be read
  async function load({ focusId = null } = {}) {
    if (!works) { library = null; render(); return; }
    const serial = ++loadSerial;
    try {
      const list = await works.list({ sort: sortBy });
      if (serial !== loadSerial) return;
      library = list; loadError = null;
    } catch (e) {
      if (serial !== loadSerial) return;
      library = null; loadError = e?.status ? `HTTP ${e.status}` : String(e?.message ?? e);
    }
    if (selected) unfocus();
    render();
    if (focusId) grid.querySelector(`[data-id="${CSS.escape(focusId)}"]`)?.focus({ preventScroll: false });
  }
  const findWork = (id) => library?.find((w) => w.id === id);
  // keep plans open in the design page in step with a change made here, so their next save is no false conflict
  function follow(before, after) {
    if (!after) return;
    for (const p of recent?.() ?? []) if (p.work?.id === after.id && p.work.updated_at === before?.updated_at) {
      p.work.updated_at = after.updated_at; if (!p.dirty && after.name) p.name = after.name;
    }
  }
  function replaceWork(after) {
    if (!library || !after) return;
    const i = library.findIndex((w) => w.id === after.id);
    if (i >= 0) library[i] = { ...library[i], ...after };
  }
  async function act(run) {
    try { return await run(); }
    catch (e) { error(say().failed(e?.message ?? String(e))); return undefined; }
  }

  // ------------------------------------------------------------ one work, up close
  function select(e, button) {
    if (phase !== "idle") return;
    const source = button.querySelector(".pw-envelope"), before = source.getBoundingClientRect();
    selected = e; selectedButton = button;
    focusArt.replaceChildren(source.cloneNode(true));
    paintDetails();
    focus.hidden = false; scroll.inert = true; page.classList.add("pw-focused");
    const after = focusArt.firstElementChild.getBoundingClientRect();
    if (!motionOff()) focusArt.firstElementChild.animate([
      { transform: `translate(${before.left - after.left}px, ${before.top - after.top}px) scale(${before.width / after.width})` },
      { transform: "none" },
    ], { duration: 480, easing: "cubic-bezier(.2,.8,.2,1)" });
    details.focus({ preventScroll: true });
    if (e.work) {
      const id = e.work.id;
      works.get(id).then((full) => {
        if (selected?.work?.id !== id) return;
        selected = { work: { ...e.work, ...full } }; replaceWork(full);
        // a name or a reason being typed is not swept away; the record shows on the next paint
        if (!details.querySelector(".pw-rename-input, .pw-fail:not([hidden])")) paintDetails({ keepFocus: true });
      }, (err) => { if (selected?.work?.id === id) paintDetails({ keepFocus: true, logError: err?.message ?? String(err) }); });
    }
  }
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function action(label, run, cls = "") {
    const b = el("button", `pw-act ${cls}`.trim(), label); b.type = "button"; b.addEventListener("click", run); return b;
  }
  function paintDetails({ keepFocus = false, logError = null } = {}) {
    const s = say(), e = selected, active = keepFocus ? document.activeElement : null;
    const keep = active && details.contains(active) ? active.dataset.keep : null;
    details.replaceChildren();
    if (!e) return;
    const head = el("h2", "pw-d-name"), nameButton = el("button", "pw-rename", entryName(e));
    nameButton.type = "button"; nameButton.dataset.keep = "rename";
    if (e.work) { nameButton.title = s.renameHint; nameButton.addEventListener("click", () => startRename(nameButton, e.work)); head.append(nameButton); }
    else head.textContent = entryName(e);
    details.append(head);
    if (!e.work) {
      details.append(el("p", "pw-d-meta", [e.plan.media ? String(e.plan.media).toUpperCase() : "", dateText(e)].filter(Boolean).join(" · ")));
      if (works && !loadError) details.append(el("p", "pw-d-note", s.unsavedNote));
      return;
    }
    const w = e.work, meta = el("p", "pw-d-meta");
    const st = el("span", `pw-state pw-state-${w.status}`); st.innerHTML = ICON[w.status] ?? ""; st.append(statusWord(w.status, lang()));
    meta.append(mediaLabel(w), " · ", st);
    if (w.cell_um) meta.append(" · ", s.cell(w.cell_um));
    details.append(meta);
    if (w.status === "failed" && w.note) details.append(el("p", "pw-d-reason", `${s.reason}：${w.note}`));
    const acts = el("div", "pw-d-actions");
    acts.append(
      action(s.copy, () => duplicate(w)), action(s.exportZip, () => exportWork(w)),
      ...(w.status !== "done" ? [action(s.markDone, () => mark(w, "done"))] : []),
      ...(w.status !== "failed" ? [action(s.markFailed, () => askReason(w), "pw-act-failed")] : []),
      action(s.bin, () => binWork(w), "pw-act-bin"));
    for (const [i, b] of [...acts.children].entries()) b.dataset.keep = `act${i}`;
    details.append(acts);
    const form = el("form", "pw-fail"); form.hidden = true;
    const reasonId = `pw-reason-${w.id}`, label = el("label", null, s.reasonLabel), area = el("textarea");
    label.htmlFor = reasonId; area.id = reasonId; area.rows = 2; area.required = true; area.placeholder = s.reasonHint; area.maxLength = 500;
    const row = el("div", "pw-d-actions"), ok = el("button", "pw-act pw-act-strong", s.confirmFailed), no = el("button", "pw-act", s.cancel);
    ok.type = "submit"; no.type = "button";
    no.addEventListener("click", () => { form.hidden = true; acts.querySelector(".pw-act-failed")?.focus(); });
    area.addEventListener("keydown", (k) => { if (k.key === "Escape") { k.preventDefault(); no.click(); } else if (k.key === "Enter" && (k.ctrlKey || k.metaKey)) { k.preventDefault(); form.requestSubmit(); } });
    form.addEventListener("submit", (k) => { k.preventDefault(); const why = area.value.trim(); if (!why) { area.focus(); return; } mark(w, "failed", why); });
    row.append(ok, no); form.append(label, area, row); details.append(form);
    const facts = el("dl", "pw-d-facts");
    const fact = (term, value, mono = false) => { if (value == null || value === "") return; facts.append(el("dt", null, term), el("dd", mono ? "pw-mono" : null, String(value))); };
    const when = (v) => { const n = Date.parse(v); return Number.isFinite(n) ? libDate(n, lang()) : null; };
    fact(s.created, when(w.created_at)); fact(s.updated, when(w.updated_at)); fact(s.opened, when(w.opened_at));
    fact(s.geo, w.geo_run, true);
    fact(s.batch, typeof w.batch === "object" && w.batch ? [w.batch.mid, w.batch.name].filter(Boolean).join(" · ") : w.batch);
    fact(s.photoL, typeof w.photo_l === "object" && w.photo_l ? [w.photo_l.L ?? w.photo_l.value, w.photo_l.source].filter((v) => v != null && v !== "").join(" · ") : w.photo_l, true);
    fact(s.source, w.source_file, true);
    if (facts.children.length) details.append(facts);
    const discs = burnedDiscs(w);
    details.append(el("h3", null, s.discsTitle(discs.length)));
    if (!discs.length) details.append(el("p", "pw-d-quiet", s.noDiscs));
    else {
      const list = el("ul", "pw-d-discs");
      for (const d of discs) {
        const li = el("li"), at = Date.parse(discTime(d) ?? "");
        li.append(el("b", "pw-code", discCode(d) ?? "—"));
        const speed = d.speed == null || d.speed === "" ? "" : /x$/i.test(String(d.speed)) ? String(d.speed) : `${d.speed}x`;
        const rest = [Number.isFinite(at) ? libDate(at, lang()) : "", d.drive, speed, d.result && d.result !== "completed" ? d.result : ""].filter(Boolean).join(" · ");
        if (rest) li.append(" ", el("span", null, rest));
        if (discISO(d)) li.append(el("span", "pw-mono pw-d-iso", String(discISO(d)).split(/[\\/]/).pop()));
        list.append(li);
      }
      details.append(list);
    }
    details.append(el("h3", null, s.log));
    const events = timeline(w, lang());
    if (!Array.isArray(w.history)) details.append(el("p", "pw-d-quiet", logError ? s.failed(logError) : s.logLoading));
    else if (!events.length) details.append(el("p", "pw-d-quiet", s.noLog));
    else {
      const log = el("ol", "pw-d-log");
      for (const ev of events.slice().reverse()) {
        const li = el("li"), time = el("time", null, ev.at == null ? "" : libDate(ev.at, lang()));
        if (ev.at != null) time.dateTime = new Date(ev.at).toISOString();
        li.append(time, el("span", null, ev.text));
        if (ev.detail) li.append(el("small", null, ev.detail));
        log.append(li);
      }
      details.append(log);
    }
    if (keep) details.querySelector(`[data-keep="${keep}"]`)?.focus({ preventScroll: true });
  }
  function askReason(w) {
    const form = details.querySelector(".pw-fail"); if (!form) return;
    form.hidden = false; form.querySelector("textarea").focus();
  }
  function unfocus() {
    focusArt.firstElementChild?.getAnimations().forEach((a) => a.cancel());
    selected = null; focus.hidden = true; scroll.inert = false; page.classList.remove("pw-focused");
    const id = selectedButton?.dataset.id;
    const back = selectedButton?.isConnected ? selectedButton : id ? grid.querySelector(`[data-id="${CSS.escape(id)}"]`) : null;
    (back ?? grid.querySelector(".pw-cell"))?.focus({ preventScroll: true }); selectedButton = null;
  }

  // ------------------------------------------------------------ managing works
  function startRename(anchor, w) {
    if (anchor.querySelector?.("input") || anchor.tagName === "INPUT") return;
    const input = document.createElement("input"); input.type = "text"; input.className = "pw-rename-input";
    input.value = w.name ?? ""; input.maxLength = 200; input.setAttribute("aria-label", say().rename);
    let done = false;
    const finish = async (commit) => {
      if (done) return; done = true;
      const name = input.value.trim();
      if (commit && !name) { notice(say().emptyName); done = false; input.focus(); return; }
      if (!commit || name === w.name) { input.replaceWith(anchor); anchor.focus({ preventScroll: true }); return; }
      input.disabled = true;
      const after = await act(() => works.rename(w.id, name));
      if (!after) { input.replaceWith(anchor); anchor.focus(); return; }
      follow(w, after); replaceWork(after);
      notice(say().renamed(after.name ?? name));
      if (selected?.work?.id === w.id) { await refreshSelected(after); details.querySelector(".pw-rename")?.focus({ preventScroll: true }); render(); }
      else { render(); grid.querySelector(`[data-id="${CSS.escape(w.id)}"]`)?.focus({ preventScroll: true }); }
    };
    input.addEventListener("keydown", (k) => {
      k.stopPropagation();
      if (k.key === "Enter") { k.preventDefault(); finish(true); }
      else if (k.key === "Escape") { k.preventDefault(); finish(false); }
    });
    input.addEventListener("blur", () => finish(true));
    anchor.replaceWith(input); input.focus(); input.select();
  }
  // the work up close after a change: its fresh record, and its bag re-stamped
  async function refreshSelected(after) {
    const id = after.id;
    selected = { work: { ...selected.work, ...after } };
    const full = await works.get(id).catch(() => null);
    if (selected?.work?.id !== id) return;
    if (full) { selected = { work: { ...selected.work, ...full } }; replaceWork(full); }
    focusArt.replaceChildren(envelope(selected));
    paintDetails();
  }
  async function duplicate(w) {
    // the core keeps the name on a copy; two works with one name cannot be told apart
    const copy = await act(() => works.duplicate(w.id, lang() === "en" ? `${w.name} (copy)` : `${w.name} 副本`));
    if (!copy) return;
    notice(say().copied(copy.name));
    if (selected) unfocus();
    await load({ focusId: copy.id });
  }
  async function exportWork(w) {
    const out = await act(() => works.exportZip(w.id, w.name));
    if (!out) return;
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(out.blob), download: out.name });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    notice(say().exported(out.name));
  }
  async function mark(w, to, note) {
    const after = await act(() => works.mark(w.id, to, note));
    if (!after) return;
    follow(w, after); replaceWork(after);
    if (selected?.work?.id === w.id) {
      await refreshSelected(after);
      details.querySelector(".pw-d-actions .pw-act")?.focus({ preventScroll: true });
    }
    render();
    notice(say().marked(statusWord(to, lang())));
  }
  async function binWork(w) {
    const ok = await act(async () => { await works.remove(w.id); return true; });
    if (!ok) return;
    if (selected?.work?.id === w.id) { selectedButton = null; unfocus(); }
    const index = [...grid.children].findIndex((c) => c.dataset.id === w.id);
    library = library?.filter((x) => x.id !== w.id) ?? library;
    render();
    const cells = grid.querySelectorAll(".pw-cell");
    cells[Math.min(Math.max(index, 1), cells.length - 1)]?.focus({ preventScroll: true });
    notice(say().binned(w.name), { action: say().undo, time: 10000, run: async () => {
      const back = await act(() => works.restore(w.id));
      if (!back) return;
      notice(say().restored(back.name ?? w.name));
      await load({ focusId: w.id });
    } });
  }
  async function importFiles(files) {
    let last = null;
    for (const f of files) {
      try { last = await works.importFile(f); notice(say().imported(last?.name ?? f.name)); }
      catch (e) { error(e?.status === 409 ? say().importExists(f.name) : say().importFailed(f.name, e?.message ?? String(e))); }
    }
    if (last) await load({ focusId: last.id });
  }
  async function openSelected() {
    const e = selected;
    if (!e) return;
    if (e.plan) return leaveFor(() => openPlan ? openPlan(e.plan) : import("./design.js").then((d) => d.start(api, { plan: e.plan, fly: false })));
    leaveFor(async () => {
      const text = await works.design(e.work.id).catch((err) => { if (err?.status === 404) return null; throw err; });
      if (openWork) await openWork(e.work, text);
      else (await import("./design.js")).start(api, { fly: false, work: { ...e.work, text } });
    });
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
  const typing = (t) => t?.closest?.("input:not([type=search]), textarea, [contenteditable=true]");
  function keydown(e) {
    if (!active() || e.defaultPrevented || e.isComposing) return;
    // Existing settings, shortcut help and terminal keep their own Escape.
    if (document.querySelector('.term:not([hidden]), .keys-help:not([hidden]), #set-menu:not([hidden]), dialog[open]')) return;
    if (typing(e.target)) return;                  // renaming, a failure reason: the field owns its keys
    if (undoing && phase === "idle" && (e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && e.target !== search) {
      e.preventDefault(); e.stopImmediatePropagation(); undoing(); return;
    }
    if (e.key === "Escape" && e.target === search && search.value) { e.preventDefault(); e.stopImmediatePropagation(); search.value = ""; filter.q = ""; render(); return; }
    if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); back(); }
    else if (e.key === "Enter" && (flight || phase === "loading")) { e.preventDefault(); e.stopImmediatePropagation(); skip(); }
    else if (phase === "idle" && !selected && e.key === "/" && e.target !== search) { e.preventDefault(); search.focus(); }
  }
  window.addEventListener("keydown", keydown, { capture: true, signal });
  window.addEventListener("click", (e) => {
    if (!active() || (!flight && phase !== "loading") || e.target.closest?.("#back")) return;
    e.preventDefault(); e.stopImmediatePropagation(); skip();
  }, { capture: true, signal });
  $("back")?.addEventListener("click", (e) => { if (active()) { e.preventDefault(); e.stopImmediatePropagation(); back(); } }, { capture: true, signal });
  // On a card: arrows move, F2 renames, Delete moves it to the bin (with undo)
  grid.addEventListener("keydown", (e) => {
    const cell = e.target.closest?.(".pw-cell");
    if (!cell || phase !== "idle" || selected || e.altKey || e.ctrlKey || e.metaKey) return;
    const cells = [...grid.querySelectorAll(".pw-cell")], i = cells.indexOf(cell);
    if (/^Arrow|^Home$|^End$/.test(e.key)) {
      const top = cells[0].offsetTop, columns = Math.max(1, cells.filter((c) => c.offsetTop === top).length);
      const to = gridStep(i, e.key, cells.length, columns);
      if (to !== i) { e.preventDefault(); cells[to].focus(); }
      return;
    }
    const w = cell.dataset.id && findWork(cell.dataset.id);
    if (!w) return;
    // F2: the work up close, its name ready to edit (a field inside the card's button would not take keys)
    if (e.key === "F2") { e.preventDefault(); select({ work: w }, cell); const n = details.querySelector(".pw-rename"); if (n) startRename(n, findWork(w.id) ?? w); }
    else if (e.key === "Delete") { e.preventDefault(); binWork(w); }
  }, { signal });
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
  // the filter words: a click picks one; arrows move along a group (radio keys)
  for (const box of page.querySelectorAll(".pw-filter")) {
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      filter[box.dataset.filter] = b.dataset.value; render();
      q(`[data-filter="${box.dataset.filter}"] [aria-checked="true"]`)?.focus({ preventScroll: true });
    }, { signal });
    box.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
      const all = [...box.querySelectorAll("button")], i = all.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      all[(i + (/Right|Down/.test(e.key) ? 1 : all.length - 1)) % all.length].click();
    }, { signal });
  }
  search.addEventListener("input", () => { filter.q = search.value; render(); }, { signal });
  q(".pw-import").addEventListener("click", () => fileInput.click(), { signal });
  fileInput.addEventListener("change", () => { const fs = [...fileInput.files]; fileInput.value = ""; if (fs.length) importFiles(fs); }, { signal });
  // Drop a .zip or .discdesign anywhere on the page to import it
  let dragDepth = 0;
  const canDrop = (e) => usingLibrary() && phase === "idle" && e.dataTransfer?.types?.includes("Files");
  page.addEventListener("dragenter", (e) => { if (!canDrop(e)) return; e.preventDefault(); dragDepth++; drop.hidden = false; }, { signal });
  page.addEventListener("dragover", (e) => { if (canDrop(e)) e.preventDefault(); }, { signal });
  page.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) drop.hidden = true; }, { signal });
  page.addEventListener("drop", (e) => {
    dragDepth = 0; drop.hidden = true;
    if (!canDrop(e)) return;
    e.preventDefault(); e.stopPropagation();
    const fs = [...e.dataTransfer.files].filter((f) => /\.(zip|discdesign|json)$/i.test(f.name));
    if (fs.length) importFiles(fs);
  }, { signal });
  q(".pw-open").addEventListener("click", openSelected, { signal });
  window.addEventListener("resize", resize, { signal });
  window.addEventListener("dp-lang", () => { words(); if (phase === "idle") { if (selected) paintDetails(); render(); } }, { signal });
  const observer = new MutationObserver(() => {
    paintTheme();
    if (flight && motionOff()) finishFlight();
    if (motionOff()) focusArt.firstElementChild?.getAnimations().forEach((a) => a.finish());
  });
  observer.observe(root, { attributes: true, attributeFilter: ["data-theme", "data-motion"] });
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  reduced.addEventListener("change", () => { if (flight && motionOff()) finishFlight(); }, { signal });
  resize(); paintTheme(); words();
  return {
    page,
    get state() { return { phase, visits, focused: !!selected, camera, library: usingLibrary(), filter: { ...filter }, sort: sortBy }; },
    // nextPlans: this session's plans (the whole list without a library; the unsaved ones with it)
    async show(nextPlans = [], { from = $("lobby-open"), box = null } = {}) {
      if (phase !== "closed") return;
      phase = "loading";
      // the list is read while the textures decode; the fall does not wait for it
      library = null; loadError = null; filter = { ...filter, q: "" }; search.value = "";
      const listed = works ? works.list({ sort: sortBy }).then((l) => { library = l; loadError = null; },
        (e) => { library = null; loadError = e?.status ? `HTTP ${e.status}` : String(e?.message ?? e); }) : Promise.resolve();
      await stylesheet();
      previous = { mode: root.dataset.mode || "", backHidden: $("back")?.hidden ?? true };
      plans = [...nextPlans]; selected = null; focus.hidden = true; page.classList.remove("pw-focused");
      status.hidden = true; words(); paintTheme();
      await Promise.race([listed, new Promise((r) => setTimeout(r, motionOff() ? 1500 : 250))]);
      render();
      if (works && !library && !loadError) listed.then(() => { if (phase !== "closed" && !selected) render(); });
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
    back, skip, reload: () => load(),
    destroy() { if (phase !== "closed") release(); controller.abort(); observer.disconnect(); page.remove(); },
  };
}

let singleton, prepared;
export function prepare(api) {
  if (!prepared) prepared = Promise.all([stylesheet(), import("./design.js"), import("./pastworks/works.mjs")]).then(async ([, design, lib]) => {
    const works = await lib.worksFor(api, { capable: hasCapability("works") });
    singleton = createPastWorks(api, { thumbnail: design.planThumbnail, works, mock: !!works?.mock, recent: design.recentPlans });
    return design;
  }).catch((e) => { prepared = null; throw e; });
  return prepared;
}
export async function start(api, options) {
  const design = await prepare(api);
  await singleton.show(design.recentPlans(), options);
}
