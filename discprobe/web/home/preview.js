// The preview page: look at the disc as it will be written, then make the burn file. A mode of the
// home page like design.js, and laid out like it: title at the top left, the disc in the middle with
// the view switch at its top right, the burn file in the right column.
//
// start(api, ctx), where ctx is
//   { media: "dvd"|"cd", item, alongTrackMeasured?,
//     project: { name?, cellMm?, render(ppm) -> canvas of the toned design, 120 mm square, centre in the middle },
//     exportIso(onProgress, { signal }) -> Promise<{ path, sectors, bytes }>,
//     back(), next?(iso), showInFolder?(path) }
// Starting again with the same ctx keeps the file already made. Nothing here touches a drive.
// The first layout and words came from a Codex draft (2026-11-10); rewritten to the design page's style.

import { DEFAULT_POSE } from "./sim/model.mjs";
import { SimView } from "./sim/view.mjs";

let simulation = null;
let api, $, ctx = null, W = null, life = null, state = null, src = null, view = "design";
const root = document.documentElement;
const isOn = () => root.dataset.mode === "preview";
const V = { s: 1, cx: 0, cy: 0, w: 0, h: 0, dpr: 1, moved: false };   // moved: the user zoomed or panned
const PHOTO_DEFAULTS = { photoLook: 1, flash: 1, wear: 45, background: 0 };
const look = { ...DEFAULT_POSE, ...PHOTO_DEFAULTS };
let twist = 1;                       // degrees at the outer edge in the "off by a little" view

const STR = {
  zh: {
    title: "预览", next: "下一步：刻录", views: "预览方式",
    v: { design: "设计投影", off: "失配模拟", look: "拟真", read: "成品读回" },
    file: "刻录文件", fileNote: "把设计变成可以刻录的文件。生成以后才能去刻录。",
    make: "生成刻录文件", again: "重新生成", cancel: "取消", making: "正在生成…", made: "刻录文件已生成",
    cancelled: "已取消，可以重新生成。", failed: "没有生成出来。", sectors: "扇区", where: "保存位置", folder: "在文件夹里显示",
    folderLater: "接上桌面服务以后才能打开文件夹。", details: "详细信息",
    cd: "这张 CD 还没做拍照标定：文件照样能生成，但刻出来的图可能整体歪一点。",
    offH: "差一点会怎样", offNote: "标定差一点时，图会一圈一圈地拧开，离中间那一圈越远拧得越多。这就是要先标定的原因。",
    offAt: "外圈偏多少", lookH: "拟真", lookNote: "模型预测，不是照片。拖动太阳移动灯，拖动手机移动相机。转动或倾斜盘片，看看图案和彩虹怎样变化。",
    photoLook: "照片感", flash: "闪光灯（关闭用室内灯）", wear: "灰尘和划痕", background: "背后是什么", hand: "手心", table: "暗桌面", roughNote: "按实拍照片加了反光、划痕和手机成像的瑕疵。",
    rotate: "转动盘片", exposure: "曝光", camera: "手机", height: "相机高度", lightHeight: "灯的高度", resetLook: "恢复默认位置",
    loading: "正在准备设计…", refining: "正在细化…", simError: "模拟没有完成，请返回设计页再试。", cdModel: "此模型适用于 DVD，暂不预测 CD 的外观。",
    tilt: "盘斜多少", light: "灯", readH: "先刻录，再读回", readNote: "刻好以后回到这里，把盘读回来和设计对比。现在还没有刻好的盘。",
    dim: "压暗的内圈和外圈不刻图。", fit: "适应", noProject: "设计页还没有图。回去放一张图再来。",
  },
  en: {
    title: "Preview", next: "Next: burn", views: "Preview mode",
    v: { design: "Design", off: "Off by a little", look: "Simulated", read: "Read back" },
    file: "Burn file", fileNote: "Turn the design into a file to burn. Make it before going on to burn.",
    make: "Make the burn file", again: "Make it again", cancel: "Cancel", making: "Making…", made: "Burn file ready",
    cancelled: "Cancelled. You can make it again.", failed: "The file wasn't made.", sectors: "sectors", where: "Saved at", folder: "Show in folder",
    folderLater: "Opening the folder needs the desktop service.", details: "Details",
    cd: "This CD hasn't had its photo calibration yet: the file can still be made, but the picture may come out slightly turned.",
    offH: "What a small error does", offNote: "When calibration is a little off, the picture twists ring by ring, more the further from the middle ring. That is why calibration comes first.",
    offAt: "Off at the outer edge", lookH: "Simulated look", lookNote: "Model prediction, not a photo. Drag the sun to move the light and the phone to move the camera. Turn or tilt the disc to see the picture and rainbow change.",
    photoLook: "Photo look", flash: "Flash (off: room lamp)", wear: "Dust and scratches", background: "Behind the disc", hand: "Hand", table: "Dark table", roughNote: "Reflections, scratches and phone-camera imperfections added from photo references.",
    rotate: "Turn the disc", exposure: "Exposure", camera: "Phone", height: "Camera height", lightHeight: "Light height", resetLook: "Reset the view",
    loading: "Preparing the design…", refining: "Refining…", simError: "Simulation failed. Return to Design and try again.", cdModel: "This model predicts DVD appearance. CD appearance is not available yet.",
    tilt: "Disc tilt", light: "Light", readH: "Burn first, then read back", readNote: "After burning, come back here to read the disc and compare it with the design. There's no burned disc yet.",
    dim: "The dimmed inner and outer rings aren't drawn.", fit: "Fit", noProject: "The design page has no picture yet. Go back and add one.",
  },
};
const T = () => STR[api.lang()] ?? STR.zh;
const SUN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/></svg>';
const RANGE = { dvd: [24, 58], cd: [23, 58] };

// ---------------------------------------------------------------- building
function build() {
  if (!document.querySelector('link[href$="design.css"]')) {
    const d = document.createElement("link"); d.rel = "stylesheet"; d.href = new URL("./design.css", import.meta.url).href; document.head.append(d);
  }
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = new URL("./preview.css", import.meta.url).href;
  document.head.append(css);
  const ws = document.createElement("div");
  ws.className = "ws pv";
  ws.innerHTML = `<div class="ws-title"><b class="pname"></b><span class="sub"></span></div>` +
    `<aside class="col col-r"></aside>` +
    `<div class="cv"><canvas class="main"></canvas>` +
    `<div class="seg viewsw" role="group">${Object.keys(STR.zh.v).map((k) => `<button type="button" data-v="${k}"></button>`).join("")}</div>` +
    `<p class="cv-note"></p><div class="empty-c" hidden><p></p></div>` +
    `<button class="pv-sun" type="button" hidden>${SUN}</button>` +
    `<button class="pv-phone" type="button" hidden><svg viewBox="0 0 24 24"><rect x="6" y="2.5" width="12" height="19" rx="2"/><path d="M10 5h4M11 18.5h2"/></svg></button>` +
    `<button class="zoomr" type="button"></button></div>`;
  document.body.append(ws);
  const q = (s) => ws.querySelector(s);
  W = { ws, right: q(".col-r"), cv: q(".cv"), canvas: q("canvas.main"), view: q(".viewsw"), note: q(".cv-note"),
    empty: q(".empty-c"), sun: q(".pv-sun"), phone: q(".pv-phone"), zoom: q(".zoomr"), pname: q(".pname"), sub: q(".ws-title .sub") };
}

// ---------------------------------------------------------------- the right column
function fmtBytes(n) { return n >= 1e9 ? `${(n / 1e9).toFixed(2)} GB` : `${(n / 1e6).toFixed(1)} MB`; }
function buildRight() {
  const t = T(), s = state;
  const busy = s.phase === "making", ready = s.phase === "ready";
  const fileSec = `<section><h3>${t.file}</h3>` +
    (ready ? `<p class="note">${t.made}</p>` +
      `<div class="pv-file"><b>${esc(s.iso.path.split(/[\\/]/).pop())}</b><span class="mono">${fmtBytes(s.iso.bytes)} · ${s.iso.sectors.toLocaleString()} ${t.sectors}</span></div>` +
      `<details class="pv-more"><summary>${t.details}</summary><p class="note mono">${esc(s.iso.path)}</p></details>` +
      `<div class="row2"><button class="sbtn" type="button" data-a="folder">${t.folder}</button><button class="sbtn" type="button" data-a="make">${t.again}</button></div>`
    : busy ? `<div class="pv-gen" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((s.fraction ?? 0) * 100)}"></div>` +
      `<p class="note">${esc(s.stage || t.making)}${s.fraction ? ` <span class="mono">${Math.floor(s.fraction * 100)}%</span>` : ""}</p>` +
      `<button class="sbtn wide" type="button" data-a="cancel">${t.cancel}</button>`
    : `<p class="note">${s.phase === "failed" ? `<span class="pv-err">${esc(s.error || t.failed)}</span>` : s.phase === "cancelled" ? t.cancelled : t.fileNote}</p>` +
      `<button class="sbtn wide pv-make" type="button" data-a="make" ${src ? "" : "disabled"}>${s.phase === "failed" ? t.again : t.make}</button>`) +
    (ctx.media === "cd" && !ctx.alongTrackMeasured ? `<p class="note pv-warn">${t.cd}</p>` : "") + `</section>`;
  let viewSec = "";
  if (view === "off") viewSec = `<section><h3>${t.offH}</h3><p class="note">${t.offNote}</p>` +
    `<label class="pv-ctl"><span>${t.offAt}</span><input class="rng" type="range" min="0" max="2" step="0.05" value="${twist}" data-k="twist"><output class="mono">${twist.toFixed(2)}°</output></label></section>`;
  if (view === "look") viewSec = `<section><h3>${t.lookH}</h3><p class="note">${t.lookNote}</p>` +
    (ctx.media === "cd" ? `<p class="note">${t.cdModel}</p>` :
      `<div class="pv-photo-controls">` +
      ["photoLook", "flash"].map(k => `<label class="pv-check"><span>${t[k]}</span><input type="checkbox" data-photo="${k}" ${look[k] ? "checked" : ""} ${k !== "photoLook" && !look.photoLook ? "disabled" : ""}></label>`).join("") +
      `<label class="pv-backing"><span>${t.wear}</span><select data-photo="wear" ${!look.photoLook ? "disabled" : ""}>${[0, 45, 100].map(v => `<option value="${v}" ${look.wear === v ? "selected" : ""}>${v}%</option>`).join("")}</select></label>` +
      `<label class="pv-backing"><span>${t.background}</span><select data-photo="background" ${!look.photoLook ? "disabled" : ""}><option value="0" ${!look.background ? "selected" : ""}>${t.hand}</option><option value="1" ${look.background ? "selected" : ""}>${t.table}</option></select></label></div>` +
      `<p class="note pv-rough-note" ${!look.photoLook ? "hidden" : ""}>${t.roughNote}</p>` +
      [["rotate", t.rotate, -180, 180, 1], ["tilt", t.tilt, -30, 30, 1], ["exposure", t.exposure, -3, 3, .1],
       ["cz", t.height, 150, 650, 10], ["lz", t.lightHeight, 150, 650, 10]].map(([key, label, min, max, step]) =>
        `<label class="pv-ctl"><span>${label}</span><input class="rng" type="range" min="${min}" max="${max}" step="${step}" value="${look[key]}" data-k="${key}"><output class="mono">${lookValue(key, look[key])}</output></label>`).join("") +
      `<button class="sbtn" type="button" data-a="reset-look">${t.resetLook}</button>`) + `</section>`;
  W.right.innerHTML = fileSec + viewSec;
  if (busy && s.thumb) { W.right.querySelector(".pv-gen").append(s.thumb); paintThumb(s); }
  $("next").disabled = !ready;
}

// While the burn file is made: the disc thumbnail fills cell by cell, counterclockwise from twelve
// o'clock, like the random-data disc on the calibration page, but each cell shows the design.
const RINGS = 20, SECTORS = 120, HUB_MM = 7.5, DATA_MM = 22;
function paintThumb(job) {
  const c = job.thumb, g = c.getContext("2d"), N = c.width, cx = N / 2, R = N / 2 - 3;
  const ri = R * (DATA_MM / 60), rh = R * (HUB_MM / 60), top = -Math.PI / 2, p = job.fraction ?? 0;
  g.clearRect(0, 0, N, N);
  g.lineWidth = 1.5; g.strokeStyle = css("--ink-3") || "#888";
  g.beginPath(); g.arc(cx, cx, R, 0, Math.PI * 2); g.stroke();
  g.beginPath(); g.arc(cx, cx, rh, 0, Math.PI * 2); g.stroke();
  // the data area as one quiet base, so the cells never show seams
  g.fillStyle = css("--paper-2") || "rgba(128,128,128,.2)";
  g.beginPath(); g.arc(cx, cx, R, 0, Math.PI * 2); g.arc(cx, cx, ri, 0, Math.PI * 2, true); g.fill();
  if (!src || p <= 0) return;
  // every cell written so far as one clip, then the design through it
  g.save();
  g.beginPath();
  for (let k = 0; k < RINGS; k++) {
    const a = ri + ((R - ri) * k) / RINGS, b = ri + ((R - ri) * (k + 1)) / RINGS;
    for (let s = 0; s < SECTORS && s / SECTORS < p; s++) {
      const t0 = top - (s / SECTORS) * Math.PI * 2, t1 = top - ((s + 1.15) / SECTORS) * Math.PI * 2;
      g.moveTo(cx + b * Math.cos(t0), cx + b * Math.sin(t0));
      g.arc(cx, cx, b, t0, t1, true); g.arc(cx, cx, a, t1, t0, false); g.closePath();
    }
  }
  g.clip();
  g.fillStyle = css("--face") || "#d6d1c8"; g.fillRect(cx - R, cx - R, 2 * R, 2 * R);
  g.imageSmoothingEnabled = true;
  g.drawImage(src, cx - R, cx - R, 2 * R, 2 * R);     // src spans the whole 120 mm disc
  g.restore();
}
const lookValue = (key, v) => key === "wear" ? `${v}%` : key === "exposure" ? `${v > 0 ? "+" : ""}${v.toFixed(1)} EV` : key === "cz" || key === "lz" ? `${v} mm` : `${v}°`;
const esc = (x) => String(x).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

async function make() {
  if (!src || state.phase === "making") return;
  const thumb = document.createElement("canvas");
  thumb.width = thumb.height = Math.round(240 * Math.min(2, devicePixelRatio || 1));
  thumb.setAttribute("aria-hidden", "true");
  const job = state = { phase: "making", fraction: null, stage: "", ctl: new AbortController(), thumb };
  buildRight();
  try {
    const iso = await ctx.exportIso((p) => {
      if (state !== job) return;
      const f = typeof p === "number" ? p : p?.fraction;
      job.fraction = Number.isFinite(f) ? Math.max(job.fraction ?? 0, Math.min(1, f)) : job.fraction;
      if (p?.stage) job.stage = p.stage;
      buildRight();
    }, { signal: job.ctl.signal });
    if (state !== job) return;
    if (!iso?.path || !(iso.bytes > 0) || !(iso.sectors > 0)) throw new Error(T().failed);
    state = { phase: "ready", iso };
  } catch (e) {
    if (state !== job) return;
    state = { phase: e?.name === "AbortError" ? "cancelled" : "failed", error: e?.message };
  }
  ctx.state = state;
  buildRight();
}
function cancel() {
  if (state.phase !== "making") return;
  state.ctl.abort();
  state = ctx.state = { phase: "cancelled" };
  buildRight();
}

// ---------------------------------------------------------------- the canvas
function fit() { V.s = Math.min(V.w, V.h) * 0.92 / 120; V.cx = V.w / 2; V.cy = V.h / 2; V.moved = false; draw(); }
function zoomAt(f, sx, sy) {
  const s = Math.min(Math.max(V.s * f, Math.min(V.w, V.h) * 0.2 / 120), 60), k = s / V.s;
  V.moved = true;
  V.cx = sx - (sx - V.cx) * k; V.cy = sy - (sy - V.cy) * k; V.s = s; draw();
}
function resize() {
  const r = W.cv.getBoundingClientRect();
  V.w = r.width; V.h = r.height; V.dpr = devicePixelRatio || 1;
  W.canvas.width = Math.round(V.w * V.dpr); W.canvas.height = Math.round(V.h * V.dpr);
  if (!V.moved) fit(); else draw();
}
const css = (n) => getComputedStyle(root).getPropertyValue(n).trim();
function draw() {
  if (!W || !isOn()) return;
  const t = T(), g = W.canvas.getContext("2d"), [r0, r1] = RANGE[ctx.media] ?? RANGE.dvd;
  g.setTransform(V.dpr, 0, 0, V.dpr, 0, 0);
  g.clearRect(0, 0, V.w, V.h);
  const empty = view === "read" || !src;
  W.empty.hidden = !empty;
  W.empty.querySelector("p").textContent = view === "read" ? `${t.readH}。${t.readNote}`.replace("。。", "。") : t.noProject;
  W.ws.classList.toggle("pv-looking", view === "look");
  W.sun.hidden = W.phone.hidden = view !== "look" || !src || ctx.media === "cd";
  W.zoom.hidden = empty || view === "look";
  W.note.hidden = empty;
  W.note.textContent = view === "look" ? t.lookH + " · " + (api.lang() === "zh" ? "模型预测" : "model prediction") : t.dim;
  if (empty) return;
  if (view === "look") {
    g.fillStyle = "#000"; g.fillRect(0, 0, V.w, V.h);
    if (ctx.media === "cd") { W.note.textContent = t.cdModel; return; }
    try {
      if (!simulation) simulation = new SimView(ctx.project, draw);
      simulation.request(look);
    } catch { if (simulation) simulation.status = "error"; W.note.textContent = t.simError; return; }
    const side = Math.min(V.w, V.h) * .88, squash = Math.cos(look.tilt * Math.PI / 180);
    if (simulation.canvas.width && simulation.status !== "loading") g.drawImage(simulation.canvas,
      (V.w - side) / 2, (V.h - side * squash) / 2, side, side * squash);
    const status = simulation.status;
    W.note.textContent += status === "error" ? ` · ${t.simError}` : status === "loading" ? ` · ${t.loading}` : status === "refining" ? ` · ${t.refining}` : "";
    const scale = (Math.min(V.w, V.h) / 2 - 26) / 150;
    for (const [el, x, y] of [[W.sun, look.lx, look.ly], [W.phone, look.cx, look.cy]]) {
      el.style.left = `${V.w / 2 + x * scale}px`;
      el.style.top = `${V.h / 2 - y * scale}px`;
    }
    return;
  }
  const R = V.s, cx = V.cx, cy = V.cy;
  g.save();
  g.translate(cx, cy);
  g.beginPath(); g.arc(0, 0, 60 * R, 0, Math.PI * 2); g.clip();
  g.fillStyle = css("--face") || "#d6d1c8"; g.fillRect(-60 * R, -60 * R, 120 * R, 120 * R);
  g.imageSmoothingEnabled = R * 120 < src.width;
  if (view === "off") {
    // ring by ring, turned more the further from the middle of the measured span
    const mid = (r0 + r1) / 2, half = (r1 - r0) / 2;
    for (let mm = r0 - 1; mm < r1 + 1; mm += 0.5) {
      g.save();
      g.beginPath(); g.arc(0, 0, (mm + 0.52) * R, 0, Math.PI * 2); g.arc(0, 0, mm * R, 0, Math.PI * 2, true); g.clip();
      g.rotate(twist * Math.PI / 180 * ((mm - mid) / half) ** 2 * Math.sign(mm - mid || 1));
      g.drawImage(src, -60 * R, -60 * R, 120 * R, 120 * R);
      g.restore();
    }
  } else g.drawImage(src, -60 * R, -60 * R, 120 * R, 120 * R);
  g.globalAlpha = 1;
  // outside the drawable ring, dimmed; the hole in the middle
  g.fillStyle = css("--dim");
  g.beginPath(); g.arc(0, 0, 60 * R, 0, Math.PI * 2); g.arc(0, 0, r1 * R, 0, Math.PI * 2, true); g.fill("evenodd");
  g.beginPath(); g.arc(0, 0, r0 * R, 0, Math.PI * 2); g.fill();
  g.fillStyle = css("--paper");
  g.beginPath(); g.arc(0, 0, 7.5 * R, 0, Math.PI * 2); g.fill();
  g.restore();
  g.strokeStyle = css("--rule-strong"); g.lineWidth = 1;
  g.beginPath(); g.arc(cx, cy, 60 * R, 0, Math.PI * 2); g.stroke();
  W.zoom.textContent = `${Math.round(V.s * (ctx.project?.cellMm ?? 0.02) * 100)}%`;
}

// ---------------------------------------------------------------- words, start, leave
function words() {
  const t = T();
  W.pname.textContent = t.title;
  W.sub.textContent = ctx.project?.name ?? ctx.item?.name ?? "";
  W.view.setAttribute("aria-label", t.views);
  for (const b of W.view.children) { b.textContent = t.v[b.dataset.v]; b.setAttribute("aria-pressed", String(b.dataset.v === view)); }
  W.sun.setAttribute("aria-label", t.light); W.sun.title = t.light;
  W.phone.setAttribute("aria-label", t.camera); W.phone.title = t.camera;
  W.zoom.title = `${t.fit} (0)`;
  $("next-text").textContent = t.next;
  buildRight(); draw();
}
function bind(signal) {
  const on = (el, ev, fn, o = {}) => el.addEventListener(ev, fn, { ...o, signal });
  on(W.view, "click", (e) => {
    const b = e.target.closest("[data-v]"); if (!b) return;
    view = b.dataset.v; if (view !== "look") { simulation?.stop(); simulation = null; fit(); } words();
  });
  on(W.right, "click", (e) => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "reset-look") { Object.assign(look, DEFAULT_POSE, PHOTO_DEFAULTS); buildRight(); draw(); }
    if (a === "make") make();
    if (a === "cancel") cancel();
    if (a === "folder") ctx.showInFolder ? ctx.showInFolder(state.iso.path) : toast(T().folderLater);
  });
  on(W.right, "change", (e) => {
    const k = e.target.dataset.photo;
    if (!k) return;
    look[k] = (k === "background" || k === "wear") ? Number(e.target.value) : Number(e.target.checked);
    if (k === "photoLook") {
      W.right.querySelectorAll('[data-photo="flash"], [data-photo="background"], [data-photo="wear"]').forEach(el => { el.disabled = !look.photoLook; });
      W.right.querySelector('.pv-rough-note').hidden = !look.photoLook;
    }
    draw();
  });
  on(W.right, "input", (e) => {
    const k = e.target.dataset.k, v = Number(e.target.value);
    if (k === "twist") twist = v;
    if (Object.hasOwn(look, k)) look[k] = v;
    const o = e.target.nextElementSibling; if (o) o.textContent = k === "twist" ? `${v.toFixed(2)}°` : lookValue(k, v);
    draw();
  });
  on(W.zoom, "click", fit);
  // pan and zoom like the design page; in the simulated view, drag the sun
  let drag = null;
  on(W.canvas, "pointerdown", (e) => { if (view === "look") return; W.canvas.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, cx: V.cx, cy: V.cy }; });
  on(W.canvas, "pointermove", (e) => { if (!drag) return; V.moved = true; V.cx = drag.cx + e.clientX - drag.x; V.cy = drag.cy + e.clientY - drag.y; draw(); });
  on(W.canvas, "pointerup", () => { drag = null; });
  on(W.canvas, "wheel", (e) => {
    if (view === "look") return;
    e.preventDefault();
    const r = W.canvas.getBoundingClientRect(), p = [e.clientX - r.left, e.clientY - r.top];
    const mouse = e.deltaMode === 1 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY));
    if (e.ctrlKey) zoomAt(Math.exp(-e.deltaY * 0.01), ...p);
    else if (mouse) zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, ...p);
    else { V.cx -= e.deltaX; V.cy -= e.deltaY; V.moved = true; draw(); }
  }, { passive: false });
  for (const [el, x, y] of [[W.sun, "lx", "ly"], [W.phone, "cx", "cy"]]) {
    let active = false;
    const clamp = v => Math.max(-150, Math.min(150, v));
    on(el, "pointerdown", e => { el.setPointerCapture(e.pointerId); active = true; });
    on(el, "pointermove", e => {
      if (!active) return;
      const r = W.cv.getBoundingClientRect(), k = (Math.min(V.w, V.h) / 2 - 26) / 150;
      look[x] = clamp((e.clientX - r.left - V.w / 2) / k);
      look[y] = clamp(-(e.clientY - r.top - V.h / 2) / k);
      draw();
    });
    for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) on(el, event, () => { active = false; });
    on(el, "keydown", e => {
      const d = { ArrowLeft: [-5, 0], ArrowRight: [5, 0], ArrowUp: [0, 5], ArrowDown: [0, -5] }[e.key];
      if (!d) return; e.preventDefault(); look[x] = clamp(look[x] + d[0]); look[y] = clamp(look[y] + d[1]); draw();
    });
  }
  on(window, "keydown", (e) => {
    if (!isOn() || e.target.closest?.("input, select, textarea")) return;
    if (e.key === "0") fit();       // Esc is keys.js's: the Back button, which leaves
  });
  on(document, "dp-lang", () => { if (isOn()) words(); });
  on(window, "dp-lang", () => { if (isOn()) words(); });
  on($("back"), "click", (e) => { if (!isOn()) return; e.stopImmediatePropagation(); leave(); }, { capture: true });
  on($("next"), "click", (e) => {
    if (!isOn()) return;
    e.stopImmediatePropagation();
    if (state.phase !== "ready") return;
    const iso = state.iso;
    leave(false); ctx.next?.(iso);
  }, { capture: true });
  const ro = new ResizeObserver(resize); ro.observe(W.cv); signal.addEventListener("abort", () => ro.disconnect());
  const mo = new MutationObserver(draw); mo.observe(root, { attributes: true, attributeFilter: ["data-theme"] }); signal.addEventListener("abort", () => mo.disconnect());
}
let toastEl = null, toastT = 0;
function toast(text) {
  if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); document.body.append(toastEl); }
  toastEl.textContent = text; toastEl.classList.add("on");
  clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove("on"), 2600);
}

export function start(homeApi, context = {}) {
  api = homeApi; $ = api.$;
  if (life) leave(false);
  const same = context === ctx;
  ctx = context;
  if (!W) build();
  state = same && ctx.state ? ctx.state : (ctx.state = { phase: "idle" });
  if (!same) { view = "design"; src = null; try { src = ctx.project?.render(12) ?? null; } catch { src = null; } }
  life = new AbortController();
  root.dataset.mode = "preview";
  $("back").hidden = false;
  W.ws.classList.add("on");
  bind(life.signal);
  words();
  requestAnimationFrame(resize);
  return { leave };
}
export function leave(goBack = true) {
  if (state?.phase === "making") cancel();
  life?.abort(); life = null;
  simulation?.stop(); simulation = null;
  W?.ws.classList.remove("on");
  if (isOn()) root.dataset.mode = "";
  if (api) { $("next").disabled = false; $("back").hidden = true; }
  if (goBack) ctx?.back?.();
}
