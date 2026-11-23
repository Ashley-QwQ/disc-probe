import { isActionEnter } from "./kit/shared.js";
// The news fax (prototype): a fax on the lobby desk that, when clicked, phones the person's own news source,
// downloads today's paper and prints it. The call hides the download: the handset lifts, the keys dial with
// their tones, the line rings until the data is in, then the paper prints and is laid on the desk.
//
// Download only. The page asks the local news API; Python tries the repository mirrors and falls back to
// its cache or sample. The core sends plain GETs, with no cookies, referrer or machine details. A skin
// "order" asks the same core for a parcel. Nothing is uploaded or counted. The first visit explains this.
//
// Every way out ends somewhere readable: no line (offline, refused, timed out) prints a receipt with redial
// and yesterday's paper; a reply that is not a paper prints what was wrong with it. Reduced motion skips the
// whole call (the paper is simply there when the data is); a click or Enter skips it at any moment; a page in
// the background skips its animations and stays quiet.
//
// Art (faxnews/fax.json, from art/desk/fax-news via faxnews/render_faxnews.py): the fax from straight above on
// the desk, its handset and the handset's shadow as separate pictures, and in canvas pixels the display, the
// keys and the output slot. The page draws the display's words, the key presses, the printout and the paper.

import { pageFlight, TOP_START } from "./flight.mjs";
import { prepareLobby, pushLobby } from "./lobby.js";
import * as sfx from "./faxsfx.mjs";
import { DEFAULT_SOURCE, withToken, PaperError, readPaper, readSkin, layOut, pick, resolveRef, compareVersions } from "./faxnews-data.mjs";
import { receive as receiveCommunity, mountList as mountCommunity } from "./community.mjs";

let communityData = null, communityError = '';

const KEY = { seen: "dp-fax-seen", source: "dp-fax-source", last: "dp-fax-last", parcels: "dp-fax-parcels" };
const TIMEOUT_MS = 120000, MAX_BYTES = 2 * 1024 * 1024, SHIP_MS = 3500;   // core retries each mirror for at most 8 seconds
const STR = {
  zh: {
    title: "新闻传真机", mast: "DP 日报", edition: "传真版", issue: (n) => `第 ${n} 期`, free: "免费",
    sample: "样张", local: (v) => `本机 ${v}`, newer: "新版本", upToDate: (v) => `本机 ${v} 已是最新`,
    toRelease: "去下载页", stories: "本报讯", ads: "广告", art: "本期盘面", by: (b) => `作者 ${b}`, bg: "盘面背景预设",
    joke: "笑一笑", coming: "以后会有", order: "订购", ordered: "已下单", shipping: "配送中……", delivered: "已送达，包裹在大厅桌上",
    shipFail: (e) => `没送到：${e}`, reorder: "重新订购", size: (k) => `约 ${k} KB`,
    foot: (s) => `本报只下载，不上传，不统计。来源：${s}`, redial: "重拨", about: "关于这台传真机",
    lcd: { idle: "DP 日报  按开始", dial: (n) => `拨号 ${n}`, ring: "响铃……", ok: "接通  接收中", print: "打印 1/1", done: (d) => `已收到 ${d}`,
           dead: "线路不通", bad: "收到的不是报纸", missing: (s) => `号码不存在 ${s}`, wait: "接收中……" },
    noticeTitle: "这台传真机", noticeWhat: "它是什么",
    noticeWhatText: "一台只收不发的传真机。点一下，它去你设定的地址取今天的“报纸”：DP 的新版本和更新日志、盘面背景预设、盘面作品、笑话和以后要做的功能。",
    noticeDo: "它会做什么", noticeDoText: "由 disc-probe 程序下载报纸，每个地址只发一个普通请求。没接通就试下一个，最后看上次的报纸或自带样张。点“订购”时，再下载那件皮肤包裹。",
    noticeNever: "它永远不做什么", noticeNeverText: "不上传任何东西，不带你的任何信息，不计数，不追踪，不在后台自己拨号。",
    source: "数据源地址", sourceDefault: "默认（GitHub 仓库）", sourceHelp: "默认取 GitHub 仓库里的报纸，也可以填自己的 HTTPS 地址。由 disc-probe 程序下载，只发一个普通请求，不上传任何东西。",
    reset: "用默认", dial: "拨号", sourceBad: "地址要是 HTTPS，不能带查询参数或片段",
    slipTitle: "传真回执", deadTitle: "没接通", deadText: "线路不通：可能没联网，或者对方没开机。", badTitle: "收到的不是报纸",
    badText: "对方有回应，但传来的内容看不懂：", missingTitle: "号码不存在", missingText: (s) => `对方说没有这份报纸（${s}）。`,
    lastPaper: (d) => `看上次的报纸（${d}）`, old: "旧报", changeSource: "换数据源地址",
    parcelTitle: "包裹", parcelText: (n) => `收到 ${n}。皮肤换装以后接上，现在先放在桌上。`, parcelClear: "收起包裹", close: "关闭",
  },
  en: {
    title: "News fax", mast: "DP Daily", edition: "Fax edition", issue: (n) => `No. ${n}`, free: "Free",
    sample: "Sample", local: (v) => `This copy ${v}`, newer: "New version", upToDate: (v) => `This copy ${v} is up to date`,
    toRelease: "Go to downloads", stories: "News", ads: "Advertisements", art: "Disc of the day", by: (b) => `By ${b}`, bg: "Disc background presets",
    joke: "Smile", coming: "Coming later", order: "Order", ordered: "Ordered", shipping: "On its way…", delivered: "Delivered: the parcel is on the lobby desk",
    shipFail: (e) => `Not delivered: ${e}`, reorder: "Order again", size: (k) => `about ${k} KB`,
    foot: (s) => `This paper only downloads; it uploads and counts nothing. Source: ${s}`, redial: "Redial", about: "About this fax",
    lcd: { idle: "DP DAILY  PRESS START", dial: (n) => `DIAL ${n}`, ring: "RINGING…", ok: "CONNECTED  RECEIVING", print: "PRINTING 1/1", done: (d) => `RECEIVED ${d}`,
           dead: "NO LINE", bad: "NOT A PAPER", missing: (s) => `NO SUCH NUMBER ${s}`, wait: "RECEIVING…" },
    noticeTitle: "This fax", noticeWhat: "What it is",
    noticeWhatText: "A fax that only receives. Press it and it fetches today's \"paper\" from the address you set: new DP versions and the changelog, disc background presets, disc artworks, jokes and what is planned.",
    noticeDo: "What it does", noticeDoText: "The disc-probe program downloads the paper, with one plain request per address. If the line is dead, it tries the next address, then the last paper or the bundled sample. Ordering a skin downloads its parcel too.",
    noticeNever: "What it never does", noticeNeverText: "It uploads nothing, sends nothing about you, counts nothing, tracks nothing, and never dials by itself.",
    source: "Source address", sourceDefault: "Default (GitHub repository)", sourceHelp: "The default paper lives in the GitHub repository. You can use your own HTTPS address. The disc-probe program downloads it with one plain request and uploads nothing.",
    reset: "Default", dial: "Dial", sourceBad: "Use HTTPS without a query or fragment",
    slipTitle: "Fax receipt", deadTitle: "No line", deadText: "The line is dead: no network, or nobody answering.", badTitle: "That was not a paper",
    badText: "Somebody answered, but what came through cannot be read:", missingTitle: "No such number", missingText: (s) => `The other end has no such paper (${s}).`,
    lastPaper: (d) => `Read the last paper (${d})`, old: "Old paper", changeSource: "Change the source address",
    parcelTitle: "Parcel", parcelText: (n) => `${n} arrived. Wearing a skin comes later; for now it waits on the desk.`, parcelClear: "Put the parcel away", close: "Close",
  },
};

let api, $, A = null, F = null, art = null, cssReady = null, prepared = null;
const root = document.documentElement;
const T = () => STR[api?.lang?.() === "en" ? "en" : "zh"];
const lang = () => (api?.lang?.() === "en" ? "en" : "zh");
const theme = () => (root.dataset.theme === "dark" ? "dark" : "paper");
const motionOff = () => !!api?.reduce;
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const shortDate = (d) => (d ? d.slice(5) : "");

// ---------------------------------------------------------------- the source and the download
export function sourceOf() { return store.get(KEY.source) || DEFAULT_SOURCE; }
export function validSource(s) {
  if (typeof s !== "string" || !s.trim() || s.length > 400) return false;
  s = s.trim();
  return s === DEFAULT_SOURCE || /^https:\/\/[^\s?#]+$/i.test(s);
}
const sourceURL = (s) => withToken(s === DEFAULT_SOURCE ? DEFAULT_SOURCE : `${DEFAULT_SOURCE}?source=${encodeURIComponent(s)}`);
// One GET with nothing of ours in it. Resolves {paper} or rejects with {kind: "dead" | "missing" | "bad", detail}.
export async function download(source, { signal, fetcher = fetch } = {}) {
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  signal?.addEventListener("abort", () => ctl.abort(), { once: true });
  let res, text;
  try {
    res = await fetcher(sourceURL(source), { method: "GET", cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer", redirect: "follow", signal: ctl.signal });
    if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { kind: "missing", detail: `HTTP ${res.status}` });
    text = await res.text();
  } catch (e) {
    if (e.kind) throw e;
    throw { kind: "dead", detail: signal?.aborted ? "aborted" : ctl.signal.aborted ? "timeout" : String(e?.message ?? e) };
  } finally { clearTimeout(timer); }
  if (text.length > MAX_BYTES) throw { kind: "bad", detail: `too large (${Math.round(text.length / 1024)} KB)` };
  let data;
  try { data = JSON.parse(text); } catch { throw { kind: "bad", detail: "not JSON" }; }
  try { return { paper: readPaper(data?.paper), raw: data?.paper, from: data?.from, source: data?.source }; } catch (e) {
    if (e instanceof PaperError) throw { kind: "bad", detail: e.problems.slice(0, 4).join("; ") };
    throw e;
  }
}
function remember(source, raw) {
  try { store.set(KEY.last, JSON.stringify({ source, at: Date.now(), paper: raw })); } catch {}
}
function lastPaper() {
  try { const v = JSON.parse(store.get(KEY.last) || "null"); return v?.paper ? { ...v, paper: readPaper(v.paper) } : null; } catch { return null; }
}

// ---------------------------------------------------------------- skin orders (they outlive the page)
const orders = new Map();         // id -> {state: "shipping" | "delivered" | "failed", error}
export function parcels() { try { const v = JSON.parse(store.get(KEY.parcels) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } }
function saveParcels(list) { store.set(KEY.parcels, JSON.stringify(list)); dispatchEvent(new CustomEvent("dp-fax-parcel", { detail: list })); }
export function clearParcels() { saveParcels([]); }
export async function order(skin, source, { fetcher = fetch, shipMs = SHIP_MS } = {}) {
  if (orders.get(skin.id)?.state === "shipping") return;
  orders.set(skin.id, { state: "shipping" });
  paintAds();
  try {
    const url = resolveRef(skin.package, source, new URL(".", import.meta.url).href);
    if (!url) throw new Error("bad address");
    const [res] = await Promise.all([fetcher(url, { method: "GET", cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" }),
      new Promise((r) => setTimeout(r, shipMs))]);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const got = readSkin(JSON.parse(await res.text()), skin.id);
    saveParcels([...parcels().filter((p) => p.id !== got.id), { id: got.id, name: got.name, tokens: got.tokens, at: Date.now() }]);
    orders.set(skin.id, { state: "delivered" });
    sfx.bell();
  } catch (e) {
    orders.set(skin.id, { state: "failed", error: e instanceof PaperError ? "not a skin parcel" : String(e?.message ?? e) });
  }
  paintAds();
}
const orderState = (id) => orders.get(id)?.state ?? (parcels().some((p) => p.id === id) ? "delivered" : null);

// ---------------------------------------------------------------- the page
function build() {
  const page = el("section", "fx"); page.id = "faxnews"; page.hidden = true;
  page.setAttribute("aria-label", T().title);
  const stage = el("div", "fx-stage");
  const top = el("img", "fx-top"), shadow = el("img", "fx-hs-shadow"), handset = el("img", "fx-handset");
  for (const i of [top, shadow, handset]) { i.alt = ""; i.decoding = "async"; i.draggable = false; }
  const lcd = el("div", "fx-lcd"); lcd.setAttribute("role", "status"); lcd.append(el("span"));
  const keys = el("div", "fx-keys");
  stage.append(top, shadow, handset, keys, lcd);
  const paper = el("article", "fx-paper"); paper.hidden = true; paper.tabIndex = -1;
  const notice = el("aside", "fx-notice"); notice.hidden = true;
  page.append(stage, paper, notice);
  document.body.append(page);
  F = { page, stage, top, shadow, handset, lcd, keys, paper, notice, keyEls: {} };
  page.addEventListener("click", (e) => { if (A?.running && !e.target.closest("button, a, input, .fx-paper, .fx-notice")) skip(); });
  addEventListener("keydown", (e) => {
    if (root.dataset.mode !== "faxnews" || e.defaultPrevented || e.isComposing) return;
    if (document.querySelector('.term:not([hidden]), .keys-help:not([hidden]), #set-menu:not([hidden])')) return;
    // ime-enter-exempt: Existing composition guard and input/button/link exclusion above; keep unchanged.
    if (e.key === "Enter" && A?.running && !e.target.closest?.("input, button, a")) { e.preventDefault(); e.stopImmediatePropagation(); skip(); }
  }, { capture: true });
  $("back")?.addEventListener("click", (e) => { if (root.dataset.mode === "faxnews") { e.preventDefault(); e.stopImmediatePropagation(); back(); } }, { capture: true });
  addEventListener("resize", place);
  new MutationObserver(() => { paintTheme(); }).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  addEventListener("dp-lang", () => { if (!F.page.hidden) { paintLCD(); if (A?.shown) A.shown(); if (!F.notice.hidden) showNotice(noticeThen); } });
  document.addEventListener("visibilitychange", () => { if (document.hidden && A?.running) skip(true); });
}
async function loadArt() {
  art ??= await fetch(new URL("./faxnews/fax.json", import.meta.url)).then((r) => r.json());
  return art;
}
function paintTheme() {
  if (!F || !art || (!prepared && F.page.hidden)) return;
  const t = theme(), base = new URL("./faxnews/", import.meta.url).href;
  F.top.src = `${base}top_${t}.webp`; F.shadow.src = `${base}handset_shadow_${t}.webp`; F.handset.src = `${base}handset_${t}.webp`;
}
// Project the baked body and slot with the stage so the paper follows the fax at any size.
function place() {
  if (!F || !art) return;
  F.delivery?.cancel();
  const [w, h] = art.canvas, vw = innerWidth, vh = innerHeight;
  const [left, top, right, bottom] = art.body_rect;
  const [sx0, , sx1, sy] = art.slot, slotX = (sx0 + sx1) / 2;
  const stacked = vw <= 760;
  const k = stacked ? Math.min(vw * .72 / (right - left), vh * .27 / (bottom - top))
    : Math.max(vw / w, Math.min(vh / h, vw * .47 / (right - left)));
  const x = stacked ? vw / 2 - slotX * k : Math.max((vw - w * k) / 2, 12 - left * k);
  const y = stacked ? -top * k : (vh - h * k) / 2;
  F.page.classList.toggle("fx-stacked", stacked);
  F.stage.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
  F.page.style.setProperty("--fx-body-right", `${x + right * k}px`);
  F.page.style.setProperty("--fx-slot-y", `${y + sy * k}px`);
  F.slot = { x: x + slotX * k, y: y + sy * k, width: (sx1 - sx0) * k * .94 };
  F.focus = [x + art.focus[0] * k, y + art.focus[1] * k];
  F.bodyWidth = (right - left) * k;
}
function layoutArt() {
  const [W, H] = art.canvas;
  Object.assign(F.stage.style, { width: `${W}px`, height: `${H}px` });
  Object.assign(F.top.style, { left: 0, top: 0, width: `${W}px`, height: `${H}px` });
  const box = (img, [x0, y0, x1, y1]) => Object.assign(img.style, { left: `${x0}px`, top: `${y0}px`, width: `${x1 - x0}px`, height: `${y1 - y0}px` });
  box(F.handset, art.handset.box); box(F.shadow, art.handset_shadow.box);
  const [cx, cy] = art.handset.centre;
  F.handset.style.transformOrigin = `${cx - art.handset.box[0]}px ${cy - art.handset.box[1]}px`;
  // the display: a box mapped onto its quad
  const q = art.screen_quad, w = Math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]), h = Math.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]);
  Object.assign(F.lcd.style, { width: `${w}px`, height: `${h}px`, left: `${q[0][0]}px`, top: `${q[0][1]}px`, fontSize: `${(h * .42).toFixed(1)}px` });
  // the keys the call presses, with their legends
  F.keys.replaceChildren();
  for (const [name, kq] of Object.entries(art.keys)) {
    const xs = kq.quad.map((p) => p[0]), ys = kq.quad.map((p) => p[1]);
    const n = el("i", "fx-key", name === "start" ? "" : name === "star" ? "*" : name === "hash" ? "#" : name);
    if (name === "start") n.classList.add("start");
    Object.assign(n.style, { left: `${Math.min(...xs)}px`, top: `${Math.min(...ys)}px`, width: `${Math.max(...xs) - Math.min(...xs)}px`, height: `${Math.max(...ys) - Math.min(...ys)}px` });
    F.keys.append(n); F.keyEls[name] = n;
  }
}
export function prepare(homeApi) {
  api = homeApi; $ = api.$;
  if (!cssReady) {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = new URL("./faxnews.css", import.meta.url).href;
    cssReady = new Promise((r) => { css.onload = css.onerror = r; });
    document.head.append(css);
  }
  prepared ??= (async () => {
    await loadArt();
    if (!F) { build(); layoutArt(); }
    paintTheme(); place();
    await Promise.race([cssReady, new Promise((r) => setTimeout(r, 1500))]);
    // decode() waits for a rendered frame, which a page in the background never gets: never wait on it long
    await Promise.race([Promise.all([F.top, F.handset, F.shadow].map((i) => i.decode?.().catch(() => {}))), new Promise((r) => setTimeout(r, 600))]);
  })().catch((e) => { prepared = null; throw e; });
  return prepared;
}

// ---------------------------------------------------------------- the flight in and out (as the drive's)
const focusPoint = () => [F.focus[0], F.stage.offsetTop + F.focus[1]];
function pushFor(from) {
  const r = from.getBoundingClientRect(), [sx, sy] = [r.left + r.width / 2, r.top + r.height / 2];
  const push = Math.max(1.4, Math.min(4, F.bodyWidth / TOP_START / Math.max(40, r.width)));
  return { origin: `${sx}px ${sy}px`, to: `translate(${innerWidth / 2 - sx}px, ${innerHeight / 2 - sy}px) scale(${push.toFixed(3)})` };
}
let flight = null, from = null;
export async function start(homeApi, { from: origin = null } = {}) {
  api = homeApi; $ = api.$;
  if (root.dataset.mode === "faxnews") return;
  await prepare(homeApi);       // the art's numbers and markup; pictures still decoding after 0.6 s come in late
  from = origin;
  const fly = !!origin?.getBoundingClientRect?.().width && !motionOff();
  const push = fly ? pushLobby(pushFor(origin)) : null;
  if (push) await new Promise((r) => setTimeout(r, 300));
  root.dataset.mode = "faxnews";
  $("back").hidden = false;
  resetStage();
  F.page.hidden = false;
  place();
  if (push) {
    const [tx, ty] = focusPoint();
    F.page.style.transformOrigin = `${tx}px ${ty}px`;
    const a = pageFlight(F.page, focusPoint);
    flight = { push, anims: [...push.anims, a] };
    a.finished.catch(() => {}).then(() => { if (flight?.push !== push) return; push.done(); flight = null; F.page.style.transformOrigin = ""; });
  }
  if (store.get(KEY.seen)) call();
  else showNotice(() => { store.set(KEY.seen, "1"); call(); });
}
function leave() {
  A?.abort?.abort(); A = null;
  F.page.hidden = true; F.paper.hidden = true; F.notice.hidden = true;
  F.page.getAnimations({ subtree: true }).forEach((a) => a.cancel());
  F.paper.replaceChildren(); F.notice.replaceChildren();
  for (const image of [F.top, F.shadow, F.handset]) image.removeAttribute("src");
  prepared = null;
  root.dataset.mode = ""; $("back").hidden = true;
  api.toLobby();
  setTimeout(() => from?.focus?.({ preventScroll: true }), 0);
}
export async function back() {
  if (!F || F.page.hidden || F.leaving) return;
  F.leaving = true;
  try {
    A?.abort?.abort();
    if (A) { A.running = false; A.cancelled = true; A.stopRing?.(); }
    if (motionOff() || !from?.isConnected) { leave(); return; }
    if (flight) {
      const f = flight; flight = null;
      f.anims.forEach((a) => a.reverse());
      await Promise.all(f.anims.map((a) => a.finished)).catch(() => {});
      leave(); f.push.done(); F.page.style.transformOrigin = "";
      return;
    }
    await Promise.race([prepareLobby(), new Promise(resolve => setTimeout(resolve, 600))]);
    const pull = pushLobby(pushFor(from), true);
    const a = pageFlight(F.page, focusPoint, true);
    await Promise.all([a.finished, pull.finished]).catch(() => {});
    leave(); a.cancel(); pull.done(); F.page.style.transformOrigin = "";
  } finally { F.leaving = false; }
}

// ---------------------------------------------------------------- the call
function resetStage() {
  for (const n of [F.handset, F.shadow, F.paper]) n.getAnimations().forEach((a) => a.cancel());
  F.handset.style.transform = F.shadow.style.transform = F.shadow.style.opacity = F.shadow.style.filter = "";
  F.paper.hidden = true; F.notice.hidden = true;
  Object.values(F.keyEls).forEach((k) => k.classList.remove("down"));
  setLCD("idle");
}
let lcdState = ["idle"];
function setLCD(state, ...args) { lcdState = [state, ...args]; paintLCD(); }
function paintLCD() {
  if (!F) return;
  const [s, ...a] = lcdState, w = T().lcd[s];
  F.lcd.firstElementChild.textContent = typeof w === "function" ? w(...a) : w;
  F.lcd.dataset.state = s;
}
// the handset lifted: bigger (nearer the camera, which looks straight down), a little toward the lamp's side; its
// shadow falls further off (down-left, away from the lamp), softer and lighter
const LIFT = { handset: { transform: "translate(-18px, -30px) scale(1.3)" },
  shadow: { transform: "translate(-48px, 56px) scale(1.08)", opacity: .5, filter: "blur(10px)" } };
// the number dialled: the paper's day, as a phone number would read (07-11 14)
const numberFor = (day) => `07${day.slice(5, 7)}${day.slice(8, 10)}`;
function skip(quiet = false) {
  if (!A?.running) return;
  A.skipped = true; if (quiet) A.quiet = true;
  A.stopRing?.();
  A.wake?.();
  F.page.getAnimations({ subtree: true }).forEach((a) => { if (a.playState === "running") a.finish(); });
}
async function call() {
  A?.abort?.abort();
  const run = A = { running: true, skipped: motionOff() || document.hidden, quiet: document.hidden, abort: new AbortController() };
  const alive = () => A === run && !run.cancelled;
  const source = sourceOf();
  resetStage();
  // the download starts at once; the call is there to cover it
  const community = receiveCommunity({ refresh: true, signal: run.abort.signal }).then(r => {
    if (alive()) { communityData = r; communityError = ''; }
  }, e => { if (alive()) { communityData = null; communityError = String(e.message || e); } });
  const got = Promise.all([download(source, { signal: run.abort.signal }).then((r) => ({ ok: true, ...r }), (e) => ({ ok: false, ...e })), community]).then(([r]) => r);
  const wait = (ms) => new Promise((r) => { if (run.skipped) return r(); const t = setTimeout(r, ms); run.wake = () => { clearTimeout(t); r(); }; });
  const anim = (node, frames, opts) => { const a = node.animate(frames, { fill: "forwards", ...opts }); if (run.skipped) a.finish(); return a.finished.catch(() => {}); };
  const sound = (f) => { if (!run.quiet && !run.skipped) f(); };
  const day = today();
  // 1. the handset lifts (bigger: nearer the camera; its shadow falls further off and softens)
  await wait(motionOff() ? 0 : 420);
  if (!alive()) return;
  setLCD("dial", numberFor(day));
  await Promise.all([
    anim(F.handset, [{ transform: "none" }, LIFT.handset], { duration: 520, easing: "cubic-bezier(.3, .7, .2, 1)" }),
    anim(F.shadow, [{ transform: "none", opacity: 1, filter: "blur(0)" }, LIFT.shadow], { duration: 520, easing: "cubic-bezier(.3, .7, .2, 1)" }),
  ]);
  // 2. the keys dial themselves, with their tones
  for (const d of numberFor(day)) {
    if (!alive()) return;
    const k = F.keyEls[d];
    if (!run.skipped && k) { k.classList.add("down"); sound(() => sfx.key(d)); await wait(120); k.classList.remove("down"); await wait(110); }
  }
  // 3. it rings until the paper is in (at least once), then the line answers
  if (!alive()) return;
  setLCD("ring");
  let result = null;
  got.then((r) => { result = r; });          // the ring goes on at least once even when the paper is already here
  if (!run.skipped && !run.quiet) run.stopRing = sfx.ring();
  await wait(1600);
  // a real timer even when skipped: the download needs the event loop to turn
  while (!result && alive()) { if (run.skipped) setLCD("wait"); await Promise.race([got, new Promise((r) => setTimeout(r, run.skipped ? 50 : 400))]); }
  run.stopRing?.();
  if (!alive()) return;
  if (!result.ok) return hangUp(run, result, source);
  setLCD("ok");
  sound(sfx.connect);
  remember(result.source, result.raw);
  // press start, put the handset back
  const start_ = F.keyEls.start;
  if (!run.skipped && start_) { await wait(700); start_.classList.add("down"); await wait(160); start_.classList.remove("down"); }
  await Promise.all([
    anim(F.handset, [LIFT.handset, { transform: "none" }], { duration: 420, easing: "cubic-bezier(.5, 0, .7, 1)" }),
    anim(F.shadow, [LIFT.shadow, { transform: "none", opacity: 1, filter: "blur(0)" }], { duration: 420, easing: "cubic-bezier(.5, 0, .7, 1)" }),
  ]);
  // 4. the paper prints out of the slot
  if (!alive()) return;
  const lay = layOut(result.paper, { local: localVersion(), day });
  setLCD("print");
  sound(() => sfx.print(1.6));
  showPaper(lay, result.source, false, result.from);
  if (!run.skipped) await deliverSheet(1700, 24);
  if (!alive()) return;
  setLCD("done", shortDate(result.paper.date));
  run.running = false;
}
// no paper: busy tone, the handset goes back, a receipt prints instead
async function hangUp(run, result, source) {
  setLCD(result.kind === "missing" ? "missing" : result.kind === "bad" ? "bad" : "dead", result.detail ?? "");
  if (!run.quiet && !run.skipped) sfx.busy();
  const a = F.handset.animate([LIFT.handset, { transform: "none" }], { duration: run.skipped ? 0 : 420, fill: "forwards" });
  F.shadow.animate([LIFT.shadow, { transform: "none", opacity: 1, filter: "blur(0)" }], { duration: run.skipped ? 0 : 420, fill: "forwards" });
  await a.finished.catch(() => {});
  if (A !== run || run.cancelled) return;
  showSlip(result, source);
  if (!run.skipped) await deliverSheet(540, 10);
  run.running = false;
}
function localVersion() { return ($("wm-ver")?.textContent || "").trim(); }

// ---------------------------------------------------------------- printing
async function deliverSheet(feedTime, steps) {
  const paper = F.paper, { x, y, width } = F.slot;
  const slotY = F.stage.offsetTop + y;
  const top = paper.offsetTop, w = paper.offsetWidth, h = paper.offsetHeight;
  const room = top + parseFloat(getComputedStyle(paper).maxHeight) - slotY;
  if (!w || !h || room <= 0) return;
  const scale = Math.min(1, width / w, room / h);
  const dx = x - paper.offsetLeft - w * scale / 2, dy = slotY - top;
  const duration = feedTime + 420;
  // Advance the cut and the sheet together, keeping the visible edge fixed at the slot lip.
  const animation = F.delivery = paper.animate([
    { transform: `translate(${dx}px, ${dy - h * scale}px) scale(${scale})`, clipPath: "inset(100% 0 0)", easing: `steps(${steps}, end)` },
    { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, clipPath: "inset(0% 0 0)", offset: feedTime / duration, easing: "cubic-bezier(.2, .8, .2, 1)" },
    { transform: "none", clipPath: "inset(-64px -64px -64px)" },
  ], { duration });
  await animation.finished.catch(() => {});
  if (F.delivery === animation) F.delivery = null;
}
// the receipt for a call that brought no paper: what happened, and every way on from here
function showSlip(result, source) {
  const t = T(), slip = F.paper;
  slip.replaceChildren(); slip.className = "fx-paper fx-slip";
  slip.append(el("p", "fx-slip-kicker", t.slipTitle));
  const [title, text] = result.kind === "missing" ? [t.missingTitle, t.missingText(result.detail)]
    : result.kind === "bad" ? [t.badTitle, t.badText] : [t.deadTitle, t.deadText];
  slip.append(el("h2", "", title), el("p", "", text));
  if (result.kind === "bad") slip.append(el("pre", "fx-slip-detail", result.detail));
  slip.append(el("p", "fx-slip-src", source === DEFAULT_SOURCE ? t.sourceDefault : source));
  const row = el("div", "fx-slip-row");
  const redial = el("button", "fx-btn primary", t.redial); redial.type = "button"; redial.addEventListener("click", () => call());
  row.append(redial);
  const last = lastPaper();
  if (last) {
    const b = el("button", "fx-btn", t.lastPaper(shortDate(last.paper.date))); b.type = "button";
    b.addEventListener("click", () => { setLCD("done", shortDate(last.paper.date)); showPaper(layOut(last.paper, { local: localVersion(), day: today() }), last.source, true); });
    row.append(b);
  }
  const ch = el("button", "fx-btn", t.changeSource); ch.type = "button"; ch.addEventListener("click", () => showNotice(() => call()));
  row.append(ch);
  slip.append(row);
  slip.hidden = false;
  slip.scrollTop = 0;
  A && (A.shown = () => showSlip(result, source));
  redial.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- the paper
let current = null;
function showPaper(lay, source, old, from = "network") {
  current = { lay, source, old, from };
  const t = T(), L = lang(), P = F.paper;
  P.replaceChildren(); P.className = "fx-paper";
  // masthead
  const mast = el("header", "fx-mast");
  const issue = Math.max(1, Math.floor((Date.parse(lay.date) - Date.parse("2026-11-01")) / 864e5) + 1);
  mast.append(el("h1", "", t.mast));
  const line = el("p", "fx-dateline");
  line.append(el("span", "", lay.date), el("span", "", t.edition), el("span", "", t.issue(issue)), el("span", "", t.free));
  if (lay.local) line.append(el("span", "", t.local(lay.local)));
  mast.append(line);
  if (lay.sample || old) { const s = el("span", "fx-stamp", old ? t.old : t.sample); mast.append(s); }
  P.append(mast);
  if (from === "cache" || from === "bundled") {
    const note = lang() === "zh"
      ? (from === "cache" ? `没连上，显示的是上次的报纸（${shortDate(lay.date)}）` : "没连上，先看看程序自带的样张。")
      : (from === "cache" ? `No line; showing the last paper (${shortDate(lay.date)}).` : "No line; showing the sample that comes with the program.");
    P.append(el("p", "fx-note", note));
  }
  // the lead: a newer version, else the newest story
  if (lay.lead) {
    const lead = el("section", "fx-lead");
    if (lay.lead.kind === "release") {
      lead.append(el("p", "fx-kicker", `${t.newer} · ${lay.lead.version} · ${lay.lead.date}`), el("h2", "", pick(lay.lead.headline, L)));
      if (lay.lead.summary) lead.append(el("p", "fx-deck", pick(lay.lead.summary, L)));
      if (lay.lead.url) { const a = el("a", "fx-btn", t.toRelease); a.href = lay.lead.url; a.target = "_blank"; a.rel = "noopener noreferrer"; lead.append(a); }
    } else {
      lead.append(el("p", "fx-kicker", `${lay.lead.version} · ${lay.lead.date}`), el("h2", "", pick(lay.lead.title, L)), el("p", "fx-deck", pick(lay.lead.story, L)));
      if (lay.upToDate) lead.append(el("p", "fx-note", t.upToDate(lay.local)));
    }
    P.append(lead);
  }
  const cols = el("div", "fx-cols");
  // column 1: the changelog as news stories
  const c1 = el("section", "fx-col");
  if (communityData) mountCommunity(c1, communityData, {zh: L === 'zh', onImported: () => api.syncState?.()});
  else if (communityError) c1.append(el('p','fx-note',(L === 'zh' ? '社区提示未取到：' : 'Community hints unavailable: ') + communityError));
  if (lay.stories.length) {
    c1.append(el("h3", "fx-sect", t.stories));
    for (const s of lay.stories) {
      const a = el("article", "fx-story");
      a.append(el("h4", "", pick(s.title, L)), el("p", "fx-byline", `${s.version} · ${s.date}`), el("p", "", pick(s.story, L)));
      c1.append(a);
    }
  }
  // column 2: the skins, as retro ads
  const c2 = el("section", "fx-col fx-ads");
  if (lay.skins.length) {
    c2.append(el("h3", "fx-sect", t.ads));
    for (const s of lay.skins) c2.append(adFor(s, source));
  }
  // column 3: the disc of the day, a background preset, a joke, what comes later
  const c3 = el("section", "fx-col");
  if (lay.artwork) {
    const f = el("figure", "fx-art");
    c3.append(el("h3", "fx-sect", t.art));
    const img = el("img"); img.alt = pick(lay.artwork.title, L); img.loading = "lazy"; img.decoding = "async";
    img.src = resolveRef(lay.artwork.image, source, new URL(".", import.meta.url).href);
    img.referrerPolicy = "no-referrer";
    const shot = el("div", "fx-halftone"); shot.append(img);
    const cap = el("figcaption");
    cap.append(el("b", "", pick(lay.artwork.title, L)), document.createTextNode(" " + [pick(lay.artwork.disc, L), lay.artwork.by ? t.by(pick(lay.artwork.by, L)) : ""].filter(Boolean).join(" · ")));
    if (lay.artwork.caption) cap.append(el("span", "", pick(lay.artwork.caption, L)));
    f.append(shot, cap);
    c3.append(f);
  }
  if (lay.background) {
    c3.append(el("h3", "fx-sect", t.bg));
    const b = el("figure", "fx-bg"), cv = el("canvas"); cv.width = cv.height = 176;
    b.append(cv, el("figcaption", "", `${pick(lay.background.name, L)}${lay.background.note ? " · " + pick(lay.background.note, L) : ""}`));
    c3.append(b);
    drawPattern(cv, lay.background.pattern);
  }
  if (lay.joke) { const j = el("aside", "fx-joke"); j.append(el("h3", "fx-sect", t.joke), el("p", "", pick(lay.joke, L))); c3.append(j); }
  if (lay.coming.length) {
    const ul = el("ul", "fx-coming");
    for (const c of lay.coming) { const li = el("li"); li.append(el("b", "", pick(c.title, L))); if (c.note) li.append(document.createTextNode(" " + pick(c.note, L))); ul.append(li); }
    c3.append(el("h3", "fx-sect", t.coming), ul);
  }
  cols.append(c1, c2, c3);
  P.append(cols);
  const foot = el("footer", "fx-foot");
  foot.append(el("p", "", t.foot(source)));
  const row = el("div", "fx-slip-row");
  const redial = el("button", "fx-btn", t.redial); redial.type = "button"; redial.addEventListener("click", () => call());
  const about = el("button", "fx-btn", t.about); about.type = "button"; about.addEventListener("click", () => showNotice(() => call()));
  row.append(redial, about); foot.append(row);
  P.append(foot);
  P.hidden = false; P.scrollTop = 0;
  if (A) A.shown = () => showPaper(lay, source, old, from);
  P.focus({ preventScroll: true });
}
function adFor(s, source) {
  const t = T(), L = lang(), ad = el("article", "fx-ad"); ad.dataset.skin = s.id;
  const sw = el("div", "fx-swatches");
  for (const c of s.swatches) { const d = el("i"); d.style.background = c; sw.append(d); }
  ad.append(el("p", "fx-ad-new", lang() === "en" ? "NEW!" : "新品"), el("h4", "", pick(s.name, L)), sw, el("p", "", pick(s.pitch, L)));
  const price = el("p", "fx-ad-price", [pick(s.price, L), s.size_kb != null ? t.size(s.size_kb) : ""].filter(Boolean).join(" · "));
  const act = el("div", "fx-ad-act");
  ad.append(price, act);
  paintAd(ad, s, source);
  return ad;
}
function paintAd(ad, s, source) {
  const t = T(), act = ad.querySelector(".fx-ad-act"), st = orderState(s.id), info = orders.get(s.id);
  act.replaceChildren();
  if (!st || st === "failed") {
    const b = el("button", "fx-btn primary", st === "failed" ? t.reorder : t.order); b.type = "button";
    b.addEventListener("click", () => order(s, source));
    act.append(b);
    if (st === "failed") act.append(el("p", "fx-ad-state warn", t.shipFail(info?.error ?? "")));
  } else {
    act.append(el("span", "fx-ordered", t.ordered), el("p", "fx-ad-state", st === "delivered" ? t.delivered : t.shipping));
  }
  ad.dataset.state = st ?? "";
}
function paintAds() {
  if (!F || F.paper.hidden || !current) return;
  for (const ad of F.paper.querySelectorAll(".fx-ad")) {
    const s = current.lay.skins.find((x) => x.id === ad.dataset.skin);
    if (s) paintAd(ad, s, current.source);
  }
}
// a background preset, printed as a small disc (design/pattern.mjs draws the pattern, slot 0 = ink)
async function drawPattern(cv, p) {
  try {
    const { render } = await import("./design/pattern.mjs");
    const n = cv.width, cell = 120 / n;
    const out = render({ version: 1, ...p, origin_mm: [0, 0], phase_mm: [0, 0], materials: [0, 1], ...(p.coordinates === "polar" ? { reference_radius_mm: 40 } : {}) },
      { width: n, height: n, cell_mm: cell, left_mm: -60, top_mm: -60, annulus_mm: [7.5, 59] });
    const g = cv.getContext("2d"), im = g.createImageData(n, n), ink = getComputedStyle(F.paper).color.match(/\d+/g).map(Number);
    for (let i = 0; i < out.length; i++) {
      const v = out[i]; if (v === 65535) continue;
      const a = v === 0 ? 235 : 46;
      im.data.set([ink[0], ink[1], ink[2], a], i * 4);
    }
    g.putImageData(im, 0, 0);
  } catch (e) { cv.replaceWith(el("p", "fx-note", String(e?.message ?? e))); }
}

// ---------------------------------------------------------------- the first-visit note (and the source address)
let noticeThen = null;
function showNotice(then) {
  const t = T(), N = F.notice;
  noticeThen = then;
  N.replaceChildren();
  N.append(el("h2", "", t.noticeTitle));
  for (const [h, p] of [[t.noticeWhat, t.noticeWhatText], [t.noticeDo, t.noticeDoText], [t.noticeNever, t.noticeNeverText]]) N.append(el("h3", "", h), el("p", "", p));
  const lab = el("label", "fx-src");
  const input = el("input"); input.type = "text"; input.spellcheck = false; input.autocomplete = "off";
  const source = sourceOf();
  input.placeholder = t.sourceDefault;
  input.value = source === DEFAULT_SOURCE ? "" : source;
  const help = el("small", "", t.sourceHelp), err = el("small", "fx-src-err"); err.hidden = true;
  lab.append(el("span", "", t.source), input, help, err);
  const row = el("div", "fx-slip-row");
  const dial = el("button", "fx-btn primary", t.dial); dial.type = "button";
  const reset = el("button", "fx-btn", t.reset); reset.type = "button";
  reset.addEventListener("click", () => { input.value = ""; err.hidden = true; });
  const go = () => {
    const v = input.value.trim() || DEFAULT_SOURCE;
    if (!validSource(v)) { err.textContent = t.sourceBad; err.hidden = false; input.focus(); return; }
    if (v === DEFAULT_SOURCE) store.del(KEY.source); else store.set(KEY.source, v);
    N.hidden = true; then?.();
  };
  dial.addEventListener("click", go);
  input.addEventListener("keydown", (e) => { if (isActionEnter(e)) { e.preventDefault(); go(); } });
  row.append(dial, reset);
  N.append(lab, row);
  F.paper.hidden = true;
  N.hidden = false;
  setLCD("idle");
  dial.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- the parcel on the lobby desk
export async function openParcel(homeApi, anchor) {
  api = homeApi; $ = api.$;
  prepare(homeApi).catch(() => {});
  await Promise.race([cssReady, new Promise((r) => setTimeout(r, 800))]);     // measured below: the slip's style first
  document.querySelector(".fx-parcel")?.remove();
  const t = T(), list = parcels();
  if (!list.length) return;
  const card = el("div", "fx-parcel"); card.setAttribute("role", "dialog"); card.setAttribute("aria-label", t.parcelTitle);
  card.append(el("h3", "", t.parcelTitle), el("p", "", t.parcelText(list.map((p) => pick(p.name, lang())).join("、"))));
  const row = el("div", "fx-slip-row");
  const clear = el("button", "fx-btn", t.parcelClear); clear.type = "button";
  const close = el("button", "fx-btn", t.close); close.type = "button";
  clear.addEventListener("click", () => { clearParcels(); card.remove(); });
  close.addEventListener("click", () => card.remove());
  card.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); card.remove(); anchor?.focus?.(); } });
  row.append(clear, close); card.append(row);
  const r = anchor?.getBoundingClientRect?.();
  document.body.append(card);
  if (r) Object.assign(card.style, { left: `${Math.max(16, Math.min(innerWidth - card.offsetWidth - 16, r.left + r.width / 2 - card.offsetWidth / 2))}px`, top: `${Math.max(16, r.top - card.offsetHeight - 12)}px` });
  close.focus({ preventScroll: true });
}

// for tests
export const _test = { STR, numberFor, orders, compareVersions };
