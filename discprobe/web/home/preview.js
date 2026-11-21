import { observeActivity } from "./kit/shared.js";
import { ringButton } from "./kit/ringbutton.js";
import { drawFileGuides } from "./design/disc-files.mjs";
﻿// The preview page: look at the disc as it will be written, then make the burn file. A mode of the
// home page like design.js, and laid out like it: title at the top left, the disc in the middle with
// the view switch at its top right, the burn file in the right column.
//
// start(api, ctx), where ctx is
//   { media: "dvd"|"cd", item, alongTrackMeasured?,
//     project: { name?, cellMm?, render(ppm) -> canvas of the toned design, 120 mm square, centre in the middle },
//     exportIso(onProgress, { signal }) -> Promise<{ path, sectors, bytes }>,
//     back(), next?(iso) }
// Starting again with the same ctx keeps the file already made. Nothing here touches a drive.
// The first layout and words came from a Codex draft (2026-11-10); rewritten to the design page's style.

import { DEFAULT_POSE } from "./sim/model.mjs";
import { SimView } from "./sim/view.mjs";
import { LampPreview } from "./design/editor-lamp.mjs";
import { ColourPreview } from "./design/colour-preview.mjs";
import { colourShootGuide, mountColourShootStyles } from "./design/colour-shoot-guide.mjs";
import * as sfx from "./sfx.js";

let simulation = null, makeRing = null, canvasActive = true;
let restoration = null;
// The lamp view of a work from the design page: the design page's own renderer (design/lamp-*.mjs, the A3 v3 model of
// simulate_a3) on the work's document, so both pages show the same disc. sim/ (the older A5/B9 model with a photo
// stage) stays only for a project without a document (dev-preview.html).
let lampView = null;
const lampOf = () => ctx?.project?.lamp ?? null;
// the pose the design page was looking from (its phone, height and turn), in this page's terms
function lookFromDesign() {
  const p = lampOf()?.pose?.();
  if (!p) return { ...DEFAULT_POSE };
  const r = ((p.rotate ?? 0) + 180) % 360 - 180;
  return { ...DEFAULT_POSE, rotate: Math.round(r), cx: p.camera[0], cy: p.camera[1], cz: p.camera[2], lx: p.flash[0], ly: p.flash[1], lz: p.flash[2], deltaScale: p.delta_scale ?? 1 };
}
// tilt as sim/model.mjs: camera and light turned about x into the disc's frame; the drawing is squashed by cos(tilt)
function lookPose() {
  const t = look.tilt * Math.PI / 180, ct = Math.cos(t), st = Math.sin(t), turn = (x, y, z) => [x, y * ct + z * st, -y * st + z * ct];
  const pose = { camera: turn(look.cx, look.cy, look.cz), flash: turn(look.lx, look.ly, look.lz), rotate: ((look.rotate % 360) + 360) % 360 };
  if (look.deltaScale && look.deltaScale !== 1) pose.delta_scale = look.deltaScale;
  return pose;
}
let api, $, ctx = null, W = null, life = null, state = null, src = null, view = "design";
const root = document.documentElement;
const isOn = () => root.dataset.mode === "preview";
const V = { s: 1, cx: 0, cy: 0, w: 0, h: 0, dpr: 1, moved: false };   // moved: the user zoomed or panned
const PHOTO_DEFAULTS = { photoLook: 1, flash: 1, wear: 45, background: 0 };
const look = { ...DEFAULT_POSE, ...PHOTO_DEFAULTS };
let twist = 1;                       // degrees at the outer edge in the "off by a little" view

const STR = {
  zh: {
    nextBatch: "下一步：选批次", needBatch: "请先在盘库选好批次，再生成刻录文件。",
    title: "预览", next: "下一步：刻录", views: "预览方式",
    v: { design: "设计稿", off: "几何偏一点会怎样", look: "灯下的样子" },
    say: { design: "设计稿：刻进盘的黑白图。压暗的内圈和外圈不刻图。", off: "几何偏一点会怎样：标定差一点时，图会一圈一圈拧开，离中间越远拧得越多。",
      look: "灯下的样子：模拟一盏灯照在盘上，颜色随角度变。这是模型，不是照片。" },
    checkH: "刻之前", checkDiscH: "先刻一张检查盘", checkDiscNote: "第一次用这台光驱配这批盘时：先刻一张检查盘，用手机拍 3 张以上，程序读出沿轨方向的偏差。之后再生成的刻录文件会自动修正它。已经拍过这批盘的检查盘，可以跳过。检查盘的纹理是按 RITEKF1 DVD-R 挑的，别的盘还没试过。", checkDiscGo: "生成检查盘并去刻录", checkDiscMaking: "正在生成检查盘…", nextMake: "下一步：生成并去刻录", nextCal: "下一步：先标定这批盘", making2: (p) => `正在生成${p == null ? "…" : ` ${p}%`}`,
    whyMaking: "生成中：可以先回大厅，不会中断",
    carryOn: "生成在后台继续。重新打开这件作品的预览，可以查看进度或继续去刻录。",
    checkingFile: "正在查找这件作品的刻录文件…",
    unverified: "刻录文件找不到，或缺少当前文件的自检通过记录。请重新生成。",
    eta: (s) => s >= 90 ? `约还要 ${Math.round(s / 60)} 分钟` : `约还要 ${Math.max(5, Math.round(s / 5) * 5)} 秒`,
    checkSummary: (n, warn) => warn ? `刻之前：${n} 项里 ${warn} 项要看` : `刻之前：${n} 项都好`,
    doneAway: "刻录文件生成好了：回到这件作品的预览就能去刻。", checkReady: "检查盘的刻录文件已生成。", checkBurn: "去刻检查盘", whyLevels: "灰阶要选 2 级才能刻", whyEmpty: "先放一张图",
    ck: { imported_corrected: "几何来自 DIS，含转换后的修正，未经实测。位置准不准，要看第一张盘。", imported: "几何来自 DIS，未经实测。位置准不准，要看第一张盘。", batch: "这批盘标定过了", latest: "没选批次：用这种盘最近一次的测量", saved: "没选批次：用这件作品上次用的测量", none: "还没有可用的测量：先标定这批盘",
      incompatible: "这个 DIS 预设无法在本工具生成镜像。请先标定这批盘，或返回设计页另选一批盘。",
      range: "这个 DIS 预设的半径与可刻区没有足够的重叠。请先标定这批盘，或返回设计页另选一批盘。",
      nominalRange: "图在 DIS 预设的名义范围内", nominalCut: "图超出 DIS 预设的名义范围，超出部分会被裁掉",
      of: (n, w) => `（${[n, w].filter(Boolean).join("，")}）`,
      fxBw: "颜色、彩色图案和特效只是预览实验：这次按黑白刻，这些地方刻成深色。",
      fxExp: "按实验纹理刻：颜色是模型预测，网页这条路还没有实刻验证。",
      fxCd: "CD 刻不了颜色和特效：这些地方刻成深色。",
      fxTry: "改按实验纹理刻（只限 DVD，不保证颜色）",
      fxMore: "研究盘只在 GH70N 光驱、RITEKF1 DVD-R、iPhone 17 Pro 的设计机位实刻看到过红、蓝、紫和流光、O/X、合环，那些盘不是用网页这条导出路径刻的。特效按默认机位（手机在盘上方 330 mm）挑纹理，不跟着灯下视图里改的机位走。",
      cell: (u) => `格子 ${u} µm`,
      inRange: "图都在可刻区内", outRange: "有一部分在可刻区外，会被裁掉", measured: (r) => `（这批盘实测到 ${r[0].toFixed(1)}–${r[1].toFixed(1)} mm，圈外没测过，位置不可信，所以不刻图）`, lv2: "刻成深浅两种纹理，灰度靠抖动", lv4: "灰阶是 4 级，只能预览",
      blank: (n) => `光驱里是空白盘${n ? `（${n}）` : ""}`, written: "光驱里的盘刻过了：刻录页会请你换盘", other: (n) => `光驱里是别的批次（${n}）：刻录页会请你换盘`,
      kind: "光驱里是另一种盘：刻录页会请你换盘", nodisc: "光驱里还没放盘：刻录页会等你放",
      time: (m) => `刻录约 ${m} 分钟`, timeLater: "刻录时间：生成后知道", size: (b) => `文件 ${b}` },
    file: "刻录文件", fileNote: "把设计变成可以刻录的文件。生成以后才能去刻录。",
    make: "生成刻录文件", again: "重新生成", calibrate: "先标定这批盘", cancel: "取消", making: "正在生成…", made: "刻录文件已生成", madeExp: "实验纹理的刻录文件已生成：颜色没有验证过。", geoUsed: "几何",
    cancelled: "已取消，可以重新生成。", failed: "没有生成出来。", sectors: "扇区", where: "保存位置",
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
    nextBatch: "Next: choose a batch", needBatch: "Choose a batch from the disc library before making a burn file.",
    title: "Preview", next: "Next: burn", views: "Preview mode",
    v: { design: "Design", off: "If the geometry is a little off", look: "Under a lamp" },
    say: { design: "Design: the black and white picture that is burned. The dimmed inner and outer rings are not drawn.",
      off: "If the geometry is a little off: the picture twists ring by ring, more the further from the middle.",
      look: "Under a lamp: one light on the disc; the colours change with the angle. A model, not a photo." },
    checkH: "Before burning", checkDiscH: "Burn a check disc first", checkDiscNote: "The first time with this drive and this batch: burn a check disc and take 3 or more phone photos of it; the program reads the offset along the track from them, and every burn file made afterwards corrects it. Skip this if this batch's check disc was photographed already. Its textures were chosen for RITEKF1 DVD-R; other discs are untried.", checkDiscGo: "Make the check disc and burn it", checkDiscMaking: "Making the check disc…", nextMake: "Next: make the file and burn", nextCal: "Next: calibrate this batch first", making2: (p) => `Making the file${p == null ? "…" : ` ${p}%`}`,
    whyMaking: "Making it: you can go back to the lobby, it carries on",
    carryOn: "Making the file continues in the background. Reopen this work's preview to check progress or continue to burning.",
    checkingFile: "Looking for this work's burn file…",
    unverified: "The burn file is missing or has no passing self-check for the current file. Make it again.",
    eta: (s) => s >= 90 ? `about ${Math.round(s / 60)} min left` : `about ${Math.max(5, Math.round(s / 5) * 5)} s left`,
    checkSummary: (n, warn) => warn ? `Before burning: ${warn} of ${n} need a look` : `Before burning: all ${n} fine`,
    doneAway: "The burn file is ready: open this work's preview to burn it.", checkReady: "The check disc's burn file is ready.", checkBurn: "Burn the check disc", whyLevels: "Choose 2 grey levels to burn", whyEmpty: "Add a picture first",
    ck: { imported_corrected: "Geometry from DIS, with a converted correction. It is unmeasured. Check the placement on the first disc.", imported: "Geometry from DIS. It is unmeasured. Check the placement on the first disc.", batch: "This batch is calibrated", latest: "No batch chosen: uses the latest measurement of this kind", saved: "No batch chosen: uses the measurement this work used before", none: "No usable measurement yet: calibrate this batch first",
      incompatible: "This DIS preset cannot make an image here. Calibrate this batch or choose another batch in Design.",
      range: "The DIS preset's radii overlap too little with the burnable area. Calibrate this batch or choose another batch in Design.",
      nominalRange: "The picture fits within the DIS preset's nominal range", nominalCut: "The picture extends beyond the DIS preset's nominal range and will be clipped",
      of: (n, w) => ` (${[n, w].filter(Boolean).join(", ")})`,
      fxBw: "Colours, coloured patterns and effects are a preview experiment: this burn is black and white, and those areas burn dark.",
      fxExp: "Burning the experimental textures: the colours are a model prediction; this web route hasn't been checked on a burned disc.",
      fxCd: "A CD can't burn colours or effects: those areas burn dark.",
      fxTry: "Burn the experimental textures instead (DVD only, colours not guaranteed)",
      fxMore: "Research discs showed red, blue, purple and the flowing band, O/X and ring effects only with a GH70N drive, RITEKF1 DVD-R and an iPhone 17 Pro at the design position, and they were not made through this web export. Effects pick textures for the default position (phone 330 mm above the disc), not the one moved in the lamp view.",
      cell: (u) => `${u} µm grid`,
      inRange: "The picture is inside the burnable range", outRange: "Part of it is outside the range and will be cut", measured: (r) => ` (this batch was measured from ${r[0].toFixed(1)} to ${r[1].toFixed(1)} mm; outside that the positions are a guess, so no picture goes there)`, lv2: "Burned as two textures; greys come from dithering", lv4: "4 grey levels: preview only",
      blank: (n) => `A blank disc is in the drive${n ? ` (${n})` : ""}`, written: "The disc in the drive is written: the burn page will ask for a blank", other: (n) => `Another batch is in the drive (${n}): the burn page will ask for a blank`,
      kind: "Another kind of disc is in the drive: the burn page will ask for a blank", nodisc: "No disc in the drive yet: the burn page will wait for one",
      time: (m) => `Burning takes about ${m} min`, timeLater: "Burn time: known once the file is made", size: (b) => `File ${b}` },
    file: "Burn file", fileNote: "Turn the design into a file to burn. Make it before going on to burn.",
    make: "Make the burn file", again: "Make it again", calibrate: "Calibrate this batch first", cancel: "Cancel", making: "Making…", made: "Burn file ready", madeExp: "Experimental-texture burn file ready: the colours are unverified.", geoUsed: "Geometry",
    cancelled: "Cancelled. You can make it again.", failed: "The file wasn't made.", sectors: "sectors", where: "Saved at",
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
  if(ctx.reviewSaved){
    W.right.replaceChildren();
    const p=document.createElement('p');p.textContent=api.lang()==='en'?'Saved design thumbnail · 512 pixels, not a physical photograph. Return to the burn report to record what you saw.':'本次刻录保存的设计缩略图 · 512 像素，不是实物照片。返回刻录报告，记录你看到的结果。';
    W.right.append(p);paintNext();return;
  }
  const busy = s.phase === "making", ready = s.phase === "ready";
  const c = ctx.checks?.(), row = (ok, text) => `<li data-s="${ok === true ? "good" : ok === false ? "warn" : "unknown"}">${esc(text)}</li>`;
  const minutes = ready ? Math.max(1, Math.round((s.iso.bytes / ((ctx.media === "cd" ? 176400 : 1385000) * 8) + 90) / 60)) : null;
  const rows = !c ? [] : [c.geo === "batch", c.inRange, c.levels === 2, c.disc === "blank"];
  const checkSec = !c ? "" : `<section class="pv-list"><details class="pv-fold"${busy ? "" : " open"}><summary><h3>${busy ? t.checkSummary(rows.length, rows.filter((x) => !x).length) : t.checkH}</h3></summary><ul>` +
    (ctx.batchDeferred ? row(false, t.needBatch)
      : row(c.geo === "batch" ? true : c.geo === "none" ? false : null, t.ck[c.importProblem || c.geo] + (c.geoName && c.geo !== "batch" && c.geo !== "none" ? t.ck.of(c.geoName, c.geoWhen) : ""))) +
    (c.geo === "none" ? "" : c.nominal ? row(c.inRange ? null : false, c.inRange ? t.ck.nominalRange : t.ck.nominalCut)
      : row(c.inRange, (c.inRange ? t.ck.inRange : t.ck.outRange) + (c.ring ? t.ck.measured(c.ring) : ""))) +
    row(c.levels === 2, c.levels === 2 ? t.ck.lv2 : t.ck.lv4) +
    (c.effects && c.effects !== "none" ? row(false, !c.canExperiment ? t.ck.fxCd : c.effects === "experimental" ? t.ck.fxExp : t.ck.fxBw) : "") +
    row(c.disc === "blank" ? true : c.disc === "none" ? null : false, c.disc === "blank" ? t.ck.blank(c.discName) : c.disc === "other" ? t.ck.other(c.discName) : c.disc === "none" ? t.ck.nodisc : t.ck[c.disc]) +
    `</ul>` + (c.effects && c.effects !== "none" && c.canExperiment ? `<label class="chk pv-exp"><input type="checkbox" data-a="experimental" ${c.effects === "experimental" ? "checked" : ""} ${busy ? "disabled" : ""}>${t.ck.fxTry}</label>` +
      `<details class="pv-more"><summary>${t.details}</summary><p class="note">${t.ck.fxMore}</p></details>` : "") +
    `<p class="note mono">${[ready ? `${t.ck.time(minutes)} · ${t.ck.size(fmtBytes(s.iso.bytes))}` : t.ck.timeLater, c.cellUm ? t.ck.cell(c.cellUm) : ""].filter(Boolean).join(" · ")}</p></details></section>`;
  const checkDiscSec = !ctx.batchDeferred && ctx.exportCheck && c && c.geo !== "none" && !c.nominal && !busy && s.phase !== "restoring"
    ? `<section class="pv-checkdisc"><h3>${t.checkDiscH}</h3><p class="note">${t.checkDiscNote}</p>` +
      `<button class="sbtn wide" type="button" data-a="checkdisc">${t.checkDiscGo}</button></section>` : "";
  const pct = s.fraction ? Math.floor(s.fraction * 100) : null;
  const eta = busy && s.fraction > .03 && s.t0 ? (Date.now() - s.t0) / 1000 * (1 - s.fraction) / s.fraction : null;
  const fileBody = s.phase === "idle" && !s.checkIso ? "" : (`<section class="${busy ? "pv-now" : ""}"><h3>${t.file}</h3>` +
    (ready ? `<p class="note">${s.iso.experimental ? t.madeExp : t.made}</p>` +
      `<div class="pv-file"><b>${esc(s.iso.path.split(/[\\/]/).pop())}</b><span class="mono">${fmtBytes(s.iso.bytes)} · ${s.iso.sectors.toLocaleString()} ${t.sectors}</span></div>` +
      `<details class="pv-more"><summary>${t.details}</summary><p class="note mono">${esc(s.iso.path)}</p>${s.iso.geo ? `<p class="note mono">${t.geoUsed}: ${esc(s.iso.geo)}</p>` : ""}</details>` +
      `<div class="row2"><button class="sbtn" type="button" data-a="make">${t.again}</button></div>`
    : busy ? `<div class="pv-gen" aria-hidden="true"></div>` +
      // the bar the page had before the filling disc (64f6884): percent and time left when the core reports progress
      `<div class="pv-bar live" role="progressbar" aria-valuemin="0" aria-valuemax="100" ${pct == null ? "" : `aria-valuenow="${pct}"`} aria-label="${esc(s.stage || t.making)}"><i style="--f:${s.fraction ?? 0}" class="${s.fraction ? "" : "indet"}"></i></div>` +
      `<p class="note pv-prog"><b>${esc(s.stage || t.making)}</b>${pct == null ? "" : ` <span class="mono">${pct}%</span>`}${eta == null ? "" : ` · <span>${t.eta(eta)}</span>`}</p>` +
      `<p class="note">${t.carryOn}</p>` +
      `<button class="sbtn wide" type="button" data-a="cancel">${t.cancel}</button>`
    : s.checkIso ? `<p class="note">${t.checkReady}</p><button class="sbtn wide" type="button" data-a="checkburn">${t.checkBurn}</button>`
    : `<p class="note">${s.phase === "failed" ? `<span class="pv-err">${esc(s.error || t.failed)}</span>` : s.phase === "unverified" ? t.unverified : s.phase === "restoring" ? t.checkingFile : s.phase === "cancelled" ? t.cancelled : t.fileNote}</p>` +
      // no geometry yet: the way on is calibrating, not making the file again
      (s.code === "nogeo" && ctx.calibrate ? `<button class="sbtn wide pv-make" type="button" data-a="calibrate">${t.calibrate}</button>`
        : "")) + "</section>");
  // while making, the file is the one thing that matters: it comes first, the checklist folds to a line
  const fileSec = (busy ? fileBody + checkSec : checkSec + checkDiscSec + fileBody) +
    (ctx.media === "cd" && !ctx.alongTrackMeasured ? `<section><p class="note pv-warn">${t.cd}</p></section>` : "");
  let viewSec = "";
  if (view === "off") viewSec = `<section><h3>${t.offH}</h3><p class="note">${t.offNote}</p>` +
    `<label class="pv-ctl"><span>${t.offAt}</span><input class="rng" type="range" min="0" max="2" step="0.05" value="${twist}" data-k="twist"><output class="mono">${twist.toFixed(2)}°</output></label></section>`;
  if (view === "look") viewSec = `<section><h3>${t.lookH}</h3><p class="note">${t.lookNote}</p>` +
    (ctx.media === "cd" ? `<p class="note">${t.cdModel}</p>` :
      (lampOf() ? "" : `<div class="pv-photo-controls">` +
      ["photoLook", "flash"].map(k => `<label class="pv-check"><span>${t[k]}</span><input type="checkbox" data-photo="${k}" ${look[k] ? "checked" : ""} ${k !== "photoLook" && !look.photoLook ? "disabled" : ""}></label>`).join("") +
      `<label class="pv-backing"><span>${t.wear}</span><select data-photo="wear" ${!look.photoLook ? "disabled" : ""}>${[0, 45, 100].map(v => `<option value="${v}" ${look.wear === v ? "selected" : ""}>${v}%</option>`).join("")}</select></label>` +
      `<label class="pv-backing"><span>${t.background}</span><select data-photo="background" ${!look.photoLook ? "disabled" : ""}><option value="0" ${!look.background ? "selected" : ""}>${t.hand}</option><option value="1" ${look.background ? "selected" : ""}>${t.table}</option></select></label></div>` +
      `<p class="note pv-rough-note" ${!look.photoLook ? "hidden" : ""}>${t.roughNote}</p>`) +
      [["rotate", t.rotate, -180, 180, 1], ["tilt", t.tilt, -30, 30, 1], ["exposure", t.exposure, -3, 3, .1],
       ["cz", t.height, 150, 650, 10], ["lz", t.lightHeight, 150, 650, 10]].map(([key, label, min, max, step]) =>
        `<label class="pv-ctl"><span>${label}</span><input class="rng" type="range" min="${min}" max="${max}" step="${step}" value="${look[key]}" data-k="${key}"><output class="mono">${lookValue(key, look[key])}</output></label>`).join("") +
      `<button class="sbtn" type="button" data-a="reset-look">${t.resetLook}</button>`) + `</section>`;
  if (!W || !isOn() || state !== s) return;           // a job finishing in the background: shown when the page is back
  const guideOpen = W.right.querySelector('.colour-shoot-guide')?.open;
  W.right.innerHTML = fileSec + (busy ? "" : colourShootGuide(ctx.colourGuide,api.lang(),guideOpen)) + viewSec;
  if (busy && s.thumb) { W.right.querySelector(".pv-gen").append(s.thumb); paintThumb(s); }
  paintNext();
}

// The one Next: with no file yet it makes it and goes on to burn; without a calibrated disc kind it goes to
// calibrate; it says why when it cannot go on (making, 4 grey levels, no picture).
function nextStep() {
  if (ctx.calibrating) return null;
  if(ctx.reviewSaved)return 'review';
  if (ctx.batchDeferred) return ctx.chooseBatch ? "batch" : null;
  const c = ctx.checks?.();
  if (state.phase === "ready") return "burn";
  if (!src || ["making", "restoring"].includes(state.phase) || c?.levels === 4) return null;
  if ((c?.geo === "none" || state.code === "nogeo") && ctx.calibrate) return "calibrate";
  return "make";
}
function paintNext() {                                // only from buildRight, which returns first when the page is not on
  const t = T(), step = nextStep(), s = state;
  $("next-text").textContent = ctx.calibrating ? (api.lang() === "en" ? "Preparing calibration…" : "正在准备标定…")
    : ctx.batchDeferred ? t.nextBatch : step === "burn" ? t.next : step === "calibrate" ? t.nextCal
    : s.phase === "making" ? t.making2(s.fraction == null ? null : Math.floor(s.fraction * 100)) : t.nextMake;
  if(ctx.reviewSaved)$("next-text").textContent=api.lang()==='en'?'Back to the burn report':'返回刻录报告';
  $("next").disabled = !step;
  makeRing ||= ringButton($("next"), {lang:api.lang()});
  if (s.phase === 'making') makeRing.progress(s.fraction ?? null);
  else if (s.phase === 'ready') makeRing.done();
  else makeRing.reset();
  api.nextWhy?.(ctx.batchDeferred ? t.needBatch : !src ? t.whyEmpty : s.phase === "making" ? t.whyMaking : ctx.checks?.()?.levels === 4 ? t.whyLevels : "");
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
  if (ctx.batchDeferred || !src || ["making", "restoring"].includes(state.phase)) return;
  const thumb = document.createElement("canvas");
  thumb.width = thumb.height = Math.round(240 * Math.min(2, devicePixelRatio || 1));
  thumb.setAttribute("aria-hidden", "true");
  const job = state = ctx.state = { phase: "making", fraction: null, stage: "", ctl: new AbortController(), thumb, t0: Date.now() };
  const jobCtx = ctx; remember(jobCtx, job);
  buildRight();
  try {
    const iso = await jobCtx.exportIso((p) => {
      if (job.phase !== "making") return;
      const f = typeof p === "number" ? p : p?.fraction;
      job.fraction = Number.isFinite(f) ? Math.max(job.fraction ?? 0, Math.min(1, f)) : job.fraction;
      if (p?.stage) job.stage = p.stage;
      if (p?.jobId) job.jobId = p.jobId;
      remember(jobCtx, job);                           // the work is saved while its file is made: its id now finds it too
      if (state === job) buildRight();
    }, { signal: job.ctl.signal });
    if (!iso?.path || !(iso.bytes > 0) || !(iso.sectors > 0)) throw new Error(T().failed);
    finish(jobCtx, job, { phase: "ready", iso });
    if (!isOn()) toast(T().doneAway);
  } catch (e) {
    const end = { phase: e?.name === "AbortError" ? "cancelled" : "failed", error: e?.message, code: e?.code };
    finish(jobCtx, job, end);
    if (end.phase === "failed") sfx.problem();
  }
}
// A file being made belongs to its work, not to the page: leaving the preview does not stop it, and opening the
// same work's preview again (design.js ctx.keys: the plan, then its saved work id) shows it, running or finished.
const jobs = new Map();
function remember(c, job) { for (const k of c.keys?.() ?? []) jobs.set(k, { job, ctx: c }); }
function finish(c, job, end) {
  job.phase = end.phase;                               // late progress from a finished job is ignored
  for (const [k, v] of jobs) if (v.job === job) jobs.set(k, { job: end, ctx: c });
  for (const k of c.keys?.() ?? []) jobs.set(k, { job: end, ctx: c });    // the work may have been saved meanwhile
  if (c.state === job) c.state = end;
  if (state === job) { state = end; if (ctx === c) ctx.state = end; buildRight(); }
}
function carried(c) {
  for (const k of c.keys?.() ?? []) { const v = jobs.get(k); if (v) return v.job; }
  return null;
}
async function imageStatus(query, signal) {
  const response = await fetch(`/api/image-job?${new URLSearchParams(query)}`, { signal });
  if (!response.ok) throw Error(T().checkingFile);
  return response.json();
}
async function restoreImage(work, signal) {
  let status;
  try { status = await imageStatus({ work }, signal); }
  catch { status = { phase: "failed" }; }
  if (signal.aborted) return;
  if (status.phase !== "making") {
    state = ctx.state = status;
    if (status.iso) ctx.setEffects?.(status.iso.experimental ? "experimental" : "bw");
    buildRight();
    return;
  }
  const job = state = ctx.state = {
    phase: "making", stage: T().making, fraction: status.fraction,
    t0: status.started_at * 1000, ctl: new AbortController(),
  };
  job.ctl.signal.addEventListener("abort", () => {
    fetch(`/api/jobs/${status.job}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
  }, { once: true });
  buildRight();
  void followImage(status.job, job, signal);
}
async function followImage(id, job, signal) {
  while (!signal.aborted && state === job) {
    await new Promise(resolve => setTimeout(resolve, 750));
    if (signal.aborted || state !== job) return;
    let status;
    try { status = await imageStatus({ job: id }, signal); }
    catch { continue; }
    if (signal.aborted || state !== job) return;
    if (status.phase !== "making") {
      state = ctx.state = status;
      if (status.iso) ctx.setEffects?.(status.iso.experimental ? "experimental" : "bw");
      buildRight();
      return;
    }
    job.fraction = status.fraction;
    buildRight();
  }
}
// The check disc: made like the burn file (same progress and cancel), then straight to the burn page; after the
// burn, the burn page offers the photos (design.js photograph), and they come back here.
async function makeCheck() {
  if (ctx.batchDeferred || state.phase === "making" || !ctx.exportCheck) return;
  const job = state = { phase: "making", fraction: null, stage: T().checkDiscMaking, ctl: new AbortController(), check: true, t0: Date.now() };
  const jobCtx = ctx; remember(jobCtx, job);
  buildRight();
  try {
    const iso = await jobCtx.exportCheck((p) => {
      if (job.phase !== "making") return;
      const f = typeof p === "number" ? p : p?.fraction;
      job.fraction = Number.isFinite(f) ? Math.max(job.fraction ?? 0, Math.min(1, f)) : job.fraction;
      if (state === job) buildRight();
    }, { signal: job.ctl.signal });
    // the picture's own file is still to be made, after the photos
    if (state === job && isOn()) { finish(jobCtx, job, { phase: "idle" }); leave(false); jobCtx.next?.(iso); }
    else { finish(jobCtx, job, { phase: "idle", checkIso: iso }); toast(T().checkReady); }     // made while away
  } catch (e) {
    const end = { phase: e?.name === "AbortError" ? "cancelled" : "failed", error: e?.message, code: e?.code };
    finish(jobCtx, job, end);
    if (end.phase === "failed") sfx.problem();
  }
}
function cancel() {
  if (state.phase !== "making") return;
  state.ctl.abort();
  state = ctx.state = { phase: "cancelled" };
  buildRight();
}

// ---------------------------------------------------------------- the canvas
const fitScale = () => Math.min(V.w, V.h) * 0.92 / 120;
function fit() { V.s = fitScale(); V.cx = V.w / 2; V.cy = V.h / 2; V.moved = false; draw(); }
// W8: the disc lies on the desk; at the whole-disc size or smaller nothing is to be panned, so it stays centred and
// whole (a pan or a window change at 8% left it off-centre and cut by the frame). Panning is for a closer look.
function settle() { if (V.s <= fitScale() + 1e-9) { V.cx = V.w / 2; V.cy = V.h / 2; } }
function zoomAt(f, sx, sy) {
  const s = Math.min(Math.max(V.s * f, Math.min(V.w, V.h) * 0.2 / 120), 60), k = s / V.s;
  V.moved = true;
  V.cx = sx - (sx - V.cx) * k; V.cy = sy - (sy - V.cy) * k; V.s = s; settle(); draw();
}
function resize() {
  const r = W.cv.getBoundingClientRect();
  V.w = r.width; V.h = r.height; V.dpr = devicePixelRatio || 1;
  W.canvas.width = Math.round(V.w * V.dpr); W.canvas.height = Math.round(V.h * V.dpr);
  if (!V.moved) fit(); else { settle(); draw(); }
}
const css = (n) => getComputedStyle(root).getPropertyValue(n).trim();
function draw() {
  if (!canvasActive || document.hidden || !isOn()) return;
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
    const side = Math.min(V.w, V.h) * .88, squash = Math.cos(look.tilt * Math.PI / 180), lamp = lampOf();
    let status;
    if (lamp) {
      lampView ??= lamp.colour ? new ColourPreview(draw) : new LampPreview({ onChange: draw });
      const image = lampView.view({ rev: lamp.revision(), document: lamp.document, pose: lookPose(), screen: side * V.dpr, exposure: look.exposure });
      if (image) g.drawImage(image, (V.w - side) / 2, (V.h - side * squash) / 2, side, side * squash);
      status = { waiting: "loading", refining: "refining", error: "error" }[lampView.phase] ?? "ready";
    } else {
      try {
        if (!simulation) simulation = new SimView(ctx.project, draw);
        simulation.request(look);
      } catch { if (simulation) simulation.status = "error"; W.note.textContent = t.simError; return; }
      if (simulation.canvas.width && simulation.status !== "loading") g.drawImage(simulation.canvas,
        (V.w - side) / 2, (V.h - side * squash) / 2, side, side * squash);
      status = simulation.status;
    }
    W.note.textContent += status === "error" ? ` · ${t.simError}` : status === "loading" ? ` · ${t.loading}` : status === "refining" ? ` · ${t.refining}` : "";
    g.save();g.translate(V.w/2,V.h/2);g.scale(1,squash);
    drawFileGuides(g,{cx:0,cy:0,s:side/120},ctx.project?.fileRegions?.()??[],css);g.restore();
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
  drawFileGuides(g,V,ctx.project?.fileRegions?.()??[],css);
  g.beginPath(); g.arc(cx, cy, 60 * R, 0, Math.PI * 2); g.stroke();
  W.zoom.textContent = `${Math.round(V.s * (ctx.project?.cellMm ?? 0.02) * 100)}%`;
}

// ---------------------------------------------------------------- words, start, leave
function words() {
  const t = T();
  if(ctx.reviewSaved)$("back").replaceChildren(api.lang()==='en'?'Back to the burn report':'返回刻录报告');
  W.pname.textContent = t.title;
  W.sub.textContent = ctx.project?.name ?? ctx.item?.name ?? "";
  W.view.setAttribute("aria-label", t.views);
  for (const b of W.view.children) { b.textContent = t.v[b.dataset.v]; b.setAttribute("aria-pressed", String(b.dataset.v === view)); b.disabled=!!ctx.reviewSaved && b.dataset.v==='look'; }
  W.sun.setAttribute("aria-label", t.light); W.sun.title = t.light;
  W.phone.setAttribute("aria-label", t.camera); W.phone.title = t.camera;
  W.zoom.title = `${t.fit} (0)`;
  buildRight(); draw();          // buildRight words Next (paintNext)
}
function bind(signal) {
  const unobserve = observeActivity(W.canvas, active => {
    canvasActive = active;
    if (!active) { simulation?.stop(); simulation = null; lampView?.pause(); }
    else draw();
  });
  signal.addEventListener('abort', unobserve, { once: true });
  const on = (el, ev, fn, o = {}) => el.addEventListener(ev, fn, { ...o, signal });
  on(W.view, "click", (e) => {
    const b = e.target.closest("[data-v]"); if (!b) return;
    if(ctx.reviewSaved && b.dataset.v==='look')return;
    view = b.dataset.v; if (view !== "look") { simulation?.stop(); simulation = null; lampView?.pause(); fit(); } words();
  });
  on(W.right, "click", (e) => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "reset-look") { Object.assign(look, lookFromDesign(), PHOTO_DEFAULTS); buildRight(); draw(); }
    if (a === "make") make();
    if (a === "checkdisc") makeCheck();
    if (a === "calibrate") void detour();
    if (a === "cancel") cancel();
    if (a === "checkburn" && !ctx.batchDeferred) { const iso = state.checkIso; finish(ctx, state, { phase: "idle" }); leave(false); ctx.next?.(iso); }
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
  on(W.canvas, "pointermove", (e) => { if (!drag) return; V.moved = true; V.cx = drag.cx + e.clientX - drag.x; V.cy = drag.cy + e.clientY - drag.y; settle(); draw(); });
  on(W.canvas, "pointerup", () => { drag = null; });
  on(W.canvas, "wheel", (e) => {
    if (view === "look") return;
    e.preventDefault();
    const r = W.canvas.getBoundingClientRect(), p = [e.clientX - r.left, e.clientY - r.top];
    const mouse = e.deltaMode === 1 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY));
    if (e.ctrlKey) zoomAt(Math.exp(-e.deltaY * 0.01), ...p);
    else if (mouse) zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, ...p);
    else { V.cx -= e.deltaX; V.cy -= e.deltaY; V.moved = true; settle(); draw(); }
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
    if(step === 'review'){leave(false);ctx.next?.();return;}
    if (step === "batch") { const choose = ctx.chooseBatch; leave(false); choose(); return; }
    if (step === "calibrate") { void detour(); return; }
    if (step === "make" || step === "burn") void advanceToBurn(step);
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

async function detour() {
  const active = ctx, signal = life.signal;
  if (active.calibrating) return;
  active.calibrating = true;
  paintNext();
  try { await active.calibrate(() => !signal.aborted); }
  catch (error) { toast(error.message); }
  finally {
    active.calibrating = false;
    if (ctx === active && isOn()) paintNext();
  }
}

async function advanceToBurn(step) {
  const active = ctx, signal = life.signal;
  if (step === "make") await make();
  if (signal.aborted || state.phase !== "ready") return;
  const iso = state.iso;
  leave(false); active.next?.(iso);
}

export async function continueToBurn(homeApi, context) {
  context.calibrating = false;
  context.state = { phase: "idle" };
  start(homeApi, context);
  await restoration;
  if (!isOn() || ctx !== context) return;
  const step = nextStep();
  if (step === "make" || step === "burn") return advanceToBurn(step);
}

export function start(homeApi, context = {}) {
  api = homeApi; $ = api.$;
  if (life) leave(false);
  const same = context === ctx;
  ctx = context;
  if (!W) build();
  if (context.colourGuide) mountColourShootStyles();
  const cached = (same && ctx.state) || carried(ctx);
  const work = ctx.imageWork?.();
  const lookup = work && (cached?.phase !== "making" || cached.jobId) && !cached?.checkIso;
  state = ctx.state = lookup ? { phase: "restoring" } : cached ?? { phase: "idle" };
  if (!same) {
    view = ctx.media === "dvd" && !ctx.reviewSaved ? "look" : "design"; src = null; try { src = ctx.project?.render(12) ?? null; } catch { src = null; }
    lampView?.dispose(); lampView = null; Object.assign(look, lookFromDesign());
  }
  life = new AbortController();
  root.dataset.mode = "preview";
  root.classList.toggle('saved-burn-preview',!!ctx.reviewSaved);
  $("back").hidden = false;
  W.ws.classList.add("on");
  bind(life.signal);
  words();
  restoration = lookup ? restoreImage(work, life.signal) : null;
  requestAnimationFrame(resize);
  return { leave };
}
export function leave(goBack = true) {
  root.classList.remove('saved-burn-preview');
  // a file being made carries on (it belongs to the work, see `jobs`); only the Cancel button stops it
  makeRing?.destroy(); makeRing = null;
  life?.abort(); life = null;
  simulation?.stop(); simulation = null;
  lampView?.pause();
  W?.ws.classList.remove("on");
  if (isOn()) root.dataset.mode = "";
  if (api) { $("next").disabled = false; $("back").hidden = true; }
  if (goBack) ctx?.back?.();
}
export function navigationState() { return {context: ctx, state: ctx?.state}; }
export async function resumeNavigation(homeApi, saved) {
  if (saved?.context) start(homeApi, saved.context);
  if (ctx && saved?.state && (!ctx.imageWork?.() || saved.state.checkIso)) {
    state = ctx.state = saved.state;
    words();
  }
  await restoration;
}
