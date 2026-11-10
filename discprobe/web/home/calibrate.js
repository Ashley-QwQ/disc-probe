// The calibration flow, as a mode of the home page: the scene stays at the drive, the right column
// becomes the step panel, the bar shows the job, the back button takes the top-left corner.
// Mock only: the steps follow `guide` (docs/goals/gui-flow.md) but the jobs are simulated, sped up
// DEMO times, with made-up readings. The real page drives them from /api/run and /api/events.

const DEMO = Number(new URLSearchParams(location.search).get("demo")) || 40;   // simulated jobs run this many times faster (?demo=N)
const R0 = 22, R1 = 58.5;             // data area, mm: the radius the head sweeps while burning

const STR = {
  zh: {
    steps: ["准备测量盘", "测转速", "测几何", "拍照"],
    prepare: "准备一张测量盘",
    prepareLede: (d) => `测量要用一张刻满随机数据的 ${d}。刻一次，测量就能开始。`,
    optBurn: "刻一张测量盘", optBurnSub: "放入一张同批次的空白盘，约 14 分钟。",
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
    readyBurn: "镜像好了，可以刻", readyLede: "按住右下角的按钮开始刻录，约 14 分钟。刻的时候托盘会关上。",
    holdBurn: "下一步：刻测量盘（按住）",
    burning: "正在刻测量盘", burningLede: "托盘关着，别动光驱。刻完会自动接着测量。",
    burnJob: "刻测量盘",
    burned: "测量盘刻好了",
    startMeasure: "下一步：开始测量",
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
    optBurn: "Burn a measurement disc", optBurnSub: "Put in a blank from the same batch. About 14 minutes.",
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
    readyBurn: "The image is ready to burn", readyLede: "Hold the button at the bottom right to start. About 14 minutes; the tray closes while it burns.",
    holdBurn: "Next: burn the disc (hold)",
    burning: "Burning the measurement disc", burningLede: "The tray stays closed; leave the drive alone. Measuring follows on its own.",
    burnJob: "Burning",
    burned: "Measurement disc burned",
    startMeasure: "Next: start measuring",
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
    ...ui,
  };
}

export function start(homeApi) {
  api = homeApi; $ = api.$;
  const item = api.current().item;
  // a job still running belongs to its disc: come back to it; otherwise start over for this disc
  if (!flow || (flow.item !== item && !flow.job)) {
    flow = newFlow(item);
    if (!ui) build();
  }
  open();
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
  addEventListener("keydown", (e) => {
    if (!isCal()) return;
    if (e.key === "Escape") back();
    if (e.key === "s" || e.key === "S") cycleState();
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
}

function leave() {
  release();
  // a disc that was in the air goes back to waiting; detection starts over next time
  if (!flow.job && ["detecting", "identify", "flying", "hover", "falling", "checking"].includes(flow.disc)) flow.disc = "detect";
  if (!flow.job && flow.disc === "remove") flow.disc = "detect";
  api.goTo(...api.locate(flow.item));     // back to where the disc stands on the shelf
}

function back() {
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
  f.querySelector(".print textPath").textContent = flow.item.name;
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
  const tick = () => {
    if (flow.job !== job) return;
    job.p = Math.min(1, ((performance.now() - job.started) / 1000) * DEMO / seconds);
    const r = radiusAt(job.p);
    const fill = $("job-fill");
    fill.style.width = `${(job.p * 100).toFixed(2)}%`;
    fill.style.background = disc
      ? `linear-gradient(90deg, ${Array.from({ length: 9 }, (_, i) => rainbowAt(R0 + ((r - R0) * i) / 8)).join(", ")})`
      : "var(--ink)";
    const leftS = seconds * (1 - job.p);
    $("job-time").textContent = leftS > 90 ? T().left(leftS) : T().leftSec(leftS);
    flow.plateP = job.p;
    if (kind === "burn") updateInterior(job.p, leftS);
    else drawPlate();
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
}

function cancelJob() {
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
const CROP = [10, 25, 1180, 920];             // what of the 1600 × 1062 canvas is drive (mirrored px)
let inside = null;
async function buildInterior() {
  if (inside) return inside;
  const info = await fetch("interior/interior.json").then((r) => r.json());
  const stage = document.createElement("div");
  stage.className = "cutaway live";
  stage.innerHTML = `<div class="cutaway-in"></div>`;
  const box = stage.firstChild, sets = {};
  for (const theme of ["dark", "paper"]) {
    const set = document.createElement("div");
    set.className = `inside ${theme === "dark" ? "dark" : "light"}`;
    const disc = theme === "dark" ? "disc" : "disc_cut";          // dark: see-through disc; paper: cut away
    const img = (name, cls) => `<img class="${cls}" alt="" decoding="async" data-src="interior/${name}_${theme}.webp">`;
    set.innerHTML = img("bg", "bg") + img("sled", "sled") + img("mid", "mid") + img(disc, "disc") + img("glow", "glow") + img("occluders", "occ");
    box.append(set);
    sets[theme] = set;
  }
  // flat type, placed in canvas px (the picture is mirrored, the type is not)
  const at = (el, x, y) => { el.style.left = `${(1 - x / 1600) * 100}%`; el.style.top = `${(y / 1062) * 100}%`; };
  const pct = document.createElement("div"), clock = document.createElement("div");
  pct.className = "inside-type big"; clock.className = "inside-type";
  const d = info.disc.centre_px_top_face, m = info.disc.plane_matrix_px_per_mm;
  at(pct, d[0] + m.a * 37 + m.c * 17, d[1] + m.b * 37 + m.d * 17);   // the open part of the disc, below the clamp bridge
  at(clock, 705, 468);                         // the flat floor of the closed tray, beside the pickup
  box.append(pct, clock);
  document.body.append(stage);
  inside = { info, stage, box, sets, pct, clock, on: false };
  addEventListener("resize", () => { if (inside.on) place(); });
  return inside;
}
function insideTheme() { return document.documentElement.dataset.theme === "dark" ? "dark" : "paper"; }
function loadInside(theme) {
  for (const im of inside.sets[theme].querySelectorAll("img[data-src]")) { im.src = im.dataset.src; im.removeAttribute("data-src"); }
}
function rigRect() {
  return [...api.burnerLayer.querySelectorAll(".rig")].find((n) => n.getBoundingClientRect().width > 0)?.getBoundingClientRect();
}
// the big place: the left half of the window, up to the text column, between the top row and the bar
function place() {
  const W = innerWidth, H = innerHeight;
  const calLeft = $("cal").getBoundingClientRect().left || W * 0.56;
  const x0 = 12, x1 = Math.min(calLeft - 56, W * 0.6), y0 = 76, y1 = H - 80 - 8;
  const [cx, cy, cw, ch] = CROP;
  const k = Math.min((x1 - x0) / cw, (y1 - y0) / ch);
  const L = x0 + (x1 - x0 - cw * k) / 2 - cx * k, T0 = y0 + (y1 - y0 - ch * k) / 2 - cy * k;
  Object.assign(inside.box.style, { left: `${L}px`, top: `${T0}px`, width: `${1600 * k}px`, height: `${1062 * k}px` });
  return { L, T: T0, w: 1600 * k };
}
// the transform that puts the big cutaway back onto the drive picture
function fromRig(to) {
  const r = rigRect();
  if (!r) return "none";
  return `translate(${r.left - to.L}px, ${r.top - to.T}px) scale(${r.width / to.w})`;
}
async function showInterior(on) {
  const root = document.documentElement;
  if (!on) {
    if (!inside?.on) return;
    inside.on = false;
    const to = { L: parseFloat(inside.box.style.left), T: parseFloat(inside.box.style.top), w: parseFloat(inside.box.style.width) };
    inside.box.style.transform = fromRig(to);          // shrink back into the drive
    inside.stage.classList.remove("on");
    root.classList.remove("burning");
    api.burnerLayer.classList.remove("inside-on");
    return;
  }
  const s0 = await buildInterior();
  if (s0.on) { place(); return; }
  s0.on = true;
  loadInside(insideTheme());
  const to = place();
  s0.box.style.transition = "none";
  s0.box.style.transform = fromRig(to);               // start exactly on the drive picture
  void s0.box.offsetWidth;
  s0.box.style.transition = "";
  s0.stage.classList.add("on");
  api.burnerLayer.classList.add("inside-on");
  root.classList.add("burning");
  setTimeout(() => { if (s0.on) s0.box.style.transform = "none"; }, 30);   // then grow into place
}
function updateInterior(p, leftS) {
  if (!inside) return;
  const sl = inside.info.sled, size = inside.info.image_size;
  const r = Math.min(sl.radius_mm[1], Math.max(sl.radius_mm[0], radiusAt(p) * (sl.radius_mm[1] / R1)));
  const t = (r - sl.radius_mm[0]) / sl.travel_mm;
  const tx = `${((sl.offset_px[0] * t) / size[0]) * 100}%`, ty = `${((sl.offset_px[1] * t) / size[1]) * 100}%`;
  inside.box.style.setProperty("--sled", `${tx}, ${ty}`);
  inside.pct.textContent = `${Math.floor(p * 100)}%`;
  const m = Math.floor(leftS / 60), sec = Math.floor(leftS % 60);
  inside.clock.textContent = `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}
// the theme can change while it burns: load the other set when it is first needed
new MutationObserver(() => { if (inside) loadInside(insideTheme()); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

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
  const st = flow.state;
  if (st === "stopped" || st === "changed" || st === "unknown" || st === "narrow") { flow.state = null; flow.step = 1; startTiming(); return; }
  if (st === "tray") { flow.state = null; api.setTray(true, false); paint(); return; }
  if (st) return;
  switch (flow.step) {
    case 0:
      if (flow.disc !== "ok") return;
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
  if (!flow || !isCal()) return;
  const t = T(), it = flow.item, kind = it.name.match(/BD|CD|DVD/)?.[0] ?? "DVD";
  const discWord = it.name.replace(/\s+\d+x$/, "");
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
