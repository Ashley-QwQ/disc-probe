import { isActionEnter } from "./kit/shared.js";
import { expandBurnStop, closeBurnStop, paintStopButton, shortDiscWords, interruptedBurn } from './burn-stop.js';
import { calibratedBatch, discDisplayKind, localDay, sameMaker } from "./batches.mjs";
import { checkBurn, confirmBurn, checkingText, discText, failureText, keepDiscForReview, measurementGateText, recheckText } from './burn-preflight.js';
import { nextConfirm } from "./kit/nextconfirm.js";
import { ringButton } from "./kit/ringbutton.js";
import { flipNumber, flipValue } from "./kit/flipnum.js";
import { countdown, countdownText } from "./kit/countdown.mjs";
// The calibration flow, as a mode of the home page: the scene stays at the drive, the right column
// becomes the step panel, the bar shows the job, the back button takes the top-left corner.
// Live jobs use the local API. Simulated readings and timers are limited to ?mock / ?demo=N.

import { adviceHTML, budgetHTML, cdPhoto, measurementRecovery, recoveryKind, recoveryAction, recoveryCommands, remeasure, stopReason, photoSaveWords } from "./guidance.mjs";
import { photoReasonWords, adoptionWords, applicationWords, savedBurnWords, sliderWords, reasonOf, seconds as photoSeconds } from "./photowords.mjs";
import { hasCapability } from "./handshake.mjs";
import { cutaway } from "./drive-scene.js";
import { floorLog } from "./floor-log.js";
import * as sfx from "./sfx.js";
import { stage } from "./calstage.js";
import * as loadDisc from "./loaddisc.js";
import * as calchart from "./calchart.js";      // the measurement charts as engineering drawings (the designer's review)
import { photoPage } from "./photocal.js";
import { curveEditor } from "./curve-edit.js";
const DEMO = Number(new URLSearchParams(location.search).get("demo")) || 40;   // simulated jobs run this many times faster (?demo=N)
const R0 = 22, R1 = 58.5;             // data area, mm: the radius the head sweeps while burning

const STR = {
  zh: {
    steps: ["准备测量盘", "测转速", "测几何", "拍照"],
    prepare: "准备一张测量盘",
    prepareLede: (d) => `测量要用一张刻满随机数据的 ${d}。刻一次，测量就能开始。`,
    optBurn: "刻一张测量盘", optBurnSub: "放入一张同批次的空白盘；耗盘和时间见上面的预算。",
    optHave: "用已刻好的数据盘", optHaveSub: "同批次、刻满随机数据的盘也可以，省一张盘。",
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
    readyBurn: "镜像好了，可以刻", readyLede: "滑动右下角的确认条开始刻录。刻的时候托盘会关上；耗盘和时间见下面的预算。",
    holdBurn: "滑动确认刻测量盘",
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
    geo: "正在测几何", geoLede: "光头在不同半径读出螺旋的位置。每测完一处，图上就添一个点。",
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
  },
  en: {
    steps: ["Measurement disc", "Speed", "Geometry", "Photos"],
    prepare: "Prepare a measurement disc",
    prepareLede: (d) => `Measuring needs a ${d} filled with random data. Burn it once and measuring can start.`,
    optBurn: "Burn a measurement disc", optBurnSub: "Put in a blank from the same batch; see the disc and time budget above.",
    optHave: "Use a data disc you already burned", optHaveSub: "A disc from the same batch filled with random data works too, and saves a blank.",
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
    readyBurn: "The image is ready to burn", readyLede: "Slide the confirmation at the bottom right to start. The tray closes while it burns; see the disc and time budget below.",
    holdBurn: "Slide to burn the measurement disc",
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
    geo: "Measuring the geometry", geoLede: "The drive reads the spiral at different radii. Each completed reading adds a point to the chart.",
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
    item, step: 0, choice: "burn",
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
let returnTo = null, returnAnim = null, returnLabel = null;
function giveBack(result) {
  const r = returnTo;
  returnTo = returnAnim = returnLabel = null;
  if (!r) return false;
  void r(result);
  return true;
}
export function start(homeApi, { returnTo: back = null, returnAnim: anim = null, returnLabel: label = null, keep = false, item = homeApi.current().item } = {}) {
  api = homeApi; $ = api.$;
  if (!keep && !flow?.job) { returnTo = back; returnAnim = back ? anim : null; returnLabel = label; }
  // a job still running belongs to its disc: come back to it; otherwise start over for this disc
  // keep: the note "see the result" brings the person back to a run that ended while another page was open
  if (!flow || (!keep && flow.item !== item && !flow.job)) {
    flow = newFlow(item);
    if (!ui) build();
  }
  if (!api.backend.mock) { flow.realPhase ??= "inspect"; flow.disc = "waiting"; }
  return open();
}

export function resumeSaved(homeApi, item) {
  api = homeApi; $ = api.$;
  if (flow?.job) return open();
  const issue = item.calibration_issue;
  returnTo = returnAnim = returnLabel = null;
  flow = newFlow(item);
  if (!ui) build();
  flow.detected = {media:item.row, mid:item.mid, capacity_sectors:item.capacity_sectors};
  flow.blankSectors = item.capacity_sectors;
  flow.geo = {path:issue.geo, verdict:issue.verdict, measurement:{missing_mm:issue.missing_mm,
    can_resume:issue.can_resume, ...(issue.stopped ? {retry_kind:"rung"} : {})}};
  flow.calibratedOk = false;
  flow.calibrationReason = issue.reason;
  flow.realPhase = "review";
  return open();
}

// After a DVD measurement is saved: the PCAL-C check disc (checkdisc.py) is the default next step, as the CD's
// target photos are. Not when this page is itself the photo step of a check disc burned elsewhere.
function checkDiscOffered() {
  return flow?.realPhase === "saved" && flow.detected?.media === "dvd" && !flow.photoOnly && !!flow.geo?.path && !flow.savedPhotoShift?.written;
}
// leave the saved page: back to the new-plan form with the new batch in it, else the lobby
function savedDone() {
  if (returnTo) { leave(); return; }
  flow = null; release(); api.toLobby?.();
}
// Make the check disc from this measurement, burn it on the burn page, then photograph it here (as the
// burn review's "check disc" does, afterburn.js). Whoever opened the calibration gets it back at the end.
async function burnCheckDisc() {
  const f = flow, geo = f.geo.path;
  if (f.checkMaking) return;
  f.checkMaking = -1; f.checkError = null; paint();
  try {
    const output = `iso/check-${Date.now()}.iso`;
    await realJob("checkdisc", { geo, output });      // the task bar shows it, as the measurement image's making
    const iso = await api.backend.request(`/api/iso?path=${encodeURIComponent(output)}`);
    iso.target = true; iso.geo = geo;
    const burnPage = await import("./burn.js");
    if (flow !== f) return;                      // the page was left meanwhile: the file is made, nothing is burned
    const id = api.selectedDrive(), drive = { id, name: id, speeds: [] };
    const request = (speed, erase) => ({ action: "burn", drive: id, media: "dvd", args: { iso: iso.path, ...(speed ? { speed } : {}), ...(erase ? { erase: true } : {}) } });
    const opener = returnTo, result = { done: true, id: f.savedId, batch: f.savedBatch };
    const finish = () => f.starterCheck ? backToMeasurement(f, 'check_not_completed', opener) : opener ? void opener(result) : api.toLobby?.();
    const item = f.item;
    const ctx = { media: "dvd", item: { name: f.savedBatch?.name ?? f.detected?.mid ?? "" }, iso, drive, preflight: true,
      back: finish, done: () => ctx.photograph(),
      backText: () => opener ? liveText('回到刚才那一步', 'Back to where you were') : liveText('返回大厅', 'Back to the lobby'),
      async recheck() {
        const seen = await checkBurn(api.backend, request(null, drive.eraseRequired));
        ctx.burnDisc = seen.disc; ctx.burnGate = seen.gate; ctx.discIn = !!seen.disc?.present;
        drive.speeds = seen.speeds_x ?? []; drive.rewritable = !!seen.disc?.rewritable;
      },
      burn(onProgress, { speed, erase, confirmed }) {
        let jobId, reason, gate;
        (async () => { try {
          const approved = await confirmBurn(api.backend, request(speed, erase), confirmed, api.lang());
          await api.backend.job(approved, e => {
            if (e.type === "started") jobId = e.job;
            if (e.type === "error") { reason = e.message; gate = e.burn_gate || gate; }
            if (e.type === "progress") onProgress({ progress: e.fraction, elapsed: e.elapsed_s, remaining: e.eta_s });
            // the burn's own record (burner, path, mode) goes with the photos: without it the core will not apply L
            if (e.type === "burn_result") { iso.burnResult = e; onProgress({ burnResult: e }); }
          }); onProgress({ status: "success", progress: 1 });
        } catch (error) { if (reason) error.message = reason; if (gate) error.burnGate = gate;
          onProgress({ status: "failed", errorInfo: error, started: !!jobId }); } })();
        return { cancel() { if (jobId) api.backend.cancel(jobId); } };
      },
      async photograph() { burnPage.leave(); photograph(api, { item, media: "dvd", geo, burnCheck: iso.burnResult ?? null,
        starterCheck: f.starterCheck, returnTo: f.starterCheck ? opener : opener ? () => opener(result) : null }); },
      photographSaved() { burnPage.leave(); photographSaved(api, {item, geo, returnTo: () => burnPage.start(api, ctx),
        burnAgain: () => burnPage.start(api, ctx)}); },
    };
    // close this page without handing it back yet: the opener gets it after the photos (or the burn page's back)
    returnTo = returnAnim = returnLabel = null; f.checkMaking = 0;
    flow = null; release();
    burnPage.start(api, ctx);
  } catch (error) {
    f.checkMaking = 0; f.checkError = error?.message || String(error);
    if (flow === f) paint();
  }
}

// Straight to the photos of a disc just burned with this geometry (the burn page's "Photograph the disc"):
// the photo page reads them against that geometry's run, the core keeps the result next to it (photo.json),
// and the next burn file made from that geometry applies the along-track correction. Back or done: returnTo.
export function photograph(homeApi, { item = null, media = "dvd", geo, burnCheck = null, saved = null, burnAgain = null, starterCheck = null, returnTo: back = null } = {}) {
  api = homeApi; $ = api.$;
  if (flow?.job) return open();                // a measurement still running comes first
  returnTo = back; returnAnim = returnLabel = null;
  flow = newFlow(item ?? { kind: "new", row: media, name: "", mid: "", s: "new" });
  if (!ui) build();
  flow.detected = { media, mid: item?.mid ?? null, capacity_sectors: item?.capacity_sectors ?? item?.sectors ?? null };
  // the burn page's own record of this write: the photo result names how the disc was burned (photo.photo_l)
  flow.geo = { path: geo?.replace(/[\\/](?:summary|starter)\.json$/i, "") }; flow.burnCheck = burnCheck; flow.photoOnly = true; flow.realPhase = "photo";
  flow.starterCheck = starterCheck;
  if (saved) {
    flow.savedBurn = {id:saved.id || null, confirmed:!!saved.confirmed, burnAgain};
    if (typeof saved.discId === "string") flow.photoDiscId = saved.discId;
  }
  // Photographed straight after its burn here: the disc is known, so it gets a number at once (editable) rather
  // than an empty field that, left empty, keeps the photos from ever reaching a picture.
  if (burnCheck?.result === "completed") {
    const d = new Date(), two = (n) => String(n).padStart(2, "0");
    flow.photoDiscId = burnCheck.disc_id || `C${two(d.getMonth() + 1)}${two(d.getDate())}-${two(d.getHours())}${two(d.getMinutes())}`;
  }
  if (starterCheck) {
    flow.photoDiscId = burnCheck?.starter_burn?.disc_id;
    if (!flow.photoDiscId) return backToMeasurement(flow, 'check_not_completed', back);
  }
  if (burnCheckFailed(burnCheck)) { flow.photoOnly = false; flow.realPhase = "review"; }
  return open();
}

export function photographSaved(homeApi, options) {
  return photograph(homeApi, {...options, saved:options.saved ?? {}});
}

// Follow the job's record after reloading, including a result that arrived while the page was closed.
export function attach(homeApi, job) {
  api = homeApi; $ = api.$;
  if (!flow?.job) {
    returnTo = returnAnim = returnLabel = null;
    flow = newFlow({ kind: "new", row: job.media || "dvd", name: "", mid: "", s: "new" });
    if (!ui) build();
    flow.realPhase = "checking"; flow.detected = { ...job.disc, media: job.media || "dvd" };
    flow.iso=job.args?.iso;flow.eraseRequested=!!job.args?.erase;
    flow.blankSectors = job.args?.sectors;
    flow.repairingCoverage = !!job.args?.resume;
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
  addEventListener("resize", () => { if (flyer.dataset.x) placeFlyer(flyer); });
  noise();

  $("back").addEventListener("click", back);
  $("job-cancel").addEventListener("click", cancelJob);
  addEventListener("dp-lang", () => { if (isCal()) paint(); if (flow?.job) paintJob(); });
  // Esc is keys.js's (the Back button); in the mock, Shift+S steps through the states
  addEventListener("keydown", (e) => {
    if (isCal() && api.backend.mock && e.key === "S" && e.shiftKey) cycleState();
  });
  bindNext($("next"));
}

let st = null;                             // the stage (calstage.js), live pages only
let discWentIn = false;                    // the "disc goes into the drive" animation played on this visit
let pendingNext = null;
let nextTime = null;
function writeNext({ text, time }) {
  const label = $("next-text");
  if (!time) {
    if (nextTime) { nextTime.flip.destroy(); nextTime = null; }
    if (label.textContent !== text || label.children.length) label.textContent = text;
    return;
  }
  if (!nextTime || nextTime.el.parentNode !== label) {
    nextTime?.flip.destroy();
    const el = document.createElement("span");
    el.className = "cal-next-time";
    label.replaceChildren(document.createTextNode(""), el);
    nextTime = { el, flip: flipNumber(el, { lang: api.lang(), live: false }) };
  }
  label.firstChild.data = liveText(`${text}，`, `${text}, `);
  if (flipValue(nextTime.el) !== time) nextTime.flip.set(time);
}
function nextWords(text, time = "") {
  pendingNext = { text, time };
  if (!document.documentElement.classList.contains("pan-in")) writeNext(pendingNext);
}
export function arrived() {
  if (isCal() && pendingNext !== null) writeNext(pendingNext);
}
function jobTime(job, seconds) {
  const text = countdownText(seconds);
  if (text === job.left) return;
  job.left = text;
  $("job-time").textContent = text;
  if (!isCal() || leaving) return;
  st?.time(text);
  if (job.nextLabel) nextWords(job.nextLabel, text);
}
function open() {
  document.documentElement.dataset.mode = "cal";
  paintJob();
  // the disc goes in once on a visit, when the drive is seen to hold it; a job running or a result on the
  // paper: it is in already
  discWentIn = !!flow.job || ["review", "saving", "saved"].includes(flow.realPhase);
  $("cal").hidden = false;
  $("back").hidden = false;
  api.focusDrive();
  // resolves when the stage and the desk under it are on screen (at once on the mock page)
  const shown = api.backend.mock ? Promise.resolve() : stage(api).then(async (s) => {
    st = s;
    if (!isCal()) return;
    document.documentElement.classList.add("cal-staged"); st.show(true);
    // until then the story's first frame: the disc on the desk before the open tray (loaddisc.js)
    st.hold(!discWentIn);
    const desk = discWentIn ? loadDisc.desk(true, st.art()) : loadDisc.pose(st.art(), 0);
    paint();
    await desk;
  }).catch((e) => { st?.hold(false); console.error("calibration stage", e); });
  paint();
  // coming back while it burns: the drive is open again, the plate as it was
  if (flow.job?.kind === "burn") setTimeout(() => showInterior(true), 750);
  else if (flow.plate !== "off") setPlate(flow.plate);
  return shown;
}

function release() {
  // A result is "seen" once its page is left, not when it is drawn: a reload on the result (or the CD's
  // photos after it) reopens it, since home reattaches a calibration whose result was not seen.
  if (flow && !flow.photoOnly && ["review", "photo"].includes(flow.realPhase)) acknowledgeResult();
  closeBurnStop();
  globalThis.dispatchEvent(new Event('dp-catalogue-changed'));
  closePhoto();
  nextKit(false, false);
  document.documentElement.dataset.mode = "";
  const ruler = document.getElementById("cal-ruler"); if (ruler) ruler.hidden = true;
  st?.show(false); loadDisc.desk(false); document.documentElement.classList.remove("cal-staged"); sideButton(null);
  document.title = "disc-probe";
  $("cal").hidden = true;
  $("back").hidden = true;
  const nb = $("next");
  nb.disabled = false; nb.classList.remove("hold"); nb.dataset.hold = ""; nb.style.removeProperty("--hold");
  for (const el of [ui.flyerEl, ui.plateEl, ui.warnEl, ui.ledEl, ui.parcelEl]) el.classList.remove("on", "hover", "drop", "breathe", "up", "ship");
  showInterior(false);
  flog.hide();
  paintJob();
}

let leaving = false;
// For navigation snapshots: a photo step opened straight on a batch (photograph()) is restored to that batch's
// photo page after a reload, instead of starting a new calibration. Nothing about a running job is kept.
export function navigationState() {
  if (!flow?.photoOnly || flow.realPhase !== 'photo' || !flow.geo?.path) return null;
  const saved = flow.savedBurn;
  return {media: flow.detected?.media || 'dvd', geo: flow.geo.path, batch: flow.item?.id ?? null,
    ...(saved ? {saved:{id:saved.id, confirmed:saved.confirmed, discId:flow.photoDiscId}} : {})};
}
export function suspendNavigation() {
  if (!flow) return;
  if (flow.job) flow.callMe = true;
  release();
}
function leave() {
  if (leaving) return;                         // the opener already owns the return pan/card hand-off
  closeBurnStop();
  // a disc that was in the air goes back to waiting; detection starts over next time
  if (!flow.job && ["detecting", "identify", "flying", "hover", "falling", "checking"].includes(flow.disc)) flow.disc = "detect";
  if (!flow.job && flow.disc === "remove") flow.disc = "detect";
  const closed = flow;
  const done = closed?.realPhase === "saved";
  const result = { done, id: done ? closed.savedId : undefined, batch: done ? closed.savedBatch : undefined };
  const finish = () => {
    release();
    if (done) flow = null;
    if (!giveBack(result)) api.goTo(...api.locate(closed.item));
  };
  if (returnTo && returnAnim && !api.reduce) {          // the opener takes the camera back first, then the page closes
    leaving = true;
    const anim = returnAnim; returnAnim = null;
    anim(finish, async (signal) => {
      if (!st || !discWentIn) return;
      st.hold(true);
      try { await loadDisc.play(st.art(), { reverse: true, signal }); }
      catch (e) { console.error("reverse disc animation", e); }
      finally { if (!leaving) st.hold(false); }
    }).finally(() => { leaving = false; });
    return;
  }
  finish();
}

function back() {
  if (!isCal()) return;
  if (flow.job) {
    flow.callMe = true;
    release();
    api.toLobby?.();
    return;
  }
  if (!api.backend.mock) {
    if (flow.realPhase === "photo") { if (photoUI?.page) photoUI.page.back(); else photoReview(); return; }
    if (!flow.job && CAPACITY_PHASES.includes(flow.realPhase)) {
      flow.realPhase = flow.realPhase === "capacityWritten" ? "capacityBlank" : "prepare";
      flow.blankSectors = null;
      flow.error = null; paint(); return;
    }
    leave(); return;
  }
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

// Percent positions belong to the camera's box; convert only at a target change or resize.
function placeFlyer(f, x = f.dataset.x, y = f.dataset.y) {
  f.dataset.x = x; f.dataset.y = y;
  f.style.transform = `translate(${parseFloat(x) / 100 * api.cam.clientWidth}px, ${parseFloat(y) / 100 * api.cam.clientHeight}px) translate(-50%, -50%)`;
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
  placeFlyer(f, tx, ty);
  f.classList.add("on", "up");
  api.placeDisc(false);
  void f.offsetWidth;
  f.style.transition = "";
  const [hx, hy] = pct(...hoverPoint());
  placeFlyer(f, hx, hy);
  await wait(1400);
  if (stale(fl)) return;
  f.classList.add("hover");
}

async function takenOut() {
  const f = flow.flyerEl;
  f.classList.remove("hover");
  placeFlyer(f, f.dataset.x, "-30%");         // gone, up and away
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
  placeFlyer(f, x, "-30%");
  f.classList.add("on");
  void f.offsetWidth;
  f.style.transition = "";
  placeFlyer(f, x, y);
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
  placeFlyer(f, x, y);
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
  $("job-name").textContent = { gen: t.genJob, burn: t.burnJob, timing: t.timingJob, geo: t.geoJob }[kind];
  paintJob();
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
    jobTime(job, leftS / DEMO);
    job.fraction = job.p;
    if (kind === "gen") imageRing?.progress(job.p);
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
  closeBurnStop();
  clearInterval(flow.job.timer);
  flow.job.clock?.clear();
  flow.job = null;
  paintJob();
  flog.end();
}

export const hasJob = () => !!flow?.job;
// The burn step has three parts a person can tell apart: writing; the drive finishing the disc after 100 %
// (no events from it); and the sampled read-back (verify_progress). Each says what it is.
function burnPart() {
  const job = flow?.job;
  if (!job || flow.realPhase !== 'burning') return null;
  return job.verifying ? 'verify' : (job.p ?? 0) >= 0.999 ? 'finish' : 'write';
}
const burnPartWords = part => part === 'verify' ? liveText('抽查回读', 'Checking the burn')
  : part === 'finish' ? liveText('封盘', 'Finishing the disc') : null;
function isWriting(job) {
  return api.backend.mock ? job.kind === "burn" : flow.realPhase === "burning" && !job.verifying;
}
// the task bar's label is kept as a key (flow.jobWord) so a language switch rewrites it here
function paintJob() {
  if (flow?.job && flow.jobWord) $("job-name").textContent = flow.jobWord === 'erase' ? liveText('擦除光盘','Erasing')
    : (flow.jobWord === 'burn' && burnPartWords(burnPart())) || stepWords(flow.jobWord);
  const job = flow?.job, active = !!job;
  $("job").hidden = !active;
  const name = $("job-name");
  name.disabled = !active || isCal();
  if (active) {
    name.setAttribute("aria-label", liveText("回到校准", "Return to calibration"));
    paintStopButton($("job-cancel"), isWriting(job), api.lang(), flow.realPhase === "erasing");
    $("job-cancel").disabled = !!job.stopping || (!api.backend.mock && !job.id);
  }
  globalThis.dispatchEvent?.(new Event("dp-cal-job"));
}

function cancelJob(confirmed = false) {
  if (!flow?.job) return;
  const current=flow.job;
  const burning=isWriting(current);
  // click listeners pass an Event, so only the slider's literal true can authorize a write stop.
  if(burning && confirmed!==true){
    expandBurnStop($("job-cancel"),{lang:api.lang(),rewritable:!!flow.detected?.rewritable,valid:()=>flow?.job===current && (api.backend.mock||flow.realPhase==='burning') && !current.verifying,
      done:()=>cancelJob(true)});return;
  }
  if (!api.backend.mock) { if (current.id && !current.stopping) {
    current.stopping=true;$("job-cancel").disabled=true;
    api.backend.cancel(current.id).catch(error=>{current.stopping=false;$("job-cancel").disabled=false;
      flow.error=api.backend.errorText(error,api.lang());paint();});
  } return; }
  const kind = flow.job?.kind;
  if(kind==='burn'){
    flow.burnP=current.p;flow.burnInterrupted=true;flow.burnCheck={result:'cancelled'};
    flow.cancelledByUser={phase:'burn',fraction:current.p};
  }
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
  if (st && !api.backend.mock) on = false;     // the stage shows the inside from above instead of the cutaway
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
  if(flow.burnInterrupted){
    flow.state=null;flow.burnInterrupted=false;flow.burnCheck=null;flow.cancelledByUser=null;
    flow.step=0;flow.disc='out';setPlate('off');paint();return;
  }
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
  it.last = localDay().map((n) => String(n).padStart(2, "0")).join("-");
  it.drive = "GH70N";
  const v = Number($("left-input")?.value);
  if (Number.isFinite(v) && v >= 0) it.left = Math.min(it.of, Math.round(v));
  flow.savedId = it.id; flow.savedBatch = it; flow.realPhase = "saved";
  leave();
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
    if(flow.burnInterrupted){h=liveText('刻录已停止','Burn stopped');body=note('error',[interruptedBurn(flow,api.lang()),'']);nextText=liveText('换一张空白盘重新刻','Replace with a blank and burn again');}
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
    body = `<div class="choices">${opt("burn", t.optBurn, t.optBurnSub)}${opt("have", t.optHave, t.optHaveSub)}</div>`;
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
  nextWords(nextText);
  nb.disabled = !nextOn;

  nextKit(hold, !nextOn, flow.job?.kind === "gen");
  flow.warnEl.classList.toggle("on", warn);
  flog.title(flow.job ? h : "");
  $("cal").classList.toggle("floor-titled", !!flow.job && !st);     // with the stage, the title stays on the paper

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
  $("newname")?.addEventListener("keydown", (e) => { e.stopPropagation(); if (isActionEnter(e)) { e.preventDefault(); next(); } });
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

// The irreversible step owns a slider; other steps keep the normal Next button.
let imageRing = null;
function nextKit(slide, disabled, making = false) {
  nextConfirm($("next"), {active:slide, disabled, lang:api.lang(), label:flow?.eraseRequested?liveText('滑动确认擦除后重刻','Slide to erase and burn again'):undefined, done:() => {
    if (isCal() && !$("next").disabled) next();
  }});
  if (making) {
    imageRing ||= ringButton($("next"), {lang:api.lang()});
    imageRing.progress(flow.job?.fraction ?? null);
  } else { imageRing?.destroy(); imageRing = null; }
}
function bindNext(btn) {
  btn.addEventListener("click", () => {
    if (!isCal() || btn.hidden || btn.disabled) return;
    next();
  });
}

// Live workflow: phases describe the visible panel; measurements and verdicts come from disk.
const liveText = (zh, en) => api.lang() === "zh" ? zh : en;
const escapeRetry = value => api.backend.escapeHTML(value);
const usbRetryWords = () => liveText(
  '如果用的是超薄 USB 光驱，试试主板后面的 USB 3.0 口，或用带电源的 USB 集线器。测量时别碰桌子。',
  'For a slim USB drive, try a rear USB 3.0 port on the motherboard or a powered USB hub. Keep the table still while measuring.');

function retryButton(id, words, speed = null) {
  return `<button id="${id}" class="placed" type="button"${speed == null ? '' : ` data-speed="${escapeRetry(speed)}"`}>${escapeRetry(words)}</button>`;
}

function readRetryOptions(part) {
  const measurement = part?.measurement;
  const advice = measurement?.retry_speed_advice || measurement?.speed_advice;
  const suggested = advice?.next_speed;
  const lower = advice?.lower_speeds || [];
  return (suggested ? retryButton('real-suggested-speed',
    liveText(`用建议速度 ${suggested} kB/s 重测`, `Remeasure at ${suggested} kB/s (suggested)`), suggested) : '')
    + (lower.length ? `<div class="row"><label>${liveText('更低的读取速度', 'Lower reading speed')}
      <select id="real-lower-read-speed">${lower.map(speed => `<option value="${escapeRetry(speed)}">${escapeRetry(speed)} kB/s</option>`).join('')}</select></label>
      ${retryButton('real-lower-read', liveText('用所选速度重测', 'Remeasure at selected speed'))}</div>` : '');
}

function diagnosticWords() {
  const part = flow.geo || flow.timing;
  const details = flow.retryDiagnostics;
  const reason = part?.measurement?.stopped || flow.calibrationReason || flow.burnCheck?.reason
    || flow.coverageNotice || flow.error || measurementRecovery(flow)[api.lang()];
  const powershell = api.platform?.() === 'win32';
  const argv = (details?.argv || []).map(word => /^[\w.:/\\-]+$/.test(word) ? word
    : "'" + word.replaceAll("'", powershell ? "''" : "'\\''") + "'");
  const command = (powershell && argv[0]?.startsWith("'") ? '& ' : '') + argv.join(' ');
  return [
    liveText('我在用 disc-probe 标定测量盘，想请帮忙排查。', 'I am calibrating a measurement disc with disc-probe and would like help.'),
    reason,
    command && liveText(`执行过的命令：${command}`, `Command run: ${command}`),
    details?.log_path && liveText(`任务日志：${details.log_path}`, `Job log: ${details.log_path}`),
    part?.path && liveText(`测量记录：${part.path}`, `Measurement record: ${part.path}`),
    flow.burnCheck?.log_path && liveText(`刻录日志：${flow.burnCheck.log_path}`, `Burn log: ${flow.burnCheck.log_path}`),
  ].filter(Boolean).join('\n');
}

function diagnosticOptions() {
  if (!hasCapability('measurement-retry')) return '';
  return `<details class="cal-advanced"><summary>${liveText('诊断信息', 'Diagnostics')}</summary>
    <pre class="cal-cmd">${escapeRetry(diagnosticWords())}</pre>
    ${retryButton('real-copy-diagnostics', liveText('复制求助信息', 'Copy help request'))}
    ${retryButton('real-download-diagnostics', liveText('导出诊断信息', 'Export diagnostics'))}</details>`;
}

function checkMeasurementDisc() {
  return `<details class="cal-advanced"><summary>${liveText('检查测量盘的刻录', 'Check the measurement burn')}</summary>
    <p>${liveText('在终端运行这条命令检查测量盘。若仍读不出来，用同批空白盘，选较低速度重刻随机数据测量盘。',
      'Run this command in Terminal to check the measurement disc. If it still cannot be read, burn a new random-data measurement disc from the same batch at a lower write speed.')}</p>
    <pre class="cal-cmd">python -m discprobe checkburn --drive ${escapeRetry(JSON.stringify(api.selectedDrive()))}</pre></details>`;
}

function burnRetryOptions(report) {
  if (!flow.burnRetry) return '';
  const previous = flow.lastBurnSpeed;
  const speeds = (report?.speeds_x || []).filter(speed => !previous || speed < previous);
  if (!speeds.length) return `<p>${liveText('这张盘没有报出更低的刻录速度。', 'This disc reports no lower write speeds.')}</p>`;
  const label = previous ? liveText('更低的刻录速度', 'Lower write speed') : liveText('刻录速度', 'Write speed');
  return `<label>${label} <select id="real-burn-speed">
    <option value="">${liveText('默认速度', 'Default speed')}</option>
    ${speeds.map(speed => `<option value="${escapeRetry(speed)}"${flow.burnSpeed === speed ? ' selected' : ''}>${escapeRetry(speed)}×</option>`).join('')}
    </select></label>`;
}

function measuringButton(phase) {
  return { burning: {verify: liveText("核对中", "Checking"), finish: liveText("封盘中", "Finishing")}[burnPart()] ?? liveText("刻录中", "Burning"), random: liveText("生成中", "Making"),
    saving: liveText("保存中", "Saving"), erasing: liveText("擦除中", "Erasing") }[phase]
    ?? liveText("测量中", "Measuring");
}
function burnCheckFailed(burn) {
  const v = burn?.verification;
  return !!burn && ((burn.result && burn.result !== "completed") || burn.disc_state?.status === "failed" ||
    (v && v.status !== "skipped" && (v.status !== "completed" || v.differing || v.unreadable || v.untested)));
}
const needsBlankCapacity = () => !(
  flow.blankSectors || flow.detected.capacity_sectors || flow.catalogueSectors
);
const CAPACITY_PHASES = ["capacityBlank", "capacityWritten"];
const MAX_SECTORS = 25_000_000;   // webui.py's sectors argument limit
function manualCapacity(value) {
  const sectors = Number(value);
  return Number.isInteger(sectors) && sectors > 0 && sectors <= MAX_SECTORS ? sectors : undefined;
}
function realError(error) {
  setTimeout(callBack, 0);
  if (error?.failure) sfx.failure(); else sfx.problem();      // a disc lost, or something to put right
  const burnPhase = ['burn','burning','erasing','checking'].includes(flow.realPhase) && flow.iso;
  if(burnPhase)flow.burnFailureGate=error.burnGate;
  flow.error = burnPhase ? measurementGateText(error.burnGate,api.lang()) ||
    failureText(error,api.lang(),{started:!!flow.burnStarted,readBack:!!flow.burnCheck?.verification})
    : api.backend.errorText(error, api.lang());
  if (flow.realPhase === "saving") flow.realPhase = "review";
  if(interruptedBurn(flow,api.lang()) || flow.burnStarted && flow.realPhase==='burning'){
    flow.burnInterrupted=true;flow.realPhase='burnStopped';
  } else if(burnPhase && !flow.burnStarted && ['burn','burning'].includes(flow.realPhase)){
    flow.realPhase='burn';flow.burnInspection=null;flow.batchConfirmed=false;
  }
  flow.ask = null;
  if (flow.job) endJob();
  showInterior(false);
  paint();
}
function realPaint() {
  if (!flow || !isCal()) return;
  const esc = api.backend.escapeHTML, phase = flow.realPhase;
  if (phase === "photo") {
    paintRuler();
    if (flow.savedBurn && (!flow.savedBurn.confirmed || !flow.savedBurn.record)) paintSavedBurn();
    else paintPhoto();
    return;
  }
  closePhoto(); st?.show(true);
  let title = liveText('标定这批盘', 'Calibrate this batch'), text = "", button = T().next;
  let html = "", disabled = !!flow.job;
  let hold = false;
  if (phase === "inspect") {
    text = liveText('放入这种盘，再点检测。检测只读，不会打开托盘。', 'Insert this disc, then check it. Checking is read-only and leaves the tray alone.');
    button = liveText('检测光盘', 'Check disc');
    if (flow.starterFailure) html = note('warn', [esc(flow.starterFailure), '']);
  } else if (phase === "capacityBlank") {
    title = liveText('读取空白盘容量', 'Read blank disc capacity');
    text = liveText('放入一张同批次的空白盘，再点检测。检测只读，不会打开托盘。', 'Insert a blank from the same batch, then check it. Checking is read-only and leaves the tray alone.');
    button = liveText('检测光盘', 'Check disc');
  } else if (phase === "capacityWritten") {
    title = liveText('放回测量盘', 'Put the measurement disc back');
    text = liveText(`已读到空白盘容量：${flow.blankSectors.toLocaleString()} 扇区。换回刚才的测量盘，再点检测。`,
      `Blank capacity read: ${flow.blankSectors.toLocaleString()} sectors. Put the measurement disc back, then check it.`);
    button = liveText('检测刻好的盘', 'Check the burned disc');
  } else if (phase === "prepare") {
    title = discDisplayKind(flow.detected, api.lang());
    text = `${flow.detected.mid || liveText('厂商编号未知', 'Unknown maker code')} · ${flow.detected.sectors ?? "—"} sectors`;
    html = `<label class="name-field">${liveText('盘的名称', 'Disc name')}<input id="real-name" maxlength="120" value="${esc(flow.realName || flow.detected.mid || flow.detected.kind)}"></label>`;
    html += `<p>${esc(T().identified(title, flow.detected.mid || '—')[1])}</p>`;
    if (flow.detected.rewritable && flow.detected.blank === false) {
      html += `<p>${liveText('这张可擦写盘已有内容。擦除后重刻会清掉盘上的内容。','This rewritable disc has data. Erasing before burning clears its contents.')}</p><button id="real-erase" type="button" class="btn">${liveText('擦除后重刻','Erase and burn again')}</button>`;
    }
    if (flow.detected.blank === true) {
      button = liveText('生成测量镜像', 'Make measurement image');
      if (flow.starterFailure) html += note('warn', [esc(flow.starterFailure), '']);
      if (flow.starterCandidates?.length) {
        const sourceText = source => {
          const measured = source.measured_span_mm?.join('–');
          const from = ({same_drive:liveText('同一台光驱', 'Same drive'), same_model:liveText('同型号光驱', 'Same drive model'),
            community:liveText('社区', 'Community')})[source.kind];
          const warning = source.kind === 'same_drive' ? '' : liveText(' · 未验证：跨机器/跨批次没有实测数据', ' · Unverified: no measurements across machines or batches');
          return `${from} · ${source.name} · ${source.drive} · ${measured ? `${measured} mm` : liveText('测量范围未知', 'Measured range unknown')}${warning}`;
        };
        // The route is the first decision on this page, so it sits above the name, as cards like the
        // measuring-disc choice rather than a menu. The measuring disc stays first and chosen by default.
        const card = (value, head, sub) => `<label class="choice"><input type="radio" name="starter-choice" value="${esc(value)}"${(flow.starterChoice || '') === value ? ' checked' : ''}><b>${head}</b><span>${sub}</span></label>`;
        html = `<div class="choices" id="starter-choice" role="radiogroup" aria-label="${esc(liveText('用起步预设，跳过测量盘', 'Use a starter preset and skip the measurement disc'))}">${
          card('', liveText('先刻测量盘', 'Burn a measurement disc first'), liveText('原来的路线：测量盘、检查盘、成品。', 'The usual route: measurement disc, check disc, picture.'))}${
          flow.starterCandidates.map(s => card(s.id, s.kind === 'same_drive' ? liveText('跳过测量盘，用这台光驱的已有标定', 'Skip it: start from this drive’s calibration')
            : liveText('跳过测量盘，用别处的标定（未验证）', 'Skip it: start from another calibration (unverified)'), esc(sourceText(s)))).join('')}</div>
          <p>${liveText('这批盘还没确认。选择起步预设后，仍要刻检查盘并拍照。', 'This batch is unconfirmed. A starter preset still needs a burned check disc and photos.')}</p>` + html;
        if (flow.starterChoice) button = liveText('刻检查盘', 'Burn the check disc');
      }
    }
    else if (flow.detected.blank === false) {
      html += `<label><input id="measurement-confirm" type="checkbox" ${flow.measureConfirmed ? "checked" : ""}>${liveText('这是同批次、刻满随机数据的测量盘', 'This is a full random-data measurement disc from this batch')}</label>`;
      button = liveText('测转速', 'Measure rotation'); disabled = !flow.measureConfirmed;
      if (flow.measureConfirmed && needsBlankCapacity()) {
        html += `<p>${liveText('这批盘的空白容量未知。推荐放一张同批空白盘读容量，再换回这张测量盘。', 'The blank capacity for this batch is unknown. We recommend reading a blank from the same batch, then putting this measurement disc back.')}</p>
          <button id="real-capacity-check" type="button" class="btn">${liveText('放一张同批空白盘读容量', 'Read a blank from the same batch')}</button>
          <label class="name-field">${liveText('或手动输入空白盘扇区数', 'Or enter the blank disc sector count')}
            <input id="real-capacity" type="number" inputmode="numeric" min="1" max="${MAX_SECTORS}" step="1"
              aria-describedby="real-capacity-help" value="${esc(flow.manualSectors ?? '')}">
          </label>
          <p id="real-capacity-help">${liveText('用同批空白盘的 info 读数。常见值仅供参考：DVD-R 2,297,888，DVD+R 2,295,104。', 'Use the info reading from a blank of the same batch. Common values for reference: DVD-R 2,297,888 and DVD+R 2,295,104.')}</p>`;
        disabled = !manualCapacity(flow.manualSectors);
      }
    } else { text += liveText('。空白状态未知，请重新检测。', '. Blank status is unknown; check again.'); button = liveText('重新检测', 'Check again'); }
  } else if (phase === "burn" && cdHere()) {
    // the core cannot write CDs on Windows yet (burner.WindowsDVD): Windows' own image burner, as guide.py says
    title = liveText('刻测量盘', 'Burn the measurement disc');
    cdCommand();
    text = liveText('这台电脑上还不能从页面刻 CD。光驱里放着这批的空白 CD 时，在 PowerShell 里运行下面这条命令，用仓库里的刻录脚本以 8x 刻（Windows 自带的“刻录光盘映像”会用 40x，在 GH70N 上刻便宜的 CD-R 失败过）。约 11 分钟；刻完托盘弹出又收回，再点“检测刻好的盘”。',
      "This computer cannot burn CDs from the page yet. With a blank CD from this batch in the drive, run the command below in PowerShell: it burns at 8x with the repo's script (Windows' own Burn disc image picks 40x, which failed on a GH70N with cheap CD-R). About 11 minutes; the tray opens and closes again when it is done, then press Check the burned disc.");
    html = flow.cdCommand ? `<pre class="cal-cmd">${esc(flow.cdCommand)}</pre><button id="real-copy" type="button" class="btn">${liveText('复制刻录命令', 'Copy the burn command')}</button>`
      : flow.cdCommand === "" ? `<p>${liveText('没取到刻录命令。在终端运行 guide --media cd，它会打印同一条命令。', 'Could not get the burn command. In Terminal, guide --media cd prints the same command.')}</p><p><code>${esc(flow.iso)}</code></p>`
      : `<p><code>${esc(flow.iso)}</code></p>`;
    button = liveText('检测刻好的盘', 'Check the burned disc');
  } else if (phase === "burn") {
    title = liveText('刻测量盘', 'Burn the measurement disc');
    text = liveText('光驱里放着同批次的空白盘。滑动右下角确认刻录：托盘会关上，刻录不能撤销，DVD 约 14 分钟。刻完会自己检查这张盘，接着开始测量。',
      'The drive holds a blank from this batch. Slide the confirmation at the bottom right to burn: the tray closes, burning cannot be undone, about 14 minutes for a DVD. When it is done the disc is checked and measuring starts on its own.');
    html = `<p class="cal-aside">${liveText('也可以用别的刻录程序把', 'Or burn')} <code>${esc(flow.iso)}</code> ${flow.eraseRequested ? liveText('擦除后刻到这张盘上，放进光驱后', 'to this disc with another program after erasing it, put it in, and') : liveText('刻到同批次的空白盘上，放进光驱后', 'to a blank from this batch with another program, put it in, and')} <button id="real-have" type="button" class="btn">${liveText('检测刻好的盘', 'check the burned disc')}</button></p>`;
    button = flow.eraseRequested?liveText('滑动确认擦除后重刻','Slide to erase and burn again'):liveText('滑动确认刻测量盘', 'Slide to burn the measurement disc');
    if(flow.eraseRequested)text=liveText('盘上的内容会被清掉。滑动右下角确认擦除后重刻；擦除完成后才开始刻录。','The disc contents will be cleared. Slide to confirm erasing and burning again; burning starts only after erasing succeeds.');
    const lang=api.lang(), report=flow.burnInspection, gate=report?.gate;
    const mismatch=gate?.code==='other_batch', blocked=!report || !!(gate&&!mismatch) || !!report.error;
    const status=discText(report?.disc,lang), message=measurementGateText(gate,lang)||(report?.error&&failureText(report.error,lang));
    const discLine='<p role="status">'+esc(flow.burnInspecting?checkingText(lang):status)+'</p>';
    if(blocked){
      text=message || (flow.burnInspecting?checkingText(lang):liveText('先检查光驱里的盘。','Check the disc in the drive first.'));
      html=discLine;
      if(gate?.code==='recorded_rw')html+=`<button id="real-burn-erase" type="button" class="btn">${liveText('准备擦除后重刻','Prepare to erase and burn')}</button>`;
      button=recheckText(lang);disabled=!!flow.burnInspecting;
    } else {
      html=discLine+(mismatch?`<label><input id="measurement-batch-confirm" type="checkbox" ${flow.batchConfirmed?'checked':''}>${liveText('我确认用这张盘刻测量盘，并标定这批盘。','I confirm that I want to burn this measurement disc and calibrate this batch.')}</label>`:'')+
        `<button id="real-burn-recheck" type="button" class="btn">${recheckText(lang)}</button>`+burnRetryOptions(report)+html;
      if(mismatch)text=message;
      hold=true; disabled=mismatch&&!flow.batchConfirmed;
    }
  } else if (["timing", "geo", "random", "saving", "burning", "erasing", "checking"].includes(phase)) {
    title = {erasing:liveText('正在擦除光盘','Erasing the disc'),timing:T().timing, geo:T().geo, random:T().generate, saving:liveText('正在保存预设', 'Saving preset'), burning:{verify:liveText('正在抽查回读','Checking the burn'), finish:liveText('正在封盘','Finishing the disc')}[burnPart()] ?? T().burning,
      checking:liveText('正在检查刻好的盘', 'Checking the burned disc')}[phase];
    // the core's stage words, in the page's language where they are known ("rung 4/22")
    const rung = /^rung (\d+)\/(\d+)$/.exec(flow.stage || "");
    // Only stages the page can say in its own language. The core's stage names ("imapi-4", "reading check points")
    // are for logs: untranslated, and meaningless to a person.
    const stage = rung ? liveText(`第 ${rung[1]} 处，共 ${rung[2]} 处。`, `Place ${rung[1]} of ${rung[2]}. `) : "";
    text = stage + (phase === 'erasing' ? liveText('可以关掉这个网页，擦除和之后的刻录在后台继续。', 'You can close this page; erasing and the burn after it go on.') : phase === 'burning' ? ({verify: liveText('从盘上抽样读回来，和镜像核对，大约一分钟。可以关掉这个网页。', 'Reading samples back from the disc to compare with the image; about a minute. You can close this page.'),
        finish: liveText('写完了。光驱正在封盘，之后自动抽查回读。可以关掉这个网页。', 'Written. The drive is finishing the disc; the read-back check follows on its own. You can close this page.')}[burnPart()]
        ?? liveText('大约 14 分钟。可以关掉这个网页，刻录在后台继续。', 'About 14 minutes. You can close this page; the burn keeps going.')) : liveText('可以关掉这个网页，测量在后台继续。', 'You can close this page; the work goes on.'));
    disabled = true;
    if (flow.job) {
      html += runningPaper(phase);                       // what is happening: only while it happens
      button = measuringButton(phase);
    }
  } else if (phase === "review") {
    title = liveText('测量结果', 'Measurement result');
    const part = flow.geo || flow.timing;
    text = api.lang() === 'zh' ? ({good:'测量可用', usable:'测量可用', narrow_span:'测量范围偏窄', too_noisy:'噪声太大', drive_changed:'光驱状态改变', stopped_early:'提前停止', unknown:'结果未知'}[part?.verdict] || '结果未知') : (part?.verdict || "unknown").replaceAll("_", " ");
    const recovery = recoveryAction(flow);
    const kind = recoveryKind(flow);
    if (kind === 'coverage') text = liveText('实测范围有空档', 'Measurement has gaps');
    if (kind === 'calibration_failed') text = liveText('标定未完成', 'Calibration incomplete');
    const severity = kind === 'good' ? 'good' : ['too_noisy','drive_changed','media'].includes(kind) ? 'error' : 'warn';
    // a stamp of equal weight whatever it says, then three lines: what it means, for the picture, what now
    const zh = api.lang() === "zh" ? 0 : 1;
    const STAMP = { good: ["可用", "Usable"], usable: ["可用", "Usable"], narrow_span: ["范围偏窄", "Narrow"], too_noisy: ["太吵", "Too noisy"],
      drive_changed: ["光驱变了", "Drive changed"], stopped_early: ["中途停了", "Stopped"], media: ["读不出", "Unreadable"], rotation: ["转速不稳", "Unsteady"],
      coverage: ["范围待补测", "Gaps in coverage"], calibration_failed: ["未完成", "Incomplete"], slow: ["读盘太慢", "Reading too slowly"],
      unknown: ["不知道", "Unknown"] }[kind] ?? ["不知道", "Unknown"];
    const FOR = { good: ["可以用来刻图。", "Good for a picture."], usable: ["可以刻图，边缘可能有小偏差。", "Good for a picture; the edges may be slightly off."],
      narrow_span: ["测到的范围以外可能偏。", "Outside the measured range it may be off."], stopped_early: ["只测到一部分，还不能用来刻图。", "Only part was measured; not for a picture yet."],
      media: ["这张盘不能用来测。", "This disc cannot be measured."] }[kind] ?? ["还不能用来刻图。", "Not for a picture yet."];
    html = `<div class="cal-stamp"><b>${STAMP[zh]}</b><dl>` +
      `<div><dt>${liveText("意思", "Means")}</dt><dd>${esc(measurementRecovery(flow)[api.lang()])}</dd></div>` +
      `<div><dt>${liveText("对你的图", "For the picture")}</dt><dd>${FOR[zh]}</dd></div>` +
      `<div><dt>${liveText("现在", "Now")}</dt><dd class="act">${esc(recovery.id === "save" ? (flow.detected.media === "dvd" ? liveText("保存测量，再刻检查盘", "Save, then burn the check disc") : T().save) : recovery.label[api.lang()])}</dd></div></dl></div>`;
    // the measurement disc's own read-back after it was burned here: a bad sample is said, never hidden
    const v = flow.burnCheck?.verification;
    if (v && v.status !== "skipped" && (v.status !== "completed" || v.differing || v.unreadable))
      html += note("warn", [liveText(`刻好的测量盘抽样回读：${v.unreadable} 块读不出、${v.differing} 块不对。测量结果照上面的判断用；若几何停在这些地方，换一张同批空白盘、换个速度再刻测量盘。`,
        `Read-back of the measurement disc burned here: ${v.unreadable} sampled blocks unreadable, ${v.differing} differing. Use the result as judged above; if measuring stops there, burn another measurement disc from this batch at another speed.`), ""]);
    const ok = recovery.id === 'save';
    const retryPart = ok ? (flow.timing?.measurement?.retry_kind === 'noisy' ? flow.timing : null) : part;
    if (retryPart) {
      if (ok) html += `<p>${liveText('这次测转速时读数有些乱。也可以换个速度重测。', 'The rotation readings were noisy. You can also try measuring at a different speed.')}</p>`;
      html += readRetryOptions(retryPart);
      if (!ok && kind !== 'coverage') html += `<p>${usbRetryWords()}</p>`;
      if (kind === 'media') html += checkMeasurementDisc();
      if (recovery.id === 'coverage' && part?.measurement?.retry_kind === 'rung') html += `<p>${liveText(
        '继续测时，请使用同一张盘、同一台光驱和原来的读取速度。换速度会重新检查转速并开始新一次测量。',
        'To continue, use the same disc, drive and read speed. Picking a different speed checks rotation and starts a new measurement.')}</p>`;
      html += diagnosticOptions();
    }
    if (flow.coverageNotice) html += `<div role="alert">${note("warn", [esc(flow.coverageNotice), ""])}</div>`;
    const skipped = flow.detected.media === "cd" && flow.photoSkipped;
    button = ok ? (skipped ? liveText('保存测量（不含照片修正）', 'Save without the photo correction')
      : flow.detected.media === "cd" ? liveText('查看 CD 标定下一步', 'CD calibration: next step') : returnTo || flow.detected.media === "dvd" ? liveText('保存测量', 'Save the measurement') : T().save) : recovery.label[api.lang()];
    if (ok && skipped) html += note("info", [liveText('这一轮跳过了拍照：保存的预设只有计时测得的几何，沿轨常数 L 未知，外圈可能偏。保存后可以导出给 DIS，或之后再拍照补上。',
      'You skipped the photo for this measurement: the saved preset has the timing geometry only, the along-track constant L is unknown and the outer rings may be off. After saving you can export it to DIS, or take the photo later.'), ""]);
    const details = ok
      ? liveText('想把这次测量用于同批光盘，点右下角继续。', 'To use this measurement for discs from the same batch, continue with the button at the bottom right.')
      : liveText(`要继续，点右下角的“${button}”。如果需要重测，先留着这张测量盘。`, `To continue, choose “${button}” at the bottom right. If you need to measure again, keep this measurement disc.`);
    const reason = ['media', 'slow'].includes(part?.measurement?.retry_kind) ? '' : kind === 'coverage' && flow.calibrationReason === 'the preset was not written'
      ? liveText('补齐空档后才能保存预设。', 'The preset can be saved once the gaps have been measured.')
      : flow.calibrationReason ? stopText(flow.calibrationReason) : '';
    const chart = calchart.resultChart(flow.geo?.measurement, { zh: api.lang() === "zh" });
    const commands = recoveryCommands(flow, {drive:api.selectedDrive(), media:flow.detected.media, sectors:flow.blankSectors ?? flow.detected.sectors});
    const advanced = liveText('只有在排查读盘问题、需要手动指定速度或测量区域，或比较不同测量结果时，才用这些终端命令。改速度时，把 SPEED 换成光驱支持的值（如 4x），先确认转速稳定再测几何。START-END 是要读的数据扇区范围。导出时指定半径只影响拟合，预设仍覆盖整张盘。', 'Use these terminal commands to troubleshoot reads, set a specific reading speed or area, or compare measurements. For a speed change, replace SPEED with a supported value such as 4x and check that rotation is steady before measuring geometry. START-END is the range of data sectors to read. Export radius options limit the fit. The preset still covers the whole disc.');
    html += `<details class="cal-details"><summary>${liveText('详情', 'Details')}</summary><p>${esc(details)}</p>` +
      (kind === 'coverage' ? `<p>${esc(measurementRecovery(flow)[api.lang()])}</p>` : "") +
      (reason ? `<p>${esc(reason)}</p>` : "") +
      (part?.measurement?.correction ? `<p>${liveText('这次带轨距修正：导出给 DIS 的预设未必能完全复现这条曲线，导出前先看转换误差；测量范围以外仍是外推。',
        'This measurement carries a pitch correction: a DIS preset may not reproduce the curve exactly, so check the conversion error before exporting. Outside the measured radii is extrapolation.')}</p>` : "") +
      (chart ? `<p>${liveText('下图显示光驱在盘面哪些位置检查过。', 'The chart shows where the drive checked the disc.')}</p>${chart}` : "") +
      (kind === 'usable' || recovery.id === 'coverage' ? `<button id="real-remeasure" class="placed" type="button">${liveText('检查转速并重测', 'Check rotation and remeasure')}</button>` : "") +
      (commands || part?.path ? `<details class="cal-advanced"><summary>${liveText('进阶', 'Advanced')}</summary>` +
        (commands ? `<p>${advanced}</p><pre>${esc(commands)}</pre>` : "") +
        (part?.path ? `<p><code>${esc(part.path)}</code></p>` : "") + `</details>` : "") + `</details>`;
    if (kind === 'narrow_span') html += `<button id="real-photo" class="placed" type="button">${liveText('拍一张照，补上外圈', 'Take a photo to fill in the outer rings')}</button>`;
    if (flow.photoResult) html += photoStamp(flow.photoResult);
    if (ok) html += `<label class="count-input">${liveText("这桶还剩几张空白盘（选填）", "Blank discs left in this spindle (optional)")}
      <input id="left-input" type="number" min="0" max="100000" step="1" aria-describedby="left-help" value="${flow.left ?? ""}"></label>
      <p id="left-help">${liveText("只用来在盘库里记个数。", "Only shown in the disc library.")}</p>`;
  } else if (phase === "saved") {
    title = liveText('预设已保存', 'Preset saved'); text = flow.savedPath;
    if (flow.detected.media === "cd" || flow.savedPhotoShift?.reason === "invalid_preset")
      html = `<p role="status">${esc(photoSaveWords(flow.savedPhotoShift)[api.lang()])}</p>`;
    if (flow.detected.media === "cd" && !flow.savedPhotoShift?.written) html += `<p>${esc(cdPhoto[api.lang()])}</p>`;
    if (flow.photoResult && !flow.savedPhotoShift?.origin?.startsWith('manual-')) html += photoStamp(flow.photoResult, flow.savedPhotoShift || {});
    const later = returnLabel?.() ?? (returnTo ? liveText('回到刚才那一步', 'Back to where you were') : liveText('回到大厅', 'Return to lobby'));
    button = later;
    if (checkDiscOffered()) {
      const mid = flow.detected?.mid || flow.savedBatch?.mid || "";
      html += `<p>${liveText('下一步刻一张检查盘（8 倍速约 7 分钟），用手机拍 3 张。程序从照片读出位置偏差，之后刻的图都会自动修正。',
        'Next, burn a check disc (about 7 minutes at 8×) and take 3 photos of it with your phone. The photos show how far positions are off, and every picture burned afterwards is corrected.')}</p>` +
        (/RITEKF1/i.test(mid) ? "" : `<p class="cal-aside">${liveText('检查盘的纹理是按 RITEKF1 挑的，这批盘还没试过，照片可能读不出来。', 'The check disc’s textures were chosen for RITEKF1; this batch is untried and the photos may not read.')}</p>`) +
        (flow.checkError ? note("error", [esc(flow.checkError), ""]) : '') +
        (flow.checkMaking ? '' : (hasCapability("photo-burn-recovery")
          ? `<button type="button" class="pc-text-button" id="cal-check-photo">${savedBurnWords.entry[api.lang()]}</button>` : '') +
          `<button type="button" class="pc-text-button" id="cal-check-later">${esc(liveText('先不刻，', 'Not now: ') + later)}</button>`);
      button = liveText('刻检查盘', 'Burn the check disc');
      if (flow.checkMaking) disabled = true;
    }
  }
  if (phase === 'starterCheck') {
    title = liveText('刻检查盘', 'Burn the check disc');
    text = liveText('这批盘还没确认。请刻一张检查盘，再用手机拍照。', 'This batch is unconfirmed. Burn a check disc and take photos with your phone.');
    button = liveText('刻检查盘', 'Burn the check disc');
    if (flow.checkError) html = note('error', [esc(flow.checkError), '']);
    disabled ||= !!flow.checkMaking;
  }
  if (["prepare", "burn"].includes(phase)) html = (flow.detected.rewritable
    ? `<p class="cal-aside">${liveText('可擦写盘可以重复使用。快速擦除约 1 分钟；完全擦除约为 1× 刻满一张盘的时间。擦除完成后才会开始重刻。','Rewritable discs can be reused. Quick erase takes about a minute; full erase takes about as long as filling a disc at 1x. Burning starts after erasing completes.')}</p>`
    : budgetHTML(flow.detected.media, api.lang())) + html;
  if (flow.ask) {
    html += `<p role="status">${esc(flow.ask.question)}</p><button id="real-yes">${liveText('继续', 'Continue')}</button><button id="real-no">${liveText('取消这一步', 'Decline')}</button>`;
    disabled = true;
  }
  if (flow.error) {
    if (!flow.job && ["timing", "geo", "random", "saving", "burning", "erasing", "checking"].includes(phase)) { title = liveText('这一步没有完成', 'This step did not finish'); text = ""; }
    const errorText=measurementGateText(flow.burnFailureGate,api.lang())||flow.error;
    html += `<div role="alert">${note("error", [esc(errorText), ""])}</div><button id="real-retry">${liveText('重新检测', 'Check again')}</button>`; disabled = true;
  }
  const badBurn = burnCheckFailed(flow.burnCheck);
  if (badBurn && !flow.job && !['inspect', 'prepare', 'random', 'burn'].includes(phase)) {
    title = liveText('刻录检查未通过', 'Burn check failed');
    text = flow.burnCheck.reason || liveText('请重新读取这张盘，查看保存的日志，再决定是否重刻。', 'Re-read this disc and inspect the saved logs before another burn.');
    html = `<button id="real-retry">${liveText('重新检测', 'Check again')}</button>`;
    disabled = true;
  }
  const burnStop=!flow.job && interruptedBurn(flow,api.lang());
  if(burnStop){
    title=liveText(flow.cancelledByUser?.phase==='burn'?'刻录已停止':'刻录没有完成',flow.cancelledByUser?.phase==='burn'?'Burn stopped':'Burn did not finish');
    text=measurementGateText(flow.burnFailureGate,api.lang())||burnStop;
    html=keepDiscForReview(flow.burnFailureGate) ? checkMeasurementDisc() : `<p>${liveText(
      '换盘或擦除后，可以从新盘支持的档位里选一个较低的刻录速度。测量盘可以用低速刻。',
      'After replacing or erasing the disc, choose a lower write speed from the speeds the drive reports. A measurement disc can be burned at low speed.')}</p>`;
    html += diagnosticOptions();
    button=keepDiscForReview(flow.burnFailureGate)?recheckText(api.lang())
      :flow.detected?.rewritable?liveText('擦除后重新刻','Erase and burn again'):liveText('换一张空白盘重新刻','Replace with a blank and burn again');
    disabled=false;
  } else if(phase==='discRejected'){
    title=liveText('这张盘不能用来测','This disc cannot be measured');text=flow.discIssue;html='';
    button=flow.detected?.rewritable?liveText('擦除后重新刻','Erase and burn again'):liveText('换一张空白盘重新刻','Replace with a blank and burn again');disabled=false;
  }
  if (!burnStop && badBurn && flow.iso && !flow.job && !['inspect', 'prepare', 'random', 'burn'].includes(phase))
    html += checkMeasurementDisc() + diagnosticOptions();
  if (!burnStop && !badBurn && flow.error && !flow.job && ['timing', 'geo'].includes(phase))
    html += retryButton('real-remeasure', liveText('检查转速并重测', 'Check rotation and remeasure')) + diagnosticOptions();
  if (flow.job && phase === 'burning' && flow.burnStarted && burnPart() === 'write')
    html += `<p>${liveText('进度很久不动，就点“停止刻录”，换一张盘用低一点的速度重刻。',
      'If progress stops moving for a long time, choose Stop burn and use a fresh disc at a lower speed.')}</p>`;
  paintRuler(); paintStage();
  sideButton(flow.job && ["burning", "checking", "timing", "geo"].includes(phase)
    ? returnTo ? liveText("先回大厅，测好了叫我", "Go to the lobby; call me when done")
      : liveText("先去放图，测好了叫我", "Place the picture; call me when done") : null);
  const previousAlert = $("cal").querySelector('.note[data-s="warn"], .note[data-s="error"]')?.textContent;
  // what is not known yet and what to do next, for the phase on screen (an error panel has its own words)
  const burnNotice=phase==='burn'&&!cdHere()&&(!flow.burnInspection||flow.burnInspection.gate||flow.burnInspection.error||flow.eraseRequested);
  const advice = flow.error || badBurn || burnNotice ? "" : adviceHTML(phase, api.lang(), { good: phase === "review" ? ["good", "usable"].includes(recoveryKind(flow)) : undefined, photoTaken: !!flow.photoOnly, cd: flow.detected?.media === "cd",
    external: phase === "burn" && cdHere() });
  $("cal").innerHTML = `<h2>${esc(title)}</h2><div class="cal-body"><p class="lede">${esc(text)}</p>${advice}${html}</div>`;
  if (phase === 'review' && flow.geo?.path && !badBurn) {
    const f = flow;
    curveEditor($("cal").querySelector(".cal-body"), {run:f.geo.path, lang:api.lang(), state:f.curveState ||= {},
      job:payload => api.backend.job(payload), onSaved:() => { f.preset = null; },
      onBusy:busy => { f.curvePending = busy; if (flow === f && f.realPhase === 'review') $("next").disabled = busy || disabled; }});
  }
  const alertNote = $("cal").querySelector('.note[data-s="warn"], .note[data-s="error"]');
  if (alertNote && alertNote.textContent !== previousAlert) alertNote.classList.add('flash');
  flow.warnEl.classList.toggle('on', !!flow.error || (phase === 'review' && recoveryKind(flow) !== 'good'));
  // while a job runs, its step's name lies on the floor in front of the drive (floor-log.js)
  flog.title(flow.job ? title : "");
  $("cal").classList.toggle("floor-titled", !!flow.job && !st);     // with the stage, the title stays on the paper
  // The burn step requires the kit slider; all other steps use Next.
  disabled ||= !!flow.curvePending;
  if(flow.job){
    flow.job.nextLabel = disabled && !flow.ask && !flow.error && !badBurn ? button : null;
  }
  nextWords(button, flow.job?.nextLabel ? flow.job.left : "");
  $("next").disabled = disabled; nextKit(hold, disabled, phase === "random" && !!flow.job);
  // why it is grey, beside it: running, waiting for an answer, a problem to put right, a box to tick
  api.nextWhy?.(flow.error ? liveText('先处理上面的问题', 'Put the problem above right first')
    : flow.ask ? liveText('先回答上面的问题', 'Answer the question above first')
    : flow.job ? liveText('在测，做完会自己接上；可以关掉网页', 'Working; it goes on by itself, even with the page closed')
    : phase === "prepare" && flow.detected?.blank === false && !flow.measureConfirmed ? liveText('先勾选上面：这是测量盘', 'Tick the box above first: this is the measurement disc')
    : "");

  $("real-erase")?.addEventListener('click',()=>{flow.eraseRequested=true;flow.measureConfirmed=false;realNext();});
  $("real-burn-erase")?.addEventListener('click',()=>{flow.eraseRequested=true;refreshBurnInspection();});
  $("real-burn-recheck")?.addEventListener('click',()=>{flow.eraseRequested=false;refreshBurnInspection();});
  $("real-burn-speed")?.addEventListener('change', e => { flow.burnSpeed = Number(e.target.value) || undefined; });
  $("measurement-batch-confirm")?.addEventListener('change',e=>{
    flow.batchConfirmed=e.target.checked;paint();$("measurement-batch-confirm")?.focus();
  });
  $("real-name")?.addEventListener("input", e => {flow.realName = e.target.value;});
  for (const radio of document.querySelectorAll('#starter-choice input')) radio.addEventListener('change', () => {
    flow.starterChoice = radio.value; paint();
    document.querySelector(`#starter-choice input[value="${CSS.escape(radio.value)}"]`)?.focus(); });
  $("measurement-confirm")?.addEventListener("change", e => {
    flow.measureConfirmed = e.target.checked; paint(); $("measurement-confirm").focus();
  });
  $("real-capacity-check")?.addEventListener("click", () => { flow.error = null; flow.realPhase = "capacityBlank"; paint(); });
  $("real-capacity")?.addEventListener("input", e => {
    flow.manualSectors = e.target.value;
    $("next").disabled = !!flow.error || !manualCapacity(flow.manualSectors);
  });
  $("left-input")?.addEventListener("input", e => { flow.left = e.target.value === "" ? null : Number(e.target.value); });
  $("real-retry")?.addEventListener("click", () => {
    flow.error = null;
    if (badBurn && flow.iso) {
      flow.burnRetry = true;
      flow.burnSpeed = undefined;
      flow.burnInspection = null;
    }
    if(phase==='burn'&&!cdHere()){flow.eraseRequested=false;refreshBurnInspection();return;}
    if (phase !== "review" && !CAPACITY_PHASES.includes(phase)) flow.realPhase = "inspect";
    paint();
  });
  for (const [id, yes] of [["real-yes",true],["real-no",false]]) $(id)?.addEventListener("click", async () => {
    try { const ask = flow.ask; await api.backend.answer(ask.job, ask.id, yes); flow.ask = null; paint(); } catch(e) {realError(e);}
  });
  $("cal-check-later")?.addEventListener("click", () => savedDone());
  $("cal-check-photo")?.addEventListener("click", () => {
    const from = flow, opener = returnTo;
    photographSaved(api, {item:from.item, geo:from.geo.path, returnTo:() => {
      flow = from; returnTo = opener; open();
    }});
  });
  $("real-remeasure")?.addEventListener("click", () => retryMeasurement());
  $("real-suggested-speed")?.addEventListener("click", e => retryMeasurement(e.target.dataset.speed));
  $("real-lower-read")?.addEventListener("click", () => retryMeasurement($("real-lower-read-speed").value));
  $("real-copy-diagnostics")?.addEventListener("click", async e => {
    try { await navigator.clipboard.writeText(diagnosticWords()); e.target.textContent = liveText('已复制', 'Copied'); }
    catch { e.target.textContent = liveText('请选择上面的文字复制', 'Select the text above to copy it'); }
  });
  $("real-download-diagnostics")?.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([diagnosticWords()], {type:'text/plain;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url; link.download = 'disc-probe-diagnostics.txt'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $("real-photo")?.addEventListener("click", enterPhoto);
  $("real-have")?.addEventListener("click", () => { flow.realPhase = "inspect"; realNext(); });
  $("real-copy")?.addEventListener("click", async (e) => {
    try { await navigator.clipboard.writeText(flow.cdCommand); e.target.textContent = liveText('已复制', 'Copied'); }
    catch { e.target.textContent = liveText('复制不了，请选中命令复制', 'Select the command to copy it'); }
  });

}
// ---------------------------------------------------------------- photos, scoped to this geometry run
let photoUI = null;
const photoRun = f => String(f.geo?.path || '').replace(/\\/g, '/').replace(/\/$/, '').split('/').pop() || null;
const burnWords = key => savedBurnWords[key][api.lang()];
const photoQuery = u => 'run=' + encodeURIComponent(u.run) +
  (u.flow.savedBurn?.record ? '&burn_record=' + encodeURIComponent(u.flow.savedBurn.record.id) : '');
const photoUnavailable = error => error?.status === 404;

function burnLabel(record, withPath = false) {
  const time = new Date(record.time * 1000).toLocaleString(api.lang() === 'zh' ? 'zh-CN' : 'en', {
    year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit',
  });
  const details = withPath ? [record.burner, record.path, record.mode] : [];
  return [time, record.disc_id || burnWords('missing'), ...details].join(' · ');
}

function paintSavedBurn() {
  closePhoto(); st?.show(false); loadDisc.desk(false); sideButton(null);
  nextKit(false, false);
  $('next').disabled = true;
  $('next-text').textContent = burnWords('confirm');
  api.nextWhy?.('');
  const f = flow, saved = f.savedBurn, esc = api.backend.escapeHTML;
  const paper = $('cal');
  paper.innerHTML = `<h2>${burnWords('title')}</h2>`;
  const status = text => { const node = document.createElement('p'); node.setAttribute('role','status'); node.textContent = text; paper.append(node); };
  const action = (key, fn) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'placed'; button.id = 'photo-burn-' + key;
    button.textContent = burnWords(key); button.onclick = fn; paper.append(button); return button;
  };
  if (!saved.listing) {
    if (saved.error) {
      status(api.backend.errorText(saved.error,api.lang()));
      action('retry', () => { saved.error = null; paint(); });
      return;
    }
    status(burnWords('loading'));
    if (!saved.loading) {
      saved.loading = api.backend.request(`/api/photo-burns?run=${encodeURIComponent(photoRun(f))}`).then(listing => {
        saved.listing = listing;
        saved.record = listing.burns.find(row => row.id === saved.id) || null;
        if (!saved.record) {
          saved.confirmed = false;
          saved.record = listing.burns.length === 1 ? listing.burns[0] : null;
          f.photoDiscId = undefined;
        }
        saved.id = saved.record?.id ?? null;
        f.photoDiscId ??= saved.record?.disc_id ?? '';
      }).catch(error => { saved.error = error; }).finally(() => {
        saved.loading = null;
        if (flow === f && isCal()) paint();
      });
    }
    return;
  }
  const burns = saved.listing.burns;
  if (!burns.length) {
    const unavailable = saved.listing.unavailable;
    status(burnWords(unavailable.includes('legacy_burn') ? 'legacy' : unavailable.includes('unknown_burn') ? 'unknown' : 'empty'));
    if (f.checkError) status(f.checkError);
    action('again', () => {
      if (!saved.burnAgain) { burnCheckDisc(); return; }
      returnTo = returnAnim = returnLabel = null;
      flow = null; release(); saved.burnAgain();
    }).disabled = !!f.checkMaking;
    return;
  }
  status(burnWords('choose'));
  // One card per burn, newest first, like the measuring-disc choice: the time is what people remember,
  // the number is what is written on the disc. A single burn comes already chosen.
  const when = (row) => new Date(row.time * 1000).toLocaleString(api.lang() === 'zh' ? 'zh-CN' : 'en', {
    month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
  paper.insertAdjacentHTML('beforeend', `<div class="choices" id="photo-burns" role="radiogroup" aria-label="${esc(burnWords('select'))}">${
    burns.map(row => `<label class="choice"><input type="radio" name="photo-burn" value="${esc(row.id)}"${saved.id === row.id ? ' checked' : ''}>
      <b>${esc(when(row))}</b><span>${esc(`${burnWords('number')} ${row.disc_id || burnWords('missing')}${row.burner ? ` · ${row.burner}` : ''}`)}</span></label>`).join('')}</div>`);
  for (const radio of document.querySelectorAll('#photo-burns input')) radio.onchange = () => {
    saved.record = burns.find(row => row.id === radio.value) || null;
    saved.id = saved.record?.id ?? null;
    f.photoDiscId = saved.record?.disc_id ?? '';
    paint(); document.querySelector(`#photo-burns input[value="${CSS.escape(radio.value)}"]`)?.focus();
  };
  if (!saved.record) return;
  paper.insertAdjacentHTML('beforeend', `<label class="pc-disc-id"><span>${burnWords('number')}</span>
    <input id="photo-burn-number" maxlength="40" autocomplete="off" spellcheck="false">
    <small>${burnWords('numberHint')}</small></label>`);
  const input = $('photo-burn-number');
  input.value = f.photoDiscId || '';
  const numberInput = () => { f.photoDiscId = input.value; $('next').disabled = !input.value.trim(); };
  input.oninput = numberInput;
  numberInput();
}
function enterPhoto() {
  if (flow.job) return;
  flow.error = null; flow.realPhase = 'photo'; paint();
}
function closePhoto() {
  if (!photoUI) return;
  const u = photoUI; photoUI = null;
  clearTimeout(u.timer);
  clearTimeout(u.readTimer);
  if (u.page) u.flow.photoSnapshot = u.page.state();
  u.page?.destroy(); u.host.remove();
  document.documentElement.classList.remove('cal-photo');
}
function photoReview() {
  if (flow.starterCheck) { backToMeasurement(flow, 'photo_not_confirmed', returnTo); return; }
  if (flow.photoOnly) { closePhoto(); flow.error = null; leave(); return; }   // came from the burn page: back there
  closePhoto(); flow.realPhase = 'review'; flow.error = null; paint();
}

function backToMeasurement(previous, reason, opener) {
  closePhoto();
  returnTo = opener;
  flow = newFlow(previous.item);
  flow.realPhase = 'inspect';
  flow.starterDeclined = true;
  const detail = ({
    shape_not_1_over_r: liveText('不同半径的偏差无法用一个沿轨常数校正。', 'The ring bands do not support a single along-track correction.'),
    large_residual: liveText('检查盘图案偏差太大。', 'The check disc pattern is too far from the expected positions.'),
    check_not_completed: liveText('检查盘未完成刻录和回读。', 'The check disc burn and read-back did not complete.'),
    no_rim: liveText('照片里没找到盘边。', 'The disc edge was missing from the photos.'),
    photos_disagree: liveText('照片读出的偏移互相对不上。', 'The photos gave conflicting offsets.'),
    ambiguous_majority: liveText('照片分成两组互相冲突的读数。', 'The readings split into two conflicting groups.'),
    invalid_starter_photo_evidence: liveText('照片来源与检查盘记录无法核对。', 'The photo evidence could not be matched to the check disc.'),
  })[reason] || liveText('照片未通过检查。', 'The photos did not pass the check.');
  flow.starterFailure = `${detail} ${liveText('请换一张同批空白盘，回到测量盘流程。', 'Insert a blank from this batch and return to the measurement-disc flow.')}`;
  return open();
}
// "Skip, use the current results": remembered for this measurement, so the review's next step saves without the
// photo's correction instead of sending the person back to the photo page (CD went round in that circle).
function photoSkip() {
  if (!flow.photoOnly) flow.photoSkipped = true;
  photoReview();
}
const photoLive = u => photoUI === u && flow === u.flow && isCal() && flow.realPhase === 'photo';
// The along-track constant's state for this read: the core's own decision when it gives one, else the group vote.
const photoAdoption = result => result?.adoption?.state ? result.adoption
  : result?.verdict === 'ok' ? {state:'adopted'} : {state:'none'};
const PHOTO_HELD = ['provisional','disagree','split','refused'];
function photoStamp(result, saved = null) {
  const esc = api.backend.escapeHTML, adoption = photoAdoption(result);
  // Only an adopted group is usable: a provisional single photo, a disagreement or a refusal never is.
  const ok = result.verdict === 'ok' && !PHOTO_HELD.includes(adoption.state);
  const held = PHOTO_HELD.includes(adoption.state) ? adoptionWords(adoption) : null;
  // Whether pictures will use it is the core's further gate (disc number, burn path, same drive and run).
  const applied = ok && result.application ? applicationWords(result.application, flow?.detected?.media) : null;
  // Adopted by a majority: say how many agreed, and which photos were left out as outliers (never on a tie).
  const majority = ok && adoption.source === 'core' ? adoptionWords(adoption, result.per_photo || []) : null;
  // One line per kind of problem, with how many photos it applies to; the same advice is not repeated.
  const kinds = new Map();
  for (const p of result.per_photo || []) if (p.verdict !== 'ok') { const w = photoReasonWords(p)[api.lang()]; if (w) kinds.set(w, (kinds.get(w) || 0) + 1); }
  const reasons = [...kinds].map(([w, n]) => (n > 1 ? liveText(`${n} 张 · `, `${n} photos · `) : '') + w).join('\n');
  const value = Number.isFinite(result.L_frames) ? `L = ${result.L_frames} frames` : '';
  const row = (zh, en, text, act = false) => `<div><dt>${liveText(zh,en)}</dt><dd${act ? ' class="act"' : ''}>${esc(text)}</dd></div>`;
  const head = held ? held.title[api.lang()] : ok ? liveText('已采用','Adopted') : result.verdict === 'rejected' ? liveText('照片读不出','Photo unreadable') : adoptionWords(adoption, result.per_photo || []).title[api.lang()];
  return `<div class="cal-stamp" role="status" data-adoption="${esc(adoption.state)}"><b>${esc(head)}</b><dl>` +
    row('意思','Means', reasons || (ok ? liveText('照片读完了。','Photo read.') : liveText('照片还不能给出可信的结果。','The photo cannot give a trusted result yet.'))) +
    row('对你的图','For the picture', ok ? liveText('已保留照片结果；现有几何的覆盖限制仍按测量结果判断。','Photo result retained; the measured geometry still determines its coverage limits.') : liveText('保留现有测量，不用这次照片改它。','Keep the existing measurement; this photo does not change it.')) +
    (held ? row('沿轨常数','Along-track constant', held.body[api.lang()], true) : '') +
    (majority ? row('沿轨常数','Along-track constant', majority.body[api.lang()], !!adoption.outliers?.length) : '') +
    (applied ? row('出图','Pictures', applied.words[api.lang()], !applied.applied) : '') +
    row('现在','Now', saved ? photoSaveWords(saved)[api.lang()] : ok ? (value ? `${value} · ${liveText('已保留，尚未写入预设','retained, not yet written into the preset')}` : liveText('保存现有测量和照片结果。','Save the existing measurement and retain the photo result.')) : liveText('再拍一张，或跳过，就用现在的结果。','Take another photo, or skip and keep the current result.'), !ok) + '</dl></div>';
}
function photoNavigation(u) {
  if (!photoLive(u)) return;
  const unavailable = u.status === 'unavailable', cd = flow.detected.media === 'cd';
  nextKit(false, false);
  if (u.manual) {
    $('next-text').textContent = sliderWords.save[api.lang()];
    $('next').disabled = !u.canUse || !!flow.job || !!u.reading;
    api.nextWhy?.(u.reading ? liveText('正在读取照片…','Reading photos…') : '');
    return;
  }
  $('next-text').textContent = unavailable ? (cd ? liveText('导出 DIS 预设','Export DIS preset') : liveText('返回测量结果','Back to measurement result')) : liveText('采用结果','Use the result');
  const usable = u.flow.photoResult?.verdict === 'ok' && !PHOTO_HELD.includes(photoAdoption(u.flow.photoResult).state);
  $('next').disabled = !!flow.job || !!u.reading || !!u.readTimer || (!unavailable && (u.status !== 'ready' || !usable));
  api.nextWhy?.(unavailable ? '' : flow.job || u.reading ? liveText('正在读取照片…','Reading photos…') : u.status === 'loading' ? liveText('正在连接照片服务…','Connecting to the photo service…') : !usable ? (g => liveText(`还差 ${g.left} 张`, `${g.left} more needed`))(photoProgress(u)) : '');
}
function photoFallback(u, error) {
  if (!photoLive(u)) return;
  u.status = 'unavailable'; clearTimeout(u.timer); clearTimeout(u.readTimer); u.readTimer = null;
  if (u.page) u.flow.photoSnapshot = u.page.state();
  u.page?.destroy(); u.page = null; u.host.replaceChildren();
  const esc = api.backend.escapeHTML;
  $('cal').innerHTML = `<h2>${liveText('照片暂不可用','Photos not available')}</h2><p role="status">${esc(error ? api.backend.errorText(error,api.lang()) : liveText('照片服务暂不可用；可以返回测量结果。','The photo service is not available; you can return to the measurement result.'))}</p>` +
    (flow.detected.media === 'cd' ? `<h2>${liveText('CD：接着在 DIS 标定','CD: continue calibration in DIS')}</h2><p>${esc(cdPhoto[api.lang()])}</p>` : '') +
    `<button id="photo-back" class="placed" type="button">${liveText('返回测量结果','Back to measurement result')}</button>`;
  $('photo-back').onclick = photoReview;
  photoNavigation(u);
}
async function pollPhotos(u) {
  if (!photoLive(u) || u.status !== 'ready') return;
  try {
    const result = await api.backend.request(`/api/photos?${photoQuery(u)}`);
    if (!photoLive(u)) return;
    const fresh = (result.photos || []).filter(p => !u.seen.has(p.id));
    for (const p of result.photos || []) u.rows.set(p.id,p);
    for (const p of fresh) u.seen.add(p.id);
    await u.page.addPhotos(fresh, {preserveSelection:true});
    if (!photoLive(u)) return;
    u.listing = result; u.page.setListing?.(result); paintReadState(u);
    u.page.setReasons(u.flow.photoResult?.per_photo || []);
    if (fresh.length) queuePhotoRead(u);
    u.notice.textContent = u.flow.photoNotice || '';
    await pollDevices(u);
  } catch (error) {
    if (!photoLive(u)) return;
    if (photoUnavailable(error)) { photoFallback(u); return; }
    u.notice.textContent = api.backend.errorText(error,api.lang());
  }
  if (photoLive(u) && u.status === 'ready') u.timer = setTimeout(() => pollPhotos(u), 2000);
}
// What the computer is doing with the photos, with real times: received, reading (so far), read (how long).
// It is said as what happened after they arrived, never as a judgement made while shooting.
function paintReadState(u) {
  if (!photoLive(u) || !u.readState) return;
  const l = u.listing || {}, photos = l.photos || [], a = l.analysis, n = photos.length;
  let text = '';
  if (a?.state === 'reading') {
    const s = photoSeconds(a.seconds);
    text = liveText(`收到 ${n} 张。正在读其中 ${a.photos.length} 张，已 ${s.zh}。`, `${n} received. Reading ${a.photos.length} of them: ${s.en} so far.`);
  } else if (photos.some(p => !p.verdict)) {
    text = liveText(`收到 ${n} 张，${photos.filter(p => !p.verdict).length} 张等待读取。`, `${n} received, ${photos.filter(p => !p.verdict).length} waiting to be read.`);
  } else if (a && Number.isFinite(a.seconds)) {
    const s = photoSeconds(a.seconds);
    text = liveText(`收到 ${n} 张。上次读取 ${a.photos.length} 张用了 ${s.zh}。`, `${n} received. The last read of ${a.photos.length} took ${s.en}.`);
  } else if (n) text = liveText(`收到 ${n} 张。`, `${n} received.`);
  u.readState.textContent = text;
  paintStatus(u);
}
// Where the photo step stands, as the page's one headline: how many usable photos of how many needed, and one
// piece of advice from the latest photo that needs retaking. Everything else on the paper is secondary.
function photoProgress(u) {
  const l = u.listing || {}, photos = l.photos || [], result = u.flow.photoResult || u.shownResult;
  const adoption = result ? photoAdoption(result) : {state:'none'};
  const per = result?.per_photo?.length ? result.per_photo : photos.filter(p => p.verdict);
  const usable = per.filter(p => p.verdict === 'ok').length;
  const need = Number.isFinite(adoption.required_count) ? adoption.required_count : 2;
  const adopted = result?.verdict === 'ok' && !PHOTO_HELD.includes(adoption.state);
  const reading = !!u.reading || l.analysis?.state === 'reading' || photos.some(p => !p.verdict);
  // photos the page holds, the listing knows or the last read covered: whichever saw most
  const count = Math.max(photos.length, result?.per_photo?.length || 0, u.page?.state?.().photos?.length || 0);
  return {photos, count, per, usable, need, adopted, reading, adoption, left: Math.max(1, need - usable)};
}
function paintReadProgress(u) {
  const part = u.statusParts, a = u.listing?.analysis;
  if (!part?.read) return;
  if (a?.state === 'done' && a.photos?.length && Number.isFinite(a.seconds)) u.perPhotoSeconds = a.seconds / a.photos.length;
  const reading = a?.state === 'reading' && a.photos?.length;
  part.read.hidden = !reading;
  if (!reading) { u.readBarKey = null; return; }
  const n = a.photos.length, done = Math.min(n - 1, Math.max(0, Math.round((Number(a.fraction) || 0) * n)));
  const elapsed = Number(a.seconds) || 0, est = done > 0 ? elapsed / done : (u.perPhotoSeconds || 30);
  // aim at where the read should be at the next poll (2 s), so the 2 s transition keeps it moving
  const within = Math.min(0.95, Math.max(0, (elapsed + 2 - done * est) / est));
  const fraction = Math.min(1, (done + within) / n);
  if (u.readBarKey !== a.job) { u.readBarKey = a.job; part.readBar.style.transition = 'none'; part.readBar.style.width = '0%'; void part.readBar.offsetWidth; }
  part.readBar.style.transition = ''; part.readBar.style.width = `${(fraction * 100).toFixed(1)}%`;
  part.readText.textContent = liveText(`正在读第 ${done + 1} / ${n} 张`, `Reading photo ${done + 1} of ${n}`);
}
function paintStatus(u) {
  if (!photoLive(u) || !u.statusParts) return;
  const g = photoProgress(u), lang = api.lang();
  let head, tip = '';
  if (!g.count) { head = liveText('等第一张照片', 'Waiting for the first photo'); tip = liveText('用手机扫下面的码拍，拍完会自动传到这里。', 'Scan the code below with your phone; photos arrive here by themselves.'); }
  else if (g.adopted) { head = liveText('可以采用了', 'Ready to use'); tip = liveText(`${g.usable} 张照片读数一致。`, `${g.usable} photos agree.`); }
  else if (['disagree', 'split'].includes(g.adoption.state)) { head = liveText('读数对不上', 'The readings disagree'); tip = liveText('再拍一张不同角度的，看它和哪张一致。', 'Take another from a different angle to see which one it agrees with.'); }
  else if (g.reading && !g.usable) head = liveText('正在读照片…', 'Reading photos…');
  else head = liveText(`还差 ${g.left} 张`, `${g.left} more photo${g.left > 1 ? 's' : ''} needed`);
  if (!tip && g.count && !g.adopted) {
    const last = [...g.per].reverse().find(p => p.verdict && p.verdict !== 'ok');
    tip = last ? reasonOf(last).why[lang] : liveText('转一下盘，再拍一张不同角度的。', 'Turn the disc and take another from a different angle.');
  }
  const box = u.statusBox, part = u.statusParts; if (box.dataset) box.dataset.state = g.adopted ? 'ok' : g.count ? 'open' : 'empty';
  part.head.textContent = head;
  part.dots.replaceChildren?.();
  for (let i = 0; i < g.need; i++) { const d = document.createElement('i'); if (d.dataset) d.dataset.on = String(i < g.usable); part.dots.append(d); }
  part.label.textContent = g.count ? liveText(`可用 ${Math.min(g.usable, g.need)} / 需要 ${g.need}`, `${Math.min(g.usable, g.need)} of ${g.need} usable`) : '';
  part.tip.textContent = tip;
  paintReadProgress(u);
}
async function phoneLink(u, address) {
  if (address === undefined) { try { address = sessionStorage.getItem('discprobe-phone-address'); } catch { /* storage unavailable */ } }
  const base = `/api/phone-link?${photoQuery(u)}`;
  try { return await api.backend.request(base + (address ? '&address=' + encodeURIComponent(address) : '')); }
  catch (error) { if (address && error.status === 400) return api.backend.request(base); throw error; }
}
async function choosePhoneAddress(u, address) {
  const link = await phoneLink(u,address);
  if (!photoLive(u)) return;
  try { sessionStorage.setItem('discprobe-phone-address',address); } catch { /* storage unavailable */ }
  u.page.setPhoneLink(link); await pollDevices(u);
}
async function pollDevices(u) {
  if (!photoLive(u) || u.devicesUnavailable) return;
  try {
    const result = await api.backend.request(`/api/phone-devices?${photoQuery(u)}`);
    if (!photoLive(u)) return;
    const rows = Array.isArray(result.devices) ? result.devices : [];
    u.page.setDevices?.([
      {id:'this-computer', name:liveText('这台电脑','This computer'), kind:'computer', thisDevice:true},
      ...rows.map(d => ({...d, since:d.first_seen, sent:d.photos_sent})),
    ]);
  } catch (error) {
    if (!photoLive(u)) return;
    if (photoUnavailable(error)) { u.devicesUnavailable = true; u.page.setDevices?.(null); }
    else u.notice.textContent = api.backend.errorText(error,api.lang());
  }
}
async function disconnectPhone(u, id) {
  if (!photoLive(u)) return;
  try {
    await api.backend.request(`/api/phone-devices/${encodeURIComponent(id)}/disconnect`, {});
  } catch (error) {
    if (photoUnavailable(error)) { u.devicesUnavailable = true; u.page.setDevices?.(null); return; }
    throw error;
  }
  // Rotation revokes every device using the old run token. Refresh the QR before reconnecting.
  u.page.setDevices?.(null);
  try {
    const link = await phoneLink(u);
    if (!photoLive(u)) return;
    u.page.setPhoneLink?.(link);
    u.notice.textContent = liveText('旧链接已失效。其他手机也需重新扫码。','The old link has expired. Other phones must scan again too.');
    await pollDevices(u);
  } catch (error) {
    if (!photoLive(u)) return;
    u.page.setPhoneLink?.({url:null,qr_svg:null});
    u.notice.textContent = api.backend.errorText(error,api.lang());
  }
}
function showPhotoResult(u, result) {
  if (!photoLive(u)) return;
  u.page.setReasons(result.per_photo || []);
  u.page.setReadResult?.(result);
  u.result.innerHTML = photoStamp(result); u.result.hidden = false;
  u.retry.hidden = u.skip.hidden = result.verdict === 'ok';
  u.shownResult = result; paintStatus(u);
}
function queuePhotoRead(u) {
  if (!photoLive(u) || u.status !== 'ready') return;
  clearTimeout(u.readTimer);
  u.readTimer = setTimeout(() => {
    u.readTimer = null;
    if (u.reading) { u.readAgain = true; return; }
    readPhoto(u);
  }, 1500);
  photoNavigation(u);
}
function photoBurnArgs(f) {
  if (f.starterCheck) return {};  // The core retrieves the path from the verified burn receipt.
  const burn = f.burnCheck;
  const saved = f.savedBurn?.record?.id;
  const edited = burn?.burn_record && f.photoDiscId && f.photoDiscId !== burn.disc_id;
  if (saved || edited) return {burn_record:saved || burn.burn_record};
  // A displayed external command cannot prove how, or where, a disc was burned.
  return {burner:burn?.result === 'completed' ? burn.burner || null : null,
    burn_path:burn?.result === 'completed' ? burn.burn_path || null : null,
    burn_mode:burn?.result === 'completed' ? burn.burn_mode || null : null};
}
async function usePhotoResult(u, photo = null) {
  const result = await readPhoto(u,photo);
  if (u.flow.starterCheck && photoLive(u)) {
    if (!result?.starter?.written) { backToMeasurement(u.flow, result?.starter?.reason, returnTo); return; }
    const check = u.flow.starterCheck;
    const batch = { id: `starter:${u.run}`, geo: check.path, starter: true, row: 'dvd', s: 'good', mid: check.mid,
      name: check.name, checked_mm:check.checked_mm, capacity_sectors:check.capacity_sectors };
    const opener = returnTo;
    closePhoto(); returnTo = null; flow = null; release();
    if (opener) await opener({done:true, id:batch.id, batch}); else api.toLobby?.();
    return;
  }
  if (result?.verdict !== 'ok' || !photoLive(u)) return;
  await savePhotoPreset(u);
}
async function savePhotoPreset(u) {
  try { await realSave(); if (isCal()) paint(); }
  catch (error) { if (isCal() && flow === u.flow) { u.flow.photoNotice = api.backend.errorText(error,api.lang()); u.flow.realPhase = 'photo'; paint(); if (photoUI?.notice) photoUI.notice.textContent = u.flow.photoNotice; } }
}
async function readPhoto(u, photo = null, rings = null) {
  const f = u.flow;
  if (!photoLive(u) || u.status !== 'ready' || !u.page) return null;
  if (u.manualSaving) return null;
  if (f.savedBurn && !photoDiscId(f, u.run)) { u.notice.textContent = burnWords('numberHint'); return null; }
  if (u.reading || f.job) { u.readAgain = true; return null; }
  clearTimeout(u.readTimer); u.readTimer = null; u.reading = true;
  f.photoNotice = null; u.notice.textContent = '';
  try {
    const candidates = [...(u.page.state().photos || [])];
    if (photo && !candidates.some(p => p.id && p.id === photo.id || p.file && p.file === photo.file)) candidates.push(photo);
    for (const photo of candidates) {
      let id = photo.id;
      if (!id && photo.file) {
        f.photoUploads ??= new Map(); id = f.photoUploads.get(photo.file);
        if (!id) {
          const token = new URLSearchParams(location.search).get('token');
          const response = await fetch(`/api/photos?${photoQuery(u)}`, {method:'POST', headers:{'Content-Type':photo.file.type || 'image/jpeg', 'X-Filename':encodeURIComponent(photo.name), ...(token ? {'X-Discprobe-Token':token} : {})}, body:photo.file});
          if (response.status === 409) throw new Error(liveText('这张照片已经加过了。转一下盘，拍一张新的。','This photo was already added. Turn the disc and take a new one.'));
          if (!response.ok) throw Object.assign(new Error(response.statusText),{status:response.status});
          const uploaded = await response.json(); id = uploaded.id;
          f.photoUploads.set(photo.file,id); u.seen.add(id);
        }
      }
      if (!photoLive(u)) return null;
      if (!id) throw new Error(liveText('这张照片还没上传。请重新加入照片。','This photo has not uploaded. Add it again.'));
      u.page.setPhotoId(photo,id); u.rows.set(id,{id});
    }
    const ids = [...u.rows.keys()].sort();
    if (!ids.length) return null;
    const disc = photoDiscId(f, u.run);
    const key = JSON.stringify([ids,rings,disc]), readIds = JSON.stringify([ids,disc]);
    if ((f.photoReadKey === key || rings === null && f.photoReadIds === readIds) && f.photoResult) { showPhotoResult(u,f.photoResult); return f.photoResult; }
    // Another page (or an earlier visit) is reading this run now: wait for it instead of a second read.
    if (u.listing?.analysis?.state === 'reading') { u.readAgain = true; await new Promise(r => setTimeout(r, 3000)); return null; }
    // ...and when that read covered exactly these photos, it is this read.
    const earlier = rings === null && readFromListing(u.listing, ids);
    if (earlier) { f.photoResult = earlier; f.photoReadKey = key; f.photoReadIds = readIds; showPhotoResult(u,earlier); return earlier; }
    let result;
    try { result = await realJob('photo', {run:u.run, media:f.detected.media, photos:ids, rings_mm:rings, ...photoBurnArgs(f), ...(disc ? {disc_id:disc} : {})}); }
    catch (error) { if (!error.result?.verdict) throw error; result = error.result; }
    if (!['ok','unsure','rejected'].includes(result?.verdict)) throw new Error(liveText('照片服务没有返回判断。','The photo service returned no verdict.'));
    if (disc !== photoDiscId(f, u.run)) { u.readAgain = true; return null; }
    // A job may finish after Back. Keep its evidence with its own flow, but never navigate that page.
    f.photoResult = result; f.photoReadKey = key; f.photoReadIds = readIds;
    if (f.starterCheck && photoLive(u) && !result?.starter?.written &&
        (ids.length >= 3 || ['large_residual', 'shape_not_1_over_r'].includes(result?.starter?.reason))) {
      backToMeasurement(f, result?.starter?.reason, returnTo);
      return result;
    }
    showPhotoResult(u,result);
    return result;
  } catch (error) {
    if (photoLive(u)) {
      if (photoUnavailable(error)) photoFallback(u);
      // Kept in the flow: the 2-second poll repaints the notice from it, and must not wipe a read's failure.
      else u.notice.textContent = f.photoNotice = api.backend.errorText(error,api.lang());
    }
    return null;
  } finally {
    u.reading = false;
    if (photoLive(u)) { if (u.readAgain) { u.readAgain = false; queuePhotoRead(u); } photoNavigation(u); }
    if (flow === f && isCal() && f.realPhase === 'review') paint();
  }
}
// The run's last read, as the listing reports it, when it covered exactly `ids`; else null.
// It has the verdict, per-photo statuses and the L state; the value itself stays in the run's photo.json.
function readFromListing(list, ids) {
  const read = list?.read_photos || [];
  if (!list?.verdict || !ids.length || read.length !== ids.length || !ids.every(id => read.includes(id))) return null;
  // A read made under another disc number is not this read.
  if ((list.disc_id || '') !== (photoDiscId(flow, photoUI?.run) || '')) return null;
  return {verdict:list.verdict, per_photo:(list.photos || []).filter(p => ids.includes(p.id)).map(p => ({id:p.id, verdict:p.verdict, status:p.status, reason:p.reason})),
    adoption:list.adoption, application:list.application, group:list.group, provisional_mm:list.provisional_mm ?? null,
    ...(flow?.starterCheck ? {starter:list.application} : {}),
    rings_mm:null, offset_mm:null, L_frames:null, confidence:null};
}
// The physical target disc these photos are of (photo --disc-id). Typed by the person, kept per run in this browser.
function photoDiscId(f, run) {
  if (f && typeof f.photoDiscId === 'string') return f.photoDiscId.trim();
  try { return (sessionStorage.getItem('discprobe-disc-id-' + run) || '').trim(); } catch { return ''; }
}
function discField(u) {
  const label = document.createElement('label'); label.className = 'pc-disc-id';
  const cd = u.flow?.detected?.media === 'cd';
  const title = document.createElement('span'); title.textContent = cd ? liveText('标靶盘号','Target disc number') : liveText('检查盘号','Check disc number');
  const input = document.createElement('input'); input.type = 'text'; input.maxLength = 40; input.autocomplete = 'off'; input.spellcheck = false;
  input.placeholder = liveText('例如 T1','e.g. T1'); input.value = photoDiscId(u.flow, u.run);
  if (u.flow.savedBurn) input.addEventListener('input', () => { u.flow.photoDiscId = input.value; });
  input.readOnly = !!u.flow.starterCheck;
  const hint = document.createElement('small');
  hint.textContent = u.flow.savedBurn ? burnWords('numberHint') : u.flow?.burnCheck?.result === 'completed' && input.value
    ? liveText('刚刻好的这张盘已经自动编了号。想以后认得出它，就用记号笔把编号写在盘的内圈。',
      'The disc just burned has been numbered for you. To know it again later, write the number on its inner ring with a marker.')
    : cd ? liveText('用记号笔在这张标靶盘的内圈写个编号，这里填同样的。照片只和这张盘一起采用；空着就不会用到出图上。',
    'Write a number on this target disc\u2019s inner ring with a marker and type the same here. Photos are adopted only with this disc; left empty, they are not used for pictures.')
    : liveText('用记号笔在这张检查盘的内圈写个编号，这里填同样的。照片只和这张盘一起采用；空着就不会用到出图上。',
    'Write a number on this check disc\u2019s inner ring with a marker and type the same here. Photos are adopted only with this disc; left empty, they are not used for pictures.');
  input.addEventListener('change', () => {
    const value = input.value.trim().slice(0, 40); input.value = value;
    u.flow.photoDiscId = value;
    if (!u.flow.savedBurn) {
      try { sessionStorage.setItem('discprobe-disc-id-' + u.run, value); } catch { /* storage unavailable */ }
    }
    // The disc number is part of the read: read again under the new one.
    u.flow.photoResult = null; u.flow.photoReadKey = null; u.flow.photoReadIds = null;
    u.result.hidden = true; if (u.rows.size) queuePhotoRead(u); photoNavigation(u);
  });
  label.append(title, input, hint);
  return label;
}
function paintPhoto() {
  st?.show(false); loadDisc.desk(false); sideButton(null);
  if (photoUI && photoUI.lang !== api.lang()) closePhoto();
  if (photoUI) { photoNavigation(photoUI); return; }
  document.documentElement.classList.add('cal-photo');
  const host = document.createElement('div'); host.className = 'cal-photo-host'; document.body.append(host);
  const u = photoUI = {host,flow,run:photoRun(flow),lang:api.lang(),status:'loading',seen:new Set(),rows:new Map()};
  $('cal').innerHTML = `<p role="status">${liveText('正在连接照片服务…','Connecting to the photo service…')}</p>`;
  photoNavigation(u);
  (async () => {
    if (!u.run) { photoFallback(u); return; }
    try {
      const results = await Promise.allSettled([
        phoneLink(u),
        api.backend.request(`/api/photos?${photoQuery(u)}`),
      ]);
      if (!photoLive(u)) return;
      const failed = results.find(r => r.status === 'rejected');
      if (failed) { photoFallback(u,photoUnavailable(failed.reason) ? null : failed.reason); return; }
      const [phone,list] = results.map(r => r.value);
      const photos = [...(u.flow.photoSnapshot?.photos || [])];
      for (const p of list.photos || []) if (!photos.some(x => x.id === p.id)) photos.push(p);
      photos.forEach(p => { if (p.id) u.seen.add(p.id); });
      for (const p of list.photos || []) u.rows.set(p.id,p);
      // Every photo was read already (a reload, or Back and in again): show that read, do not read again.
      const listed = (list.photos || []).map(p => p.id).sort(), earlier = readFromListing(list, listed);
      if (!u.flow.photoResult && earlier) { u.flow.photoResult = earlier; u.flow.photoReadIds = JSON.stringify([listed, photoDiscId(u.flow, u.run)]); }
      u.status = 'ready';
      u.page = photoPage(host, {
        lang:u.lang, media:u.flow.detected.media, purpose:u.flow.photoOnly ? 'check' : null, paperHost:$('cal'), photos, ringsMm:u.flow.photoSnapshot?.ringsMm, activePhoto:u.flow.photoSnapshot?.activePhoto,
        measuredMm:u.flow.geo?.measurement?.span_mm,
        phoneUrl:phone.url, phoneQrSvg:phone.qr_svg, addresses:phone.addresses, address:phone.address,
        onAddress:address => choosePhoneAddress(u,address), automaticRead:true, onPhotos:() => queuePhotoRead(u),
        onDisconnect:id => disconnectPhone(u, id),
        onStateChange:state => { u.canUse = state.canUse; u.manual = state.manual; u.manualSaving = state.manualSaving; photoNavigation(u); },
        onBack:photoReview, onSkip:photoSkip,
        // "Auto-align" re-reads with the target's own rings (the core's default for this run). The page's ring
        // guides start from generic radii, not this target's; sending them once replaced a good read of every
        // photo with a failed one (11-22), so they never go to the reader from here.
        autoAlign:async (photo) => {
          const result = await readPhoto(u,photo,null);
          if (result?.verdict === 'ok') {
            return {rings:result.rings_mm,offsetMm:result.offset_mm};
          }
          return null;
        },
        onUse:photo => usePhotoResult(u,photo),
        ...(hasCapability('photo-manual-alignment') && !u.flow.starterCheck ? {
          manualAlignment:(action, photo, values) => api.backend.request('/api/photo-alignment',
            {action, run:u.run, photo:photo.id, ...values}),
          onManualSaved:async result => {
            clearTimeout(u.readTimer); u.readTimer = null;
            u.flow.photoManual = result;
            await savePhotoPreset(u);
          },
        } : {}),
      });
      const paper = $('cal').querySelector('.pc-paper');
      u.notice = document.createElement('p'); u.notice.setAttribute('role','status');
      u.notice.textContent = u.flow.photoNotice || '';
      u.result = document.createElement('div'); u.result.hidden = true;
      u.readState = document.createElement('p'); u.readState.className = 'pc-read-state'; u.readState.setAttribute('aria-live','polite');
      u.listing = list;
      const action = (text,fn) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'pc-button pc-wide'; b.textContent = text; b.hidden = true; b.onclick = fn; paper.append(b); return b; };
      // One headline under the title; the phone, then the disc number; the read's details and timing under "More".
      const el = (tag, cls) => { const n = document.createElement(tag); n.className = cls; return n; };
      u.statusBox = el('div', 'pc-status'); u.statusBox.setAttribute('role', 'status');
      u.statusParts = {head: el('h2', 'pc-status-head'), dots: el('span', 'pc-dots'), label: el('span', 'pc-dots-label'), tip: el('p', 'pc-status-tip')};
      const progress = el('div', 'pc-progress'); progress.append(u.statusParts.dots, u.statusParts.label);
      // the read's own progress: the core reports each photo as it starts; between reports the bar runs on the
      // average time per photo, never past 95 % of the photo being read
      u.statusParts.read = el('div', 'pc-read-progress'); u.statusParts.read.hidden = true;
      u.statusParts.readBar = el('span', 'pc-read-bar'); u.statusParts.readText = el('span', 'pc-read-text');
      const track = el('span', 'pc-read-track'); track.append(u.statusParts.readBar);
      u.statusParts.read.append(track, u.statusParts.readText);
      // Privacy for screenshots: blur what is around the disc on this page (the photo itself is not changed).
      const privacy = el('label', 'pc-privacy-option'), box = document.createElement('input');
      box.type = 'checkbox'; box.checked = !!u.page.privacy?.();
      box.addEventListener?.('change', () => u.page.setPrivacy?.(box.checked));
      privacy.append(box, liveText('截图时保护隐私：模糊盘面以外的画面', 'Privacy for screenshots: blur everything around the disc'));
      u.statusBox.append(u.statusParts.head, progress, u.statusParts.read, u.statusParts.tip, privacy);
      const anchor = paper.querySelector?.('.pc-why'), more = paper.querySelector?.('.pc-more'), phoneSection = paper.querySelector?.('.pc-add-section');
      if (anchor?.after) anchor.after(u.statusBox); else paper.append(u.statusBox);
      if (u.flow.savedBurn) {
        const selected = el('section',''), details = el('p',''), change = el('button','pc-text-button');
        details.id = 'photo-burn-confirmed';
        details.textContent = burnLabel(u.flow.savedBurn.record, true);
        change.type = 'button';
        change.textContent = burnWords('change');
        change.onclick = () => {
          if (u.reading || u.flow.job) return;
          closePhoto();
          Object.assign(u.flow, {photoSnapshot:null, photoResult:null, photoReadKey:null, photoReadIds:null,
            photoNotice:null, photoUploads:null});
          u.flow.savedBurn.confirmed = false;
          paint();
        };
        selected.append(details, change); u.statusBox.after(selected);
      }
      const field = discField(u);
      if (phoneSection?.after) phoneSection.after(field); else paper.append(field);
      if (more?.append) more.append(u.readState, u.result); else paper.append(u.readState, u.result);
      paper.append(u.notice);
      // No "take another" button: a connected phone's next photo arrives by itself. Kept detached for the old wiring.
      u.retry = document.createElement('button'); u.retry.hidden = true;
      u.skip = action(u.flow.starterCheck ? liveText('改用测量盘', 'Use a measurement disc') : liveText('跳过，就用现在的结果','Skip and keep the current result'),photoSkip);
      u.skip.className = 'pc-text-button pc-skip-link';   // secondary: the one primary action is "Use the result", bottom right
      u.page.ready?.then(() => { if (!photoLive(u)) return; u.page.setListing?.(u.listing); paintReadState(u); if (u.flow.photoResult) showPhotoResult(u,u.flow.photoResult); });
      if (photos.length) queuePhotoRead(u);
      pollPhotos(u);
    } catch (error) { photoFallback(u,photoUnavailable(error) ? null : error); }
  })();
}
// a CD on a Windows machine: the core has no CD writer there (burner.WindowsDVD), so the disc is burned elsewhere
const cdHere = () => flow?.detected?.media === "cd" && api.platform?.() === "win32";
// the core's command for that (burner.imapi_cd_command): fetched once per image, "" when it could not be had
function cdCommand() {
  const f = flow;
  if (!f?.iso || f.cdCommandFor === f.iso) return;
  f.cdCommandFor = f.iso; f.cdCommand = undefined;
  api.backend.request(`/api/burn-command?drive=${encodeURIComponent(api.selectedDrive() || "")}&media=cd&iso=${encodeURIComponent(f.iso)}`)
    .then((r) => { f.cdCommand = r.command || ""; }, () => { f.cdCommand = ""; })
    .finally(() => { if (flow === f) paint(); });
}
// ---------------------------------------------------------------- the paper while a step runs
// What is happening and what comes next, in words; for the geometry, the points as they are measured (no
// curve: nothing is fitted yet) and the last lines of the record.
function runningPaper(phase) {
  const tape = flow.tape?.length ? `<pre class="cal-tape">${api.backend.escapeHTML(flow.tape.join("\n"))}</pre>` : "";
  const say = (zh, en) => `<p class="cal-say">${liveText(zh, en)}</p>`;
  if (phase === "burning" && burnPart() !== 'write' && burnPart() !== null) return "";
  if (phase === "burning") return say("随机数据从内圈往外刻。刻完自动抽查回读，然后开始测量。",
    "Random data goes on from the inside out. Then a sample is read back and measuring starts.");
  if (phase === "checking") return say("读一下刚刻好的盘：是不是这批、刻满了没有。几秒钟。", "Reading the disc just burned: the right batch, filled. A few seconds.");
  if (phase === "timing") return say("在盘的三个位置各读几十次，看光驱转得稳不稳。稳了才能测几何。", "Reading at three places on the disc, many times each, to see whether the drive turns steadily. Geometry needs that.") + tape;
  if (phase === "geo") return say("图上的点越贴近中线，读数越一致。", "Points nearer the middle line agree more closely.")
    // wrapped: as a bare grid item the SVG's row collapsed to 0 and the stamp below sat on the chart
    + `<div class="cal-chart">${calchart.liveChart(flow.points || [], { head: flow.head, zh: api.lang() === "zh" })}</div>` + soFar(flow.points || []) + tape;
  if (phase === "saving") return say("把测量写成这批盘的预设。", "Writing the measurement as this batch's preset.");
  return "";
}
// While the geometry is measured: what the points so far say, as the result's stamp says it (designer's example:
// "目前可用 / 读过的这一段很稳 / 内圈到 41 mm ... / 不用做什么"). Judged only on what was read: steady when the
// points' scatter is within about twice their own uncertainty.
function soFar(points) {
  if (points.length < 3) return "";
  const s = points.map((p) => p.s).sort((a, b) => a - b)[points.length >> 1];
  const mean = points.reduce((a, p) => a + p.d, 0) / points.length;
  const spread = Math.sqrt(points.reduce((a, p) => a + (p.d - mean) ** 2, 0) / points.length);
  const steady = spread <= 2 * Math.max(s, .02);
  const row = (dt, dd, act = false) => `<div><dt>${dt}</dt><dd${act ? ' class="act"' : ""}>${dd}</dd></div>`;
  return `<div class="cal-stamp"><b>${steady ? liveText("测点一致", "Readings agree") : liveText("还看不出", "Not clear yet")}</b><dl>` +
    row(liveText("意思", "Means"), steady ? liveText("已读的测点彼此接近。", "The points read so far agree closely.") : liveText("已读测点有些抖，还要再读几处。", "The readings vary; the drive will read more points.")) +
    row(liveText("现在", "Now"), liveText("等测完再检查覆盖范围。", "Coverage is checked after the readings finish.")) + `</dl></div>`;
}
// ---------------------------------------------------------------- the stage: what the disc shows now
function paintStage() {
  if (!st || !flow || api.backend.mock || leaving) return;
  const phase = flow.realPhase, d = flow.detected, job = flow.job, p = Math.max(0, Math.min(1, job?.p ?? 0));
  const disc = (phase === "inspect" && !d) || d?.present === false ? "none" : d?.blank === true || phase === "capacityWritten" ? "blank" : "in";
  let read = null, head = null, band = null;
  if (phase === "burning") read = [R0, radiusAt(p)];                       // the measurement image going on
  // a burn that stopped part way: what was written, and a copper band where it stopped (that disc is spent)
  if (["burning","burnStopped"].includes(phase) && !job && flow.error && flow.burnP > 0) {
    const r = radiusAt(flow.burnP);
    read = [R0, r]; band = [r, Math.min(58, r + 2)];
  }
  if (phase === "geo" && Number.isFinite(flow.head)) head = flow.head;
  const readRadii = phase === "geo" || (phase === "review" && flow.geo) ? flow.points?.map(point => point.r) : null;
  if (phase === "review") {
    const m = flow.geo?.measurement, k = recoveryKind(flow);
    if (["stopped_early", "narrow_span", "media"].includes(k) && m?.span_mm) band = [m.span_mm[1], Math.min(58, m.span_mm[1] + 3)];
  }
  // the moment the drive holds a disc on this visit: it goes in, seen from above (loaddisc.js); then the stage
  if (disc !== "none" && !discWentIn) {
    discWentIn = true; st.hold(true);
    loadDisc.play(st.art()).catch((e) => console.error("disc animation", e)).finally(() => { if (!leaving) st.hold(false); });
  }
  // the browser tab says it too, so a person in another tab sees it going ("62% · 测几何")
  document.title = job ? `${Math.round(p * 100)}% · ${$("job-name").textContent}` : "disc-probe";
  st.set({ disc, read, readRadii, head, band, busy: !!job,
    percent: job ? p * 100 : null, left: job ? job.left || job.status || "" : "" });
}
// "place the picture first, call me when it is measured": the job goes on; the person goes back to the work
// (or starts one); the done sound and a note say when it has finished
function sideButton(words) {
  let b = document.getElementById("cal-side");
  if (!b) {
    b = document.createElement("button"); b.id = "cal-side"; b.type = "button"; b.className = "next-side";
    $("next").before(b);
    b.addEventListener("click", () => {
      back();
      if (!returnTo) api.newWork?.();
    });
  }
  b.hidden = !words; if (words) b.textContent = words;
}
// ---------------------------------------------------------------- the step ruler (header, middle)
// Four segments as long as the steps take: making and burning the measurement disc (about 14 min), the
// rotation check (1-3), the geometry (about 5), and the photo, dashed: only when the picture disc is off.
// Done: ink with a tick; the current one copper, filled as far as the job is; the rest a thin grey line.
const RULER = [
  { key: "disc", min: 14, zh: ["准备测量盘", "约 14 分"], en: ["Measurement disc", "~14 min"] },
  { key: "spin", min: 2.5, zh: ["测转速", "1–3 分"], en: ["Rotation", "1–3 min"] },
  { key: "geo", min: 5, zh: ["测几何", "约 5 分"], en: ["Geometry", "~5 min"] },
  { key: "photo", min: 3.5, dashed: true, zh: ["拍照", "需要时"], en: ["Photo", "if needed"] },
];
const RULER_AT = { inspect: 0, prepare: 0, capacityBlank: 0, capacityWritten: 0, random: 0, burn: 0, burning: 0, checking: 1, timing: 1, geo: 2, saving: 2, review: 2, photo: 3, saved: 4 };
function paintRuler() {
  let nav = document.getElementById("cal-ruler");
  if (!nav) {
    nav = document.createElement("nav"); nav.id = "cal-ruler"; nav.className = "cal-ruler";
    document.body.append(nav);
  }
  const live = isCal() && !api.backend.mock && flow;
  nav.hidden = !live;
  if (!live) return;
  let at = RULER_AT[flow.realPhase] ?? 0;
  // a measurement disc burned before: the first step is done already; a usable result: the geometry too
  if (at === 0 && flow.realPhase === "prepare" && flow.detected?.blank === false) at = 1;
  const usable = flow.realPhase === "review" && ["good", "usable"].includes(recoveryKind(flow));
  if (usable) at = 3;
  if(interruptedBurn(flow,api.lang()) || flow.realPhase==='discRejected')at=0;
  const total = RULER.reduce((a, r) => a + r.min, 0), lang = api.lang() === "zh" ? "zh" : "en";
  nav.setAttribute("aria-label", liveText("标定的步骤和用时", "Calibration steps and their times"));
  nav.innerHTML = RULER.map((r, i) => {
    const state = i < at ? "done" : i === at && !(r.dashed && usable) ? "now" : "next";
    const fill = state === "now" && flow.job ? Math.round(100 * Math.max(0, Math.min(1, flow.job.p || 0))) : 0;
    return `<div class="step" data-s="${state}" ${r.dashed ? "data-dashed" : ""} style="flex:${r.min / total}" ${state === "now" ? 'aria-current="step"' : ""}>` +
      `<span class="name">${state === "done" ? '<svg class="tick" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5l2.6 2.6L10 3.5"/></svg>' : ""}${r[lang][0]}</span>` +
      `<span class="line"><i style="width:${fill}%"></i></span><span class="len">${r[lang][1]}</span></div>`;
  }).join("");
}
// the core's steps (calibrate.py) as this page's phases
const STEP_PHASE = { burn: "burning", check: "checking", timing: "timing", geo: "geo", preset: "saving" };
// the core's step names (calibrate.py, info, random) in the page's words, for the job bar
const STEP_WORDS = {
  info: ["检测光盘", "Checking the disc"], random: ["生成测量图", "Making the image"], burn: ["刻测量盘", "Burning"],
  check: ["检查刻好的盘", "Checking the burn"], timing: ["测转速", "Rotation"], geo: ["测几何", "Geometry"],
  preset: ["保存预设", "Saving the preset"], calibrate: ["标定", "Calibrating"], photo: ["读照片", "Reading photo"],
  checkdisc: ["生成检查盘", "Making the check disc"],
  starter: ["检查起步预设", "Checking starter presets"],
};
const stepWords = (name) => STEP_WORDS[name] ? liveText(...STEP_WORDS[name]) : name;
const stepEta = (name, flow) => name === "geo" ? (flow.repairingCoverage ? 120 : 300) : name === "timing" ? 90 : null;
// The disc check reports no progress of its own and takes a second or two: its bar stays empty and says it is
// reading, then fills when the answer comes. A bar that filled over a guessed time would look like a measurement.
async function realJob(action, args = {}, extra = {}, following = null) {
  const f = flow;
  const current = {kind:action, id:following, p:0}; f.job = current;
  current.clock = countdown(seconds => { if (flow === f && f.job === current) jobTime(current, seconds); });
  jobTime(current, null);
  current.clock.estimate(stepEta(action, f));
  if (action === "geo") { f.points = []; f.tape = []; f.head = null; }
  flow.jobWord = action; $("job-name").textContent = stepWords(action); paint(); paintJob();
  const drive = ["info","timing","geo","burn","calibrate","starter"].includes(action) ? api.selectedDrive() : undefined;
  placeLog(); flog.start(commandLine(action, drive));
  let why = "", lastLine = "", burnGate;            // the core's own reason survives later summary events
  // checking the disc reports no progress of its own: the bar stays empty and the words say it is reading
  // (a guessed percentage or time left would only be wrong); it fills when the answer is in
  if (action === "info") {
    api.jobProgress(0, f.detected?.media || f.item?.row || "dvd");
    $("job-time").textContent = current.status = liveText("读取中", "Reading");
    paintStage();
  }
  const onEvent = event => {
      if (flow !== f) return;
      if (event.type === 'diagnostics') f.retryDiagnostics = event;
      if (event.type === "error" && event.message) why = event.message;
      if (event.type === "error" && event.burn_gate) burnGate = event.burn_gate;
      if (event.type === "log" && event.text?.trim()) lastLine = event.text.trim();
      // the measurement record: each geometry rung the core reports ("41.0 mm: moved +0.123 deg ...")
      if (event.type === "log" && /^\s*\d+(\.\d+)? mm: /.test(event.text || "")) {
        // the core's own words, no clock: lines replayed after a reload would all show the reload's time
        f.tape = [...(f.tape || []), event.text.trim()].slice(-3);
        if (isCal()) paint();
      }
      if (event.type === "geo_point" && [event.radius_mm, event.residual_deg, event.sigma_deg].every(Number.isFinite)) {
        f.points ||= [];
        if (!f.points.some(p => p.rung === event.rung)) {
          f.points.push({rung:event.rung, r:event.radius_mm, d:event.residual_deg, s:event.sigma_deg});
          f.head = event.radius_mm;
          if (isCal()) paint();
        }
      }
      // where the head is: only a radius the core worked out from its own fit, never a guess
      if (event.type === "progress" && Number.isFinite(event.radius_mm)) f.head = event.radius_mm;
      if (event.type === 'erase_started') {current.clock.clear();f.realPhase='erasing';f.jobWord='erase';$("job-name").textContent=liveText('擦除光盘','Erasing');f.stage=liveText('正在擦除光盘，盘上的内容会被清掉。','Erasing the disc; its contents will be cleared.');closeBurnStop();paint();paintJob();}
      if (event.type === 'erase_progress') {current.p=event.fraction;api.jobProgress(current.p,f.detected?.media||'dvd');current.clock.estimate(event.eta_s);f.stage=liveText('盘上的内容正在清掉。','The disc contents are being cleared.');paint();}
      if (event.type === 'erase_result') {f.eraseResult=event;if(event.result!=='completed'){f.burnStarted=false;f.realPhase='burn';}}
      if (event.type === 'burn_speed') {
        if(f.realPhase!=='burning')current.clock.clear();
        f.lastBurnSpeed = event.actual_speed_x ?? event.selected_speed_x ?? f.lastBurnSpeed;
        f.realPhase='burning';f.jobWord='burn';$("job-name").textContent=stepWords('burn');f.burnStarted=true;f.stage=null;paint();paintJob();
      }
      if (event.type === "burn_result") { f.burnCheck = event; if(event.result==='completed')f.burnStarted=false; }
      if (event.type === "cancelled" && event.by==='user') f.cancelledByUser=event;
      if (event.type === "verify_progress" && !current.verifying) {current.verifying=true;closeBurnStop();paint();paintJob();}
      if (event.type === "started") {current.id = event.job;paint();paintJob();}
      if (event.type === "step") {
        current.clock.clear();
        closeBurnStop();current.verifying=false;
        f.realPhase = STEP_PHASE[event.name] ?? f.realPhase; f.stage = null; current.p = 0; f.head = null;
        current.clock.estimate(stepEta(event.name, f));
        if (event.name === "geo") { f.points = []; f.tape = []; }
        sfx.step(event.index ?? 0);
        f.jobWord = event.name; $("job-name").textContent = stepWords(event.name);
        flog.log(`$ python -m discprobe ${event.name}`, "command");
        if (event.name !== "geo") showInterior(false);
        paint(); paintJob();
      }
      if (event.type === "disc" && event.present) {
        f.detected = { ...f.detected, ...event, mid: event.mid || f.detected?.mid };
        f.blankSectors ??= event.capacity_sectors;
        paint();
      }
      if (event.type === "log") flog.log(event.text, event.level, event.ansi);
      if (event.type === "progress") flog.progress(event.fraction, event.stage, event.eta_s);
      if (event.type === "ask") { f.ask = event; paint(); }
      if (event.type === "answer") { f.ask = null; paint(); }
      if (event.type === "stopped") f.error = liveText('提前停止：', 'Stopped early: ') + event.reason;
      if (event.type === "progress" && action !== "info") {
        current.p = Math.max(0, Math.min(1, event.fraction || 0)); f.plateP = current.p;
        current.fraction = Number.isFinite(event.fraction) ? current.p : null;
        if (action === "random" && isCal()) imageRing?.progress(current.fraction);
        if (f.realPhase === "burning") {
          const done = current.p >= 0.999 && (f.burnP ?? 0) < 0.999;
          f.burnP = current.p;                                          // how far the burn got (a stop shows it)
          if (done) queueMicrotask(() => { paint(); paintJob(); });     // written: the page says the drive is finishing
        }
        f.stage = event.stage; api.jobProgress(current.p, f.detected?.media || f.item?.row || "dvd");
        current.clock.estimate(event.eta_s);
        if (action === "geo" || f.realPhase === "geo") { setPlate("geo"); showInterior(true); updateInterior(current.p, Math.max(0, event.eta_s || 0)); }
        paintStage(); paintRuler();
      }
  };
  try {
    if (drive && !following) await api.waitForDiscCheck?.(drive);
    const result = following ? await api.backend.follow(following, onEvent)
      : await api.backend.job({action, media:f.detected?.media || f.item.row || "dvd", drive, args, ...extra}, onEvent);
    if (action === "info") { current.p = 1; api.jobProgress(1, f.detected?.media || f.item?.row || "dvd"); }      // the answer is in: the bar ends full
    if (action === "random") imageRing?.done();
    const burn = f.burnCheck;
    if (["burn", "calibrate"].includes(action) && burnCheckFailed(burn))
      throw Object.assign(new Error(burn.reason || liveText('刻录没有通过检查。请重新读取这张盘，查看保存的日志，再决定是否重刻。', 'The burn did not check out. Re-read this disc and inspect the saved logs before another burn.')), {failure:true});
    if (action === "calibrate" && result?.ok) f.resultJob = { id:current.id };
    return result;
  } catch (error) {
    if (error.status === 422 && (why || lastLine)) error.message = why || lastLine;
    if (burnGate) error.burnGate = burnGate;
    throw error;
  } finally { if (flow === f) {endJob(); f.ask = null; showInterior(false);} }
}
async function inspectDisc() {
  if (!api.selectedDrive()) await api.syncState?.();          // plugged in since the page opened?
  if (!api.selectedDrive()) throw new Error(liveText('没找到光驱。接好光驱，等电脑认出它，再点“重新检测”。', 'No drive found. Connect the drive, wait for the computer to see it, then press Check again.'));
  const want = flow.item.row || flow.detected?.media || "dvd";
  const expectedMid = flow.detected?.mid || flow.item.mid || flow.item.readMid;
  const result = await realJob("info");
  if (!result?.disc?.present) throw new Error(liveText('没有读到盘。放入光盘再检测。', 'No disc detected. Insert a disc and check again.'));
  const got = String(result.disc.media || "?").toUpperCase();
  if (result.disc.media !== want) throw new Error(liveText(`光驱里是 ${got} 盘，这里标定的是 ${want.toUpperCase()}。换一张 ${want.toUpperCase()} 再检测。`, `The drive holds a ${got} disc; this calibrates ${want.toUpperCase()}. Put in a ${want.toUpperCase()} and check again.`));
  if (expectedMid && result.disc.mid && !sameMaker(result.disc.mid, expectedMid)) throw new Error(liveText('厂商编号已改变，请放回同批次光盘。', 'The maker code changed. Insert a disc from the same batch.'));
  return result;
}
async function retryMeasurement(speed = null) {
  if (flow.job || flow.curvePending || $("left-input")?.reportValidity?.() === false) return;
  const previous = {timing:flow.timing};
  flow.error = null; flow.calibratedOk = null; flow.calibrationReason = null; flow.coverageNotice = null;
  flow.retryDiagnostics = null;
  flow.photoResult = null; flow.photoReadKey = null; flow.photoSnapshot = null; flow.photoUploads = null; flow.photoNotice = null;
  flow.photoSkipped = false;
  flow.preset = null; flow.geo = null; flow.timing = null;
  try {
    const result = await remeasure(async (action, args) => {
      flow.realPhase = action;
      const result = await realJob(action, args);
      flow[action] = result;
      return result;
    }, previous, speed);
    Object.assign(flow, result);
  } catch (error) {
    if (!error.result) { realError(error); return; }
    flow[flow.realPhase] = error.result[flow.realPhase] || error.result;
  }
  flow.realPhase = 'review';
  paint();
}

async function realNext() {
  if (flow.job || flow.curvePending) return;
  flow.error = null;
  try {
    const phase = flow.realPhase;
    if(phase==='burnStopped'&&keepDiscForReview(flow.burnFailureGate)){
      flow.burnFailureGate=null;flow.burnCheck=null;flow.burnInterrupted=false;flow.burnStarted=false;
      flow.burnInspection=null;flow.burnRetry=true;flow.burnSpeed=undefined;
      flow.eraseRequested=false;flow.realPhase='inspect';
      await realNext();return;
    }
    if(phase==='burnStopped'||phase==='discRejected'||interruptedBurn(flow,api.lang())){
      if (phase !== 'discRejected') {
        flow.burnRetry = true;
        flow.burnSpeed = undefined;
        flow.burnInspection = null;
      }
      if(flow.detected?.rewritable){
        flow.eraseRequested=true;flow.burnCheck=null;flow.cancelledByUser=null;flow.burnInterrupted=false;flow.burnStarted=false;
        flow.requireBlank=false;flow.measureConfirmed=false;flow.realPhase='prepare';
        await realNext();return;
      }
      flow.requireBlank=true;flow.burnCheck=null;flow.cancelledByUser=null;flow.burnInterrupted=false;flow.burnStarted=false;
      flow.geo=null;flow.timing=null;flow.preset=null;flow.measureConfirmed=false;flow.discIssue=null;
      flow.realPhase='inspect';paint();return;
    }
    if (phase === "burn" && cdHere()) { flow.realPhase = "inspect"; return realNext(); }   // burned elsewhere: read it
    if (phase === "burn") {
      const report=flow.burnInspection, gate=report?.gate;
      if(!report || report.error || gate && gate.code!=='other_batch')await refreshBurnInspection();
      else if(!gate || flow.batchConfirmed)await realBurn();
    }
    else if (phase === "capacityBlank") {
      const {disc} = await inspectDisc();
      if (disc.blank !== true) throw new Error(liveText('请放入一张同批次的空白盘，再检测。', 'Insert a blank from the same batch, then check again.'));
      const sectors = disc.capacity_sectors ?? disc.sectors;
      if (!manualCapacity(sectors)) throw new Error(liveText('没读到空白盘容量。请重新检测，或返回手动输入。', 'Could not read the blank disc capacity. Check again, or go back to enter it by hand.'));
      flow.blankSectors = sectors;
      flow.realPhase = "capacityWritten";
    } else if (phase === "capacityWritten") {
      const {disc} = await inspectDisc();
      if (disc.blank !== false) throw new Error(liveText('请放回刚才刻满随机数据的测量盘，再检测。', 'Put the full random-data measurement disc back, then check again.'));
      const issue = shortDiscWords(disc, api.lang());
      if (issue) throw new Error(issue);
      flow.detected = disc;
      flow.realPhase = "prepare";
    } else if (phase === "inspect" || (phase === "prepare" && flow.detected.blank == null)) {
      const result = await inspectDisc();
      const disc = result.disc;
      flow.starterCandidates = !flow.starterDeclined && disc.media === 'dvd' && disc.blank === true && hasCapability('starter-preset')
        ? result.starter_candidates ?? [] : [];
      if (returnTo && !flow.starterDeclined && !flow.starterCandidates.length) {
        await api.syncState?.();
        const batch = calibratedBatch(api.catalogue?.(result.disc.media) ?? [], flow.item, result.disc);
        if (batch) {
          flow.savedId = batch.id; flow.savedBatch = batch; flow.realPhase = "saved";
          leave(); return;
        }
      }
      flow.catalogueSectors = result.catalogue_capacity_sectors;
      flow.detected = result.disc; flow.realPhase = "prepare"; flow.measureConfirmed = false;
      const issue=shortDiscWords(result.disc,api.lang());
      if(issue || flow.requireBlank && result.disc.blank!==true && !result.disc.rewritable){
        flow.discIssue=issue||liveText('上次的刻录没有完成。请换一张同批的空白盘，不能继续测这张盘。','The previous burn did not finish. Insert a blank from the same batch; this disc cannot be measured.');
        flow.realPhase='discRejected';paint();return;
      }
      if(result.disc.blank===true)flow.requireBlank=false;
      if (result.disc.blank === true) flow.blankSectors = result.disc.capacity_sectors ?? result.disc.sectors;
    } else if (phase === "prepare") {
      if (flow.starterChoice && flow.detected.blank === true) {
        const selected = await realJob('starter', {source:flow.starterChoice});
        if (!selected?.path || selected.mid !== flow.detected.mid) throw new Error(liveText('起步预设与当前空白盘不匹配。', 'The starter preset does not match this blank disc.'));
        flow.starterCheck = {...selected, name:flow.realName || selected.mid};
        flow.geo = {path:selected.path}; flow.realPhase = 'starterCheck';
        await burnCheckDisc();
        return;
      }
      if ((flow.detected.blank === true || flow.eraseRequested) && flow.iso) flow.realPhase = "burn";     // the image made before, kept for a retry
      else if (flow.detected.blank === true || flow.eraseRequested) {
        const media = flow.detected.media;
        const capacity = flow.detected.capacity_sectors || flow.detected.sectors;
        if (!Number.isInteger(capacity)) throw new Error(liveText('容量未知。请重新检测空白盘。', 'Capacity is unknown. Check the blank disc again.'));
        flow.iso = `iso/${media}-measurement-${Date.now()}.iso`;
        flow.realPhase = "random";
        const sectors = Math.floor(capacity * .98 / (media === "cd" ? 1 : 16)) * (media === "cd" ? 1 : 16);
        const result = await realJob("random", {sectors, output:flow.iso});
        if (!result?.path) throw new Error("No measurement image was saved.");
        flow.realPhase = "burn";
      } else if (flow.measureConfirmed) {
        const needsCapacity = needsBlankCapacity();
        const sectors = needsCapacity ? manualCapacity(flow.manualSectors) : undefined;
        if (!needsCapacity || sectors) await realCalibrate({sectors});
      }
    } else if (phase === 'starterCheck') {
      await burnCheckDisc(); return;
    } else if (phase === "review") {
      if ($("left-input")?.reportValidity?.() === false) return;
      const recovery = recoveryAction(flow);
      if (recovery.id === 'coverage') {
        flow.coverageNotice = null;
        flow.repairingCoverage = true;
        try { await realCalibrate({resume:flow.geo.path}); }
        catch (error) {
          flow.realPhase = 'review';
          flow.coverageNotice = api.backend.errorText(error, api.lang());
        } finally { flow.repairingCoverage = false; }
      } else if (recovery.id === 'drive') {
        flow.geo = null; flow.timing = null; flow.preset = null;
        flow.realPhase = "inspect";
      } else if (recovery.id === 'blank') {
        flow.geo = null; flow.timing = null; flow.preset = null;
        flow.burnRetry = true; flow.burnSpeed = undefined; flow.burnInspection = null;
        flow.realPhase = "inspect";
        await realNext();
      } else if (recovery.id === 'measure') await retryMeasurement();
      else if (flow.detected.media === "cd" && !flow.photoSkipped) enterPhoto();
      else await realSave();
    } else if (phase === "photo") {
      if (flow.savedBurn && !flow.savedBurn.confirmed) {
        if (flow.savedBurn.record && flow.photoDiscId?.trim()) {
          flow.photoDiscId = flow.photoDiscId.trim();
          flow.savedBurn.confirmed = true;
          paint();
        }
        return;
      }
      if (photoUI?.status === 'unavailable') { if (flow.detected.media === 'cd') await realSave(); else photoReview(); }
      // A server-readable photo (e.g. HEIC) may have no preview in this browser.
      else if (photoUI?.page?.state().activePhoto < 0) await usePhotoResult(photoUI);
      else await photoUI?.page?.use();
    }
    else if (phase === "saved") {
      if (checkDiscOffered()) { await burnCheckDisc(); return; }
      savedDone(); return;
    }
    if(flow.realPhase==='burn'&&!cdHere()&&!flow.burnInspection)await refreshBurnInspection();
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
  const avoid = (flow.burnCheck?.verification?.failures || [])
    .filter(f => typeof f.radius_mm === "number" && Number.isFinite(f.radius_mm))
    .map(f => [Math.max(0, f.radius_mm - 2), f.radius_mm + 2])
    .filter(([a, b]) => a < b).sort((a, b) => a[0] - b[0]);
  const bands = [];
  for (const [a, b] of avoid) {
    const last = bands[bands.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else bands.push([a, b]);
  }
  flow.burnCheck = null;
  try { result = await realJob("calibrate", { mid: flow.detected?.mid || undefined, ...args, speed: "4x", avoid_mm: args.resume ? [] : bands.map(([a, b]) => `${a}-${b}`), preset, sectors: args.sectors ?? flow.blankSectors ?? undefined }, extra); }
  catch (error) {
    if (error.burnGate || (args.resume && !error.result?.geo?.measurement?.span_mm)) throw error;
    if (flow.burnCheck?.result === "failed" && flow.burnCheck.reason)
      throw Object.assign(new Error(flow.burnCheck.reason), {failure:true});
    if (!error.result?.timing && !error.result?.geo) {
      // the core said why it stopped: in words, with the next step (a half-written disc is not used again)
      if (error.result?.reason) throw Object.assign(new Error(stopText(error.result.reason)),
        { failure: /the burn did not finish/.test(error.result.reason) && ["failed", "cancelled"].includes(flow.burnCheck?.result) });
      throw error;
    }
    result = error.result;
  }
  flow.error = null;
  finishCalibrate(result);
}
const stopText = (reason) => stopReason(reason, {burnStarted: ["failed", "cancelled"].includes(flow?.burnCheck?.result)})[api.lang()];
// The person went to place the picture meanwhile: a note on whatever page is open, with the way back.
function callBack() {
  if (!flow?.callMe || isCal()) return;
  flow.callMe = false;
  let n = document.getElementById("cal-callback");
  if (!n) {
    n = document.createElement("div"); n.id = "cal-callback"; n.className = "cal-callback"; n.setAttribute("role", "status");
    document.body.append(n);
  }
  const ok = ["good", "usable"].includes(recoveryKind(flow));
  n.innerHTML = `<span>${ok ? liveText("标定测好了。", "Calibration measured.") : liveText("标定停下了，要你看一下。", "Calibration stopped; it needs you.")}</span>` +
    `<button type="button">${liveText("去看结果", "See the result")}</button>`;
  n.hidden = false;
  n.querySelector("button").onclick = () => { n.hidden = true; start(api, { keep: true }); };
}
function finishCalibrate(result) {
  if (!result?.ok && !result?.geo && !result?.timing) throw new Error(result?.reason ? stopText(result.reason) : liveText('标定没有完成。', 'The calibration did not finish.'));
  flow.timing = flow.repairingCoverage ? result.timing ?? flow.timing : result.timing;
  flow.geo = result.geo; flow.preset = result.preset;
  flow.calibratedOk = result.ok;
  flow.calibrationReason = result.ok ? null : result.reason;
  flow.curveState = null; flow.curvePending = false;
  flow.photoResult = null; flow.photoReadKey = null; flow.photoSnapshot = null; flow.photoUploads = null; flow.photoNotice = null;
  if (result.ok) sfx.done(); else sfx.problem();          // measured and usable / measured, but not usable yet
  if (result.disc) flow.detected = { ...flow.detected, ...result.disc, mid: result.disc.mid || flow.detected?.mid };
  flow.blankSectors = result.sectors ?? flow.blankSectors;
  flow.realPhase = "review";
  setTimeout(callBack, 0);
}
function acknowledgeResult() {
  const job = flow?.resultJob;
  if (!job?.id || job.acknowledged) return;
  job.acknowledged = true;
  api.backend.request(`/api/jobs/${job.id}/result-seen`, {}, {keepalive:true}).catch(() => { job.acknowledged = false; });
}
// The measurement disc, burned here: a fresh read-only look that the tray still holds a blank (which also
// lets the server accept this one burn), a one-time token, the burn; then the disc is read again (written
// now, same maker code) and measuring starts.
function measurementBurnRequest(f) {
  return {action:'calibrate',drive:api.selectedDrive(),media:f.detected?.media||f.item.row||'dvd',
    args:{iso:f.iso,mid:f.detected?.mid||f.item.mid||undefined,burn_speed:f.burnSpeed,...(f.eraseRequested?{erase:true}:{})}};
}

async function refreshBurnInspection() {
  const f=flow;
  if(f.burnInspecting)return;
  f.burnInspecting=true;f.burnInspection=null;f.batchConfirmed=false;paint();
  try {
    await api.waitForDiscCheck?.(api.selectedDrive());
    f.burnInspection=await checkBurn(api.backend,measurementBurnRequest(f));
    if (!f.burnInspection.speeds_x?.includes(f.burnSpeed)) f.burnSpeed = undefined;
  }
  catch(error){f.burnInspection={error};}
  finally{f.burnInspecting=false;if(flow===f)paint();}
}

async function realBurn() {
  const confirmed=flow.batchConfirmed?flow.burnInspection?.gate:null;
  flow.burnCheck=null;flow.burnFailureGate=null;flow.cancelledByUser=null;flow.burnInterrupted=false;flow.burnStarted=false;
  flow.realPhase = "burning"; flow.burnP = 0; flow.stage = checkingText(api.lang()); paint();
  const {args,burn_token}=await confirmBurn(api.backend,measurementBurnRequest(flow),confirmed,api.lang());
  flow.stage = null;
  if(confirmed)flow.blankSectors=flow.burnInspection?.disc?.capacity_sectors || undefined;
  await realCalibrate(args, {burn_token});
}
async function realSave() {
  if (flow.calibratedOk === false) throw new Error(liveText(
    '标定未通过。请完成测量后再保存预设。', 'Calibration did not pass. Complete the measurement before saving a preset.'));
  flow.realPhase = "saving";
  const output = `presets/calibration-${Date.now()}.json`;
  const sectors = flow.blankSectors ?? flow.detected.capacity_sectors;
  // Recheck a CD even when a preset already exists: its registered drive may
  // differ from the one now selected, including when the photo step was skipped.
  const needsExport = !flow.preset || !!flow.photoResult || !!flow.photoManual || flow.detected.media === 'cd';
  if (needsExport && (!Number.isInteger(sectors) || sectors <= 0)) throw new Error(liveText('空白盘容量未知。请用 calibrate --sectors 指定容量。', 'Blank capacity is unknown. Run calibrate with --sectors.'));
  // Only send a path to the stored reader record. Browser-supplied L/verdicts
  // cannot bypass the exporter's provenance gate, including a stale photo run.
  const manual = flow.photoManual;
  const photoPath = manual ? flow.geo.path : flow.photoResult?.path || (flow.photoResult ? flow.geo.path : null);
  const photoFile = manual ? 'photo-manual.json' : 'photo.json';
  const result = needsExport ? await realJob("disexport", {geo:flow.geo.path, sectors, output,
    reading_drive:api.selectedDrive(), ...(photoPath ? {photo:`${photoPath.replace(/[\\/]+$/, '')}/${photoFile}`} : {})}) : { path: flow.preset };
  if (!result?.path) throw new Error("No preset was saved.");
  if (manual && (!result.photo_shift?.written || result.photo_shift.provenance_sha256 !== manual.provenance_sha256)) {
    throw new Error(liveText('预设没能采用刚保存的人工值。请检查光驱与测量是否对应，再保存一次。',
      'The preset could not use the manual value just saved. Check the drive and measurement, then save again.'));
  }
  const state = await api.backend.state();
  const entry = state.catalogue[flow.detected.media].find(x => x.geo === flow.geo.path);
  if (!entry) throw new Error("The calibration is not in the saved catalogue.");
  // the name the form showed (the maker code, else the disc kind) unless one was typed; never the folder name
  const saved = await api.backend.request("/api/catalogue", {id:entry.id, name:flow.realName?.trim() || flow.detected?.mid || entry.name, preset:result.path,
    ...(flow.left == null ? {} : {left:flow.left})});
  flow.savedPhotoShift = saved.photo_shift || result.photo_shift || {written:false, reason:'no_photo'};
  await api.syncState?.();
  flow.savedBatch = api.catalogue?.(flow.detected.media)?.find(x => x.id === entry.id) ?? entry;
  flow.savedPath = result.path; flow.savedId = entry.id; flow.realPhase = "saved";
  acknowledgeResult();
}

