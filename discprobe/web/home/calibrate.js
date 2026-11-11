// The calibration flow, as a mode of the home page: the scene stays at the drive, the right column
// becomes the step panel, the bar shows the job, the back button takes the top-left corner.
// Live jobs use the local API. Simulated readings and timers are limited to ?mock / ?demo=N.

import { budgetHTML, cdPhoto, measurementRecovery, recoveryKind, recoveryAction, recoveryCommands, remeasure } from "./guidance.mjs";
import { cutaway } from "./drive-scene.js";
import { floorLog } from "./floor-log.js";
const DEMO = Number(new URLSearchParams(location.search).get("demo")) || 40;   // simulated jobs run this many times faster (?demo=N)
const R0 = 22, R1 = 58.5;             // data area, mm: the radius the head sweeps while burning

const STR = {
  zh: {
    steps: ["准备测量盘", "测转速", "测几何", "拍照"],
    prepare: "准备一张测量盘",
    prepareLede: (d) => `测量要用一张刻满随机数据的 ${d}。刻一次，测量就能开始。`,
    optBurn: "刻一张测量盘", optBurnSub: "放入一张同批次的空白盘；耗盘和时间见上面的预算。",
    optHave: "用已刻好的数据盘", optHaveSub: "同批次、刻满随机数据的盘也可以，省一张盘。",
    optRw: "擦写这张可擦写盘再刻", optRwSub: "可擦写盘可以反复用来测量。",
    putBlank: (d) => `把一张空白 ${d} 放到托盘上。`, putData: "把刻好的测量盘放到托盘上。",
    placed: "我放好了", placedAgain: "我换好了", wrongDemo: "（样稿）放一张不对的盘",
    checking: "正在看托盘里的盘……",
    detect: "正在检测光驱里有没有盘……", identify: "光驱里有一张盘，正在看是不是测量盘……",
    notMeasure: ["这张不是测量盘", "里面是一张刻过别的内容的 DVD-R。把它从托盘上取出来。"],
    removed: "我拿出来了", isMeasure: "光驱里正好是同批次的测量盘，可以直接测量。",
    blankReady: (d, gb) => `空白 ${d}，${gb} GB，可以刻。`,
    dataReady: "测量盘就绪，可以直接测量。",
    wrongDisc: ["这是 CD-R，不是 DVD", "这一步要一张空白 DVD-R。换一张再点“我换好了”。"],
    generate: "正在生成测量镜像", generateLede: "随机数据，每一张都不一样；几十秒。",
    genJob: "生成镜像",
    recheck: "开刻之前，再确认一次托盘里还是那张空白盘……",
    notBlankNow: ["托盘里不是空盘了", "可能被换过。这次没有开始刻录，放一张空白盘再来。"],
    readyBurn: "镜像好了，可以刻", readyLede: "按住右下角的按钮开始刻录。刻的时候托盘会关上；耗盘和时间见下面的预算。",
    holdBurn: "下一步：刻测量盘（按住）",
    burning: "正在刻测量盘", burningLede: "托盘关着，别动光驱。刻完会自动接着测量。",
    burnJob: "刻测量盘",
    burned: "测量盘刻好了",
    startMeasure: "下一步：开始测量",
    nameH: "先认一下这张新盘", newPut: (k) => `把这种盘的一张空白 ${k} 放进光驱，先读出它的类型和厂商编号。`,
    identified: (k, mid) => [`读出来了：空白 ${k}`, `厂商编号 ${mid}。页面会复用这个编号以前的测量（如果有）；编号相同也可能几何不同。先在另一张同批空盘上刻网格，检查线是否笔直。`],
    nameLabel: "给这种盘起个名字", nameUse: "下一步：就叫这个", newDiscPrint: "新盘",
    timing: "正在测转速", timingLede: "确认这台光驱读盘时转速稳定，1 到 3 分钟。",
    timingJob: "测转速",
    rpm: "转速", jitter: "抖动", mode: "转法",
    geo: "正在测几何", geoLede: "逐圈读出盘面螺旋的位置，约 5 分钟。点会一个个长出来。",
    geoJob: "测几何", geoDone: "几何测好了",
    points: "测点", span: "覆盖", sigma: "角度不确定度",
    photo: "拍几张照片", photoLede: "第一次用这台光驱配这批盘，还差一个沿轨常数，要靠照片读出来。刻一张标靶盘，用手机拍 3 张就够。",
    photoScan: "用手机扫这个码，打开拍照页", photoGot: (n) => `已收到 ${n} / 3 张`, photoDemo: "（样稿）收到一张照片",
    photoRead: "读出来了：沿轨常数 −2.12 mm", next: "下一步",
    done: "标定好了", doneLede: "曲线是拟合的几何，色带是它的不确定范围。点太偏的话可以去掉再拟合。",
    source: "来源：自动", leftQ: "这一桶还剩", leftUnit: "张",
    save: "保存，回到首页",
    cancel: "取消", leaveNote: "离开这一页，任务也会接着跑。",
    stNoDisc: ["光驱里没有盘", "放入一张盘再继续。"],
    stBlank: ["这是空白盘", "测量要刻好的数据盘。先回到第 1 步刻一张。"],
    stBusy: ["光驱正忙", "命令行里有别的任务在用它（geo，H:）。等它结束，这里会自己接着走。"],
    stStopped: ["提前停了", "29–33 mm 那一段读得不稳。换个速度再测一次，或跳过这一段。"],
    stChanged: ["光驱中途变了", "开头和结尾的检查点对不上，之前的结果不能接着用。"],
    stNarrow: ["测到的范围偏窄", "只覆盖到 41 mm，外圈的图会偏。再测一次外圈。"],
    stUnknown: ["不知道", "两次结果差了 0.6°，比不确定度大。换个速度再测一次。"],
    stTray: ["托盘要动了", "确认手和东西不在托盘前面。"],
    remeasure: "下一步：重新测量", retry: "下一步：换速度重测", waitBusy: "等光驱空出来", trayOk: "下一步：打开托盘",
    left: (s) => `约 ${Math.max(1, Math.ceil(s / 60))} 分钟`, leftSec: (s) => `约 ${Math.ceil(s)} 秒`,
  },
  en: {
    steps: ["Measurement disc", "Speed", "Geometry", "Photos"],
    prepare: "Prepare a measurement disc",
    prepareLede: (d) => `Measuring needs a ${d} filled with random data. Burn it once and measuring can start.`,
    optBurn: "Burn a measurement disc", optBurnSub: "Put in a blank from the same batch; see the disc and time budget above.",
    optHave: "Use a data disc you already burned", optHaveSub: "A disc from the same batch filled with random data works too, and saves a blank.",
    optRw: "Erase this rewritable and burn it", optRwSub: "A rewritable can be measured again and again.",
    putBlank: (d) => `Put a blank ${d} on the tray.`, putData: "Put the burned measurement disc on the tray.",
    placed: "It's in", placedAgain: "Swapped it", wrongDemo: "(mock) Put in the wrong disc",
    checking: "Looking at the disc in the tray…",
    detect: "Checking whether there is a disc in the drive…", identify: "There is a disc in the drive. Checking whether it's a measurement disc…",
    notMeasure: ["This isn't a measurement disc", "It's a DVD-R burned with something else. Take it off the tray."],
    removed: "I took it out", isMeasure: "The drive already holds a measurement disc from this batch. Measuring can start.",
    blankReady: (d, gb) => `Blank ${d}, ${gb} GB. Ready to burn.`,
    dataReady: "Measurement disc ready. Measuring can start.",
    wrongDisc: ["This is a CD-R, not a DVD", "This step needs a blank DVD-R. Swap it and press “Swapped it”."],
    generate: "Making the measurement image", generateLede: "Random data, different every time. A few tens of seconds.",
    genJob: "Image",
    recheck: "Before burning, checking once more that the tray still holds the blank…",
    notBlankNow: ["The disc is no longer blank", "It may have been swapped. Burning didn't start; put in a blank and try again."],
    readyBurn: "The image is ready to burn", readyLede: "Hold the button at the bottom right to start. The tray closes while it burns; see the disc and time budget below.",
    holdBurn: "Next: burn the disc (hold)",
    burning: "Burning the measurement disc", burningLede: "The tray stays closed; leave the drive alone. Measuring follows on its own.",
    burnJob: "Burning",
    burned: "Measurement disc burned",
    startMeasure: "Next: start measuring",
    nameH: "First, identify the new disc", newPut: (k) => `Put a blank ${k} of this kind in the drive; its type and maker code are read first.`,
    identified: (k, mid) => [`Found a blank ${k}`, `Maker code ${mid}. The page reuses an earlier measurement for this code, if one exists. Geometry can still differ: burn a grid on another blank from this batch and check for straight lines.`],
    nameLabel: "Name this kind of disc", nameUse: "Next: use this name", newDiscPrint: "New disc",
    timing: "Measuring the speed", timingLede: "Checks the drive spins the disc steadily. 1 to 3 minutes.",
    timingJob: "Speed",
    rpm: "Speed", jitter: "Jitter", mode: "Mode",
    geo: "Measuring the geometry", geoLede: "Reads where the spiral is, turn by turn. About 5 minutes. The points appear one by one.",
    geoJob: "Geometry", geoDone: "Geometry measured",
    points: "Points", span: "Covers", sigma: "Angle uncertainty",
    photo: "Take a few photos", photoLede: "First time with this drive and this batch: one constant along the track is still missing, and only a photo can read it. Burn a target disc and take 3 photos with a phone.",
    photoScan: "Scan this with your phone to open the camera page", photoGot: (n) => `${n} of 3 photos received`, photoDemo: "(mock) A photo arrives",
    photoRead: "Read: along-track constant −2.12 mm", next: "Next",
    done: "Calibrated", doneLede: "The curve is the fitted geometry; the band is how sure it is. Points far off can be removed and the fit redone.",
    source: "Source: automatic", leftQ: "Left in this spindle", leftUnit: "",
    save: "Save and go home",
    cancel: "Cancel", leaveNote: "Leaving this page keeps the job running.",
    stNoDisc: ["No disc in the drive", "Put a disc in to go on."],
    stBlank: ["This is a blank", "Measuring needs a burned data disc. Go back to step 1 and burn one."],
    stBusy: ["The drive is busy", "Another job is using it from the command line (geo, H:). This page carries on when it ends."],
    stStopped: ["Stopped early", "The 29–33 mm band read unsteadily. Measure again at another speed, or skip that band."],
    stChanged: ["The drive changed during the run", "The check points at the start and the end disagree; the earlier result can't be reused."],
    stNarrow: ["The measured range is narrow", "It only reaches 41 mm; artwork further out will be off. Measure the outer area again."],
    stUnknown: ["Not sure", "Two runs differ by 0.6°, more than the uncertainty. Measure again at another speed."],
    stTray: ["The tray is about to move", "Keep hands and things clear of the tray."],
    remeasure: "Next: measure again", retry: "Next: try another speed", waitBusy: "Waiting for the drive", trayOk: "Next: open the tray",
    left: (s) => `about ${Math.max(1, Math.ceil(s / 60))} min`, leftSec: (s) => `about ${Math.ceil(s)} s`,
  },
};

// OKLCH -> sRGB, as ui.py does; the signature: colour follows the radius the head is at
function oklch(l, c, hDeg) {
  const h = (hDeg * Math.PI) / 180, a = c * Math.cos(h), b = c * Math.sin(h);
  const L = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3, M = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3, S = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S, -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S, -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S];
  return "#" + lin.map((v) => Math.round(Math.min(1, v <= 0 ? 0 : v < 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055) * 255).toString(16).padStart(2, "0")).join("");
}
const hueAt = (r) => 262 - Math.min(1, Math.max(0, (r - R0) / (R1 - R0))) * 237;
const rainbowAt = (r) => oklch(0.72, 0.12, hueAt(r));
const radiusAt = (p) => Math.sqrt(R0 * R0 + (R1 * R1 - R0 * R0) * p);   // constant linear velocity

// made-up but plausible measurement: 22 rungs from 24 to 58 mm, residuals within a few tenths
const RUNGS = Array.from({ length: 22 }, (_, i) => {
  const r = 24.2 + (i * (58.1 - 24.2)) / 21;
  const noise = Math.sin(i * 12.9898) * 43758.5453 % 1;
  return { r, res: 0.22 * noise - 0.03 * Math.sin(r / 6), err: 0.1 + 0.08 * Math.abs(Math.cos(i * 1.7)) };
});

let api, $, flow;
const isCal = () => document.documentElement.dataset.mode === "cal";
const wait = (ms) => new Promise((r) => setTimeout(r, api.reduce ? 0 : ms));

let ui = null;                              // the scene pieces, built once
function newFlow(item) {
  return {
    item, step: 0, choice: item.rw ? "rw" : "burn",
    // detect → (identify → ok | remove → out) | out → flying → hover → falling → checking → ok | wrong
    disc: "detect",
    // mock: what the drive holds when the flow starts (the home page's drive has a disc in it,
    // a DVD-R burned with something else); the real page reads it with `info`
    inDrive: api.tray().disc ? "foreign" : "empty",
    state: null, job: null, rungs: 0, photos: 0, left: item.left, plate: "off", plateP: 0,
    naming: item.kind === "new",            // a kind that isn't listed: read it and name it first
    ...ui,
  };
}

// returnTo: who opened this page and gets it back when it closes (the new-plan form's "calibrate
// first"), called with { done } instead of going back to the disc's place on the shelf
let returnTo = null;
function giveBack(done) {
  const r = returnTo;
  returnTo = null;
  if (!r) return false;
  r({ done });
  return true;
}
export function start(homeApi, { returnTo: back = null } = {}) {
  api = homeApi; $ = api.$;
  returnTo = back;
  const item = api.current().item;
  // a job still running belongs to its disc: come back to it; otherwise start over for this disc
  if (!flow || (flow.item !== item && !flow.job)) {
    flow = newFlow(item);
    if (!ui) build();
  }
  if (!api.backend.mock) { flow.realPhase ??= "inspect"; flow.disc = "waiting"; }
  open();
}

// A calibration the core is already running (the page was reloaded or closed meanwhile): show it and follow
// it to its end, as if it had been started here.
export function attach(homeApi, job) {
  api = homeApi; $ = api.$;
  returnTo = null;
  if (!flow?.job) {
    flow = newFlow({ kind: "new", row: job.media || "dvd", name: "", mid: "", s: "new" });
    if (!ui) build();
    flow.realPhase = "checking"; flow.detected = { media: job.media || "dvd" };
  }
  open();
  if (flow.job) return;
  (async () => {
    try { finishCalibrate(await realJob(job.action, {}, {}, job.id)); paint(); }
    catch (error) { if (error.result?.geo || error.result?.timing) { finishCalibrate(error.result); flow.error = null; paint(); } else realError(error); }
  })();
}

function T() { return STR[api.lang()]; }

// ---------------------------------------------------------------- scene pieces
// positions are scene units (the art's 1600×1000 frame) turned into % of the camera layer
const pct = (x, y) => [`${(x / api.meta.width) * 100}%`, `${(y / api.meta.height) * 100}%`];
function ledPoint() {
  const n = [...api.burnerLayer.querySelectorAll(".rig, img")].find((x) => x.getBoundingClientRect().width > 0);
  const cam = api.cam.getBoundingClientRect(), k = cam.width / api.meta.width;
  if (!n) return hoverPoint();
  const r = n.getBoundingClientRect();
  return [(r.left + (1 - 825.01 / 1600) * r.width - cam.left) / k, (r.top + (775.97 / 1062) * r.height - cam.top) / k];
}
function blink(on) {
  const [x, y] = pct(...ledPoint());
  flow.ledEl.style.left = x; flow.ledEl.style.top = y;
  flow.ledEl.classList.toggle("on", on);
}
// where the disc lies on the OPEN tray, worked out from the rig's box (which does not move with
// the tray): burner.json's disc centre, mirrored, plus the extra 60 mm the page opens the tray by
function trayPoint() {
  const rig = [...api.burnerLayer.querySelectorAll(".rig, img")].find((n) => n.getBoundingClientRect().width > 0);
  const cam = api.cam.getBoundingClientRect(), k = cam.width / api.meta.width;
  const a = api.meta.burnerAnchor;
  if (!rig) return [a.x, a.y];
  const r = rig.getBoundingClientRect();
  const extra = [-(-60 / 140) * 438.666, (-60 / 140) * -253.264];        // mirrored x
  const x = (1600 - 659.34 + extra[0]) / 1600, y = (608.19 + extra[1]) / 1062;
  return [(r.left + x * r.width - cam.left) / k, (r.top + y * r.height - cam.top) / k];
}
function hoverPoint() { const [x, y] = trayPoint(); return [x, y - 115]; }   // just above the tray
const discPx = () => 120 * api.meta.axisPx;                 // a 120 mm disc at the scene's scale

// The image being made is a parcel: a small box (150 × 150 × 70 mm) on the floor beside the drive,
// drawn in the same isometric projection, with the image's disc printed on its lid.
function makeParcel() {
  const S = 130, Hm = 62;
  const a = S * api.meta.axisPx, h = Hm * api.meta.axisPx;          // scene px
  const w = 1.732 * a, H = a + h;
  const [tx, ty] = trayPoint();
  const fx = tx - discPx() * 2.5, fy = ty + discPx() * 0.6;          // floor centre of the box, clear of the drive
  const el = document.createElement("div");
  el.className = "parcel";
  el.style.left = `${((fx - w / 2) / api.meta.width) * 100}%`;
  el.style.top = `${((fy - h - a / 2) / api.meta.height) * 100}%`;
  el.style.width = `${(w / api.meta.width) * 100}%`;
  el.style.aspectRatio = `${w} / ${H}`;
  const X = (v) => (v / w) * 100, Y = (v) => (v / H) * 100;           // to the viewBox (0..100)
  const cx = w / 2, top = a / 2;                                       // lid centre in box px
  const P = (pts) => pts.map(([x, y]) => `${X(cx + x).toFixed(2)},${Y(top + y).toFixed(2)}`).join(" ");
  const k = 0.866 * a, half = a / 2;
  // tape along the lid, a strip of the square's width a/6
  const t = a / 12, sq = (u, v) => [0.866 * (u - v), 0.5 * (u + v)];
  const tape = [sq(-half, -t), sq(half, -t), sq(half, t), sq(-half, t)];
  el.innerHTML = `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">` +
    `<polygon class="side-l" points="${P([[-k, 0], [0, half], [0, half + h], [-k, h]])}"/>` +
    `<polygon class="side-r" points="${P([[0, half], [k, 0], [k, h], [0, half + h]])}"/>` +
    `<polygon class="lid" points="${P([[0, -half], [k, 0], [0, half], [-k, 0]])}"/>` +
    `<polygon class="tape" points="${P(tape)}"/>` +
    `<polyline class="tape-edge" points="${P([tape[3], [tape[3][0], tape[3][1] + h]])}"/>` +
    `</svg><div class="lid-print floor"><canvas width="512" height="512"></canvas></div>`;
  const lid = el.querySelector(".lid-print");
  lid.style.width = `${(a / w) * 100}%`;
  lid.style.left = `${((cx - a / 2) / w) * 100}%`;
  lid.style.top = `${((top - a / 2) / H) * 100}%`;
  return el;
}

function build() {
  const [hx, hy] = pct(...hoverPoint());
  const size = `${(discPx() / api.meta.width) * 100}%`;
  // the plate: a disc-shaped canvas lying over the drive (image being made, burn ring, rainbow rim)
  const plate = document.createElement("div");
  plate.className = "cal-plate";
  plate.style.left = hx; plate.style.top = hy; plate.style.width = size;
  plate.innerHTML = `<div class="floor"><canvas width="512" height="512"></canvas></div>`;
  // the flying disc, printed with its model, and the arrow that says where it goes
  const flyer = document.createElement("div");
  flyer.className = "flyer";
  flyer.style.width = size;
  // the model printed round the disc, following its edge
  flyer.innerHTML = `<div class="floor"><div class="face"><svg class="print" viewBox="0 0 100 100" aria-hidden="true">` +
    `<defs><path id="fly-arc" d="M50,50 m-35.5,0 a35.5,35.5 0 1,1 71,0 a35.5,35.5 0 1,1 -71,0"/></defs>` +
    `<text><textPath href="#fly-arc" startOffset="25%" text-anchor="middle"></textPath></text></svg></div></div>` +
    `<svg class="arrow" viewBox="0 0 24 40" aria-hidden="true"><path d="M12 2v32M4 26l8 9 8-9"/></svg>`;
  // the warning sign: an exclamation mark standing upright over the drive, parallel to its front
  const warn = document.createElement("div");
  warn.className = "warn-sign";
  // on the floor in front of the drive, lying flat like the gallery word
  const [tx, ty] = trayPoint();
  const [wx, wy] = pct(tx - discPx() * 0.55, ty + discPx() * 0.95);
  warn.style.left = wx; warn.style.top = wy;
  warn.innerHTML = `<div class="flat"><span>!</span></div>`;
  // the drive's activity light, blinking while it looks at the disc (hidden behind an open tray)
  const led = document.createElement("div");
  led.className = "drive-led";
  const parcel = makeParcel();
  api.cam.append(parcel, plate, flyer, warn, led);
  ui = { plateEl: plate, canvas: plate.querySelector("canvas"), flyerEl: flyer, warnEl: warn, ledEl: led,
    parcelEl: parcel, parcelCanvas: parcel.querySelector("canvas") };
  Object.assign(flow, ui);
  noise();

  $("back").addEventListener("click", back);
  $("job-cancel").addEventListener("click", cancelJob);
  addEventListener("dp-lang", () => { if (isCal()) paint(); });
  // Esc is keys.js's (the Back button); in the mock, Shift+S steps through the states
  addEventListener("keydown", (e) => {
    if (isCal() && api.backend.mock && e.key === "S" && e.shiftKey) cycleState();
  });
  holdButton($("next"));
}

function open() {
  document.documentElement.dataset.mode = "cal";
  $("cal").hidden = false;
  $("back").hidden = false;
  api.focusDrive();
  paint();
  // coming back while it burns: the drive is open again, the plate as it was
  if (flow.job?.kind === "burn") setTimeout(() => showInterior(true), 750);
  else if (flow.plate !== "off") setPlate(flow.plate);
}

function release() {
  document.documentElement.dataset.mode = "";
  $("cal").hidden = true;
  $("back").hidden = true;
  const nb = $("next");
  nb.disabled = false; nb.classList.remove("hold"); nb.dataset.hold = ""; nb.style.removeProperty("--hold");
  for (const el of [ui.flyerEl, ui.plateEl, ui.warnEl, ui.ledEl, ui.parcelEl]) el.classList.remove("on", "hover", "drop", "breathe", "up", "ship");
  showInterior(false);
  flog.hide();
}

function leave() {
  release();
  // a disc that was in the air goes back to waiting; detection starts over next time
  if (!flow.job && ["detecting", "identify", "flying", "hover", "falling", "checking"].includes(flow.disc)) flow.disc = "detect";
  if (!flow.job && flow.disc === "remove") flow.disc = "detect";
  if (giveBack(flow.realPhase === "saved")) return;
  api.goTo(...api.locate(flow.item));     // back to where the disc stands on the shelf
}

function back() {
  if (!api.backend.mock) { if (flow.photoLink?.dispose) flow.photoLink.dispose(); leave(); return; }
  if (!isCal()) return;
  if (flow.job) { leave(); return; }               // the job keeps running in the bar
  if (flow.state) { flow.state = null; paint(); return; }
  if (flow.step === 0) { leave(); return; }
  flow.step = Math.max(0, Math.ceil(flow.step) - 1);
  paint();
}

// ---------------------------------------------------------------- what is in the drive
const stale = (f) => flow !== f || !isCal();
async function detect() {
  const f = flow;
  f.disc = "detecting";
  api.setTray(false, api.tray().disc);
  await wait(250);
  if (stale(f)) return;
  blink(true);
  paint();
  await wait(1300);                          // the real page asks the drive: is a disc loaded?
  if (stale(f)) return;
  if (!api.tray().disc) { blink(false); f.disc = "out"; paint(); return; }
  f.disc = "identify";
  paint();
  await wait(1300);                          // info: blank or written, what MID, does it hold random data?
  if (stale(f)) return;
  blink(false);
  // the measurement disc for this batch can be used as it is; anything else has to come out
  if (f.inDrive === "measure" && f.choice === "have") { f.measureInDrive = true; f.disc = "ok"; paint(); return; }
  f.disc = "remove";
  paint();
  await liftOut();
}

async function liftOut() {
  // the tray opens with the disc; the disc rises above it with an arrow pointing up
  const fl = flow;
  api.setTray(true, true);
  await wait(1000);
  if (stale(fl)) return;
  const f = flow.flyerEl;
  f.querySelector(".print textPath").textContent = "DVD-R · 4.7 GB";
  const [tx, ty] = pct(...trayPoint());
  f.style.transition = "none";
  f.style.left = tx; f.style.top = ty;
  f.classList.add("on", "up");
  api.placeDisc(false);
  void f.offsetWidth;
  f.style.transition = "";
  const [hx, hy] = pct(...hoverPoint());
  f.style.left = hx; f.style.top = hy;
  await wait(1400);
  if (stale(fl)) return;
  f.classList.add("hover");
}

async function takenOut() {
  const f = flow.flyerEl;
  f.classList.remove("hover");
  f.style.top = "-30%";                      // gone, up and away
  const fl = flow;
  await wait(1300);
  f.classList.remove("on", "up");
  if (stale(fl)) return;
  fl.inDrive = "empty";
  fl.disc = "out";
  paint();
}

// ---------------------------------------------------------------- the disc going in
async function flyIn() {
  const f = flow.flyerEl;
  f.querySelector(".print textPath").textContent = flow.item.name || T().newDiscPrint;
  f.classList.remove("up");
  const [x, y] = pct(...hoverPoint());
  f.style.transition = "none";
  f.style.left = x; f.style.top = "-30%";
  f.classList.add("on");
  void f.offsetWidth;
  f.style.transition = "";
  f.style.top = y;
  await wait(1400);
  if (flow.disc !== "flying") return;
  flow.disc = "hover";
  f.classList.add("hover");                 // now it breathes, and the arrow points down
}

async function dropIn(wrong = false) {
  const f = flow.flyerEl;
  f.classList.remove("hover");
  const [x, y] = pct(...trayPoint());
  f.classList.add("drop");
  f.style.left = x; f.style.top = y;
  flow.disc = "falling";
  paint();
  await wait(950);
  f.classList.remove("on", "drop");
  api.placeDisc(true);                      // the disc now lies in the tray picture
  flow.disc = "checking";
  api.setTray(false, true);                 // the drive pulls it in, then reads it
  paint();
  await wait(900);
  blink(true);
  await wait(1300);                         // the real page asks the drive (info: blank? what MID?)
  blink(false);
  flow.disc = wrong ? "wrong" : "ok";
  paint();
}

// ---------------------------------------------------------------- jobs
function runJob(kind, seconds, onTick, onDone) {
  const t = T();
  const job = { kind, seconds, started: performance.now(), p: 0 };
  flow.job = job;
  $("job").hidden = false;
  $("job-name").textContent = { gen: t.genJob, burn: t.burnJob, timing: t.timingJob, geo: t.geoJob }[kind];
  $("job-cancel").setAttribute("aria-label", `${t.cancel} ${$("job-name").textContent}`);
  const disc = kind === "burn" || kind === "geo";
  const demo = DEMO_LOG[kind] ?? [];
  let printed = 0;
  if (demo.length) { placeLog(); flog.start(commandLine(kind, api.selectedDrive?.() || "H:")); }
  const tick = () => {
    if (flow.job !== job) return;
    job.p = Math.min(1, ((performance.now() - job.started) / 1000) * DEMO / seconds);
    const r = radiusAt(job.p);
    api.jobProgress(job.p, flow.item?.row || "dvd");
    const leftS = seconds * (1 - job.p);
    $("job-time").textContent = leftS > 90 ? T().left(leftS) : T().leftSec(leftS);
    flow.plateP = job.p;
    if (kind === "burn") updateInterior(job.p, leftS);
    else drawPlate();
    if (demo.length) {
      while (printed < Math.min(demo.length, Math.floor(job.p * (demo.length + 1)))) flog.log(demo[printed++]);
      flog.progress(job.p, kind === "geo" ? `rung ${Math.min(22, Math.floor(job.p * 22) + 1)}/22` : "rotation test", leftS);
    }
    onTick?.(job.p);
    if (job.p >= 1) { endJob(); onDone?.(); }
  };
  // driven by a timer, not animation frames: a job is real time, and a hidden page gets no frames
  job.timer = setInterval(tick, 100);
  tick();
}

function endJob() {
  if (!flow.job) return;
  clearInterval(flow.job.timer);
  flow.job = null;
  $("job").hidden = true;
  flog.end();
}

function cancelJob() {
  if (!api.backend.mock) { if (flow.job?.id) api.backend.cancel(flow.job.id).catch(realError); return; }
  const kind = flow.job?.kind;
  endJob();
  showInterior(false);
  if (kind === "burn" || kind === "gen") { flow.step = 0; flow.disc = "ok"; setPlate("off"); }
  flow.state = "stopped";
  paint();
}

// ---------------------------------------------------------------- the inside of the drive
// While it burns, the drive opens up into a big cutaway that fills the left half of the window.
// The layers were rendered from the drive's camera on the drive's canvas, so the cutaway starts
// exactly on the drive picture and grows from there (transform only). The pickup moves with the
// head's radius, so the pickup IS the progress bar; the percentage lies on the disc and the time
// left on the tray floor, both flat like the floor.
let cut = null;                               // the cutaway (drive-scene.js), made on first use
const cutOf = () => cut ??= cutaway(api, { mirrored: true, textLeft: () => $("cal").getBoundingClientRect().left || innerWidth * 0.56 });
function showInterior(on) {
  if (!on && !cut) return undefined;
  return Promise.resolve(cutOf().show(on)).then(placeLog);
}

// the job's terminal output on the floor beside the drive: in the cutaway while it is open
const flog = floorLog();
function placeLog() {
  flog.mount(cut?.on ? cut.box : api.burnerLayer.querySelector(".burner-frame"));
}
// what the same job looks like typed at a terminal, as the log's first line
function commandLine(action, drive) {
  return `$ python -m discprobe ${action}${drive ? ` --drive ${drive}` : ""}`;
}
// the mock jobs print what a real run on this drive printed
const DEMO_LOG = {
  timing: ["Disc: DVD-R, last LBA 2295103, reading with read12",
    "Cache: plain p50 1122.8 us, fua p50 30392.3 us -> strategy fua",
    "Spindle steady: T = 10.151 ms (5910.7 rpm)",
    "Zone 0.05 (LBA 114752): T = 10.14983 ms (5911.43 rpm), jitter 26.41 us = 0.937 deg",
    "Zone 0.50 (LBA 1147536): T = 10.15063 ms (5910.97 rpm), jitter 60.95 us = 2.162 deg",
    "Zone 0.95 (LBA 2180336): T = 10.15084 ms (5910.84 rpm), jitter 89.88 us = 3.188 deg",
    "Rotation: CAV",
    "Target 0.15 (LBA 344256): phase 246.841 deg +/- 0.459 (n=37)",
    "Target 0.55 (LBA 1262304): phase 125.773 deg +/- 0.303 (n=39)",
    "Target 0.95 (LBA 2180336): phase 341.035 deg +/- 0.855 (n=40)"],
  geo: ["Checking which parts of the disc hold random data...",
    "Reference LBA 1009840; readable ranges [(68848, 1950832)]",
    "Spindle settled: T = 21.1858 ms (2832.1 rpm), jitter 67.5 us",
    "Check points read: 27.0 mm, 35.1 mm, 53.6 mm (read again at the end)",
    "  rung  1: LBA  1009920 (+1.5 turns) phase  195.032 +/- 0.200 deg",
    "  rung  2: LBA  1010048 (+4.0 turns) phase    2.727 +/- 0.200 deg",
    "  rung  3: LBA  1016496 predicted +/-  14.39 deg, whole turns     128, residual  +0.001 deg, chi2/dof 0.27",
    "  rung  4: LBA  1036544 predicted +/-   5.50 deg, whole turns     512, residual  -0.000 deg, chi2/dof 0.27",
    "  rung  5: LBA  1130464 predicted +/-  18.38 deg, whole turns    2279, residual  +0.003 deg, chi2/dof 0.81",
    "  rung  6: LBA  1661280 predicted +/-  22.58 deg, whole turns   11413, residual  -0.000 deg, chi2/dof 0.54",
    "  rung  7: LBA    68848 predicted +/-  14.57 deg, whole turns  -22599, residual  -0.005 deg, chi2/dof 1.19",
    "  rung  8: LBA  1950816 predicted +/-   0.33 deg, whole turns   15915, residual  -0.088 deg, chi2/dof 1.08",
    "  rung  9: LBA   117088 predicted +/-   0.18 deg, whole turns  -21094, residual  +0.161 deg, chi2/dof 1.09",
    "  rung 10: LBA   551392 predicted +/-   0.13 deg, whole turns   -9648, residual  +0.100 deg, chi2/dof 0.99",
    "  rung 11: LBA  1902560 predicted +/-   0.15 deg, whole turns   15184, residual  +0.082 deg, chi2/dof 0.89",
    "  rung 12: LBA   165344 predicted +/-   0.11 deg, whole turns  -19650, residual  +0.163 deg, chi2/dof 0.89",
    "Reading the check points again, to see that the drive stayed in one state...",
    "  27.1 mm: moved -0.091 deg (+/- 0.096)",
    "  35.2 mm: moved -0.157 deg (+/- 0.063)",
    "  53.8 mm: moved +0.009 deg (+/- 0.069)"],
};
function updateInterior(p, leftS) { cut?.update(p, leftS); }

// ---------------------------------------------------------------- the plate over the drive
let NOISE;
function noise() {
  // a fixed mosaic: 20 rings × 120 sectors of random greys, drawn as the image fills
  NOISE = Array.from({ length: 20 * 120 }, (_, i) => (Math.sin(i * 78.233) * 43758.5453) % 1);
}
function setPlate(mode) {
  const was = flow.plate;
  flow.plate = mode;
  flow.parcelEl.classList.toggle("on", mode === "gen");
  if (was === "gen" && mode === "burn") {
    // the parcel goes into the drive, then the disc over the drive takes over
    flow.parcelEl.classList.add("ship");
    setTimeout(() => flow?.parcelEl.classList.remove("ship"), 900);
  }
  flow.plateEl.classList.toggle("on", mode !== "off" && mode !== "gen" && mode !== "burn");
  flow.plateEl.classList.toggle("breathe", mode === "burn");
  drawPlate();
}
function drawPlate() {
  const c = flow.plate === "gen" ? flow.parcelCanvas : flow.canvas;
  const g = c.getContext("2d"), W = c.width, cx = W / 2, R = W / 2 - (flow.plate === "gen" ? 40 : 4);   // the lid leaves a margin
  const ri = R * (R0 / 60), rh = R * (7.5 / 60), dark = document.documentElement.dataset.theme === "dark";
  const ink = flow.plate === "gen" ? (dark ? "rgba(236,235,228,.7)" : "rgba(60,45,25,.75)") : dark ? "rgba(236,235,228,.85)" : "rgba(29,27,24,.85)";
  g.clearRect(0, 0, W, W);
  if (flow.plate === "off") return;
  // the disc outline and hub
  g.lineWidth = 2; g.strokeStyle = ink;
  g.beginPath(); g.arc(cx, cx, R, 0, Math.PI * 2); g.stroke();
  g.beginPath(); g.arc(cx, cx, rh, 0, Math.PI * 2); g.stroke();
  const p = flow.plate === "gen" ? flow.plateP : 1;
  // the data area as one quiet base first, so the cells never show seams between them
  g.fillStyle = dark ? "rgba(70,78,76,.35)" : "rgba(160,152,140,.25)";
  g.beginPath(); g.arc(cx, cx, R, 0, Math.PI * 2); g.arc(cx, cx, ri, 0, Math.PI * 2, true); g.fill();
  // the random data, filling counterclockwise from twelve o'clock
  const rings = 20, sectors = 120, top = -Math.PI / 2;
  for (let k = 0; k < rings; k++) {
    const a = ri + ((R - ri) * k) / rings, b = ri + ((R - ri) * (k + 1)) / rings;
    for (let s = 0; s < sectors; s++) {
      if (s / sectors >= p) break;
      const t0 = top - (s / sectors) * Math.PI * 2, t1 = top - ((s + 1.15) / sectors) * Math.PI * 2;
      const v = Math.abs(NOISE[k * sectors + s]);
      const l = dark ? 55 + v * 110 : 110 + v * 120;
      g.fillStyle = `rgba(${l},${l},${l},${flow.plate === "gen" ? 0.9 : 0.55})`;
      g.beginPath(); g.arc(cx, cx, b, t0, t1, true); g.arc(cx, cx, a, t1, t0, false); g.closePath(); g.fill();
    }
  }
  if (flow.plate === "burn" || flow.plate === "geo") {
    // progress round the rim, each angle coloured by the radius it stands for
    const steps = 120, q = flow.plateP;
    for (let i = 0; i < steps * q; i++) {
      g.strokeStyle = rainbowAt(radiusAt(i / steps));
      g.lineWidth = 14;
      g.beginPath(); g.arc(cx, cx, R - 9, top + (i / steps) * Math.PI * 2, top + ((i + 1.2) / steps) * Math.PI * 2); g.stroke();
    }
  }
  if (flow.plate === "done") {
    // burned: the outer band catches the light like a real disc, the whole spectrum round the rim
    for (let i = 0; i < 180; i++) {
      g.strokeStyle = oklch(0.74, 0.13, (i / 180) * 360);
      g.lineWidth = 16;
      g.beginPath(); g.arc(cx, cx, R - 10, top + (i / 180) * Math.PI * 2, top + ((i + 1.3) / 180) * Math.PI * 2); g.stroke();
    }
  }
}

// ---------------------------------------------------------------- the steps
function next() {
  if (!api.backend.mock) { realNext(); return; }
  const st = flow.state;
  if (st === "stopped" || st === "changed" || st === "unknown" || st === "narrow") { flow.state = null; flow.step = 1; startTiming(); return; }
  if (st === "tray") { flow.state = null; api.setTray(true, false); paint(); return; }
  if (st) return;
  switch (flow.step) {
    case 0:
      if (flow.disc !== "ok") return;
      if (flow.naming) {                      // the new kind gets its name; then the usual first step
        const v = document.getElementById("newname")?.value.trim();
        Object.assign(flow.item, { name: v || flow.item.name || "?", mid: flow.newMid, s: "none" });
        flow.naming = false;
        paint();
        return;
      }
      if (flow.choice === "have") { flow.step = 1; startTiming(); return; }
      flow.step = 0.3; setPlate("gen");
      runJob("gen", 40, null, () => { flow.step = 0.4; paint(); });
      paint();
      return;
    case 0.4:                                 // held: one more look at the disc, then burn
      recheckThenBurn();
      return;
    case 0.9: flow.step = 1; startTiming(); return;
    case 2.9: flow.step = 3; setPlate("off"); paint(); return;
    case 3:
      if (flow.photos >= 3) { flow.step = 4; paint(); }
      return;
    case 4: save(); return;
  }
}

// Burning can't be undone, so the disc is checked once more right before it starts: still there,
// still blank, still the type the image was made for. (Mock: ?notblank=1 makes this check fail.)
async function recheckThenBurn() {
  const f = flow;
  api.setTray(false, true);
  f.step = 0.45;
  paint();
  blink(true);
  await wait(1300);
  blink(false);
  if (stale(f)) return;
  if (new URLSearchParams(location.search).has("notblank")) {
    f.step = 0; f.disc = "notblank"; f.inDrive = "foreign";
    paint();
    return;
  }
  f.step = 0.5;
  setPlate("burn");
  showInterior(true);
  runJob("burn", 14 * 60, null, () => {
    showInterior(false);
    flow.step = 0.9; setPlate("done"); paint();
  });
  paint();
}

function startTiming() {
  api.setTray(false, true);
  setPlate("off");
  runJob("timing", 100, null, () => { flow.step = 2; flow.rungs = 0; startGeo(); });
  paint();
}

function startGeo() {
  setPlate("geo");
  runJob("geo", 300, (p) => {
    const n = Math.floor(p * RUNGS.length);
    if (n !== flow.rungs) { flow.rungs = n; paint(); }
  }, () => { flow.rungs = RUNGS.length; flow.step = 2.9; paint(); });
  paint();
}

function save() {
  const it = flow.item;
  it.s = "good";
  it.last = new Date().toISOString().slice(0, 10);
  it.drive = "GH70N";
  const v = Number($("left-input")?.value);
  if (Number.isFinite(v) && v >= 0) it.left = Math.min(it.of, Math.round(v));
  flow = null;
  release();
  if (giveBack(true)) return;
  api.goTo(...api.locate(it));
}

// review helper: walk through every state the page must draw
const STATES = [null, "noDisc", "blank", "busy", "tray", "stopped", "changed", "narrow", "unknown"];
function cycleState() {
  flow.state = STATES[(STATES.indexOf(flow.state) + 1) % STATES.length];
  paint();
}

// ---------------------------------------------------------------- drawing
const ICON = { good: "i-good", warn: "i-warn", error: "i-error", unknown: "i-none", info: "i-drive" };
function note(kind, [title, why]) {
  return `<div class="note" data-s="${kind}"><svg class="icon"><use href="#${ICON[kind] || "i-none"}"/></svg><p>${title}${why ? `<small>${why}</small>` : ""}</p></div>`;
}

function chart(n, done) {
  const W = 560, H = 230, L = 46, B = 30, x0 = 22, x1 = 60, y0 = -0.6, y1 = 0.6;
  const X = (r) => L + ((r - x0) / (x1 - x0)) * (W - L - 8), Y = (v) => 8 + ((y1 - v) / (y1 - y0)) * (H - B - 8);
  let g = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${T().points}">`;
  for (const v of [-0.5, 0, 0.5]) g += `<line class="grid" x1="${L}" x2="${W - 8}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 8}" y="${Y(v) + 4}" text-anchor="end">${v > 0 ? "+" : ""}${v}°</text>`;
  for (const r of [25, 35, 45, 55]) g += `<text x="${X(r)}" y="${H - 8}" text-anchor="middle">${r} mm</text>`;
  if (done) {
    const top = RUNGS.map((p) => `${X(p.r)},${Y(0.16 + 0.04 * Math.abs(p.r - 40) / 18)}`);
    const bot = RUNGS.map((p) => `${X(p.r)},${Y(-0.16 - 0.04 * Math.abs(p.r - 40) / 18)}`).reverse();
    g += `<polygon class="band" points="${[...top, ...bot].join(" ")}"/>`;
    g += `<polyline class="fit" points="${RUNGS.map((p) => `${X(p.r)},${Y(-0.03 * Math.sin(p.r / 6))}`).join(" ")}"/>`;
  }
  RUNGS.slice(0, n).forEach((p, i) => {
    g += `<line class="bar" x1="${X(p.r)}" x2="${X(p.r)}" y1="${Y(p.res - p.err)}" y2="${Y(p.res + p.err)}"/>`;
    g += `<circle class="pt${i === n - 1 && !done ? " new" : ""}" cx="${X(p.r)}" cy="${Y(p.res)}" r="4"/>`;
  });
  return g + `</svg>`;
}

const PROBLEM = { noDisc: 1, blank: 1, stopped: 1, changed: 1, narrow: 1, unknown: 1, tray: 1 };

function paint() {
  if (api && !api.backend.mock) { realPaint(); return; }
  if (!flow || !isCal()) return;
  const t = T(), it = flow.item, kind = it.row ? it.row.toUpperCase() : it.name.match(/BD|CD|DVD/)?.[0] ?? "DVD";
  const discWord = flow.naming ? `${kind}-R` : it.name.replace(/\s+\d+x$/, "");
  const stepIx = flow.step < 1 ? 0 : flow.step < 2 ? 1 : flow.step < 3 ? 2 : 3;
  const steps = `<ol class="steps">${t.steps.map((s, i) => `<li${i === stepIx ? ' aria-current="step"' : i < stepIx ? ' class="done"' : ""}>${s}</li>`).join("")}</ol>`;
  let h = "", lede = "", body = "", nextText = t.next, nextOn = true, hold = false;
  let warn = !!PROBLEM[flow.state];

  if (flow.state) {
    const map = {
      noDisc: ["info", t.stNoDisc, t.next, false], blank: ["warn", t.stBlank, t.next, false],
      busy: ["unknown", t.stBusy, t.waitBusy, false], tray: ["warn", t.stTray, t.trayOk, true],
      stopped: ["warn", t.stStopped, t.retry, true], changed: ["error", t.stChanged, t.remeasure, true],
      narrow: ["warn", t.stNarrow, t.remeasure, true], unknown: ["unknown", t.stUnknown, t.retry, true],
    }[flow.state];
    h = map[1][0];                                   // the problem itself is the title
    body = note(map[0], [map[1][1], ""]);
    nextText = map[2]; nextOn = map[3];
  } else if (flow.step === 0 && flow.naming) {
    h = t.nameH; lede = t.newPut(discWord);
    if (flow.disc === "detect" || flow.disc === "detecting" || flow.disc === "identify") {
      body = note("info", [flow.disc === "identify" ? t.identify : t.detect, ""]); nextOn = false;
    } else if (flow.disc === "remove") {
      body = note("warn", t.notMeasure) + `<div class="row"><button class="placed" id="removed" type="button">${t.removed}</button></div>`;
      nextOn = false; warn = true;
    } else if (flow.disc === "out" || flow.disc === "flying" || flow.disc === "hover") {
      body = `<div class="row"><button class="placed" id="placed" type="button">${t.placed}</button></div>`; nextOn = false;
    } else if (flow.disc === "falling" || flow.disc === "checking") {
      body = note("info", [t.checking, ""]); nextOn = false;
    } else {
      // mock: what `info` would read off the blank disc
      const mid = { DVD: "CMC MAG. M01", CD: "97m26s66f", BD: "CMCMAG-BA5" }[kind];
      flow.newMid = mid;
      const guess = { DVD: "CMC DVD-R 16x", CD: "CD-R 52x (97m26s66f)", BD: "CMC BD-R 6x" }[kind];
      body = note("good", t.identified(`${kind}-R`, mid)) +
        `<label class="name-field"><span>${t.nameLabel}</span><input id="newname" type="text" maxlength="40" value="${flow.newName ?? guess}"></label>`;
      nextText = t.nameUse;
    }
  } else if (flow.step === 0) {
    h = t.prepare; lede = t.prepareLede(discWord);
    const free = ["out", "flying", "hover", "remove"].includes(flow.disc);
    const opt = (v, a, b) => `<label class="choice"><input type="radio" name="src" value="${v}"${flow.choice === v ? " checked" : ""}${free ? "" : " disabled"}><b>${a}</b><span>${b}</span></label>`;
    body = `<div class="choices">${it.rw ? opt("rw", t.optRw, t.optRwSub) : opt("burn", t.optBurn, t.optBurnSub)}${opt("have", t.optHave, t.optHaveSub)}</div>`;
    const put = flow.choice === "have" ? t.putData : t.putBlank(discWord);
    if (flow.disc === "detect" || flow.disc === "detecting" || flow.disc === "identify") {
      body += note("info", [flow.disc === "identify" ? t.identify : t.detect, ""]); nextOn = false;
    } else if (flow.disc === "remove") {
      body += note("warn", t.notMeasure) + `<div class="row"><button class="placed" id="removed" type="button">${t.removed}</button></div>`;
      nextOn = false; warn = true;
    } else if (flow.disc === "out" || flow.disc === "flying" || flow.disc === "hover") {
      body += note("info", [put, ""]) + `<div class="row"><button class="placed" id="placed" type="button">${t.placed}</button><button class="demo" id="wrong" type="button">${t.wrongDemo}</button></div>`;
      nextOn = false;
    } else if (flow.disc === "falling" || flow.disc === "checking") {
      body += note("info", [t.checking, ""]); nextOn = false;
    } else if (flow.disc === "notblank") {
      body += note("error", t.notBlankNow) + `<div class="row"><button class="placed" id="swapped" type="button">${t.placedAgain}</button></div>`;
      nextOn = false; warn = true;
    } else if (flow.disc === "wrong") {
      body += note("error", t.wrongDisc) + `<div class="row"><button class="placed" id="swapped" type="button">${t.placedAgain}</button></div>`;
      nextOn = false; warn = true;
    } else {
      body += note("good", [flow.choice === "have" ? (flow.measureInDrive ? t.isMeasure : t.dataReady) : t.blankReady(discWord, kind === "BD" ? "25" : kind === "CD" ? "0.7" : "4.7"), ""]);
    }
    nextText = flow.choice === "have" ? t.startMeasure : t.next;
  } else if (flow.step === 0.45) {
    h = t.readyBurn; body = note("info", [t.recheck, ""]); nextOn = false; nextText = t.holdBurn;
  } else if (flow.step === 0.3) {
    h = t.generate; lede = t.generateLede; nextOn = false; nextText = t.holdBurn;
  } else if (flow.step === 0.4) {
    h = t.readyBurn; lede = t.readyLede; nextText = t.holdBurn; hold = true;
  } else if (flow.step === 0.5) {
    h = t.burning; lede = t.burningLede; body = note("info", [t.leaveNote, ""]); nextOn = false; nextText = t.startMeasure;
  } else if (flow.step === 0.9) {
    h = t.burned; nextText = t.startMeasure;
  } else if (flow.step === 1) {
    h = t.timing; lede = t.timingLede;
    const p = flow.job?.p ?? 0;
    body = `<dl class="readout"><div><dt>${t.rpm}</dt><dd>${p > 0.2 ? "2,355" : "—"}</dd></div><div><dt>${t.jitter}</dt><dd>${p > 0.5 ? "0.61°" : "—"}</dd></div><div><dt>${t.mode}</dt><dd>${p > 0.2 ? "CAV" : "—"}</dd></div></dl>`;
    nextOn = false;
  } else if (flow.step === 2 || flow.step === 2.9) {
    const done = flow.step === 2.9;
    h = done ? t.geoDone : t.geo; lede = done ? "" : t.geoLede;
    body = chart(flow.rungs, done) + `<dl class="readout"><div><dt>${t.points}</dt><dd>${flow.rungs} / ${RUNGS.length}</dd></div><div><dt>${t.span}</dt><dd>${flow.rungs ? `24.2–${RUNGS[Math.max(0, flow.rungs - 1)].r.toFixed(1)} mm` : "—"}</dd></div><div><dt>${t.sigma}</dt><dd>${done ? "0.14°" : "—"}</dd></div></dl>`;
    nextOn = done;
  } else if (flow.step === 3) {
    h = t.photo; lede = t.photoLede;
    body = `<div class="row"><div class="qr" aria-label="QR">QR</div><div>${note(flow.photos >= 3 ? "good" : "info", [flow.photos >= 3 ? t.photoRead : t.photoScan, t.photoGot(Math.min(3, flow.photos))])}</div></div>`;
    if (flow.photos < 3) body += `<button class="demo" id="photo" type="button">${t.photoDemo}</button>`;
    nextOn = flow.photos >= 3;
  } else if (flow.step === 4) {
    h = t.done; lede = t.doneLede;
    body = chart(RUNGS.length, true) + `<div class="row"><span class="note" data-s="good"><svg class="icon"><use href="#i-good"/></svg><p>${t.source}</p></span>` +
      `<label class="count-input">${t.leftQ}<input id="left-input" type="number" min="0" max="${it.of}" value="${flow.left}">${t.leftUnit}</label></div>`;
    nextText = t.save;
  }

  if ([0, 0.4].includes(flow.step)) body = budgetHTML(it.row, api.lang()) + body;
  const before = $("cal").querySelector('.note[data-s="warn"], .note[data-s="error"]')?.textContent;
  $("cal").innerHTML = `${steps}<h2>${h}</h2>${lede ? `<p class="lede">${lede}</p>` : ""}${body}`;
  const alertNote = $("cal").querySelector('.note[data-s="warn"], .note[data-s="error"]');
  if (alertNote && alertNote.textContent !== before) alertNote.classList.add("flash");
  const nb = $("next");
  $("next-text").textContent = nextText;
  nb.disabled = !nextOn;
  nb.classList.toggle("hold", hold && nextOn);
  nb.dataset.hold = hold && nextOn ? "1" : "";
  flow.warnEl.classList.toggle("on", warn);
  flog.title(flow.job ? h : "");
  $("cal").classList.toggle("floor-titled", !!flow.job);

  for (const r of $("cal").querySelectorAll('input[name="src"]')) r.addEventListener("change", () => {
    flow.choice = r.value;
    // a disc on its way in is the wrong one now (its print changes): bring the right one in.
    // A disc waiting to be taken out stays where it is.
    if (flow.disc === "hover" || flow.disc === "flying") { flow.flyerEl.classList.remove("on", "hover", "up"); flow.disc = "out"; }
    paint();
  });
  $("placed")?.addEventListener("click", () => dropIn(false));
  $("wrong")?.addEventListener("click", () => dropIn(true));
  $("swapped")?.addEventListener("click", () => {
    api.placeDisc(false);                    // the wrong disc is taken out; a new one comes in
    api.setTray(true, false);
    flow.disc = "out"; paint();
  });
  $("removed")?.addEventListener("click", takenOut);
  $("newname")?.addEventListener("input", (e) => { flow.newName = e.target.value; });
  $("newname")?.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") next(); });
  $("photo")?.addEventListener("click", () => { flow.photos += 1; paint(); });
  // first look at what is in the drive; once it is empty and open, bring a disc down to it
  if (flow.step === 0 && !flow.state && flow.disc === "detect") { detect(); return; }
  if (flow.step === 0 && !flow.state && flow.disc === "out") {
    flow.disc = "flying";
    if (!api.tray().open) api.setTray(true, false);
    else api.placeDisc(false);
    flyIn();
  }
}

// ---------------------------------------------------------------- hold to confirm on the next button
function holdButton(btn) {
  // A timer decides (one second held = confirmed); animation frames only draw the fill, so the
  // confirmation works even when the page gets no frames.
  let t0 = 0, raf = 0, timer = 0;
  const set = (v) => btn.style.setProperty("--hold", v.toFixed(3));
  const stop = () => { cancelAnimationFrame(raf); clearTimeout(timer); t0 = 0; set(0); };
  const draw = (now) => {
    if (!t0) return;
    set(api.reduce ? 0 : Math.min(1, (now - t0) / 1000));
    raf = requestAnimationFrame(draw);
  };
  const begin = (e) => {
    if (!isCal() || btn.disabled || !btn.dataset.hold) return;
    e.preventDefault();
    if (!t0) {
      t0 = performance.now();
      raf = requestAnimationFrame(draw);
      timer = setTimeout(() => { if (t0) { stop(); next(); } }, 1000);
    }
  };
  btn.addEventListener("pointerdown", begin);
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) btn.addEventListener(ev, () => { if (btn.dataset.hold) stop(); });
  btn.addEventListener("keydown", (e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat && btn.dataset.hold) begin(e); });
  btn.addEventListener("keyup", (e) => { if ((e.key === " " || e.key === "Enter") && btn.dataset.hold) stop(); });
  btn.addEventListener("click", () => {
    if (!isCal() || btn.dataset.hold || btn.disabled) return;
    next();
  });
}


// Live workflow: phases describe the visible panel; measurements and verdicts come from disk.
const liveText = (zh, en) => api.lang() === "zh" ? zh : en;
function realError(error) {
  flow.error = api.backend.errorText(error, api.lang());
  flow.ask = null;
  if (flow.job) endJob();
  showInterior(false);
  paint();
}
function realPaint() {
  if (!flow || !isCal()) return;
  const esc = api.backend.escapeHTML, phase = flow.realPhase;
  let title = liveText('标定这批盘', 'Calibrate this batch'), text = "", button = T().next;
  let html = "", disabled = !!flow.job;
  if (phase === "inspect") {
    text = liveText('放入这种盘，再点检测。检测只读，不会打开托盘。', 'Insert this disc, then check it. Checking is read-only and leaves the tray alone.');
    button = liveText('检测光盘', 'Check disc');
  } else if (phase === "prepare") {
    title = flow.detected.kind;
    text = `${flow.detected.mid || liveText('厂商编号未知', 'Unknown maker code')} · ${flow.detected.sectors ?? "—"} sectors`;
    html = `<label class="name-field">${liveText('盘的名称', 'Disc name')}<input id="real-name" maxlength="120" value="${esc(flow.realName || flow.detected.mid || flow.detected.kind)}"></label>`;
    html += `<p>${esc(T().identified(flow.detected.kind, flow.detected.mid || '—')[1])}</p>`;
    if (flow.detected.blank === true) button = liveText('生成测量镜像', 'Make measurement image');
    else if (flow.detected.blank === false) {
      html += `<label><input id="measurement-confirm" type="checkbox" ${flow.measureConfirmed ? "checked" : ""}>${liveText('这是同批次、刻满随机数据的测量盘', 'This is a full random-data measurement disc from this batch')}</label>`;
      button = liveText('测转速', 'Measure rotation'); disabled = !flow.measureConfirmed;
    } else { text += liveText('。空白状态未知，请重新检测。', '. Blank status is unknown; check again.'); button = liveText('重新检测', 'Check again'); }
  } else if (phase === "burn") {
    title = liveText('刻测量盘', 'Burn the measurement disc');
    text = liveText('光驱里放着同批次的空白盘。按住下一步 1 秒开始刻录：托盘会关上，刻录不能撤销，DVD 约 14 分钟。刻完会自己检查这张盘，接着开始测量。',
      'The drive holds a blank from this batch. Hold Next for a second to burn: the tray closes, burning cannot be undone, about 14 minutes for a DVD. When it is done the disc is checked and measuring starts on its own.');
    html = `<p class="cal-aside">${liveText('也可以用别的刻录程序把', 'Or burn')} <code>${esc(flow.iso)}</code> ${liveText('刻到同批次的空白盘上，放进光驱后', 'to a blank from this batch with another program, put it in, and')} <button id="real-have" type="button" class="btn">${liveText('检测刻好的盘', 'check the burned disc')}</button></p>`;
    button = liveText('下一步：刻测量盘（按住）', 'Next: burn the disc (hold)');
  } else if (["timing", "geo", "random", "saving", "burning", "checking"].includes(phase)) {
    title = {timing:T().timing, geo:T().geo, random:T().generate, saving:liveText('正在保存预设', 'Saving preset'), burning:T().burning,
      checking:liveText('正在检查刻好的盘', 'Checking the burned disc')}[phase];
    text = flow.stage || liveText('等待任务进度。可以取消。', 'Waiting for progress. You can cancel.'); disabled = true;
  } else if (phase === "review") {
    title = liveText('测量结果', 'Measurement result');
    const part = flow.geo || flow.timing;
    text = api.lang() === 'zh' ? ({good:'测量可用', usable:'测量可用但有噪声', narrow_span:'测量范围偏窄', too_noisy:'噪声太大', drive_changed:'光驱状态改变', stopped_early:'提前停止', unknown:'结果未知'}[part?.verdict] || '结果未知') : (part?.verdict || "unknown").replaceAll("_", " ");
    const recovery = recoveryAction(flow);
    const kind = recoveryKind(flow);
    const severity = kind === 'good' ? 'good' : ['too_noisy','drive_changed','media'].includes(kind) ? 'error' : 'warn';
    html = `<div class="cal-recovery">${note(severity, [esc(measurementRecovery(flow)[api.lang()]), ''])}</div>`;
    const ok = recovery.id === 'save';
    button = ok ? (flow.detected.media === "cd" ? liveText('查看 CD 标定下一步', 'CD calibration: next step') : T().save) : recovery.label[api.lang()];
    html += `<details class="cal-details"><summary>${liveText('详情', 'Details')}</summary><p>${liveText('导出的预设仍覆盖整盘；半径参数只限定拟合区域，不能裁掉未测区域。更换读取速度、选择测量区域和比较模型须在电脑命令行操作。将 START-END 换成实际的数据扇区范围，SPEED 换成光驱支持的读取速度（如 4x）；先确认恒速，再执行下一条。光驱保持恒速检查通过后，页面才会继续测量。', 'Use the computer terminal to change reading speed, select measurement areas or compare models. An exported preset covers the full disc; radius options limit fitting and do not remove unmeasured areas. Replace START-END with actual data-sector limits and SPEED with a supported reading speed (such as 4x); confirm steady rotation before the next command. The page continues measuring only after a steady-rotation check passes.')}</p><pre>${esc(recoveryCommands(flow, {drive:api.selectedDrive(), media:flow.detected.media, sectors:flow.blankSectors ?? flow.detected.sectors}))}</pre><p><code>${esc(part?.path || '')}</code></p>${realChart(flow.geo?.measurement)}</details>`;
    if (part?.verdict === 'usable') html += `<button id="real-remeasure" class="placed" type="button">${liveText('检查转速并重测', 'Check rotation and remeasure')}</button>`;
    if (ok) html += `<label class="count-input">${T().leftQ}<input id="left-input" type="number" min="0" max="100000" value="${flow.left ?? ""}"></label>`;
  } else if (phase === "photo") {
    title = liveText('CD：接着在 DIS 标定', 'CD: continue calibration in DIS');
    text = cdPhoto[api.lang()];
    html = `<p>${esc(flow.geo.path)}</p><p>${liveText('导出预设不代表已完成 CD 标定。', 'Exporting a preset does not complete CD calibration.')}</p>`;
    button = liveText('导出 DIS 预设', 'Export DIS preset');
  } else if (phase === "saved") {
    title = liveText('预设已保存', 'Preset saved'); text = flow.savedPath;
    if (flow.detected.media === "cd") html = `<p>${esc(cdPhoto[api.lang()])}</p>`;
    button = liveText('回到首页', 'Return home');
  }
  if (["prepare", "burn"].includes(phase)) html = budgetHTML(flow.detected.media, api.lang()) + html;
  if (flow.ask) {
    html += `<p role="status">${esc(flow.ask.question)}</p><button id="real-yes">${liveText('继续', 'Continue')}</button><button id="real-no">${liveText('取消这一步', 'Decline')}</button>`;
    disabled = true;
  }
  if (flow.error) { html += `<div role="alert">${note("error", [esc(flow.error), ""])}</div><button id="real-retry">${liveText('重新检测', 'Check again')}</button>`; disabled = true; }
  const previousAlert = $("cal").querySelector('.note[data-s="warn"], .note[data-s="error"]')?.textContent;
  $("cal").innerHTML = `<h2>${esc(title)}</h2><p class="lede">${esc(text)}</p>${html}`;
  const alertNote = $("cal").querySelector('.note[data-s="warn"], .note[data-s="error"]');
  if (alertNote && alertNote.textContent !== previousAlert) alertNote.classList.add('flash');
  flow.warnEl.classList.toggle('on', !!flow.error || (phase === 'review' && recoveryKind(flow) !== 'good'));
  // while a job runs, its step's name lies on the floor in front of the drive (floor-log.js)
  flog.title(flow.job ? title : "");
  $("cal").classList.toggle("floor-titled", !!flow.job);
  // burning is confirmed by holding the button (holdButton), everything else by a click
  const hold = phase === "burn" && !disabled;
  $("next-text").textContent = button; $("next").disabled = disabled; $("next").dataset.hold = hold ? "1" : "";
  $("next").classList.toggle("hold", hold);
  $("real-name")?.addEventListener("input", e => {flow.realName = e.target.value;});
  $("measurement-confirm")?.addEventListener("change", e => {flow.measureConfirmed = e.target.checked; paint();});
  $("left-input")?.addEventListener("input", e => { flow.left = e.target.value === "" ? null : Number(e.target.value); });
  $("real-retry")?.addEventListener("click", () => {flow.error = null; flow.realPhase = "inspect"; paint();});
  for (const [id, yes] of [["real-yes",true],["real-no",false]]) $(id)?.addEventListener("click", async () => {
    try { const ask = flow.ask; await api.backend.answer(ask.job, ask.id, yes); flow.ask = null; paint(); } catch(e) {realError(e);}
  });
  $("real-remeasure")?.addEventListener("click", () => realNext(true));
  $("real-have")?.addEventListener("click", () => { flow.realPhase = "inspect"; realNext(); });

}
// the core's steps (calibrate.py) as this page's phases
const STEP_PHASE = { burn: "burning", check: "checking", timing: "timing", geo: "geo", preset: "saving" };
async function realJob(action, args = {}, extra = {}, following = null) {
  const f = flow;
  const current = {kind:action, id:following, p:0}; f.job = current;
  $("job").hidden = false; $("job-name").textContent = action; paint();
  const drive = ["info","timing","geo","burn","calibrate"].includes(action) ? api.selectedDrive() : undefined;
  placeLog(); flog.start(commandLine(action, drive));
  const onEvent = event => {
      if (flow !== f) return;
      if (event.type === "started") current.id = event.job;
      if (event.type === "step") {
        f.realPhase = STEP_PHASE[event.name] ?? f.realPhase; f.stage = null; current.p = 0;
        $("job-name").textContent = event.name;
        flog.log(`$ python -m discprobe ${event.name}`, "command");
        if (event.name !== "geo") showInterior(false);
        paint();
      }
      if (event.type === "disc" && event.present) f.detected = { ...f.detected, ...event };
      if (event.type === "log") flog.log(event.text, event.level, event.ansi);
      if (event.type === "progress") flog.progress(event.fraction, event.stage, event.eta_s);
      if (event.type === "ask") { f.ask = event; paint(); }
      if (event.type === "answer") { f.ask = null; paint(); }
      if (event.type === "stopped") f.error = liveText('提前停止：', 'Stopped early: ') + event.reason;
      if (event.type === "progress") {
        current.p = Math.max(0, Math.min(1, event.fraction || 0)); f.plateP = current.p;
        f.stage = event.stage; api.jobProgress(current.p, f.detected?.media || f.item?.row || "dvd");
        $("job-time").textContent = Number.isFinite(event.eta_s) ? T().leftSec(Math.max(0, event.eta_s)) : "?";
        if (action === "geo" || f.realPhase === "geo") { setPlate("geo"); showInterior(true); updateInterior(current.p, Math.max(0, event.eta_s || 0)); }
      }
  };
  try {
    return following ? await api.backend.follow(following, onEvent)
      : await api.backend.job({action, media:f.detected?.media || f.item.row || "dvd", drive, args, ...extra}, onEvent);
  } finally { if (flow === f) {endJob(); f.ask = null; showInterior(false);} }
}
async function realNext(forceMeasure = false) {
  if (flow.job) return;
  flow.error = null;
  try {
    const phase = flow.realPhase;
    if (phase === "burn") await realBurn();
    else if (phase === "inspect" || (phase === "prepare" && flow.detected.blank == null)) {
      const result = await realJob("info");
      if (!result?.disc?.present) throw new Error(liveText('没有读到盘。放入光盘再检测。', 'No disc detected. Insert a disc and check again.'));
      if (result.disc.media !== (flow.item.row || flow.detected?.media || "dvd")) throw new Error(liveText('盘的类型不符，请换盘后重试。', 'Wrong disc family. Replace the disc and check again.'));
      const expectedMid = flow.detected?.mid || flow.item.mid;
      if (expectedMid && result.disc.mid !== expectedMid) throw new Error(liveText('厂商编号已改变，请放回同批次光盘。', 'The maker code changed. Insert a disc from the same batch.'));
      flow.detected = result.disc; flow.realPhase = "prepare"; flow.measureConfirmed = false;
      if (result.disc.blank === true) flow.blankSectors = result.disc.sectors;     // the capacity a preset needs
    } else if (phase === "prepare") {
      if (flow.detected.blank === true && flow.iso) flow.realPhase = "burn";     // the image made before, kept for a retry
      else if (flow.detected.blank === true) {
        const media = flow.detected.media;
        const capacity = flow.detected.sectors;
        if (!Number.isInteger(capacity)) throw new Error(liveText('容量未知。请重新检测空白盘。', 'Capacity is unknown. Check the blank disc again.'));
        flow.iso = `iso/${media}-measurement-${Date.now()}.iso`;
        flow.realPhase = "random";
        const sectors = Math.floor(capacity * .98 / (media === "cd" ? 1 : 16)) * (media === "cd" ? 1 : 16);
        const result = await realJob("random", {sectors, output:flow.iso});
        if (!result?.path) throw new Error("No measurement image was saved.");
        flow.realPhase = "burn";
      } else if (flow.measureConfirmed) await realCalibrate();
    } else if (phase === "review") {
      const recovery = forceMeasure === true ? {id:'measure'} : recoveryAction(flow);
      if (recovery.id === 'blank') {
        flow.geo = null; flow.timing = null; flow.preset = null;
        flow.realPhase = "inspect";
        await realNext();
      } else if (recovery.id === 'measure') {
        flow.preset = null; flow.geo = null; flow.timing = null;
        try {
          const result = await remeasure(async (action, args) => {
            flow.realPhase = action;
            const result = await realJob(action, args);
            flow[action] = result;
            return result;
          });
          Object.assign(flow, result);
        } catch (error) {
          if (!error.result) throw error;
          const part = error.result.geo || error.result.timing || error.result;
          flow[flow.realPhase] = part;
        }
        flow.realPhase = 'review';
      } else if (flow.detected.media === "cd") flow.realPhase = "photo";
      else await realSave();
    } else if (phase === "photo") await realSave();
    else if (phase === "saved") { flow = null; release(); await api.reload(); return; }
    paint();
  } catch(error) { realError(error); }
}
// The rest is the core's (`discprobe calibrate`, one job): with an image it burns it first, then checks the
// disc, measures the rotation and the geometry and writes the preset. The page only follows the job's steps,
// so a reload or a closed tab does not stop it (home finds the job again and calls attach()).
async function realCalibrate(args = {}, extra = {}) {
  const preset = `presets/calibration-${Date.now()}.json`;
  // the preset needs the blank's capacity: known when the blank was read here; else the core reads it before burning
  let result;
  try { result = await realJob("calibrate", { ...args, mid: flow.detected?.mid || undefined, preset, sectors: flow.blankSectors || undefined }, extra); }
  catch (error) { if (!error.result?.timing && !error.result?.geo) throw error; result = error.result; }
  flow.error = null;
  finishCalibrate(result);
}
function finishCalibrate(result) {
  if (!result?.ok && !result?.geo && !result?.timing) throw new Error(result?.reason ? liveText('标定停在这一步：', 'Calibration stopped: ') + result.reason : liveText('标定没有完成。', 'The calibration did not finish.'));
  flow.timing = result.timing; flow.geo = result.geo; flow.preset = result.preset;
  if (result.disc) flow.detected = { ...flow.detected, ...result.disc };
  flow.realPhase = "review";
}
// The measurement disc, burned here: a fresh read-only look that the tray still holds a blank (which also
// lets the server accept this one burn), a one-time token, the burn; then the disc is read again (written
// now, same maker code) and measuring starts.
async function realBurn() {
  const media = flow.detected.media, drive = api.selectedDrive();
  flow.realPhase = "burning"; flow.stage = liveText('检查托盘里还是空白盘…', 'Checking the tray still holds the blank…'); paint();
  const report = await api.backend.request(`/api/burn-speeds?drive=${encodeURIComponent(drive)}&media=${media}`);
  if (report?.blank !== true) { flow.realPhase = "burn"; throw new Error(liveText('光驱里不是空白盘。放回这批的空白盘再刻。', 'The drive does not hold a blank. Put a blank from this batch back and burn again.')); }
  const { token } = await api.backend.request("/api/burn-token");
  flow.stage = null;
  await realCalibrate({ iso: flow.iso }, { burn_token: token });
}
async function realSave() {
  flow.realPhase = "saving";
  const output = `presets/calibration-${Date.now()}.json`;
  const result = flow.preset ? { path: flow.preset } : await realJob("disexport", {geo:flow.geo.path, sectors:flow.blankSectors ?? flow.detected.sectors, output});
  if (!result?.path) throw new Error("No preset was saved.");
  const state = await api.backend.state();
  const entry = state.catalogue[flow.detected.media].find(x => x.geo === flow.geo.path);
  if (!entry) throw new Error("The calibration is not in the saved catalogue.");
  await api.backend.request("/api/catalogue", {id:entry.id, name:flow.realName || entry.name, preset:result.path,
    ...(flow.left == null ? {} : {left:flow.left})});
  flow.savedPath = result.path; flow.realPhase = "saved";
}

function realChart(measurement) {
  const points = measurement?.points || [];
  if (!points.length) return "";
  const lo = Math.min(...points.map(p => p.lba)), hi = Math.max(...points.map(p => p.lba));
  const extent = Math.max(.1, ...points.map(p => Math.abs(p.residual_deg) + p.sigma_deg));
  const X = p => 45 + (p.lba-lo)/Math.max(1,hi-lo)*500;
  const Y = v => 100-v/extent*80;
  return `<svg class="chart" viewBox="0 0 560 230" role="img" aria-label="Measured residuals and one sigma error bars">` +
    `<line class="grid" x1="45" x2="545" y1="100" y2="100"/>` +
    points.map(p=>`<line class="bar" x1="${X(p)}" x2="${X(p)}" y1="${Y(p.residual_deg-p.sigma_deg)}" y2="${Y(p.residual_deg+p.sigma_deg)}"/><circle class="pt" cx="${X(p)}" cy="${Y(p.residual_deg)}" r="3"/>`).join("") +
    `<text x="45" y="220">LBA ${lo.toFixed(0)}</text><text x="545" y="220" text-anchor="end">${hi.toFixed(0)} · ±${extent.toFixed(2)}°</text></svg>`;
}
