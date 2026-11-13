import { ringButton } from "./kit/ringbutton.js";
﻿// The preview page: look at the disc as it will be written, then make the burn file. A mode of the
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
import * as sfx from "./sfx.js";

let simulation = null, makeRing = null;
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
    v: { design: "设计稿", off: "几何偏一点会怎样", look: "灯下的样子" },
    say: { design: "设计稿：刻进盘的黑白图。压暗的内圈和外圈不刻图。", off: "几何偏一点会怎样：标定差一点时，图会一圈一圈拧开，离中间越远拧得越多。",
      look: "灯下的样子：模拟一盏灯照在盘上，颜色随角度变。这是模型，不是照片。" },
    checkH: "刻之前", nextMake: "下一步：生成并去刻录", nextCal: "下一步：先标定这批盘", making2: (p) => `正在生成${p == null ? "…" : ` ${p}%`}`,
    whyMaking: "生成中，可以在右边取消", whyLevels: "灰阶要选 2 级才能刻", whyEmpty: "先放一张图",
    ck: { imported_corrected: "从 DIS 导入，换算成 DP 修正（未经 DP 实测）", imported: "从 DIS 导入，换算成 DP 几何（未经 DP 实测）", batch: "这批盘标定过了", latest: "没选批次：用这种盘最近一次的测量", saved: "没选批次：用这件作品上次用的测量", none: "还没有可用的测量：先标定这批盘",
      of: (n, w) => `（${[n, w].filter(Boolean).join("，")}）`,
      fxBw: "颜色、彩色图案和特效只是预览实验：这次按黑白刻，这些地方刻成深色。",
      fxExp: "按实验纹理刻：颜色是模型预测，网页这条路还没有实刻验证。",
      fxCd: "CD 刻不了颜色和特效：这些地方刻成深色。",
      fxTry: "改按实验纹理刻（只限 DVD，不保证颜色）",
      fxMore: "研究盘只在 GH70N 光驱、RITEKF1 DVD-R、iPhone 17 Pro 的设计机位实刻看到过红、蓝、紫和流光、O/X、合环，那些盘不是用网页这条导出路径刻的。特效按默认机位（手机在盘上方 330 mm）挑纹理，不跟着灯下视图里改的机位走。",
      cell: (u) => `格子 ${u} µm`,
      inRange: "图都在可刻区内", outRange: "有一部分在可刻区外，会被裁掉", lv2: "灰阶是 2 级", lv4: "灰阶是 4 级，只能预览",
      blank: (n) => `光驱里是空白盘${n ? `（${n}）` : ""}`, written: "光驱里的盘刻过了：刻录页会请你换盘", other: (n) => `光驱里是别的批次（${n}）：刻录页会请你换盘`,
      kind: "光驱里是另一种盘：刻录页会请你换盘", nodisc: "光驱里还没放盘：刻录页会等你放",
      time: (m) => `刻录约 ${m} 分钟`, timeLater: "刻录时间：生成后知道", size: (b) => `文件 ${b}` },
    file: "刻录文件", fileNote: "把设计变成可以刻录的文件。生成以后才能去刻录。",
    make: "生成刻录文件", again: "重新生成", calibrate: "先标定这批盘", cancel: "取消", making: "正在生成…", made: "刻录文件已生成", madeExp: "实验纹理的刻录文件已生成：颜色没有验证过。", geoUsed: "几何",
    cancelled: "已取消，可以重新生成。", failed: "没有生成出来。", sectors: "扇区", where: "保存位置", folder: "在文件夹里显示",
    details: "详细信息",
    cd: "这张 CD 的沿轨常数还没确认，径向线可能扭曲。回到标定页，用手机拍照读出它；读不出来时，也可以导出 DIS 预设，在 DIS 里精细标定。",
    offH: "差一点会怎样", offNote: "标定差一点时，图会一圈一圈地拧开，离中间那一圈越远拧得越多。这就是要先标定的原因。",
    offAt: "外圈偏多少", lookH: "灯下的样子", lookNote: "模型预测，不是照片。拖动太阳移动灯，拖动手机移动相机。转动或倾斜盘片，看看图案和彩虹怎样变化。",
    photoLook: "照片感", flash: "闪光灯（关闭用室内灯）", wear: "灰尘和划痕", background: "背后是什么", hand: "手心", table: "暗桌面", roughNote: "按实拍照片加了反光、划痕和手机成像的瑕疵。",
    rotate: "转动盘片", exposure: "曝光", camera: "手机", height: "相机高度", lightHeight: "灯的高度", resetLook: "恢复默认位置",
    loading: "正在准备设计…", refining: "正在细化…", simError: "模拟没有完成，请返回设计页再试。", cdModel: "此模型适用于 DVD，暂不预测 CD 的外观。",
    tilt: "盘斜多少", light: "灯",
    dim: "压暗的内圈和外圈不刻图。", fit: "适应", noProject: "这件作品还没有图。回去放一张图再来。",
  },
  en: {
    title: "Preview", next: "Next: burn", views: "Preview mode",
    v: { design: "Design", off: "If the geometry is a little off", look: "Under a lamp" },
    say: { design: "Design: the black and white picture that is burned. The dimmed inner and outer rings are not drawn.",
      off: "If the geometry is a little off: the picture twists ring by ring, more the further from the middle.",
      look: "Under a lamp: one light on the disc; the colours change with the angle. A model, not a photo." },
    checkH: "Before burning", nextMake: "Next: make the file and burn", nextCal: "Next: calibrate this batch first", making2: (p) => `Making the file${p == null ? "…" : ` ${p}%`}`,
    whyMaking: "Making it; cancel on the right", whyLevels: "Choose 2 grey levels to burn", whyEmpty: "Add a picture first",
    ck: { imported_corrected: "Imported from DIS, converted to DP correction (not measured by DP)", imported: "Imported from DIS, converted to DP geometry (not measured by DP)", batch: "This batch is calibrated", latest: "No batch chosen: uses the latest measurement of this kind", saved: "No batch chosen: uses the measurement this work used before", none: "No usable measurement yet: calibrate this batch first",
      of: (n, w) => ` (${[n, w].filter(Boolean).join(", ")})`,
      fxBw: "Colours, coloured patterns and effects are a preview experiment: this burn is black and white, and those areas burn dark.",
      fxExp: "Burning the experimental textures: the colours are a model prediction; this web route hasn't been checked on a burned disc.",
      fxCd: "A CD can't burn colours or effects: those areas burn dark.",
      fxTry: "Burn the experimental textures instead (DVD only, colours not guaranteed)",
      fxMore: "Research discs showed red, blue, purple and the flowing band, O/X and ring effects only with a GH70N drive, RITEKF1 DVD-R and an iPhone 17 Pro at the design position, and they were not made through this web export. Effects pick textures for the default position (phone 330 mm above the disc), not the one moved in the lamp view.",
      cell: (u) => `${u} µm grid`,
      inRange: "The picture is inside the burnable range", outRange: "Part of it is outside the range and will be cut", lv2: "2 grey levels", lv4: "4 grey levels: preview only",
      blank: (n) => `A blank disc is in the drive${n ? ` (${n})` : ""}`, written: "The disc in the drive is written: the burn page will ask for a blank", other: (n) => `Another batch is in the drive (${n}): the burn page will ask for a blank`,
      kind: "Another kind of disc is in the drive: the burn page will ask for a blank", nodisc: "No disc in the drive yet: the burn page will wait for one",
      time: (m) => `Burning takes about ${m} min`, timeLater: "Burn time: known once the file is made", size: (b) => `File ${b}` },
    file: "Burn file", fileNote: "Turn the design into a file to burn. Make it before going on to burn.",
    make: "Make the burn file", again: "Make it again", calibrate: "Calibrate this batch first", cancel: "Cancel", making: "Making…", made: "Burn file ready", madeExp: "Experimental-texture burn file ready: the colours are unverified.", geoUsed: "Geometry",
    cancelled: "Cancelled. You can make it again.", failed: "The file wasn't made.", sectors: "sectors", where: "Saved at", folder: "Show in folder",
    details: "Details",
    cd: "This CD’s along-track constant is not confirmed; radial lines may twist. Go back to calibration and read it from phone photos; if they cannot be read, export a DIS preset and fine-calibrate in DIS.",
    offH: "What a small error does", offNote: "When calibration is a little off, the picture twists ring by ring, more the further from the middle ring. That is why calibration comes first.",
    offAt: "Off at the outer edge", lookH: "Under a lamp", lookNote: "Model prediction, not a photo. Drag the sun to move the light and the phone to move the camera. Turn or tilt the disc to see the picture and rainbow change.",
    photoLook: "Photo look", flash: "Flash (off: room lamp)", wear: "Dust and scratches", background: "Behind the disc", hand: "Hand", table: "Dark table", roughNote: "Reflections, scratches and phone-camera imperfections added from photo references.",
    rotate: "Turn the disc", exposure: "Exposure", camera: "Phone", height: "Camera height", lightHeight: "Light height", resetLook: "Reset the view",
    loading: "Preparing the design…", refining: "Refining…", simError: "Simulation failed. Return to Design and try again.", cdModel: "This model predicts DVD appearance. CD appearance is not available yet.",
    tilt: "Disc tilt", light: "Light",
    dim: "The dimmed inner and outer rings aren't drawn.", fit: "Fit", noProject: "This work has no picture yet. Go back and add one.",
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
  const c = ctx.checks?.(), row = (ok, text) => `<li data-s="${ok === true ? "good" : ok === false ? "warn" : "unknown"}">${esc(text)}</li>`;
  const minutes = ready ? Math.max(1, Math.round((s.iso.bytes / ((ctx.media === "cd" ? 176400 : 1385000) * 8) + 90) / 60)) : null;
  const checkSec = !c ? "" : `<section class="pv-list"><h3>${t.checkH}</h3><ul>` +
    row(c.geo === "batch" ? true : c.geo === "none" ? false : null, t.ck[c.geo] + (c.geoName && c.geo !== "batch" && c.geo !== "none" ? t.ck.of(c.geoName, c.geoWhen) : "")) +
    row(c.inRange, c.inRange ? t.ck.inRange : t.ck.outRange) +
    row(c.levels === 2, c.levels === 2 ? t.ck.lv2 : t.ck.lv4) +
    (c.effects && c.effects !== "none" ? row(false, !c.canExperiment ? t.ck.fxCd : c.effects === "experimental" ? t.ck.fxExp : t.ck.fxBw) : "") +
    row(c.disc === "blank" ? true : c.disc === "none" ? null : false, c.disc === "blank" ? t.ck.blank(c.discName) : c.disc === "other" ? t.ck.other(c.discName) : c.disc === "none" ? t.ck.nodisc : t.ck[c.disc]) +
    `</ul>` + (c.effects && c.effects !== "none" && c.canExperiment ? `<label class="chk pv-exp"><input type="checkbox" data-a="experimental" ${c.effects === "experimental" ? "checked" : ""} ${busy ? "disabled" : ""}>${t.ck.fxTry}</label>` +
      `<details class="pv-more"><summary>${t.details}</summary><p class="note">${t.ck.fxMore}</p></details>` : "") +
    `<p class="note mono">${[ready ? `${t.ck.time(minutes)} · ${t.ck.size(fmtBytes(s.iso.bytes))}` : t.ck.timeLater, c.cellUm ? t.ck.cell(c.cellUm) : ""].filter(Boolean).join(" · ")}</p></section>`;
  const fileSec = checkSec + (s.phase === "idle" ? "" : `<section><h3>${t.file}</h3>` +
    (ready ? `<p class="note">${s.iso.experimental ? t.madeExp : t.made}</p>` +
      `<div class="pv-file"><b>${esc(s.iso.path.split(/[\\/]/).pop())}</b><span class="mono">${fmtBytes(s.iso.bytes)} · ${s.iso.sectors.toLocaleString()} ${t.sectors}</span></div>` +
      `<details class="pv-more"><summary>${t.details}</summary><p class="note mono">${esc(s.iso.path)}</p>${s.iso.geo ? `<p class="note mono">${t.geoUsed}: ${esc(s.iso.geo)}</p>` : ""}</details>` +
      `<div class="row2">${ctx.showInFolder ? `<button class="sbtn" type="button" data-a="folder">${t.folder}</button>` : ''}<button class="sbtn" type="button" data-a="make">${t.again}</button></div>`
    : busy ? `<div class="pv-gen" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((s.fraction ?? 0) * 100)}"></div>` +
      `<p class="note">${esc(s.stage || t.making)}${s.fraction ? ` <span class="mono">${Math.floor(s.fraction * 100)}%</span>` : ""}</p>` +
      `<button class="sbtn wide" type="button" data-a="cancel">${t.cancel}</button>`
    : `<p class="note">${s.phase === "failed" ? `<span class="pv-err">${esc(s.error || t.failed)}</span>` : s.phase === "cancelled" ? t.cancelled : t.fileNote}</p>` +
      // no geometry yet: the way on is calibrating, not making the file again
      (s.code === "nogeo" && ctx.calibrate ? `<button class="sbtn wide pv-make" type="button" data-a="calibrate">${t.calibrate}</button>`
        : "")) + "</section>") +
    (ctx.media === "cd" && !ctx.alongTrackMeasured ? `<section><p class="note pv-warn">${t.cd}</p></section>` : "");
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
  paintNext();
}

// The one Next: with no file yet it makes it and goes on to burn; without a calibrated disc kind it goes to
// calibrate; it says why when it cannot go on (making, 4 grey levels, no picture).
function nextStep() {
  const c = ctx.checks?.();
  if (state.phase === "ready") return "burn";
  if (!src || state.phase === "making" || c?.levels === 4) return null;
  if ((c?.geo === "none" || state.code === "nogeo") && ctx.calibrate) return "calibrate";
  return "make";
}
function paintNext() {
  const t = T(), step = nextStep(), s = state;
  $("next-text").textContent = step === "burn" ? t.next : step === "calibrate" ? t.nextCal
    : s.phase === "making" ? t.making2(s.fraction == null ? null : Math.floor(s.fraction * 100)) : t.nextMake;
  $("next").disabled = !step;
  makeRing ||= ringButton($("next"), {lang:api.lang()});
  if (s.phase === 'making') makeRing.progress(s.fraction ?? null);
  else if (s.phase === 'ready') makeRing.done();
  else makeRing.reset();
  api.nextWhy?.(!src ? t.whyEmpty : s.phase === "making" ? t.whyMaking : ctx.checks?.()?.levels === 4 ? t.whyLevels : "");
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
    state = { phase: e?.name === "AbortError" ? "cancelled" : "failed", error: e?.message, code: e?.code };
    if (state.phase === "failed") sfx.problem();
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
  const empty = !src;
  W.empty.hidden = !empty;
  W.empty.querySelector("p").textContent = t.noProject;
  W.ws.classList.toggle("pv-looking", view === "look");
  W.sun.hidden = W.phone.hidden = view !== "look" || !src || ctx.media === "cd";
  W.zoom.hidden = empty || view === "look";
  W.note.hidden = empty;
  W.note.textContent = t.say[view];
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
  g.fillStyle = css("--face-dim") || css("--dim");     // the disc where nothing is burned (design.css)
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
  buildRight(); draw();          // buildRight words Next (paintNext)
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
    if (a === "calibrate") { state = ctx.state = { phase: "idle" }; leave(false); ctx.calibrate(); }
    if (a === "cancel") cancel();
    if (a === "folder") ctx.showInFolder?.(state.iso.path);
  });
  on(W.right, "change", (e) => {
    if (e.target.dataset.a === "experimental") {
      if (state.phase === "making") return;
      ctx.setEffects?.(e.target.checked ? "experimental" : "bw");
      if (state.phase !== "idle") state = ctx.state = { phase: "idle" };
      buildRight(); return;
    }
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
    const step = nextStep();
    if (step === "calibrate") { state = ctx.state = { phase: "idle" }; leave(false); ctx.calibrate(); return; }
    if (step === "make") { make().then(() => { if (isOn() && state.phase === "ready") { const iso = state.iso; leave(false); ctx.next?.(iso); } }); return; }
    if (step !== "burn") return;
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
  if (!same) { view = ctx.media === "dvd" ? "look" : "design"; src = null; try { src = ctx.project?.render(12) ?? null; } catch { src = null; } }
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
  makeRing?.destroy(); makeRing = null;
  life?.abort(); life = null;
  simulation?.stop(); simulation = null;
  W?.ws.classList.remove("on");
  if (isOn()) root.dataset.mode = "";
  if (api) { $("next").disabled = false; $("back").hidden = true; }
  if (goBack) ctx?.back?.();
}
